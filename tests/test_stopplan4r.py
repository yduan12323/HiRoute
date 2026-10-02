"""4R acceptance: independently enumerated toy worlds and semantic boundaries."""
from dataclasses import replace
from itertools import permutations, product
import math

import numpy as np
import pandas as pd
import pytest

from graph.road_graph import IgraphRoadGraph
from stopplan4r.models import (EVModel, LocalSupport, PiecewiseChargingCurve, PlannerConfig,
                               ScheduledStop, SearchLabel, StopSite, Trip)
from stopplan4r.evaluation import GraphTravel, best_one_stop, evaluate_site
from stopplan4r.planner import FlatStopPlanner
from stopplan4r.sites import build_sites, sites_from_table, validate_static_table
from stopplan4r.uncertainty import (Candidate, ChargerEvidence, CostInterval, EvidenceState as E,
                                  Query, decision_pruned, query_allowed, resolve_query)

EV = EVModel()
CURVE = PiecewiseChargingCurve(((1, 60),))


def site(node, charge=True, meal=1, toilet=0):
    return StopSite(f'4r:node/{node + 100}', 'node', node + 100, 46, 14 + node * 0.001, node,
                    frozenset({'charge' if charge else 'parking'}), LocalSupport(meal_count=meal, toilet_count=toilet))


def world(energies=(10, 15, 15), times=None):
    n = len(energies) + 1
    times = (60,) * len(energies) if times is None else times
    nodes = pd.DataFrame({'node_id': range(n), 'osm_node_id': range(n), 'lat': [46.] * n, 'lon': np.arange(n) * 0.01 + 14})
    edges = pd.DataFrame({'edge_id': range(n - 1), 'source': range(n - 1), 'target': range(1, n),
                          'length_m': np.array(energies) / EV.consumption_kwh_km * 1000,
                          'travel_time_s': times})
    return GraphTravel(IgraphRoadGraph(nodes, edges))


def grid_oracle(trip, sites, travel, ev, curves, schedule, cfg):
    """Independent finite exhaustive oracle, no planner/evaluator assembly calls.

    Fixture energies and continuous optima lie at integer kWh breakpoints. The
    oracle explicitly enumerates every stop order, departure energy, requirement
    assignment and relevant schedule start; it verifies the known small cases.
    """
    best = math.inf
    for count in range(cfg.maximum_stops + 1):
        for order in permutations(sites, count):
            nodes = [trip.origin, *(s.access_node for s in order), trip.destination]
            legs = [travel.leg(a, b) for a, b in zip(nodes, nodes[1:])]
            if any(l is None for l in legs):
                continue
            drive = sum(l.time_s for l in legs)
            if trip.mobility_budget_s is not None and drive > trip.mobility_budget_s:
                continue
            assignments = [None] if schedule is None or not schedule.hard else []
            if schedule:
                assignments += [i for i, s in enumerate(order) if s.support.meal_count >= schedule.meal_threshold]
            energies = [range(int(ev.capacity_kwh) + 1) if 'charge' in s.transport_capabilities else [None] for s in order]
            for departures in product(*energies):
                for activity_at in assignments:
                    energy, clock = trip.initial_energy_kwh, 0.0
                    penalty = schedule.miss_penalty_s if schedule and activity_at is None else 0.0
                    valid = True
                    for i, s in enumerate(order):
                        clock += legs[i].time_s; energy -= ev.drive_energy(legs[i].distance_m)
                        departure = energy if departures[i] is None else departures[i]
                        if energy < ev.minimum_energy_kwh - 1e-8 or departure < energy - 1e-8:
                            valid = False; break
                        curve = curves.get(s.site_id, CURVE)
                        duration = sum(max(0, min(departure, hi) - max(energy, lo)) * slope
                                       for lo, hi, slope, _ in curve.segments(ev.capacity_kwh))
                        dwell = cfg.overhead_s + duration
                        if i == activity_at:
                            earliest = clock + cfg.overhead_s + (0 if schedule.compatible_with_charging else duration)
                            choices = []
                            starts = {max(earliest, x) for x in (earliest,
                                schedule.window_start_s - trip.start_time_s,
                                schedule.window_end_s - trip.start_time_s,
                                clock + cfg.overhead_s + duration - schedule.duration_s)}
                            for start in starts:
                                off = max(schedule.window_start_s - trip.start_time_s - start,
                                          start - (schedule.window_end_s - trip.start_time_s), 0)
                                if not schedule.hard or off < 1e-8:
                                    d = max(dwell, start - clock + schedule.duration_s)
                                    p = off * schedule.time_penalty_per_s
                                    choices.append((d + p, d, p))
                            if not choices:
                                valid = False; break
                            _, dwell, penalty = min(choices)
                        clock += dwell; energy = departure
                    energy -= ev.drive_energy(legs[-1].distance_m)
                    if valid and energy >= ev.terminal_floor - 1e-8:
                        clock += legs[-1].time_s
                        cost = clock + cfg.lambda_stop_s * count + penalty + cfg.distance_penalty_s_per_km * sum(l.distance_m for l in legs) / 1000
                        best = min(best, cost)
    return best


