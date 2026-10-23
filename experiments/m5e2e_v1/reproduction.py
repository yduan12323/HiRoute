"""Canonical content comparison; paths/timestamps are not mathematical identity."""
import hashlib
from pathlib import Path
from .common import canonical, load, digest


CANONICALIZATION_SCHEMA = 'hiroute.report_canonicalization.v2'


def _value(value):
    if isinstance(value, bytes):
        return {'binary_bytes_hex': value.hex()}
    if isinstance(value, float):
        return {'binary64': value.hex()}
    if isinstance(value, dict):
        return {'mapping': {k: _value(v) for k, v in value.items()}}
    if isinstance(value, tuple):
        return {'tuple': [_value(v) for v in value]}
    if isinstance(value, list):
        return [_value(v) for v in value]
    if hasattr(value, 'isoformat'):
        return {'iso': value.isoformat()}
    return value


def canonical_parquet(path):
    import pyarrow.parquet as pq
    f=pq.ParquetFile(path); names=sorted(f.schema_arrow.names)
    h=hashlib.sha256();h.update(canonical({'schema':CANONICALIZATION_SCHEMA,'columns':names}))
    for batch in f.iter_batches(batch_size=8192,columns=names,use_threads=False):
        for row in batch.to_pylist():h.update(canonical(_value(row))+b'\n')
    return h.hexdigest()


def _snapshot(root):
    p=load(root/'preflight.json')
    prepared=load(root/'prepare-invocation/artifacts/prepared.json')
    cases=load(root/'freeze-invocation/artifacts/cases.json')['cases']
    graph=Path(prepared['graph_directory'])
    model=dict(canonicalization_schema=CANONICALIZATION_SCHEMA,source=p['source']['commit'],config=p['config_sha256'],
        raw=prepared['raw_report'],
        graph={k:canonical_parquet(graph/(k+'.parquet')) for k in ('nodes','edges')},
        sites=canonical_parquet(prepared['sites_path']),
        hierarchy=digest(load(prepared['hierarchy_path'])),cases=[])
    for case in cases:
        row=dict(case_id=case['case_id'],status=case['status'])
        if case['status']=='READY':
            table=load(case['legs_path'])
            # Serialized parquet container hashes may differ; normalized physical
            # graph and hierarchy identities replace only these provenance fields.
            table['source_sha256']=model['graph']
            table['hierarchy_sha256']=model['hierarchy']
            table.pop('selection_certificate_sha256',None)
            row.update(query=load(case['query_path']),legs=table,
                       candidate_ids=case['domain_binding']['candidate_site_ids'])
        model['cases'].append(row)
    outcomes=[]
    for slot in load(root/'method_slots.json')['slots']:
        if slot.get('result_path'):
            r=load(slot['result_path'])
            outcomes.append(dict(case_id=slot['case_id'],method=slot['method'],
                operation_status=r['operation_status'],outcome=r['canonical_outcome']))
        else:outcomes.append(dict(case_id=slot['case_id'],method=slot['method'],operation_status=slot['operation_status']))
    return p,model,outcomes


def compare_builds(a, b):
    if a.resolve() == b.resolve():
        raise ValueError('Two distinct clean build roots required')
    try:
        pa, ma, oa = _snapshot(a)
        pb, mb, ob = _snapshot(b)
    except FileNotFoundError as exc:
        return dict(status='INCOMPLETE', reason=str(exc),
                    canonicalization_schema=CANONICALIZATION_SCHEMA)

    map_a = {(r['case_id'], r['method']): r for r in oa}
    map_b = {(r['case_id'], r['method']): r for r in ob}
    common_keys = sorted(set(map_a) & set(map_b))
    comparable = [k for k in common_keys
                  if map_a[k].get('operation_status') == 'SUCCESS'
                  and map_b[k].get('operation_status') == 'SUCCESS'
                  and map_a[k].get('outcome') is not None
                  and map_b[k].get('outcome') is not None]
    conflicts = [dict(case_id=k[0], method=k[1],
                      outcome_a=map_a[k]['outcome'], outcome_b=map_b[k]['outcome'])
                 for k in comparable if map_a[k]['outcome'] != map_b[k]['outcome']]
    outcomes_equal = None if not comparable else not conflicts
    complete = (len(map_a) == len(map_b) == 9
                and set(map_a) == set(map_b)
                and all(r.get('operation_status') == 'SUCCESS'
                        and r.get('outcome') is not None for r in oa + ob))
    model_equal = ma == mb
    different_environment = pa['environment']['executable'] != pb['environment']['executable']
    installs = (pa.get('installation') == pb.get('installation')
                and 'error' not in pa.get('installation', {'error': 'missing'})
                and bool(pa.get('installation')))
    distinct_sources = pa['source']['path'] != pb['source']['path']
    environment_identity_ok = different_environment and installs and distinct_sources

    if not model_equal:
        status = 'REPRODUCTION_MISMATCH'
    elif conflicts:
        status = 'CORRECTNESS_FAILED'
    elif not complete:
        status = 'INCOMPLETE'
    elif not environment_identity_ok:
        status = 'REPRODUCTION_MISMATCH'
    else:
        status = 'MATCH'

    missing_a = sorted((k[0], k[1]) for k, r in map_a.items()
                       if r.get('operation_status') != 'SUCCESS' or r.get('outcome') is None)
    missing_b = sorted((k[0], k[1]) for k, r in map_b.items()
                       if r.get('operation_status') != 'SUCCESS' or r.get('outcome') is None)
    return dict(status=status, canonicalization_schema=CANONICALIZATION_SCHEMA,
        model_equal=model_equal, mathematical_outcomes_equal=outcomes_equal,
        comparable_successful_result_count=len(comparable), outcome_conflicts=conflicts,
        complete_mathematical_results=complete,
        missing_result_slots_a=missing_a, missing_result_slots_b=missing_b,
        distinct_environment_executables=different_environment,
        installed_sources_and_dependencies_equal=installs,
        distinct_source_workspaces=distinct_sources,
        environment_identity_ok=environment_identity_ok,
        model_a_sha256=digest(ma), model_b_sha256=digest(mb),
        reproduction_scope='clean_environment_same_host',
        note='Timeouts or missing results yield INCOMPLETE; they do not imply mathematical disagreement. Model identity and conflicts among paired successful outcomes remain explicit.')
