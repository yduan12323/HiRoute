"""Synthetic orchestration/admission plus tiny native method-pair tests only."""
import copy
from fractions import Fraction as F
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

from experiments.post_service_cohort_v1 import run as gate
from experiments.post_service_cohort_v1 import domain as adapter
from experiments.post_service_cohort_v1 import lifecycle
from experiments.dev_cohort_v1 import run as cohort
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from test_envelope_sweep_gate import envelope_counts
from test_analytic_charge_gate import analytic_counts
from test_post_service_gate import final_reducer_counts
from experiments.remaining_charge_gate_v1.singleton import POLICY_SCHEMA


def tiny_domain(root,method):
    old=support_domain(root/'original','support_on')
    return adapter.PostServiceCohortDomain(arm=method,case_binding={'case_id':'tiny','candidate_count':len(old.sites)},
        manifest_binding=base.digest('tiny post-service matched cohort'),graph_factory=old.graph_factory,query=json.loads(old.query_bytes),
        sites=old.sites,tree=old.tree,source_hashes=old.source_hashes,cache=root/'cohort',compiler=old.compiler['compiler'])


def terminal_fixture(method,status='attained_optimum',key=None):
    key=key or ['8','1',1,[['s','C']]]
    payload=dict(status='attained_optimum',J=key[0],Q_total=key[1],H=key[2],site_action_tuple=key[3],lex_key=key,
        charges=['1'],witness_replayed=True)
    if status=='infimum_unattained':payload=dict(status='primary_unattained',primary_infimum='7')
    value=dict(status=status,method=method,strategy=method,post_service_cohort_arm=method,accepted_key=key,
        post_service_cohort_schema=gate.SCHEMA,post_service_cohort_configuration=gate.CONFIGS[method],post_service_policy=gate.POST_SERVICE_POLICY,
        completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY)
    completed=dict(value,Hmax=33,result=dict(H_ref=33,result=payload))
    full=dict(value,search_status='SUCCESS')
    return completed,full


