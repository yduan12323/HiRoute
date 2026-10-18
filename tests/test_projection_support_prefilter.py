"""Tiny exact support, independent formula, witness and context checks."""
import asyncio
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction as R
from itertools import product
import unittest
from unittest.mock import patch

from timecut5.bounded import Problem, replay_witness, solve_bounded
from timecut5.hierarchy import solve_hierarchical
from timecut5.probe import AffineFamily, ChargingCurve, Interval, State
from timecut5.provenance import Recorder, signature, witness_dict
from timecut5.pwa import (CutPiece, Projection, ProjectionSupportPrefilter,
                         charge_pwa, combined_pwa, schedule_pwa)
from validation.family5 import independent_oracle_v2 as oracle


CURVE = ChargingCurve(((0, 2, 1, 0), (2, 4, 2, -2), (4, 6, 3, -6)))


def family(domain, slope=0, intercept=0, chi=True):
    return CutPiece.from_affine(AffineFamily(domain, slope, intercept, chi, 0,
                                            (), State("origin", 1, 0)))


def quadratic_support(domain, incoming, outgoing):
    """Independent complete 2D order-cell enumeration, no production filter.

    All inequalities have endpoints among these knots, plus x < y. Two
    interior representatives per open knot-cell also cover that diagonal.
    This is an exhaustive rational arrangement, not an approximate energy grid.
    """
    il, ih = incoming[:2]
    ol, oh = outgoing[:2]
    knots = sorted({domain.lo, domain.hi, il, ih, ol, oh})
    values = set(knots)
    for lo, hi in zip(knots, knots[1:]):
        values.update(((2*lo+hi)/3, (lo+2*hi)/3))
    def inside(x):
        return ((domain.lo < x or domain.lo == x and domain.left_closed)
                and (x < domain.hi or x == domain.hi and domain.right_closed))
    return any(inside(x) and il <= x <= ih and ol <= y <= oh and x < y
               for x, y in product(values, repeat=2))


def output_signature(pieces):
    return [(signature(p), tuple(witness_dict(p.at((p.domain.lo+p.domain.hi)/2)
                  .approach(epsilon)) for epsilon in (R(1), R(1, 10**35))))
            for p in pieces]


def case(schedule=False):
    return dict(case_id="projection-support-tiny", H_ref=2, origin="o", destination="z",
        start_time_s="0", initial_energy_kwh="2", capacity_kwh="6",
        minimum_energy_kwh="0", reserve_kwh="1", overhead_s="1",
        lambda_stop_s="1", consumption_kwh_per_m="1",
        charging_segments=[[str(x) for x in row] for row in CURVE.segments],
        sites={"c": ["C", "S", "CS"] if schedule else ["C"]},
        schedule=dict(a="0", b="20", D="2") if schedule else None,
        edges=[dict(source=a, target=b, time_s="1", length_m="1")
               for a, b in (("o", "c"), ("c", "z"))])


