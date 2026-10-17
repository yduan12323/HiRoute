"""Bounded fixtures exercise the real unchanged selected-leg reconstruction.

No graph files, native binary, seed search, production admission or Git action.
Run normally and with -OO. The synthetic router is deliberately NOT evidence
of production native provenance; that remains the existing caller's guard.
"""
import copy
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import timecut5.portable_candidate_policy as policy
from timecut5.portable_candidate_policy import (ELIGIBILITY_POLICY, ELIGIBILITY_SCHEMA, OneSourceRouter,
                             PolicyError, ProposalStatus, build_portable_domain, canonical, digest)
from timecut5.road_provider import TableFreeRoadSelectedLegProvider


class TinyRouter:
    def __init__(self):
        self.calls = []
        self.provenance = {"source_sha256": "a" * 64,
                           "implementation_kind": "synthetic_python_fixture_v1"}
        self.hook = None

    def full_edges(self, source):
        self.calls.append(source)
        labels = (np.array([0., 1., 2., np.inf, 3., 2., 1.]),
                  np.array([0., 4., 9., np.inf, 10., 0., 11.]),
                  np.array([-1, 0, 1, -1, 2, 0, 0], dtype=np.int64),
                  np.array([-1, 0, 1, -1, 3, 4, 5], dtype=np.int64))
        return self.hook(labels) if self.hook else labels


def site(sid, node, effects=("C",)):
    return dict(site_id=sid, access_node=node, anchor_id="road:" + str(node), effects=list(effects))


def rebind(f):
    """Fixture-only bindings, not an authentication or production loader API."""
    baseline, catalog, query = f["baseline_sites"], f["eligible_charging_sites"], f["query"]
    query_sha = digest(canonical(query))
    catalog_sha = digest(canonical(catalog))
    sources = {key: char * 64 for key, char in (("sites", "d"), ("pools", "e"), ("geo", "f"), ("slate", "1"))}
    eligibility = f.setdefault("eligibility", {})
    eligibility.update(schema=ELIGIBILITY_SCHEMA, policy_version=ELIGIBILITY_POLICY,
                       complete=True, source_sha256=sources, query_sha256=query_sha,
                       origin=query["origin"], destination=query["destination"],
                       od_id="tiny_actual_od", origin_site_id="origin_site", destination_site_id="destination_site",
                       radius_m="75000", eligible_charging_count=len(catalog),
                       eligible_candidate_sha256=digest(canonical(sorted(x["site_id"] for x in catalog))),
                       eligible_sites_sha256=catalog_sha)
    f["bindings"] = dict(source_sha256={"nodes": "b" * 64, "edges": "c" * 64, "router": "a" * 64},
                         catalog_source_sha256=sources, baseline_domain_sha256=query["sparse_domain_sha256"],
                         baseline_candidate_sha256=digest(canonical(sorted(x["site_id"] for x in baseline))),
                         baseline_sites_sha256=digest(canonical(baseline)), eligible_catalog_sha256=catalog_sha,
                         eligibility_sha256=digest(canonical(eligibility)), query_sha256=query_sha,
                         native_provenance_sha256=digest(canonical(f["router"].provenance)))
    return f


def fixture():
    # Native selected path to node 2 is 0->1->2, distance 9, despite a slower
    # direct edge with distance 1. Energy must use the selected time path.
    graph = SimpleNamespace(node_count=7, edge_count=6,
        source=np.array([0, 1, 0, 2, 0, 0], dtype=np.int64),
        target=np.array([1, 2, 2, 4, 5, 6], dtype=np.int64),
        weights={"travel_time": np.array([1., 1., 9., 1., 2., 1.]),
                 "distance": np.array([4., 5., 1., 1., 0., 11.])})
    for array in (graph.source, graph.target, *graph.weights.values()):
        array.flags.writeable = False
    baseline = [dict(site("base_charge", 1, ("C", "S", "CS")), original_note="retain verbatim"),
                site("base_meal", 3, ("S",))]
    catalog = [copy.deepcopy(baseline[0]), site("colocated", 1), site("reserve_fail_a", 2),
               site("reserve_fail_b", 2), site("unreachable", 3), site("zero_distance", 5),
               site("floor_fail", 6)]
    query = dict(case_id="tiny_actual_query", origin="road:0", destination="road:4",
                 initial_energy_kwh="10", minimum_energy_kwh="0", reserve_kwh="6",
                 consumption_kwh_per_m="1", capacity_kwh="10", sparse_domain_sha256="2" * 64,
                 schedule={"a": "100", "b": "200", "D": "10"}, H_ref=4)
    return rebind(dict(graph=graph, router=TinyRouter(), baseline_sites=baseline,
                       eligible_charging_sites=catalog, query=query, cap=20))


