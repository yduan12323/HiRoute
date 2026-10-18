"""Graph-free contract and tiny-native tests for the separately bound DEV gates."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.scalability_development_v1 import run as gate
from experiments.mechanism_recovery_v1 import run as base
from test_runner import native_test_domain


def tiny_domain(path, arm):
    original = native_test_domain(path/'original')
    return gate.ScalabilityDomain(arm=arm, manifest_binding=base.digest('tiny closed manifest'),
        graph_factory=original.graph_factory, query=json.loads(original.query_bytes),
        sites=original.sites, tree=original.tree, source_hashes=original.source_hashes,
        cache=path/arm, compiler=original.compiler['compiler'])


def synthetic_inputs(root):
    import hashlib
    from timecut5.real_legs import RealSite, TIE_POLICY
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.sparse_seed import sparse_domain_digest
    sites = [dict(site_id=f's{i:03}', anchor_id='road:1', effects=['C']) for i in range(128)]
    data = {'nodes.parquet':b'tiny nodes', 'edges.parquet':b'tiny edges', 'metadata.json':b'{}',
        'pools.json':base.canonical(dict(pools=[dict(od_id='OD10',sites=sites)])),
        'hierarchy.json':base.canonical(dict(site_ids=[s['site_id'] for s in sites],
            regions=[dict(parent=-1,children=[],members=list(range(128)))]))}
    bindings = {}
    for name, value in data.items():
        (root/name).write_bytes(value)
        bindings[name] = dict(size=len(value),sha256=hashlib.sha256(value).hexdigest())
    sources = dict(graph_nodes=bindings['nodes.parquet']['sha256'],graph_edges=bindings['edges.parquet']['sha256'],
        hierarchy=bindings['hierarchy.json']['sha256'],pools=bindings['pools.json']['sha256'],router_cpp='a'*64)
    query = dict(case_id=gate.CASE,origin='road:0',destination='road:2',H_ref=4,
        hierarchy_sha256=bindings['hierarchy.json']['sha256'],capacity_kwh='60',initial_energy_kwh='228/5',
        overhead_s='300',lambda_stop_s='600',schedule=None)
    closed = {}
    for count in (32,128):
        selected = {s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in sites[:count]}
        anchors = {'road:0':0,'road:1':1,'road:2':2}
        provider = dict(nodes=sources['graph_nodes'],edges=sources['graph_edges'],router=sources['router_cpp'],
            anchors=base.digest(anchors),tie_policy=hashlib.sha256(TIE_POLICY.encode()).hexdigest())
        domain = sparse_domain_digest(provider,site_catalog_digest(selected),base.digest(sorted(selected)),
            query['hierarchy_sha256'],query['origin'],query['destination'])
        q = dict(query,sparse_domain_sha256=domain)
        closed[str(count)] = dict(candidate_site_ids=list(selected),candidate_sha256=base.digest(sorted(selected)),
            site_catalog_sha256=site_catalog_digest(selected),anchor_catalog_sha256=base.digest(anchors),
            query=q,query_sha256=base.digest(q),sparse_domain_sha256=domain)
    document = dict(source_sha256=sources,queries=[dict(query_id=gate.CASE,od_id='OD10',bindings=closed)])
    raw = base.canonical(document);(root/'queries.json').write_bytes(raw)
    bindings['queries.json'] = dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    return bindings, document


class ScalabilityGateTests(unittest.TestCase):
    def test_closed_plan_and_separate_five_stage_denominator(self):
        for count in (32,128):
            m = gate.prospective(count)
            self.assertFalse(m['launchable']); self.assertFalse(m['auto_next_size'])
            self.assertEqual(m['prior_n32_gate_required'],count==128)
            self.assertEqual(m['denominator']['total_stages'],5)
            self.assertEqual(m['reserve_plan']['maximum_worker_cpu_soft_seconds'],2040)
            self.assertEqual(m['policy']['method'],'HIER')
        for bad in (True,31,64,129):
            with self.assertRaises(ValueError):gate.prospective(bad)

    def test_plan_and_policy_fail_closed_before_source_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json';m=gate.prospective()
            path.write_bytes(base.canonical(m))
            with self.assertRaisesRegex(ValueError,'not launchable'):gate._manifest(path,base.file_hash(path))
            for field,value in [('order',list(reversed(gate.ARMS))),('arms',{}),('limits',{}),('auto_next_size',True)]:
                changed=dict(m,launchable=True);changed[field]=value;path.write_bytes(base.canonical(changed))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_original_nested_domain_authentication(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);bindings,document=synthetic_inputs(root)
            a=gate.extract_case(root,32,bindings);b=gate.extract_case(root,128,bindings)
            self.assertEqual(list(a[1]),list(b[1])[:32]);self.assertEqual(len(b[1]),128)
            self.assertNotEqual(a[0]['sparse_domain_sha256'],b[0]['sparse_domain_sha256'])
            mutations=[lambda d:d['queries'][0]['bindings']['128']['candidate_site_ids'].reverse(),
                lambda d:d['queries'][0]['bindings']['128']['query'].update(initial_energy_kwh='10'),
                lambda d:d['queries'][0]['bindings']['32'].update(anchor_catalog_sha256='0'*64),
                lambda d:d['queries'][0]['bindings']['32'].update(sparse_domain_sha256='0'*64)]
            for mutate in mutations:
                changed=copy.deepcopy(document);mutate(changed);raw=base.canonical(changed)
                (root/'queries.json').write_bytes(raw)
                current=dict(bindings);current['queries.json']=dict(size=len(raw),sha256=base.file_hash(root/'queries.json'))
                with self.assertRaises(ValueError):gate.extract_case(root,32,current)

    def test_n128_is_blocked_without_prior_n32_and_n32_rejects_prior(self):
        with patch.object(gate,'_manifest',return_value=dict(candidate_count=128)):
            with self.assertRaisesRegex(ValueError,'requires authenticated'):gate.run_gate('m','h','o',0)
        with patch.object(gate,'_manifest',return_value=dict(candidate_count=32)):
            with self.assertRaisesRegex(ValueError,'cannot supply'):gate.run_gate('m','h','o',0,prior_path='old')

    def test_exact_phase_and_cleanup_needed_for_admission(self):
        def completed(operation, strategy=None):
            return dict(status='SUCCESS',cleanup_verified=True,worker_receipt=dict(result=dict(
                operation=operation,case_id=gate.CASE,strategy=strategy,
                summary=dict(status='common_feasible_seed' if operation=='prepare' else 'timeout_feasible_only'))))
        common=completed('prepare')
        stages=[dict(id='prepare-'+gate.CASE,operation='prepare',case=gate.CASE,status='SUCCESS')]
        arms=[]
        for index, strategy in enumerate(gate.ARMS):
            search=dict(status='TIMEOUT',reason='phase_timeout',phase_entered_monotonic=1,
                phase_budget=dict(seconds=120,identity=dict(case_id=gate.CASE,strategy=strategy,arm_index=str(index))),
                cleanup_verified=True)
            arms.append(dict(case=gate.CASE,pair=0,strategy=strategy,receipt=search,
                verification=completed('verify',strategy),status='timeout_feasible_only'))
            stages.extend([dict(id=f'search-{index}',operation='search',case=gate.CASE,strategy=strategy,status='TIMEOUT'),
                dict(id=f'verify-{index}',operation='verify',case=gate.CASE,strategy=strategy,status='SUCCESS')])
        ledger=dict(schema=gate.SCHEMA,status='COMPLETED',denominator=5,operational_admission=True,
            stages=stages,common={gate.CASE:common},arms=arms)
        gate.admission(ledger)
        for mutate in (lambda x:x['arms'][0]['receipt'].update(reason='wall_timeout'),
            lambda x:x['arms'][0]['verification'].update(cleanup_verified=False),
            lambda x:x['stages'][0].update(status='FAILED'),
            lambda x:x.update(operational_admission=False)):
            changed=copy.deepcopy(ledger);mutate(changed)
            with self.assertRaises(ValueError):gate.admission(changed)
        self.valid_ledger = ledger

    def test_failed_unknown_and_stage_receipt_mismatches_rejected(self):
        self.test_exact_phase_and_cleanup_needed_for_admission()
        ledger=self.valid_ledger
        for status in ('FAILED','UNKNOWN','PENDING','BLOCKED'):
            for match_stage in (False,True):
                with self.subTest(status=status,match_stage=match_stage):
                    changed=copy.deepcopy(ledger);changed['arms'][0]['receipt']['status']=status
                    if match_stage:changed['stages'][1]['status']=status
                    with self.assertRaises(ValueError):gate.admission(changed)
        mutations=(
            lambda x:x['stages'][1].update(status='SUCCESS'),
            lambda x:x['stages'][1].update(id='search-1'),
            lambda x:x['stages'][1].update(strategy='skyline_only'),
            lambda x:x['stages'][2].update(operation='prepare'),
            lambda x:x['arms'][0].update(case='other'),
            lambda x:x['arms'][0].update(status='attained_optimum'),
            lambda x:x['arms'][0]['receipt']['phase_budget']['identity'].update(arm_index='1'),
            lambda x:x['arms'][0]['verification']['worker_receipt']['result'].update(strategy='skyline_only'),
            lambda x:x['common'][gate.CASE]['worker_receipt']['result'].update(case_id='other'),
        )
        for mutate in mutations:
            changed=copy.deepcopy(ledger);mutate(changed)
            with self.assertRaises(ValueError):gate.admission(changed)

    def test_prior_gate_authenticates_digest_source_manifest_and_receipts(self):
        self.test_exact_phase_and_cleanup_needed_for_admission()
        ledger=copy.deepcopy(self.valid_ledger)
        source=dict(closure_sha256='a'*64)
        current=dict(gate.prospective(128),source=source)
        prior=dict(gate.prospective(32),source=source)
        ledger.update(candidate_count=32,source=source,manifest_path='prior-manifest',manifest_sha256='b'*64)
        def read_result(path):
            name=Path(path).name
            if name.startswith('prepare-'):return ledger['common'][gate.CASE]
            index=int(name.rsplit('-',1)[1])
            return ledger['arms'][index]['receipt' if name.startswith('arm-') else 'verification']
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'ledger.json';path.write_bytes(base.canonical(ledger));sha=base.file_hash(path)
            with patch.object(gate,'_manifest',return_value=prior), \
                patch.object(base,'load_worker_result',return_value={}), \
                patch('experiments.mechanism_recovery_v1.supervisor.read_result',side_effect=read_result):
                self.assertEqual(gate.prior_gate(path,sha,current)['candidate_count'],32)
                with self.assertRaisesRegex(ValueError,'digest mismatch'):gate.prior_gate(path,'0'*64,current)
                changed=copy.deepcopy(current);changed['source']={'closure_sha256':'c'*64}
                with self.assertRaisesRegex(ValueError,'source/count'):gate.prior_gate(path,sha,changed)
                changed=copy.deepcopy(current);changed['order']=list(reversed(gate.ARMS))
                with self.assertRaisesRegex(ValueError,'manifest differs'):gate.prior_gate(path,sha,changed)
                changed=copy.deepcopy(ledger);changed['candidate_count']=128;path.write_bytes(base.canonical(changed))
                with self.assertRaisesRegex(ValueError,'source/count'):gate.prior_gate(path,base.file_hash(path),current)
                path.write_bytes(base.canonical(ledger))
            with patch.object(gate,'_manifest',return_value=prior), \
                patch('experiments.mechanism_recovery_v1.supervisor.read_result',return_value={'status':'UNKNOWN'}):
                with self.assertRaisesRegex(ValueError,'receipt changed'):gate.prior_gate(path,sha,current)

    def test_runner_wiring_keeps_hier_and_fixed_first_order(self):
        manifest=dict(candidate_count=32,source={})
        ledger=dict(schema=gate.SCHEMA,status='FAILED_COMMON_PREPARATION',denominator=5,
            arms=[dict(strategy=a,status='BLOCKED') for a in gate.ARMS],stages=[])
        with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest), \
            patch.object(base,'_run_plan',return_value=ledger) as plan:
            result=gate.run_gate('manifest','hash',temp,0)
        self.assertFalse(result['operational_admission'])
        args=plan.call_args.kwargs
        self.assertEqual(args['fixed_cases'],(gate.CASE,));self.assertEqual(args['fixed_pairs'],[[gate.CASE,list(gate.ARMS)]])
        self.assertEqual(args['worker_module'],'experiments.scalability_development_v1.run')

    def test_runtime_source_closure_includes_new_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'experiments/scalability_development_v1';folder.mkdir(parents=True)
            (folder/'run.py').write_text('runtime v1')
            inherited=dict(closure={'src/example.py':'a'*64},closure_sha256='old',commit='b'*40)
            with patch.object(base,'source_identity',return_value=inherited):
                first=gate.source_identity(root)
                self.assertIn('experiments/scalability_development_v1/run.py',first['closure'])
                (folder/'run.py').write_text('runtime v2')
                second=gate.source_identity(root)
            self.assertNotEqual(first['closure_sha256'],second['closure_sha256'])

    def test_source_drift_rejected_before_input_access(self):
        m=gate.prospective();m.update(launchable=True,repo='repo',source={'commit':'old'},
            compiler=dict(path='compiler',sha256='c'*64,version='compiler version',flags=['-O3','-std=c++17']))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json';path.write_bytes(base.canonical(m));expected=base.file_hash(path)
            with patch.object(base,'file_hash',return_value='c'*64), \
                patch('subprocess.check_output',return_value='compiler version'), \
                patch.object(gate,'source_identity',return_value={'commit':'changed'}):
                with self.assertRaisesRegex(ValueError,'closure differs'):gate._manifest(path,expected)

    def test_each_supervisor_failure_keeps_five_stage_denominator(self):
        import resource
        for failed_at in range(5):
            m=dict(schema=gate.SCHEMA,repo='.',source=dict(closure_sha256='a'*64),candidate_count=32)
            responses=[dict(status='SUCCESS') for _ in range(failed_at)]+[dict(status='FAILED')]
            with self.subTest(stage=failed_at),tempfile.TemporaryDirectory() as temp, \
                patch.object(gate,'_manifest',return_value=m), \
                patch.object(base,'file_hash',return_value='b'*64), \
                patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only')), \
                patch('experiments.mechanism_recovery_v1.supervisor.run',side_effect=responses) as launch, \
                patch('os.sched_getaffinity',return_value={0}),patch('os.sched_setaffinity'), \
                patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)), \
                patch('resource.setrlimit'),patch('signal.signal'):
                result=gate.run_gate('manifest','sha',Path(temp)/'gate',0)
            self.assertEqual(result['denominator'],5);self.assertEqual(len(result['stages']),5)
            self.assertEqual(result['stages'][failed_at]['status'],'FAILED')
            self.assertEqual(launch.call_count,failed_at+1);self.assertFalse(result['operational_admission'])
            self.assertTrue(all(s['status']=='BLOCKED' for s in result['stages'][failed_at+1:]))

    def test_tiny_native_both_reducers_exact_key_and_fresh_replay(self):
        from timecut5.bounded import _solve_problem
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);baseline=tiny_domain(root,'baseline')
            with baseline.context('verification') as context:
                witness=_solve_problem(baseline.problem(context),True).result.witness
            seed=baseline.freeze_seed(witness);keys=[]
            for arm in gate.ARMS:
                domain=baseline if arm=='baseline' else tiny_domain(root,arm)
                self.assertEqual(domain.freeze_seed(witness),seed)
                output=root/('result-'+arm);result=domain.run_arm(arm,seed,output,search_seconds=2)
                recovered=domain.recover_durable(seed,output/'incumbent.json')
                self.assertEqual(result['accepted_key'],recovered['accepted_key']);keys.append(recovered['accepted_key'])
                metrics=json.loads((output/'metrics.json').read_bytes())
                self.assertTrue(metrics['counters_complete']);self.assertGreater(metrics['reducer']['calls'],0)
                self.assertEqual(metrics['configuration'],gate.CONFIGS[arm])
                self.assertIn('route_at_phase_start',metrics);self.assertIn('search_route_counter_deltas',metrics)
                self.assertIn('interval_distinct_source_count',metrics['routing_telemetry_search_delta'])
                self.assertIn('calls',metrics['durable_callback'])
                self.assertEqual(result['Hmax'],seed.max_depth)
                self.assertEqual(result['seed_key'],json.loads(seed.key_bytes))
            self.assertEqual(keys[0],keys[1])
            with self.assertRaises(ValueError):baseline.recover_durable(seed,root/'result-skyline_only/incumbent.json')
            baseline.config['reducer']='reduce_frontier_skyline'
            with self.assertRaisesRegex(ValueError,'policy changed'):baseline.check()


if __name__ == '__main__':unittest.main()
