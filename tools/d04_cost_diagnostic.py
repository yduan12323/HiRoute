"""One frozen, instrumented D04 worker; no solver or routing policy changes."""
from __future__ import annotations
import argparse
from collections import defaultdict,OrderedDict
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


from hiroute.data.identity import domain_digest


def source_reuse_analysis(events,node_count,edge_count):
    """Offline fixed-trace work proxy, never a routing or runtime experiment.

    A build is charged a whole-graph upper bound. Covered future A* work is
    merely identified: perfect-potential reverse-DAG work is NOT assumed zero.
    """
    leaves=[e for e in events if e['kind']=='search_leaf' and e['settled_vertices']>0 and not e.get('error')]
    groups=defaultdict(list)
    for event in leaves:groups[event['source']].append(event)
    sources=[dict(source=s,misses=len(xs),distinct_targets=len({x['target'] for x in xs}),
        astar_s=sum(x['astar_s'] for x in xs),settled_vertices=sum(x['settled_vertices'] for x in xs),
        relaxed_edges=sum(x['relaxed_edges'] for x in xs)) for s,xs in groups.items()]
    sources.sort(key=lambda x:x['astar_s'],reverse=True)
    sketches=[]
    for capacity in (1,2):
        resident=OrderedDict();spent=defaultdict(int);builds=0;covered=[]
        for event in leaves:
            source=event['source']
            if source in resident:
                resident.move_to_end(source);covered.append(event);continue
            spent[source]+=event['relaxed_edges']
            if spent[source]>=edge_count:
                builds+=1;resident[source]=True;spent[source]=0
                while len(resident)>capacity:resident.popitem(last=False)
        sketches.append(dict(capacity=capacity,forward_tree_builds=builds,
            covered_later_pairs=len(covered),observed_covered_astar_s=sum(x['astar_s'] for x in covered),
            observed_covered_vertices=sum(x['settled_vertices'] for x in covered),
            observed_covered_relaxed_edges=sum(x['relaxed_edges'] for x in covered),
            full_tree_vertices_upper_work=builds*node_count,
            full_tree_edges_upper_work=builds*edge_count,
            canonical_path_vertices_lower_work=sum(x['path_edges']+1 if x['path_edges'] else 0 for x in covered)))
    return dict(offline_only=True,algorithm_executed=False,runtime_saving_estimate=None,
        completed_leaf_pairs=len(leaves),distinct_sources=len(groups),
        distinct_targets=len({e['target'] for e in leaves}),
        trigger='cumulative noncached A* edge relaxations for a source >= whole-graph edge count',
        incomplete_queries_excluded=True,sources=sources,sketches=sketches,
        caveat='Fixed interrupted trace only. Full-tree costs, equality-DAG work, queue costs, memory and future search remain unmeasured; no net runtime or optimality claim.')


