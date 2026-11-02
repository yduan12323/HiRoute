"""Guarded construction-only probe; no real graph or planning optimization."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time

from exact_leg_fixtures import synthetic_payload
from exact_leg_table import ExactLegTable,GroundedLookup,dag_nodes

ROOT=Path(__file__).resolve().parents[1]


def atomic(path,value):
    path=Path(path);temporary=path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
        stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


def source():
    return dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        python=platform.python_version(),executable=sys.executable,platform=platform.platform())


def config(path):
    value=json.loads(Path(path).read_text())
    if (value['additional_cap_CPU_s']!=400 or value['parent_stage_cap_CPU_s']!=600 or
            value['workers']!=1 or value['threads']!=1 or not value['execution_authorized'] or
            value['probe_denominator']!=2 or value['solver_check_calls']!=0 or value['optimize_calls']!=0):
        raise ValueError('construction-only admission mismatch')
    return value


def preflight(args):
    cfg=config(args.config);src=source()
    if src['dirty']:raise ValueError('commit the run source before construction verification')
    if importlib.metadata.version('z3-solver')!=cfg['z3_solver_distribution']:
        raise ValueError('pinned installed Z3 distribution mismatch')
    import z3
    z3.set_param('parallel.enable',False)
    out=Path(args.output)
    if out.exists():raise ValueError('preflight already exists; inspect before reuse')
    if shutil.disk_usage(out.parent).free<2*1024**3:raise ValueError('disk headroom')
    # Host/process memory are checked by the external supervisor. This function
    # checks dependency/import/API readiness only and creates no full table/AST.
    atomic(out,dict(status='dependency_ready',source=src,config=cfg,
        z3_version=z3.get_version_string(),z3_distribution=importlib.metadata.version('z3-solver'),
        SMT_calls=0,real_road_queries=0,full_width_probe_started=False))
    print(json.dumps(dict(status='dependency_ready',source=src,z3=z3.get_version_string())))


def run(args):
    cfg=config(args.config);ready=json.loads(Path(args.preflight).read_text());src=source()
    if ready['config']!=cfg or ready['source']['commit']!=src['commit'] or src['dirty']:
        raise ValueError('within-run source/config changed since preflight')
    if importlib.metadata.version('z3-solver')!=cfg['z3_solver_distribution']:
        raise ValueError('installed runtime changed')
    row=next(p for p in cfg['probes'] if p['id']==args.probe)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    atomic(out/'started.json',dict(pid=os.getpid(),source=src,profile=row,
        scope='synthetic input/discrete-trace construction only',real_road_queries=0,SMT_calls=0))
    wall0,cpu0=time.monotonic(),time.process_time();last=0.;stage='starting'
    def check():
        nonlocal last
        now=time.monotonic()
        if now-wall0>cfg['command_wall_limit_s']:raise RuntimeError('construction wall guard')
        if now-last>.5:
            atomic(out/'progress.json',dict(stage=stage,elapsed_wall_s=now-wall0,cpu_s=time.process_time()-cpu0))
            last=now
    result=dict(source=src,profile=row,scope='synthetic input/discrete-trace component only',
        real_graph_loaded=False,real_table_generated=False,real_road_queries=0,
        physical_continuous_model_constructed=False,optimizer_integrated=False,
        charging_curve_constraints_constructed=False,SMT_calls=0,Optimize_calls=0,
        road_selection_certified=False,planning_optimality_claim=False)
    try:
        stage='synthetic_input';start=time.monotonic()
        payload=synthetic_payload(row['sites'],row['aliases'])
        raw=(json.dumps(payload,sort_keys=True,separators=(',',':'))+'\n').encode()
        (out/'synthetic-input.json').write_bytes(raw)
        result['input_generation_wall_s']=time.monotonic()-start
        stage='input_validation';start=time.monotonic();table=ExactLegTable.from_bytes(raw,check)
        result['input_validation_wall_s']=time.monotonic()-start
        if (len(table.candidate_order)!=row['sites'] or len(table.actions)!=row['actions'] or
                len(set(table.sources)|set(table.targets))!=row['physical_anchors'] or
                len(table.pairs)!=row['pairs']):raise ValueError('full-width profile not retained')
        stage='cold_z3_import';start=time.monotonic();import z3
        z3.set_param('parallel.enable',False)
        result['cold_z3_import_wall_s']=time.monotonic()-start
        calls=dict(Solver=0,SolverFor=0,Optimize=0)
        def forbidden(name):
            def invoke(*a,**kw):calls[name]+=1;raise RuntimeError(name+' forbidden in construction gate')
            return invoke
        for name in calls:setattr(z3,name,forbidden(name))
        stage='shared_lookup';start=time.monotonic();lookup=GroundedLookup(table,check)
        result['lookup_build_wall_s']=time.monotonic()-start
        stage='discrete_trace';start=time.monotonic();trace=lookup.trace(row['slots'],1,check=check)
        result['trace_build_wall_s']=time.monotonic()-start
        stage='DAG_count';start=time.monotonic();nodes=dag_nodes(lookup.roots(trace))
        result['DAG_count_wall_s']=time.monotonic()-start
        stage='literal_sequence_projection';plan=[('Site/000','C'),('Site/001','S'),('Site/002','C')]
        resolved=lookup.resolve(trace,plan);literal=table.literal_plan_legs(plan,1)
        if resolved['legs'][:3]+resolved['legs'][-1:]!=tuple((x.time,x.length) for x in literal):
            raise ValueError('literal plan/source/terminal mapping mismatch')
        if len(trace.choices)!=row['slots'] or any(calls.values()):raise ValueError('scope/profile mismatch')
        if source()['commit']!=src['commit'] or source()['dirty']:
            raise ValueError('source changed during one probe')
        native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak=native if sys.platform=='darwin' else native*1024
        if peak>cfg['process_RSS_guard_GiB']*1024**3:raise RuntimeError('postexit peak RSS guard')
        result.update(status='constructed',input_sha256=table.payload_sha256,
            literal_Sites=len(table.candidate_order),literal_actions=len(table.actions),
            physical_sources=len(table.sources),physical_targets=len(table.targets),
            pair_records=len(table.pairs),zero_pair_records=sum(p.source==p.target for p in table.pairs.values()),
            slots=len(trace.choices),unique_expression_AST_nodes=nodes,peak_RSS_bytes=peak,
            literal_plan_projection_verified=True,SMT_constructor_calls=calls,
            z3_version=z3.get_version_string(),z3_distribution=importlib.metadata.version('z3-solver'))
    except BaseException as exc:
        result.update(status='error',error=repr(exc),stage=stage)
    result.update(cpu_s=time.process_time()-cpu0,wall_s=time.monotonic()-wall0)
    atomic(out/'receipt.json',result);print(json.dumps(result,indent=2))
    return 0 if result['status']=='constructed' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('preflight','run'))
    p.add_argument('--config',default=str(ROOT/'configs/exact_leg_construction_gate.json'))
    p.add_argument('--output',required=True);p.add_argument('--preflight');p.add_argument('--probe')
    args=p.parse_args()
    if args.action=='preflight':preflight(args)
    else:raise SystemExit(run(args))
