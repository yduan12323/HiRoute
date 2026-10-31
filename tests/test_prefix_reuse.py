"""Exact prefix reuse versus cold plan propagation, including lifted witnesses."""
from dataclasses import FrozenInstanceError
from fractions import Fraction as F
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from hiroute.contracts import ProblemSnapshot, SolverConfig
from hiroute.exact import search
from hiroute.exact.interval import Interval
from hiroute.exact.pipeline import initial_piece, replay_chain
from hiroute_ref.cli import snapshot_case
from hiroute_ref.model import normalize_case, replay_witness

ROOT = Path(__file__).resolve().parents[1]


def config(method):
    return SolverConfig(method,'none','bounded_time_cut_v2','none','none','none',
                        'full_lexicographic_J_Q_H_Pi')


def raw_case():
    raw=json.loads((ROOT/'tests/r0/c01_zero_stop_snapshot.json').read_text())
    raw.update(initial_energy_kwh='2',capacity_kwh='5',stop_penalty_s='0',
               candidate_order=['a','b'],site_capabilities={'a':['C'],'b':['C']},depth_limit=3,
               charging_curve=[['0','5','1','0']],directed_edges=[
                   dict(source=a,target=b,time_s='1',length_m='1',edge_id=a+b)
                   for a,b in [('o','a'),('a','b'),('b','a'),('a','z'),('b','z')]])
    return raw


def cold(cache, plan, steps):
    # Test-only old implementation: reset to the exact same root for each plan.
    return search.execute_exact_plan(cache.families[()],steps)


def math_result(result):
    return tuple(result.get(k) for k in ('status','key','primary_infimum','primary_value','secondary_infimum'))


class PrefixReuseTests(unittest.TestCase):
    def compare(self, raw, frozen_expected=None):
        snapshot=ProblemSnapshot.from_dict(raw)
        results={}
        for method in ('flat','flat_bb','hier'):
            with self.subTest(method=method):
                with patch.object(search._PlanPrefixCache,'propagate',cold):
                    expected=search.solve_snapshot(snapshot,config(method),observer='detailed_trace')
                actual=search.solve_snapshot(snapshot,config(method),observer='detailed_trace')
                results[method]=actual
                self.assertEqual(math_result(actual),math_result(expected))
                self.assertEqual(actual['observer']['trace'],expected['observer']['trace'])
                self.assertEqual(actual.get('hierarchy_metrics'),expected.get('hierarchy_metrics'))
                if actual['status']=='attained_optimum':
                    self.assertEqual(actual['replay'],expected['replay'])
                    self.assertEqual(actual['legs'],expected['legs'])
                    charges=[oe-ie for effect,_,ie,_,oe,_ in actual['replay']['trace'] if effect in ('C','CS')]
                    source,_=snapshot_case(raw)
                    physical=replay_witness(normalize_case(source),actual['plan'],charges)
                    self.assertEqual(physical['lex_key'],actual['key'])
                    self.assertTrue(all(q>0 for q in charges))
                if frozen_expected is not None:
                    self.assertEqual(actual['status'],frozen_expected['status'])
                    self.assertIsNone(actual.get('key'))
                    for field in ('primary_infimum','secondary_infimum'):
                        if field in frozen_expected:
                            self.assertEqual(actual[field],F(frozen_expected[field]))
                    if 'J' in frozen_expected:
                        self.assertEqual(actual['primary_value'],F(frozen_expected['J']))
                        self.assertEqual(actual['primary_infimum'],F(frozen_expected['J']))
        for method,result in results.items():
            with self.subTest(parity_method=method):
                self.assertEqual(math_result(result),math_result(results['flat']))
        return actual

    def test_shared_and_repeated_site_prefixes_match_every_cold_plan(self):
        result=self.compare(raw_case())
        metrics=result['observer']['prefix_cache']
        self.assertGreater(metrics['hits'],0)
        self.assertEqual(metrics['entries'],metrics['misses']+1)

    def test_different_action_history_schedule_and_snapshot_are_not_shared(self):
        raw=raw_case()
        raw.update(initial_energy_kwh='1',initial_remaining_schedule=1,
                   schedule={'a':'10','b':'20','D':'3'},
                   site_capabilities={'a':['C','S','CS'],'b':['C','S','CS']},depth_limit=2)
        self.compare(raw)
        # Same sites/actions, distinct departure/window and energy/curve context.
        shifted=dict(raw,departure_time_s='-3600',schedule={'a':'-3590','b':'-3580','D':'3'})
        self.compare(shifted)
        self.compare(dict(raw,initial_energy_kwh='3',charging_curve=[['0','5','2','0']]))

    def test_cached_family_and_witness_ancestry_survive_sibling_and_replay(self):
        snap=ProblemSnapshot.from_dict(raw_case())
        initial=initial_piece(Interval(F(2),F(2)),anchor='o',remaining_schedule=0,rho=-2)
        cache=search._PlanPrefixCache((initial,))
        prefix=(('a','C'),)
        steps,_=search._plan_steps(snap,prefix,{})
        cache.propagate(prefix,steps)
        family=cache.families[prefix]
        self.assertEqual(family,search.execute_exact_plan((initial,),steps[:-1]))
        before=tuple((p.domain,p.slope,p.intercept,p.attained,p.rho,p.prefix,p.state_key,p.witness_lifter)
                     for p in family)
        sibling=prefix+(('b','C'),)
        steps,_=search._plan_steps(snap,sibling,{})
        cache.propagate(sibling,steps)
        self.assertEqual(cache.families[sibling],search.execute_exact_plan((initial,),steps[:-1]))
        for p in family:
            energy=(p.domain.lo+p.domain.hi)/2
            if not p.domain.contains(energy): continue
            # Unattained cuts have feasible witnesses strictly above the cut.
            witness=p.witness_lifter(energy,p.cut_time_at(energy)+1)
            self.assertEqual(replay_chain(witness)[2],prefix)
        self.assertIs(cache.families[prefix],family)
        self.assertEqual(before,tuple((p.domain,p.slope,p.intercept,p.attained,p.rho,p.prefix,p.state_key,p.witness_lifter)
                                      for p in family))
        with self.assertRaises(FrozenInstanceError):
            family[0].rho=F(99)
        self.assertNotIn((('b','C'),('a','C')),cache.families)

    def test_empty_prefix_is_cached_and_does_not_poison_other_histories(self):
        raw=raw_case();raw.update(initial_energy_kwh='0')
        result=self.compare(raw)
        self.assertEqual(result['status'],'infeasible')
        self.assertGreater(result['observer']['prefix_cache']['hits'],0)

    def test_primary_and_secondary_unattainment_are_preserved(self):
        frozen=json.loads((ROOT/'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        for c in (frozen[5],frozen[6]):
            raw=raw_case()
            raw.update(origin=c['origin'],destination=c['destination'],departure_time_s=c['start_time_s'],
                       initial_energy_kwh=c['initial_energy_kwh'],capacity_kwh=c['capacity_kwh'],
                       minimum_energy_kwh=c['minimum_energy_kwh'],destination_reserve_kwh=c['reserve_kwh'],
                       stop_overhead_s=c['overhead_s'],stop_penalty_s=c['lambda_stop_s'],
                       consumption_kwh_per_m=c['consumption_kwh_per_m'],charging_curve=c['charging_segments'],
                       candidate_order=list(c['sites']),site_capabilities=c['sites'],depth_limit=c['H_ref'],
                       initial_remaining_schedule=1,schedule=c['schedule'],directed_edges=c['edges'])
            self.compare(raw,frozen_expected=c['independent_expected'])


if __name__=='__main__':
    unittest.main()