class CostProfile:
    def __init__(self,metadata=None,clock=time.monotonic):
        self.clock=clock;self.metadata=metadata or {}
        self.seconds=defaultdict(float);self.calls=defaultdict(int)
        self.events=[];self.last_leaf=None;self.ub=None
        self.solving=False;self.seed=False;self.terminal=False
        self.route_wrapper_s=0.;self.window_start=None;self.window_end=None

    def event_kind(self):
        if self.seed:return 'seed_terminal' if self.terminal else 'seed_extension'
        if self.terminal:return 'terminal'
        return 'search_leaf' if self.solving else 'input_preparation'

    def mark_bound(self,value):
        event=self.last_leaf
        if event is not None and value is not None and self.ub is not None and value>self.ub:
            event['outcome']='late_bound_prune'

    def mark_child(self,state,site,child):
        event=self.last_leaf
        if event is None:return
        a=self.metadata.get(event['source'],{}).get('site_id',event['source'])
        b=self.metadata.get(event['target'],{}).get('site_id',event['target'])
        if (a,b)!=(state.anchor,site):
            self.calls['association_mismatch']+=1
            return
        event['outcome']='nonempty_child' if child.family else 'empty_family'
        event['depth']=len(state.plan)+1

    def summary(self):
        def aggregate(events):
            out=dict(requests=len(events),misses=sum(not e['cache_hit'] for e in events))
            for key in ('wall_s','native_s','astar_s','settled_vertices','relaxed_edges','path_edges'):
                out[key]=sum(e.get(key,0) for e in events)
            return out
        def groups(key,events):
            buckets=defaultdict(list)
            for e in events:buckets[key(e)].append(e)
            return {k:aggregate(v) for k,v in sorted(buckets.items())}
        leaves=[e for e in self.events if e['kind']=='search_leaf']
        targets=groups(lambda e:e['target'],leaves)
        hot=sorted(targets.items(),key=lambda kv:kv[1]['astar_s'],reverse=True)[:10]
        for target,row in hot:
            row['distinct_sources']=len({e['source'] for e in leaves if e['target']==target and not e['cache_hit']})
            row['site_id']=self.metadata.get(target,{}).get('site_id',target)
        end=self.window_end if self.window_end is not None else self.clock()
        total=0. if self.window_start is None else end-self.window_start
        measured=sum(self.seconds.values())
        return dict(diagnostic_only=True,performance_comparison=False,
            measurement_window_s=total,exclusive_seconds=dict(self.seconds),
            residual_other_s=total-measured,calls=dict(self.calls),
            routing=aggregate(self.events),
            by_kind=groups(lambda e:e['kind'],self.events),
            leaf_outcomes=groups(lambda e:e['outcome'],leaves),
            leaf_geometry=groups(lambda e:('backward' if e.get('backward') else 'forward_or_equal')+
                ('_wide' if e.get('wide') else '_inner'),leaves),
            leaf_miss_work_bins=groups(lambda e:('0' if e['settled_vertices']==0 else
                '<10k' if e['settled_vertices']<10000 else '<100k' if e['settled_vertices']<100000
                else '<1m' if e['settled_vertices']<1000000 else '>=1m'),
                [e for e in leaves if not e['cache_hit']]),
            hottest_targets=[dict(target=k,**v) for k,v in hot])


class MeasuredProvider:
    """Observe the existing provider, preserving its cache, check and values."""
    def __init__(self,provider,profile):self.provider=provider;self.profile=profile
    def __getattr__(self,name):return getattr(self.provider,name)
    @property
    def check(self):return self.provider.check
    @check.setter
    def check(self,value):self.provider.check=value
    def _timed_scalar(self,name,*args,**kwargs):
        start=self.profile.clock()
        try:return getattr(self.provider,name)(*args,**kwargs)
        finally:
            bucket='landmark_preparation_s' if name=='prepare_landmarks' else 'scalar_relaxation_s'
            self.profile.seconds[bucket]+=self.profile.clock()-start
            self.profile.calls[bucket]+=1
    def prepare_landmarks(self,*args,**kwargs):return self._timed_scalar('prepare_landmarks',*args,**kwargs)
    def distances_from(self,*args,**kwargs):return self._timed_scalar('distances_from',*args,**kwargs)
    def distances_to(self,*args,**kwargs):return self._timed_scalar('distances_to',*args,**kwargs)
    def _counters(self):
        # Native metrics are O(number of scalar workspaces), not a scan of the
        # Python path cache. These queries do not mutate solver/routing counters.
        query=getattr(self.provider,'_query',None)
        return query('metrics') if query else self.provider.metrics()
    def selected_leg(self,source,target):
        p=self.profile;outer=p.clock();kind=p.event_kind()
        cache=getattr(self.provider,'_leg_cache',{})
        hit=(source,target) in cache
        before={} if hit else self._counters()
        start=p.clock();result=None;error=None
        try:
            result=self.provider.selected_leg(source,target)
            return result
        except BaseException as exc:
            error=type(exc).__name__
            raise
        finally:
            wall=p.clock()-start
            after={} if hit else self._counters()
            delta=lambda key:after.get(key,0)-before.get(key,0)
            a,b=p.metadata.get(source,{}),p.metadata.get(target,{})
            event=dict(source=source,target=target,kind=kind,cache_hit=hit,wall_s=wall,
                native_s=delta('selected_leg_time_s'),astar_s=delta('astar_time_s'),
                settled_vertices=delta('astar_settled_vertices'),relaxed_edges=delta('astar_relaxed_edges'),
                path_edges=0 if result is None else len(result.edges),
                outcome='interrupted' if error else 'unreachable' if result is None else 'selected',
                error=error,backward=b.get('progress',0)<a.get('progress',0),
                wide=max(a.get('corridor_distance_m',0),b.get('corridor_distance_m',0))>50000)
            p.events.append(event)
            if kind=='search_leaf':p.last_leaf=event
            wrapper=p.clock()-outer
            p.route_wrapper_s+=wrapper
            p.seconds['selected_leg_python_and_native_s']+=wall
            p.seconds['route_counter_and_adapter_overhead_s']+=wrapper-wall
    def close(self):
        self.profile.window_end=self.profile.clock()
        return self.provider.close()


