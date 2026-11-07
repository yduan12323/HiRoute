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
from exact_leg_table import ExactLegTable,GroundedLookup
from exact_physical_adapter import solve,solve_real,table_relevant_depth,relevant_depth,Engine,replay
from split_leg_table import write as split_write,read as split_read,close as split_close,digest as split_digest,LIMITS
from exact_physical_fixtures import case,tiny_table,IDS,semantics
from run_shared_leg_pilot import write_table,sample_pairs,verify_paths,physical,receipt,sha,header,freeze,compiler_preflight,native_build_preflight,verify_native_build
from shared_pilot_budget import admit,total_spent,tree_usage,reap_group,record_outcome,terminal_summary
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

    def test_actual_controller_finalizer_stops_failed_real_phase_and_never_clears_stop(self):
        cases=[('generation',75,None,'UNKNOWN',None),('generation',0,'wall_guard','COMPLETE',None),
               ('freeze',None,'unstarted_host_resource_guard',None,None),
               ('validation',0,None,None,None),('optimization',0,None,'COMPLETE','unknown_resource_or_solver')]
        for phase,code,guard,status,comparison in cases:
            with self.subTest(phase=phase,guard=guard):
                d=dict(phase_charged_CPU_s=dict.fromkeys(['freeze','generation','validation','optimization'],0),records=[],active={'x':1},state='running')
                r=dict(phase=phase,label='failed',charged_CPU_s='1.25',actual_child_returncode=code,
                    guard_reason=guard,terminal_mode=phase,terminal_status=status,comparison_status=comparison,terminal_read_error=None)
                record_outcome(d,r)
                self.assertTrue(d['real_work_stopped']);self.assertIsNone(d['active'])
                self.assertEqual(d['phase_charged_CPU_s'][phase],'1.25')
                with self.assertRaises(ValueError):admit(d,'generation',300,270,300)
                r=dict(r,phase='generation',label='later',actual_child_returncode=0,guard_reason=None,terminal_mode='generation',terminal_status='COMPLETE')
                record_outcome(d,r);self.assertTrue(d['real_work_stopped'])
        for status in ('attained_optimum','primary_unattained','secondary_unattained'):
            d=dict(phase_charged_CPU_s={'optimization':0},records=[],active=True,state='running')
            record_outcome(d,dict(phase='optimization',label='finished',charged_CPU_s='1',actual_child_returncode=0,
                guard_reason=None,terminal_mode='optimization',terminal_status='COMPLETE',comparison_status=status,terminal_read_error=None))
            self.assertFalse(d.get('real_work_stopped',False))

    def test_native_prebuild_uses_full_native_loader_and_binds_generated_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)/'native'
            def build(path):
                path.mkdir();binary=path/'road_index.so';binary.write_bytes(b'unit-test-artifact-not-a-real-build')
                return SimpleNamespace(_name=str(binary)),None
            with patch('hiroute.exact.road_index._load_native_library',side_effect=build) as loader:
                value=native_build_preflight(directory);loader.assert_called_once()
            verify_native_build(value)
            with self.assertRaises(ValueError):verify_native_build(dict(value,loaded=False))
            Path(value['binary']).write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_native_build(value)

    def test_terminal_summary_cannot_vacuously_complete_missing_or_large_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json';self.assertIsNotNone(terminal_summary(p)[3])
            p.write_text('{"mode":"generation","status":"COMPLETE"}')
            self.assertEqual(terminal_summary(p),('generation','COMPLETE',None,None))
            p.write_bytes(b' '* (4*1024**2+1));self.assertIsNotNone(terminal_summary(p)[3])


