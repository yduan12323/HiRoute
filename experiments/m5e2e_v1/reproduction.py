"""Canonical content comparison; paths/timestamps are not mathematical identity."""
import hashlib
from pathlib import Path
from .common import canonical, load, digest


def _value(value):
    if isinstance(value,float):return {'binary64':value.hex()}
    if isinstance(value,dict):return {k:_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_value(v) for v in value]
    if hasattr(value,'isoformat'):return {'iso':value.isoformat()}
    return value


def canonical_parquet(path):
    import pyarrow.parquet as pq
    f=pq.ParquetFile(path); names=sorted(f.schema_arrow.names)
    h=hashlib.sha256();h.update(canonical(names))
    for batch in f.iter_batches(batch_size=8192,columns=names,use_threads=False):
        for row in batch.to_pylist():h.update(canonical(_value(row))+b'\n')
    return h.hexdigest()


def _snapshot(root):
    p=load(root/'preflight.json')
    prepared=load(root/'prepare-invocation/artifacts/prepared.json')
    cases=load(root/'freeze-invocation/artifacts/cases.json')['cases']
    graph=Path(prepared['graph_directory'])
    model=dict(source=p['source']['commit'],config=p['config_sha256'],
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


def compare_builds(a,b):
    if a.resolve()==b.resolve():raise ValueError('Two distinct clean build roots required')
    try:
        pa,ma,oa=_snapshot(a);pb,mb,ob=_snapshot(b)
    except FileNotFoundError as exc:
        return dict(status='REPRODUCTION_INCOMPLETE',reason=str(exc))
    different_environment=pa['environment']['executable']!=pb['environment']['executable']
    complete = (len(oa)==len(ob)==9 and all(r.get('operation_status')=='SUCCESS'
        and r.get('outcome') is not None for r in oa+ob))
    installs = (pa.get('installation')==pb.get('installation') and
        'error' not in pa.get('installation',{'error':'missing'}) and bool(pa.get('installation')))
    distinct_sources=pa['source']['path']!=pb['source']['path']
    equal=ma==mb and oa==ob and different_environment and complete and installs and distinct_sources
    return dict(status='MATCH' if equal else 'MISMATCH',
        model_equal=ma==mb,mathematical_outcomes_equal=oa==ob,
        distinct_environment_executables=different_environment, complete_mathematical_results=complete,
        installed_sources_and_dependencies_equal=installs, distinct_source_workspaces=distinct_sources,
        model_a_sha256=digest(ma),model_b_sha256=digest(mb),
        reproduction_scope='clean_environment_same_host',
        note='No second-host claim; generation provenance and isolated roots must also be verified.')
