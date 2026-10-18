"""Plan fixed geographic partitions and validate/aggregate their physical screens.

Only combines producer receipts; never runs routing or optimization. JSON output
is deterministic for identical source bytes. Candidate order and >450001m cutoff
are frozen and are not selected using route outcomes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

CUTOFF = 450001000000
INTEGER_LIMIT = 10000000000000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def read(path: Path) -> dict:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'duplicate JSON key: {key}')
            result[key] = value
        return result
    result = json.loads(path.read_text(), object_pairs_hook=reject_duplicates,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    require(isinstance(result, dict), f'Expected object: {path}')
    return result


def candidates(screen: dict) -> list[dict]:
    require(screen.get('schema') == 'hiroute.m5d.geographic_screen.v1', 'Geographic schema mismatch')
    rows = screen['fixed_grid_candidates']
    require(len(rows) >= 2 and screen['fixed_grid_candidate_count'] == len(rows), 'Candidate count mismatch')
    require(len({r['site_id'] for r in rows}) == len(rows), 'Duplicate candidate site')
    require(len({(r['lat_cell'], r['lon_cell']) for r in rows}) == len(rows), 'Duplicate grid cell')
    require(rows == sorted(rows, key=lambda r: (r['lat_cell'], r['lon_cell'])), 'Candidate grid order changed')
    require(all(type(r['access_node']) is int and r['access_node'] >= 0 for r in rows), 'Invalid candidate anchor')
    require(digest(screen['nodes_sha256']) and digest(screen['sites_sha256']), 'Invalid geographic source identity')
    return rows


def read_config(path: Path) -> dict:
    config = read(path)
    require(config.get('schema') == 'hiroute.m5d.fixed_screen_config.v1', 'Config schema mismatch')
    require(config['candidate_order'] == ['lat_cell', 'lon_cell'] and
            config['long_pair_cutoff_micrometers_exclusive'] == CUTOFF and
            config['integer_cutoff_micrometers'] == INTEGER_LIMIT,
            'Config changes frozen producer cutoff/order')
    require(type(config['grid_size']) is int and 2 <= config['grid_size'] <= 20, 'Invalid grid size')
    require(type(config['partition_count']) is int and config['partition_count'] > 0, 'Invalid partition count')
    for key in ('expected_candidate_count', 'expected_long_pair_count'):
        require(type(config[key]) is int and config[key] >= 0, f'Invalid {key}')
    require(config['source_inputs'] == {
        'graph_root': 'runtime:GRAPH', 'nodes': 'nodes.parquet', 'edges': 'edges.parquet',
        'metadata': 'metadata.json', 'attached_sites': 'runtime:SITES',
        'output_root': 'runtime:RUN', 'geographic_screen': 'geographic_screen_v5_grid14.json'},
        'Unsupported source input references')
    return config


def partition_plan(geographic: Path, count: int = 4, config_path: Path | None = None) -> dict:
    screen = read(geographic)
    rows = candidates(screen)
    config = read_config(config_path) if config_path else None
    if config:
        count = config['partition_count']
        require(len(rows) == config['expected_candidate_count'], 'Configured candidate population changed')
        require(geographic.name == config['source_inputs']['geographic_screen'], 'Configured geographic filename mismatch')
        require(screen.get('fixed_grid_rule') ==
                f"one_nearest_attached_site_per_populated_cell_in_{config['grid_size']}x{config['grid_size']}_lat_lon_bounds",
                'Configured grid rule mismatch')
    require(type(count) is int and 1 <= count <= len(rows), 'Invalid partition count')
    # ceil-sized contiguous partitions reproduce [0,40),[40,80),[80,120),[120,158).
    size = (len(rows) + count - 1) // count
    ranges = []
    start = 0
    for index in range(count):
        stop = min(start + size, len(rows) - (count - index - 1))
        ranges.append([start, stop])
        start = stop
    result = {'schema': 'hiroute.m5d.fixed_screen_partition_plan.v1',
            'geographic_screen_sha256': sha(geographic), 'candidate_count': len(rows),
            'long_pair_cutoff_micrometers_exclusive': CUTOFF,
            'partitions': [{'index': i, 'origin_partition': bounds,
                            'distance_file': f'grid14_distance_p{i}.json',
                            'potential_file': f'grid14_potential_p{i}.json'}
                           for i, bounds in enumerate(ranges)]}
    if config_path:
        result['config_sha256'] = sha(config_path)
        result['experiment_id'] = config['experiment_id']
        result['source_inputs'] = config['source_inputs']
    return result


def aggregate(geographic: Path, plan_path: Path, directory: Path,
              frozen_population: bool = False, config_path: Path | None = None) -> dict:
    screen = read(geographic)
    sites = candidates(screen)
    plan = read(plan_path)
    expected = partition_plan(geographic, len(plan['partitions']), config_path)
    require(plan == expected, 'Partition plan/source/order mismatch')
    sources = {geographic.name: sha(geographic)}
    require(geographic.name not in {p[k] for p in plan['partitions'] for k in ('distance_file', 'potential_file')},
            'Source filename collision')
    partitions, checks, long_rows = [], [], []
    graph_edges = None
    finite_total = 0
    for part in plan['partitions']:
        path = directory / part['distance_file']
        proof_path = directory / part['potential_file']
        data, proof = read(path), read(proof_path)
        require(data.get('schema') == 'hiroute.m5d.extrema_native_distance_screen.v1', 'Distance schema mismatch')
        require(proof.get('schema') == 'hiroute.m5d.distance_potential_check.v1', 'Potential schema mismatch')
        require(data['geographic_screen_sha256'] == sha(geographic), 'Geographic identity mismatch')
        require(data['candidate_mode'] == 'all_grid' and data['candidate_count'] == len(sites), 'Candidate mode/count mismatch')
        require(data['distance_mode'] == 'integer_micrometer_lower_bound' and
                data['integer_cutoff_micrometers'] == INTEGER_LIMIT and
                data['one_metre_selected_route_rounding_margin'] is True, 'Distance mode/cutoff mismatch')
        require(data['origin_partition'] == part['origin_partition'], 'Partition bounds mismatch')
        for key in ('graph_nodes_sha256', 'graph_edges_sha256', 'native_router_sha256'):
            require(digest(data[key]) and proof[key] == data[key], f'Proof identity mismatch: {key}')
        require(data['graph_nodes_sha256'] == screen['nodes_sha256'], 'Graph nodes mismatch')
        if graph_edges is None:
            graph_edges = data['graph_edges_sha256']
        require(graph_edges == data['graph_edges_sha256'], 'Partitions use different graph edges')
        require(digest(data['tool_sha256']) and digest(proof['tool_sha256']), 'Invalid producer identity')
        require(proof['pair_screen_sha256'] == sha(path), 'Potential receipt source mismatch')
        start, stop = part['origin_partition']
        pairs = [(a, b) for a in sites[start:stop] for b in sites if a['site_id'] != b['site_id']]
        rows = data['pairs']
        require(len(rows) == len(pairs) == data['pair_count'], 'Incomplete pair coverage')
        for row, (a, b) in zip(rows, pairs):
            require((row['origin_site'], row['destination_site'], row['origin_anchor'], row['destination_anchor']) ==
                    (a['site_id'], b['site_id'], a['access_node'], b['access_node']), 'Pair identity/order/duplicate mismatch')
            value = row['integer_micrometers']
            require(value is None or (type(value) is int and 0 <= value <= INTEGER_LIMIT), 'Invalid integer distance')
            require(row['distance_cost_m'] == (None if value is None else value / 1000000), 'Distance unit mismatch')
        finite = sum(r['integer_micrometers'] is not None for r in rows)
        long = [r for r in rows if r['integer_micrometers'] is not None and r['integer_micrometers'] > CUTOFF]
        require(finite == data['finite_pair_count'] and len(long) == data['pairs_over_450km'], 'Distance summary mismatch')
        roots = sorted({r['origin_anchor'] for r in long})
        audits = proof['audits']
        require([a['root'] for a in audits] == roots and proof['verified_root_count'] == len(roots), 'Independent root coverage mismatch')
        targets = Counter(r['origin_anchor'] for r in rows)
        for audit in audits:
            require(audit['matched_screened_targets'] == targets[audit['root']], 'Independent target coverage mismatch')
            require(type(audit['reached_node_count']) is int and audit['reached_node_count'] > 0 and
                    type(audit['checked_reached_edges']) is int and audit['checked_reached_edges'] >= 0 and
                    digest(audit['label_sha256']), 'Invalid independent audit')
        margin = proof['selected_leg_rounding_error_upper_m']
        require(isinstance(margin, (int, float)) and not isinstance(margin, bool) and
                math.isfinite(margin) and 0 <= margin < 1 and proof['one_metre_margin_passed'] is True,
                'Independent rounding margin failed')
        require(proof['verified_long_pair_count'] == len(long), 'Independent long-pair count mismatch')
        sources[path.name], sources[proof_path.name] = sha(path), sha(proof_path)
        partitions.append({'partition': [start, stop], 'pairs': len(rows), 'finite': finite,
                           'over_450001m': len(long)})
        checks.append({'partition': part['index'], 'receipt_sha256': sha(proof_path),
                       'verified_long_pairs': len(long), 'verified_roots': len(roots)})
        finite_total += finite
        long_rows.extend(long)
    if config_path:
        config = read_config(config_path)
        require(len(long_rows) == config['expected_long_pair_count'], 'Configured long-pair population changed')
    if frozen_population:
        require(screen.get('fixed_grid_rule') == 'one_nearest_attached_site_per_populated_cell_in_14x14_lat_lon_bounds'
                and len(sites) == 158 and len(partitions) == 4 and len(long_rows) == 140,
                'Frozen grid14 population changed; do not replace candidates')
    result = {'schema': 'hiroute.m5d.grid14_fixed_screen_aggregate.v1',
            'source_sha256': sources, 'partition_plan_sha256': sha(plan_path),
            'tool_sha256': sha(Path(__file__)), 'graph_nodes_sha256': screen['nodes_sha256'],
            'graph_edges_sha256': graph_edges, 'anchor_count': len(sites),
            'directed_pair_count': len(sites) * (len(sites) - 1), 'finite_pair_count': finite_total,
            'over_450001m_pair_count': len(long_rows), 'independent_checked_long_pairs': len(long_rows),
            'independent_checked_origins_by_partition': sum(c['verified_roots'] for c in checks),
            'distinct_long_pair_origins': len({r['origin_site'] for r in long_rows}),
            'distinct_long_pair_destinations': len({r['destination_site'] for r in long_rows}),
            'partitions': partitions, 'independent_edge_potential_checks': checks,
            'long_pair_cutoff_micrometers_exclusive': CUTOFF,
            'no_new_grid_refinement': True, 'preserved_input_results': True,
            'interpretation': 'Pre-comparison physical candidate screen only; long pairs are not verified two-charge query states.'}
    if config_path:
        result['config_sha256'] = sha(config_path)
        result['experiment_id'] = config['experiment_id']
        result['source_inputs'] = config['source_inputs']
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'aggregate'))
    parser.add_argument('--geographic-screen', type=Path, required=True)
    parser.add_argument('--partition-count', type=int, default=4)
    parser.add_argument('--config', type=Path, help='Versioned experiment config; binds plan and expected population')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--input-dir', type=Path)
    parser.add_argument('--require-frozen-population', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; use a fresh run directory')
    if args.action == 'aggregate' and (args.plan is None or args.input_dir is None):
        parser.error('aggregate requires --plan and --input-dir')
    result = (partition_plan(args.geographic_screen, args.partition_count, args.config) if args.action == 'plan'
              else aggregate(args.geographic_screen, args.plan, args.input_dir, args.require_frozen_population, args.config))
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
