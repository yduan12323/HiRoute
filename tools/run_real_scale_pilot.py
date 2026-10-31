"""Sequential real DEV pilot using the existing OS supervisor.

Run preflight first. Each query gets a fresh numerical process, one numerical
thread, an independently enforced internal120s deadline, and a guarded cold-load
allowance. Every failure is kept. No automatic extension, holdout or merging.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from real_scale_inputs import (SiteAliasedProvider, bind_snapshot, domain_rows,
                               InputDomainUnavailable)


def jsonable(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value


def worker_cpu():
    """Include the completed cold compiler child in worker CPU accounting."""
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time()+children.ru_utime+children.ru_stime


def atomic(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(jsonable(value), sort_keys=True)+'\n')
    os.replace(tmp, path)


def aliases(query, n, scenario):
    result = {row['site_id']: row['access_node'] for row in domain_rows(query,n,scenario)}
    result.update({row['site_id']: row['access_node'] for row in query['endpoints'].values()})
    return result


@contextmanager
def loaded_query_watchdog(started, limit):
    """Bound the entire loaded query; disarm before final file serialization."""
    from hiroute.exact.scale import ResourceLimit
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_signum, _frame):
        raise ResourceLimit('time_limit')
    try:
        signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,max(1e-6,limit-(time.monotonic()-started)))
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def worker(args):
    from hiroute.exact.road_index import NativeRoadIndex
    from hiroute.exact.scale import ResourceLimit, solve_scale, validate_scale_input, _resident_bytes
    from hiroute.exact.scale_replay import verify_scale_witness
    config = json.loads(Path(args.config).read_text())
    preflight = json.loads(Path(args.preflight).read_text())
    declared_job = declared_worker_job(config,args)
    query = next(q for q in preflight['queries'] if q['query_id'] == args.query)
    if args.diagnostic:
        declared = config['diagnostics']['legacy_common_domain']
        if (args.query,args.n,args.scenario) != (declared['query_id'],declared['N'],declared['scenario']):
            raise ValueError('undeclared legacy diagnostic')
        scenario_domains = {**query['scenario_candidate_domains']}
        scenario_domains[args.scenario] = {**scenario_domains[args.scenario],
            str(args.n):domain_rows(query,16,args.scenario)[:args.n]}
        query = {**query,'scenario_candidate_domains':scenario_domains}
    resources = config['resources']
    initial_cpu = worker_cpu()
    entered = time.monotonic()
    def host_guard():
        from hiroute.runtime import system_mem_available_bytes
        available = system_mem_available_bytes()
        if available < resources['host_headroom_bytes']:
            raise ResourceLimit('host_headroom_limit')
    if sys.platform == 'darwin':
        # The existing monitor adapter supplies Darwin process+host samples.
        import hiroute.runtime as runtime
        import psutil
        runtime.system_mem_available_bytes = lambda: psutil.virtual_memory().available
    row = dict(query_id=args.query, N=args.n, scenario=args.scenario, method=args.method,
        bound_enabled=not args.no_bound, source_kind='real_shandong_dev',
        candidate_domain_claim=config['selection']['domain_claim'],
        great_circle_m=query['great_circle_m'], eligible_unique_anchors=query['eligible_unique_anchors'],
        scenario_eligible_sites=query['scenario_eligible_counts'][args.scenario],
        status='loading', mathematical_status='unknown')
    try:
        origin_aliases = aliases(query,args.n,args.scenario)
    except InputDomainUnavailable as exc:
        row.update(status='input_domain_unavailable',mathematical_status='unknown',
            failed_phase='candidate_input',requested_N=exc.requested,available_N=exc.available,
            reason=str(exc),worker_cpu_s=worker_cpu()-initial_cpu,
            worker_total_s=time.monotonic()-entered,
            worker_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))
        atomic(args.output,row)
        return
    # Cold graph/index residency is reported explicitly. The supervisor retains
    # an absolute process+host guard throughout construction and solving.
    try:
        native = NativeRoadIndex(args.graph_tsv, origin_aliases.values(),
            cache_directory=args.native_cache, check=host_guard)
    except (ResourceLimit, MemoryError) as exc:
        row.update(status=exc.status if isinstance(exc, ResourceLimit) else 'memory_limit',
            failed_phase='cold_graph_index', cold_index_wall_s=time.monotonic()-entered,
            worker_cpu_s=worker_cpu()-initial_cpu,
            worker_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))
        atomic(args.output,row)
        return
    provider = SiteAliasedProvider(native, origin_aliases)
    row['cold_index_wall_s'] = time.monotonic()-entered
    row['cold_index_cpu_s'] = worker_cpu()-initial_cpu
    row['graph_index_resident_bytes'] = _resident_bytes()
    loaded = time.monotonic()
    query_cpu = time.process_time()
    limit = declared_job['solve_limit_s']
    query_memory_baseline = row['graph_index_resident_bytes']
    query_sampled_peak = query_memory_baseline
    row['query_memory_baseline_bytes'] = query_memory_baseline
    def preparing_check():
        nonlocal query_sampled_peak
        host_guard()
        query_sampled_peak = max(query_sampled_peak, _resident_bytes())
        if query_sampled_peak-query_memory_baseline > resources['query_extra_memory_bytes']:
            raise ResourceLimit('memory_limit')
        if time.monotonic()-loaded >= limit:
            raise ResourceLimit('time_limit')
    provider.check = preparing_check
    output = Path(args.output)
    checkpoint = output.with_suffix('.incumbent.json')
    first_feasible = None
    snapshot = None
    last_verified_payload = None
    checkpoint_pending = False
    def keep(record):
        nonlocal first_feasible, last_verified_payload, checkpoint_pending
        preparing_check()
        verified = verify_scale_witness(snapshot, record, site_to_road=origin_aliases)
        preparing_check()
        if first_feasible is None:
            first_feasible = time.monotonic()-loaded
        last_verified_payload = dict(key=record['key'], plan=record['plan'], verified=verified,
            legs=[dict(source=l.source, target=l.target, time_s=l.time_s, length_m=l.length_m,
                       edges=[dict(e) for e in l.edges]) for l in record['legs']],
            replay=record['replay'], time_to_first_feasible_s=first_feasible)
        checkpoint_pending = True
        atomic(checkpoint, last_verified_payload)
        checkpoint_pending = False
        preparing_check()
    try:
        # Covers kernels, replay and callback I/O that do not route/check.
        with loaded_query_watchdog(loaded,limit):
            snapshot = bind_snapshot(config, query, args.n, args.scenario, provider)
            if args.diagnostic:
                from dataclasses import replace
                snapshot = replace(snapshot, depth_mode='diagnostic_cap',
                    depth_limit=config['diagnostics']['legacy_common_domain']['depth_limit'])
            validate_scale_input(snapshot)
            direct = provider.selected_leg(snapshot.origin, snapshot.destination)
            row['direct_selected_time_s'] = None if direct is None else str(direct.time_s)
            row['direct_selected_length_m'] = None if direct is None else str(direct.length_m)
            # Shortest physical distance is an independent energy lower bound;
            # the straight-line screen is descriptive only, never pruning.
            d = provider.distances_to(snapshot.destination, 'length_m').get(snapshot.origin)
            row['shortest_road_distance_m'] = None if d is None else str(d)
            if d is not None:
                energy_need = d*Fraction(snapshot.consumption_kwh_per_m)+Fraction(snapshot.destination_reserve_kwh)
                deficit = max(Fraction(0), energy_need-Fraction(snapshot.initial_energy_kwh))
                usable_per_charge = Fraction(snapshot.capacity_kwh)-Fraction(snapshot.minimum_energy_kwh)
                row['necessary_charge_count_lower_bound'] = int(-(-deficit//usable_per_charge))
            prepare_s = time.monotonic()-loaded
            row['candidate_and_input_preparation_s'] = prepare_s
            remaining = limit-prepare_s
            if remaining <= 0:
                raise ResourceLimit('time_limit')
            if args.method == 'flat_bb_legacy':
                from unittest.mock import patch
                from hiroute.contracts import SolverConfig
                from hiroute.exact import search
                def selected_leg(_snapshot, source, target, cache=None):
                    return provider.selected_leg(source,target)
                with patch.object(search,'selected_leg',selected_leg):
                    result=search.solve_snapshot(snapshot,SolverConfig('flat_bb','none',
                        'bounded_time_cut_v2','none','none','none','full_lexicographic_J_Q_H_Pi'),
                        time_limit_s=remaining,on_incumbent=keep,observer='metrics')
                result.update(metrics=result['observer']['search_metrics'],seconds={},
                    seed=None,query_extra_peak_bytes=None,routing_metrics=provider.metrics(),
                    open_remaining=None,depth_contract={'mode':'diagnostic_cap','declared_limit':snapshot.depth_limit})
            else:
                result = solve_scale(snapshot, method=args.method, provider=provider,
                    time_limit_s=remaining, memory_limit_bytes=resources['query_extra_memory_bytes'],
                    on_incumbent=keep, use_bound=not args.no_bound,
                    memory_baseline_bytes=query_memory_baseline)
            row.update(status=result['status'], mathematical_status=result.get('mathematical_status', result['status']),
                key=result.get('key'), primary_infimum=result.get('primary_infimum'),
                secondary_infimum=result.get('secondary_infimum'), metrics=result['metrics'],
                seconds=result['seconds'], depth_contract=result['depth_contract'],
                seed_key=None if result['seed'] is None else result['seed']['key'],
                query_extra_peak_bytes=result['query_extra_peak_bytes'],
                routing_metrics=result['routing_metrics'], open_remaining=result['open_remaining'])
            preparing_check()
            record = result if result['status']=='attained_optimum' else result.get('incumbent')
            if record is not None:
                row['witness'] = verify_scale_witness(snapshot, record, site_to_road=origin_aliases)
                preparing_check()
                row['feasible_key'] = record['key']
            else:
                row['witness'] = None
    except (ResourceLimit, MemoryError) as exc:
        row.update(status=exc.status if isinstance(exc, ResourceLimit) else 'memory_limit',
            mathematical_status='unknown')
        for key in ('key','primary_value','primary_infimum','secondary_infimum'):
            row.pop(key,None)
    except Exception as exc:
        row.update(status='worker_error',mathematical_status='unknown',error=repr(exc))
        for key in ('key','primary_value','primary_infimum','secondary_infimum'):
            row.pop(key,None)
        raise
    finally:
        # If an alarm interrupted atomic checkpoint I/O, persist only the already
        # independently verified payload during final output; never re-solve it.
        if checkpoint_pending and last_verified_payload is not None:
            atomic(checkpoint,last_verified_payload)
        if last_verified_payload is not None and not row.get('witness'):
            row['feasible_key'] = last_verified_payload['key']
            row['witness'] = last_verified_payload['verified']
        query_sampled_peak = max(query_sampled_peak,_resident_bytes())
        row['query_extra_peak_bytes'] = max(row.get('query_extra_peak_bytes') or 0,
            query_sampled_peak-query_memory_baseline)
        row.update(query_loaded_total_s=time.monotonic()-loaded,
            query_cpu_s=time.process_time()-query_cpu,
            worker_cpu_s=worker_cpu()-initial_cpu,
            time_to_first_feasible_s=first_feasible,
            worker_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
            worker_total_s=time.monotonic()-entered)
        atomic(output, row)
        native.close()


def preflight(args):
    from hiroute.exact.scale import validate_scale_input
    from hiroute.runtime import system_mem_available_bytes
    config = json.loads(Path(args.config).read_text())
    manifest = json.loads(Path(args.preflight).read_text())
    if manifest['selection_uses_solver_results'] or manifest['config'] != config:
        raise ValueError('preflight/config mismatch')
    if len(manifest['queries']) != 4:
        raise ValueError('pilot requires its four declared OD')
    if config['resources']['numeric_workers'] != 1 or config['resources']['numeric_threads'] != 1:
        raise ValueError('pilot is single numerical worker/thread')
    if not Path(args.graph_tsv).is_file():
        raise ValueError('real graph TSV not prepared')
    unavailable = []
    for query in manifest['queries']:
        for scenario in config['selection']['scenarios']:
            for n in config['selection']['candidate_counts']:
                rows = domain_rows(query,n,scenario,require_full=False)
                if len(rows) > n:
                    raise ValueError('declared candidate domain exceeds requested N')
                if len(rows) != n:
                    unavailable.append(dict(query_id=query['query_id'],scenario=scenario,
                        requested_N=n,available_N=len(rows),status='input_domain_unavailable'))
                    continue
                if (any(not row['capabilities'] for row in rows) or
                        (scenario=='energy_only' and any('C' not in row['capabilities'] for row in rows))):
                    raise ValueError('declared domain contains a scenario-ineligible Site')
                mapping = aliases(query,n,scenario)
                if len(mapping) != n+2 or len(set(mapping.values())) != len(mapping):
                    raise ValueError('candidate/endpoint aliases overlap')
    if sys.platform == 'darwin':
        import psutil
        available = psutil.virtual_memory().available
    else:
        available = system_mem_available_bytes()
    if available < config['resources']['host_headroom_bytes']+512*1024**2:
        raise ValueError('insufficient host memory before pilot')
    print(json.dumps(dict(preflight='passed', queries=8, domain_counts=config['selection']['candidate_counts'],
        host_available_bytes=available, graph_tsv_bytes=Path(args.graph_tsv).stat().st_size,
        input_domain_unavailable=unavailable,solver_called=False), sort_keys=True), flush=True)


def _scope(value, convert=str):
    if value is None:
        return None
    parts = value.split(',')
    if not parts or any(not part.strip() for part in parts):
        raise ValueError('empty workload scope')
    result = tuple(convert(part.strip()) for part in parts)
    if len(set(result)) != len(result):
        raise ValueError('duplicate workload scope')
    return set(result)


def selected_workload(config, args):
    """Select only predeclared matrix entries, never create a Cartesian extension."""
    if args.diagnostic and args.ablation:
        raise ValueError('diagnostic and ablation modes are mutually exclusive')
    normal_methods = ('flat_bb_strong','scale')
    limit_override = args.solve_limit_seconds
    if limit_override is not None and (not math.isfinite(limit_override) or limit_override <= 0):
        raise ValueError('solve limit must be finite and positive')
    rows = []
    if args.diagnostic:
        spec = config['diagnostics']['legacy_common_domain']
        limit = spec['wall_s']
        if args.no_bound or (limit_override is not None and limit_override != limit):
            raise ValueError('legacy diagnostic must match declared bound policy and wall limit')
        for method in ('flat_bb_legacy',)+normal_methods:
            rows.append(dict(N=spec['N'],query_id=spec['query_id'],scenario=spec['scenario'],
                method=method,use_bound=True,solve_limit_s=limit,mode='diagnostic'))
    elif args.ablation:
        spec = config['diagnostics']['bound_ablation']
        limit = spec['wall_s']
        if limit_override is not None and limit_override != limit:
            raise ValueError('bound ablation must match declared wall limit')
        variants = spec['use_bound_values']
        if not variants or any(type(v) is not bool for v in variants) or len(set(variants)) != len(variants):
            raise ValueError('invalid declared bound ablation variants')
        for use_bound in variants:
            if args.no_bound and use_bound:
                continue
            rows.append(dict(N=spec['N'],query_id=spec['query_id'],scenario=spec['scenario'],
                method=spec['method'],use_bound=use_bound,solve_limit_s=limit,mode='ablation'))
    else:
        if args.no_bound:
            raise ValueError('--no-bound requires the declared --ablation mode')
        resources = config['resources']
        limit = resources['pilot_method_query_wall_s'] if limit_override is None else limit_override
        if limit not in (resources['pilot_method_query_wall_s'],resources['main_threshold_s']):
            raise ValueError('undeclared pilot/main comparison wall limit')
        allowed_queries = {od['query_id'] for od in config['selection']['ods']}
        for block in config['pilot_matrix']:
            if (block['N'] not in config['selection']['candidate_counts'] or
                    not set(block['query_ids']) <= allowed_queries or
                    not set(block['scenarios']) <= set(config['selection']['scenarios'])):
                raise ValueError('pilot matrix contains an undeclared domain/query/scenario')
            for query in block['query_ids']:
                for scenario in block['scenarios']:
                    for method in normal_methods:
                        rows.append(dict(N=block['N'],query_id=query,scenario=scenario,
                            method=method,use_bound=True,solve_limit_s=limit,mode='pilot'))
    scopes = {'N':_scope(args.domains,int),'query_id':_scope(args.queries),
              'scenario':_scope(args.scenarios),'method':_scope(args.methods)}
    for field, values in scopes.items():
        if values is not None and not values <= {row[field] for row in rows}:
            raise ValueError('undeclared '+field+' scope')
    result = [row for row in rows if all(values is None or row[field] in values
        for field,values in scopes.items())]
    if not result:
        raise ValueError('no declared workload entries match the requested scopes')
    for field, values in scopes.items():
        if values is not None and not values <= {row[field] for row in result}:
            raise ValueError('requested '+field+' scope has no entry after other filters')
    identities = {(r['N'],r['query_id'],r['scenario'],r['method'],r['use_bound']) for r in result}
    if len(identities) != len(result):
        raise ValueError('duplicate configured workload entries')
    return result


def declared_worker_job(config,args):
    """Check direct worker invocations against the same configured workload."""
    scoped = argparse.Namespace(diagnostic=args.diagnostic,ablation=args.ablation,
        no_bound=args.no_bound,solve_limit_seconds=args.solve_limit_seconds,
        domains=str(args.n),queries=args.query,scenarios=args.scenario,methods=args.method)
    matches = [row for row in selected_workload(config,scoped)
               if row['use_bound'] == (not args.no_bound)]
    if len(matches) != 1:
        raise ValueError('worker must identify exactly one declared workload entry')
    return matches[0]


def apply_supervisor_outcome(row, supervised, checkpoint_record=None):
    """Merge enforcement/exit status without treating a written file as success."""
    row = dict(row)
    if checkpoint_record is not None:
        verified = checkpoint_record.get('verified')
        if not isinstance(verified,dict) or verified.get('physical_verified') is not True:
            raise ValueError('incumbent checkpoint is not independently physically verified')
        if not isinstance(row.get('witness'),dict) or row['witness'].get('physical_verified') is not True:
            row['feasible_key'] = checkpoint_record['key']
            row['witness'] = verified
        if row.get('feasible_key') is None:
            row['feasible_key'] = checkpoint_record['key']
        if row.get('time_to_first_feasible_s') is None:
            row['time_to_first_feasible_s'] = checkpoint_record['time_to_first_feasible_s']
    outcome = ('time_limit' if supervised.timed_out else
        'memory_limit' if supervised.memory_limited else
        'host_headroom_limit' if supervised.host_headroom_limited else
        'cpu_limit' if supervised.cpu_limited else
        'worker_error' if supervised.returncode not in (None,0) else None)
    if outcome is not None:
        if 'status' in row:
            row['solver_reported_status'] = row['status']
        row.update(status=outcome,mathematical_status='unknown')
        for key in ('key','primary_value','primary_infimum','secondary_infimum'):
            row.pop(key,None)
        if not isinstance(row.get('witness'),dict) or row['witness'].get('physical_verified') is not True:
            row.pop('feasible_key',None)
            row.pop('witness',None)
    if supervised.returncode not in (None,0):
        row['error'] = supervised.stderr.decode(errors='replace')[-3000:]
    row.update(supervisor_total_s=supervised.elapsed_s,
        process_group_peak_rss_bytes=supervised.rss_peak_bytes,
        host_available_min_bytes=supervised.host_available_min_bytes,
        supervisor_cpu_s=supervised.cpu_peak_s)
    return row


def supervised_main(args):
    from hiroute.runtime import run_supervised
    config = json.loads(Path(args.config).read_text())
    preflight(args)
    if args.preflight_only:
        return
    workload = selected_workload(config,args)
    resources = config['resources']
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(out)
    run_dir = out.parent/(out.stem+'-workers')
    run_dir.mkdir()
    total_cpu = args.development_cpu_s
    env = dict(os.environ, **{key:'1' for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS',
        'MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS')})
    for job in workload:
        n,query,scenario,method = (job[key] for key in ('N','query_id','scenario','method'))
        identity = f'{query}-N{n}-{scenario}-{method}'+('-no-bound' if not job['use_bound'] else '')
        result_path = run_dir/(identity+'.json')
        row = dict(query_id=query,N=n,scenario=scenario,method=method,
            bound_enabled=job['use_bound'],solve_limit_s=job['solve_limit_s'],workload_mode=job['mode'])
        # Reserve the complete maximum worker CPU allowance, including cold
        # loading, before starting. Never spend the final budget on a partial run.
        reserve_cpu = args.cold_load_allowance_s+job['solve_limit_s']
        if total_cpu+reserve_cpu > resources['new_solve_and_finite_ref_cpu_budget_s']:
            row.update(status='not_run_cpu_budget',mathematical_status='unknown')
        else:
            argv = [sys.executable,str(Path(__file__).resolve()),'--worker',
                '--config',str(Path(args.config).resolve()),'--preflight',str(Path(args.preflight).resolve()),
                '--graph-tsv',str(Path(args.graph_tsv).resolve()),'--native-cache',str(Path(args.native_cache).resolve()),
                '--query',query,'--n',str(n),'--scenario',scenario,'--method',method,'--output',str(result_path),
                '--solve-limit-seconds',str(job['solve_limit_s'])]
            if not job['use_bound']:
                argv.append('--no-bound')
            if job['mode']=='diagnostic':
                argv.append('--diagnostic')
            elif job['mode']=='ablation':
                argv.append('--ablation')
            supervised = run_supervised(argv,timeout_s=reserve_cpu,cpu_limit_s=reserve_cpu,
                memory_limit_bytes=args.process_memory_gib*1024**3,
                host_min_available_bytes=resources['host_headroom_bytes'],
                memory_poll_s=.1,cwd=str(ROOT),env=env)
            if result_path.exists():
                row.update(json.loads(result_path.read_text()))
            else:
                row.update(status='worker_error',mathematical_status='unknown')
            checkpoint = result_path.with_suffix('.incumbent.json')
            saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
            row = apply_supervisor_outcome(row,supervised,saved)
            # Conservative fresh budget: all observed worker CPU, including
            # cold index load; the separate map TSV export is not charged here.
            total_cpu += max(row.get('worker_cpu_s',0),supervised.cpu_peak_s)
        row['new_total_cpu_s'] = total_cpu
        with out.open('a') as stream:
            stream.write(json.dumps(jsonable(row),sort_keys=True)+'\n')
        print(identity,row['status'],row.get('query_loaded_total_s'),flush=True)


def main(args):
    with ExitStack() as stack:
        if sys.platform == 'darwin':
            from profile_small_cases import mac_monitors
            import psutil
            psutil.pids()  # permission preflight before numerical work
            mac_monitors(stack)
        supervised_main(args)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('config','preflight','graph-tsv','native-cache','output'):
        p.add_argument('--'+key,required=True)
    p.add_argument('--worker',action='store_true')
    p.add_argument('--preflight-only',action='store_true')
    p.add_argument('--query');p.add_argument('--n',type=int)
    p.add_argument('--scenario');p.add_argument('--method')
    p.add_argument('--domains')
    p.add_argument('--queries');p.add_argument('--scenarios')
    p.add_argument('--methods')
    p.add_argument('--no-bound',action='store_true')
    p.add_argument('--diagnostic',action='store_true')
    p.add_argument('--ablation',action='store_true')
    p.add_argument('--solve-limit-seconds',type=float)
    p.add_argument('--development-cpu-s',type=float,default=0)
    p.add_argument('--cold-load-allowance-s',type=int,default=180)
    p.add_argument('--process-memory-gib',type=int,default=16)
    a=p.parse_args()
    worker(a) if a.worker else main(a)
