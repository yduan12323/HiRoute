"""One frozen tiny semantic cell with durable started and terminal receipts."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import time
from fractions import Fraction

from exact_physical_adapter import solve,replay,relevant_depth
from exact_physical_fixtures import IDS,case,tiny_table,legacy_snapshot,semantics

ROOT=Path(__file__).resolve().parents[1]

def convert(v):
    if isinstance(v,Fraction):return str(v)
    if isinstance(v,dict):return {k:convert(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [convert(x) for x in v]
    return v

def atomic(path,value):
    tmp=path.with_suffix('.tmp')
    with tmp.open('w') as stream:
        json.dump(convert(value),stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    tmp.replace(path)

def source():
    return dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()))

def config():
    p=ROOT/'configs/exact_physical_gate.json';cfg=json.loads(p.read_text())
    if (cfg['case_denominator']!=8 or cfg['case_ids']!=list(IDS) or cfg['stage_cap_CPU_s']!=900 or
        cfg['real_road_generation'] is not False or cfg['real_scale_solves'] is not False or cfg['holdout'] is not False):
        raise ValueError('frozen tiny physical gate identity/coverage')
    if importlib.metadata.version('z3-solver')!=cfg['z3_solver_distribution']:raise ValueError('pinned Z3 runtime')
    return cfg,hashlib.sha256(p.read_bytes()).hexdigest()

def run(name,output):
    cfg,cfg_sha=config();src=source()
    if src['dirty']:raise ValueError('commit run source before gate')
    if name not in cfg['case_ids']:raise ValueError('outside frozen eight cells')
    out=Path(output);out.mkdir(exist_ok=False,parents=True)
    atomic(out/'started.json',dict(case=name,pid=os.getpid(),source=src,config_sha256=cfg_sha))
    started=time.monotonic();cpu=time.process_time();result=dict(case=name,source=src,config_sha256=cfg_sha,status='error')
    try:
        fixture=case(name);table,raw,cert=tiny_table(fixture)
        (out/'tiny-table.json').write_bytes(raw);atomic(out/'input.json',fixture);atomic(out/'tiny-road-certificate.json',cert)
        depth,upper=relevant_depth(table,fixture['physics'],fixture['upper_witness'])
        legacy=legacy_snapshot(fixture);seed_cross=False;witness_cross=False
        if legacy is not None:
            from tiny_smt import replay as independent_old_replay
            w=fixture['upper_witness'];old=independent_old_replay(legacy,tuple(tuple(a) for a in w['plan']),w['charges'],w['initial_wait'])
            if old['key']!=upper['key']:raise ValueError('separate seed replay mismatch')
            seed_cross=True
        solved=solve(table,fixture['physics'],fixture['upper_witness'],out/'SMT',cfg['case_query_wall_s'])
        actual=semantics(solved)
        if solved['status']=='attained_optimum' and legacy is not None:
            w=solved['witness'];old=independent_old_replay(legacy,tuple(tuple(a) for a in w['plan']),w['charges'],w['initial_wait'])
            if old['key']!=solved['key']:raise ValueError('separate final witness replay mismatch')
            witness_cross=True
        if source()!=src:raise ValueError('source changed within cell')
        result.update(status='verified' if actual==fixture['expected'] else 'semantic_mismatch_or_unknown',
            expected=fixture['expected'],actual=actual,result=solved,derived_depth=depth,certificate=cert,
            separate_seed_replay=seed_cross,separate_final_replay=witness_cross,
            production_optimizer_called=False,real_road_generation=False,real_scale_solve=False,holdout=False)
    except BaseException as exc:result.update(error=repr(exc))
    result.update(cpu_s=time.process_time()-cpu,wall_s=time.monotonic()-started)
    atomic(out/'receipt.json',result);print(json.dumps(convert(result),indent=2))
    return 0 if result['status']=='verified' else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=IDS,required=True);p.add_argument('--output',required=True)
    args=p.parse_args();raise SystemExit(run(args.case,args.output))
