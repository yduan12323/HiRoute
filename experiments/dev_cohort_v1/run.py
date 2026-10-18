"""Fixed fifteen-slot known-DEV paired FLAT/HIER experiment; no automatic next run."""
import argparse
from dataclasses import asdict
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
from .domain import SCHEMA,METHODS,INNER_ARM,METHOD_POLICY,CohortDomain,shared_configuration,method_admission,POLICY_SCHEMA

from .runtime_inputs import compact_binding, ordered_candidates_match, require_prefix, require_generated_inputs

BINDING_PATH=Path(__file__).resolve().parents[2]/'docs/dev_cohort_v1_bindings.json'
COHORT=json.loads(BINDING_PATH.read_bytes())
CASES=tuple(row['case_id'] for row in COHORT['cases'])
SPECS={row['case_id']:row for row in COHORT['cases']}
PAIRS=[[case,SPECS[case]['method_order']] for case in CASES]
LIMITS=dict(completion.LIMITS)
OBSERVER=dict(envelope.OBSERVER)
RESERVE=dict(completion.RESERVE,total_exact_search_seconds=1440,
    maximum_worker_wall_seconds=6480,maximum_worker_cpu_soft_seconds=6120)
require_exact_phase=completion.require_exact_phase


ENVELOPE_SELECTION=dict(enabled=False,selection='engineering_choice_informed_by_exposed_OD10_DEV_control',
    control_schema=envelope.SCHEMA,outcome_blind=False,production_default_changed=False)


def prospective(envelope_enabled=False):
    if envelope_enabled is not False:raise ValueError('Reviewed cohort requires explicit envelope OFF')
    configuration=shared_configuration(False)
    return dict(schema=SCHEMA,launchable=False,status='prospective_envelope_off_pending_source_review',
        cohort=COHORT,cohort_binding_sha256=base.file_hash(BINDING_PATH),order=PAIRS,
        shared_configuration=configuration,configuration_selection=ENVELOPE_SELECTION,method_policy=METHOD_POLICY,observer=OBSERVER,
        denominator=COHORT['denominator'],reserve_plan=RESERVE,limits=LIMITS,cache_policy=base.CACHE_POLICY,
        inputs=COHORT['inputs'],repo=None,input_directory=None,compiler=None,source=None,
        max_heavy_workers=1,automatic_next_run=False,holdout=False,historical_pooling=False,require_positive_result=False)


def source_identity(repo):
    identity=envelope.source_identity(repo);closure=dict(identity['closure']);repo=Path(repo)
    paths=list((repo/'experiments/dev_cohort_v1').rglob('*'))+[repo/'docs/dev_cohort_v1_bindings.json',repo/'docs/DEV_COHORT_PAIRED_PLAN.md']
    for path in sorted(paths):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            closure[str(path.relative_to(repo))]=base.file_hash(path)
    return dict(identity,closure=closure,closure_sha256=base.digest(closure))


def _manifest(path,expected_sha256):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Cohort manifest digest differs')
    manifest=json.loads(raw)
    configuration=manifest.get('shared_configuration')
    if type(configuration) is not dict:raise ValueError('Explicit common configuration required')
    expected=prospective(configuration.get('envelope_sweep'))
    if manifest.get('schema')!=SCHEMA or manifest.get('launchable') is not True:raise ValueError('Prospective cohort is not launchable')
    runtime={'launchable','status','repo','input_directory','compiler','source'}
    if set(manifest)!=set(expected) or any(base.canonical(manifest[k])!=base.canonical(v) for k,v in expected.items() if k not in runtime):
        raise ValueError('Frozen cohort policy differs')
    compiler=manifest['compiler']
    if (set(compiler)!={'path','sha256','version','flags'} or base.file_hash(compiler['path'])!=compiler['sha256'] or
        subprocess.check_output([compiler['path'],'--version'],text=True)!=compiler['version'] or compiler['flags']!=['-O3','-std=c++17']):
        raise ValueError('Pinned cohort compiler differs')
    if manifest['source']!=source_identity(manifest['repo']):raise ValueError('Cohort executable closure differs')
    require_generated_inputs(manifest['input_directory'],manifest['inputs'])
    for name,binding in manifest['inputs'].items():
        target=Path(manifest['input_directory'])/name
        if target.stat().st_size!=binding['size'] or base.file_hash(target)!=binding['sha256']:raise ValueError('Cohort input differs: '+name)
    return manifest