class SplitInputTests(unittest.TestCase):
    def payload(self,name='CS_overlap'):
        fixture=case(name);_,raw,_=tiny_table(fixture)
        return fixture,json.loads(raw)
    def write(self,root,payload,**kw):
        return split_write(root,{k:v for k,v in payload.items() if k!='pairs'},iter(payload['pairs']),dict(test='synthetic'),**kw)
    def edit(self,root,name,value):
        path=root/name;path.chmod(0o644);path.write_text(json.dumps(value,separators=(',',':')))
        if name!='manifest.json':
            manifest=json.loads((root/'manifest.json').read_text());manifest['files'][name]=dict(bytes=path.stat().st_size,sha256=split_digest(path))
            self.edit(root,'manifest.json',manifest)

    def test_eight_class_split_inline_replay_depth_and_full_key_parity(self):
        for name in IDS:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                f,p=self.payload(name);inline=ExactLegTable.from_dict(p);root=Path(d)
                count,sha=self.write(root,p);table=split_read(root)
                try:
                    self.assertEqual(count,len(inline.pairs));self.assertEqual(sha,table.payload_sha256)
                    self.assertEqual(table.actions,inline.actions);self.assertEqual(table.candidate_order,inline.candidate_order)
                    for key,x in inline.pairs.items():
                        y=table.pairs[key]
                        self.assertEqual((x.time,x.length,x.nodes,x.edges),(y.time,y.length,y.nodes,y.edges))
                    w=f['upper_witness']
                    self.assertEqual(replay(table,f['physics'],w['plan'],w['charges'],w['initial_wait']),
                                     replay(inline,f['physics'],w['plan'],w['charges'],w['initial_wait']))
                    self.assertEqual(table_relevant_depth(table,f['physics'],w),table_relevant_depth(inline,f['physics'],w))
                    if name in ('CS_overlap','primary_unattained','secondary_unattained','equality_attained'):
                        self.assertEqual(semantics(solve_real(table,f['physics'],w,time_limit_s=8)),f['expected'])
                finally:split_close(table)

    def test_paths_preserve_lexical_edge_tie_selected_length(self):
        p=RoadIndex([dict(source=u,target=v,edge_id=e,time_s='1',length_m=str(L)) for u,v,e,L in
                     [('o','a','oa',2),('o','b','ob',1),('a','z','az9',1),('a','z','az1',3),('b','z','bz',1)]])
        f,payload=self.payload('directed_unreachable');payload['sites']={'literal-a':dict(anchor='a',effects=['C'])};payload['candidate_order']=['literal-a']
        from run_shared_leg_pilot import record
        payload['pairs']=[record(p.selected_leg(s,t),s,t) for s in ('a','o') for t in ('a','z')]
        with tempfile.TemporaryDirectory() as d:
            self.write(Path(d),payload);table=split_read(Path(d))
            try:self.assertEqual((table.pairs['o','z'].nodes,table.pairs['o','z'].edges,table.pairs['o','z'].length),(('o','a','z'),('oa','az1'),5))
            finally:split_close(table)

    def test_missing_extra_duplicate_or_mismatched_pair_index_rejected(self):
        _,p=self.payload()
        for kind in ('missing','duplicate','extra','offset','ordinal','numeric','trailing'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);self.write(root,p);index=json.loads((root/'paths.index.json').read_text())
                if kind=='missing':index.pop()
                elif kind in ('duplicate','extra'):index.append(copy.deepcopy(index[-1]))
                elif kind=='offset':index[-1]['offset']+=1
                elif kind=='ordinal':index[-1]['ordinal']=True
                elif kind=='numeric':
                    numeric=json.loads((root/'numeric.json').read_text());numeric['pairs'][-1]['time_s']='999';self.edit(root,'numeric.json',numeric)
                elif kind=='trailing':
                    path=root/'paths.bin';path.chmod(0o644);path.write_bytes(path.read_bytes()+b'x')
                    m=json.loads((root/'manifest.json').read_text());m['files']['paths.bin']=dict(bytes=path.stat().st_size,sha256=split_digest(path));self.edit(root,'manifest.json',m)
                self.edit(root,'paths.index.json',index)
                with self.assertRaises((ValueError,TypeError)):split_read(root)

    def test_frame_corruption_truncation_digest_swap_and_decoded_bounds_rejected(self):
        _,p=self.payload()
        for kind in ('corrupt','truncated','hash','decoded','framequota','totalquota','identityquota','manifestquota'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);self.write(root,p);limits={}
                if kind in ('corrupt','truncated'):
                    path=root/'paths.bin';path.chmod(0o644);data=path.read_bytes();path.write_bytes((bytes([data[0]^1])+data[1:]) if kind=='corrupt' else data[:-1])
                elif kind in ('hash','decoded'):
                    index=json.loads((root/'paths.index.json').read_text())
                    if kind=='hash':index[0]['decoded_sha256']='0'*64
                    else:index[0]['decoded_bytes']=1
                    self.edit(root,'paths.index.json',index)
                else:limits[{ 'framequota':'frame','totalquota':'decoded','identityquota':'identity','manifestquota':'manifest'}[kind]]=1
                with self.assertRaises((ValueError,TypeError)):split_read(root,limits=limits)

    def test_interrupted_output_never_commits_manifest_or_repeats(self):
        _,p=self.payload()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(RuntimeError):self.write(root,p,limits={'paths':1})
            self.assertFalse((root/'manifest.json').exists())
            with self.assertRaises(FileNotFoundError):split_read(root)
            with self.assertRaises(ValueError):self.write(root,p)

    def test_lazy_fetch_rechecks_owned_descriptor_and_closed_store(self):
        _,p=self.payload()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.write(root,p);t=split_read(root);pair=next(iter(t.pairs.values()))
            path=root/'paths.bin';path.chmod(0o644)
            with path.open('r+b') as f:f.write(b'X')
            with self.assertRaises((ValueError,__import__('zlib').error)):pair.nodes
            split_close(t)
            with self.assertRaises(ValueError):pair.edges

    def test_distinct_payloads_do_not_share_owned_lookup_traces(self):
        _,p=self.payload()
        with tempfile.TemporaryDirectory() as d:
            aroot,broot=Path(d)/'a',Path(d)/'b';self.write(aroot,p)
            altered=copy.deepcopy(p)
            for row in altered['pairs']:
                if row['reachable']:row['actual_length_m']=str(F(row['actual_length_m'])*2)
            self.write(broot,altered);a,b=split_read(aroot),split_read(broot)
            try:
                self.assertNotEqual(a.payload_sha256,b.payload_sha256)
                lookup=GroundedLookup(a);trace=lookup.trace(1,1)
                with self.assertRaises(ValueError):GroundedLookup(b).resolve(trace,[('p','CS')])
            finally:split_close(a);split_close(b)


if __name__=='__main__':unittest.main()
