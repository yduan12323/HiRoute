"""Bounded v2 theorem probes; stdlib-runnable independently of data fixtures.

These tests do not amend or waive the historical v0/v1 failing contracts.
"""
from dataclasses import replace
from fractions import Fraction as R
import unittest

from timecut5.probe import (
    AffineFamily, ChargingCurve, FROZEN_CURVE, Interval, State, UnattainedError,
    charge_at, charge_point, combined_point, continuation_equivalent, cut_le,
    dominates, drive, reduce_cuts, schedule, terminal,
)


def seed(tau=0, chi=True, energy=1, rho=0, pi=(("1", "C"),),
         anchor="v", remaining=1):
    return AffineFamily(Interval(energy, energy), 0, tau, chi, rho, pi,
                        State(anchor, remaining, len(pi))).at(energy)


def v1_families():
    state = State("v", 1, 1)
    a = AffineFamily(Interval(0, 1, False, True), 60, 1000, True, 0,
                     (("1", "C"),), state)
    b = AffineFamily(Interval(R(1, 2), R(1, 2)), 0, 1031, True, 1,
                     (("2", "C"),), state)
    return a, b


class TestCutSemantics(unittest.TestCase):
    def test_exact_input_validation(self):
        with self.assertRaises(TypeError):
            Interval(0.0, 1)
        with self.assertRaises(TypeError):
            seed(tau=0.1)
        with self.assertRaises(ValueError):
            Interval(1, 1, False, True)
        with self.assertRaises(ValueError):
            seed().approach(R(0))

    def test_four_equal_time_cut_orders(self):
        for ac in (False, True):
            for bc in (False, True):
                with self.subTest(a=ac, b=bc):
                    self.assertEqual(cut_le(seed(5, ac), seed(5, bc)), ac or not bc)

    def test_strict_time_order_ignores_attainment(self):
        self.assertTrue(cut_le(seed(5, False), seed(6, True)))
        self.assertFalse(cut_le(seed(6, True), seed(5, False)))

    def test_open_cut_cannot_execute_limit(self):
        cut = seed(1336, False)
        with self.assertRaises(UnattainedError):
            cut.minimum()
        with self.assertRaises(UnattainedError):
            cut.realize_le(1336)
        for epsilon in (R(1), R(1, 10**50)):
            w = cut.approach(epsilon)
            self.assertTrue(1336 < w.time < 1336 + epsilon)

    def test_constructive_dominance_budget(self):
        earlier, later = seed(1336, False), seed(1349, True, rho=1)
        self.assertTrue(dominates(earlier, later))
        w = earlier.realize_le(later.minimum().time)
        self.assertLess(w.time, 1349)

    def test_rho_and_tuple_are_required(self):
        a, b = seed(1, rho=2), seed(2, rho=1)
        self.assertFalse(dominates(a, b))
        self.assertFalse(dominates(b, a))
        # Equal rho needs tuple order even when time is strictly earlier.
        self.assertFalse(dominates(seed(1, pi=(("2", "C"),)), seed(2)))

    def test_no_cross_energy_or_state_deletion(self):
        a = seed(0)
        for b in (seed(1, energy=2), seed(1, anchor="other"), seed(1, remaining=0)):
            self.assertFalse(dominates(a, b))

    def test_reduction_idempotence_and_mutual_coverage(self):
        a, b = seed(1336, False), seed(1349, True, rho=1)
        reduced = reduce_cuts((b, a, a))
        self.assertEqual(reduced, (a,))
        self.assertEqual(reduce_cuts(reduced), reduced)
        self.assertTrue(continuation_equivalent(reduced, (a, b)))
        self.assertFalse(continuation_equivalent((), (a,)))


