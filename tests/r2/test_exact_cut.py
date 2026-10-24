from fractions import Fraction as F
import unittest

from hiroute.exact import (TimeCut, UnattainedError, cut_le, exact, fixed_member)
from timecut5.probe import Cut as FrozenCut, State, Witness as FrozenWitness, cut_le as frozen_cut_le

class ExactScalarTests(unittest.TestCase):
    def test_exact_inputs_reject_float_and_bool(self):
        self.assertEqual(exact("5/2"), F(5, 2))
        self.assertEqual(exact(3), F(3))
        for invalid in (True, 1.25, "01", "1/0", "1.0"):
            with self.subTest(invalid=invalid), self.assertRaises(TypeError):
                exact(invalid)

class TimeCutTests(unittest.TestCase):
    def test_open_boundary_approach_and_realization(self):
        cut = fixed_member(F(3), attained=False, context=("site", F(2), 0, 1), family_id="branch-A")
        w = cut.approach(F(1, 10))
        self.assertGreater(w.time, F(3))
        self.assertLess(w.time, F(31, 10))
        self.assertEqual(cut.realize_le(F(4, 1)).context, cut.context)
        with self.assertRaises(UnattainedError):
            cut.minimum()
        with self.assertRaises(UnattainedError):
            cut.realize_le(F(3))

    def test_closed_boundary_and_budget(self):
        cut = fixed_member(F(7, 3), attained=True, context="state", family_id="closed")
        self.assertEqual(cut.minimum().time, F(7, 3))
        self.assertEqual(cut.realize_le(F(7, 3)).time, F(7, 3))

    def test_witness_cannot_escape_inherited_family(self):
        def wrong_family(_epsilon):
            from hiroute.exact import CutWitness
            return CutWitness(F(1), ("s", F(2), 0, 1), "unrestricted-parent")
        cut = TimeCut(F(1), True, ("s", F(2), 0, 1), "restricted-child", wrong_family)
        with self.assertRaisesRegex(ValueError, "family"):
            cut.minimum()

    def test_open_closed_preorder_matches_frozen_v2(self):
        state = State("x", 0, 0)
        def make_old(tau, chi, fid):
            def approach(epsilon):
                t = tau if chi else tau + min(F(1), epsilon / 2)
                return FrozenWitness(t, F(1), F(0), (), state)
            return FrozenCut(F(tau), chi, F(1), F(0), (), state, approach)
        for ta in (F(0), F(1), F(3, 2)):
            for tb in (F(0), F(1), F(3, 2)):
                for ca in (False, True):
                    for cb in (False, True):
                        new_a = fixed_member(ta, attained=ca, context="same", family_id="a")
                        new_b = fixed_member(tb, attained=cb, context="same", family_id="b")
                        self.assertEqual(cut_le(new_a, new_b), frozen_cut_le(make_old(ta, ca, "a"), make_old(tb, cb, "b")))

if __name__ == "__main__":
    unittest.main()
