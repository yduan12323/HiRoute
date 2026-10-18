"""Prospective q0/q10 gate tests; no recovered road inputs are loaded."""
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from experiments.dyadic_alt_gate_v1 import run as gate
from experiments.mechanism_recovery_v1 import run as base
from test_runner import native_test_domain


def tiny_domain(path,arm,required_hmax=None):
    original=native_test_domain(path/'original')
    return gate.DyadicALTDomain(arm=arm,manifest_binding=base.digest('tiny dyadic manifest'),required_hmax=required_hmax,
        graph_factory=original.graph_factory,query=json.loads(original.query_bytes),sites=original.sites,
        tree=original.tree,source_hashes=original.source_hashes,cache=path/arm,compiler=original.compiler['compiler'])


def common_fixture():
    return dict(query=dict(origin='road:0',destination='road:2',overhead_s=2,lambda_stop_s=1),
        tree_sha256='d'*64,seed=dict(max_depth=2,site_sha256='e'*64,key_bytes='["5", "4", 1, []]',native_sha256='f'*64))


def admission_fixture(arm,common):
    policy=gate.TIME_POLICIES[arm];units=policy['time_units_per_second']
    sources=dict(nodes='a'*64,edges='b'*64,router='c'*64)
    certificate=dict(schema=policy['certificate_schema'],edge_weight_policy=policy['edge_weight_policy'],
        graph_nodes_sha256=sources['nodes'],graph_edges_sha256=sources['edges'],router_source_sha256=sources['router'],
        exact_integer_limit=2**53,root_anchor='road:0',anchor_labels={'road:0':[0,0],'road:2':[units,units]})
    if gate.QUANTA[arm]:certificate.update(time_quantum_exponent=10,time_units_per_second=1024)
    suffix=base.digest(dict(schema=policy['suffix_binding_schema'],construction_sha256=base.digest(certificate),
        source_sha256=sources,destination='road:2',site_catalog_sha256=common['seed']['site_sha256']))
    binding=dict(schema='hiroute.remaining_charge_runtime.v1',original_hmax=2,routing_mode='destination_target',
        provider_sources=sources,potential_bindings=['a'*64,suffix])
    return dict(schema=gate.SCHEMA,arm=arm,portable_bound_policy=gate.BOUND_POLICY,original_Hmax=2,
        context_receipt_portable=False,status='active',seed_H=1,seed_J='5',seed_bound='4',activation_wall_ns=123,
        diagnostic=dict(global_lower_zero='1',global_lower_original_Hmax='7',stop_threshold=1,changes_declared_Hmax=False),
        runtime_binding=binding,runtime_binding_sha256=base.digest(binding),time_policy=policy,
        time_admission=dict(certificate=certificate,certificate_sha256=base.digest(certificate),suffix_binding_sha256=suffix,
            origin_suffix_status='active',origin_suffix_seconds='1'))


def echo(admission):
    return dict(remaining_charge_activation_diagnostic=admission['diagnostic'],remaining_charge_seed_bound=admission['seed_bound'],
        remaining_charge_activation_wall_ns=admission['activation_wall_ns'],time_policy=admission['time_policy'],time_admission=admission['time_admission'])


