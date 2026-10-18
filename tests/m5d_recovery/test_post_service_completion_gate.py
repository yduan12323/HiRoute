"""Synthetic/tiny-native three-slot600-second completion-gate checks."""
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

from experiments.post_service_completion_gate_v1 import run as gate
from experiments.post_service_completion_gate_v1 import domain as adapter
from experiments.post_service_completion_gate_v1 import lifecycle
from experiments.dev_cohort_v1 import run as cohort
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from test_envelope_sweep_gate import envelope_counts
from test_analytic_charge_gate import analytic_counts
from test_post_service_gate import final_reducer_counts


def tiny_domain(root):
    old=support_domain(root/'original','support_on')
    return adapter.PostServiceCompletionDomain(arm=gate.ARMS[0],case_binding={'case_id':'tiny','candidate_count':len(old.sites)},
        manifest_binding=base.digest('tiny post-service completion'),graph_factory=old.graph_factory,query=json.loads(old.query_bytes),
        sites=old.sites,tree=old.tree,source_hashes=old.source_hashes,cache=root/'completion',compiler=old.compiler['compiler'])


def ledger_fixture(timeout=False):
    manifest=dict(gate.prospective(),source={'closure_sha256':'a'*64})
    arm=gate.ARMS[0];status='TIMEOUT' if timeout else 'SUCCESS';outcome='timeout_feasible_only' if timeout else 'attained_optimum'
    receipt=dict(status=status,reason='phase_timeout' if timeout else 'success',cleanup_verified=True,phase_entered_monotonic=1,
        phase_budget=dict(seconds=600,identity=dict(case_id=gate.CASE,strategy=arm,arm_index='0',manifest_sha256='sha',
            source_closure_sha256='a'*64,experiment_schema=gate.SCHEMA,completion_policy_sha256=base.digest(gate.COMPLETION_POLICY))))
    ledger=dict(status='COMPLETED',denominator=3,
        stages=[dict(id='prepare-'+gate.CASE,operation='prepare',case=gate.CASE,status='SUCCESS'),
            dict(id='search-0',operation='search',case=gate.CASE,strategy=arm,status=status),
            dict(id='verify-0',operation='verify',case=gate.CASE,strategy=arm,status='SUCCESS')],
        arms=[dict(case=gate.CASE,strategy=arm,pair=0,status=outcome,receipt=receipt,verification=dict(status='SUCCESS',cleanup_verified=True))],
        common={gate.CASE:dict(status='SUCCESS',cleanup_verified=True)})
    def load(directory,receipt,operation,case,arm=None):
        if operation=='prepare':return {'case_id':case,'seed':{'max_depth':33}}
        value=dict(status=outcome,method='hier',strategy=arm,post_service_completion_arm=arm,accepted_key=['8','1',1,[['s','C']]],
            post_service_completion_schema=gate.SCHEMA,post_service_completion_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
            completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,case_binding_sha256=base.digest(gate.SPECS[case]))
        if operation=='verify':return dict(value,search_status=status)
        return dict(value,Hmax=33,result=dict(H_ref=33,result=dict(status='attained_optimum',J='8',Q_total='1',H=1,
            site_action_tuple=[['s','C']],lex_key=['8','1',1,[['s','C']]],charges=['1'],witness_replayed=True)))
    return manifest,ledger,load


