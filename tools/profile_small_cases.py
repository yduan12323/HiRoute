"""Fixed, sequential P0-after-P1 diagnostics; no optimization or data recovery.

Run from an installed Python 3.11 environment. macOS monitoring needs psutil;
Linux uses the existing /proc supervisor unchanged. Binary profiles stay local.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import cProfile
from dataclasses import asdict
from fractions import Fraction
import json
import os
from pathlib import Path
import pstats
import resource
import sys
import tempfile
import time
from unittest.mock import patch


def load_case(config_path, case_id):
    config = json.loads(Path(config_path).read_text())
    case = next(c for c in config['cases'] if c['case_id'] == case_id)
    if case['source_kind'] == 'real_dev':
        if not case.get('snapshot_path'):
            return config, case, None
        raw = json.loads(Path(case['snapshot_path']).read_text())
    else:
        raw = dict(config['base_snapshot'], **case['overrides'])
    return config, case, raw


def solver_config(method):
    from hiroute.contracts import SolverConfig
    return SolverConfig(method, 'none', 'bounded_time_cut_v2', 'none', 'none',
                        'none', 'full_lexicographic_J_Q_H_Pi')


class Measurements:
    """Only counts real calls. Timers below are exclusive across categories."""
    def __init__(self):
        self.counts = dict(selected_leg_calls=0, routing_cache_misses=0, adjacency_builds=0,
                           plans_attempted=0, complete_propagations=0, drive_transition_calls=0,
                           stop_transition_calls=0, max_transition_input_pieces=0,
                           max_transition_output_pieces=0, propagated_pwa_pieces=0,
                           peak_pieces=0, region_reachable_bound_evaluations=0)
        self.seconds = dict(routing_s=0., transition_propagation_s=0., terminal_s=0.,
                            hierarchy_bound_and_traversal_s=0., result_and_witness_s=0.)
        self.c_seconds = 0.
        self.effect_stack = []
        self.prefixes = set()
        self.operator_keys = set()
        self.operator_calls = 0
        self.discrete_operator_visits = 0

    def install(self, stack):
        from hiroute.exact import search, pipeline, pwa_partition, analytic_charge
        def wrap(module, name, make):
            stack.enter_context(patch.object(module, name, make(getattr(module, name))))
        def timer(category):
            def make(fn):
                def call(*a, **kw):
                    started = time.perf_counter()
                    try:
                        return fn(*a, **kw)
                    finally:
                        self.seconds[category] += time.perf_counter()-started
                return call
            return make
        def routing(fn):
            def call(snapshot, source, target, cache=None):
                self.counts['selected_leg_calls'] += 1
                if cache is None or (source,target) not in cache:
                    self.counts['routing_cache_misses'] += 1
                return fn(snapshot,source,target,cache)
            return timer('routing_s')(call)
        wrap(search,'selected_leg',routing)
        def adjacency(fn):
            def call(*a,**kw):
                self.counts['adjacency_builds'] += 1
                return fn(*a,**kw)
            return call
        wrap(search,'_adjacency',adjacency)
        def plans(fn):
            def call(*a,**kw):
                self.counts['plans_attempted'] += 1
                return fn(*a,**kw)
            return call
        wrap(search,'_plan_steps',plans)
        def execute(fn):
            def call(*a,**kw):
                result=fn(*a,**kw)
                self.counts['complete_propagations'] += 1
                return result
            return timer('transition_propagation_s')(call)
        wrap(search,'execute_exact_plan',execute)
        wrap(search,'terminal_optimize',timer('terminal_s'))
        wrap(search,'replay_terminal',timer('result_and_witness_s'))
        def hierarchy(fn):
            def call(snapshot, cache, evaluate):
                evaluation_s=0.
                route_before=self.seconds['routing_s']
                route_in_evaluation=0.
                def observed(plan):
                    nonlocal evaluation_s,route_in_evaluation
                    t=time.perf_counter(); r=self.seconds['routing_s']
                    try:
                        return evaluate(plan)
                    finally:
                        evaluation_s+=time.perf_counter()-t
                        route_in_evaluation+=self.seconds['routing_s']-r
                if hasattr(evaluate, 'search_metrics'):
                    observed.search_metrics = evaluate.search_metrics
                t=time.perf_counter()
                try:
                    return fn(snapshot,cache,observed)
                finally:
                    # Traversal contains routing outside evaluate: exclude that
                    # because it is already included in routing_s.
                    self.seconds['hierarchy_bound_and_traversal_s'] += (
                        time.perf_counter()-t-evaluation_s
                        -(self.seconds['routing_s']-route_before-route_in_evaluation))
            return call
        wrap(search,'_hierarchical_plans',hierarchy)
        wrap(search,'_flat_bb_plans',hierarchy)
        def bound(fn):
            def call(*a,**kw):
                self.counts['region_reachable_bound_evaluations']+=1
                return fn(*a,**kw)
            return call
        wrap(search,'_next_stop_bound',bound)
        def transition(kind, family=False):
            def make(fn):
                def call(*a,**kw):
                    pieces = tuple(a[0]) if family else (a[0],)
                    self.counts[kind+'_transition_calls'] += 1
                    self.counts['max_transition_input_pieces']=max(self.counts['max_transition_input_pieces'],len(pieces))
                    if kind=='drive':
                        site=a[1]; effect='D'
                    else:
                        effect,site=(a[1],a[2]) if family else ('S',a[1])
                    for p in pieces:
                        self.prefixes.add(p.prefix)
                        self.operator_keys.add((p.prefix,effect,site))
                        self.operator_calls+=1
                        if effect!='D': self.prefixes.add(p.prefix+((site,effect),))
                    self.discrete_operator_visits += len({p.prefix for p in pieces})
                    out=fn(*a,**kw)
                    n=len(out) if isinstance(out,(tuple,list)) else int(out is not None)
                    self.counts['propagated_pwa_pieces'] += n
                    self.counts['max_transition_output_pieces']=max(self.counts['max_transition_output_pieces'],n)
                    return out
                return call
            return make
        wrap(pipeline,'drive_piece',transition('drive'))
        wrap(pipeline,'schedule_piece',transition('stop'))
        def stop(fn):
            observed = transition('stop',True)(fn)
            def call(pieces, effect, site, curve, overhead, **kw):
                pieces=tuple(pieces)
                self.counts[effect+'_calls'] += 1
                self.counts[effect+'_segment_pairs'] += len(pieces)*len(curve)**2
                self.effect_stack.append(effect)
                started=time.perf_counter()
                try:
                    return observed(pieces,effect,site,curve,overhead,**kw)
                finally:
                    if effect=='C': self.c_seconds+=time.perf_counter()-started
                    self.effect_stack.pop()
            return call
        for key in ('C_calls','C_segment_pairs','CS_calls','CS_segment_pairs',
                    'C_projection_builds','CS_projection_builds','analytic_pair_attempts','analytic_builds'):
            self.counts[key]=0
        wrap(pipeline,'stop_partition',stop)
        original=pwa_partition.Projection.build
        def build(*args,**kwargs):
            self.counts[self.effect_stack[-1]+'_projection_builds']+=1
            return original(*args,**kwargs)
        stack.enter_context(patch.object(pwa_partition.Projection,'build',staticmethod(build)))
        def analytic(fn):
            def call(*args,**kwargs):
                self.counts['analytic_pair_attempts']+=1
                out=fn(*args,**kwargs)
                self.counts['analytic_builds']+=bool(out)
                return out
            return call
        wrap(analytic_charge,'charge_pair',analytic)
        def union(fn):
            def call(*a,**kw):
                out=fn(*a,**kw)
                self.counts['peak_pieces']=max(self.counts['peak_pieces'],len(out))
                return out
            return call
        wrap(pipeline,'family_union',union)

    def report(self):
        return dict(self.counts, **self.seconds, C_operator_s=self.c_seconds, distinct_prefixes=len(self.prefixes),
                    distinct_operator_prefix_keys=len(self.operator_keys),
                    discrete_operator_visits=self.discrete_operator_visits,
                    repeated_prefix_operator_calls=self.discrete_operator_visits-len(self.operator_keys),
                    piece_operator_visits=self.operator_calls,
                    repeated_piece_operator_visits=self.operator_calls-len(self.operator_keys))


def outcome(result, reference=False):
    status=result['status']
    if status=='infeasible_within_H_ref': status='infeasible'
    key=result.get('lex_key' if reference else 'key')
    return dict(status=status,key=key,primary_infimum=result.get('primary_infimum') if not key else key[0],
                secondary_infimum=result.get('secondary_infimum') if not key else key[1])


def worker(args):
    entered=time.perf_counter()
    from hiroute.contracts import ProblemSnapshot
    from hiroute.exact.search import solve_snapshot
    from hiroute_ref.cli import snapshot_case
    from hiroute_ref.model import normalize_case, replay_witness
    from hiroute_ref.solver import solve_case, jsonable
    config,case,raw=load_case(args.config,args.case)
    snapshot=ProblemSnapshot.from_dict(raw)
    row=dict(case_id=args.case,source_kind=case['source_kind'],N=len(snapshot.candidate_order),
             H=snapshot.depth_limit,method=args.method,c_backend=args.c_backend,run_kind='profiling' if args.profile else 'normal',
             load_and_parse_s=time.perf_counter()-entered)
    measured=Measurements()
    profiler=cProfile.Profile() if args.profile else None
    with ExitStack() as stack:
        if args.method!='ref' and not args.no_counts: measured.install(stack)
        started=time.perf_counter()
        cpu_started=time.process_time()
        if profiler: profiler.enable()
        if args.method=='ref':
            source,_=snapshot_case(raw)
            result=solve_case(source,keep_evidence=False)['result']
        else:
            result=solve_snapshot(snapshot,solver_config(args.method),time_limit_s=config['budget']['wall_s'],observer='metrics',c_backend=args.c_backend)
        if profiler: profiler.disable()
        row['solve_total_s']=time.perf_counter()-started
        row['solve_cpu_s']=time.process_time()-cpu_started
    row.update(outcome(result,args.method=='ref'))
    row.update(measured.report() if args.method!='ref' and not args.no_counts else {})
    row['witness_check']=None
    row['positive_charge_count']=None
    row['schedule_completed']=None
    verify=time.perf_counter()
    if result['status']=='attained_optimum':
        if args.method=='ref':
            row['witness_check']=result['witness_replayed']
            row['positive_charge_count']=sum(q>0 for q in result['charges'])
            row['schedule_completed']=result['remaining_schedule']==0
        else:
            trace=result['replay']['trace']
            charges=[oe-ie for effect,_,ie,_,oe,_ in trace if effect in ('C','CS')]
            source,_=snapshot_case(raw)
            replay=replay_witness(normalize_case(source),result['plan'],charges)
            if replay['lex_key']!=result['key']: raise ValueError('independent physical replay full-key mismatch')
            row['witness_check']=True
            row['positive_charge_count']=sum(q>0 for q in charges)
            row['schedule_completed']=replay['remaining_schedule']==0
    row['independent_witness_check_s']=time.perf_counter()-verify
    observation=result.get('observer') or {}
    row['prefix_cache']=observation.get('prefix_cache')
    row['search_metrics']=observation.get('search_metrics')
    row['first_attained_incumbent']=observation.get('first_attained_incumbent')
    row['infimal_threshold_updates']=observation.get('infimal_threshold_updates')
    row['unattained_threshold_updates']=observation.get('unattained_threshold_updates')
    row['comparison_threshold']=observation.get('comparison_threshold')
    if args.method!='ref' and not args.no_counts:
        # P2 chunks the pipeline; distinguish calls from completed plan evaluations.
        row['propagation_pipeline_calls']=row['complete_propagations']
        row['complete_propagations']=observation.get('plans_evaluated')
    hm=result.get('hierarchy_metrics') or {}
    row.update(region_visits=hm.get('region_nodes'),pruned_regions=hm.get('pruned_regions'),
               equality_retained=hm.get('equality_nodes_retained'),leaf_actions=hm.get('leaf_actions'))
    row['region_member_visits']=(observation.get('search_metrics') or {}).get('region_member_visits')
    if args.method!='ref' and not args.no_counts:
        row['solve_other_s']=row['solve_total_s']-sum(measured.seconds.values())
    row['cpu_s']=time.process_time()
    row['wall_worker_s']=time.perf_counter()-entered
    row['worker_maxrss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
    if profiler:
        profiler.dump_stats(args.profile)
        stats=pstats.Stats(profiler)
        ranked=sorted(stats.stats.items(),key=lambda x:x[1][3],reverse=True)[:18]
        row['profile_hotspots']=[dict(function=f'{Path(k[0]).name}:{k[1]}:{k[2]}',calls=v[1],self_s=v[2],cumulative_s=v[3]) for k,v in ranked]
    Path(args.output).write_text(json.dumps(jsonable(row),sort_keys=True)+'\n')


def mac_monitors(stack):
    """Adapt existing supervisor samples on macOS; retain its enforcement loop."""
    import psutil
    import hiroute.runtime as runtime
    def members(pgid):
        # Worker is single-process; include all current descendants defensively.
        try:
            leader=psutil.Process(pgid)
            return [leader,*leader.children(recursive=True)]
        except psutil.NoSuchProcess:
            return []
    def memory(pgid, field):
        total=0
        for p in members(pgid):
            try: total+=getattr(p.memory_info(),field)
            except psutil.NoSuchProcess: pass
        return total
    def cpu(pgid):
        total=0.
        for p in members(pgid):
            try:
                t=p.cpu_times();total+=t.user+t.system
            except psutil.NoSuchProcess: pass
        return total
    for name,fn in (('_group_rss_bytes',lambda p:memory(p,'rss')),
                    ('_group_vmsize_bytes',lambda p:memory(p,'vms')),
                    ('_group_cpu_seconds',cpu),
                    ('system_mem_available_bytes',lambda:psutil.virtual_memory().available)):
        stack.enter_context(patch.object(runtime,name,fn))


def main(args):
    from hiroute.runtime import run_supervised
    config=json.loads(Path(args.config).read_text())
    baseline=[] if not args.baseline else [json.loads(line) for line in Path(args.baseline).read_text().splitlines()]
    budget=config['budget']
    prior_cpu=args.development_cpu_s if args.mechanism else 0 if args.compare_c else sum(max(r.get('cpu_s') or 0,r.get('sampled_group_cpu_peak_s') or 0) for r in baseline)
    total_cpu=prior_cpu;rows=[]
    print(f'Previous accounted CPU seconds: {prior_cpu:.6f}; remaining: {budget["total_cpu_s"]-prior_cpu:.6f}',flush=True)
    def baseline_row(case_id, method):
        return next((r for r in baseline if r['case_id']==case_id and r['method']==method
                     and r['run_kind']=='normal'),None)
    def signature(row):
        return tuple(row.get(k) for k in ('status','key','primary_infimum','secondary_infimum'))
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',
             VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH',None)
    output=Path(args.output)
    if output.exists(): raise FileExistsError(output)
    def save(row):
        row.setdefault('execution_status', 'completed' if row.get('counters_complete') else row['status'])
        row.setdefault('mathematical_status', row['status'] if row.get('counters_complete') else 'unknown')
        required = ('N','H','key','primary_infimum','secondary_infimum','positive_charge_count',
                    'schedule_completed','witness_check','reference_status','load_and_parse_s',
                    'routing_s','transition_propagation_s','terminal_s','hierarchy_bound_and_traversal_s',
                    'result_and_witness_s','solve_total_s','wall_total_s','cpu_s',
                    'selected_leg_calls','routing_cache_misses','adjacency_builds','plans_attempted',
                    'complete_propagations','distinct_prefixes','drive_transition_calls',
                    'stop_transition_calls','peak_pieces','region_visits','region_member_visits',
                    'pruned_regions','equality_retained','leaf_actions','sampled_group_rss_peak_bytes',
                    'counters_complete')
        for key in required: row.setdefault(key,None)
        key=row.get('key')
        row.update(J_or_primary_infimum=key[0] if key else row['primary_infimum'],
                   Q_or_secondary_infimum=key[1] if key else row['secondary_infimum'],
                   H_stops=key[2] if key else None,Pi=key[3] if key else None)
        rows.append(row)
        with output.open('a') as stream: stream.write(json.dumps(row,sort_keys=True)+'\n')
        print(row['case_id'],row['method'],row.get('run_kind'),row['status'],flush=True)
    with tempfile.TemporaryDirectory(prefix='hiroute-small-profile-') as tmp, ExitStack() as stack:
        if sys.platform=='darwin':
            # Check observation permission BEFORE launching numerical work.
            import psutil
            psutil.pids()
            mac_monitors(stack)
        def run(case,method,profile=False,c_backend="projection", repetition=0):
            nonlocal total_cpu
            limit=budget['ref_s'] if method=='ref' else budget['wall_s']
            if total_cpu+limit>budget['total_cpu_s']:
                return dict(case_id=case['case_id'],method=method,status='NOT_RUN_CPU_BUDGET')
            result=Path(tmp)/'row.json'
            result.unlink(missing_ok=True)
            argv=[sys.executable,str(Path(__file__).resolve()),'--worker','--config',str(Path(args.config).resolve()),
                  '--case',case['case_id'],'--method',method,'--output',str(result),
                  '--c-backend',c_backend]
            if profile:
                profile_path=Path(args.profiles)/f"{case['case_id']}-{method}.pstats"
                profile_path.parent.mkdir(parents=True,exist_ok=True)
                argv+=['--profile',str(profile_path)]
            limit=budget['ref_s'] if method=='ref' else budget['wall_s']
            supervised=run_supervised(argv,timeout_s=limit,cpu_limit_s=limit,
                memory_limit_bytes=budget['memory_bytes'],host_min_available_bytes=budget['host_headroom_bytes'],
                memory_poll_s=.05,cwd=str(Path.cwd()),env=env)
            row=json.loads(result.read_text()) if result.exists() else dict(case_id=case['case_id'],
                source_kind=case['source_kind'],method=method,run_kind='profiling' if profile else 'normal')
            row.update(c_backend=c_backend,repetition=repetition,wall_total_s=supervised.elapsed_s,sampled_group_rss_peak_bytes=supervised.rss_peak_bytes,
                       sampled_group_cpu_peak_s=supervised.cpu_peak_s,host_available_min_bytes=supervised.host_available_min_bytes)
            total_cpu+=max(row.get('cpu_s',0),supervised.cpu_peak_s)
            if supervised.timed_out: row['status']='REF_TIMEOUT' if method=='ref' else 'time_limit'
            elif supervised.memory_limited: row['status']='memory_limit'
            elif supervised.cpu_limited: row['status']='cpu_limit'
            elif supervised.host_headroom_limited: row['status']='host_headroom_limit'
            elif supervised.returncode!=0:
                row['status']='ERROR';row['notes']=supervised.stderr.decode()[-4000:]
            row['counters_complete']=result.exists() and row.get('status') not in ('time_limit','REF_TIMEOUT','cpu_limit','memory_limit','host_headroom_limit','ERROR')
            if not row['counters_complete']:
                # Never promote partial counters to final measurements.
                for key in Measurements().report(): row[key]=None
            return row
        if args.mechanism:
            # Correctness work (including the only two new REF solves) finishes
            # before launching any timed production row. No baseline ledger.
            if baseline or args.compare_c: raise ValueError('mechanism has its own budget and matrix')
            refs = {}
            for case in config['cases']:
                if case['case_id'] not in config['ref_cases']: continue
                if case['case_id'] in args.unavailable_ref_case:
                    ref = dict(case_id=case['case_id'],method='ref',status='REF_RESULT_UNAVAILABLE',
                        counters_complete=False,notes='Earlier REF worker exited after resource monitor permission failure; output unavailable. Not retried; its full CPU limit is charged in development-cpu-s.')
                else:
                    ref = run(case, 'ref', c_backend='analytic')
                ref['run_kind'] = 'correctness_ref'
                refs[case['case_id']] = ref
                save(ref)
            for case in config['cases']:
                expected = None
                for repetition in range(3):
                    methods = ('flat', 'flat_bb', 'hier')
                    order = methods[repetition:]+methods[:repetition]
                    for position, method in enumerate(order):
                        row = run(case, method, c_backend='analytic', repetition=repetition)
                        row['execution_order'] = position
                        row['execution_status'] = 'completed' if row.get('counters_complete') else row['status']
                        row['mathematical_status'] = row['status'] if row.get('counters_complete') else 'unknown'
                        ref = refs.get(case['case_id'])
                        row['reference_status'] = ref['status'] if ref else 'REF_NOT_RUN_PARITY_REPLAY_ONLY'
                        save(row)  # Preserve the terminal record even on disagreement/cutoff.
                        if not row.get('counters_complete'): continue
                        current = signature(row)
                        if expected is not None and current != expected:
                            raise ValueError('Mechanism mathematical disagreement: '+case['case_id'])
                        expected = current
                        if ref and ref.get('counters_complete') and current != signature(ref):
                            raise ValueError('Mechanism REF disagreement: '+case['case_id'])
            print(f'Mechanism measured CPU seconds (new budget only): {total_cpu:.6f}',flush=True)
            return
        if args.compare_c:
            # One new C-only budget; baseline REF outcomes are read-only references.
            for i,case in enumerate(config['cases']):
                if case['source_kind']=='real_dev' and not case.get('snapshot_path'):
                    save(dict(case_id=case['case_id'],source_kind='real_dev',method='both',
                        c_backend='both',run_kind='normal',status='NOT_RUN_INPUT_UNAVAILABLE',
                        reference_status='REF_NOT_RUN'))
                    continue
                for repetition in range(3 if case['case_id']=='P07' else 1):
                    pair=[]
                    order=('projection','analytic') if (i+repetition)%2==0 else ('analytic','projection')
                    for method in ('flat','hier'):
                        for backend in order:
                            row=run(case,method,c_backend=backend,repetition=repetition)
                            old=baseline_row(case['case_id'],method)
                            ref=baseline_row(case['case_id'],'ref')
                            if not row.get('counters_complete'):
                                save(row)
                                raise RuntimeError('C comparison incomplete: '+str(row))
                            if old and signature(row)!=signature(old):
                                raise ValueError('Existing mathematical outcome changed: '+case['case_id'])
                            row['baseline_comparison']='MATCH' if old else 'NOT_SUPPLIED'
                            row['reference_status']='REF_REUSED_'+ref['status'].upper() if ref else 'REF_NOT_RUN'
                            pair.append(row)
                    if len({json.dumps(signature(r),sort_keys=True) for r in pair})!=1:
                        raise ValueError('C backend/method mathematical disagreement: '+case['case_id'])
                    for row in pair: save(row)
            print(f'New C-only CPU seconds: {total_cpu:.6f}',flush=True)
            return
        for i,case in enumerate(config['cases']):
            if case['source_kind']=='real_dev' and not case.get('snapshot_path'):
                for method in ('flat','hier'):
                    save(dict(case_id=case['case_id'],source_kind='real_dev',method=method,run_kind='normal',
                              status='NOT_RUN_INPUT_UNAVAILABLE',reference_status='REF_NOT_RUN'))
                continue
            pair=[]
            for method in (('flat','hier') if i%2==0 else ('hier','flat')):
                pair.append(run(case,method))
            ref=baseline_row(case['case_id'],'ref') if baseline else (run(case,'ref') if i<3 else None)
            for row in pair:
                old=baseline_row(case['case_id'],row['method'])
                if old:
                    if row.get('counters_complete') and signature(row)!=signature(old):
                        raise ValueError('Baseline mathematical disagreement: '+case['case_id'])
                    row['baseline_comparison']='MATCH' if row.get('counters_complete') else 'UNRESOLVED'
                    row['baseline_source']=args.baseline
                    row['baseline_measurements']={k:old.get(k) for k in (
                        'solve_total_s','wall_total_s','cpu_s','sampled_group_rss_peak_bytes',
                        'worker_maxrss_bytes','stop_transition_calls','drive_transition_calls',
                        'selected_leg_calls','plans_attempted','complete_propagations','peak_pieces')}
            if pair[0].get('counters_complete') and pair[1].get('counters_complete') and signature(pair[0])!=signature(pair[1]):
                raise ValueError('FLAT/HIER mathematical disagreement: '+case['case_id'])
            if all(r.get('key') is not None for r in pair) and pair[0]['key']!=pair[1]['key']:
                raise ValueError('FLAT/HIER full-key disagreement: '+case['case_id'])
            if ref and ref.get('status') in ('attained_optimum','primary_unattained','secondary_unattained','infeasible'):
                for row in pair:
                    if row.get('status') in ('attained_optimum','primary_unattained','secondary_unattained','infeasible'):
                        if (row['status'],row.get('key'))!=(ref['status'],ref.get('key')):
                            raise ValueError('REF disagreement: '+case['case_id'])
            for row in pair:
                row['reference_status']=('REF_REUSED_'+ref['status'].upper() if baseline else ref['status']) if ref else 'REF_NOT_RUN'
                save(row)
            if ref and not baseline: save(ref)
        completed={r['case_id'] for r in rows if r['method']=='flat' and r['status']=='attained_optimum'} & {
                   r['case_id'] for r in rows if r['method']=='hier' and r['status']=='attained_optimum'}
        if completed and not args.skip_profiles:
            selected=max(completed,key=lambda c:max(r.get('solve_total_s',0) for r in rows if r['case_id']==c))
            case=next(c for c in config['cases'] if c['case_id']==selected)
            for method in ('flat','hier'): save(run(case,method,True))
    print(f'Total charged CPU seconds including baseline: {total_cpu:.6f}; new: {total_cpu-prior_cpu:.6f}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/diagnostics/small_profile.json')
    parser.add_argument('--output',required=True)
    parser.add_argument('--profiles',default='results/small-profile-local')
    parser.add_argument('--baseline',help='Reuse verified tiny REF and account all prior numerical CPU')
    parser.add_argument('--skip-profiles',action='store_true',help='Do not consume more detailed profiler slots')
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--case')
    parser.add_argument('--method',choices=('flat','flat_bb','hier','ref'))
    parser.add_argument('--profile')
    parser.add_argument('--no-counts',action='store_true')
    parser.add_argument('--c-backend',choices=('projection','analytic'),default='projection')
    parser.add_argument('--compare-c',action='store_true',help='Fixed P01-P07 C backend comparison, independent new CPU budget; no profiles')
    parser.add_argument('--mechanism',action='store_true',help='Fixed 8 x 3 x 3 matrix; two tiny REF checks first; no profiles')
    parser.add_argument('--development-cpu-s',type=float,default=0.,help='This task only: already consumed development numerical CPU')
    parser.add_argument('--unavailable-ref-case',action='append',default=[],help='Retain an earlier lost REF attempt as unknown; do not repeat its optimization')
    args=parser.parse_args()
    worker(args) if args.worker else main(args)
