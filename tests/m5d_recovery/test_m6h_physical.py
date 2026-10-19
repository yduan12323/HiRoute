"""Physical wrapper contracts and exposed tiny native regression; no holdout."""
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
from experiments.m6h_manifest_v1 import physical as gate
from experiments.m6h_manifest_v1 import physical_domain as adapter
from experiments.m6h_manifest_v1 import physical_inputs as inputs
from experiments.mechanism_recovery_v1 import run as base
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite,encode_binary64


def fixture(count=8,ordinal=0):
    case='unseen-name-synthetic-only'
    sites=[dict(site_id=f's{i}',anchor_id=f'road:{i+1}',effects=['C','S','CS']) for i in range(count)]
    query=dict(copy.deepcopy(inputs.PHYSICAL),case_id=case,origin='road:0',destination='road:200',
        H_ref=4,initial_energy_kwh='18',schedule=dict(a='400',b='700',D='2700'),
        hierarchy_sha256='a'*64,sparse_domain_sha256='b'*64)
    bound=dict(query=query,query_sha256=base.digest(query),candidate_site_ids=[s['site_id'] for s in sites],
        candidate_sha256=base.digest(sorted(s['site_id'] for s in sites)),
        site_catalog_sha256=site_catalog_digest({s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in sites}),
        anchor_catalog_sha256=base.digest({a:int(a.removeprefix('road:')) for a in ['road:0',*[s['anchor_id'] for s in sites],'road:200']}),
        sparse_domain_sha256=query['sparse_domain_sha256'])
    spec=dict(case_id=case+':N'+str(count),candidate_count=count,original_binding=bound,original_pool_prefix=sites)
    return dict(schema=gate.SCHEMA,launchable=True,status='frozen_m6h_domain_not_launched',case_id=case,
        candidate_count=count,case_binding=spec,selection_sha256='c'*64,protocol_sha256='d'*64,domain_ordinal=ordinal,
        method_order=['flat','hier'] if ordinal%2==0 else ['hier','flat'],
        shared_configuration=gate.cohort.shared_configuration(False),arms=gate.CONFIGS,
        pending_window_policy=gate.PENDING_WINDOW_POLICY,post_service_policy=gate.POST_SERVICE_POLICY,
        analytic_charge_policy=gate.ANALYTIC_POLICY,completion_policy=gate.COMPLETION_POLICY,
        method_policy=gate.METHOD_POLICY,limits=gate.LIMITS,cache_policy=base.CACHE_POLICY,
        inputs={n:dict(size=1,sha256='a'*64) for n in base.INPUT_NAMES},repo='/mock/repo',
        input_directory='/mock/inputs',compiler={},source={'closure_sha256':'e'*64})


def grid_fixture():
    from experiments.m6h_manifest_v1.contract import plan
    declaration=plan(6);manifests={}
    for ordinal,d in enumerate(declaration['domains']):
        m=fixture(d['candidate_count'],ordinal);g=d['group_slot'];case=f'new-group-{g}-soc-{d["soc"]}'
        m['case_id']=case;spec=m['case_binding'];spec['case_id']=case+':N'+str(d['candidate_count'])
        b=spec['original_binding'];q=b['query'];q['case_id']=case
        q['origin']=f'road:{1000*g}';q['destination']=f'road:{1000*g+200}'
        q['initial_energy_kwh']='18' if d['soc']=='3/10' else '228/5'
        b['query_sha256']=base.digest(q)
        anchors=[q['origin'],*[r['anchor_id'] for r in spec['original_pool_prefix']],q['destination']]
        b['anchor_catalog_sha256']=base.digest({a:int(a.removeprefix('road:')) for a in anchors})
        manifests[d['id']]=m
    return declaration,manifests


