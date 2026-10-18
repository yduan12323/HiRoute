"""Synthetic/tiny-native gate bindings, lifecycle and censoring checks."""
import copy
from dataclasses import asdict
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

from experiments.post_service_gate_v1 import run as gate
from experiments.post_service_gate_v1 import domain as adapter
from experiments.dev_cohort_v1 import run as cohort
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from test_envelope_sweep_gate import envelope_counts
from test_analytic_charge_gate import analytic_counts
from timecut5.analytic_charge import AnalyticCharge
from timecut5.post_service_dominance import PostServiceDominanceStatistics


def reducer_counts(enabled,**changes):
    result={n:0 for n in PostServiceDominanceStatistics.__dataclass_fields__}
    result['enabled']=enabled
    result.update(changes)
    return result


def final_reducer_counts(enabled):
    if enabled:
        return reducer_counts(True,calls=2,input_pieces=4,output_pieces=3,strong_calls=1,
            pre_service_fallback_calls=1,arrangement_cells=2,selected_cells=2,
            candidate_visits=4,strict_primary_discarded=1,tied_primary_discarded=1)
    return reducer_counts(False,calls=2,input_pieces=4,output_pieces=3,disabled_fallback_calls=2)


def tiny_domain(root,arm):
    old=support_domain(root/'original','support_on')
    return adapter.PostServiceDomain(arm=arm,case_binding={'case_id':'tiny','candidate_count':len(old.sites)},
        manifest_binding=base.digest('tiny post-service gate'),graph_factory=old.graph_factory,query=json.loads(old.query_bytes),
        sites=old.sites,tree=old.tree,source_hashes=old.source_hashes,cache=root/arm,compiler=old.compiler['compiler'])


def ledger_fixture(timeout=False):
    manifest=dict(gate.prospective(),source={'closure_sha256':'a'*64})
    status='TIMEOUT' if timeout else 'SUCCESS';outcome='timeout_feasible_only' if timeout else 'attained_optimum'
    stages=[dict(id='prepare-'+gate.CASE,operation='prepare',case=gate.CASE,status='SUCCESS')];arms=[]
    for i,arm in enumerate(gate.ARMS):
        receipt=dict(status=status,reason='phase_timeout' if timeout else 'success',cleanup_verified=True,phase_entered_monotonic=1,
            phase_budget=dict(seconds=240,identity=dict(case_id=gate.CASE,strategy=arm,arm_index=str(i),manifest_sha256='sha',source_closure_sha256='a'*64)))
        arms.append(dict(case=gate.CASE,strategy=arm,pair=0,status=outcome,receipt=receipt,verification=dict(status='SUCCESS',cleanup_verified=True)))
        stages.extend([dict(id=f'search-{i}',operation='search',case=gate.CASE,strategy=arm,status=status),
            dict(id=f'verify-{i}',operation='verify',case=gate.CASE,strategy=arm,status='SUCCESS')])
    ledger=dict(status='COMPLETED',denominator=5,stages=stages,arms=arms,
        common={gate.CASE:dict(status='SUCCESS',cleanup_verified=True)})
    def load(directory,receipt,operation,case,arm=None):
        if operation=='prepare':return {'case_id':case,'seed':{'max_depth':33}}
        value=dict(status=outcome,method='hier',strategy=arm,post_service_arm=arm,accepted_key=['8','1',1,[['s','C']]],
            post_service_schema=gate.SCHEMA,post_service_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
            analytic_charge_policy=gate.ANALYTIC_POLICY,case_binding_sha256=base.digest(gate.SPECS[case]))
        if operation=='verify':return dict(value,search_status=status)
        return dict(value,Hmax=33,result=dict(H_ref=33,result=dict(status='attained_optimum',J='8',Q_total='1',H=1,
            site_action_tuple=[['s','C']],lex_key=['8','1',1,[['s','C']]],
            charges=['1' if arm==gate.ARMS[0] else '2'],witness_replayed=True)))
    return manifest,ledger,load


