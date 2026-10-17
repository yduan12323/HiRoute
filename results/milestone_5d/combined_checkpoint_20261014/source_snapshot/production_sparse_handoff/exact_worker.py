"""Separately supervised production sparse exact worker; reviewed admission required."""
import hashlib, json, os, resource, sys, time, shutil, subprocess, stat
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
OLD=BASE/'optimized_od06_phase2'
SPARSE=BASE/'sparse_feasible_handoff_work'
sys.path[:0]=[str(SPARSE/'src'),str(SPARSE),str(OLD/'runner/src'),str(OLD/'runner'),str(OLD/'deps')]
from cloud_adapter import sha,atomic
from seed_only_launcher import bindings,load_graph,verify_source

def closure_check(spec):
    for name,digest in spec['source_sha256'].items():
        if sha(BASE/name)!=digest:raise ValueError('Source closure differs: '+name)
    if sha(ROOT/'exact_manifest.json')!=sys.argv[2]:raise ValueError('Manifest changed')

def main():
    if len(sys.argv)!=5 or not stat.S_ISFIFO(os.fstat(int(sys.argv[4])).st_mode):raise ValueError('Supervised parent pipe required')
    guard=json.loads(os.read(int(sys.argv[4]),16384));os.close(int(sys.argv[4]))
    if guard!=dict(parent_pid=os.getppid(),manifest_sha256=sys.argv[2],method=sys.argv[3]):raise ValueError('Supervisor binding differs')
    spec=json.loads((ROOT/'exact_manifest.json').read_bytes())
    out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
    if (resource.getrlimit(resource.RLIMIT_AS)!=(8*1024**3,)*2 or
        resource.getrlimit(resource.RLIMIT_CPU)!=(595,596) or
        len(os.sched_getaffinity(0))!=1 or os.getpgid(0)!=os.getpid()):
        raise ValueError('Required process containment absent')
    router=None;start=time.monotonic();cpu=time.process_time()
    def stage(s,**kw):
        value=dict(stage=s,wall_s=time.monotonic()-start,cpu_s=time.process_time()-cpu,**kw)
        atomic(out/'stage.json',value)
        with (out/'phases.jsonl').open('a') as f:
            f.write(json.dumps(value,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
    try:
        closure_check(spec);verify_source()
        ledger=json.loads((ROOT/'exact_ledger.json').read_bytes())
        if ledger['manifest_sha256']!=sys.argv[2] or ledger.get('blocked') or ledger['attempts'][-1]['method']!=sys.argv[3] or ledger['attempts'][-1]['state']!='reserved':raise ValueError('No active method reservation')
        if sha(sys.executable)!=spec['interpreter']['sha256']:raise ValueError('Interpreter differs')
        for path,digest in spec['toolchain_sha256'].items():
            if sha(path)!=digest:raise ValueError('Compiler toolchain differs')
        import importlib.metadata
        for name,version in spec['runtime_packages'].items():
            if importlib.metadata.version(name)!=version:raise ValueError('Runtime package version differs')
        m,qs,row,b,query,selected=bindings(spec['input_spec'])
        hierarchy=BASE/spec['hierarchy_path']
        if sha(hierarchy)!=m['input_sha256']['hierarchy'] or hierarchy.stat().st_size!=5271372:raise ValueError('Hierarchy bytes differ')
        checkpoint=BASE/spec['checkpoint_path']
        if sha(checkpoint)!=spec['checkpoint_sha256']:raise ValueError('Snapshot differs')
        from microplan.routing import ExactRouter
        from timecut5.feasible_incumbent import recover_feasible_incumbent,verifier_sources,canonical
        from timecut5.real_legs import RealSite
        from timecut5.real_adapter import site_catalog_digest
        from timecut5.road_provider import TableFreeRoadSelectedLegProvider
        from timecut5.sparse_seed import SparseSeedCatalog
        sites={s['site_id']:RealSite(s['site_id'],s['anchor_id'],tuple(s['effects'])) for s in selected}
        if len(sites)!=128 or site_catalog_digest(sites)!=b['site_catalog_sha256']:raise ValueError('Site binding differs')
        anchors=list(dict.fromkeys([query['origin']]+[s.anchor_id for s in sites.values()]+[query['destination']]))
        anodes={a:int(a.removeprefix('road:')) for a in anchors}
        if hashlib.sha256(canonical(anodes)).hexdigest()!=b['anchor_catalog_sha256']:raise ValueError('Anchor binding differs')
        if verifier_sources()!=spec['approved_verifier_sha256']:raise ValueError('Verifier closure differs')
        graph_dir=Path(spec['input_spec']['graph_dir'])
        import pyarrow.parquet as pq
        metadata=json.loads((graph_dir/'metadata.json').read_bytes())
        if (metadata['directed'] is not True or metadata['units']['length']!='metres' or metadata['units']['travel_time']!='seconds' or
            pq.ParquetFile(graph_dir/'nodes.parquet').metadata.num_rows!=metadata['node_count'] or
            pq.ParquetFile(graph_dir/'edges.parquet').metadata.num_rows!=metadata['edge_count']):raise ValueError('Graph metadata/row counts differ')
        for fn in ['nodes.parquet','edges.parquet']:
            if metadata['files'][fn]['sha256']!=sha(graph_dir/fn) or metadata['files'][fn]['size_bytes']!=(graph_dir/fn).stat().st_size:raise ValueError('Graph file metadata differs')
        stage('inputs_verified',hierarchy_bytes_verified=True)
        # Prior reviewed loader preserves on-disk Parquet row order. No edge sort,
        # remap, duplicate collapse, weight conversion or replacement hierarchy.
        graph=load_graph(graph_dir)
        for a in [graph.source,graph.target,*graph.weights.values()]:a.flags.writeable=False
        stage('graph_loaded',nodes=graph.node_count,edges=graph.edge_count)
        compiler=shutil.which('g++')
        if sha(compiler)!=spec['compiler_sha256']:raise ValueError('Compiler differs')
        router=ExactRouter(graph,{'compiler':compiler,'compiler_flags':['-O3','-std=c++17']},out/'road_native')
        if router.provenance['source_sha256']!=m['source_sha256']['src/microplan/routing.cpp']:raise ValueError('Native source differs')
        binary=(out/'road_native/routing.so').resolve()
        if str(binary) not in Path('/proc/self/maps').read_text():raise ValueError('Expected native binary not loaded')
        native=dict(router.provenance,binary_path=str(binary),binary_sha256=sha(binary),compiler_sha256=sha(compiler),loaded_binary_path_verified=True)
        atomic(out/'native_provenance.json',native)
        provider=TableFreeRoadSelectedLegProvider(graph,router,anodes,nodes_sha256=m['input_sha256']['graph_nodes'],edges_sha256=m['input_sha256']['graph_edges'],router_sha256=router.provenance['source_sha256'],anchor_catalog_sha256=b['anchor_catalog_sha256'],source_cache_max_bytes=256*1024**2,source_cache_max_sources=1)
        catalog=SparseSeedCatalog(provider,sites,origin_anchor=query['origin'],destination_anchor=query['destination'],nodes_path=graph_dir/'nodes.parquet',edges_path=graph_dir/'edges.parquet',site_catalog_sha256=b['site_catalog_sha256'],hierarchy_sha256=query['hierarchy_sha256'],candidate_sha256=b['candidate_sha256'])
        if catalog.domain_sha256!=b['sparse_domain_sha256']:raise ValueError('Domain differs')
        stage('fresh_provider_ready',source_runs=provider.source_run_count)
        from production_boundary import run_production
        def save(name,value):
            # Serialize exact rational result coordinates without float conversion.
            atomic(out/name,json.loads(json.dumps(value,default=str)))
        def router_factory(conservative):
            stage('landmark_native_compilation_started')
            r=ExactRouter(conservative,{'compiler':compiler,'compiler_flags':['-O3','-std=c++17']},out/'landmark_native')
            bp=(out/'landmark_native/routing.so').resolve()
            if str(bp) not in Path('/proc/self/maps').read_text() or r.provenance['source_sha256']!=m['source_sha256']['src/microplan/routing.cpp']:raise ValueError('Landmark native chain differs')
            save('landmark_native_provenance.json',dict(r.provenance,binary_path=str(bp),binary_sha256=sha(bp),compiler_sha256=sha(compiler),loaded_binary_path_verified=True))
            original_full=r.full
            def observed_full(root,reverse=False):
                direction='reverse' if reverse else 'forward'
                stage('landmark_'+direction+'_started')
                result=original_full(root,reverse=reverse)
                stage('landmark_'+direction+'_completed')
                return result
            r.full=observed_full
            stage('landmark_native_compiled_loaded_verified')
            return r
        inputs=dict(checkpoint_path=checkpoint,expected_checkpoint_sha256=spec['checkpoint_sha256'],query_bytes=canonical(query),catalog=catalog,nodes_path=graph_dir/'nodes.parquet',edges_path=graph_dir/'edges.parquet',router_source_path=OLD/'runner/src/microplan/routing.cpp',approved_verifier_sha256=spec['approved_verifier_sha256'])
        def complete_closure_check():
            closure_check(spec)
            for filename in ['native_provenance.json','landmark_native_provenance.json']:
                info=json.loads((out/filename).read_bytes())
                if sha(info['binary_path'])!=info['binary_sha256']:raise ValueError('Native binary changed')
        result=run_production(inputs=inputs,spec=spec,native=native,method=sys.argv[3],router_factory=router_factory,stage=stage,save=save,closure_check=complete_closure_check)
        save('exact_result.json',dict(result,denominator_included=False,region_policy=spec['region_policy'],original_hierarchy_equivalence=False,all_pairs_built=False,heuristic_search_started=False))
    except BaseException as e:
        atomic(out/'error.json',dict(type=type(e).__name__,message=str(e),last_stage=json.loads((out/'stage.json').read_bytes()) if (out/'stage.json').exists() else None));raise
    finally:
        if router is not None:router.close()
if __name__=='__main__':main()