def selected_grid_fixture():
    from experiments.m6h_selection_v1.rules import group,RULE_VERSION
    declaration,manifests=grid_fixture();ods=[]
    for index in range(6):
        origin=dict(site_id=f'origin{index}',access_node=index*1000,lat=float(-70+index*20),lon=float(-100+index*20))
        destination=dict(site_id=f'destination{index}',access_node=index*1000+200,lat=float(-64+index*20),lon=float(-94+index*20))
        ods.append(dict(od_id=f'HOD{index:02d}',origin=origin,destination=destination,origin_site=origin['site_id'],destination_site=destination['site_id'],origin_anchor=origin['access_node'],
            destination_anchor=destination['access_node'],geographic_group=[list(c) for c in group(origin,destination)]))
    selection=dict(schema='hiroute.m6h.od_selection.v1',status='SELECTED',selected_group_count=6,no_replacement=True,
                   rule_version=RULE_VERSION,od=ods)
    for d in declaration['domains']:
        m=manifests[d['id']];case=f'HOD{d["group_slot"]:02d}_energy_and_scheduled_soc'+d['soc'].replace('/','_')
        m['case_id']=case;m['selection_sha256']=base.digest(selection);spec=m['case_binding'];spec['case_id']=case+':N'+str(d['candidate_count'])
        b=spec['original_binding'];b['query']['case_id']=case;b['query_sha256']=base.digest(b['query'])
    return declaration,manifests,selection


def input_failure(manifest,domain):
    names=('domain_ordinal','case_id','candidate_count','method_order','selection_sha256','protocol_sha256',
           'inputs','source','compiler','repo','input_directory')
    return dict({n:copy.deepcopy(manifest[n]) for n in names},schema='hiroute.m6h.input_failure.v1',status='FAILED_INPUT',
                domain_id=domain['id'],reason_code='INVALID_INPUT',failure_stage='input_generation',
                solver_invoked=False,replacement=False)


def tiny_domain(root,arm,required_hmax=None,manifest=None):
    from test_projection_support_gate import tiny_domain as support_domain
    original=support_domain(root/'original','support_on');query=json.loads(original.query_bytes)
    query['schedule']=dict(a=2,b=30,D=1);query['H_ref']=4
    sites={sid:RealSite(s.site_id,s.anchor_id,('C','S','CS')) for sid,s in original.sites.items()}
    spec={'case_id':'synthetic-only','candidate_count':len(sites)}
    sources=original.source_hashes if manifest is None else dict(
        {n:manifest['inputs'][n+'.parquet']['sha256'] for n in ('nodes','edges')},
        source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in manifest['inputs'].items()})
    return adapter.ScheduledMethodDomain(arm=arm,required_hmax=required_hmax,
        case_binding=spec,manifest_binding=base.digest('m6h tiny' if manifest is None else manifest),
        graph_factory=original.graph_factory,query=query,sites=sites,tree=original.tree,
        source_hashes=sources,cache=root/'method',compiler=original.compiler['compiler'])


