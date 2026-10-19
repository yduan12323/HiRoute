"""Frozen source-to-domain producer; real entry remains held before any I/O.

The sole runnable entry generates a fixed, internally constructed synthetic
catalogue and graph. It cannot accept replacement input paths or data objects.
"""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import io
import json
import os
import stat
from pathlib import Path
import shutil
import subprocess
import tempfile

from .contract import canonical, digest, plan
from .physical_inputs import INPUT_NAMES, PHYSICAL, require_root_freeze
from experiments.m6h_selection_v1 import rules


def _write(path, value):
    path.write_bytes(canonical(value))
    return dict(path=str(path.resolve()), sha256=_hash(path.read_bytes()))


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _identities(root):
    return {n:dict(size=(root/n).stat().st_size,sha256=_hash((root/n).read_bytes())) for n in INPUT_NAMES}


def compiler_identity():
    path=str(Path(shutil.which('g++')).resolve())
    return dict(path=path,sha256=_hash(Path(path).read_bytes()),
        version=subprocess.check_output([path,'--version'],text=True),flags=['-O3','-std=c++17'])


def _check_budget(budget):
    if budget is None:raise ValueError('Same-process enclosing Budget required')
    if min(budget.remaining())<=0:raise RuntimeError('Global generation budget exhausted')


def generate_preprocessed(*args, **kwargs):
    """Future real entry: fail closed before opening any supplied source."""
    raise PermissionError('Historical generic generation entry remains held')


