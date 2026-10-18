"""Separately declared240-second completion gate; tiny/mocked execution only."""
import copy
import inspect
import json
from pathlib import Path
import resource
import tempfile
import unittest
from unittest.mock import patch
from experiments.projection_completion_gate_v1 import run as gate
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from experiments.search_extensions_v1.run import require_exact_phase as old_phase
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts


def tiny_domain(root,arm):
    old=support_domain(root/'original',arm)
    return gate.CompletionDomain(arm=arm,manifest_binding=base.digest('tiny completion240 manifest'),
        graph_factory=old.graph_factory,query=json.loads(old.query_bytes),sites=old.sites,tree=old.tree,
        source_hashes=old.source_hashes,cache=root/arm,compiler=old.compiler['compiler'])


def terminal_ledger(timeout=False):
    manifest=dict(gate.prospective(),source=dict(closure_sha256='a'*64))
    common=dict(case_id=gate.CASE,candidate_count=32,sites=[{}]*32,seed=dict(max_depth=26))
    stages=[dict(id='prepare-'+gate.CASE,operation='prepare',case=gate.CASE,status='SUCCESS')];arms=[]
    for i,arm in enumerate(gate.ARMS):
        status='TIMEOUT' if timeout else 'SUCCESS'
        search=dict(status=status,reason='phase_timeout' if timeout else 'completed',cleanup_verified=True,phase_entered_monotonic=1,
            phase_budget=dict(seconds=240,identity=dict(case_id=gate.CASE,strategy=arm,arm_index=str(i),manifest_sha256='sha',source_closure_sha256='a'*64)))
        arms.append(dict(case=gate.CASE,pair=0,strategy=arm,status='timeout_feasible_only' if timeout else 'attained_optimum',
            receipt=search,verification=dict(status='SUCCESS',cleanup_verified=True)))
        stages.extend([dict(id=f'search-{i}',operation='search',case=gate.CASE,strategy=arm,status=status),
            dict(id=f'verify-{i}',operation='verify',case=gate.CASE,strategy=arm,status='SUCCESS')])
    ledger=dict(status='COMPLETED',denominator=5,stages=stages,arms=arms,common={gate.CASE:dict(status='SUCCESS',cleanup_verified=True)})
    def load(directory,receipt,operation,*args):
        if operation=='prepare':return common
        if operation=='verify':return dict(status='timeout_feasible_only' if timeout else 'attained_optimum',accepted_key=['8'],search_status='TIMEOUT' if timeout else 'SUCCESS')
        if timeout:raise AssertionError('Timeout cannot load an authenticated normal result')
        return dict(status='attained_optimum',accepted_key=['8'],result=dict(result={'status':'attained_optimum','J':'8'}))
    return manifest,ledger,load


