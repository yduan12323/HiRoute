"""Synthetic exact recovery regressions; no native optimization calls."""
from fractions import Fraction as F
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from validation.suffix5 import vendor_lp as v, basis_exchange as ex
from validation.suffix5.checker import verify_lp_certificate
from validation.suffix5.model import plain


class BasisExchangeTests(unittest.TestCase):
    def check(self,c,A,b,eq,cert):
        task=dict(c=list(map(str,c)),A=[list(map(str,row)) for row in A],b=list(map(str,b)),
                  equalities=[[list(map(str,row)),str(rhs)] for row,rhs in eq])
        self.assertEqual(verify_lp_certificate(task,plain(cert))['objective'],str(cert['objective']))
        self.assertTrue(v.verify_certificate(c,A,b,eq,cert))

    def test_float_identical_bounds_need_different_exact_dual_support(self):
        epsilon=F(1,2**80)
        c=(F(0),F(0),F(-1));A=[(-1,0,1),(1,0,0),(0,-1,1),(1,1,0)];b=[F(0),F(1),F(0),2-epsilon]
        self.assertEqual(float(F(1)),float(1-epsilon/2))
        seed=dict(x=(F(1),F(1),F(1)),inequality_dual=(F(-1),F(-1),F(0),F(0)),equality_dual=())
        with patch.object(ex,'recover_exchange',side_effect=v.UncertifiedLP('legacy exhausted')):
            with self.assertRaisesRegex(v.UncertifiedLP,'legacy exhausted'):v.recover_certificate(c,A,b,(),seed)
        cert=v.recover_certificate(c,A,b,(),seed)
        self.assertEqual(cert['x'],(1-epsilon/2,)*3)
        self.assertEqual(cert['objective'],-1+epsilon/2)
        self.assertEqual(cert['recovery_dual_support'],(0,2,3))
        self.check(c,A,b,(),cert)

    def test_greedy_inactive_row_is_replaced_without_changing_dual_optimum(self):
        epsilon=F(1,2**80)
        c=(F(0),F(0),F(-1));A=[(-1,0,1),(1,0,0),(0,-1,1),(-1,-1,0)]
        b=[F(0),F(1),F(0),-2+epsilon]
        seed=dict(x=(F(1),1-epsilon,F(1)),inequality_dual=(F(-1),F(-1),F(0),F(0)),equality_dual=())
        cert=v.recover_certificate(c,A,b,(),seed)
        self.assertEqual(cert['x'],(F(1),)*3);self.assertEqual(cert['objective'],F(-1))
        self.check(c,A,b,(),cert)

    def test_old_success_does_not_enter_exchange(self):
        seed=dict(x=(F(1),F(1)-F(1,10**12)),inequality_dual=(-F(1),F(0)),equality_dual=())
        with patch.object(ex,'recover_exchange',side_effect=AssertionError('unexpected fallback')):
            cert=v.recover_certificate((F(1),F(0)),[(-1,0),(0,-1)],[-F(1),-F(1)],(),seed)
        self.assertEqual(cert['x'],(F(1),F(1)))

    def test_native_candidate_path_uses_one_fake_pass_and_independent_check(self):
        eps=F(1,2**80);c=(F(0),F(0),F(-1));A=[(-1,0,1),(1,0,0),(0,-1,1),(1,1,0)];b=[0,1,0,2-eps]
        fake=SimpleNamespace(success=True,status=0,message='hand candidate',x=[1.,1.,1.],
            ineqlin=SimpleNamespace(marginals=[-1.,-1.,0.,0.]),eqlin=SimpleNamespace(marginals=[]))
        with patch.object(v,'linprog',return_value=fake) as native:cert=v.exact_lp(c,A,b)
        self.assertEqual(native.call_count,1);self.check(c,A,b,(),cert)

    def test_equalities_remain_mandatory_during_exchange(self):
        eps=F(1,2**80);c=(F(0),F(0),F(-1),F(0));A=[(-1,0,1,0),(1,0,0,0),(0,-1,1,0),(1,1,0,0)]
        b=[F(0),F(1),F(0),2-eps];eq=[((0,0,0,1),F(3)),((0,0,0,2),F(6))]
        seed=dict(x=(F(1),F(1),F(1),F(3)),inequality_dual=(F(-1),F(-1),F(0),F(0)),equality_dual=(F(0),F(0)))
        cert=v.recover_certificate(c,A,b,eq,seed)
        self.assertEqual(cert['x'][-1],3);self.check(c,A,b,eq,cert)

    def test_infeasible_constraints_cannot_become_an_accepted_certificate(self):
        seed=dict(x=(F(0),),inequality_dual=(F(0),F(0)),equality_dual=())
        with self.assertRaises(v.UncertifiedLP):v.recover_certificate((F(0),),[(1,),(-1,)],[F(0),F(-1)],(),seed)

    def test_finite_trial_cap_and_no_native_reentry(self):
        epsilon=F(1,2**80);c=(F(0),F(0),F(-1));A=[(-1,0,1),(1,0,0),(0,-1,1),(1,1,0)];b=[F(0),F(1),F(0),2-epsilon]
        seed=dict(x=(F(1),F(1),F(1)),inequality_dual=(F(-1),F(-1),F(0),F(0)),equality_dual=())
        with patch.object(ex,'MAX_EXCHANGE_TRIALS',1),patch.object(v,'linprog',side_effect=AssertionError('native forbidden')):
            with self.assertRaisesRegex(v.UncertifiedLP,'trial cap'):v.recover_certificate(c,A,b,(),seed)


if __name__=='__main__':unittest.main()