def extract_case(directory,case_id,bindings):
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.real_legs import RealSite
    if case_id not in SPECS:raise ValueError('Case is outside fixed known-DEV cohort')
    require_generated_inputs(directory,base.INPUT_NAMES)
    base.verify_inputs(directory,{n:bindings[n] for n in base.INPUT_NAMES})
    spec=SPECS[case_id];root=Path(directory)
    rows=json.loads((root/'queries.json').read_bytes())['queries']
    matches=[row for row in rows if row['query_id']==case_id]
    if len(matches)!=1:raise ValueError('Ambiguous cohort query')
    row=matches[0];binding=row['bindings'][str(spec['candidate_count'])]
    pools=json.loads((root/'pools.json').read_bytes())['pools'];matches=[p for p in pools if p['od_id']==row['od_id']]
    if len(matches)!=1:raise ValueError('Ambiguous cohort pool')
    prefix=matches[0]['sites'][:spec['candidate_count']]
    require_prefix(prefix,spec)
    if base.canonical(compact_binding(binding))!=base.canonical(spec['original_binding']):
        raise ValueError('Original candidate/query binding changed')
    sites={s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in prefix};query=binding['query']
    if (len(sites)!=spec['candidate_count'] or list(sites)!=binding['candidate_site_ids'] or
        base.digest(sorted(sites))!=binding['candidate_sha256'] or site_catalog_digest(sites)!=binding['site_catalog_sha256'] or
        base.digest(query)!=binding['query_sha256'] or query['case_id']!=case_id or query['hierarchy_sha256']!=bindings['hierarchy.json']['sha256']):
        raise ValueError('Cohort physical identities differ')
    tree=base.original_tree((root/'hierarchy.json').read_bytes(),query['hierarchy_sha256'],list(sites))
    return query,sites,tree


