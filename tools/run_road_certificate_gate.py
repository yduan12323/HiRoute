"""Frozen tiny certificate checker gate; never a real table producer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from road_certificate_fixtures import IDS,fixture,raw
from exact_leg_table import ExactLegTable
from exact_road_certificate import ExactRoadGraph,CertificateSession,Unsupported

ROOT=Path(__file__).resolve().parents[1]

def atomic(path,value):
    tmp=path.with_suffix('.tmp')
    with tmp.open('w') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    tmp.replace(path)

def source():
    return dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()))

def freeze_config():
    p=ROOT/'configs/road_certificate_gate.json';c=json.loads(p.read_text())
    if (c['stage_cap_CPU_s']!=600 or c['case_denominator']!=15 or c['case_ids']!=list(IDS) or
        c['real_table_generation'] is not False or c['real_scale_optimization'] is not False or c['holdout'] is not False):
        raise ValueError('frozen checker gate identity/coverage/scope')
    return c,hashlib.sha256(p.read_bytes()).hexdigest()

def materialize(f,path):
    path.mkdir(exist_ok=False)
    if 'unsupported_graph' in f:
        (path/'graph.json').write_bytes(raw(f['unsupported_graph']))
    else:
        b=f['bundle'];(path/'graph.json').write_bytes(raw(b['graph_payload']))
        (path/'table.json').write_bytes(raw(b['table_payload']))
        for i,c in enumerate(b['certificates']):(path/f'source-{i:04}.json').write_bytes(raw(c))
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.iterdir())}

def evaluate_saved(path):
    """Check the actual saved bytes, not the generator's in-memory answers."""
    try:
        graph=ExactRoadGraph.from_bytes((path/'graph.json').read_bytes())
        if not (path/'table.json').exists():return dict(status='incorrectly_accepted_unsupported')
        table=ExactLegTable.from_bytes((path/'table.json').read_bytes())
        session=CertificateSession(graph,table)
        for file in sorted(path.glob('source-*.json')):session.check_source(file.read_bytes())
        checked=session.finish();example=table.pairs[table.origin_anchor,table.destination_anchor]
        return dict(status='verified',checked_pairs=checked.checked_pairs,literal_sites=checked.literal_sites,
            physical_sources=len(table.sources),physical_targets=len(table.targets),
            zero_pairs=sum(r['zero_pairs'] for r in checked.source_receipts),
            graph_sha256=checked.graph_sha256,table_sha256=checked.table_sha256,
            graph_nodes=len(graph.nodes),graph_edges=len(graph.edges),owns_exact_inputs=checked.is_for(graph,table),
            scope='exact supplied synthetic graph/table only',source_receipts=[dict(r) for r in checked.source_receipts],
            selected_example=dict(nodes=example.nodes,edges=example.edges,actual_length=str(example.length)))
    except Unsupported as exc:return dict(status='unsupported',reason=str(exc))
    except (ValueError,TypeError) as exc:return dict(status='rejected',reason=str(exc))


def run(output):
    cfg,cfgsha=freeze_config();src=source()
    if src['dirty']:raise ValueError('commit gate source before checking')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();cpu=time.process_time()
    result=dict(schema='hiroute.road_certificate_results.v1',source=src,config_sha256=cfgsha,
        scope='supplied synthetic tiny graph/table certificates only',case_denominator=15,
        rows=[dict(case=name,status='unrun') for name in IDS],
        real_table_generation=False,real_scale_optimization=False,holdout=False,production_oracle=False,
        original_taskbook_complete=False)
    atomic(out/'started.json',dict(pid=os.getpid(),source=src,config_sha256=cfgsha));atomic(out/'results.json',result)
    for row in result['rows']:
        row.update(status='started');atomic(out/'results.json',result)
        try:
            f=fixture(row['case']);hashes=materialize(f,out/row['case']);actual=evaluate_saved(out/row['case'])
            row.update(status='verified' if actual['status']==f['expected'] else 'semantic_mismatch',
                expected=f['expected'],actual=actual,input_sha256=hashes)
        except BaseException as exc:row.update(status='error',error=repr(exc))
        atomic(out/'results.json',result)
        if row['status']!='verified':break
    if source()!=src:result['source_consistency_error']=True
    result.update(cpu_s=time.process_time()-cpu,wall_s=time.monotonic()-started,
        gate_status='PASS_TINY_CERTIFICATE_CHECKER' if all(r['status']=='verified' for r in result['rows']) and not result.get('source_consistency_error') else 'LIMITED_OR_FAILED')
    atomic(out/'results.json',result);print(json.dumps(result,indent=2))
    return 0 if result['gate_status']=='PASS_TINY_CERTIFICATE_CHECKER' else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args();raise SystemExit(run(a.output))
