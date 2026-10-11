from fractions import Fraction as F
import hashlib
import inspect
import json
from math import inf
from pathlib import Path
import unittest

from timecut5.deployable import (
    DomainBinding, LandmarkDistances, QueryDomain, RegionBoundProvider,
    RegionLandmarkSummary, RouteContract,
    SearchOutcome, SelectedLegCache, SolveStatus, VerifiedSeed,
    certified_depth, check_region_summary_offline, construct_verified_seed,
    constructive_seed_candidates, prepared_checkpoint_bytes, solve_deployable_pair,
    directed_alt_region_bound, member_set_digest,
)
from timecut5.real_legs import ImmutableLegTable, SelectedLeg, restrict_frozen_tree
from timecut5.hierarchy import Region
from timecut5.real_legs import NUMERICS, TIE_POLICY
from validation.reference5.real_input import IndependentLegTable
from validation.reference5.real_solver import replay_real_witness, solve_real_case


D = "a" * 64
E = "b" * 64
F_HASH = "c" * 64


def domain():
    return DomainBinding(D, D, D, D, D, D, D, D, D, D, D)


class DeployableContractTest(unittest.TestCase):
    def test_byte_closure_and_route_policy(self):
        sources = {name: (name.encode(), hashlib.sha256(name.encode()).hexdigest())
                   for name in DomainBinding.__dataclass_fields__}
        bound = DomainBinding.from_verified_bytes(sources)
        self.assertEqual(bound.graph_sha256, sources["graph_sha256"][1])
        tampered = dict(sources, graph_sha256=(b"changed", sources["graph_sha256"][1]))
        with self.assertRaises(ValueError):
            DomainBinding.from_verified_bytes(tampered)
        with self.assertRaises(ValueError):
            DomainBinding.from_verified_bytes({k: v for k, v in sources.items() if k != "graph_sha256"})
        route_bytes = {name: name.encode() for name in RouteContract.__dataclass_fields__
                       if name.endswith("_sha256")}
        route_bytes.update(tie_policy_sha256=TIE_POLICY.encode(),
                           direction_policy_sha256=b"forward_per_source_v1",
                           numerical_contract_sha256=NUMERICS.encode())
        route_sources = {name: (value, hashlib.sha256(value).hexdigest())
                         for name, value in route_bytes.items()}
        contract = RouteContract.from_verified_bytes(route_sources, direction_policy="forward_per_source_v1")
        with self.assertRaises(ValueError):
            RouteContract.from_verified_bytes(route_sources, direction_policy="explicit_per_leg_v1")
        def reverse_provider(a, b):
            return SelectedLeg(a, b, True, F(1), F(1), "reverse_from_target",
                               float(1).hex(), float(1).hex())
        with self.assertRaises(ValueError):
            SelectedLegCache(contract, reverse_provider).leg("a", "b")

    def test_status_and_same_domain_depth_gate(self):
        bound = domain()
        seed = VerifiedSeed(bound, F(3600), E, F_HASH)
        self.assertEqual(certified_depth(seed, bound, F(300), F(600)), 4)
        changed = DomainBinding(D, D, D, D, D, D, E, D, D, D, D)
        with self.assertRaises(ValueError):
            certified_depth(seed, changed, F(300), F(600))
        with self.assertRaises(ValueError):
            certified_depth(seed, bound, F(0), F(600))
        SearchOutcome(bound, SolveStatus.INFIMUM_UNATTAINED_J, j=F(10))
        with self.assertRaises(ValueError):
            SearchOutcome(bound, SolveStatus.INFIMUM_UNATTAINED_J, j=F(10), q=F(1))
        with self.assertRaises(ValueError):
            SearchOutcome(bound, SolveStatus.ATTAINED_OPTIMUM, j=F(10), q=F(1),
                          h=1, pi=(("site", "C"),))

    def test_directed_cache_preserves_selected_length(self):
        calls = []

        def provider(a, b):
            calls.append((a, b))
            length = 17 if a == "a" else 23
            return SelectedLeg(a, b, True, F(1), F(length),
                               "forward_from_source", float(1).hex(), float(length).hex())

        cache = SelectedLegCache(RouteContract(D, D, D, D, D, D), provider)
        self.assertEqual(cache.leg("a", "b").actual_length, F(17))
        self.assertEqual(cache.leg("a", "b").actual_length, F(17))
        self.assertEqual(cache.leg("b", "a").actual_length, F(23))
        self.assertEqual(calls, [("a", "b"), ("b", "a")])
        self.assertEqual((cache.hits, cache.misses), (1, 2))

    def test_constructive_seed_uses_no_optimizer_and_independent_replay(self):
        fixture = Path(__file__).resolve().parents[1] / "results/milestone_5_real_leg_contract/mock_solver_cases.json"
        case = json.loads(fixture.read_text())[1]
        data = json.dumps(case["table"], sort_keys=True, separators=(",", ":")).encode()
        table = ImmutableLegTable.from_bytes(data, case["table_sha256"])
        independent = IndependentLegTable.from_bytes(data, case["table_sha256"])
        query = dict(case["query"], leg_payload_sha256=table.payload_sha256,
                     selection_certificate_sha256=table.selection_certificate_sha256,
                     hierarchy_sha256=table.hierarchy_sha256)
        proposals = constructive_seed_candidates(query, table)
        self.assertTrue(proposals)
        independently_feasible = []
        for sequence, charges in proposals:
            try:
                independently_feasible.append(replay_real_witness(query, independent, sequence, charges))
            except (ValueError, AssertionError):
                pass
        self.assertTrue(independently_feasible)
        self.assertTrue(all(result["witness_replayed"] for result in independently_feasible))
        with self.assertRaises(ValueError):
            constructive_seed_candidates(dict(query, leg_payload_sha256=E), table)

    def test_directed_alt_skips_nonfinite_terms_and_checks_summary(self):
        # Landmark 0's forward term is useful, while its reverse term is +inf
        # subtraction. Landmark 1 has a finite reverse term only.
        landmarks = (
            LandmarkDistances({"v": 3, "x": 8, "y": 9},
                              {"v": 20, "x": inf, "y": 5}),
            LandmarkDistances({"v": inf, "x": 1, "y": 2},
                              {"v": 12, "x": 3, "y": 4}),
        )
        member_hash = member_set_digest(("x", "y"))
        summary = RegionLandmarkSummary(member_hash, D, F_HASH, (8, 1), (inf, 4))
        self.assertTrue(check_region_summary_offline(("x", "y"), landmarks, summary))
        self.assertEqual(directed_alt_region_bound("v", landmarks, summary,
                         graph_sha256=D, landmark_sha256=F_HASH,
                         member_set_sha256=member_hash), 8)
        with self.assertRaises(ValueError):
            directed_alt_region_bound("v", landmarks, summary,
                        graph_sha256=D, landmark_sha256=F_HASH,
                        member_set_sha256=D)
        bad = RegionLandmarkSummary(member_hash, D, F_HASH, (9, 1), (inf, 4))
        self.assertFalse(check_region_summary_offline(("x", "y"), landmarks, bad))

    def test_bound_query_independent_seed_to_depth(self):
        fixture = Path(__file__).resolve().parents[1] / "results/milestone_5_real_leg_contract/mock_solver_cases.json"
        case = json.loads(fixture.read_text())[1]
        table_bytes = json.dumps(case["table"], sort_keys=True, separators=(",", ":")).encode()
        table = ImmutableLegTable.from_bytes(table_bytes, case["table_sha256"])
        query = dict(case["query"], leg_payload_sha256=table.payload_sha256,
                     selection_certificate_sha256=table.selection_certificate_sha256,
                     hierarchy_sha256=table.hierarchy_sha256)
        query_bytes = json.dumps(query, sort_keys=True, separators=(",", ":")).encode()
        candidate_bytes = json.dumps(sorted(table.sites)).encode()
        digests = {name: hashlib.sha256(name.encode()).hexdigest()
                   for name in DomainBinding.__dataclass_fields__}
        digests.update(query_sha256=hashlib.sha256(query_bytes).hexdigest(),
                       candidate_set_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
                       hierarchy_sha256=table.hierarchy_sha256,
                       mobility_budget_sha256=hashlib.sha256(b"unrestricted").hexdigest(),
                       depth_policy_sha256=hashlib.sha256(
                           b"positive_overhead_verified_seed_v1").hexdigest())
        binding = DomainBinding(**digests)
        domain = QueryDomain(binding, query_bytes, candidate_bytes, table_bytes,
                             case["table_sha256"])
        from validation.reference5 import model, real_input, real_solver, solver
        verifier_hashes = {name: hashlib.sha256(Path(inspect.getsourcefile(module)).read_bytes()).hexdigest()
                           for name, module in (("real_solver", real_solver),
                               ("real_input", real_input), ("model", model), ("solver", solver))}
        result = construct_verified_seed(domain, verifier_hashes)
        self.assertNotIsInstance(result, SearchOutcome)
        self.assertEqual(result.seed.domain, binding)
        self.assertEqual(result.seed.independent_verifier_sha256,
                         hashlib.sha256(json.dumps(dict(sorted(verifier_hashes.items())),
                         sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        self.assertEqual(result.max_depth, certified_depth(result.seed, binding,
                         F(query["overhead_s"]), F(query["lambda_stop_s"])))
        self.assertLessEqual(len(result.sequence), result.max_depth)
        independent = IndependentLegTable.from_bytes(table_bytes, case["table_sha256"])
        self.assertEqual(result.seed.primary_j,
                         replay_real_witness(query, independent, result.sequence,
                                             result.charges)["J"])
        with self.assertRaises(ValueError):
            QueryDomain(binding, query_bytes, b"[]", table_bytes, case["table_sha256"])
        duplicated = query_bytes[:-1] + b',"origin":"tampered"}'
        duplicated_binding = DomainBinding(**dict(digests,
                           query_sha256=hashlib.sha256(duplicated).hexdigest()))
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            QueryDomain(duplicated_binding, duplicated, candidate_bytes, table_bytes,
                        case["table_sha256"])
        with self.assertRaises(ValueError):
            construct_verified_seed(domain, dict(verifier_hashes, real_input=D))
        with self.assertRaises(ValueError):
            QueryDomain(DomainBinding(**dict(digests, mobility_budget_sha256=D)),
                        query_bytes, candidate_bytes, table_bytes, case["table_sha256"])
        from dataclasses import replace
        with self.assertRaises(ValueError):
            replace(result, max_depth=len(result.sequence))
        with self.assertRaises(ValueError):
            replace(result, charges=(F(2),) if result.charges else (F(1),))
        hierarchy_bytes = json.dumps(case["original_tree"], sort_keys=True,
                                     separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(hierarchy_bytes).hexdigest(), table.hierarchy_sha256)
        checkpoint = prepared_checkpoint_bytes(result, hierarchy_bytes)
        pair = solve_deployable_pair(result, hierarchy_bytes, verifier_hashes,
                                     prepared_checkpoint=checkpoint)
        self.assertEqual(pair.flat.status, SolveStatus.ATTAINED_OPTIMUM)
        self.assertEqual(pair.flat, pair.hier)
        self.assertEqual(pair.hier_bound_member_scans, 0)
        self.assertGreater(pair.hier_provider_queries, 0)
        self.assertEqual(pair.shared_seed_cache_misses, 3)
        self.assertGreaterEqual(pair.flat_cache_misses, pair.shared_seed_cache_misses)
        self.assertGreaterEqual(pair.hier_cache_misses, pair.shared_seed_cache_misses)
        keys = set(table.anchors) | set(table.sites)
        landmark = LandmarkDistances({key: 0 for key in keys},
                                     {key: inf for key in keys})
        empty_child_tree = Region(0, tuple(sorted(table.sites)), (
            Region(1, ()), Region(2, ("A",)), Region(3, ("B",))))
        summaries = {region_id: RegionLandmarkSummary(
            member_set_digest((site,)) if region_id else member_set_digest(tuple(sorted(table.sites))),
            binding.graph_sha256, binding.landmark_sha256, (0,), (inf,))
            for region_id, site in ((0, "A"), (2, "A"), (3, "B"))}
        provider = RegionBoundProvider(domain, empty_child_tree,
                                       landmarks=(landmark,), summaries=summaries)
        self.assertEqual(provider.online_member_leg_lookups, 0)
        alt_pair = solve_deployable_pair(result, hierarchy_bytes, verifier_hashes,
                                         landmarks=(landmark,), summaries={
            row.region_id: RegionLandmarkSummary(member_set_digest(row.site_ids),
                binding.graph_sha256, binding.landmark_sha256, (0,), (inf,))
            for row in restrict_frozen_tree(hierarchy_bytes, table.hierarchy_sha256,
                                            list(table.sites)).regions if row.site_ids})
        self.assertEqual(alt_pair.flat, pair.flat)
        self.assertEqual(alt_pair.hier, pair.hier)
        excessive = LandmarkDistances({key: 100 for key in keys} | {"road:o": 0},
                                      {key: inf for key in keys})
        with self.assertRaises(ValueError):
            RegionBoundProvider(domain, empty_child_tree, landmarks=(excessive,),
                                summaries={region_id: RegionLandmarkSummary(
                                    member_set_digest((site,)) if region_id else
                                    member_set_digest(tuple(sorted(table.sites))),
                                    binding.graph_sha256, binding.landmark_sha256,
                                    (100,), (inf,)) for region_id, site in
                                    ((0, "A"), (2, "A"), (3, "B"))})
        reference = solve_real_case(query, independent, regime_limit=10)
        self.assertEqual(reference["preflight"]["counts"]["continuous_regimes"], 3)
        self.assertEqual((pair.flat.j, pair.flat.q, pair.flat.h, pair.flat.pi),
                         reference["result"]["lex_key"])
        with self.assertRaises(ValueError):
            solve_deployable_pair(result, b"{}", verifier_hashes)
        with self.assertRaises(ValueError):
            solve_deployable_pair(result, hierarchy_bytes, verifier_hashes,
                                  prepared_checkpoint=checkpoint.replace(
                                      b"before_search_no_open_state", b"partial_open_state"))

    def test_retained_schedule_already_satisfied_and_two_charge_seed(self):
        fixture = Path(__file__).resolve().parents[1] / "results/milestone_5_real_leg_contract/mock_solver_cases.json"
        cases = json.loads(fixture.read_text())
        scheduled = cases[0]
        data = json.dumps(scheduled["table"], sort_keys=True, separators=(",", ":")).encode()
        table = ImmutableLegTable.from_bytes(data, scheduled["table_sha256"])
        independent = IndependentLegTable.from_bytes(data, scheduled["table_sha256"])
        query = dict(scheduled["query"], initial_remaining_schedule=0,
                     leg_payload_sha256=table.payload_sha256,
                     selection_certificate_sha256=table.selection_certificate_sha256,
                     hierarchy_sha256=table.hierarchy_sha256)
        proposals = constructive_seed_candidates(query, table)
        self.assertTrue(any(sequence == (("A", "C"),) for sequence, _ in proposals))
        self.assertTrue(any(replay_real_witness(query, independent, sequence, charges)["witness_replayed"]
                            for sequence, charges in proposals if sequence == (("A", "C"),)))

        modified = json.loads(json.dumps(cases[1]["table"]))
        for leg in modified["legs"]:
            if (leg["source_anchor"], leg["target_anchor"]) == ("road:o", "road:b"):
                leg["actual_length_m"] = {"hex": float(4).hex(), "ratio": ["4", "1"]}
        data = json.dumps(modified, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(data).hexdigest()
        table = ImmutableLegTable.from_bytes(data, digest)
        independent = IndependentLegTable.from_bytes(data, digest)
        query = dict(cases[1]["query"], leg_payload_sha256=table.payload_sha256,
                     selection_certificate_sha256=table.selection_certificate_sha256,
                     hierarchy_sha256=table.hierarchy_sha256)
        proposals = constructive_seed_candidates(query, table)
        feasible = []
        for sequence, charges in proposals:
            try:
                replay_real_witness(query, independent, sequence, charges)
                feasible.append(sequence)
            except (ValueError, AssertionError):
                pass
        self.assertTrue(feasible)
        self.assertTrue(all(len(sequence) >= 2 for sequence in feasible))

        shifted = dict(query, start_time_s=11)
        shifted_proposals = constructive_seed_candidates(shifted, table)
        shifted_feasible = [replay_real_witness(shifted, independent, sequence, charges)
                            for sequence, charges in shifted_proposals
                            if sequence == (("A", "C"), ("B", "C")) and
                            charges == (F(1, 2), F(1, 2))]
        self.assertTrue(shifted_feasible)
        self.assertEqual(shifted_feasible[0]["J"], F(6))

    def test_coattached_sites_keep_distinct_action_identity(self):
        fixture = Path(__file__).resolve().parents[1] / "results/milestone_5_real_leg_contract/mock_solver_cases.json"
        case = json.loads(fixture.read_text())[1]
        payload = json.loads(json.dumps(case["table"]))
        payload["sites"][1]["anchor_id"] = "road:x"
        for leg in payload["legs"]:
            if (leg["source_anchor"], leg["target_anchor"]) == ("road:x", "road:z"):
                leg["time_s"] = {"hex": float(1).hex(), "ratio": ["1", "1"]}
                leg["actual_length_m"] = {"hex": float(1).hex(), "ratio": ["1", "1"]}
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(data).hexdigest()
        table = ImmutableLegTable.from_bytes(data, digest)
        self.assertEqual(table.site("A").anchor_id, table.site("B").anchor_id)
        query = dict(case["query"], leg_payload_sha256=table.payload_sha256,
                     selection_certificate_sha256=table.selection_certificate_sha256,
                     hierarchy_sha256=table.hierarchy_sha256)
        proposals = constructive_seed_candidates(query, table)
        identities = {sequence[0][0] for sequence, _ in proposals if len(sequence) == 1}
        self.assertEqual(identities, {"A", "B"})


if __name__ == "__main__":
    unittest.main()
