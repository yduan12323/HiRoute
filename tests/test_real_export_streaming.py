"""Streaming exporter tests use tiny fixtures, never frozen real graph data."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

PATH = Path(__file__).resolve().parents[1] / 'experiments/time_cut_v2/real_export/export.py'
spec = importlib.util.spec_from_file_location('real_export_streaming', PATH)
export = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = export
spec.loader.exec_module(export)


def fixture_graph(tmp_path, *, node_ids=None, edge_ids=None, sources=None, costs=None):
    nodes = tmp_path / 'nodes.parquet'
    edges = tmp_path / 'edges.parquet'
    pq.write_table(pa.table({'node_id': [0, 1, 2, 3] if node_ids is None else node_ids,
                            'irrelevant': ['x'] * 4}), nodes)
    pq.write_table(pa.table({'edge_id': [0, 1, 2, 3] if edge_ids is None else edge_ids,
                            'source': [0, 1, 0, 2] if sources is None else sources,
                            'target': [1, 3, 2, 3],
                            'travel_time_s': [1., 1., 1., 1.] if costs is None else costs,
                            'length_m': [9., 1., 1., 2.], 'irrelevant': ['y'] * 4}), edges)
    return nodes, edges


def test_memory_formula_and_guard():
    plan = export.estimate_memory(5892498, 11561067)
    assert plan['input_arrays_bytes'] == 369954144
    assert plan['native_persistent_index_bytes'] == 422468440
    assert plan['native_constructor_offset_copies_bytes'] == 94279984
    assert plan['one_full_calibration_output_bytes'] == 141419952
    assert plan['planned_peak_increment_bytes'] == 3175606168
    with pytest.raises(MemoryError):
        export.require_memory(plan, {'available_bytes': plan['planned_peak_increment_bytes'] - 1})
    assert export.require_memory(plan, {'available_bytes': plan['planned_peak_increment_bytes']})
    with pytest.raises(ValueError):
        export.estimate_memory(2**32, 1)


def test_streaming_exact_order_dtype_and_bits(tmp_path):
    nodes, edges = fixture_graph(tmp_path, costs=[-0., 1.1, 2.5, 3.75])
    graph = export.load_native_arrays(nodes, edges, 4, 4, batch_size=1)
    assert graph.array_bytes == 4 * 4 * 8
    assert graph.source.tolist() == [0, 1, 0, 2]
    assert graph.target.tolist() == [1, 3, 2, 3]
    assert graph.weights['distance'].tolist() == [9., 1., 1., 2.]
    assert graph.weights['travel_time'][0].item().hex() == '-0x0.0p+0'
    assert all(a.flags.c_contiguous for a in [graph.source, graph.target, *graph.weights.values()])


@pytest.mark.parametrize('kwargs,error', [
    ({'node_ids': [0, 1, 3, 2]}, 'Node IDs'),
    ({'edge_ids': [0, 2, 1, 3]}, 'Edge IDs'),
    ({'sources': [0, 4, 0, 2]}, 'outside node domain'),
    ({'sources': [-1, 1, 0, 2]}, 'outside node domain'),
    ({'costs': [1., float('inf'), 1., 1.]}, 'finite nonnegative'),
    ({'costs': [1., float('nan'), 1., 1.]}, 'finite nonnegative'),
    ({'costs': [1., -1., 1., 1.]}, 'finite nonnegative'),
    ({'costs': [1., None, 1., 1.]}, 'nonnull'),
])
def test_stream_validation(tmp_path, kwargs, error):
    nodes, edges = fixture_graph(tmp_path, **kwargs)
    with pytest.raises(ValueError, match=error):
        export.load_native_arrays(nodes, edges, 4, 4, batch_size=2)


def test_colocated_sites_remain_distinct_and_complete_pairs():
    catalog = {'sites': [{'site_id': sid, 'access_node': 1, 'can_C': True, 'can_S': False, 'can_CS': False}
                         for sid in ['s1', 's2']]}
    manifest = {'pools': [{'pool_id': 'p', 'instance_id': 0, 'selected_site_ids': ['s1', 's2'],
                           'chosen': [{'site_id': sid, 'access_node': 1, 'eligible_actions': ['C']}
                                      for sid in ['s1', 's2']]}]}
    requests, pools = export.selected_requests(manifest, catalog, [{'instance_id': 0, 'origin_node': 0, 'destination_node': 3}])
    assert requests == {0: [0, 1, 3], 1: [0, 1, 3], 3: [0, 1, 3]}
    assert len(pools[0]['sites']) == 2
    assert [s['anchor_id'] for s in pools[0]['sites']] == ['road:1', 'road:1']
    catalog['sites'][0]['access_node'] = 3
    manifest['pools'][0]['chosen'][0]['access_node'] = 3
    with pytest.raises(ValueError, match='Terminal-anchor'):
        export.selected_requests(manifest, catalog, [{'instance_id': 0, 'origin_node': 0, 'destination_node': 3}])


def test_selected_only_export_one_source_and_unreachable(tmp_path):
    class FakeRouter:
        def __init__(self):
            self.calls = []
        def pairs(self, sources, targets, cutoff):
            assert len(set(sources)) == 1
            assert cutoff == sys.float_info.max
            self.calls.append((list(sources), list(targets)))
            c = np.array([0. if s == t else float('inf') for s, t in zip(sources, targets)])
            return c, c.copy()
    router = FakeRouter()
    rows, _ = export.export_selected_pairs(router, {0: [0, 2], 2: [0, 2]}, tmp_path / 'rows.jsonl')
    assert len(router.calls) == 2 and len(rows) == 4
    assert rows[0, 0]['label_direction'] == 'identity'
    assert rows[0, 2]['reachable'] is False
    assert rows[0, 2]['time_s'] is None
    assert len((tmp_path / 'rows.jsonl').read_text().splitlines()) == 2


@pytest.mark.parametrize('cost,length', [(0., 1.), (1., 0.), (float('inf'), 1.), (float('nan'), 1.)])
def test_invalid_native_labels_rejected(cost, length):
    with pytest.raises(ValueError):
        export.leg_row(0, 1, cost, length)


def test_native_bitwise_calibration_and_fastest_actual_length(tmp_path):
    nodes, edges = fixture_graph(tmp_path)
    graph = export.load_native_arrays(nodes, edges, 4, 4, batch_size=2)
    router = export.ExactRouter(graph, {'compiler': 'g++', 'compiler_flags': ['-O3', '-std=c++17']}, tmp_path/'native')
    try:
        report = export.calibrate(router, {0: [0, 1, 2, 3], 1: [0, 1, 2, 3]}, source_count=2)
        assert report['passed'] and report['pair_count'] == 8
        rows, _ = export.export_selected_pairs(router, {0: [0, 1, 2, 3]})
        assert rows[0, 3]['time_s'] == export.encode_binary64(2.)
        assert rows[0, 3]['actual_length_m'] == export.encode_binary64(3.)
    finally:
        router.close()


def test_resolved_schedule_uses_exact_ratio_before_scaling():
    state = {'consumption_kwh_per_m': '1/6250', 'capacity_kwh': '60', 'terminal_reserve_kwh': '6',
             'energy_floor_kwh': '0', 'overhead_s': '300', 'stop_penalty_s': '600', 'start_time_s': '0',
             'charging_primitive': {'energy_breakpoints_kwh': ['0', '30', '48', '60'],
                                    'slopes_s_per_kwh': ['36', '60', '120'], 'intercepts_s': ['0', '-720', '-3600'],
                                    'label': 'canonical_synthetic_PWA_cumulative'},
             'instance_id': 0, 'pool_id': 'p', 'schedule': {'duration_s': '2700', 'pending_reason': 'pending'}}
    rows = {(0, 1): export.leg_row(0, 1, 0.1, 1.)}
    result = export.resolved_states([state], [{'instance_id': 0, 'origin_node': 0, 'destination_node': 1}], rows, {'p': {'sha256': 'hash'}})[0]
    assert export.Fraction(result['schedule']['window_start_s']) == export.Fraction(2, 5)*export.Fraction.from_float(0.1)
    assert export.Fraction(result['schedule']['window_start_s']) != export.Fraction.from_float(0.1 * 0.4)
    assert 'pending_reason' not in result['schedule']
    assert state['schedule']['pending_reason'] == 'pending'


def test_restrictions_preserve_empty_regions_and_ids(tmp_path):
    tree = {'site_ids': ['s1', 's2'], 'regions': [
        {'parent': -1, 'children': [1, 2], 'members': [0, 1]},
        {'parent': 0, 'children': [], 'members': [0]},
        {'parent': 0, 'children': [], 'members': [1]},
    ]}
    path = tmp_path / 'tree.json'
    digest = export.write_json(path, tree)
    outputs = export.export_restrictions(path, digest, 'a'*64,
                                        [{'pool_id': 'p', 'sites': [{'site_id': 's1'}]}], tmp_path)
    result = export.read_json(tmp_path / outputs['p']['path'])
    assert result['original_sha256'] == digest
    assert result['selected_site_ids'] == ['s1']
    assert result['regions'] == [
        {'region_id': 0, 'parent_id': -1, 'child_ids': [1, 2], 'site_ids': ['s1']},
        {'region_id': 1, 'parent_id': 0, 'child_ids': [], 'site_ids': ['s1']},
        {'region_id': 2, 'parent_id': 0, 'child_ids': [], 'site_ids': []},
    ]
    assert outputs['p']['empty_region_count'] == 1
    with pytest.raises(ValueError, match='hash mismatch'):
        export.export_restrictions(path, 'b'*64, 'a'*64,
                                   [{'pool_id': 'p', 'sites': [{'site_id': 's1'}]}], tmp_path)


def test_verify_files_detects_tampering(tmp_path):
    path = tmp_path / 'input.json'
    path.write_text('frozen')
    entries = [{'path': str(path), 'sha256': export.sha256(path), 'size_bytes': 6}]
    assert export.verify_files(entries)[0]['size_bytes'] == 6
    path.write_text('tampered')
    with pytest.raises(ValueError, match='hash/size mismatch'):
        export.verify_files(entries)
