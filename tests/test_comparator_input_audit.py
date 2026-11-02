import builtins
import copy
from fractions import Fraction as F
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
from audit_comparator_input import audit, conditional_depths, digest, footprint


def fixture(root):
    def write(name,value):
        p=root/name;p.write_text(json.dumps(value));return str(p)
    graph=write('graph',{'fixture':'not a road graph: audit hashes, never routes'})
    names=['c'+str(i) for i in range(64)]
    rows=[dict(site_id=s,access_node='r'+s,capabilities=['C']) for s in names]
    q=dict(query_id='fixture',endpoints={k:dict(site_id=k,access_node='r'+k)
          for k in ('origin','destination')},scenario_candidate_domains={
          'energy_only':{'64':rows},'schedule':{'64':rows[:-1]}})
    config=dict(model=dict(stop_overhead_s='1',stop_penalty_s='1',charging_curve=[[0,1,1,0]]*3),
        selection=dict(scenarios=['energy_only','schedule'],schedule_recipe=dict(duration_s='3')))
    c=write('config',config);m=write('manifest',dict(config=config,queries=[q]))
    prep=dict(inputs={'graph':graph},input_sha256={'graph':digest(graph)},
        configs={'18':dict(config=c,config_sha256=digest(c),preflight=m,preflight_sha256=digest(m))})
    import hashlib
    domain=hashlib.sha256(json.dumps(dict(endpoints=q['endpoints'],candidates=rows),
                         sort_keys=True,separators=(',',':')).encode()).hexdigest()
    records=[]
    for scenario,method in itertools.product(config['selection']['scenarios'],('flat_bb_strong','scale')):
        records.append(dict(query_id='fixture',initial_energy_kwh='18',scenario=scenario,
            method=method,N=64,status='input_domain_unavailable' if scenario=='schedule' else 'time_limit',
            candidate_domain_sha256=domain,feasible_key=['100','1',1,[['c0','C']]],
            witness={'physical_verified':True},direct_selected_time_s='10'))
    result=dict(preparation={'input_sha256':prep['input_sha256']},rows=records)
    return write('preparation',prep),write('results',result),prep,result


class AuditTests(unittest.TestCase):
    def test_equality_and_empty_prefix_preserve_complete_floor(self):
        # An equality plan has direct drive7, pending activity3 and2*(h+lambda)=10.
        b=conditional_depths('20','2','3','7','3')
        self.assertEqual(b,dict(status='conditional_not_certified',basic=4,road=2,road_activity=2))
        self.assertEqual(conditional_depths('7','2','3','7')['road'],0)

    def test_repeated_charging_visits_are_not_capped_by_number_of_sites(self):
        b=conditional_depths('100','1','0','0')
        f=footprint(['c'],{'c':['C']},{'o':'o','c':'c','z':'z'},'o','z',b['road_activity'],3)
        self.assertEqual(b['road_activity'],100)
        self.assertEqual(f['current_movement_pair_predicate_builds'],200)
        self.assertEqual(f['proposed_direct_leg_lookups'],101)

    def test_missing_upper_or_direct_time_never_becomes_infeasibility_or_hidden_H6(self):
        b=conditional_depths(None,'1','0','7')
        self.assertEqual(b['status'],'unknown_no_attained_witness')
        self.assertIsNone(b['basic'])
        b=conditional_depths('100','1','0')
        self.assertEqual(b['basic'],100);self.assertIsNone(b['road'])

    def test_nonexact_and_inconsistent_inputs_fail_closed(self):
        for value in (True,0.5,'0.5','nan','1/0'):
            with self.subTest(value=value),self.assertRaises((TypeError,ValueError)):
                conditional_depths(value,'1','0')
        for args in [('1','0','0'),('1','1','-1'),('4','1','0','3','2')]:
            with self.subTest(args=args),self.assertRaises(ValueError):conditional_depths(*args)

    def test_alias_projection_preserves_Site_actions_direction_and_terminal_pairs(self):
        f=footprint(['a','b','c'],{'a':['C'],'b':['S'],'c':['C','S','CS']},
                    {'o':'o','a':'p','b':'p','c':'q','z':'z'},'o','z',7,3)
        self.assertEqual((f['sites'],f['actions']),(3,5))
        self.assertEqual((f['required_physical_pair_records'],f['zero_diagonal_records']),(9,2))
        self.assertEqual(f['nontrivial_directed_pairs'],7)
        self.assertEqual(f['current_movement_pair_predicate_builds'],140)

    def test_depth_relaxation_on_repeated_histories_with_CS_overlap(self):
        # Directed times are abs coordinates plus1 for distinct nodes: a metric.
        pos={'o':0,'a':2,'b':5,'z':8}
        dt=lambda a,b:F(0) if a==b else F(abs(pos[a]-pos[b])+1)
        tau=dt('o','z');h,lam,D=F(2),F(3),F(4)
        actions=list(itertools.product(('a','b'),('C','S','CS')))
        tested=0
        for H in range(1,5):
            for plan in itertools.product(actions,repeat=H):
                if sum(e!='C' for _,e in plan)!=1:continue
                anchor='o';time=F(0)
                for site,effect in plan:
                    time+=dt(anchor,site)+h
                    time+=F(3) if effect=='C' else D if effect=='S' else max(D,F(3))
                    anchor=site
                U=time+dt(anchor,'z')+lam*H
                bounds=conditional_depths(str(U),str(h),str(lam),str(tau),str(D))
                self.assertLessEqual(H,bounds['road_activity']);tested+=1
        self.assertGreater(tested,100)

    def test_full_fixture_audit_imports_no_solver_and_retains_unavailable_denominator(self):
        original=builtins.__import__
        def block(name,*args,**kwargs):
            if name.split('.')[0] in ('hiroute','z3','compact_smt','tiny_smt','timecut5'):
                raise AssertionError('solver/internal import')
            return original(name,*args,**kwargs)
        with tempfile.TemporaryDirectory() as t:
            p,r,_,_=fixture(Path(t))
            spec=importlib.util.spec_from_file_location('isolated_audit',TOOLS/'audit_comparator_input.py')
            module=importlib.util.module_from_spec(spec)
            with patch('builtins.__import__',side_effect=block):
                spec.loader.exec_module(module);result=module.audit(p,r)
            self.assertEqual((result['query_cell_denominator'],result['historical_method_row_denominator']),(2,4))
            self.assertEqual((result['input_available_cells'],result['input_unavailable_cells']),(1,1))
            self.assertEqual(result['SMT_calls'],0)
            self.assertEqual(result['road_query_calls'],0)
            self.assertFalse(result['independent_optimality_claim'])
            self.assertFalse(result['cells'][0]['independent_upper_replay_performed'])

    def test_duplicate_cells_and_changed_inputs_are_rejected_before_forecast(self):
        with tempfile.TemporaryDirectory() as t:
            p,r,prep,result=fixture(Path(t))
            result['rows'].append(copy.deepcopy(result['rows'][0]));Path(r).write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'duplicate'):audit(p,r)
            result['rows'].pop();Path(r).write_text(json.dumps(result))
            Path(prep['inputs']['graph']).write_text('changed')
            with self.assertRaisesRegex(ValueError,'physical input changed'):audit(p,r)


if __name__=='__main__':unittest.main()
