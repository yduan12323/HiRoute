"""UNLAUNCHED diagnostics worker template; new manifest/controller review required."""
import hashlib, json, os, resource, sys, time, shutil, subprocess, stat
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]
OLD=BASE/'optimized_od06_phase2'
SPARSE=BASE/'sparse_feasible_handoff_work'
sys.path[:0]=[str(ROOT.parent/'candidate/src'),str(ROOT.parent/'integration'),str(SPARSE/'src'),str(SPARSE),str(OLD/'runner/src'),str(OLD/'runner'),str(OLD/'deps')]
from cloud_adapter import sha,atomic
from seed_only_launcher import bindings,load_graph,verify_source

def closure_check(spec):
    for name,digest in spec['source_sha256'].items():
        if sha(BASE/name)!=digest:raise ValueError('Source closure differs: '+name)
    if sha(ROOT/'launch_manifest.json')!=sys.argv[2]:raise ValueError('Manifest changed')

def cache_configuration(spec):
    """Only the independently reviewed two-source/512-MiB trial is admitted."""
    expected=dict(source_cache_max_bytes=512*1024**2,source_cache_max_sources=2)
    actual={key:spec['cache'].get(key) for key in expected}
    if any(type(value) is not int for value in actual.values()) or actual!=expected:
        raise ValueError('Cache trial configuration differs')
    return actual


