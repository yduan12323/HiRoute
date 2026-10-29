from fractions import Fraction as F
import unittest

from hiroute.exact import Projection, Row, eliminate, normalize
from timecut5.pwa import Projection as FrozenProjection, Row as FrozenRow, eliminate as frozen_eliminate

class StrictProjectionTests(unittest.TestCase):
    def test_strict_pair_projects_to_open_boundary_and_lifts(self):
        rows = (Row((-1, 0), 0, True), Row((1, -1), 0))  # 0 < x <= y
        projected = Projection.build(rows, (0,))
        self.assertEqual(projected.rows, (Row((0, -1), 0, True),))  # y > 0
        self.assertEqual(projected.lift({1: F(2)}), (F(1), F(2)))
        with self.assertRaises(ValueError):
            projected.lift({1: F(0)})

    def test_empty_equality_strictness_and_constant_rows(self):
        rows = (Row((-1,), -1), Row((-1,), -1, True), Row((1,), 1))
        self.assertIsNone(Projection.build(rows, (0,)))
        self.assertIsNone(Projection.build((Row((0,), 0, True),), ()))
        self.assertEqual(normalize((Row((0, 0), 1),)), ())

    def test_exact_lift_preserves_unconstrained_coordinates(self):
        p = Projection.build((Row((1, 0), 2, True),), (0,))
        point = p.lift({1: F(7)})
        self.assertEqual(point, (F(1), F(7)))
        self.assertTrue(all(r.holds(point) for r in p.original))

    def test_projection_matches_frozen_v2_on_curated_strict_systems(self):
        cases = [
            (((-1, 0), 0, True), ((1, -1), 0, False)),
            (((1, 0), 5, False), ((0, -1), -3, True)),
            (((-2, 0), -2, False), ((0, 0), 1, False)),
            (((1, 0), 2, True),),
            (((-1, 0), -2, True),),
            (((-1, 0, 0), 0, True), ((1, -1, 0), 0, False), ((0, 1, -1), 0, True)),
        ]
        for raw in cases:
            rows = tuple(Row(c, b, strict) for c, b, strict in raw)
            old = tuple(FrozenRow(c, b, strict) for c, b, strict in raw)
            dimension = len(rows[0].coefficients)
            for variables in [(), (0,), tuple(range(min(2, dimension)))]:
                new_projection = Projection.build(rows, variables)
                old_projection = FrozenProjection.build(old, variables)
                self.assertEqual(new_projection is None, old_projection is None, (raw, variables))
                if new_projection is not None:
                    self.assertEqual(tuple((r.coefficients, r.rhs, r.strict) for r in new_projection.rows), tuple((r.coefficients, r.rhs, r.strict) for r in old_projection.rows), (raw, variables))
            if rows[0].coefficients:
                for v in range(len(rows[0].coefficients)):
                    new_eliminated = eliminate(rows, v)
                    old_eliminated = frozen_eliminate(old, v)
                    self.assertEqual(None if new_eliminated is None else tuple((r.coefficients, r.rhs, r.strict) for r in new_eliminated), None if old_eliminated is None else tuple((r.coefficients, r.rhs, r.strict) for r in old_eliminated), (raw, v))

    def test_declared_dimension_survives_true_zero_rows_and_lifts(self):
        truth = Row((F(0), F(0)), F(1))
        projection = Projection.build((truth,), (0,))
        self.assertEqual(projection.dimension, 2)
        self.assertEqual(projection.original, ())
        self.assertEqual(projection.rows, ())
        self.assertEqual(projection.lift({1: F(7)}), (F(0), F(7)))

    def test_empty_row_projection_retains_declared_space(self):
        projection = Projection.build((Row((F(0), F(0)), F(1)),), ())
        self.assertEqual(projection.dimension, 2)
        self.assertEqual(projection.lift({0: F(5), 1: F(7)}), (F(5), F(7)))

    def test_duplicate_variable_elimination_rejected(self):
        with self.assertRaises(ValueError):
            Projection.build((Row((1, 0), 1),), (0, 0))

if __name__ == "__main__":
    unittest.main()
