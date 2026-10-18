"""Separate OD10 N32 HIER full/target+energy diagnostic with bounded heartbeat."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.scalability_development_v1 import run as development
from experiments.search_extensions_v1.run import require_exact_phase
from timecut5.exact_progress import ExactSearchProgress, operation

SCHEMA = 'hiroute.scalability_profile.v1'
CASE = development.CASE
ARMS = ('baseline_full', 'destination_target_only')
CONFIGS = {arm:dict(routing='full' if arm=='baseline_full' else 'destination_target',
    terminal_energy=True,reducer='reduce_frontier',onward_alt=False,coalescing=False)
    for arm in ARMS}
OBSERVER = dict(interval_seconds=0.5,max_events=32,max_snapshot_bytes=262144,
    persistence='rate_limited_initial_final_and_heartbeat',enabled_in_both_arms=True,
    inclusive_nested_timings=True,global_gap=False)
POLICY = dict(development.POLICY,routing='one_factor_full_vs_destination_target',
    candidate_count=32,observer=OBSERVER,cross_size_seed_policy='not_applicable_fixed_N32',
    method='HIER',reducer='reduce_frontier')


def source_identity(repo):
    identity=development.source_identity(repo)
    closure=dict(identity['closure'])
    for path in sorted((Path(repo)/'experiments/scalability_profile_v1').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            closure[str(path.relative_to(repo))]=base.file_hash(path)
    return dict(identity,closure=closure,closure_sha256=base.digest(closure))


def prospective():
    return dict(schema=SCHEMA,launchable=False,status='prospective_pending_source_review',
        candidate_count=32,policy=POLICY,arms=CONFIGS,order=list(ARMS),observer=OBSERVER,
        denominator=development.DENOMINATOR,reserve_plan=development.RESERVE,
        limits=base.LIMITS,cache_policy=base.CACHE_POLICY,inputs=development.prospective()['inputs'],
        repo=None,input_directory=None,compiler=None,source=None,auto_next_gate=False,
        holdout=False,historical_pooling=False,require_positive_result=False)


def _manifest(path, expected_sha256):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Profile manifest digest differs')
    manifest=json.loads(raw);expected=prospective()
    if manifest.get('schema')!=SCHEMA or manifest.get('launchable') is not True:
        raise ValueError('Prospective profile plan is not launchable')
    runtime={'launchable','status','repo','input_directory','compiler','source'}
    if set(manifest)!=set(expected) or any(manifest[k]!=v for k,v in expected.items() if k not in runtime):
        raise ValueError('Frozen profile policy differs')
    compiler=manifest['compiler']
    if (set(compiler)!={'path','sha256','version','flags'} or base.file_hash(compiler['path'])!=compiler['sha256'] or
        subprocess.check_output([compiler['path'],'--version'],text=True)!=compiler['version'] or
        compiler['flags']!=['-O3','-std=c++17']):raise ValueError('Pinned compiler differs')
    if manifest['source']!=source_identity(manifest['repo']):raise ValueError('Profile executable source closure differs')
    for name,binding in manifest['inputs'].items():
        path=Path(manifest['input_directory'])/name
        if path.stat().st_size!=binding['size'] or base.file_hash(path)!=binding['sha256']:
            raise ValueError('Profile input differs: '+name)
    return manifest


class ProfileProgress(ExactSearchProgress):
    """Reuse stock observation while bounding fsync rate and recording write gaps.

    Throttling affects only diagnostic snapshots. It never changes the solver,
    native routing, event ordering or state. Final snapshots bypass rate limiting.
    """
    def __init__(self, output_dir, **kwargs):
        kwargs.setdefault('interval',OBSERVER['interval_seconds'])
        kwargs.setdefault('max_events',OBSERVER['max_events'])
        super().__init__(output_dir,**kwargs)
        self._write_gate=threading.Lock()
        self._last_persist_ns=None
        self.state.update(profile_schema=SCHEMA,persist_attempts=0,rate_limited_calls=0,
            maximum_observed_write_gap_ns=0,
            synchronous_operation_boundaries='Rate-limited; initial/final and heartbeat snapshots, no per-operation fsync guarantee',
            observer_overhead_claim='Persistence clock only; total observer overhead is not fully measured')

    def metrics(self):
        if self.provider is None:return {}
        # Cumulative counts/times only: cache occupancy is not a counter delta.
        result={name:getattr(self.provider,name) for name in ('source_run_count','source_run_distinct_count',
            'source_run_repeat_count','source_run_untracked_count','source_cache_hits','source_cache_evictions',
            'source_cache_skips','target_run_count','route_wall_ns','route_process_cpu_ns')
            if hasattr(self.provider,name)}
        result['selected_pairs']=len(self.provider.legs)
        for node,count in getattr(self.provider,'_source_runs_by_node',{}).items():
            result['source_runs_node_'+str(node)]=count
        return result

    def persist(self):
        if not self._write_gate.acquire(blocking=False):return
        try:
            now=time.monotonic_ns()
            force=self.state['status'] in ('returned','error')
            if self._last_persist_ns is not None and not force and now-self._last_persist_ns<int(self.interval*1e9):
                with self.lock:self.state['rate_limited_calls']+=1
                return
            with self.lock:
                self.state['persist_attempts']+=1
                if self._last_persist_ns is not None:
                    self.state['maximum_observed_write_gap_ns']=max(self.state['maximum_observed_write_gap_ns'],now-self._last_persist_ns)
                if self.provider is not None:
                    self.state['provider_end_gauges']=dict(source_cache_bytes=self.provider.source_cache_bytes,
                        source_cache_entries=len(self.provider._source_labels))
            self._last_persist_ns=now
            super().persist()
        finally:self._write_gate.release()


class ProfileDomain(base.NativeDomain):
    def __init__(self, *, arm,manifest_binding,**kwargs):
        if arm not in CONFIGS:raise ValueError('Unknown profile arm')
        self.arm=arm;self.config=dict(CONFIGS[arm]);self._config=base.canonical(self.config)
        self.manifest_binding=manifest_binding;self._manifest=manifest_binding
        super().__init__(**kwargs)

    def check(self):
        super().check()
        if (base.canonical(self.config)!=self._config or self.config!=CONFIGS[self.arm] or
            self.manifest_binding!=self._manifest):raise ValueError('Profile runtime policy changed')

    def context(self, role):
        from timecut5.routing_config import RoutingConfig,TerminalEnergyConfig
        self.check();query=json.loads(self.query_bytes)
        anchors={a:int(a.removeprefix('road:')) for a in [query['origin'],query['destination'],*[s.anchor_id for s in self.sites.values()]]}
        self._serial+=1;graph=self.graph_factory();base.cache_capacity(self.cache_policy,graph.node_count)
        context=RoutingConfig(self.config['routing'],TerminalEnergyConfig()).create_context(
            graph,self.compiler,self.cache/str(self._serial),role=role,artifact=self.artifact,
            energy_artifact=self.energy_artifact,anchor_nodes=anchors,nodes_sha256=self.source_hashes['nodes'],
            edges_sha256=self.source_hashes['edges'],anchor_catalog_sha256=base.digest(anchors),**self.cache_policy)
        if any(getattr(context.provider,k)!=v for k,v in self.cache_policy.items()):
            context.close();raise ValueError('Profile provider cache policy differs')
        return context

    def durable_binding(self, seed):
        binding=super().durable_binding(seed)
        binding['domain_sha256']=base.digest([binding['domain_sha256'],SCHEMA,self.arm,self.config,self.manifest_binding])
        binding['source_sha256']=dict(binding['source_sha256'],profile_policy=base.digest([self.arm,self.config,self.manifest_binding]))
        return binding

    def make_bound(self, context, strategy):
        self._search_provider=context.provider
        return super().make_bound(context,'indexed')

    def solve_exact(self, problem,witness,key,bound,store):
        from timecut5.hierarchy import _solve_hierarchical_problem
        binding=self.durable_binding(self._seed)
        observer=ProfileProgress(self._output/'progress',query_sha256=base.digest(json.loads(self.query_bytes)),
            domain_sha256=binding['domain_sha256'],source_sha256=binding['source_sha256'],provider=self._search_provider)
        observer.state.update(arm=self.arm,configuration=self.config,manifest_binding=self.manifest_binding,
            candidate_count=len(self.sites),Hmax=self._seed.max_depth)
        observer.state['timings']['durable_incumbent_callback']=dict(calls=0,wall_ns=0,cpu_ns=0,errors=0)
        observed_store=operation('durable_incumbent_callback')(store)
        try:
            return _solve_hierarchical_problem(problem,True,self.tree,witness,verified_primary_upper=key[0],
                bound_provider=bound,incumbent_hook=observed_store,progress_hook=observer)
        finally:
            self._observer_status=dict(io_error=observer.state['io_error'],heartbeat_error=observer.state.get('heartbeat_error'),
                status=observer.state['status'],persist_attempts=observer.state['persist_attempts'])

    def run_arm(self,strategy,seed,output,**kwargs):
        if strategy!=self.arm:raise ValueError('Profile arm differs')
        self._seed=seed;self._output=Path(output)
        result=super().run_arm('indexed',seed,output,**kwargs)
        result.update(schema=SCHEMA,strategy=self.arm,configuration=self.config,manifest_binding=self.manifest_binding,
            full_routing=self.config['routing']=='full',observer=self._observer_status,
            progress_sha256=base.file_hash(self._output/'progress/progress.json'))
        (self._output/'result.json').write_bytes(base.canonical(result));return result


def domain_factory(manifest,query,sites,cache,*,arm):
    if len(sites)!=32:raise ValueError('Profile requires original N32')
    directory,bindings=manifest['input_directory'],manifest['inputs']
    tree=base.original_tree((Path(directory)/'hierarchy.json').read_bytes(),bindings['hierarchy.json']['sha256'],list(sites))
    return ProfileDomain(arm=arm,manifest_binding=base.digest(manifest),graph_factory=lambda:base.load_graph(directory,bindings),
        query=query,sites=sites,tree=tree,source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache,compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def progress_binding(manifest,arm,common):
    seed=common['seed']
    ordinary=base.digest([common['query'],common['tree_sha256'],seed['site_sha256'],
        json.loads(seed['key_bytes']),seed['max_depth'],seed['native_sha256'],manifest['cache_policy']])
    manifest_binding=base.digest(manifest)
    sources=dict({n:manifest['inputs'][n+'.parquet']['sha256'] for n in ('nodes','edges')},
        source_closure=manifest['source']['closure_sha256'],
        **{'input:'+n:b['sha256'] for n,b in manifest['inputs'].items()},
        profile_policy=base.digest([arm,CONFIGS[arm],manifest_binding]))
    return base.digest([ordinary,SCHEMA,arm,CONFIGS[arm],manifest_binding]),sources


def read_progress(path,manifest,arm,common,*,search_status,completed_result=None):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>OBSERVER['max_snapshot_bytes']:
        raise ValueError('Missing or unbounded profile snapshot')
    raw=path.read_bytes();value=json.loads(raw)
    expected_domain,expected_sources=progress_binding(manifest,arm,common)
    if (value.get('domain_sha256')!=expected_domain or value.get('source_sha256')!=expected_sources or
        value.get('profile_schema')!=SCHEMA or value.get('arm')!=arm or value.get('configuration')!=CONFIGS[arm] or
        value.get('manifest_binding')!=base.digest(manifest) or value.get('candidate_count')!=32 or
        value.get('query_sha256')!=base.digest(common['query']) or value.get('Hmax')!=common['seed']['max_depth'] or
        value.get('status') not in ('running','returned') or value.get('io_error') is not None or value.get('heartbeat_error') is not None):
        raise ValueError('Profile snapshot binding or observer health differs')
    raw_sha=hashlib.sha256(raw).hexdigest()
    if search_status not in ('SUCCESS','TIMEOUT'):raise ValueError('Profile search outcome not admitted')
    final_health=False
    if search_status=='SUCCESS':
        if not isinstance(completed_result,dict):raise ValueError('Authenticated normal arm result required')
        final=completed_result.get('observer',{})
        if (completed_result.get('progress_sha256')!=raw_sha or completed_result.get('strategy')!=arm or
            completed_result.get('configuration')!=CONFIGS[arm] or completed_result.get('manifest_binding')!=base.digest(manifest) or
            final.get('status')!='returned' or 'io_error' not in final or 'heartbeat_error' not in final or
            final['io_error'] is not None or final['heartbeat_error'] is not None or value['status']!='returned'):
            raise ValueError('Authenticated final observer result is unhealthy or snapshot hash differs')
        final_health=True
    return dict(sha256=raw_sha,bytes=len(raw),status=value['status'],
        sampled_wall_ns=value['sampled_wall_ns'],last_active_stack=value['active_stack'],
        maximum_observed_write_gap_ns=value['maximum_observed_write_gap_ns'],
        timeout_snapshot_is_censored=search_status=='TIMEOUT',terminal_observer_health_proved=final_health)


def run_gate(path,sha256,output,cpu):
    manifest=_manifest(path,sha256)
    ledger=base._run_plan(path,sha256,output,cpu,scope='od02_gate',manifest_loader=_manifest,
        worker_module='experiments.scalability_profile_v1.run',fixed_cases=(CASE,),fixed_pairs=[[CASE,list(ARMS)]])
    ledger.update(scope='od10_n32_profile_gate',operational_admission=False,diagnostic_admission='inconclusive')
    try:
        if (ledger['status']!='COMPLETED' or ledger['denominator']!=5 or len(ledger['stages'])!=5 or
            len(ledger.get('arms',[]))!=2 or [a.get('strategy') for a in ledger['arms']]!=list(ARMS)):
            raise ValueError('Profile gate has incomplete stages')
        common=base.load_worker_result(Path(output)/('prepare-'+CASE),ledger['common'][CASE],'prepare',CASE)
        stages=ledger['stages']
        receipts=[ledger['common'][CASE]]
        for index,arm in enumerate(ledger['arms']):
            if arm['strategy']!=ARMS[index] or arm.get('case')!=CASE or arm.get('pair')!=0:
                raise ValueError('Profile arm identity differs')
            search,verified=arm['receipt'],arm['verification']
            if search['status'] not in ('SUCCESS','TIMEOUT') or verified['status']!='SUCCESS':
                raise ValueError('Profile receipt status not admitted')
            require_exact_phase(search)
            identity=search.get('phase_budget',{}).get('identity',{})
            if (identity.get('case_id')!=CASE or identity.get('strategy')!=arm['strategy'] or
                identity.get('arm_index')!=str(index) or identity.get('manifest_sha256')!=sha256 or
                identity.get('source_closure_sha256')!=manifest['source']['closure_sha256']):
                raise ValueError('Profile search phase identity differs')
            receipts.extend([search,verified])
            for position,op,receipt in ((1+2*index,'search',search),(2+2*index,'verify',verified)):
                if stages[position]!=dict(id=f'{op}-{index}',operation=op,case=CASE,strategy=arm['strategy'],status=receipt['status']):
                    raise ValueError('Profile stage/receipt differs')
            full=base.load_worker_result(Path(output)/f'verify-{index:02d}',verified,'verify',CASE,arm['strategy'])
            if arm['status']!=full['status']:raise ValueError('Profile verified outcome differs')
            completed=None
            if search['status']=='SUCCESS':
                completed=base.load_worker_result(Path(output)/f'arm-{index:02d}',search,'arm',CASE,arm['strategy'])
            arm['progress']=read_progress(Path(output)/f'arm-{index:02d}/artifacts/arm/progress/progress.json',
                manifest,arm['strategy'],common,search_status=search['status'],completed_result=completed)
        if (stages[0]!=dict(id='prepare-'+CASE,operation='prepare',case=CASE,status='SUCCESS') or
            ledger['common'][CASE]['status']!='SUCCESS' or any(not r.get('cleanup_verified') for r in receipts)):
            raise ValueError('Profile common receipt or cleanup differs')
        if all(a['receipt']['status']=='SUCCESS' for a in ledger['arms']):
            payloads=[]
            for index,arm in enumerate(ledger['arms']):
                finished=base.load_worker_result(Path(output)/f'arm-{index:02d}',arm['receipt'],'arm',CASE,arm['strategy'])
                payload=dict(finished['result']['result']);payload.pop('charges',None);payload.pop('witness_replayed',None)
                payloads.append(payload)
            if payloads[0]!=payloads[1]:raise ValueError('Completed exact answers disagree')
        ledger['operational_admission']=True
        ledger['diagnostic_admission']='admitted_observed_prefixes'
    except (KeyError,TypeError,ValueError,OSError) as exc:
        ledger['admission_error']=str(exc)
        if ledger['status']=='COMPLETED':ledger['status']='FAILED_ADMISSION'
    temporary=Path(output)/'ledger.tmp';temporary.write_bytes(base.canonical(ledger));os.replace(temporary,Path(output)/'ledger.json')
    return ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--freeze',action='store_true');mode.add_argument('--gate',action='store_true')
    mode.add_argument('--worker',choices=('prepare','arm','verify'))
    for name in ('manifest','manifest-sha256','output','input-directory','common','common-sha256','search-directory','search-receipt-sha256'):
        parser.add_argument('--'+name)
    parser.add_argument('--cpu',type=int);parser.add_argument('--case',choices=(CASE,));parser.add_argument('--strategy',choices=ARMS)
    args=parser.parse_args()
    if args.plan:print(json.dumps(prospective(),indent=2,sort_keys=True));return 0
    if args.freeze:
        if not args.output or not args.input_directory:parser.error('--freeze requires --output and --input-directory')
        root=Path.cwd().resolve();compiler=Path(shutil.which('g++')).resolve();manifest=prospective()
        manifest.update(launchable=True,status='frozen_profile_gate_not_launched',repo=str(root),input_directory=str(Path(args.input_directory).resolve()),
            compiler=dict(path=str(compiler),sha256=base.file_hash(compiler),version=subprocess.check_output([str(compiler),'--version'],text=True),flags=['-O3','-std=c++17']),source=source_identity(root))
        raw=base.canonical(manifest)
        with Path(args.output).open('xb') as stream:stream.write(raw)
        sha=hashlib.sha256(raw).hexdigest();_manifest(args.output,sha)
        print(json.dumps(dict(manifest=str(Path(args.output).resolve()),sha256=sha)));return 0
    if args.gate:
        if args.output is None or args.cpu is None or args.case is not None or args.strategy is not None:
            parser.error('--gate requires output/cpu and fixed cases/arms')
        return 0 if run_gate(args.manifest,args.manifest_sha256,args.output,args.cpu)['operational_admission'] else 1
    manifest=_manifest(args.manifest,args.manifest_sha256)
    if args.case!=CASE or (args.worker!='prepare' and args.strategy is None):parser.error('Worker requires fixed case/arm')
    if args.worker=='prepare':
        result=development.prepare_case(manifest,Path(os.environ['HIROUTE_OUTPUT_DIR'])/'prepared')
        result.update(schema=SCHEMA,profile_seed_policy='inherited_originalN32_full_energy_generation_double_replay')
        (Path(os.environ['HIROUTE_OUTPUT_DIR'])/'prepared/common.json').write_bytes(base.canonical(result))
    else:
        if args.worker=='verify':
            from experiments.mechanism_recovery_v1.supervisor import read_result
            require_exact_phase(read_result(args.search_directory))
        factory=lambda m,q,s,c:domain_factory(m,q,s,c,arm=args.strategy)
        base.worker(manifest,args.worker,args.case,args.common,args.common_sha256,args.strategy,args.search_directory,args.search_receipt_sha256,domain_factory=factory)
    _manifest(args.manifest,args.manifest_sha256)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(base.canonical(dict(status='COMPLETED',
        result=base.result_envelope(os.environ['HIROUTE_OUTPUT_DIR'],args.worker,args.case,args.strategy))))
    return 0


if __name__=='__main__':sys.exit(main())
