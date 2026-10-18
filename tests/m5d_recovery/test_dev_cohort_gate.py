"""Graph-free fixed-cohort admission and tiny method-aware native lifecycle."""
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import resource
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from experiments.dev_cohort_v1 import run as gate
from experiments.dev_cohort_v1 import domain as adapter
from experiments.projection_support_gate_v1 import run as projection
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain,common_fixture,admission_fixture,echo,counts
from test_envelope_sweep_gate import envelope_counts
from timecut5.provenance import encoded
from synthetic_runtime_inputs import synthetic_cohort, toy_prefix, toy_binding


def tiny_domain(root,method,envelope=False):
    old=support_domain(root/'original','support_on')
    return adapter.CohortDomain(method=method,envelope_enabled=envelope,case_binding={'case_id':'tiny','candidate_count':len(old.sites)},
        manifest_binding=base.digest(['tiny cohort',envelope]),graph_factory=old.graph_factory,query=json.loads(old.query_bytes),
        sites=old.sites,tree=old.tree,source_hashes=old.source_hashes,cache=root/method,compiler=old.compiler['compiler'])


def singleton_counts(**kwargs):
    return dict(dict(schema=adapter.POLICY_SCHEMA,runtime_enabled=True,calls=0,original_none=0,active_calls=0,disabled_calls=0,strengthened_calls=0),**kwargs)


def ledger_fixture(timeout=False):
    manifest=dict(gate.prospective(False),source={'closure_sha256':'a'*64})
    status='TIMEOUT' if timeout else 'SUCCESS';outcome='timeout_feasible_only' if timeout else 'attained_optimum'
    common={c:dict(status='SUCCESS',cleanup_verified=True) for c in gate.CASES}
    stages=[dict(id='prepare-'+c,operation='prepare',case=c,status='SUCCESS') for c in gate.CASES];arms=[]
    for pair,(case,order) in enumerate(gate.PAIRS):
        for method in order:
            i=len(arms);receipt=dict(status=status,reason='phase_timeout' if timeout else 'success',cleanup_verified=True,phase_entered_monotonic=1,
                phase_budget=dict(seconds=240,identity=dict(case_id=case,strategy=method,arm_index=str(i),manifest_sha256='sha',source_closure_sha256='a'*64)))
            arms.append(dict(case=case,strategy=method,pair=pair,status=outcome,receipt=receipt,verification=dict(status='SUCCESS',cleanup_verified=True)))
            stages.extend([dict(id=f'search-{i}',operation='search',case=case,strategy=method,status=status),
                dict(id=f'verify-{i}',operation='verify',case=case,strategy=method,status='SUCCESS')])
    ledger=dict(status='COMPLETED',schema=gate.SCHEMA,denominator=15,stages=stages,arms=arms,common=common)
    def load(directory,receipt,operation,case,method=None):
        if operation=='prepare':return {'case_id':case,'seed':{'max_depth':gate.SPECS[case]['historical_hmax']}}
        value=dict(status=outcome,method=method,strategy=method,accepted_key=['8','1',1,[['s','C']]],case_binding_sha256=base.digest(gate.SPECS[case]))
        if operation=='verify':return dict(value,search_status=status)
        return dict(value,Hmax=gate.SPECS[case]['historical_hmax'],result=dict(H_ref=gate.SPECS[case]['historical_hmax'],
            result=dict(status='attained_optimum',J='8',Q_total='1',H=1,site_action_tuple=[['s','C']],lex_key=['8','1',1,[['s','C']]])))
    return manifest,ledger,load


