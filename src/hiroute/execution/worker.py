"""One numerical query process and its exact physical replay/checkpoint boundary."""
from __future__ import annotations
from contextlib import contextmanager
from fractions import Fraction
import json,os,resource,signal,sys,time
from pathlib import Path
from ..data.queries import SiteAliasedProvider, bind_snapshot, domain_rows, InputDomainUnavailable
from .workload import declared_worker_job

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


def preserve_live_diagnostics(row, diagnostics):
    """Keep partial counters after an outer limit; never synthesize a result."""
    if row.get('metrics') is None and diagnostics:
        row['metrics'] = diagnostics.get('metrics')
        row['seconds'] = diagnostics.get('seconds')
        row['diagnostic_capture'] = 'live_partial_after_resource_exception'
        row['seconds_are_partial'] = True


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
    policy_adapter = None
    if config.get('planning_policy'):
        import planning_value_policy as policy_adapter
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
    implementation = config.get('implementation', {})
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
        implementation=implementation,
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
            cache_directory=args.native_cache, check=host_guard,
            pair_query_mode=implementation.get('pair_query_mode', 'reverse_tree'),
            source_tree_reuse=implementation.get('source_tree_reuse', False))
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
    original_snapshot = None
    last_verified_payload = None
    checkpoint_pending = False
    diagnostics = {}
    def verify(record):
        if original_snapshot is not None:
            return policy_adapter.verify_policy_witness(original_snapshot, snapshot, record,
                site_to_road=origin_aliases, direct_length_m=row.get('direct_selected_length_m'))
        return verify_scale_witness(snapshot, record, site_to_road=origin_aliases)
    def keep(record):
        nonlocal first_feasible, last_verified_payload, checkpoint_pending
        preparing_check()
        verified = verify(record)
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
            if implementation.get('pair_query_mode') == 'landmark_astar':
                native.prepare_landmarks(*(origin_aliases[query['endpoints'][end]['site_id']]
                    for end in ('origin','destination')))
            snapshot = bind_snapshot(config, query, args.n, args.scenario, provider)
            if config.get('planning_policy'):
                if args.method != 'flat_bb_strong' or args.diagnostic or args.scenario != 'schedule':
                    raise ValueError('policy adapter requires declared Strong schedule DEV')
                original_snapshot = snapshot
                snapshot, policy_info = policy_adapter.adapt_snapshot(original_snapshot, config['planning_policy'], provider)
                row['policy_info'] = policy_info
                if snapshot is None:
                    raise policy_adapter.PolicyNoEligibleActivity(policy_info['reason'])
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
                    seed_beam_pruning=implementation.get('seed_beam_pruning', False),
                    inbound_energy_bound=implementation.get('inbound_energy_bound', False),
                    eager_incumbent_pruning=implementation.get('eager_incumbent_pruning', False),
                    pending_activity_screen=implementation.get('pending_activity_screen', False),
                    diagnostics=diagnostics,
                    memory_baseline_bytes=query_memory_baseline)
            row.update(status=result['status'], mathematical_status=result.get('mathematical_status', result['status']),
                key=result.get('key'), primary_infimum=result.get('primary_infimum'),
                primary_value=result.get('primary_value'),
                secondary_infimum=result.get('secondary_infimum'), metrics=result['metrics'],
                seconds=result['seconds'], depth_contract=result['depth_contract'],
                seed_key=None if result['seed'] is None else result['seed']['key'],
                query_extra_peak_bytes=result['query_extra_peak_bytes'],
                routing_metrics=result['routing_metrics'], open_remaining=result['open_remaining'])
            preparing_check()
            record = result if result['status']=='attained_optimum' else result.get('incumbent')
            if record is not None:
                row['witness'] = verify(record)
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
        if policy_adapter is not None and isinstance(exc, policy_adapter.PolicyNoEligibleActivity):
            row.update(status='policy_no_eligible_activity', mathematical_status='unknown', reason=str(exc))
        else:
            row.update(status='worker_error',mathematical_status='unknown',error=repr(exc))
            for key in ('key','primary_value','primary_infimum','secondary_infimum'):
                row.pop(key,None)
            raise
    finally:
        preserve_live_diagnostics(row, diagnostics)
        row['routing_metrics'] = native.metrics()
        # If an alarm interrupted atomic checkpoint I/O, persist only the already
        # independently verified payload during final output; never re-solve it.
        if last_verified_payload is not None:
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


if __name__ == "__main__":
    from .pilot import cli
    cli()