@contextmanager
def instrument(profile):
    from hiroute.exact import scale,scale_bounds,road_index
    with ExitStack() as stack:
        def timed(module,name,bucket,after=None):
            original=getattr(module,name)
            def wrapped(*args,**kwargs):
                start=profile.clock();result=None
                try:
                    result=original(*args,**kwargs)
                    return result
                finally:
                    profile.seconds[bucket]+=profile.clock()-start
                    profile.calls[bucket]+=1
                    if after is not None:after(args,result)
            stack.enter_context(patch.object(module,name,wrapped))
        # Both functions are imported locally by solve_scale after these patches.
        original_bound=scale_bounds.completion_bound
        def bound(*args,**kwargs):
            caller=sys._getframe(1).f_code.co_name
            bucket='leaf_completion_bound_s' if caller=='solve_scale' else 'region_completion_bound_s'
            start=profile.clock();result=None
            try:
                result=original_bound(*args,**kwargs)
                return result
            finally:
                profile.seconds[bucket]+=profile.clock()-start;profile.calls[bucket]+=1
                if caller=='solve_scale':profile.mark_bound(result)
        stack.enter_context(patch.object(scale_bounds,'completion_bound',bound))
        timed(scale_bounds,'region_travel_lower_bounds','region_travel_relaxation_s')
        timed(scale,'extend_prefix','prefix_transition_s',lambda a,r:
            profile.mark_child(a[1],a[2],r) if not profile.seed and r is not None else None)
        original_terminal=scale.terminal_attempt
        def terminal(*args,**kwargs):
            old=profile.terminal;profile.terminal=True
            start=profile.clock();routed=profile.route_wrapper_s
            try:return original_terminal(*args,**kwargs)
            finally:
                profile.seconds['terminal_excluding_selected_leg_s']+=profile.clock()-start-(profile.route_wrapper_s-routed)
                profile.terminal=old
        stack.enter_context(patch.object(scale,'terminal_attempt',terminal))
        original_seed=scale.deterministic_seed
        def seed(*args,**kwargs):
            old=profile.seed;profile.seed=True
            try:return original_seed(*args,**kwargs)
            finally:profile.seed=old
        stack.enter_context(patch.object(scale,'deterministic_seed',seed))
        original_solve=scale.solve_scale
        def solve(*args,**kwargs):
            callback=kwargs.get('on_incumbent')
            def incumbent(record):
                profile.ub=record['key'][0]
                start=profile.clock()
                try:
                    if callback:callback(record)
                finally:profile.seconds['incumbent_callback_s']+=profile.clock()-start
            kwargs['on_incumbent']=incumbent;profile.solving=True
            try:return original_solve(*args,**kwargs)
            finally:profile.solving=False
        stack.enter_context(patch.object(scale,'solve_scale',solve))
        original_native=road_index.NativeRoadIndex
        def native(*args,**kwargs):
            provider=original_native(*args,**kwargs)
            profile.window_start=profile.clock()
            return MeasuredProvider(provider,profile)
        stack.enter_context(patch.object(road_index,'NativeRoadIndex',native))
        yield


def instrumented_worker(args,worker):
    import run_real_scale_pilot as pilot
    config=json.loads(Path(args.config).read_text());spec=config['cost_diagnostic']
    job=pilot.declared_worker_job(config,args)
    if (args.query,args.n,args.scenario,args.method,job['solve_limit_s']) != (
            spec['query_id'],spec['N'],spec['scenario'],spec['method'],spec['solve_limit_s']):
        raise ValueError('undeclared cost diagnostic worker')
    manifest=json.loads(Path(args.preflight).read_text())
    q=next(q for q in manifest['queries'] if q['query_id']==args.query)
    if domain_digest(q,args.n,args.scenario)!=spec['candidate_domain_sha256']:
        raise ValueError('cost diagnostic input domain changed')
    rows=q['scenario_candidate_domains'][args.scenario][str(args.n)]
    metadata={r['access_node']:r for r in rows}
    for which,progress in (('origin',0),('destination',1)):
        r=q['endpoints'][which];metadata[r['access_node']]={**r,'progress':progress}
    profile=CostProfile(metadata)
    try:
        with instrument(profile):worker(args)
    finally:
        summary=profile.summary()
        summary.update(scope=spec,source_kind='instrumented_real_shandong_dev')
        pilot.atomic(Path(args.output).with_suffix('.cost.json'),summary)
        pilot.atomic(Path(args.output).with_suffix('.cost-events.json'),profile.events)


