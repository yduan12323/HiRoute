"""Generic physically bound M6-H workers; source/runtime freeze remains held.

Adapted from reviewed DEV worker validators without dropping their mathematical
identity and replay checks. Domain identities now come from explicit bindings.
"""
import argparse
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.scalability_development_v1 import run as development
from experiments.projection_completion_gate_v1 import run as completion
from experiments.projection_support_gate_v1 import run as projection
from experiments.envelope_sweep_gate_v1 import run as envelope
from experiments.dev_cohort_v1 import run as cohort
from experiments.pending_window_completion_v1 import run as predecessor
from experiments.dev_cohort_v1.domain import method_admission
from .physical_domain import (SCHEMA,METHODS,INNER_ARM,METHOD_POLICY,ARMS,EXACT_PHASE_SECONDS,
    PENDING_WINDOW_POLICY,POST_SERVICE_POLICY,ANALYTIC_POLICY,REVIEW_STATUS,CURRENT_PAIR_STATUS,SOURCE_BASE_COMMIT,COMPLETION_POLICY,
    CONFIGS,ScheduledMethodDomain,historical_operators,outer_admission)

from .physical_inputs import spec_for, validate_manifest_contract, require_root_freeze, InvalidGraphInput
FIXED_CPU=0
PRODUCTION_SOURCE_ENTRIES=97
PRODUCTION_SRC_SHA256='fe1232d4061ab43f92d320ee3937222e88c3e1eead054a53cdd49a6c2ac39fbc'
LIMITS=dict(completion.LIMITS,search_seconds=1200,search_worker_wall_seconds=1500,search_worker_cpu_seconds=1500,
    parent_cpu_soft_seconds=180,parent_cpu_hard_policy='preserve_inherited_at_least_1501')
OBSERVER=dict(envelope.OBSERVER)
RESERVE=dict(completion.RESERVE,exact_search_seconds_per_arm=1200,total_exact_search_seconds=2400,
    maximum_worker_wall_seconds=3960,maximum_worker_cpu_soft_seconds=3840,parent_cpu_soft_seconds=180)
MEMORY_POLICY=dict(schema='hiroute.scheduled_method_pair_memory_planning.v1',
    planning_worker_bytes=5120*1024**2,available_memory_reserve_bytes=2048*1024**2,
    required_available_memory_bytes=7168*1024**2,read_only_before_every_heavy_worker=True,
    observed_process_peak_approx_MiB=4032,estimate_is_certified_process_tree_peak=False,
    reservation=False,aggregate_hard_limit=False,source_plan='docs/DEV_COHORT_PAIRED_PLAN.md#stages-entry-reuse-and-resource-policy')
EXECUTION_POLICY=dict(schema='hiroute.scheduled_method_pair_execution.v1',
    cpu=FIXED_CPU,max_heavy_workers=1,stages_serial=True,numeric_threads=1,
    dedicated_single_threaded_supervisor=True,automatic_retry=False,
    aggregate_memory_hard_limit=False,cgroup_enforced=False,clean_cache_claim=False,isolation_claim=False)


parquet_engine_identity=predecessor.parquet_engine_identity


