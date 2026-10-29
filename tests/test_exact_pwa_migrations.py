"""Local parity checks for bounded exact S/C/CS migration operators."""
from fractions import Fraction as Q
import unittest

from hiroute.exact import (schedule_piece as exported_schedule_piece,
                           charge_fixed as exported_charge_fixed,
                           combined_fixed as exported_combined_fixed,
                           reduce_family_pieces as exported_reduce_family)
from hiroute.exact.interval import Interval
from hiroute.exact.pwa import (
    AffineCutPiece, schedule_piece, charge_fixed, combined_fixed, reduce_family_pieces,
)
from timecut5.probe import AffineFamily, FROZEN_CURVE, State
from timecut5.pwa import CutPiece, schedule_pwa, charge_pwa, combined_pwa, reduce_frontier


def exact_piece(domain, slope, intercept, attained, state):
    return AffineCutPiece(domain, Q(slope), Q(intercept), attained,
                          Q(0), (), (state.anchor, state.remaining_schedule,
                                     state.stop_count))


class TestExactLocalStopMigration(unittest.TestCase):
    def test_migrated_operators_are_exported(self):
        self.assertIs(exported_schedule_piece, schedule_piece)
        self.assertIs(exported_charge_fixed, charge_fixed)
        self.assertIs(exported_combined_fixed, combined_fixed)
        self.assertIs(exported_reduce_family, reduce_family_pieces)

    def test_schedule_waiting_plateau_and_open_threshold_match_legacy(self):
        domain = Interval(0, 2)
        state = State("s", 1, 0)
        source = CutPiece.from_affine(
            AffineFamily(domain, -4, 15, False, 0, (), state))
        old = schedule_pwa((source,), "s", 12, 25, 3, 2)
        new = schedule_piece(exact_piece(domain, -4, 15, False, state),
                             "s", 12, 25, 3, 2)
        for energy in map(Q, (0, 1, Q(3, 2), 2)):
            prior = [p for p in old if p.domain.contains(energy)]
            migrated = [p for p in new if p.domain.contains(energy)]
            self.assertEqual(len(prior), 1, (energy, old))
            self.assertEqual(len(migrated), 1, (energy, new))
            cut = prior[0].at(energy)
            self.assertEqual((migrated[0].cut_time_at(energy),
                              migrated[0].attained),
                             (cut.tau, cut.chi))
        at_threshold = next(p for p in new if p.domain.contains(Q(5, 4)))
        self.assertFalse(at_threshold.attained)
        self.assertEqual(at_threshold.cut_time_at(Q(5, 4)), 15)
        plateau = next(p for p in new if p.domain.contains(Q(3, 2)))
        self.assertTrue(plateau.attained)
        self.assertEqual(plateau.cut_time_at(Q(3, 2)), 15)

    def test_same_family_reduction_matches_old_and_never_crosses_family(self):
        domain = Interval(0, 2)
        state = State("s", 0, 1)
        prefix = (("s", "S"),)
        better = AffineCutPiece(domain, Q(0), Q(3), True, Q(0),
                                prefix, ("s", 0, 1))
        worse = AffineCutPiece(domain, Q(0), Q(4), False, Q(1),
                               prefix, ("s", 0, 1))
        reduced = reduce_family_pieces((better, worse))
        self.assertEqual(reduced, (better,))
        old_better = CutPiece.from_affine(
            AffineFamily(domain, 0, 3, True, 0, prefix, state))
        old_worse = CutPiece.from_affine(
            AffineFamily(domain, 0, 4, False, 1, prefix, state))
        old = reduce_frontier((old_better, old_worse))
        for energy in map(Q, (0, 1, 2)):
            selected = [piece for piece in old if piece.domain.contains(energy)]
            self.assertEqual(len(selected), 1)
            old_cut = selected[0].at(energy)
            new_cut = next(piece for piece in reduced
                           if piece.domain.contains(energy))
            self.assertEqual((new_cut.cut_time_at(energy), new_cut.attained,
                              new_cut.rho, new_cut.prefix),
                             (old_cut.tau, old_cut.chi,
                              old_cut.rho, old_cut.pi))

        other_family = AffineCutPiece(domain, Q(-100), Q(0), True, Q(0),
                                      prefix, ("other", 0, 1))
        kept = reduce_family_pieces((better, other_family))
        self.assertEqual(kept, (better, other_family))


    def test_fixed_charge_infimum_matches_legacy_pwa_at_three_outputs(self):
        domain = Interval(0, 1, False, True)
        state = State("s", 1, 0)
        source = CutPiece.from_affine(
            AffineFamily(domain, 60, 1000, True, 0, (), state))
        migrated = exact_piece(domain, 60, 1000, True, state)
        old = charge_pwa((source,), FROZEN_CURVE, 300, "c")
        for output_energy in map(Q, (30, 48, 60)):
            prior = [p for p in old if p.domain.contains(output_energy)]
            self.assertTrue(prior, output_energy)
            cut = prior[0].at(output_energy)
            result = charge_fixed(migrated, output_energy,
                                  FROZEN_CURVE.segments, 300)
            self.assertEqual((result.tau, result.attained),
                             (cut.tau, cut.chi))
            self.assertLess(result.input_energy, output_energy)

    def test_fixed_cs_matches_legacy_pwa_on_fixed_energy_pair(self):
        domain = Interval(0, 0)
        state = State("s", 1, 0)
        source = CutPiece.from_affine(
            AffineFamily(domain, 1, 0, True, 0, (), state))
        migrated = exact_piece(domain, 1, 0, True, state)
        old = combined_pwa((source,), FROZEN_CURVE, "cs", 5, 5, 2, 1)
        input_energy, output_energy = Q(0), Q(1)
        prior = [p for p in old if p.domain.contains(output_energy)]
        self.assertTrue(prior)
        cut = prior[0].at(output_energy)
        result = combined_fixed(
            migrated, input_energy, output_energy, FROZEN_CURVE.segments,
            "cs", 5, 5, 2, 1)
        self.assertEqual((result.tau, result.attained),
                         (cut.tau, cut.chi))


if __name__ == "__main__":
    unittest.main()
