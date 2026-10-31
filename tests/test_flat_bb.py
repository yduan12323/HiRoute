"""Fair singleton B&B regressions; physical replay is not full REF optimization."""
from fractions import Fraction as F
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from hiroute.contracts import ProblemSnapshot, SolverConfig
from hiroute.cli import _native_result
from hiroute.exact import search
from hiroute_ref.cli import snapshot_case
from hiroute_ref.model import normalize_case, replay_witness

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('flat', 'flat_bb', 'hier')


def config(method):
    return SolverConfig(method, 'none', 'bounded_time_cut_v2', 'none', 'none',
                        'none', 'full_lexicographic_J_Q_H_Pi')


def raw(**changes):
    result = json.loads((ROOT/'tests/r0/c01_zero_stop_snapshot.json').read_text())
    result.update(changes)
    return result


def edge(a, b, t=1, length=1):
    return dict(source=a, target=b, time_s=str(t), length_m=str(length), edge_id=a+'>'+b)


class FlatBBTests(unittest.TestCase):
    def parity(self, source):
        snap = ProblemSnapshot.from_dict(source)
        results = []
        for method in METHODS:
            with self.subTest(method=method):
                result = search.solve_snapshot(snap, config(method), observer='metrics')
                results.append(result)
                # Observer evidence is embedded directly in the public JSON.
                json.dumps(_native_result(snap, config(method), result, observer='metrics'))
                if result['status'] == 'attained_optimum':
                    charges = [oe-ie for effect, _, ie, _, oe, _ in result['replay']['trace']
                               if effect in ('C', 'CS')]
                    independent, _ = snapshot_case(source)
                    replay = replay_witness(normalize_case(independent), result['plan'], charges)
                    self.assertEqual(replay['lex_key'], result['key'])
        for field in ('status', 'key', 'primary_infimum', 'primary_value', 'secondary_infimum'):
            self.assertEqual([r.get(field) for r in results], [results[0].get(field)]*3)
        return results

    def test_zero_stop_infeasible_and_unreachable_actions(self):
        self.assertEqual(self.parity(raw())[1]['key'], (1, 0, 0, ()))
        source = raw(candidate_order=['u'], site_capabilities={'u':['C']},
                     charging_curve=[['0','10','1','0']], depth_limit=1)
        rows = self.parity(source)
        hm = rows[2]['observer']['search_metrics']
        self.assertEqual(hm['region_member_visits'], 1)
        self.assertEqual(hm['unreachable_member_visits'], 1)
        self.assertEqual(hm['coverage_member_scans'], 5)
        self.assertEqual(rows[1]['observer']['search_metrics']['unreachable_actions'], 1)
        self.assertEqual(self.parity(dict(source, directed_edges=[]))[1]['status'], 'infeasible')

    def test_terminal_infeasible_prefix_still_has_two_charge_continuation(self):
        source = raw(initial_energy_kwh='2', capacity_kwh='2',
            candidate_order=['a','b'], site_capabilities={'a':['C'],'b':['C']},
            charging_curve=[['0','2','1','0']], depth_limit=2,
            directed_edges=[edge('o','a',length=2),edge('a','b',length=2),edge('b','z',length=2)])
        self.assertEqual(self.parity(dict(source,depth_limit=1))[1]['status'], 'infeasible')
        rows = self.parity(source)
        self.assertEqual(rows[1]['plan'], (('a','C'),('b','C')))
        self.assertEqual(rows[1]['key'], (11,4,2,(('a','C'),('b','C'))))
        with patch.object(search, '_build_regions', side_effect=AssertionError('Flat-BB built a Region')):
            self.assertEqual(search.solve_snapshot(ProblemSnapshot.from_dict(source),config('flat_bb'))['key'],rows[0]['key'])

    def test_schedule_effects_completion_and_time_translation(self):
        source = raw(initial_energy_kwh='1', capacity_kwh='5', stop_penalty_s='0',
            candidate_order=['a','b'],site_capabilities={'a':['C','S','CS'],'b':['C']},
            charging_curve=[['0','5','1','0']],depth_limit=2,
            schedule={'a':'10','b':'20','D':'3'},initial_remaining_schedule=1,
            directed_edges=[edge('o','a'),edge('a','z'),edge('o','b'),edge('b','a')])
        for shift in (0,3600,-3600):
            shifted = dict(source,departure_time_s=str(shift),
                           schedule={'a':str(10+shift),'b':str(20+shift),'D':'3'})
            rows = self.parity(shifted)
            self.assertEqual(rows[1]['key'], (14,1,1,(('a','CS'),)))
            self.assertEqual(rows[1]['replay']['time'], 14+shift)
        rows = self.parity(dict(source, initial_remaining_schedule=0))
        self.assertEqual(rows[1]['plan'], (('a','C'),))
        self.assertGreater(rows[1]['observer']['search_metrics']['schedule_actions_skipped'], 0)
        self.assertEqual(self.parity(dict(source, initial_energy_kwh='3'))[1]['plan'], (('a','S'),))

    def test_equal_bound_keeps_better_secondary_key(self):
        source = raw(initial_energy_kwh='1',capacity_kwh='5',stop_penalty_s='0',
            candidate_order=['a','b'],site_capabilities={'a':['C'],'b':['C']},depth_limit=1,
            charging_curve=[['0','5','1','0']],directed_edges=[
                edge('o','a'),edge('a','z',length=3),edge('o','b',t=2),edge('b','z',t=2)])
        # Equal attained J=6; the later leaf b improves Q from 3 to 1.
        rows = self.parity(source)
        self.assertEqual(rows[1]['key'], (6,1,1,(('b','C'),)))
        # Separately isolate strict equality retention at the traversal boundary.
        # The real bound omits positive overhead, so a leaf at bound==U cannot
        # attain U in this fixture; nevertheless the contract retains it.
        source['directed_edges'][-2:] = [edge('o','b',t=3),edge('b','z',t=3)]
        for traversal in (search._flat_bb_plans,search._hierarchical_plans):
            seen=[]
            def evaluate(plan):
                seen.append(plan)
                return F(6) if plan else None
            metrics=traversal(ProblemSnapshot.from_dict(source),{},evaluate)
            self.assertIn((('b','C'),),seen)
            self.assertGreater(metrics['equality_nodes_retained'],0)

    def test_arithmetic_leaf_ties_match_actual_hier_heap_without_region_in_flat_bb(self):
        # Callback isolates traversal from numerical work; every bound ties.
        for n in range(1,9):
            sites = [str(i) for i in range(n)]
            source = raw(candidate_order=sites,site_capabilities={s:['C','S','CS'] for s in sites},
                charging_curve=[['0','10','1','0']],schedule={'a':'0','b':'100','D':'0'},
                initial_remaining_schedule=1,depth_limit=1,
                directed_edges=[e for s in sites for e in (edge('o',s),edge(s,'z'))])
            snap=ProblemSnapshot.from_dict(source)
            orders=[]
            for traversal in (search._flat_bb_plans,search._hierarchical_plans):
                seen=[]
                def evaluate(plan): seen.append(plan); return None
                traversal(snap,{},evaluate)
                orders.append(seen)
            self.assertEqual(*orders)

    def test_timeout_remains_unknown_in_public_contract(self):
        snapshot=ProblemSnapshot.from_dict(raw())
        for method in METHODS:
            ticks=iter((0,0,2))
            result=search.solve_snapshot(snapshot,config(method),time_limit_s=1,
                _clock=lambda:next(ticks,2),observer='metrics')
            self.assertEqual(result['status'],'time_limit')
            self.assertEqual(_native_result(snapshot,config(method),result)['mathematical_status'],'unknown')


