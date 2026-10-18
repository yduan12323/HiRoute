"""Old-FME, independent-formula, exact witness and provenance differentials."""
import asyncio
from dataclasses import FrozenInstanceError, asdict, replace
from fractions import Fraction as R
from itertools import product
import random
import unittest
from unittest.mock import patch

from timecut5 import analytic_charge as analytic, provenance as prov
from timecut5.analytic_charge import AnalyticCharge
from timecut5.bounded import Problem, replay_witness, solve_bounded
from timecut5.hierarchy import solve_hierarchical
from timecut5.probe import AffineFamily, ChargingCurve, Interval, State
from timecut5.pwa import (CutPiece, Projection, ProjectionSupportPrefilter, Row,
    _extract, _interval_rows, charge_pwa, combined_pwa, schedule_pwa)
from validation.family5 import independent_oracle_v2 as oracle
from validation.family5.checker import verify_bundle


CURVE = ChargingCurve(((0, 2, 1, 0), (2, 4, 2, -2), (4, 6, 3, -6)))


def family(domain, slope=0, intercept=10, chi=True):
    return CutPiece.from_affine(AffineFamily(domain, slope, intercept, chi, 0,
                                            (), State("o", 1, 0)))


def old_projection(source, incoming, outgoing, h=R(1)):
    """Frozen original C row system; does not invoke the new builder."""
    il, ih, im, ic = incoming
    ol, oh, om, oc = outgoing
    rows = [*_interval_rows(source.domain, 0),
            Row((source.slope, -1, 0, 0), -source.intercept, not source.chi),
            *_interval_rows(Interval(il, ih), 0),
            *_interval_rows(Interval(ol, oh), 2),
            Row((1, 0, -1, 0), 0, True),
            Row((-im, 1, om, -1), -h-oc+ic)]
    return Projection.build(rows, (1, 0))


def raw(projector, source, incoming, outgoing, curve=CURVE, h=R(1)):
    return (() if projector is None else _extract(projector, source, "C", "c", h,
            curve, in_segment=incoming, out_segment=outgoing))


def outputs(pieces):
    return [(prov.signature(p), [prov.witness_dict(p.at((p.domain.lo+p.domain.hi)/2)
                .approach(eps)) for eps in (R(1), R(1, 10**60))]) for p in pieces]


def case(scheduled=False):
    return dict(case_id="analytic-c-tiny", H_ref=2, origin="o", destination="z",
        start_time_s="0", initial_energy_kwh="2", capacity_kwh="6",
        minimum_energy_kwh="0", reserve_kwh="1", overhead_s="1",
        lambda_stop_s="1", consumption_kwh_per_m="1",
        charging_segments=[[str(x) for x in row] for row in CURVE.segments],
        sites={"c": ["C", "S", "CS"] if scheduled else ["C"]},
        schedule=dict(a="0", b="20", D="2") if scheduled else None,
        edges=[dict(source=a, target=b, time_s="1", length_m="1")
               for a, b in (("o", "c"), ("c", "z"))])


