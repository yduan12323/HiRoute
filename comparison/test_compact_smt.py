import copy
from fractions import Fraction as F
import importlib.abc
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from compact_smt import Encoding, MixedEngine, solve
from run_gate import semantics
from tiny_smt import Unsupported, canonical_legs, real, replay

CASES=json.loads(Path(__file__).with_name('compact_cases.json').read_text())['cases']


def fixture(name):return copy.deepcopy(next(c for c in CASES if c['id']==name))


def encoded(case):
    s,w=case['snapshot'],case['upper_witness']
    U=replay(s,w['plan'],w['charges'],w['initial_wait'])['key'][0]
    H=int(U//(F(s['stop_overhead_s'])+F(s['stop_penalty_s'])))
    model=Encoding(s,H,U,canonical_legs(s))
    return model,model.state_copy('test_objective'),model.state_copy('test_support')


class CompactTests(unittest.TestCase):
    def test_analytic_cases_without_hiroute_imports(self):
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,path=None,target=None):
                if fullname.startswith('hiroute'):raise AssertionError('internal optimizer import')
        blocker=Block();sys.meta_path.insert(0,blocker)
        try:
            for case in CASES:
                with self.subTest(case=case['id']):
                    result=solve(case['snapshot'],case['upper_witness'])
                    self.assertEqual(semantics(result),case['expected'])
                    self.assertEqual(result['explicit_plan_enumerations'],0)
                    if result['status']=='attained_optimum':
                        w=result['witness'];self.assertEqual(replay(case['snapshot'],w['plan'],w['charges'],w['initial_wait'])['key'],result['key'])
        finally:sys.meta_path.remove(blocker)

    def test_closing_the_disjunction_without_support_invents_a_cheaper_plan(self):
        case=fixture('strict_empty_disjunct');m,x,y=encoded(case);e=MixedEngine()
        self.assertEqual(e.minimum(m.G+x['P'],x['J'],'unsafe-closed'),14)
        self.assertEqual(solve(case['snapshot'],case['upper_witness'])['key'][0],20)

    def test_secondary_support_must_itself_attain_primary(self):
        case=fixture('primary_face_support_trap');m,x,y=encoded(case);e=MixedEngine()
        supported=m.G+x['P']+y['P']+y['strict']+[x['J']==real(13)]
        self.assertEqual(e.minimum(supported,x['Q'],'unsafe-primary-support'),0)
        self.assertEqual(solve(case['snapshot'],case['upper_witness'])['key'][:2],(F(13),F(1)))

    def test_three_relevant_slots_do_not_call_the_plan_or_branch_enumerator(self):
        case=fixture('loose_valid_bound_H3')
        with patch('tiny_smt.plans',side_effect=AssertionError('plan enumeration')),patch('tiny_smt.branches',side_effect=AssertionError('branch enumeration')):
            result=solve(case['snapshot'],case['upper_witness'])
        self.assertEqual(result['derived_depth'],3)
        self.assertEqual(result['selector_count'],12)
        self.assertEqual(result['key'][2],1)

    def test_no_seed_is_unknown_and_large_bound_is_not_silently_capped(self):
        case=fixture('one_charge')
        self.assertEqual(solve(case['snapshot'])['status'],'unknown_no_attained_bound')
        case['upper_witness']['initial_wait']='1000'
        result=solve(case['snapshot'],case['upper_witness'])
        self.assertEqual(result['status'],'unsupported_relevant_depth')
        self.assertGreater(result['derived_depth'],6)
        self.assertNotIn('key',result)

    def test_invalid_upper_and_diagnostic_domain_are_rejected(self):
        case=fixture('one_charge');case['upper_witness']['charges']=['0']
        with self.assertRaises(ValueError):solve(case['snapshot'],case['upper_witness'])
        case=fixture('one_charge');case['snapshot']['depth_mode']='diagnostic_cap'
        with self.assertRaises(Unsupported):solve(case['snapshot'],case['upper_witness'])

    def test_complete_H2_face_uses_H_before_Pi_on_a_waiting_plateau(self):
        case=fixture('one_charge');s=case['snapshot']
        s.update(initial_energy_kwh='1',capacity_kwh='1',destination_reserve_kwh='0',
            stop_penalty_s='0',charging_curve=[['0','1','1/10','0']],
            initial_remaining_schedule=1,schedule=dict(a='11/5',b='10',D='1/10'),
            site_capabilities={'c':['C','S','CS']},directed_edges=[
                dict(source=a,target=b,time_s='1/10',length_m='1',edge_id=a+'>'+b)
                for a,b in [('o','c'),('c','z')]])
        upper=dict(plan=[['c','CS']],charges=['1'],initial_wait='0')
        result=solve(s,upper)
        self.assertEqual(result['derived_depth'],2)
        self.assertEqual(result['key'],(F(12,5),F(1),1,(('c','CS'),)))
        self.assertEqual(replay(s,(('c','C'),('c','S')),(F(1),))['key'][:2],result['key'][:2])

    def test_contract_versions_and_exact_input_types_are_not_silently_coerced(self):
        case=fixture('one_charge');case['snapshot']['numerical_contract_id']='floating'
        with self.assertRaises(Unsupported):solve(case['snapshot'],case['upper_witness'])
        for value in (0.5,True,'0.5'):
            case=fixture('one_charge');case['snapshot']['departure_time_s']=value
            with self.subTest(value=value),self.assertRaises(TypeError):solve(case['snapshot'],case['upper_witness'])

    def test_required_three_stops_cannot_be_replaced_by_a_diagnostic_H2(self):
        s=fixture('temporal_energy_equality')['snapshot']
        s.update(schedule=dict(a='0',b='100',D='1'),directed_edges=[
            dict(source=a,target=b,time_s='1',length_m=str(d),edge_id=a+'>'+b)
            for a,b,d in [('o','c',1),('c','s',1),('s','c',1),('c','z',2)]])
        upper=dict(plan=[['c','C'],['s','S'],['c','C']],charges=['2','2'],initial_wait='0')
        result=solve(s,upper)
        self.assertEqual(result['derived_depth'],3)
        self.assertEqual(result['key'],(F(42),F(4),3,(('c','C'),('s','S'),('c','C'))))
        self.assertEqual(replay(s,result['witness']['plan'],result['witness']['charges'],result['witness']['initial_wait'])['key'],result['key'])
        capped=Encoding(s,2,F(42),canonical_legs(s));x=capped.state_copy('H2')
        self.assertIsNone(MixedEngine().feasible(capped.G+x['P']+x['strict'],'H2-impossible'))
        # Compare only after the independent result and analytic key are fixed.
        from hiroute.contracts import ProblemSnapshot
        from hiroute.exact.scale import solve_scale
        for method in ('flat_bb_strong','scale'):
            with self.subTest(method=method):
                core=solve_scale(ProblemSnapshot.from_dict(s),method=method,time_limit_s=5)
                self.assertEqual(core['status'],'attained_optimum')
                self.assertEqual(core['key'],result['key'])
