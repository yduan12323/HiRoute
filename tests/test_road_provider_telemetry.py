"""Bounded route telemetry; tiny graphs only, no road experiment launch."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import unittest

import numpy as np

from timecut5.road_provider import TableFreeRoadSelectedLegProvider


class NativeStub:
    provenance = {'source_sha256': 'a' * 64}

    def __init__(self, graph):
        self.graph = graph
        self.calls = []
        self.fail = False
        self.edges = {(int(a), int(b)): i for i, (a, b) in
                      enumerate(zip(graph.source, graph.target))}

    def labels(self, root):
        count = self.graph.node_count
        costs = np.ones(count, dtype=np.float64)
        costs[root] = 0
        parents = np.full(count, root, dtype=np.int64)
        parents[root] = -1
        edges = np.array([-1 if node == root else self.edges[root, node]
                          for node in range(count)], dtype=np.int64)
        return costs, costs.copy(), parents, edges

    def full_edges(self, root):
        if self.fail:
            raise RuntimeError('native call interrupted')
        self.calls.append(root)
        return self.labels(root)


class TargetStub(NativeStub):
    role = 'search'
    mode = 'destination_target'
    artifact = {'semantic_contract_sha256': 'd' * 64,
                'artifact_identity_sha256': 'e' * 64}

    def __init__(self, graph):
        super().__init__(graph)
        self.bound = True
        self.target_calls = []

    def validate_binding(self):
        if not self.bound:
            raise ValueError('changed native binding')

    def verify_artifact(self):
        self.validate_binding()

    def target_edges(self, root, target):
        self.target_calls.append((root, target))
        return self.labels(root)


class RoadTelemetryTests(unittest.TestCase):
    def provider(self, *, count=5, anchor_count=None, router_type=NativeStub, **kwargs):
        pairs = [(a, b) for a in range(count) for b in range(count) if a != b]
        graph = SimpleNamespace(node_count=count, edge_count=len(pairs),
            source=np.array([a for a, _ in pairs], dtype=np.int64),
            target=np.array([b for _, b in pairs], dtype=np.int64),
            weights={'travel_time': np.ones(len(pairs)),
                     'distance': np.ones(len(pairs))})
        anchors = {f'road:{i}': i for i in range(anchor_count or count)}
        binding = hashlib.sha256(json.dumps(anchors, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        return TableFreeRoadSelectedLegProvider(graph, router_type(graph), anchors,
            nodes_sha256='b' * 64, edges_sha256='c' * 64,
            router_sha256='a' * 64, anchor_catalog_sha256=binding, **kwargs)

    @staticmethod
    def leg(provider, a, b, **kwargs):
        return provider.leg(f'road:{a}', f'road:{b}', **kwargs)

    def test_counts_expose_repeats_without_changing_default_recency(self):
        p = self.provider()
        expected = self.leg(p, 0, 1)
        self.leg(p, 0, 2)
        before = p.routing_telemetry_snapshot()
        self.leg(p, 1, 4)
        self.leg(p, 0, 2)  # Pair hit keeps the historical LRU order unchanged.
        self.leg(p, 2, 4)
        self.leg(p, 0, 3)
        self.assertEqual(p.router.calls, [0, 1, 2, 0])
        self.assertEqual((p.source_run_count, p.source_run_distinct_count,
                          p.source_run_repeat_count), (4, 3, 1))
        self.assertEqual(self.leg(p, 0, 1), expected)
        self.assertEqual(p.router.calls, [0, 1, 2, 0])
        delta = p.routing_telemetry_delta(before)
        self.assertEqual(delta['counters']['source_run_count'], 3)
        self.assertEqual(delta['counters']['source_run_distinct_count'], 2)
        self.assertEqual(delta['counters']['source_run_repeat_count'], 1)
        self.assertEqual(delta['interval_distinct_source_count'], 3)
        self.assertEqual(delta['interval_repeat_source_run_count'], 0)
        self.assertEqual(delta['source_runs_by_node'], {'0': 1, '1': 1, '2': 1, '3': 0, '4': 0})
        self.assertEqual(before['source_runs_by_node']['0'], 1)
        self.assertEqual(before['counters']['source_run_count'], 1)

    def test_snapshot_detached_serializable_and_does_not_touch_cache(self):
        p = self.provider()
        self.leg(p, 0, 1)
        self.leg(p, 2, 3)
        order = list(p._source_labels)
        before = p.routing_telemetry_snapshot()
        encoded = json.loads(json.dumps(before))
        self.assertEqual(p.routing_telemetry_delta(encoded)['counters']['source_run_count'], 0)
        self.assertEqual(order, list(p._source_labels))
        before['source_runs_by_node']['0'] = 999
        before['counters']['source_run_count'] = 999
        self.assertEqual(p.routing_telemetry_snapshot()['source_runs_by_node']['0'], 1)
        self.assertEqual(p.source_run_count, 2)

    def test_declared_node_map_bounded_for_private_undeclared_calls(self):
        p = self.provider(anchor_count=3, source_cache_max_bytes=0)
        before = p.routing_telemetry_snapshot()
        p._labels(3)
        p._labels(4)
        p._labels(3)
        self.leg(p, 0, 1)
        self.leg(p, 0, 2)
        snapshot = p.routing_telemetry_snapshot()
        self.assertEqual(snapshot['source_runs_by_node'], {'0': 2, '1': 0, '2': 0})
        self.assertEqual(p.source_run_untracked_count, 3)
        self.assertEqual((p.source_run_count, p.source_run_distinct_count,
                          p.source_run_repeat_count), (5, 1, 1))
        delta = p.routing_telemetry_delta(before)
        self.assertEqual(delta['interval_distinct_source_count'], 1)
        self.assertEqual(delta['interval_repeat_source_run_count'], 1)
        self.assertEqual(delta['counters']['source_run_untracked_count'], 3)
        self.assertEqual(delta['end_gauges'], {'source_cache_bytes': 0, 'source_cache_entries': 0})

    def test_interrupted_native_call_not_successful_and_gauge_may_decrease(self):
        p = self.provider(source_cache_max_sources=1)
        self.leg(p, 0, 1)
        before = p.routing_telemetry_snapshot()
        p.router.fail = True
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            self.leg(p, 2, 3)
        delta = p.routing_telemetry_delta(before)
        self.assertTrue(all(value == 0 for value in delta['source_runs_by_node'].values()))
        self.assertEqual(delta['counters']['source_run_count'], 0)
        self.assertEqual(delta['counters']['source_cache_evictions'], 1)
        self.assertEqual(delta['end_gauges']['source_cache_bytes'], 0)
        self.assertGreater(before['gauges']['source_cache_bytes'], 0)

    def test_target_calls_never_enter_full_source_counts_or_cache(self):
        p = self.provider(router_type=TargetStub)
        before = p.routing_telemetry_snapshot()
        first = self.leg(p, 0, 1, target_only=True)
        self.leg(p, 0, 2, target_only=True)
        self.assertEqual(self.leg(p, 0, 1, target_only=True), first)
        delta = p.routing_telemetry_delta(before)
        self.assertEqual(delta['counters']['target_run_count'], 2)
        self.assertEqual(delta['counters']['source_run_count'], 0)
        self.assertEqual(delta['interval_distinct_source_count'], 0)
        self.assertEqual(p._source_labels, {})
        self.assertEqual(delta['end_gauges']['source_cache_bytes'], 0)
        p.router.bound = False
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.leg(p, 0, 1, target_only=True)

    def test_owned_full_arrays_capacity_and_cache_hit_guard_unchanged(self):
        budget = TableFreeRoadSelectedLegProvider.source_cache_entry_bytes(5)
        p = self.provider(source_cache_max_bytes=budget, source_cache_max_sources=2)
        class Guard:
            def __init__(self):
                self.calls = []
            def begin(self, provider): self.calls.append('begin')
            def end(self, provider): self.calls.append('end')
            def abort(self): self.calls.append('abort')
        guard = Guard()
        p._terminal_energy_route_guard = guard
        self.leg(p, 0, 1)
        guard.calls.clear()
        self.leg(p, 0, 1)
        self.assertEqual(guard.calls, ['begin', 'end'])
        self.leg(p, 2, 3)
        self.assertEqual(len(p._source_labels), 1)
        self.assertLessEqual(p.source_cache_bytes, budget)
        for arrays, _ in p._source_labels.values():
            self.assertTrue(all(array.flags.owndata and not array.flags.writeable for array in arrays))

    def test_delta_rejects_cross_provider_corrupt_and_nonmonotone_baselines(self):
        p = self.provider()
        other = self.provider()
        with self.assertRaisesRegex(ValueError, 'Same-provider'):
            p.routing_telemetry_delta(other.routing_telemetry_snapshot())
        self.leg(p, 0, 1)
        before = p.routing_telemetry_snapshot()
        for section, key, value in [('source_runs_by_node', '0', 2),
                                    ('counters', 'source_run_count', True),
                                    ('counters', 'source_run_count', -1),
                                    ('counters', 'source_run_count', 0),
                                    ('gauges', 'source_cache_bytes', -1)]:
            bad = deepcopy(before)
            bad[section][key] = value
            with self.subTest(section=section, key=key, value=value), self.assertRaises(ValueError):
                p.routing_telemetry_delta(bad)
        bad = deepcopy(before)
        bad['source_runs_by_node']['undeclared'] = 0
        with self.assertRaises(ValueError):
            p.routing_telemetry_delta(bad)


if __name__ == '__main__':
    unittest.main()