class ProjectionSupportTests(unittest.TestCase):
    def assert_counts(self, policy, considered, empty, strict, builds):
        s = policy.snapshot()
        self.assertEqual((s.considered_pairs, s.skipped_empty_input,
                          s.skipped_strict_energy, s.projection_builds),
                         (considered, empty, strict, builds))
        self.assertEqual(s.considered_pairs,
                         s.skipped_empty_input+s.skipped_strict_energy+s.projection_builds)

    def test_exact_bool_readonly_policy_and_detached_snapshot(self):
        for value in (None, 0, 1, 0.0, 1.0, R(1), "true"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ProjectionSupportPrefilter(enabled=value)
        policy = ProjectionSupportPrefilter()
        self.assertFalse(policy.enabled)
        with self.assertRaises(AttributeError):
            policy.enabled = True
        before = policy.snapshot()
        with policy:
            charge_pwa((family(Interval(0, 1)),), CURVE, 1, "c")
        self.assertEqual(before.projection_builds, 0)
        with self.assertRaises(FrozenInstanceError):
            before.projection_builds = 1
        self.assert_counts(policy, 9, 0, 0, 9)

    def test_absent_and_disabled_keep_old_arithmetic_and_witnesses(self):
        source = family(Interval(0, 1, False, True), 2, 3, False)
        with patch.object(Interval, "intersect", side_effect=AssertionError("new arithmetic")):
            expected = charge_pwa((source,), CURVE, 1, "c")
            with ProjectionSupportPrefilter(enabled=False) as policy:
                actual = charge_pwa((source,), CURVE, 1, "c")
        self.assertEqual(output_signature(actual), output_signature(expected))
        self.assert_counts(policy, 9, 0, 0, 9)

    def test_nested_context_exception_restores_and_instances_are_single_use(self):
        source = family(Interval(0, 1))
        with ProjectionSupportPrefilter(enabled=True) as outer:
            charge_pwa((source,), CURVE, 1, "c")
            with self.assertRaisesRegex(RuntimeError, "nested"):
                with ProjectionSupportPrefilter(enabled=False) as inner:
                    charge_pwa((source,), CURVE, 1, "c")
                    raise RuntimeError("nested")
            charge_pwa((source,), CURVE, 1, "c")
            with self.assertRaises(ValueError):
                with outer:
                    pass
        snapshot = outer.snapshot()
        charge_pwa((source,), CURVE, 1, "c")
        self.assertEqual(outer.snapshot(), snapshot)
        self.assert_counts(outer, 18, 12, 0, 6)
        self.assert_counts(inner, 9, 0, 0, 9)
        with self.assertRaises(ValueError):
            with outer:
                pass

    def test_interleaved_async_contexts_have_separate_modes_and_counts(self):
        async def run(enabled):
            with ProjectionSupportPrefilter(enabled=enabled) as policy:
                await asyncio.sleep(0)
                charge_pwa((family(Interval(0, 1)),), CURVE, 1, "c")
                await asyncio.sleep(0)
                charge_pwa((family(Interval(0, 1)),), CURVE, 1, "c")
            return policy
        async def both():
            return await asyncio.gather(run(True), run(False))
        on, off = asyncio.run(both())
        self.assert_counts(on, 18, 12, 0, 6)
        self.assert_counts(off, 18, 0, 0, 18)

    def test_all_endpoint_support_against_independent_quadratic_oracle(self):
        domains = [Interval(x, x) for x in (R(0), R(2), R(4), R(6), R(7))]
        domains += [Interval(lo, hi, lc, rc)
                    for lo, hi in ((R(-1), R(0)), (R(0), R(2)),
                                   (R(2), R(4)), (R(1), R(5)))
                    for lc, rc in product((False, True), repeat=2)]
        original = Projection.build
        for domain in domains:
            source = family(domain)
            baseline_rows, actual_rows = [], []
            def capture(rows, variables, into):
                rows = tuple(rows)
                into.append((rows, tuple(variables)))
                return original(rows, variables)
            with patch.object(Projection, "build", side_effect=lambda r, v: capture(r, v, baseline_rows)):
                baseline = charge_pwa((source,), CURVE, 1, "c")
            with ProjectionSupportPrefilter(enabled=True) as policy:
                with patch.object(Projection, "build", side_effect=lambda r, v: capture(r, v, actual_rows)):
                    actual = charge_pwa((source,), CURVE, 1, "c")
            keep = [i for i, (incoming, outgoing) in enumerate(product(CURVE.segments, repeat=2))
                    if quadratic_support(domain, incoming, outgoing)]
            with self.subTest(domain=domain):
                self.assertEqual(actual_rows, [baseline_rows[i] for i in keep])
                self.assertEqual(policy.snapshot().projection_builds, len(keep))
                self.assertEqual(output_signature(actual), output_signature(baseline))
                self.assertEqual(policy.snapshot().considered_pairs, 9)

    def test_three_segment_mechanism_and_zero_capacity_endpoint(self):
        for domain, expected in ((Interval(0, 6), (9, 0, 3, 6)),
                                 (Interval(0, 0), (9, 6, 0, 3)),
                                 (Interval(2, 2), (9, 3, 2, 4)),
                                 (Interval(6, 6), (9, 6, 3, 0))):
            with ProjectionSupportPrefilter(enabled=True) as policy:
                result = charge_pwa((family(domain),), CURVE, 1, "c")
            self.assert_counts(policy, *expected)
            if domain == Interval(6, 6):
                self.assertEqual(result, ())
        with ProjectionSupportPrefilter(enabled=True) as policy:
            self.assertEqual(charge_pwa((), CURVE, 1, "c"), ())
        self.assert_counts(policy, 0, 0, 0, 0)

    def test_complete_formula_and_witness_parity_for_c_and_cs(self):
        sources = [family(Interval(0, 1, False, False), 1, 3),
                   family(Interval(2, 4, False, True), -1, 8, False),
                   family(Interval(2, 2), 0, 4),
                   family(Interval(0, 6), 2, 0)]
        params = dict(site="c", h=R(1), a=R(5), b=R(15), D=R(2), curve=CURVE.segments)
        for source, effect in product(sources, ("C", "CS")):
            def run():
                return (charge_pwa((source,), CURVE, 1, "c") if effect == "C" else
                        combined_pwa((source,), CURVE, "c", 5, 15, 2, 1))
            baseline = run()
            with ProjectionSupportPrefilter(enabled=True):
                actual = run()
            self.assertEqual(output_signature(actual), output_signature(baseline))
            expected = oracle.transform([oracle.load(signature(source))], effect, params)
            oracle.exact_family_equal([oracle.load(signature(p)) for p in actual], expected)

    def test_inherited_restriction_and_tied_sources_keep_lifting(self):
        initial = (family(Interval(0, 1, False, True), 2, 3, False),
                   family(Interval(R(1, 2), R(1, 2)), 0, 4))
        def run():
            first = charge_pwa(initial, CURVE, 1, "first")
            chosen = next(p for p in first if p.domain.lo < p.domain.hi)
            lo, hi = chosen.domain.lo, chosen.domain.hi
            restricted = replace(chosen, domain=Interval((2*lo+hi)/3, (lo+2*hi)/3, False, False))
            return charge_pwa((restricted,), CURVE, 1, "second")
        baseline = run()
        with ProjectionSupportPrefilter(enabled=True):
            actual = run()
        self.assertEqual(output_signature(actual), output_signature(baseline))

    def test_schedule_and_invalid_inputs_keep_baseline_behavior(self):
        source = family(Interval(0, 2))
        expected = schedule_pwa((source,), "s", 0, 10, 2, 1)
        with ProjectionSupportPrefilter(enabled=True) as policy:
            actual = schedule_pwa((source,), "s", 0, 10, 2, 1)
        self.assertEqual(output_signature(actual), output_signature(expected))
        self.assert_counts(policy, 0, 0, 0, 0)
        for enabled in (False, True):
            with ProjectionSupportPrefilter(enabled=enabled) as policy:
                with self.assertRaises(ValueError):
                    charge_pwa((source,), CURVE, 0, "c")
                self.assertEqual(combined_pwa((source,), CURVE, "c", 2, 1, 0, 1), ())
                with self.assertRaises(ValueError):
                    combined_pwa((replace(source, state=State("origin", 0, 0)),), CURVE, "c", 0, 10, 0, 1)
            self.assert_counts(policy, 0, 0, 0, 0)

    def test_recorded_nodes_batches_and_witnesses_are_byte_equivalent(self):
        def run(enabled):
            with ProjectionSupportPrefilter(enabled=enabled), Recorder() as recorder:
                problem = Problem(case(True))
                first = problem.advance((problem.initial_piece(),), "c", "CS")
                output = problem.finish(first)
                witnesses = output_signature(output)
                return recorder.export(output), recorder.export_witness_requests(), witnesses
        self.assertEqual(run(False), run(True))

    def test_tiny_flat_and_hierarchy_same_exact_keys_and_physical_replay(self):
        for scheduled, solver, dominance in product((False, True),
                (solve_bounded, solve_hierarchical), (False, True)):
            query = case(scheduled)
            expected = solver(query, dominance=dominance)
            with ProjectionSupportPrefilter(enabled=True):
                actual = solver(query, dominance=dominance)
            self.assertEqual(actual.canonical(), expected.canonical())
            bounded = actual.bounded if hasattr(actual, "bounded") else actual
            if bounded.result.witness is not None:
                self.assertEqual(replay_witness(query, bounded.result.witness), bounded.result.key)


if __name__ == "__main__":
    unittest.main()
