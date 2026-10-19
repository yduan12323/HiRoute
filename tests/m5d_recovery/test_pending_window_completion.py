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

from experiments.pending_window_completion_v1 import run as gate
from experiments.pending_window_completion_v1 import domain as adapter
from experiments.pending_window_completion_v1 import lifecycle
from experiments.dev_cohort_v1 import run as cohort
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from historical_source_fixture import historical_production_source, current_production_source
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
        manifest_binding=base.digest('tiny pending completion'),graph_factory=old.graph_factory,query=query,
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


class PendingCompletionGateTests(unittest.TestCase):
    def test_future_reviewed_manifest_still_pins_compiler_inputs_and_closure(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(gate,'REVIEW_STATUS','approved_independent_completion_gate_review'):
            root=Path(temp);path=root/'m.json';manifest=gate.prospective()
            manifest.update(launchable=True,status='frozen_pending_window_completion_not_launched',repo=str(root),input_directory=str(root/'inputs'),
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
        with patch.object(lifecycle,'run',side_effect=launch),patch.object(base,'load_worker_result',side_effect=load),patch('os.sched_getaffinity',return_value={0,1,3}),patch('os.sched_setaffinity'),patch('resource.getrlimit',side_effect=lambda which:(resource.RLIM_INFINITY,hard if which==resource.RLIMIT_CPU else resource.RLIM_INFINITY)),patch('resource.setrlimit') as setlimit,patch('signal.signal'):
            result=lifecycle.run_plan('m','sha',root/'run',gate.FIXED_CPU,manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
        return result,seen,setlimit


    def test_each_dedicated_arm_pipeline_has_fresh_prepare_then_search_replay(self):
        for arm in gate.ARMS:
            for status in ('SUCCESS','TIMEOUT'):
                with tempfile.TemporaryDirectory() as temp:result,seen,setlimit=self.run_pipeline(Path(temp),arm,outcomes=['SUCCESS',status,'SUCCESS'])
                self.assertEqual(result['status'],'COMPLETED');self.assertEqual(result['denominator'],3)
                self.assertEqual([(r[0],r[1]) for r in seen],[('prepare',None),('arm',arm),('verify',arm)])
                self.assertEqual([(r[2].wall_seconds,r[2].cpu_seconds) for r in seen],[(600,600),(1500,1500),(180,120)])
                for op,_,limits,phase in seen:
                    self.assertEqual(limits.cpu,gate.FIXED_CPU);self.assertEqual(limits.address_space_bytes,8*1024**3)
                    if op=='arm':
                        phase.validate();self.assertEqual(phase.seconds,1200);self.assertEqual(phase.identity['method'],'hier')
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
        with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_pipeline(Path(temp),gate.ARMS[0],hard=1500)
        self.assertEqual(seen,[]);self.assertIn('1501s',result['pipeline_error']['error'])


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
        arm=gate.ARMS[0];old=final_reducer_counts(True);new=pending_counts(arm)
        new.update(calls=3,input_pieces=6,output_pieces=4,strong_calls=1,arrangement_cells=1,selected_cells=1,candidate_visits=2,late_primary_discarded=1,kept_candidate_visits=1)
        gate.validate_pending_window_statistics(new,old,arm,completed=True)
        self.assertNotEqual(old['calls'],new['calls'])
        bad=copy.deepcopy(old);bad['calls']=new['calls']
        with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_pending_window_statistics(new,bad,arm,completed=True)


    def test_exact_phase_and_proper_unattained_components(self):
        for status in ('SUCCESS','TIMEOUT'):
            value=dict(status=status,reason='phase_timeout' if status=='TIMEOUT' else 'success',phase_entered_monotonic=1,phase_budget={'seconds':1200});gate.require_exact_phase(value)
            for mutate in [lambda x:x['phase_budget'].update(seconds=1200.0),lambda x:x['phase_budget'].update(seconds=True),lambda x:x.update(phase_entered_monotonic=None),lambda x:x.update(reason='wall_timeout',status='TIMEOUT')]:
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


    @patch.object(gate,'REVIEW_STATUS','pending_independent_completion_gate_review')
    def test_prospective_exact_treatment_and_blocked_freeze(self):
        plan=gate.prospective();self.assertEqual(gate.ARMS,('pending_completion_on',))
        self.assertEqual((plan['case_id'],plan['candidate_count'],plan['historical_hmax'],plan['method']),
            ('OD06_energy_and_scheduled_soc3_10',128,39,'hier'))
        self.assertEqual(plan['case_binding'],cohort.SPECS[gate.CASE])
        self.assertEqual(plan['source_base_commit'],'02493a4d4248ffc0f96760efd40ed984c8f61a4e')
        self.assertEqual(plan['production_source_entries'],96);self.assertEqual(plan['allowed_new_production_modules'],[])
        self.assertEqual(plan['limits']['search_seconds'],1200)
        self.assertEqual((plan['limits']['search_worker_wall_seconds'],plan['limits']['search_worker_cpu_seconds']),(1500,1500))
        self.assertEqual((plan['limits']['stage_wall_seconds'],plan['limits']['worker_cpu_seconds']),(600,600))
        self.assertEqual((plan['limits']['verification_wall_seconds'],plan['limits']['verification_cpu_seconds']),(180,120))
        self.assertEqual(plan['limits']['address_space_bytes'],8*1024**3)
        self.assertEqual((plan['reserve_plan']['maximum_worker_wall_seconds'],plan['reserve_plan']['maximum_worker_cpu_soft_seconds']),(2280,2220))
        self.assertEqual(plan['denominator'],dict(common_preparations=1,search_arms=1,independent_replays=1,total_stages=3))
        self.assertEqual(plan['execution_policy']['cpu'],0);self.assertEqual(plan['execution_policy']['numeric_threads'],1)
        self.assertEqual(plan['max_heavy_workers'],1)
        for name in ('launchable','automatic_next_run','holdout','historical_pooling','outcome_blind','same_budget_speedup_comparison','matched_control'):
            self.assertIs(plan[name],False,name)
        self.assertTrue(plan['historical_600_results_retained']);self.assertTrue(plan['interrupted_verification_evidence_retained'])
        config=plan['arms'][gate.ARMS[0]]
        self.assertTrue(config['pending_window_dominance']);self.assertTrue(config['post_service_dominance']);self.assertTrue(config['analytic_charge'])
        for name in ('convex_charge_count_runtime','operator_compaction_candidate','service_deadline_screen'):self.assertFalse(config[name])
        shared=config['shared_configuration'];self.assertEqual(shared,cohort.shared_configuration(False))
        self.assertTrue(shared['projection_support']);self.assertFalse(shared['envelope_sweep']);self.assertFalse(shared['coalescing'])
        self.assertEqual(shared['time_quantum_exponent'],10)
        with self.assertRaisesRegex(ValueError,'review is pending'):gate.require_launch_review()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json'
            with patch.object(sys,'argv',['gate','--freeze','--input-directory',temp,'--output',str(path)]),patch.object(gate,'source_identity') as identity:
                with self.assertRaisesRegex(ValueError,'review is pending'):gate.main()
            self.assertFalse(path.exists());identity.assert_not_called()
            plan['launchable']=True;path.write_bytes(base.canonical(plan))
            with self.assertRaisesRegex(ValueError,'review is pending'):gate._manifest(path,base.file_hash(path))
            for mutate in [lambda x:x['limits'].update(search_seconds=600),lambda x:x['limits'].update(search_worker_cpu_seconds=900),
                lambda x:x['completion_policy'].update(exact_phase_seconds=600),lambda x:x['arms'][gate.ARMS[0]].update(pending_window_dominance=False),
                lambda x:x.update(candidate_count=32),lambda x:x.update(historical_hmax=38),lambda x:x.update(same_budget_speedup_comparison=True),
                lambda x:x['denominator'].update(total_stages=6),lambda x:x['execution_policy'].update(cpu=1)]:
                bad=copy.deepcopy(plan);mutate(bad);path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_source_guard_pins_all96_including_pending_module_and_full_closure(self):
        root=Path(__file__).resolve().parents[2]
        production=historical_production_source()
        self.assertEqual(len(production),96);self.assertEqual(base.digest(production),gate.PRODUCTION_SRC_SHA256)
        closure=dict(production,**{'experiments/pending_window_gate_v1/run.py':'prior','src/hiroute.egg-info/PKG-INFO':'metadata'})
        with patch.object(gate.pending_gate,'source_identity',return_value=dict(closure=closure,dependencies={'pyarrow':'26.0.0'})),patch.object(gate,'parquet_engine_identity',return_value={'guard':'ok'}):
            identity=gate.source_identity(root);self.assertEqual(identity['production_source_entries'],96)
            self.assertEqual(identity['parquet_engine'],{'guard':'ok'});self.assertEqual(identity['dependencies'],{'pyarrow':'26.0.0'})
            self.assertEqual(identity['closure_sha256'],base.digest(identity['closure']))
            self.assertIn('experiments/pending_window_completion_v1/lifecycle.py',identity['closure'])
            self.assertEqual(identity['closure']['experiments/pending_window_gate_v1/run.py'],'prior')
            for path in ('src/timecut5/pending_window_dominance.py','src/timecut5/pwa.py','src/timecut5/remaining_charge_runtime.py'):
                bad=dict(closure);bad[path]='changed'
                with patch.object(gate.pending_gate,'source_identity',return_value={'closure':bad}):
                    with self.assertRaisesRegex(ValueError,'96-entry baseline'):gate.source_identity(root)
            for path in ('src/timecut5/lazy_backend.py','src/hiroute.egg-info-runtime.py','src/other.egg-info/runtime.py'):
                with patch.object(gate.pending_gate,'source_identity',return_value={'closure':dict(closure,**{path:'new'})}):
                    with self.assertRaisesRegex(ValueError,'96-entry baseline'):gate.source_identity(root)
            changed=dict(closure);changed['src/hiroute.egg-info/PKG-INFO']='changed metadata'
            with patch.object(gate.pending_gate,'source_identity',return_value={'closure':changed}):
                self.assertNotEqual(gate.source_identity(root)['closure_sha256'],identity['closure_sha256'])
            with patch.object(gate,'parquet_engine_identity',side_effect=ImportError('missing pyarrow')):
                with self.assertRaisesRegex(ImportError,'missing pyarrow'):gate.source_identity(root)

    def test_source_guard_rejects_current_road_policy_tree(self):
        root=Path(__file__).resolve().parents[2]
        production=current_production_source(root)
        self.assertIn('src/graph/raw_way_policy.py',production)
        self.assertEqual(len(production),97)
        self.assertNotEqual(base.digest(production),gate.PRODUCTION_SRC_SHA256)
        with patch.object(gate.pending_gate,'source_identity',return_value={'closure':production}), \
                patch.object(gate,'parquet_engine_identity') as engine:
            with self.assertRaisesRegex(ValueError,'96-entry baseline'):gate.source_identity(root)
            engine.assert_not_called()

    def test_parquet_engine_preflight_imports_real_engine_and_roundtrips_tiny_buffer(self):
        identity=gate.parquet_engine_identity()
        self.assertEqual(identity['engine'],'pandas.io.parquet.PyArrowImpl');self.assertTrue(identity['in_memory_roundtrip'])
        self.assertEqual(set(identity['imported_files']),{'pandas','pandas.io.parquet','pyarrow','pyarrow.parquet','pyarrow._parquet'})
        self.assertEqual(identity,gate.parquet_engine_identity())
        with patch('pandas.io.parquet.get_engine',side_effect=ImportError('engine unavailable')):
            with self.assertRaisesRegex(ImportError,'engine unavailable'):gate.parquet_engine_identity()
        fake=SimpleNamespace()
        with patch('pandas.io.parquet.get_engine',return_value=fake):
            with self.assertRaisesRegex(ValueError,'engine differs'):gate.parquet_engine_identity()
        with patch('pandas.read_parquet',return_value=SimpleNamespace(to_dict=lambda mode:{'guard_value':[2]})):
            with self.assertRaisesRegex(ValueError,'roundtrip differs'):gate.parquet_engine_identity()

    def test_approved_freeze_fails_before_file_creation_if_engine_missing(self):
        closure=historical_production_source()
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'manifest.json'
            with patch.object(gate,'REVIEW_STATUS','approved_independent_completion_gate_review'), \
                patch.object(gate.pending_gate,'source_identity',return_value={'closure':closure}), \
                patch.object(gate,'parquet_engine_identity',side_effect=ImportError('missing pyarrow engine')) as engine, \
                patch.object(sys,'argv',['gate','--freeze','--input-directory',temp,'--output',str(target)]):
                with self.assertRaisesRegex(ImportError,'missing pyarrow engine'):gate.main()
                engine.assert_called_once_with()
            self.assertFalse(target.exists())

    def test_lifecycle_fixed_cpu_preflight_and_single_thread_requirement_keep_slots(self):
        for cpu,threads,hard,as_hard in ((1,1,resource.RLIM_INFINITY,resource.RLIM_INFINITY),
            (0,2,resource.RLIM_INFINITY,resource.RLIM_INFINITY),(0,1,1500,resource.RLIM_INFINITY),
            (0,1,resource.RLIM_INFINITY,8*1024**3-1)):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest=dict(gate.prospective(),repo=str(root),source={'closure_sha256':'a'*64})
                def getrlimit(which):return (resource.RLIM_INFINITY,hard if which==resource.RLIMIT_CPU else as_hard)
                with patch.object(lifecycle,'run') as launch,patch('os.sched_getaffinity',return_value={0,1,2}), \
                    patch('os.sched_setaffinity'),patch('threading.active_count',return_value=threads), \
                    patch('resource.getrlimit',side_effect=getrlimit),patch('resource.setrlimit'),patch('signal.signal'):
                    result=lifecycle.run_plan('m','sha',root/'run',cpu,manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
                launch.assert_not_called();self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(result['denominator'],3)
                self.assertFalse(any(x['status']=='PENDING' for x in [*result['stages'],*result['arms']]))
        with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_pipeline(Path(temp),gate.ARMS[0],hard=1501)
        self.assertEqual(result['status'],'COMPLETED');self.assertEqual(len(seen),3)

    def fixture(self,root,timeout=False,unattained=False):
        manifest=dict(gate.prospective(),source={'closure_sha256':'a'*64});arm=gate.ARMS[0]
        common=root/('prepare-'+gate.CASE)/'artifacts/prepared/common.json';common.parent.mkdir(parents=True);common.write_bytes(b'{}')
        ledger=lifecycle.completion_ledger(arm,'sha');ledger['status']='COMPLETED'
        status='TIMEOUT' if timeout else 'SUCCESS';outcome='timeout_feasible_only' if timeout else 'infimum_unattained' if unattained else 'attained_optimum'
        identity=dict(nonce='fixture',case_id=gate.CASE,strategy=arm,feature_arm=arm,method='hier',arm_index='0',manifest_sha256='sha',
            common_sha256=base.file_hash(common),source_closure_sha256='a'*64,experiment_schema=gate.SCHEMA,
            configuration_sha256=base.digest(gate.CONFIGS[arm]),pending_window_policy_sha256=base.digest(gate.PENDING_WINDOW_POLICY),
            completion_policy_sha256=base.digest(gate.COMPLETION_POLICY))
        ledger['common'][gate.CASE]=dict(status='SUCCESS',cleanup_verified=True)
        ledger['arms'][0].update(status=outcome,receipt=dict(status=status,reason='phase_timeout' if timeout else 'success',cleanup_verified=True,
            phase_entered_monotonic=1,phase_budget=dict(seconds=1200,identity=identity)),verification=dict(status='SUCCESS',cleanup_verified=True))
        for row,value in zip(ledger['stages'],('SUCCESS',status,'SUCCESS')):row['status']=value
        def load(directory,receipt,operation,case,arm=None):
            if operation=='prepare':return physical_common()
            completed,full=terminal_fixture(arm,'infimum_unattained' if unattained else 'attained_optimum')
            if timeout:full.update(search_status='TIMEOUT',status='timeout_feasible_only')
            return full if operation=='verify' else completed
        return manifest,ledger,load

    def test_three_slot_final_admission_bound_success_timeout_and_unattained(self):
        for timeout,unattained in ((False,False),(True,False),(False,True)):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest,ledger,load=self.fixture(root,timeout,unattained)
                with patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_plan',return_value=ledger),patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',return_value={}):
                    result=gate.run_gate('m','sha',root,0)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['authenticated_complete'],not timeout)
            self.assertEqual(result['denominator'],3);self.assertFalse(result['same_budget_speedup_comparison'])
            self.assertTrue(result['historical_600_results_retained']);self.assertTrue(result['interrupted_verification_evidence_retained'])
        for failure in ('phase','method','feature','common_sha','nonce','full_policy','key','hmax','observer','denominator','cleanup','status','ledger'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest,ledger,load=self.fixture(root)
                search=ledger['arms'][0]['receipt']
                if failure=='phase':search['phase_budget']['seconds']=600
                if failure in ('method','feature','common_sha','nonce'):
                    search['phase_budget']['identity'][dict(method='method',feature='feature_arm',common_sha='common_sha256',nonce='nonce')[failure]]='wrong' if failure!='nonce' else ''
                if failure=='denominator':ledger['denominator']=6
                if failure=='cleanup':ledger['arms'][0]['verification']['cleanup_verified']=False
                if failure=='ledger':ledger['status']='UNKNOWN'
                def broken(directory,receipt,operation,case,arm=None):
                    value=load(directory,receipt,operation,case,arm)
                    if operation=='verify':
                        if failure=='full_policy':value['completion_policy']={}
                        if failure=='status':value['status']='infimum_unattained'
                    if operation=='arm':
                        if failure=='key':value['result']['result']['J']='9'
                        if failure=='hmax':value['Hmax']=38
                    return value
                with patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_plan',return_value=ledger),patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',side_effect=ValueError('observer failed') if failure=='observer' else None,return_value={}):
                    result=gate.run_gate('m','sha',root,0)
            self.assertFalse(result['operational_admission'],failure)
            self.assertFalse(result['authenticated_complete'],failure)
            self.assertEqual(len(result['stages']),3)

    def test_tiny_native_treatment_full_replay_and_original_control_same_answer(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import pending_window_dominance
        from timecut5.remaining_charge_runtime import RemainingChargeRuntimeV1
        from test_pending_window_gate import tiny_domain as original_domain
        arm=gate.ARMS[0]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domain=tiny_domain(root/'treatment',arm)
            with adapter.historical_operators(),domain.context('verification') as context:witness=_solve_problem(domain.problem(context),True).result.witness
            seed=domain.freeze_seed(witness);out=root/'result'
            with patch.object(pending_window_dominance,'make_pending_window_reducer',wraps=pending_window_dominance.make_pending_window_reducer) as factory:
                result=domain.run_arm(arm,seed,out,search_seconds=15);factory.assert_called_once();args=factory.call_args
                self.assertIs(type(args.kwargs['runtime']),RemainingChargeRuntimeV1);self.assertIs(args.kwargs['runtime']._problem,args.args[0])
                self.assertTrue(args.kwargs['enabled']);self.assertTrue(args.kwargs['post_service_enabled']);self.assertTrue(args.kwargs['completed_departure_layers'])
                fresh=tiny_domain(root/'fresh',arm);recovered=fresh.recover_durable(seed,out/'incumbent.json');factory.assert_called_once()
            self.assertEqual(result['accepted_key'],recovered['accepted_key']);self.assertEqual(result['status'],'attained_optimum')
            self.assertEqual(recovered['pending_window_schema'],gate.SCHEMA);self.assertEqual(recovered['pending_window_arm'],arm)
            self.assertEqual(recovered['completion_policy'],gate.COMPLETION_POLICY);self.assertIsNone(domain._singleton)
            with fresh.context('verification') as context:self.assertEqual(context.router.mode,'full')
            gate.validate_post_service_statistics(result['post_service_statistics'],arm,completed=True)
            gate.validate_pending_window_statistics(result['pending_window_statistics'],result['post_service_statistics'],arm,completed=True)
            gate.validate_combined_statistics(result['projection_support_statistics'],result['analytic_charge_statistics'],arm,completed=True)
            self.assertGreater(result['post_service_statistics']['strong_calls'],0);self.assertGreater(result['pending_window_statistics']['strong_calls'],0)
            snapshot=json.loads((out/'progress/progress.json').read_bytes())
            for key in ('pending_window_statistics','post_service_statistics','analytic_charge_statistics','pending_window_policy','completion_policy'):
                self.assertEqual(snapshot[key],result[key])
            admission=json.loads((out/'pending_window_admission.json').read_bytes());self.assertEqual(admission['exact_phase_seconds'],1200)
            self.assertEqual(admission['completion_policy'],gate.COMPLETION_POLICY)
            with self.assertRaises(ValueError):domain.run_arm('pending_on',seed,root/'wrong')
            # Tiny old control is only regression QA, never part of the proposed real diagnostic.
            control=original_domain(root/'old-control','pending_off');other=control.freeze_seed(witness);self.assertEqual(seed,other)
            old=control.run_arm('pending_off',other,root/'control-result',search_seconds=15)
            self.assertEqual(result['accepted_key'],old['accepted_key'])
            with self.assertRaises(ValueError):control.recover_durable(other,out/'incumbent.json')


if __name__=='__main__':unittest.main()
