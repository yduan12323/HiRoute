"""Projection support integration; synthetic/tiny native fixtures only."""
import copy
from dataclasses import asdict
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from experiments.projection_support_gate_v1 import run as gate
from experiments.dyadic_alt_gate_v1 import run as dyadic
from experiments.mechanism_recovery_v1 import run as base
from test_runner import native_test_domain
from test_dyadic_alt_gate import common_fixture,admission_fixture as dyadic_admission_fixture,echo as dyadic_echo
from timecut5.pwa import ProjectionSupportPrefilter


def tiny_domain(path,arm):
    original=native_test_domain(path/'original');query=json.loads(original.query_bytes)
    query['charging_segments']=[[0,1,1,0],[1,3,2,-1],[3,5,3,-4]]
    return gate.ProjectionSupportDomain(arm=arm,manifest_binding=base.digest('tiny support manifest'),
        graph_factory=original.graph_factory,query=query,sites=original.sites,
        tree=original.tree,source_hashes=original.source_hashes,cache=path/arm,compiler=original.compiler['compiler'])


def counts(enabled,considered=3,empty=0,strict=0,builds=3):
    return dict(enabled=enabled,considered_pairs=considered,skipped_empty_input=empty,skipped_strict_energy=strict,projection_builds=builds)


def admission_fixture(arm,common):
    result=dyadic_admission_fixture(dyadic.ARMS[1],common)
    return dict(result,schema=gate.SCHEMA,arm=arm,projection_support_policy=gate.SUPPORT_POLICY,
        projection_support_enabled=gate.CONFIGS[arm]['projection_support'])


def echo(admission):
    return dict(dyadic_echo(admission),projection_support_policy=gate.SUPPORT_POLICY,
        projection_support_enabled=admission['projection_support_enabled'])


