"""Bounded tiny-hierarchy coverage, bounds, equality and physical parity checks."""
from copy import deepcopy
from fractions import Fraction as R
import json
from pathlib import Path
import unittest

from timecut5.bounded import Problem, evaluate_sequence, replay_witness
from timecut5.hierarchy import actions, build_regions, region_bound, solve_hierarchical


ROOT = Path(__file__).resolve().parents[1]


def normalized_expected(expected):
    result = dict(expected)
    for key in ("J","Q_total","primary_infimum","secondary_infimum"):
        if key in result:
            result[key] = R(result[key])
    if "site_action_tuple" in result:
        result["site_action_tuple"] = tuple(tuple(x) for x in result["site_action_tuple"])
    if "lex_key" in result:
        j,q,h,pi = result["lex_key"]
        result["lex_key"] = (R(j),R(q),h,tuple(tuple(x) for x in pi))
    return result


class TestBoundedHierarchy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / "results/milestone_5_reference/frozen_cases_v2.json").read_text())
        cls.original = json.loads((ROOT / "results/milestone_4r_b2_b21/hand_cases.json").read_text())[0]

    def test_exact_static_action_partitions(self):
        case = next(c for c in self.cases if c["case_id"].startswith("deterministic_site_tuple"))
        problem = Problem(case)
        tree = build_regions(problem.sites)
        def check(region):
            if region.children:
                self.assertEqual(set(region.members), set.union(*(set(c.members) for c in region.children)))
                self.assertEqual(sum(len(c.members) for c in region.children),len(region.members))
                for r in (0,1):
                    for effect in ("C","S","CS"):
                        parent = actions(problem,region,effect,r)
                        children = [a for c in region.children for a in actions(problem,c,effect,r)]
                        self.assertEqual(set(parent),set(children))
                        self.assertEqual(len(children),len(set(children)))
                for child in region.children: check(child)
        check(tree)

    def test_all_frozen_positive_cases_both_reduction_modes(self):
        for case in self.cases:
            expected = normalized_expected(case["independent_expected"])
            for dominance in (False,True):
                with self.subTest(case=case["case_id"],dominance=dominance):
                    result = solve_hierarchical(case,dominance)
                    actual = result.canonical()["result"]
                    for key,value in expected.items(): self.assertEqual(actual[key],value)
                    self.assertEqual((result.missing_actions,result.duplicate_actions),(0,0))
                    if result.bounded.result.witness is not None:
                        self.assertEqual(replay_witness(case,result.bounded.result.witness),
                                         result.bounded.result.key)

    def test_original76_with_own_incumbent_and_strict_prune_certificates(self):
        result = solve_hierarchical(self.original)
        self.assertEqual(result.bounded.result.key[:3],(44950,76,3))
        self.assertEqual(result.incumbent_source,"own_search")
        self.assertEqual((result.missing_actions,result.duplicate_actions),(0,0))
        self.assertGreater(result.pruned_regions,0)
        self.assertGreater(result.equality_nodes_retained,0)
        for record in result.pruning_audit:
            if record["reason"]=="strict_primary":
                self.assertGreater(record["lower_bound"],record["incumbent_key"][0])
                self.assertEqual(replay_witness(self.original,record["incumbent_witness"]),
                                 record["incumbent_key"])

    def test_equal_primary_cannot_prune_a_lower_charge_candidate(self):
        case = deepcopy(next(c for c in self.cases if c["case_id"].startswith("deterministic_site_tuple")))
        for edge in case["edges"]:
            if edge["source"]=="b" and edge["target"]=="z": edge["length_m"] += 1
        supplied = evaluate_sequence(case,(("b","CS"),)).witness
        result = solve_hierarchical(case,incumbent=supplied)
        self.assertEqual(result.incumbent_source,"externally_supplied_verified")
        self.assertEqual(result.bounded.result.key,(13,2,1,(("a","CS"),)))
        self.assertGreater(result.equality_nodes_retained,0)

    def test_bounds_below_exact_one_action_clock_completion(self):
        for case in self.cases:
            problem = Problem(case)
            prefix = (problem.initial_piece(),)
            tree = build_regions(problem.sites)
            for effect in ("C","S","CS"):
                lower,_ = region_bound(problem,prefix,tree,effect)
                if lower is None: continue
                for site,_ in actions(problem,tree,effect,problem.initial_remaining):
                    outputs = problem.advance(prefix,site,effect)
                    outgoing = problem.legs.get((site,problem.destination))
                    if not outgoing: continue
                    for p in outputs:
                        e,_ = p.domain.affine_infimum(p.slope)
                        relaxed = p.slope*e+p.intercept+outgoing.time-problem.start+problem.penalty
                        self.assertLessEqual(lower,relaxed)

    def test_post_audit_destination_and_transit_cases(self):
        cases = json.loads((ROOT / "results/milestone_5_reference/audit_regression_cases.json").read_text())
        for case in cases:
            result = solve_hierarchical(case).canonical()["result"]
            for key,value in normalized_expected(case["independent_expected"]).items():
                self.assertEqual(result[key],value)

    def test_post_audit_global_attainment_and_incumbent_regressions(self):
        path = ROOT / "experiments/time_cut_v2/solver_audit/targeted_attainment_cases_v1.json"
        for case in json.loads(path.read_text()):
            expected = normalized_expected(case["independent_expected"])
            supplied = evaluate_sequence(case,tuple(map(tuple,case["external_incumbent_sequence"]))).witness
            self.assertIsNotNone(supplied)
            for dominance in (False,True):
                for external in (False,True):
                    with self.subTest(case=case["case_id"],dominance=dominance,external=external):
                        result = solve_hierarchical(case,dominance,incumbent=supplied if external else None)
                        for key,value in expected.items():
                            self.assertEqual(result.canonical()["result"][key],value)


if __name__ == "__main__":
    unittest.main()
