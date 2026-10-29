"""One fixed known-DEV OD02 N128 treatment-only600-second completion diagnostic."""
import argparse
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import json
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
from .domain import (SCHEMA,CASE,METHOD,INNER_ARM,METHOD_POLICY,ARMS,EXACT_PHASE_SECONDS,
    ORIGINAL_HMAX,POST_SERVICE_POLICY,ANALYTIC_POLICY,REVIEW_STATUS,BASELINE_SOURCE_COMMIT,COMPLETION_POLICY,
    CONFIGS,PostServiceCompletionDomain,historical_operators,outer_admission)

CASES=(CASE,)
SPECS={CASE:cohort.SPECS[CASE]}
PAIRS=[[CASE,list(ARMS)]]
LIMITS=dict(completion.LIMITS,search_seconds=600,search_worker_wall_seconds=900,search_worker_cpu_seconds=900,
    parent_cpu_hard_policy='preserve_inherited_at_least_901')
OBSERVER=dict(envelope.OBSERVER)
RESERVE=dict(completion.RESERVE,exact_search_seconds_per_arm=600,total_exact_search_seconds=600,
    maximum_worker_wall_seconds=1680,maximum_worker_cpu_soft_seconds=1620)
extract_case=cohort.extract_case


def prospective():
    return dict(schema=SCHEMA,launchable=False,status='prospective_'+REVIEW_STATUS,
        review_status=REVIEW_STATUS,baseline_source_commit=BASELINE_SOURCE_COMMIT,
        case_id=CASE,candidate_count=128,historical_hmax=ORIGINAL_HMAX,case_binding=SPECS[CASE],
        cohort_binding_sha256=base.file_hash(cohort.BINDING_PATH),order=PAIRS,method=METHOD,
        shared_configuration=cohort.shared_configuration(False),arms=CONFIGS,post_service_policy=POST_SERVICE_POLICY,
        analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,
        method_policy=METHOD_POLICY,observer=OBSERVER,
        denominator=dict(common_preparations=1,search_arms=1,independent_replays=1,total_stages=3),
        reserve_plan=RESERVE,limits=LIMITS,cache_policy=base.CACHE_POLICY,inputs=cohort.COHORT['inputs'],
        repo=None,input_directory=None,compiler=None,source=None,max_heavy_workers=1,
        automatic_next_run=False,holdout=False,historical_pooling=False,require_positive_result=False,
        selection='previously_exposed_240s_pair_did_not_reach_second_layer_reduction',outcome_blind=False,
        same_budget_speedup_comparison=False,historical_240_results_retained=True)