class AnalyticChargeTests(unittest.TestCase):
    def test_exact_bool_readonly_detached_single_use_and_nested_exception(self):
        for value in (None, 0, 1, 0.0, 1.0, R(1), "true"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AnalyticCharge(enabled=value)
        policy = AnalyticCharge(enabled=True)
        before = policy.snapshot()
        with self.assertRaises(AttributeError):
            policy.enabled = False
        with self.assertRaises(FrozenInstanceError):
            before.analytic_builds = 1
        source = family(Interval(0, 1))
        with policy:
            charge_pwa((source,), CURVE, 1, "c")
            with self.assertRaisesRegex(RuntimeError, "nested"):
                with AnalyticCharge(enabled=False) as inner:
                    charge_pwa((source,), CURVE, 1, "c")
                    raise RuntimeError("nested")
            charge_pwa((source,), CURVE, 1, "c")
        self.assertEqual(before.analytic_builds, 0)
        self.assertEqual(policy.snapshot().analytic_builds, 18)
        self.assertEqual(inner.snapshot().generic_projection_builds, 9)
        with self.assertRaises(ValueError):
            with policy:
                pass
        after = policy.snapshot()
        charge_pwa((source,), CURVE, 1, "c")
        self.assertEqual(policy.snapshot(), after)

    def test_absent_disabled_and_cs_s_keep_historical_path(self):
        source = family(Interval(0, 2), chi=False)
        with patch.object(analytic, "_build", side_effect=AssertionError("analytic path")):
            baseline = charge_pwa((source,), CURVE, 1, "c")
            with AnalyticCharge(enabled=False) as control:
                actual = charge_pwa((source,), CURVE, 1, "c")
            with AnalyticCharge(enabled=True) as policy:
                combined_pwa((source,), CURVE, "c", 1, 20, 2, 1)
                schedule_pwa((source,), "c", 1, 20, 2, 1)
        self.assertEqual(outputs(actual), outputs(baseline))
        self.assertEqual(control.snapshot().generic_projection_builds, 9)
        self.assertEqual(policy.snapshot().considered_pairs, 0)

    def test_raw_ordered_pair_signatures_and_lift_match_old_fme(self):
        domains = [Interval(x, x) for x in (R(0), R(2), R(4), R(6))]
        domains += [Interval(lo, hi, lc, rc) for lo, hi in
                    ((-1, 0), (0, 1), (0, 2), (1, 5), (2, 4), (4, 7))
                    for lc, rc in product((False, True), repeat=2)]
        checked = 0
        for domain, slope, chi in product(domains, (-2, 0, 1, 2, 3), (False, True)):
            source = family(domain, R(slope), chi=chi)
            for incoming, outgoing in product(CURVE.segments, repeat=2):
                old = old_projection(source, incoming, outgoing)
                new = analytic._build(source, incoming, outgoing, R(1))
                old_pieces = raw(old, source, incoming, outgoing)
                new_pieces = raw(new, source, incoming, outgoing)
                with self.subTest(domain=domain, slope=slope, chi=chi,
                                  incoming=incoming, outgoing=outgoing):
                    self.assertEqual(outputs(new_pieces), outputs(old_pieces))
                    for piece in old_pieces:
                        y = (piece.domain.lo+piece.domain.hi)/2
                        value = piece.slope*y+piece.intercept
                        for slack in ((R(0), R(1, 10**60)) if piece.chi else
                                      (R(1), R(1, 10**60))):
                            self.assertEqual(new.lift({2:y, 3:value+slack}),
                                             old.lift({2:y, 3:value+slack}))
                        if not piece.chi:
                            with self.assertRaises(ValueError):
                                new.lift({2:y, 3:value})
                checked += 1
        self.assertEqual(checked, 2520)

    def test_strict_hinge_inactive_knots_and_normalized_tie_slope(self):
        source = family(Interval(0, 1), slope=0)
        incoming, outgoing = CURVE.segments[0], CURVE.segments[1]
        old = raw(old_projection(source, incoming, outgoing), source, incoming, outgoing)
        new = raw(analytic._build(source, incoming, outgoing, R(1)), source, incoming, outgoing)
        self.assertEqual(outputs(new), outputs(old))
        # With a wider output segment, inactive source/incoming upper-bound
        # lines cross the moving line at BOTH 1 and 2, even after saturation.
        curve = ChargingCurve(((0, 6, 1, 0),))
        source = family(Interval(0, 2), slope=0)
        segment = curve.segments[0]
        with AnalyticCharge(enabled=True):
            actual = charge_pwa((source,), curve, 1, "c")
        boundary = next(p for p in actual if p.domain == Interval(2, 2))
        self.assertFalse(boundary.chi)
        self.assertTrue(next(p for p in actual if p.domain.contains(R(3))).chi)
        self.assertEqual(outputs(actual), outputs(charge_pwa((source,), curve, 1, "c")))
        # Source endpoint 5 is inactive after incoming segment ends at 2,
        # but old FME still emits it as a knot in the outgoing segment [4,6].
        source = family(Interval(0, 5), slope=0)
        incoming, outgoing = CURVE.segments[0], CURVE.segments[2]
        pieces = raw(analytic._build(source, incoming, outgoing, R(1)), source, incoming, outgoing)
        self.assertTrue(any(p.domain == Interval(5, 5) for p in pieces))
        self.assertEqual(outputs(pieces), outputs(raw(old_projection(source, incoming, outgoing), source, incoming, outgoing)))

    def test_complete_independent_formula_seeded_rational_unions(self):
        rng = random.Random(202610171602)
        for trial in range(70):
            knots = (R(0), R(2), R(5), R(7))
            segments, value = [], R(0)
            for lo, hi in zip(knots, knots[1:]):
                slope = R(rng.randrange(1, 7), rng.randrange(1, 4))
                segments.append((lo, hi, slope, value-slope*lo))
                value += slope*(hi-lo)
            curve = ChargingCurve(tuple(segments))
            sources = []
            for _ in range(rng.randrange(1, 4)):
                lo, hi = sorted((R(rng.randrange(15),2), R(rng.randrange(15),2)))
                flags = (True, True) if lo == hi else (bool(rng.randrange(2)), bool(rng.randrange(2)))
                sources.append(family(Interval(lo, hi, *flags),
                    R(rng.randrange(-5, 8), rng.randrange(1, 4)),
                    R(rng.randrange(8, 20),3), bool(rng.randrange(2))))
            expected = charge_pwa(sources, curve, R(2,3), "c")
            with AnalyticCharge(enabled=True):
                actual = charge_pwa(sources, curve, R(2,3), "c")
            self.assertEqual(outputs(actual), outputs(expected))
            params = dict(site="c", h=R(2,3), a=R(0), b=R(0), D=R(0), curve=curve.segments)
            formula = oracle.transform([oracle.load(prov.signature(p)) for p in sources], "C", params)
            oracle.exact_family_equal([oracle.load(prov.signature(p)) for p in actual], formula)

    def test_tied_sources_preserve_first_attaining_original_parent(self):
        first = family(Interval(0, 2), 1, 10, False)
        second = family(Interval(0, 2), 1, 10, True)
        curve = ChargingCurve(((0, 6, 1, 0),))
        for sources in ((first, second), (second, first), (first, first), (second, second)):
            expected = charge_pwa(sources, curve, 1, "c")
            with AnalyticCharge(enabled=True):
                actual = charge_pwa(sources, curve, 1, "c")
            self.assertEqual(outputs(actual), outputs(expected))

    def test_equal_chi_ties_dispatch_identical_original_callback_labels(self):
        curve = ChargingCurve(((0, 6, 1, 0),))
        for chi in (False, True):
            calls = []
            def tagged(label):
                source = family(Interval(0, 2), 1, 10, chi)
                original = source._point
                def point(energy):
                    calls.append((label, energy))
                    return original(energy)
                return replace(source, _point=point)
            a, b = tagged("a"), tagged("b")
            for sources, label in (((a,b), "a"), ((b,a), "b"),
                                   ((a,b,a), "a"), ((b,b,a), "b")):
                calls.clear()
                expected = outputs(charge_pwa(sources, curve, 1, "c"))
                historical_dispatch = tuple(calls)
                self.assertTrue(historical_dispatch)
                self.assertEqual({row[0] for row in calls}, {label})
                calls.clear()
                with AnalyticCharge(enabled=True):
                    actual = outputs(charge_pwa(sources, curve, 1, "c"))
                self.assertEqual(actual, expected)
                self.assertEqual(tuple(calls), historical_dispatch)

    def test_direct_lift_keeps_restricted_two_charge_ancestry(self):
        f1, f2 = ChargingCurve(((0,2,1,0),)), ChargingCurve(((0,2,2,0),))
        seed = family(Interval(0,0), intercept=0)
        def run(enabled, closed):
            with AnalyticCharge(enabled=enabled):
                first = charge_pwa((seed,), f1, 1, "one")
                restricted = [replace(p, domain=d) for p in first
                    if (d := p.domain.intersect(Interval(0,R(1,2),False,closed))) is not None]
                return charge_pwa(restricted, f2, 1, "two")
        for closed in (False, True):
            expected, actual = run(False, closed), run(True, closed)
            self.assertEqual(outputs(actual), outputs(expected))
            cut = next(p.at(R(1)) for p in actual if p.domain.contains(R(1)))
            self.assertEqual((cut.tau, cut.chi), (R(7,2), closed))
            for epsilon in (R(1,7), R(1,10**60)):
                witness = cut.approach(epsilon)
                self.assertTrue(0 < witness.events[-1].arrival_energy <= R(1,2))
                if not closed:
                    self.assertLess(witness.events[-1].arrival_energy, R(1,2))

    def test_truthful_generic_counts_and_combined_conservation(self):
        source = family(Interval(0, 1))
        for support_on, analytic_on in product((False, True), repeat=2):
            original = Projection.build
            with patch.object(Projection, "build", wraps=original) as calls:
                with ProjectionSupportPrefilter(enabled=support_on) as support, AnalyticCharge(enabled=analytic_on) as policy:
                    charge_pwa((source,), CURVE, 1, "c")
                    combined_pwa((source,), CURVE, "c", 0, 30, 1, 1)
            s, a = support.snapshot(), policy.snapshot()
            self.assertEqual(set(asdict(s)), {"enabled", "considered_pairs", "skipped_empty_input", "skipped_strict_energy", "projection_builds"})
            self.assertEqual(s.projection_builds, calls.call_count)
            self.assertEqual(s.considered_pairs, s.skipped_empty_input+s.skipped_strict_energy+s.projection_builds+a.analytic_builds)
            self.assertEqual(a.considered_pairs, a.support_skipped_pairs+a.analytic_builds+a.generic_projection_builds)
            self.assertEqual(a.considered_pairs, 9)
            self.assertEqual(a.recorded_fallback_builds, 0)
        with AnalyticCharge(enabled=True), patch.object(Projection, "build", side_effect=AssertionError("generic build")):
            actual = charge_pwa((source,), CURVE, 1, "c")
            outputs(actual)  # Direct witness lifts also avoid the generic projector.

    def test_recorder_full_historical_bytes_and_fail_closed_known_parent(self):
        def run(enabled):
            query = case()
            with AnalyticCharge(enabled=enabled) as policy, prov.Recorder() as recorder:
                problem = Problem(query)
                parent = problem.initial_piece()
                output = problem.finish(problem.advance((parent,), "c", "C"))
                witnesses = outputs(output)
                bundle = recorder.export(output)
                requests = recorder.export_witness_requests()
            verify_bundle(bundle, query)
            return bundle, requests, witnesses, policy.snapshot(), parent
        old, new = run(False), run(True)
        self.assertEqual(new[:3], old[:3])
        self.assertEqual(new[3].analytic_builds, 0)
        self.assertEqual(new[3].recorded_fallback_builds, new[3].generic_projection_builds)
        with AnalyticCharge(enabled=True), patch.object(analytic, "_build", side_effect=AssertionError("escaped guard")):
            with self.assertRaisesRegex(ValueError, "Recorder"):
                charge_pwa((new[4],), CURVE, 1, "c")
        with AnalyticCharge(enabled=True), prov.Recorder():
            with self.assertRaises(ValueError):
                charge_pwa((new[4],), CURVE, 1, "c")

    def test_tiny_flat_hier_full_keys_witnesses_and_fresh_replay(self):
        for scheduled, solver, dominance in product((False, True), (solve_bounded, solve_hierarchical), (False, True)):
            query = case(scheduled)
            expected = solver(query, dominance=dominance)
            with AnalyticCharge(enabled=True), ProjectionSupportPrefilter(enabled=True):
                actual = solver(query, dominance=dominance)
            self.assertEqual(actual.canonical(), expected.canonical())
            left = actual.bounded if hasattr(actual, "bounded") else actual
            right = expected.bounded if hasattr(expected, "bounded") else expected
            self.assertEqual(prov.witness_dict(left.result.witness), prov.witness_dict(right.result.witness))
            self.assertEqual(replay_witness(query, left.result.witness), left.result.key)

    def test_primary_and_secondary_unattained_solver_contracts(self):
        for secondary, solver, dominance in product((False, True),
                (solve_bounded, solve_hierarchical), (False, True)):
            edges = [("o", "s", 1, 1)]
            edges += ([("o", "g", 1, 100), ("s", "g", 1, 1), ("g", "z", 1, 1)]
                      if secondary else [("o", "z", 1, 20), ("s", "z", 1, 1)])
            query = dict(H_ref=3, origin="o", destination="z", start_time_s=0,
                initial_energy_kwh=10, capacity_kwh=10, minimum_energy_kwh=0,
                reserve_kwh=0, consumption_kwh_per_m=1, overhead_s=1,
                lambda_stop_s=1, schedule={"a":10,"b":10,"D":1} if secondary else None,
                sites={"s":["C"], "g":["S"]} if secondary else {"s":["C"]},
                charging_segments=[[0,10,1,0]],
                edges=[dict(source=a,target=b,time_s=t,length_m=c) for a,b,t,c in edges])
            expected = solver(query, dominance=dominance).canonical()
            with AnalyticCharge(enabled=True):
                actual = solver(query, dominance=dominance).canonical()
            self.assertEqual(actual, expected)
            self.assertEqual(actual["result"]["status"],
                             "secondary_unattained" if secondary else "primary_unattained")
            self.assertNotIn("lex_key", actual["result"])

    def test_async_contexts_isolated_and_invalid_inputs_unchanged(self):
        async def run(enabled):
            with AnalyticCharge(enabled=enabled) as policy:
                await asyncio.sleep(0)
                charge_pwa((family(Interval(0, 1)),), CURVE, 1, "c")
                await asyncio.sleep(0)
            return policy.snapshot()
        async def both():
            return await asyncio.gather(run(True), run(False))
        on, off = asyncio.run(both())
        self.assertEqual((on.analytic_builds, off.generic_projection_builds), (9, 9))
        for enabled in (False, True):
            with AnalyticCharge(enabled=enabled) as policy:
                with self.assertRaises(ValueError):
                    charge_pwa((family(Interval(0, 1)),), CURVE, 0, "c")
                with self.assertRaises(ValueError):
                    charge_pwa((family(Interval(0, 1)), replace(family(Interval(0, 1)), rho=1)), CURVE, 1, "c")
            self.assertEqual(policy.snapshot().considered_pairs, 0)


if __name__ == "__main__":
    unittest.main()
