"""Compare unchanged Slovenia ODs with their original OSM identities in the region."""
from __future__ import annotations

import argparse
import json
import resource
import time

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from _common import ROOT, configs, load_graph, read_config, record_run, sha256, verified_dataset
from _envelope_common import envelope_config, fingerprints
from _regional_common import GEOD, remap_osm_nodes
from envelope import NumericalTolerance, build_envelope_from_precomputed, precompute_detour_distances
from envelope.boundary import boundary_node_risk, read_poly
from envelope.expansion import FixedSchedulePolicy, iter_policy_envelopes
from envelope.sampling import sample_waypoint_paths
from run_envelope_benchmark import distribution


def validate_comparison_schema(frame):
    required = {'instance_id', 'ratio', 'si_nodes', 'ext_nodes', 'si_edges', 'ext_edges',
                'si_budget_s', 'ext_budget_s', 'si_boundary_risk', 'ext_boundary_risk',
                'si_dataset_sha256', 'ext_dataset_sha256', 'routing_config_sha256',
                'od_instances_sha256', 'boundary_sha256'}
    if required - set(frame.columns):
        raise ValueError(f'Missing cross-dataset fields: {sorted(required-set(frame.columns))}')
    if frame.duplicated(['instance_id', 'ratio']).any() or frame[list(required)].isna().any().any():
        raise ValueError('Duplicate or null cross-dataset records')
    if (frame[['si_nodes', 'ext_nodes', 'si_edges', 'ext_edges']] < 0).any().any():
        raise ValueError('Negative envelope sizes')
    if not np.isfinite(frame[['si_budget_s', 'ext_budget_s']].to_numpy()).all():
        raise ValueError('Nonfinite cross-dataset budgets')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='configs/regional.yaml')
    args = parser.parse_args()
    config = read_config(args.config)
    envelope_config_ = envelope_config()
    data, routing = configs('configs/data_extended.yaml')
    if data['results_dir'] != config['results_dir'] or data['graph_dir'] != config['graph_dir']:
        raise ValueError('Regional benchmark output/configuration mismatch')
    si_data, _ = configs()
    verified_dataset(data)
    verified_dataset(si_data)
    si_provenance = fingerprints(si_data)
    metadata = json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())
    provenance = {**si_provenance, 'dataset_sha256': data['dataset']['sha256'],
                  'graph_nodes_sha256': metadata['files']['nodes.parquet']['sha256'],
                  'graph_edges_sha256': metadata['files']['edges.parquet']['sha256']}
    output = ROOT/config['results_dir']
    run = record_run('regional_benchmark', data, {'routing': routing, 'envelope': envelope_config_, 'regional': config}, config['seed'])
    design = json.loads((output/'region_design.json').read_text())
    if sha256(ROOT/config['polygon_path']) != design['polygon_sha256']:
        raise ValueError('Frozen extraction polygon changed')
    polygon = shape(json.loads((ROOT/config['polygon_path']).read_text())['geometry'])
    start = time.perf_counter()
    graph = load_graph(data, routing)
    load_seconds = time.perf_counter()-start
    nodes_si = pd.read_parquet(ROOT/si_data['graph_dir']/'nodes.parquet')
    instances = pd.read_parquet(ROOT/si_data['instances_path'])
    instance_meta = json.loads((ROOT/si_data['instances_path']).with_suffix('.metadata.json').read_text())
    if len(instances) != 30 or sha256(ROOT/si_data['instances_path']) != instance_meta['sha256']:
        raise ValueError('Expected the unchanged 30 original ODs')
    if not instances.dataset_sha256.eq(si_provenance['dataset_sha256']).all() or not instances.graph_edges_sha256.eq(si_provenance['graph_edges_sha256']).all():
        raise ValueError('Original ODs belong to a different graph')
    edge_identity_columns=['osm_way_id','source_osm','target_osm','direction']
    original_edge_ids=np.unique(np.concatenate(instances.path_edges.to_list()))
    original_edges=pd.read_parquet(ROOT/si_data['graph_dir']/'edges.parquet',
                                  columns=edge_identity_columns).iloc[original_edge_ids]
    extended_edges=pd.read_parquet(ROOT/data['graph_dir']/'edges.parquet',columns=edge_identity_columns)
    remapping = pd.DataFrame(remap_osm_nodes(nodes_si, graph.nodes,
        instances[['origin_node','destination_node']].to_numpy().ravel(), config['coordinate_tolerance_m']))
    remapping.to_parquet(output/'node_remapping.parquet', index=False)
    mapping = remapping.set_index('slovenia_node_id').extended_node_id.to_dict()
    risk, x, y = boundary_node_risk(graph.nodes.lat.to_numpy(), graph.nodes.lon.to_numpy(),
        polygon, config['projection'], config['boundary_margin_m'])
    from pyproj import Transformer
    transform = Transformer.from_crs(4326, config['projection'], always_xy=True)
    coverage_paths = [output/'boundary'/(name+'.poly') for name in
                      ['austria','nord-est','croatia','hungary','bosnia-herzegovina']]
    for path in coverage_paths:
        if sha256(path) != design['coverage_polygon_sha256'][path.name]:
            raise ValueError('Archived source-coverage polygon changed')
    source_coverage = shapely.union_all([read_poly(ROOT/config['base_polygon']),
                                       *[read_poly(path) for path in coverage_paths]])
    projected_polygon=shapely.transform(polygon,transform.transform,interleaved=False)
    projected_coverage=shapely.transform(source_coverage,transform.transform,interleaved=False)
    source_gap = projected_polygon.difference(projected_coverage)
    gap_margin = source_gap.buffer(config['boundary_margin_m'])
    shapely.prepare(gap_margin)
    source_gap_risk = shapely.contains_xy(gap_margin,x,y)
    cell_x = np.floor(x/config['map_grid_m']).astype(np.int64)
    cell_y = np.floor(y/config['map_grid_m']).astype(np.int64)
    # Stable integer cell encoding; cells may be negative in general.
    width = int(cell_x.max()-cell_x.min()+1)
    cells = (cell_y-cell_y.min())*width+(cell_x-cell_x.min())
    tolerance = NumericalTolerance(**envelope_config_['numerical_tolerance'])
    ratios = envelope_config_['detour_ratios']
    policy = FixedSchedulePolicy(tuple(ratios), envelope_config_['max_ratio'])
    rows, baselines, timings, checks, od_rows = [], [], [], [], []
    started = time.perf_counter()
    for od in instances.itertuples():
        origin, destination = int(mapping[od.origin_node]), int(mapping[od.destination_node])
        deltas = {}
        for side, node in [('origin', origin), ('destination', destination)]:
            requested_lon, requested_lat = getattr(od,side+'_lon'), getattr(od,side+'_lat')
            snapped = graph.nodes.iloc[node]
            snap = float(GEOD.inv(requested_lon,requested_lat,float(snapped.lon),float(snapped.lat))[2])
            if abs(snap-getattr(od,side+'_snap_m')) > config['coordinate_tolerance_m']:
                raise RuntimeError('OD remapping altered the original snap')
            deltas[side+'_snap_geodesic_m'] = snap
            deltas[side+'_snap_delta_m'] = snap-getattr(od,side+'_snap_m')
            deltas[side+'_osm_node_id'] = int(snapped.osm_node_id)
        route_start = time.perf_counter()
        route = graph.shortest_path(origin,destination)
        route_seconds = time.perf_counter()-route_start
        graph.validate_route(route)
        old_sequence = nodes_si.iloc[list(od.path_nodes)].osm_node_id.astype(int).tolist()
        new_sequence = graph.nodes.iloc[list(route.nodes)].osm_node_id.astype(int).tolist()
        old_osm, new_osm = set(old_sequence), set(new_sequence)
        old_edge_sequence=list(original_edges.loc[list(od.path_edges),edge_identity_columns].itertuples(index=False,name=None))
        new_edge_sequence=list(extended_edges.iloc[list(route.edge_ids)].itertuples(index=False,name=None))
        old_edge_set,new_edge_set=set(old_edge_sequence),set(new_edge_sequence)
        absolute = route.travel_time_s-od.shortest_path_travel_time_s
        relative = absolute/od.shortest_path_travel_time_s
        baseline = {'instance_id': int(od.instance_id), 'origin_city': od.origin_city,
            'destination_city': od.destination_city, 'si_baseline_time_s': od.shortest_path_travel_time_s,
            'ext_baseline_time_s': route.travel_time_s, 'time_difference_s': absolute,
            'absolute_time_difference_s': abs(absolute), 'relative_time_difference': relative,
            'si_fastest_distance_m': od.fastest_path_distance_m, 'ext_fastest_distance_m': route.distance_m,
            'si_shortest_distance_m': od.shortest_path_distance_m,
            'ext_shortest_distance_m': graph.shortest_path_cost(origin,destination,'distance'),
            'route_osm_node_jaccard': len(old_osm & new_osm)/len(old_osm | new_osm),
            'original_route_node_fraction_retained': len(old_osm & new_osm)/len(old_osm),
            'route_osm_edge_jaccard': len(old_edge_set & new_edge_set)/len(old_edge_set | new_edge_set),
            'original_route_edge_fraction_retained': len(old_edge_set & new_edge_set)/len(old_edge_set),
            'material_time_change': abs(relative) >= config['material_route_change_relative'],
            'route_topology_changed': old_edge_sequence != new_edge_sequence,
            'route_seconds': route_seconds, **deltas, **provenance}
        baselines.append(baseline)
        od_rows.append({'instance_id': int(od.instance_id), 'si_origin_node': int(od.origin_node),
                       'si_destination_node': int(od.destination_node), 'origin_node': origin,
                       'destination_node': destination, 'path_nodes': list(route.nodes),
                       'path_edges': list(route.edge_ids), **baseline})
        distances = precompute_detour_distances(graph, origin, destination, envelope_config_['cost'])
        if abs(distances.baseline_cost-route.travel_time_s) > tolerance.allowance(route.travel_time_s):
            raise RuntimeError('Extended baseline route and distances disagree')
        if abs(distances.reverse_distances[origin]-distances.baseline_cost) > tolerance.allowance(distances.baseline_cost):
            raise RuntimeError('Forward/reverse costs disagree')
        paths = sample_waypoint_paths(graph,distances,envelope_config_['seed']+int(od.instance_id),
            envelope_config_['sampling']['waypoint_count'],envelope_config_['sampling']['waypoint_ratios'])
        timings.append({'instance_id': int(od.instance_id), 'forward_seconds': distances.forward_seconds,
            'reverse_seconds': distances.reverse_seconds, 'lower_bound_seconds': distances.lower_bound_seconds,
            'precomputed_bytes': distances.storage_bytes, **provenance})
        iterator = iter_policy_envelopes(distances,policy,envelope_config_['max_ratio']*distances.baseline_cost,tolerance)
        previous = None
        previous_nodes, previous_edges = 0,0
        for ratio in ratios:
            start = time.perf_counter()
            envelope = next(iterator)
            measurements = [time.perf_counter()-start]
            for _ in range(envelope_config_['benchmark']['mask_repeats']-1):
                start = time.perf_counter()
                repeated = build_envelope_from_precomputed(distances,envelope.budget,tolerance)
                measurements.append(time.perf_counter()-start)
                if not np.array_equal(repeated.node_mask,envelope.node_mask) or not np.array_equal(repeated.edge_mask,envelope.edge_mask):
                    raise RuntimeError('Nondeterministic masks')
                del repeated
            if previous is not None and ((previous.node_mask & ~envelope.node_mask).any() or (previous.edge_mask & ~envelope.edge_mask).any()):
                raise RuntimeError('Nesting violation')
            if (envelope.edge_mask & ~(envelope.node_mask[graph.source] & envelope.node_mask[graph.target])).any():
                raise RuntimeError('Retained edge endpoints omitted')
            if not envelope.node_mask[list(route.nodes)].all() or not envelope.edge_mask[list(route.edge_ids)].all():
                raise RuntimeError('Baseline containment violation')
            for path in paths:
                within = path.base_cost <= envelope.budget+tolerance.allowance(envelope.budget)
                contained = bool(envelope.node_mask[path.nodes].all() and envelope.edge_mask[path.edges].all())
                checks.append({'instance_id': int(od.instance_id), 'ratio': ratio,
                    'sample_id': path.sample_id, 'path_cost_s': path.base_cost, 'budget_s': envelope.budget,
                    'within_budget': within, 'contained': contained, 'violation': within and not contained,
                    'path_sha256': path.fingerprint, **provenance})
                if within and not contained:
                    raise RuntimeError('Bounded-path containment violation')
            n,e = int(envelope.node_mask.sum()),int(envelope.edge_mask.sum())
            included_x,included_y = x[envelope.node_mask],y[envelope.node_mask]
            occupied = len(np.unique(cells[envelope.node_mask]))
            near = int(np.count_nonzero(risk & envelope.node_mask))
            gap_near = int(np.count_nonzero(source_gap_risk & envelope.node_mask))
            rows.append({'instance_id': int(od.instance_id), 'ratio': ratio, 'cost': distances.cost,
                'unit': distances.unit, 'baseline_cost': distances.baseline_cost, 'budget': envelope.budget,
                'nodes': n, 'edges': e, 'node_percent': 100*n/graph.node_count, 'edge_percent': 100*e/graph.edge_count,
                'delta_nodes': n-previous_nodes, 'delta_edges': e-previous_edges,
                'marginal_from_previous': previous is not None,
                'occupied_grid_area_km2': occupied*config['map_grid_m']**2/1e6,
                'bbox_area_km2': (included_x.max()-included_x.min())*(included_y.max()-included_y.min())/1e6,
                'extent_x_min_m': included_x.min(), 'extent_x_max_m': included_x.max(),
                'extent_y_min_m': included_y.min(), 'extent_y_max_m': included_y.max(),
                'near_boundary_nodes': near, 'near_source_gap_nodes': gap_near,
                'crop_boundary_risk': near>0, 'source_gap_risk': gap_near>0,
                'boundary_risk': near>0 or gap_near>0,
                'boundary_sha256': design['polygon_sha256'], 'build_ms': float(np.median(measurements)*1000),
                'mask_bytes': envelope.mask_bytes, 'precomputed_bytes': distances.storage_bytes,
                **provenance})
            previous = envelope
            previous_nodes,previous_edges=n,e
        print(f'OD {od.instance_id:02d}: baseline change {relative:+.2%}; forward {distances.forward_seconds:.2f}s; reverse {distances.reverse_seconds:.2f}s; max {n:,} nodes, boundary={near>0}',flush=True)
        del iterator,previous,envelope,distances,paths
    table = pd.DataFrame(rows)
    table[['instance_id','ratio','boundary_risk','crop_boundary_risk','source_gap_risk',
           'near_boundary_nodes','near_source_gap_nodes','boundary_sha256',*provenance]].to_parquet(
               output/'boundary_diagnostics.parquet',index=False)
    for name, frame in [('envelope_stats',table),('baseline_comparison',pd.DataFrame(baselines)),
                        ('distance_benchmark',pd.DataFrame(timings)),('path_containment_tests',pd.DataFrame(checks)),
                        ('od_remapping',pd.DataFrame(od_rows))]:
        frame.to_parquet(output/(name+'.parquet'),index=False,compression='zstd')
        if name in ('baseline_comparison','distance_benchmark'):
            frame.to_csv(output/(name+'.csv'),index=False)
    si = pd.read_parquet(ROOT/'results/milestone_2/envelope_stats.parquet')
    si = si.rename(columns={name:'si_'+name for name in si.columns if name not in ('instance_id','ratio')})
    ext = table.rename(columns={name:'ext_'+name for name in table.columns if name not in ('instance_id','ratio')})
    comparison = si.merge(ext,on=['instance_id','ratio'],validate='one_to_one')
    comparison['si_budget_s'],comparison['ext_budget_s']=comparison.si_budget,comparison.ext_budget
    comparison['routing_config_sha256']=provenance['routing_config_sha256']
    comparison['od_instances_sha256']=provenance['od_instances_sha256']
    comparison['boundary_sha256']=design['polygon_sha256']
    comparison['si_boundary_sha256']=envelope_config_['boundary']['sha256']
    validate_comparison_schema(comparison)
    comparison.to_parquet(output/'envelope_comparison.parquet',index=False)
    comparison.to_csv(output/'envelope_comparison.csv',index=False)
    growth = table.groupby('ratio').agg(nodes_median=('nodes','median'),edges_median=('edges','median'),
        delta_nodes_median=('delta_nodes','median'),delta_edges_median=('delta_edges','median'),
        occupied_grid_area_km2_median=('occupied_grid_area_km2','median'),
        bbox_area_km2_median=('bbox_area_km2','median'),boundary_risk_ods=('boundary_risk','sum'),
        crop_boundary_risk_ods=('crop_boundary_risk','sum'),
        source_gap_risk_ods=('source_gap_risk','sum')).reset_index()
    original_growth = si.groupby('ratio').agg(si_nodes_median=('si_nodes','median'),
        si_edges_median=('si_edges','median'),si_bbox_area_km2_median=('si_bbox_area_km2','median'),
        si_boundary_risk_ods=('si_boundary_risk','sum')).reset_index()
    growth = growth.merge(original_growth,on='ratio',validate='one_to_one')
    growth.to_csv(output/'envelope_growth.csv',index=False)
    growth.to_parquet(output/'envelope_growth.parquet',index=False)
    meta = json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())
    result = {'run': run, 'provenance': provenance, 'slovenia_provenance': si_provenance,
              'node_count': graph.node_count, 'edge_count': graph.edge_count,
              'graph_storage_bytes': sum(p.stat().st_size for p in (ROOT/data['graph_dir']).iterdir() if p.is_file()),
              'load_seconds': load_seconds, 'experiment_seconds': time.perf_counter()-started,
              'process_peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
              'preprocessing_seconds': meta['preprocessing_seconds'], 'preprocessing_peak_rss_mib': meta['process_peak_rss_mib'],
              'forward_seconds': distribution(pd.DataFrame(timings).forward_seconds),
              'reverse_seconds': distribution(pd.DataFrame(timings).reverse_seconds),
              'mask_ms': distribution(table.build_ms),
              'material_time_change_ods': [b['instance_id'] for b in baselines if b['material_time_change']],
              'topology_changed_ods': [b['instance_id'] for b in baselines if b['route_topology_changed']],
              'containment_checks': len(checks), 'containment_violations': sum(c['violation'] for c in checks),
              'growth': growth.to_dict('records'), 'comparison_budget_basis': 'each dataset own baseline C*',
              'spatial_area_definition': 'occupied 1 km square cells containing envelope vertices, not land area or reachable-area measure',
              'routing_configuration_identical': meta['run']['configuration']['routing'] == routing}
    result['source_gap_area_km2'] = source_gap.area/1e6
    result['source_gap_proximity_ods'] = int(table.groupby('instance_id').source_gap_risk.any().sum())
    result['files'] = {p.name:sha256(p) for p in output.glob('*.parquet')}
    (output/'benchmark.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('run','growth','provenance','slovenia_provenance')},indent=2))


if __name__ == '__main__':
    main()
