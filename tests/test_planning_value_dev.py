"""Tiny policy/replay checks and mocked accounting; never load a real graph."""
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import planning_value_policy as policy
import run_planning_value_dev as stage
from hiroute.contracts import ProblemSnapshot
from hiroute.exact.road_index import RoadIndex
from hiroute.exact.scale import solve_scale


def snapshot():
    cases=json.loads((ROOT/'comparison/compact_cases.json').read_text())['cases']
    base=ProblemSnapshot.from_dict(next(c['snapshot'] for c in cases if c['id']=='one_charge'))
    return replace(base,schedule={'a':'0','b':'100','D':'3'},initial_remaining_schedule=1,
                   site_capabilities={'c':('C','S','CS')})


class PolicyAdapter(unittest.TestCase):
    def test_worker_dispatch_and_no_activity_receipts_with_tiny_index(self):
        original=snapshot()
        class TinyNative(RoadIndex):
            def __init__(self,*args,**kwargs):
                super().__init__(original.directed_edges,check=kwargs['check'])
                self.exposed_nodes=('o','c','z')
            def close(self):pass
        query=dict(query_id='WD01',great_circle_m=0,eligible_unique_anchors=1,
            scenario_eligible_counts={'schedule':1},
            endpoints={k:dict(site_id=v,access_node=v) for k,v in [('origin','o'),('destination','z')]},
            scenario_candidate_domains={'schedule':{'1':[dict(site_id='c',access_node='c',capabilities=['C','S','CS'])]}})
        config=dict(planning_policy='separated_no_overlap',implementation={},
            resources=dict(host_headroom_bytes=0,query_extra_memory_bytes=8*1024**3,
                           pilot_method_query_wall_s=120,main_threshold_s=60),
            selection=dict(candidate_counts=[1],scenarios=['schedule'],ods=[dict(query_id='WD01')],
                           domain_claim='tiny policy fixture'),
            pilot_matrix=[dict(N=1,query_ids=['WD01'],scenarios=['schedule'])])
        for caps,expected in [({'c':('C','S','CS')},'attained_optimum'),
                              ({'c':('CS',)},'policy_no_eligible_activity')]:
            with self.subTest(capabilities=caps), tempfile.TemporaryDirectory() as directory:
                out=Path(directory)
                stage.pilot.atomic(out/'config.json',config)
                stage.pilot.atomic(out/'preflight.json',dict(queries=[query]))
                args=SimpleNamespace(config=str(out/'config.json'),preflight=str(out/'preflight.json'),
                    query='WD01',n=1,scenario='schedule',method='flat_bb_strong',diagnostic=False,
                    ablation=False,no_bound=False,solve_limit_seconds=None,graph_tsv='tiny',
                    native_cache=str(out/'cache'),output=str(out/'row.json'))
                with patch('hiroute.exact.road_index.NativeRoadIndex',TinyNative),\
                     patch.object(stage.pilot,'bind_snapshot',return_value=replace(original,site_capabilities=caps)):
                    stage.pilot.worker(args)
                row=stage.load(out/'row.json')
                self.assertEqual(row['status'],expected)
                if expected=='attained_optimum':
                    self.assertEqual(row['feasible_key'][:3],['30','3',2])
                    self.assertTrue(row['witness']['original_joint_model_verified'])
                    checkpoint=stage.load(out/'row.incumbent.json')
                    self.assertTrue(checkpoint['verified']['policy_verified'])
                else:
                    self.assertNotIn('feasible_key',row)
                    self.assertEqual(row['mathematical_status'],'unknown')

    def test_exact_tiny_policy_keys_and_replay_in_original_model(self):
        original=snapshot()
        for name,expected in [('separated_no_overlap',(F(30),F(3),2)),
                              ('activity_first_fixed_site',(F(16),F(3),1))]:
            with self.subTest(policy=name):
                provider=RoadIndex(original.directed_edges)
                restricted,info=policy.adapt_snapshot(original,name,provider)
                result=solve_scale(restricted,method='flat_bb_strong',provider=provider,time_limit_s=5)
                self.assertEqual(result['status'],'attained_optimum')
                self.assertEqual(result['key'][:3],expected)
                self.assertEqual(result['depth_contract']['mode'],'unrestricted')
                verified=policy.verify_policy_witness(original,restricted,result,direct_length_m='4')
                self.assertTrue(verified['original_joint_model_verified'])
                self.assertEqual(verified['charging_duration_s'],3)
                self.assertEqual(verified['signed_distance_delta_from_direct_fastest_m'],-1)
                self.assertEqual(verified['charging_activity_overlap_s'],
                                 0 if name=='separated_no_overlap' else 3)
                if name=='separated_no_overlap':
                    self.assertEqual(result['plan'],(('c','C'),('c','S')))
                else:
                    self.assertEqual(info['selected_activity_site'],'c')
                    damaged={**result,'replay':dict(result['replay'])}
                    trace=list(damaged['replay']['trace']);event=list(trace[1]);event[4]=event[2]
                    trace[1]=event;damaged['replay']['trace']=trace
                    with self.assertRaises(ValueError):policy.verify_policy_witness(original,restricted,damaged)

    def test_order_capabilities_and_unchanged_physical_fields(self):
        original=replace(snapshot(),candidate_order=('z_site','a_site','b_site'),
                         site_capabilities={'z_site':('CS',),'a_site':('S','C','CS'),'b_site':('C',)})
        restricted,info=policy.adapt_snapshot(original,'separated_no_overlap',None)
        self.assertEqual(restricted.candidate_order,('a_site','b_site'))
        self.assertEqual(restricted.site_capabilities,{'a_site':('S','C'),'b_site':('C',)})
        self.assertEqual(info['original_candidate_count'],3)
        self.assertEqual(info['effective_candidate_count'],2)
        before,after=original.to_dict(),restricted.to_dict()
        for key in ('candidate_order','site_capabilities','semantic_problem_id'):
            before.pop(key);after.pop(key)
        self.assertEqual(before,after)
        cs_only=replace(snapshot(),site_capabilities={'c':('CS',)})
        restricted,info=policy.adapt_snapshot(cs_only,'separated_no_overlap',None)
        self.assertIsNone(restricted)
        self.assertEqual(info['effective_action_count'],0)

    def test_activity_choice_time_only_no_energy_filter_or_fallback(self):
        class Times:
            def distances_from(self,source,weight):
                self.assert_weight(weight);return {'a':F(2),'b':F(3),'c':F(1)}
            def distances_to(self,target,weight):
                self.assert_weight(weight);return {'a':F(1),'b':F(1),'c':F(1)}
            @staticmethod
            def assert_weight(weight):
                if weight!='time_s':raise AssertionError('energy/length ranking input')
        original=replace(snapshot(),candidate_order=('c','b','a'),
            site_capabilities={'c':('C',),'b':('CS',),'a':('S',)})
        for energy in ('0','3'):
            restricted,info=policy.adapt_snapshot(replace(original,initial_energy_kwh=energy),
                                                 'activity_first_fixed_site',Times())
            self.assertEqual(info['selected_activity_site'],'a')
            self.assertEqual(restricted.site_capabilities,{'c':('C',),'a':('S',)})
            self.assertFalse(info['selection_uses_energy_or_solver_results'])


