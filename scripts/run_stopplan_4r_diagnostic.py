"""All 30 development ODs, exhaustive zero/one-stop canonical EV diagnostics."""
import argparse
import json
import time

import numpy as np
import pandas as pd

from _common import configs, load_graph
from _stopplan4r_common import ROOT, memory_guard, peak_rss_mib, read_config, sha256, write_json
from microplan.routing import ExactRouter
from stopplan4r.evaluation import best_one_stop
from stopplan4r.models import EVModel, PiecewiseChargingCurve, PlannerConfig, ScheduledStop, TravelLeg, Trip
from stopplan4r.sites import sites_from_table


class ODTravel:
    """Read the existing native fastest-path label arrays, no per-POI routing.

    Forward/reverse labels minimize (time, actual path length) lexicographically.
    Never combine an independent distance-shortest path with fastest-path time.
    """
    def __init__(self, origin, destination, forward_time, forward_length, reverse_time, reverse_length):
        self.origin, self.destination = origin, destination
        self.ft, self.fl, self.rt, self.rl = forward_time, forward_length, reverse_time, reverse_length

    def leg(self, source, target):
        if source == self.origin:
            time_s, distance_m = self.ft[target], self.fl[target]
        elif target == self.destination:
            time_s, distance_m = self.rt[source], self.rl[source]
        else:
            raise ValueError('Diagnostic router only supplies source/Site/destination legs')
        if not np.isfinite(time_s):
            return None
        return TravelLeg(float(time_s), float(distance_m))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='configs/stopplan_4r.yaml')
    args = parser.parse_args(); cfg = read_config(args.config)
    if cfg['planner']['maximum_stops'] != 1:
        raise ValueError('Real diagnostic is exhaustive zero/one-stop only; no multi-stop restriction is improvised')
    out = ROOT / cfg['results_dir']; out.mkdir(parents=True, exist_ok=True)
    ev, curve, planner_cfg = EVModel(**cfg['ev']), PiecewiseChargingCurve(tuple(map(tuple, cfg['charging']['bands']))), PlannerConfig(**cfg['planner'])
    build = json.loads((out / 'site_build.json').read_text())
    contract = {'inventory_sha256': sha256(ROOT / cfg['inventory']),
        'attachments_sha256': sha256(ROOT / cfg['attachments']),
        'radii_m': cfg['support']['radii_m'], 'primary_radius_m': cfg['support']['primary_radius_m'],
        'method': cfg['support']['method']}
    if build['static_contract'] != contract:
        raise ValueError('Static input/support contracts differ; trip parameters never require a Site rebuild')
    for name in ['stop_sites.parquet', 'local_support.parquet']:
        if sha256(out / name) != build['outputs'][name]:
            raise ValueError(f'Site output checksum mismatch: {name}')
    start = time.perf_counter()
    preflight = memory_guard(cfg['memory'], projected_additional_gib=7)
    sites = sites_from_table(pd.read_parquet(out / 'stop_sites.parquet'))
    attached = tuple(s for s in sites if s.access_node is not None and s.attachment_status == 'attached')
    access = np.array([s.access_node for s in attached], dtype=np.int64)
    data, routing = configs(cfg['graph_data_config'])
    graph_start = time.perf_counter(); graph = load_graph(data, routing)
    graph_load_s = time.perf_counter() - graph_start
    router = ExactRouter(graph, cfg, out / 'native_cache')
    ods = pd.read_parquet(ROOT / cfg['development_ods'])
    if len(ods) != 30 or set(ods.instance_id) != set(range(30)):
        raise ValueError('Expected frozen 30 development ODs')
    records, envelope_records, runtime, checks = [], [], [], []
    for od in ods.itertuples():
        memory_guard(cfg['memory'], projected_additional_gib=1)
        od_start = time.perf_counter(); routing_start = time.perf_counter()
        ft, fl, parents = router.full(int(od.origin_node))
        rt, rl, next_nodes = router.full(int(od.destination_node), reverse=True)
        routing_s = time.perf_counter() - routing_start
        travel = ODTravel(int(od.origin_node), int(od.destination_node), ft, fl, rt, rl)
        baseline = travel.leg(travel.origin, travel.destination)
        if not np.isclose(baseline.time_s, od.ext_baseline_time_s):
            raise ValueError('Native baseline disagrees with frozen OD')
        lower_bounds = ft[access] + rt[access]
        # Independent path totals for a deterministic subset across three ODs.
        if od.instance_id in [0, 10, 20]:
            usable = np.flatnonzero(np.isfinite(lower_bounds))
            indices = usable[np.linspace(0, len(usable) - 1, 3, dtype=int)]
            for i in indices:
                for source, target in [(travel.origin, int(access[i])), (int(access[i]), travel.destination)]:
                    actual = graph.shortest_path(source, target, 'travel_time')
                    native = travel.leg(source, target)
                    passed = np.isclose(actual.travel_time_s, native.time_s, rtol=1e-10, atol=1e-7)
                    # Tied fastest routes can differ in length; the native router
                    # explicitly picks the shortest length among equal-time labels.
                    passed = bool(passed and native.distance_m <= actual.distance_m + 1e-5)
                    checks.append({'instance_id': int(od.instance_id), 'source': source, 'target': target,
                        'time_s': native.time_s, 'distance_m': native.distance_m, 'passed': passed})
                    if not passed:
                        raise ValueError('Independent directed route check failed')
        planning_start = time.perf_counter()
        for ratio in cfg['diagnostics']['envelope_ratios']:
            budget = ratio * baseline.time_s
            tolerance = 1e-8 + budget * 1e-10  # Existing M2 NumericalTolerance.
            indices = np.flatnonzero(np.isfinite(lower_bounds) & (lower_bounds <= budget + tolerance))
            eligible = tuple(attached[i] for i in indices)
            # With one stop the sum of optimal prefix/suffix is also actual
            # mobility cost. The planner checks total cost again for every plan.
            envelope_records.append({'instance_id': int(od.instance_id), 'ratio': ratio,
                'budget_s': budget, 'site_count': len(eligible),
                'charger_count': sum('charge' in s.transport_capabilities for s in eligible),
                'meal_supported_count': sum(s.support.meal_count >= cfg['support']['meal_threshold'] for s in eligible)})
            window = [f * baseline.time_s for f in cfg['diagnostics']['window_baseline_fraction']]
            schedule = ScheduledStop(*window, duration_s=cfg['diagnostics']['scheduled_duration_s'],
                meal_threshold=cfg['support']['meal_threshold'], hard=cfg['diagnostics']['scheduled_hard'],
                miss_penalty_s=cfg['diagnostics']['miss_penalty_s'], time_penalty_per_s=cfg['diagnostics']['time_penalty_per_s'],
                compatible_with_charging=cfg['diagnostics']['compatible_with_charging'])
            for initial_soc in cfg['diagnostics']['initial_soc']:
                trip = Trip(travel.origin, travel.destination, initial_soc * ev.capacity_kwh, mobility_budget_s=budget)
                energy_only = best_one_stop(trip, eligible, travel, ev, curve, None, planner_cfg)
                scheduled = best_one_stop(trip, eligible, travel, ev, curve, schedule, planner_cfg)
                # Evidence of real-data instantiability, not a forced outcome.
                charging_sites = [s for s in eligible if 'charge' in s.transport_capabilities and schedule.supports(s)]
                reach = sum(trip.initial_energy_kwh - ev.drive_energy(travel.leg(trip.origin, s.access_node).distance_m) >= ev.minimum_energy_kwh for s in charging_sites)
                for scenario, plan in [('energy_only', energy_only), ('energy_and_scheduled', scheduled)]:
                    records.append({'instance_id': int(od.instance_id), 'ratio': ratio, 'initial_soc': initial_soc,
                        'scenario': scenario, 'eligible_site_count': len(eligible), 'feasible': plan is not None,
                        'status': 'feasible_in_zero_one_stop_domain' if plan else 'cannot_instantiate_in_zero_one_stop_domain',
                        'exactness': 'exhaustive_zero_one_stop; canonical_usable_chargers; time_optimal_legs_only',
                        'window_start_s': window[0], 'window_end_s': window[1],
                        'reachable_charger_with_meal_support_count': reach,
                        'direct_terminal_energy_kwh': trip.initial_energy_kwh - ev.drive_energy(baseline.distance_m),
                        'stop_count': None if plan is None else plan.stop_count,
                        'site_id': None if plan is None or not plan.stops else plan.stops[0].site_id,
                        'clock_s': None if plan is None else plan.clock_s,
                        'drive_s': None if plan is None else plan.drive_s,
                        'distance_m': None if plan is None else plan.distance_m,
                        'detour_s': None if plan is None else plan.drive_s - baseline.time_s,
                        'charged_kwh': None if plan is None else sum(e.charged_kwh for e in plan.stops),
                        'charging_duration_s': None if plan is None else sum(e.charging_duration_s for e in plan.stops),
                        'terminal_energy_kwh': None if plan is None else plan.terminal_energy_kwh,
                        'requirement_penalty_s': None if plan is None else plan.requirement_penalty_s,
                        'generalized_cost_s': None if plan is None else plan.generalized_cost_s,
                        'scheduled_activity_start_s': None if plan is None or not plan.stops else plan.stops[0].scheduled_start_s})
        runtime.append({'instance_id': int(od.instance_id), 'routing_seconds': routing_s,
                        'one_stop_planning_seconds': time.perf_counter() - planning_start,
                        'od_total_seconds': time.perf_counter() - od_start, 'peak_rss_mib': peak_rss_mib()})
        print(f'OD {od.instance_id:02d}: completed, {runtime[-1]["od_total_seconds"]:.2f}s, peak {peak_rss_mib():.1f} MiB', flush=True)
        del ft, fl, rt, rl, parents, next_nodes, travel
    router.close()
    plans = pd.DataFrame(records); envelopes = pd.DataFrame(envelope_records)
    plans.to_parquet(out / 'one_stop_diagnostics.parquet', index=False, compression='zstd')
    plans.to_csv(out / 'one_stop_diagnostics.csv', index=False)
    envelopes.to_parquet(out / 'envelope_site_counts.parquet', index=False, compression='zstd')
    pd.DataFrame(runtime).to_csv(out / 'diagnostic_runtime.csv', index=False)
    inputs = [cfg['inventory'], cfg['attachments'], cfg['development_ods'], cfg['graph_data_config'], 'configs/routing.yaml', 'RESEARCH_SPEC_v0.2.md', args.config]
    inputs += [str((ROOT / data['graph_dir'] / name).relative_to(ROOT)) for name in ['nodes.parquet', 'edges.parquet', 'metadata.json']]
    summary = [{'scenario': scenario, 'initial_soc': float(soc), 'cases': len(group),
        'feasible_cases': int(group.feasible.sum()), 'cannot_instantiate_cases': int((~group.feasible).sum()),
        'zero_stop_cases': int(group.stop_count.eq(0).sum()), 'one_stop_cases': int(group.stop_count.eq(1).sum()),
        'charging_cases': int(group.charged_kwh.gt(1e-8).sum()),
        'median_clock_s_feasible': None if not group.feasible.any() else float(group.clock_s.median())}
        for (scenario, soc), group in plans.groupby(['scenario', 'initial_soc'])]
    record = {'command': ' '.join(__import__('sys').argv), 'configuration': cfg,
        'scope': 'development only; not holdout or revised Go-1; no multi-stop real experiment',
        'assumptions': ['all attached charger anchors usable under synthetic canonical curve',
                        'fixed time-optimal directed legs; alternative time/energy road paths not enumerated',
                        'geographic local support does not certify walkability or legal stopping access'],
        'exactness': 'all eligible Sites, zero/one-stop, continuous minimum charging, analytical schedule starts; no candidate caps',
        'multi_stop': 'not run; continuous exhaustive small-world reference and synthetic tests only',
        'uninstantiated_semantics': 'future-stop coupling and two-stop nuisance tradeoffs not instantiated by this one-stop domain; unknown-availability queries synthetic only',
        'development_od_count': len(ods), 'case_count': len(plans), 'envelope_case_count': len(envelopes),
        'graph_load_seconds': graph_load_s, 'runtime_seconds': time.perf_counter() - start,
        'peak_rss_mib': peak_rss_mib(), 'memory_preflight': preflight, 'summary': summary,
        'independent_route_checks': checks, 'native_routing': router.provenance,
        'inputs': {p: sha256(ROOT / p) for p in inputs},
        'outputs': {name: sha256(out / name) for name in ['one_stop_diagnostics.parquet', 'one_stop_diagnostics.csv', 'envelope_site_counts.parquet', 'diagnostic_runtime.csv']}}
    write_json(out / 'diagnostic.json', record)
    print(json.dumps({k: record[k] for k in ['case_count', 'runtime_seconds', 'peak_rss_mib', 'summary']}, indent=2))


if __name__ == '__main__':
    main()