def _produce(output, *, graph_files, site_rows, hierarchy_bytes, exposure_registry,
             repo, compiler, source, budget, protocol_sha256=None, site_catalog_sha256=None, recovery_admission=None):
    """Trusted frozen implementation shared with the sealed built-in fixture.

    Selection is persisted before any pool or direct-route computation. Invalid
    whole-OD inputs retain all five planned domains. Integrity errors propagate;
    no exception from source/native authentication becomes an input failure.
    """
    from . import physical
    from .physical_queue_adapter import validate_manifest_grid
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.real_legs import RealSite, encode_binary64
    from timecut5.sparse_seed import sparse_domain_digest
    from experiments.mechanism_recovery_v1 import run as base
    _check_budget(budget)
    root=Path(output).resolve();root.mkdir(parents=True,exist_ok=False)
    directory=root/'inputs';directory.mkdir()
    for name in ('nodes.parquet','edges.parquet','metadata.json'):
        (directory/name).write_bytes(graph_files[name])
    (directory/'hierarchy.json').write_bytes(hierarchy_bytes)
    _write(directory/'queries.json',dict(queries=[]));_write(directory/'pools.json',dict(pools=[]))
    selection_options={}
    if recovery_admission is not None:
        selection_options=dict(recovery_admission=recovery_admission,graph_file_identity={
            'nodes_sha256':_hash(graph_files['nodes.parquet']),
            'edges_sha256':_hash(graph_files['edges.parquet'])})
    selection=rules.select_od_slate(site_rows,exposure_registry,
        site_catalog_sha256=site_catalog_sha256 or digest(site_rows),**selection_options)
    selected=_write(root/'selection.json',selection)
    _write(root/'exposure.json',exposure_registry)
    if selection['status']!='SELECTED':
        if source!=physical.source_identity(repo) or compiler!=compiler_identity():
            raise ValueError('Source/compiler changed during selection')
        return dict(status='DATA_LIMITED',selection_binding=selected,selection=selection,source=source,compiler=compiler,
                    measured_generation=budget.measured(),replacement=False)
    declaration=plan(6);pools=[];failures={};query_rows=[];bindings_by_case={}
    # Authenticate graph raw types before native construction. Placeholder JSON
    # is confined to this staging directory; its final identities are recomputed.
    inputs=_identities(directory)
    try:
        graph=physical.load_bound_graph(directory,inputs,dict(origin='road:0',destination='road:1'),{})
    except physical.InvalidGraphInput:
        graph=None
        failures.update({od['od_id']:'INVALID_INPUT' for od in selection['od']})
    hierarchy_sha=_hash(hierarchy_bytes)
    for od in selection['od']:
        _check_budget(budget)
        if graph is None:
            pools.append(dict(od_id=od['od_id'],status='FAILED_INPUT',reason_code='INVALID_INPUT',sites=[]))
            continue
        try:
            pool=rules.build_capability_pool(od['origin'],od['destination'],site_rows,od_id=od['od_id'])
        except (rules.PoolFailure,rules.InvalidInput) as exc:
            reason=str(exc) if isinstance(exc,rules.PoolFailure) else 'INVALID_INPUT'
            failures[od['od_id']]=reason
            pool=dict(od_id=od['od_id'],status='FAILED_INPUT',reason_code=reason,sites=[])
        pools.append(pool)
        if pool['status']=='FAILED_INPUT':continue
        anchors=[od['origin_anchor'],od['destination_anchor'],*[r['access_node'] for r in pool['sites']]]
        if any(type(a) is not int or not 0<=a<graph.node_count for a in anchors):
            failures[od['od_id']]='INVALID_ANCHOR';continue
        try:base.original_tree(hierarchy_bytes,hierarchy_sha,[r['site_id'] for r in pool['sites']])
        except ValueError:
            failures[od['od_id']]='HIERARCHY_COVERAGE';continue
        direct=None
        for soc,energy in (('3/10','18'),('19/25','228/5')):
            case=od['od_id']+'_energy_and_scheduled_soc'+soc.replace('/','_');bindings={}
            for n in ((8,32,128) if soc=='3/10' else (32,128)):
                _check_budget(budget)
                prefix=pool['sites'][:n]
                sites={r['site_id']:RealSite(r['site_id'],r['anchor_id'],tuple(r['effects'])) for r in prefix}
                tree=base.original_tree(hierarchy_bytes,hierarchy_sha,list(sites))
                query=dict(deepcopy(PHYSICAL),case_id=case,origin=f"road:{od['origin_anchor']}",
                    destination=f"road:{od['destination_anchor']}",H_ref=4,initial_energy_kwh=energy,
                    schedule=dict(a='1',b='7/4',D='2700'),hierarchy_sha256=hierarchy_sha,sparse_domain_sha256='0'*64)
                domain=base.NativeDomain(graph_factory=lambda:graph,query=query,sites=sites,tree=tree,
                    source_hashes={k:inputs[k+'.parquet']['sha256'] for k in ('nodes','edges')},
                    cache=root/'generation-native',compiler=compiler['path'],cache_policy=base.CACHE_POLICY)
                with domain.context('generation') as context:
                    leg=context.provider.leg(query['origin'],query['destination'])
                    if not leg.reachable:
                        failures[od['od_id']]='INVALID_WINDOW';break
                    record=dict(time_s=encode_binary64(float.fromhex(leg.time_hex)),
                        actual_length_m=encode_binary64(float.fromhex(leg.length_hex)),
                        selected_edges=list(context.provider.edge_witnesses[query['origin'],query['destination']]))
                    if direct is not None and record!=direct:raise ValueError('Direct baseline changed across prefixes')
                    direct=record;T=F(float.fromhex(leg.time_hex))
                    if T<=0:failures[od['od_id']]='INVALID_WINDOW';break
                    query['schedule']=dict(a=str(F(2,5)*T),b=str(F(7,10)*T),D='2700')
                    query['sparse_domain_sha256']=sparse_domain_digest(context.provider.source_sha256,
                        site_catalog_digest(sites),digest(sorted(sites)),hierarchy_sha,query['origin'],query['destination'])
                physical.validate_direct_baseline(direct,query)
                anchor_map={a:int(a.removeprefix('road:')) for a in [query['origin'],*[s.anchor_id for s in sites.values()],query['destination']]}
                binding=dict(query=query,query_sha256=digest(query),candidate_site_ids=list(sites),candidate_sha256=digest(sorted(sites)),
                    site_catalog_sha256=site_catalog_digest(sites),anchor_catalog_sha256=digest(anchor_map),sparse_domain_sha256=query['sparse_domain_sha256'])
                bindings[str(n)]=binding
            bindings_by_case[case]=bindings
            if od['od_id'] in failures:break
            query_rows.append(dict(query_id=case,od_id=od['od_id'],baseline_direct_binary64=direct,bindings=bindings))
    query_rows=[r for r in query_rows if r['od_id'] not in failures]
    _write(directory/'queries.json',dict(queries=query_rows));_write(directory/'pools.json',dict(pools=pools))
    inputs=_identities(directory);manifests={};manifest_bindings={}
    for ordinal,d in enumerate(declaration['domains']):
        _check_budget(budget)
        od=selection['od'][d['group_slot']];case=od['od_id']+'_energy_and_scheduled_soc'+d['soc'].replace('/','_')
        common=dict(case_id=case,candidate_count=d['candidate_count'],domain_ordinal=ordinal,method_order=d['method_order'],
            selection_sha256=selected['sha256'],protocol_sha256=protocol_sha256 or digest(declaration),inputs=inputs,
            repo=str(Path(repo).resolve()),input_directory=str(directory),compiler=compiler,source=source)
        if od['od_id'] in failures:
            m=dict(common,schema='hiroute.m6h.input_failure.v1',status='FAILED_INPUT',domain_id=d['id'],
                reason_code=failures[od['od_id']],failure_stage='input_generation',solver_invoked=False,replacement=False)
        else:
            n=d['candidate_count'];pool=pools[d['group_slot']]
            spec=dict(case_id=case+':N'+str(n),candidate_count=n,original_binding=bindings_by_case[case][str(n)],original_pool_prefix=pool['sites'][:n])
            m=dict(common,schema=physical.SCHEMA,launchable=True,status='frozen_m6h_domain_not_launched',case_binding=spec,
                shared_configuration=physical.cohort.shared_configuration(False),arms=physical.CONFIGS,
                pending_window_policy=physical.PENDING_WINDOW_POLICY,post_service_policy=physical.POST_SERVICE_POLICY,
                analytic_charge_policy=physical.ANALYTIC_POLICY,completion_policy=physical.COMPLETION_POLICY,
                method_policy=physical.METHOD_POLICY,limits=physical.LIMITS,cache_policy=base.CACHE_POLICY)
        manifests[d['id']]=m
        manifest_bindings[d['id']]=_write(root/(d['id']+'.json'),m)
    validate_manifest_grid(declaration,manifests,selection,recovery_admission=recovery_admission)
    if source!=physical.source_identity(repo) or compiler!=compiler_identity():
        raise ValueError('Source/compiler changed during generation')
    _check_budget(budget)
    receipt=dict(status='FROZEN',declaration=declaration,bindings=manifest_bindings,selection_binding=selected,
                 measured_generation=budget.measured(),source=source,compiler=compiler)
    _write(root/'generation.json',receipt)
    return receipt


