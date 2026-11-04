import copy
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src'),str(ROOT/'comparison')]
from exact_leg_table import ExactLegTable
from exact_physical_adapter import solve,solve_real,table_relevant_depth,relevant_depth,Engine
from exact_physical_fixtures import case,tiny_table,IDS,semantics
from run_shared_leg_pilot import write_table,sample_pairs,verify_paths,physical,receipt,sha,header,freeze,compiler_preflight
from shared_pilot_budget import admit,total_spent,tree_usage,reap_group
from hiroute.exact.road_index import RoadIndex


class SharedPilotTests(unittest.TestCase):
    def test_streamed_table_keeps_ties_length_alias_terminal_and_directed_missing(self):
        rows=[dict(source=u,target=v,edge_id=e,time_s=str(t),length_m=str(L)) for u,v,e,t,L in
              [('o','a','oa',1,10),('a','z','az9',1,10),('a','z','az1',1,11),
               ('o','b','ob',1,1),('b','z','bz',1,1),('o','dead','od',1,1)]]
        p=RoadIndex(rows,leg_cache_size=0)
        f=dict(domain=dict(endpoints={'origin':{'access_node':'o'},'destination':{'access_node':'z'}},
             candidates=[dict(site_id='literal-a',access_node='a',capabilities=['C']),
                         dict(site_id='literal-dead',access_node='dead',capabilities=['S'])]),
             expected_input_sha256={'graph':'tiny'},physical_sources=['a','dead','o'],physical_targets=['a','dead','z'])
        h,s,t=header(f)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'table.json';self.assertEqual(write_table(p,h,s,t,path),9)
            table=ExactLegTable.from_bytes(path.read_bytes())
            self.assertEqual(table.pairs['o','z'].nodes,('o','a','z'))
            self.assertEqual(table.pairs['o','z'].edges,('oa','az1'))
            self.assertEqual(table.pairs['o','z'].length,21)
            self.assertFalse(table.pairs['dead','z'].reachable)
            self.assertEqual(table.pairs['a','a'].nodes,('a',))
            self.assertEqual(table.candidate_order,('literal-a','literal-dead'))
            raw={r['edge_id']:(r['source'],r['target'],r['time_s'],r['length_m']) for r in rows}
            checked=verify_paths(table,[('o','z'),('a','a'),('dead','z')],raw.__getitem__)
            self.assertEqual(len(checked),3)
            raw['az1']=('a','z','1','10')
            with self.assertRaises(ValueError):verify_paths(table,[('o','z')],raw.__getitem__)

    def test_output_quota_leaves_partial_not_complete_table(self):
        p=RoadIndex([dict(source='o',target='z',edge_id='e',time_s='1',length_m='1')])
        h=dict(schema='x')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'table.json'
            with self.assertRaises(RuntimeError):write_table(p,h,['o'],['z'],path,limit=10)
            self.assertFalse(path.exists());self.assertTrue(path.with_suffix('.partial').exists())

    def test_fixed_sample_covers_od_terminal_reciprocal_and_zero(self):
        s=['a','b','o'];t=['a','b','z'];a=sample_pairs(s,t,'o','z')
        self.assertEqual(a,sample_pairs(list(reversed(s)),list(reversed(t)),'o','z'))
        for pair in [('o','z'),('a','z'),('b','z'),('a','b'),('b','a'),('a','a')]:self.assertIn(pair,a)

    def test_complete_depth_subtracts_time_and_activity_retains_repeats_equality(self):
        f=case('repeated_C_S_C');table,_,_=tiny_table(f);w=f['upper_witness']
        H,u=table_relevant_depth(table,f['physics'],w)
        self.assertEqual(H,3);self.assertEqual(H,len(w['plan']))
        basic,_=relevant_depth(table,f['physics'],w);self.assertGreater(basic,H)
        h=F(f['physics']['stop_overhead_s'])+F(f['physics']['stop_penalty_s'])
        lower=table.pairs['o','z'].time+F(f['physics']['schedule']['D'])+H*h
        self.assertLessEqual(lower,u['key'][0])
        # Exactly the integer depth face remains legal; no strict-floor loss.
        f=case('empty_prefix_terminal');t,_,_=tiny_table(f)
        self.assertEqual(table_relevant_depth(t,f['physics'],f['upper_witness'])[0],0)
        f=case('alias_positive_charge');t,_,_=tiny_table(f);w=copy.deepcopy(f['upper_witness']);w['initial_wait']='100'
        self.assertGreater(table_relevant_depth(t,f['physics'],w)[0],6)

    def test_real_entry_preserves_tiny_guard_and_full_key_semantics(self):
        f=case('CS_overlap');t,_,_=tiny_table(f)
        with self.assertRaises(ValueError):solve(t,f['physics'],f['upper_witness'],time_limit_s=9)
        with self.assertRaises(ValueError):solve_real(t,f['physics'],f['upper_witness'],time_limit_s=121)
        r=solve_real(t,f['physics'],f['upper_witness'],time_limit_s=8)
        self.assertEqual(r['status'],'attained_optimum');self.assertEqual(r['key'][0],16)
        self.assertEqual(r['key'][3],(('p','CS'),));self.assertEqual(r['solver_check_timeout_cap_ms'],120000)
        self.assertFalse(r['road_selection_certified'])

    def test_timeout_profile_is_not_hidden_two_second_real_cap(self):
        with patch('exact_physical_adapter.time.monotonic',return_value=0):
            self.assertEqual(Engine(100).remaining(),2000)
            self.assertEqual(Engine(100,max_check_ms=120000).remaining(),100000)

    def test_table_depth_covers_eight_semantic_classes_and_integer_equality(self):
        for name in IDS:
            with self.subTest(name=name):
                f=case(name);t,_,_=tiny_table(f);w=f['upper_witness']
                H,_=table_relevant_depth(t,f['physics'],w);basic,_=relevant_depth(t,f['physics'],w)
                self.assertGreaterEqual(H,len(w['plan']));self.assertLessEqual(H,basic)
        f=case('alias_positive_charge');t,_,_=tiny_table(f);w=copy.deepcopy(f['upper_witness']);w['initial_wait']='3'
        H,u=table_relevant_depth(t,f['physics'],w)
        self.assertEqual((u['key'][0]-t.pairs['o','z'].time)/5,4);self.assertEqual(H,4)

    def test_real_profile_keeps_primary_secondary_nonattainment_and_temporal_equality(self):
        for name in ('primary_unattained','secondary_unattained','equality_attained'):
            with self.subTest(name=name):
                f=case(name);t,_,_=tiny_table(f)
                self.assertEqual(semantics(solve_real(t,f['physics'],f['upper_witness'],time_limit_s=8)),f['expected'])

    def test_freeze_rejects_substituted_query_before_any_road_load(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'frozen.json';p.write_text(json.dumps(dict(query_id='WD01',initial_energy_kwh='18',scenario='schedule',N=63)))
            with self.assertRaises(ValueError):freeze(SimpleNamespace(frozen_domain=p),dict(frozen_domain_sha256=sha(p)))

    def test_exact_schedule_recipe_is_not_rounded(self):
        f=case('CS_overlap');t,_,_=tiny_table(f)
        p=physical(f['physics'],t,dict(a_fraction_direct_time='2/5',b_fraction_direct_time='7/10',duration_s='2700'))
        self.assertEqual(p['schedule'],dict(a='4/5',b='7/5',D='2700'))
        self.assertEqual(p['charging_curve'],f['physics']['charging_curve'])

    def test_controller_chain_rejects_failed_missing_and_tampered_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);p=out/'generation.result.json';p.write_text('{"status":"COMPLETE","mode":"generation"}')
            record=dict(phase='generation',actual_child_returncode=0,guard_reason=None,terminal_sha256=sha(p))
            ledger=out/'budget.json';ledger.write_text(json.dumps(dict(records=[record])))
            self.assertEqual(receipt(out,'generation')['status'],'COMPLETE')
            p.write_text('{"status":"COMPLETE","mode":"generation","changed":true}')
            with self.assertRaises(ValueError):receipt(out,'generation')
            record['terminal_sha256']=sha(p);record['guard_reason']='wall_guard'
            ledger.write_text(json.dumps(dict(records=[record])))
            with self.assertRaises(ValueError):receipt(out,'generation')

    def test_inclusive_admission_carries_fixed_controller_and_previous_invocations(self):
        d=dict(active=None,state='admitted',cap_CPU_s=1200,carried_research_CPU_s='17720.070834741',
            original_cap_CPU_s=28800,allocations_CPU_s={'development':240,'generation':300,'optimization':240},
            phase_charged_CPU_s={'development':10,'generation':0,'optimization':0},fixed_precharge_CPU_s=120,
            fixed_precharge_phase='development',allowed_real_attempts={'generation':1,'optimization':1},records=[])
        self.assertEqual(total_spent(d),130);admit(d,'generation',300,270,300)
        d['phase_charged_CPU_s']['development']=10.000000000000002
        self.assertGreater(total_spent(d),130)
        with self.assertRaises(ValueError):admit(d,'development',120,100,60)
        d['records']=[dict(phase='generation')]
        with self.assertRaises(ValueError):admit(d,'generation',300,270,300)
        d['active']={'pid':123}
        with self.assertRaises(ValueError):admit(d,'optimization',240,120,120)

    def test_live_cpu_accounting_retains_waited_compiler_cpu(self):
        class Process:
            def __init__(self,values,children=()):self.values=values;self.group=children
            def cpu_times(self):return SimpleNamespace(**dict(zip(('user','system','children_user','children_system'),self.values)))
            def children(self,recursive=False):return list(self.group)
            def memory_info(self):return SimpleNamespace(rss=10)
        live=Process((3,1,2,1));root=Process((5,1,20,4),[live])
        cpu,rss=tree_usage(root);self.assertEqual(cpu,37);self.assertEqual(rss,20)

    def test_group_cleanup_runs_even_when_worker_root_already_exited(self):
        worker=SimpleNamespace(pid=123,wait=Mock(return_value=0),poll=Mock(return_value=0))
        with patch('shared_pilot_budget.os.killpg') as kill:
            reap_group(worker);kill.assert_called_once();self.assertEqual(kill.call_args.args[0],123)
        worker.wait.assert_called_once()

    def test_missing_native_dependency_fails_before_road_query_admission(self):
        with patch('run_shared_leg_pilot.shutil.which',return_value='/fake/c++'):
            with patch('run_shared_leg_pilot.subprocess.run',return_value=SimpleNamespace(returncode=1,stderr='missing cpp_int.hpp')):
                with self.assertRaisesRegex(RuntimeError,'before road-query admission'):compiler_preflight()
            with patch('run_shared_leg_pilot.subprocess.run',return_value=SimpleNamespace(returncode=0,stderr='')) as run:
                self.assertEqual(compiler_preflight()['compiler'],'/fake/c++')
                self.assertIn('-fsyntax-only',run.call_args.args[0])
                self.assertIn('boost::multiprecision::cpp_int',run.call_args.kwargs['input'])

    def test_failure_stops_all_real_phases_without_spending_unused_reservations(self):
        d=dict(active=None,state='generation_failed',real_work_stopped=True)
        for phase in ('freeze','generation','validation','optimization'):
            with self.subTest(phase=phase),self.assertRaises(ValueError):admit(d,phase,300,120,120)


if __name__=='__main__':unittest.main()