class TestDriveAndSchedule(unittest.TestCase):
    def test_drive_preserves_charge_conservation_and_openness(self):
        source = seed(5, False, energy=10, rho=2)
        result = drive(source, "next", 3, 4)
        self.assertEqual((result.tau, result.chi, result.energy, result.rho), (8, False, 6, 6))
        w = result.approach(R(1, 100))
        self.assertEqual(w.charge, source.energy + source.rho)
        self.assertEqual(w.events[-1].effect, "D")
        self.assertIsNone(drive(source, "next", 3, 11))

    def test_schedule_creates_attainment_on_strict_plateau(self):
        result = schedule(seed(1336, False), "4", 2000, 2100, 100, 300)
        self.assertEqual((result.tau, result.chi), (2100, True))
        w = result.minimum()
        self.assertEqual(w.time, 2100)
        self.assertGreater(w.events[-1].arrival_time, 1336)
        self.assertEqual(w.state.remaining_schedule, 0)

    def test_schedule_plateau_equality_does_not_close_open_cut(self):
        for chi in (False, True):
            result = schedule(seed(1700, chi), "4", 2000, 2100, 100, 300)
            self.assertEqual((result.tau, result.chi), (2100, chi))
            result.approach(R(1, 1000))

    def test_schedule_after_plateau_preserves_attainment(self):
        result = schedule(seed(1750, False), "4", 2000, 2100, 100, 300)
        self.assertEqual((result.tau, result.chi), (2150, False))

    def test_latest_start_boundary_is_exact(self):
        self.assertIsNone(schedule(seed(1800, False), "4", 2000, 2100, 100, 300))
        closed = schedule(seed(1800, True), "4", 2000, 2100, 100, 300)
        self.assertEqual(closed.minimum().time, 2200)
        tiny_slack = schedule(seed(1800 - R(1, 10**50), False), "4", 2000, 2100, 100, 300)
        w = tiny_slack.approach(R(1))
        self.assertLessEqual(w.events[-1].arrival_time + 300, 2100)

    def test_zero_duration_singleton_window_and_invalid_window(self):
        result = schedule(seed(5, False), "s", 10, 10, 0, 1)
        self.assertEqual(result.minimum().time, 10)
        self.assertIsNone(schedule(seed(5), "s", 11, 10, 0, 1))
        with self.assertRaises(ValueError):
            schedule(seed(5, remaining=0), "s", 10, 10, 0, 1)


