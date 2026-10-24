import sys
import unittest
from fractions import Fraction as F
sys.path.insert(0, "tests")
from timecut5.probe import Interval as LegacyInterval
from hiroute.exact.interval import Interval

class ExactIntervalTests(unittest.TestCase):
    def test_endpoint_attainment_and_affine_infimum_parity(self):
        intervals = [Interval(F(0), F(2)), Interval(F(0), F(2), False, True),
                     Interval(F(0), F(2), True, False), Interval(F(1), F(1))]
        for current in intervals:
            legacy = LegacyInterval(current.lo, current.hi, current.left_closed, current.right_closed)
            for slope in map(F, (-2, 0, 3)):
                self.assertEqual(current.affine_infimum(slope), legacy.affine_infimum(slope))
                for value in map(F, (-1, 0, 1, 2, 3)):
                    self.assertEqual(current.contains(value), legacy.contains(value))

    def test_intersection_tracks_open_singleton(self):
        self.assertIsNone(Interval(F(0), F(1), True, False).intersect(Interval(F(1), F(2))))
        self.assertEqual(Interval(F(0), F(1)).intersect(Interval(F(1), F(2))), Interval(F(1), F(1)))

    def test_open_optimizer_is_constructive(self):
        interval = Interval(F(0), F(2), False, True)
        x = interval.approach_optimizer(F(3), F(1, 10))
        self.assertTrue(interval.contains(x))
        self.assertLess(3 * (x - interval.lo), F(1, 10))
        self.assertEqual(interval.approach_optimizer(F(0), F(1, 10)), F(1))

    def test_rejects_approximate_values_and_empty_intervals(self):
        with self.assertRaises(TypeError):
            Interval(0.0, 1)
        with self.assertRaises(ValueError):
            Interval(F(1), F(1), False, True)

if __name__ == "__main__":
    unittest.main()
