import sys
import unittest
from fractions import Fraction as F
sys.path.insert(0, "tests")
from hiroute.exact.interval import Interval
from hiroute.exact.pwa import AffineCutPiece
from timecut5.probe import AffineFamily, Interval as OldInterval, State
from timecut5.pwa import CutPiece as OldCutPiece

class PwaPieceParityTests(unittest.TestCase):
    def test_piece_values_identity_and_domain_match_legacy(self):
        domains = [(Interval(F(0), F(2)), True),
                   (Interval(F(0), F(2), False, True), False),
                   (Interval(F(0), F(2), True, False), True)]
        for domain, attained in domains:
            current = AffineCutPiece(domain, F(3, 2), F(4), attained,
                                     rho=F(2), prefix=(), state_key=("s", 1, 0))
            old_domain = OldInterval(domain.lo, domain.hi, domain.left_closed, domain.right_closed)
            old = OldCutPiece.from_affine(AffineFamily(old_domain, F(3, 2), F(4), attained,
                                                        F(2), (), State("s", 1, 0)))
            for energy in (F(1, 2), F(1), F(2)):
                if domain.contains(energy):
                    self.assertEqual(current.cut_time_at(energy), old.at(energy).tau)
            old_energy, old_endpoint_attained = old.domain.affine_infimum(old.slope)
            self.assertEqual(current.infimum(),
                             (old.slope * old_energy + old.intercept,
                              old.chi and old_endpoint_attained, old_energy))
            with self.assertRaises(ValueError):
                current.cut_time_at(F(3))

    def test_rejects_float_and_preserves_metadata(self):
        piece = AffineCutPiece(Interval(F(0), F(1)), F(2), F(3), True,
                               rho=F(1), prefix=(), state_key=("x", 0, 0))
        self.assertEqual(piece.cut_time_at(F(1, 2)), F(4))
        with self.assertRaises(TypeError):
            AffineCutPiece(Interval(F(0), F(1)), 0.1, 0, True)

if __name__ == "__main__":
    unittest.main()
