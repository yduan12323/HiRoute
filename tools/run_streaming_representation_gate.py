"""Prospectively bounded representation gate. No real source tree or optimizer."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from streaming_road_graph import build,validate,sha,Unsupported
from streaming_road_fixtures import evaluate,analytic_wide
from road_certificate_fixtures import IDS,fixture,evaluate as reference
from preflight_real_road_certificate import validate_domain


def save(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w') as s:
        json.dump(value,s,indent=2,sort_keys=True);s.write('\n');s.flush()
        import os
        os.fsync(s.fileno())
    temporary.replace(path)


def source():
    return dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True)),python=sys.version)


def decision(function):
    try:return function()
    except Unsupported as exc:return dict(status='unsupported',reason=str(exc))
    except (ValueError,TypeError) as exc:return dict(status='rejected',reason=str(exc))


def frozen(config,path):
    if sha(path)!=config['frozen_domain_sha256']:raise ValueError('original full frozen domain changed')
    f=json.loads(Path(path).read_text());S,T=validate_domain(f)
    if f['candidate_domain_sha256']!=config['candidate_domain_sha256'] or f['expected_input_sha256']['graph']!=config['raw_graph_sha256']:
        raise ValueError('full input/domain identity mismatch')
    for name in ('config','preflight'):
        if sha(f[name+'_path'])!=f[name+'_sha256']:raise ValueError('physical/config input changed')
    for name in ('bindings','catalog'):
        if sha(f['input_paths'][name])!=f['expected_input_sha256'][name]:raise ValueError('frozen Site input changed')
    return f,S,T


def run(args):
    c=json.loads(Path(args.config).read_text());out=Path(args.output);out.mkdir(exist_ok=False)
    start=dict(mode=args.mode,started_at=time.time(),source=source(),config_sha256=sha(args.config),source_generation=False,real_optimizer=False,holdout=False)
    if start['source']['dirty']:raise ValueError('commit settled producer before a formal run')
    save(out/'started.json',start);cpu=time.process_time();wall=time.monotonic()
    result=dict(started=start,mode=args.mode,source_generation=False,real_optimizer=False,holdout=False,whole_road_table_certified=False,upper_witness_replayed=False)
    if args.mode=='tiny':
        names=[*IDS,'analytic_N64_65bit']
        if c['tiny_case_ids']!=names or c['tiny_denominator']!=len(names):raise ValueError('full frozen tiny coverage required')
        rows=[dict(case=n,status='unrun') for n in names];result.update(case_denominator=len(names),rows=rows)
        save(out/'results.json',result)
        for i,name in enumerate(names):
            f=analytic_wide() if name=='analytic_N64_65bit' else fixture(name)
            rows[i].update(status='started');save(out/'results.json',result)
            old=decision(lambda:reference(f));new=decision(lambda:evaluate(f,out/name))
            rows[i].update(expected=f['expected'],reference=old,streaming=new,status='matched' if old['status']==new['status']==f['expected'] else 'mismatch')
            save(out/'results.json',result)
            if rows[i]['status']!='matched':break
        result['decision']='PASS_TINY_COMPONENT_ONLY' if all(r['status']=='matched' for r in rows) else 'FAILED_OR_INCOMPLETE'
    else:
        f,S,T=frozen(c,args.frozen_domain);raw=f['input_paths']['graph']
        if shutil.disk_usage(out).free<c['full_admission_free_disk_bytes']:raise ValueError('complete representation disk admission failed')
        result.update(query='WD01/E18/schedule/N64',candidate_domain_sha256=f['candidate_domain_sha256'],literal_sites=64,
            source_denominator=65,pair_denominator=4225,source_status_counts=dict(unrun_source_generation_not_admitted=65),
            pair_status_counts=dict(unrun_source_generation_not_admitted=4225))
        if args.mode=='build':
            result['construction']=build(raw,out/'road.sqlite',expected_raw_sha=c['raw_graph_sha256'],max_bytes=c['max_graph_DB_bytes'],progress=lambda v:save(out/'progress.json',v))
            result['decision']='CONSTRUCTED_UNTRUSTED_NOT_CERTIFIED'
        else:
            built=Path(args.graph_DB)
            g=validate(raw,built,out/'identity-validation',expected_raw_sha=c['raw_graph_sha256'],max_tracking_bytes=c['max_tracking_DB_bytes'],progress=lambda v:save(out/'progress.json',v))
            try:
                if g.edge_count!=c['expected_frozen_edge_rows'] or not all(g.has_node(v) for v in set(S)|set(T)):
                    raise ValueError('full graph/domain cardinality or anchors lost')
                result.update(decision='PASS_FULL_REPRESENTATION_IDENTITY_ONLY',graph_identity=g.payload_sha256,
                    representation_sha256=g.representation_sha256,raw_graph_sha256=g.raw_sha256,
                    independently_counted_nodes=g.node_count,independently_counted_edges=g.edge_count,
                    all_source_terminal_anchors_present=True,graph_DB_bytes=built.stat().st_size,
                    node_identity_bijection_checked=True,edge_identity_bijection_checked=True,global_edge_ID_uniqueness_checked=True,
                    integer_weight_or_path_width_assumed=False,SQLite_heap_limit_bytes=134217728,SQLite_cache_per_connection_bytes=16384*1024,mmap_bytes=0)
            finally:g.close()
    result.update(body_CPU_s=time.process_time()-cpu,body_wall_s=time.monotonic()-wall)
    result['final_source']=source()
    if result['final_source']!=start['source']:result['source_consistency_error']=True
    save(out/'results.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    return 0 if result['decision'] not in ('FAILED_OR_INCOMPLETE',) and not result.get('source_consistency_error') else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=('tiny','build','validate'),required=True)
    p.add_argument('--config',default='configs/streaming_road_representation.json');p.add_argument('--output',required=True)
    p.add_argument('--frozen-domain');p.add_argument('--graph-DB');a=p.parse_args()
    try:code=run(a)
    except BaseException as exc:
        out=Path(a.output)
        if out.exists():save(out/'failure.json',dict(error=repr(exc),source_generation=False,whole_road_table_certified=False))
        raise
    raise SystemExit(code)
