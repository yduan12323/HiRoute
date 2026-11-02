"""One check-only diagnostic on the preserved frozen synthetic4096 input.

Never calls a generator/packer. No real-data path argument or scan admission.
"""
import argparse
import json
from pathlib import Path
import time

from streaming_road_graph import sha,validate
from streaming_road_certificate import read_source_unit,SourceSession
from run_packed_source_feasibility import IDS,save


def run(root,expected_matrix_sha,out,source_commit):
    root=Path(root);matrix=root/'results.json'
    if sha(matrix)!=expected_matrix_sha:raise ValueError('immutable prior matrix identity')
    original=json.loads(matrix.read_text())
    if [r['id'] for r in original['profiles']]!=list(IDS) or original.get('component_decision')!='PASS_SYNTHETIC_COMPONENT_ONLY':raise ValueError('original complete frozen synthetic profiles')
    if original.get('real_source') is not False or original.get('real_graph_scan') is not False:raise ValueError('synthetic-only artifact')
    old=original['profiles'][-1]
    if (old['nodes'],old['edges'],old['status'])!=(4096,16377,'INDEPENDENTLY_VERIFIED_SYNTHETIC'):raise ValueError('frozen complete scaling shape')
    folder=root/'scaling_4096';unit=folder/'unit-0';paths=unit/'paths.jsonl';cert=unit/'source.jsonl'
    previous=old['unit_receipts'][0]
    if sha(paths)!=previous['paths_sha256'] or sha(cert)!=previous['source_sha256']:raise ValueError('unchanged candidate bytes required')
    if (folder/'graph.tsv').stat().st_size>16*1024**2 or (folder/'nodes.jsonl').stat().st_size>1024**2 or (folder/'graph.sqlite').stat().st_size>32*1024**2:raise ValueError('synthetic input-size envelope; no real scan')
    out=Path(out);out.mkdir(exist_ok=False);result=dict(scope='synthetic check-only diagnostic, not a new end-to-end measurement',
        source_commit=source_commit,producer_commit=original['source_commit'],matrix_sha256=expected_matrix_sha,
        paths_sha256=previous['paths_sha256'],source_sha256=previous['source_sha256'],old_source_check=old['source_checks'][0],
        real_graph_scan=False,real_source=False,EV_solve=False,holdout=False,status='STARTED')
    save(out/'result.json',result);g=t=None;body_cpu=time.process_time();body_wall=time.monotonic()
    try:
        c,w=time.process_time(),time.monotonic();g=validate(folder/'graph.tsv',folder/'graph.sqlite',out/'graph-revalidation',nodes_path=folder/'nodes.jsonl')
        result['synthetic_graph_revalidation']=dict(CPU_s=time.process_time()-c,wall_s=time.monotonic()-w)
        if g.payload_sha256!=previous['independent_receipt']['graph_sha256']:raise ValueError('same authoritative synthetic graph')
        c,w=time.process_time(),time.monotonic();t=read_source_unit(paths,g,out/'table.sqlite')
        result['choice_query_plan']=t._db.execute('EXPLAIN QUERY PLAN SELECT t,v,eid FROM steps INDEXED BY steps_choice_lookup WHERE s=? AND u=? ORDER BY t COLLATE BINARY',('o','n00001')).fetchall()
        s=SourceSession(g,t);s.check_source(cert,out/'source-check');result['independent_receipt']=dict(s.finish())
        result['source_check']=dict(CPU_s=time.process_time()-c,wall_s=time.monotonic()-w)
        result['compiled_path_SQLite_bytes']=t.path.stat().st_size
        if sha(paths)!=result['paths_sha256'] or sha(cert)!=result['source_sha256']:raise ValueError('candidate input changed')
        result.update(status='INDEPENDENTLY_VERIFIED_SYNTHETIC',body_CPU_s=time.process_time()-body_cpu,body_wall_s=time.monotonic()-body_wall)
    except BaseException as exc:result.update(status='ERROR',error=repr(exc));save(out/'result.json',result);raise
    finally:
        if t is not None:t.close()
        if g is not None:g.close()
    save(out/'result.json',result);print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('matrix','matrix-sha','output','source-commit'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(a.matrix,a.matrix_sha,a.output,a.source_commit)