def _synthetic_sources():
    """Fixed 17-node, two-edge graph; 128 aliased but distinct physical Sites."""
    import pandas as pd
    rows=[dict(site_id=f's{i:04}',access_node=i,lat=.1,lon=i*2+.1,
               transport_capabilities=[],meal_count=0) for i in range(16)]
    rows += [dict(site_id=f'z{i:04}',access_node=16,lat=.1,lon=.2+i*.001,
                  transport_capabilities=['charge'],meal_count=1) for i in range(128)]
    graph={}
    for name,frame in [('nodes.parquet',pd.DataFrame(dict(node_id=range(17)))),
        ('edges.parquet',pd.DataFrame(dict(source=[0,16],target=[16,1],travel_time_s=[1000.,1000.],length_m=[50.,50.])) )]:
        buf=io.BytesIO();frame.to_parquet(buf,index=False);graph[name]=buf.getvalue()
    graph['metadata.json']=canonical(dict(node_count=17,edge_count=2))
    ids=[r['site_id'] for r in rows]
    hierarchy=canonical(dict(site_ids=ids,regions=[dict(parent=-1,children=[],members=list(range(len(ids))))]))
    endpoint=lambda i,coord:dict(site_id=f'exposed{i}',access_node=900+i,lat=coord,lon=coord)
    registry=dict(schema='hiroute.m6h.exposure_registry.v1',coverage=dict(status='complete',
        scope='recovered_project_development_artifacts',known_missing_artifacts=[],reviewer='sealed-synthetic-fixture',
        included_categories=['all_geographic_screens','all_route_screen_pairs','all_dev_queries','all_diagnostics','all_candidate_selection']),
        sources=[dict(source_id='sealed-synthetic',sha256='0'*64)],
        records=[dict(source_id='sealed-synthetic',reason='DEV',origin=endpoint(0,-40),destination=endpoint(1,-30))],inspected_endpoints=[])
    return graph,rows,hierarchy,registry


def make_synthetic_fixture(output, repo=None, *, budget=None):
    """No external data arguments: fixture construction is the only runnable path."""
    from .resources import Budget
    from .physical import source_identity
    repo=Path(__file__).resolve().parents[2] if repo is None else Path(repo).resolve()
    if repo!=Path(__file__).resolve().parents[2]:raise ValueError('Fixture requires its own frozen repository')
    budget=budget or Budget()
    graph,rows,hierarchy,registry=_synthetic_sources()
    return _produce(output,graph_files=graph,site_rows=rows,hierarchy_bytes=hierarchy,exposure_registry=registry,
        repo=repo,compiler=compiler_identity(),source=source_identity(repo),budget=budget)


_VERIFIED={}


