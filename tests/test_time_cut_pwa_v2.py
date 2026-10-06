"""Exact energy-cell and constructive-witness tests for the PWA prototype."""
from dataclasses import replace
from fractions import Fraction as R
import unittest

from timecut5.probe import (
    AffineFamily, ChargingCurve, FROZEN_CURVE, Interval, State,
    continuation_equivalent,
)
from timecut5.pwa import (
    CutPiece, Projection, Row, charge_pwa, combined_pwa, drive_pwa,
    eliminate, lower_envelope, reduce_frontier, schedule_pwa,
)


def family(domain=Interval(0, 1), slope=0, intercept=0, chi=True, rho=0,
           pi=(), anchor="s", remaining=1):
    return CutPiece.from_affine(AffineFamily(domain, slope, intercept, chi, rho,
                                            pi, State(anchor, remaining, len(pi))))


def at(pieces, energy):
    return tuple(p.at(energy) for p in pieces if p.domain.contains(energy))


def one(pieces, energy):
    values = at(pieces, energy)
    assert len(values) == 1, values
    return values[0]


class TestStrictProjection(unittest.TestCase):
    def test_strict_pair_and_exact_lifting(self):
        # 0<x<=y projects to y>0, not y>=0.
        rows = (Row((-1, 0), 0, True), Row((1, -1), 0))
        projection = Projection.build(rows, (0,))
        self.assertEqual(projection.rows, (Row((0, -1), 0, True),))
        self.assertEqual(projection.lift({1: R(2)}), (1, 2))
        with self.assertRaises(ValueError):
            projection.lift({1: R(0)})

    def test_mixed_strict_equality_is_empty(self):
        rows = (Row((-1,), -1), Row((-1,), -1, True), Row((1,), 1))
        self.assertIsNone(Projection.build(rows, (0,)))
        closed = Projection.build((Row((-1,), -1), Row((1,), 1)), (0,))
        self.assertEqual(closed.lift({}), (1,))

    def test_zero_rows_and_positive_normalization(self):
        self.assertIsNone(Projection.build((Row((0,), -1),), ()))
        self.assertIsNone(Projection.build((Row((0,), 0, True),), ()))
        projection = Projection.build((Row((-2, 0), -2), Row((0, 0), 1)), (0,))
        self.assertEqual(projection.lift({1: R(9)}), (1, 9))

    def test_zero_coefficient_residual_is_preserved(self):
        projected = eliminate((Row((1, 0), 5), Row((0, -1), -3, True)), 0)
        self.assertEqual(projected, (Row((0, -1), -3, True),))

    def test_one_sided_and_unconstrained_fibers(self):
        upper = Projection.build((Row((1, 0), 2, True),), (0,))
        lower = Projection.build((Row((-1, 0), -2, True),), (0,))
        self.assertEqual(upper.lift({1: R(7)}), (1, 7))
        self.assertEqual(lower.lift({1: R(7)}), (3, 7))
        unconstrained = Projection.build((Row((0, 0), 1),), (0,))
        self.assertEqual(unconstrained.lift({1: R(7)}), (0, 7))

    def test_two_variable_reverse_reconstruction(self):
        rows = (Row((-1, 0, 0), 0, True), Row((1, -1, 0), 0),
                Row((0, 1, -1), 0, True))
        projection = Projection.build(rows, (0, 1))
        point = projection.lift({2: R(1, 10**60)})
        self.assertTrue(0 < point[0] <= point[1] < point[2])
        self.assertTrue(all(row.holds(point) for row in rows))