class ProjectionCompletionGateTests(unittest.TestCase):
    def test_distinct_policy_same_arms_caps_and_old_default(self):
        plan=gate.prospective()
        self.assertEqual(plan['schema'],gate.SCHEMA);self.assertNotEqual(plan['schema'],projection.SCHEMA)
        self.assertEqual(plan['arms'],projection.CONFIGS);self.assertEqual(plan['limits'],dict(base.LIMITS,search_seconds=240))
        self.assertEqual(base.LIMITS['search_seconds'],120)
        self.assertEqual(plan['reserve_plan']['exact_search_seconds_per_arm'],240)
        self.assertEqual(plan['reserve_plan']['total_exact_search_seconds'],480)
        self.assertEqual(projection.prospective()['reserve_plan']['exact_search_seconds_per_arm'],120)
        self.assertEqual(projection.prospective()['reserve_plan']['total_exact_search_seconds'],240)
        for field in ('maximum_worker_wall_seconds','maximum_worker_cpu_soft_seconds','parent_cpu_soft_seconds'):
            self.assertEqual(plan['reserve_plan'][field],projection.prospective()['reserve_plan'][field])
        self.assertEqual(inspect.signature(base._run_plan).parameters['exact_phase_seconds'].default,120)
        self.assertEqual(projection.prospective()['limits']['search_seconds'],120)
        self.assertFalse(plan['policy']['completion_policy']['envelope_sweep']);self.assertFalse(plan['auto_next_gate'])
        receipt=dict(status='TIMEOUT',reason='phase_timeout',phase_entered_monotonic=1,phase_budget=dict(seconds=240))
        gate.require_exact_phase(receipt)
        with self.assertRaises(ValueError):old_phase(receipt)
        for seconds in (120,True,240.0,600):
            with self.assertRaises(ValueError):gate.require_exact_phase(dict(receipt,phase_budget=dict(seconds=seconds)))
        for status in ('UNKNOWN','FAILED'):
            with self.assertRaises(ValueError):gate.require_exact_phase(dict(receipt,status=status))

    def test_explicit_budget_rejects_bad_types_mismatched_manifest_before_launch(self):
        with tempfile.TemporaryDirectory() as temp,patch('experiments.mechanism_recovery_v1.supervisor.run') as launch:
            for value in (True,120.0,240.0,0,600,None):
                with self.assertRaises(ValueError):base._run_plan('m','sha',Path(temp)/str(value),0,scope='od02_gate',exact_phase_seconds=value)
            for limits in (None,base.LIMITS,dict(gate.LIMITS,worker_cpu_seconds=601),dict(gate.LIMITS,search_seconds=240.0)):
                with self.assertRaisesRegex(ValueError,'manifest limits'):
                    base._run_plan('m','sha',Path(temp)/'bad',0,scope='od02_gate',exact_phase_seconds=240,
                        manifest_loader=lambda *a:dict(limits=limits))
            launch.assert_not_called()

    def test_supervisor_receives240_and_all_other_caps_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest=dict(repo=temp,source=dict(closure_sha256='a'*64),limits=gate.LIMITS)
            replies=[dict(status='SUCCESS'),dict(status='TIMEOUT'),dict(status='SUCCESS'),dict(status='TIMEOUT'),dict(status='SUCCESS')]
            with patch('experiments.mechanism_recovery_v1.supervisor.run',side_effect=replies) as launch, \
                patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only')),patch.object(base,'file_hash',return_value='b'*64), \
                patch('os.sched_getaffinity',return_value={0}),patch('os.sched_setaffinity'), \
                patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)),patch('resource.setrlimit'),patch('signal.signal'):
                ledger=base._run_plan('m','sha',Path(temp)/'gate',0,scope='od02_gate',manifest_loader=lambda *a:manifest,
                    fixed_cases=(gate.CASE,),fixed_pairs=[[gate.CASE,list(gate.ARMS)]],exact_phase_seconds=240)
            self.assertEqual(ledger['status'],'COMPLETED');self.assertEqual(launch.call_count,5)
            calls=launch.call_args_list;self.assertEqual([calls[i].kwargs['phase_budget'].seconds for i in (1,3)],[240,240])
            self.assertEqual([c.kwargs['limits'].wall_seconds for c in calls],[600,600,180,600,180])
            self.assertEqual([c.kwargs['limits'].cpu_seconds for c in calls],[600,600,120,600,120])
            self.assertTrue(all(c.kwargs['limits'].address_space_bytes==8*1024**3 for c in calls))

    def test_completed_result_and_matching_fresh_replay_required(self):
        for timeout in (False,True):
            manifest,ledger,load=terminal_ledger(timeout)
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger) as run, \
                patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'read_progress',return_value={}):
                result=gate.run_gate('m','sha',temp,2)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['both_authenticated_complete'],not timeout)
            self.assertEqual(run.call_args.kwargs['exact_phase_seconds'],240)
        for failure in ('missing_result','replay_key','old_budget','nonterminal_status','null_result','null_payload','wrong_payload_status'):
            manifest,ledger,load=terminal_ledger()
            if failure=='old_budget':ledger['arms'][0]['receipt']['phase_budget']['seconds']=120
            if failure=='nonterminal_status':
                for arm in ledger['arms']:arm['status']='timeout_feasible_only'
            def broken(directory,receipt,operation,*args):
                if operation=='arm' and failure=='missing_result':raise ValueError('No authenticated result')
                value=load(directory,receipt,operation,*args)
                if operation=='verify' and failure=='replay_key':value['accepted_key']=['9']
                if operation in ('arm','verify') and failure=='nonterminal_status':value['status']='timeout_feasible_only'
                if operation=='arm':
                    if failure=='null_result':value['result']=None
                    if failure=='null_payload':value['result']['result']=None
                    if failure=='wrong_payload_status':value['result']['result']['status']='infeasible_within_H_ref'
                return value
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger), \
                patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'read_progress',return_value={}):result=gate.run_gate('m','sha',temp,2)
            self.assertFalse(result['operational_admission']);self.assertFalse(result['both_authenticated_complete'])

    def test_tiny_authenticated_result_fresh_replay_and_new_portable_binding(self):
        from timecut5.bounded import _solve_problem
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,a) for a in gate.ARMS]
            with domains[0].context('verification') as context:witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed);out=root/('result-'+domain.arm)
                result=domain.run_arm(domain.arm,seed,out,search_seconds=8)
                self.assertEqual(result['schema'],gate.SCHEMA);self.assertEqual(result['status'],'attained_optimum')
                self.assertEqual(result['completion_admission_sha256'],base.file_hash(out/'completion_admission.json'))
                self.assertEqual(result['completion_policy'],gate.COMPLETION_POLICY)
                fresh=tiny_domain(root/('fresh-'+domain.arm),domain.arm)
                recovered=fresh.recover_durable(seed,out/'incumbent.json');keys.append(recovered['accepted_key'])
                self.assertEqual(result['accepted_key'],keys[-1]);self.assertEqual(result['Hmax'],seed.max_depth)
                with domain.context('verification') as context:self.assertEqual(context.router.mode,'full')
                inner=projection.ProjectionSupportDomain(arm=domain.arm,manifest_binding=domain.manifest_binding,
                    graph_factory=domain.graph_factory,query=json.loads(domain.query_bytes),sites=domain.sites,tree=domain.tree,
                    source_hashes=domain.source_hashes,cache=root/('inner-'+domain.arm),compiler=domain.compiler['compiler'])
                with self.assertRaises(ValueError):inner.recover_durable(seed,out/'incumbent.json')
            self.assertEqual(keys[0],keys[1])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/('result-'+gate.ARMS[1])/'incumbent.json')

    def test_outer_completion_admission_and_final_result_hashes(self):
        common=common_fixture();arm=gate.ARMS[1];admission=admission_fixture(arm,common)
        manifest=dict(gate.prospective(),source=dict(closure_sha256='c'*64));domain,sources=gate.progress_binding(manifest,arm,common)
        value=dict(echo(admission),profile_schema=projection.SCHEMA,domain_sha256=domain,source_sha256=sources,arm=arm,configuration=gate.CONFIGS[arm],
            manifest_binding=base.digest(manifest),candidate_count=32,query_sha256=base.digest(common['query']),Hmax=2,
            status='returned',io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
            projection_support_statistics=counts(True))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json';ap=root/'remaining_charge_admission.json';cp=root/'completion_admission.json'
            ap.write_bytes(base.canonical(admission));value['remaining_charge_admission_sha256']=base.file_hash(ap);path.write_bytes(base.canonical(value))
            completion=dict(schema=gate.SCHEMA,arm=arm,completion_policy=gate.COMPLETION_POLICY,manifest_binding=base.digest(manifest),
                inner_experiment_schema=projection.SCHEMA,inner_configuration=gate.CONFIGS[arm],inner_admission_sha256=base.file_hash(ap))
            cp.write_bytes(base.canonical(completion))
            result=dict(schema=gate.SCHEMA,inner_experiment_schema=projection.SCHEMA,completion_policy=gate.COMPLETION_POLICY,
                completion_admission_sha256=base.file_hash(cp),progress_sha256=base.file_hash(path),remaining_charge_admission_sha256=base.file_hash(ap),strategy=arm,
                remaining_charge_activation_wall_ns=123,configuration=gate.CONFIGS[arm],time_policy=gate.TIME_POLICIES[arm],
                manifest_binding=base.digest(manifest),observer=dict(status='returned',io_error=None,heartbeat_error=None),
                projection_support_policy=gate.SUPPORT_POLICY,projection_support_statistics=counts(True))
            self.assertTrue(gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=result)['terminal_observer_health_proved'])
            self.assertFalse(gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')['terminal_observer_health_proved'])
            for mutate in [lambda x:x.update(completion_admission_sha256='0'*64),lambda x:x.update(schema=projection.SCHEMA),
                lambda x:x['observer'].update(io_error='OSError')]:
                bad=copy.deepcopy(result);mutate(bad)
                with self.assertRaises(ValueError):gate.read_progress(path,manifest,arm,common,search_status='SUCCESS',completed_result=bad)
            cp.write_bytes(base.canonical(dict(completion,arm=gate.ARMS[0])))
            with self.assertRaisesRegex(ValueError,'Outer'):gate.read_progress(path,manifest,arm,common,search_status='TIMEOUT')


if __name__=='__main__':unittest.main()
