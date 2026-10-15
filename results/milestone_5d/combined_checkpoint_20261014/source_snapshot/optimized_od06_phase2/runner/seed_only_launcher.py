"""Separate, non-formal exploratory seed launcher. Never imports a main runner."""
import argparse
import fcntl
import hashlib
import json
import os
import resource
import signal
import stat
from pathlib import Path
import sys
import time
from cloud_adapter import Limits, atomic, run, sha

ROOT=Path(__file__).resolve().parent
ROWS=('OD06_energy_only_soc3_10_n32_flat','OD06_energy_and_scheduled_soc3_10_n32_flat',
      'OD06_energy_and_scheduled_soc3_10_n128_flat')
MANIFEST_SHA='a575039c65b8ce31b4f725e389685c5cb78e71ae6df7c2a99d66da7b70ce1064'
canon=lambda x:json.dumps(x,sort_keys=True,separators=(',',':')).encode()

def source_identity():
    return {str(p.relative_to(ROOT)):sha(p) for base in ('src','validation')
        for p in sorted((ROOT/base).rglob('*')) if p.suffix in ('.py','.cpp')} | {
        name:sha(ROOT/name) for name in ('seed_only_launcher.py','cloud_adapter.py')}

def verify_source():
    frozen=json.loads((ROOT/'source_provenance.json').read_bytes())
    if frozen['source_sha256']!=source_identity():raise ValueError('Exploratory source closure changed')
    return frozen

def bindings(spec, *, verify_graph=True):
    if spec['row_id'] not in ROWS:raise ValueError('Row outside exact exploratory allowlist')
    manifest_path=Path(spec['manifest']);queries_path=Path(spec['queries']);pools_path=Path(spec['pools'])
    if sha(manifest_path)!=MANIFEST_SHA:raise ValueError('Original manifest hash differs')
    m=json.loads(manifest_path.read_bytes())
    if sha(queries_path)!=m['input_sha256']['queries'] or sha(pools_path)!=m['input_sha256']['pools']:
        raise ValueError('Original query/pool bytes differ')
    qs=json.loads(queries_path.read_bytes());pools=json.loads(pools_path.read_bytes())
    if qs['schema']!='hiroute.m5d.frozen_48_query_payloads.v1' or len(qs['queries'])!=48:
        raise ValueError('Original query schema/count differs')
    row=next(x for x in m['rows'] if x['row_id']==spec['row_id'])
    qr=next(x for x in qs['queries'] if x['query_id']==row['query_id'])
    b=qr['bindings'][str(row['candidate_prefix_count'])];query=b['query']
    if hashlib.sha256(canon(query)).hexdigest()!=b['query_sha256']:raise ValueError('Query binding differs')
    if query['hierarchy_sha256']!=m['input_sha256']['hierarchy']:raise ValueError('Hierarchy identity differs')
    pool=next(x for x in pools['pools'] if x['od_id']==qr['od_id'])
    selected=pool['sites'][:row['candidate_prefix_count']]
    if [x['site_id'] for x in selected]!=b['candidate_site_ids']:raise ValueError('Candidate prefix order differs')
    for key in ('graph_nodes','graph_edges','graph_metadata','pools','hierarchy'):
        if qs['source_sha256'][key]!=m['input_sha256'][key]:raise ValueError('Query source reference differs')
    if qs['source_sha256']['router_cpp']!=m['source_sha256']['src/microplan/routing.cpp']:
        raise ValueError('Query native source reference differs')
    if verify_graph:
        for name,key in [('nodes.parquet','graph_nodes'),('edges.parquet','graph_edges'),('metadata.json','graph_metadata')]:
            if sha(Path(spec['graph_dir'])/name)!=m['input_sha256'][key]:raise ValueError('Graph input differs: '+name)
    return m,qs,row,b,query,selected

