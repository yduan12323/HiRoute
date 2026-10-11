"""Tiny directed path witnesses for the real-road provider boundary."""
import hashlib
import json
from types import SimpleNamespace
import unittest

import numpy as np

from timecut5.real_legs import (ImmutableLegTable, NUMERICS, SCHEMA,
                                TIE_POLICY, RealSite, encode_binary64)
from timecut5.real_adapter import TableFreeRealProblem, site_catalog_digest
from timecut5.bounded import _solve_problem
from timecut5.hierarchy import Region, _solve_hierarchical_problem
from timecut5.live_replay import ExactLayerReplay, LayerCheckpointStop
from timecut5.road_provider import (RoadSelectedLegProvider,
    TableFreeRoadSelectedLegProvider, TableFreeRegionBoundProvider)
from timecut5.road_landmark import certify_integer_landmark


class NativeStub:
    provenance = {"source_sha256": "a" * 64}
    def __init__(self, wrong_edge=False):
        self.wrong_edge = wrong_edge

    def full_edges(self, root):
        rows = (
            ([0., 1., 2.], [0., 10., 20.], [-1, 0, 1], [-1, 0, 1]),
            ([2., 0., 1.], [20., 0., 10.], [2, -1, 1], [2, -1, 1]),
            ([1., 2., 0.], [10., 20., 0.], [2, 0, -1], [2, 0, -1]),
        )
        cost, length, parent, edge = rows[root]
        edge = list(edge)
        if self.wrong_edge and root == 0:
            edge[2] = 3
        return (np.array(cost), np.array(length), np.array(parent, dtype=np.int64),
                np.array(edge, dtype=np.int64))


