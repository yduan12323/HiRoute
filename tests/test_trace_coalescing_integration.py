"""Merged-base integration on a hand-authored tiny synthetic graph."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from timecut5.bounded import Problem, _solve_problem, solve_bounded
from timecut5.coalesced_solver import solve_bounded_coalesced, solve_hierarchical_coalesced
from timecut5.hierarchy import _solve_hierarchical_problem, build_regions, solve_hierarchical
from timecut5.invocation_trace import InvocationTrace
from timecut5.provenance import Recorder
from timecut5.pwa import reduce_frontier
from validation.trace5 import verify_trace


def result_key(result):
    value = result.canonical()['result']
    status = value['status']
    if status == 'attained_optimum':
        return (status, Fraction(value['J']), Fraction(value['Q_total']), value['H'],
                tuple(map(tuple, value['site_action_tuple'])))
    if status == 'primary_unattained':
        return status, Fraction(value['primary_infimum'])
    if status == 'secondary_unattained':
        return status, Fraction(value['J']), Fraction(value['secondary_infimum'])
    return status,


class TraceCoalescingIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads((ROOT / 'tests/fixtures/invocation_trace_pilot_v1.json').read_text())

    def test_untraced_baseline_and_optional_modes_keep_the_same_key(self):
        self.assertIsNone(Problem(self.case).initial_piece()._family)
        expected = result_key(solve_bounded(self.case, dominance=False))
        for solver in (solve_bounded, solve_hierarchical,
                       solve_bounded_coalesced, solve_hierarchical_coalesced):
            for dominance in (False, True):
                with self.subTest(solver=solver.__name__, dominance=dominance):
                    self.assertEqual(result_key(solver(self.case, dominance=dominance)), expected)

    def test_both_private_cores_still_honor_explicit_reducer_hooks(self):
        for hierarchical in (False, True):
            with self.subTest(hierarchical=hierarchical):
                calls = []

                def reducer(pieces):
                    calls.append(len(pieces))
                    return reduce_frontier(pieces)

                problem = Problem(deepcopy(self.case))
                if hierarchical:
                    value = _solve_hierarchical_problem(
                        problem, True, build_regions(problem.sites), reducer=reducer)
                else:
                    value = _solve_problem(problem, True, reducer=reducer)
                self.assertTrue(calls)
                self.assertEqual(result_key(value), result_key(solve_bounded(self.case)))

    def test_recorded_baseline_is_independently_checkable_and_stays_a_pilot(self):
        plain = solve_hierarchical(self.case)
        with Recorder() as recorder, InvocationTrace(recorder) as trace:
            recorded = solve_hierarchical(self.case)
        stream = trace.export()
        bundle = recorder.export()
        bundle['roots'] = stream['events'][-1]['payload']['terminal_families']
        checked = verify_trace(stream, bundle, self.case)
        self.assertEqual(result_key(recorded), result_key(plain))
        self.assertTrue(checked.summary['verified'])
        self.assertFalse(checked.summary['literal_G8_closed'])

    def test_optional_modes_fail_closed_with_active_family_recording(self):
        for solver in (solve_bounded_coalesced, solve_hierarchical_coalesced):
            for dominance in (False, True):
                with self.subTest(solver=solver.__name__, dominance=dominance):
                    with self.assertRaisesRegex(ValueError, 'before processing'):
                        with Recorder():
                            solver(self.case, dominance=dominance)
                    self.assertIsNone(Problem(self.case).initial_piece()._family)
                    self.assertEqual(result_key(solver(self.case, dominance=dominance)),
                                     result_key(solve_bounded(self.case)))

    def test_trace_does_not_claim_completion_when_optional_mode_rejects_a_family(self):
        with self.assertRaisesRegex(ValueError, 'before processing'):
            with Recorder() as recorder, InvocationTrace(recorder) as trace:
                solve_hierarchical_coalesced(self.case)
        self.assertTrue(recorder.nodes)
        self.assertNotIn('run_end', [event['kind'] for event in trace.export()['events']])
        self.assertIsNone(Problem(self.case).initial_piece()._family)


if __name__ == '__main__':
    unittest.main()