def check_oracle(planner, trip, sites, schedule=None):
    result = planner.solve(trip, sites, schedule)
    expected = grid_oracle(trip, sites, planner.travel, planner.ev, planner.site_curves, schedule, planner.config)
    assert (result is None) == math.isinf(expected)
    if result:
        assert result.generalized_cost_s == pytest.approx(expected, abs=1e-5)
    return result


def test_01_enough_energy_scheduled_stop_does_not_force_charge():
    p = FlatStopPlanner(world((5, 5)), curve=CURVE, config=PlannerConfig(0, 0, maximum_stops=1))
    plan = check_oracle(p, Trip(0, 2, 30), [site(1, charge=False)], ScheduledStop(0, 1000, 600))
    assert plan.stop_count == 1 and plan.stops[0].charged_kwh == 0


def test_02_insufficient_energy_rejects_noncharging_plan():
    p = FlatStopPlanner(world((10, 30)), curve=CURVE, config=PlannerConfig(maximum_stops=1))
    assert check_oracle(p, Trip(0, 2, 15), [site(1, charge=False)]) is None
    assert check_oracle(p, Trip(0, 2, 15), [site(1)]).terminal_energy_kwh == pytest.approx(6)


def test_03_charger_and_local_meal_are_one_overlapping_stop():
    p = FlatStopPlanner(world((10, 30)), curve=CURVE, config=PlannerConfig(120, 0, maximum_stops=1))
    plan = check_oracle(p, Trip(0, 2, 15), [site(1)], ScheduledStop(0, 1000, 2700))
    event = plan.stops[0]
    assert event.charged_kwh == pytest.approx(31)
    assert event.duration_s == pytest.approx(120 + max(31 * 60, 2700))
    assert plan.clock_s == pytest.approx(120 + event.duration_s)


def inventory_fixture():
    caps = [['parking'], ['meal'], ['charge', 'sleep'], ['toilets'], ['rest'], ['services'], ['groceries'], ['pharmacy']]
    table = pd.DataFrame({'osm_type': ['node'] * len(caps), 'osm_id': range(1, len(caps) + 1),
                          'lat': [46.] * len(caps), 'lon': [14 + i * .0002 for i in range(len(caps))],
                          'capabilities': caps, 'original_tags': ['{}'] * len(caps),
                          'geometry_type': ['Point'] * len(caps), 'geometry_method': ['OSM node'] * len(caps),
                          'source_datasets': [('toy',)] * len(caps), 'snapshot_timestamp': ['toy'] * len(caps)})
    attachment = table[['osm_type', 'osm_id']].copy()
    attachment['access_node'] = range(len(caps)); attachment['access_osm_node_id'] = range(len(caps))
    attachment['access_distance_m'] = 0.; attachment['attachment_status'] = 'attached'
    return table, attachment


def test_04_local_restaurant_is_never_a_vehicle_waypoint():
    raw, attached = inventory_fixture()
    table, _, _ = build_sites(raw, attached)
    anchors = sites_from_table(table)
    assert set(table.osm_id) == {1, 3, 5, 6}
    assert all(s.support.meal_count == 1 for s in anchors)
    # Restrict to a small directed graph with transport anchor 0 and meal POI 1.
    p = FlatStopPlanner(world((5,)), curve=CURVE, config=PlannerConfig(0, 0, maximum_stops=1))
    plan = p.solve(Trip(0, 1, 30), [anchors[0]], ScheduledStop(0, 1000, 600))
    assert [e.site_id for e in plan.stops] == ['4r:node/1']


