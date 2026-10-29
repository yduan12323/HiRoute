"""Prospective gate tests: synthetic orchestration and tiny native graphs only."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import resource
import sys
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_TESTS=Path(__file__).resolve().parents[1]
for _path in (_TESTS,_TESTS/'m5d_recovery'):
    if str(_path) not in sys.path:sys.path.append(str(_path))

from experiments.pending_window_gate_v1 import run as gate
from experiments.pending_window_gate_v1 import domain as adapter
from experiments.pending_window_gate_v1 import lifecycle
from experiments.dev_cohort_v1 import run as cohort
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from test_envelope_sweep_gate import envelope_counts
from test_analytic_charge_gate import analytic_counts
from test_post_service_gate import final_reducer_counts


def pending_counts(arm):
    from timecut5.pending_window_dominance import PendingWindowDominanceStatistics
    value={n:0 for n in PendingWindowDominanceStatistics.__dataclass_fields__}
    value.update(enabled=gate.CONFIGS[arm]['pending_window_dominance'],post_service_enabled=True,
        calls=2,input_pieces=4,output_pieces=3)
    value['phase_fallback_calls' if value['enabled'] else 'disabled_fallback_calls']=2
    return value


def tiny_domain(root,arm):
    from timecut5.real_legs import RealSite
    old=support_domain(root/'original','support_on');query=json.loads(old.query_bytes)
    query['schedule']=dict(a=2,b=30,D=1)
    sites={sid:RealSite(s.site_id,s.anchor_id,('C','S','CS')) for sid,s in old.sites.items()}
    return adapter.PendingWindowDomain(arm=arm,case_binding={'case_id':'tiny','candidate_count':len(sites)},
        manifest_binding=base.digest('tiny pending feature pair'),graph_factory=old.graph_factory,query=query,
        sites=sites,tree=old.tree,source_hashes=old.source_hashes,cache=root/'pending',compiler=old.compiler['compiler'])


def terminal_fixture(arm,status='attained_optimum',key=None):
    key=key or ['8','1',1,[['s','CS']]]
    payload=dict(status='attained_optimum',J=key[0],Q_total=key[1],H=key[2],site_action_tuple=key[3],lex_key=key,
        charges=['1'],witness_replayed=True)
    if status=='infimum_unattained':payload=dict(status='primary_unattained',primary_infimum='7')
    value=dict(status=status,method='hier',strategy=arm,pending_window_arm=arm,accepted_key=key,
        pending_window_schema=gate.SCHEMA,pending_window_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
        pending_window_policy=gate.PENDING_WINDOW_POLICY,completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,
        case_binding_sha256=base.digest(gate.SPECS[gate.CASE]))
    return dict(value,Hmax=39,result=dict(H_ref=39,result=payload)),dict(value,search_status='SUCCESS')


def physical_common():
    common=dict(case_id=gate.CASE,candidate_count=128,case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),
        query={'physical':'same'},historical_query_sha256='h',runtime_rebinding_fields=['sparse_domain_sha256'],sites=[],
        tree_sha256='tree',seed=dict(max_depth=39,witness_bytes='same physical witness',key_bytes='same complete seed key'),
        proposal_ordinal=0,candidate_repair=None,seed_policy='historical',source={},inputs={},cache_policy=base.CACHE_POLICY)
    return common


class PendingWindowGateTests(unittest.TestCase):
    @patch.object(gate,'REVIEW_STATUS','pending_independent_proof_and_gate_review')
    def test_fixed_prospective_single_case_feature_pair_and_resources(self):
        plan=gate.prospective();off,on=[copy.deepcopy(gate.CONFIGS[a]) for a in gate.ARMS]
        self.assertFalse(off.pop('pending_window_dominance'));self.assertTrue(on.pop('pending_window_dominance'));self.assertEqual(off,on)
        self.assertEqual(gate.CASE,'OD06_energy_and_scheduled_soc3_10');self.assertEqual(gate.ORIGINAL_HMAX,39)
        self.assertEqual((plan['candidate_count'],plan['method']),(128,'hier'))
        for config in gate.CONFIGS.values():
            self.assertTrue(config['post_service_dominance']);self.assertTrue(config['analytic_charge'])
            for name in ('convex_charge_count_runtime','operator_compaction_candidate','service_deadline_screen'):self.assertFalse(config[name])
            shared=config['shared_configuration'];self.assertFalse(shared['envelope_sweep']);self.assertFalse(shared['coalescing'])
            self.assertTrue(shared['projection_support']);self.assertEqual(shared['time_quantum_exponent'],10)
            self.assertEqual(shared['routing'],'destination_target')
            for name in ('terminal_energy','onward_alt','remaining_charge'):self.assertTrue(shared[name])
        self.assertEqual(plan['denominator'],dict(independent_preparations=2,search_arms=2,independent_replays=2,total_stages=6,stages_per_pipeline=3))
        self.assertNotIn('baseline_src_sha256',plan);self.assertNotIn('production_source_entries',plan)
        self.assertNotIn('allowed_new_production_modules',plan)
        self.assertEqual(plan['source_base_commit'],'1a83b6440f57da00a773cff514f9a4c8f395d69c')
        limits=plan['limits'];self.assertEqual([limits[n] for n in ('search_seconds','search_worker_wall_seconds','search_worker_cpu_seconds','stage_wall_seconds','worker_cpu_seconds','verification_wall_seconds','verification_cpu_seconds')],[600,900,900,600,600,180,120])
        self.assertEqual(limits['address_space_bytes'],8*1024**3)
        self.assertEqual([plan['reserve_plan'][n] for n in ('total_exact_search_seconds','maximum_worker_wall_seconds','maximum_worker_cpu_soft_seconds')],[1200,3360,3240])
        self.assertEqual(gate.CPU_BY_ARM,dict(pending_off=0,pending_on=1));policy=plan['concurrency_policy']
        self.assertEqual((policy['pipeline_count'],policy['max_heavy_workers'],policy['numeric_threads']),(2,2,1))
        for name in ('aggregate_memory_hard_limit','cgroup_enforced','clean_cache_claim','isolation_claim','automatic_concurrency_reduction'):self.assertFalse(policy[name])
        self.assertFalse(plan['launchable']);self.assertFalse(plan['holdout']);self.assertFalse(plan['automatic_next_run'])
        with self.assertRaisesRegex(ValueError,'review is pending'):gate.require_launch_review()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json';bad=copy.deepcopy(plan);bad['launchable']=True;path.write_bytes(base.canonical(bad))
            with self.assertRaisesRegex(ValueError,'review is pending'):gate._manifest(path,base.file_hash(path))
            with patch.object(sys,'argv',['gate','--freeze','--input-directory',temp,'--output',str(path)]),patch.object(gate,'source_identity') as identity:
                with self.assertRaisesRegex(ValueError,'review is pending'):gate.main()
            identity.assert_not_called()
            for mutate in [lambda x:x['limits'].update(search_seconds=240),lambda x:x['arms']['pending_off'].update(post_service_dominance=False),
                lambda x:x['arms']['pending_on'].update(service_deadline_screen=True),lambda x:x.update(candidate_count=32),
                lambda x:x['concurrency_policy'].update(max_heavy_workers=1),lambda x:x['denominator'].update(total_stages=5)]:
                bad=copy.deepcopy(plan);bad['launchable']=True;mutate(bad);path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_future_reviewed_manifest_still_pins_compiler_inputs_and_closure(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(gate,'REVIEW_STATUS','approved_independent_proof_and_gate_review'):
            root=Path(temp);path=root/'m.json';manifest=gate.prospective()
            manifest.update(launchable=True,status='frozen_pending_window_pair_not_launched',repo=str(root),input_directory=str(root/'inputs'),
                compiler=dict(path=str(root/'compiler'),sha256='c'*64,version='pinned compiler\n',flags=['-O3','-std=c++17']),source={'closure_sha256':'d'*64})
            path.write_bytes(base.canonical(manifest));digest=base.file_hash(path)
            def pinned_hash(target):
                if Path(target)==cohort.BINDING_PATH:return manifest['cohort_binding_sha256']
                return 'c'*64 if str(target)==manifest['compiler']['path'] else manifest['inputs'][Path(target).name]['sha256']
            with patch.object(base,'file_hash',side_effect=pinned_hash),patch.object(Path,'stat',lambda p:SimpleNamespace(st_mode=stat.S_IFREG,st_size=manifest['inputs'][p.name]['size'])),patch.object(gate.subprocess,'check_output',return_value='pinned compiler\n'),patch.object(gate,'source_identity',return_value=manifest['source']):
                self.assertEqual(gate._manifest(path,digest),manifest)
                with patch.object(gate,'source_identity',return_value={'closure_sha256':'0'*64}):
                    with self.assertRaisesRegex(ValueError,'executable closure'):gate._manifest(path,digest)
                with patch.object(gate.subprocess,'check_output',return_value='wrong compiler\n'):
                    with self.assertRaisesRegex(ValueError,'compiler differs'):gate._manifest(path,digest)
                with patch.object(base,'file_hash',side_effect=lambda p:'0'*64 if Path(p).parent==root/'inputs' else pinned_hash(p)):
                    with self.assertRaisesRegex(ValueError,'input differs'):gate._manifest(path,digest)

    def test_source_identity_records_current_closure_without_historical_pin(self):
        root=Path(__file__).resolve().parents[2]
        initial={'src/timecut5/post_service_dominance.py':'old',gate.NEW_MODULE:'new','prior-gate':'p'}
        with patch.object(gate.prior_gate,'source_identity',return_value={'closure':initial}):
            identity=gate.source_identity(root)
            self.assertEqual(identity['pending_window_module_sha256'],'new')
            self.assertEqual(identity['pending_window_reducer_version'],'pending-window-late-primary-order-v1')
            self.assertEqual(identity['closure_sha256'],base.digest(identity['closure']))
            changed=dict(initial,**{'src/timecut5/optional.py':'new source'})
            with patch.object(gate.prior_gate,'source_identity',return_value={'closure':changed}):
                updated=gate.source_identity(root)
            self.assertNotEqual(updated['closure_sha256'],identity['closure_sha256'])
            self.assertEqual(updated['production_source_sha256'],base.digest({n:h for n,h in updated['closure'].items() if n.startswith('src/') and not n.startswith('src/hiroute.egg-info/')}))
            with patch.object(gate.prior_gate,'source_identity',return_value={'closure':{'src/timecut5/post_service_dominance.py':'old'}}):
                with self.assertRaisesRegex(ValueError,'lacks the new reducer'):
                    gate.source_identity(root)

    def run_pipeline(self,root,arm,*,outcomes=None,launch_exception=None,cleanup_failure=None,broken_artifact=None,hard=resource.RLIM_INFINITY):
        manifest=dict(gate.prospective(),repo=str(root),source={'closure_sha256':'a'*64});seen=[];outcomes=outcomes or ['SUCCESS']*3
        def launch(argv,*,output_dir,limits,cwd,phase_budget=None):
            op=argv[argv.index('--worker')+1];strategy=argv[argv.index('--strategy')+1] if '--strategy' in argv else None
            position=len(seen);seen.append((op,strategy,limits,phase_budget))
            if position==launch_exception:raise ValueError('injected launch')
            output_dir.mkdir(parents=True,exist_ok=False)
            if op=='prepare':
                target=output_dir/'artifacts/prepared/common.json';target.parent.mkdir(parents=True);target.write_bytes(b'{}')
            (output_dir/'receipt.json').write_bytes(b'{}')
            return dict(status=outcomes[position],cleanup_verified=position!=cleanup_failure)
        def load(*args):
            if len(seen)-1==broken_artifact:raise ValueError('injected artifact failure')
            return dict(status='attained_optimum')
        with patch.object(lifecycle,'run',side_effect=launch),patch.object(base,'load_worker_result',side_effect=load),patch('os.sched_getaffinity',return_value={0,1,3}),patch('os.sched_setaffinity'),patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,hard)),patch('resource.setrlimit') as setlimit,patch('signal.signal'):
            result=lifecycle.run_arm_plan('m','sha',root/'run',arm,gate.CPU_BY_ARM[arm],manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
        return result,seen,setlimit

    def test_each_dedicated_arm_pipeline_has_fresh_prepare_then_search_replay(self):
        for arm in gate.ARMS:
            for status in ('SUCCESS','TIMEOUT'):
                with tempfile.TemporaryDirectory() as temp:result,seen,setlimit=self.run_pipeline(Path(temp),arm,outcomes=['SUCCESS',status,'SUCCESS'])
                self.assertEqual(result['status'],'COMPLETED');self.assertEqual(result['denominator'],3)
                self.assertEqual([(r[0],r[1]) for r in seen],[('prepare',None),('arm',arm),('verify',arm)])
                self.assertEqual([(r[2].wall_seconds,r[2].cpu_seconds) for r in seen],[(600,600),(900,900),(180,120)])
                for op,_,limits,phase in seen:
                    self.assertEqual(limits.cpu,gate.CPU_BY_ARM[arm]);self.assertEqual(limits.address_space_bytes,8*1024**3)
                    if op=='arm':
                        phase.validate();self.assertEqual(phase.seconds,600);self.assertEqual(phase.identity['method'],'hier')
                        self.assertEqual(phase.identity['feature_arm'],arm);self.assertEqual(phase.identity['configuration_sha256'],base.digest(gate.CONFIGS[arm]))
                        self.assertEqual(phase.identity['pending_window_policy_sha256'],base.digest(gate.PENDING_WINDOW_POLICY))
                    else:self.assertIsNone(phase)
                self.assertEqual(setlimit.call_args.args[1][1],resource.RLIM_INFINITY)

    def test_every_pipeline_failure_retains_three_slots_and_never_retries(self):
        for position in range(3):
            for failure in ('FAILED','UNKNOWN','launch','cleanup','artifact'):
                outcomes=['SUCCESS']*3;kwargs={}
                if failure in ('FAILED','UNKNOWN'):outcomes[position]=failure
                else:kwargs[dict(launch='launch_exception',cleanup='cleanup_failure',artifact='broken_artifact')[failure]]=position
                with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_pipeline(Path(temp),gate.ARMS[0],outcomes=outcomes,**kwargs)
                self.assertNotEqual(result['status'],'COMPLETED');self.assertEqual(len(result['stages']),3);self.assertEqual(len(result['arms']),1)
                self.assertEqual(len(seen),position+1);self.assertFalse(any(r['status']=='PENDING' for r in [*result['stages'],*result['arms']]))
        with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_pipeline(Path(temp),gate.ARMS[0],hard=900)
        self.assertEqual(seen,[]);self.assertIn('901s',result['pipeline_error']['error'])

    def test_memory_admission_is_read_only_conservative_and_fail_closed(self):
        policy=gate.CONCURRENCY_POLICY;required=8448*1024**2
        for available in (required-1024,required,required+1024):
            with patch.object(Path,'read_text',return_value='MemAvailable: '+str(available//1024)+' kB\n'):
                row=lifecycle.available_memory_admission(policy)
            self.assertEqual(row['admitted'],available>=required);self.assertFalse(row['reservation']);self.assertFalse(row['aggregate_hard_limit'])
        for contents in ('','MemAvailable: unknown kB','MemAvailable: 9999 bytes'):
            with patch.object(Path,'read_text',return_value=contents):
                with self.assertRaises(ValueError):lifecycle.available_memory_admission(policy)

    def coordinator_fixture(self,root,*,missing=None,corrupt=None,cleanup_error=False,memory=True):
        manifest=dict(gate.prospective(),repo=str(root));seen=[]
        def popen(argv,**kwargs):
            arm=argv[argv.index('--strategy')+1];out=Path(argv[argv.index('--output')+1]);out.mkdir(parents=True)
            value=lifecycle.arm_ledger(arm,'sha');value['status']='COMPLETED'
            for row in value['stages']:row['status']='SUCCESS'
            for row in value['arms']:row['status']='attained_optimum'
            if arm==corrupt:value['denominator']=2
            if arm!=missing:lifecycle.atomic(out/'ledger.json',value)
            seen.append((argv,kwargs));polls=iter([None,0]);return SimpleNamespace(pid=100000+len(seen),returncode=0,poll=lambda:next(polls,0))
        with patch('os.sched_getaffinity',return_value={0,1,3}),patch.object(lifecycle,'available_memory_admission',return_value={'admitted':memory}),patch.object(lifecycle.subprocess,'Popen',side_effect=popen),patch('resource.setrlimit'),patch.object(lifecycle.supervisor,'_children',return_value=set()),patch.object(lifecycle.supervisor,'_tree',side_effect=OSError('cleanup inspect') if cleanup_error else None,return_value=({},False)),patch.object(lifecycle.time,'sleep'),patch.object(lifecycle.ctypes,'CDLL',return_value=SimpleNamespace(prctl=lambda *a:0)),patch.object(lifecycle,'run') as heavy:
            result=lifecycle.run_coordinator('m','sha',root/'run',manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
        heavy.assert_not_called();return result,seen

    def test_coordinator_only_launches_two_feature_pipelines_and_retains_six_slots(self):
        for failure in ('none','missing','corrupt','cleanup','memory'):
            with tempfile.TemporaryDirectory() as temp:
                result,seen=self.coordinator_fixture(Path(temp),missing=gate.ARMS[0] if failure=='missing' else None,corrupt=gate.ARMS[0] if failure=='corrupt' else None,cleanup_error=failure=='cleanup',memory=failure!='memory')
            self.assertEqual(len(seen),0 if failure=='memory' else 2);self.assertEqual(result['denominator'],6)
            self.assertEqual(len(result['stages']),6);self.assertEqual(len(result['arms']),2);self.assertEqual(result['status'],'COMPLETED' if failure=='none' else 'UNKNOWN')
            self.assertFalse(any(r['status']=='PENDING' for r in result['stages']))
            for arm,(argv,kwargs) in zip(gate.ARMS,seen):
                self.assertIn('--pipeline',argv);self.assertNotIn('--worker',argv);self.assertEqual(argv[argv.index('--cpu')+1],str(gate.CPU_BY_ARM[arm]))
                self.assertTrue(kwargs['start_new_session']);self.assertTrue(all(kwargs['env'][n]=='1' for n in lifecycle.THREAD_ENV))
            if failure in ('missing','corrupt'):self.assertEqual(result['pipelines'][gate.ARMS[1]]['status'],'COMPLETED')

    def matched_fixture(self,root,*,timeout=None,unattained=False):
        manifest=dict(gate.prospective(),source={'closure_sha256':'a'*64});pipelines={}
        for index,arm in enumerate(gate.ARMS):
            directory=root/arm;target=directory/('prepare-'+gate.CASE)/'artifacts/prepared/common.json';target.parent.mkdir(parents=True);target.write_bytes(b'{}')
            value=lifecycle.arm_ledger(arm,'sha');value.update(status='COMPLETED',process_returncode=0,pipeline_cleanup_verified=True)
            value['common'][gate.CASE]=dict(status='SUCCESS',cleanup_verified=True);value['stages'][0]['status']='SUCCESS'
            status='TIMEOUT' if timeout==arm else 'SUCCESS';outcome='timeout_feasible_only' if status=='TIMEOUT' else 'infimum_unattained' if unattained else 'attained_optimum'
            identity=dict(nonce='fixture',case_id=gate.CASE,strategy=arm,feature_arm=arm,method='hier',arm_index=str(index),manifest_sha256='sha',common_sha256=base.file_hash(target),source_closure_sha256='a'*64,
                experiment_schema=gate.SCHEMA,configuration_sha256=base.digest(gate.CONFIGS[arm]),pending_window_policy_sha256=base.digest(gate.PENDING_WINDOW_POLICY),completion_policy_sha256=base.digest(gate.COMPLETION_POLICY))
            value['arms'][0].update(status=outcome,receipt=dict(status=status,reason='phase_timeout' if status=='TIMEOUT' else 'success',cleanup_verified=True,phase_entered_monotonic=1,phase_budget=dict(seconds=600,identity=identity)),verification=dict(status='SUCCESS',cleanup_verified=True))
            value['stages'][1]['status']=status;value['stages'][2]['status']='SUCCESS';pipelines[arm]=value
        ledger=dict(status='COMPLETED',denominator=6,pipelines=pipelines,stages=[r for a in gate.ARMS for r in pipelines[a]['stages']],arms=[r for a in gate.ARMS for r in pipelines[a]['arms']])
        def load(directory,receipt,operation,case,arm=None):
            if operation=='prepare':return physical_common()
            completed,full=terminal_fixture(arm,'infimum_unattained' if unattained else 'attained_optimum')
            if arm==timeout:full.update(search_status='TIMEOUT',status='timeout_feasible_only')
            return full if operation=='verify' else completed
        return manifest,ledger,load

    def test_pair_admission_full_keys_unattained_and_timeout_censoring(self):
        for timeout,unattained in ((None,False),('pending_off',False),(None,True)):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest,ledger,load=self.matched_fixture(root,timeout=timeout,unattained=unattained)
                with patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_coordinator',return_value=ledger),patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',return_value={}):result=gate.run_gate('m','sha',root)
            self.assertTrue(result['operational_admission']);self.assertTrue(result['physical_preparations_match']);self.assertEqual(result['both_authenticated_complete'],timeout is None)
            self.assertEqual(result['denominator'],6);self.assertEqual(len(result['stages']),6)
        for failure in ('phase','method','feature','common_sha','key','infimum','hmax','observer','denominator','physical_query','seed_key','seed_witness','status'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest,ledger,load=self.matched_fixture(root,unattained=failure=='infimum')
                if failure=='phase':ledger['arms'][0]['receipt']['phase_budget']['seconds']=240
                if failure in ('method','feature','common_sha'):ledger['arms'][0]['receipt']['phase_budget']['identity'][dict(method='method',feature='feature_arm',common_sha='common_sha256')[failure]]='wrong'
                if failure=='denominator':ledger['pipelines'][gate.ARMS[0]]['denominator']=2
                def broken(directory,receipt,operation,case,arm=None):
                    value=load(directory,receipt,operation,case,arm)
                    is_off=gate.ARMS[0] in str(directory)
                    if is_off:
                        if failure=='physical_query' and operation=='prepare':value['query']['physical']='changed'
                        if failure in ('seed_key','seed_witness') and operation=='prepare':value['seed']['key_bytes' if failure=='seed_key' else 'witness_bytes']='changed'
                        if failure=='key' and operation!='prepare':
                            value['accepted_key'][0]='9'
                            if operation=='arm':value['result']['result'].update(J='9',lex_key=value['accepted_key'])
                        if failure=='infimum' and operation=='arm':value['result']['result']['primary_infimum']='6'
                        if failure=='status' and operation=='verify':value['status']='infimum_unattained'
                        if failure=='hmax' and operation=='arm':value['Hmax']=38
                    return value
                with patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_coordinator',return_value=ledger),patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',side_effect=ValueError('observer failed') if failure=='observer' else None,return_value={}):result=gate.run_gate('m','sha',root)
            self.assertFalse(result['operational_admission'],failure);self.assertFalse(result['both_authenticated_complete'],failure);self.assertEqual(len(result['stages']),6)

    def test_independent_preparation_match_ignores_only_nonphysical_receipt_paths_and_timing(self):
        first=physical_common();other=copy.deepcopy(first)
        first.update(charged_wall_ns=1,native={'artifact_path':'/first'});other.update(charged_wall_ns=99,native={'artifact_path':'/second'})
        self.assertEqual(gate.physical_preparation_identity(first),gate.physical_preparation_identity(other))
        other['seed']['native_sha256']='different stable native identity'
        self.assertNotEqual(gate.physical_preparation_identity(first),gate.physical_preparation_identity(other))

    def test_new_and_old_counters_remain_separate_and_censored_until_final(self):
        for arm in gate.ARMS:
            old=final_reducer_counts(True);new=pending_counts(arm)
            gate.validate_post_service_statistics(old,arm,completed=True);gate.validate_pending_window_statistics(new,old,arm,completed=True)
            sampled=copy.deepcopy(new);sampled['calls']+=1
            gate.validate_pending_window_statistics(sampled,old,arm,completed=False)
            with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_pending_window_statistics(sampled,old,arm,completed=True)
            for mutate in [lambda x:x.update(enabled=1),lambda x:x.update(post_service_enabled=False),lambda x:x.update(calls=True),lambda x:x.update(output_pieces=-1)]:
                bad=copy.deepcopy(new);mutate(bad)
                with self.assertRaises(ValueError):gate.validate_pending_window_statistics(bad,old,arm,completed=False)
        arm='pending_on';old=final_reducer_counts(True);new=pending_counts(arm)
        new.update(calls=3,input_pieces=6,output_pieces=4,strong_calls=1,arrangement_cells=1,selected_cells=1,candidate_visits=2,late_primary_discarded=1,kept_candidate_visits=1)
        gate.validate_pending_window_statistics(new,old,arm,completed=True)
        self.assertNotEqual(old['calls'],new['calls'])
        bad=copy.deepcopy(old);bad['calls']=new['calls']
        with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_pending_window_statistics(new,bad,arm,completed=True)

    def test_exact_phase_and_proper_unattained_components(self):
        for status in ('SUCCESS','TIMEOUT'):
            value=dict(status=status,reason='phase_timeout' if status=='TIMEOUT' else 'success',phase_entered_monotonic=1,phase_budget={'seconds':600});gate.require_exact_phase(value)
            for mutate in [lambda x:x['phase_budget'].update(seconds=600.0),lambda x:x['phase_budget'].update(seconds=True),lambda x:x.update(phase_entered_monotonic=None),lambda x:x.update(reason='wall_timeout',status='TIMEOUT')]:
                bad=copy.deepcopy(value);mutate(bad)
                with self.assertRaises(ValueError):gate.require_exact_phase(bad)
        for arm in gate.ARMS:
            for key in (['8','1',True,[['s','CS']]],['16/2','1',1,[['s','CS']]],['8','1',1,[]],['8',1,1,[['s','CS']]]):
                completed,full=terminal_fixture(arm,key=key)
                with self.assertRaises(ValueError):gate.validate_terminal(completed,full,arm,39)
            completed,full=terminal_fixture(arm,'infimum_unattained');self.assertEqual(gate.validate_terminal(completed,full,arm,39),dict(status='primary_unattained',primary_infimum='7'))
            for payload in (dict(status='primary_unattained',primary_infimum='14/2'),dict(status='primary_unattained',primary_infimum='-1'),dict(status='primary_unattained',primary_infimum='7',extra='1')):
                bad=copy.deepcopy(completed);bad['result']['result']=payload
                with self.assertRaises(ValueError):gate.validate_terminal(bad,full,arm,39)
            completed['result']['result']=dict(status='secondary_unattained',J='7',secondary_infimum='1/2')
            self.assertEqual(gate.validate_terminal(completed,full,arm,39),dict(status='secondary_unattained',J='7',secondary_infimum='1/2'))

    def test_tiny_native_both_hier_arms_same_physical_seed_and_fresh_full_replay(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import pending_window_dominance
        from timecut5.remaining_charge_runtime import RemainingChargeRuntimeV1
        answers={};bindings={};seed=None
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for arm in gate.ARMS:
                domain=tiny_domain(root/arm,arm)
                with adapter.historical_operators(),domain.context('verification') as context:witness=_solve_problem(domain.problem(context),True).result.witness
                current=domain.freeze_seed(witness)
                if seed is None:seed=current
                else:self.assertEqual(current,seed)
                bindings[arm]=domain.durable_binding(seed);out=root/(arm+'-result')
                with patch.object(pending_window_dominance,'make_pending_window_reducer',wraps=pending_window_dominance.make_pending_window_reducer) as factory:
                    result=domain.run_arm(arm,seed,out,search_seconds=15);factory.assert_called_once();args=factory.call_args
                    self.assertIs(type(args.kwargs['runtime']),RemainingChargeRuntimeV1);self.assertIs(args.kwargs['runtime']._problem,args.args[0])
                    self.assertEqual(args.kwargs['enabled'],gate.CONFIGS[arm]['pending_window_dominance']);self.assertTrue(args.kwargs['post_service_enabled']);self.assertTrue(args.kwargs['completed_departure_layers'])
                    fresh=tiny_domain(root/(arm+'-fresh'),arm);recovered=fresh.recover_durable(seed,out/'incumbent.json');factory.assert_called_once()
                self.assertEqual(result['method'],'hier');self.assertEqual(result['accepted_key'],recovered['accepted_key']);self.assertEqual(result['status'],'attained_optimum')
                self.assertEqual(recovered['pending_window_arm'],arm);self.assertIsNone(domain._singleton)
                with fresh.context('verification') as context:self.assertEqual(context.router.mode,'full')
                gate.validate_post_service_statistics(result['post_service_statistics'],arm,completed=True)
                gate.validate_pending_window_statistics(result['pending_window_statistics'],result['post_service_statistics'],arm,completed=True)
                gate.validate_combined_statistics(result['projection_support_statistics'],result['analytic_charge_statistics'],arm,completed=True)
                self.assertGreater(result['post_service_statistics']['strong_calls'],0)
                if arm=='pending_on':self.assertGreater(result['pending_window_statistics']['strong_calls'],0)
                snapshot=json.loads((out/'progress/progress.json').read_bytes())
                for key in ('pending_window_statistics','post_service_statistics','analytic_charge_statistics','pending_window_policy'):self.assertEqual(snapshot[key],result[key])
                other=gate.ARMS[1-gate.ARMS.index(arm)]
                with self.assertRaises(ValueError):domain.run_arm(other,seed,root/'wrong')
                with self.assertRaises(ValueError):tiny_domain(root/(arm+'-wrong'),other).recover_durable(seed,out/'incumbent.json')
                answers[arm]=result['accepted_key']
            self.assertEqual(*answers.values());self.assertNotEqual(bindings['pending_off'],bindings['pending_on'])

    def test_progress_bindings_final_health_and_fallback_subset_statistics(self):
        common=common_fixture();manifest=dict(gate.prospective(),source={'closure_sha256':'c'*64})
        for arm in gate.ARMS:
            support=counts(True,builds=0);analytic=analytic_counts(True,analytic=3,generic=0)
            post=final_reducer_counts(True);pending=pending_counts(arm);inner=admission_fixture('support_on',common)
            domain,sources=gate.progress_binding(manifest,arm,gate.CASE,common)
            value=dict(echo(inner),profile_schema=projection.SCHEMA,arm='support_on',configuration=projection.CONFIGS['support_on'],
                manifest_binding=base.digest(manifest),candidate_count=128,query_sha256=base.digest(common['query']),Hmax=2,status='returned',
                io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
                cohort_schema=cohort.SCHEMA,method='hier',shared_configuration=manifest['shared_configuration'],case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),
                method_policy=adapter.METHOD_POLICY,domain_sha256=domain,source_sha256=sources,projection_support_statistics=support,
                envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=None,pending_window_schema=gate.SCHEMA,pending_window_arm=arm,
                pending_window_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,pending_window_policy=gate.PENDING_WINDOW_POLICY,
                completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,analytic_charge_statistics=analytic,
                post_service_statistics=post,pending_window_statistics=pending)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json';ip=root/'remaining_charge_admission.json';mp=root/'method_admission.json';ap=root/'pending_window_admission.json'
                ip.write_bytes(base.canonical(inner));value['remaining_charge_admission_sha256']=base.file_hash(ip)
                method=gate.method_admission(base.digest(manifest),'hier',manifest['shared_configuration'],gate.SPECS[gate.CASE],base.file_hash(ip))
                mp.write_bytes(base.canonical(method));value['method_admission_sha256']=base.file_hash(mp)
                outer=adapter.outer_admission(base.digest(manifest),arm,base.file_hash(mp));ap.write_bytes(base.canonical(outer));value['pending_window_admission_sha256']=base.file_hash(ap)
                path.write_bytes(base.canonical(value));result=copy.deepcopy(value)
                result.update(schema=gate.SCHEMA,strategy=arm,inner_arm='support_on',progress_sha256=base.file_hash(path),remaining_charge_activation_wall_ns=123,
                    observer=dict(status='returned',io_error=None,heartbeat_error=None),projection_support_policy=projection.SUPPORT_POLICY)
                read=lambda status,final=None:gate.read_progress(path,manifest,arm,gate.CASE,common,search_status=status,completed_result=final)
                self.assertTrue(read('SUCCESS',result)['terminal_observer_health_proved']);self.assertTrue(read('TIMEOUT')['timeout_snapshot_is_censored'])
                for mutate in [lambda x:x.update(method='flat'),lambda x:x.update(pending_window_arm='wrong'),lambda x:x.update(pending_window_policy={}),
                    lambda x:x.update(post_service_policy={}),lambda x:x.update(progress_sha256='0'*64),lambda x:x['observer'].update(io_error='OSError'),
                    lambda x:x['pending_window_statistics'].update(calls=99),lambda x:x['post_service_statistics'].update(calls=99)]:
                    bad=copy.deepcopy(result);mutate(bad)
                    with self.assertRaises(ValueError):read('SUCCESS',bad)
                live=copy.deepcopy(value);live['pending_window_statistics']['calls']=99;path.write_bytes(base.canonical(live));self.assertFalse(read('TIMEOUT')['terminal_observer_health_proved'])
                bad=copy.deepcopy(result);bad.update(progress_sha256=base.file_hash(path),pending_window_statistics=live['pending_window_statistics'])
                with self.assertRaisesRegex(ValueError,'conserve'):read('SUCCESS',bad)
                path.write_bytes(base.canonical(value));ap.write_bytes(base.canonical(dict(outer,arm='wrong')))
                with self.assertRaisesRegex(ValueError,'admission differs'):read('TIMEOUT')


if __name__=='__main__':unittest.main()
