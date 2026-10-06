"""Literal adversarial oracle self-tests; production is never imported."""
import unittest
from fractions import Fraction as Q
from oracle import Answer, Oracle, Seed, Span


class OracleLiterals(unittest.TestCase):
    def oracle(self, domains, curve=((0,10,2,0),), h=1, **kwargs):
        return Oracle([Seed(Span(*d),Q(m),Q(c),chi) for d,m,c,chi in domains],curve,h,**kwargs)

    def test_open_arrival_boundary_positive_slope_historical(self):
        o = self.oracle([((0,1,False,True),60,1000,True)],curve=((0,10,36,0),),h=300)
        self.assertEqual(o.at(1),Answer(Q(1336),False))
        self.assertIsNone(o.at(0))

    def test_negative_zero_positive_tau_minus_f(self):
        for slope,tau,chi in [(0,101,False),(2,103,True),(4,103,True)]:
            with self.subTest(slope=slope):
                o = self.oracle([((0,2),slope,100,True)])
                self.assertEqual(o.at(1),Answer(Q(tau),chi))

    def test_zero_slope_open_time_is_not_attained(self):
        o = self.oracle([((0,2,False,False),2,100,False)])
        self.assertEqual(o.at(1),Answer(Q(103),False))

    def test_forbidden_zero_charge_and_capacity_end(self):
        o = self.oracle([((2,2),0,0,True)],curve=((0,3,1,0),))
        self.assertIsNone(o.at(2))
        self.assertEqual(o.at(3),Answer(Q(2),True))
        self.assertIsNone(o.at(Q(7,2)))
        full = self.oracle([((3,3),0,0,True)],curve=((0,3,1,0),))
        self.assertIsNone(full.at(3))

    def test_right_open_optimizer(self):
        o = self.oracle([((0,1,True,False),0,100,True)])
        self.assertEqual(o.at(2),Answer(Q(103),False))

    def test_charge_kinks(self):
        o = self.oracle([((0,3),2,0,True)],curve=((0,1,1,0),(1,3,3,-2)))
        self.assertEqual(o.at(1),Answer(Q(2),True))
        self.assertEqual(o.at(Q(3,2)),Answer(Q(7,2),True))
        self.assertEqual(o.at(2),Answer(Q(5),True))
        self.assertEqual(o.at(3),Answer(Q(7),False))

    def test_deadline_equality_open_closed(self):
        for chi in (False,True):
            o = self.oracle([((0,0),0,4,chi)],a=5,b=5,duration=2)
            self.assertEqual(o.at(1),Answer(Q(7),True) if chi else None)

    def test_cs_plateau_interior_boundary_and_charge_dominance(self):
        o = self.oracle([((0,0),0,0,False)],curve=((0,8,1,0),),a=5,b=5,duration=2)
        self.assertEqual(o.at(4),Answer(Q(7),True))
        self.assertEqual(o.at(6),Answer(Q(7),False))
        self.assertEqual(o.at(8),Answer(Q(9),False))

    def test_cs_plateau_endpoint_attained_input(self):
        o = self.oracle([((0,0),0,0,True)],curve=((0,8,1,0),),a=5,b=5,duration=2)
        self.assertEqual(o.at(6),Answer(Q(7),True))

    def test_tied_minimizers_attainment_or(self):
        o = self.oracle([((0,1,False,True),4,0,True),((0,0),0,0,True)])
        self.assertEqual(o.at(1),Answer(Q(3),True))
        o_open = self.oracle([((0,1,False,True),4,0,True)])
        self.assertEqual(o_open.at(1),Answer(Q(3),False))

    def test_cs_invalid_window_is_empty(self):
        o = self.oracle([((0,1),0,0,True)],a=6,b=5,duration=1)
        self.assertIsNone(o.at(1))

    def test_symbolic_partition_exposes_open_boundary(self):
        o = self.oracle([((0,0),0,0,False)],curve=((0,8,1,0),),a=5,b=5,duration=2)
        self.assertIn(Q(6),o.boundaries())
        pieces = o.pieces()
        self.assertTrue(any(d.lo == d.hi == 6 and not chi for d,_,chi in pieces))
        for d,f,chi in pieces:
            e = d.member()
            self.assertEqual(o.at(e),Answer(f(e),chi))


if __name__ == '__main__':
    unittest.main()
