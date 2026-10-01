"""Frozen regional geometry, original-OSM remapping and measured subprocesses."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from pyproj import Geod, Transformer
import shapely

from _common import ROOT, sha256
from envelope.boundary import read_poly

GEOD = Geod(ellps='WGS84')


def region_polygon(config, margin_km=None):
    path = ROOT / config['base_polygon']
    if sha256(path) != config['base_polygon_sha256']:
        raise ValueError('Base polygon checksum mismatch')
    forward = Transformer.from_crs(4326, config['projection'], always_xy=True)
    reverse = Transformer.from_crs(config['projection'], 4326, always_xy=True)
    base = shapely.transform(read_poly(path), forward.transform, interleaved=False)
    margin = config['buffer_km'] if margin_km is None else margin_km
    if not np.isfinite(margin) or margin <= 0:
        raise ValueError('Buffer distance must be finite and positive')
    buffered = base.buffer(margin * 1000, quad_segs=config['buffer_quad_segs'])
    polygon = shapely.transform(buffered, reverse.transform, interleaved=False)
    return polygon, buffered, base


def polygon_bytes(polygon):
    """Canonical GeoJSON bytes are the extraction contract, including full precision."""
    if polygon.is_empty or not polygon.is_valid or polygon.geom_type not in ('Polygon', 'MultiPolygon'):
        raise ValueError('Invalid extraction geometry')
    return (json.dumps({'type': 'Feature', 'properties': {},
                        'geometry': shapely.geometry.mapping(polygon)},
                       sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def coordinate_distance_m(a, b):
    return float(GEOD.inv(float(a.lon), float(a.lat), float(b.lon), float(b.lat))[2])


def remap_osm_nodes(old_nodes, new_nodes, old_ids, tolerance_m):
    """Never reuse contiguous IDs or silently resnap a missing original identity."""
    if not old_nodes.osm_node_id.is_unique or not new_nodes.osm_node_id.is_unique:
        raise ValueError('Duplicate original OSM node identities')
    lookup = new_nodes.set_index('osm_node_id')
    records = []
    for node in np.unique(old_ids):
        old = old_nodes.loc[old_nodes.node_id.eq(node)].iloc[0]
        if int(old.osm_node_id) not in lookup.index:
            raise ValueError(f'Missing OSM node {int(old.osm_node_id)}')
        new = lookup.loc[int(old.osm_node_id)]
        delta = coordinate_distance_m(old, new)
        if delta > tolerance_m:
            raise ValueError(f'Coordinate drift for OSM node {int(old.osm_node_id)}: {delta} m')
        records.append({'slovenia_node_id': int(node), 'osm_node_id': int(old.osm_node_id),
                        'extended_node_id': int(new.node_id), 'coordinate_delta_m': delta})
    return records


def available_memory_bytes():
    fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(fields['MemAvailable'].split()[0]) * 1024


def tree_rss_bytes(pid):
    """Count Linux process descendants without an additional runtime dependency."""
    total, pending = 0, [pid]
    while pending:
        current = pending.pop()
        try:
            status = Path(f'/proc/{current}/status').read_text()
            rss = next(line for line in status.splitlines() if line.startswith('VmRSS:'))
            total += int(rss.split()[1]) * 1024
            children = Path(f'/proc/{current}/task/{current}/children').read_text().split()
            pending.extend(map(int, children))
        except (FileNotFoundError, ProcessLookupError, StopIteration):
            pass
    return total


def measured_command(command, output_record, *, rss_limit_gib=38, reserve_gib=10, interval=0.5):
    """External time captures child high-water RSS; live monitoring prevents unsafe growth."""
    output_record = Path(output_record)
    if rss_limit_gib <= 0 or reserve_gib < 0 or interval <= 0:
        raise ValueError('Invalid memory-monitor limits')
    output_record.parent.mkdir(parents=True, exist_ok=True)
    timing = output_record.with_suffix('.time.txt')
    stdout = output_record.with_suffix('.stdout.txt')
    started = time.perf_counter()
    peak, minimum_available, aborted = 0, available_memory_bytes(), None
    with stdout.open('w') as log:
        process = subprocess.Popen(['/usr/bin/time', '-v', '-o', str(timing), *map(str, command)],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                   env={**os.environ, 'OSMIUM_POOL_THREADS': '1'})
        while process.poll() is None:
            rss, available = tree_rss_bytes(process.pid), available_memory_bytes()
            peak, minimum_available = max(peak, rss), min(minimum_available, available)
            if rss > rss_limit_gib * 2**30 or available < reserve_gib * 2**30:
                aborted = 'RSS limit' if rss > rss_limit_gib * 2**30 else 'available-memory reserve'
                os.killpg(process.pid, 15)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, 9)
                break
            time.sleep(interval)
        code = process.wait()
    record = {'command': list(map(str, command)), 'elapsed_seconds': time.perf_counter() - started,
              'exit_code': code, 'sampled_tree_peak_rss_mib': peak / 2**20,
              'minimum_available_gib': minimum_available / 2**30, 'aborted': aborted,
              'monitor_interval_s': interval,
              'osmium_pool_threads': 1,
              'stdout': str(stdout.relative_to(ROOT)) if stdout.is_relative_to(ROOT) else str(stdout)}
    if timing.exists():
        for line in timing.read_text().splitlines():
            if 'Maximum resident set size (kbytes):' in line:
                record['process_peak_rss_mib'] = int(line.rsplit(':', 1)[1]) / 1024
    output_record.write_text(json.dumps(record, indent=2) + '\n')
    if code or aborted:
        raise RuntimeError(f'Command failed ({aborted or code}); inspect {stdout}')
    return record
