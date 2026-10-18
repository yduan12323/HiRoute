"""Envelope adapter: graph-free admission and tiny native parity only."""
import copy
from dataclasses import asdict
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from experiments.envelope_sweep_gate_v1 import run as gate
from experiments.projection_completion_gate_v1 import run as completion
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from test_projection_completion_gate import terminal_ledger as completion_ledger
from timecut5.envelope_sweep import EnvelopeSweep
from timecut5.pwa import ProjectionSupportPrefilter


def tiny_domain(root,arm):
    old=support_domain(root/'original',gate.INNER_ARM)
    return gate.EnvelopeDomain(arm=arm,manifest_binding=base.digest('tiny envelope manifest'),
        graph_factory=old.graph_factory,query=json.loads(old.query_bytes),sites=old.sites,tree=old.tree,
        source_hashes=old.source_hashes,cache=root/arm,compiler=old.compiler['compiler'])


def envelope_counts(enabled,**kwargs):
    return dict(asdict(EnvelopeSweep(enabled=enabled).snapshot()),**kwargs)


def terminal_ledger(timeout=False):
    _,ledger,load=completion_ledger(timeout)
    manifest=dict(gate.prospective(),source=dict(closure_sha256='a'*64))
    for i,arm in enumerate(gate.ARMS):
        ledger['arms'][i]['strategy']=arm
        ledger['arms'][i]['receipt']['phase_budget']['identity']['strategy']=arm
        for row in ledger['stages'][1+2*i:3+2*i]:row['strategy']=arm
    return manifest,ledger,load


