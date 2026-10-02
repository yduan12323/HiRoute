"""Trip-conditioned evaluation, never serialized into the static world."""
from dataclasses import dataclass
from math import inf

from graph.road_graph import NoPathError
from .models import EVModel, Plan, PlannerConfig, SearchLabel, StopEvent, TravelLeg


class GraphTravel:
    """Use time-optimal directed graph paths and their actual lengths."""
    def __init__(self, graph):
        self.graph = graph
        self.cache = {}

    def leg(self, source, target):
        key = (source, target)
        if key not in self.cache:
            try:
                route = self.graph.shortest_path(source, target, 'travel_time')
                self.cache[key] = TravelLeg(route.travel_time_s, route.distance_m)
            except NoPathError:
                self.cache[key] = None
        return self.cache[key]


@dataclass(frozen=True)
class SiteEvaluation:
    arrival_time_s: float
    arrival_energy_kwh: float
    detour_s: float
    energy_feasible: bool
    required_charge_kwh: float
    charging_duration_s: float
    scheduled_satisfied: bool
    scheduled_penalty_s: float
    stop_duration_s: float


def validate_trip(trip, ev):
    import math
    if not math.isfinite(trip.initial_energy_kwh) or not ev.minimum_energy_kwh <= trip.initial_energy_kwh <= ev.capacity_kwh or not math.isfinite(trip.start_time_s):
        raise ValueError('Invalid trip state')
    if trip.mobility_budget_s is not None and (not math.isfinite(trip.mobility_budget_s) or trip.mobility_budget_s < 0):
        raise ValueError('Invalid mobility budget')


def scheduled_start_candidates(arrival, charging, schedule, config, time_origin=0.0):
    """All breakpoints of the one-stop makespan + window-deviation objective.

    Compatible charging creates free slack: activity may start later without
    extending dwell until charge_end - activity_duration. This breakpoint is
    necessary when a soft early-arrival penalty is less than one second/second.
    """
    earliest = arrival + config.overhead_s + (0 if schedule.compatible_with_charging else charging)
    return sorted({max(earliest, t) for t in (
        earliest, schedule.window_start_s - time_origin, schedule.window_end_s - time_origin,
        arrival + config.overhead_s + charging - schedule.duration_s)})


def evaluate_site(site, state, destination, travel, ev, curve, schedule, config, perform_scheduled=False, start_time_s=0.0):
    """Evaluate a partial elapsed-time label; returned arrival time is absolute.

    Minimum charging is to finish directly, separate from multi-stop optimization.
    Pass the trip's clock origin when evaluating labels from a nonzero-start trip.
    """
    if site.access_node is None or site.attachment_status != 'attached':
        return None
    first, last, baseline = (travel.leg(state.anchor, site.access_node),
                              travel.leg(site.access_node, destination),
                              travel.leg(state.anchor, destination))
    if first is None or last is None or baseline is None:
        return None
    arrival = start_time_s + state.elapsed_s + first.time_s
    energy = state.energy_kwh - ev.drive_energy(first.distance_m)
    needed = max(0.0, ev.drive_energy(last.distance_m) + ev.terminal_floor - energy)
    feasible = energy >= ev.minimum_energy_kwh - 1e-8 and energy + needed <= ev.capacity_kwh + 1e-8 and (needed <= 1e-8 or 'charge' in site.transport_capabilities)
    charging = curve.duration_s(max(0.0, energy), min(ev.capacity_kwh, energy + needed), ev.capacity_kwh) if feasible else inf
    satisfied = bool(perform_scheduled and schedule is not None and schedule.supports(site))
    activity = schedule.duration_s if satisfied else 0.0
    penalty, duration = 0.0, config.overhead_s + charging
    if satisfied and feasible:
        starts = scheduled_start_candidates(arrival, charging, schedule, config)
        def values(start):
            off_window = max(schedule.window_start_s - start, start - schedule.window_end_s, 0)
            penalty = off_window * schedule.time_penalty_per_s
            if schedule.hard and off_window > 1e-8:
                penalty = inf
            dwell = max(config.overhead_s + charging, start - arrival + activity)
            return dwell + penalty, dwell, penalty, start
        _, duration, penalty, _ = min(map(values, starts))
    return SiteEvaluation(arrival, energy, first.time_s + last.time_s - baseline.time_s,
                          feasible, needed, charging, satisfied, penalty, duration)


