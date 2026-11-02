"""Exactly one source candidate attempt and a separate independent check.

The external durable controller owns CPU/RSS/headroom limits. This worker never
spawns subprocesses. An incomplete producer cannot admit the checker or a retry.
"""
import argparse
import json
from pathlib import Path
import time

from exact_leg_table import NUMERICAL,SELECTION
from streaming_road_graph import sha,validate,ResourceStop,json_line,lines
from streaming_road_certificate import UNIT_SCHEMA,read_source_unit,SourceSession
from generate_exact_source_unit import generate,domain


def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(path)


def frozen_header(config,path):
    if sha(path)!=config['frozen_domain_sha256']:raise ValueError('frozen complete query identity')
    f=json.loads(Path(path).read_text());D=f['domain'];c=D['candidates']
    h=dict(schema=UNIT_SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
        graph_identity='sha256:'+config['graph_identity'],origin_anchor=D['endpoints']['origin']['access_node'],
        destination_anchor=D['endpoints']['destination']['access_node'],candidate_order=[v['site_id'] for v in c],
        sites={v['site_id']:dict(anchor=v['access_node'],effects=v['capabilities']) for v in c},source_unit=config['source'])
    S,T=domain(h)
    if (len(c),len(S),len(T),len(S)*len(T),list(S),list(T))!=(64,65,65,4225,f['physical_sources'],f['physical_targets']):
        raise ValueError('original64 literal Sites /65sources /4225pairs required')
    if h['origin_anchor']!=config['source']:raise ValueError('predeclared original OD source')
    return h


def run(args):
    config=json.loads(Path(args.config).read_text());header=frozen_header(config,args.frozen_domain)
    out=Path(args.output);out.mkdir(exist_ok=False);start=time.monotonic();deadline=start+120
    def check():
        if time.monotonic()>=deadline:raise ResourceStop('120s component wall limit')
    base=dict(mode=args.mode,source=config['source'],source_denominator=65,pair_denominator=4225,
        target_count=65,source_commit=args.source_commit,config_sha256=sha(args.config),
        frozen_domain_sha256=sha(args.frozen_domain),started_at=time.time(),whole_table_certified=False,
        EV_solve=False,upper_replay=False,holdout=False)
    save(out/'started.json',base)
    def progress(value):save(out/'progress.json',dict(value,wall_s=time.monotonic()-start))
    try:
        if args.mode=='generate':
            result=generate(args.graph_db,header,out/'candidate',expected_graph_sha=config['representation_sha256'],check=check,progress=progress)
            decision='UNTRUSTED_SOURCE_CANDIDATE_COMPLETE'
        else:
            producer=Path(args.producer);p=json.loads((producer/'result.json').read_text())
            if p['decision']!='UNTRUSTED_SOURCE_CANDIDATE_COMPLETE':raise ValueError('no complete generation receipt')
            if (p['source_commit'],p['config_sha256'],p['frozen_domain_sha256'])!=(args.source_commit,sha(args.config),sha(args.frozen_domain)):
                raise ValueError('same-attempt provenance required')
            paths=producer/'candidate/paths.jsonl';cert=producer/'candidate/source.jsonl'
            if (sha(paths),sha(cert))!=(p['result']['paths_sha256'],p['result']['source_sha256']):raise ValueError('actual producer artifact identity')
            actual=json_line(next(iter(lines(paths))))
            if actual!=header:raise ValueError('unit must retain original full literal Site/action/Pi metadata')
            if sha(args.graph_db)!=config['representation_sha256']:raise ValueError('actual graph representation bytes')
            g=t=None
            try:
                # This repeats only the necessary independent artifact
                # revalidation in this new attempt and charges it explicitly.
                g=validate(args.raw,args.graph_db,out/'graph-revalidation',expected_raw_sha=config['raw_sha256'],check=check,progress=progress)
                if (g.payload_sha256,g.node_count,g.edge_count)!=(config['graph_identity'],2986695,5900232):raise ValueError('complete frozen graph')
                t=read_source_unit(paths,g,out/'paths.sqlite',check=check)
                s=SourceSession(g,t,check=check);s.check_source(cert,out/'source-check');result=dict(s.finish())
                decision='VERIFIED_SINGLE_SOURCE_ONLY'
            finally:
                if t is not None:t.close()
                if g is not None:g.close()
        check();terminal=dict(base,decision=decision,result=result,wall_s=time.monotonic()-start,finished_at=time.time())
    except BaseException as exc:
        terminal=dict(base,decision='UNKNOWN_UNCERTIFIED',error=repr(exc),wall_s=time.monotonic()-start,finished_at=time.time())
        save(out/'result.json',terminal);raise
    save(out/'result.json',terminal);print(json.dumps(terminal))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('generate','check'),required=True)
    for name in ('config','frozen-domain','graph-db','raw','output','source-commit'):p.add_argument('--'+name,required=True)
    p.add_argument('--producer');run(p.parse_args())
