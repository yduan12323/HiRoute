"""One admitted complete-domain packed-source attempt, then conditional proof.

Neither partial search nor schema/hash validation certifies a source. The
checker reparses the authoritative complete graph independently of the pack.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from packed_source_prototype import Packed,generate
from generate_exact_source_unit import domain
from run_one_source_gate import frozen_header
from streaming_road_graph import ResourceStop,sha,flush_file,validate,lines,json_line
from streaming_road_certificate import read_source_unit,SourceSession


def admit(c):
    fixed=dict(schema='hiroute.packed_single_source.config.v1',source='3797700636',
        frozen_domain_sha256='250ff5d84aed3e6fbf86e371f0cabbf135c4cc89034f9ce27fbc5f0bb411db7a',
        graph_identity='00f983ee3fdcfb04fa1b6dc008b39ab73e30e384c9c264d2f8691ea7224f1601',
        raw_sha256='8076e850b096c5cf74f307ae7ad34c2aebd1f1e53c3c4d092234d40078a4c54d',
        representation_sha256='db363d5b58d3bfe8731f7ff30e3a354c6d6223f276edd407d3c4ee197c60bfc1',
        packed_sha256='2c64f108db4dc97d916e82cc23567ff82e0c7514372c1a3562c965c9c0ffa603',
        packed_bytes=669640897,nodes=2986695,edges=5900232,sites=64,sources=65,targets=65,pairs=4225,
        component_CPU_s=120,component_wall_s=120,label_bytes=512*1024**2,
        SQLite_file_bytes=1024**3,whole_tree_RSS_bytes=1024**3,host_start_bytes=3*1024**3,
        host_floor_bytes=2*1024**3,disk_start_bytes=12*1024**3,disk_floor_bytes=2*1024**3,
        new_workspace_bytes=10*1024**3,worker_threads=1,EV_solve=False,upper_replay=False,holdout=False,
        output_limits=dict(paths=2*1024**3,binary=512*1024**2,decoded=3*1024**3))
    if type(c) is not dict or set(c)!=set(fixed):raise ValueError('complete frozen admission fields required')
    for k,v in fixed.items():
        if type(c[k]) is not type(v) or c[k]!=v:raise ValueError('frozen admission changed: '+k)
    if any(type(c['output_limits'][k]) is not int for k in fixed['output_limits']):raise ValueError('integer quotas')


def save(path,value):
    path=Path(path);temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n')
    flush_file(temporary);temporary.replace(path)


def small_json(path):
    if Path(path).stat().st_size>1024**2:raise ResourceStop('bounded receipt input')
    return json.loads(Path(path).read_text())


def complete_input(producer,header,config_sha,source_commit,limits,check=lambda:None):
    """Actual complete receipt AND all bytes must match before checker admission."""
    producer=Path(producer);r=small_json(producer/'result.json');S,T=domain(header)
    if (r.get('decision'),r.get('mode'),r.get('source'),r.get('source_commit'),r.get('config_sha256'))!=(
        'COMPLETE_UNTRUSTED_PACKED_SOURCE','generate',header['source_unit'],source_commit,config_sha):raise ValueError('no same-attempt complete generation receipt')
    if r.get('source_dirty') is not False or r.get('whole_table_certified') is not False:raise ValueError('producer provenance/coverage')
    result=r['result']
    if (result['source'],result['source_denominator'],result['pair_denominator'],result['candidate_pairs'])!=(header['source_unit'],len(S),len(S)*len(T),len(T)):raise ValueError('complete original unit domain')
    paths=producer/'candidate/paths.jsonl';cert=producer/'candidate/source.jsonl';binary=producer/'candidate/source.binary'
    for path,key,expected_size,expected_sha in (
        (paths,'paths',result['output_bytes']['paths'],result['paths_sha256']),
        (cert,'decoded',result['output_bytes']['certificate'],result['source_sha256']),
        (binary,'binary',result['output_bytes']['binary'],result['lossless_codec']['encoded_sha256'])):
        check()
        if type(expected_size) is not int or not 0<=expected_size<=limits[key] or path.stat().st_size!=expected_size:raise ValueError('complete artifact sizes/quotas')
        if sha(path)!=expected_sha:raise ValueError('actual complete artifact bytes')
    rows=iter(lines(paths))
    try:
        if json_line(next(rows))!=header:raise ValueError('original complete Site/action/Pi header')
    finally:rows.close()
    check();return paths,cert,r


def run(args):
    start=time.monotonic();cpu=time.process_time();deadline=start+120
    out=Path(args.output);out.mkdir(exist_ok=False)
    def check():
        if time.monotonic()>=deadline:raise ResourceStop('120s component wall limit')
    base=dict(mode=args.mode,decision='STARTED_UNCERTIFIED',source='3797700636',source_denominator=65,
        target_count=65,pair_denominator=4225,whole_table_certified=False,EV_solve=False,upper_replay=False,holdout=False,
        old_SQL_attempt='UNKNOWN, immutable; distinct implementation/attempt',started_at=time.time())
    save(out/'started.json',base);g=t=packed=None
    def progress(value):save(out/'progress.json',dict(value,component_CPU_s=time.process_time()-cpu,component_wall_s=time.monotonic()-start))
    try:
        c=small_json(args.config);admit(c);header=frozen_header(c,args.frozen_domain)
        frozen=small_json(args.frozen_domain)
        for k in ('config','preflight'):
            if sha(frozen[k+'_path'])!=frozen[k+'_sha256']:raise ValueError('original input configuration changed')
        for name,path in frozen['input_paths'].items():
            if name!='graph' and sha(path)!=frozen['expected_input_sha256'][name]:raise ValueError('original physical input changed')
        if frozen['expected_input_sha256']['graph']!=c['raw_sha256']:raise ValueError('original raw graph identity')
        base.update(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
            config_sha256=sha(args.config),frozen_domain_sha256=sha(args.frozen_domain),packed_sha256=c['packed_sha256'])
        if base['source_dirty']:raise ValueError('per-run clean source required; freeze before real execution')
        save(out/'started.json',base);check()
        if args.mode=='generate':
            progress(dict(phase='packed_admission',phase_complete=False))
            packed=Packed.open(args.packed)
            if (packed.N,packed.E,packed.data_sha256,packed.pages.size,packed.graph_identity)!=(c['nodes'],c['edges'],c['packed_sha256'],c['packed_bytes'],c['graph_identity']):raise ValueError('actual complete packed input')
            check();result=generate(packed,header,out/'candidate',label_bytes=c['label_bytes'],check=check,
                output_limits=c['output_limits'],progress=progress)
            decision='COMPLETE_UNTRUSTED_PACKED_SOURCE'
        else:
            if args.producer is None:raise ValueError('complete producer required')
            paths,cert,producer=complete_input(args.producer,header,base['config_sha256'],base['source_commit'],c['output_limits'],check)
            if producer['frozen_domain_sha256']!=base['frozen_domain_sha256'] or producer['packed_sha256']!=c['packed_sha256']:raise ValueError('same-attempt inputs changed')
            if sha(args.graph_db)!=c['representation_sha256']:raise ValueError('actual immutable full graph DB')
            progress(dict(phase='independent_graph_revalidation',phase_complete=False))
            g=validate(frozen['input_paths']['graph'],args.graph_db,out/'raw-revalidation',
                expected_raw_sha=c['raw_sha256'],max_tracking_bytes=c['SQLite_file_bytes'],check=check,progress=progress)
            if (g.payload_sha256,g.node_count,g.edge_count)!=(c['graph_identity'],c['nodes'],c['edges']):raise ValueError('independent complete raw graph')
            progress(dict(phase='selected_paths_parse',phase_complete=False))
            t=read_source_unit(paths,g,out/'paths.sqlite',max_bytes=c['SQLite_file_bytes'],check=check)
            progress(dict(phase='independent_full_source_check',phase_complete=False))
            s=SourceSession(g,t,max_state_bytes=c['SQLite_file_bytes'],check=check)
            s.check_source(cert,out/'source-check');result=dict(s.finish())
            if (result['checked_sources'],result['checked_pairs'],result['unrun_sources'],result['whole_table_certified'])!=(1,65,64,False):raise ValueError('single-source proof coverage')
            decision='VERIFIED_ONE_SOURCE_65_PAIRS_ONLY'
        check();terminal=dict(base,decision=decision,result=result,finished_at=time.time(),body_CPU_s=time.process_time()-cpu,wall_s=time.monotonic()-start)
    except BaseException as exc:
        terminal=dict(base,decision='UNKNOWN_UNCERTIFIED',error=repr(exc),finished_at=time.time(),body_CPU_s=time.process_time()-cpu,wall_s=time.monotonic()-start)
        save(out/'result.json',terminal);raise
    finally:
        if packed is not None:packed.close()
        if t is not None:t.close()
        if g is not None:g.close()
    save(out/'result.json',terminal);print(json.dumps(terminal))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('generate','check'),required=True)
    for name in ('config','frozen-domain','packed','graph-db','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--producer');run(p.parse_args())
