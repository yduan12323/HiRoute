"""One declared real comparison conditional on a charged common exact leg table.

The producer is the existing production road provider. Independent validation
spot-checks path sums, not global road optimality. The optimizer never imports
the production optimization kernel. All bulk artifacts remain outside Git.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from exact_leg_table import ExactLegTable,SCHEMA,NUMERICAL,SELECTION,unique
from packing_output_limits import LimitedFile


def convert(x):
    if isinstance(x,F):return str(x)
    if isinstance(x,dict):return {k:convert(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [convert(v) for v in x]
    return x


def atomic(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(convert(value),indent=2)+'\n');temp.replace(path)


def load(path,limit=4*1024**2):
    if path.stat().st_size>limit:raise ValueError('bounded metadata size')
    return json.loads(path.read_text(),object_pairs_hook=unique)


def sha(path,check=lambda:None):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):check();h.update(block)
    return h.hexdigest()


def source():
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    return dict(commit=git('rev-parse','HEAD'),dirty=bool(git('status','--porcelain')))


def dependency_environment():
    return dict(compiler=shutil.which('c++') or shutil.which('g++'),
                CPATH=os.environ.get('CPATH'),CPLUS_INCLUDE_PATH=os.environ.get('CPLUS_INCLUDE_PATH'))


def compiler_preflight():
    """Syntax-only prerequisite before any real graph preparation/query."""
    env=dependency_environment()
    if env['compiler'] is None:raise RuntimeError('native C++17 compiler unavailable')
    probe='#include <boost/multiprecision/cpp_int.hpp>\nint main(){boost::multiprecision::cpp_int x=1;x<<=160;return x==0;}\n'
    result=subprocess.run([env['compiler'],'-std=c++17','-x','c++','-fsyntax-only','-'],
        input=probe,capture_output=True,text=True,timeout=15)
    if result.returncode:raise RuntimeError('native dependency probe failed before road-query admission: '+result.stderr[-2000:])
    return env


def native_build_preflight(directory):
    """A real fresh C++ build AND ABI load, without graph construction/query."""
    from hiroute.exact.road_index import _load_native_library
    directory=Path(directory).resolve()
    if directory.exists():raise ValueError('inspect existing native prebuild; no uncertain repetition')
    start=time.monotonic();library,_=_load_native_library(directory)
    binary=Path(library._name).resolve()
    if not binary.is_relative_to(directory):raise ValueError('fresh native build provenance')
    return dict(loaded=True,scope='actual compilation and ctypes ABI load only; no graph/index/query',
        binary=str(binary),binary_sha256=sha(binary),binary_bytes=binary.stat().st_size,
        source_cpp_sha256=sha(ROOT/'src/hiroute/exact/road_index_native.cpp'),
        wall_s=time.monotonic()-start)


def verify_native_build(value):
    if not value or value.get('loaded') is not True:raise ValueError('actual successful native build required')
    if (sha(Path(value['binary']))!=value['binary_sha256'] or
        sha(ROOT/'src/hiroute/exact/road_index_native.cpp')!=value['source_cpp_sha256']):
        raise ValueError('native build artifact/input provenance changed')


def header(frozen):
    rows=frozen['domain']['candidates'];ends=frozen['domain']['endpoints']
    result=dict(schema=SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
        road_selection_certified=False,origin_anchor=ends['origin']['access_node'],
        destination_anchor=ends['destination']['access_node'],
        graph_identity=frozen['expected_input_sha256']['graph'],
        candidate_order=[r['site_id'] for r in rows],
        sites={r['site_id']:dict(anchor=r['access_node'],effects=r['capabilities']) for r in rows})
    if len(result['sites'])!=len(rows):raise ValueError('duplicate literal Site')
    sources=sorted({result['origin_anchor'],*(r['anchor'] for r in result['sites'].values())})
    targets=sorted({result['destination_anchor'],*(r['anchor'] for r in result['sites'].values())})
    if sources!=frozen['physical_sources'] or targets!=frozen['physical_targets']:
        raise ValueError('frozen source/terminal coverage mismatch')
    return result,sources,targets


def sample_pairs(sources,targets,origin,destination):
    pairs=sorted((s,t) for s in sources for t in targets if s!=t)
    chosen={pairs[(i*(len(pairs)-1))//15] for i in range(16)} if pairs else set()
    shared=sorted(set(sources)&set(targets))
    chosen.add((origin,destination))
    if shared:
        a,b=shared[0],shared[-1]
        chosen.update(((origin,a),(origin,b),(a,destination),(b,destination),(a,b),(b,a),(a,a)))
    return sorted(chosen)


def record(leg,s,t):
    if leg is None:return dict(source=s,target=t,reachable=False,time_s=None,actual_length_m=None,nodes=[],edges=[])
    nodes=[s];edges=[]
    for e in leg.edges:
        if e['source']!=nodes[-1]:raise ValueError('provider path disconnected')
        nodes.append(e['target']);edges.append(e['edge_id'])
    if nodes[-1]!=t:raise ValueError('provider path endpoint')
    return dict(source=s,target=t,reachable=True,time_s=str(leg.time_s),actual_length_m=str(leg.length_m),nodes=nodes,edges=edges)


def write_table(provider,h,sources,targets,path,progress=lambda n:None,limit=256*1024**2):
    count=0;temp=path.with_suffix('.partial')
    with LimitedFile(temp,'x',limit) as f:
        text=json.dumps(h,separators=(',',':'));f.write(text[:-1]+',"pairs":[')
        for t in targets:
            for s in sources:
                row=record(provider.selected_leg(s,t),s,t)
                if count:f.write(',')
                f.write(json.dumps(row,separators=(',',':')));count+=1
                if count%16==0:progress(count)
        f.write(']}\n');f.flush();os.fsync(f.fileno())
    temp.replace(path);path.chmod(0o444)
    return count


def table_bytes(path,expected,check=lambda:None):
    if path.stat().st_size>256*1024**2:raise ValueError('table byte quota')
    if sha(path,check)!=expected:raise ValueError('immutable table mismatch')
    return ExactLegTable.from_bytes(path.read_bytes(),check=check)


def pilot_table(out,generation,cfg,check):
    if cfg.get('split_input'):
        from split_leg_table import read
        table=read(out/'split-table',check)
        if table.payload_sha256!=generation['table_sha256']:
            table._path_store.close();raise ValueError('complete split table receipt mismatch')
        return table
    return table_bytes(out/'table.json',generation['table_sha256'],check)


def physical(model,table,recipe):
    from exact_physical_adapter import SCHEMA as PHYS,FIELDS
    direct=table.pairs[table.origin_anchor,table.destination_anchor]
    if not direct.reachable:raise ValueError('scheduled OD unreachable')
    return dict({k:model[k] for k in FIELDS},schema=PHYS,charging_curve=model['charging_curve'],
        initial_remaining_schedule=1,schedule=dict(a=str(direct.time*F(recipe['a_fraction_direct_time'])),
            b=str(direct.time*F(recipe['b_fraction_direct_time'])),D=recipe['duration_s']))


def verify_paths(table,pairs,edge,check=lambda:None):
    result=[]
    for s,t in sorted(set(map(tuple,pairs))):
        check();p=table.pairs[s,t]
        if not p.reachable:
            result.append(dict(source=s,target=t,status='common_provider_unreachable_not_independent_cut'));continue
        duration=length=F(0)
        for eid,u,v in zip(p.edges,p.nodes,p.nodes[1:]):
            check();a,b,dt,ds=edge(eid)
            if (a,b)!=(u,v):raise ValueError('raw edge identity/connectivity mismatch')
            duration+=F(dt);length+=F(ds)
        if duration!=p.time or length!=p.length:raise ValueError('raw selected path totals mismatch')
        result.append(dict(source=s,target=t,status='exact_path_replay_pass',edges=len(p.edges)))
    return result


def freeze(args,cfg):
    frozen=load(args.frozen_domain)
    if sha(args.frozen_domain)!=cfg['frozen_domain_sha256']:raise ValueError('frozen domain bytes')
    if (frozen['query_id'],frozen['initial_energy_kwh'],frozen['scenario'],frozen['N'])!=('WD01','18','schedule',64):
        raise ValueError('single declared query only')
    if frozen['candidate_domain_sha256']!=cfg['candidate_domain_sha256']:raise ValueError('domain identity')
    h,sources,targets=header(frozen)
    actions=sum(len(v['effects']) for v in h['sites'].values())
    if (len(h['sites']),actions,len(sources),len(targets),len(sources)*len(targets))!=(64,78,65,65,4225):
        raise ValueError('no candidate/action/pair reduction')
    if len(set(sources)&set(targets))!=64:raise ValueError('alias-zero denominator')
    dependency=compiler_preflight()
    expected=cfg.get('command_scoped_include_environment',{})
    if any(dependency.get(k)!=v for k,v in expected.items()):raise ValueError('declared include environment')
    native_build=native_build_preflight(args.output/'native-prebuild')
    for key,expected in frozen['expected_input_sha256'].items():
        if expected!=cfg['expected_input_sha256'][key] or sha(Path(frozen['input_paths'][key]))!=expected:
            raise ValueError('frozen source input '+key)
    for key in ('config','preflight'):
        if frozen[key+'_sha256']!=cfg[key+'_sha256'] or sha(Path(frozen[key+'_path']))!=cfg[key+'_sha256']:
            raise ValueError('original recipe/config mismatch')
    if sha(args.graph_db)!=cfg['representation_sha256']:raise ValueError('validated immutable DB bytes')
    proof=load(ROOT/'docs/streaming_road_representation_results.json')['full_validation']
    if (proof['decision']!='PASS_FULL_REPRESENTATION_IDENTITY_ONLY' or
        proof['representation_sha256']!=cfg['representation_sha256'] or
        proof['raw_graph_sha256']!=cfg['expected_input_sha256']['graph']):raise ValueError('prior identity proof binding')
    prior=load(args.historical_row);w=prior['witness']
    if (prior['query_id'],prior['initial_energy_kwh'],prior['scenario'],prior['N'])!=('WD01','18','schedule',64):
        raise ValueError('historical witness domain')
    if prior['candidate_domain_sha256']!=cfg['candidate_domain_sha256'] or not w['physical_verified']:
        raise ValueError('historical witness identity/provenance')
    # Only the concrete plan/charges/wait are supplied, never the old objective.
    upper=dict(plan=w['independent_key'][3],charges=w['charges_kwh'],initial_wait=w['initial_wait_s'])
    old=load(Path(frozen['config_path']));src=source()
    if src['dirty']:raise ValueError('freeze requires a clean recorded producer')
    return dict(status='FROZEN_INPUT_NOT_YET_TABLE',source=src,config_sha256=sha(args.config),
        frozen_domain_sha256=cfg['frozen_domain_sha256'],candidate_domain_sha256=cfg['candidate_domain_sha256'],
        header=h,sources=sources,targets=targets,sample_pairs=sample_pairs(sources,targets,h['origin_anchor'],h['destination_anchor']),
        model=old['model'],schedule_recipe=old['selection']['schedule_recipe'],upper_witness=upper,
        dependency_environment=dependency,
        native_build_preflight=native_build,
        graph_tsv=frozen['input_paths']['graph'],graph_db=str(args.graph_db.resolve()),
        graph_db_sha256=cfg['representation_sha256'],graph_sha256=cfg['expected_input_sha256']['graph'],
        historical_reference=dict(path=str(args.historical_row.resolve()),sha256=sha(args.historical_row),
            status=prior['status'],generation_CPU_s=prior['worker_cpu_s'],timing_control=False),
        pair_denominator=4225,site_denominator=64,actions=78,road_selection_certified=False,holdout=False)


def receipt(out,mode):
    path=out/(mode+'.result.json');budget=load(out/'budget.json')
    records=[r for r in budget['records'] if r['phase']==mode]
    if (len(records)!=1 or records[0].get('actual_child_returncode')!=0 or records[0].get('guard_reason') is not None
        or records[0].get('terminal_sha256')!=sha(path)):raise ValueError('prior controller terminal/receipt binding')
    value=load(path)
    if value.get('mode')!=mode:raise ValueError('prior phase receipt mode')
    if value.get('status')!='COMPLETE':raise ValueError('prior phase incomplete')
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['freeze','generation','validation','optimization'],required=True)
    p.add_argument('--config',type=Path,default=ROOT/'configs/shared_leg_pilot.json');p.add_argument('--output',type=Path,required=True)
    for name in ('frozen-domain','graph-db','historical-row'):p.add_argument('--'+name,type=Path)
    a=p.parse_args();cfg=load(a.config);out=a.output;out.mkdir(exist_ok=True)
    start=time.monotonic();cpu=time.process_time();started=out/(a.mode+'.started.json');terminal=out/(a.mode+'.result.json')
    if started.exists() or terminal.exists():raise ValueError('inspect existing phase; no repeated/uncertain attempt')
    initial_source=source()
    with started.open('x') as f:json.dump(dict(mode=a.mode,source=initial_source,started_at=time.time(),query='WD01/E18/schedule/N64',pair_denominator=4225),f)
    def check():
        if time.monotonic()-start>({'freeze':55,'generation':295,'validation':175,'optimization':120}[a.mode]):
            raise TimeoutError('phase wall deadline')
    result=dict(status='UNKNOWN',mode=a.mode,road_selection_certified=False,holdout=False)
    try:
        if a.mode=='freeze':
            admission=freeze(a,cfg);atomic(out/'admission.json',admission);result.update(status='COMPLETE',admission_sha256=sha(out/'admission.json'))
        else:
            frozen_receipt=receipt(out,'freeze');ad=load(out/'admission.json')
            if sha(out/'admission.json')!=frozen_receipt['admission_sha256']:raise ValueError('frozen admission changed')
            if ad['source']!=source() or ad['config_sha256']!=sha(a.config):raise ValueError('within-run source/config provenance mismatch')
            if ad['dependency_environment']!=dependency_environment():raise ValueError('within-run compiler/include environment changed')
            if a.mode=='generation':
                from hiroute.exact.road_index import NativeRoadIndex
                verify_native_build(ad.get('native_build_preflight'))
                if sha(Path(ad['graph_tsv']),check)!=ad['graph_sha256']:raise ValueError('road input changed')
                with NativeRoadIndex(ad['graph_tsv'],sorted(set(ad['sources']+ad['targets'])),cache_directory=out/'native-cache',
                    leg_cache_size=0,distance_cache_size=2,check=check) as provider:
                    dims=provider.metrics()
                    if (dims['nodes'],dims['edges'])!=(cfg['graph_nodes'],cfg['graph_edges']):
                        raise ValueError('full frozen road graph dimensions')
                    progress=lambda n:atomic(out/'generation.progress.json',dict(completed_pairs=n,pair_denominator=4225)) if n%16==0 else None
                    if cfg.get('split_input'):
                        from split_leg_table import write
                        rows=(record(provider.selected_leg(s,t),s,t) for t in ad['targets'] for s in ad['sources'])
                        count,table_sha=write(out/'split-table',ad['header'],rows,
                            dict(source=ad['source'],config_sha256=ad['config_sha256'],
                                 graph_sha256=ad['graph_sha256'],candidate_domain_sha256=ad['candidate_domain_sha256']),check,progress)
                    else:
                        count=write_table(provider,ad['header'],ad['sources'],ad['targets'],out/'table.json',progress)
                        table_sha=sha(out/'table.json',check)
                    metrics=provider.metrics()
                if count!=4225:raise ValueError('incomplete table')
                result.update(status='COMPLETE',completed_pairs=count,table_sha256=table_sha,
                    table_bytes=sum(p.stat().st_size for p in (out/'split-table').iterdir()) if cfg.get('split_input') else (out/'table.json').stat().st_size,
                    provider_metrics=metrics,independent_road_certified_pairs=0)
            else:
                gen=receipt(out,'generation')
                if gen['source']!=ad['source'] or gen['completed_pairs']!=4225:raise ValueError('complete producer provenance')
                table=pilot_table(out,gen,cfg,check)
                if cfg.get('split_input'):
                    if table._path_store.manifest['provenance']!=dict(source=ad['source'],config_sha256=ad['config_sha256'],
                        graph_sha256=ad['graph_sha256'],candidate_domain_sha256=ad['candidate_domain_sha256']):raise ValueError('split producer/input provenance')
                    expected=dict(ad['header']);actual={k:v for k,v in table._path_store.numeric.items() if k!='pairs'}
                    if actual!=expected:raise ValueError('split frozen literal header mismatch')
                parameters=physical(ad['model'],table,ad['schedule_recipe'])
                if a.mode=='validation':
                    from exact_physical_adapter import replay,table_relevant_depth
                    from streaming_road_graph import connect
                    if sha(Path(ad['graph_db']),check)!=ad['graph_db_sha256']:raise ValueError('raw-joined DB input changed')
                    upper=ad['upper_witness'];checked=replay(table,parameters,upper['plan'],upper['charges'],upper['initial_wait'])
                    depth,_=table_relevant_depth(table,parameters,upper)
                    pairs=[*ad['sample_pairs'],*((x.source,x.target) for x in table.literal_plan_legs(upper['plan'],1))]
                    db=connect(Path(ad['graph_db']))
                    def edge(eid):
                        row=db.execute('SELECT u,v,t,l FROM edges WHERE eid=? COLLATE BINARY',(eid,)).fetchone()
                        if row is None:raise ValueError('missing raw literal edge')
                        return row
                    try:paths=verify_paths(table,pairs,edge,check)
                    finally:db.close()
                    atomic(out/'physics.json',parameters)
                    result.update(status='COMPLETE',table_sha256=table.payload_sha256,upper_replay=checked,
                        derived_complete_H=depth,physics_sha256=sha(out/'physics.json'),sample_path_checks=paths,
                        route_optimality_scope='common exact provider assumption; raw path samples are not shortest-road certificates')
                else:
                    val=receipt(out,'validation')
                    if (val['source']!=ad['source'] or val['table_sha256']!=table.payload_sha256
                        or val['physics_sha256']!=sha(out/'physics.json')):
                        raise ValueError('validated inputs changed')
                    from exact_physical_adapter import solve_real
                    remaining=120-(time.monotonic()-start)
                    if remaining<=0:raise TimeoutError('optimizer load consumed deadline')
                    comparison=solve_real(table,parameters,ad['upper_witness'],out/'SMT',remaining)
                    atomic(out/'optimizer.returned.json',dict(scope='solver return before final raw-path validation',comparison=comparison))
                    output_paths=[]
                    if comparison['status']=='attained_optimum':
                        from streaming_road_graph import connect
                        if sha(Path(ad['graph_db']),check)!=ad['graph_db_sha256']:raise ValueError('output path DB changed')
                        db=connect(Path(ad['graph_db']))
                        def output_edge(eid):
                            row=db.execute('SELECT u,v,t,l FROM edges WHERE eid=? COLLATE BINARY',(eid,)).fetchone()
                            if row is None:raise ValueError('missing output raw edge')
                            return row
                        try:
                            output_paths=verify_paths(table,[(x.source,x.target) for x in table.literal_plan_legs(comparison['witness']['plan'],1)],output_edge,check)
                        finally:db.close()
                    result.update(status='COMPLETE',comparison=comparison,output_path_checks=output_paths,
                        table_sha256=table.payload_sha256,prep_cost_not_free=True,historical_timing_control=False)
                    check()
        check()
    except Exception as exc:result.update(status='UNKNOWN',reason=repr(exc))
    finally:
        if 'table' in locals() and hasattr(table,'_path_store'):table._path_store.close()
    ended_source=source()
    if ended_source!=initial_source:result.update(status='UNKNOWN',reason='within-run source provenance changed')
    result.update(body_CPU_s=time.process_time()-cpu,body_wall_s=time.monotonic()-start,source=ended_source)
    atomic(terminal,result);print(json.dumps(convert(result)),flush=True)
    return 0 if result['status']=='COMPLETE' else 75


if __name__=='__main__':raise SystemExit(main())