def verify_synthetic_fixture(manifest_path, manifest_sha256):
    """Regenerate known fixture and authenticate all bytes before fixture admission.

    The cache contains regenerated expectations only; every call rereads actual
    six files and all thirty manifests, so mutation cannot exploit a prior pass.
    """
    from .physical import source_identity
    path=Path(manifest_path).absolute();root=path.parent
    def owned_regular(item):
        info=item.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():
            raise ValueError('Synthetic fixture requires owned regular files')
        if item.resolve()!=item.absolute():raise ValueError('Synthetic fixture rejects symlink paths')
    owned_regular(path)
    for name in INPUT_NAMES:owned_regular(root/'inputs'/name)
    for name in ('selection.json','exposure.json'):owned_regular(root/name)
    for domain in plan(6)['domains']:owned_regular(root/(domain['id']+'.json'))
    raw=path.read_bytes()
    if _hash(raw)!=manifest_sha256:raise ValueError('Synthetic manifest hash differs')
    manifest=json.loads(raw);repo=Path(__file__).resolve().parents[2]
    source=source_identity(repo);compiler=compiler_identity();key=digest(dict(source=source,compiler=compiler))
    if key not in _VERIFIED:
        with tempfile.TemporaryDirectory(prefix='m6h-sealed-fixture-') as tmp:
            result=make_synthetic_fixture(Path(tmp)/'fixture',repo)
            expected_root=Path(tmp)/'fixture'
            _VERIFIED[key]=dict(files={n:(expected_root/'inputs'/n).read_bytes() for n in INPUT_NAMES},
                selection=(expected_root/'selection.json').read_bytes(),exposure=(expected_root/'exposure.json').read_bytes(),
                manifests={d['id']:json.loads(Path(result['bindings'][d['id']]['path']).read_bytes()) for d in plan(6)['domains']})
    expected=_VERIFIED[key]
    if path.name not in {d['id']+'.json' for d in plan(6)['domains']}:raise ValueError('Not a fixed synthetic domain')
    if any((root/'inputs'/name).read_bytes()!=data for name,data in expected['files'].items()):
        raise ValueError('Input bytes differ from internally generated synthetic fixture')
    if (root/'selection.json').read_bytes()!=expected['selection'] or (root/'exposure.json').read_bytes()!=expected['exposure']:
        raise ValueError('Synthetic selection/exposure differs')
    for name,value in expected['manifests'].items():
        rebased=dict(value,input_directory=str(root/'inputs'))
        if (root/(name+'.json')).read_bytes()!=canonical(rebased):raise ValueError('Synthetic domain grid differs')
    if manifest['source']!=source or manifest['compiler']!=compiler:raise ValueError('Synthetic executable closure differs')


def _normalize_site_catalog(table):
    """Preserve original build_sites nullable Int64 anchors; never coerce floats."""
    import pandas as pd
    from numbers import Integral
    rows=[]
    for raw in table.to_dict('records'):
        node=raw['access_node']
        if pd.isna(node):node=None
        elif isinstance(node,bool) or not isinstance(node,Integral):raise ValueError('Raw Site anchor must be integer or null')
        else:node=int(node)
        row=dict(raw,access_node=node,transport_capabilities=list(raw['transport_capabilities']))
        if pd.isna(row['meal_count']):row['meal_count']=None
        rows.append(row)
    return rows


def _bound_stage_manifest(identity):
    path=Path(identity['path'])/'artifact_manifest.json'
    raw=path.read_bytes()
    if _hash(raw)!=identity['manifest_sha256']:raise ValueError('Stage manifest changed while consuming')
    return json.loads(raw)


def _bound_stage_bytes(identity,manifest,name):
    """Authenticate the exact immutable bytes handed to parsers/materialization."""
    record=manifest['files'][name]
    raw=(Path(identity['path'])/name).read_bytes()
    if len(raw)!=record['size_bytes'] or _hash(raw)!=record['sha256']:
        raise ValueError('Consumed stage bytes differ: '+name)
    return raw


