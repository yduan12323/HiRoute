"""HELD source-only planner. No downloader, data reader, or execution bypass.

This is deliberately not an executable real-data adapter. A later reviewed
integration must bind the same enclosing Budget to preparation and the queue.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
PROJECTION = '+proj=lcc +lat_1=35 +lat_2=38 +lat_0=36.5 +lon_0=118.5 +datum=WGS84 +units=m +no_defs +type=crs'
SOURCE = 'https://download.geofabrik.de/asia/china/shandong-261016.osm.pbf'
STAGES = (
    ('source_freeze', 'stream dated PBF and publisher MD5; SHA256; exact size and header timestamp; freeze provider polygon separately'),
    ('road_filter', 'osmium tags-filter w/highway retaining references; no geographic subsetting beyond frozen province'),
    ('road_graph', 'build_graph normalize_network unchanged; unknown road class fails closed'),
    ('opportunity_extract', 'original taxonomy; smart extraction with relation types any; GeoJSON sequence'),
    ('inventory', 'same typed OSM identities and geometry priority; explicit regional projection'),
    ('attachments', 'attach_opportunities unchanged WGS84 nearest eligible road node'),
    ('sites', 'build_sites unchanged; all transport identities; original local support radii'),
    ('global_hierarchy', 'original bisection.cpp across ALL graph nodes and attached Sites, OSM identity rank, capacity 64; independent rebuild'),
    ('input_freeze', 'freeze graph/site/tree bytes, provenance and generation implementation before OD selection'),
    ('selection_and_queue', 'existing preregistered selection and fixed queue using SAME enclosing Budget'),
    ('terminal_receipt', 'external waited-process CPU/wall receipt includes final persistence and cleanup'),
)

class HeldError(RuntimeError):
    pass


def validate(config):
    if config.get('schema_version') != 1 or config.get('status') != 'HELD' or config.get('execution_enabled') is not False:
        raise HeldError('This implementation is source-only and cannot be enabled by editing configuration')
    source = config['source']
    if source['url'] != SOURCE or source['expected_size_bytes'] != 71651758 or source['snapshot_timestamp'] != '2026-10-16T20:21:21Z':
        raise ValueError('Proposed dated source contract changed')
    if source['sha256'] != '844f1de519e56f341b62e3d8f4c2db6984e32f1a8a5ca2a851e9ccdd35fc7464' or any(source[k] is not None for k in ('publisher_md5', 'polygon_sha256')):
        raise HeldError('Source hashes must remain unknown until authorized acquisition in a new reviewed protocol')
    if config['geometry']['projection'] != PROJECTION:
        raise ValueError('Public-geography projection proposal changed')
    r = config['resources']
    expected = {'cpu_seconds': 144000, 'wall_seconds': 172800,
                'sampled_tree_rss_bytes': 5*2**30, 'host_reserve_bytes': 2*2**30,
                'per_process_as_bytes': 8*2**30, 'threads': 1, 'monitor_interval_s': 0.1}
    if any(type(r.get(k)) not in (int, float) or r[k] != v for k,v in expected.items()):
        raise ValueError('Resource contract changed')
    if config.get('required_approvals') != ['user_data_scope', 'root_protocol_and_source_freeze']:
        raise ValueError('Approval requirements changed')
    return config


def plan(config):
    """Inspect supplied configuration only, never source/graph/catalogue paths."""
    validate(config)
    encoded = json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return {'status': 'HELD', 'config_sha256': hashlib.sha256(encoded).hexdigest(),
            'source_accessed': False, 'execution_available': False,
            'stages': [{'stage': name, 'contract': contract} for name,contract in STAGES],
            'unvalidated': ['real-data RAM/runtime', 'full-source projection/geometry coverage',
                            'first real-source bounded preprocessing',
                            'same-Budget integration and external terminal receipt', 'eligible OD count']}


def dependency_report():
    modules = ('numpy', 'scipy', 'pandas', 'pyarrow', 'pyrosm', 'pyproj', 'shapely', 'yaml', 'igraph')
    return {'python_modules': {m: importlib.util.find_spec(m) is not None for m in modules},
            'executables': {m: shutil.which(m) for m in ('osmium', 'g++', 'curl')}}


def execute(*args, **kwargs):
    # Deliberately unconditional, including direct calls; no approval CLI/token.
    raise HeldError('HELD: user data-scope approval and reviewed source/protocol freeze required; use gated pipeline adapter after review')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--dependencies', action='store_true')
    args = parser.parse_args()
    if args.execute:
        execute()  # Before even reading config.
    config = json.loads((HERE/'config.json').read_text())
    result = plan(config)
    if args.dependencies:
        result['dependencies'] = dependency_report()
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