class DyadicALTGateTests(unittest.TestCase):
    def test_one_factor_fixed_domain_and_manifest_types(self):
        plan=gate.prospective();a,b=[copy.deepcopy(gate.CONFIGS[x]) for x in gate.ARMS]
        self.assertEqual(a.pop('time_quantum_exponent'),0);self.assertEqual(b.pop('time_quantum_exponent'),10);self.assertEqual(a,b)
        for field in ('terminal_energy','onward_alt','remaining_charge'):self.assertTrue(a[field])
        self.assertEqual(a['routing'],'destination_target');self.assertEqual(a['reducer'],'reduce_frontier_skyline')
        self.assertEqual(plan['policy']['original_Hmax'],26);self.assertEqual(plan['candidate_count'],32)
        self.assertEqual(plan['denominator']['total_stages'],5);self.assertFalse(plan['holdout']);self.assertFalse(plan['auto_next_gate'])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json'
            for field,value in [('candidate_count',128),('order',list(reversed(gate.ARMS))),('arms',dict(gate.CONFIGS,time_q0=dict(gate.CONFIGS['time_q0'],time_quantum_exponent=False)))]:
                changed=dict(plan,launchable=True);changed[field]=value;path.write_bytes(base.canonical(changed))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_common_original_hmax_is_explicit_not_rewritten(self):
        common=dict(case_id=gate.CASE,candidate_count=32,sites=[{}]*32,seed=dict(max_depth=26))
        gate.validate_common_domain(common)
        for changed in [dict(common,candidate_count=128),dict(common,seed=dict(max_depth=25)),dict(common,seed=dict(max_depth=26.0)),dict(common,sites=[{}]*31)]:
            with self.assertRaises(ValueError):gate.validate_common_domain(changed)

    def test_quantum_certificate_runtime_binding_and_seconds_agree(self):
        common=common_fixture()
        for arm in gate.ARMS:
            admission=admission_fixture(arm,common);gate.validate_activation_receipt(admission,echo(admission),arm,common)
        self.assertNotEqual(admission_fixture(gate.ARMS[0],common)['runtime_binding_sha256'],admission_fixture(gate.ARMS[1],common)['runtime_binding_sha256'])

    def test_rehashed_unit_certificate_policy_and_runtime_mismatches_fail(self):
        common=common_fixture();arm=gate.ARMS[1];good=admission_fixture(arm,common)
        mutations=[lambda x:x['time_policy'].update(time_units_per_second=1),
            lambda x:x['time_policy'].update(time_quantum_exponent=10.0),
            lambda x:x['time_admission']['certificate'].update(time_units_per_second=1),
            lambda x:x['time_admission']['certificate'].update(time_quantum_exponent=10.0),
            lambda x:x['time_admission']['certificate'].update(schema=gate.TIME_POLICIES[gate.ARMS[0]]['certificate_schema']),
            lambda x:x['time_admission'].update(origin_suffix_seconds='1024'),
            lambda x:x['time_admission'].update(origin_suffix_seconds='1/0'),
            lambda x:x['runtime_binding']['potential_bindings'].__setitem__(1,'0'*64),
            lambda x:x.update(seed_J='6'),lambda x:x['diagnostic'].update(stop_threshold=0)]
        for mutate in mutations:
            bad=copy.deepcopy(good);mutate(bad)
            bad['time_admission']['certificate_sha256']=base.digest(bad['time_admission']['certificate'])
            bad['runtime_binding_sha256']=base.digest(bad['runtime_binding'])
            with self.assertRaises(ValueError):gate.validate_activation_receipt(bad,echo(bad),arm,common)
        bad=admission_fixture(gate.ARMS[0],common);bad['time_admission']['certificate']['time_quantum_exponent']=0
        bad['time_admission']['certificate_sha256']=base.digest(bad['time_admission']['certificate'])
        with self.assertRaises(ValueError):gate.validate_activation_receipt(bad,echo(bad),gate.ARMS[0],common)

    def test_tiny_native_q0_q10_same_seed_exact_answer_fresh_full_replay(self):
        from timecut5.bounded import _solve_problem
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,a) for a in gate.ARMS]
            with domains[0].context('verification') as context:witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[];suffix=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed)
                with domain.context('verification') as context:self.assertEqual(context.router.mode,'full')
                output=root/('result-'+domain.arm);result=domain.run_arm(domain.arm,seed,output,search_seconds=5)
                recovered=domain.recover_durable(seed,output/'incumbent.json');keys.append(recovered['accepted_key'])
                self.assertEqual(result['status'],'attained_optimum');self.assertEqual(result['accepted_key'],keys[-1])
                self.assertEqual(result['Hmax'],seed.max_depth);self.assertTrue(domain._remaining_bound.original.onward_alt)
                self.assertEqual(domain._remaining_bound.original.time_quantum_exponent,gate.QUANTA[domain.arm])
                self.assertEqual(domain._remaining_bound.original.time_units_per_second,2**gate.QUANTA[domain.arm])
                progress=json.loads((output/'progress/progress.json').read_bytes());admission=json.loads((output/'remaining_charge_admission.json').read_bytes())
                self.assertEqual(progress['status'],'returned');self.assertIsNone(progress['io_error']);self.assertEqual(admission['status'],'active')
                gate.validate_activation_receipt(admission,progress,domain.arm,dict(query=json.loads(domain.query_bytes),seed=dict(key_bytes=seed.key_bytes,max_depth=seed.max_depth,site_sha256=seed.site_sha256)))
                suffix.append(F(admission['time_admission']['origin_suffix_seconds']))
                fresh=tiny_domain(root/('fresh-'+domain.arm),domain.arm)
                self.assertEqual(fresh.durable_binding(seed),domain.durable_binding(seed))
                self.assertEqual(fresh.recover_durable(seed,output/'incumbent.json')['accepted_key'],keys[-1])
            self.assertEqual(keys[0],keys[1]);self.assertGreater(suffix[1],suffix[0])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/('result-'+gate.ARMS[1])/'incumbent.json')
            fixed=tiny_domain(root/'fixed',gate.ARMS[0],required_hmax=26)
            with self.assertRaisesRegex(ValueError,'Hmax'):fixed.durable_binding(seed)

    def test_success_health_hashes_and_timeout_censoring(self):
        common=common_fixture();arm=gate.ARMS[1];admission=admission_fixture(arm,common)
        manifest=dict(gate.prospective(),source=dict(closure_sha256='c'*64));domain,sources=gate.progress_binding(manifest,arm,common)
        value=dict(echo(admission),profile_schema=gate.SCHEMA,domain_sha256=domain,source_sha256=sources,arm=arm,configuration=gate.CONFIGS[arm],
            manifest_binding=base.digest(manifest),candidate_count=32,query_sha256=base.digest(common['query']),Hmax=2,
            status='returned',io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json';ap=root/'remaining_charge_admission.json'
            ap.write_bytes(base.canonical(admission));value['remaining_charge_admission_sha256']=base.file_hash(ap);path.write_bytes(base.canonical(value))
            result=dict(progress_sha256=base.file_hash(path),remaining_charge_admission_sha256=base.file_hash(ap),strategy=arm,
                remaining_charge_activation_wall_ns=123,configuration=gate.CONFIGS[arm],time_policy=gate.TIME_POLICIES[arm],
                manifest_binding=base.digest(manifest),observer=dict(status='returned',io_error=None,heartbeat_error=None))
            self.assertFalse(gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')['terminal_observer_health_proved'])
            self.assertTrue(gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=result)['terminal_observer_health_proved'])
            for mutate in [lambda x:x['observer'].update(io_error='OSError'),lambda x:x.update(progress_sha256='0'*64),lambda x:x.update(time_policy=gate.TIME_POLICIES[gate.ARMS[0]])]:
                bad=copy.deepcopy(result);mutate(bad)
                with self.assertRaises(ValueError):gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=bad)
            bad=dict(value,configuration=dict(gate.CONFIGS[arm],time_quantum_exponent=10.0));path.write_bytes(base.canonical(bad))
            with self.assertRaises(ValueError):gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')

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