def source_identity(repo):
    """Complete inherited solver closure, unchanged production, M6 wrapper sources."""
    # M6 authenticates the approved current map-policy source independently.
    # Historical DEV 95/96-entry guards remain untouched and are not called.
    identity=base.source_identity(repo);closure=dict(identity['closure']);repo=Path(repo)
    production={n:h for n,h in closure.items() if n.startswith('src/') and not n.startswith('src/hiroute.egg-info/')}
    if len(production)!=PRODUCTION_SOURCE_ENTRIES or base.digest(production)!=PRODUCTION_SRC_SHA256:
        raise ValueError('M6-H production source changed')
    # Bind all experiment sources: imported helpers and selection implementation
    # are executable identity even when they do not run inside a method worker.
    for path in sorted((repo/'experiments').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            closure[str(path.relative_to(repo))]=base.file_hash(path)
    root=repo.resolve()
    for name,module in tuple(sys.modules.items()):
        if name not in ('experiments','validation','scripts') and not name.startswith(('experiments.','validation.','scripts.')):continue
        location=getattr(module,'__file__',None)
        if location is None:continue
        try:relative=str(Path(location).resolve().relative_to(root))
        except ValueError as exc:raise ValueError('Active helper resolves outside frozen repo: '+name) from exc
        if relative not in closure or base.file_hash(location)!=closure[relative]:
            raise ValueError('Active executable helper differs from closure: '+name)
    return dict(identity,closure=closure,closure_sha256=base.digest(closure),
        production_src_sha256=base.digest(production),production_source_entries=len(production),
        parquet_engine=parquet_engine_identity(),
        python_executable=dict(path=str(Path(sys.executable).resolve()),sha256=base.file_hash(Path(sys.executable).resolve())))


def require_exact_phase(search):
    phase=search.get('phase_budget',{});entered=search.get('phase_entered_monotonic')
    if (type(phase) is not dict or type(entered) not in (int,float) or not math.isfinite(entered) or entered<=0 or search.get('status') not in ('SUCCESS','TIMEOUT') or type(phase.get('seconds')) is not int or phase['seconds']!=EXACT_PHASE_SECONDS or
        search['status']=='TIMEOUT' and search.get('reason')!='phase_timeout'):
        raise ValueError('Search did not complete or exhaust its declared1200-second exact phase')


def _manifest(path,expected_sha256):
    require_root_freeze()
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('M6-H manifest digest differs')
    manifest=json.loads(raw)
    if raw!=base.canonical(manifest):raise ValueError('Frozen manifest must use unique canonical JSON encoding')
    validate_manifest_contract(manifest)
    compiler=manifest['compiler']
    if (set(compiler)!={'path','sha256','version','flags'} or base.file_hash(compiler['path'])!=compiler['sha256'] or
        subprocess.check_output([compiler['path'],'--version'],text=True)!=compiler['version'] or compiler['flags']!=['-O3','-std=c++17']):
        raise ValueError('Pinned compiler differs')
    if manifest['source']!=source_identity(manifest['repo']):raise ValueError('M6-H executable closure differs')
    base.verify_inputs(manifest['input_directory'],manifest['inputs'])
    return manifest


def read_bound_input(directory,name,bindings):
    require_root_freeze()
    if name not in base.INPUT_NAMES:raise ValueError('Unbound input name')
    raw=(Path(directory)/name).read_bytes();expected=bindings[name]
    if len(raw)!=expected['size'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']:
        raise ValueError('Input changed while loading: '+name)
    return raw


def extract_case(directory,case_id,bindings,manifest):
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.real_legs import RealSite
    require_root_freeze()
    spec_for(manifest,case_id)
    base.verify_inputs(directory,{n:bindings[n] for n in base.INPUT_NAMES})
    spec=spec_for(manifest,case_id);root=Path(directory)
    rows=json.loads(read_bound_input(root,'queries.json',bindings))['queries']
    matches=[row for row in rows if row['query_id']==case_id]
    if len(matches)!=1:raise ValueError('Ambiguous cohort query')
    row=matches[0];binding=row['bindings'][str(spec['candidate_count'])]
    validate_direct_baseline(row['baseline_direct_binary64'],binding['query'])
    pools=json.loads(read_bound_input(root,'pools.json',bindings))['pools'];matches=[p for p in pools if p['od_id']==row['od_id']]
    if len(matches)!=1:raise ValueError('Ambiguous cohort pool')
    prefix=matches[0]['sites'][:spec['candidate_count']]
    if base.canonical(binding)!=base.canonical(spec['original_binding']) or base.canonical(prefix)!=base.canonical(spec['original_pool_prefix']):
        raise ValueError('Original candidate/query binding changed')
    sites={s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in prefix};query=binding['query']
    if (len(sites)!=spec['candidate_count'] or list(sites)!=binding['candidate_site_ids'] or
        base.digest(sorted(sites))!=binding['candidate_sha256'] or site_catalog_digest(sites)!=binding['site_catalog_sha256'] or
        base.digest(query)!=binding['query_sha256'] or query['case_id']!=case_id or query['hierarchy_sha256']!=bindings['hierarchy.json']['sha256']):
        raise ValueError('Cohort physical identities differ')
    tree=base.original_tree((root/'hierarchy.json').read_bytes(),query['hierarchy_sha256'],list(sites))
    return query,sites,tree


def validate_direct_baseline(value,query):
    from timecut5.real_legs import decode_binary64
    if type(value) is not dict or set(value)!={'time_s','actual_length_m','selected_edges'}:
        raise ValueError('Selected-fastest direct baseline identity required')
    direct=decode_binary64(value['time_s']);decode_binary64(value['actual_length_m'])
    if direct<=0 or query['schedule']!={'a':str(F(2,5)*direct),'b':str(F(7,10)*direct),'D':'2700'}:
        raise ValueError('Scheduled window differs from exact selected-fastest direct time')
    edges=value['selected_edges']
    if type(edges) is not list or not edges or any(type(e) is not int or e<0 for e in edges):
        raise ValueError('Explicit direct selected edge witness required')
    return value


def verify_direct_baseline(manifest,case_id,query,provider):
    require_root_freeze()
    from timecut5.real_legs import encode_binary64
    root=Path(manifest['input_directory']);raw=(root/'queries.json').read_bytes()
    binding=manifest['inputs']['queries.json']
    if len(raw)!=binding['size'] or hashlib.sha256(raw).hexdigest()!=binding['sha256']:
        raise ValueError('Direct baseline input changed')
    rows=[r for r in json.loads(raw)['queries'] if r['query_id']==case_id]
    if len(rows)!=1:raise ValueError('Ambiguous direct baseline')
    expected=validate_direct_baseline(rows[0]['baseline_direct_binary64'],query)
    leg=provider.leg(query['origin'],query['destination'])
    if not leg.reachable:raise ValueError('Declared direct baseline is unreachable')
    actual=dict(time_s=encode_binary64(float.fromhex(leg.time_hex)),
        actual_length_m=encode_binary64(float.fromhex(leg.length_hex)),
        selected_edges=list(provider.edge_witnesses[query['origin'],query['destination']]))
    if base.canonical(actual)!=base.canonical(expected):
        raise ValueError('Fresh selected-fastest direct time/length/edges differ')


def load_bound_graph(directory,bindings,query,sites):
    # Validate authenticated raw types before any NumPy coercion. Legacy loader
    # casts fractional/bool endpoints to int64; that is not an admissible graph.
    import io
    import numpy as np
    import pandas as pd
    from types import SimpleNamespace
    base.verify_inputs(directory,bindings)
    def raw(name):
        value=(Path(directory)/name).read_bytes()
        if len(value)!=bindings[name]['size'] or hashlib.sha256(value).hexdigest()!=bindings[name]['sha256']:
            raise ValueError('Loaded graph bytes differ: '+name)
        return value
    try:metadata=json.loads(raw('metadata.json'))
    except (json.JSONDecodeError,UnicodeDecodeError) as exc:
        raise InvalidGraphInput('Invalid graph metadata JSON') from exc
    if type(metadata) is not dict:raise InvalidGraphInput('Graph metadata object required')
    n,m=metadata.get('node_count'),metadata.get('edge_count')
    if type(n) is not int or type(m) is not int or min(n,m)<=0 or max(n,m)>np.iinfo(np.int64).max:
        raise InvalidGraphInput('Strict positive graph metadata counts required')
    node_bytes=raw('nodes.parquet');edge_bytes=raw('edges.parquet')
    try:
        nodes=pd.read_parquet(io.BytesIO(node_bytes),columns=['node_id'])
        edges=pd.read_parquet(io.BytesIO(edge_bytes),columns=['source','target','travel_time_s','length_m'])
    except (ValueError,KeyError) as exc:
        raise InvalidGraphInput('Invalid graph Parquet schema') from exc
    def integers(series):
        return pd.api.types.is_integer_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype) and not series.isna().any()
    ids=nodes['node_id']
    if len(nodes)!=n or not integers(ids) or not np.array_equal(np.sort(ids.to_numpy()),np.arange(n)):
        raise InvalidGraphInput('Graph node IDs must be unique contiguous integers')
    if len(edges)!=m:raise InvalidGraphInput('Graph edge count differs')
    for name in ('source','target'):
        col=edges[name]
        if not integers(col) or (col<0).any() or (col>=n).any():raise InvalidGraphInput('Strict in-range integer graph endpoints required')
    for name in ('travel_time_s','length_m'):
        col=edges[name]
        if (not pd.api.types.is_numeric_dtype(col.dtype) or pd.api.types.is_bool_dtype(col.dtype) or
            col.isna().any() or not np.isfinite(col.to_numpy()).all() or (col<0).any()):
            raise InvalidGraphInput('Finite nonnegative graph weights required')
    # Retain reviewed native compatibility; zero-time edges need explicit review.
    if (edges['travel_time_s']<=0).any():raise InvalidGraphInput('Existing native routing requires positive edge travel time')
    arrays=[np.ascontiguousarray(edges[name].to_numpy(dtype=np.int64 if i<2 else np.float64))
        for i,name in enumerate(('source','target','travel_time_s','length_m'))]
    for array in arrays:array.flags.writeable=False
    graph=SimpleNamespace(node_count=n,edge_count=m,source=arrays[0],target=arrays[1],
        weights=dict(travel_time=arrays[2],distance=arrays[3]))
    anchors=[query['origin'],query['destination']]+[site.anchor_id for site in sites.values()]
    if any(not 0<=int(anchor.removeprefix('road:'))<graph.node_count for anchor in anchors):
        raise InvalidGraphInput('Physical endpoint or Site anchor outside graph')
    return graph


def domain_factory(manifest,query,sites,cache,*,arm,case_id,admitted_hmax=None):
    require_root_freeze()
    spec=spec_for(manifest,case_id)
    if len(sites)!=spec['candidate_count'] or list(sites)!=spec['original_binding']['candidate_site_ids']:
        raise ValueError('Original post-service candidate order differs')
    bindings=manifest['inputs'];directory=manifest['input_directory']
    tree=base.original_tree((Path(directory)/'hierarchy.json').read_bytes(),bindings['hierarchy.json']['sha256'],list(sites))
    return ScheduledMethodDomain(arm=arm,case_binding=spec,required_hmax=admitted_hmax,manifest_binding=base.digest(manifest),
        graph_factory=lambda:load_bound_graph(directory,bindings,query,sites),query=query,sites=sites,tree=tree,
        source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache,compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def validate_common(common,case_id,manifest):
    require_root_freeze()
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.real_legs import RealSite
    spec=spec_for(manifest,case_id);binding=spec['original_binding']
    if common.get('case_id')!=case_id or type(common.get('candidate_count')) is not int or common['candidate_count']!=spec['candidate_count'] or common.get('case_binding_sha256')!=base.digest(spec):
        raise ValueError('Cohort common case binding differs')
    seed=common['seed']
    if type(seed.get('key_bytes')) is not str:raise ValueError('Serialized exact seed key required')
    require_canonical_full_key(json.loads(seed['key_bytes']))
    if (common.get('schema')!=SCHEMA or common.get('status')!='common_feasible_seed' or
        type(seed['max_depth']) is not int or seed['max_depth']<0 or
        seed['max_depth']!=base.depth_bound(common['query'],tuple(F(v) if i<2 else v for i,v in enumerate(json.loads(seed['key_bytes']))))):
        raise ValueError('Fresh seed-derived Hmax differs from unchanged original rule')
    query=common['query'];original=dict(query);original['sparse_domain_sha256']=binding['query']['sparse_domain_sha256']
    if base.canonical(original)!=base.canonical(binding['query']) or common.get('historical_query_sha256')!=binding['query_sha256']:
        raise ValueError('Cohort query changed beyond runtime source rebinding')
    sites={s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in common['sites']}
    if (len(common['sites'])!=spec['candidate_count'] or len(sites)!=spec['candidate_count'] or list(sites)!=binding['candidate_site_ids'] or
        site_catalog_digest(sites)!=binding['site_catalog_sha256'] or seed['site_sha256']!=binding['site_catalog_sha256'] or
        seed['query_sha256']!=base.digest(query) or common['source']!=manifest['source'] or common['inputs']!=manifest['inputs'] or
        common['cache_policy']!=manifest['cache_policy']):raise ValueError('Common candidate/source/seed identity differs')
    tree=base.original_tree((Path(manifest['input_directory'])/'hierarchy.json').read_bytes(),manifest['inputs']['hierarchy.json']['sha256'],list(sites))
    if common['tree_sha256']!=base.digest(base.tree_value(tree)) or seed['tree_sha256']!=common['tree_sha256']:
        raise ValueError('Original cohort hierarchy topology differs')


def validate_no_seed(note,case_id,manifest):
    """Only a normally exhausted original proposal stream has this typed outcome."""
    require_root_freeze()
    spec=spec_for(manifest,case_id);binding=spec['original_binding']
    names={'schema','status','classification','case_id','candidate_count','case_binding_sha256',
        'original_query_sha256','runtime_query_sha256','query','tree_sha256','site_catalog_sha256',
        'prospective_full_selection_sha256','manifest_sha256','source','inputs','proposal_count',
        'replay_rejections','stream_exhausted','feasibility','global_infeasibility_claim','charged_wall_ns','seed_policy'}
    if (type(note) is not dict or set(note)!=names or note['schema']!=SCHEMA or
        note['status']!='seed_exhausted_unknown' or note['classification']!='normal_original_proposal_stream_exhaustion' or
        note['case_id']!=case_id or type(note['candidate_count']) is not int or note['candidate_count']!=spec['candidate_count'] or
        note['case_binding_sha256']!=base.digest(spec) or note['original_query_sha256']!=binding['query_sha256'] or
        note['runtime_query_sha256']!=base.digest(note['query']) or note['site_catalog_sha256']!=binding['site_catalog_sha256'] or
        note['prospective_full_selection_sha256']!=manifest['selection_sha256'] or note['manifest_sha256']!=base.digest(manifest) or
        note['source']!=manifest['source'] or note['inputs']!=manifest['inputs'] or
        note['seed_policy']!=development.POLICY['seed_policy'] or note['stream_exhausted'] is not True or
        note['feasibility']!='unknown' or note['global_infeasibility_claim'] is not False or
        any(type(note[n]) is not int or note[n]<0 for n in ('proposal_count','replay_rejections','charged_wall_ns')) or
        note['proposal_count']!=note['replay_rejections']):
        raise ValueError('Unrecognized or unauthenticated expected no-seed outcome')
    original=dict(note['query']);original['sparse_domain_sha256']=binding['query']['sparse_domain_sha256']
    if base.canonical(original)!=base.canonical(binding['query']):raise ValueError('No-seed query changed beyond runtime sparse rebinding')
    tree=base.original_tree((Path(manifest['input_directory'])/'hierarchy.json').read_bytes(),
        manifest['inputs']['hierarchy.json']['sha256'],binding['candidate_site_ids'])
    if note['tree_sha256']!=base.digest(base.tree_value(tree)):raise ValueError('No-seed original hierarchy differs')
    return note


PREPARE_RESULT_SCHEMA='hiroute.m6h.prepare_result.v1'


def _prepare_summary(value):
    if value.get('schema')!=SCHEMA:raise ValueError('Preparation artifact schema differs')
    if value.get('status')=='common_feasible_seed':
        return dict(status=value['status'],candidate_count=value['candidate_count'],max_depth=value['seed']['max_depth'])
    if value.get('status')=='seed_exhausted_unknown':
        return dict(status=value['status'],candidate_count=value['candidate_count'],proposal_count=value['proposal_count'],
            replay_rejections=value['replay_rejections'])
    raise ValueError('Unknown preparation outcome')


def result_envelope(artifacts,operation,case_id,strategy=None):
    if operation!='prepare':return base.result_envelope(artifacts,operation,case_id,strategy)
    raw=(Path(artifacts)/'prepared/common.json').read_bytes()
    if not 0<len(raw)<=base.MAX_RESULT_BYTES:raise ValueError('Preparation result exceeds bounded contract')
    result=json.loads(raw)
    return dict(schema=PREPARE_RESULT_SCHEMA,operation='prepare',case_id=case_id,strategy=strategy,
        artifact=dict(path='prepared/common.json',size=len(raw),sha256=hashlib.sha256(raw).hexdigest()),summary=_prepare_summary(result))


def load_worker_result(directory,receipt,operation,case_id,strategy=None):
    if operation!='prepare':return base.load_worker_result(directory,receipt,operation,case_id,strategy)
    envelope=receipt['worker_receipt']['result']
    if (type(envelope) is not dict or set(envelope)!={'schema','operation','case_id','strategy','artifact','summary'} or
        envelope['schema']!=PREPARE_RESULT_SCHEMA or envelope['operation']!='prepare' or
        envelope['case_id']!=case_id or envelope['strategy'] is not None or strategy is not None or len(base.canonical(envelope))>4096):
        raise ValueError('Preparation result identity differs')
    b=envelope['artifact']
    if (type(b) is not dict or set(b)!={'path','size','sha256'} or b['path']!='prepared/common.json' or
        type(b['size']) is not int or not 0<b['size']<=base.MAX_RESULT_BYTES):raise ValueError('Preparation artifact reference differs')
    root=Path(directory)/'artifacts';path=root/'prepared/common.json'
    if root.is_symlink() or path.parent.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size!=b['size']:
        raise ValueError('Missing or symlink preparation artifact')
    raw=path.read_bytes()
    if len(raw)!=b['size'] or hashlib.sha256(raw).hexdigest()!=b['sha256']:raise ValueError('Preparation artifact digest differs')
    result=json.loads(raw)
    if _prepare_summary(result)!=envelope['summary']:raise ValueError('Preparation summary differs')
    return result


@historical_operators()
def prepare_case(manifest,case_id,output):
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.sparse_seed import SparseSeedCatalog,sparse_domain_digest,replay_sparse_seed,SeedInfeasible
    from timecut5.deployable import iter_constructive_seed_candidates
    from timecut5.provenance import primitive
    require_root_freeze()
    started=time.monotonic_ns();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    directory,bindings=manifest['input_directory'],manifest['inputs'];spec=spec_for(manifest,case_id)
    query,sites,_=extract_case(directory,case_id,bindings,manifest);historical=base.digest(query)
    make=lambda q:domain_factory(manifest,q,sites,output/'native',arm=ARMS[0],case_id=case_id)
    domain=make(query)
    with domain.context('generation') as context:
        verify_direct_baseline(manifest,case_id,query,context.provider)
        query=dict(query,sparse_domain_sha256=sparse_domain_digest(context.provider.source_sha256,site_catalog_digest(sites),
            base.digest(sorted(sites)),query['hierarchy_sha256'],query['origin'],query['destination']))
    domain=make(query)
    def catalog(context):
        return SparseSeedCatalog(context.provider,sites,origin_anchor=query['origin'],destination_anchor=query['destination'],
            nodes_path=Path(directory)/'nodes.parquet',edges_path=Path(directory)/'edges.parquet',site_catalog_sha256=site_catalog_digest(sites),
            hierarchy_sha256=query['hierarchy_sha256'],candidate_sha256=base.digest(sorted(sites)))
    with domain.context('generation') as context:
        sparse=catalog(context);witness=None;proposal_count=0;replay_rejections=0
        for ordinal,(sequence,charges) in enumerate(iter_constructive_seed_candidates(query,sparse)):
            proposal_count+=1
            try:replay_sparse_seed(query,sparse,sequence,charges)
            except SeedInfeasible:
                replay_rejections+=1;continue
            witness=base.proposal_witness(domain.problem(context),sequence,charges);break
    if witness is None:
        note=dict(schema=SCHEMA,status='seed_exhausted_unknown',classification='normal_original_proposal_stream_exhaustion',
            case_id=case_id,candidate_count=spec['candidate_count'],case_binding_sha256=base.digest(spec),
            original_query_sha256=historical,runtime_query_sha256=base.digest(query),query=query,
            tree_sha256=domain.tree_sha256,site_catalog_sha256=domain.site_sha256,
            prospective_full_selection_sha256=manifest['selection_sha256'],manifest_sha256=base.digest(manifest),
            source=manifest['source'],inputs=bindings,proposal_count=proposal_count,replay_rejections=replay_rejections,
            stream_exhausted=True,feasibility='unknown',global_infeasibility_claim=False,
            charged_wall_ns=time.monotonic_ns()-started,seed_policy=development.POLICY['seed_policy'])
        validate_no_seed(note,case_id,manifest)
        (output/'common.json').write_bytes(base.canonical(note));return note
    seed=domain.freeze_seed(witness)
    with domain.context('verification') as context:
        replayed=replay_sparse_seed(query,catalog(context),witness.pi,
            tuple(e.departure_energy-e.arrival_energy for e in witness.events if e.effect in ('C','CS')))
        if base.canonical(primitive(replayed['lex_key']))!=seed.key_bytes:raise ValueError('Independent common sparse replay differs')
    values=asdict(seed)
    for name in ('witness_bytes','key_bytes'):values[name]=values[name].decode()
    common=dict(schema=SCHEMA,status='common_feasible_seed',case_id=case_id,candidate_count=spec['candidate_count'],
        case_binding_sha256=base.digest(spec),query=query,historical_query_sha256=historical,runtime_rebinding_fields=['sparse_domain_sha256'],
        sites=[dict(site_id=s.site_id,anchor_id=s.anchor_id,effects=list(s.effects)) for s in sites.values()],tree_sha256=domain.tree_sha256,
        seed=values,proposal_ordinal=ordinal,candidate_repair=None,native=dict(router=domain.artifact.receipt,energy=domain.energy_artifact.receipt),
        charged_wall_ns=time.monotonic_ns()-started,seed_policy=development.POLICY['seed_policy'],source=manifest['source'],inputs=bindings,cache_policy=domain.cache_policy)
    (output/'common.json').write_bytes(base.canonical(common))
    validate_common(common,case_id,manifest)
    return common


def progress_binding(manifest,arm,case_id,common):
    if arm not in ARMS or case_id!=manifest['case_id']:raise ValueError('Outside fixed pending-window gate')
    inner,sources=projection.progress_binding(manifest,INNER_ARM,common)
    cohort_policy=[cohort.SCHEMA,arm,manifest['shared_configuration'],spec_for(manifest,case_id),METHOD_POLICY,base.digest(manifest)]
    inner,sources=base.digest([inner,*cohort_policy]),dict(sources,cohort_method=base.digest(cohort_policy))
    policy=[SCHEMA,arm,CONFIGS[arm],PENDING_WINDOW_POLICY,POST_SERVICE_POLICY,ANALYTIC_POLICY,COMPLETION_POLICY,base.digest(manifest)]
    return base.digest([inner,*policy]),dict(sources,pending_window_policy=base.digest(policy))


def validate_combined_statistics(support,analytic,arm,*,completed):
    if arm not in ARMS:raise ValueError('Unknown scheduled method')
    predecessor.validate_combined_statistics(support,analytic,predecessor.ARMS[0],completed=completed)


def validate_post_service_statistics(value,arm,*,completed):
    if arm not in ARMS:raise ValueError('Unknown scheduled method')
    predecessor.validate_post_service_statistics(value,predecessor.ARMS[0],completed=completed)


def validate_pending_window_statistics(value,post_service,arm,*,completed):
    if arm not in ARMS:raise ValueError('Unknown scheduled method')
    predecessor.validate_pending_window_statistics(value,post_service,predecessor.ARMS[0],completed=completed)


def read_progress(path,manifest,arm,case_id,common,*,search_status,completed_result=None):
    if arm not in ARMS or case_id!=manifest['case_id']:raise ValueError('Outside fixed pending-window gate')
    method=arm
    path=Path(path);value,raw_sha,size=envelope.read_bounded_json(path)
    inner,inner_sha,_=envelope.read_bounded_json(path.parent.parent/'remaining_charge_admission.json')
    outer,outer_sha,_=envelope.read_bounded_json(path.parent.parent/'method_admission.json')
    reducer_admission,reducer_sha,_=envelope.read_bounded_json(path.parent.parent/'pending_window_admission.json')
    spec=spec_for(manifest,case_id);config=manifest['shared_configuration'];digest=base.digest(manifest)
    if base.canonical(reducer_admission)!=base.canonical(outer_admission(digest,arm,outer_sha)):
        raise ValueError('Outer post-service admission differs')
    if (value.get('pending_window_schema')!=SCHEMA or value.get('pending_window_arm')!=arm or
        base.canonical(value.get('pending_window_configuration'))!=base.canonical(CONFIGS[arm]) or
        base.canonical(value.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
        base.canonical(value.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
        base.canonical(value.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or
        base.canonical(value.get('pending_window_policy'))!=base.canonical(PENDING_WINDOW_POLICY) or value.get('pending_window_admission_sha256')!=reducer_sha):
        raise ValueError('Outer post-service progress binding differs')
    if base.canonical(outer)!=base.canonical(method_admission(digest,method,config,spec,inner_sha)):
        raise ValueError('Outer cohort method admission differs')
    domain,sources=progress_binding(manifest,arm,case_id,common)
    if (value.get('cohort_schema')!=cohort.SCHEMA or value.get('method')!=method or value.get('case_binding_sha256')!=base.digest(spec) or
        base.canonical(value.get('shared_configuration'))!=base.canonical(config) or base.canonical(value.get('method_policy'))!=base.canonical(METHOD_POLICY) or
        value.get('method_admission_sha256')!=outer_sha or value.get('domain_sha256')!=domain or value.get('source_sha256')!=sources):
        raise ValueError('Outer method progress binding differs')
    if (value.get('profile_schema')!=projection.SCHEMA or value.get('arm')!=INNER_ARM or
        base.canonical(value.get('configuration'))!=base.canonical(projection.CONFIGS[INNER_ARM]) or
        value.get('manifest_binding')!=digest or value.get('candidate_count')!=spec['candidate_count'] or
        value.get('query_sha256')!=base.digest(common['query']) or value.get('Hmax')!=common['seed']['max_depth'] or
        value.get('status') not in ('running','returned') or value.get('io_error') is not None or value.get('heartbeat_error') is not None or
        value.get('remaining_charge_admission_sha256')!=inner_sha or inner.get('portable_bound_policy')!=projection.BOUND_POLICY or
        inner.get('original_Hmax')!=common['seed']['max_depth'] or inner.get('context_receipt_portable') is not False):
        raise ValueError('Inner operator snapshot binding or health differs')
    projection.validate_activation_receipt(inner,value,INNER_ARM,common)
    sweep_arm=envelope.ARMS[int(config['envelope_sweep'])]
    def counters(row,completed):
        validate_combined_statistics(row.get('projection_support_statistics'),row.get('analytic_charge_statistics'),arm,completed=completed)
        validate_post_service_statistics(row.get('post_service_statistics'),arm,completed=completed)
        validate_pending_window_statistics(row.get('pending_window_statistics'),row.get('post_service_statistics'),arm,completed=completed)
        envelope.validate_envelope_statistics(row.get('envelope_sweep_statistics'),sweep_arm,completed=completed)
        cohort.validate_singleton_statistics(row.get('singleton_bound_statistics'),method,completed=completed)
    counters(value,False)
    if search_status not in ('SUCCESS','TIMEOUT'):raise ValueError('Method receipt outcome not admitted')
    healthy=False
    if search_status=='SUCCESS':
        result=completed_result
        if type(result) is not dict:raise ValueError('Authenticated method result required')
        final=result.get('observer',{})
        if (result.get('schema')!=SCHEMA or result.get('strategy')!=arm or result.get('method')!=method or
            result.get('pending_window_arm')!=arm or base.canonical(result.get('pending_window_configuration'))!=base.canonical(CONFIGS[arm]) or
            base.canonical(result.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
            base.canonical(result.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
            base.canonical(result.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or
            base.canonical(result.get('pending_window_policy'))!=base.canonical(PENDING_WINDOW_POLICY) or result.get('pending_window_admission_sha256')!=reducer_sha or
            result.get('inner_arm')!=INNER_ARM or result.get('case_binding_sha256')!=base.digest(spec) or
            base.canonical(result.get('shared_configuration'))!=base.canonical(config) or base.canonical(result.get('method_policy'))!=base.canonical(METHOD_POLICY) or
            result.get('method_admission_sha256')!=outer_sha or result.get('remaining_charge_admission_sha256')!=inner_sha or
            result.get('progress_sha256')!=raw_sha or result.get('remaining_charge_activation_wall_ns')!=inner['activation_wall_ns'] or
            base.canonical(result.get('time_policy'))!=base.canonical(projection.TIME_POLICIES[INNER_ARM]) or
            base.canonical(result.get('configuration'))!=base.canonical(projection.CONFIGS[INNER_ARM]) or result.get('manifest_binding')!=digest or
            final.get('status')!='returned' or 'io_error' not in final or 'heartbeat_error' not in final or
            final['io_error'] is not None or final['heartbeat_error'] is not None or value['status']!='returned'):
            raise ValueError('Authenticated method result/observer differs')
        if base.canonical(result.get('projection_support_policy'))!=base.canonical(projection.SUPPORT_POLICY) or any(result.get(n)!=value[n] for n in
            ('projection_support_statistics','envelope_sweep_statistics','singleton_bound_statistics','analytic_charge_statistics','post_service_statistics','pending_window_statistics')):
            raise ValueError('Authenticated operator statistics differ')
        counters(result,True);healthy=True
    return dict(sha256=raw_sha,bytes=size,pending_window_admission_sha256=reducer_sha,analytic_charge_statistics=value['analytic_charge_statistics'],status=value['status'],method_admission_sha256=outer_sha,
        remaining_charge_admission_sha256=inner_sha,remaining_charge_activation_diagnostic=inner.get('diagnostic'),
        projection_support_statistics=value['projection_support_statistics'],envelope_sweep_statistics=value['envelope_sweep_statistics'],
        post_service_statistics=value['post_service_statistics'],pending_window_statistics=value['pending_window_statistics'],
        post_service_counter_scope='delegated_fallback_calls_only',
        singleton_bound_statistics=value['singleton_bound_statistics'],sampled_wall_ns=value['sampled_wall_ns'],last_active_stack=value['active_stack'],
        maximum_observed_write_gap_ns=value['maximum_observed_write_gap_ns'],timeout_snapshot_is_censored=search_status=='TIMEOUT',
        terminal_observer_health_proved=healthy)


require_canonical_full_key=predecessor.require_canonical_full_key


def validate_terminal(completed,full,arm,expected_hmax):
    if arm not in ARMS:raise ValueError('Unknown pending-window arm')
    method=arm
    exact=completed.get('result');payload=exact.get('result') if type(exact) is dict else None
    statuses={'attained_optimum':('attained_optimum',),'infimum_unattained':('primary_unattained','secondary_unattained')}
    if (completed.get('method')!=method or completed.get('strategy')!=arm or completed.get('pending_window_arm')!=arm or completed.get('status') not in statuses or
        type(payload) is not dict or payload.get('status') not in statuses[completed['status']]):
        raise ValueError('Missing or mis-tagged exact method terminal payload')
    if (full.get('method')!=method or full.get('pending_window_schema')!=SCHEMA or full.get('pending_window_arm')!=arm or
        base.canonical(full.get('pending_window_configuration'))!=base.canonical(CONFIGS[arm]) or
        base.canonical(full.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
        base.canonical(full.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
        base.canonical(full.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or
        base.canonical(full.get('pending_window_policy'))!=base.canonical(PENDING_WINDOW_POLICY) or
        base.canonical(completed['accepted_key'])!=base.canonical(full['accepted_key']) or completed['status']!=full['status'] or
        full.get('search_status')!='SUCCESS'):raise ValueError('Completed method answer lacks matching fresh full replay')
    if (type(expected_hmax) is not int or type(completed.get('Hmax')) is not int or completed['Hmax']!=expected_hmax or
        type(exact.get('H_ref')) is not int or exact['H_ref']!=expected_hmax):
        raise ValueError('Completed exact Hmax differs from common seed')
    if completed['status']=='attained_optimum':
        accepted=completed['accepted_key']
        require_canonical_full_key(accepted)
        if (type(accepted) is not list or len(accepted)!=4 or
            base.canonical(payload.get('lex_key'))!=base.canonical(accepted) or
            base.canonical([payload.get('J'),payload.get('Q_total'),payload.get('H'),payload.get('site_action_tuple')])!=base.canonical(accepted)):
            raise ValueError('Attained terminal payload differs from replayed full key')
    else:
        rational_fields={'primary_unattained':('primary_infimum',),
            'secondary_unattained':('J','secondary_infimum')}[payload['status']]
        if set(payload)!={'status',*rational_fields}:raise ValueError('Unattained terminal payload schema differs')
        try:
            if any(type(payload[n]) is not str or str(F(payload[n]))!=payload[n] or F(payload[n])<0 for n in rational_fields):
                raise ValueError('Noncanonical unattained rational')
        except (ValueError,ZeroDivisionError) as exc:
            raise ValueError('Unattained terminal payload needs canonical exact nonnegative rationals') from exc
    return dict(status='attained_optimum',lex_key=completed['accepted_key']) if completed['status']=='attained_optimum' else dict(payload)




def phase_identity(manifest,sha256,arm,common_sha):
    CASE=manifest['case_id']
    return dict(case_id=CASE,candidate_count=str(manifest['candidate_count']),strategy=arm,feature_arm=arm,method=arm,arm_index=str(manifest['method_order'].index(arm)),
        common_sha256=common_sha,manifest_sha256=sha256,source_closure_sha256=manifest['source']['closure_sha256'],
        experiment_schema=SCHEMA,configuration_sha256=base.digest(CONFIGS[arm]),
        pending_window_policy_sha256=base.digest(PENDING_WINDOW_POLICY),completion_policy_sha256=base.digest(COMPLETION_POLICY))


def require_search_phase(manifest,sha256,arm,common_sha,receipt):
    require_exact_phase(receipt)
    identity=receipt['phase_budget'].get('identity',{})
    expected=phase_identity(manifest,sha256,arm,common_sha)
    if (type(identity) is not dict or set(identity)!={*expected,'nonce'} or
        any(identity.get(k)!=v for k,v in expected.items()) or type(identity.get('nonce')) is not str or not identity['nonce']):
        raise ValueError('Search exact-phase case/N/method/common/source identity differs')


def admit_method(row,manifest,sha256,output,index,common,common_sha,receipt):
    """Authenticate one method before any subsequent heavy worker starts."""
    output=Path(output);CASE=manifest['case_id'];arm=manifest['method_order'][index]
    search,verify=row['receipt'],row['verification']
    if (search.get('status') not in ('SUCCESS','TIMEOUT') or verify.get('status')!='SUCCESS' or
        search.get('cleanup_verified') is not True or verify.get('cleanup_verified') is not True):
        raise ValueError('Method receipt or owned cleanup not admitted')
    require_search_phase(manifest,sha256,arm,common_sha,search)
    full=base.load_worker_result(output/f'verify-{index:02d}',verify,'verify',CASE,arm)
    if (row['status']!=full['status'] or full.get('method')!=arm or full.get('pending_window_schema')!=SCHEMA or
        full.get('pending_window_arm')!=arm or base.canonical(full.get('pending_window_configuration'))!=base.canonical(CONFIGS[arm]) or
        base.canonical(full.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
        base.canonical(full.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
        base.canonical(full.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or
        base.canonical(full.get('pending_window_policy'))!=base.canonical(PENDING_WINDOW_POLICY) or
        full.get('case_binding_sha256')!=base.digest(spec_for(manifest,CASE))):
        raise ValueError('Fresh verifier feature/method/case differs')
    completed=None;terminal=None
    if search['status']=='SUCCESS':
        completed=base.load_worker_result(output/f'arm-{index:02d}',search,'arm',CASE,arm)
        if base.canonical(completed.get('seed_key')).decode()!=common['seed']['key_bytes']:
            raise ValueError('Method search did not retain original common seed key')
        terminal=validate_terminal(completed,full,arm,common['seed']['max_depth'])
    elif full.get('search_status')!='TIMEOUT' or full['status']!='timeout_feasible_only':
        raise ValueError('Timeout verifier claims more than feasible evidence')
    row['progress']=read_progress(output/f'arm-{index:02d}/artifacts/arm/progress/progress.json',manifest,arm,CASE,common,
        search_status=search['status'],completed_result=completed)
    row['authenticated_completion']=search['status']=='SUCCESS';row['operational_admission']=True
    # The shared preparation is physically executed once but fully charged
    # to each standalone method. Never sum inclusive nested timings.
    row['standalone_charged_wall_seconds']=sum(r['wall_seconds'] for r in (receipt,search,verify))
    row['standalone_cost_components']=dict(common_preparation_wall_seconds=receipt['wall_seconds'],
        search_worker_wall_seconds=search['wall_seconds'],fresh_full_replay_worker_wall_seconds=verify['wall_seconds'])
    return terminal


def worker(operation, manifest_path, manifest_sha256, case_id, *, strategy=None,
           common_path=None, common_sha256=None, search_directory=None, search_receipt_sha256=None):
    """Fresh supervised process entry; not an unsupervised launch convenience."""
    manifest=_manifest(manifest_path,manifest_sha256)
    spec_for(manifest,case_id)
    if operation not in ('prepare','arm','verify'):raise ValueError('Unknown operation')
    if operation=='prepare':
        if strategy is not None:raise ValueError('Preparation has no strategy')
        prepare_case(manifest,case_id,Path(os.environ['HIROUTE_OUTPUT_DIR'])/'prepared')
    else:
        if strategy not in ARMS:raise ValueError('Method required')
        raw=Path(common_path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=common_sha256:raise ValueError('Common artifact differs')
        common=json.loads(raw);validate_common(common,case_id,manifest)
        if operation=='verify':
            from experiments.mechanism_recovery_v1.supervisor import read_result
            require_search_phase(manifest,manifest_sha256,strategy,common_sha256,read_result(search_directory))
        factory=lambda m,q,s,c:domain_factory(m,q,s,c,arm=strategy,case_id=case_id,admitted_hmax=common['seed']['max_depth'])
        with historical_operators():
            base.worker(manifest,operation,case_id,common_path,common_sha256,strategy,search_directory,
                        search_receipt_sha256,domain_factory=factory)
    _manifest(manifest_path,manifest_sha256)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(base.canonical(dict(status='COMPLETED',result=result_envelope(
        os.environ['HIROUTE_OUTPUT_DIR'],operation,case_id,strategy))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',required=True,choices=('prepare','arm','verify'))
    for name in ('manifest','manifest-sha256','case','strategy','common','common-sha256','search-directory','search-receipt-sha256'):
        parser.add_argument('--'+name,required=name in ('manifest','manifest-sha256','case'))
    args=parser.parse_args()
    worker(args.worker,args.manifest,args.manifest_sha256,args.case,strategy=args.strategy,
        common_path=args.common,common_sha256=args.common_sha256,search_directory=args.search_directory,
        search_receipt_sha256=args.search_receipt_sha256)
    return 0


if __name__=='__main__':sys.exit(main())