class PortablePolicyTests(unittest.TestCase):
    def result(self, f):
        result = build_portable_domain(**f)
        self.assertEqual(result.as_dict()["status"], result.status.value)
        return result

    def assert_unknown(self, f, match=None):
        result = self.result(f)
        self.assertIs(result.status, ProposalStatus.UNKNOWN)
        body = result.as_dict()
        self.assertFalse(body["complete"])
        self.assertIsNone(body["candidate_ids"])
        self.assertIsNone(body["sites"])
        self.assertIsNone(body["domain_sha256"])
        if match:
            self.assertIn(match, body["reason"])
        return body

    def test_real_selected_leg_union_preserves_baseline_colocated_and_reserve_fail(self):
        f = fixture()
        r = self.result(f)
        self.assertIs(r.status, ProposalStatus.PROPOSED_COMPLETE)
        v = r.as_dict()
        self.assertEqual(f["router"].calls, [0])
        self.assertEqual(v["source_runs"], 1)
        self.assertEqual(v["counts"]["unique_eligible_anchors"], 5)
        self.assertEqual(v["added_ids"], ["colocated", "reserve_fail_a", "reserve_fail_b", "zero_distance"])
        self.assertEqual(v["counts"]["added_floor_pass_reserve_fail"], 2)
        rows = {x["site_id"]: x for x in v["sites"]}
        for original in f["baseline_sites"]:
            self.assertEqual(rows[original["site_id"]], original)
        verdict = {x["anchor_node"]: x for x in v["anchor_verdicts"]}
        self.assertEqual(verdict[2]["selected_distance_m"], "9")
        self.assertEqual(verdict[2]["arrival_energy_kwh"], "1")
        self.assertEqual(verdict[2]["edge_path_sha256"], digest(canonical([0, 1])))
        self.assertFalse(verdict[2]["reserve_pass"])
        self.assertFalse(verdict[3]["road_reachable"])
        self.assertFalse(verdict[6]["minimum_floor_pass"])
        self.assertEqual(v["unchanged_query"], f["query"])
        self.assertFalse(v["launchable"])
        self.assertFalse(v["runtime_admission_complete"])
        self.assertFalse(v["native_provenance_authenticated_here"])
        self.assertFalse(v["catalog_completeness_authenticated_here"])
        self.assertIsNone(v["loaded_sparse_domain_sha256"])
        self.assertEqual(v["domain_sha256"], digest(canonical(v["descriptor"])))

    def test_zero_headroom_keeps_zero_length_and_all_original_sites(self):
        f = fixture()
        f["query"]["initial_energy_kwh"] = "0"
        rebind(f)
        v = self.result(f).as_dict()
        self.assertEqual(v["status"], "proposed_complete")
        self.assertEqual(v["added_ids"], ["zero_distance"])
        self.assertEqual(v["counts"]["added_floor_pass_reserve_fail"], 1)
        self.assertIn("base_charge", v["candidate_ids"])
        self.assertEqual(f["router"].calls, [0])

    def test_exact_floor_boundary_is_inclusive(self):
        f = fixture()
        f["query"]["minimum_energy_kwh"] = "1"
        rebind(f)
        v = self.result(f).as_dict()
        self.assertIn("reserve_fail_a", v["added_ids"])
        self.assertIn("reserve_fail_b", v["added_ids"])

    def test_no_additions_is_completed_not_unknown(self):
        f = fixture()
        f["eligible_charging_sites"] = [copy.deepcopy(f["baseline_sites"][0]), site("unreachable", 3)]
        rebind(f)
        v = self.result(f).as_dict()
        self.assertEqual(v["status"], "proposed_complete")
        self.assertTrue(v["complete"])
        self.assertEqual(v["added_ids"], [])
        self.assertEqual(v["counts"]["added"], 0)
        self.assertEqual(v["candidate_ids"], ["base_charge", "base_meal"])

    def test_no_eligible_chargers_needs_no_source(self):
        f = fixture()
        f["baseline_sites"] = [site("meal_only", 3, ("S",))]
        f["eligible_charging_sites"] = []
        rebind(f)
        v = self.result(f).as_dict()
        self.assertEqual(v["status"], "proposed_complete")
        self.assertEqual(v["source_runs"], 0)
        self.assertEqual(f["router"].calls, [])

    def test_cap_overflow_drops_no_ids_and_returns_no_domain(self):
        f = fixture()
        f["cap"] = 5
        result = self.result(f)
        self.assertIs(result.status, ProposalStatus.FALLBACK_REQUIRED)
        v = result.as_dict()
        self.assertTrue(v["complete"])
        self.assertEqual(v["counts"]["total"], 6)
        self.assertEqual(v["counts"]["completed_anchors"], 5)
        for key in ("candidate_ids", "sites", "descriptor", "domain_sha256", "candidate_sha256"):
            self.assertIsNone(v[key])
        self.assertEqual(f["router"].calls, [0])

    def test_result_is_immutable_detached_and_deterministic(self):
        f = fixture()
        a, b = self.result(f), self.result(fixture())
        self.assertEqual(a.payload_bytes, b.payload_bytes)
        first = a.as_dict()
        first["sites"][0]["effects"].clear()
        f["baseline_sites"][0]["effects"].clear()
        self.assertEqual(a.payload_bytes, b.payload_bytes)
        self.assertNotEqual(first, a.as_dict())
        with self.assertRaises(FrozenInstanceError):
            a.status = ProposalStatus.UNKNOWN

    def test_changed_query_catalog_baseline_and_eligibility_fail_before_routing(self):
        mutators = [lambda f: f["query"].update(initial_energy_kwh="9"),
                    lambda f: f["query"]["schedule"].update(a="101"),
                    lambda f: f["baseline_sites"][0].update(original_note="changed"),
                    lambda f: f["eligible_charging_sites"].pop(),
                    lambda f: f["eligibility"].update(od_id="other_od"),
                    lambda f: f["bindings"]["catalog_source_sha256"].update(sites="3" * 64)]
        for mutate in mutators:
            with self.subTest(mutate=mutate):
                f = fixture()
                mutate(f)
                self.assert_unknown(f)
                self.assertEqual(f["router"].calls, [])

    def test_bound_but_semantically_invalid_eligibility_is_unknown(self):
        for changes in ({"complete": False}, {"eligible_charging_count": True},
                        {"policy_version": "new_heuristic"}, {"origin": "road:1"},
                        {"eligible_candidate_sha256": "0" * 64}):
            f = fixture()
            f["eligibility"].update(changes)
            f["bindings"]["eligibility_sha256"] = digest(canonical(f["eligibility"]))
            self.assert_unknown(f)
            self.assertEqual(f["router"].calls, [])

    def test_no_caller_reachability_and_original_endpoint_exclusions(self):
        for update in ({"minimum_floor_pass": True}, {"access_node": 0, "anchor_id": "road:0"},
                       {"effects": ["S"]}):
            f = fixture()
            f["eligible_charging_sites"][1].update(update)
            rebind(f)
            self.assert_unknown(f)
            self.assertEqual(f["router"].calls, [])

    def test_strict_bool_float_node_cap_and_effect_types(self):
        for name, value in (("cap", True), ("cap", 0), ("cap", 2.0)):
            f = fixture()
            f[name] = value
            self.assert_unknown(f)
        for value in (True, 1.0, "1"):
            f = fixture()
            f["eligible_charging_sites"][1]["access_node"] = value
            rebind(f)
            self.assert_unknown(f)
        for value in (True, 1.0, "nan", "1/0"):
            f = fixture()
            f["query"]["initial_energy_kwh"] = value
            rebind(f)
            self.assert_unknown(f)
        for effects in (["CS"], ["C", "C"], ["C", True]):
            f = fixture()
            f["eligible_charging_sites"][1]["effects"] = effects
            rebind(f)
            self.assert_unknown(f)

    def test_duplicate_missing_baseline_and_row_drift_fail_closed(self):
        f = fixture()
        f["eligible_charging_sites"].append(copy.deepcopy(f["eligible_charging_sites"][1]))
        rebind(f)
        self.assert_unknown(f, "duplicate")
        f = fixture()
        f["eligible_charging_sites"].pop(0)
        rebind(f)
        self.assert_unknown(f, "baseline missing")
        f = fixture()
        f["eligible_charging_sites"][0]["effects"] = ["C"]
        rebind(f)
        self.assert_unknown(f, "row drift")

    def test_source_provenance_mismatch_fails_before_native(self):
        f = fixture()
        f["bindings"]["source_sha256"]["router"] = "4" * 64
        self.assert_unknown(f, "Router source")
        self.assertEqual(f["router"].calls, [])
        f = fixture()
        f["router"].provenance["source_sha256"] = "4" * 64
        self.assert_unknown(f, "Native provenance")
        self.assertEqual(f["router"].calls, [])

    def test_source_failure_is_unknown_not_empty_union(self):
        f = fixture()
        def fail(_):
            raise RuntimeError("tiny source failed")
        f["router"].hook = fail
        v = self.assert_unknown(f, "tiny source failed")
        self.assertEqual(v["source_runs"], 1)
        self.assertEqual(v["source_completed_runs"], 0)
        self.assertEqual(f["router"].calls, [0])

    def test_partial_path_failure_never_returns_partial_domain(self):
        f = fixture()
        def bad_path(labels):
            labels[3][2] = 2  # direct edge is not the reported predecessor 1->2
            return labels
        f["router"].hook = bad_path
        v = self.assert_unknown(f, "predecessor")
        self.assertEqual(v["completed_anchors"], 1)
        self.assertEqual(f["router"].calls, [0])

    def test_exact_replay_rejects_changed_distance_labels(self):
        f = fixture()
        def bad_distance(labels):
            labels[1][2] = 1.0  # shortest-distance route, not native selected path
            return labels
        f["router"].hook = bad_distance
        self.assert_unknown(f, "does not replay")
        self.assertEqual(f["router"].calls, [0])

    def test_uncacheable_labels_do_not_trigger_second_source(self):
        f = fixture()
        f["router"].hook = lambda arrays: tuple(array.tolist() for array in arrays)
        self.assert_unknown(f, "not retained once")
        self.assertEqual(f["router"].calls, [0])

    def test_fixed_source_wrapper_blocks_second_and_foreign_source(self):
        router = TinyRouter()
        wrapper = OneSourceRouter(router, 0, digest(canonical(router.provenance)), lambda: None)
        for bad in (1, True, "0"):
            with self.assertRaises(PolicyError):
                wrapper.full_edges(bad)
        self.assertEqual(router.calls, [])
        wrapper.full_edges(0)
        with self.assertRaises(PolicyError):
            wrapper.full_edges(0)
        self.assertEqual(router.calls, [0])

    def test_mid_source_input_or_provenance_mutation_is_unknown(self):
        for kind in ("query", "catalog", "provenance"):
            f = fixture()
            def mutate(labels):
                if kind == "query":
                    f["query"]["initial_energy_kwh"] = "9"
                elif kind == "catalog":
                    f["eligible_charging_sites"].pop()
                else:
                    f["router"].provenance["source_sha256"] = "5" * 64
                return labels
            f["router"].hook = mutate
            self.assert_unknown(f, "changed during query")
            self.assertEqual(f["router"].calls, [0])

    def test_mutable_or_replaced_graph_is_rejected(self):
        f = fixture()
        f["graph"].source.flags.writeable = True
        self.assert_unknown(f, "immutable")
        self.assertEqual(f["router"].calls, [])
        f = fixture()
        def replace_graph(labels):
            f["graph"].source = f["graph"].source.copy()
            f["graph"].source.flags.writeable = False
            return labels
        f["router"].hook = replace_graph
        self.assert_unknown(f, "graph changed")
        self.assertEqual(f["router"].calls, [0])

    def test_live_witness_retention_is_one_target_and_labels_cleaned(self):
        captured = []
        class InspectingProvider(TableFreeRoadSelectedLegProvider):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                captured.append(self)
            def leg(self, source, target):
                if self.legs or self.edge_witnesses:
                    raise AssertionError("Previous target route retained")
                result = super().leg(source, target)
                if len(self._source_labels) != 1:
                    raise AssertionError("Expected one retained source")
                return result
        with patch.object(policy, "TableFreeRoadSelectedLegProvider", InspectingProvider):
            self.assertIs(self.result(fixture()).status, ProposalStatus.PROPOSED_COMPLETE)
            f = fixture()
            f["router"].hook = lambda labels: (_ for _ in ()).throw(RuntimeError("failed"))
            self.assert_unknown(f)
        for provider in captured:
            self.assertEqual(provider.legs, {})
            self.assertEqual(provider.edge_witnesses, {})
            self.assertEqual(len(provider._source_labels), 0)
            self.assertEqual(provider.source_cache_bytes, 0)


if __name__ == "__main__":
    unittest.main()