def test_05_charge_meal_toilet_same_anchor_counts_once():
    p = FlatStopPlanner(world((10, 30)), curve=CURVE, config=PlannerConfig(0, 500, maximum_stops=1))
    plan = check_oracle(p, Trip(0, 2, 15), [site(1, toilet=2)], ScheduledStop(0, 1000, 2700))
    assert plan.stop_count == 1
    assert plan.generalized_cost_s == pytest.approx(plan.clock_s + 500)


def test_06_no_implicit_fatigue_rest_stop():
    p = FlatStopPlanner(world((5, 5), (7200, 7200)), curve=CURVE)
    plan = check_oracle(p, Trip(0, 2, 50), [replace(site(1), transport_capabilities=frozenset({'rest'}))])
    assert plan.stop_count == 0 and plan.clock_s == 14400


def test_07_later_window_aligned_charger_can_beat_earlier():
    p = FlatStopPlanner(world((10, 5, 20), (300, 900, 300)), curve=CURVE, config=PlannerConfig(0, 100, maximum_stops=2))
    plan = check_oracle(p, Trip(0, 3, 20), [site(1), site(2)], ScheduledStop(1200, 1500, 600))
    assert [e.site_id for e in plan.stops] == [site(2).site_id]


def test_08_76_percent_sufficient_never_waits_for_80_percent():
    p = FlatStopPlanner(world((10, 17)), curve=CURVE, config=PlannerConfig(0, 0, maximum_stops=1))
    plan = p.solve(Trip(0, 2, .76 * 60), [site(1)], ScheduledStop(0, 1000, 600))
    assert plan.stops[0].charged_kwh == 0
    assert plan.clock_s == 120 + 600


def test_09_extra_15_minutes_now_avoids_later_25_minute_stop():
    p = FlatStopPlanner(world(), curve=CURVE, config=PlannerConfig(600, 0, maximum_stops=2))
    sites, schedule, trip = [site(1), site(2, meal=0)], ScheduledStop(0, 1000, 900), Trip(0, 3, 10)
    plan = check_oracle(p, trip, sites, schedule)
    assert plan.stop_count == 1 and plan.stops[0].charged_kwh == pytest.approx(36)
    # To reach B with the execution floor needs 15 kWh (15 min); here terminal
    # reserve adds 6 kWh. Compare an alternative A departure=21 kWh, then B=21.
    # A charges 21 min, extra 15 min at A saves a B event of 10 + 15 = 25 min.
    assert plan.stops[0].charging_duration_s - 21 * 60 == pytest.approx(15 * 60)
    two = p.optimize_order(trip, sites, schedule)
    assert two.clock_s - plan.clock_s == pytest.approx(10 * 60)


def test_10_stop_penalty_changes_one_vs_two_stop_choice():
    sites = [site(1), site(2, meal=0)]
    curves = {sites[0].site_id: PiecewiseChargingCurve(((1, 30),))}
    trip, schedule = Trip(0, 3, 10), ScheduledStop(0, 1000, 900)
    cfg = PlannerConfig(600, 0, maximum_stops=2)
    p = FlatStopPlanner(world(), curve=CURVE, config=cfg, site_curves=curves)
    two = check_oracle(p, trip, sites, schedule)
    one = check_oracle(FlatStopPlanner(p.travel, curve=CURVE, config=replace(cfg, lambda_stop_s=2000), site_curves=curves), trip, sites, schedule)
    assert two.stop_count == 2 and one.stop_count == 1
    assert two.clock_s < one.clock_s


def candidate(lower=60, usability=E.UNKNOWN):
    return Candidate('B', CostInterval(lower, 140), ChargerEvidence(E.PRESENT, usability))


def test_11_decision_pruning_precedes_query_logic():
    def must_not_be_called(latency):
        raise AssertionError('Already-pruned candidate reached query feasibility')
    allowed, reason = query_allowed(candidate(99), CostInterval(100, 100), Query('B', 1, 10, 1), must_not_be_called, epsilon_dec=2)
    assert not allowed and reason == 'decision_pruned'
    assert decision_pruned(CostInterval(98, 120), CostInterval(100, 100), 2)


def test_12_unknown_usability_is_conditionally_viable():
    b = candidate()
    assert b.charger.conditionally_viable
    assert query_allowed(b, CostInterval(100, 100), Query('B', 1, 10, 1), lambda dt: True)[0]
    assert not candidate(usability=E.ABSENT).charger.conditionally_viable


