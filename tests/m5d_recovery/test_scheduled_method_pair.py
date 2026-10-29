"""Held method pair: synthetic admission and tiny native graphs, no real run."""
import copy
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

from experiments.scheduled_method_pair_v1 import run as gate
from experiments.scheduled_method_pair_v1 import domain as adapter
from experiments.scheduled_method_pair_v1 import lifecycle
from experiments.dev_cohort_v1 import run as cohort
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from historical_source_fixture import historical_production_source, current_production_source
from test_envelope_sweep_gate import envelope_counts
from test_analytic_charge_gate import analytic_counts
from test_post_service_gate import final_reducer_counts
from test_pending_window_completion import pending_counts as prior_pending_counts
from test_dev_cohort_gate import singleton_counts


def pending_counts(arm):return prior_pending_counts(gate.predecessor.ARMS[0])


def tiny_domain(root,arm):
    from timecut5.real_legs import RealSite
    old=support_domain(root/'original','support_on');query=json.loads(old.query_bytes)
    query['schedule']=dict(a=2,b=30,D=1)
    sites={sid:RealSite(s.site_id,s.anchor_id,('C','S','CS')) for sid,s in old.sites.items()}
    return adapter.ScheduledMethodDomain(arm=arm,case_binding={'case_id':'tiny','candidate_count':len(sites)},
        manifest_binding=base.digest('tiny scheduled method pair'),graph_factory=old.graph_factory,query=query,
        sites=sites,tree=old.tree,source_hashes=old.source_hashes,cache=root/'method',compiler=old.compiler['compiler'])


def terminal_fixture(arm,status='attained_optimum',key=None):
    key=key or ['8','1',1,[['s','CS']]]
    payload=dict(status='attained_optimum',J=key[0],Q_total=key[1],H=key[2],site_action_tuple=key[3],lex_key=key,
        charges=['1'],witness_replayed=True)
    if status=='infimum_unattained':payload=dict(status='primary_unattained',primary_infimum='7')
    value=dict(status=status,method=arm,strategy=arm,pending_window_arm=arm,accepted_key=key,
        pending_window_schema=gate.SCHEMA,pending_window_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
        pending_window_policy=gate.PENDING_WINDOW_POLICY,completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,
        case_binding_sha256=base.digest(gate.SPECS[gate.CASE]))
    return dict(value,Hmax=39,seed_key=key,result=dict(H_ref=39,result=payload)),dict(value,search_status='SUCCESS')


def memory_observation(stage):
    return dict(stage=stage,available_bytes=8*1024**3,required_bytes=7168*1024**2,admitted=True,
        sampled_wall_ns=1,reservation=False,aggregate_hard_limit=False)