class TestPwaOperators(unittest.TestCase):
    def test_v1_c_full_energy_symbolic_formula(self):
        source = family(Interval(0, 1, False, True), 60, 1000, pi=(("1", "C"),))
        result = charge_pwa((source,), FROZEN_CURVE, 300, "3")
        self.assertEqual(len(result), 6)
        expected = ((0, 30, 36, 1300), (30, 48, 60, 580), (48, 60, 120, -2300))
        for lo, hi, slope, intercept in expected:
            piece = next(p for p in result if p.domain == Interval(lo, hi, False, False))
            self.assertEqual((piece.slope, piece.intercept, piece.chi), (slope, intercept, False))
            closed_endpoint = one(result, R(hi))
            self.assertEqual((closed_endpoint.tau, closed_endpoint.chi),
                             (1300 + FROZEN_CURVE.at(hi), False))
        self.assertEqual(at(result, R(0)), ())
        self.assertEqual((one(result, R(1)).tau, one(result, R(1)).chi), (1336, False))
        for piece in result:
            e = (piece.domain.lo + piece.domain.hi) / 2
            w = piece.at(e).approach(R(1, 10**60))
            self.assertTrue(0 < w.events[-1].arrival_energy < e)

    def test_v1_schedule_symbolic_plateau_boundary_and_deadline(self):
        source = family(Interval(0, 1, False, True), 60, 1000)
        charged = charge_pwa((source,), FROZEN_CURVE, 300, "3")
        result = schedule_pwa(charged, "4", 2000, 2100, 100, 300)
        self.assertEqual([(p.domain, p.slope, p.intercept, p.chi) for p in result], [
            (Interval(0, R(100, 9), False, False), 0, 2100, True),
            (Interval(R(100, 9), R(100, 9)), 0, 2100, False),
            (Interval(R(100, 9), R(125, 9), False, False), 36, 1700, False),
        ])
        self.assertEqual(one(result, R(1)).minimum().time, 2100)
        self.assertEqual(at(result, R(125, 9)), ())

    def test_flat_charge_objective_attains_on_open_input_interval(self):
        source = family(Interval(0, 1, False, False), 36, 1000)
        result = charge_pwa((source,), FROZEN_CURVE, 300, "3")
        self.assertTrue(all(p.chi for p in result))
        for e in (R(1, 10**60), R(1), R(60)):
            cut = one(result, e)
            self.assertEqual(cut.minimum().time, 1300 + FROZEN_CURVE.at(e))

    def test_cs_full_energy_plateau_and_charging_bottleneck(self):
        curve = ChargingCurve(((0, 10, 1, 0),))
        source = family(Interval(0, 0), chi=False)
        result = combined_pwa((source,), curve, "cs", 5, 5, 2, 1)
        self.assertEqual([(p.domain, p.slope, p.intercept, p.chi) for p in result], [
            # The complete row arrangement retains an inactive-line crossing
            # at E=2; minimal segmentation/coalescing is not part of this API.
            (Interval(0, 2, False, False), 0, 7, True),
            (Interval(2, 2), 0, 7, True),
            (Interval(2, 6, False, False), 0, 7, True),
            (Interval(6, 6), 0, 7, False),
            (Interval(6, 10, False, False), 1, 1, False),
            (Interval(10, 10), 1, 1, False),
        ])
        self.assertEqual(one(result, R(4)).minimum().time, 7)
        w = one(result, R(10)).approach(R(1, 10**60))
        self.assertGreater(w.time, 11)
        self.assertLessEqual(w.events[-1].arrival_time + 1, 5)

    def test_schedule_infeasible_open_latest_start(self):
        source = family(Interval(0, 1), intercept=4, chi=False)
        self.assertEqual(schedule_pwa((source,), "s", 0, 5, 2, 1), ())
        self.assertEqual(combined_pwa((source,), FROZEN_CURVE, "s", 0, 5, 2, 1), ())
        closed = replace(source, chi=True, _point=family(Interval(0, 1), intercept=4).at)
        result = schedule_pwa((closed,), "s", 0, 5, 2, 1)
        self.assertEqual(one(result, R(1)).minimum().time, 7)

    def test_singleton_input_energy_output_boundary(self):
        source = family(Interval(R(1, 2), R(1, 2)), intercept=1031, rho=1)
        result = charge_pwa((source,), FROZEN_CURVE, 300, "3")
        self.assertEqual(at(result, R(1, 2)), ())
        self.assertEqual(one(result, R(1)).minimum().time, 1349)
        self.assertEqual(one(result, R(60)).minimum().time, 4913)

    def test_tied_minimum_regime_attainment_is_or(self):
        open_piece = family(Interval(0, 1, False, True), 60, 1000)
        singleton = family(Interval(R(1, 2), R(1, 2)), intercept=1018)
        result = charge_pwa((open_piece, singleton), FROZEN_CURVE, 300, "3")
        self.assertFalse(one(result, R(1, 2)).chi)
        self.assertTrue(one(result, R(1)).chi)
        self.assertEqual(one(result, R(1)).minimum().time, 1336)

    def test_drive_clips_without_creating_open_endpoint_energy(self):
        source = family(Interval(1, 3, False, True), slope=2, intercept=5, rho=4)
        result = drive_pwa((source,), "next", 3, 1, floor=1)
        self.assertEqual(result[0].domain, Interval(1, 2))
        self.assertEqual((result[0].slope, result[0].intercept, result[0].rho), (2, 10, 5))
        w = result[0].at(R(1)).minimum()
        self.assertEqual((w.time, w.charge), (12, 6))
        self.assertEqual(drive_pwa((source,), "next", 3, 4), ())

    def test_inherited_subfamily_restriction_survives_second_charge(self):
        curve = ChargingCurve(((0, 4, 1, 0),))
        first = charge_pwa((family(Interval(0, 2)),), curve, 1, "first")
        open_piece = next(p for p in first if p.domain == Interval(0, 2, False, False))
        restricted = replace(open_piece, domain=Interval(1, R(3, 2), False, False))
        second = charge_pwa((restricted,), curve, 1, "second")
        cut = one(second, R(3))
        self.assertEqual((cut.tau, cut.chi), (R(7, 2), False))
        for epsilon in (R(100), R(1, 10**60)):
            w = cut.approach(epsilon)
            predecessor_energy = w.events[-1].arrival_energy
            self.assertTrue(1 < predecessor_energy < R(3, 2))
            self.assertEqual(w.events[-2].departure_energy, predecessor_energy)
            self.assertGreater(w.time, R(7, 2))