class RoadProviderTest(unittest.TestCase):
    def fixture(self):
        anchors = ["road:0", "road:1", "road:2"]
        rows = NativeStub().full_edges
        legs = []
        for source in range(3):
            cost, length, _, _ = rows(source)
            for target in range(3):
                legs.append(dict(source_anchor=anchors[source], target_anchor=anchors[target],
                    reachable=True, label_direction="identity" if source == target else
                    "forward_from_source", time_s=encode_binary64(float(cost[target])),
                    actual_length_m=encode_binary64(float(length[target]))))
        payload = dict(schema=SCHEMA, numerical_contract=NUMERICS, anchors=anchors,
            origin_anchor=anchors[0], destination_anchor=anchors[2],
            sites=[dict(site_id="s1", anchor_id=anchors[1], effects=["C"])],
            backend=dict(name="native stub", tie_policy=TIE_POLICY,
                         direction_policy="forward_per_source_v1",
                         source_sha256={"router": "a" * 64}),
            source_sha256={
                "data/processed/graphs/slovenia_extended/nodes.parquet": "b" * 64,
                "data/processed/graphs/slovenia_extended/edges.parquet": "c" * 64},
            selection_certificate_sha256="d" * 64, hierarchy_sha256="e" * 64,
            legs=legs)
        data = json.dumps(payload, sort_keys=True).encode()
        table = ImmutableLegTable.from_bytes(data, hashlib.sha256(data).hexdigest())
        graph = SimpleNamespace(node_count=3, edge_count=4,
            source=np.array([0, 1, 2, 0]), target=np.array([1, 2, 0, 2]),
            weights={"travel_time": np.array([1., 1., 1., 3.]),
                     "distance": np.array([10., 10., 10., 10.])})
        return table, graph

    def test_selected_path_and_parallel_policy(self):
        table, graph = self.fixture()
        provider = RoadSelectedLegProvider(graph, NativeStub(), table,
            {f"road:{i}": i for i in range(3)}, nodes_sha256="b" * 64,
            edges_sha256="c" * 64)
        self.assertEqual(provider.leg("road:0", "road:2"), table.leg("road:0", "road:2"))
        self.assertEqual(provider.edge_witnesses["road:0", "road:2"], (0, 1))
        self.assertEqual(provider.source_run_count, 1)
        provider.leg("road:0", "road:1")
        self.assertEqual(provider.source_run_count, 1)

    def test_invalid_predecessor_edge_fails_closed(self):
        table, graph = self.fixture()
        provider = RoadSelectedLegProvider(graph, NativeStub(wrong_edge=True), table,
            {f"road:{i}": i for i in range(3)}, nodes_sha256="b" * 64,
            edges_sha256="c" * 64)
        with self.assertRaises(ValueError):
            provider.leg("road:0", "road:2")

    def test_table_free_selected_target_and_edge_replay(self):
        table, graph = self.fixture()
        anchors = {f"road:{i}": i for i in range(3)}
        catalog_sha = hashlib.sha256(json.dumps(anchors, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        provider = TableFreeRoadSelectedLegProvider(graph, NativeStub(),
            anchors, nodes_sha256="b" * 64,
            edges_sha256="c" * 64, router_sha256="a" * 64,
            anchor_catalog_sha256=catalog_sha)
        self.assertEqual(provider.leg("road:0", "road:2"), table.leg("road:0", "road:2"))
        self.assertEqual(provider.edge_witnesses["road:0", "road:2"], (0, 1))
        self.assertEqual(set(provider.legs), {("road:0", "road:2")})
        provider.leg("road:0", "road:2")
        self.assertEqual(provider.source_run_count, 1)
        broken = TableFreeRoadSelectedLegProvider(graph, NativeStub(wrong_edge=True),
            anchors, nodes_sha256="b" * 64,
            edges_sha256="c" * 64, router_sha256="a" * 64,
            anchor_catalog_sha256=catalog_sha)
        with self.assertRaises(ValueError):
            broken.leg("road:0", "road:2")
        with self.assertRaisesRegex(ValueError, "catalog bytes"):
            TableFreeRoadSelectedLegProvider(graph, NativeStub(), anchors,
                nodes_sha256="b" * 64, edges_sha256="c" * 64,
                router_sha256="a" * 64, anchor_catalog_sha256="d" * 64)

    def test_integer_landmark_checks_both_directed_potentials(self):
        _, graph = self.fixture()
        class Router:
            provenance = {"source_sha256": "f" * 64}
            def __init__(self, bad=False):
                self.bad = bad
            def full(self, root, reverse=False):
                labels = np.array([0., 10., 0.]) if self.bad else np.zeros(3)
                return labels, labels.copy(), np.array([-1, -1, -1])
            def close(self):
                pass
        distances, data = certify_integer_landmark(graph,
            {f"road:{i}": i for i in range(3)}, "road:0", lambda _: Router(),
            graph_nodes_sha256="b" * 64, graph_edges_sha256="c" * 64)
        self.assertEqual(distances.from_landmark["road:1"], 0)
        self.assertEqual(json.loads(data)["audited"][0]["checked_edges"], 4)
        with self.assertRaises(ValueError):
            certify_integer_landmark(graph, {f"road:{i}": i for i in range(3)},
                "road:0", lambda _: Router(bad=True),
                graph_nodes_sha256="b" * 64, graph_edges_sha256="c" * 64)

    def test_table_free_real_adapter_executes_both_exact_engines(self):
        table, graph = self.fixture()
        anchors = {f"road:{i}": i for i in range(3)}
        catalog_sha = hashlib.sha256(json.dumps(anchors, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        def problem():
            provider = TableFreeRoadSelectedLegProvider(graph, NativeStub(), anchors,
                nodes_sha256="b" * 64, edges_sha256="c" * 64,
                router_sha256="a" * 64, anchor_catalog_sha256=catalog_sha)
            query = dict(H_ref=1, start_time_s=0, initial_energy_kwh=1,
                capacity_kwh=2, minimum_energy_kwh=0, reserve_kwh=0,
                consumption_kwh_per_m="1/10", overhead_s=1, lambda_stop_s=0,
                schedule=None, charging_segments=[[0, 2, 1, 0]])
            return TableFreeRealProblem(query, table.sites, provider,
                origin_anchor="road:0", destination_anchor="road:2",
                site_catalog_sha256=site_catalog_digest(table.sites))
        class LandmarkRouter:
            provenance = {"source_sha256": "f" * 64}
            def full(self, root, reverse=False):
                zeros = np.zeros(3)
                return zeros, zeros.copy(), np.array([-1, -1, -1])
            def close(self):
                pass
        flat_problem, hier_problem = problem(), problem()
        with self.assertRaisesRegex(ValueError, "Site catalog bytes"):
            TableFreeRealProblem(dict(H_ref=0, start_time_s=0,
                initial_energy_kwh=1, capacity_kwh=2, minimum_energy_kwh=0,
                reserve_kwh=0, consumption_kwh_per_m="1/10", overhead_s=1,
                lambda_stop_s=0, schedule=None, charging_segments=[[0, 2, 1, 0]]),
                table.sites, hier_problem.provider, origin_anchor="road:0",
                destination_anchor="road:2", site_catalog_sha256="0" * 64)
        root = Region(0, ("s1",))
        bound = TableFreeRegionBoundProvider(hier_problem.provider, table.sites,
            root, destination_anchor="road:2", landmark_anchor="road:0",
            site_catalog_sha256=site_catalog_digest(table.sites),
            router_factory=lambda _: LandmarkRouter())
        self.assertEqual(json.loads(bound.landmark_certificate)["audited"][0]["checked_edges"], 4)
        self.assertEqual(set(hier_problem.provider.legs), set())
        flat = _solve_problem(flat_problem, singleton_bound=bound.singleton_bound)
        hier = _solve_hierarchical_problem(hier_problem, True, root,
            bound_provider=bound)
        self.assertEqual(flat.result.key, hier.bounded.result.key)
        self.assertEqual(flat.result.key[2], 1)
        collision = {"road:0": RealSite("road:0", "road:1", ("C",))}
        alias_bound = TableFreeRegionBoundProvider(hier_problem.provider, collision,
            Region(1, ("road:0",)), destination_anchor="road:2",
            landmark_anchor="road:0", site_catalog_sha256=site_catalog_digest(collision),
            router_factory=lambda _: LandmarkRouter())
        self.assertEqual(alias_bound.landmarks[0].from_landmark["road:0"], 0)
        for mode in ("flat", "hier"):
            def solve(hook):
                instance = problem()
                indexed = TableFreeRegionBoundProvider(instance.provider, table.sites,
                    root, destination_anchor="road:2", landmark_anchor="road:0",
                    site_catalog_sha256=site_catalog_digest(table.sites),
                    router_factory=lambda _: LandmarkRouter())
                return (_solve_problem(instance, checkpoint_hook=hook,
                    verified_primary_upper=flat.result.key[0],
                    singleton_bound=indexed.singleton_bound) if mode == "flat"
                    else _solve_hierarchical_problem(instance, True, root,
                        checkpoint_hook=hook, verified_primary_upper=flat.result.key[0],
                        bound_provider=indexed))
            original = solve(None)
            stopped = ExactLayerReplay(mode=mode, domain_sha256="d" * 64,
                external_source_sha256={"graph": "b" * 64}, stop_after_depth=1)
            with self.assertRaises(LayerCheckpointStop) as interrupted:
                solve(stopped)
            restored = ExactLayerReplay(mode=mode, domain_sha256="d" * 64,
                external_source_sha256={"graph": "b" * 64},
                previous_checkpoint=interrupted.exception.checkpoint_bytes)
            resumed = solve(restored)
            restored.finish()
            self.assertEqual(restored.replayed_restore_layers, 2)
            self.assertEqual((original.result if mode == "flat" else original.bounded.result).key,
                             (resumed.result if mode == "flat" else resumed.bounded.result).key)
            with self.assertRaises(ValueError):
                ExactLayerReplay(mode=mode, domain_sha256="e" * 64,
                    external_source_sha256={"graph": "b" * 64},
                    previous_checkpoint=interrupted.exception.checkpoint_bytes)
            altered = json.loads(interrupted.exception.checkpoint_bytes)
            altered["layers"][1]["state_sha256"] = "0" * 64
            tampered = ExactLayerReplay(mode=mode, domain_sha256="d" * 64,
                external_source_sha256={"graph": "b" * 64},
                previous_checkpoint=json.dumps(altered, sort_keys=True,
                    separators=(",", ":")).encode())
            with self.assertRaisesRegex(ValueError, "OPEN"):
                solve(tampered)


if __name__ == "__main__":
    unittest.main()