class PostServiceGateTests(unittest.TestCase):
    def test_fixed_original_domain_one_factor_and_reviewed_launch_state(self):
        plan=gate.prospective();a,b=[copy.deepcopy(gate.CONFIGS[x]) for x in gate.ARMS]
        self.assertFalse(a.pop('post_service_dominance'));self.assertTrue(b.pop('post_service_dominance'));self.assertEqual(a,b)
        self.assertIs(a['analytic_charge'],True);self.assertEqual(a['method'],'hier');self.assertEqual(a['inner_arm'],'support_on')
        shared=a['shared_configuration'];self.assertFalse(shared['envelope_sweep']);self.assertTrue(shared['projection_support'])
        self.assertFalse(shared['coalescing']);self.assertEqual(shared['time_quantum_exponent'],10)
        self.assertEqual((plan['case_id'],plan['candidate_count'],plan['historical_hmax']),(gate.CASE,128,33))
        self.assertEqual(plan['case_binding'],cohort.SPECS[gate.CASE]);self.assertEqual(plan['denominator']['total_stages'],5)
        self.assertEqual(plan['reserve_plan']['total_exact_search_seconds'],480);self.assertEqual(plan['limits']['search_seconds'],240)
        self.assertFalse(plan['launchable']);self.assertFalse(plan['automatic_next_run']);self.assertFalse(plan['holdout']);self.assertFalse(plan['outcome_blind'])
        self.assertTrue(plan['post_service_policy']['legacy_product_order_certificate_unchanged'])
        self.assertEqual(plan['post_service_policy']['phase'],'remaining_schedule_equals_zero')
        self.assertEqual(plan['post_service_policy']['reducer_version'],'post-service-total-cut-order-v1')
        self.assertEqual(plan['post_service_policy']['selected_parent_compaction'],
            'identical_original_parent_connected_energy_union_original_callback_retained')
        self.assertEqual(plan['baseline_source_commit'],'46b088e5e62d49a3fbcf22cea1af9f8e72694b36')
        self.assertEqual(plan['review_status'],'approved_proof_and_gate_review')
        self.assertIsNone(gate.require_launch_review())
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json'
            # Pending source revisions retain the launch blocker after release.
            with patch.object(gate,'REVIEW_STATUS','pending_proof_and_gate_review'):
                with self.assertRaisesRegex(ValueError,'review are pending'):gate.require_launch_review()
                bad=gate.prospective();bad['launchable']=True;path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'review are pending'):gate._manifest(path,base.file_hash(path))
                with patch.object(sys,'argv',['gate','--freeze','--input-directory',temp,'--output',str(path)]), \
                    patch.object(gate,'source_identity') as identity,patch.object(gate.shutil,'which') as compiler:
                    with self.assertRaisesRegex(ValueError,'review are pending'):gate.main()
                identity.assert_not_called();compiler.assert_not_called()
            for mutate in [lambda x:x.update(method='flat'),lambda x:x.update(historical_hmax=4),
                lambda x:x['shared_configuration'].update(envelope_sweep=True),lambda x:x['arms'][gate.ARMS[1]].update(analytic_charge=False),
                lambda x:x.update(candidate_count=32),lambda x:x.update(max_heavy_workers=2),
                lambda x:x.update(baseline_source_commit='0'*40),lambda x:x['post_service_policy'].update(default_enabled=True)]:
                bad=copy.deepcopy(plan);bad['launchable']=True;mutate(bad);path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_approved_manifest_path_retains_compiler_source_and_input_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'manifest.json';manifest=gate.prospective()
            manifest.update(launchable=True,status='frozen_post_service_pair_not_launched',repo=str(root),input_directory=str(root/'inputs'),
                compiler=dict(path=str(root/'compiler'),sha256='c'*64,version='pinned compiler\n',flags=['-O3','-std=c++17']),
                source={'closure_sha256':'d'*64})
            path.write_bytes(base.canonical(manifest));digest=base.file_hash(path)
            def pinned_hash(target):
                if Path(target)==cohort.BINDING_PATH:return manifest['cohort_binding_sha256']
                return 'c'*64 if str(target)==manifest['compiler']['path'] else manifest['inputs'][Path(target).name]['sha256']
            def pinned_stat(target):
                return SimpleNamespace(st_mode=stat.S_IFREG,st_size=manifest['inputs'][target.name]['size'])
            with patch.object(base,'file_hash',side_effect=pinned_hash),patch.object(Path,'stat',pinned_stat), \
                patch.object(gate.subprocess,'check_output',return_value='pinned compiler\n'), \
                patch.object(gate,'source_identity',return_value=manifest['source']) as source:
                self.assertEqual(gate._manifest(path,digest),manifest)
                source.assert_called_once_with(str(root))
                with patch.object(gate,'source_identity',return_value={'closure_sha256':'0'*64}):
                    with self.assertRaisesRegex(ValueError,'executable closure'):gate._manifest(path,digest)
                with patch.object(gate.subprocess,'check_output',return_value='different compiler\n'):
                    with self.assertRaisesRegex(ValueError,'compiler differs'):gate._manifest(path,digest)
                with patch.object(base,'file_hash',side_effect=lambda target:'0'*64 if Path(target).parent==root/'inputs' else pinned_hash(target)):
                    with self.assertRaisesRegex(ValueError,'input differs'):gate._manifest(path,digest)

    def test_source_closure_includes_module_new_gate_and_analytic_dependency(self):
        root=Path(__file__).resolve().parents[2];module='src/timecut5/post_service_dominance.py'
        with patch.object(gate.analytic_gate,'source_identity',return_value=dict(closure={module:'m','analytic-dependency':'a'})):
            identity=gate.source_identity(root)
        names={str(p.relative_to(root)) for p in (root/'experiments/post_service_gate_v1').iterdir() if p.is_file()}
        self.assertTrue(names<=set(identity['closure']));self.assertIn(module,identity['closure']);self.assertIn('analytic-dependency',identity['closure'])
        self.assertEqual(identity['closure_sha256'],base.digest(identity['closure']))
        with patch.object(gate.analytic_gate,'source_identity',return_value=dict(closure={})):
            with self.assertRaisesRegex(ValueError,'lacks the reducer'):gate.source_identity(root)

    def test_original_hmax_schema_and_order_reject_before_graph(self):
        common=dict(schema=gate.SCHEMA,case_id=gate.CASE,candidate_count=128,case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),seed=dict(max_depth=4))
        with patch.object(base,'original_tree') as tree,self.assertRaisesRegex(ValueError,'BLOCKED_SEED_HMAX_MISMATCH'):
            gate.validate_common(common,gate.CASE,gate.prospective())
        tree.assert_not_called()
        with self.assertRaisesRegex(ValueError,'schema/case'):gate.validate_common(dict(common,schema=cohort.SCHEMA),gate.CASE,gate.prospective())
        with patch.object(base,'original_tree') as tree,self.assertRaisesRegex(ValueError,'candidate order'):
            gate.domain_factory(gate.prospective(),{},dict.fromkeys(range(128)),None,arm=gate.ARMS[0],case_id=gate.CASE)
        tree.assert_not_called()

    def test_counter_types_fixed_analytic_and_final_only_reducer_identities(self):
        for arm in gate.ARMS:
            gate.validate_combined_statistics(counts(True,builds=0),analytic_counts(True,analytic=3,generic=0),arm,completed=True)
            with self.assertRaises(ValueError):gate.validate_combined_statistics(counts(True),analytic_counts(False),arm,completed=False)
            value=final_reducer_counts(gate.CONFIGS[arm]['post_service_dominance'])
            gate.validate_post_service_statistics(value,arm,completed=True)
            live=dict(value,calls=99)
            gate.validate_post_service_statistics(live,arm,completed=False)
            with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_post_service_statistics(live,arm,completed=True)
            for mutate in [lambda x:x.update(enabled=1),lambda x:x.update(calls=True),lambda x:x.update(candidate_visits=-1),lambda x:x.update(extra=0)]:
                bad=copy.deepcopy(value);mutate(bad)
                with self.assertRaises(ValueError):gate.validate_post_service_statistics(bad,arm,completed=False)
        for values in [dict(strong_calls=1),dict(recorded_fallback_calls=1),dict(parent_run_coalesces=1)]:
            with self.assertRaisesRegex(ValueError,'Disabled'):gate.validate_post_service_statistics(reducer_counts(False,**values),gate.ARMS[0],completed=False)
        for values in [dict(candidate_visits=99),dict(parent_run_coalesces=3),dict(output_pieces=0)]:
            bad=final_reducer_counts(True);bad.update(values)
            with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_post_service_statistics(bad,gate.ARMS[1],completed=True)
        with self.assertRaisesRegex(ValueError,'Enabled'):
            gate.validate_post_service_statistics(reducer_counts(True,calls=1,disabled_fallback_calls=1),gate.ARMS[1],completed=True)
        for bad in [reducer_counts(True,calls=1,strong_calls=1,selected_cells=1,candidate_visits=1,output_pieces=1),
            reducer_counts(True,calls=1,strong_calls=1,arrangement_cells=1,selected_cells=1,candidate_visits=1,output_pieces=2)]:
            gate.validate_post_service_statistics(bad,gate.ARMS[1],completed=False)
            with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_post_service_statistics(bad,gate.ARMS[1],completed=True)
        # Legitimate arrangement splitting can produce more pieces than input.
        split=reducer_counts(True,calls=1,strong_calls=1,input_pieces=1,output_pieces=3,
            arrangement_cells=3,selected_cells=3,candidate_visits=3)
        gate.validate_post_service_statistics(split,gate.ARMS[1],completed=True)

    def test_historical_context_restores_ambient_even_on_callback_error(self):
        from timecut5 import analytic_charge,pwa,envelope_sweep
        with AnalyticCharge(enabled=True) as ambient:
            with adapter.historical_operators():
                self.assertFalse(analytic_charge._active.get().enabled)
                self.assertFalse(pwa._projection_support_prefilter.get().enabled);self.assertFalse(envelope_sweep._active.get().enabled)
            self.assertIs(analytic_charge._active.get(),ambient)
            with self.assertRaisesRegex(RuntimeError,'fixture'):
                with adapter.historical_operators():raise RuntimeError('fixture')
            self.assertIs(analytic_charge._active.get(),ambient)
        for arm in gate.ARMS:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                for name in ('remaining_charge_admission','method_admission','post_service_admission'):(root/(name+'.json')).write_bytes(b'{}')
                domain=SimpleNamespace(outer_arm=arm,outer_config=adapter.CONFIGS[arm],method='hier',
                    config=projection.CONFIGS['support_on'],shared_configuration=cohort.shared_configuration(False),case_binding={},
                    _seed=SimpleNamespace(max_depth=2),_output=root,query_bytes=b'{}',sites={},tree=None,_search_provider=None,
                    manifest_binding='m',_activation_wall_ns=0,_activation_receipt={'time_admission':{}},_singleton=None,
                    durable_binding=lambda seed:dict(domain_sha256='b'*64,source_sha256={}))
                reducer=SimpleNamespace(snapshot=lambda:PostServiceDominanceStatistics(**reducer_counts(gate.CONFIGS[arm]['post_service_dominance'])))
                runtime=object();bound=SimpleNamespace(current_upper=F(2),runtime=runtime);seen=[]
                def active():return tuple(p.enabled for p in (analytic_charge._active.get(),pwa._projection_support_prefilter.get(),envelope_sweep._active.get()))
                def store(candidate,key):seen.append(active());raise RuntimeError('verifier')
                def solver(*args,**kwargs):
                    self.assertIs(kwargs['reducer'],reducer);seen.append(active())
                    with self.assertRaisesRegex(RuntimeError,'verifier'):kwargs['incumbent_hook'](None,(F(1),))
                    seen.append(active());return SimpleNamespace(pruned_regions=0)
                problem=object()
                with patch('timecut5.post_service_dominance.make_post_service_reducer',return_value=reducer) as factory, \
                    patch('timecut5.hierarchy._solve_hierarchical_problem',side_effect=solver), \
                    patch.object(adapter.cohort,'normalize_result',return_value='normalized'):
                    self.assertEqual(adapter.PostServiceDomain.solve_exact(domain,problem,None,(F(2),),bound,store),'normalized')
                factory.assert_called_once_with(problem,enabled=gate.CONFIGS[arm]['post_service_dominance'],completed_departure_layers=True,runtime=runtime)
                self.assertEqual(seen,[(True,True,False),(False,False,False),(True,True,False)])
                self.assertEqual(domain._post_service_statistics,asdict(reducer.snapshot()))
        self.assertIsNone(analytic_charge._active.get());self.assertIsNone(pwa._projection_support_prefilter.get());self.assertIsNone(envelope_sweep._active.get())

    def test_actual_supervisor_preserves_five_slots_without_starting_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest=dict(repo=temp,source={'closure_sha256':'a'*64},limits=gate.LIMITS)
            with patch('experiments.mechanism_recovery_v1.supervisor.run',return_value=dict(status='FAILED')) as launch, \
                patch('os.sched_getaffinity',return_value={3}),patch('os.sched_setaffinity'), \
                patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)),patch('resource.setrlimit'),patch('signal.signal'):
                result=base._run_plan('m','sha',Path(temp)/'gate',3,scope='full_batch',manifest_loader=lambda *a:manifest,
                    worker_module='experiments.post_service_gate_v1.run',fixed_cases=gate.CASES,fixed_pairs=gate.PAIRS,exact_phase_seconds=240)
            self.assertEqual(result['denominator'],5);self.assertEqual(len(result['stages']),5);self.assertEqual(launch.call_count,1)
            self.assertIn('experiments.post_service_gate_v1.run',launch.call_args.args[0])
            self.assertTrue(all(s['status']=='BLOCKED_COMMON_PREPARATION' for s in result['stages'][1:]))

    def test_ledger_admits_complete_or_censored_with_witness_differences(self):
        for timeout in (False,True):
            manifest,ledger,load=ledger_fixture(timeout)
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger) as run, \
                patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',return_value={}):
                result=gate.run_gate('m','sha',temp,3)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['both_authenticated_complete'],not timeout)
            self.assertEqual(run.call_args.kwargs['exact_phase_seconds'],240);self.assertEqual(run.call_args.kwargs['fixed_cases'],gate.CASES)
            self.assertEqual(run.call_args.kwargs['worker_module'],'experiments.post_service_gate_v1.run')

    def test_ledger_retains_failures_and_authenticates_every_layer(self):
        for failure in ('prepare','stop','arm','method','null','disagree','phase','progress','key','secondary','hmax','payload_bool','analytic_policy'):
            manifest,ledger,load=ledger_fixture()
            if failure=='prepare':ledger['common'][gate.CASE]['status']='FAILED';ledger['stages'][0]['status']='FAILED'
            if failure=='stop':
                ledger['status']='UNKNOWN'
                for row in ledger['stages'][1:]:row['status']='PENDING'
                for arm in ledger['arms']:arm['status']='PENDING'
            if failure=='phase':ledger['arms'][0]['receipt']['phase_budget']['seconds']=120
            def broken(directory,receipt,operation,case,arm=None):
                value=load(directory,receipt,operation,case,arm)
                if failure=='disagree' and operation in ('arm','verify') and arm==gate.ARMS[1]:value['accepted_key'][0]='9'
                if operation=='arm' and arm==gate.ARMS[1]:
                    if failure=='arm':value['post_service_arm']=gate.ARMS[0]
                    if failure=='method':value['method']='flat'
                    if failure=='null':value['result']=None
                    if failure=='disagree':value['result']['result']['J']='9';value['result']['result']['lex_key'][0]='9'
                    if failure=='key':value['result']['result']['lex_key'][0]='9'
                    if failure=='secondary':value['result']['result']['Q_total']='2'
                    if failure=='hmax':value['result']['H_ref']=4
                    if failure=='payload_bool':value['result']['result']['H']=True
                if failure=='analytic_policy' and operation=='verify':value['analytic_charge_policy']={}
                return value
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger), \
                patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'validate_common'), \
                patch.object(gate,'read_progress',side_effect=ValueError('unhealthy final') if failure=='progress' else None,return_value={}):
                result=gate.run_gate('m','sha',temp,3)
            self.assertFalse(result['operational_admission'],failure);self.assertFalse(result['both_authenticated_complete'],failure)
            self.assertEqual(len(result['stages']),5)

    def test_unattained_payload_does_not_use_a_feasible_witness_as_infimum(self):
        _,_,load=ledger_fixture();full=load(None,None,'verify',gate.CASE,gate.ARMS[1]);full['status']='infimum_unattained'
        completed=load(None,None,'arm',gate.CASE,gate.ARMS[1]);completed['status']='infimum_unattained'
        for payload in (dict(status='primary_unattained',primary_infimum='7'),dict(status='secondary_unattained',J='7',secondary_infimum='0')):
            completed['result']['result']=payload
            self.assertEqual(gate.validate_terminal(completed,full,gate.ARMS[1],33),payload)
        for payload in [dict(status='primary_unattained'),dict(status='secondary_unattained',J='7'),
            dict(status='primary_unattained',primary_infimum='7',charges=[]),
            *[dict(status='primary_unattained',primary_infimum=x) for x in (True,1,1.0,'nan','1/0','2/2','-1')],
            *[dict(status='secondary_unattained',J=x,secondary_infimum='0') for x in (True,'7.0','-1')],
            *[dict(status='secondary_unattained',J='7',secondary_infimum=x) for x in (None,'1/0','-1')]]:
            completed['result']['result']=payload
            with self.assertRaisesRegex(ValueError,'Unattained'):gate.validate_terminal(completed,full,gate.ARMS[1],33)

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
                post_service_schema=gate.SCHEMA,post_service_arm=arm,post_service_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
                analytic_charge_policy=gate.ANALYTIC_POLICY,analytic_charge_statistics=analytic,post_service_statistics=post)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json'
                ip=root/'remaining_charge_admission.json';mp=root/'method_admission.json';ap=root/'post_service_admission.json'
                ip.write_bytes(base.canonical(inner));value['remaining_charge_admission_sha256']=base.file_hash(ip)
                method=gate.method_admission(base.digest(manifest),'hier',manifest['shared_configuration'],gate.SPECS[gate.CASE],base.file_hash(ip))
                mp.write_bytes(base.canonical(method));value['method_admission_sha256']=base.file_hash(mp)
                outer=adapter.outer_admission(base.digest(manifest),arm,base.file_hash(mp))
                ap.write_bytes(base.canonical(outer));value['post_service_admission_sha256']=base.file_hash(ap);path.write_bytes(base.canonical(value))
                result=dict(schema=gate.SCHEMA,strategy=arm,method='hier',inner_arm='support_on',case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),
                    shared_configuration=manifest['shared_configuration'],method_policy=adapter.METHOD_POLICY,method_admission_sha256=base.file_hash(mp),
                    remaining_charge_admission_sha256=base.file_hash(ip),progress_sha256=base.file_hash(path),remaining_charge_activation_wall_ns=123,
                    time_policy=projection.TIME_POLICIES['support_on'],configuration=projection.CONFIGS['support_on'],manifest_binding=base.digest(manifest),
                    observer=dict(status='returned',io_error=None,heartbeat_error=None),projection_support_policy=projection.SUPPORT_POLICY,
                    projection_support_statistics=support,envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=None,
                    post_service_arm=arm,post_service_configuration=gate.CONFIGS[arm],post_service_policy=gate.POST_SERVICE_POLICY,
                    analytic_charge_policy=gate.ANALYTIC_POLICY,analytic_charge_statistics=analytic,post_service_statistics=post,post_service_admission_sha256=base.file_hash(ap))
                read=lambda status,final=None:gate.read_progress(path,manifest,arm,gate.CASE,common,search_status=status,completed_result=final)
                self.assertTrue(read('SUCCESS',result)['terminal_observer_health_proved'])
                self.assertFalse(read('TIMEOUT')['terminal_observer_health_proved'])
                for mutate in [lambda x:x.update(method='flat'),lambda x:x.update(post_service_arm=gate.ARMS[1] if arm==gate.ARMS[0] else gate.ARMS[0]),
                    lambda x:x.update(progress_sha256='0'*64),lambda x:x['observer'].update(io_error='OSError'),
                    lambda x:x['post_service_statistics'].update(calls=99),lambda x:x.update(post_service_policy={}),lambda x:x.update(analytic_charge_policy={})]:
                    bad=copy.deepcopy(result);mutate(bad)
                    with self.assertRaises(ValueError):read('SUCCESS',bad)
                live=copy.deepcopy(value);live['post_service_statistics']['calls']=99
                path.write_bytes(base.canonical(live));sample=read('TIMEOUT')
                self.assertTrue(sample['timeout_snapshot_is_censored']);self.assertFalse(sample['terminal_observer_health_proved'])
                bad=copy.deepcopy(result);bad.update(progress_sha256=base.file_hash(path),post_service_statistics=live['post_service_statistics'])
                with self.assertRaisesRegex(ValueError,'conserve'):read('SUCCESS',bad)
                path.write_bytes(base.canonical(value));ap.write_bytes(base.canonical(dict(outer,method='flat')))
                with self.assertRaisesRegex(ValueError,'Outer post-service'):read('TIMEOUT')

    def test_progress_snapshot_is_detached_bounded_and_separate(self):
        from timecut5.envelope_sweep import EnvelopeSweep
        from timecut5.pwa import ProjectionSupportPrefilter
        with tempfile.TemporaryDirectory() as temp:
            analytic=AnalyticCharge(enabled=True);support=ProjectionSupportPrefilter(enabled=True);sweep=EnvelopeSweep(enabled=False)
            stats=PostServiceDominanceStatistics(**reducer_counts(True))
            reducer=SimpleNamespace(snapshot=lambda:copy.deepcopy(stats))
            observer=adapter.PostServiceProgress(Path(temp)/'progress',analytic_charge=analytic,post_service=reducer,projection_support=support,
                envelope_sweep=sweep,singleton=None,query_sha256='a'*64,domain_sha256='b'*64,source_sha256={})
            with analytic,support,sweep:
                with observer:pass
            disk=json.loads((observer.path/'progress.json').read_bytes())
            self.assertEqual(disk['post_service_statistics'],asdict(stats));self.assertEqual(disk['analytic_charge_statistics'],asdict(analytic.snapshot()))
            self.assertEqual(len(disk['projection_support_statistics']),5)
            self.assertLessEqual((observer.path/'progress.json').stat().st_size,gate.OBSERVER['max_snapshot_bytes'])
            self.assertEqual(disk['status'],'returned')

    def test_tiny_native_actual_runtime_reducer_and_fresh_physical_replay(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import post_service_dominance
        from timecut5.remaining_charge_runtime import RemainingChargeRuntimeV1
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,a) for a in gate.ARMS]
            # A common witness is generated and replayed using historical operators.
            with adapter.historical_operators(),domains[0].context('verification') as context:
                witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[];answers=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed);out=root/('result-'+domain.outer_arm)
                with patch.object(post_service_dominance,'make_post_service_reducer',wraps=post_service_dominance.make_post_service_reducer) as factory:
                    result=domain.run_arm(domain.outer_arm,seed,out,search_seconds=15)
                    factory.assert_called_once()
                    args=factory.call_args
                    self.assertIs(type(args.kwargs['runtime']),RemainingChargeRuntimeV1)
                    self.assertIs(args.kwargs['runtime']._problem,args.args[0])
                    self.assertTrue(args.kwargs['completed_departure_layers'])
                    self.assertIs(args.kwargs['enabled'],gate.CONFIGS[domain.outer_arm]['post_service_dominance'])
                    fresh=tiny_domain(root/('fresh-'+domain.outer_arm),domain.outer_arm)
                    recovered=fresh.recover_durable(seed,out/'incumbent.json')
                    # Independent replay never creates an experimental reducer.
                    factory.assert_called_once()
                keys.append(recovered['accepted_key']);self.assertEqual(result['accepted_key'],keys[-1])
                self.assertEqual(result['status'],'attained_optimum');self.assertEqual(result['Hmax'],seed.max_depth)
                self.assertEqual(recovered['post_service_arm'],domain.outer_arm)
                self.assertEqual(recovered['analytic_charge_policy'],gate.ANALYTIC_POLICY)
                with fresh.context('verification') as context:self.assertEqual(context.router.mode,'full')
                gate.validate_combined_statistics(result['projection_support_statistics'],result['analytic_charge_statistics'],domain.outer_arm,completed=True)
                gate.validate_post_service_statistics(result['post_service_statistics'],domain.outer_arm,completed=True)
                counters=result['post_service_statistics']
                if domain.outer_arm==gate.ARMS[1]:self.assertGreater(counters['strong_calls'],0)
                else:self.assertEqual(counters['strong_calls'],0);self.assertGreater(counters['disabled_fallback_calls'],0)
                self.assertGreater(result['analytic_charge_statistics']['analytic_builds'],0)
                self.assertEqual(counters['recorded_fallback_calls'],0)
                self.assertFalse(result['envelope_sweep_statistics']['enabled']);self.assertIsNone(result['singleton_bound_statistics'])
                snapshot=json.loads((out/'progress/progress.json').read_bytes())
                for key in ('post_service_statistics','analytic_charge_statistics','projection_support_statistics'):
                    self.assertEqual(snapshot[key],result[key])
                payload=result['result']['result']
                answers.append({k:v for k,v in payload.items() if k not in ('charges','witness_replayed')})
            self.assertEqual(keys[0],keys[1]);self.assertEqual(answers[0],answers[1])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/('result-'+gate.ARMS[1])/'incumbent.json')
            domains[0].outer_config['analytic_charge']=False
            with self.assertRaisesRegex(ValueError,'outer arm'):domains[0].check()


if __name__=='__main__':unittest.main()