def load_graph(graph_dir):
    # Exact frozen loader arithmetic/validation; hashes verified by bindings().
    import numpy as np
    import pandas as pd
    from types import SimpleNamespace
    graph_dir=Path(graph_dir);metadata=json.loads((graph_dir/'metadata.json').read_text())
    edges=pd.read_parquet(graph_dir/'edges.parquet',columns=['source','target','travel_time_s','length_m'])
    source=np.ascontiguousarray(edges.source.to_numpy(dtype=np.int64))
    target=np.ascontiguousarray(edges.target.to_numpy(dtype=np.int64))
    travel=np.ascontiguousarray(edges.travel_time_s.to_numpy(dtype=np.float64))
    length=np.ascontiguousarray(edges.length_m.to_numpy(dtype=np.float64));del edges
    n,m=int(metadata['node_count']),int(metadata['edge_count'])
    if (len(source)!=m or len(target)!=m or (source<0).any() or (source>=n).any() or
        (target<0).any() or (target>=n).any() or not np.isfinite(travel).all() or
        (travel<=0).any() or not np.isfinite(length).all() or (length<0).any()):
        raise ValueError('Graph arrays violate directed native routing contract')
    return SimpleNamespace(node_count=n,edge_count=m,source=source,target=target,
        weights={'travel_time':travel,'distance':length})

def worker(spec_path,guard_fd):
    if guard_fd is None or not stat.S_ISFIFO(os.fstat(guard_fd).st_mode):
        raise ValueError('Worker requires its admitted parent supervision pipe')
    guard=json.loads(os.read(guard_fd,16384));os.close(guard_fd)
    spec=json.loads(Path(spec_path).read_bytes())
    if guard['parent_pid']!=os.getppid() or guard['spec_sha256']!=sha(spec_path):
        raise ValueError('Worker parent/spec guard differs')
    if (resource.getrlimit(resource.RLIMIT_AS)!=(8*1024**3,8*1024**3)
        or resource.getrlimit(resource.RLIMIT_CPU)!=(600,601)
        or list(os.sched_getaffinity(0))!=[guard['cpu']]
        or os.getpgid(0)!=os.getpid()):
        raise ValueError('Worker exploratory limits are not active')
    admission=json.loads(Path(spec['admission_path']).read_bytes())
    ledger=json.loads(Path(spec['ledger_path']).read_bytes())
    if (admission.get('approved') is not True or admission.get('synthetic_only') is not False
        or sha(spec['admission_path'])!=spec['admission_sha256']
        or ledger['admission_sha256']!=spec['admission_sha256']
        or ledger.get('blocked') or ledger['attempts'][-1]['row_id']!=spec['row_id']
        or ledger['attempts'][-1]['state']!='reserved'):
        raise ValueError('Worker active admission reservation missing')
    out=Path(spec['worker_output']);out.mkdir(exist_ok=False)
    sys.path[:0]=[str(ROOT/'src'),str(ROOT),str(Path(spec['dependency_dir']).resolve())]
    router=None
    try:
        source=verify_source();m,qs,row,b,query,selected=bindings(spec)
        from microplan.routing import ExactRouter
        from timecut5.real_legs import RealSite
        from timecut5.real_adapter import site_catalog_digest
        from timecut5.road_provider import TableFreeRoadSelectedLegProvider
        from timecut5.sparse_seed import SparseSeedCatalog
        from timecut5.streaming_seed_diagnostic import observe_streaming_seed
        sites={s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in selected}
        if len(sites)!=row['candidate_prefix_count'] or site_catalog_digest(sites)!=b['site_catalog_sha256']:
            raise ValueError('Site catalog binding differs')
        anchors=list(dict.fromkeys([query['origin']]+[s.anchor_id for s in sites.values()]+[query['destination']]))
        anodes={a:int(a.removeprefix('road:')) for a in anchors}
        if hashlib.sha256(canon(anodes)).hexdigest()!=b['anchor_catalog_sha256']:raise ValueError('Anchor binding differs')
        atomic(out/'stage.json',dict(stage='inputs_verified',hierarchy_bytes_verified=False))
        graph=load_graph(spec['graph_dir'])
        atomic(out/'stage.json',dict(stage='graph_loaded',nodes=graph.node_count,edges=graph.edge_count))
        router=ExactRouter(graph,{'compiler':'g++','compiler_flags':['-O3','-std=c++17']},out/'road_native')
        if router.provenance['source_sha256']!=m['source_sha256']['src/microplan/routing.cpp']:
            raise ValueError('Native source differs')
        provider=TableFreeRoadSelectedLegProvider(graph,router,anodes,
            nodes_sha256=m['input_sha256']['graph_nodes'],edges_sha256=m['input_sha256']['graph_edges'],
            router_sha256=router.provenance['source_sha256'],anchor_catalog_sha256=b['anchor_catalog_sha256'],
            source_cache_max_bytes=256*1024*1024,source_cache_max_sources=1)
        catalog=SparseSeedCatalog(provider,sites,origin_anchor=query['origin'],destination_anchor=query['destination'],
            nodes_path=Path(spec['graph_dir'])/'nodes.parquet',edges_path=Path(spec['graph_dir'])/'edges.parquet',
            site_catalog_sha256=b['site_catalog_sha256'],hierarchy_sha256=query['hierarchy_sha256'],candidate_sha256=b['candidate_sha256'])
        if catalog.domain_sha256!=b['sparse_domain_sha256']:raise ValueError('Sparse domain binding differs')
        provenance=dict(kind='non_formal_exploratory_seed_only',row_id=spec['row_id'],
            hierarchy_bytes_verified=False,hierarchy_digest_source='exact_hash_verified_original_query',
            frozen_main_admission=False,cgroup_equivalent=False,admission_sha256=spec['admission_sha256'],
            original_input_sha256=m['input_sha256'],query_path=spec['queries'],pool_path=spec['pools'],
            native_binary_sha256=sha(out/'road_native/routing.so'),historical_query_binary_sha256=qs['source_sha256']['router_binary'],
            diagnostic_source=source,compiler=router.provenance,
            interpreter_executable=sys.executable,interpreter_version=sys.version,
            interpreter_sha256=sha(sys.executable),
            packages={name:__import__('importlib.metadata',fromlist=['version']).version(name)
                for name in ('numpy','pandas','pyarrow','psutil','igraph','pyproj','scipy','matplotlib','texttable','certifi')})
        seed=observe_streaming_seed(query,catalog,output_dir=out/'diagnostic',provenance=provenance)
        atomic(out/'result.json',dict(status=seed['status'],proposal_count=seed['proposal_count'],
            accepted_count=seed.get('accepted_count',0),solver_started=False,denominator_included=False))
    except BaseException as exc:
        atomic(out/'error.json',dict(type=type(exc).__name__,message=str(exc),solver_started=False))
        raise
    finally:
        if router is not None:router.close()

