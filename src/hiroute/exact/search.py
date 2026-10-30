"""Bounded FLAT/HIER search over immutable positive-time directed edge snapshots.

The migrated core currently supports diagnostic depth caps, exact transition
evaluation, strict-primary Region pruning, wall deadlines, and diagnostic
observers. A timeout returns an attained, replayable incumbent separately
from the mathematical status, which remains unknown.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import heapq
import itertools
import time

from ..contracts import canonical_json, content_id

from ..contracts import ProblemSnapshot, SolverConfig
from .interval import Interval
from .pipeline import DriveStep, StopStep, execute_exact_plan, initial_piece, replay_terminal
from .scalar import exact, rational_text
from .terminal import terminal_optimize


class _DeadlineReached(Exception):
    pass


@dataclass(frozen=True)
class SelectedLeg:
    source: str
    target: str
    time_s: Fraction
    length_m: Fraction
    edges: tuple[dict, ...]


def _adjacency(snapshot):
    graph = {}
    for index, raw in enumerate(snapshot.directed_edges):
        row = dict(raw)
        row.setdefault("edge_id", f"input:{index:08d}")
        row["time_s"] = exact(row["time_s"])
        row["length_m"] = exact(row["length_m"])
        graph.setdefault(row["source"], []).append(row)
    return graph


def selected_leg(snapshot: ProblemSnapshot, source: str, target: str, cache=None):
    """Minimize (time, node tuple, edge-ID tuple); length is an attribute.

    Positive edge times imply every predecessor of a shortest path is settled
    before its endpoint. Equal-time paths to the same node cannot be proper
    prefixes of one another (that would require a zero-time cycle), so extending
    the smaller node tuple preserves its order. With equal nodes, equal-length
    edge tuples preserve their order too. Thus one full-key label per vertex
    suffices; this is Dijkstra, not enumeration of simple paths.
    """
    if cache is None:
        cache = {}
    key = (source, target)
    if key in cache:
        return cache[key]
    if source == target:
        result = SelectedLeg(source, target, Fraction(0), Fraction(0), ())
        cache[key] = result
        return result
    graph = _adjacency(snapshot)
    serial = itertools.count()
    start = (Fraction(0), (source,), ())
    heap = [(*start, next(serial), source, Fraction(0), ())]
    best = {source: start}
    while heap:
        time, nodes, identities, _, node, length, path = heapq.heappop(heap)
        if best.get(node) != (time, nodes, identities):
            continue
        if node == target:
            result = SelectedLeg(source, target, time, length, path)
            cache[key] = result
            return result
        for edge in graph.get(node, ()):
            nxt = edge["target"]
            value = (time + edge["time_s"], nodes + (nxt,), identities + (edge["edge_id"],))
            if nxt not in best or value < best[nxt]:
                best[nxt] = value
                heapq.heappush(heap, (*value, next(serial), nxt,
                                      length + edge["length_m"], path + (edge,)))
    cache[key] = None
    return None


def _action_sequences(snapshot, limit):
    capabilities = snapshot.site_capabilities
    sites = snapshot.candidate_order
    yield ()
    frontier = [()]
    for _depth in range(1, limit + 1):
        following = []
        for prefix in frontier:
            for site in sites:
                for effect in capabilities[site]:
                    if effect in {"S", "CS"} and (snapshot.schedule is None or snapshot.initial_remaining_schedule != 1):
                        continue
                    if effect in {"S", "CS"} and any(a in {"S", "CS"} for _, a in prefix):
                        continue
                    plan = prefix + ((site, effect),)
                    following.append(plan)
                    yield plan
        frontier = following


def _plan_steps(snapshot, plan, cache):
    energy = exact(snapshot.initial_energy_kwh)
    floor = exact(snapshot.minimum_energy_kwh)
    rate = exact(snapshot.consumption_kwh_per_m)
    overhead = exact(snapshot.stop_overhead_s)
    steps = []
    legs = []
    anchor = snapshot.origin
    for site, effect in plan:
        leg = selected_leg(snapshot, anchor, site, cache)
        if leg is None:
            return None
        legs.append(leg)
        steps.append(DriveStep(site, leg.time_s, rate * leg.length_m, floor))
        if effect == "S":
            sch = snapshot.schedule
            steps.append(StopStep("S", site, overhead,
                                  a=exact(sch["a"]), b=exact(sch["b"]),
                                  duration=exact(sch["D"])))
        elif effect == "CS":
            sch = snapshot.schedule
            steps.append(StopStep("CS", site, overhead, snapshot.charging_curve,
                                  exact(sch["a"]), exact(sch["b"]), exact(sch["D"])))
        else:
            steps.append(StopStep("C", site, overhead, snapshot.charging_curve))
        anchor = site
    final_leg = selected_leg(snapshot, anchor, snapshot.destination, cache)
    if final_leg is None:
        return None
    legs.append(final_leg)
    steps.append(DriveStep(snapshot.destination, final_leg.time_s,
                           rate * final_leg.length_m, floor))
    return tuple(steps), tuple(legs)


def _leg_dict(leg):
    return {"source": leg.source, "target": leg.target,
            "time_s": str(leg.time_s), "actual_length_m": str(leg.length_m),
            "edges": [{"source": e["source"], "target": e["target"],
                       "edge_id": e["edge_id"], "time_s": str(e["time_s"]),
                       "length_m": str(e["length_m"])} for e in leg.edges]}


@dataclass(frozen=True)
class Region:
    identifier: int
    members: tuple[str, ...]
    children: tuple["Region", ...] = ()


def _build_regions(sites):
    members = tuple(sorted(set(sites)))
    def build(items, identifier):
        if len(items) <= 1: return Region(identifier, items)
        middle = len(items) // 2
        return Region(identifier, items, (build(items[:middle], identifier * 2 + 1), build(items[middle:], identifier * 2 + 2)))
    return build(members, 0)


def _primary(item):
    terminal = item[0]
    if terminal.status == "primary_unattained": return terminal.primary_infimum
    if terminal.status in {"attained_optimum", "secondary_unattained"}: return terminal.primary_value
    return None


def _next_stop_bound(snapshot, prefix_time, inbound, onward, prefix_stops):
    """Relative driving duration plus unavoidable nonnegative stop penalties."""
    return (prefix_time + inbound.time_s + onward.time_s
            + exact(snapshot.stop_penalty_s) * (prefix_stops + 1))


def _hierarchical_plans(snapshot, cache, evaluate):
    """Disjoint Region refinement with an admissible strict-primary bound."""
    root = _build_regions(snapshot.candidate_order)
    serial = itertools.count()
    metrics = {"region_nodes": 0, "leaf_actions": 0, "pruned_regions": 0, "equality_nodes_retained": 0, "coverage_groups": 0, "missing_actions": 0, "duplicate_actions": 0, "empty_regions": 0, "unreachable_regions": 0, "max_depth": 0}
    best_j = None
    seen_plans = set()
    def prefix_route_time(plan):
        anchor = snapshot.origin; total = Fraction(0)
        for site, _ in plan:
            leg = selected_leg(snapshot, anchor, site, cache)
            if leg is None: return None, anchor
            total += leg.time_s; anchor = site
        return total, anchor
    def add_prefix(plan):
        nonlocal best_j
        if plan in seen_plans: return
        seen_plans.add(plan)
        value = evaluate(plan)
        if value is not None: best_j = min((x for x in (best_j, value) if x is not None), default=None)
        metrics["max_depth"] = max(metrics["max_depth"], len(plan))
        if len(plan) >= snapshot.depth_limit: return
        elapsed, anchor = prefix_route_time(plan)
        if elapsed is None: return
        queue = []
        expected = {(site, effect) for site in snapshot.candidate_order for effect in snapshot.site_capabilities[site]
                    if not (effect in {"S", "CS"} and (snapshot.schedule is None or snapshot.initial_remaining_schedule != 1))
                    and not (effect in {"S", "CS"} and any(a in {"S", "CS"} for _, a in plan))}
        covered = set()
        if not expected:
            metrics["empty_regions"] += 1; metrics["coverage_groups"] += 1; return
        def enqueue(region, effect, members=None):
            action_set = ({(site, effect) for site in region.members if (site, effect) in expected} if members is None else members)
            if not action_set: metrics["empty_regions"] += 1; return
            if members is None:
                overlap = covered.intersection(action_set)
                if overlap:
                    metrics["duplicate_actions"] += len(overlap); raise AssertionError("Region action partition overlaps")
                covered.update(action_set)
            bounds = []
            for site, _ in sorted(action_set):
                inbound = selected_leg(snapshot, anchor, site, cache); onward = selected_leg(snapshot, site, snapshot.destination, cache)
                if inbound is None or onward is None: continue
                bounds.append(_next_stop_bound(snapshot, elapsed, inbound, onward, len(plan)))
            if not bounds: metrics["unreachable_regions"] += 1; return
            heapq.heappush(queue, (min(bounds), len(plan), effect, region.identifier, next(serial), plan, region, action_set))
        for effect in ("C", "S", "CS"): enqueue(root, effect)
        metrics["coverage_groups"] += 1
        if covered != expected:
            metrics["missing_actions"] += len(expected - covered); raise AssertionError("Region refinement lost a statically legal action")
        while queue:
            bound, _, effect, _, _, prefix, region, action_set = heapq.heappop(queue); metrics["region_nodes"] += 1
            if best_j is not None and bound > best_j: metrics["pruned_regions"] += 1; continue
            if best_j is not None and bound == best_j: metrics["equality_nodes_retained"] += 1
            if region.children:
                child_covered = set()
                for child in region.children:
                    child_actions = {(site, effect) for site in child.members if (site, effect) in action_set}
                    if child_covered.intersection(child_actions): raise AssertionError("Region children overlap")
                    child_covered.update(child_actions); enqueue(child, effect, child_actions)
                if child_covered != action_set: raise AssertionError("Region children do not exactly cover parent")
                continue
            for site, action in sorted(action_set):
                metrics["leaf_actions"] += 1; add_prefix(prefix + ((site, action),))
    add_prefix(())
    return metrics


def _witness_record(plan, legs, replay):
    trace = replay["trace"]
    charges = [str(oe - ie) for effect, _site, ie, _it, oe, _ot in trace
               if effect in {"C", "CS"}]
    return {
        "schema": "hiroute.witness.v1",
        "actions": [list(x) for x in replay["key"][3]],
        "charges_kwh": charges,
        "route_legs": [_leg_dict(x) for x in legs],
        "events": [{"effect": effect, "site": site,
                    "input_energy_kwh": str(ie), "input_time_s": str(it),
                    "output_energy_kwh": str(oe), "output_time_s": str(ot)}
                   for effect, site, ie, it, oe, ot in trace],
    }


def _verify_seed_depth_certificate(snapshot, config, certificate):
    """Verify the accepted D2 common-seed bound from a separately supplied plan.

    The certificate plan is replayed against this immutable snapshot before its
    primary value can bound depth. It is not taken from FLAT/HIER search output.
    """
    if not isinstance(certificate, dict):
        raise ValueError("seed_derived depth requires a certificate object")
    required = {"schema", "semantic_problem_id", "reference", "plan", "key",
                "witness", "h_min", "lambda", "U_J", "H_max"}
    if set(certificate) != required or certificate.get("schema") != "hiroute.seed_depth_certificate.v1":
        raise ValueError("invalid seed depth certificate schema or fields")
    if certificate["semantic_problem_id"] != snapshot.semantic_problem_id:
        raise ValueError("seed certificate semantic problem identity mismatch")
    if certificate["reference"] != snapshot.depth_certificate_reference:
        raise ValueError("seed certificate reference mismatch")
    if type(certificate["plan"]) is not list or any(
            type(row) is not list or len(row) != 2 or not all(isinstance(x, str) for x in row)
            for row in certificate["plan"]):
        raise ValueError("seed certificate plan must be an explicit action sequence")
    plan = tuple(tuple(row) for row in certificate["plan"])
    if len(plan) > len(snapshot.candidate_order) or len(set(site for site, _ in plan)) != len(plan):
        raise ValueError("seed certificate plan is not a simple bounded stop sequence")
    expected_h = exact(snapshot.stop_overhead_s, "stop_overhead_s")
    expected_lambda = exact(snapshot.stop_penalty_s, "stop_penalty_s")
    if exact(certificate["h_min"], "certificate.h_min") != expected_h or expected_h <= 0:
        raise ValueError("seed certificate stop overhead premise mismatch")
    if exact(certificate["lambda"], "certificate.lambda") != expected_lambda or expected_lambda < 0:
        raise ValueError("seed certificate stop penalty premise mismatch")
    # D2 relies on nonnegative drive, service, waiting, and charge durations.
    if any(exact(row[2], "charging_curve.slope") < 0 for row in snapshot.charging_curve):
        raise ValueError("seed depth bound requires nonnegative charging-time slopes")
    if any(effect in {"C", "CS"} for effects in snapshot.site_capabilities.values() for effect in effects):
        if not snapshot.charging_curve:
            raise ValueError("seed depth bound requires a defined charging-time curve")
    compiled = _plan_steps(snapshot, plan, {})
    if compiled is None:
        raise ValueError("seed certificate route is unreachable")
    steps, legs = compiled
    initial = initial_piece(
        Interval(exact(snapshot.initial_energy_kwh), exact(snapshot.initial_energy_kwh)),
        start_time=exact(snapshot.departure_time_s), anchor=snapshot.origin,
        remaining_schedule=snapshot.initial_remaining_schedule,
        rho=-exact(snapshot.initial_energy_kwh))
    pieces = execute_exact_plan((initial,), steps)
    terminal = terminal_optimize(pieces, snapshot.destination, snapshot.destination_reserve_kwh,
                                 exact(snapshot.departure_time_s), expected_lambda)
    if terminal.status != "attained_optimum":
        raise ValueError("seed certificate does not replay to an attained feasible witness")
    replay = replay_terminal(terminal, snapshot.destination, snapshot.destination_reserve_kwh,
                             exact(snapshot.departure_time_s), expected_lambda)
    full_key = [str(terminal.key[0]), str(terminal.key[1]), terminal.key[2],
                [list(x) for x in terminal.key[3]]]
    if certificate["key"] != full_key:
        raise ValueError("seed certificate complete lexicographic key mismatch")
    witness = _witness_record(plan, legs, replay)
    if certificate["witness"] != witness:
        raise ValueError("seed certificate witness differs from exact physical replay")
    objective = exact(certificate["U_J"], "certificate.U_J")
    if objective != terminal.key[0] or objective < 0:
        raise ValueError("seed certificate U_J differs from replayed primary value")
    unit = expected_h + expected_lambda
    if unit <= 0:
        raise ValueError("seed certificate has no positive per-stop objective lower bound")
    h_max = objective // unit
    if type(certificate["H_max"]) is not int or certificate["H_max"] != h_max:
        raise ValueError("seed certificate H_max differs from floor(U_J/(h_min+lambda))")
    if snapshot.depth_limit != h_max:
        raise ValueError("snapshot diagnostic limit does not equal certified H_max")
    if (h_max + 1) * unit <= objective:
        raise ValueError("first excluded depth is not strictly worse than the seed")
    return {"mode": "seed_derived", "limit": h_max,
            "certificate_reference": snapshot.depth_certificate_reference,
            "certificate_id": content_id(certificate), "seed_key": full_key,
            "per_stop_lower_bound": str(unit),
            "first_excluded_depth": h_max + 1,
            "first_excluded_lower_bound": str((h_max + 1) * unit),
            "strictly_worse_excluded_depths": True,
            "equality_depth_retained": True,
            "incumbent_pruning": False}


def solve_snapshot(snapshot: ProblemSnapshot, config: SolverConfig, *,
                   time_limit_s: float | None = None, observer: str = "off",
                   on_incumbent=None, depth_certificate: dict | None = None,
                   _clock=time.monotonic):
    """Search the declared diagnostic cap through native FLAT or Region HIER.

    HIER splits the statically legal next-action set into disjoint binary
    Regions and prunes only when an admissible primary lower bound is strictly
    greater than an attained incumbent. Equal-primary Regions remain active.
    """
    started = _clock()
    depth_evidence = None
    if snapshot.depth_mode == "seed_derived":
        if config.seed_policy != "verified_seed_certificate":
            raise NotImplementedError("unsupported_model: seed_derived requires verified_seed_certificate policy")
        depth_evidence = _verify_seed_depth_certificate(snapshot, config, depth_certificate)
    elif snapshot.depth_mode == "diagnostic_cap":
        if config.seed_policy != "none" or depth_certificate is not None:
            raise ValueError("diagnostic_cap requires seed_policy=none and no certificate")
    else:
        raise NotImplementedError("unsupported depth mode")
    if snapshot.depth_limit > 5:
        raise NotImplementedError("native exact search currently caps diagnostic depth at 5")
    if len(snapshot.candidate_order) > 8:
        raise NotImplementedError("native exact search currently caps candidates at 8")
    if config.method not in {"flat", "hier"}:
        raise NotImplementedError("unsupported native search method")
    if time_limit_s is not None and time_limit_s <= 0:
        raise ValueError("time_limit_s must be positive")
    if observer not in {"off", "metrics", "detailed_trace"}:
        raise ValueError("observer must be off, metrics, or detailed_trace")
    seed_verification_elapsed = _clock() - started
    if depth_evidence is not None:
        depth_evidence["seed_verification_elapsed_s"] = seed_verification_elapsed
    deadline = None if time_limit_s is None else started + time_limit_s
    cache = {}
    terminals = []
    incumbent = None
    observed_plans = 0
    observer_trace = []
    domains = 0
    plans_seen = 0
    def evaluate(plan):
        nonlocal domains, plans_seen, incumbent, observed_plans
        if deadline is not None and _clock() >= deadline:
            raise _DeadlineReached
        plans_seen += 1
        if plans_seen > 100_000: raise NotImplementedError("native diagnostic plan enumeration exceeds 100000")
        compiled = _plan_steps(snapshot, plan, cache)
        if compiled is None: return None
        steps, legs = compiled; domains += 1
        if domains > 100_000: raise NotImplementedError("native diagnostic plan domain exceeds 100000")
        start = exact(snapshot.departure_time_s)
        # Q is total charged energy: terminal Q=E+rho. Seeding rho=-E0
        # makes drives add consumption and charge stops add delivered charge.
        initial = initial_piece(
            Interval(exact(snapshot.initial_energy_kwh), exact(snapshot.initial_energy_kwh)),
            start_time=start, anchor=snapshot.origin,
            remaining_schedule=snapshot.initial_remaining_schedule,
            rho=-exact(snapshot.initial_energy_kwh))
        pieces = execute_exact_plan((initial,), steps)
        terminal = terminal_optimize(pieces, snapshot.destination, snapshot.destination_reserve_kwh, start, snapshot.stop_penalty_s)
        terminals.append((terminal, plan, legs))
        observed_plans += 1
        if observer == "detailed_trace":
            trace_key = None if terminal.key is None else [
                rational_text(terminal.key[0], "trace.J"),
                rational_text(terminal.key[1], "trace.Q"), terminal.key[2],
                [list(action) for action in terminal.key[3]],
            ]
            observer_trace.append({"plan": [list(action) for action in plan],
                                   "terminal_status": terminal.status, "key": trace_key})
        if terminal.status == "attained_optimum" and (incumbent is None or terminal.key < incumbent["key"]):
            incumbent = {"key": terminal.key, "plan": plan, "legs": legs,
                "replay": replay_terminal(terminal, snapshot.destination, snapshot.destination_reserve_kwh,
                    exact(snapshot.departure_time_s), exact(snapshot.stop_penalty_s))}
            if on_incumbent is not None:
                on_incumbent(incumbent)
        return _primary(terminals[-1])
    hierarchy_metrics = None
    timed_out = False
    try:
        if config.method == "hier": hierarchy_metrics = _hierarchical_plans(snapshot, cache, evaluate)
        else:
            for plan in _action_sequences(snapshot, snapshot.depth_limit): evaluate(plan)
        if deadline is not None and _clock() >= deadline:
            timed_out = True
    except _DeadlineReached:
        timed_out = True
    observer_record = None if observer == "off" else {
        "profile": observer, "plans_evaluated": observed_plans, "terminal_domains": domains,
        "trace": observer_trace if observer == "detailed_trace" else None}
    if timed_out:
        return {"status": "time_limit", "domains": domains, "incumbent": incumbent,
            "elapsed_s": _clock() - started,
            "hierarchical_search": "region_refinement_strict_primary_bound" if config.method == "hier" else "not_requested",
            "enumeration_backend": "exact_region_search" if config.method == "hier" else "exact_enumeration_backend",
            "hierarchy_metrics": hierarchy_metrics, "observer": observer_record, "depth_certificate": depth_evidence}
    if not terminals:
        return {"status": "infeasible", "domains": 0,
                "hierarchical_search": "region_refinement_strict_primary_bound" if config.method == "hier" else "not_requested",
                "enumeration_backend": "exact_region_search" if config.method == "hier" else "exact_enumeration_backend",
                "hierarchy_metrics": hierarchy_metrics, "observer": observer_record, "depth_certificate": depth_evidence}
    primary = [(t.primary_infimum if t.status == "primary_unattained"
                else t.primary_value if t.status in {"attained_optimum", "secondary_unattained"}
                else None) for t, _, _ in terminals]
    primary = [x for x in primary if x is not None]
    if not primary:
        return {"status": "infeasible", "domains": domains, "observer": observer_record}
    best_j = min(primary)
    jface = [(t, p, l) for t, p, l in terminals
             if ((t.primary_infimum if t.status == "primary_unattained" else
                  t.primary_value if t.status in {"attained_optimum", "secondary_unattained"} else None) == best_j)]
    attained_primary = [(t, p, l) for t, p, l in jface if t.status in {"attained_optimum", "secondary_unattained"}]
    if not attained_primary:
        return {"status": "primary_unattained", "primary_infimum": best_j,
                "domains": domains}
    q_values = [(t.key[1], t, p, l) for t, p, l in attained_primary
                if t.status == "attained_optimum"]
    q_values += [(t.secondary_infimum, t, p, l) for t, p, l in jface
                 if t.status == "secondary_unattained"]
    best_q = min(x[0] for x in q_values)
    attained_q = [(t, p, l) for q, t, p, l in q_values
                  if q == best_q and t.status == "attained_optimum"]
    if not attained_q:
        return {"status": "secondary_unattained", "primary_value": best_j,
                "primary_infimum": best_j, "secondary_infimum": best_q,
                "domains": domains}
    terminal, plan, legs = min(attained_q, key=lambda x: (x[0].key[2], x[0].key[3]))
    replay = replay_terminal(terminal, snapshot.destination,
                             snapshot.destination_reserve_kwh,
                             exact(snapshot.departure_time_s), exact(snapshot.stop_penalty_s))
    return {"status": terminal.status, "key": terminal.key, "witness": terminal.witness,
            "replay": replay, "plan": plan, "legs": legs, "domains": domains,
            "input_identity": {
                "semantic_problem_id": snapshot.semantic_problem_id,
                "model_contract_id": snapshot.model_contract_id,
                "numerical_contract_id": snapshot.numerical_contract_id,
                "graph_or_leg_identity": snapshot.graph_or_leg_identity,
                "selected_leg_contract": snapshot.selected_leg_contract,
            },
            "routing_cache_entries": len(cache), "selected_leg_identity": snapshot.graph_or_leg_identity,
            "hierarchical_search": "region_refinement_strict_primary_bound" if config.method == "hier" else "not_requested",
            "enumeration_backend": "exact_region_search" if config.method == "hier" else "exact_enumeration_backend",
            "hierarchy_metrics": hierarchy_metrics, "observer": observer_record, "depth_certificate": depth_evidence}