class TestPwaReduction(unittest.TestCase):
    def test_singleton_endpoint_attainment_is_not_merged_away(self):
        open_piece = family(Interval(0, 2), chi=False)
        singleton = family(Interval(1, 1))
        result = lower_envelope((open_piece, singleton))
        self.assertTrue(one(result, R(1)).chi)
        self.assertFalse(one(result, R(1, 2)).chi)
        self.assertFalse(one(result, R(3, 2)).chi)

    def test_earlier_larger_rho_branches_both_survive(self):
        a = family(Interval(0, 2), intercept=0, rho=2, pi=(("1", "C"),))
        b = family(Interval(0, 2), intercept=1, rho=1, pi=(("2", "C"),))
        result = reduce_frontier((a, b))
        for e in (R(0), R(1), R(2)):
            self.assertEqual(len(at(result, e)), 2)

    def test_exact_affine_crossing_preserves_point_tie_key(self):
        a = family(Interval(0, 2), slope=1, pi=(("1", "C"),))
        b = family(Interval(0, 2), slope=-1, intercept=2, pi=(("2", "C"),))
        result = reduce_frontier((a, b))
        self.assertEqual(len(at(result, R(1, 2))), 1)
        self.assertEqual(at(result, R(1))[0].pi, a.pi)
        # B is earlier after the crossing but has lex-worse pi at equal rho;
        # the conservative continuation preorder retains both there.
        self.assertEqual(len(at(result, R(3, 2))), 2)

    def test_v1_reduction_before_after_charge_full_energy(self):
        a = family(Interval(0, 1, False, True), 60, 1000, pi=(("1", "C"),))
        b = family(Interval(R(1, 2), R(1, 2)), intercept=1031, rho=1, pi=(("2", "C"),))
        reduced = reduce_frontier((a, b))
        self.assertTrue(all(p.pi == a.pi for p in reduced))
        left = charge_pwa(reduced, FROZEN_CURVE, 300, "3")
        right = reduce_frontier((*charge_pwa((a,), FROZEN_CURVE, 300, "3"),
                                 *charge_pwa((b,), FROZEN_CURVE, 300, "3")))
        # All output pieces have the proven exact curve formula, not merely
        # agreement at sampled SOC values.
        for collection in (left, right):
            for p in collection:
                for lo, hi, m, c in FROZEN_CURVE.segments:
                    e = (p.domain.lo + p.domain.hi) / 2
                    if lo < e < hi:
                        self.assertEqual((p.slope, p.intercept, p.chi, p.rho),
                                         (m, 1300 + c, False, 0))
                p.at((p.domain.lo + p.domain.hi) / 2).approach(R(1, 10**60))
        for e in (R(1, 10**60), R(1, 2), R(1), R(30), R(48), R(60)):
            self.assertTrue(continuation_equivalent(at(left, e), at(right, e)))

    def test_v0_analytic_full_energy_suffix_keeps_76_kwh(self):
        branches = []
        for base, rho, first in ((20100, 35, "1"), (20328, 28, "2")):
            branch = tuple(family(Interval(lo, hi, lo != 0, True), m, base + c,
                                  rho=rho, pi=((first, "C"), ("3", "C")), anchor="3")
                           for lo, hi, m, c in FROZEN_CURVE.segments)
            arrived = drive_pwa(branch, "4", 9000, 40)
            served = schedule_pwa(arrived, "4", 40000, 40000, 2700, 300)
            branches.extend(drive_pwa(served, "z", 450, 2, floor=6))
        reduced = reduce_frontier(branches)
        self.assertTrue(all(p.pi[0][0] == "2" for p in reduced))
        w = one(reduced, R(6)).minimum()
        self.assertEqual((w.time + 600 * w.state.stop_count, w.charge, w.state.stop_count),
                         (44950, 76, 3))
        self.assertEqual(w.events[-2].departure_time, 42700)


if __name__ == "__main__":
    unittest.main()