def produce_preprocessing_artifacts(output, *, artifacts, exposure_binding, protocol_sha256,
                                   repo, compiler, source, budget, preprocessing_identity, recovery_admission=None):
    """Held, strict supervisor-approved preprocessing handoff, without rerouting selection."""
    active=require_root_freeze()  # before any supplied artifact/exposure access
    if recovery_admission is None or recovery_admission!=active['recovery_admission']:
        raise ValueError('Generation requires exact reviewed recovery admission')
    from experiments.shandong_preprocessing_v1.phases import verify_stage
    from .physical_inputs import sha
    import pandas as pd
    from numbers import Integral
    sha(protocol_sha256)
    if set(artifacts)!={'source','graph','inventory','sites','hierarchy'}:
        raise ValueError('Complete five-stage preprocessing closure required')
    dirs={};stage_manifests={};order=('source','graph','inventory','sites','hierarchy')
    for phase in order:
        identity=artifacts[phase]
        if identity.get('synthetic') is not False:raise ValueError('Actual producer requires real stage provenance')
        dirs[phase]=verify_stage(identity,phase,checkpoint=lambda:_check_budget(budget))
        stage_manifests[phase]=_bound_stage_manifest(identity)
        if set(preprocessing_identity)!={'toolchain_identity','config_sha256','implementation_sha256','core_source_contract'}:
            raise ValueError('Complete preprocessing runtime/source freeze required')
        if any(canonical(stage_manifests[phase].get(k))!=canonical(v) for k,v in preprocessing_identity.items()):
            raise ValueError('Stage belongs to another preprocessing freeze')
        expected={p:artifacts[p] for p in order[:order.index(phase)]}
        if canonical(stage_manifests[phase].get('prior'))!=canonical(expected):
            raise ValueError('Preprocessing stages do not share one authenticated chain')
    if type(exposure_binding) is not dict or set(exposure_binding)!={'path','sha256'}:
        raise ValueError('Pre-source exposure freeze binding required')
    exposure_raw=Path(exposure_binding['path']).read_bytes()
    if _hash(exposure_raw)!=sha(exposure_binding['sha256']):raise ValueError('Exposure freeze changed')
    exposures=json.loads(exposure_raw)
    # Byte SHA is distinct from canonical semantic admission SHA.
    rules.validate_recovered_exposures(exposures,recovery_admission)
    take=lambda phase,name:_bound_stage_bytes(artifacts[phase],stage_manifests[phase],name)
    site_raw=take('sites','stop_sites.parquet')
    table=pd.read_parquet(io.BytesIO(site_raw),columns=['site_id','access_node','lat','lon','transport_capabilities','meal_count'])
    rows=_normalize_site_catalog(table)
    result=_produce(output,graph_files={n:take('graph',n) for n in ('nodes.parquet','edges.parquet','metadata.json')},
        site_rows=rows,hierarchy_bytes=take('hierarchy','hierarchy.json'),exposure_registry=exposures,
        repo=repo,compiler=compiler,source=source,budget=budget,protocol_sha256=protocol_sha256,
        site_catalog_sha256=_hash(site_raw),recovery_admission=recovery_admission)
    # Reauthenticate complete handoff after materialization, even on DATA_LIMITED.
    for phase,identity in artifacts.items():verify_stage(identity,phase,checkpoint=lambda:_check_budget(budget))
    result['preprocessing_bindings']=artifacts
    result['exposure_binding']=exposure_binding
    result['protocol_sha256']=protocol_sha256
    _write(Path(output)/'generation.json',result)
    return result


def _real_worker(job_path,job_sha256):
    require_root_freeze()  # no CLI flag can release it
    from .physical import source_identity
    from .resources import Budget
    raw=Path(job_path).read_bytes()
    if _hash(raw)!=job_sha256:raise ValueError('Generation job identity differs')
    job=json.loads(raw)
    if set(job)!={'artifacts','exposure_binding','protocol_sha256','repo','compiler','source','remaining_cpu','remaining_wall','preprocessing_identity','recovery_admission'}:
        raise ValueError('Unexpected frozen generation job')
    if source_identity(job['repo'])!=job['source'] or compiler_identity()!=job['compiler']:
        raise ValueError('Generation source/runtime changed')
    # Subordinate child cap only; the original enclosing parent Budget continues
    # accounting all self and waited descendants and is never reset or replaced.
    budget=Budget(cpu_seconds=min(7200,job['remaining_cpu']),wall_seconds=min(10800,job['remaining_wall']))
    output=Path(os.environ['HIROUTE_OUTPUT_DIR'])/'frozen'
    result=produce_preprocessing_artifacts(output,**{k:job[k] for k in ('artifacts','exposure_binding','protocol_sha256','repo','compiler','source','preprocessing_identity','recovery_admission')},budget=budget)
    generation=output/'generation.json'
    _write(Path(os.environ['HIROUTE_WORKER_RECEIPT']),dict(status='COMPLETED',result=dict(
        status=result['status'],generation=dict(path=str(generation),sha256=_hash(generation.read_bytes())))))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-job',required=True);parser.add_argument('--job-sha256',required=True)
    args=parser.parse_args();_real_worker(args.real_job,args.job_sha256)