class StageAccounting(unittest.TestCase):
    def setUp(self):
        self.spec,self.definition,_=stage.recipe(ROOT/'configs/planning_value_dev_gate.json')

    def test_inclusive_pair_and_cleanup_reservation(self):
        self.assertTrue(stage.admission(self.spec,740))
        self.assertFalse(stage.admission(self.spec,740.001))
        constrained={**self.spec,'original_cap_cpu_s':self.spec['carried_cpu_s']+900+1800}
        self.assertTrue(stage.admission(constrained,440))
        self.assertFalse(stage.admission(constrained,440.001))

    def prepare_mock(self,out):
        stage.pilot.atomic(out/'preparation.json',dict(spec=self.spec,definition=self.definition,
            source={},configs={},inputs={},input_stat={}))

    def execute_mock(self,out,worker):
        with patch.object(stage,'recipe',return_value=(self.spec,self.definition,{})),\
             patch.object(stage.common,'source_identity',return_value={}),\
             patch.object(stage.time,'process_time',return_value=0),\
             patch.object(stage,'run_worker',side_effect=worker) as launch:
            stage.execute(SimpleNamespace(output_root=str(out),config='mock'))
            return launch.call_count

    def worker(self,cost,fail=False):
        calls=[]
        def run(out,prepared,slot,total,guard):
            calls.append(stage.row_id(slot))
            prior=(len(calls)-1)*(cost+1)
            with patch.object(stage.time,'process_time',return_value=5):
                self.assertTrue(guard(1974-prior))  #5+1974+120=2099
                self.assertFalse(guard(1975-prior))
            (out/'attempts'/stage.row_id(slot)).mkdir(parents=True,exist_ok=True)
            return dict(status='worker_error' if fail else 'time_limit',mathematical_status='unknown',
                        worker_cpu_s=cost,supervisor_cpu_s=cost)
        return run

    def test_eight_slots_order_live_controller_cost_and_terminal_guard(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.prepare_mock(out)
            self.assertEqual(self.execute_mock(out,self.worker(2)),8)
            rows=stage.load(out/'results.json')['rows']
            self.assertEqual([stage.row_id(r) for r in rows],
                             [stage.row_id(r) for r in self.definition['rows']])
            self.assertEqual(stage.load(out/'status.json')['worker_cpu_charged_s'],24)
            self.assertEqual(stage.load(out/'status.json')['state'],'complete')
            with self.assertRaisesRegex(RuntimeError,'inspect instead'):
                self.execute_mock(out,lambda *_:self.fail('duplicate execution'))

    def test_budget_suffix_keeps_denominator_and_no_fresh_late_pair(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.prepare_mock(out)
            self.assertEqual(self.execute_mock(out,self.worker(300)),4)
            rows=stage.load(out/'results.json')['rows']
            self.assertEqual(len(rows),8)
            self.assertEqual([r['status'] for r in rows],['time_limit']*4+['budget_unrun']*4)
            self.assertEqual(stage.load(out/'status.json')['state'],'budget_stopped')
            self.assertEqual(stage.load(out/'status.json')['inclusive_gate_charged_cpu_s'],2104)

    def test_failure_receipt_charged_before_pause_and_never_replayed(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.prepare_mock(out)
            with self.assertRaisesRegex(RuntimeError,'unexpected worker outcome'):
                self.execute_mock(out,self.worker(2,fail=True))
            rows=stage.load(out/'results.json')['rows']
            self.assertEqual([r['status'] for r in rows],['worker_error']+['not_run']*7)
            self.assertEqual(stage.load(out/'status.json')['worker_cpu_charged_s'],3)
            with self.assertRaisesRegex(RuntimeError,'inspect instead'):
                self.execute_mock(out,lambda *_:self.fail('retry'))

    def test_paused_boundary_carries_controller_across_resume(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.prepare_mock(out)
            stage.pilot.atomic(out/'status.json',dict(state='paused_requested',total_controller_cpu_s=5.1))
            def worker(out,prepared,slot,total,guard):
                self.assertTrue(guard(1971))  #ceil(5.1)+2+1971+120=2099
                self.assertFalse(guard(1972))
                (out/'attempts'/stage.row_id(slot)).mkdir(parents=True,exist_ok=True)
                return dict(status='time_limit',mathematical_status='unknown',worker_cpu_s=0,supervisor_cpu_s=0)
            # Only inspect first admission/worker guard: subsequent workers have
            # additional charged tails, so deliberately pause via a clear error.
            def once(*args):
                if (out/'attempts').exists():raise RuntimeError('mock boundary')
                return worker(*args)
            with self.assertRaisesRegex(RuntimeError,'mock boundary'):
                self.execute_mock(out,once)
            self.assertEqual(stage.load(out/'status.json')['total_controller_cpu_s'],8)
            self.assertEqual(stage.load(out/'status.json')['worker_cpu_charged_s'],1)


if __name__=='__main__':unittest.main()
