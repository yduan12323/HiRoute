"""Exact external-model tests; no archived dataset or real query."""
import copy
from fractions import Fraction as F
import importlib.abc
import json
from pathlib import Path
import sys
import unittest

import z3
from tiny_smt import Engine, Unsupported, branches, canonical_legs, fraction, replay, solve
from run_gate import semantics

CASES=json.loads(Path(__file__).with_name('cases.json').read_text())['cases']


class GateTests(unittest.TestCase):
    def test_analytic_cases_solve_with_all_hiroute_imports_blocked(self):
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.startswith('hiroute'):
                    raise AssertionError('independent model imported '+fullname)
        blocker=Block();sys.meta_path.insert(0,blocker)
        try:
            for case in CASES:
                with self.subTest(case=case['id']):
                    result=solve(case['snapshot'])
                    self.assertEqual(semantics(result),case['expected'])
                    self.assertLessEqual(result['linear_branches'],128)
                    if result['status']=='attained_optimum':
                        w=result['witness']
                        self.assertEqual(replay(case['snapshot'],w['plan'],w['charges'],w['initial_wait'])['key'],result['key'])
        finally:
            sys.meta_path.remove(blocker)

    def test_strict_empty_branch_is_discarded_before_cheap_closed_optimum(self):
        case=next(c['snapshot'] for c in CASES if c['id']=='strict_empty_full_battery_branch')
        engine=Engine();saw_closed=False
        for branch in branches(case,canonical_legs(case)):
            if engine.feasible(branch['P'],'closed') is not None:
                saw_closed=True
                self.assertIsNone(engine.feasible(branch['P']+branch['strict'],'strict'))
        self.assertTrue(saw_closed)
        self.assertEqual(solve(case)['status'],'infeasible')

    def test_canonical_nodes_then_edges_not_shortest_length_and_directedness(self):
        snapshot=dict(origin='o',destination='z',candidate_order=[],directed_edges=[
            dict(source=a,target=b,time_s='1',length_m=str(d),edge_id=i)
            for a,b,d,i in [('o','x',5,'z'),('o','x',7,'a'),('x','z',5,'xz'),
                            ('o','y',1,'oy'),('y','z',1,'yz')]])
        legs=canonical_legs(snapshot)
        self.assertEqual(legs['o','z'],(F(2),F(12),('o','x','z'),('a','xz')))
        self.assertNotIn(('z','o'),legs)

    def test_replay_rejects_zero_charge_and_wrong_energy(self):
        case=next(c['snapshot'] for c in CASES if c['id']=='one_charge')
        for charge in (0,1,4):
            with self.subTest(charge=charge),self.assertRaises(ValueError):
                replay(case,(('c','C'),),(F(charge),))

    def test_full_key_prefers_fewer_stops_on_same_primary_and_charge_face(self):
        s=copy.deepcopy(next(c['snapshot'] for c in CASES if c['id']=='one_charge'))
        s.update(depth_limit=2,stop_penalty_s='0',initial_remaining_schedule=1,
            schedule=dict(a='100',b='200',D='1'),site_capabilities={'c':['C','S','CS']})
        result=solve(s)
        self.assertEqual(result['key'],(F(102),F(3),1,(('c','CS'),)))
        two=replay(s,(('c','C'),('c','S')),(F(3),))['key']
        self.assertEqual(two[:2],result['key'][:2])
        self.assertEqual(two[2],2)

    def test_integer_and_rational_bounds_never_round_or_accept_infinity(self):
        self.assertEqual(fraction(z3.IntVal(16)),F(16))
        self.assertEqual(fraction(z3.RealVal('1/3')),F(1,3))
        with self.assertRaises(Exception):fraction(z3.Real('unbounded'))

    def test_explosion_limits_and_invalid_inputs_fail_before_enumeration(self):
        s=copy.deepcopy(CASES[1]['snapshot']);s['depth_limit']=3
        with self.assertRaises(Unsupported):solve(s)
        s=copy.deepcopy(CASES[1]['snapshot']);s['site_capabilities']['c']=['C']*100
        with self.assertRaises(ValueError):solve(s)
        s=copy.deepcopy(CASES[1]['snapshot']);s['directed_edges']*=5
        with self.assertRaises(Unsupported):solve(s)


if __name__=='__main__':unittest.main()
