"""Tiny/synthetic analytic gate admission, scope and exact-key checks."""
import copy
from dataclasses import asdict
from fractions import Fraction as F
import json
from pathlib import Path
import resource
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

# Explicit fixture imports do not select or override the production package.
_TESTS=Path(__file__).resolve().parents[1]
for _path in (_TESTS,_TESTS/'m5d_recovery'):
    if str(_path) not in sys.path:sys.path.append(str(_path))

from experiments.analytic_charge_gate_v1 import run as gate
from experiments.analytic_charge_gate_v1 import domain as adapter
from experiments.dev_cohort_v1 import run as cohort
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from test_envelope_sweep_gate import envelope_counts
from timecut5.analytic_charge import AnalyticCharge
from timecut5.provenance import encoded


def analytic_counts(enabled,considered=3,skipped=0,analytic=0,generic=3,fallback=0):
    return dict(enabled=enabled,considered_pairs=considered,support_skipped_pairs=skipped,
        analytic_builds=analytic,generic_projection_builds=generic,recorded_fallback_builds=fallback)


def tiny_domain(root,arm):
    old=support_domain(root/'original','support_on')
    return adapter.AnalyticDomain(arm=arm,case_binding={'case_id':'tiny','candidate_count':len(old.sites)},
        manifest_binding=base.digest('tiny analytic gate'),graph_factory=old.graph_factory,query=json.loads(old.query_bytes),
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
        value=dict(status=outcome,method='hier',strategy=arm,analytic_arm=arm,accepted_key=['8','1',1,[['s','C']]],
            analytic_schema=gate.SCHEMA,analytic_configuration=gate.CONFIGS[arm],analytic_policy=gate.ANALYTIC_POLICY,
            case_binding_sha256=base.digest(gate.SPECS[case]))
        if operation=='verify':return dict(value,search_status=status)
        return dict(value,Hmax=33,result=dict(H_ref=33,result=dict(status='attained_optimum',J='8',Q_total='1',H=1,
            site_action_tuple=[['s','C']],lex_key=['8','1',1,[['s','C']]])))
    return manifest,ledger,load


class AnalyticChargeGateTests(unittest.TestCase):
    def test_fixed_original_domain_and_one_factor_policy(self):
        plan=gate.prospective();a,b=[copy.deepcopy(gate.CONFIGS[x]) for x in gate.ARMS]
        self.assertFalse(a.pop('analytic_charge'));self.assertTrue(b.pop('analytic_charge'));self.assertEqual(a,b)
        self.assertEqual(a['method'],'hier');self.assertEqual(a['inner_arm'],'support_on')
        shared=a['shared_configuration'];self.assertFalse(shared['envelope_sweep']);self.assertTrue(shared['projection_support'])
        self.assertEqual(shared['time_quantum_exponent'],10)
        self.assertEqual((plan['case_id'],plan['candidate_count'],plan['historical_hmax']),(gate.CASE,128,33))
        self.assertEqual(plan['case_binding'],cohort.SPECS[gate.CASE]);self.assertEqual(plan['denominator']['total_stages'],5)
        self.assertEqual(plan['reserve_plan']['total_exact_search_seconds'],480);self.assertEqual(plan['limits']['search_seconds'],240)
        self.assertFalse(plan['launchable']);self.assertFalse(plan['automatic_next_run']);self.assertFalse(plan['holdout']);self.assertFalse(plan['outcome_blind'])
        with tempfile.TemporaryDirectory() as temp:
            for mutate in [lambda x:x.update(method='flat'),lambda x:x.update(historical_hmax=4),
                lambda x:x['shared_configuration'].update(envelope_sweep=True),lambda x:x['arms']['analytic_on'].update(analytic_charge=1),
                lambda x:x.update(candidate_count=32),lambda x:x.update(max_heavy_workers=2)]:
                bad=copy.deepcopy(plan);bad['launchable']=True;mutate(bad);path=Path(temp)/'m.json';path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_original_hmax_and_schema_fail_before_graph(self):
        common=dict(schema=gate.SCHEMA,case_id=gate.CASE,candidate_count=128,case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),seed=dict(max_depth=4))
        with patch.object(base,'original_tree') as tree,self.assertRaisesRegex(ValueError,'BLOCKED_SEED_HMAX_MISMATCH'):
            gate.validate_common(common,gate.CASE,gate.prospective())
        tree.assert_not_called()
        with self.assertRaisesRegex(ValueError,'schema/case'):gate.validate_common(dict(common,schema=cohort.SCHEMA),gate.CASE,gate.prospective())

    def test_combined_generic_truth_c_only_accounting_and_censoring(self):
        # One CS generic build plus three C pairs: one skip, two analytic.
        support=counts(True,considered=4,empty=1,builds=1)
        analytic=analytic_counts(True,considered=3,skipped=1,analytic=2,generic=0)
        gate.validate_combined_statistics(support,analytic,'analytic_on',completed=True)
        self.assertEqual(len(support),5);self.assertEqual(support['projection_builds'],1)
        with self.assertRaises(ValueError):projection.validate_support_statistics(support,'support_on',completed=True)
        gate.validate_combined_statistics(counts(True),analytic_counts(False),'analytic_off',completed=True)
        live=dict(analytic,considered_pairs=99)
        gate.validate_combined_statistics(support,live,'analytic_on',completed=False)
        with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_combined_statistics(support,live,'analytic_on',completed=True)
        for mutate in [lambda x:x.update(enabled=1),lambda x:x.update(generic_projection_builds=True),
            lambda x:x.update(analytic_builds=-1),lambda x:x.update(extra=0)]:
            bad=copy.deepcopy(analytic);mutate(bad)
            with self.assertRaises(ValueError):gate.validate_combined_statistics(support,bad,'analytic_on',completed=False)
        for bad in [analytic_counts(False,analytic=1),analytic_counts(False,fallback=1)]:
            with self.assertRaises(ValueError):gate.validate_combined_statistics(counts(True),bad,'analytic_off',completed=False)
        with self.assertRaises(ValueError):gate.validate_combined_statistics(counts(True),analytic_counts(True,fallback=4),'analytic_on',completed=True)

    def test_historical_context_restores_ambient_and_callback_scope(self):
        from timecut5 import analytic_charge,pwa,envelope_sweep
        with AnalyticCharge(enabled=True) as ambient:
            with adapter.historical_operators():
                self.assertFalse(analytic_charge._active.get().enabled)
                self.assertFalse(pwa._projection_support_prefilter.get().enabled);self.assertFalse(envelope_sweep._active.get().enabled)
            self.assertIs(analytic_charge._active.get(),ambient)
            with self.assertRaisesRegex(RuntimeError,'fixture'):
                with adapter.historical_operators():raise RuntimeError('fixture')
            self.assertIs(analytic_charge._active.get(),ambient)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('remaining_charge_admission','method_admission','analytic_admission'):(root/(name+'.json')).write_bytes(b'{}')
            domain=SimpleNamespace(outer_arm='analytic_on',outer_config=adapter.CONFIGS['analytic_on'],method='hier',
                config=projection.CONFIGS['support_on'],shared_configuration=cohort.shared_configuration(False),case_binding={},
                _seed=SimpleNamespace(max_depth=2),_output=root,query_bytes=b'{}',sites={},tree=None,_search_provider=None,
                manifest_binding='m',_activation_wall_ns=0,_activation_receipt={'time_admission':{}},_singleton=None,
                durable_binding=lambda seed:dict(domain_sha256='b'*64,source_sha256={}))
            seen=[]
            def active():return tuple(p.enabled for p in (analytic_charge._active.get(),pwa._projection_support_prefilter.get(),envelope_sweep._active.get()))
            def store(candidate,key):seen.append(active());raise RuntimeError('verifier')
            def solver(*args,**kwargs):
                seen.append(active())
                with self.assertRaisesRegex(RuntimeError,'verifier'):kwargs['incumbent_hook'](None,(F(1),))
                seen.append(active());return SimpleNamespace(pruned_regions=0)
            with patch('timecut5.hierarchy._solve_hierarchical_problem',side_effect=solver),patch.object(adapter.cohort,'normalize_result',return_value='normalized'):
                self.assertEqual(adapter.AnalyticDomain.solve_exact(domain,None,None,(F(2),),SimpleNamespace(current_upper=F(2)),store),'normalized')
            self.assertEqual(seen,[(True,True,False),(False,False,False),(True,True,False)])
            self.assertIsNone(analytic_charge._active.get());self.assertIsNone(pwa._projection_support_prefilter.get());self.assertIsNone(envelope_sweep._active.get())

    def test_actual_supervisor_preserves_five_slots_and_phase(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest=dict(repo=temp,source={'closure_sha256':'a'*64},limits=gate.LIMITS)
            with patch('experiments.mechanism_recovery_v1.supervisor.run',return_value=dict(status='FAILED')) as launch, \
                patch('os.sched_getaffinity',return_value={1}),patch('os.sched_setaffinity'), \
                patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)),patch('resource.setrlimit'),patch('signal.signal'):
                result=base._run_plan('m','sha',Path(temp)/'gate',1,scope='full_batch',manifest_loader=lambda *a:manifest,
                    fixed_cases=gate.CASES,fixed_pairs=gate.PAIRS,exact_phase_seconds=240)
            self.assertEqual(result['denominator'],5);self.assertEqual(len(result['stages']),5);self.assertEqual(launch.call_count,1)
            self.assertTrue(all(s['status']=='BLOCKED_COMMON_PREPARATION' for s in result['stages'][1:]))

    def test_ledger_completion_timeout_failures_retain_denominator(self):
        for timeout in (False,True):
            manifest,ledger,load=ledger_fixture(timeout)
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger) as run, \
                patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',return_value={}):
                result=gate.run_gate('m','sha',temp,1)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['both_authenticated_complete'],not timeout)
            self.assertEqual(run.call_args.kwargs['exact_phase_seconds'],240);self.assertEqual(run.call_args.kwargs['fixed_cases'],gate.CASES)
        for failure in ('prepare','stop','arm','method','null','disagree','phase','progress','key','secondary','hmax','payload_bool'):
            manifest,ledger,load=ledger_fixture()
            if failure=='prepare':ledger['common'][gate.CASE]['status']='FAILED';ledger['stages'][0]['status']='FAILED'
            if failure=='stop':
                ledger['status']='UNKNOWN'
                for row in ledger['stages'][1:]:row['status']='PENDING'
                for arm in ledger['arms']:arm['status']='PENDING'
            if failure=='phase':ledger['arms'][0]['receipt']['phase_budget']['seconds']=120
            def broken(directory,receipt,operation,case,arm=None):
                value=load(directory,receipt,operation,case,arm)
                if failure=='disagree' and operation in ('arm','verify') and arm=='analytic_on':value['accepted_key'][0]='9'
                if operation=='arm' and arm=='analytic_on':
                    if failure=='arm':value['analytic_arm']='analytic_off'
                    if failure=='method':value['method']='flat'
                    if failure=='null':value['result']=None
                    if failure=='disagree':value['result']['result']['J']='9';value['result']['result']['lex_key'][0]='9'
                    if failure=='key':value['result']['result']['lex_key'][0]='9'
                    if failure=='secondary':value['result']['result']['Q_total']='2'
                    if failure=='hmax':value['result']['H_ref']=4
                    if failure=='payload_bool':value['result']['result']['H']=True
                return value
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger), \
                patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'validate_common'), \
                patch.object(gate,'read_progress',side_effect=ValueError('unhealthy final') if failure=='progress' else None,return_value={}):
                result=gate.run_gate('m','sha',temp,1)
            self.assertFalse(result['operational_admission'],failure);self.assertFalse(result['both_authenticated_complete'],failure)
            self.assertEqual(len(result['stages']),5)

    def test_unattained_payload_is_distinct_from_feasible_durable_key(self):
        _,_,load=ledger_fixture();full=load(None,None,'verify',gate.CASE,'analytic_on');full['status']='infimum_unattained'
        completed=load(None,None,'arm',gate.CASE,'analytic_on');completed['status']='infimum_unattained'
        for payload in (dict(status='primary_unattained',primary_infimum='7'),dict(status='secondary_unattained',J='7',secondary_infimum='0')):
            completed['result']['result']=payload
            self.assertEqual(gate.validate_terminal(completed,full,'analytic_on',33),payload)

    def test_outer_and_inner_progress_chain_final_health_and_censoring(self):
        common=common_fixture();manifest=dict(gate.prospective(),source={'closure_sha256':'c'*64})
        for arm in gate.ARMS:
            enabled=gate.CONFIGS[arm]['analytic_charge']
            support=counts(True,builds=0 if enabled else 3)
            analytic=analytic_counts(enabled,analytic=3 if enabled else 0,generic=0 if enabled else 3)
            inner=admission_fixture('support_on',common);domain,sources=gate.progress_binding(manifest,arm,gate.CASE,common)
            value=dict(echo(inner),profile_schema=projection.SCHEMA,arm='support_on',configuration=projection.CONFIGS['support_on'],
                manifest_binding=base.digest(manifest),candidate_count=128,query_sha256=base.digest(common['query']),
                Hmax=2,status='returned',io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
                cohort_schema=cohort.SCHEMA,method='hier',shared_configuration=manifest['shared_configuration'],case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),
                method_policy=adapter.METHOD_POLICY,domain_sha256=domain,source_sha256=sources,
                projection_support_statistics=support,envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=None,
                analytic_schema=gate.SCHEMA,analytic_arm=arm,analytic_configuration=gate.CONFIGS[arm],analytic_policy=gate.ANALYTIC_POLICY,
                analytic_charge_statistics=analytic)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json'
                ip=root/'remaining_charge_admission.json';mp=root/'method_admission.json';ap=root/'analytic_admission.json'
                ip.write_bytes(base.canonical(inner));value['remaining_charge_admission_sha256']=base.file_hash(ip)
                method=gate.method_admission(base.digest(manifest),'hier',manifest['shared_configuration'],gate.SPECS[gate.CASE],base.file_hash(ip))
                mp.write_bytes(base.canonical(method));value['method_admission_sha256']=base.file_hash(mp)
                outer=adapter.outer_admission(base.digest(manifest),arm,base.file_hash(mp))
                ap.write_bytes(base.canonical(outer));value['analytic_admission_sha256']=base.file_hash(ap);path.write_bytes(base.canonical(value))
                result=dict(schema=gate.SCHEMA,strategy=arm,method='hier',inner_arm='support_on',case_binding_sha256=base.digest(gate.SPECS[gate.CASE]),
                    shared_configuration=manifest['shared_configuration'],method_policy=adapter.METHOD_POLICY,method_admission_sha256=base.file_hash(mp),
                    remaining_charge_admission_sha256=base.file_hash(ip),progress_sha256=base.file_hash(path),remaining_charge_activation_wall_ns=123,
                    time_policy=projection.TIME_POLICIES['support_on'],configuration=projection.CONFIGS['support_on'],manifest_binding=base.digest(manifest),
                    observer=dict(status='returned',io_error=None,heartbeat_error=None),projection_support_policy=projection.SUPPORT_POLICY,
                    projection_support_statistics=support,envelope_sweep_statistics=envelope_counts(False),singleton_bound_statistics=None,
                    analytic_arm=arm,analytic_configuration=gate.CONFIGS[arm],analytic_policy=gate.ANALYTIC_POLICY,
                    analytic_charge_statistics=analytic,analytic_admission_sha256=base.file_hash(ap))
                read=lambda status,final=None:gate.read_progress(path,manifest,arm,gate.CASE,common,search_status=status,completed_result=final)
                self.assertTrue(read('SUCCESS',result)['terminal_observer_health_proved'])
                self.assertFalse(read('TIMEOUT')['terminal_observer_health_proved'])
                for mutate in [lambda x:x.update(method='flat'),lambda x:x.update(analytic_arm=gate.ARMS[not enabled]),
                    lambda x:x.update(progress_sha256='0'*64),lambda x:x['observer'].update(io_error='OSError'),
                    lambda x:x['analytic_charge_statistics'].update(considered_pairs=99),lambda x:x.update(analytic_policy={})]:
                    bad=copy.deepcopy(result);mutate(bad)
                    with self.assertRaises(ValueError):read('SUCCESS',bad)
                # A returned-but-censored sample must not prove final conservation.
                live=copy.deepcopy(value);live['analytic_charge_statistics']['considered_pairs']=99
                path.write_bytes(base.canonical(live));self.assertFalse(read('TIMEOUT')['terminal_observer_health_proved'])
                bad=copy.deepcopy(result);bad.update(progress_sha256=base.file_hash(path),analytic_charge_statistics=live['analytic_charge_statistics'])
                with self.assertRaisesRegex(ValueError,'conserve'):read('SUCCESS',bad)
                path.write_bytes(base.canonical(value))
                ap.write_bytes(base.canonical(dict(outer,method='flat')))
                with self.assertRaisesRegex(ValueError,'Outer analytic'):read('TIMEOUT')
                ap.write_bytes(base.canonical(outer))
                stale=dict(inner,arm='support_off',projection_support_enabled=False);ip.write_bytes(base.canonical(stale))
                method['inner_admission_sha256']=base.file_hash(ip);mp.write_bytes(base.canonical(method))
                outer['method_admission_sha256']=base.file_hash(mp);ap.write_bytes(base.canonical(outer))
                value.update(method_admission_sha256=base.file_hash(mp),remaining_charge_admission_sha256=base.file_hash(ip),
                    analytic_admission_sha256=base.file_hash(ap),projection_support_enabled=False)
                path.write_bytes(base.canonical(value))
                with self.assertRaisesRegex(ValueError,'activation policy'):read('TIMEOUT')

    def test_detached_scalar_observer_statistics(self):
        from timecut5.envelope_sweep import EnvelopeSweep
        from timecut5.pwa import ProjectionSupportPrefilter
        with tempfile.TemporaryDirectory() as temp:
            analytic=AnalyticCharge(enabled=True);support=ProjectionSupportPrefilter(enabled=True);sweep=EnvelopeSweep(enabled=False)
            observer=adapter.AnalyticProgress(Path(temp)/'progress',analytic_charge=analytic,projection_support=support,
                envelope_sweep=sweep,singleton=None,query_sha256='a'*64,domain_sha256='b'*64,source_sha256={})
            before=asdict(analytic.snapshot())
            with analytic,support,sweep:
                with observer:pass
            disk=json.loads((observer.path/'progress.json').read_bytes())
            self.assertEqual(disk['analytic_charge_statistics'],before);self.assertEqual(len(before),6)
            self.assertEqual(len(disk['projection_support_statistics']),5)
            self.assertLessEqual((observer.path/'progress.json').stat().st_size,gate.OBSERVER['max_snapshot_bytes'])
            self.assertEqual(disk['status'],'returned')

    def test_tiny_native_same_seed_key_full_replay_and_outer_binding(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import analytic_charge
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,a) for a in gate.ARMS]
            with domains[0].context('verification') as context:witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[];payloads=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed);out=root/('result-'+domain.outer_arm)
                with AnalyticCharge(enabled=True) as ambient:
                    result=domain.run_arm(domain.outer_arm,seed,out,search_seconds=15)
                    self.assertIs(analytic_charge._active.get(),ambient)
                self.assertEqual(result['method'],'hier');self.assertEqual(result['strategy'],domain.outer_arm);self.assertEqual(result['status'],'attained_optimum')
                self.assertEqual(domain.arm,'support_on');self.assertEqual(result['Hmax'],seed.max_depth)
                record=json.loads((out/'incumbent.json').read_bytes());self.assertEqual(record['payload']['method'],'hier')
                fresh=tiny_domain(root/('fresh-'+domain.outer_arm),domain.outer_arm)
                recovered=fresh.recover_durable(seed,out/'incumbent.json');keys.append(recovered['accepted_key']);payloads.append(result['result'])
                self.assertEqual(result['accepted_key'],keys[-1]);self.assertEqual(recovered['analytic_arm'],domain.outer_arm)
                with fresh.context('verification') as context:self.assertEqual(context.router.mode,'full')
                gate.validate_combined_statistics(result['projection_support_statistics'],result['analytic_charge_statistics'],domain.outer_arm,completed=True)
                self.assertFalse(result['envelope_sweep_statistics']['enabled']);self.assertIsNone(result['singleton_bound_statistics'])
                if domain.outer_arm=='analytic_on':self.assertGreater(result['analytic_charge_statistics']['analytic_builds'],0)
                else:self.assertEqual(result['analytic_charge_statistics']['analytic_builds'],0)
                snapshot=json.loads((out/'progress/progress.json').read_bytes())
                self.assertEqual(snapshot['analytic_charge_statistics'],result['analytic_charge_statistics'])
                self.assertEqual(snapshot['projection_support_statistics'],result['projection_support_statistics'])
                bad=copy.deepcopy(record);bad['payload']['method']='flat'
                import hashlib
                bad['sha256']=hashlib.sha256(encoded(bad['payload']).encode()).hexdigest();path=out/'wrong-method.json';path.write_text(encoded(bad))
                with self.assertRaisesRegex(ValueError,'method tag'):fresh.recover_durable(seed,path)
            self.assertEqual(keys[0],keys[1]);self.assertEqual(payloads[0],payloads[1])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/'result-analytic_on/incumbent.json')
            domains[0].method='flat'
            with self.assertRaises(ValueError):domains[0].check()
            self.assertIsNone(analytic_charge._active.get())


if __name__=='__main__':unittest.main()