def domain_factory(manifest,query,sites,cache,*,method,case_id):
    spec=SPECS[case_id]
    if len(sites)!=spec['candidate_count'] or not ordered_candidates_match(sites,spec):
        raise ValueError('Original cohort candidate order differs')
    bindings=manifest['inputs'];directory=manifest['input_directory']
    tree=base.original_tree((Path(directory)/'hierarchy.json').read_bytes(),bindings['hierarchy.json']['sha256'],list(sites))
    return CohortDomain(method=method,envelope_enabled=manifest['shared_configuration']['envelope_sweep'],case_binding=spec,
        required_hmax=spec['historical_hmax'],manifest_binding=base.digest(manifest),graph_factory=lambda:base.load_graph(directory,bindings),
        query=query,sites=sites,tree=tree,source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache,compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def validate_common(common,case_id,manifest):
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.real_legs import RealSite
    spec=SPECS[case_id];binding=spec['original_binding']
    if common.get('case_id')!=case_id or type(common.get('candidate_count')) is not int or common['candidate_count']!=spec['candidate_count'] or common.get('case_binding_sha256')!=base.digest(spec):
        raise ValueError('Cohort common case binding differs')
    seed=common['seed']
    if type(seed['max_depth']) is not int or seed['max_depth']!=spec['historical_hmax']:
        raise ValueError('BLOCKED_SEED_HMAX_MISMATCH expected='+str(spec['historical_hmax'])+' observed='+str(seed['max_depth']))
    query=common['query'];original=dict(query);original['sparse_domain_sha256']=binding['query']['sparse_domain_sha256']
    if base.canonical(original)!=base.canonical(binding['query']) or common.get('historical_query_sha256')!=binding['query_sha256']:
        raise ValueError('Cohort query changed beyond runtime source rebinding')
    sites={s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in common['sites']}
    if (len(common['sites'])!=spec['candidate_count'] or len(sites)!=spec['candidate_count'] or not ordered_candidates_match(sites,spec) or
        site_catalog_digest(sites)!=binding['site_catalog_sha256'] or seed['site_sha256']!=binding['site_catalog_sha256'] or
        seed['query_sha256']!=base.digest(query) or common['source']!=manifest['source'] or common['inputs']!=manifest['inputs'] or
        common['cache_policy']!=manifest['cache_policy']):raise ValueError('Common candidate/source/seed identity differs')
    tree=base.original_tree((Path(manifest['input_directory'])/'hierarchy.json').read_bytes(),manifest['inputs']['hierarchy.json']['sha256'],list(sites))
    if common['tree_sha256']!=base.digest(base.tree_value(tree)) or seed['tree_sha256']!=common['tree_sha256']:
        raise ValueError('Original cohort hierarchy topology differs')


def prepare_case(manifest,case_id,output):
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.sparse_seed import SparseSeedCatalog,sparse_domain_digest,replay_sparse_seed,SeedInfeasible
    from timecut5.deployable import iter_constructive_seed_candidates
    from timecut5.provenance import primitive
    started=time.monotonic_ns();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    directory,bindings=manifest['input_directory'],manifest['inputs'];spec=SPECS[case_id]
    query,sites,_=extract_case(directory,case_id,bindings);historical=base.digest(query)
    make=lambda q:domain_factory(manifest,q,sites,output/'native',method=spec['method_order'][0],case_id=case_id)
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


def progress_binding(manifest,method,case_id,common):
    inner,sources=projection.progress_binding(manifest,INNER_ARM,common)
    policy=[SCHEMA,method,manifest['shared_configuration'],SPECS[case_id],METHOD_POLICY,base.digest(manifest)]
    return base.digest([inner,*policy]),dict(sources,cohort_method=base.digest(policy))


def validate_singleton_statistics(value,method,*,completed):
    if method=='hier':
        if value is not None:raise ValueError('HIER unexpectedly used FLAT singleton adapter')
        return
    names={'schema','runtime_enabled','calls','original_none','active_calls','disabled_calls','strengthened_calls'}
    if (type(value) is not dict or set(value)!=names or value['schema']!=POLICY_SCHEMA or value['runtime_enabled'] is not True or
        any(type(value[n]) is not int or value[n]<0 for n in names-{'schema','runtime_enabled'})):
        raise ValueError('FLAT singleton statistics differ')
    if completed and (value['calls']!=value['original_none']+value['active_calls']+value['disabled_calls'] or
        value['strengthened_calls']>value['active_calls']):raise ValueError('Completed singleton counts do not conserve')


def read_progress(path,manifest,method,case_id,common,*,search_status,completed_result=None):
    path=Path(path);value,raw_sha,size=envelope.read_bounded_json(path)
    inner,inner_sha,_=envelope.read_bounded_json(path.parent.parent/'remaining_charge_admission.json')
    outer,outer_sha,_=envelope.read_bounded_json(path.parent.parent/'method_admission.json')
    spec=SPECS[case_id];config=manifest['shared_configuration'];digest=base.digest(manifest)
    if base.canonical(outer)!=base.canonical(method_admission(digest,method,config,spec,inner_sha)):
        raise ValueError('Outer cohort method admission differs')
    domain,sources=progress_binding(manifest,method,case_id,common)
    if (value.get('cohort_schema')!=SCHEMA or value.get('method')!=method or value.get('case_binding_sha256')!=base.digest(spec) or
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
        projection.validate_support_statistics(row.get('projection_support_statistics'),INNER_ARM,completed=completed)
        envelope.validate_envelope_statistics(row.get('envelope_sweep_statistics'),sweep_arm,completed=completed)
        validate_singleton_statistics(row.get('singleton_bound_statistics'),method,completed=completed)
    counters(value,False)
    if search_status not in ('SUCCESS','TIMEOUT'):raise ValueError('Method receipt outcome not admitted')
    healthy=False
    if search_status=='SUCCESS':
        result=completed_result
        if type(result) is not dict:raise ValueError('Authenticated method result required')
        final=result.get('observer',{})
        if (result.get('schema')!=SCHEMA or result.get('strategy')!=method or result.get('method')!=method or
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
            ('projection_support_statistics','envelope_sweep_statistics','singleton_bound_statistics')):
            raise ValueError('Authenticated operator statistics differ')
        counters(result,True);healthy=True
    return dict(sha256=raw_sha,bytes=size,status=value['status'],method_admission_sha256=outer_sha,
        remaining_charge_admission_sha256=inner_sha,remaining_charge_activation_diagnostic=inner.get('diagnostic'),
        projection_support_statistics=value['projection_support_statistics'],envelope_sweep_statistics=value['envelope_sweep_statistics'],
        singleton_bound_statistics=value['singleton_bound_statistics'],sampled_wall_ns=value['sampled_wall_ns'],last_active_stack=value['active_stack'],
        maximum_observed_write_gap_ns=value['maximum_observed_write_gap_ns'],timeout_snapshot_is_censored=search_status=='TIMEOUT',
        terminal_observer_health_proved=healthy)


def validate_terminal(completed,full,method,expected_hmax):
    exact=completed.get('result');payload=exact.get('result') if type(exact) is dict else None
    statuses={'attained_optimum':('attained_optimum',),'infimum_unattained':('primary_unattained','secondary_unattained')}
    if (completed.get('method')!=method or completed.get('strategy')!=method or completed.get('status') not in statuses or
        type(payload) is not dict or payload.get('status') not in statuses[completed['status']]):
        raise ValueError('Missing or mis-tagged exact method terminal payload')
    if (full.get('method')!=method or completed['accepted_key']!=full['accepted_key'] or completed['status']!=full['status'] or
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
    ledger=base._run_plan(path,sha256,output,cpu,scope='full_batch',manifest_loader=_manifest,
        worker_module='experiments.dev_cohort_v1.run',fixed_cases=CASES,fixed_pairs=PAIRS,exact_phase_seconds=240)
    # Early stop never removes slots. Preserve original receipts/outcomes and
    # distinguish unattempted dependent stages from attempted failures.
    for row in ledger['stages']:
        if row['status']=='PENDING':row.update(status='BLOCKED_EXECUTION_STOPPED',reason=ledger['status'])
    for arm in ledger['arms']:
        if arm['status']=='PENDING':arm['status']='BLOCKED_EXECUTION_STOPPED'
    ledger.update(scope='known_dev_paired_cohort_v1',operational_admission=False,all_pairs_authenticated_complete=False,
        case_outcomes={},admission_errors=[],completion_outcome='incomplete_or_blocked')
    try:
        if ledger['denominator']!=15 or len(ledger['stages'])!=15 or len(ledger['arms'])!=6:
            raise ValueError('Fixed fifteen-slot denominator differs')
        expected_arms=[(case,method,index) for index,(case,order) in enumerate(PAIRS) for method in order]
        if any(type(a.get('pair')) is not int for a in ledger['arms']):raise ValueError('Exact pair indices required')
        if [(a.get('case'),a.get('strategy'),a.get('pair')) for a in ledger['arms']]!=expected_arms:raise ValueError('Fixed cohort arm order differs')
        def stage(position,identifier,operation,case,method,receipt,allowed):
            if receipt.get('status') not in allowed or not receipt.get('cleanup_verified'):raise ValueError('Unadmitted receipt/cleanup: '+identifier)
            expected=dict(id=identifier,operation=operation,case=case,status=receipt['status'])
            if method is not None:expected['strategy']=method
            if ledger['stages'][position]!=expected:raise ValueError('Stage/receipt identity differs: '+identifier)
        common={}
        for i,case in enumerate(CASES):
            receipt=ledger['common'].get(case,{})
            ledger['case_outcomes'][case]=dict(operational_admission=False,both_authenticated_complete=False,status='blocked_or_inconclusive')
            try:
                stage(i,'prepare-'+case,'prepare',case,None,receipt,('SUCCESS',))
                prepared=base.load_worker_result(output/('prepare-'+case),receipt,'prepare',case)
                validate_common(prepared,case,manifest);common[case]=prepared
            except (ValueError,KeyError,TypeError,OSError) as exc:
                ledger['case_outcomes'][case]['blocked_reason']='common_preparation_not_admitted: '+str(exc)
                ledger['admission_errors'].append(dict(case=case,stage='prepare',error=str(exc)))
                try:ledger['case_outcomes'][case]['preparation_blocked_diagnostic']=blocked_preparation_diagnostic(output/('prepare-'+case),case)
                except (ValueError,KeyError,TypeError,OSError):pass
        payloads={};admitted={}
        for i,arm in enumerate(ledger['arms']):
            case,method=arm['case'],arm['strategy'];arm['authenticated_completion']=False;arm['operational_admission']=False
            if case not in common:continue
            try:
                search,verify=arm['receipt'],arm['verification']
                stage(3+2*i,'search-'+str(i),'search',case,method,search,('SUCCESS','TIMEOUT'))
                stage(4+2*i,'verify-'+str(i),'verify',case,method,verify,('SUCCESS',));require_exact_phase(search)
                identity=search.get('phase_budget',{}).get('identity',{})
                if (identity.get('case_id')!=case or identity.get('strategy')!=method or identity.get('arm_index')!=str(i) or
                    identity.get('manifest_sha256')!=sha256 or identity.get('source_closure_sha256')!=manifest['source']['closure_sha256']):
                    raise ValueError('Method phase identity differs')
                full=base.load_worker_result(output/f'verify-{i:02d}',verify,'verify',case,method)
                if arm['status']!=full['status'] or full.get('method')!=method or full.get('case_binding_sha256')!=base.digest(SPECS[case]):
                    raise ValueError('Fresh verifier method/case outcome differs')
                completed=None
                if search['status']=='SUCCESS':
                    completed=base.load_worker_result(output/f'arm-{i:02d}',search,'arm',case,method)
                    payloads[(case,method)]=validate_terminal(completed,full,method,common[case]['seed']['max_depth'])
                elif full.get('search_status')!='TIMEOUT' or full['status']!='timeout_feasible_only':
                    raise ValueError('Timeout verifier claims more than feasible evidence')
                arm['progress']=read_progress(output/f'arm-{i:02d}/artifacts/arm/progress/progress.json',manifest,method,case,common[case],
                    search_status=search['status'],completed_result=completed)
                arm['authenticated_completion']=search['status']=='SUCCESS'
                arm['operational_admission']=True;admitted[(case,method)]=arm['authenticated_completion']
            except (ValueError,KeyError,TypeError,OSError) as exc:
                arm['admission_error']=str(exc);ledger['admission_errors'].append(dict(case=case,method=method,error=str(exc)))
        for case in CASES:
            outcome=ledger['case_outcomes'][case]
            if all((case,m) in admitted for m in METHODS):
                outcome.update(operational_admission=True,status='operational_feasible_evidence')
                if all(admitted[(case,m)] for m in METHODS):
                    if payloads[(case,'flat')]!=payloads[(case,'hier')]:
                        outcome.update(operational_admission=False,status='completed_exact_disagreement')
                        ledger['admission_errors'].append(dict(case=case,error='Completed FLAT/HIER answers disagree'))
                    else:outcome.update(both_authenticated_complete=True,status='both_authenticated_complete')
        ledger['operational_admission']=ledger['status']=='COMPLETED' and all(x['operational_admission'] for x in ledger['case_outcomes'].values())
        ledger['all_pairs_authenticated_complete']=ledger['operational_admission'] and all(x['both_authenticated_complete'] for x in ledger['case_outcomes'].values())
        if ledger['all_pairs_authenticated_complete']:ledger['completion_outcome']='all_three_pairs_authenticated_complete'
        elif ledger['operational_admission']:ledger['completion_outcome']='operational_partial_or_timeouts'
    except (ValueError,KeyError,TypeError,OSError) as exc:ledger['admission_errors'].append(dict(error=str(exc)))
    temporary=output/'ledger.tmp';temporary.write_bytes(base.canonical(ledger));os.replace(temporary,output/'ledger.json')
    return ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--freeze',action='store_true');mode.add_argument('--gate',action='store_true')
    mode.add_argument('--worker',choices=('prepare','arm','verify'))
    for name in ('manifest','manifest-sha256','output','input-directory','common','common-sha256','search-directory','search-receipt-sha256'):
        parser.add_argument('--'+name)
    parser.add_argument('--cpu',type=int);parser.add_argument('--case',choices=CASES);parser.add_argument('--strategy',choices=METHODS)
    parser.add_argument('--envelope-sweep',choices=('off',))
    args=parser.parse_args()
    if args.plan:print(json.dumps(prospective(False),indent=2,sort_keys=True));return 0
    if args.freeze:
        if not args.output or not args.input_directory or args.envelope_sweep is None:parser.error('Freeze requires output, input directory and explicit envelope choice')
        manifest=prospective(args.envelope_sweep=='on');root=Path.cwd().resolve();compiler=Path(shutil.which('g++')).resolve()
        manifest.update(launchable=True,status='frozen_known_dev_cohort_not_launched',repo=str(root),input_directory=str(Path(args.input_directory).resolve()),
            compiler=dict(path=str(compiler),sha256=base.file_hash(compiler),version=subprocess.check_output([str(compiler),'--version'],text=True),flags=['-O3','-std=c++17']),source=source_identity(root))
        raw=base.canonical(manifest)
        with Path(args.output).open('xb') as stream:stream.write(raw)
        digest=hashlib.sha256(raw).hexdigest();_manifest(args.output,digest);print(json.dumps(dict(manifest=str(Path(args.output).resolve()),sha256=digest)));return 0
    if args.envelope_sweep is not None:parser.error('Runtime configuration is frozen in the manifest')
    if args.gate:
        if args.output is None or args.cpu is None or args.case is not None or args.strategy is not None:parser.error('Fixed cohort gate requires output/cpu only')
        return 0 if run_gate(args.manifest,args.manifest_sha256,args.output,args.cpu)['operational_admission'] else 1
    manifest=_manifest(args.manifest,args.manifest_sha256)
    if args.case is None or (args.worker!='prepare' and args.strategy is None):parser.error('Worker requires case and method')
    if args.worker=='prepare':prepare_case(manifest,args.case,Path(os.environ['HIROUTE_OUTPUT_DIR'])/'prepared')
    else:
        common=json.loads(Path(args.common).read_bytes());validate_common(common,args.case,manifest)
        if args.worker=='verify':
            from experiments.mechanism_recovery_v1.supervisor import read_result
            require_exact_phase(read_result(args.search_directory))
        factory=lambda m,q,s,c:domain_factory(m,q,s,c,method=args.strategy,case_id=args.case)
        base.worker(manifest,args.worker,args.case,args.common,args.common_sha256,args.strategy,args.search_directory,args.search_receipt_sha256,domain_factory=factory)
    _manifest(args.manifest,args.manifest_sha256)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(base.canonical(dict(status='COMPLETED',result=base.result_envelope(
        os.environ['HIROUTE_OUTPUT_DIR'],args.worker,args.case,args.strategy))))
    return 0


if __name__=='__main__':sys.exit(main())
