"""Opt-in remaining-charge gate contracts; synthetic/tiny native fixtures only."""
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from experiments.remaining_charge_gate_v1 import run as gate
from experiments.mechanism_recovery_v1 import run as base
from timecut5.remaining_charge_runtime import RemainingChargeBoundResultV1 as Result
from test_runner import native_test_domain


def tiny_domain(path,arm):
    original=native_test_domain(path/'original')
    return gate.RemainingChargeDomain(arm=arm,manifest_binding=base.digest('tiny remaining charge manifest'),
        graph_factory=original.graph_factory,query=json.loads(original.query_bytes),sites=original.sites,
        tree=original.tree,source_hashes=original.source_hashes,cache=path/arm,compiler=original.compiler['compiler'])


def wrapper(lower=F(3),prefix=F(4),whole=F(5),upper=F(4),status='active'):
    problem=SimpleNamespace(bound=3)
    original=Mock();original.bound.return_value=(lower,7);original.action_mask.return_value=123
    runtime=Mock(binding_sha256='a'*64)
    runtime.evaluate_group.return_value=Result(status,prefix,'a'*64)
    runtime.whole_route_lower_bound.return_value=Result(status,whole,'a'*64)
    wrapped=gate.RemainingChargeRegionBound(original,problem,runtime=runtime,current_upper=upper)
    return wrapped,problem,(SimpleNamespace(state=SimpleNamespace(stop_count=1)),)


