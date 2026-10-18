"""Two fixed known-DEV N128 matched FLAT/HIER600-second case pipelines."""
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
from experiments.analytic_charge_gate_v1 import run as analytic_gate
from experiments.post_service_gate_v1 import run as prior_gate
from experiments.dev_cohort_v1.domain import method_admission
from .domain import (SCHEMA,CASES,METHODS,INNER_ARM,METHOD_POLICY,ARMS,EXACT_PHASE_SECONDS,
    ORIGINAL_HMAX,POST_SERVICE_POLICY,ANALYTIC_POLICY,REVIEW_STATUS,BASELINE_SOURCE_COMMIT,BASELINE_SRC_SHA256,COMPLETION_POLICY,
    CONFIGS,PostServiceCohortDomain,historical_operators,outer_admission)

SPECS={case:cohort.SPECS[case] for case in CASES}
PAIRS=[[CASES[0],['flat','hier']],[CASES[1],['hier','flat']]]
CPU_BY_CASE={CASES[0]:0,CASES[1]:1}
PRODUCTION_SOURCE_ENTRIES=95
LIMITS=dict(completion.LIMITS,search_seconds=600,search_worker_wall_seconds=900,search_worker_cpu_seconds=900,
    parent_cpu_hard_policy='preserve_inherited_at_least_901',pipeline_wall_seconds=3000)
OBSERVER=dict(envelope.OBSERVER)
RESERVE=dict(completion.RESERVE,exact_search_seconds_per_arm=600,total_exact_search_seconds=2400,exact_search_seconds_per_case=1200,
    maximum_worker_wall_seconds=5520,maximum_worker_cpu_soft_seconds=5280,
    maximum_worker_wall_seconds_per_case=2760,maximum_worker_cpu_soft_seconds_per_case=2640)
extract_case=cohort.extract_case


CONCURRENCY_POLICY=dict(schema='hiroute.post_service_cohort_concurrency.v1',
    pipeline_count=2,max_heavy_workers=2,cpu_by_case=CPU_BY_CASE,
    one_dedicated_single_threaded_supervisor_process_per_case=True,
    case_stages_serial=True,parent_only_supervises_case_pipelines=True,numeric_threads=1,
    aggregate_memory_hard_limit=False,cgroup_enforced=False,clean_cache_claim=False,
    isolation_claim=False,automatic_concurrency_reduction=False,
    expected_peak_rss_bytes_per_heavy_worker=round(3.6*1024**3),
    admission_rss_budget_bytes_per_heavy_worker=3840*1024**2,
    available_memory_reserve_bytes=768*1024**2,
    required_available_memory_bytes=8448*1024**2,
    memory_admission='prelaunch_MemAvailable_observation_not_reservation')


def prospective():
    return dict(schema=SCHEMA,launchable=False,status='prospective_'+REVIEW_STATUS,
        review_status=REVIEW_STATUS,baseline_source_commit=BASELINE_SOURCE_COMMIT,baseline_src_sha256=BASELINE_SRC_SHA256,
        production_source_entries=PRODUCTION_SOURCE_ENTRIES,
        cases=[SPECS[case] for case in CASES],candidate_count=128,historical_hmax=ORIGINAL_HMAX,
        cohort_binding_sha256=base.file_hash(cohort.BINDING_PATH),order=PAIRS,
        shared_configuration=cohort.shared_configuration(False),arms=CONFIGS,post_service_policy=POST_SERVICE_POLICY,
        analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,
        method_policy=METHOD_POLICY,observer=OBSERVER,concurrency_policy=CONCURRENCY_POLICY,
        denominator=dict(common_preparations=2,search_arms=4,independent_replays=4,total_stages=10,stages_per_case=5),
        reserve_plan=RESERVE,limits=LIMITS,cache_policy=base.CACHE_POLICY,inputs=cohort.COHORT['inputs'],
        repo=None,input_directory=None,compiler=None,source=None,max_heavy_workers=2,
        automatic_next_run=False,holdout=False,historical_pooling=False,require_positive_result=False,
        selection='two_previously_exposed_N128_energy_only_and_scheduled_DEV_cases',outcome_blind=False,
        same_budget_speedup_comparison=True,performance_interpretation='descriptive_shared_host_only',
        historical_240_results_retained=True)


