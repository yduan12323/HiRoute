"""Read-only compact-export audit, with no graph load and no optimization.

Independently reconstructs expected selected memberships and exact windows from
original artifacts rather than trusting the exporter's aggregate counts.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from timecut5.real_legs import ImmutableLegTable, decode_binary64


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def verify(output, selection):
    if not __debug__:
        raise RuntimeError("Run this assertion-based audit without Python optimization flags")
    output, selection = Path(output), Path(selection)
    manifest = load(output / 'export_manifest.json')
    frozen = load(selection / 'selection_manifest.json')
    states = load(output / 'query_states_resolved.json')
    source_states = {s['state_id']: s for s in load(selection / 'query_states.json')}
    assert manifest['status'] == 'export_complete_preparation_only'
    assert manifest['no_optimization'] is True
    assert manifest['selection_certificate_sha256'] == digest(selection / 'selection_manifest.json')
    assert manifest['query_states_resolved_sha256'] == digest(output / 'query_states_resolved.json')
    for key, filename in [('preflight_sha256', 'preflight.json'), ('native_router_sha256', 'native_router.json'),
                          ('calibration_sha256', 'real_pair_full_calibration.json')]:
        assert manifest[key] == digest(output / filename)
    calibration = load(output / 'real_pair_full_calibration.json')
    assert calibration['passed'] and all(s['time_and_actual_length_bitwise_equal'] for s in calibration['sources'])
    tree_path = manifest['original_hierarchy_path']
    assert digest(tree_path) == frozen['original_hierarchy_sha256'] == manifest['hierarchy_sha256']
    tree = load(tree_path)
    catalog = {s['site_id']: s for s in load(selection / 'chosen_site_catalog.json')['sites']}
    ods = {o['instance_id']: o for o in load(selection / 'od_anchors.json')}
    tables = {}
    coattached, region_checks, pair_count = 0, 0, 0
    unique_pairs = {}
    historical_comparisons = {}
    for pool in frozen['pools']:
        pid, selected = pool['pool_id'], set(pool['selected_site_ids'])
        od = ods[pool['instance_id']]
        spec = manifest['tables'][pid]
        table = ImmutableLegTable.from_bytes((output / spec['path']).read_bytes(), spec['sha256'])
        assert table.selection_certificate_sha256 == manifest['selection_certificate_sha256']
        assert table.hierarchy_sha256 == manifest['hierarchy_sha256']
        assert set(table.sites) == selected
        assert table.origin_anchor == f"road:{od['origin_node']}"
        assert table.destination_anchor == f"road:{od['destination_node']}"
        baseline = table.leg(table.origin_anchor, table.destination_anchor)
        historical_comparisons[od['instance_id']] = {
            'instance_id': od['instance_id'], 'accepted_time_hex': baseline.time_hex,
            'historical_time_hex': float(od['ext_baseline_time_s']).hex(),
            'time_bitwise_equal': baseline.time_hex == float(od['ext_baseline_time_s']).hex(),
            'time_difference_exact_s': str(baseline.time - Fraction.from_float(od['ext_baseline_time_s'])),
            'accepted_actual_length_hex': baseline.length_hex,
            'historical_actual_length_hex': float(od['ext_fastest_distance_m']).hex(),
            'actual_length_bitwise_equal': baseline.length_hex == float(od['ext_fastest_distance_m']).hex(),
            'actual_length_difference_exact_m': str(baseline.actual_length - Fraction.from_float(od['ext_fastest_distance_m'])),
        }
        expected_anchors = {table.origin_anchor, table.destination_anchor}
        for chosen in pool['chosen']:
            site = table.sites[chosen['site_id']]
            assert site.anchor_id == f"road:{catalog[site.site_id]['access_node']}"
            assert list(site.effects) == chosen['eligible_actions']
            expected_anchors.add(site.anchor_id)
        assert set(table.anchors) == expected_anchors
        coattached += len(table.sites) - len({s.anchor_id for s in table.sites.values()})
        for pair, leg in table.legs.items():
            value = (leg.reachable, leg.time_hex, leg.length_hex, leg.label_direction)
            assert pair not in unique_pairs or unique_pairs[pair] == value
            unique_pairs[pair] = value
        r_spec = manifest['restrictions'][pid]
        assert digest(output / r_spec['path']) == r_spec['sha256']
        restriction = load(output / r_spec['path'])
        assert restriction['original_sha256'] == table.hierarchy_sha256
        assert restriction['selection_certificate_sha256'] == table.selection_certificate_sha256
        assert restriction['selected_site_ids'] == [s for s in tree['site_ids'] if s in selected]
        assert len(restriction['regions']) == len(tree['regions']) == r_spec['region_count']
        for i, (old, new) in enumerate(zip(tree['regions'], restriction['regions'])):
            assert new['region_id'] == i
            assert new['parent_id'] == old['parent'] and new['child_ids'] == old['children']
            assert new['site_ids'] == [tree['site_ids'][j] for j in old['members'] if tree['site_ids'][j] in selected]
            region_checks += 1
        pair_count += len(table.legs)
        tables[pid] = table
    assert len(states) == len(source_states) == frozen['state_count']
    assert len({s['state_id'] for s in states}) == len(states)
    for state in states:
        old = source_states[state['state_id']]
        for key in ['instance_id', 'pool_id', 'initial_energy_kwh', 'initial_soc', 'mode', 'capacity_kwh',
                    'terminal_reserve_kwh', 'energy_floor_kwh', 'overhead_s', 'stop_penalty_s', 'start_time_s',
                    'consumption_kwh_per_m', 'charging_primitive', 'solve_status', 'H_ref']:
            assert state[key] == old[key]
        table = tables[state['pool_id']]
        baseline = table.leg(table.origin_anchor, table.destination_anchor)
        assert state['accepted_baseline_time_s']['hex'] == baseline.time_hex
        assert state['accepted_baseline_actual_length_m']['hex'] == baseline.length_hex
        assert decode_binary64(state['accepted_baseline_time_s']) == baseline.time
        assert decode_binary64(state['accepted_baseline_actual_length_m']) == baseline.actual_length
        assert state['immutable_direct_leg_table'] == manifest['tables'][state['pool_id']]
        assert state['original_tree_restriction'] == manifest['restrictions'][state['pool_id']]
        if old['schedule'] is None:
            assert state['schedule'] is None
        else:
            schedule = state['schedule']
            assert Fraction(schedule['baseline_time_s']) == baseline.time
            assert Fraction(schedule['window_start_s']) == Fraction(2, 5) * baseline.time
            assert Fraction(schedule['window_end_s']) == Fraction(7, 10) * baseline.time
            assert schedule['duration_s'] == old['schedule']['duration_s']
    assert len(unique_pairs) == manifest['requested_pair_count']
    return {'passed': True, 'no_graph_load': True, 'no_optimization': True,
            'pool_tables_checked': len(tables), 'states_checked': len(states),
            'complete_table_rows_checked': pair_count, 'unique_ordered_pairs_checked': len(unique_pairs),
            'original_region_rows_checked': region_checks, 'coattached_extra_site_instances': coattached,
            'export_manifest_sha256': digest(output / 'export_manifest.json'),
            'historical_comparison_diagnostic_only': list(historical_comparisons.values())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--selection', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.output, args.selection), indent=2, sort_keys=True))
