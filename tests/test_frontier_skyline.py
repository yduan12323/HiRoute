"""Opt-in exact skyline: independent point oracle, full cells and lineage.

All cases are synthetic. Comparison counts test the algorithmic mechanism,
not real-road runtime or completion of a 32/128-candidate exact search.
"""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as R
from itertools import product
import json
import math
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from timecut5.bounded import Problem, _replay_problem, _solve_problem
from timecut5.hierarchy import _solve_hierarchical_problem, build_regions
from timecut5.invocation_trace import InvocationTrace
from timecut5.probe import Cut, Event, Interval, State, Witness, reduce_cuts
from timecut5.provenance import Recorder, signature, witness_dict
from timecut5.pwa import (CutPiece, _same_state_energy_skyline,
                         reduce_frontier, reduce_frontier_skyline)


ROOT = Path(__file__).resolve().parents[1]


def piece(domain, slope=0, intercept=0, chi=True, rho=0, name="a", tag="seed"):
    state = State("x", 0, 1)
    pi = ((name, "C"),)
    def point(energy):
        if not domain.contains(energy):
            raise AssertionError("Witness escaped its original domain")
        tau = slope * energy + intercept
        def approach(epsilon):
            time = tau if chi else tau + epsilon / 2
            return Witness(time, energy, rho, pi, state,
                           (Event("analytic", tag, time, time, energy, energy),))
        return Cut(tau, chi, energy, rho, pi, state, approach)
    return CutPiece(domain, slope, intercept, chi, rho, pi, state, point)


def quadratic_indices(cuts):
    """Independent all-pairs definition, including first equivalent witness.

    Deliberately does not call production dominance or skyline functions.
    """
    def covers(left, right):
        return ((left.tau < right.tau or
                 left.tau == right.tau and (left.chi or not right.chi)) and
                (left.rho < right.rho or
                 left.rho == right.rho and left.pi <= right.pi))
    return tuple(i for i, candidate in enumerate(cuts)
                 if not any(j != i and covers(other, candidate) and
                            (j < i or not covers(candidate, other))
                            for j, other in enumerate(cuts)))


def independent_cells(pieces):
    """Exact separate arrangement construction: knots AND every open cell."""
    knots = {edge for p in pieces for edge in (p.domain.lo, p.domain.hi)}
    for i, left in enumerate(pieces):
        for right in pieces[i + 1:]:
            if left.slope != right.slope:
                energy = (right.intercept - left.intercept) / (left.slope - right.slope)
                if max(left.domain.lo, right.domain.lo) <= energy <= min(left.domain.hi, right.domain.hi):
                    knots.add(energy)
    knots = sorted(knots)
    result = []
    for i, knot in enumerate(knots):
        result.append(Interval(knot, knot))
        if i + 1 < len(knots):
            result.append(Interval(knot, knots[i + 1], False, False))
    return result


def output_signature(pieces):
    result = []
    for p in pieces:
        energy = (p.domain.lo + p.domain.hi) / 2
        result.append((signature(p), tuple(witness_dict(p.at(energy).approach(epsilon))
                       for epsilon in (R(1), R(1, 10**45)))))
    return result