class ProjectionSupportGateTests(unittest.TestCase):
    def test_only_prefilter_changes_original_domain_fixed(self):
        plan=gate.prospective();a,b=[copy.deepcopy(gate.CONFIGS[x]) for x in gate.ARMS]
        self.assertFalse(a.pop('projection_support'));self.assertTrue(b.pop('projection_support'));self.assertEqual(a,b)
        self.assertEqual(a['time_quantum_exponent'],10)
        for field in ('terminal_energy','onward_alt','remaining_charge'):self.assertTrue(a[field])
        self.assertEqual(a['routing'],'destination_target');self.assertEqual(a['reducer'],'reduce_frontier_skyline')
        self.assertEqual(plan['policy']['original_Hmax'],26);self.assertEqual(plan['candidate_count'],32)
        self.assertEqual(plan['denominator']['total_stages'],5);self.assertFalse(plan['auto_next_gate']);self.assertFalse(plan['holdout'])
        common=dict(case_id=gate.CASE,candidate_count=32,sites=[{}]*32,seed=dict(max_depth=26));gate.validate_common_domain(common)
        with self.assertRaises(ValueError):gate.validate_common_domain(dict(common,seed=dict(max_depth=25)))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json';bad=copy.deepcopy(plan);bad['launchable']=True;bad['arms'][gate.ARMS[0]]['projection_support']=0
            path.write_bytes(base.canonical(bad))
            with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_live_counts_censored_final_counts_conserve(self):
        gate.validate_support_statistics(counts(True),gate.ARMS[1],completed=True)
        interrupted=counts(True,considered=4)
        gate.validate_support_statistics(interrupted,gate.ARMS[1],completed=False)
        with self.assertRaisesRegex(ValueError,'conserve'):gate.validate_support_statistics(interrupted,gate.ARMS[1],completed=True)
        for bad,arm in [(counts(False,empty=1),gate.ARMS[0]),(counts(True,considered=True),gate.ARMS[1]),
            (counts(True,builds=-1),gate.ARMS[1]),(counts(1),gate.ARMS[1]),(dict(counts(True),extra=0),gate.ARMS[1])]:
            with self.assertRaises(ValueError):gate.validate_support_statistics(bad,arm,completed=False)

    def test_policy_receipt_runtime_and_echo_mismatches_reject(self):
        common=common_fixture()
        for arm in gate.ARMS:
            admission=admission_fixture(arm,common);gate.validate_activation_receipt(admission,echo(admission),arm,common)
            for mutate in [lambda x:x.update(projection_support_enabled=not x['projection_support_enabled']),
                lambda x:x.update(projection_support_enabled=int(x['projection_support_enabled'])),
                lambda x:x.update(projection_support_policy={}),lambda x:x['time_policy'].update(time_quantum_exponent=0),
                lambda x:x.update(seed_bound='6')]:
                bad=copy.deepcopy(admission);mutate(bad)
                with self.assertRaises(ValueError):gate.validate_activation_receipt(bad,echo(bad),arm,common)

    def test_observer_detached_constant_size_support_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            policy=ProjectionSupportPrefilter(enabled=True)
            observer=gate.ProfileProgress(Path(temp)/'progress',projection_support=policy,
                query_sha256='a'*64,domain_sha256='b'*64,source_sha256={})
            with policy:
                with observer:pass
            disk=json.loads((observer.path/'progress.json').read_bytes())
            self.assertEqual(disk['projection_support_statistics'],asdict(policy.snapshot()))
            self.assertEqual(len(disk['projection_support_statistics']),5)
            self.assertLessEqual((observer.path/'progress.json').stat().st_size,gate.OBSERVER['max_snapshot_bytes'])
            self.assertEqual(disk['status'],'returned')

    def test_incumbent_verifier_context_disabled_and_restored_on_error(self):
        from timecut5 import pwa
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'remaining_charge_admission.json').write_bytes(b'{}')
            domain=SimpleNamespace(config=gate.CONFIGS[gate.ARMS[1]],arm=gate.ARMS[1],_seed=SimpleNamespace(max_depth=2),
                _output=root,query_bytes=b'{}',sites={},tree=None,_search_provider=None,manifest_binding='m',
                _activation_wall_ns=0,_activation_receipt={'time_admission':{}},
                durable_binding=lambda seed:dict(domain_sha256='b'*64,source_sha256={}))
            seen=[]
            def store(candidate,key):
                seen.append(pwa._projection_support_prefilter.get().enabled)
                raise RuntimeError('verification fixture')
            def solver(*args,**kwargs):
                seen.append(pwa._projection_support_prefilter.get().enabled)
                with self.assertRaisesRegex(RuntimeError,'verification fixture'):kwargs['incumbent_hook'](None,(F(1),))
                seen.append(pwa._projection_support_prefilter.get().enabled)
                return SimpleNamespace(pruned_regions=0)
            with patch('timecut5.hierarchy._solve_hierarchical_problem',side_effect=solver):
                gate.ProjectionSupportDomain.solve_exact(domain,None,None,(F(2),),SimpleNamespace(current_upper=F(2)),store)
            self.assertEqual(seen,[True,False,True]);self.assertIsNone(pwa._projection_support_prefilter.get())

    def test_tiny_native_exact_key_full_replay_and_actual_projection_savings(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import pwa
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,a) for a in gate.ARMS]
            with domains[0].context('verification') as context:witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[];stats=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed);output=root/('result-'+domain.arm)
                result=domain.run_arm(domain.arm,seed,output,search_seconds=8)
                self.assertIsNone(pwa._projection_support_prefilter.get())
                recovered=domain.recover_durable(seed,output/'incumbent.json');keys.append(recovered['accepted_key'])
                self.assertEqual(result['status'],'attained_optimum');self.assertEqual(result['accepted_key'],keys[-1]);self.assertEqual(result['Hmax'],seed.max_depth)
                self.assertEqual(domain._remaining_bound.original.time_quantum_exponent,10)
                with domain.context('verification') as context:self.assertEqual(context.router.mode,'full')
                progress=json.loads((output/'progress/progress.json').read_bytes());admission=json.loads((output/'remaining_charge_admission.json').read_bytes())
                gate.validate_activation_receipt(admission,progress,domain.arm,dict(query=json.loads(domain.query_bytes),seed=dict(key_bytes=seed.key_bytes,max_depth=seed.max_depth,site_sha256=seed.site_sha256)))
                stats.append(result['projection_support_statistics']);gate.validate_support_statistics(stats[-1],domain.arm,completed=True)
                self.assertEqual(stats[-1],progress['projection_support_statistics']);self.assertEqual(progress['status'],'returned')
                fresh=tiny_domain(root/('fresh-'+domain.arm),domain.arm)
                self.assertEqual(fresh.recover_durable(seed,output/'incumbent.json')['accepted_key'],keys[-1])
            self.assertEqual(keys[0],keys[1]);self.assertEqual(stats[0]['considered_pairs'],stats[1]['considered_pairs'])
            self.assertGreater(stats[1]['skipped_empty_input']+stats[1]['skipped_strict_energy'],0)
            self.assertLess(stats[1]['projection_builds'],stats[0]['projection_builds'])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/('result-'+gate.ARMS[1])/'incumbent.json')

    def test_completed_statistics_hash_health_and_timeout_censoring(self):
        common=common_fixture();arm=gate.ARMS[1];admission=admission_fixture(arm,common)
        manifest=dict(gate.prospective(),source=dict(closure_sha256='c'*64));domain,sources=gate.progress_binding(manifest,arm,common)
        value=dict(echo(admission),profile_schema=gate.SCHEMA,domain_sha256=domain,source_sha256=sources,arm=arm,configuration=gate.CONFIGS[arm],
            manifest_binding=base.digest(manifest),candidate_count=32,query_sha256=base.digest(common['query']),Hmax=2,
            status='returned',io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
            projection_support_statistics=counts(True))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json';ap=root/'remaining_charge_admission.json'
            ap.write_bytes(base.canonical(admission));value['remaining_charge_admission_sha256']=base.file_hash(ap);path.write_bytes(base.canonical(value))
            result=dict(progress_sha256=base.file_hash(path),remaining_charge_admission_sha256=base.file_hash(ap),strategy=arm,
                remaining_charge_activation_wall_ns=123,configuration=gate.CONFIGS[arm],time_policy=gate.TIME_POLICIES[arm],
                manifest_binding=base.digest(manifest),observer=dict(status='returned',io_error=None,heartbeat_error=None),
                projection_support_policy=gate.SUPPORT_POLICY,projection_support_statistics=counts(True))
            self.assertTrue(gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=result)['terminal_observer_health_proved'])
            for mutate in [lambda x:x['observer'].update(io_error='OSError'),lambda x:x.update(progress_sha256='0'*64),
                lambda x:x.update(projection_support_statistics=counts(True,considered=4))]:
                bad=copy.deepcopy(result);mutate(bad)
                with self.assertRaises(ValueError):gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=bad)
            value['projection_support_statistics']=counts(True,considered=4);path.write_bytes(base.canonical(value))
            self.assertFalse(gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')['terminal_observer_health_proved'])
            result.update(progress_sha256=base.file_hash(path),projection_support_statistics=value['projection_support_statistics'])
            with self.assertRaisesRegex(ValueError,'conserve'):gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=result)

    def test_receipt_admission_rejects_failed_unknown_mismatched_and_observer_failure(self):
        manifest=dict(gate.prospective(),source=dict(closure_sha256='a'*64))
        stages=[dict(id='prepare-'+gate.CASE,operation='prepare',case=gate.CASE,status='SUCCESS')]
        arms=[]
        for index,strategy in enumerate(gate.ARMS):
            search=dict(status='TIMEOUT',reason='phase_timeout',cleanup_verified=True,phase_entered_monotonic=1,
                phase_budget=dict(seconds=120,identity=dict(case_id=gate.CASE,strategy=strategy,arm_index=str(index),
                    manifest_sha256='sha',source_closure_sha256='a'*64)))
            verified=dict(status='SUCCESS',cleanup_verified=True)
            arms.append(dict(case=gate.CASE,pair=0,strategy=strategy,status='timeout_feasible_only',receipt=search,verification=verified))
            stages.extend([dict(id=f'search-{index}',operation='search',case=gate.CASE,strategy=strategy,status='TIMEOUT'),
                dict(id=f'verify-{index}',operation='verify',case=gate.CASE,strategy=strategy,status='SUCCESS')])
        ledger=dict(status='COMPLETED',denominator=5,stages=stages,arms=arms,
            common={gate.CASE:dict(status='SUCCESS',cleanup_verified=True)})
        mutations=[None,
            lambda x:x['arms'][0]['receipt'].update(status='FAILED'),
            lambda x:x['arms'][1]['receipt'].update(status='UNKNOWN'),
            lambda x:x['stages'][1].update(status='SUCCESS'),
            lambda x:x['arms'][0]['receipt']['phase_budget']['identity'].update(strategy=gate.ARMS[1]),
            lambda x:x['arms'][0]['verification'].update(cleanup_verified=False),
            lambda x:x.update(arms=[]),
        ]
        for mutate in mutations:
            current=copy.deepcopy(ledger)
            if mutate:mutate(current)
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest), \
                patch.object(base,'_run_plan',return_value=current), \
                patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only',case_id=gate.CASE,candidate_count=32,sites=[{}]*32,seed=dict(max_depth=26))), \
                patch.object(gate,'read_progress',return_value=dict(status='running')):
                result=gate.run_gate('manifest','sha',temp,2)
            self.assertEqual(result['operational_admission'],mutate is None)
        with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest), \
            patch.object(base,'_run_plan',return_value=copy.deepcopy(ledger)), \
            patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only',case_id=gate.CASE,candidate_count=32,sites=[{}]*32,seed=dict(max_depth=26))), \
            patch.object(gate,'read_progress',side_effect=ValueError('Observer failed')):
            result=gate.run_gate('manifest','sha',temp,2)
        self.assertFalse(result['operational_admission']);self.assertEqual(len(result['stages']),5)


if __name__=='__main__':unittest.main()
