"""Hand/fake candidates only; native optimization is never invoked."""
from fractions import Fraction as F
from itertools import permutations
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from validation.suffix5 import vendor_lp as v, basis_exchange as ex, basis_walk as w
from validation.suffix5.checker import verify_lp_certificate
from validation.suffix5.model import plain


def energy():
    c = tuple(map(F, (0, 0, 0, -1)))
    A = [tuple(map(F, r)) for r in ((-1,0,0,1), (1,0,0,0), (0,1,0,0),
        (0,0,1,0), (0,-1,0,1), (0,0,-1,1), (1,1,1,0))]
    b = list(map(F, (0,1,1,1,0,0,3))); b[-1] -= F(1, 2**80)
    seed = dict(x=(F(1),)*4, inequality_dual=tuple(map(F, (-1,-1,0,0,0,0,0))), equality_dual=())
    return c, A, b, seed


class BasisWalkTests(unittest.TestCase):
    def check(self, c, A, b, eq, cert):
        task = dict(c=list(map(str,c)), A=[list(map(str,row)) for row in A],
            b=list(map(str,b)), equalities=[[list(map(str,row)),str(rhs)] for row,rhs in eq])
        self.assertEqual(verify_lp_certificate(task, plain(cert))['objective'], str(cert['objective']))
        self.assertTrue(v.verify_certificate(c, A, b, eq, cert))
        self.assertTrue(all(v.dot(A[i], cert['x']) == b[i] for i in cert['recovery_inequality_rows']))

    def test_successive_energy_faces_need_more_than_one_original_exchange(self):
        c, A, b, seed = energy()
        with patch.object(w, 'recover_walk', side_effect=v.UncertifiedLP('walk needed')):
            with self.assertRaisesRegex(v.UncertifiedLP, 'walk needed'):
                v.recover_certificate(c, A, b, (), seed)
        with patch.object(v, 'linprog', side_effect=AssertionError('native forbidden')):
            cert = v.recover_certificate(c, A, b, (), seed)
        expected = 1-F(1, 3*2**80)
        self.assertEqual(cert['x'], (expected,)*4)
        self.assertEqual(cert['objective'], -expected)
        self.check(c, A, b, (), cert)

    def test_multiple_clock_epigraphs_move_together(self):
        c = tuple(map(F, (-1,0,0)))
        A = [tuple(map(F, r)) for r in ((1,0,0),(-1,0,0),(1,-1,0),(2,-1,0),(0,1,-1),(0,2,-1))]
        b = list(map(F, (1,0,0,0,0,0)))
        seed = dict(x=(F(1),)*3, inequality_dual=tuple(map(F, (-1,0,0,0,0,0))), equality_dual=())
        with patch.object(w, 'recover_walk', side_effect=v.UncertifiedLP('walk needed')):
            with self.assertRaisesRegex(v.UncertifiedLP, 'walk needed'):
                v.recover_certificate(c,A,b,(),seed)
        cert = v.recover_certificate(c,A,b,(),seed)
        self.assertEqual(cert['x'], (1,2,4)); self.check(c,A,b,(),cert)

    def test_objective_and_equality_columns_are_not_lifted(self):
        A = ((F(-1),F(0)), (F(1),F(-1)))
        self.assertEqual(w._upward_columns((F(0),F(1)), A, ()), ())
        self.assertEqual(w._upward_columns((F(0),F(0)), A, (((0,1),F(3)),)), ())
        self.assertEqual(w._upward_columns((F(0),F(0)), A, ()), (1,0))
        cycle = ((F(1),F(-1)),(F(-1),F(1)))
        self.assertEqual(w._upward_columns((F(0),F(0)), cycle, ()), ())

    def test_equalities_remain_exact_and_redundancy_is_allowed(self):
        c,A,b,seed = energy()
        c += (F(0),); A = [r+(F(0),) for r in A]
        eq = [((0,0,0,0,1),F(3)), ((0,0,0,0,2),F(6))]
        seed = dict(seed, x=seed['x']+(F(3),), equality_dual=(F(0),F(0)))
        cert = v.recover_certificate(c,A,b,eq,seed)
        self.assertEqual(cert['x'][-1],3); self.check(c,A,b,eq,cert)

    def test_row_permutations_keep_exact_solution(self):
        c,A,b,seed = energy()
        for head in permutations(range(4)):
            order = tuple(head)+(4,5,6)
            rows, rhs = [A[i] for i in order], [b[i] for i in order]
            candidate = dict(seed, inequality_dual=tuple(seed['inequality_dual'][i] for i in order))
            cert = v.recover_certificate(c,rows,rhs,(),candidate)
            self.assertEqual(cert['objective'], -1+F(1,3*2**80))
            self.check(c,rows,rhs,(),cert)

    def test_fake_native_single_pass_and_independent_check(self):
        c,A,b,seed = energy()
        result = SimpleNamespace(status=0,success=True,message='hand candidate',x=[1.]*4,
            ineqlin=SimpleNamespace(marginals=[-1.,-1.,0.,0.,0.,0.,0.]),
            eqlin=SimpleNamespace(marginals=[]))
        with patch.object(v, 'linprog', return_value=result) as native:
            cert = v.exact_lp(c,A,b)
        self.assertEqual(native.call_count,1); self.check(c,A,b,(),cert)

    def test_legacy_success_never_enters_walk(self):
        seed = dict(x=(F(1),), inequality_dual=(F(-1),), equality_dual=())
        with patch.object(w,'recover_walk',side_effect=AssertionError('unexpected walk')):
            cert=v.recover_certificate((F(-1),),[(F(1),)],[F(1)],(),seed)
        self.assertEqual(cert['x'],(F(1),))

    def test_other_exchange_failures_do_not_bypass_caps(self):
        c,A,b,seed = energy()
        for error in ('Exact basis-exchange trial cap exhausted','wrong source'):
            with self.subTest(error=error), patch.object(ex,'recover_exchange',side_effect=v.UncertifiedLP(error)), \
                 patch.object(w,'recover_walk',side_effect=AssertionError('unexpected walk')):
                with self.assertRaisesRegex(v.UncertifiedLP,error): v.recover_certificate(c,A,b,(),seed)

    def test_trial_and_discovery_caps_remain_unresolved(self):
        c,A,b,seed = energy()
        for name in ('MAX_BASES','MAX_DISCOVERED'):
            with self.subTest(name=name), patch.object(w,name,1):
                with self.assertRaisesRegex(v.UncertifiedLP,'cap exhausted'):
                    w.recover_walk(c,A,b,(),seed,[0,1,2,3])

    def test_invalid_caps_rows_and_dimensions_reject(self):
        c,A,b,seed = energy()
        for name in ('MAX_BASES','MAX_DISCOVERED'):
            for value in (True,0,-1,1.0):
                with self.subTest(name=name,value=value), patch.object(w,name,value):
                    with self.assertRaises(v.UncertifiedLP):w.recover_walk(c,A,b,(),seed,[0,1,2,3])
        for ids in ([0,0],[True,1],[0,99]):
            with self.assertRaises(v.UncertifiedLP):w.recover_walk(c,A,b,(),seed,ids)
        with patch.object(w,'MAX_VARIABLES',3):
            with self.assertRaises(v.UncertifiedLP):w.recover_walk(c,A,b,(),seed,[0,1,2,3])

    def test_feasible_point_with_bad_dual_is_not_accepted(self):
        seed=dict(x=(F(0),),inequality_dual=(F(0),F(0)),equality_dual=())
        with self.assertRaisesRegex(v.UncertifiedLP,'neighborhood'):
            w.recover_walk((F(-1),),[(F(1),),(F(-1),)],[F(1),F(0)],(),seed,[1])

    def test_infeasible_system_cannot_be_certified(self):
        seed=dict(x=(F(0),),inequality_dual=(F(0),F(0)),equality_dual=())
        with self.assertRaises(v.UncertifiedLP):
            w.recover_walk((F(0),),[(F(1),),(F(-1),)],[F(0),F(-1)],(),seed,[0])

    def test_deadline_exception_is_not_swallowed(self):
        c,A,b,seed=energy()
        with patch.object(v,'solve_rational_equalities',side_effect=TimeoutError('deadline')):
            with self.assertRaises(TimeoutError):w.recover_walk(c,A,b,(),seed,[0,1,2,3])


if __name__ == '__main__':
    unittest.main()