def assemble_plan(trip, sites, legs, arrivals_e, departures_e, arrivals_t, departures_t,
                  charge_times, scheduled_index, scheduled_start, penalty, ev, config):
    events, labels = [], [SearchLabel(trip.origin, 0.0, trip.initial_energy_kwh, False, 0, 0.0)]
    drive_s = sum(leg.time_s for leg in legs)
    distance_m = sum(leg.distance_m for leg in legs)
    for i, site in enumerate(sites):
        activity_start = scheduled_start if i == scheduled_index else None
        events.append(StopEvent(site.site_id, site.access_node, trip.start_time_s + arrivals_t[i], arrivals_e[i],
                                trip.start_time_s + departures_t[i], departures_e[i], max(0.0, departures_e[i] - arrivals_e[i]),
                                charge_times[i], None if activity_start is None else trip.start_time_s + activity_start))
        prefix_distance = sum(leg.distance_m for leg in legs[:i + 1])
        labels.append(SearchLabel(site.access_node, departures_t[i], departures_e[i],
                                  scheduled_index is not None and i >= scheduled_index, i + 1,
                                  departures_t[i] + config.lambda_stop_s * (i + 1) +
                                  config.distance_penalty_s_per_km * prefix_distance / 1000 +
                                  (penalty if activity_start is not None else 0)))
    clock = (departures_t[-1] if events else 0.0) + legs[-1].time_s
    terminal = (departures_e[-1] if events else trip.initial_energy_kwh) - ev.drive_energy(legs[-1].distance_m)
    cost = clock + config.lambda_stop_s * len(events) + penalty + config.distance_penalty_s_per_km * distance_m / 1000
    labels.append(SearchLabel(trip.destination, clock, terminal, scheduled_index is not None, len(events), cost))
    return Plan(tuple(events), clock, drive_s, distance_m, terminal, penalty, cost, tuple(labels))


def best_one_stop(trip, sites, travel, ev, curve, schedule, config):
    """Exhaustive zero/one-stop optimum on supplied time-optimal road legs.

    Monotone charging duration and no terminal reward imply minimum departure
    energy. The schedule-start objective is piecewise linear; earliest feasible
    start, window bounds and charge-end slack suffice. No Site cap or energy grid.
    """
    validate_trip(trip, ev)
    baseline = travel.leg(trip.origin, trip.destination)
    if baseline is None:
        return None
    plans = []
    def in_budget(legs):
        return trip.mobility_budget_s is None or sum(l.time_s for l in legs) <= trip.mobility_budget_s + 1e-7
    if trip.initial_energy_kwh - ev.drive_energy(baseline.distance_m) >= ev.terminal_floor - 1e-8 and in_budget([baseline]) and (schedule is None or not schedule.hard):
        plans.append(assemble_plan(trip, (), [baseline], [], [], [], [], [], None, None,
                                   0 if schedule is None else schedule.miss_penalty_s, ev, config))
    for site in sites:
        root = SearchLabel(trip.origin, 0.0, trip.initial_energy_kwh, False, 0, 0)
        view = evaluate_site(site, root, trip.destination, travel, ev, curve, schedule, config,
                             start_time_s=trip.start_time_s)
        if view is None or not view.energy_feasible:
            continue
        legs = [travel.leg(trip.origin, site.access_node), travel.leg(site.access_node, trip.destination)]
        if not in_budget(legs):
            continue
        arrival = view.arrival_time_s - trip.start_time_s
        charge = view.charging_duration_s
        options = []
        if schedule is None or not schedule.hard:
            options.append((None, config.overhead_s + charge, 0 if schedule is None else schedule.miss_penalty_s))
        if schedule is not None and schedule.supports(site):
            for start in scheduled_start_candidates(arrival, charge, schedule, config, trip.start_time_s):
                off = max(schedule.window_start_s - trip.start_time_s - start, start - (schedule.window_end_s - trip.start_time_s), 0)
                if schedule.hard and off > 1e-8:
                    continue
                duration = max(config.overhead_s + charge, start - arrival + schedule.duration_s)
                options.append((start, duration, off * schedule.time_penalty_per_s))
        for start, duration, penalty in options:
            plans.append(assemble_plan(trip, (site,), legs, [view.arrival_energy_kwh],
                         [view.arrival_energy_kwh + view.required_charge_kwh], [arrival], [arrival + duration],
                         [charge], None if start is None else 0, start, penalty, ev, config))
    return min(plans, key=plan_key) if plans else None


def plan_key(plan):
    # Tie-breaking removes gratuitous charge, including charge hidden by overlap.
    return (round(plan.generalized_cost_s, 7), sum(e.charged_kwh for e in plan.stops),
            plan.stop_count, tuple(e.site_id for e in plan.stops))