class TestPointSkyline(unittest.TestCase):
    def assert_same_identity(self, cuts):
        expected = tuple(cuts[i] for i in quadratic_indices(cuts))
        result = _same_state_energy_skyline(tuple(cuts))
        self.assertEqual(tuple(map(id, result)), tuple(map(id, expected)))
        self.assertEqual(tuple(map(id, result)), tuple(map(id, reduce_cuts(cuts))))

    def test_exhaustive_two_point_time_attainment_charge_and_prefix_orders(self):
        choices = [piece(Interval(0, 0), intercept=tau, chi=chi, rho=rho, name=name).at(R(0))
                   for tau, chi, rho, name in product((-1, 0, 1), (False, True),
                                                     (-1, 0, 1), ("a", "z"))]
        for left, right in product(choices, repeat=2):
            self.assert_same_identity((left, right))

    def test_random_rational_points_and_duplicate_identity_keep_stable_order(self):
        rng = random.Random(20261017)
        for _ in range(180):
            cuts = []
            for i in range(rng.randrange(1, 48)):
                if cuts and rng.randrange(6) == 0:
                    cuts.append(rng.choice(cuts))
                    continue
                cuts.append(piece(Interval(0, 0), intercept=R(rng.randrange(-9, 10), rng.randrange(1, 5)),
                    chi=bool(rng.randrange(2)), rho=R(rng.randrange(-6, 7), rng.randrange(1, 4)),
                    name=rng.choice(("a", "b", "c")), tag=str(i)).at(R(0)))
            rng.shuffle(cuts)
            self.assert_same_identity(cuts)

    def test_all_nondominated_and_all_equivalent_inputs(self):
        cuts = tuple(piece(Interval(0, 0), intercept=i, rho=128-i,
                           tag=str(i)).at(R(0)) for i in range(128))
        self.assert_same_identity(cuts)
        self.assertEqual(_same_state_energy_skyline(cuts), cuts)
        equivalent = tuple(piece(Interval(0, 0), tag=str(i)).at(R(0)) for i in range(128))
        self.assert_same_identity(equivalent)
        self.assertIs(_same_state_energy_skyline(equivalent)[0], equivalent[0])

    def test_empty_and_cross_state_or_energy_fail_closed(self):
        self.assertEqual(_same_state_energy_skyline(()), ())
        cut = piece(Interval(0, 1)).at(R(0))
        for other in (replace(cut, state=State("other", 0, 1)), replace(cut, energy=R(1))):
            with self.assertRaisesRegex(ValueError, "one physical state and energy"):
                _same_state_energy_skyline((cut, other))

    def test_comparison_growth_is_sort_plus_scan_on_128_point_antichain(self):
        class Counted:
            calls = 0
            def __init__(self, value):
                self.value = value
            def __lt__(self, other):
                type(self).calls += 1
                return self.value < other.value
            def __eq__(self, other):
                type(self).calls += 1
                return self.value == other.value
        n = 128
        order = list(range(n))
        random.Random(72).shuffle(order)
        cuts = tuple(SimpleNamespace(tau=Counted(i), chi=True, rho=Counted(n-i),
                                    pi=(("a", "C"),), state="same", energy=0) for i in order)
        actual = _same_state_energy_skyline(cuts)
        skyline_comparisons = Counted.calls
        Counted.calls = 0
        expected = quadratic_indices(cuts)
        quadratic_comparisons = Counted.calls
        self.assertEqual(tuple(map(id, actual)), tuple(id(cuts[i]) for i in expected))
        self.assertLess(skyline_comparisons, 8*n*math.ceil(math.log2(n)) + 10*n)
        self.assertGreater(quadratic_comparisons, 4*skyline_comparisons)


class TestFrontierSkyline(unittest.TestCase):
    def assert_parity(self, pieces):
        expected = reduce_frontier(pieces)
        actual = reduce_frontier_skyline(pieces)
        self.assertEqual(output_signature(actual), output_signature(expected))
        # Independently compare affine metadata and stable source identity on
        # every complete symbolic cell, not a grid of selected energy values.
        oracle = []
        for cell in independent_cells(pieces):
            energy = (cell.lo + cell.hi) / 2
            active = tuple(p for p in pieces if p.domain.contains(energy))
            cuts = tuple(p.at(energy) for p in active)
            winners = {id(cuts[i]) for i in quadratic_indices(cuts)}
            for p, cut in zip(active, cuts):
                if id(cut) in winners:
                    oracle.extend(output_signature((replace(p, domain=cell),)))
        self.assertEqual(output_signature(actual), oracle)
        return actual

    def test_crossing_open_and_singleton_endpoint_matrix(self):
        for left_closed, right_closed, attained in product((False, True), repeat=3):
            self.assert_parity((
                piece(Interval(0, 2, left_closed, right_closed), slope=1, chi=attained, name="a"),
                piece(Interval(0, 2), slope=-1, intercept=2, chi=not attained, name="z"),
                piece(Interval(1, 1), intercept=1, chi=True, name="a", tag="singleton"),
                piece(Interval(2, 3, False, False), rho=-1, tag="disjoint")))

    def test_random_rational_arrangements_and_witnesses(self):
        rng = random.Random(611)
        for _ in range(60):
            pieces = []
            for i in range(rng.randrange(1, 13)):
                lo, hi = sorted(R(rng.randrange(0, 10), rng.randrange(1, 4)) for _ in range(2))
                closed = (True, True) if lo == hi else (bool(rng.randrange(2)), bool(rng.randrange(2)))
                pieces.append(piece(Interval(lo, hi, *closed),
                    slope=R(rng.randrange(-4, 5), rng.randrange(1, 4)),
                    intercept=R(rng.randrange(-4, 5), rng.randrange(1, 4)),
                    chi=bool(rng.randrange(2)), rho=R(rng.randrange(-3, 4), rng.randrange(1, 4)),
                    name=rng.choice(("a", "b", "c")), tag=str(i)))
            self.assert_parity(tuple(pieces))

    def test_repeated_piece_and_shared_cut_objects_match_legacy_identity(self):
        parent = piece(Interval(0, 0))
        cut = parent.at(R(0))
        first = replace(parent, _point=lambda energy: cut)
        second = replace(parent, _point=lambda energy: cut)
        actual = self.assert_parity((first, first, second))
        self.assertEqual(len(actual), 3)

    def test_all_callbacks_validated_including_dominated_piece(self):
        better = piece(Interval(0, 1))
        bad = replace(piece(Interval(0, 1), intercept=1),
                      _point=lambda energy: better.at(energy))
        for reducer in (reduce_frontier, reduce_frontier_skyline):
            with self.assertRaisesRegex(AssertionError, "Point witness disagrees"):
                reducer((better, bad))

    def test_empty_cross_state_and_tampered_family_fail_closed(self):
        self.assertEqual(reduce_frontier_skyline(()), ())
        parent = piece(Interval(0, 1))
        with self.assertRaisesRegex(ValueError, "cross-state"):
            reduce_frontier_skyline((parent, replace(parent, state=State("other", 0, 1))))
        case = json.loads((ROOT / "tests/fixtures/invocation_trace_pilot_v1.json").read_text())
        with Recorder():
            parent = Problem(case).initial_piece()
            with self.assertRaisesRegex(ValueError, "Stale family"):
                reduce_frontier_skyline((replace(parent, intercept=parent.intercept+1),))


class TestSkylineSolverIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads((ROOT / "tests/fixtures/invocation_trace_pilot_v1.json").read_text())

    def solve(self, case, hierarchical, reducer=None):
        problem = Problem(deepcopy(case))
        if hierarchical:
            return _solve_hierarchical_problem(problem, True, build_regions(problem.sites), reducer=reducer)
        return _solve_problem(problem, True, reducer=reducer)

    def test_explicit_hook_retains_flat_hier_keys_statuses_and_counters(self):
        from test_time_cut_bounded_v2 import simple_case
        attained = deepcopy(self.case)
        cases = (attained, simple_case(), simple_case(True), dict(attained, H_ref=0))
        for case, hierarchical in product(cases, (False, True)):
            with self.subTest(case=case.get("case_id"), hierarchical=hierarchical):
                legacy = self.solve(case, hierarchical)
                skyline = self.solve(case, hierarchical, reduce_frontier_skyline)
                self.assertEqual(skyline.canonical(), legacy.canonical())
                old = legacy.bounded if hierarchical else legacy
                new = skyline.bounded if hierarchical else skyline
                self.assertEqual((new.attempted_extensions, new.feasible_prefixes,
                                  new.terminal_piece_count, new.max_layer_piece_count),
                                 (old.attempted_extensions, old.feasible_prefixes,
                                  old.terminal_piece_count, old.max_layer_piece_count))
                if new.result.witness is not None:
                    self.assertEqual(witness_dict(new.result.witness), witness_dict(old.result.witness))
                    self.assertEqual(_replay_problem(Problem(case), new.result.witness), new.result.key)

    def test_baseline_default_does_not_enable_skyline(self):
        with patch("timecut5.pwa._same_state_energy_skyline", side_effect=AssertionError("default enabled")):
            for hierarchical in (False, True):
                self.solve(self.case, hierarchical)

    def test_recorded_trace_and_family_dag_are_byte_identical_and_verified(self):
        from validation.trace5 import verify_trace
        runs = []
        for reducer in (reduce_frontier, reduce_frontier_skyline):
            with Recorder() as recorder, InvocationTrace(recorder) as trace:
                result = self.solve(self.case, True, reducer)
            stream = trace.export()
            bundle = recorder.export()
            bundle["roots"] = stream["events"][-1]["payload"]["terminal_families"]
            checked = verify_trace(stream, bundle, self.case)
            self.assertTrue(checked.summary["verified"])
            runs.append((result.canonical(), stream, bundle, recorder.export_witness_requests()))
        self.assertEqual(runs[0], runs[1])


if __name__ == "__main__":
    unittest.main()