class TestCharge(unittest.TestCase):
    def test_frozen_curve_exact_breakpoints(self):
        self.assertEqual([FROZEN_CURVE.at(e) for e in (0, 30, 48, 60)], [0, 1080, 2160, 3600])
        with self.assertRaises(ValueError):
            FROZEN_CURVE.at(61)
        with self.assertRaises(ValueError):
            ChargingCurve(((0, 1, 1, 0), (1, 2, 2, 0)))

    def test_v1_infimum_and_real_noninfimal_witnesses(self):
        a, b = v1_families()
        ac = charge_at((a,), 1, FROZEN_CURVE, 300, "3")
        bc = charge_at((b,), 1, FROZEN_CURVE, 300, "3")
        self.assertEqual((ac.tau, ac.chi, bc.tau, bc.chi), (1336, False, 1349, True))
        for ea, expected in ((R(1, 4), 1342), (R(1, 2), 1348)):
            w = charge_point(a.at(ea), 1, FROZEN_CURVE, 300, "3").minimum()
            self.assertEqual(w.time, expected)
            self.assertGreater(w.events[-1].departure_energy, w.events[-1].arrival_energy)
        with self.assertRaises(UnattainedError):
            ac.minimum()

    def test_v1_arbitrary_approach_and_schedule_replay(self):
        a, _ = v1_families()
        result = charge_at((a,), 1, FROZEN_CURVE, 300, "3")
        for epsilon in (R(100), R(1), R(1, 10**50)):
            w = result.approach(epsilon)
            self.assertTrue(1336 < w.time < 1336 + epsilon)
            ea = w.events[-1].arrival_energy
            self.assertTrue(0 < ea < 1)
            self.assertEqual(w.time, 1336 + 24 * ea)
            self.assertEqual(w.charge, R(1))
        final = schedule(result, "4", 2000, 2100, 100, 300)
        self.assertEqual(final.minimum().time, 2100)
        self.assertEqual([e.effect for e in final.minimum().events], ["analytic_seed", "C", "S"])

    def test_v1_cut_congruence_uses_continuation_coverage(self):
        a, b = v1_families()
        self.assertTrue(dominates(a.at(R(1, 2)), b.at(R(1, 2))))
        ac, bc = (charge_at((f,), 1, FROZEN_CURVE, 300, "3") for f in (a, b))
        # Historical v1 attained-record sets differ; v2 asks a DIFFERENT
        # semantic comparison and carries ac's executable approach witness.
        self.assertEqual([c.tau for c in (ac,) if c.chi], [])
        self.assertEqual([c.tau for c in (ac, bc) if c.chi], [1349])
        self.assertTrue(continuation_equivalent((ac,), (ac, bc)))
        self.assertEqual(reduce_cuts((ac, bc)), (ac,))
        self.assertLess(ac.realize_le(bc.minimum().time).time, bc.minimum().time)

    def test_strict_charge_zero_duration_limit_never_executes(self):
        a, _ = v1_families()
        family = replace(a, domain=Interval(0, 1), slope=0, intercept=1000)
        result = charge_at((family,), 1, FROZEN_CURVE, 300, "3")
        self.assertEqual((result.tau, result.chi), (1300, False))
        for epsilon in (R(1), R(1, 10**50)):
            w = result.approach(epsilon)
            self.assertGreater(w.events[-1].departure_energy, w.events[-1].arrival_energy)
        with self.assertRaises(ValueError):
            charge_point(family.at(1), 1, FROZEN_CURVE, 300, "3")

    def test_constant_objective_attains_on_open_energy_interval(self):
        a, _ = v1_families()
        family = replace(a, domain=Interval(0, 1, False, False), slope=36)
        result = charge_at((family,), 1, FROZEN_CURVE, 300, "3")
        self.assertEqual((result.tau, result.chi), (1336, True))
        self.assertTrue(0 < result.minimum().events[-1].arrival_energy < 1)

    def test_open_input_time_prevents_charge_attainment(self):
        a, _ = v1_families()
        family = replace(a, domain=Interval(0, 1), slope=36, chi=False)
        result = charge_at((family,), 1, FROZEN_CURVE, 300, "3")
        self.assertEqual((result.tau, result.chi), (1336, False))
        result.approach(R(1, 10**50))

    def test_piecewise_curve_and_attained_tied_regime(self):
        state = State("v", 1, 1)
        base = AffineFamily(Interval(29, 31), 50, 1000, True, 0, (("1", "C"),), state)
        result = charge_at((base,), 48, FROZEN_CURVE, 300, "3")
        self.assertEqual((result.tau, result.chi), (3866, True))
        self.assertEqual(result.minimum().events[-1].arrival_energy, 29)
        # Two equal minima: an attained singleton must close the union even
        # when the first regime only approaches the same boundary.
        a, _ = v1_families()
        singleton = replace(a, domain=Interval(R(1, 2), R(1, 2)), slope=0, intercept=1018)
        tied = charge_at((a, singleton), 1, FROZEN_CURVE, 300, "3")
        self.assertEqual((tied.tau, tied.chi), (1336, True))
        self.assertEqual(tied.minimum().time, 1336)

    def test_empty_charge_domain_and_prefix_isolation(self):
        a, b = v1_families()
        self.assertIsNone(charge_at((a,), 0, FROZEN_CURVE, 300, "3"))
        self.assertIsNone(charge_at((b,), R(1, 2), FROZEN_CURVE, 300, "3"))
        with self.assertRaises(ValueError):
            charge_at((a, b), 1, FROZEN_CURVE, 300, "3")

    def test_open_kink_can_be_approached_but_never_used_as_optimizer(self):
        a, _ = v1_families()
        # tau-F is decreasing before 30 and increasing after 30.
        # Both adjacent pieces exclude the unique closure optimizer E=30.
        # Use different affine tau slopes, continuous at the missing point.
        left = replace(a, domain=Interval(29, 30, True, False), slope=20, intercept=1000)
        right = replace(a, domain=Interval(30, 31, False, True), slope=80, intercept=-800)
        result = charge_at((left, right), 48, FROZEN_CURVE, 300, "3")
        self.assertEqual((result.tau, result.chi), (2980, False))
        w = result.approach(R(1, 10**50))
        self.assertNotEqual(w.events[-1].arrival_energy, 30)
        self.assertGreater(w.time, 2980)


