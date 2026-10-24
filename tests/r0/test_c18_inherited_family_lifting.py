"""C18: inherited-family restrictions must survive charging witness lifting."""
from dataclasses import replace
from fractions import Fraction as Q
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from timecut5.probe import AffineFamily, ChargingCurve, Interval, State
from timecut5.pwa import CutPiece, charge_pwa


def _piece(domain):
    return CutPiece.from_affine(AffineFamily(domain, 0, 0, True, 0, (), State("s", 1, 0)))


class InheritedFamilyWitnessLifting(unittest.TestCase):
    def test_restriction_survives_second_charge_and_lifts_approach_witness(self):
        curve = ChargingCurve(((0, 4, 1, 0),))
        first = charge_pwa((_piece(Interval(0, 2)),), curve, 1, "first")
        inherited = next(p for p in first if p.domain == Interval(0, 2, False, False))
        restricted_domain = Interval(1, Q(3, 2), False, False)
        inherited = replace(inherited, domain=restricted_domain)
        second = charge_pwa((inherited,), curve, 1, "second")
        cut = next(p.at(Q(3)) for p in second if p.domain.contains(Q(3)))

        self.assertEqual((cut.tau, cut.chi), (Q(7, 2), False))
        for epsilon in (Q(100), Q(1, 10**60)):
            witness = cut.approach(epsilon)
            predecessor_energy = witness.events[-1].arrival_energy
            self.assertTrue(restricted_domain.contains(predecessor_energy))
            self.assertEqual(witness.events[-2].departure_energy, predecessor_energy)
            self.assertGreater(witness.time, Q(7, 2))


if __name__ == "__main__":
    unittest.main()
