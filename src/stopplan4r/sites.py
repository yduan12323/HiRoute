"""One Site per raw transport identity; indexed aggregate local support only."""
from dataclasses import asdict
import time

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from graph.road_graph import unit_sphere
from .models import LocalSupport, StopSite, TRANSPORT

EARTH_RADIUS_M = 6371008.8
STATIC_COLUMNS = frozenset({
    'site_id', 'osm_type', 'osm_id', 'lat', 'lon', 'access_node',
    'transport_capabilities', 'original_tags', 'access_osm_node_id',
    'access_distance_m', 'attachment_status', 'geometry_type', 'geometry_method',
    'source_datasets', 'snapshot_timestamp', 'support_radius_m', 'support_method',
    'meal_count', 'nearest_meal_m', 'toilet_count', 'nearest_toilet_m',
    'lodging_count', 'nearest_lodging_m'})


def validate_static_table(table):
    if set(table.columns) != STATIC_COLUMNS:
        raise ValueError(f'Static schema mismatch: {set(table.columns) ^ STATIC_COLUMNS}')
    if table.site_id.duplicated().any():
        raise ValueError('Duplicate Site identity')
    expected = '4r:' + table.osm_type.astype(str) + '/' + table.osm_id.astype(str)
    if not table.site_id.eq(expected).all():
        raise ValueError('Unstable Site identity')
    if not table.transport_capabilities.map(lambda c: len(c) > 0 and set(c) <= TRANSPORT).all():
        raise ValueError('Non-transport anchor')


def aggregate_support(inventory, anchors, radii_m=(250.0, 500.0, 750.0)):
    """Exact spherical distance within each radius, a proxy for human access.

    Counts retain raw OSM identities (including co-located objects); nearest
    distances are within-radius minima, null if no matching evidence exists.
    Query_ball_point(return_length=True) avoids materializing all pairs.
    """
    radii_m = tuple(sorted(set(map(float, radii_m))))
    if not radii_m or any(not np.isfinite(r) or not 0 < r < np.pi * EARTH_RADIUS_M for r in radii_m):
        raise ValueError('Invalid local support radius')
    start = time.perf_counter()
    xyz = unit_sphere(anchors.lat, anchors.lon)
    frames = {r: pd.DataFrame({'site_id': anchors.site_id.to_numpy(), 'radius_m': r,
                               'method': 'spherical_geographic_distance_proxy'}) for r in radii_m}
    index_stats = {}
    for name, capability in [('meal', 'meal'), ('toilet', 'toilets'), ('lodging', 'sleep')]:
        evidence = inventory[inventory.capabilities.map(lambda c: capability in c)]
        tree_start = time.perf_counter()
        tree = cKDTree(unit_sphere(evidence.lat, evidence.lon))
        build_s = time.perf_counter() - tree_start
        query_start = time.perf_counter()
        nearest, _ = tree.query(xyz)
        distance_m = 2 * EARTH_RADIUS_M * np.arcsin(np.minimum(nearest / 2, 1))
        for r, frame in frames.items():
            chord = 2 * np.sin(r / (2 * EARTH_RADIUS_M))
            frame[name + '_count'] = tree.query_ball_point(xyz, chord, return_length=True)
            frame['nearest_' + name + '_m'] = np.where(nearest <= chord, distance_m, np.nan)
        index_stats[name] = {'raw_evidence_count': len(evidence), 'index_build_s': build_s,
                            'queries_s': time.perf_counter() - query_start,
                            'coordinate_storage_bytes': tree.data.nbytes}
    return pd.concat(frames.values(), ignore_index=True), {
        'seconds': time.perf_counter() - start, 'indexes': index_stats,
        'method': 'cKDTree_on_unit_sphere; great_circle_proxy; raw_identity_counts'}


def build_sites(inventory, attachments, radii_m=(250.0, 500.0, 750.0), primary_radius_m=500.0):
    keys = ['osm_type', 'osm_id']
    if inventory.duplicated(keys).any() or attachments.duplicated(keys).any():
        raise ValueError('Duplicate source OSM identity')
    if set(zip(inventory.osm_type, inventory.osm_id)) != set(zip(attachments.osm_type, attachments.osm_id)):
        raise ValueError('Inventory/attachment identities disagree')
    if primary_radius_m not in radii_m:
        raise ValueError('Primary radius must be included')
    transport = inventory.capabilities.map(lambda c: sorted(set(c) & TRANSPORT))
    selected = inventory.loc[transport.map(bool)].drop(columns=['geometry_wkb', 'inside_polygon', 'subtype'], errors='ignore').copy()
    selected['transport_capabilities'] = transport.loc[selected.index]
    selected = selected.drop(columns='capabilities').merge(attachments, on=keys, validate='one_to_one')
    selected = selected.sort_values(keys).reset_index(drop=True)
    selected['site_id'] = '4r:' + selected.osm_type.astype(str) + '/' + selected.osm_id.astype(str)
    # Preserve unattached Sites as static anchors, with no routable node inferred.
    for column in ['access_node', 'access_osm_node_id']:
        selected[column] = selected[column].where(selected.attachment_status.eq('attached')).astype('Int64')
    support, stats = aggregate_support(inventory, selected, radii_m)
    primary = support[support.radius_m.eq(primary_radius_m)].rename(columns={'radius_m': 'support_radius_m', 'method': 'support_method'})
    table = selected.merge(primary, on='site_id', validate='one_to_one')
    table = table[sorted(STATIC_COLUMNS)]
    validate_static_table(table)
    return table, support, stats


def sites_from_table(table):
    validate_static_table(table)
    result = []
    for row in table.to_dict('records'):
        support = LocalSupport(radius_m=row.pop('support_radius_m'), method=row.pop('support_method'),
                               **{k: (None if pd.isna(row[k]) else row[k]) for k in asdict(LocalSupport()) if k not in ('radius_m', 'method')})
        for k in asdict(LocalSupport()):
            if k not in ('radius_m', 'method'):
                row.pop(k)
        for k in ['access_node', 'access_osm_node_id']:
            row[k] = None if pd.isna(row[k]) else int(row[k])
        row['source_datasets'] = tuple(row['source_datasets'])
        result.append(StopSite(**row, support=support))
    return tuple(result)