class CohortTests(unittest.TestCase):
    def test_fixed_prospective_plan_and_reviewed_release(self):
        plan=gate.prospective()
        self.assertEqual(gate.CASES,('OD02_energy_only_soc3_10','OD06_energy_and_scheduled_soc3_10'))
        self.assertEqual(gate.PAIRS,[[gate.CASES[0],['flat','hier']],[gate.CASES[1],['hier','flat']]])
        self.assertEqual(gate.ORIGINAL_HMAX,{gate.CASES[0]:33,gate.CASES[1]:39})
        self.assertEqual(plan['cases'],[cohort.SPECS[c] for c in gate.CASES]);self.assertEqual(plan['candidate_count'],128)
        self.assertEqual(plan['denominator'],dict(common_preparations=2,search_arms=4,independent_replays=4,total_stages=10,stages_per_case=5))
        self.assertNotIn('production_source_entries',plan);self.assertNotIn('baseline_src_sha256',plan)
        for method,config in plan['arms'].items():
            self.assertEqual(config['method'],method);self.assertTrue(config['analytic_charge']);self.assertTrue(config['post_service_dominance'])
            self.assertFalse(config['convex_charge_count_runtime']);self.assertFalse(config['operator_compaction_candidate'])
            self.assertFalse(config['shared_configuration']['envelope_sweep']);self.assertFalse(config['shared_configuration']['coalescing'])
            self.assertTrue(config['shared_configuration']['projection_support']);self.assertEqual(config['shared_configuration']['time_quantum_exponent'],10)
        limits=plan['limits'];self.assertEqual((limits['search_seconds'],limits['search_worker_wall_seconds'],limits['search_worker_cpu_seconds']),(600,900,900))
        self.assertEqual((limits['stage_wall_seconds'],limits['worker_cpu_seconds'],limits['verification_wall_seconds'],limits['verification_cpu_seconds']),(600,600,180,120))
        self.assertEqual(limits['address_space_bytes'],8*1024**3)
        self.assertEqual((plan['reserve_plan']['total_exact_search_seconds'],plan['reserve_plan']['maximum_worker_wall_seconds'],plan['reserve_plan']['maximum_worker_cpu_soft_seconds']),(2400,5520,5280))
        concurrent=plan['concurrency_policy'];self.assertEqual(concurrent['cpu_by_case'],{gate.CASES[0]:0,gate.CASES[1]:1})
        self.assertEqual((concurrent['pipeline_count'],concurrent['max_heavy_workers'],concurrent['numeric_threads']),(2,2,1))
        for name in ('aggregate_memory_hard_limit','cgroup_enforced','clean_cache_claim','isolation_claim','automatic_concurrency_reduction'):self.assertFalse(concurrent[name])
        self.assertFalse(plan['launchable']);self.assertFalse(plan['automatic_next_run']);self.assertFalse(plan['holdout'])
        self.assertEqual(plan['performance_interpretation'],'descriptive_shared_host_only')
        self.assertEqual(plan['review_status'],'approved_independent_cohort_review')
        self.assertIsNone(gate.require_launch_review())
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json'
            with patch.object(gate,'REVIEW_STATUS','pending_independent_cohort_review'):
                with self.assertRaisesRegex(ValueError,'review is pending'):gate.require_launch_review()
                bad=gate.prospective();bad['launchable']=True;path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'review is pending'):gate._manifest(path,base.file_hash(path))
                with patch.object(sys,'argv',['gate','--freeze','--input-directory',temp,'--output',str(path)]),patch.object(gate,'source_identity') as identity:
                    with self.assertRaisesRegex(ValueError,'review is pending'):gate.main()
                identity.assert_not_called()
            for mutate in [lambda x:x['limits'].update(search_seconds=240),lambda x:x['limits'].update(search_worker_cpu_seconds=600),
                lambda x:x['completion_policy'].update(exact_phase_seconds=240),lambda x:x['arms']['flat'].update(convex_charge_count_runtime=True),
                lambda x:x.update(candidate_count=32),lambda x:x['historical_hmax'].update({gate.CASES[0]:32}),
                lambda x:x['concurrency_policy'].update(max_heavy_workers=1),lambda x:x['denominator'].update(total_stages=5)]:
                bad=copy.deepcopy(plan);bad['launchable']=True;mutate(bad);path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_reviewed_manifest_still_checks_compiler_closure_and_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'manifest.json'
            with patch.object(gate,'REVIEW_STATUS','approved_independent_cohort_review'):
                manifest=gate.prospective();manifest.update(launchable=True,status='frozen_post_service_cohort_not_launched',repo=str(root),input_directory=str(root/'inputs'),
                    compiler=dict(path=str(root/'compiler'),sha256='c'*64,version='pinned compiler\n',flags=['-O3','-std=c++17']),source={'closure_sha256':'d'*64})
                path.write_bytes(base.canonical(manifest));digest=base.file_hash(path)
                def pinned_hash(target):
                    if Path(target)==cohort.BINDING_PATH:return manifest['cohort_binding_sha256']
                    return 'c'*64 if str(target)==manifest['compiler']['path'] else manifest['inputs'][Path(target).name]['sha256']
                def pinned_stat(target):return SimpleNamespace(st_mode=stat.S_IFREG,st_size=manifest['inputs'][target.name]['size'])
                with patch.object(base,'file_hash',side_effect=pinned_hash),patch.object(Path,'stat',pinned_stat),patch.object(gate.subprocess,'check_output',return_value='pinned compiler\n'),patch.object(gate,'source_identity',return_value=manifest['source']):
                    self.assertEqual(gate._manifest(path,digest),manifest)
                    with patch.object(gate,'source_identity',return_value={'closure_sha256':'0'*64}):
                        with self.assertRaisesRegex(ValueError,'executable closure'):gate._manifest(path,digest)
                    with patch.object(gate.subprocess,'check_output',return_value='different compiler\n'):
                        with self.assertRaisesRegex(ValueError,'compiler differs'):gate._manifest(path,digest)
                    with patch.object(base,'file_hash',side_effect=lambda target:'0'*64 if Path(target).parent==root/'inputs' else pinned_hash(target)):
                        with self.assertRaisesRegex(ValueError,'input differs'):gate._manifest(path,digest)

    def test_exact600_phase_and_terminal_canonical_components(self):
        for status in ('SUCCESS','TIMEOUT'):
            row=dict(status=status,reason='phase_timeout' if status=='TIMEOUT' else 'success',phase_entered_monotonic=1,phase_budget={'seconds':600})
            gate.require_exact_phase(row)
            for mutate in [lambda x:x['phase_budget'].update(seconds=240),lambda x:x['phase_budget'].update(seconds=600.0),
                lambda x:x['phase_budget'].update(seconds=True),lambda x:x.update(phase_entered_monotonic=None),lambda x:x.update(status='FAILED')]:
                bad=copy.deepcopy(row);mutate(bad)
                with self.assertRaisesRegex(ValueError,'600-second'):gate.require_exact_phase(bad)
        with self.assertRaises(ValueError):gate.require_exact_phase(dict(status='TIMEOUT',reason='wall_timeout',phase_entered_monotonic=1,phase_budget={'seconds':600}))
        for method in gate.METHODS:
            completed,full=terminal_fixture(method);self.assertEqual(gate.validate_terminal(completed,full,method,33)['lex_key'],full['accepted_key'])
            bad=copy.deepcopy(completed);bad['result']['result']['J']='9'
            with self.assertRaises(ValueError):gate.validate_terminal(bad,full,method,33)
            with self.assertRaises(ValueError):gate.validate_terminal(completed,full,method,39)
            completed,full=terminal_fixture(method,'infimum_unattained');self.assertEqual(gate.validate_terminal(completed,full,method,33),dict(status='primary_unattained',primary_infimum='7'))
            for mutate in [lambda x:x['result']['result'].update(primary_infimum='14/2'),lambda x:x['result']['result'].update(extra='1'),lambda x:x['result']['result'].update(primary_infimum='-1')]:
                bad=copy.deepcopy(completed);mutate(bad)
                with self.assertRaises(ValueError):gate.validate_terminal(bad,full,method,33)

    def test_source_identity_records_current_closure_and_required_reducer(self):
        root=Path(__file__).resolve().parents[2];module='src/timecut5/post_service_dominance.py'
        initial={module:'m','prior-gate':'p'}
        with patch.object(gate.prior_gate,'source_identity',return_value=dict(closure=initial)):
            identity=gate.source_identity(root)
            self.assertIn('experiments/post_service_cohort_v1/lifecycle.py',identity['closure'])
            self.assertEqual(identity['closure_sha256'],base.digest(identity['closure']))
            changed=dict(initial,**{'src/timecut5/new_module.py':'new'})
            with patch.object(gate.prior_gate,'source_identity',return_value=dict(closure=changed)):
                updated=gate.source_identity(root)
            self.assertNotEqual(updated['closure_sha256'],identity['closure_sha256'])
            self.assertEqual(updated['production_source_entries'],2)
            with patch.object(gate.prior_gate,'source_identity',return_value={'closure':{'prior-gate':'p'}}):
                with self.assertRaisesRegex(ValueError,'lacks the reducer'):
                    gate.source_identity(root)

    def run_pipeline(self,root,case,*,outcomes=None,launch_exception=None,cleanup_failure=None,broken_artifact=None,hard=resource.RLIM_INFINITY):
        manifest=dict(gate.prospective(),repo=str(root),source={'closure_sha256':'a'*64});seen=[]
        outcomes=outcomes or ['SUCCESS']*5
        def launch(argv,*,output_dir,limits,cwd,phase_budget=None):
            operation=argv[argv.index('--worker')+1];method=argv[argv.index('--strategy')+1] if '--strategy' in argv else None
            position=len(seen);seen.append((operation,method,limits,phase_budget))
            if position==launch_exception:raise ValueError('injected supervisor launch')
            output_dir.mkdir(parents=True,exist_ok=False)
            if operation=='prepare':
                common=output_dir/'artifacts/prepared/common.json';common.parent.mkdir(parents=True);common.write_bytes(b'{}')
            (output_dir/'receipt.json').write_bytes(b'{}')
            return dict(status=outcomes[position],cleanup_verified=position!=cleanup_failure)
        def load(directory,receipt,operation,case,strategy=None):
            if len(seen)-1==broken_artifact:raise ValueError('injected artifact failure')
            return dict(status='attained_optimum')
        with patch.object(lifecycle,'run',side_effect=launch),patch.object(base,'load_worker_result',side_effect=load),patch('os.sched_getaffinity',return_value={0,1,3}),patch('os.sched_setaffinity'),patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,hard)),patch('resource.setrlimit') as setlimit,patch('signal.signal'):
            result=lifecycle.run_case_plan('manifest','sha',root/'run',case,gate.CPU_BY_CASE[case],manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
        return result,seen,setlimit

    def test_dedicated_case_pipeline_serial_order_caps_and_method_phase(self):
        for case in gate.CASES:
            for search_status in ('SUCCESS','TIMEOUT'):
                with tempfile.TemporaryDirectory() as temp:result,seen,setlimit=self.run_pipeline(Path(temp),case,outcomes=['SUCCESS',search_status,'SUCCESS',search_status,'SUCCESS'])
                self.assertEqual(result['status'],'COMPLETED');self.assertEqual(result['denominator'],5);self.assertEqual(len(result['stages']),5)
                order=dict(gate.PAIRS)[case];self.assertEqual([(x[0],x[1]) for x in seen],[('prepare',None),('arm',order[0]),('verify',order[0]),('arm',order[1]),('verify',order[1])])
                self.assertEqual([(x[2].wall_seconds,x[2].cpu_seconds) for x in seen],[(600,600),(900,900),(180,120),(900,900),(180,120)])
                for index,(op,method,limits,phase) in enumerate(seen):
                    self.assertEqual(limits.cpu,gate.CPU_BY_CASE[case]);self.assertEqual(limits.address_space_bytes,8*1024**3)
                    if op=='arm':
                        self.assertEqual(phase.seconds,600);phase.validate();self.assertEqual(phase.identity['method'],method)
                        self.assertEqual(phase.identity['completion_policy_sha256'],base.digest(gate.COMPLETION_POLICY));self.assertEqual(phase.identity['experiment_schema'],gate.SCHEMA)
                    else:self.assertIsNone(phase)
                self.assertEqual(setlimit.call_args.args[1][1],resource.RLIM_INFINITY)

    def test_pipeline_all_failure_positions_retain_five_slots_without_retry(self):
        case=gate.CASES[0]
        for position in range(5):
            for failure in ('FAILED','UNKNOWN','launch','cleanup','artifact'):
                outcomes=['SUCCESS']*5;kwargs={}
                if failure in ('FAILED','UNKNOWN'):outcomes[position]=failure
                else:kwargs[dict(launch='launch_exception',cleanup='cleanup_failure',artifact='broken_artifact')[failure]]=position
                with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_pipeline(Path(temp),case,outcomes=outcomes,**kwargs)
                self.assertNotEqual(result['status'],'COMPLETED');self.assertEqual(len(result['stages']),5);self.assertEqual(len(result['arms']),2)
                self.assertEqual(len(seen),position+1);self.assertFalse(any(r['status']=='PENDING' for r in [*result['stages'],*result['arms']]))
        with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_pipeline(Path(temp),case,hard=900)
        self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(seen,[]);self.assertIn('901s',result['pipeline_error']['error'])

    def test_memory_admission_is_read_only_conservative_and_fail_closed(self):
        policy=gate.CONCURRENCY_POLICY;required=policy['required_available_memory_bytes']
        for available in (required-1024,required,required+1024):
            with patch.object(Path,'read_text',return_value='MemTotal: 99999999 kB\nMemAvailable: '+str(available//1024)+' kB\n'):
                row=lifecycle.available_memory_admission(policy)
            self.assertEqual(row['admitted'],available>=required);self.assertFalse(row['reservation']);self.assertFalse(row['aggregate_hard_limit'])
        for text in ('MemFree: 999999 kB\n','MemAvailable: nan kB\n','MemAvailable: 100000000 MB\n'):
            with patch.object(Path,'read_text',return_value=text),self.assertRaises(ValueError):lifecycle.available_memory_admission(policy)

    def test_coordinator_prelaunch_failure_preserves_ten_slots(self):
        for failure in ('memory','memory_unknown','cpu','launch'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest=dict(gate.prospective(),repo=str(root))
                with patch('os.sched_getaffinity',return_value={3} if failure=='cpu' else {0,1,3}),patch.object(lifecycle,'available_memory_admission',side_effect=ValueError('missing sample') if failure=='memory_unknown' else None,return_value={'admitted':failure!='memory'}),patch.object(lifecycle.subprocess,'Popen',side_effect=ValueError('injected pipeline launch')) as popen,patch('resource.setrlimit'):
                    ledger=lifecycle.run_coordinator('m','sha',root/'run',manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
                self.assertEqual(ledger['denominator'],10);self.assertEqual(len(ledger['stages']),10);self.assertEqual(len(ledger['arms']),4)
                self.assertEqual(ledger['status'],'UNKNOWN');self.assertFalse(any(r['status']=='PENDING' for r in ledger['stages']))
                if failure!='launch':popen.assert_not_called()

    def coordinator_fixture(self,root,*,missing_ledger=None,corrupt_ledger=None,cleanup_error=False):
        manifest=dict(gate.prospective(),repo=str(root));seen=[]
        def popen(argv,**kwargs):
            case=argv[argv.index('--case')+1];out=Path(argv[argv.index('--output')+1]);out.mkdir()
            value=lifecycle.case_ledger(case,'sha');value['status']='COMPLETED'
            for row in value['stages']:row['status']='SUCCESS'
            for row in value['arms']:row['status']='attained_optimum'
            if case==corrupt_ledger:value['denominator']=4
            if case!=missing_ledger:lifecycle.atomic(out/'ledger.json',value)
            polls=iter([None,0]);proc=SimpleNamespace(pid=100000+len(seen),returncode=0,poll=lambda:next(polls,0))
            seen.append((argv,kwargs));return proc
        tree=OSError('injected cleanup inspection') if cleanup_error else None
        with patch('os.sched_getaffinity',return_value={0,1,3}),patch.object(lifecycle,'available_memory_admission',return_value={'admitted':True}),patch.object(lifecycle.subprocess,'Popen',side_effect=popen),patch('resource.setrlimit'),patch.object(lifecycle.supervisor,'_children',return_value=set()),patch.object(lifecycle.supervisor,'_tree',side_effect=tree,return_value=({},False)),patch.object(lifecycle.time,'sleep'):
            ledger=lifecycle.run_coordinator('m','sha',root/'run',manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
        return ledger,seen

    def test_coordinator_launches_only_two_independent_case_processes_and_retains_failures(self):
        for failure in ('none','missing','corrupt','cleanup'):
            with tempfile.TemporaryDirectory() as temp:
                ledger,seen=self.coordinator_fixture(Path(temp),missing_ledger=gate.CASES[0] if failure=='missing' else None,
                    corrupt_ledger=gate.CASES[0] if failure=='corrupt' else None,cleanup_error=failure=='cleanup')
            self.assertEqual(len(seen),2);self.assertEqual(ledger['denominator'],10);self.assertEqual(len(ledger['stages']),10);self.assertEqual(len(ledger['arms']),4)
            self.assertEqual(ledger['status'],'COMPLETED' if failure=='none' else 'UNKNOWN')
            self.assertFalse(any(r['status']=='PENDING' for r in ledger['stages']))
            for case,(argv,kwargs) in zip(gate.CASES,seen):
                self.assertIn('--pipeline',argv);self.assertNotIn('--worker',argv);self.assertEqual(argv[argv.index('--cpu')+1],str(gate.CPU_BY_CASE[case]))
                self.assertTrue(kwargs['start_new_session']);self.assertTrue(all(kwargs['env'][name]=='1' for name in lifecycle.THREAD_ENV))
            if failure in ('missing','corrupt'):self.assertEqual(ledger['pipelines'][gate.CASES[1]]['status'],'COMPLETED')

    def matched_fixture(self,root,*,timeout_method=None,unattained=False):
        manifest=dict(gate.prospective(),source={'closure_sha256':'a'*64});pipelines={}
        for case in gate.CASES:
            directory=root/case;target=directory/('prepare-'+case)/'artifacts/prepared/common.json';target.parent.mkdir(parents=True);target.write_bytes(b'{}')
            value=lifecycle.case_ledger(case,'sha');value.update(status='COMPLETED',process_returncode=0,pipeline_cleanup_verified=True)
            value['common'][case]=dict(status='SUCCESS',cleanup_verified=True);value['stages'][0]['status']='SUCCESS'
            for local,arm in enumerate(value['arms']):
                method=arm['strategy'];status='TIMEOUT' if timeout_method==method else 'SUCCESS';index=2*gate.CASES.index(case)+local
                outcome='timeout_feasible_only' if status=='TIMEOUT' else 'infimum_unattained' if unattained else 'attained_optimum'
                identity=dict(case_id=case,strategy=method,method=method,arm_index=str(index),manifest_sha256='sha',common_sha256=base.file_hash(target),source_closure_sha256='a'*64,
                    experiment_schema=gate.SCHEMA,completion_policy_sha256=base.digest(gate.COMPLETION_POLICY))
                arm.update(status=outcome,receipt=dict(status=status,reason='phase_timeout' if status=='TIMEOUT' else 'success',cleanup_verified=True,phase_entered_monotonic=1,phase_budget=dict(seconds=600,identity=identity)),verification=dict(status='SUCCESS',cleanup_verified=True))
                value['stages'][1+2*local]['status']=status;value['stages'][2+2*local]['status']='SUCCESS'
            pipelines[case]=value
        ledger=dict(status='COMPLETED',denominator=10,pipelines=pipelines,stages=[r for c in gate.CASES for r in pipelines[c]['stages']],arms=[r for c in gate.CASES for r in pipelines[c]['arms']])
        def load(directory,receipt,operation,case,method=None):
            if operation=='prepare':return dict(case_id=case,seed={'max_depth':gate.ORIGINAL_HMAX[case]})
            completed,full=terminal_fixture(method,'infimum_unattained' if unattained else 'attained_optimum')
            completed['Hmax']=completed['result']['H_ref']=gate.ORIGINAL_HMAX[case]
            completed['case_binding_sha256']=full['case_binding_sha256']=base.digest(gate.SPECS[case])
            if method==timeout_method:full.update(search_status='TIMEOUT',status='timeout_feasible_only')
            return full if operation=='verify' else completed
        return manifest,ledger,load

    def test_pair_admission_compares_full_keys_or_unattained_components_and_keeps_timeouts_censored(self):
        for timeout,unattained in ((None,False),('flat',False),(None,True)):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest,ledger,load=self.matched_fixture(root,timeout_method=timeout,unattained=unattained)
                with patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_coordinator',return_value=ledger),patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',return_value={}):
                    result=gate.run_gate('m','sha',root)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['all_pairs_authenticated_complete'],timeout is None)
            self.assertEqual(result['denominator'],10);self.assertEqual(len(result['stages']),10)
        for failure in ('phase','method','common','key_disagreement','infimum_disagreement','hmax','observer','denominator','status_disagreement'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest,ledger,load=self.matched_fixture(root,unattained=failure=='infimum_disagreement')
                if failure=='phase':ledger['arms'][0]['receipt']['phase_budget']['seconds']=240
                if failure=='method':ledger['arms'][0]['receipt']['phase_budget']['identity']['method']='hier'
                if failure=='common':ledger['arms'][0]['receipt']['phase_budget']['identity']['common_sha256']='0'*64
                if failure=='denominator':ledger['pipelines'][gate.CASES[0]]['denominator']=4
                def broken(directory,receipt,operation,case,method=None):
                    value=load(directory,receipt,operation,case,method)
                    if method=='flat' and case==gate.CASES[0]:
                        if failure=='key_disagreement' and operation!='prepare':
                            value['accepted_key'][0]='9'
                            if operation=='arm':value['result']['result'].update(J='9',lex_key=value['accepted_key'])
                        if failure=='infimum_disagreement' and operation=='arm':value['result']['result']['primary_infimum']='6'
                        if failure=='status_disagreement' and operation=='verify':value['status']='infimum_unattained'
                        if failure=='hmax' and operation=='arm':value['Hmax']=32
                    return value
                with patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_coordinator',return_value=ledger),patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',side_effect=ValueError('final observer failed') if failure=='observer' else None,return_value={}):
                    result=gate.run_gate('m','sha',root)
                self.assertFalse(result['operational_admission'],failure);self.assertFalse(result['all_pairs_authenticated_complete'],failure)
                self.assertEqual(len(result['stages']),10);self.assertEqual(result['denominator'],10)

    def test_tiny_native_both_methods_explicit_singleton_and_fresh_full_replay(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import post_service_dominance
        from timecut5.remaining_charge_runtime import RemainingChargeRuntimeV1
        from experiments.remaining_charge_gate_v1.singleton import RemainingChargeSingletonBound
        answers={}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for method in gate.METHODS:
                domain=tiny_domain(root/method,method)
                with adapter.historical_operators(),domain.context('verification') as context:witness=_solve_problem(domain.problem(context),True).result.witness
                seed=domain.freeze_seed(witness);out=root/(method+'-result')
                with patch.object(post_service_dominance,'make_post_service_reducer',wraps=post_service_dominance.make_post_service_reducer) as factory:
                    result=domain.run_arm(method,seed,out,search_seconds=15);factory.assert_called_once()
                    args=factory.call_args;self.assertIs(type(args.kwargs['runtime']),RemainingChargeRuntimeV1)
                    self.assertIs(args.kwargs['runtime']._problem,args.args[0]);self.assertTrue(args.kwargs['enabled']);self.assertTrue(args.kwargs['completed_departure_layers'])
                    fresh=tiny_domain(root/(method+'-fresh'),method);recovered=fresh.recover_durable(seed,out/'incumbent.json');factory.assert_called_once()
                self.assertEqual(result['accepted_key'],recovered['accepted_key']);self.assertEqual(result['status'],'attained_optimum')
                self.assertEqual(result['Hmax'],seed.max_depth);self.assertEqual(recovered['post_service_cohort_arm'],method)
                with fresh.context('verification') as context:self.assertEqual(context.router.mode,'full')
                if method=='flat':
                    self.assertIsInstance(domain._singleton,RemainingChargeSingletonBound);self.assertGreater(result['singleton_bound_statistics']['calls'],0)
                else:self.assertIsNone(domain._singleton)
                self.assertGreater(result['post_service_statistics']['strong_calls'],0);self.assertGreater(result['analytic_charge_statistics']['analytic_builds'],0)
                gate.validate_post_service_statistics(result['post_service_statistics'],method,completed=True)
                gate.validate_combined_statistics(result['projection_support_statistics'],result['analytic_charge_statistics'],method,completed=True)
                cohort.validate_singleton_statistics(result['singleton_bound_statistics'],method,completed=True)
                snapshot=json.loads((out/'progress/progress.json').read_bytes())
                self.assertEqual(snapshot['method'],method)
                for key in ('post_service_statistics','analytic_charge_statistics','completion_policy'):self.assertEqual(snapshot[key],result[key])
                other='hier' if method=='flat' else 'flat'
                with self.assertRaises(ValueError):domain.run_arm(other,seed,root/'wrong-arm')
                with self.assertRaisesRegex(ValueError,'method'):tiny_domain(root/(method+'-wrong'),other).recover_durable(seed,out/'incumbent.json')
                answers[method]=result['accepted_key']
            self.assertEqual(answers['flat'],answers['hier'])

    def test_progress_chain_final_statistics_health_and_timeout_censoring(self):
        common=common_fixture();manifest=dict(gate.prospective(),source={'closure_sha256':'c'*64})
        for arm in gate.ARMS:
            support=counts(True,builds=0);analytic=analytic_counts(True,analytic=3,generic=0)
            singleton=None if arm=='hier' else dict(schema=POLICY_SCHEMA,runtime_enabled=True,calls=0,original_none=0,active_calls=0,disabled_calls=0,strengthened_calls=0)
            post=final_reducer_counts(gate.CONFIGS[arm]['post_service_dominance'])
            inner=admission_fixture('support_on',common);domain,sources=gate.progress_binding(manifest,arm,gate.CASES[0],common)
            value=dict(echo(inner),profile_schema=projection.SCHEMA,arm='support_on',configuration=projection.CONFIGS['support_on'],
                manifest_binding=base.digest(manifest),candidate_count=128,query_sha256=base.digest(common['query']),
                Hmax=2,status='returned',io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
                cohort_schema=cohort.SCHEMA,method=arm,shared_configuration=manifest['shared_configuration'],case_binding_sha256=base.digest(gate.SPECS[gate.CASES[0]]),
                method_policy=adapter.METHOD_POLICY,domain_sha256=domain,source_sha256=sources,
                projection_support_statistics=support,envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=singleton,
                post_service_cohort_schema=gate.SCHEMA,post_service_cohort_arm=arm,post_service_cohort_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
                completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,analytic_charge_statistics=analytic,post_service_statistics=post)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json'
                ip=root/'remaining_charge_admission.json';mp=root/'method_admission.json';ap=root/'post_service_cohort_admission.json'
                ip.write_bytes(base.canonical(inner));value['remaining_charge_admission_sha256']=base.file_hash(ip)
                method=gate.method_admission(base.digest(manifest),arm,manifest['shared_configuration'],gate.SPECS[gate.CASES[0]],base.file_hash(ip))
                mp.write_bytes(base.canonical(method));value['method_admission_sha256']=base.file_hash(mp)
                outer=adapter.outer_admission(base.digest(manifest),arm,base.file_hash(mp))
                ap.write_bytes(base.canonical(outer));value['post_service_cohort_admission_sha256']=base.file_hash(ap);path.write_bytes(base.canonical(value))
                result=dict(schema=gate.SCHEMA,strategy=arm,method=arm,inner_arm='support_on',case_binding_sha256=base.digest(gate.SPECS[gate.CASES[0]]),
                    shared_configuration=manifest['shared_configuration'],method_policy=adapter.METHOD_POLICY,method_admission_sha256=base.file_hash(mp),
                    remaining_charge_admission_sha256=base.file_hash(ip),progress_sha256=base.file_hash(path),remaining_charge_activation_wall_ns=123,
                    time_policy=projection.TIME_POLICIES['support_on'],configuration=projection.CONFIGS['support_on'],manifest_binding=base.digest(manifest),
                    observer=dict(status='returned',io_error=None,heartbeat_error=None),projection_support_policy=projection.SUPPORT_POLICY,
                    projection_support_statistics=support,envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=singleton,
                    post_service_cohort_arm=arm,post_service_cohort_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
                    completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,analytic_charge_statistics=analytic,post_service_statistics=post,post_service_cohort_admission_sha256=base.file_hash(ap))
                read=lambda status,final=None:gate.read_progress(path,manifest,arm,gate.CASES[0],common,search_status=status,completed_result=final)
                self.assertTrue(read('SUCCESS',result)['terminal_observer_health_proved'])
                self.assertFalse(read('TIMEOUT')['terminal_observer_health_proved'])
                for mutate in [lambda x:x.update(method='hier' if arm=='flat' else 'flat'),lambda x:x.update(post_service_cohort_arm='post_service_on'),
                    lambda x:x.update(progress_sha256='0'*64),lambda x:x['observer'].update(io_error='OSError'),
                    lambda x:x['post_service_statistics'].update(calls=99),lambda x:x.update(post_service_policy={}),lambda x:x.update(analytic_charge_policy={}),lambda x:x.update(completion_policy={})]:
                    bad=copy.deepcopy(result);mutate(bad)
                    with self.assertRaises(ValueError):read('SUCCESS',bad)
                live=copy.deepcopy(value);live['post_service_statistics']['calls']=99
                path.write_bytes(base.canonical(live));sample=read('TIMEOUT')
                self.assertTrue(sample['timeout_snapshot_is_censored']);self.assertFalse(sample['terminal_observer_health_proved'])
                bad=copy.deepcopy(result);bad.update(progress_sha256=base.file_hash(path),post_service_statistics=live['post_service_statistics'])
                with self.assertRaisesRegex(ValueError,'conserve'):read('SUCCESS',bad)
                path.write_bytes(base.canonical(value));ap.write_bytes(base.canonical(dict(outer,method='hier' if arm=='flat' else 'flat')))
                with self.assertRaisesRegex(ValueError,'Outer post-service'):read('TIMEOUT')


if __name__=='__main__':unittest.main()