def source_identity(repo):
    # Include the unchanged analytic gate whose counter validator we reuse.
    identity=prior_gate.source_identity(repo);closure=dict(identity['closure']);repo=Path(repo)
    if 'src/timecut5/post_service_dominance.py' not in closure:
        raise ValueError('Post-service executable closure lacks the reducer module')
    # Generated metadata is not production code. Exclude this exact known
    # packaging prefix only; the full executable closure still binds it.
    production={n:h for n,h in closure.items() if n.startswith('src/') and not n.startswith('src/hiroute.egg-info/')}
    if len(production)!=PRODUCTION_SOURCE_ENTRIES or base.digest(production)!=BASELINE_SRC_SHA256:
        raise ValueError('Completion production source differs from fixed pre-convex-runtime baseline')
    for path in sorted((repo/'experiments/post_service_cohort_v1').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            closure[str(path.relative_to(repo))]=base.file_hash(path)
    return dict(identity,closure=closure,closure_sha256=base.digest(closure))


def require_launch_review():
    """The scaffold cannot produce or consume a launchable manifest yet."""
    if REVIEW_STATUS!='approved_independent_cohort_review':
        raise ValueError('Post-service completion launch blocked: independent gate review is pending')


def require_exact_phase(search):
    phase=search.get('phase_budget',{});entered=search.get('phase_entered_monotonic')
    if (type(phase) is not dict or type(entered) not in (int,float) or not math.isfinite(entered) or entered<=0 or search.get('status') not in ('SUCCESS','TIMEOUT') or type(phase.get('seconds')) is not int or phase['seconds']!=EXACT_PHASE_SECONDS or
        search['status']=='TIMEOUT' and search.get('reason')!='phase_timeout'):
        raise ValueError('Search did not complete or exhaust its declared600-second exact phase')


def _manifest(path,expected_sha256):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Post-service manifest digest differs')
    manifest=json.loads(raw)
    expected=prospective()
    if manifest.get('schema')!=SCHEMA or manifest.get('launchable') is not True:raise ValueError('Prospective post-service is not launchable')
    runtime={'launchable','status','repo','input_directory','compiler','source'}
    if set(manifest)!=set(expected) or any(base.canonical(manifest[k])!=base.canonical(v) for k,v in expected.items() if k not in runtime):
        raise ValueError('Frozen post-service policy differs')
    require_launch_review()
    if manifest['status']!='frozen_post_service_cohort_not_launched':raise ValueError('Frozen post-service status differs')
    compiler=manifest['compiler']
    if (set(compiler)!={'path','sha256','version','flags'} or base.file_hash(compiler['path'])!=compiler['sha256'] or
        subprocess.check_output([compiler['path'],'--version'],text=True)!=compiler['version'] or compiler['flags']!=['-O3','-std=c++17']):
        raise ValueError('Pinned post-service compiler differs')
    if manifest['source']!=source_identity(manifest['repo']):raise ValueError('Post-service executable closure differs')
    cohort.require_generated_inputs(manifest['input_directory'],manifest['inputs'])
    for name,binding in manifest['inputs'].items():
        target=Path(manifest['input_directory'])/name
        if target.stat().st_size!=binding['size'] or base.file_hash(target)!=binding['sha256']:raise ValueError('Post-service input differs: '+name)
    return manifest


def domain_factory(manifest,query,sites,cache,*,arm,case_id):
    if case_id not in CASES:raise ValueError('Case is outside fixed post-service gate')
    spec=SPECS[case_id]
    if len(sites)!=128 or not cohort.ordered_candidates_match(sites,spec):
        raise ValueError('Original post-service candidate order differs')
    bindings=manifest['inputs'];directory=manifest['input_directory']
    tree=base.original_tree((Path(directory)/'hierarchy.json').read_bytes(),bindings['hierarchy.json']['sha256'],list(sites))
    return PostServiceCohortDomain(arm=arm,case_binding=spec,required_hmax=ORIGINAL_HMAX[case_id],manifest_binding=base.digest(manifest),
        graph_factory=lambda:base.load_graph(directory,bindings),query=query,sites=sites,tree=tree,
        source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache,compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def validate_common(common,case_id,manifest):
    if case_id not in CASES or common.get('schema')!=SCHEMA:raise ValueError('Post-service common schema/case differs')
    cohort.validate_common(common,case_id,manifest)


@historical_operators()
def prepare_case(manifest,case_id,output):
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.sparse_seed import SparseSeedCatalog,sparse_domain_digest,replay_sparse_seed,SeedInfeasible
    from timecut5.deployable import iter_constructive_seed_candidates
    from timecut5.provenance import primitive
    started=time.monotonic_ns();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    directory,bindings=manifest['input_directory'],manifest['inputs'];spec=SPECS[case_id]
    query,sites,_=extract_case(directory,case_id,bindings);historical=base.digest(query)
    make=lambda q:domain_factory(manifest,q,sites,output/'native',arm=ARMS[0],case_id=case_id)
    domain=make(query)
    with domain.context('generation') as context:
        query=dict(query,sparse_domain_sha256=sparse_domain_digest(context.provider.source_sha256,site_catalog_digest(sites),
            base.digest(sorted(sites)),query['hierarchy_sha256'],query['origin'],query['destination']))
    domain=make(query)
    def catalog(context):
        return SparseSeedCatalog(context.provider,sites,origin_anchor=query['origin'],destination_anchor=query['destination'],
            nodes_path=Path(directory)/'nodes.parquet',edges_path=Path(directory)/'edges.parquet',site_catalog_sha256=site_catalog_digest(sites),
            hierarchy_sha256=query['hierarchy_sha256'],candidate_sha256=base.digest(sorted(sites)))
    with domain.context('generation') as context:
        sparse=catalog(context);witness=None
        for ordinal,(sequence,charges) in enumerate(iter_constructive_seed_candidates(query,sparse)):
            try:replay_sparse_seed(query,sparse,sequence,charges)
            except SeedInfeasible:continue
            witness=base.proposal_witness(domain.problem(context),sequence,charges);break
        if witness is None:raise ValueError('incumbent_search_failed: fixed proposal stream exhausted; feasibility unknown')
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
    if seed.max_depth!=spec['historical_hmax']:
        blocked=dict(schema=SCHEMA,case_id=case_id,reason='BLOCKED_SEED_HMAX_MISMATCH',expected=spec['historical_hmax'],observed=seed.max_depth,
            common_sha256=base.file_hash(output/'common.json'),case_binding_sha256=base.digest(spec))
        (output/'blocked.json').write_bytes(base.canonical(blocked))
    validate_common(common,case_id,manifest)
    return common


def progress_binding(manifest,arm,case_id,common):
    if arm not in ARMS or case_id not in CASES:raise ValueError('Outside fixed post-service gate')
    inner,sources=cohort.progress_binding(manifest,arm,case_id,common)
    policy=[SCHEMA,arm,CONFIGS[arm],POST_SERVICE_POLICY,ANALYTIC_POLICY,COMPLETION_POLICY,base.digest(manifest)]
    return base.digest([inner,*policy]),dict(sources,post_service_policy=base.digest(policy))


def validate_combined_statistics(support,analytic,arm,*,completed):
    """Preserve the historical joined support/C count meanings, analyticON."""
    if arm not in ARMS:raise ValueError('Unknown post-service arm')
    analytic_gate.validate_combined_statistics(support,analytic,'analytic_on',completed=completed)


def validate_post_service_statistics(value,arm,*,completed):
    """Validate scalar samples; final identities need healthy terminal context."""
    from timecut5.post_service_dominance import PostServiceDominanceStatistics
    if arm not in ARMS:raise ValueError('Unknown post-service arm')
    names=set(PostServiceDominanceStatistics.__dataclass_fields__)
    if (type(value) is not dict or set(value)!=names or type(value['enabled']) is not bool or
        value['enabled'] is not CONFIGS[arm]['post_service_dominance'] or
        any(type(value[n]) is not int or value[n]<0 for n in names-{'enabled'})):
        raise ValueError('Post-service statistics types or policy differ')
    strong=('strong_calls','arrangement_cells','selected_cells','candidate_visits',
        'strict_primary_discarded','tied_primary_discarded','parent_run_coalesces')
    if not value['enabled'] and any(value[n] for n in (*strong,
        'pre_service_fallback_calls','recorded_fallback_calls','unsupported_fallback_calls')):
        raise ValueError('Disabled post-service reducer reported enabled work')
    if value['enabled'] and value['disabled_fallback_calls']:
        raise ValueError('Enabled post-service reducer reported disabled work')
    fallbacks=sum(value[n] for n in ('disabled_fallback_calls','pre_service_fallback_calls',
        'recorded_fallback_calls','unsupported_fallback_calls'))
    strong_outputs=value['selected_cells']-value['parent_run_coalesces']
    if completed and (
        value['calls']!=value['strong_calls']+fallbacks or
        value['candidate_visits']!=value['selected_cells']+value['strict_primary_discarded']+value['tied_primary_discarded'] or
        value['parent_run_coalesces']>value['selected_cells'] or
        value['selected_cells']>value['arrangement_cells'] or
        strong_outputs>value['output_pieces'] or
        not fallbacks and value['output_pieces']!=strong_outputs):
        raise ValueError('Completed post-service counters do not conserve')


def read_progress(path,manifest,arm,case_id,common,*,search_status,completed_result=None):
    if arm not in ARMS or case_id not in CASES:raise ValueError('Outside fixed post-service gate')
    method=arm
    path=Path(path);value,raw_sha,size=envelope.read_bounded_json(path)
    inner,inner_sha,_=envelope.read_bounded_json(path.parent.parent/'remaining_charge_admission.json')
    outer,outer_sha,_=envelope.read_bounded_json(path.parent.parent/'method_admission.json')
    reducer_admission,reducer_sha,_=envelope.read_bounded_json(path.parent.parent/'post_service_cohort_admission.json')
    spec=SPECS[case_id];config=manifest['shared_configuration'];digest=base.digest(manifest)
    if base.canonical(reducer_admission)!=base.canonical(outer_admission(digest,arm,outer_sha)):
        raise ValueError('Outer post-service admission differs')
    if (value.get('post_service_cohort_schema')!=SCHEMA or value.get('post_service_cohort_arm')!=arm or
        base.canonical(value.get('post_service_cohort_configuration'))!=base.canonical(CONFIGS[arm]) or
        base.canonical(value.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
        base.canonical(value.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
        base.canonical(value.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or value.get('post_service_cohort_admission_sha256')!=reducer_sha):
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
            result.get('post_service_cohort_arm')!=arm or base.canonical(result.get('post_service_cohort_configuration'))!=base.canonical(CONFIGS[arm]) or
            base.canonical(result.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
            base.canonical(result.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
            base.canonical(result.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or result.get('post_service_cohort_admission_sha256')!=reducer_sha or
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
            ('projection_support_statistics','envelope_sweep_statistics','singleton_bound_statistics','analytic_charge_statistics','post_service_statistics')):
            raise ValueError('Authenticated operator statistics differ')
        counters(result,True);healthy=True
    return dict(sha256=raw_sha,bytes=size,post_service_cohort_admission_sha256=reducer_sha,analytic_charge_statistics=value['analytic_charge_statistics'],status=value['status'],method_admission_sha256=outer_sha,
        remaining_charge_admission_sha256=inner_sha,remaining_charge_activation_diagnostic=inner.get('diagnostic'),
        projection_support_statistics=value['projection_support_statistics'],envelope_sweep_statistics=value['envelope_sweep_statistics'],
        post_service_statistics=value['post_service_statistics'],
        singleton_bound_statistics=value['singleton_bound_statistics'],sampled_wall_ns=value['sampled_wall_ns'],last_active_stack=value['active_stack'],
        maximum_observed_write_gap_ns=value['maximum_observed_write_gap_ns'],timeout_snapshot_is_censored=search_status=='TIMEOUT',
        terminal_observer_health_proved=healthy)


def validate_terminal(completed,full,arm,expected_hmax):
    if arm not in ARMS:raise ValueError('Unknown post-service arm')
    method=arm
    exact=completed.get('result');payload=exact.get('result') if type(exact) is dict else None
    statuses={'attained_optimum':('attained_optimum',),'infimum_unattained':('primary_unattained','secondary_unattained')}
    if (completed.get('method')!=method or completed.get('strategy')!=arm or completed.get('post_service_cohort_arm')!=arm or completed.get('status') not in statuses or
        type(payload) is not dict or payload.get('status') not in statuses[completed['status']]):
        raise ValueError('Missing or mis-tagged exact method terminal payload')
    if (full.get('method')!=method or full.get('post_service_cohort_schema')!=SCHEMA or full.get('post_service_cohort_arm')!=arm or
        base.canonical(full.get('post_service_cohort_configuration'))!=base.canonical(CONFIGS[arm]) or
        base.canonical(full.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
        base.canonical(full.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
        base.canonical(full.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or completed['accepted_key']!=full['accepted_key'] or completed['status']!=full['status'] or
        full.get('search_status')!='SUCCESS'):raise ValueError('Completed method answer lacks matching fresh full replay')
    if (type(expected_hmax) is not int or type(completed.get('Hmax')) is not int or completed['Hmax']!=expected_hmax or
        type(exact.get('H_ref')) is not int or exact['H_ref']!=expected_hmax):
        raise ValueError('Completed exact Hmax differs from common seed')
    if completed['status']=='attained_optimum':
        accepted=completed['accepted_key']
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


def blocked_preparation_diagnostic(directory,case_id):
    """Retained failure detail only; never grants preparation admission."""
    root=Path(directory)/'artifacts/prepared'
    note,sha,_=envelope.read_bounded_json(root/'blocked.json')
    common,common_sha,_=envelope.read_bounded_json(root/'common.json')
    spec=SPECS[case_id]
    if (note.get('schema')!=SCHEMA or note.get('case_id')!=case_id or note.get('reason')!='BLOCKED_SEED_HMAX_MISMATCH' or
        type(note.get('expected')) is not int or note['expected']!=spec['historical_hmax'] or
        type(note.get('observed')) is not int or note['observed']==note['expected'] or
        note.get('case_binding_sha256')!=base.digest(spec) or note.get('common_sha256')!=common_sha or
        common.get('seed',{}).get('max_depth')!=note['observed'] or common.get('case_id')!=case_id):
        raise ValueError('Malformed blocked preparation diagnostic')
    return dict(note,artifact_sha256=sha,diagnostic_only=True,preparation_admitted=False)


def admit_case(ledger,manifest,sha256,output,case):
    """Authenticate all five reserved slots, then compare canonical exact answers."""
    output=Path(output);order=dict(PAIRS)[case]
    outcome=dict(operational_admission=False,both_authenticated_complete=False,status='blocked_or_inconclusive')
    ledger.update(case_outcome=outcome,admission_errors=[])
    if ledger.get('denominator')!=5 or len(ledger.get('stages',[]))!=5 or len(ledger.get('arms',[]))!=2:
        raise ValueError('Fixed five-slot case denominator differs')
    pair=CASES.index(case)
    if [(a.get('case'),a.get('strategy'),a.get('pair')) for a in ledger['arms']]!=[(case,m,pair) for m in order] or any(type(a.get('pair')) is not int for a in ledger['arms']):
        raise ValueError('Fixed cohort arm identities/order differ')
    def stage(position,identifier,operation,method,receipt,allowed):
        if receipt.get('status') not in allowed or receipt.get('cleanup_verified') is not True:
            raise ValueError('Unadmitted receipt/cleanup: '+identifier)
        expected=dict(id=identifier,operation=operation,case=case,status=receipt['status'])
        if method is not None:expected['strategy']=method
        if ledger['stages'][position]!=expected:raise ValueError('Stage/receipt identity differs: '+identifier)
    receipt=ledger['common'].get(case,{})
    try:
        stage(0,'prepare-'+case,'prepare',None,receipt,('SUCCESS',))
        common=base.load_worker_result(output/('prepare-'+case),receipt,'prepare',case)
        validate_common(common,case,manifest)
    except (ValueError,KeyError,TypeError,OSError,AttributeError) as exc:
        ledger['admission_errors'].append(dict(case=case,stage='prepare',error=str(exc)))
        try:outcome['preparation_blocked_diagnostic']=blocked_preparation_diagnostic(output/('prepare-'+case),case)
        except (ValueError,KeyError,TypeError,OSError,AttributeError):pass
        return outcome
    payloads={};admitted={}
    for local_index,arm in enumerate(ledger['arms']):
        method=arm['strategy'];index=2*pair+local_index
        arm.update(authenticated_completion=False,operational_admission=False)
        try:
            search,verify=arm['receipt'],arm['verification']
            stage(1+2*local_index,'search-'+str(index),'search',method,search,('SUCCESS','TIMEOUT'))
            stage(2+2*local_index,'verify-'+str(index),'verify',method,verify,('SUCCESS',));require_exact_phase(search)
            identity=search.get('phase_budget',{}).get('identity',{})
            if (identity.get('case_id')!=case or identity.get('strategy')!=method or identity.get('method')!=method or identity.get('arm_index')!=str(index) or
                identity.get('common_sha256')!=base.file_hash(output/('prepare-'+case)/'artifacts/prepared/common.json') or
                identity.get('manifest_sha256')!=sha256 or identity.get('source_closure_sha256')!=manifest['source']['closure_sha256'] or
                identity.get('experiment_schema')!=SCHEMA or identity.get('completion_policy_sha256')!=base.digest(COMPLETION_POLICY)):
                raise ValueError('Cohort exact phase identity differs')
            full=base.load_worker_result(output/f'verify-{index:02d}',verify,'verify',case,method)
            if (arm['status']!=full['status'] or full.get('method')!=method or full.get('post_service_cohort_schema')!=SCHEMA or
                full.get('post_service_cohort_arm')!=method or base.canonical(full.get('post_service_cohort_configuration'))!=base.canonical(CONFIGS[method]) or
                base.canonical(full.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
                base.canonical(full.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
                base.canonical(full.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or
                full.get('case_binding_sha256')!=base.digest(SPECS[case])):
                raise ValueError('Fresh verifier cohort method/case differs')
            completed=None
            if search['status']=='SUCCESS':
                completed=base.load_worker_result(output/f'arm-{index:02d}',search,'arm',case,method)
                payloads[method]=validate_terminal(completed,full,method,common['seed']['max_depth'])
            elif full.get('search_status')!='TIMEOUT' or full['status']!='timeout_feasible_only':
                raise ValueError('Timeout verifier claims more than feasible evidence')
            arm['progress']=read_progress(output/f'arm-{index:02d}/artifacts/arm/progress/progress.json',manifest,method,case,common,
                search_status=search['status'],completed_result=completed)
            arm['authenticated_completion']=search['status']=='SUCCESS';arm['operational_admission']=True
            admitted[method]=arm['authenticated_completion']
        except (ValueError,KeyError,TypeError,OSError,AttributeError) as exc:
            arm['admission_error']=str(exc);ledger['admission_errors'].append(dict(case=case,method=method,error=str(exc)))
    if ledger['status']=='COMPLETED' and all(m in admitted for m in METHODS):
        outcome.update(operational_admission=True,status='operational_feasible_evidence')
        if all(admitted.values()):
            if payloads['flat']!=payloads['hier']:
                outcome.update(operational_admission=False,status='completed_exact_disagreement')
                ledger['admission_errors'].append(dict(case=case,error='Completed FLAT/HIER answers disagree'))
            else:outcome.update(both_authenticated_complete=True,status='both_authenticated_complete')
    return outcome


def run_gate(path,sha256,output):
    from .lifecycle import run_coordinator
    manifest=_manifest(path,sha256)
    ledger=run_coordinator(path,sha256,output,manifest_loader=_manifest,expected_limits=LIMITS)
    ledger.update(operational_admission=False,all_pairs_authenticated_complete=False,case_outcomes={},admission_errors=[],
        completion_outcome='incomplete_or_blocked',same_budget_speedup_comparison=True,
        performance_interpretation='descriptive_shared_host_only',historical_240_results_retained=True)
    try:
        if ledger['denominator']!=10 or len(ledger['stages'])!=10 or len(ledger['arms'])!=4:
            raise ValueError('Fixed ten-slot denominator differs')
        for case in CASES:
            pipeline=ledger['pipelines'][case]
            try:
                if pipeline.get('process_returncode')!=0 or pipeline.get('pipeline_cleanup_verified') is not True:
                    raise ValueError('Case pipeline process failed or cleanup is unverified')
                outcome=admit_case(pipeline,manifest,sha256,Path(output)/case,case)
            except (ValueError,KeyError,TypeError,OSError,AttributeError) as exc:
                outcome=dict(operational_admission=False,both_authenticated_complete=False,status='blocked_or_inconclusive')
                ledger['admission_errors'].append(dict(case=case,error=str(exc)))
            ledger['case_outcomes'][case]=outcome
            ledger['admission_errors'].extend(pipeline.get('admission_errors',[]))
        # Case rows are the authoritative independent ledgers. Rebuild the fixed
        # global denominator after admission adds observations to those rows.
        ledger['stages']=[r for case in CASES for r in ledger['pipelines'][case]['stages']]
        ledger['arms']=[r for case in CASES for r in ledger['pipelines'][case]['arms']]
        ledger['operational_admission']=ledger['status']=='COMPLETED' and all(x['operational_admission'] for x in ledger['case_outcomes'].values())
        ledger['all_pairs_authenticated_complete']=ledger['operational_admission'] and all(x['both_authenticated_complete'] for x in ledger['case_outcomes'].values())
        if ledger['all_pairs_authenticated_complete']:ledger['completion_outcome']='both_pairs_authenticated_complete'
        elif ledger['operational_admission']:ledger['completion_outcome']='operational_partial_or_timeouts'
    except (ValueError,KeyError,TypeError,OSError,AttributeError) as exc:ledger['admission_errors'].append(dict(error=str(exc)))
    temporary=Path(output)/'ledger.tmp';temporary.write_bytes(base.canonical(ledger));os.replace(temporary,Path(output)/'ledger.json')
    return ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--freeze',action='store_true');mode.add_argument('--gate',action='store_true')
    mode.add_argument('--worker',choices=('prepare','arm','verify'));mode.add_argument('--pipeline',action='store_true')
    for name in ('manifest','manifest-sha256','output','input-directory','common','common-sha256','search-directory','search-receipt-sha256'):
        parser.add_argument('--'+name)
    parser.add_argument('--cpu',type=int);parser.add_argument('--case',choices=CASES);parser.add_argument('--strategy',choices=ARMS)
    args=parser.parse_args()
    if args.plan:print(json.dumps(prospective(),indent=2,sort_keys=True));return 0
    if args.freeze:
        if not args.output or not args.input_directory:parser.error('Freeze requires output and input directory')
        require_launch_review()
        manifest=prospective();root=Path.cwd().resolve();compiler=Path(shutil.which('g++')).resolve()
        manifest.update(launchable=True,status='frozen_post_service_cohort_not_launched',repo=str(root),input_directory=str(Path(args.input_directory).resolve()),
            compiler=dict(path=str(compiler),sha256=base.file_hash(compiler),version=subprocess.check_output([str(compiler),'--version'],text=True),flags=['-O3','-std=c++17']),source=source_identity(root))
        raw=base.canonical(manifest)
        with Path(args.output).open('xb') as stream:stream.write(raw)
        digest=hashlib.sha256(raw).hexdigest();_manifest(args.output,digest)
        print(json.dumps(dict(manifest=str(Path(args.output).resolve()),sha256=digest)));return 0
    if args.gate:
        if args.output is None or args.cpu is not None or args.case is not None or args.strategy is not None:parser.error('Fixed two-case gate requires output; CPUs are frozen to0/1')
        return 0 if run_gate(args.manifest,args.manifest_sha256,args.output)['operational_admission'] else 1
    if args.pipeline:
        if args.case is None or args.output is None or args.cpu!=CPU_BY_CASE[args.case] or args.strategy is not None:parser.error('Pipeline requires fixed case, CPU and output')
        from .lifecycle import run_case_plan
        run_case_plan(args.manifest,args.manifest_sha256,args.output,args.case,args.cpu,manifest_loader=_manifest,expected_limits=LIMITS)
        return 0
    manifest=_manifest(args.manifest,args.manifest_sha256)
    if args.case is None or (args.worker!='prepare' and args.strategy is None):parser.error('Worker requires fixed case and outer arm')
    if args.worker=='prepare':prepare_case(manifest,args.case,Path(os.environ['HIROUTE_OUTPUT_DIR'])/'prepared')
    else:
        common=json.loads(Path(args.common).read_bytes());validate_common(common,args.case,manifest)
        if args.worker=='verify':
            from experiments.mechanism_recovery_v1.supervisor import read_result
            require_exact_phase(read_result(args.search_directory))
        factory=lambda m,q,s,c:domain_factory(m,q,s,c,arm=args.strategy,case_id=args.case)
        with historical_operators():
            base.worker(manifest,args.worker,args.case,args.common,args.common_sha256,args.strategy,args.search_directory,
                args.search_receipt_sha256,domain_factory=factory)
    _manifest(args.manifest,args.manifest_sha256)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(base.canonical(dict(status='COMPLETED',result=base.result_envelope(
        os.environ['HIROUTE_OUTPUT_DIR'],args.worker,args.case,args.strategy))))
    return 0


if __name__=='__main__':sys.exit(main())