def fallback_world():
    travel = world((5, 5), (10, 10))
    p = FlatStopPlanner(travel, curve=CURVE, config=PlannerConfig(0, 0, maximum_stops=1))
    # Explicit latest activity start acts as the reachability deadline after wait.
    def feasible(delay):
        return p.solve(Trip(0, 2, 30, start_time_s=delay), [site(1)], ScheduledStop(0, 20, 5)) is not None
    return feasible


def test_13_unfavorable_query_falls_back_after_latency():
    result = resolve_query(candidate(), CostInterval(100, 100), Query('B', 1, 5, 1), E.ABSENT, 'A', fallback_world())
    assert result == ('A', 'unfavorable_fallback')


def test_14_do_not_wait_if_latency_destroys_fallback():
    f = fallback_world()
    assert f(0) and not f(15)
    assert query_allowed(candidate(), CostInterval(100, 100), Query('B', 1, 15, 1), f) == (False, 'fallback_expires')
    assert resolve_query(candidate(), CostInterval(100, 100), Query('B', 1, 15, 1), E.PRESENT, 'A', f) == ('A', 'fallback_expires')


def test_15_region_labels_never_remove_a_flat_plan():
    travel = world((10, 15, 40))
    p = FlatStopPlanner(travel, curve=CURVE, config=PlannerConfig(0, 0, maximum_stops=2))
    sites, trip = [site(1), site(2, meal=0)], Trip(0, 3, 10)
    schedule = ScheduledStop(0, 1000, 600)
    expected = p.solve(trip, sites, schedule)
    actual = p.solve(trip, sites, schedule, region_labels={sites[0].site_id: 'R1', sites[1].site_id: 'R2'})
    assert actual == expected and actual.stop_count == 2


def test_static_schema_ids_and_threshold_are_trip_independent(tmp_path):
    raw, attachments = inventory_fixture()
    a, support, _ = build_sites(raw, attachments)
    b, _, _ = build_sites(raw.sample(frac=1, random_state=5), attachments.sample(frac=1, random_state=4), primary_radius_m=750)
    assert a.site_id.tolist() == b.site_id.tolist()
    path = tmp_path / 'sites.parquet'; a.to_parquet(path, index=False)
    loaded = pd.read_parquet(path); validate_static_table(loaded)
    for dynamic in ['detour', 'arrival_time', 'arrival_soc', 'arrival_energy', 'generalized_cost', 'progress', 'user_score']:
        with pytest.raises(ValueError):
            validate_static_table(loaded.assign(**{dynamic: 1}))
    sites = sites_from_table(a)
    assert ScheduledStop(0, 1000, meal_threshold=1).supports(sites[0])
    assert not ScheduledStop(0, 1000, meal_threshold=2).supports(sites[0])
    assert set(support.radius_m) == {250, 500, 750}


def test_indexed_support_matches_independent_geographic_scan():
    raw, attachments = inventory_fixture()
    raw.loc[1, 'lon'] = 14.006
    table, support, _ = build_sites(raw, attachments)
    for row in support.itertuples():
        anchor = table[table.site_id.eq(row.site_id)].iloc[0]
        for field, cap in [('meal', 'meal'), ('toilet', 'toilets'), ('lodging', 'sleep')]:
            ds = []
            for point in raw.itertuples():
                if cap in point.capabilities:
                    p1, p2 = np.deg2rad([anchor.lat, point.lat])
                    dp, dl = p2 - p1, np.deg2rad(point.lon - anchor.lon)
                    d = 2 * 6371008.8 * np.arcsin(np.sqrt(np.sin(dp / 2)**2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2)**2))
                    if d <= row.radius_m:
                        ds.append(d)
            assert getattr(row, field + '_count') == len(ds)
            nearest = getattr(row, 'nearest_' + field + '_m')
            assert nearest == pytest.approx(min(ds), abs=1e-6) if ds else pd.isna(nearest)