class ScheduledMethodPairTests(unittest.TestCase):
    @patch.object(gate,'REVIEW_STATUS','pending_independent_scheduled_method_pair_review')
    def test_fixed_plan_and_pending_review_cannot_freeze_or_consume(self):
        plan=gate.prospective()
        self.assertEqual(gate.ARMS,('flat','hier'));self.assertEqual(plan['methods'],['flat','hier'])
        self.assertEqual(plan['order'],[[gate.CASE,['flat','hier']]])
        self.assertEqual((plan['candidate_count'],plan['historical_hmax']),(128,39))
        self.assertEqual(plan['source_base_commit'],'f89e4f3087c8f11f3fafa2adc116eec5aaed272a')
        self.assertEqual(plan['denominator'],dict(common_preparations=1,search_arms=2,independent_replays=2,total_stages=5))
        self.assertEqual((plan['limits']['search_seconds'],plan['limits']['search_worker_wall_seconds'],plan['limits']['search_worker_cpu_seconds']),(1200,1500,1500))
        self.assertEqual(plan['limits']['parent_cpu_soft_seconds'],180)
        self.assertEqual((plan['reserve_plan']['maximum_worker_wall_seconds'],plan['reserve_plan']['maximum_worker_cpu_soft_seconds']),(3960,3840))
        self.assertEqual(plan['memory_policy']['required_available_memory_bytes'],7168*1024**2)
        self.assertTrue(plan['same_budget_method_comparison']);self.assertEqual(plan['max_heavy_workers'],1)
        for name in ('launchable','automatic_next_run','holdout','historical_pooling','outcome_blind','same_budget_speedup_comparison','historical_treatment_completion_is_paired_result'):
            self.assertIs(plan[name],False,name)
        for arm in gate.ARMS:
            config=plan['arms'][arm];self.assertEqual(config['method'],arm)
            for name in ('pending_window_dominance','post_service_dominance','analytic_charge'):self.assertIs(config[name],True)
            for name in ('convex_charge_count_runtime','operator_compaction_candidate','lazy_native_allocation_backend','service_deadline_screen'):self.assertIs(config[name],False)
            self.assertEqual(config['shared_configuration'],cohort.shared_configuration(False))
        with self.assertRaisesRegex(ValueError,'review is pending'):gate.require_launch_review()
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'m.json'
            with patch.object(sys,'argv',['gate','--freeze','--input-directory',temp,'--output',str(target)]),patch.object(gate,'source_identity') as identity:
                with self.assertRaisesRegex(ValueError,'review is pending'):gate.main()
            identity.assert_not_called();self.assertFalse(target.exists())
            plan['launchable']=True;target.write_bytes(base.canonical(plan))
            with self.assertRaisesRegex(ValueError,'review is pending'):gate._manifest(target,base.file_hash(target))
            for mutate in (lambda x:x['limits'].update(search_seconds=600),lambda x:x['denominator'].update(total_stages=6),
                lambda x:x.update(historical_hmax=38),lambda x:x['arms']['flat'].update(pending_window_dominance=False),
                lambda x:x['memory_policy'].update(required_available_memory_bytes=5120*1024**2),lambda x:x.update(methods=['hier','flat'])):
                bad=copy.deepcopy(plan);mutate(bad);target.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(target,base.file_hash(target))

    def test_future_reviewed_manifest_pins_compiler_inputs_and_closure(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(gate,'REVIEW_STATUS','approved_independent_scheduled_method_pair_review'):
            root=Path(temp);path=root/'m.json';manifest=gate.prospective()
            manifest.update(launchable=True,status='frozen_scheduled_method_pair_not_launched',repo=str(root),input_directory=str(root/'inputs'),
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

    def test_future_freeze_rejects_inherited_engine_failure_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'manifest.json'
            with patch.object(gate,'REVIEW_STATUS','approved_independent_scheduled_method_pair_review'), \
                patch.object(gate.predecessor,'source_identity',side_effect=ImportError('missing actual parquet engine')), \
                patch.object(sys,'argv',['gate','--freeze','--input-directory',temp,'--output',str(target)]):
                with self.assertRaisesRegex(ImportError,'missing actual parquet engine'):gate.main()
            self.assertFalse(target.exists())

    def run_pipeline(self,root,*,outcomes=None,launch_exception=None,cleanup_failure=None,broken_artifact=None,memory_failure=None,hard=resource.RLIM_INFINITY,cpu=0,threads=1):
        manifest=dict(gate.prospective(),repo=str(root),source={'closure_sha256':'a'*64});seen=[];outcomes=outcomes or ['SUCCESS']*5
        observations=[]
        def observe(policy):
            position=len(observations);value=memory_observation('unused');value.pop('stage')
            if position==memory_failure:value.update(available_bytes=7168*1024**2-1,admitted=False)
            observations.append(value);return value
        def launch(argv,*,output_dir,limits,cwd,phase_budget=None):
            op=argv[argv.index('--worker')+1];strategy=argv[argv.index('--strategy')+1] if '--strategy' in argv else None
            position=len(seen);seen.append((op,strategy,limits,phase_budget,argv))
            if position==launch_exception:raise ValueError('injected launch')
            output_dir.mkdir(parents=True,exist_ok=False)
            if op=='prepare':
                target=output_dir/'artifacts/prepared/common.json';target.parent.mkdir(parents=True);target.write_bytes(b'{}')
            (output_dir/'receipt.json').write_bytes(b'{}')
            return dict(status=outcomes[position],cleanup_verified=position!=cleanup_failure)
        def load(*args):
            if len(seen)-1==broken_artifact:raise ValueError('injected artifact failure')
            return dict(status='attained_optimum')
        with patch.object(lifecycle,'run',side_effect=launch),patch.object(lifecycle,'available_memory_admission',side_effect=observe),patch.object(base,'load_worker_result',side_effect=load),patch('os.sched_getaffinity',return_value={0,1,3}),patch('os.sched_setaffinity'),patch('threading.active_count',return_value=threads),patch('resource.getrlimit',side_effect=lambda which:(resource.RLIM_INFINITY,hard if which==resource.RLIMIT_CPU else resource.RLIM_INFINITY)),patch('resource.setrlimit') as setlimit,patch('signal.signal'):
            result=lifecycle.run_plan('m','sha',root/'run',cpu,manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
        return result,seen,setlimit

    def test_five_serial_slots_share_same_original_common_seed_and_fixed_budgets(self):
        for status in ('SUCCESS','TIMEOUT'):
            with tempfile.TemporaryDirectory() as temp:result,seen,setlimit=self.run_pipeline(Path(temp),outcomes=['SUCCESS',status,'SUCCESS',status,'SUCCESS'])
            self.assertEqual(result['status'],'COMPLETED');self.assertEqual(result['denominator'],5)
            self.assertEqual([(r[0],r[1]) for r in seen],[('prepare',None),('arm','flat'),('verify','flat'),('arm','hier'),('verify','hier')])
            self.assertEqual([(r[2].wall_seconds,r[2].cpu_seconds) for r in seen],[(600,600),(1500,1500),(180,120),(1500,1500),(180,120)])
            self.assertEqual(len(result['memory_admissions']),5)
            common=[]
            for op,arm,limits,phase,argv in seen:
                self.assertEqual(limits.cpu,0);self.assertEqual(limits.address_space_bytes,8*1024**3)
                if op!='prepare':common.append((argv[argv.index('--common')+1],argv[argv.index('--common-sha256')+1]))
                if op=='arm':
                    phase.validate();self.assertEqual(phase.seconds,1200);self.assertEqual(phase.identity['method'],arm)
                    self.assertEqual(phase.identity['configuration_sha256'],base.digest(gate.CONFIGS[arm]))
                else:self.assertIsNone(phase)
            self.assertEqual(len(set(common)),1);self.assertEqual(setlimit.call_args.args[1][1],resource.RLIM_INFINITY)

    def test_all_failures_retain_five_slots_and_never_retry(self):
        for position in range(5):
            for failure in ('FAILED','UNKNOWN','launch','cleanup','artifact','memory'):
                outcomes=['SUCCESS']*5;kwargs={}
                if failure in ('FAILED','UNKNOWN'):outcomes[position]=failure
                else:kwargs[dict(launch='launch_exception',cleanup='cleanup_failure',artifact='broken_artifact',memory='memory_failure')[failure]]=position
                with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_pipeline(Path(temp),outcomes=outcomes,**kwargs)
                self.assertNotEqual(result['status'],'COMPLETED',(position,failure));self.assertEqual(len(result['stages']),5)
                self.assertEqual(len(seen),position if failure=='memory' else position+1)
                self.assertFalse(any(r['status']=='PENDING' for r in [*result['stages'],*result['arms']]))
        for kwargs in ({'hard':1500},{'cpu':1},{'threads':2}):
            with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_pipeline(Path(temp),**kwargs)
            self.assertEqual(seen,[]);self.assertEqual(result['status'],'UNKNOWN')

    def test_read_only_memory_observation_floor_and_missing_values_fail_closed(self):
        for available,admitted in ((7168,True),(7167,False)):
            with patch.object(Path,'read_text',return_value=f'MemAvailable: {available*1024} kB\n'):
                value=lifecycle.available_memory_admission(gate.MEMORY_POLICY)
            self.assertIs(value['admitted'],admitted);self.assertFalse(value['reservation']);self.assertFalse(value['aggregate_hard_limit'])
        for text in ('MemTotal: 1 kB\n','MemAvailable: nope kB\n','MemAvailable: 100 B\n'):
            with patch.object(Path,'read_text',return_value=text),self.assertRaises(ValueError):lifecycle.available_memory_admission(gate.MEMORY_POLICY)

    def test_progress_final_health_and_counters_are_method_aware(self):
        common=common_fixture();manifest=dict(gate.prospective(),source={'closure_sha256':'c'*64})
        for arm in gate.ARMS:
            support=counts(True,builds=0);analytic=analytic_counts(True,analytic=3,generic=0)
            post=final_reducer_counts(True);pending=pending_counts(arm);inner=admission_fixture('support_on',common)
            domain,sources=gate.progress_binding(manifest,arm,gate.CASE,common)
            value=dict(echo(inner),profile_schema=projection.SCHEMA,arm='support_on',configuration=projection.CONFIGS['support_on'],
                manifest_binding=base.digest(manifest),candidate_count=128,query_sha256=base.digest(common['query']),Hmax=2,status='returned',
                io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
                cohort_schema=cohort.SCHEMA,method=arm,shared_configuration=manifest['shared_configuration'],case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),
                method_policy=adapter.METHOD_POLICY,domain_sha256=domain,source_sha256=sources,projection_support_statistics=support,
                envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=singleton_counts() if arm=='flat' else None,
                pending_window_schema=gate.SCHEMA,pending_window_arm=arm,pending_window_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
                pending_window_policy=gate.PENDING_WINDOW_POLICY,completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,
                analytic_charge_statistics=analytic,post_service_statistics=post,pending_window_statistics=pending)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json';ip=root/'remaining_charge_admission.json';mp=root/'method_admission.json';ap=root/'pending_window_admission.json'
                ip.write_bytes(base.canonical(inner));value['remaining_charge_admission_sha256']=base.file_hash(ip)
                method=gate.method_admission(base.digest(manifest),arm,manifest['shared_configuration'],gate.SPECS[gate.CASE],base.file_hash(ip))
                mp.write_bytes(base.canonical(method));value['method_admission_sha256']=base.file_hash(mp)
                outer=adapter.outer_admission(base.digest(manifest),arm,base.file_hash(mp));ap.write_bytes(base.canonical(outer));value['pending_window_admission_sha256']=base.file_hash(ap)
                path.write_bytes(base.canonical(value));result=copy.deepcopy(value)
                result.update(schema=gate.SCHEMA,strategy=arm,inner_arm='support_on',progress_sha256=base.file_hash(path),remaining_charge_activation_wall_ns=123,
                    observer=dict(status='returned',io_error=None,heartbeat_error=None),projection_support_policy=projection.SUPPORT_POLICY)
                read=lambda status,final=None:gate.read_progress(path,manifest,arm,gate.CASE,common,search_status=status,completed_result=final)
                self.assertTrue(read('SUCCESS',result)['terminal_observer_health_proved']);self.assertTrue(read('TIMEOUT')['timeout_snapshot_is_censored'])
                for mutate in [lambda x:x.update(method='hier' if arm=='flat' else 'flat'),lambda x:x.update(pending_window_policy={}),
                    lambda x:x.update(progress_sha256='0'*64),lambda x:x['observer'].update(io_error='OSError'),
                    lambda x:x['pending_window_statistics'].update(calls=99),lambda x:x['post_service_statistics'].update(calls=99),
                    lambda x:x.update(singleton_bound_statistics=None if arm=='flat' else singleton_counts())]:
                    bad=copy.deepcopy(result);mutate(bad)
                    with self.assertRaises(ValueError):read('SUCCESS',bad)
                live=copy.deepcopy(value);live['pending_window_statistics']['calls']=99;path.write_bytes(base.canonical(live))
                self.assertFalse(read('TIMEOUT')['terminal_observer_health_proved'])
                bad=copy.deepcopy(result);bad.update(progress_sha256=base.file_hash(path),pending_window_statistics=live['pending_window_statistics'])
                with self.assertRaisesRegex(ValueError,'conserve'):read('SUCCESS',bad)

    def fixture(self,root,timeout=False,unattained=False):
        manifest=dict(gate.prospective(),source={'closure_sha256':'a'*64})
        common_path=root/('prepare-'+gate.CASE)/'artifacts/prepared/common.json';common_path.parent.mkdir(parents=True);common_path.write_bytes(b'{}')
        ledger=lifecycle.pair_ledger('sha');ledger['status']='COMPLETED'
        ledger['common'][gate.CASE]=dict(status='SUCCESS',cleanup_verified=True,wall_seconds=1)
        status='TIMEOUT' if timeout else 'SUCCESS';outcome='timeout_feasible_only' if timeout else 'infimum_unattained' if unattained else 'attained_optimum'
        for index,arm in enumerate(gate.ARMS):
            identity=dict(nonce=f'fixture-{arm}',**gate.phase_identity(manifest,'sha',arm,base.file_hash(common_path)))
            ledger['arms'][index].update(status=outcome,receipt=dict(status=status,reason='phase_timeout' if timeout else 'success',cleanup_verified=True,
                wall_seconds=2,phase_entered_monotonic=1,phase_budget=dict(seconds=1200,identity=identity)),verification=dict(status='SUCCESS',cleanup_verified=True,wall_seconds=3))
        for row,value in zip(ledger['stages'],('SUCCESS',status,'SUCCESS',status,'SUCCESS')):row['status']=value
        ledger['memory_admissions']=[memory_observation(s['id']) for s in ledger['stages']]
        def load(directory,receipt,operation,case,arm=None):
            if operation=='prepare':return dict(seed=dict(max_depth=39,key_bytes=base.canonical(['8','1',1,[['s','CS']]]).decode()))
            completed,full=terminal_fixture(arm,'infimum_unattained' if unattained else 'attained_optimum')
            if timeout:full.update(search_status='TIMEOUT',status='timeout_feasible_only')
            return full if operation=='verify' else completed
        return manifest,ledger,load

    def test_pair_admission_full_keys_proper_unattained_and_timeouts(self):
        for timeout,unattained in ((False,False),(True,False),(False,True)):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest,ledger,load=self.fixture(root,timeout,unattained)
                with patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_plan',return_value=ledger),patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',return_value={}):
                    result=gate.run_gate('m','sha',root,0)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['both_authenticated_complete'],not timeout)
            self.assertEqual([r['standalone_charged_wall_seconds'] for r in result['arms']],[6,6])
            self.assertEqual(result['denominator'],5);self.assertFalse(result['historical_treatment_completion_is_paired_result'])
        for failure in ('phase','method','common','nonce','seed','key','hmax','disagreement','observer','denominator','cleanup','ledger','memory','policy'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest,ledger,load=self.fixture(root)
                search=ledger['arms'][0]['receipt']
                if failure=='phase':search['phase_budget']['seconds']=600
                if failure in ('method','common','nonce'):search['phase_budget']['identity'][dict(method='method',common='common_sha256',nonce='nonce')[failure]]='wrong' if failure!='nonce' else ''
                if failure=='denominator':ledger['denominator']=6
                if failure=='cleanup':ledger['arms'][1]['verification']['cleanup_verified']=False
                if failure=='ledger':ledger['status']='UNKNOWN'
                if failure=='memory':ledger['memory_admissions'][3]['available_bytes']=1
                def broken(directory,receipt,operation,case,arm=None):
                    value=load(directory,receipt,operation,case,arm)
                    if operation=='verify' and failure=='policy':value['completion_policy']={}
                    if operation=='arm':
                        if failure=='seed':value['seed_key'][0]='9'
                        if failure=='key':value['result']['result']['J']='9'
                        if failure=='hmax':value['Hmax']=38
                    if failure=='disagreement' and arm=='hier' and operation!='prepare':
                        value['accepted_key']=['9','1',1,[['s','CS']]]
                        if operation=='arm':value['result']['result'].update(J='9',lex_key=value['accepted_key'])
                    return value
                with patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',side_effect=ValueError('observer failed') if failure=='observer' else None,return_value={}):
                    result=gate.admit_pair(ledger,manifest,'sha',root)
            self.assertFalse(result['operational_admission'],failure);self.assertFalse(result['both_authenticated_complete'],failure)

    def test_canonical_full_keys_and_unattained_schema(self):
        for arm in gate.ARMS:
            for key in (['8','1',True,[['s','CS']]],['16/2','1',1,[['s','CS']]],['8','1',1,[]],['8',1,1,[['s','CS']]]):
                completed,full=terminal_fixture(arm,key=key)
                with self.assertRaises(ValueError):gate.validate_terminal(completed,full,arm,39)
            completed,full=terminal_fixture(arm,'infimum_unattained')
            self.assertEqual(gate.validate_terminal(completed,full,arm,39),dict(status='primary_unattained',primary_infimum='7'))
            for payload in (dict(status='primary_unattained',primary_infimum='14/2'),dict(status='primary_unattained',primary_infimum='-1'),dict(status='primary_unattained',primary_infimum='7',extra='1')):
                bad=copy.deepcopy(completed);bad['result']['result']=payload
                with self.assertRaises(ValueError):gate.validate_terminal(bad,full,arm,39)
            completed['result']['result']=dict(status='secondary_unattained',J='7',secondary_infimum='1/2')
            self.assertEqual(gate.validate_terminal(completed,full,arm,39),dict(status='secondary_unattained',J='7',secondary_infimum='1/2'))

    def test_source_identity_extends_dynamic_closure(self):
        root=Path(__file__).resolve().parents[2]
        production=historical_production_source()
        inherited=dict(closure=dict(production),parquet_engine={'actual_guard':'inherited'})
        with patch.object(gate.predecessor,'source_identity',return_value=inherited):
            identity=gate.source_identity(root)
            self.assertEqual(identity['production_source_commit'],gate.SOURCE_BASE_COMMIT)
            self.assertEqual(identity['parquet_engine'],{'actual_guard':'inherited'})
            for name in ('domain.py','lifecycle.py','run.py'):
                self.assertIn('experiments/scheduled_method_pair_v1/'+name,identity['closure'])
            self.assertEqual(identity['closure_sha256'],base.digest(identity['closure']))
            changed=dict(production,**{'src/timecut5/new_module.py':'changed'})
            with patch.object(gate.predecessor,'source_identity',return_value=dict(closure=changed)):
                updated=gate.source_identity(root)
            self.assertNotEqual(updated['closure_sha256'],identity['closure_sha256'])
            self.assertEqual(updated['production_source_entries'],len(production)+1)
        self.assertTrue(gate.parquet_engine_identity()['in_memory_roundtrip'])


    def test_tiny_native_both_methods_reducer_wiring_seed_parity_and_fresh_full_replay(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import bounded,hierarchy,pending_window_dominance
        from timecut5.remaining_charge_runtime import RemainingChargeRuntimeV1
        answers=[];seeds=[]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);first=tiny_domain(root/'seed','flat')
            with adapter.historical_operators(),first.context('verification') as context:witness=_solve_problem(first.problem(context),True).result.witness
            for arm in gate.ARMS:
                domain=tiny_domain(root/arm,arm);seed=domain.freeze_seed(witness);seeds.append(seed);out=root/('result-'+arm)
                module=bounded if arm=='flat' else hierarchy;entry='_solve_problem' if arm=='flat' else '_solve_hierarchical_problem';original=getattr(module,entry)
                reducers=[];make_reducer=pending_window_dominance.make_pending_window_reducer
                def record_reducer(*args,**kwargs):
                    value=make_reducer(*args,**kwargs);reducers.append(value);return value
                with patch.object(pending_window_dominance,'make_pending_window_reducer',side_effect=record_reducer) as factory,patch.object(module,entry,wraps=original) as engine:
                    result=domain.run_arm(arm,seed,out,search_seconds=15);factory.assert_called_once();args=factory.call_args
                    self.assertIs(type(args.kwargs['runtime']),RemainingChargeRuntimeV1);self.assertIs(args.kwargs['runtime']._problem,args.args[0])
                    self.assertTrue(args.kwargs['enabled']);self.assertTrue(args.kwargs['post_service_enabled']);self.assertTrue(args.kwargs['completed_departure_layers'])
                    engine.assert_called_once();self.assertIs(engine.call_args.kwargs['reducer'],reducers[0])
                    self.assertIn('singleton_bound' if arm=='flat' else 'bound_provider',engine.call_args.kwargs)
                    fresh=tiny_domain(root/('fresh-'+arm),arm);recovered=fresh.recover_durable(seed,out/'incumbent.json');factory.assert_called_once()
                answers.append(result['accepted_key']);self.assertEqual(result['accepted_key'],recovered['accepted_key'])
                self.assertEqual(result['status'],'attained_optimum');self.assertEqual(recovered['method'],arm)
                with fresh.context('verification') as context:self.assertEqual(context.router.mode,'full')
                if arm=='flat':self.assertIs(domain._singleton.runtime,args.kwargs['runtime'])
                else:self.assertIsNone(domain._singleton)
                gate.validate_post_service_statistics(result['post_service_statistics'],arm,completed=True)
                gate.validate_pending_window_statistics(result['pending_window_statistics'],result['post_service_statistics'],arm,completed=True)
                gate.validate_combined_statistics(result['projection_support_statistics'],result['analytic_charge_statistics'],arm,completed=True)
                cohort.validate_singleton_statistics(result['singleton_bound_statistics'],arm,completed=True)
                self.assertGreater(result['pending_window_statistics']['strong_calls'],0);self.assertGreater(result['post_service_statistics']['strong_calls'],0)
                snapshot=json.loads((out/'progress/progress.json').read_bytes())
                for name in ('pending_window_statistics','post_service_statistics','analytic_charge_statistics','completion_policy'):self.assertEqual(snapshot[name],result[name])
                wrong=tiny_domain(root/('wrong-'+arm),'hier' if arm=='flat' else 'flat')
                with self.assertRaises(ValueError):wrong.recover_durable(seed,out/'incumbent.json')
            self.assertEqual(seeds[0],seeds[1]);self.assertEqual(answers[0],answers[1])


if __name__=='__main__':unittest.main()