class RemainingChargeGateTests(unittest.TestCase):
    def test_fixed_one_factor_manifest_and_closed_source_policy(self):
        plan=gate.prospective()
        self.assertEqual(plan['candidate_count'],32);self.assertEqual(plan['denominator']['total_stages'],5)
        self.assertFalse(plan['auto_next_gate']);self.assertFalse(plan['holdout']);self.assertFalse(plan['launchable'])
        a,b=[copy.deepcopy(gate.CONFIGS[x]) for x in gate.ARMS]
        self.assertFalse(a.pop('remaining_charge'));self.assertTrue(b.pop('remaining_charge'));self.assertEqual(a,b)
        self.assertTrue(a['onward_alt']);self.assertTrue(plan['policy']['onward_alt']);self.assertEqual(a['routing'],'destination_target');self.assertEqual(a['reducer'],'reduce_frontier_skyline')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json';path.write_bytes(base.canonical(plan))
            with self.assertRaisesRegex(ValueError,'not launchable'):gate._manifest(path,base.file_hash(path))
            for field,value in [('arms',{}),('candidate_count',128),('policy',{}),('order',list(reversed(gate.ARMS)))]:
                changed=dict(plan,launchable=True);changed[field]=value;path.write_bytes(base.canonical(changed))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_max_next_stop_paid_work_and_masks_are_preserved(self):
        bound,problem,pieces=wrapper()
        self.assertEqual(bound.bound(problem,pieces,'region','C'),(F(5),7))
        bound.runtime.evaluate_group.assert_called_once_with(pieces)
        bound.runtime.whole_route_lower_bound.assert_called_once_with(2)
        self.assertEqual(bound.action_mask('region','C'),123)
        self.assertEqual(bound.counters['new_strict_prune_candidates'],1)
        self.assertEqual(bound.counters['strict_seed_prune_opportunities'],1)
        self.assertEqual(bound.counters['strengthened_calls'],1)
        bound.current_upper=F(5)
        self.assertEqual(bound.bound(problem,pieces,'region','C')[0],F(5))
        self.assertEqual(bound.counters['equality_candidates_retained'],1)
        self.assertEqual(bound.counters['new_strict_prune_candidates'],1)

    def test_original_none_off_and_disabled_leave_original_semantics(self):
        bound,problem,pieces=wrapper(lower=None)
        self.assertEqual(bound.bound(problem,pieces,'r','C'),(None,7))
        bound.runtime.evaluate_group.assert_not_called();bound.runtime.whole_route_lower_bound.assert_not_called()
        bound,problem,pieces=wrapper();bound.runtime=None
        self.assertEqual(bound.bound(problem,pieces,'r','C'),(F(3),7))
        for status in ('disabled_unsupported','inactive_no_charging_curve'):
            bound,problem,pieces=wrapper(prefix=None,whole=None,status=status)
            for _ in range(2):self.assertEqual(bound.bound(problem,pieces,'r','C'),(F(3),7))
            self.assertEqual(bound.runtime.evaluate_group.call_count,2)
            self.assertEqual(bound.runtime.whole_route_lower_bound.call_count,2)
            self.assertEqual(bound.counters['disabled_calls'],2)

    def test_integrity_owner_binding_and_declared_depth_fail_closed(self):
        bound,problem,pieces=wrapper()
        with self.assertRaisesRegex(ValueError,'owner'):bound.bound(object(),pieces,'r','C')
        with self.assertRaisesRegex(ValueError,'Nonempty'):bound.bound(problem,(),'r','C')
        problem.bound=1
        with self.assertRaisesRegex(ValueError,'Hmax'):bound.bound(problem,pieces,'r','C')
        problem.bound=3
        bound.runtime.evaluate_group.side_effect=ValueError('native drift')
        with self.assertRaisesRegex(ValueError,'native drift'):bound.bound(problem,pieces,'r','C')
        bound.runtime.evaluate_group.side_effect=None
        bound.runtime.evaluate_group.return_value=Result('active',F(4),'b'*64)
        with self.assertRaisesRegex(ValueError,'binding'):bound.bound(problem,pieces,'r','C')

    def test_tiny_native_common_seed_exact_key_full_replay_and_original_hmax(self):
        from timecut5.bounded import _solve_problem
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,a) for a in gate.ARMS]
            with domains[0].context('verification') as context:
                witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed)
                with domain.context('verification') as context:self.assertEqual(context.router.mode,'full')
                with domain.context('search') as context:self.assertEqual(context.router.mode,'destination_target')
                output=root/('result-'+domain.arm)
                result=domain.run_arm(domain.arm,seed,output,search_seconds=5)
                recovered=domain.recover_durable(seed,output/'incumbent.json');keys.append(recovered['accepted_key'])
                self.assertEqual(result['accepted_key'],recovered['accepted_key']);self.assertEqual(result['Hmax'],seed.max_depth)
                self.assertEqual(result['status'],'attained_optimum')
                self.assertTrue(domain._remaining_bound.original.onward_alt)
                progress=json.loads((output/'progress/progress.json').read_bytes())
                admission=json.loads((output/'remaining_charge_admission.json').read_bytes())
                self.assertEqual(progress['status'],'returned');self.assertIsNone(progress['io_error'])
                self.assertEqual(progress['configuration'],domain.config);self.assertEqual(progress['Hmax'],seed.max_depth)
                self.assertEqual(result['remaining_charge_admission_sha256'],base.file_hash(output/'remaining_charge_admission.json'))
                self.assertEqual(admission['original_Hmax'],seed.max_depth)
                gate.validate_activation_receipt(admission,progress,domain.arm,dict(query=json.loads(domain.query_bytes),seed=dict(key_bytes=seed.key_bytes,max_depth=seed.max_depth)))
                self.assertFalse(admission['context_receipt_portable'])
                if domain.arm==gate.ARMS[1]:
                    self.assertEqual(admission['status'],'active')
                    self.assertLessEqual(F(admission['seed_bound']),F(admission['seed_J']))
                    self.assertGreaterEqual(admission['diagnostic']['stop_threshold'],admission['seed_H'])
                    self.assertEqual(base.digest(admission['runtime_binding']),admission['runtime_binding_sha256'])
                    self.assertEqual(progress['remaining_charge_activation_diagnostic'],admission['diagnostic'])
                else:self.assertEqual(admission['status'],'disabled_by_policy')
            self.assertEqual(keys[0],keys[1])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/('result-'+gate.ARMS[1])/'incumbent.json')
            # A new domain instance/working directory can verify the ON artifact;
            # its binding cannot require the old live runtime context or paths.
            fresh=tiny_domain(root/'fresh',gate.ARMS[1])
            self.assertEqual(fresh.durable_binding(seed),domains[1].durable_binding(seed))
            self.assertEqual(fresh.recover_durable(seed,root/('result-'+gate.ARMS[1])/'incumbent.json')['accepted_key'],keys[1])

    def test_activation_rejects_bound_above_verified_seed(self):
        from timecut5.bounded import _solve_problem
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domain=tiny_domain(root,gate.ARMS[1])
            with domain.context('verification') as context:witness=_solve_problem(domain.problem(context),True).result.witness
            seed=domain.freeze_seed(witness)
            fake=Mock(binding_sha256='a'*64,original_hmax=seed.max_depth)
            fake.whole_route_lower_bound.return_value=Result('active',F(json.loads(seed.key_bytes)[0])+1,'a'*64)
            with patch('timecut5.remaining_charge_runtime.admit_remaining_charge_runtime',return_value=fake):
                with self.assertRaisesRegex(ValueError,'contradicts independently verified seed'):
                    domain.run_arm(domain.arm,seed,root/'bad',search_seconds=5)

    def test_snapshot_admission_artifact_and_final_observer_health(self):
        manifest=dict(gate.prospective(),source=dict(closure_sha256='c'*64))
        common=dict(query={'overhead_s':2,'lambda_stop_s':1},tree_sha256='d'*64,seed=dict(max_depth=2,site_sha256='e'*64,key_bytes='["5", "4", 1, []]',native_sha256='f'*64))
        arm=gate.ARMS[1];domain,sources=gate.progress_binding(manifest,arm,common)
        admission=dict(schema=gate.SCHEMA,arm=arm,portable_bound_policy=gate.BOUND_POLICY,original_Hmax=2,
            context_receipt_portable=False,status='active',seed_H=1,seed_J='5',seed_bound='4',activation_wall_ns=123,
            diagnostic=dict(global_lower_zero='1',global_lower_original_Hmax='7',stop_threshold=1,changes_declared_Hmax=False),
            runtime_binding=dict(schema='hiroute.remaining_charge_runtime.v1',original_hmax=2,routing_mode='destination_target'))
        admission['runtime_binding_sha256']=base.digest(admission['runtime_binding'])
        value=dict(profile_schema=gate.SCHEMA,domain_sha256=domain,source_sha256=sources,arm=arm,configuration=gate.CONFIGS[arm],
            manifest_binding=base.digest(manifest),candidate_count=32,query_sha256=base.digest(common['query']),Hmax=2,
            status='returned',io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
            remaining_charge_activation_wall_ns=123,remaining_charge_seed_bound='4',remaining_charge_activation_diagnostic=admission['diagnostic'])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json';ap=root/'remaining_charge_admission.json'
            ap.write_bytes(base.canonical(admission));value['remaining_charge_admission_sha256']=base.file_hash(ap)
            path.write_bytes(base.canonical(value))
            result=dict(progress_sha256=base.file_hash(path),remaining_charge_admission_sha256=base.file_hash(ap),strategy=arm,remaining_charge_activation_wall_ns=123,
                configuration=gate.CONFIGS[arm],manifest_binding=base.digest(manifest),observer=dict(status='returned',io_error=None,heartbeat_error=None))
            self.assertFalse(gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')['terminal_observer_health_proved'])
            self.assertTrue(gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=result)['terminal_observer_health_proved'])
            for mutate in [lambda x:x['observer'].update(io_error='OSError'),lambda x:x.update(progress_sha256='0'*64),
                lambda x:x.update(remaining_charge_admission_sha256='0'*64)]:
                bad=copy.deepcopy(result);mutate(bad)
                with self.assertRaises(ValueError):gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=bad)
            for mutate in [lambda x:x.pop('status'),lambda x:x.update(status='disabled_by_policy'),lambda x:x.update(seed_H=2),
                lambda x:x.update(seed_J='6'),lambda x:x.update(seed_bound='6'),lambda x:x['diagnostic'].update(stop_threshold=0),
                lambda x:x['diagnostic'].update(global_lower_original_Hmax='6'),lambda x:x.update(activation_wall_ns=124)]:
                bad=copy.deepcopy(admission);mutate(bad)
                # Rehash both artifacts: semantic admission must fail even when
                # byte hashes are internally consistent.
                ap.write_bytes(base.canonical(bad));changed=dict(value,remaining_charge_admission_sha256=base.file_hash(ap))
                path.write_bytes(base.canonical(changed))
                with self.assertRaises(ValueError):gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')
            ap.write_bytes(base.canonical(admission));path.write_bytes(base.canonical(value))
            bad_echo=dict(value,remaining_charge_seed_bound='3');path.write_bytes(base.canonical(bad_echo))
            with self.assertRaisesRegex(ValueError,'echoes'):gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')
            path.write_bytes(base.canonical(value))
            ap.write_bytes(base.canonical(dict(admission,original_Hmax=1)))
            with self.assertRaisesRegex(ValueError,'admission binding'):gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')

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
                patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only')), \
                patch.object(gate,'read_progress',return_value=dict(status='running')):
                result=gate.run_gate('manifest','sha',temp,2)
            self.assertEqual(result['operational_admission'],mutate is None)
        with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest), \
            patch.object(base,'_run_plan',return_value=copy.deepcopy(ledger)), \
            patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only')), \
            patch.object(gate,'read_progress',side_effect=ValueError('Observer failed')):
            result=gate.run_gate('manifest','sha',temp,2)
        self.assertFalse(result['operational_admission']);self.assertEqual(len(result['stages']),5)


if __name__=='__main__':unittest.main()