class DevCohortGateTests(unittest.TestCase):
    def test_fixed_original_cohort15_slots_explicit_common_configuration(self):
        self.assertEqual([(c,gate.SPECS[c]['candidate_count'],gate.SPECS[c]['historical_hmax']) for c in gate.CASES],
            [('OD00_energy_only_soc19_25',32,28),('OD02_energy_only_soc3_10',128,33),('OD06_energy_and_scheduled_soc3_10',128,39)])
        self.assertEqual([p[1] for p in gate.PAIRS],[['flat','hier'],['hier','flat'],['flat','hier']])
        pending=gate.prospective();self.assertIs(pending['shared_configuration']['envelope_sweep'],False);self.assertFalse(pending['launchable'])
        self.assertFalse(pending['configuration_selection']['outcome_blind'])
        for invalid in (None,True,0,1):
            with self.assertRaises(ValueError):gate.prospective(invalid)
        for enabled in (False,):
            plan=gate.prospective(enabled);config=plan['shared_configuration']
            self.assertIs(config['envelope_sweep'],enabled);self.assertTrue(config['projection_support']);self.assertEqual(config['time_quantum_exponent'],10)
            self.assertEqual(plan['denominator'],dict(common_preparations=3,search_arms=6,independent_replays=6,total_stages=15))
            self.assertEqual(plan['reserve_plan']['total_exact_search_seconds'],1440);self.assertEqual(plan['limits']['search_seconds'],240)
            self.assertEqual(plan['reserve_plan']['maximum_worker_wall_seconds'],6480);self.assertEqual(plan['max_heavy_workers'],1)
        for bad in (None,0,1,'on'):
            with self.assertRaises(ValueError):adapter.shared_configuration(bad)
        with tempfile.TemporaryDirectory() as temp:
            for mutate in [lambda x:x.update(shared_configuration=None),lambda x:x['shared_configuration'].update(envelope_sweep=1),
                lambda x:x['cohort']['cases'][0].update(historical_hmax=4),lambda x:x.update(max_heavy_workers=2)]:
                value=copy.deepcopy(gate.prospective(False));value['launchable']=True;mutate(value);path=Path(temp)/'m.json';path.write_bytes(base.canonical(value))
                with self.assertRaises(ValueError):gate._manifest(path,base.file_hash(path))

    @synthetic_cohort
    def test_original_binding_extraction_retains_order_and_tree_delegate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'hierarchy.json').write_bytes(b'original topology')
            for name in ('nodes.parquet', 'edges.parquet', 'metadata.json'):
                (root/name).write_bytes(b'test-only graph loader placeholder')
            rows=[dict(query_id=c,od_id=gate.SPECS[c]['od_id'],bindings={str(gate.SPECS[c]['candidate_count']):toy_binding(gate.SPECS[c])}) for c in gate.CASES]
            pools=[dict(od_id=gate.SPECS[c]['od_id'],sites=toy_prefix(gate.SPECS[c])) for c in gate.CASES]
            (root/'queries.json').write_bytes(base.canonical(dict(queries=rows)));(root/'pools.json').write_bytes(base.canonical(dict(pools=pools)))
            for case in gate.CASES:
                with patch.object(base,'verify_inputs'),patch.object(base,'original_tree',return_value='unchanged tree') as tree:
                    query,sites,actual=gate.extract_case(root,case,gate.COHORT['inputs'])
                self.assertEqual(list(sites),toy_binding(gate.SPECS[case])['candidate_site_ids']);self.assertEqual(query['H_ref'],4)
                self.assertEqual(actual,'unchanged tree');self.assertEqual(tree.call_args.args[2],list(sites))
            rows[0]['bindings']['32']=copy.deepcopy(rows[0]['bindings']['32']);rows[0]['bindings']['32']['candidate_site_ids'].reverse()
            (root/'queries.json').write_bytes(base.canonical(dict(queries=rows)))
            with patch.object(base,'verify_inputs'),self.assertRaisesRegex(ValueError,'binding changed'):gate.extract_case(root,gate.CASES[0],gate.COHORT['inputs'])

    def test_hmax_mismatch_blocks_before_graph_or_method_launch(self):
        case=gate.CASES[0];spec=gate.SPECS[case]
        common=dict(case_id=case,candidate_count=spec['candidate_count'],case_binding_sha256=base.digest(spec),seed=dict(max_depth=4))
        with patch.object(base,'original_tree') as tree,self.assertRaisesRegex(ValueError,'BLOCKED_SEED_HMAX_MISMATCH'):
            gate.validate_common(common,case,gate.prospective(False))
        tree.assert_not_called()

    @synthetic_cohort
    def test_common_validation_preserves_query_order_hmax_and_topology(self):
        from timecut5.hierarchy import Region
        for case in gate.CASES:
            spec=gate.SPECS[case];binding=toy_binding(spec)
            tree=Region('retained-original-root',tuple(binding['candidate_site_ids']),())
            query=dict(binding['query'],sparse_domain_sha256='f'*64)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'hierarchy.json').write_bytes(b'original frozen topology')
                manifest=dict(gate.prospective(False),input_directory=temp,source={'closure_sha256':'a'*64})
                common=dict(case_id=case,candidate_count=spec['candidate_count'],case_binding_sha256=base.digest(spec),
                    query=query,historical_query_sha256=binding['query_sha256'],sites=toy_prefix(spec),
                    tree_sha256=base.digest(base.tree_value(tree)),source=manifest['source'],inputs=manifest['inputs'],cache_policy=manifest['cache_policy'],
                    seed=dict(max_depth=spec['historical_hmax'],site_sha256=binding['site_catalog_sha256'],query_sha256=base.digest(query),tree_sha256=base.digest(base.tree_value(tree))))
                with patch.object(base,'original_tree',return_value=tree):gate.validate_common(common,case,manifest)
                for mutate in [lambda x:x['sites'].reverse(),lambda x:x['query'].update(H_ref=5),
                    lambda x:x.update(tree_sha256='0'*64),lambda x:x['seed'].update(max_depth=4)]:
                    bad=copy.deepcopy(common);mutate(bad)
                    with patch.object(base,'original_tree',return_value=tree),self.assertRaises(ValueError):gate.validate_common(bad,case,manifest)

    def test_actual_supervisor_keeps_preparation_blocked_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest=dict(repo=temp,source={'closure_sha256':'a'*64},limits=gate.LIMITS)
            replies=[dict(status='FAILED'),dict(status='SUCCESS'),dict(status='SUCCESS')]+[dict(status='TIMEOUT'),dict(status='SUCCESS')]*4
            with patch('experiments.mechanism_recovery_v1.supervisor.run',side_effect=replies) as launch, \
                patch.object(base,'load_worker_result',return_value={'status':'timeout_feasible_only'}),patch.object(base,'file_hash',return_value='b'*64), \
                patch('os.sched_getaffinity',return_value={2}),patch('os.sched_setaffinity'), \
                patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)),patch('resource.setrlimit'),patch('signal.signal'):
                result=base._run_plan('m','sha',Path(temp)/'gate',2,scope='full_batch',manifest_loader=lambda *a:manifest,
                    fixed_cases=gate.CASES,fixed_pairs=gate.PAIRS,exact_phase_seconds=240)
            self.assertEqual(result['denominator'],15);self.assertEqual(len(result['stages']),15);self.assertEqual(launch.call_count,11)
            self.assertTrue(all(s['status']=='BLOCKED_COMMON_PREPARATION' for s in result['stages'][3:7]))
            self.assertEqual([c.kwargs['phase_budget'].seconds for c in launch.call_args_list if 'phase_budget' in c.kwargs],[240]*4)
            self.assertTrue(all(c.kwargs['limits'].address_space_bytes==8*1024**3 for c in launch.call_args_list))

    def test_fixed_ledger_terminal_semantics_and_blocked_denominator(self):
        for timeout in (False,True):
            manifest,ledger,load=ledger_fixture(timeout)
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger) as run, \
                patch.object(base,'load_worker_result',side_effect=load),patch.object(gate,'validate_common'),patch.object(gate,'read_progress',return_value={}):
                result=gate.run_gate('m','sha',temp,2)
            self.assertTrue(result['operational_admission']);self.assertEqual(result['all_pairs_authenticated_complete'],not timeout)
            self.assertEqual(run.call_args.kwargs['fixed_cases'],gate.CASES)
        for failure in ('prepare','unknown_stop','method','null','disagree','phase','progress','payload_key','payload_secondary','hmax','result_hmax','payload_h_bool','hmax_bool','result_hmax_bool'):
            manifest,ledger,load=ledger_fixture()
            if failure=='prepare':
                ledger['common'][gate.CASES[0]]['status']='FAILED';ledger['stages'][0]['status']='FAILED'
                for row in ledger['stages'][3:7]:row['status']='BLOCKED_COMMON_PREPARATION'
            if failure=='unknown_stop':
                ledger['status']='UNKNOWN'
                for row in ledger['stages'][3:]:row['status']='PENDING'
                for arm in ledger['arms']:arm['status']='PENDING'
            if failure=='phase':ledger['arms'][0]['receipt']['phase_budget']['seconds']=120
            def broken(directory,receipt,operation,case,method=None):
                value=load(directory,receipt,operation,case,method)
                if failure=='disagree' and operation in ('arm','verify') and method=='flat':value['accepted_key'][0]='9'
                if operation=='arm' and method=='flat':
                    if failure=='method':value['method']='hier'
                    if failure=='null':value['result']=None
                    if failure=='disagree':value['result']['result']['J']='9';value['result']['result']['lex_key'][0]='9'
                    if failure=='payload_key':value['result']['result']['lex_key'][0]='9'
                    if failure=='payload_secondary':value['result']['result']['Q_total']='2'
                    if failure=='hmax':value['Hmax']-=1
                    if failure=='result_hmax':value['result']['H_ref']-=1
                    if failure=='payload_h_bool':value['result']['result']['H']=True
                    if failure=='hmax_bool':value['Hmax']=True
                    if failure=='result_hmax_bool':value['result']['H_ref']=True
                return value
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest),patch.object(base,'_run_plan',return_value=ledger), \
                patch.object(base,'load_worker_result',side_effect=broken),patch.object(gate,'validate_common'), \
                patch.object(gate,'read_progress',side_effect=ValueError('final progress authentication failed') if failure=='progress' else None,return_value={}):
                result=gate.run_gate('m','sha',temp,2)
            self.assertFalse(result['operational_admission']);self.assertFalse(result['all_pairs_authenticated_complete']);self.assertEqual(len(result['stages']),15)
            if failure=='unknown_stop':self.assertTrue(all(s['status']=='BLOCKED_EXECUTION_STOPPED' for s in result['stages'][3:]))
            if failure=='progress':self.assertTrue(all(a['authenticated_completion'] is False for a in result['arms']))

    def test_attained_unattained_result_normalization_and_exact_equality(self):
        from timecut5.bounded import Problem,_solve_problem
        from timecut5.hierarchy import build_regions,_solve_hierarchical_problem
        from timecut5.remaining_charge_runtime import RemainingChargeBoundResultV1
        for effect in ('C','CS'):
            case=dict(origin='A',destination='D',start_time_s=0,initial_energy_kwh=1 if effect=='C' else 2,capacity_kwh=10,minimum_energy_kwh=0,reserve_kwh=0,
                overhead_s=1,lambda_stop_s=1,consumption_kwh_per_m=1,H_ref=1,sites={'s':[effect]},charging_segments=[[0,10,1,0]],
                schedule=dict(a=0,b=100,D=0) if effect=='CS' else None,
                edges=[dict(source='A',target='s',time_s=1,length_m=1),dict(source='s',target='D',time_s=1,length_m=1)])
            problem=Problem(case);original=Mock();original.singleton_bound.return_value=F(0)
            upper=F(5) if effect=='C' else F(4)
            runtime=Mock(binding_sha256='a'*64);runtime.evaluate_group.return_value=runtime.whole_route_lower_bound.return_value=RemainingChargeBoundResultV1('active',upper,'a'*64)
            singleton=adapter.RemainingChargeSingletonBound(original,problem,runtime=runtime)
            flat=_solve_problem(problem,verified_primary_upper=upper,singleton_bound=singleton.singleton_bound)
            hier=_solve_hierarchical_problem(problem,True,build_regions(problem.sites))
            self.assertEqual(adapter.normalize_result('flat',flat).canonical(),adapter.normalize_result('hier',hier).canonical())
            self.assertEqual(flat.result.status,'attained_optimum' if effect=='C' else 'infimum_unattained')
            self.assertGreater(flat.attempted_extensions,0)
            if effect=='CS':self.assertIsNone(flat.result.key);self.assertEqual(flat.canonical()['result']['status'],'primary_unattained')
            with self.assertRaises(ValueError):adapter.normalize_result('flat',hier)
            with self.assertRaises(ValueError):adapter.normalize_result('hier',flat)

    def test_unattained_payload_does_not_claim_its_feasible_key_is_infimum(self):
        case=gate.CASES[0];hmax=gate.SPECS[case]['historical_hmax']
        accepted=['8','1',1,[['s','C']]]
        full=dict(method='flat',status='infimum_unattained',search_status='SUCCESS',accepted_key=accepted)
        for payload in [dict(status='primary_unattained',primary_infimum='7'),dict(status='secondary_unattained',J='7',secondary_infimum='0')]:
            completed=dict(method='flat',strategy='flat',status='infimum_unattained',accepted_key=accepted,Hmax=hmax,result=dict(H_ref=hmax,result=payload))
            self.assertEqual(gate.validate_terminal(completed,full,'flat',hmax),payload)
            self.assertNotIn('lex_key',payload)

    def test_singleton_observer_counts_are_method_specific_and_censored(self):
        gate.validate_singleton_statistics(None,'hier',completed=True);gate.validate_singleton_statistics(singleton_counts(),'flat',completed=True)
        live=singleton_counts(calls=1);gate.validate_singleton_statistics(live,'flat',completed=False)
        with self.assertRaises(ValueError):gate.validate_singleton_statistics(live,'flat',completed=True)
        for value,method in [(singleton_counts(),'hier'),(None,'flat'),(singleton_counts(calls=True),'flat'),(singleton_counts(runtime_enabled=False),'flat')]:
            with self.assertRaises(ValueError):gate.validate_singleton_statistics(value,method,completed=False)

    def test_outer_method_progress_rejects_cross_method_stale_inner_and_health(self):
        common=common_fixture();case=gate.CASES[0];manifest=dict(gate.prospective(False),source={'closure_sha256':'c'*64})
        for method in adapter.METHODS:
            inner=admission_fixture('support_on',common);domain,sources=gate.progress_binding(manifest,method,case,common)
            value=dict(echo(inner),profile_schema=projection.SCHEMA,arm='support_on',configuration=projection.CONFIGS['support_on'],
                manifest_binding=base.digest(manifest),candidate_count=gate.SPECS[case]['candidate_count'],query_sha256=base.digest(common['query']),
                Hmax=2,status='returned',io_error=None,heartbeat_error=None,sampled_wall_ns=1,active_stack=[],maximum_observed_write_gap_ns=1,
                cohort_schema=gate.SCHEMA,method=method,shared_configuration=manifest['shared_configuration'],case_binding_sha256=base.digest(gate.SPECS[case]),
                method_policy=adapter.METHOD_POLICY,domain_sha256=domain,source_sha256=sources,
                projection_support_statistics=counts(True),envelope_sweep_statistics=envelope_counts(False),
                singleton_bound_statistics=singleton_counts() if method=='flat' else None)
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'progress').mkdir();path=root/'progress/progress.json';ip=root/'remaining_charge_admission.json';mp=root/'method_admission.json'
                ip.write_bytes(base.canonical(inner));value['remaining_charge_admission_sha256']=base.file_hash(ip)
                outer=adapter.method_admission(base.digest(manifest),method,manifest['shared_configuration'],gate.SPECS[case],base.file_hash(ip))
                mp.write_bytes(base.canonical(outer));value['method_admission_sha256']=base.file_hash(mp);path.write_bytes(base.canonical(value))
                result=dict(schema=gate.SCHEMA,strategy=method,method=method,inner_arm='support_on',case_binding_sha256=base.digest(gate.SPECS[case]),
                    shared_configuration=manifest['shared_configuration'],method_policy=adapter.METHOD_POLICY,method_admission_sha256=base.file_hash(mp),
                    remaining_charge_admission_sha256=base.file_hash(ip),progress_sha256=base.file_hash(path),remaining_charge_activation_wall_ns=123,
                    time_policy=projection.TIME_POLICIES['support_on'],configuration=projection.CONFIGS['support_on'],manifest_binding=base.digest(manifest),
                    observer=dict(status='returned',io_error=None,heartbeat_error=None),projection_support_policy=projection.SUPPORT_POLICY,
                    projection_support_statistics=counts(True),envelope_sweep_statistics=envelope_counts(False),
                    singleton_bound_statistics=value['singleton_bound_statistics'])
                self.assertTrue(gate.read_progress(path,manifest,method,case,common,search_status='SUCCESS',completed_result=result)['terminal_observer_health_proved'])
                self.assertFalse(gate.read_progress(path,manifest,method,case,common,search_status='TIMEOUT')['terminal_observer_health_proved'])
                for mutate in [lambda x:x.update(method='hier' if method=='flat' else 'flat'),lambda x:x.update(case_binding_sha256='0'*64),
                    lambda x:x.update(progress_sha256='0'*64),lambda x:x['observer'].update(io_error='OSError')]:
                    bad=copy.deepcopy(result);mutate(bad)
                    with self.assertRaises(ValueError):gate.read_progress(path,manifest,method,case,common,search_status='SUCCESS',completed_result=bad)
                mp.write_bytes(base.canonical(dict(outer,method='hier' if method=='flat' else 'flat')))
                with self.assertRaisesRegex(ValueError,'Outer'):gate.read_progress(path,manifest,method,case,common,search_status='TIMEOUT')
                stale=dict(inner,arm='support_off',projection_support_enabled=False);ip.write_bytes(base.canonical(stale))
                outer['inner_admission_sha256']=base.file_hash(ip);mp.write_bytes(base.canonical(outer))
                value.update(method_admission_sha256=base.file_hash(mp),remaining_charge_admission_sha256=base.file_hash(ip),projection_support_enabled=False)
                path.write_bytes(base.canonical(value))
                with self.assertRaisesRegex(ValueError,'activation policy'):gate.read_progress(path,manifest,method,case,common,search_status='TIMEOUT')

    def test_preparation_mismatch_diagnostic_is_retained_not_admitted(self):
        case=gate.CASES[0];spec=gate.SPECS[case]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'artifacts/prepared';root.mkdir(parents=True)
            common={'case_id':case,'seed':{'max_depth':4}};(root/'common.json').write_bytes(base.canonical(common))
            note=dict(schema=gate.SCHEMA,case_id=case,reason='BLOCKED_SEED_HMAX_MISMATCH',expected=spec['historical_hmax'],observed=4,
                common_sha256=base.file_hash(root/'common.json'),case_binding_sha256=base.digest(spec))
            (root/'blocked.json').write_bytes(base.canonical(note));actual=gate.blocked_preparation_diagnostic(temp,case)
            self.assertEqual(actual['observed'],4);self.assertFalse(actual['preparation_admitted']);self.assertTrue(actual['diagnostic_only'])
            note['observed']=spec['historical_hmax'];(root/'blocked.json').write_bytes(base.canonical(note))
            with self.assertRaises(ValueError):gate.blocked_preparation_diagnostic(temp,case)

    def test_tiny_method_lifecycle_same_key_fresh_full_replay_and_tags(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import envelope_sweep,pwa
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,m,False) for m in adapter.METHODS]
            with domains[0].context('verification') as context:witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed);out=root/('result-'+domain.method)
                result=domain.run_arm(domain.method,seed,out,search_seconds=8)
                self.assertEqual(result['method'],domain.method);self.assertEqual(result['status'],'attained_optimum')
                self.assertEqual(domain.arm,'support_on');self.assertEqual(result['Hmax'],seed.max_depth)
                record=json.loads((out/'incumbent.json').read_bytes());self.assertEqual(record['payload']['method'],domain.method)
                fresh=tiny_domain(root/('fresh-'+domain.method),domain.method,False)
                recovered=fresh.recover_durable(seed,out/'incumbent.json');keys.append(recovered['accepted_key'])
                self.assertEqual(result['accepted_key'],keys[-1]);self.assertEqual(recovered['method'],domain.method)
                with fresh.context('verification') as context:self.assertEqual(context.router.mode,'full')
                gate.validate_singleton_statistics(result['singleton_bound_statistics'],domain.method,completed=True)
                if domain.method=='flat':self.assertGreater(result['singleton_bound_statistics']['active_calls'],0)
                else:self.assertIsNone(result['singleton_bound_statistics'])
                self.assertTrue(result['projection_support_statistics']['enabled']);self.assertFalse(result['envelope_sweep_statistics']['enabled'])
                self.assertIsNone(envelope_sweep._active.get());self.assertIsNone(pwa._projection_support_prefilter.get())
                bad=copy.deepcopy(record);bad['payload']['method']='hier' if domain.method=='flat' else 'flat'
                import hashlib
                bad['sha256']=hashlib.sha256(encoded(bad['payload']).encode()).hexdigest();path=out/'wrong-method.json';path.write_text(encoded(bad))
                with self.assertRaisesRegex(ValueError,'method tag'):fresh.recover_durable(seed,path)
            self.assertEqual(keys[0],keys[1])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/'result-hier/incumbent.json')


if __name__=='__main__':unittest.main()
