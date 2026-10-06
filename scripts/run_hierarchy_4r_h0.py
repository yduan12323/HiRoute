"""B1 migration gate. Run before hierarchy construction, never writes 4R-A."""
import json
import time
from dataclasses import asdict
import numpy as np
import pandas as pd
from _common import ROOT, configs, load_graph, read_config, sha256
from _stopplan4r_common import memory_guard, peak_rss_mib, write_json
from microplan.routing import ExactRouter
from run_stopplan_4r_diagnostic import ODTravel
from stopplan4r.sites import sites_from_table
from stopplan4r.models import EVModel, PiecewiseChargingCurve, PlannerConfig, ScheduledStop, Trip
from hierarchy4r.domain import flat_actions, effects, best, action_id, equal_value


def main():
    out = ROOT / 'results/milestone_4r_b1'
    if (out / 'h0_summary.json').exists():
        raise FileExistsError('H0 evidence already exists; do not silently overwrite')
    cfg = read_config('configs/stopplan_4r.yaml')
    ev, curve = EVModel(**cfg['ev']), PiecewiseChargingCurve(tuple(map(tuple, cfg['charging']['bands'])))
    pc = PlannerConfig(**cfg['planner'])
    start = time.perf_counter()
    memory_guard(cfg['memory'], projected_additional_gib=7)
    sites = tuple(s for s in sites_from_table(pd.read_parquet(ROOT / 'results/milestone_4r/stop_sites.parquet'))
                  if s.attachment_status == 'attached' and s.access_node is not None)
    access = np.array([s.access_node for s in sites])
    data, routing = configs(cfg['graph_data_config'])
    graph = load_graph(data, routing)
    router = ExactRouter(graph, cfg, out / 'h0_native_cache')
    ods = pd.read_parquet(ROOT / cfg['development_ods']).sort_values('instance_id')
    accepted = pd.read_parquet(ROOT / 'results/milestone_4r/one_stop_diagnostics.parquet')
    assert len(ods) == 30
    rows, excluded, identities, runtime = [], [], [], []
    (out / 'flat_reference').mkdir(exist_ok=True)
    failed = False
    for od in ods.itertuples():
        memory_guard(cfg['memory'], projected_additional_gib=1)
        ts = time.perf_counter()
        ft, fl, _ = router.full(int(od.origin_node))
        rt, rl, _ = router.full(int(od.destination_node), reverse=True)
        routing_s = time.perf_counter() - ts
        travel = ODTravel(int(od.origin_node), int(od.destination_node), ft, fl, rt, rl)
        baseline = travel.leg(travel.origin, travel.destination)
        assert np.isclose(baseline.time_s, od.ext_baseline_time_s)
        lower = ft[access] + rt[access]
        for ratio in cfg['diagnostics']['envelope_ratios']:
            budget = ratio * baseline.time_s
            indices = np.flatnonzero(np.isfinite(lower) & (lower <= budget + 1e-8 + budget * 1e-10))
            eligible = tuple(sites[i] for i in indices)
            window = [x * baseline.time_s for x in cfg['diagnostics']['window_baseline_fraction']]
            for soc in cfg['diagnostics']['initial_soc']:
                trip = Trip(travel.origin, travel.destination, soc * ev.capacity_kwh, mobility_budget_s=budget)
                for scenario in ['energy_only', 'energy_and_scheduled']:
                    schedule = None if scenario == 'energy_only' else ScheduledStop(*window)
                    case_id = len(rows)
                    context = dict(case_id=case_id, instance_id=int(od.instance_id), ratio=ratio,
                                   initial_soc=soc, scenario=scenario)
                    eval_start = time.perf_counter()
                    legacy, plans = flat_actions(trip, eligible, travel, ev, curve, schedule, pc)
                    records, semantic = [], []
                    if 'zero' in plans:
                        semantic.append(plans['zero'])
                    counts = dict.fromkeys(['C', 'S', 'CS'], 0)
                    empty = 0
                    for site in eligible:
                        plan = plans.get(site.site_id)
                        role = effects(plan, site, schedule)
                        if role:
                            counts[role] += 1
                            semantic.append(plan)
                        first, last = travel.leg(trip.origin, site.access_node), travel.leg(site.access_node, trip.destination)
                        event = plan.stops[0] if plan else None
                        r = dict(site_id=site.site_id, access_node=site.access_node,
                            feasible=plan is not None, role=role, tm=first.time_s, tp=last.time_s,
                            lm=first.distance_m, lp=last.distance_m,
                            arrival_energy=trip.initial_energy_kwh - ev.drive_energy(first.distance_m),
                            required_energy=ev.terminal_floor + ev.drive_energy(last.distance_m),
                            charge_kwh=None if event is None else event.charged_kwh,
                            charge_s=None if event is None else event.charging_duration_s,
                            scheduled_start=None if event is None else event.scheduled_start_s,
                            completion=None if event is None else event.departure_time_s,
                            cost=None if plan is None else plan.generalized_cost_s,
                            terminal_energy=None if plan is None else plan.terminal_energy_kwh)
                        records.append(r)
                        if plan and not role:
                            empty += 1
                            excluded.append({**context, **r})
                    semantic_best = best(semantic)
                    ok = equal_value(legacy, semantic_best)
                    ident = action_id(legacy) != action_id(semantic_best)
                    previous = accepted[(accepted.instance_id == od.instance_id) & (accepted.ratio == ratio)
                        & (accepted.initial_soc == soc) & (accepted.scenario == scenario)].iloc[0]
                    assert legacy is not None and round(legacy.generalized_cost_s, 7) == round(previous.generalized_cost_s, 7)
                    assert action_id(legacy) == ('zero' if previous.stop_count == 0 else previous.site_id)
                    row = {**context, 'legacy_eligible_site_count': len(eligible),
                        'effect_free_feasible_actions': empty, **{f'semantic_{k}': v for k, v in counts.items()},
                        'legacy_cost': legacy.generalized_cost_s,
                        'legacy_action': action_id(legacy),
                        'semantic_cost': None if semantic_best is None else semantic_best.generalized_cost_s,
                        'semantic_action': action_id(semantic_best),
                        'cost_difference': None if semantic_best is None else semantic_best.generalized_cost_s - legacy.generalized_cost_s,
                        'legacy_optimum_effect_free': bool(legacy.stops and not next(r['role'] for r in records if r['site_id'] == action_id(legacy))),
                        'identity_changed': ident, 'passed': ok}
                    rows.append(row)
                    if ident and ok:
                        identities.append(row)
                    pd.DataFrame(records).to_parquet(out / 'flat_reference' / f'case_{case_id:03d}.parquet', index=False)
                    meta = {**context, 'trip': asdict(trip), 'baseline': asdict(baseline),
                        'schedule': None if schedule is None else asdict(schedule),
                        'zero': None if 'zero' not in plans else asdict(plans['zero']),
                        'legacy': asdict(legacy), 'semantic': None if semantic_best is None else asdict(semantic_best),
                        'flat_evaluation_seconds': time.perf_counter() - eval_start}
                    write_json(out / 'flat_reference' / f'case_{case_id:03d}.json', meta)
                    if not ok:
                        failed = True
                        write_json(out / 'h0_failure_witness.json', {**meta, 'legacy_site': next(r for r in records if r['site_id'] == action_id(legacy)),
                            'overhead_s': pc.overhead_s, 'lambda_stop_s': pc.lambda_stop_s, 'comparison': row})
                        break
                if failed: break
            if failed: break
        runtime.append(dict(instance_id=int(od.instance_id), routing_seconds=routing_s,
                            total_seconds=time.perf_counter() - ts, peak_rss_mib=peak_rss_mib()))
        print(f'H0 OD {od.instance_id}: {len(rows)}/480 cases; failures={int(failed)}', flush=True)
        if failed: break
    frame = pd.DataFrame(rows)
    frame.to_csv(out / 'h0_domain_migration.csv', index=False)
    frame.to_parquet(out / 'h0_domain_migration.parquet', index=False)
    pd.DataFrame(excluded, columns=list(context) + list(records[0])).to_csv(out / 'h0_excluded_effect_free_actions.csv', index=False)
    pd.DataFrame(identities, columns=frame.columns).to_csv(out / 'h0_identity_changes.csv', index=False)
    pd.DataFrame(runtime).to_csv(out / 'h0_runtime.csv', index=False)
    summary = dict(cases_expected=480, cases_evaluated=len(rows), cost_mismatches=int((~frame.passed).sum()),
        identity_only_changes=len(identities), total_feasible_effect_free_actions=int(frame.effect_free_feasible_actions.sum()),
        passed=bool(len(rows) == 480 and frame.passed.all()), runtime_seconds=time.perf_counter() - start,
        peak_rss_mib=peak_rss_mib(), amendment_sha256=sha256(ROOT / 'docs/MILESTONE_4R_B1_ACTION_DOMAIN_AMENDMENT.md'),
        source_sha256={str(p.relative_to(ROOT)): sha256(p) for p in [Path(__file__), ROOT/'src/hierarchy4r/domain.py']},
        reference_sha256={str(p.relative_to(out)): sha256(p) for p in sorted((out/'flat_reference').iterdir())},
        native_routing=router.provenance)
    write_json(out / 'h0_summary.json', summary)
    router.close()
    print(json.dumps({k:v for k,v in summary.items() if not isinstance(v,dict)}, indent=2))


if __name__ == '__main__':
    from pathlib import Path
    main()