class TestCombinedPoint(unittest.TestCase):
    def test_open_cut_plateau_and_charging_bottleneck(self):
        curve = ChargingCurve(((0, 10, 1, 0),))
        source = seed(5, False, energy=0)
        plateau = combined_point(source, 1, curve, "s", 10, 12, 3, 1)
        self.assertEqual((plateau.tau, plateau.chi), (13, True))
        self.assertEqual(plateau.minimum().time, 13)
        bottleneck = combined_point(source, 10, curve, "s", 10, 12, 3, 1)
        self.assertEqual((bottleneck.tau, bottleneck.chi), (16, False))
        bottleneck.approach(R(1, 10**50))

    def test_cs_plateau_boundary_and_window_clipping(self):
        curve = ChargingCurve(((0, 10, 1, 0),))
        for chi in (False, True):
            result = combined_point(seed(9, chi, energy=0), 1, curve, "s", 10, 12, 3, 1)
            self.assertEqual((result.tau, result.chi), (13, chi))
        self.assertIsNone(combined_point(seed(11, False, energy=0), 1, curve, "s", 10, 12, 3, 1))


class TestTerminalAndV0AnalyticRegression(unittest.TestCase):
    def terminal_family(self, domain=Interval(0, 1), slope=0, intercept=10,
                        chi=True, rho=0, pi=()):
        return AffineFamily(domain, slope, intercept, chi, rho, pi, State("z", 0, len(pi)))

    def test_primary_unattained_does_not_report_later_attained_plan(self):
        open_time = self.terminal_family(chi=False)
        later = self.terminal_family(intercept=11)
        result = terminal((open_time, later), "z", 0)
        self.assertEqual((result.status, result.primary_infimum, result.unattained_component),
                         ("infimum_unattained", 10, "J"))
        self.assertIsNone(result.secondary_infimum)
        self.assertIsNone(result.key)
        self.assertIsNone(result.witness)

    def test_j_attained_q_unattained_on_primary_face(self):
        # Physical interpretation: after C(q>0), a schedule waiting plateau
        # fixes J=14 while Q=q and terminal E=7+q, q in (0,1].
        family = self.terminal_family(domain=Interval(7, 8, False, True),
                                      intercept=12, rho=-7, pi=(("s", "C"), ("g", "S")))
        result = terminal((family,), "z", 0, stop_penalty=1)
        self.assertEqual((result.status, result.primary_infimum, result.secondary_infimum,
                          result.unattained_component), ("infimum_unattained", 14, 0, "Q"))
        self.assertIsNone(result.key)
        self.assertIsNone(result.witness)

    def test_secondary_nonattainment_has_executable_physical_approaches(self):
        curve = ChargingCurve(((0, 10, 1, 0),))
        for q in (R(1), R(1, 100), R(1, 10**50)):
            origin = seed(0, energy=10, rho=-10, pi=(), anchor="o")
            at_s = drive(origin, "s", 1, 1)
            after_c = charge_point(at_s, 9 + q, curve, 1, "s")
            at_g = drive(after_c, "g", 1, 1)
            after_s = schedule(at_g, "g", 10, 10, 1, 1)
            at_z = drive(after_s, "z", 1, 1)
            w = at_z.minimum()
            self.assertEqual((w.time + 2, w.charge, w.energy), (14, q, 7 + q))

    def test_attained_tie_and_reserve_clipping(self):
        a = self.terminal_family(domain=Interval(0, 2, False, True), pi=(("2", "C"),))
        b = replace(a, pi=(("1", "C"),))
        result = terminal((a, b), "z", 1, stop_penalty=3)
        self.assertEqual(result.key, (13, 1, 1, (("1", "C"),)))
        self.assertEqual(result.witness.energy, 1)
        self.assertEqual(terminal((a,), "z", 3).status, "infeasible")

    def test_nonconstant_primary_face_is_a_singleton(self):
        family = self.terminal_family(slope=-1)
        result = terminal((family,), "z", 0)
        self.assertEqual(result.key, (9, 1, 0, ()))

    def test_attained_primary_tie_survives_open_primary_competitor(self):
        open_time = self.terminal_family(chi=False, rho=0)
        closed = self.terminal_family(domain=Interval(1, 1), rho=3)
        result = terminal((open_time, closed), "z", 0)
        self.assertEqual(result.key, (10, 4, 0, ()))

    def test_attained_larger_q_cannot_replace_unattained_best_q(self):
        open_q = self.terminal_family(domain=Interval(0, 1, False, True))
        attained_later = self.terminal_family(domain=Interval(2, 2))
        result = terminal((open_q, attained_later), "z", 0)
        self.assertEqual((result.status, result.unattained_component, result.secondary_infimum),
                         ("infimum_unattained", "Q", 0))

    def test_attained_singleton_restores_open_q_infimum(self):
        open_q = self.terminal_family(domain=Interval(0, 1, False, True))
        singleton = self.terminal_family(domain=Interval(0, 0))
        self.assertEqual(terminal((open_q, singleton), "z", 0).key, (10, 0, 0, ()))

    def test_stop_count_precedes_prefix_tuple_only_after_j_q(self):
        shorter = self.terminal_family(domain=Interval(1, 1), pi=(("9", "C"),))
        longer = self.terminal_family(domain=Interval(1, 1), pi=(("1", "C"), ("2", "S")))
        self.assertEqual(terminal((longer, shorter), "z", 0).key,
                         (10, 1, 1, (("9", "C"),)))

    def test_equal_keys_do_not_require_identical_continuous_witnesses(self):
        curve = ChargingCurve(((0, 2, 1, 0),))
        witnesses = []
        for first_charge in (R(1, 4), R(1, 2)):
            start = seed(0, energy=0, rho=0, pi=(), anchor="1")
            c1 = charge_point(start, first_charge, curve, 1, "1")
            c2 = charge_point(c1, 1, curve, 1, "2")
            result = schedule(c2, "3", 10, 10, 1, 1)
            witnesses.append(result.minimum())
        keys = [(w.time, w.charge, w.state.stop_count, w.pi) for w in witnesses]
        self.assertEqual(keys[0], keys[1])
        self.assertNotEqual(witnesses[0].events, witnesses[1].events)

    def test_v0_analytic_prefix_reconstruction_retains_76_kwh_winner(self):
        # Derived only from the published v0 report's exact prefix equations.
        # This is NOT the missing original graph fixture or a full REF rerun.
        energy = R(48)
        a = seed(20100 + FROZEN_CURVE.at(energy), energy=energy, rho=35,
                 pi=(("1", "C"), ("3", "C")), anchor="3")
        b = seed(20328 + FROZEN_CURVE.at(energy), energy=energy, rho=28,
                 pi=(("2", "C"), ("3", "C")), anchor="3")
        self.assertEqual(len(reduce_cuts((a, b))), 2)
        keys = []
        for cut in reduce_cuts((a, b)):
            at_4 = drive(cut, "4", 9000, 40)
            # Both starts equal a; choose b=a for this analytic reconstruction,
            # without asserting a missing original-fixture latest-start value.
            after_s = schedule(at_4, "4", 40000, 40000, 2700, 300)
            at_z = drive(after_s, "z", 450, 2, floor=6)
            w = at_z.minimum()
            keys.append((w.time + 600 * w.state.stop_count, w.charge, w.state.stop_count, w.pi))
        self.assertEqual(keys[0][:3], (44950, 83, 3))
        self.assertEqual(min(keys), (44950, 76, 3, (("2", "C"), ("3", "C"), ("4", "S"))))


if __name__ == "__main__":
    unittest.main()