class MechanismPreflightTests(unittest.TestCase):
    def preflight(self, source):
        preflight=runpy.run_path(str(ROOT/'tools/profile_small_cases.py'))['preflight_cases']
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cases.json'
            path.write_text(json.dumps(dict(base_snapshot=source,
                cases=[dict(case_id='tiny',source_kind='synthetic',overrides={})])))
            # Input preflight must never invoke an optimizer.
            with patch.object(search,'solve_snapshot',side_effect=AssertionError('preflight solved')):
                return preflight(path)

    def test_complete_input_contract_accepts_zero_stop(self):
        self.assertEqual(self.preflight(raw()),['tiny'])

    def test_m07_partial_curve_is_rejected_before_numerical_work(self):
        with self.assertRaisesRegex(ValueError,'cover the full battery domain'):
            self.preflight(raw(candidate_order=['a'],site_capabilities={'a':['C']},
                charging_curve=[['0','5','1','0']],capacity_kwh='10',depth_limit=3))

    def test_numeric_structure_and_diagnostic_domain_are_checked(self):
        for source,error in ((raw(initial_energy_kwh=10.0),TypeError),
                (raw(candidate_order=['a'],site_capabilities={'a':['X']}),ValueError),
                (raw(depth_limit=4),ValueError)):
            with self.subTest(source=source),self.assertRaises(error):
                self.preflight(source)


if __name__ == '__main__':
    unittest.main()
