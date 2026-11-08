import copy
from fractions import Fraction as F
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import z3
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
from incumbent_model_certificate import certify,incumbent_bindings,evaluate_assertions
from exact_physical_adapter import Encoding,Engine,_solve,relevant_depth
from exact_physical_fixtures import case,tiny_table,IDS,semantics
from tests.test_exact_physical_adapter import trap


def fixture_model(f,t=None,extra=2):
    if t is None:t=tiny_table(f)[0]
    h,u=relevant_depth(t,f['physics'],f['upper_witness']);m=Encoding(t,f['physics'],h+extra,u['key'][0],finite_lookup=True)
    x,y=m.state_copy(),m.state_copy();base=m.G+x['P']+y['P']+y['strict']
    return t,m,x,y,base


class IncumbentCertificateTests(unittest.TestCase):
    def test_all_tiny_seeds_inactive_suffix_repeated_visits_and_traps(self):
        for f,t in [(case(n),None) for n in IDS]+[trap(False),trap(True)]:
            t,m,x,y,base=fixture_model(f,t)
            before=tuple(base)
            with patch('z3.Solver',side_effect=AssertionError('certificate may not solve')),patch('z3.Optimize',side_effect=AssertionError('certificate may not optimize')),patch('z3.Tactic',side_effect=AssertionError('no tactic')):
                cert=certify(m,x,y,t,f['physics'],f['upper_witness'],base)
            self.assertTrue(cert['all_assertions_exactly_true']);self.assertEqual(cert['assertions'],len(base))
            self.assertTrue(all(z3.eq(a,b) for a,b in zip(before,base)))
            self.assertEqual(cert['table_sha256'],t.payload_sha256)

    def test_exact_evaluator_edges_and_fail_closed(self):
        i=z3.Int('i');r=z3.Real('r');b=z3.Bool('b')
        bindings=[(i,2),(r,F(2,7)),(b,True)]
        roots=[z3.ToReal(i)*r==F(4,7),z3.If(b,i,0)==2,z3.Implies(b,r>0),z3.Xor(b,i==3),z3.Distinct(i,0),-r+F(2,7)==0]
        evaluate_assertions(roots,bindings)
        for bad in (bindings[:-1],bindings+[(i,2)],[(i,True),(r,F(2,7)),(b,True)],[(i,2),(r,.25),(b,True)]):
            with self.assertRaises(ValueError):evaluate_assertions(roots,bad)
        for expr,bs in ((i<0,[(i,2)]),(z3.If(z3.BoolVal(True),z3.BoolVal(True),i>0),[]),(z3.ForAll(i,i==i),[]),(z3.Select(z3.Array('A',z3.IntSort(),z3.IntSort()),0)==0,[]),(r/0==1,[(r,F(1))]),(r**2==1,[(r,F(1))])):
            with self.assertRaises(ValueError):evaluate_assertions([expr],bs)
        with self.assertRaises(ValueError):evaluate_assertions(roots,bindings,max_nodes=1)
        with self.assertRaises(TimeoutError):evaluate_assertions(roots,bindings,lambda:(_ for _ in ()).throw(TimeoutError()))

    def test_mutated_bindings_roots_physics_and_foreign_states_rejected(self):
        f=case('repeated_C_S_C');t,m,x,y,base=fixture_model(f)
        bindings,_=incumbent_bindings(m,x,y,t,f['physics'],f['upper_witness'])
        for symbol in (m.choices[0],m.ins[0],m.maxima[0],x['state_symbols'][0][0]):
            bad=[(s,(999 if s.sort().kind()==z3.Z3_INT_SORT else F(999))) if z3.eq(s,symbol) else (s,v) for s,v in bindings]
            with self.assertRaises(ValueError):evaluate_assertions(base,bad)
        with self.assertRaises(ValueError):certify(m,x,y,t,f['physics'],f['upper_witness'],base[:-1])
        with self.assertRaises(ValueError):certify(m,x,y,t,f['physics'],f['upper_witness'],base[::-1])
        bad_physics=copy.deepcopy(f['physics']);bad_physics['stop_penalty_s']='99'
        with self.assertRaises(ValueError):certify(m,x,y,t,bad_physics,f['upper_witness'],base)
        other=m.state_copy();other['encoding_owner']=object()
        with self.assertRaises(ValueError):incumbent_bindings(m,x,other,t,f['physics'],f['upper_witness'])
        bad_w=copy.deepcopy(f['upper_witness']);bad_w['charges'][0]='0'
        with self.assertRaises(ValueError):certify(m,x,y,t,f['physics'],bad_w,base)

    def test_only_initial_search_skipped_all_outcomes_and_later_checks_preserved(self):
        original=Engine.feasible;seen=set()
        def feasible(engine,constraints,kind):
            self.assertNotEqual(kind,'supported-disjunction');seen.add(kind)
            return original(engine,constraints,kind)
        for f,t in [(case(n),None) for n in IDS]+[trap(False),trap(True)]:
            if t is None:t=tiny_table(f)[0]
            old=_solve(t,f['physics'],f['upper_witness'],None,8,False,finite_lookup=True)
            with patch.object(Engine,'feasible',feasible):
                new=_solve(t,f['physics'],f['upper_witness'],None,8,False,finite_lookup=True,incumbent_certificate=True)
            self.assertEqual(semantics(new),semantics(old));self.assertNotIn('unknown',new['status'])
            self.assertEqual(new['incumbent_certificate']['status'],'VERIFIED_NONEMPTY_ONLY')
        for name in ('supported-J-better','supported-J-face','primary-attainment','supported-primary-face-Q-better','supported-primary-face-Q-face','joint-attainment','attained-H-better','attained-H-face','attained-Pi-0-better','attained-Pi-0-face','attained-full-key'):self.assertIn(name,seen)

    def test_certificate_failure_prevents_all_search_and_does_not_fix_optimization(self):
        f=case('repeated_C_S_C');t,m,x,y,base=fixture_model(f)
        cert=certify(m,x,y,t,f['physics'],f['upper_witness'],base)
        # Exact original root identity is unchanged; certificate assignments are
        # data only, never appended to any constraint group or objective.
        self.assertEqual(len(base),cert['assertions'])
        self.assertTrue(all(z3.eq(a,b) for a,b in zip(base,m.G+x['P']+y['P']+y['strict'])))
        before=(x['J'],x['Q'],y['J'],m.H,*m.choices)
        certify(m,x,y,t,f['physics'],f['upper_witness'],base)
        self.assertTrue(all(z3.eq(a,b) for a,b in zip(before,(x['J'],x['Q'],y['J'],m.H,*m.choices))))
        with patch('incumbent_model_certificate.certify',side_effect=ValueError('bad certificate')),patch.object(Engine,'feasible',side_effect=AssertionError('no fallback')),patch.object(Engine,'minimum',side_effect=AssertionError('no optimization')):
            result=_solve(t,f['physics'],f['upper_witness'],None,8,False,finite_lookup=True,incumbent_certificate=True)
        self.assertEqual(result['status'],'unknown_resource_or_solver')
