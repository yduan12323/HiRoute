"""Incremental exact search with an attained upper bound and summary queries.

A node owns its exact post-stop family and full history. Destination drives are
terminal attempts only. OPEN contains states and disjoint next-action Regions;
no dominance across histories or diagnostic N/H cap is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import heapq
import itertools
import os
import resource
import sys
import time

from .interval import Interval
from .pipeline import DriveStep, StopStep, execute_exact_plan, initial_piece, replay_terminal
from .scalar import exact
from .terminal import TerminalResult, TerminalWitness, terminal_optimize


class ResourceLimit(Exception):
    def __init__(self, status):
        self.status = status


def _peak_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == 'darwin' else value * 1024


def _resident_bytes():
    if sys.platform.startswith('linux'):
        with open('/proc/self/statm') as stream:
            return int(stream.read().split()[1])*os.sysconf('SC_PAGE_SIZE')
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except ImportError:
        # The portable fallback is explicitly labelled in the result. Fresh
        # single-query workers (the pilot policy) have no earlier query peak.
        return _peak_bytes()


def validate_scale_input(snapshot):
    """Validate physical assumptions used by both transitions and lower bounds."""
    expected = {'model_contract_id': 'hiroute.time_cut_v2.bounded',
                'numerical_contract_id': 'exact_rational_inputs_v1',
                'selected_leg_contract': 'positive_time_node_path_edge_path_tie_v1'}
    for field, value in expected.items():
        if getattr(snapshot, field) != value:
            raise NotImplementedError('unsupported scale input: ' + field)
    if snapshot.depth_mode not in ('unrestricted', 'diagnostic_cap'):
        raise ValueError('scale requires unrestricted or explicit diagnostic_cap domain')
    has_charge = any(set(v) & {'C', 'CS'} for v in snapshot.site_capabilities.values())
    curve = [tuple(map(exact, row)) for row in snapshot.charging_curve]
    if has_charge:
        if not curve or curve[0][0] != 0 or curve[-1][1] != exact(snapshot.capacity_kwh):
            raise ValueError('charging curve must cover the full battery domain')
        for i, (lo, hi, slope, intercept) in enumerate(curve):
            if lo >= hi or slope <= 0:
                raise ValueError('charging segments require ordered domains and positive slopes')
            if i:
                previous = curve[i-1]
                if previous[1] != lo or previous[2]*lo+previous[3] != slope*lo+intercept:
                    raise ValueError('charging curve must be contiguous and continuous')
    return min((row[2] for row in curve), default=Fraction(0))


@dataclass(frozen=True)
class PrefixState:
    family: tuple
    anchor: str
    plan: tuple = ()
    legs: tuple = ()


def _stop(snapshot, site, effect):
    h = exact(snapshot.stop_overhead_s)
    if effect == 'C':
        return StopStep(effect, site, h, snapshot.charging_curve)
    sch = snapshot.schedule
    return StopStep(effect, site, h, snapshot.charging_curve if effect == 'CS' else (),
                    exact(sch['a']), exact(sch['b']), exact(sch['D']))


def extend_prefix(snapshot, state, site, effect, leg, *, c_backend='analytic'):
    """Only the inbound drive and new stop act on the post-stop family."""
    family = execute_exact_plan(state.family, (
        DriveStep(site, leg.time_s, exact(snapshot.consumption_kwh_per_m)*leg.length_m,
                  exact(snapshot.minimum_energy_kwh)), _stop(snapshot, site, effect)),
        c_backend=c_backend)
    return PrefixState(family, site, state.plan+((site, effect),), state.legs+(leg,))


def terminal_attempt(snapshot, state, provider, *, c_backend='analytic'):
    leg = provider.selected_leg(state.anchor, snapshot.destination)
    if leg is None:
        return TerminalResult('infeasible'), (), None
    family = execute_exact_plan(state.family, (DriveStep(snapshot.destination, leg.time_s,
        exact(snapshot.consumption_kwh_per_m)*leg.length_m,
        exact(snapshot.minimum_energy_kwh)),), c_backend=c_backend)
    terminal = terminal_optimize(family, snapshot.destination,
        snapshot.destination_reserve_kwh, snapshot.departure_time_s, snapshot.stop_penalty_s)
    return terminal, family, state.legs+(leg,)


def _feasible_terminal(snapshot, pieces):
    """Construct a physical interior witness when an infimum is not attained.

    This is used only by the seed heuristic. A strictly larger time budget
    realizes an open cut; its actual replay, rather than that budget, defines U.
    """
    for p in pieces:
        if p.state_key[1] != 0:
            continue
        lo = max(p.domain.lo, exact(snapshot.destination_reserve_kwh))
        if lo > p.domain.hi or (lo == p.domain.hi and not p.domain.right_closed):
            continue
        energy = lo if p.domain.contains(lo) else (lo+p.domain.hi)/2
        budget = p.slope*energy+p.intercept+(0 if p.attained else 1)
        predecessor = p.witness_lifter(energy, budget)
        actual = exact(getattr(predecessor, 'output_time', getattr(predecessor, 'time', budget)))
        key = (actual-exact(snapshot.departure_time_s)+exact(snapshot.stop_penalty_s)*len(p.prefix),
               energy+p.rho, len(p.prefix), p.prefix)
        witness = TerminalWitness(energy, actual, p.rho, p.prefix, p.state_key, predecessor)
        return TerminalResult('attained_optimum', primary_value=key[0], key=key, witness=witness)
    return None


class OptimalFace:
    """Constant terminal summary, retaining attainment on both objective faces."""
    def __init__(self):
        self.j = self.q = None
        self.primary_attained = False
        self.best = None

    def add(self, terminal, state, legs):
        if terminal.status == 'infeasible':
            return
        j = terminal.primary_infimum if terminal.status == 'primary_unattained' else terminal.primary_value
        if self.j is None or j < self.j:
            self.j, self.q, self.primary_attained, self.best = j, None, False, None
        if j != self.j or terminal.status == 'primary_unattained':
            return
        self.primary_attained = True
        q = terminal.secondary_infimum if terminal.status == 'secondary_unattained' else terminal.key[1]
        if self.q is None or q < self.q:
            self.q, self.best = q, None
        if q == self.q and terminal.status == 'attained_optimum':
            item = (terminal, state, legs)
            if self.best is None or terminal.key < self.best[0].key:
                self.best = item

    def result(self, snapshot):
        if self.j is None:
            return {'status': 'infeasible'}
        if not self.primary_attained:
            return {'status': 'primary_unattained', 'primary_infimum': self.j}
        if self.best is None:
            return {'status': 'secondary_unattained', 'primary_value': self.j,
                    'primary_infimum': self.j, 'secondary_infimum': self.q}
        terminal, state, legs = self.best
        replay = replay_terminal(terminal, snapshot.destination, snapshot.destination_reserve_kwh,
                                 snapshot.departure_time_s, snapshot.stop_penalty_s)
        return {'status': 'attained_optimum', 'key': terminal.key, 'witness': terminal.witness,
                'replay': replay, 'plan': state.plan, 'legs': legs}


def deterministic_seed(snapshot, root, provider, features, check, *, beam_width=4,
                       max_depth=None, c_backend='analytic'):
    """A bounded, deterministic feasibility heuristic; never an optimality oracle.

    Prefer progress toward destination, trying C/CS/S with exact transitions.
    A beam discards heuristic states only here. Exact search starts from root.
    """
    frontier = [root]
    attempts = 0
    # This is a seed-effort bound, not a bound on the exact search domain.
    max_depth = len(snapshot.candidate_order) if max_depth is None else max_depth
    for depth in range(max_depth+1):
        following = []
        for state in frontier:
            check()
            terminal, family, legs = terminal_attempt(snapshot, state, provider, c_backend=c_backend)
            attempts += 1
            feasible = terminal if terminal.status == 'attained_optimum' else _feasible_terminal(snapshot, family)
            if feasible is not None:
                replay = replay_terminal(feasible, snapshot.destination, snapshot.destination_reserve_kwh,
                    snapshot.departure_time_s, snapshot.stop_penalty_s)
                return dict(key=feasible.key, plan=state.plan, legs=legs, replay=replay), attempts
            if depth == max_depth:
                continue
            pending = state.family[0].state_key[1]
            # Avoid revisits only in this feasibility heuristic, never in search.
            visited = {site for site, _ in state.plan}
            candidates = sorted((site for site in features if site not in visited),
                key=lambda site: (features[site].to_destination_time, site))
            for site in candidates:
                check()
                effects = tuple(effect for effect in ('CS', 'C', 'S')
                    if effect in snapshot.site_capabilities[site]
                    and (effect == 'C' or pending))
                if not effects:
                    continue
                target_features = features[site]
                anchor_features = features.get(state.anchor)
                # These are exactly the static legality and empty-inbound
                # cases the old full-scan seed discovered only after routing.
                # Filtering them preserves its surviving states and rank.
                from_anchor = (target_features.from_origin_distance if anchor_features is None
                    else max(Fraction(0),
                        target_features.from_origin_distance-anchor_features.from_origin_distance,
                        anchor_features.to_destination_distance-target_features.to_destination_distance))
                if (exact(snapshot.consumption_kwh_per_m)*from_anchor
                        +exact(snapshot.minimum_energy_kwh)
                        > max(p.domain.hi for p in state.family)):
                    continue
                leg = provider.selected_leg(state.anchor, site)
                if leg is None:
                    continue
                for effect in effects:
                    child = extend_prefix(snapshot, state, site, effect, leg, c_backend=c_backend)
                    attempts += 1
                    if child.family:
                        earliest = min(p.infimum()[0] for p in child.family)
                        # pending service is sorted after completed service, then progress.
                        rank = (child.family[0].state_key[1], features[site].to_destination_time,
                                earliest, child.plan)
                        following.append((rank, child))
        frontier = [item[1] for item in sorted(following, key=lambda item: item[0])[:beam_width]]
        if not frontier:
            break
    return None, attempts


def solve_scale(snapshot, *, method='scale', provider=None, time_limit_s=60,
                memory_limit_bytes=8*1024**3, on_incumbent=None, use_bound=True,
                seed_beam_width=4, _clock=time.monotonic, c_backend='analytic',
                memory_baseline_bytes=None):
    """Solve the full declared candidate domain, with resource-limited UNKNOWN.

    flat_bb_strong and scale share the exact kernel, singleton relaxation,
    preprocessing, feasible seed and limits. Their difference is Region batching
    and associated leaf order. use_bound=False is the declared bound ablation.
    """
    from .road_index import RoadIndex
    from .scale_bounds import (SiteFeatures, build_region_tree, completion_bound,
                               region_travel_lower_bounds, singleton_region)
    if method not in ('scale', 'flat_bb_strong'):
        raise ValueError('method must be scale or flat_bb_strong')
    if time_limit_s is None or time_limit_s <= 0 or memory_limit_bytes <= 0:
        raise ValueError('positive time and memory limits are required')
    if c_backend not in ('analytic', 'projection'):
        raise ValueError('unknown C backend')
    if memory_baseline_bytes is not None and (type(memory_baseline_bytes) is not int
            or memory_baseline_bytes <= 0):
        raise ValueError('memory_baseline_bytes must be a positive integer')
    mu = validate_scale_input(snapshot)
    started = _clock()
    current_memory = _resident_bytes()
    baseline_memory = current_memory if memory_baseline_bytes is None else memory_baseline_bytes
    # An externally loaded index is outside the query delta. Every allocation
    # after that supplied baseline, including input/routing preparation, counts.
    sampled_peak = max(current_memory, baseline_memory)
    deadline = started+time_limit_s
    metrics = dict(summary_queries=0, singleton_queries=0, leaf_routes=0,
        transitions=0, transition_input_pieces=0, transition_output_pieces=0,
        terminal_attempts=0, empty_prefixes=0, terminal_infeasible_prefixes=0,
        pruned_regions=0, pruned_actions=0, equality_retained=0, max_depth=0,
        peak_open=0, safe_unreachable_sites=0, seed_attempts=0, terminal_records_peak=1)
    seconds = dict(preparation=0., seed=0., search=0., transitions=0., terminals=0.)
    incumbent = None
    seed = None
    face = OptimalFace()
    queue = []
    serial = itertools.count()
    domains = 0
    def check():
        nonlocal sampled_peak
        if _clock() >= deadline:
            raise ResourceLimit('time_limit')
        sampled_peak = max(sampled_peak, _resident_bytes())
        if sampled_peak-baseline_memory > memory_limit_bytes:
            raise ResourceLimit('memory_limit')
    def update_incumbent(record):
        nonlocal incumbent
        if record is not None and (incumbent is None or record['key'] < incumbent['key']):
            incumbent = record
            if on_incumbent is not None:
                on_incumbent(record)
    def push(bound, kind, state, region=None, effect=None):
        if bound is None:
            return
        heapq.heappush(queue, (bound, next(serial), kind, state, region, effect))
        metrics['peak_open'] = max(metrics['peak_open'], len(queue))
    root = PrefixState((initial_piece(Interval(exact(snapshot.initial_energy_kwh),
        exact(snapshot.initial_energy_kwh)), start_time=exact(snapshot.departure_time_s),
        anchor=snapshot.origin, remaining_schedule=snapshot.initial_remaining_schedule,
        rho=-exact(snapshot.initial_energy_kwh)),), snapshot.origin)
    status = None
    phase_started = started
    phase = 'preparation'
    tree = None
    features = {}
    try:
        provider = RoadIndex(snapshot.directed_edges, check=check) if provider is None else provider
        # Providers reused between queries must use this query's deadline.
        if hasattr(provider, 'check'):
            provider.check = check
        from_t = provider.distances_from(snapshot.origin, 'time_s')
        from_d = provider.distances_from(snapshot.origin, 'length_m')
        to_t = provider.distances_to(snapshot.destination, 'time_s')
        to_d = provider.distances_to(snapshot.destination, 'length_m')
        for site in snapshot.candidate_order:
            check()
            if any(site not in d for d in (from_t, from_d, to_t, to_d)):
                metrics['safe_unreachable_sites'] += 1
                continue
            features[site] = SiteFeatures(from_t[site], to_t[site], from_d[site], to_d[site])
        origin_features = SiteFeatures(0, to_t.get(snapshot.origin, 0), 0, to_d.get(snapshot.origin, 0))
        # At most O(N) static records, built once, no per-prefix coverage scans.
        if method == 'scale':
            tree = build_region_tree(tuple(features),
                {site: snapshot.site_capabilities[site] for site in features}, features)
            singletons = {}
        else:
            # Match Region leaf order without making the singleton baseline
            # construct or retain the hierarchy's internal nodes and summaries.
            ordered = sorted(features, key=lambda site: (
                features[site].from_origin_time, features[site].to_destination_time,
                features[site].from_origin_distance, features[site].to_destination_distance, site))
            singletons = {site: singleton_region(site, snapshot.site_capabilities[site],
                features[site], identifier=i) for i, site in enumerate(ordered)}
        seconds[phase] = _clock()-phase_started
        phase, phase_started = 'seed', _clock()
        seed, metrics['seed_attempts'] = deterministic_seed(snapshot, root, provider, features, check,
            beam_width=seed_beam_width,
            max_depth=snapshot.depth_limit if snapshot.depth_mode == 'diagnostic_cap' else None,
            c_backend=c_backend)
        update_incumbent(seed)
        seconds[phase] = _clock()-phase_started
        phase, phase_started = 'search', _clock()
        def bound(state, region, effect):
            check()
            if effect in ('S', 'CS') and state.family[0].state_key[1] == 0:
                return None
            if effect not in region.summaries:
                return None
            if method == 'scale':
                metrics['summary_queries'] += 1
            else:
                metrics['singleton_queries'] += 1
            anchor = origin_features if not state.plan else features[state.anchor]
            travel, distance = region_travel_lower_bounds(region, effect, anchor)
            return completion_bound(state.family, start_time=exact(snapshot.departure_time_s),
                travel_time=travel if use_bound else 0,
                drive_energy=exact(snapshot.consumption_kwh_per_m)*distance if use_bound else 0,
                reserve=exact(snapshot.destination_reserve_kwh) if use_bound else 0,
                overhead=exact(snapshot.stop_overhead_s), stop_penalty=exact(snapshot.stop_penalty_s),
                charge_slope=mu if use_bound else 0,
                service_duration=exact(snapshot.schedule['D']) if use_bound and snapshot.schedule else 0)
        push(Fraction(0), 'state', root)
        while queue:
            check()
            lower, _, kind, state, region, effect = heapq.heappop(queue)
            if incumbent is not None and lower > incumbent['key'][0]:
                metrics['pruned_regions'] += 1
                if region is not None:
                    metrics['pruned_actions'] += region.summaries[effect].count
                continue
            if incumbent is not None and lower == incumbent['key'][0]:
                metrics['equality_retained'] += 1
            if kind == 'state':
                metrics['max_depth'] = max(metrics['max_depth'], len(state.plan))
                t = _clock()
                terminal, _, legs = terminal_attempt(snapshot, state, provider, c_backend=c_backend)
                seconds['terminals'] += _clock()-t
                metrics['terminal_attempts'] += 1
                domains += 1
                if terminal.status == 'infeasible':
                    metrics['terminal_infeasible_prefixes'] += 1
                face.add(terminal, state, legs)
                if terminal.status == 'attained_optimum':
                    replay = replay_terminal(terminal, snapshot.destination,
                        snapshot.destination_reserve_kwh, snapshot.departure_time_s, snapshot.stop_penalty_s)
                    update_incumbent(dict(key=terminal.key, plan=state.plan, legs=legs, replay=replay))
                depth = None if incumbent is None else incumbent['key'][0] // (
                    exact(snapshot.stop_overhead_s)+exact(snapshot.stop_penalty_s))
                if snapshot.depth_mode == 'diagnostic_cap':
                    depth = snapshot.depth_limit if depth is None else min(depth, snapshot.depth_limit)
                if depth is not None and len(state.plan) >= depth:
                    continue
                regions = (tree,) if method == 'scale' else tuple(singletons.values())
                for next_region in regions:
                    if next_region is None:
                        continue
                    for next_effect in ('C', 'S', 'CS'):
                        push(bound(state, next_region, next_effect), 'region', state, next_region, next_effect)
            elif region.children:
                for child in region.children:
                    push(bound(state, child, effect), 'region', state, child, effect)
            else:
                site = region.site
                metrics['leaf_routes'] += 1
                leg = provider.selected_leg(state.anchor, site)
                if leg is None:
                    continue
                # Exact selected inbound data strengthens both methods equally;
                # onward distance is a directed road relaxation, never a
                # selected-fastest length treated as a metric.
                if use_bound:
                    exact_lower = completion_bound(state.family,
                        start_time=exact(snapshot.departure_time_s),
                        travel_time=leg.time_s+features[site].to_destination_time,
                        drive_energy=exact(snapshot.consumption_kwh_per_m)*(
                            leg.length_m+features[site].to_destination_distance),
                        reserve=exact(snapshot.destination_reserve_kwh),
                        overhead=exact(snapshot.stop_overhead_s),
                        stop_penalty=exact(snapshot.stop_penalty_s), charge_slope=mu,
                        service_duration=exact(snapshot.schedule['D']) if snapshot.schedule else 0)
                    lower = max(lower, exact_lower)
                    if incumbent is not None and lower > incumbent['key'][0]:
                        metrics['pruned_actions'] += 1
                        continue
                t = _clock()
                child = extend_prefix(snapshot, state, site, effect, leg, c_backend=c_backend)
                seconds['transitions'] += _clock()-t
                metrics['transitions'] += 1
                metrics['transition_input_pieces'] += len(state.family)
                metrics['transition_output_pieces'] += len(child.family)
                if not child.family:
                    metrics['empty_prefixes'] += 1
                    continue
                # The action bound also lower-bounds this exact child. Retain equality.
                push(lower, 'state', child)
        check()  # Last terminal/transition may have crossed the deadline.
        status = 'completed'
    except ResourceLimit as exc:
        status = exc.status
    except MemoryError:
        status = 'memory_limit'
    seconds[phase] += _clock()-phase_started
    if status == 'completed':
        result = face.result(snapshot)
    else:
        result = dict(status=status, mathematical_status='unknown', incumbent=incumbent)
    depth = None if incumbent is None else incumbent['key'][0] // (
        exact(snapshot.stop_overhead_s)+exact(snapshot.stop_penalty_s))
    result.update(domains=domains, elapsed_s=_clock()-started, metrics=metrics, seconds=seconds,
        incumbent=incumbent, seed=seed, seed_policy='deterministic_exact_feasibility_beam',
        depth_contract=dict(mode=snapshot.depth_mode,
            declared_limit=snapshot.depth_limit if snapshot.depth_mode == 'diagnostic_cap' else None,
            incumbent_derived_limit=depth, rule='floor(U_J/(h_min+lambda_stop))'),
        peak_process_bytes=_peak_bytes(), query_extra_peak_bytes=max(0, sampled_peak-baseline_memory),
        query_memory_baseline_bytes=baseline_memory,
        query_memory_measurement=('sampled_current_rss' if sys.platform.startswith('linux')
            or 'psutil' in sys.modules else 'process_high_water_fallback'),
        open_remaining=len(queue), routing_metrics=(provider.metrics() if provider is not None else {}),
        candidate_count=len(snapshot.candidate_order), active_candidates=len(features),
        method=method, lower_bound_enabled=use_bound,
        enumeration_backend='incremental_exact_summary_search' if method == 'scale' else 'incremental_exact_singleton_search')
    return result