class EnvelopeSweepGateTests(unittest.TestCase):
    def test_only_envelope_changes_and_original240_caps_fixed(self):
        a,b=[copy.deepcopy(gate.CONFIGS[x]) for x in gate.ARMS]
        self.assertFalse(a.pop('envelope_sweep'));self.assertTrue(b.pop('envelope_sweep'));self.assertEqual(a,b)
        self.assertEqual(a['inner_arm'],'support_on');self.assertEqual(a['inner_configuration'],projection.CONFIGS['support_on'])
        inner=a['inner_configuration']
        for key in ('projection_support','terminal_energy','onward_alt','remaining_charge'):self.assertTrue(inner[key])
        self.assertEqual(inner['time_quantum_exponent'],10);self.assertEqual(inner['routing'],'destination_target')
        self.assertEqual(inner['reducer'],'reduce_frontier_skyline')
        plan=gate.prospective();self.assertEqual(plan['limits'],completion.LIMITS);self.assertEqual(plan['reserve_plan'],completion.RESERVE)
        self.assertEqual(plan['reserve_plan']['exact_search_seconds_per_arm'],240);self.assertEqual(plan['reserve_plan']['total_exact_search_seconds'],480)
        self.assertEqual(plan['policy']['original_Hmax'],26);self.assertEqual(plan['candidate_count'],32)
        self.assertEqual(plan['denominator']['total_stages'],5);self.assertFalse(plan['auto_next_gate']);self.assertFalse(plan['holdout'])
        self.assertIs(gate.require_exact_phase,completion.require_exact_phase)
        for mutate in [lambda x:x['arms'][gate.ARMS[1]].update(envelope_sweep=1),
            lambda x:x['limits'].update(search_seconds=120),lambda x:x['arms'][gate.ARMS[0]].update(inner_arm='support_off')]:
            with tempfile.TemporaryDirectory() as temp:
                bad=copy.deepcopy(plan);bad['launchable']=True;mutate(bad);path=Path(temp)/'manifest.json';path.write_bytes(base.canonical(bad))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_live_counts_censored_and_final_completion_conservation(self):
        on=gate.ARMS[1];off=gate.ARMS[0]
        good=envelope_counts(True,calls=1,completed_calls=1,arrangement_cells=3,selected_cells=2)
        gate.validate_envelope_statistics(good,on,completed=True)
        interrupted=dict(good,calls=2)
        gate.validate_envelope_statistics(interrupted,on,completed=False)
        with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_envelope_statistics(interrupted,on,completed=True)
        for bad,arm in [(dict(good,enabled=1),on),(dict(good,calls=True),on),(dict(good,pair_tests=-1),on),
            (dict(good,extra=0),on),(envelope_counts(False,pair_tests=1),off),
            (dict(good,selected_cells=4),on),(dict(good,recorded_fallback_calls=2),on)]:
            with self.assertRaises(ValueError):gate.validate_envelope_statistics(bad,arm,completed=True)

    def test_observer_bounded_detached_both_operator_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            sweep=EnvelopeSweep(enabled=True);support=ProjectionSupportPrefilter(enabled=True)
            observer=gate.EnvelopeProgress(Path(temp)/'progress',envelope_sweep=sweep,projection_support=support,
                query_sha256='a'*64,domain_sha256='b'*64,source_sha256={})
            with sweep,support:
                with observer:pass
            path=observer.path/'progress.json';value=json.loads(path.read_bytes())
            self.assertEqual(value['envelope_sweep_statistics'],asdict(sweep.snapshot()))
            self.assertEqual(value['projection_support_statistics'],asdict(support.snapshot()))
            self.assertEqual(len(value['envelope_sweep_statistics']),15)
            self.assertLessEqual(path.stat().st_size,gate.OBSERVER['max_snapshot_bytes']);self.assertEqual(value['status'],'returned')

    def test_nested_verifier_disabled_restored_and_inner_identity_constant(self):
        from timecut5 import pwa,envelope_sweep
        for arm in gate.ARMS:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                for name in ('remaining_charge_admission.json','envelope_admission.json'):(root/name).write_bytes(b'{}')
                domain=SimpleNamespace(config=projection.CONFIGS[gate.INNER_ARM],arm=gate.INNER_ARM,
                    outer_arm=arm,outer_config=gate.CONFIGS[arm],_seed=SimpleNamespace(max_depth=2),
                    _output=root,query_bytes=b'{}',sites={},tree=None,_search_provider=None,manifest_binding='m',
                    _activation_wall_ns=0,_activation_receipt={'time_admission':{}},
                    durable_binding=lambda seed:dict(domain_sha256='b'*64,source_sha256={}))
                seen=[]
                def sample():
                    seen.append((domain.arm,envelope_sweep._active.get().enabled,pwa._projection_support_prefilter.get().enabled))
                def store(candidate,key):sample();raise RuntimeError('verifier fixture')
                def solver(*args,**kwargs):
                    sample()
                    with self.assertRaisesRegex(RuntimeError,'verifier fixture'):kwargs['incumbent_hook'](None,(F(1),))
                    sample();return SimpleNamespace(pruned_regions=0)
                with patch('timecut5.hierarchy._solve_hierarchical_problem',side_effect=solver):
                    gate.EnvelopeDomain.solve_exact(domain,None,None,(F(2),),SimpleNamespace(current_upper=F(2)),store)
                enabled=gate.CONFIGS[arm]['envelope_sweep']
                self.assertEqual(seen,[(gate.INNER_ARM,enabled,True),(gate.INNER_ARM,False,False),(gate.INNER_ARM,enabled,True)])
                self.assertIsNone(envelope_sweep._active.get());self.assertIsNone(pwa._projection_support_prefilter.get())

    def test_tiny_exact_result_full_replay_counters_and_cross_layer_rejection(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import pwa,envelope_sweep
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,a) for a in gate.ARMS]
            with domains[0].context('verification') as context:witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[];statistics=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed);out=root/('result-'+domain.outer_arm)
                result=domain.run_arm(domain.outer_arm,seed,out,search_seconds=8)
                self.assertEqual(domain.arm,gate.INNER_ARM);self.assertEqual(domain.config,projection.CONFIGS[gate.INNER_ARM])
                self.assertEqual(result['schema'],gate.SCHEMA);self.assertEqual(result['status'],'attained_optimum')
                self.assertEqual(result['strategy'],domain.outer_arm);self.assertEqual(result['inner_arm'],gate.INNER_ARM)
                self.assertEqual(result['envelope_admission_sha256'],base.file_hash(out/'envelope_admission.json'))
                fresh=tiny_domain(root/('fresh-'+domain.outer_arm),domain.outer_arm)
                recovered=fresh.recover_durable(seed,out/'incumbent.json');keys.append(recovered['accepted_key'])
                self.assertEqual(result['accepted_key'],keys[-1]);self.assertEqual(result['Hmax'],seed.max_depth)
                with domain.context('verification') as context:self.assertEqual(context.router.mode,'full')
                statistics.append(result['envelope_sweep_statistics']);gate.validate_envelope_statistics(statistics[-1],domain.outer_arm,completed=True)
                progress=json.loads((out/'progress/progress.json').read_bytes())
                self.assertEqual(progress['envelope_sweep_statistics'],statistics[-1]);self.assertEqual(progress['arm'],gate.INNER_ARM)
                self.assertEqual(progress['envelope_arm'],domain.outer_arm)
                self.assertTrue(progress['projection_support_statistics']['enabled'])
                inner=projection.ProjectionSupportDomain(arm=gate.INNER_ARM,manifest_binding=domain.manifest_binding,
                    graph_factory=domain.graph_factory,query=json.loads(domain.query_bytes),sites=domain.sites,tree=domain.tree,
                    source_hashes=domain.source_hashes,cache=root/('inner-'+domain.outer_arm),compiler=domain.compiler['compiler'])
                with self.assertRaises(ValueError):inner.recover_durable(seed,out/'incumbent.json')
                self.assertIsNone(envelope_sweep._active.get());self.assertIsNone(pwa._projection_support_prefilter.get())
            self.assertEqual(keys[0],keys[1]);self.assertGreater(statistics[0]['baseline_parent_visits'],0)
            self.assertGreater(statistics[1]['pair_tests'],0);self.assertEqual(statistics[1]['baseline_parent_visits'],0)
            for field in ('calls','completed_calls','input_pieces','arrangement_cells','selected_cells'):
                self.assertEqual(statistics[0][field],statistics[1][field])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/('result-'+gate.ARMS[1])/'incumbent.json')
            domains[0].outer_config['envelope_sweep']=True
            with self.assertRaisesRegex(ValueError,'policy changed'):domains[0].check()

    def test_outer_inner_progress_binding_hashes_health_and_timeout(self):
        common=common_fixture();arm=gate.ARMS[1];admission=admission_fixture(gate.INNER_ARM,common)
        manifest=dict(gate.prospective(),source=dict(closure_sha256='c'*64));domain,sources=gate.progress_binding(manifest,arm,common)
        value=dict(echo(admission),profile_schema=projection.SCHEMA,domain_sha256=domain,source_sha256=sources,
            arm=gate.INNER_ARM,configuration=projection.CONFIGS[gate.INNER_ARM],manifest_binding=base.digest(manifest),candidate_count=32,
            query_sha256=base.digest(common['query']),Hmax=2,status='returned',io_error=None,heartbeat_error=None,
            sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,projection_support_statistics=counts(True),
            envelope_schema=gate.SCHEMA,envelope_arm=arm,envelope_configuration=gate.CONFIGS[arm],
            envelope_sweep_policy=gate.ENVELOPE_POLICY,envelope_sweep_statistics=envelope_counts(True))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json';ap=root/'remaining_charge_admission.json';ep=root/'envelope_admission.json'
            ap.write_bytes(base.canonical(admission));value['remaining_charge_admission_sha256']=base.file_hash(ap)
            outer=gate.outer_admission(base.digest(manifest),arm,base.file_hash(ap));ep.write_bytes(base.canonical(outer))
            value['envelope_admission_sha256']=base.file_hash(ep);path.write_bytes(base.canonical(value))
            result=dict(schema=gate.SCHEMA,strategy=arm,inner_experiment_schema=projection.SCHEMA,inner_arm=gate.INNER_ARM,
                outer_configuration=gate.CONFIGS[arm],envelope_sweep_policy=gate.ENVELOPE_POLICY,envelope_admission_sha256=base.file_hash(ep),
                envelope_sweep_statistics=envelope_counts(True),progress_sha256=base.file_hash(path),remaining_charge_admission_sha256=base.file_hash(ap),
                remaining_charge_activation_wall_ns=123,configuration=projection.CONFIGS[gate.INNER_ARM],time_policy=projection.TIME_POLICIES[gate.INNER_ARM],
                manifest_binding=base.digest(manifest),observer=dict(status='returned',io_error=None,heartbeat_error=None),
                projection_support_policy=projection.SUPPORT_POLICY,projection_support_statistics=counts(True))
            self.assertTrue(gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=result)['terminal_observer_health_proved'])
            self.assertFalse(gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')['terminal_observer_health_proved'])
            for mutate in [lambda x:x.update(strategy=gate.ARMS[0]),lambda x:x.update(inner_arm='support_off'),
                lambda x:x.update(envelope_admission_sha256='0'*64),lambda x:x.update(progress_sha256='0'*64),
                lambda x:x.update(envelope_sweep_statistics=envelope_counts(True,calls=1)),lambda x:x['observer'].update(io_error='OSError')]:
                bad=copy.deepcopy(result);mutate(bad)
                with self.assertRaises(ValueError):gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=bad)
            ep.write_bytes(base.canonical(dict(outer,arm=gate.ARMS[0])))
            with self.assertRaisesRegex(ValueError,'Outer'):gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')
            ep.write_bytes(base.canonical(outer))
            # Even freshly rehashed stale inner support_off admission must fail.
            stale=dict(admission,arm='support_off',projection_support_enabled=False);ap.write_bytes(base.canonical(stale))
            outer['inner_admission_sha256']=base.file_hash(ap);ep.write_bytes(base.canonical(outer))
            value.update(envelope_admission_sha256=base.file_hash(ep),remaining_charge_admission_sha256=base.file_hash(ap),projection_support_enabled=False)
            path.write_bytes(base.canonical(value))
            with self.assertRaisesRegex(ValueError,'activation policy'):gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')

    def test_five_stages240_and_terminal_completion_semantics(self):
        for timeout in (False,True):
            manifest,ledger,load=terminal_ledger(timeout)
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger) as run, \
                patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'read_progress',return_value={}):
                result=gate.run_gate('m','sha',temp,2)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['both_authenticated_complete'],not timeout)
            self.assertEqual(run.call_args.kwargs['exact_phase_seconds'],240)
            self.assertEqual(run.call_args.kwargs['fixed_pairs'],[[gate.CASE,list(gate.ARMS)]])
        for failure in ('failed','unknown','stage','phase','null_payload','pseudo_complete','replay'):
            manifest,ledger,load=terminal_ledger()
            if failure in ('failed','unknown'):ledger['arms'][0]['receipt']['status']=failure.upper()
            if failure=='stage':ledger['stages'][1]['strategy']=gate.ARMS[1]
            if failure=='phase':ledger['arms'][0]['receipt']['phase_budget']['seconds']=120
            if failure=='pseudo_complete':
                for arm in ledger['arms']:arm['status']='timeout_feasible_only'
            def broken(directory,receipt,operation,*args):
                value=load(directory,receipt,operation,*args)
                if operation in ('arm','verify') and failure=='pseudo_complete':value['status']='timeout_feasible_only'
                if operation=='arm' and failure=='null_payload':value['result']['result']=None
                if operation=='verify' and failure=='replay':value['accepted_key']=['9']
                return value
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger), \
                patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'read_progress',return_value={}):result=gate.run_gate('m','sha',temp,2)
            self.assertFalse(result['operational_admission']);self.assertFalse(result['both_authenticated_complete'])


if __name__=='__main__':unittest.main()