class Admission:
    """Conservative per-attempt debit; no automatic retries or reservation refund."""
    def __init__(self,path,ledger,row_id,reserve_seconds, *, synthetic=False):
        self.path,self.ledger,self.row_id,self.reserve=Path(path),Path(ledger),row_id,reserve_seconds
        self.synthetic=synthetic
    def __enter__(self):
        self.admission=json.loads(self.path.read_bytes());a=self.admission
        if (a.get('synthetic_only') is not self.synthetic or a.get('approved') is not True or a.get('kind')!='delegated_compute_planning_phase'
            or a.get('row_allowlist')!=list(ROWS) or not a.get('authorization_reference')
            or type(a.get('cpu_seconds')) not in (int,float) or not 0<a['cpu_seconds']<=3600
            or type(a.get('preparation_cpu_seconds')) not in (int,float)
            or not 0<=a['preparation_cpu_seconds']<=a['cpu_seconds']):
            raise ValueError('Explicit separate exploratory admission is missing or invalid')
        if self.ledger.resolve()!=Path(a.get('ledger_path','')).resolve():
            raise ValueError('Admission is bound to one canonical ledger path')
        if not self.synthetic and self.path.resolve()!=ROOT/'admission_optimized_phase2.json':
            raise ValueError('Unrecognized real admission file')
        self.ledger.parent.mkdir(parents=True,exist_ok=True)
        self.lock=self.ledger.with_suffix('.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX)
        try:
            state=json.loads(self.ledger.read_bytes()) if self.ledger.exists() else dict(admission_sha256=sha(self.path),preparation_cpu_seconds=a['preparation_cpu_seconds'],attempts=[],blocked=False)
            if state['admission_sha256']!=sha(self.path):raise ValueError('Admission changed')
            if state.get('blocked'):raise ValueError('Prior accounting or cleanup failure blocks further rows')
            if any(x.get('state')!='finished' for x in state['attempts']):
                raise ValueError('Prior nonterminal attempt has unverified cleanup; further rows blocked')
            if self.row_id not in ROWS or any(x['row_id']==self.row_id for x in state['attempts']):raise ValueError('Unlisted or already attempted row')
            if state['preparation_cpu_seconds']+sum(x['reserved_cpu_seconds'] for x in state['attempts'])+self.reserve>a['cpu_seconds']:raise ValueError('Separate allowance exhausted')
            state['attempts'].append(dict(row_id=self.row_id,reserved_cpu_seconds=self.reserve,state='reserved',no_automatic_retry=True))
            atomic(self.ledger,state);self.state=state
            return sha(self.path)
        except BaseException:
            self.lock.close();raise
    def record(self,receipt):
        charged=receipt['conservative_wait4_cpu_seconds']+receipt.get('controller_cpu_seconds_including_preflight',receipt['parent_cpu_seconds'])
        self.state['attempts'][-1].update(receipt_cpu_seconds=charged,reason=receipt['reason'])
        if charged>self.reserve or not receipt['cleanup_verified']:
            self.state['blocked']=True
        atomic(self.ledger,self.state)
    def __exit__(self,typ,value,tb):
        self.state['attempts'][-1]['state']='finished' if typ is None else 'failed_or_interrupted'
        if typ is not None:self.state['blocked']=True
        atomic(self.ledger,self.state);self.lock.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--worker-guard-fd',type=int)
    parser.add_argument('--spec');parser.add_argument('--run',action='store_true')
    parser.add_argument('--admission');parser.add_argument('--ledger');parser.add_argument('--output')
    args=parser.parse_args()
    if args.worker:return worker(args.worker,args.worker_guard_fd)
    if not args.spec:parser.error('--spec is required')
    if args.run:
        resource.setrlimit(resource.RLIMIT_CPU,(50,resource.getrlimit(resource.RLIMIT_CPU)[1]))
        def controller_stop(signum,frame):
            raise RuntimeError('Exploratory controller CPU/signal stop: '+str(signum))
        for sig in (signal.SIGXCPU,signal.SIGTERM,signal.SIGINT):signal.signal(sig,controller_stop)
        if Path(args.spec).stat().st_size>65536:raise ValueError('Oversized run specification')
    spec=json.loads(Path(args.spec).read_bytes())
    if not args.run:
        verify_source();bindings(spec)
        print(json.dumps(dict(ready_for_spec_review=True,row_id=spec['row_id'],hierarchy_bytes_verified=False,cgroup_equivalent=False,numerical_run=False)));return
    if not all((args.admission,args.ledger,args.output)):parser.error('--run requires explicit --admission, --ledger and --output')
    limits=Limits(600,600,8*1024**3,min(os.sched_getaffinity(0)),cleanup_seconds=5)
    admission=Admission(args.admission,args.ledger,spec['row_id'],670)
    with admission as admission_sha:
        source=verify_source();bindings(spec)
        review=json.loads((ROOT/'review_clearance.json').read_bytes())
        if review.get('approved') is not True or review.get('source_sha256')!=source['source_sha256']:
            raise ValueError('Independent review clearance absent or source identity differs')
        out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
        spec.update(worker_output=str((out/'worker').resolve()),admission_sha256=admission_sha,
            admission_path=str(Path(args.admission).resolve()),ledger_path=str(Path(args.ledger).resolve()))
        atomic(out/'worker_spec.json',spec)
        guard_read,guard_write=os.pipe()
        os.write(guard_write,canon(dict(parent_pid=os.getpid(),spec_sha256=sha(out/'worker_spec.json'),cpu=limits.cpu)))
        os.close(guard_write)
        try:
            receipt=run([sys.executable,str(Path(__file__).resolve()),'--worker',str((out/'worker_spec.json').resolve()),
                '--worker-guard-fd',str(guard_read)],output_dir=out/'supervision',limits=limits,cwd=ROOT,pass_fds=(guard_read,),parent_cpu_limit=(50,60),
                extra_env={'MPLCONFIGDIR':str((out/'cache/matplotlib').resolve()),'XDG_CACHE_HOME':str((out/'cache').resolve())})
        finally:os.close(guard_read)
        receipt['controller_cpu_seconds_including_preflight']=time.process_time()
        atomic(out/'supervision/receipt.json',receipt)
        admission.record(receipt)
        print(json.dumps(receipt,sort_keys=True))
        if receipt['reason'] in ('wall_timeout','cpu_limit'):return 124
        if receipt['reason']!='success':raise RuntimeError('Diagnostic worker/supervisor failure; remaining attempts blocked')

if __name__=='__main__':raise SystemExit(main() or 0)
