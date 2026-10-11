from fractions import Fraction as F
import json
from math import inf
from pathlib import Path
import unittest

from timecut5.deployable import (
    DomainBinding, LandmarkDistances, RegionLandmarkSummary, RouteContract,
    SearchOutcome, SelectedLegCache, SolveStatus, VerifiedSeed,
    certified_depth, check_region_summary_offline, constructive_seed_candidates,
    directed_alt_region_bound, member_set_digest,
)
from timecut5.real_legs import ImmutableLegTable, SelectedLeg
from validation.reference5.real_input import IndependentLegTable
from validation.reference5.real_solver import replay_real_witness


D = "a" * 64
E = "b" * 64
F_HASH = "c" * 64


def domain():
    return DomainBinding(D, D, D, D, D, D, D, D, D, D, D)


class DeployableContractTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
