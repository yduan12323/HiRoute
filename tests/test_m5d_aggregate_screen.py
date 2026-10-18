"""Synthetic portable screens; no map, native router, or historical receipts."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('aggregate_screen', Path(__file__).parents[1] / 'scripts/m5d_aggregate_screen.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def write(path, data):
    path.write_text(json.dumps(data, sort_keys=True))


@pytest.fixture
def inputs(tmp_path):
    geo = tmp_path / 'geographic_screen_v5_grid14.json'
    sites = [dict(site_id=f'S{i}', access_node=i, lat_cell=i, lon_cell=0) for i in range(4)]
    write(geo, dict(schema='hiroute.m5d.geographic_screen.v1', nodes_sha256='a'*64,
                    sites_sha256='b'*64, fixed_grid_candidates=sites, fixed_grid_candidate_count=4))
    plan = module.partition_plan(geo, 2)
    plan_path = tmp_path / 'plan.json'
    write(plan_path, plan)
    for part in plan['partitions']:
        begin, end = part['origin_partition']
        rows = []
        for a in sites[begin:end]:
            for b in sites:
                if a == b:
                    continue
                # Exercise exact threshold, threshold+1, and unreachable rows.
                value = None if b['access_node'] == 3 else module.CUTOFF + (a['access_node'] % 2)
                rows.append(dict(origin_site=a['site_id'], destination_site=b['site_id'],
                                 origin_anchor=a['access_node'], destination_anchor=b['access_node'],
                                 integer_micrometers=value, distance_cost_m=None if value is None else value / 1e6))
        long = [r for r in rows if r['integer_micrometers'] is not None and r['integer_micrometers'] > module.CUTOFF]
        roots = sorted({r['origin_anchor'] for r in long})
        identities = dict(graph_nodes_sha256='a'*64, graph_edges_sha256='c'*64,
                          native_router_sha256='d'*64, tool_sha256='e'*64)
        distance = dict(schema='hiroute.m5d.extrema_native_distance_screen.v1', **identities,
                        geographic_screen_sha256=module.sha(geo), candidate_mode='all_grid', candidate_count=4,
                        distance_mode='integer_micrometer_lower_bound', integer_cutoff_micrometers=module.INTEGER_LIMIT,
                        one_metre_selected_route_rounding_margin=True, origin_partition=[begin, end], pairs=rows,
                        pair_count=len(rows), finite_pair_count=sum(r['integer_micrometers'] is not None for r in rows),
                        pairs_over_450km=len(long))
        path = tmp_path / part['distance_file']
        write(path, distance)
        proof = dict(schema='hiroute.m5d.distance_potential_check.v1', **identities,
                     pair_screen_sha256=module.sha(path), verified_long_pair_count=len(long),
                     verified_root_count=len(roots), selected_leg_rounding_error_upper_m=0.001,
                     one_metre_margin_passed=True,
                     audits=[dict(root=r, matched_screened_targets=3, reached_node_count=4,
                                  checked_reached_edges=6, label_sha256='f'*64) for r in roots])
        write(tmp_path / part['potential_file'], proof)
    return geo, plan_path, tmp_path


def change(inputs, filename, mutate, resign=False):
    path = inputs[2] / filename
    data = json.loads(path.read_text())
    mutate(data)
    write(path, data)
    if resign:
        proof_path = inputs[2] / filename.replace('distance', 'potential')
        proof = json.loads(proof_path.read_text())
        proof['pair_screen_sha256'] = module.sha(path)
        write(proof_path, proof)


def test_deterministic_complete_coverage_and_cutoff(inputs):
    result = module.aggregate(*inputs)
    assert result == module.aggregate(*inputs)
    assert result['directed_pair_count'] == 12
    assert result['finite_pair_count'] == 9
    assert result['independent_checked_long_pairs'] == 5
    assert len(result['source_sha256']) == 5  # geographic + two screens + two proofs
    with pytest.raises(ValueError, match='Frozen'):
        module.aggregate(*inputs, frozen_population=True)


@pytest.mark.parametrize('filename,mutate,resign', [
    ('plan.json', lambda d: d['partitions'].pop(), False),
    ('plan.json', lambda d: d['partitions'].reverse(), False),
    ('grid14_distance_p0.json', lambda d: d['pairs'].pop(), True),
    ('grid14_distance_p0.json', lambda d: d['pairs'].__setitem__(1, d['pairs'][0]), True),
    ('grid14_distance_p0.json', lambda d: d.update(origin_partition=[1, 3]), True),
    ('grid14_distance_p0.json', lambda d: d.update(graph_edges_sha256='0'*64), True),
    ('grid14_distance_p0.json', lambda d: d.update(candidate_mode='farthest_pair'), True),
    ('grid14_distance_p0.json', lambda d: d['pairs'][0].update(integer_micrometers=True), True),
    ('grid14_distance_p0.json', lambda d: d['pairs'][0].update(distance_cost_m=1), True),
    ('grid14_distance_p0.json', lambda d: d.update(finite_pair_count=0), True),
    ('grid14_distance_p0.json', lambda d: d.update(geographic_screen_sha256='0'*64), True),
    ('grid14_potential_p0.json', lambda d: d.update(pair_screen_sha256='0'*64), False),
    ('grid14_potential_p0.json', lambda d: d.update(verified_long_pair_count=0), False),
    ('grid14_potential_p0.json', lambda d: d.update(one_metre_margin_passed=False), False),
    ('grid14_potential_p0.json', lambda d: d.update(selected_leg_rounding_error_upper_m=1), False),
    ('grid14_potential_p0.json', lambda d: d['audits'].clear(), False),
    ('grid14_potential_p0.json', lambda d: d['audits'][0].update(matched_screened_targets=1), False),
])
def test_rejects_incomplete_or_corrupt_evidence(inputs, filename, mutate, resign):
    change(inputs, filename, mutate, resign)
    with pytest.raises(ValueError):
        module.aggregate(*inputs)


def test_missing_partition(inputs):
    (inputs[2] / 'grid14_distance_p1.json').unlink()
    with pytest.raises(FileNotFoundError):
        module.aggregate(*inputs)


def test_duplicate_json_keys(inputs):
    inputs[1].write_text('{"partitions": [], "partitions": []}')
    with pytest.raises(ValueError, match='duplicate JSON'):
        module.aggregate(*inputs)


def test_fixed_partition_boundaries(tmp_path):
    geo = tmp_path / 'geographic.json'
    write(geo, dict(schema='hiroute.m5d.geographic_screen.v1', nodes_sha256='a'*64,
                    sites_sha256='b'*64, fixed_grid_candidate_count=158,
                    fixed_grid_candidates=[dict(site_id=f'S{i}', access_node=i, lat_cell=i//14, lon_cell=i%14) for i in range(158)]))
    assert [p['origin_partition'] for p in module.partition_plan(geo)['partitions']] == [[0, 40], [40, 80], [80, 120], [120, 158]]


def test_zero_long_partition(inputs):
    path = inputs[2] / 'grid14_distance_p0.json'
    data = json.loads(path.read_text())
    for row in data['pairs']:
        if row['integer_micrometers'] is not None:
            row.update(integer_micrometers=module.CUTOFF, distance_cost_m=module.CUTOFF / 1e6)
    data['pairs_over_450km'] = 0
    write(path, data)
    proof_path = inputs[2] / 'grid14_potential_p0.json'
    proof = json.loads(proof_path.read_text())
    proof.update(audits=[], verified_root_count=0, verified_long_pair_count=0, pair_screen_sha256=module.sha(path))
    write(proof_path, proof)
    assert module.aggregate(*inputs)['independent_checked_long_pairs'] == 3


def test_cli_and_refusal_to_overwrite(inputs):
    import subprocess
    import sys
    output = inputs[2] / 'aggregate.json'
    command = [sys.executable, str(Path(module.__file__)), 'aggregate',
               '--geographic-screen', str(inputs[0]), '--plan', str(inputs[1]),
               '--input-dir', str(inputs[2]), '--output', str(output)]
    subprocess.run(command, check=True, capture_output=True)
    before = output.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert output.read_bytes() == before


def test_config_binding_and_population(inputs):
    config = json.loads((Path(module.__file__).parents[1] / 'configs/m5d/fixed_grid14_screen.json').read_text())
    config.update(expected_candidate_count=4, expected_long_pair_count=5, partition_count=2)
    config_path = inputs[2] / 'config.json'
    write(config_path, config)
    geo = json.loads(inputs[0].read_text())
    geo['fixed_grid_rule'] = 'one_nearest_attached_site_per_populated_cell_in_14x14_lat_lon_bounds'
    write(inputs[0], geo)
    for i in range(2):
        change(inputs, f'grid14_distance_p{i}.json', lambda d: d.update(geographic_screen_sha256=module.sha(inputs[0])), True)
    write(inputs[1], module.partition_plan(inputs[0], config_path=config_path))
    result = module.aggregate(*inputs, config_path=config_path)
    assert result['config_sha256'] == module.sha(config_path)
    config['expected_long_pair_count'] = 6
    write(config_path, config)
    with pytest.raises(ValueError, match='plan/source/order'):
        module.aggregate(*inputs, config_path=config_path)
    write(inputs[1], module.partition_plan(inputs[0], config_path=config_path))
    with pytest.raises(ValueError, match='long-pair population'):
        module.aggregate(*inputs, config_path=config_path)
    config['long_pair_cutoff_micrometers_exclusive'] += 1
    write(config_path, config)
    with pytest.raises(ValueError, match='cutoff/order'):
        module.partition_plan(inputs[0], config_path=config_path)