def source_identity(repo):
    # Include the unchanged analytic gate whose counter validator we reuse.
    identity=prior_gate.source_identity(repo);closure=dict(identity['closure']);repo=Path(repo)
    if 'src/timecut5/post_service_dominance.py' not in closure:
        raise ValueError('Post-service executable closure lacks the reducer module')
    # Generated metadata is not production code. Exclude this exact known
    # packaging prefix only; the full executable closure still binds it.
    production={n:h for n,h in closure.items() if n.startswith('src/') and not n.startswith('src/hiroute.egg-info/')}
    for path in sorted((repo/'experiments/post_service_completion_gate_v1').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            closure[str(path.relative_to(repo))]=base.file_hash(path)
    return dict(identity,closure=closure,closure_sha256=base.digest(closure),
        production_source_sha256=base.digest(production),production_source_entries=len(production))


def require_launch_review():
    """The scaffold cannot produce or consume a launchable manifest yet."""
    if REVIEW_STATUS!='approved_completion_gate_review':
        raise ValueError('Post-service completion launch blocked: independent gate review is pending')


def require_exact_phase(search):
    phase=search.get('phase_budget',{})
    if (search.get('status') not in ('SUCCESS','TIMEOUT') or search.get('phase_entered_monotonic') is None or
        type(phase.get('seconds')) is not int or phase['seconds']!=EXACT_PHASE_SECONDS or
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
    if manifest['status']!='frozen_post_service_completion_not_launched':raise ValueError('Frozen post-service status differs')
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
    if case_id!=CASE:raise ValueError('Case is outside fixed post-service gate')
    spec=SPECS[case_id]
    if len(sites)!=128 or not cohort.ordered_candidates_match(sites,spec):
        raise ValueError('Original post-service candidate order differs')
    bindings=manifest['inputs'];directory=manifest['input_directory']
    tree=base.original_tree((Path(directory)/'hierarchy.json').read_bytes(),bindings['hierarchy.json']['sha256'],list(sites))
    return PostServiceCompletionDomain(arm=arm,case_binding=spec,required_hmax=ORIGINAL_HMAX,manifest_binding=base.digest(manifest),
        graph_factory=lambda:base.load_graph(directory,bindings),query=query,sites=sites,tree=tree,
        source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache,compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def validate_common(common,case_id,manifest):
    if case_id!=CASE or common.get('schema')!=SCHEMA:raise ValueError('Post-service common schema/case differs')
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
    if arm not in ARMS or case_id!=CASE:raise ValueError('Outside fixed post-service gate')
    inner,sources=cohort.progress_binding(manifest,METHOD,case_id,common)
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
    if arm not in ARMS or case_id!=CASE:raise ValueError('Outside fixed post-service gate')
    method=METHOD
    path=Path(path);value,raw_sha,size=envelope.read_bounded_json(path)
    inner,inner_sha,_=envelope.read_bounded_json(path.parent.parent/'remaining_charge_admission.json')
    outer,outer_sha,_=envelope.read_bounded_json(path.parent.parent/'method_admission.json')
    reducer_admission,reducer_sha,_=envelope.read_bounded_json(path.parent.parent/'post_service_completion_admission.json')
    spec=SPECS[case_id];config=manifest['shared_configuration'];digest=base.digest(manifest)
    if base.canonical(reducer_admission)!=base.canonical(outer_admission(digest,arm,outer_sha)):
        raise ValueError('Outer post-service admission differs')
    if (value.get('post_service_completion_schema')!=SCHEMA or value.get('post_service_completion_arm')!=arm or
        base.canonical(value.get('post_service_completion_configuration'))!=base.canonical(CONFIGS[arm]) or
        base.canonical(value.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
        base.canonical(value.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
        base.canonical(value.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or value.get('post_service_completion_admission_sha256')!=reducer_sha):
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
            result.get('post_service_completion_arm')!=arm or base.canonical(result.get('post_service_completion_configuration'))!=base.canonical(CONFIGS[arm]) or
            base.canonical(result.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
            base.canonical(result.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
            base.canonical(result.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or result.get('post_service_completion_admission_sha256')!=reducer_sha or
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
    return dict(sha256=raw_sha,bytes=size,post_service_completion_admission_sha256=reducer_sha,analytic_charge_statistics=value['analytic_charge_statistics'],status=value['status'],method_admission_sha256=outer_sha,
        remaining_charge_admission_sha256=inner_sha,remaining_charge_activation_diagnostic=inner.get('diagnostic'),
        projection_support_statistics=value['projection_support_statistics'],envelope_sweep_statistics=value['envelope_sweep_statistics'],
        post_service_statistics=value['post_service_statistics'],
        singleton_bound_statistics=value['singleton_bound_statistics'],sampled_wall_ns=value['sampled_wall_ns'],last_active_stack=value['active_stack'],
        maximum_observed_write_gap_ns=value['maximum_observed_write_gap_ns'],timeout_snapshot_is_censored=search_status=='TIMEOUT',
        terminal_observer_health_proved=healthy)


def validate_terminal(completed,full,arm,expected_hmax):
    if arm not in ARMS:raise ValueError('Unknown post-service arm')
    method=METHOD
    exact=completed.get('result');payload=exact.get('result') if type(exact) is dict else None
    statuses={'attained_optimum':('attained_optimum',),'infimum_unattained':('primary_unattained','secondary_unattained')}
    if (completed.get('method')!=method or completed.get('strategy')!=arm or completed.get('post_service_completion_arm')!=arm or completed.get('status') not in statuses or
        type(payload) is not dict or payload.get('status') not in statuses[completed['status']]):
        raise ValueError('Missing or mis-tagged exact method terminal payload')
    if (full.get('method')!=method or full.get('post_service_completion_schema')!=SCHEMA or full.get('post_service_completion_arm')!=arm or
        base.canonical(full.get('post_service_completion_configuration'))!=base.canonical(CONFIGS[arm]) or
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
    return {k:v for k,v in payload.items() if k not in ('charges','witness_replayed')}


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


def run_gate(path,sha256,output,cpu):
    manifest=_manifest(path,sha256);output=Path(output)
    from .lifecycle import run_plan
    ledger=run_plan(path,sha256,output,cpu,manifest_loader=_manifest,expected_limits=LIMITS)
    for row in ledger['stages']:
        if row['status']=='PENDING':row.update(status='BLOCKED_EXECUTION_STOPPED',reason=ledger['status'])
    for arm in ledger['arms']:
        if arm['status']=='PENDING':arm['status']='BLOCKED_EXECUTION_STOPPED'
    ledger.update(scope='post_service_known_dev_completion_v1',method=METHOD,operational_admission=False,
        authenticated_complete=False,admission_errors=[],completion_outcome='incomplete_or_blocked',
        same_budget_speedup_comparison=False,historical_240_results_retained=True)
    try:
        if ledger['denominator']!=3 or len(ledger['stages'])!=3 or len(ledger['arms'])!=1:
            raise ValueError('Fixed three-slot denominator differs')
        if any(type(a.get('pair')) is not int for a in ledger['arms']) or [
            (a.get('case'),a.get('strategy'),a.get('pair')) for a in ledger['arms']]!=[(CASE,a,0) for a in ARMS]:
            raise ValueError('Fixed post-service arm identities/order differ')
        def stage(position,identifier,operation,arm,receipt,allowed):
            if receipt.get('status') not in allowed or not receipt.get('cleanup_verified'):
                raise ValueError('Unadmitted receipt/cleanup: '+identifier)
            expected=dict(id=identifier,operation=operation,case=CASE,status=receipt['status'])
            if arm is not None:expected['strategy']=arm
            if ledger['stages'][position]!=expected:raise ValueError('Stage/receipt identity differs: '+identifier)
        receipt=ledger['common'].get(CASE,{})
        stage(0,'prepare-'+CASE,'prepare',None,receipt,('SUCCESS',))
        common=base.load_worker_result(output/('prepare-'+CASE),receipt,'prepare',CASE)
        validate_common(common,CASE,manifest)
        admitted={}
        for i,arm in enumerate(ledger['arms']):
            name=arm['strategy'];arm['authenticated_completion']=False;arm['operational_admission']=False
            try:
                search,verify=arm['receipt'],arm['verification']
                stage(1+2*i,'search-'+str(i),'search',name,search,('SUCCESS','TIMEOUT'))
                stage(2+2*i,'verify-'+str(i),'verify',name,verify,('SUCCESS',));require_exact_phase(search)
                identity=search.get('phase_budget',{}).get('identity',{})
                if (identity.get('case_id')!=CASE or identity.get('strategy')!=name or identity.get('arm_index')!=str(i) or
                    identity.get('manifest_sha256')!=sha256 or identity.get('source_closure_sha256')!=manifest['source']['closure_sha256'] or
                    identity.get('experiment_schema')!=SCHEMA or identity.get('completion_policy_sha256')!=base.digest(COMPLETION_POLICY)):
                    raise ValueError('Post-service phase identity differs')
                full=base.load_worker_result(output/f'verify-{i:02d}',verify,'verify',CASE,name)
                if (arm['status']!=full['status'] or full.get('method')!=METHOD or full.get('post_service_completion_schema')!=SCHEMA or
                    full.get('post_service_completion_arm')!=name or base.canonical(full.get('post_service_completion_configuration'))!=base.canonical(CONFIGS[name]) or
                    base.canonical(full.get('analytic_charge_policy'))!=base.canonical(ANALYTIC_POLICY) or
                    base.canonical(full.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
                    base.canonical(full.get('post_service_policy'))!=base.canonical(POST_SERVICE_POLICY) or
                    full.get('case_binding_sha256')!=base.digest(SPECS[CASE])):
                    raise ValueError('Fresh verifier post-service arm/method/case differs')
                completed=None
                if search['status']=='SUCCESS':
                    completed=base.load_worker_result(output/f'arm-{i:02d}',search,'arm',CASE,name)
                    validate_terminal(completed,full,name,common['seed']['max_depth'])
                elif full.get('search_status')!='TIMEOUT' or full['status']!='timeout_feasible_only':
                    raise ValueError('Timeout verifier claims more than feasible evidence')
                arm['progress']=read_progress(output/f'arm-{i:02d}/artifacts/arm/progress/progress.json',manifest,name,CASE,common,
                    search_status=search['status'],completed_result=completed)
                arm['authenticated_completion']=search['status']=='SUCCESS';arm['operational_admission']=True
                admitted[name]=arm['authenticated_completion']
            except (ValueError,KeyError,TypeError,OSError) as exc:
                arm['admission_error']=str(exc);ledger['admission_errors'].append(dict(arm=name,error=str(exc)))
        ledger['operational_admission']=ledger['status']=='COMPLETED' and all(a in admitted for a in ARMS)
        if ledger['operational_admission'] and all(admitted.values()):
            ledger['authenticated_complete']=True;ledger['completion_outcome']='authenticated_complete'
        elif ledger['operational_admission']:ledger['completion_outcome']='operational_timeout_feasible_only'
    except (ValueError,KeyError,TypeError,OSError) as exc:
        ledger['admission_errors'].append(dict(error=str(exc)))
        try:ledger['preparation_blocked_diagnostic']=blocked_preparation_diagnostic(output/('prepare-'+CASE),CASE)
        except (ValueError,KeyError,TypeError,OSError):pass
    temporary=output/'ledger.tmp';temporary.write_bytes(base.canonical(ledger));os.replace(temporary,output/'ledger.json')
    return ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--freeze',action='store_true');mode.add_argument('--gate',action='store_true')
    mode.add_argument('--worker',choices=('prepare','arm','verify'))
    for name in ('manifest','manifest-sha256','output','input-directory','common','common-sha256','search-directory','search-receipt-sha256'):
        parser.add_argument('--'+name)
    parser.add_argument('--cpu',type=int);parser.add_argument('--case',choices=CASES);parser.add_argument('--strategy',choices=ARMS)
    args=parser.parse_args()
    if args.plan:print(json.dumps(prospective(),indent=2,sort_keys=True));return 0
    if args.freeze:
        if not args.output or not args.input_directory:parser.error('Freeze requires output and input directory')
        require_launch_review()
        manifest=prospective();root=Path.cwd().resolve();compiler=Path(shutil.which('g++')).resolve()
        manifest.update(launchable=True,status='frozen_post_service_completion_not_launched',repo=str(root),input_directory=str(Path(args.input_directory).resolve()),
            compiler=dict(path=str(compiler),sha256=base.file_hash(compiler),version=subprocess.check_output([str(compiler),'--version'],text=True),flags=['-O3','-std=c++17']),source=source_identity(root))
        raw=base.canonical(manifest)
        with Path(args.output).open('xb') as stream:stream.write(raw)
        digest=hashlib.sha256(raw).hexdigest();_manifest(args.output,digest)
        print(json.dumps(dict(manifest=str(Path(args.output).resolve()),sha256=digest)));return 0
    if args.gate:
        if args.output is None or args.cpu is None or args.case is not None or args.strategy is not None:parser.error('Fixed treatment-only gate requires output/cpu only')
        return 0 if run_gate(args.manifest,args.manifest_sha256,args.output,args.cpu)['operational_admission'] else 1
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