class PhysicalContractTests(unittest.TestCase):
    def test_recovery_grid_explicit_scope_and_graph_binding(self):
        from experiments.m6h_manifest_v1.physical_queue_adapter import validate_manifest_grid
        declaration,manifests,selection=selected_grid_fixture()
        admission={'registry_sha256':'a'*64}
        first=next(iter(manifests.values()))
        selection.update(rule_version='hiroute.m6h.selection_rules.disclosed_recovery.v1',
            recovery_admission_sha256=base.digest(admission),exposure_registry_sha256='a'*64,
            strict_independent_holdout_claim=False,exposure_mode='disclosed_incomplete_recovery',
            generalization_scope='new_map_correctness_and_performance_validation_with_incomplete_history',
            graph_file_identity={k+'_sha256':first['inputs'][k+'.parquet']['sha256'] for k in ('nodes','edges')})
        for m in manifests.values():m['selection_sha256']=base.digest(selection)
        validate_manifest_grid(declaration,manifests,selection,recovery_admission=admission)
        with self.assertRaises(ValueError):validate_manifest_grid(declaration,manifests,selection)
        selection['graph_file_identity']['nodes_sha256']='f'*64
        for m in manifests.values():m['selection_sha256']=base.digest(selection)
        with self.assertRaises(ValueError):validate_manifest_grid(declaration,manifests,selection,recovery_admission=admission)

    def test_real_selection_pool_outputs_roundtrip_to_bound_grid(self):
        import pandas as pd
        from experiments.m6h_selection_v1 import rules
        from experiments.m6h_manifest_v1.physical_queue_adapter import validate_manifest_grid
        from tests.test_m6h_selection_rules import registry,site
        selection=rules.select_od_slate([site(i,lon=i*2+.1) for i in range(16)],registry(),site_catalog_sha256='a'*64)
        declaration,manifests=grid_fixture();pools=[]
        for index,od in enumerate(selection['od']):
            a,b=od['origin'],od['destination']
            rows=[site(100+i,lat=a['lat'],lon=a['lon']+(b['lon']-a['lon'])*(i+1)/140) for i in range(128)]
            # Overlapping capability greedily exhausts S despite 128 eligible
            # Sites and >=64 of each capability. Preserve the literal failure.
            if index==0:
                rows=[site(100+i,lat=a['lat'],lon=a['lon']+(b['lon']-a['lon'])*(.5+i*.005)) for i in range(64)]
                rows += [site(200+i,lat=a['lat'],lon=a['lon']+(b['lon']-a['lon'])*(.0001+i*.000001),meal=0) for i in range(64)]
            try:pool=rules.build_capability_pool(a,b,rows,od_id=od['od_id'])
            except rules.PoolFailure as exc:pool=dict(od_id=od['od_id'],status='FAILED_INPUT',reason_code=str(exc),sites=[])
            pools.append(pool)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pd.DataFrame({'node_id':range(230)}).to_parquet(root/'nodes.parquet',index=False)
            pd.DataFrame(dict(source=[0],target=[1],travel_time_s=[1.],length_m=[1.])).to_parquet(root/'edges.parquet',index=False)
            for name,value in [('metadata.json',dict(node_count=230,edge_count=1)),('queries.json',{'synthetic_only':True}),
                               ('pools.json',dict(pools=pools)),('hierarchy.json',{'synthetic_only':True})]:
                (root/name).write_bytes(base.canonical(value))
            hashes={name:dict(size=(root/name).stat().st_size,sha256=hashlib.sha256((root/name).read_bytes()).hexdigest()) for name in base.INPUT_NAMES}
            for d in declaration['domains']:
                m=manifests[d['id']];od=selection['od'][d['group_slot']];pool=pools[d['group_slot']]
                case=od['od_id']+'_energy_and_scheduled_soc'+d['soc'].replace('/','_')
                m.update(case_id=case,selection_sha256=base.digest(selection),inputs=hashes,input_directory=tmp)
                if pool['status']=='FAILED_INPUT':
                    m=input_failure(m,d);m['reason_code']=pool['reason_code'];manifests[d['id']]=m
                else:
                    spec=m['case_binding'];spec['case_id']=case+':N'+str(d['candidate_count'])
                    prefix=copy.deepcopy(pool['sites'][:d['candidate_count']]);spec['original_pool_prefix']=prefix
                    binding=spec['original_binding'];q=binding['query'];q.update(case_id=case,origin=f"road:{od['origin_anchor']}",destination=f"road:{od['destination_anchor']}",hierarchy_sha256=hashes['hierarchy.json']['sha256'])
                    binding.update(query_sha256=base.digest(q),candidate_site_ids=[s['site_id'] for s in prefix],
                        candidate_sha256=base.digest(sorted(s['site_id'] for s in prefix)),
                        site_catalog_sha256=site_catalog_digest({s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in prefix}),
                        anchor_catalog_sha256=base.digest({a:int(a.removeprefix('road:')) for a in [q['origin'],q['destination'],*[s['anchor_id'] for s in prefix]]}))
                path=root/(d['id']+'.json');path.write_bytes(base.canonical(m));manifests[d['id']]=json.loads(path.read_bytes())
            validate_manifest_grid(declaration,manifests,json.loads(base.canonical(selection)))
            self.assertEqual(sum(m['status']=='FAILED_INPUT' for m in manifests.values()),5)
            # Whole-128 pool failure cannot salvage a smaller fixed domain.
            bad=copy.deepcopy(manifests)
            for m in bad.values():
                if m['status']=='FAILED_INPUT':m['reason_code']='CAPABILITY_EXHAUSTED'
            validate_manifest_grid(declaration,bad,selection)
            slot=next(d['id'] for d in declaration['domains'] if d['group_slot']==0)
            bad[slot]['reason_code']='INVALID_INPUT'
            with self.assertRaisesRegex(ValueError,'whole-pool'):validate_manifest_grid(declaration,bad,selection)
            base.verify_inputs(root,hashes)
        # Exact producer vocabulary must be retained, never silently remapped.
        self.assertIn('CAPABILITY_EXHAUSTED',inputs.INPUT_FAILURE_REASONS)
        self.assertNotIn('CANDIDATE_EXHAUSTED',inputs.INPUT_FAILURE_REASONS)

    def test_graph_raw_schema_rejects_coercion_and_zero_time(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in base.INPUT_NAMES:(root/name).write_bytes(b'{}')
            (root/'metadata.json').write_bytes(base.canonical(dict(node_count=3,edge_count=1)))
            pd.DataFrame({'node_id':[0,1,2]}).to_parquet(root/'nodes.parquet',index=False)
            def check(source=1,time=1.):
                pd.DataFrame(dict(source=[source],target=[2],travel_time_s=[time],length_m=[1.])).to_parquet(root/'edges.parquet',index=False)
                bindings={n:dict(size=(root/n).stat().st_size,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest()) for n in base.INPUT_NAMES}
                return gate.load_bound_graph(root,bindings,dict(origin='road:0',destination='road:2'),{})
            self.assertEqual(check().source.tolist(),[1])
            for source,time in [(1.5,1.),(True,1.),(-1,1.),(3,1.),(1,0.),(1,True),(1,float('nan'))]:
                with self.subTest(source=source,time=time),self.assertRaises(ValueError):check(source,time)
            pd.DataFrame({'node_id':[0,0,2]}).to_parquet(root/'nodes.parquet',index=False)
            with self.assertRaises(ValueError):check()

    def test_generic_names_sizes_and_alternating_order(self):
        for n in (8,32,128):
            for ordinal in (0,1): inputs.validate_manifest_contract(fixture(n,ordinal))
        self.assertEqual(adapter.CONFIGS,gate.CONFIGS)
        self.assertEqual(adapter.CONFIGS['flat']['shared_configuration'],adapter.CONFIGS['hier']['shared_configuration'])

    def test_plan_policy_and_binding_drift_fail(self):
        for key,new in [('candidate_count',8.0),('domain_ordinal',True),('selection_sha256','bad'),('method_order',['hier','flat'])]:
            value=fixture();value[key]=new
            with self.subTest(key=key):
                with self.assertRaises(ValueError):inputs.validate_manifest_contract(value)
        for key,new in [('capacity_kwh','30'),('overhead_s',300),('schedule',dict(a='400',b='701',D='2700'))]:
            value=fixture();b=value['case_binding']['original_binding'];b['query'][key]=new;b['query_sha256']=base.digest(b['query'])
            with self.subTest(key=key):
                with self.assertRaises(ValueError):inputs.validate_manifest_contract(value)
        value=fixture();value['case_binding']['original_pool_prefix'][1]['site_id']='s0'
        with self.assertRaises(ValueError):inputs.validate_manifest_contract(value)

    def test_direct_baseline_exact_numeric_binding(self):
        query=fixture()['case_binding']['original_binding']['query']
        value=dict(time_s=encode_binary64(1000.),actual_length_m=encode_binary64(1200.),selected_edges=[1,2])
        gate.validate_direct_baseline(value,query)
        for key,new in [('time_s',encode_binary64(1001.)),('selected_edges',[True]),('actual_length_m',{'hex':'0x0p+0','ratio':['-1','1']})]:
            damaged=copy.deepcopy(value);damaged[key]=new
            with self.assertRaises(ValueError):gate.validate_direct_baseline(damaged,query)

    def test_root_gate_precedes_real_input_io(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('must not read')):
            with self.assertRaises(PermissionError):gate._manifest('/never-open','a'*64)
            with self.assertRaises(PermissionError):gate.extract_case('/never-open','x',{},fixture())
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/'must-not-create'
            with self.assertRaises(PermissionError):gate.prepare_case(fixture(),fixture()['case_id'],target)
            self.assertFalse(target.exists())

    def test_phase_order_index_and_strict_type(self):
        manifest=fixture(8,1)
        identity=gate.phase_identity(manifest,'a'*64,'hier','b'*64)
        self.assertEqual(identity['arm_index'],'0')
        receipt=dict(status='SUCCESS',phase_budget=dict(seconds=1200,identity=dict(identity,nonce='x')),
                     phase_entered_monotonic=1.)
        gate.require_search_phase(manifest,'a'*64,'hier','b'*64,receipt)
        receipt['phase_budget']['seconds']=1200.0
        with self.assertRaises(ValueError):gate.require_search_phase(manifest,'a'*64,'hier','b'*64,receipt)

    def test_fresh_selected_fastest_baseline_replay(self):
        manifest=fixture();q=manifest['case_binding']['original_binding']['query']
        baseline=dict(time_s=encode_binary64(1000.),actual_length_m=encode_binary64(1200.),selected_edges=[1,2])
        with tempfile.TemporaryDirectory() as root,patch.object(gate,'require_root_freeze'):
            raw=base.canonical(dict(queries=[dict(query_id=manifest['case_id'],baseline_direct_binary64=baseline)]))
            (Path(root)/'queries.json').write_bytes(raw);manifest['input_directory']=root
            manifest['inputs']['queries.json']=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            provider=SimpleNamespace(leg=lambda a,b:SimpleNamespace(reachable=True,time_hex=(1000.).hex(),length_hex=(1200.).hex()),
                edge_witnesses={(q['origin'],q['destination']):(1,2)})
            gate.verify_direct_baseline(manifest,manifest['case_id'],q,provider)
            provider.edge_witnesses[(q['origin'],q['destination'])]=(2,1)
            with self.assertRaises(ValueError):gate.verify_direct_baseline(manifest,manifest['case_id'],q,provider)

    def test_whole_grid_matches_fixed_slots_and_nested_prefixes(self):
        from experiments.m6h_manifest_v1.physical_queue_adapter import validate_manifest_grid
        from experiments.m6h_manifest_v1.contract import plan
        declaration,manifests=grid_fixture();validate_manifest_grid(declaration,manifests)
        with self.assertRaises(ValueError):validate_manifest_grid(plan(1),manifests)
        slot=declaration['domains'][6]['id']
        for field,new in [('domain_ordinal',0),('selection_sha256','f'*64),('case_id','changed')]:
            bad=copy.deepcopy(manifests);bad[slot][field]=new
            with self.subTest(field=field):
                with self.assertRaises(ValueError):validate_manifest_grid(declaration,bad)
        bad=copy.deepcopy(manifests);m=bad[slot];spec=m['case_binding'];prefix=spec['original_pool_prefix']
        prefix[0],prefix[1]=prefix[1],prefix[0]
        spec['original_binding']['candidate_site_ids']=[r['site_id'] for r in prefix]
        with self.assertRaisesRegex(ValueError,'nested'):validate_manifest_grid(declaration,bad)

    def test_common_seed_and_no_seed_contracts_preserved(self):
        manifest=fixture();case=manifest['case_id'];spec=manifest['case_binding'];binding=spec['original_binding']
        query=copy.deepcopy(binding['query']);query['sparse_domain_sha256']='f'*64
        tree='synthetic-tree';tree_sha=base.digest(tree)
        key=['12601/2','1',1,[['s0','CS']]]
        common=dict(schema=gate.SCHEMA,status='common_feasible_seed',case_id=case,candidate_count=8,
            case_binding_sha256=base.digest(spec),query=query,historical_query_sha256=binding['query_sha256'],
            sites=copy.deepcopy(spec['original_pool_prefix']),tree_sha256=tree_sha,
            seed=dict(max_depth=7,key_bytes=base.canonical(key).decode(),query_sha256=base.digest(query),
                      site_sha256=binding['site_catalog_sha256'],tree_sha256=tree_sha),
            source=manifest['source'],inputs=manifest['inputs'],cache_policy=manifest['cache_policy'])
        with patch.object(gate,'require_root_freeze'),patch.object(Path,'read_bytes',return_value=b'synthetic'),patch.object(base,'original_tree',return_value=tree),patch.object(base,'tree_value',side_effect=lambda x:x):
            gate.validate_common(common,case,manifest)
            for field,new in [('max_depth',7.0),('max_depth',4),('key_bytes',base.canonical(['12601/2','1',True,[['s0','CS']]]).decode())]:
                damaged=copy.deepcopy(common);damaged['seed'][field]=new
                with self.assertRaises(ValueError):gate.validate_common(damaged,case,manifest)
            note=dict(schema=gate.SCHEMA,status='seed_exhausted_unknown',classification='normal_original_proposal_stream_exhaustion',
                case_id=case,candidate_count=8,case_binding_sha256=base.digest(spec),original_query_sha256=binding['query_sha256'],
                runtime_query_sha256=base.digest(query),query=query,tree_sha256=tree_sha,site_catalog_sha256=binding['site_catalog_sha256'],
                prospective_full_selection_sha256=manifest['selection_sha256'],manifest_sha256=base.digest(manifest),
                source=manifest['source'],inputs=manifest['inputs'],proposal_count=2,replay_rejections=2,stream_exhausted=True,
                feasibility='unknown',global_infeasibility_claim=False,charged_wall_ns=1,seed_policy=gate.development.POLICY['seed_policy'])
            gate.validate_no_seed(note,case,manifest)
            for field,new in [('stream_exhausted',False),('proposal_count',2.0),('global_infeasibility_claim',True),('replay_rejections',1)]:
                damaged=copy.deepcopy(note);damaged[field]=new
                with self.assertRaises(ValueError):gate.validate_no_seed(damaged,case,manifest)

    def test_queue_command_binds_common_source_and_method(self):
        from experiments.m6h_manifest_v1.physical_queue_adapter import PhysicalQueueAdapter
        manifest=fixture(8,1);obj=object.__new__(PhysicalQueueAdapter)
        obj._manifest=lambda domain:(manifest,dict(path='/synthetic/manifest',sha256='a'*64))
        domain=dict(id='synthetic');row=dict(operation='search',method='hier')
        context=dict(common=dict(path='/synthetic/common',sha256='b'*64))
        command=obj.command(domain,row,context)
        self.assertIn('--worker',command['argv']);self.assertIn('arm',command['argv'])
        self.assertEqual(command['phase_budget'].identity['method'],'hier')
        self.assertEqual(command['phase_budget'].identity['arm_index'],'0')
        self.assertEqual(command['phase_budget'].identity['common_sha256'],'b'*64)
        self.assertEqual(command['phase_budget'].seconds,1200)

    def test_frozen_input_failure_grid_retains_all_fixed_slots(self):
        from experiments.m6h_manifest_v1.physical_queue_adapter import validate_manifest_grid,PhysicalQueueAdapter
        declaration,manifests,selection=selected_grid_fixture()
        validate_manifest_grid(declaration,manifests,selection)
        first=declaration['domains'][0];failure=input_failure(manifests[first['id']],first)
        mixed=copy.deepcopy(manifests);mixed[first['id']]=failure
        validate_manifest_grid(declaration,mixed,selection)
        all_failed={d['id']:input_failure(manifests[d['id']],d) for d in declaration['domains']}
        validate_manifest_grid(declaration,all_failed,selection)
        self.assertEqual(len(all_failed),30)
        for field,new in [('solver_invoked',True),('replacement',True),('reason_code','TIMEOUT'),('domain_ordinal',True)]:
            bad=copy.deepcopy(mixed);bad[first['id']][field]=new
            with self.assertRaises(ValueError):validate_manifest_grid(declaration,bad,selection)
        obj=object.__new__(PhysicalQueueAdapter);obj._manifest=lambda d:(failure,{})
        obj.bindings={first['id']:dict(sha256='f'*64)}
        admitted=obj.preflight(first,{})
        self.assertEqual(admitted['status'],'FAILED_INPUT')
        self.assertEqual(admitted['frozen_record_sha256'],'f'*64)

    def test_selected_endpoint_and_geographic_drift_rejected(self):
        from experiments.m6h_manifest_v1.physical_queue_adapter import validate_manifest_grid
        declaration,manifests,selection=selected_grid_fixture()
        for mutate in ('anchor','group','overlap','version'):
            bad=copy.deepcopy(selection)
            if mutate=='anchor':bad['od'][0]['origin_anchor']+=1
            elif mutate=='group':bad['od'][0]['geographic_group'][0][0]+=1
            elif mutate=='overlap':bad['od'][1]=copy.deepcopy(bad['od'][0]);bad['od'][1]['od_id']='HOD01'
            else:bad['rule_version']='changed'
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError):validate_manifest_grid(declaration,manifests,bad)

    def test_failed_grid_still_requires_disjoint_endpoint_identities(self):
        from experiments.m6h_manifest_v1.physical_queue_adapter import validate_manifest_grid
        declaration,manifests,selection=selected_grid_fixture()
        failed={d['id']:input_failure(manifests[d['id']],d) for d in declaration['domains']}
        for mutate in ('shared_anchor','shared_site','origin_alias','destination_alias'):
            bad=copy.deepcopy(selection)
            if mutate=='shared_anchor':
                bad['od'][1]['origin']['access_node']=bad['od'][0]['origin_anchor']
                bad['od'][1]['origin_anchor']=bad['od'][0]['origin_anchor']
            elif mutate=='shared_site':
                bad['od'][1]['origin']['site_id']=bad['od'][0]['origin_site']
                bad['od'][1]['origin_site']=bad['od'][0]['origin_site']
            elif mutate=='origin_alias':bad['od'][0]['origin_site']='different'
            else:bad['od'][0]['destination_site']='different'
            records=copy.deepcopy(failed)
            for record in records.values():record['selection_sha256']=base.digest(bad)
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError):validate_manifest_grid(declaration,records,bad)

    def test_tiny_real_methods_full_depth_and_fresh_replay(self):
        from timecut5.bounded import _solve_problem
        answers=[];seeds=[];manifest=fixture();manifest['candidate_count']=1
        manifest['case_binding']={'case_id':'synthetic-only','candidate_count':1}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);first=tiny_domain(root/'seed','flat')
            with adapter.historical_operators(),first.context('verification') as context:
                witness=_solve_problem(first.problem(context),True).result.witness
            for arm in ('hier','flat'):
                domain=tiny_domain(root/arm,arm,manifest=manifest);seed=domain.freeze_seed(witness);seeds.append(seed)
                self.assertNotEqual(seed.max_depth,4)
                output=root/('result-'+arm);result=domain.run_arm(arm,seed,output,search_seconds=15)
                fresh=tiny_domain(root/('fresh-'+arm),arm,seed.max_depth,manifest=manifest)
                replayed=fresh.recover_durable(seed,output/'incumbent.json')
                replayed.update(status=result['status'],search_status='SUCCESS')
                answers.append(gate.validate_terminal(result,replayed,arm,seed.max_depth))
                self.assertEqual(result['Hmax'],seed.max_depth)
                self.assertEqual(result['seed_key'],json.loads(seed.key_bytes))
                from dataclasses import asdict
                seed_values=asdict(seed)
                for name in ('key_bytes','witness_bytes'):seed_values[name]=seed_values[name].decode()
                common=dict(query=json.loads(domain.query_bytes),tree_sha256=domain.tree_sha256,seed=seed_values)
                with patch.object(gate,'spec_for',return_value=manifest['case_binding']):
                    admitted=gate.read_progress(output/'progress/progress.json',manifest,arm,manifest['case_id'],common,
                        search_status='SUCCESS',completed_result=result)
                self.assertTrue(admitted['terminal_observer_health_proved'])
            self.assertEqual(seeds[0],seeds[1]);self.assertEqual(answers[0],answers[1])

if __name__=='__main__':unittest.main()