def summarize_run(output):
    """Read persisted evidence only, including truthful early resource stops."""
    output=Path(output)
    rows=[json.loads(line) for line in (output/'diagnostic-result.jsonl').read_text().splitlines()]
    if len(rows)!=1:raise ValueError('one diagnostic result required')
    summary=dict(diagnostic_only=True,fresh_performance_evidence=False,row=rows[0],
                 preparation=json.loads((output/'preparation.json').read_text()))
    profiles=list(output.glob('*workers/*.cost.json'))
    if len(profiles)>1:raise ValueError('one diagnostic profile required')
    summary['profile_available']=bool(profiles)
    if profiles:
        profile=json.loads(profiles[0].read_text())
        events=json.loads(profiles[0].with_suffix('').with_suffix('.cost-events.json').read_text())
        metrics=rows[0].get('routing_metrics',{})
        summary['profile']=profile
        if 'nodes' in metrics and 'edges' in metrics:
            summary['source_reuse']=source_reuse_analysis(events,metrics['nodes'],metrics['edges'])
        else:summary['source_reuse_unavailable_reason']='road index metrics unavailable after early stop'
    return summary


def main(args):
    import run_real_scale_pilot as pilot
    from real_scale_inputs import select_domains
    declared=json.loads(Path(args.config).read_text());d=declared['domain'];spec=declared['diagnostic']
    output=Path(args.output_root).resolve();output.mkdir(parents=True,exist_ok=False)
    inputs=Path(args.input_root).resolve();start=time.monotonic();cpu=time.process_time()
    config=json.loads((ROOT/declared['base_config']).read_text())
    config['selection'].update(corridor_km=d['corridor_km'],candidate_counts=[d['N']])
    config['selection']['candidate_rule']=config['selection']['candidate_rule'].replace('50 km',str(d['corridor_km'])+' km')
    config['implementation']=declared['implementation']
    config['pilot_matrix']=[dict(N=d['N'],query_ids=[d['query_id']],scenarios=[d['scenario']])]
    config['cost_diagnostic']={**d,**spec}
    manifest=select_domains(config,json.loads((inputs/'shared-sites.json').read_text()),
                            json.loads((inputs/'site-bindings.json').read_text()))
    q=next(q for q in manifest['queries'] if q['query_id']==d['query_id'])
    if domain_digest(q,d['N'],d['scenario'])!=d['candidate_domain_sha256']:
        raise ValueError('frozen D04 input identity mismatch')
    cp,mp=output/'resolved-config.json',output/'preflight.json'
    pilot.atomic(cp,config);pilot.atomic(mp,manifest)
    pilot.atomic(output/'preparation.json',dict(wall_s=time.monotonic()-start,
        cpu_s=time.process_time()-cpu,solver_called=False,domain_sha256=d['candidate_domain_sha256']))
    run=SimpleNamespace(config=str(cp),preflight=str(mp),graph_tsv=str(inputs/'real-scale-road.tsv'),
        native_cache=str(output/'native-cache'),output=str(output/'diagnostic-result.jsonl'),
        preflight_only=args.preflight_only,domains=str(d['N']),queries=d['query_id'],
        scenarios=d['scenario'],methods=spec['method'],diagnostic=False,ablation=False,no_bound=False,
        solve_limit_seconds=spec['solve_limit_s'],development_cpu_s=spec['carried_cpu_s']+spec['development_cpu_allowance_s'],
        cold_load_allowance_s=spec['cold_load_allowance_s'],process_memory_gib=spec['process_memory_gib'])
    pilot.main(run)
    if not args.preflight_only:pilot.atomic(output/'summary.json',summarize_run(output))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default=str(ROOT/'configs/d04_cost_diagnostic.json'))
    p.add_argument('--input-root',required=True);p.add_argument('--output-root',required=True)
    p.add_argument('--preflight-only',action='store_true');main(p.parse_args())