def test_piecewise_curve_and_global_continuous_charging():
    curve = PiecewiseChargingCurve()
    assert curve.duration_s(24, 54, 60) == pytest.approx(6 * 36 + 18 * 60 + 6 * 120)
    p = FlatStopPlanner(world((10, 15, 15)), curve=curve, config=PlannerConfig(600, 0, maximum_stops=2))
    trip, sites, schedule = Trip(0, 3, 10), [site(1), site(2, meal=0)], ScheduledStop(0, 1000, 900)
    # Independent oracle uses the actual piecewise curve for each Site.
    expected = grid_oracle(trip, sites, p.travel, EV, {s.site_id: curve for s in sites}, schedule, p.config)
    actual = p.solve(trip, sites, schedule)
    assert actual.generalized_cost_s == pytest.approx(expected, abs=1e-5)
    assert all(label.energy_kwh >= 0 for label in actual.labels)


@pytest.mark.parametrize('rate', [0, .5, 2])
@pytest.mark.parametrize('compatible', [True, False])
def test_one_stop_analytic_equals_continuous_optimizer(rate, compatible):
    travel, anchors = world((10, 30)), [site(1)]
    trip = Trip(0, 2, 15, start_time_s=1000)
    schedule = ScheduledStop(2400, 2500, 900, hard=False, time_penalty_per_s=rate, compatible_with_charging=compatible)
    cfg = PlannerConfig(120, 500, maximum_stops=1)
    fast = best_one_stop(trip, anchors, travel, EV, CURVE, schedule, cfg)
    slow = FlatStopPlanner(travel, curve=CURVE, config=replace(cfg, maximum_stops=2)).solve(trip, anchors, schedule)
    assert fast.generalized_cost_s == pytest.approx(slow.generalized_cost_s, abs=1e-5)


def test_soft_requirement_cannot_evade_penalty_by_omission():
    p = FlatStopPlanner(world((5,)), curve=CURVE, config=PlannerConfig(0, 0, maximum_stops=1))
    schedule = ScheduledStop(0, 100, 600, hard=False, miss_penalty_s=700)
    plan = p.solve(Trip(0, 1, 30), [], schedule)
    assert plan.requirement_penalty_s == 700 and plan.generalized_cost_s == 760


def test_energy_floor_and_no_terminal_reward_or_free_extra_charge():
    ev = replace(EV, minimum_energy_kwh=2, robust_margin_kwh=3)
    p = FlatStopPlanner(world((10, 30)), ev=ev, curve=CURVE, config=PlannerConfig(0, 0, maximum_stops=2))
    plan = p.solve(Trip(0, 2, 15), [site(1)], ScheduledStop(0, 1000, 3600))
    assert plan.terminal_energy_kwh == pytest.approx(9)
    assert plan.stops[0].charged_kwh == pytest.approx(34)
    assert FlatStopPlanner(world((15, 5)), ev=ev, curve=CURVE).solve(Trip(0, 2, 15), [site(1)]) is None


def test_unattached_transport_site_is_preserved_but_not_routed():
    raw, attachments = inventory_fixture()
    attachments.loc[0, ['access_node', 'access_osm_node_id', 'attachment_status']] = [-1, -1, 'too_far']
    table, _, _ = build_sites(raw, attachments)
    s = sites_from_table(table)[0]
    assert s.access_node is None and s.site_id == '4r:node/1'
    assert best_one_stop(Trip(0, 1, 30), [s], world((5,)), EV, CURVE, ScheduledStop(0, 1000), PlannerConfig()) is None


def test_trip_evaluator_uses_partial_state_and_keeps_site_static():
    s, travel = site(2), world()
    original = repr(s)
    state = SearchLabel(1, 1200, 25, False, 1, 1200)
    view = evaluate_site(s, state, 3, travel, EV, CURVE, ScheduledStop(0, 2000, 900), PlannerConfig(), True)
    assert view.arrival_time_s == 1260 and view.arrival_energy_kwh == pytest.approx(10)
    assert view.required_charge_kwh == pytest.approx(11)
    shifted = evaluate_site(s, state, 3, travel, EV, CURVE, ScheduledStop(2000, 3000, 900), PlannerConfig(), True, start_time_s=1000)
    assert shifted.arrival_time_s == 2260
    assert repr(s) == original


def test_query_quality_and_cost_interval_validation():
    with pytest.raises(ValueError):
        CostInterval(5, 4)
    with pytest.raises(ValueError):
        Query('B', 0, -1, 1)
    assert query_allowed(candidate(), CostInterval(100, 100), Query('B', 1, 2, .8), lambda dt: True)[1] == 'insufficient_reliability'
    assert not decision_pruned(CostInterval(0, math.inf), CostInterval(100, 100))