def main():
    if len(sys.argv)!=6 or sys.argv[5] not in ('search','verify') or not stat.S_ISFIFO(os.fstat(int(sys.argv[4])).st_mode):raise ValueError('Supervised parent pipe required')
    guard=json.loads(os.read(int(sys.argv[4]),16384));os.close(int(sys.argv[4]))
    if guard!=dict(parent_pid=os.getppid(),manifest_sha256=sys.argv[2],method=sys.argv[3],mode=sys.argv[5]):raise ValueError('Supervisor binding differs')
    spec=json.loads((ROOT/'launch_manifest.json').read_bytes())
    if spec.get('schema')!='hiroute.durable_incumbent_launch.v1':
        raise ValueError('A new diagnostics-specific reviewed protocol is required')
    if spec.get('containment')!={'rlimit_cpu':[295,296],'preparation_wall_s':180,'exact_wall_s':120,'total_wall_s':300,'parent_cpu':[50,60],'address_space_bytes':8*1024**3,'cleanup_s':3}:
        raise ValueError('Diagnostics phase containment differs')
    cache_configuration(spec)
    if spec.get('progress_enabled') is not True:
        raise ValueError('This experimental worker requires opt-in diagnostics')
    out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
    if (resource.getrlimit(resource.RLIMIT_AS)!=(8*1024**3,)*2 or
        resource.getrlimit(resource.RLIMIT_CPU)!=(tuple(spec['containment']['rlimit_cpu']) if sys.argv[5]=='search' else (115,116)) or
        len(os.sched_getaffinity(0))!=1 or os.getpgid(0)!=os.getpid()):
        raise ValueError('Required process containment absent')
    router=None;verifier_router=None;start=time.monotonic();cpu=time.process_time();phase_identity=None
    def stage(s,**kw):
        if s=='exact_engine_started':
            from phase_supervisor import publish_exact_start
            if phase_identity is None:raise ValueError('Exact phase identity not prepared')
            publish_exact_start(out/'exact_started.json',phase_identity)
        value=dict(stage=s,wall_s=time.monotonic()-start,cpu_s=time.process_time()-cpu,**kw)
        atomic(out/'stage.json',value)
        with (out/'phases.jsonl').open('a') as f:
            f.write(json.dumps(value,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
    try:
        closure_check(spec);verify_source()
        ledger=json.loads((ROOT/'ledger.json').read_bytes())
        if ledger['manifest_sha256']!=sys.argv[2] or ledger.get('blocked') or ledger['attempts'][-1]['method']!=sys.argv[3] or ledger['attempts'][-1]['mode']!=sys.argv[5] or ledger['attempts'][-1]['state']!='reserved':raise ValueError('No active method reservation')
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
        provider=TableFreeRoadSelectedLegProvider(graph,router,anodes,nodes_sha256=m['input_sha256']['graph_nodes'],edges_sha256=m['input_sha256']['graph_edges'],router_sha256=router.provenance['source_sha256'],anchor_catalog_sha256=b['anchor_catalog_sha256'],**(cache_configuration(spec) if sys.argv[5]=='search' else dict(source_cache_max_bytes=0,source_cache_max_sources=1)))
        catalog=SparseSeedCatalog(provider,sites,origin_anchor=query['origin'],destination_anchor=query['destination'],nodes_path=graph_dir/'nodes.parquet',edges_path=graph_dir/'edges.parquet',site_catalog_sha256=b['site_catalog_sha256'],hierarchy_sha256=query['hierarchy_sha256'],candidate_sha256=b['candidate_sha256'])
        if catalog.domain_sha256!=b['sparse_domain_sha256']:raise ValueError('Domain differs')
        stage('fresh_provider_ready',source_runs=provider.source_run_count,cache_configuration=cache_configuration(spec))
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
        def progress_factory(exact_query,active_provider):
            nonlocal phase_identity
            from phase_supervisor import identity_digest
            effective_query_sha256=hashlib.sha256(canonical(exact_query)).hexdigest()
            if effective_query_sha256!=spec['effective_exact_query_sha256']:
                raise ValueError('Effective exact query differs from protocol')
            phase_identity=dict(method=sys.argv[3],manifest_sha256=sys.argv[2],
                effective_query_sha256=effective_query_sha256,domain_sha256=catalog.domain_sha256,
                source_closure_sha256=identity_digest(spec['source_sha256']))
            from timecut5.exact_progress import ExactSearchProgress
            observer=ExactSearchProgress(out/'exact_progress',
                query_sha256=hashlib.sha256(canonical(exact_query)).hexdigest(),domain_sha256=catalog.domain_sha256,
                source_sha256=spec['source_sha256'],provider=active_provider,
                interval=spec['progress_interval_seconds'],
                max_events=spec['progress_max_events'])
            stage('exact_diagnostics_ready',effective_query_sha256=hashlib.sha256(canonical(exact_query)).hexdigest(),
                  progress_snapshot=str(out/'exact_progress/progress.json'))
            return observer
        from sparse_durable_session import SparseDurableSession,recover_sparse_record
        from production_boundary import runtime_policy
        from timecut5.road_provider import TIE_POLICY
        def source_supplier(active_provider,binary_path):
            closure_check(spec)
            # All source hashing and verifier work is charged to this process.
            current=dict(nodes=sha(graph_dir/'nodes.parquet'),edges=sha(graph_dir/'edges.parquet'),
                router=sha(OLD/'runner/src/microplan/routing.cpp'),anchors=hashlib.sha256(canonical(anodes)).hexdigest(),
                tie_policy=hashlib.sha256(TIE_POLICY.encode()).hexdigest(),native_binary=sha(binary_path))
            current.update({'source:'+name:sha(BASE/name) for name in spec['source_sha256']})
            return current
        sessions=[]
        def durable_factory(exact_query,admission,search_provider,method):
            nonlocal verifier_router
            verifier_router=ExactRouter(graph,{'compiler':compiler,'compiler_flags':['-O3','-std=c++17']},out/'verifier_native')
            vp=(out/'verifier_native/routing.so').resolve()
            if str(vp) not in Path('/proc/self/maps').read_text() or verifier_router.provenance['source_sha256']!=native['source_sha256'] or sha(vp)!=native['binary_sha256']:
                raise ValueError('Independent verifier native provenance differs')
            vprovider=TableFreeRoadSelectedLegProvider(graph,verifier_router,anodes,nodes_sha256=m['input_sha256']['graph_nodes'],edges_sha256=m['input_sha256']['graph_edges'],router_sha256=verifier_router.provenance['source_sha256'],anchor_catalog_sha256=b['anchor_catalog_sha256'],source_cache_max_bytes=0,source_cache_max_sources=1)
            vcatalog=SparseSeedCatalog(vprovider,sites,origin_anchor=query['origin'],destination_anchor=query['destination'],nodes_path=graph_dir/'nodes.parquet',edges_path=graph_dir/'edges.parquet',site_catalog_sha256=b['site_catalog_sha256'],hierarchy_sha256=query['hierarchy_sha256'],candidate_sha256=b['candidate_sha256'])
            def check():
                complete_closure_check()
                if runtime_policy(inputs,spec,native)!=admission.policy_bytes:raise ValueError('Admitted runtime policy changed')
                if sha(vp)!=native['binary_sha256']:raise ValueError('Verifier binary changed')
            session=SparseDurableSession(out/'durable_incumbent.json',method=method,exact_query=exact_query,
                admission=admission,search_provider=search_provider,verifier_catalog=vcatalog,
                source_supplier=lambda:source_supplier(vprovider,vp),policy_check=check)
            sessions.append(session)
            stage('initial_durable_witness_verified',path=str(session.store.path),key=list(map(str,session.initial_key[:3])))
            return session
        if sys.argv[5]=='verify':
            original=ROOT/('search_'+sys.argv[3])
            record=original/'durable_incumbent.json'
            if not record.is_file():
                save('verification_result.json',dict(status='no_durable_witness',feasibility='unknown'))
                return
            original_native=json.loads((original/'native_provenance.json').read_bytes())
            expected_path=(original/'road_native/routing.so').resolve()
            if (original_native['binary_path']!=str(expected_path) or sha(expected_path)!=native['binary_sha256'] or
                original_native['binary_sha256']!=native['binary_sha256'] or original_native['source_sha256']!=native['source_sha256'] or
                original_native['compiler_sha256']!=native['compiler_sha256']):raise ValueError('Original native provenance changed')
            expected_policy=json.loads(runtime_policy(inputs,spec,native));expected_policy['native']=original_native
            expected_policy=canonical(expected_policy)
            if canonical(json.loads((original/'runtime_policy.json').read_bytes()))!=expected_policy:raise ValueError('Saved policy differs from independently reconstructed policy')
            before=sha(record)
            def check_recovery():
                closure_check(spec)
                if sha(record)!=before or sha(binary)!=native['binary_sha256']:raise ValueError('Recovery sources changed')
                if canonical(json.loads((original/'runtime_policy.json').read_bytes()))!=expected_policy:raise ValueError('Saved policy changed')
            exact_query=dict(query,H_ref=spec['initial_max_depth'])
            witness,key=recover_sparse_record(record,exact_query=exact_query,policy_bytes=expected_policy,
                verifier_catalog=catalog,source_supplier=lambda:source_supplier(provider,binary),policy_check=check_recovery)
            from timecut5.provenance import witness_dict,primitive
            save('verification_result.json',dict(status='verified_feasible_only',lex_key=primitive(key),witness=witness_dict(witness),
                record_sha256=before,record_path=str(record),source_runs=provider.source_run_count,requested_pairs=len(provider.legs),
                initial_primary_upper=spec['initial_upper_bound'],improved_primary=key[0]<__import__('fractions').Fraction(spec['initial_upper_bound']),
                exact_optimum_claimed=False,global_gap=None))
            return
        result=run_production(inputs=inputs,spec=spec,native=native,method=sys.argv[3],router_factory=router_factory,stage=stage,save=save,closure_check=complete_closure_check,progress_factory=progress_factory,durable_factory=durable_factory)
        save('exact_result.json',dict(result,denominator_included=False,region_policy=spec['region_policy'],original_hierarchy_equivalence=False,all_pairs_built=False,heuristic_search_started=False))
    except BaseException as e:
        atomic(out/'error.json',dict(type=type(e).__name__,message=str(e),last_stage=json.loads((out/'stage.json').read_bytes()) if (out/'stage.json').exists() else None));raise
    finally:
        if verifier_router is not None:verifier_router.close()
        if router is not None:router.close()
if __name__=='__main__':main()