class CompletionGateTests(unittest.TestCase):
    def test_prospective_fixed_treatment_budgets_and_reviewed_release(self):
        plan=gate.prospective();self.assertEqual(gate.ARMS,('post_service_completion_on',))
        self.assertEqual((plan['candidate_count'],plan['historical_hmax']),(128,33))
        self.assertEqual(plan['case_binding'],cohort.SPECS[gate.CASE]);self.assertEqual(plan['denominator']['total_stages'],3)
        self.assertEqual(plan['baseline_source_commit'],'d7a38c02f83058efe8e710989695407c5f2e9483')
        config=plan['arms'][gate.ARMS[0]]
        self.assertIs(config['analytic_charge'],True);self.assertIs(config['post_service_dominance'],True)
        self.assertIs(config['convex_charge_count_runtime'],False);self.assertIs(plan['completion_policy']['convex_charge_count_runtime'],False)
        shared=config['shared_configuration'];self.assertFalse(shared['envelope_sweep']);self.assertFalse(shared['coalescing'])
        self.assertTrue(shared['projection_support']);self.assertEqual(shared['time_quantum_exponent'],10)
        self.assertEqual(plan['limits']['search_seconds'],600)
        self.assertEqual((plan['limits']['search_worker_wall_seconds'],plan['limits']['search_worker_cpu_seconds']),(900,900))
        self.assertEqual((plan['limits']['stage_wall_seconds'],plan['limits']['worker_cpu_seconds']),(600,600))
        self.assertEqual((plan['limits']['verification_wall_seconds'],plan['limits']['verification_cpu_seconds']),(180,120))
        self.assertEqual(plan['limits']['address_space_bytes'],8*1024**3)
        self.assertEqual((plan['reserve_plan']['total_exact_search_seconds'],plan['reserve_plan']['maximum_worker_wall_seconds'],plan['reserve_plan']['maximum_worker_cpu_soft_seconds']),(600,1680,1620))
        self.assertFalse(plan['launchable']);self.assertFalse(plan['automatic_next_run']);self.assertFalse(plan['holdout'])
        self.assertFalse(plan['same_budget_speedup_comparison']);self.assertTrue(plan['historical_240_results_retained'])
        self.assertEqual(plan['review_status'],'approved_completion_gate_review')
        self.assertIsNone(gate.require_launch_review())
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json'
            with patch.object(gate,'REVIEW_STATUS','pending_completion_gate_review'):
                with self.assertRaisesRegex(ValueError,'review is pending'):gate.require_launch_review()
                bad=gate.prospective();bad['launchable']=True;path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'review is pending'):gate._manifest(path,base.file_hash(path))
                with patch.object(sys,'argv',['gate','--freeze','--input-directory',temp,'--output',str(path)]),patch.object(gate,'source_identity') as identity:
                    with self.assertRaisesRegex(ValueError,'review is pending'):gate.main()
                identity.assert_not_called()
            for mutate in [lambda x:x['limits'].update(search_seconds=240),lambda x:x['limits'].update(search_worker_cpu_seconds=600),
                lambda x:x['completion_policy'].update(exact_phase_seconds=240),lambda x:x['arms'][gate.ARMS[0]].update(convex_charge_count_runtime=True),
                lambda x:x.update(candidate_count=32),lambda x:x.update(historical_hmax=32),lambda x:x.update(same_budget_speedup_comparison=True),
                lambda x:x['denominator'].update(total_stages=5)]:
                bad=copy.deepcopy(plan);bad['launchable']=True;mutate(bad);path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_approved_manifest_path_retains_compiler_source_and_input_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'manifest.json';manifest=gate.prospective()
            manifest.update(launchable=True,status='frozen_post_service_completion_not_launched',repo=str(root),input_directory=str(root/'inputs'),
                compiler=dict(path=str(root/'compiler'),sha256='c'*64,version='pinned compiler\n',flags=['-O3','-std=c++17']),
                source={'closure_sha256':'d'*64})
            path.write_bytes(base.canonical(manifest));digest=base.file_hash(path)
            def pinned_hash(target):
                if Path(target)==cohort.BINDING_PATH:return manifest['cohort_binding_sha256']
                return 'c'*64 if str(target)==manifest['compiler']['path'] else manifest['inputs'][Path(target).name]['sha256']
            def pinned_stat(target):return SimpleNamespace(st_mode=stat.S_IFREG,st_size=manifest['inputs'][target.name]['size'])
            with patch.object(base,'file_hash',side_effect=pinned_hash),patch.object(Path,'stat',pinned_stat), \
                patch.object(gate.subprocess,'check_output',return_value='pinned compiler\n'), \
                patch.object(gate,'source_identity',return_value=manifest['source']) as source:
                self.assertEqual(gate._manifest(path,digest),manifest);source.assert_called_once_with(str(root))
                with patch.object(gate,'source_identity',return_value={'closure_sha256':'0'*64}):
                    with self.assertRaisesRegex(ValueError,'executable closure'):gate._manifest(path,digest)
                with patch.object(gate.subprocess,'check_output',return_value='different compiler\n'):
                    with self.assertRaisesRegex(ValueError,'compiler differs'):gate._manifest(path,digest)
                with patch.object(base,'file_hash',side_effect=lambda target:'0'*64 if Path(target).parent==root/'inputs' else pinned_hash(target)):
                    with self.assertRaisesRegex(ValueError,'input differs'):gate._manifest(path,digest)

    def test_exact_phase_accepts_only_integer600_with_entry_and_phase_timeout(self):
        for status in ('SUCCESS','TIMEOUT'):
            row=dict(status=status,reason='phase_timeout' if status=='TIMEOUT' else 'success',phase_entered_monotonic=1,phase_budget={'seconds':600})
            gate.require_exact_phase(row)
            for mutate in [lambda x:x['phase_budget'].update(seconds=240),lambda x:x['phase_budget'].update(seconds=600.0),
                lambda x:x['phase_budget'].update(seconds=True),lambda x:x.update(phase_entered_monotonic=None),lambda x:x.update(status='FAILED')]:
                bad=copy.deepcopy(row);mutate(bad)
                with self.assertRaisesRegex(ValueError,'600-second'):gate.require_exact_phase(bad)
        with self.assertRaisesRegex(ValueError,'600-second'):
            gate.require_exact_phase(dict(status='TIMEOUT',reason='wall_timeout',phase_entered_monotonic=1,phase_budget={'seconds':600}))

    def run_lifecycle(self,root,outcomes=('SUCCESS','SUCCESS','SUCCESS'),hard=resource.RLIM_INFINITY,broken_artifact=None,launch_exception=None,cleanup_failure=None):
        manifest=dict(gate.prospective(),repo=str(root),source={'closure_sha256':'a'*64});seen=[]
        def launch(argv,*,output_dir,limits,cwd,phase_budget=None):
            op=argv[argv.index('--worker')+1];seen.append((op,limits,phase_budget));position={'prepare':0,'arm':1,'verify':2}[op]
            if op==launch_exception:raise ValueError('injected supervisor preflight exception')
            output_dir.mkdir(parents=True,exist_ok=False)
            if op=='prepare':
                target=output_dir/'artifacts/prepared/common.json';target.parent.mkdir(parents=True);target.write_bytes(b'{}')
            (output_dir/'receipt.json').write_bytes(b'{}')
            return dict(status=outcomes[position],cleanup_verified=op!=cleanup_failure)
        def load(directory,receipt,operation,case,strategy=None):
            if operation==broken_artifact:raise ValueError('tampered worker artifact')
            return dict(status='attained_optimum')
        with patch.object(lifecycle,'run',side_effect=launch),patch.object(base,'load_worker_result',side_effect=load), \
            patch('os.sched_getaffinity',return_value={3}),patch('os.sched_setaffinity'), \
            patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,hard)),patch('resource.setrlimit') as setlimit,patch('signal.signal'), \
            patch.object(base,'_run_plan',side_effect=AssertionError('old hardcoded helper must remain unused')):
            result=lifecycle.run_plan('manifest','sha',root/'run',3,manifest_loader=lambda *a:manifest,expected_limits=gate.LIMITS)
        return result,seen,setlimit

    def test_three_slot_supervision_uses600_phase900_search_and_unchanged_other_caps(self):
        for search in ('SUCCESS','TIMEOUT'):
            with tempfile.TemporaryDirectory() as temp:result,seen,setlimit=self.run_lifecycle(Path(temp),('SUCCESS',search,'SUCCESS'))
            self.assertEqual(result['denominator'],3);self.assertEqual(len(result['stages']),3);self.assertEqual(len(result['arms']),1)
            self.assertEqual(result['status'],'COMPLETED');self.assertEqual([x[0] for x in seen],['prepare','arm','verify'])
            self.assertEqual([(x[1].wall_seconds,x[1].cpu_seconds) for x in seen],[(600,600),(900,900),(180,120)])
            self.assertTrue(all(x[1].address_space_bytes==8*1024**3 for x in seen))
            phase=seen[1][2];self.assertEqual(phase.seconds,600);phase.validate()
            self.assertEqual(phase.identity['experiment_schema'],gate.SCHEMA)
            self.assertEqual(phase.identity['completion_policy_sha256'],base.digest(gate.COMPLETION_POLICY))
            self.assertIsNone(seen[0][2]);self.assertIsNone(seen[2][2])
            self.assertEqual(setlimit.call_args.args[1][1],resource.RLIM_INFINITY)

    def test_all_failures_retain_slots_and_never_retry(self):
        cases=[(('FAILED','SUCCESS','SUCCESS'),1,'FAILED_COMMON_PREPARATION'),
            (('UNKNOWN','SUCCESS','SUCCESS'),1,'UNKNOWN'),(('SUCCESS','FAILED','SUCCESS'),2,'FAILED_SEARCH'),
            (('SUCCESS','UNKNOWN','SUCCESS'),2,'UNKNOWN'),(('SUCCESS','SUCCESS','FAILED'),3,'FAILED_VERIFICATION'),
            (('SUCCESS','SUCCESS','UNKNOWN'),3,'UNKNOWN')]
        for outcomes,count,status in cases:
            with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_lifecycle(Path(temp),outcomes)
            self.assertEqual(result['status'],status);self.assertEqual(len(seen),count);self.assertEqual(len(result['stages']),3)
            self.assertFalse(any(x['status']=='PENDING' for x in result['stages']))
        for operation,count in [('prepare',1),('arm',2),('verify',3)]:
            with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_lifecycle(Path(temp),broken_artifact=operation)
            self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(len(seen),count);self.assertIn('artifact_admission_error',result)
            with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_lifecycle(Path(temp),launch_exception=operation)
            self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(len(seen),count)
            self.assertEqual(result['stages'][count-1]['status'],'UNKNOWN')
            self.assertFalse(any(x['status']=='PENDING' for x in result['stages']))
            self.assertEqual(result['launch_error']['error'],'injected supervisor preflight exception')
            self.assertIs(result['launch_error']['cleanup_verified'],False)
            with tempfile.TemporaryDirectory() as temp:result,seen,_=self.run_lifecycle(Path(temp),cleanup_failure=operation)
            self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(len(seen),count)
            self.assertEqual(result['stages'][count-1]['status'],'UNKNOWN');self.assertIn('cleanup_error',result)
            self.assertFalse(any(x['status']=='PENDING' for x in result['stages']))
        with tempfile.TemporaryDirectory() as temp,self.assertRaisesRegex(ValueError,'901s'):
            self.run_lifecycle(Path(temp),hard=900)
        with tempfile.TemporaryDirectory() as temp:result,_,setlimit=self.run_lifecycle(Path(temp),hard=901)
        self.assertEqual(result['status'],'COMPLETED');self.assertEqual(setlimit.call_args.args[1][1],901)

    def test_completion_ledger_admits_only_fresh_bound_complete_or_censored_evidence(self):
        for timeout in (False,True):
            manifest,ledger,load=ledger_fixture(timeout)
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_plan',return_value=ledger) as run, \
                patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',return_value={}):
                result=gate.run_gate('m','sha',temp,3)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['authenticated_complete'],not timeout)
            self.assertFalse(result['same_budget_speedup_comparison']);self.assertTrue(result['historical_240_results_retained'])
            self.assertEqual(run.call_args.kwargs['expected_limits'],gate.LIMITS)
        for failure in ('denominator','phase','arm','method','hmax','progress','completion_policy','source_identity','payload'):
            manifest,ledger,load=ledger_fixture()
            if failure=='denominator':ledger['denominator']=5
            if failure=='phase':ledger['arms'][0]['receipt']['phase_budget']['seconds']=240
            if failure=='source_identity':ledger['arms'][0]['receipt']['phase_budget']['identity']['source_closure_sha256']='0'*64
            def broken(directory,receipt,operation,case,arm=None):
                value=load(directory,receipt,operation,case,arm)
                if operation=='verify' and failure=='completion_policy':value['completion_policy']={}
                if operation=='arm':
                    if failure=='arm':value['post_service_completion_arm']='post_service_on'
                    if failure=='method':value['method']='flat'
                    if failure=='hmax':value['Hmax']=32
                    if failure=='payload':value['result']['result']['J']='9'
                return value
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(lifecycle,'run_plan',return_value=ledger), \
                patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'validate_common'), \
                patch.object(gate,'read_progress',side_effect=ValueError('bad snapshot') if failure=='progress' else None,return_value={}):
                result=gate.run_gate('m','sha',temp,3)
            self.assertFalse(result['operational_admission'],failure);self.assertFalse(result['authenticated_complete'],failure)
            self.assertEqual(len(result['stages']),3)

    def test_source_closure_includes_new_adapter_module_and_prior_gate(self):
        root=Path(__file__).resolve().parents[2];module='src/timecut5/post_service_dominance.py'
        with patch.object(gate.prior_gate,'source_identity',return_value=dict(closure={module:'m','prior-gate':'p'})), \
            patch.object(gate,'BASELINE_SRC_SHA256',base.digest({module:'m'})):
            identity=gate.source_identity(root)
        names={str(p.relative_to(root)) for p in (root/'experiments/post_service_completion_gate_v1').iterdir() if p.is_file()}
        self.assertTrue(names<=set(identity['closure']));self.assertIn('experiments/post_service_completion_gate_v1/lifecycle.py',identity['closure'])
        self.assertIn('prior-gate',identity['closure']);self.assertEqual(identity['closure_sha256'],base.digest(identity['closure']))
        for metadata in ('old metadata','changed metadata'):
            closure={module:'m','prior-gate':'p','src/hiroute.egg-info/PKG-INFO':metadata,
                'src/hiroute.egg-info/SOURCES.txt':metadata}
            with patch.object(gate.prior_gate,'source_identity',return_value=dict(closure=closure)), \
                patch.object(gate,'BASELINE_SRC_SHA256',base.digest({module:'m'})):
                metadata_identity=gate.source_identity(root)
            self.assertEqual(metadata_identity['closure']['src/hiroute.egg-info/PKG-INFO'],metadata)
            self.assertEqual(metadata_identity['closure_sha256'],base.digest(metadata_identity['closure']))
            self.assertNotEqual(metadata_identity['closure_sha256'],identity['closure_sha256'])
        with patch.object(gate.prior_gate,'source_identity',return_value=dict(closure={module:'m','src/timecut5/convex_runtime.py':'new'})), \
            patch.object(gate,'BASELINE_SRC_SHA256',base.digest({module:'m'})):
            with self.assertRaisesRegex(ValueError,'pre-convex-runtime baseline'):gate.source_identity(root)
        for path in ('src/other.egg-info/runtime.py','src/hiroute.egg-info-runtime.py','src/timecut5/runtime.py'):
            with patch.object(gate.prior_gate,'source_identity',return_value=dict(closure={module:'m',path:'new'})), \
                patch.object(gate,'BASELINE_SRC_SHA256',base.digest({module:'m'})):
                with self.assertRaisesRegex(ValueError,'pre-convex-runtime baseline'):gate.source_identity(root)

    def test_tiny_native_treatment_actual_runtime_and_fresh_full_replay(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import post_service_dominance
        from timecut5.remaining_charge_runtime import RemainingChargeRuntimeV1
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domain=tiny_domain(root)
            with adapter.historical_operators(),domain.context('verification') as context:
                witness=_solve_problem(domain.problem(context),True).result.witness
            seed=domain.freeze_seed(witness);out=root/'result'
            with patch.object(post_service_dominance,'make_post_service_reducer',wraps=post_service_dominance.make_post_service_reducer) as factory:
                result=domain.run_arm(gate.ARMS[0],seed,out,search_seconds=15);factory.assert_called_once()
                args=factory.call_args;self.assertIs(type(args.kwargs['runtime']),RemainingChargeRuntimeV1)
                self.assertIs(args.kwargs['runtime']._problem,args.args[0]);self.assertIs(args.kwargs['enabled'],True)
                self.assertIs(args.kwargs['completed_departure_layers'],True)
                fresh=tiny_domain(root/'fresh');recovered=fresh.recover_durable(seed,out/'incumbent.json');factory.assert_called_once()
            self.assertEqual(result['accepted_key'],recovered['accepted_key']);self.assertEqual(result['status'],'attained_optimum')
            self.assertEqual(result['Hmax'],seed.max_depth);self.assertEqual(recovered['completion_policy'],gate.COMPLETION_POLICY)
            self.assertEqual(recovered['post_service_completion_arm'],gate.ARMS[0])
            with fresh.context('verification') as context:self.assertEqual(context.router.mode,'full')
            self.assertGreater(result['post_service_statistics']['strong_calls'],0)
            self.assertGreater(result['analytic_charge_statistics']['analytic_builds'],0)
            gate.validate_post_service_statistics(result['post_service_statistics'],gate.ARMS[0],completed=True)
            gate.validate_combined_statistics(result['projection_support_statistics'],result['analytic_charge_statistics'],gate.ARMS[0],completed=True)
            snapshot=json.loads((out/'progress/progress.json').read_bytes())
            for key in ('post_service_statistics','analytic_charge_statistics','completion_policy'):
                self.assertEqual(snapshot[key],result[key])
            admission=json.loads((out/'post_service_completion_admission.json').read_bytes())
            self.assertEqual(admission['exact_phase_seconds'],600);self.assertEqual(admission['completion_policy'],gate.COMPLETION_POLICY)
            with self.assertRaises(ValueError):domain.run_arm('post_service_on',seed,root/'wrong-arm')


    def test_progress_chain_final_statistics_health_and_timeout_censoring(self):
        common=common_fixture();manifest=dict(gate.prospective(),source={'closure_sha256':'c'*64})
        for arm in gate.ARMS:
            support=counts(True,builds=0);analytic=analytic_counts(True,analytic=3,generic=0)
            post=final_reducer_counts(gate.CONFIGS[arm]['post_service_dominance'])
            inner=admission_fixture('support_on',common);domain,sources=gate.progress_binding(manifest,arm,gate.CASE,common)
            value=dict(echo(inner),profile_schema=projection.SCHEMA,arm='support_on',configuration=projection.CONFIGS['support_on'],
                manifest_binding=base.digest(manifest),candidate_count=128,query_sha256=base.digest(common['query']),
                Hmax=2,status='returned',io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
                cohort_schema=cohort.SCHEMA,method='hier',shared_configuration=manifest['shared_configuration'],case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),
                method_policy=adapter.METHOD_POLICY,domain_sha256=domain,source_sha256=sources,
                projection_support_statistics=support,envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=None,
                post_service_completion_schema=gate.SCHEMA,post_service_completion_arm=arm,post_service_completion_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
                completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,analytic_charge_statistics=analytic,post_service_statistics=post)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json'
                ip=root/'remaining_charge_admission.json';mp=root/'method_admission.json';ap=root/'post_service_completion_admission.json'
                ip.write_bytes(base.canonical(inner));value['remaining_charge_admission_sha256']=base.file_hash(ip)
                method=gate.method_admission(base.digest(manifest),'hier',manifest['shared_configuration'],gate.SPECS[gate.CASE],base.file_hash(ip))
                mp.write_bytes(base.canonical(method));value['method_admission_sha256']=base.file_hash(mp)
                outer=adapter.outer_admission(base.digest(manifest),arm,base.file_hash(mp))
                ap.write_bytes(base.canonical(outer));value['post_service_completion_admission_sha256']=base.file_hash(ap);path.write_bytes(base.canonical(value))
                result=dict(schema=gate.SCHEMA,strategy=arm,method='hier',inner_arm='support_on',case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),
                    shared_configuration=manifest['shared_configuration'],method_policy=adapter.METHOD_POLICY,method_admission_sha256=base.file_hash(mp),
                    remaining_charge_admission_sha256=base.file_hash(ip),progress_sha256=base.file_hash(path),remaining_charge_activation_wall_ns=123,
                    time_policy=projection.TIME_POLICIES['support_on'],configuration=projection.CONFIGS['support_on'],manifest_binding=base.digest(manifest),
                    observer=dict(status='returned',io_error=None,heartbeat_error=None),projection_support_policy=projection.SUPPORT_POLICY,
                    projection_support_statistics=support,envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=None,
                    post_service_completion_arm=arm,post_service_completion_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
                    completion_policy=gate.COMPLETION_POLICY,analytic_charge_policy=gate.ANALYTIC_POLICY,analytic_charge_statistics=analytic,post_service_statistics=post,post_service_completion_admission_sha256=base.file_hash(ap))
                read=lambda status,final=None:gate.read_progress(path,manifest,arm,gate.CASE,common,search_status=status,completed_result=final)
                self.assertTrue(read('SUCCESS',result)['terminal_observer_health_proved'])
                self.assertFalse(read('TIMEOUT')['terminal_observer_health_proved'])
                for mutate in [lambda x:x.update(method='flat'),lambda x:x.update(post_service_completion_arm='post_service_on'),
                    lambda x:x.update(progress_sha256='0'*64),lambda x:x['observer'].update(io_error='OSError'),
                    lambda x:x['post_service_statistics'].update(calls=99),lambda x:x.update(post_service_policy={}),lambda x:x.update(analytic_charge_policy={}),lambda x:x.update(completion_policy={})]:
                    bad=copy.deepcopy(result);mutate(bad)
                    with self.assertRaises(ValueError):read('SUCCESS',bad)
                live=copy.deepcopy(value);live['post_service_statistics']['calls']=99
                path.write_bytes(base.canonical(live));sample=read('TIMEOUT')
                self.assertTrue(sample['timeout_snapshot_is_censored']);self.assertFalse(sample['terminal_observer_health_proved'])
                bad=copy.deepcopy(result);bad.update(progress_sha256=base.file_hash(path),post_service_statistics=live['post_service_statistics'])
                with self.assertRaisesRegex(ValueError,'conserve'):read('SUCCESS',bad)
                path.write_bytes(base.canonical(value));ap.write_bytes(base.canonical(dict(outer,method='flat')))
                with self.assertRaisesRegex(ValueError,'Outer post-service'):read('TIMEOUT')



if __name__=='__main__':unittest.main()
