"""Tree-independent bounded REF over immutable native-router pair primitives.

No routing is performed. Site labels are semantic action identities; road
anchors are physical identities. The only optimization reused here is this
reference's own LP/regime kernel, independent of all production code.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as R
from time import perf_counter

from .model import InvalidInput, normalize_case, number
from .real_input import IndependentLegTable, require
from .solver import SCOPE, solve_prepared_case


@dataclass(frozen=True)
class RealLeg:
    source_road_anchor: str
    target_road_anchor: str
    time: R
    length: R
    energy: R
    time_hex: str
    length_hex: str
    label_direction: str
    table_sha256: str


@dataclass(frozen=True)
class PreparedRealCase:
    case: dict
    table: IndependentLegTable
    legs: dict
    physical_anchor: dict
    terminal_excluded_sites: tuple[str, ...]


def prepare_real_case(query, table):
    require(isinstance(table, IndependentLegTable), "Require independently validated immutable leg table")
    require(isinstance(query, dict), "Real query must be an object")
    require("edges" not in query and "sites" not in query, "Real query cannot override immutable routes or Site identities")
    require(query.get("origin") == table.origin_anchor and query.get("destination") == table.destination_anchor,
            "Query origin/destination do not match immutable physical anchors")
    numeric_fields = ("start_time_s", "initial_energy_kwh", "capacity_kwh", "minimum_energy_kwh",
                      "reserve_kwh", "consumption_kwh_per_m", "overhead_s", "lambda_stop_s")
    require(all(type(query.get(key)) is not float for key in numeric_fields),
            "Real query scalar quantities must be exact rational strings, integers or Fractions")
    if query.get("schedule") is not None:
        require(isinstance(query["schedule"], dict) and
                all(type(query["schedule"].get(key)) is not float for key in ("a", "b", "D")),
                "Real schedule values must be exact rationals")
    # Collision-free computational keys preserve even a Site whose textual ID
    # happens to equal an origin/destination road-anchor label.
    used = set(table.sites)
    origin_key, destination_key = "@REF5:origin", "@REF5:destination"
    while origin_key in used:
        origin_key += ":"
    used.add(origin_key)
    while destination_key in used:
        destination_key += ":"
    terminal_sites = tuple(sorted(site_id for site_id, site in table.sites.items()
                                  if site.anchor_id == table.destination_anchor or
                                  table.origin_anchor == table.destination_anchor))
    sites = {site_id: list(site.effects) for site_id, site in table.sites.items() if site_id not in terminal_sites}
    source = dict(query, origin=origin_key, destination=destination_key, sites=sites, edges=[])
    case = normalize_case(source)
    physical = {origin_key: table.origin_anchor, destination_key: table.destination_anchor,
                **{site_id: table.sites[site_id].anchor_id for site_id in sites}}
    legs = {}
    for source_key, source_anchor in physical.items():
        for target_key, target_anchor in physical.items():
            pair = table.pair(source_anchor, target_anchor)
            if pair.reachable:
                legs[source_key, target_key] = RealLeg(source_anchor, target_anchor, pair.time,
                    pair.actual_length, pair.actual_length * case["consumption_kwh_per_m"],
                    pair.time_hex, pair.length_hex, pair.label_direction, table.payload_sha256)
    return PreparedRealCase(case, table, legs, physical, terminal_sites)


def physical_sequence_preflight(prepared, *, keep_exclusions=True):
    """Enumerate prefixes with only independently proved physical exclusions.

    An excessive direct terminal consumption rejects that terminal candidate,
    never its continuation subtree: actual selected lengths are not a metric.
    No incumbent, Region, production bound, or optimizer is consulted.
    """
    case, legs = prepared.case, prepared.legs
    records, candidates, excluded = [], [], []
    counts = dict(prefixes_retained=0, terminal_sequences=0, continuous_regimes=0,
                  excluded_subtree_branches=0, excluded_terminal_candidates=0,
                  exclusions_by_reason={})
    segment_pairs = len(case["charging_segments"]) ** 2

    def exclude(reason, prefix, current, target=None, effect=None, consumption=None, limit=None, subtree=False):
        counts["exclusions_by_reason"][reason] = counts["exclusions_by_reason"].get(reason, 0) + 1
        counts["excluded_subtree_branches" if subtree else "excluded_terminal_candidates"] += 1
        certificate = dict(reason=reason, prefix=prefix, source_road_anchor=prepared.physical_anchor[current],
                           target_road_anchor=prepared.physical_anchor[target] if target is not None else None,
                           candidate_site=target if effect is not None else None, effect=effect,
                           table_sha256=prepared.table.payload_sha256, subtree_excluded=subtree)
        if consumption is not None:
            certificate.update(consumption_kwh=consumption, capacity_limit_kwh=limit,
                               exact_strict_excess=consumption - limit)
            require(consumption > limit, "Invalid exact energy exclusion certificate")
        if keep_exclusions:
            excluded.append(certificate)

    def visit(prefix, remaining, current):
        counts["prefixes_retained"] += 1
        records.append((prefix, remaining, current))
        direct = legs.get((current, case["destination"]))
        if direct is None:
            # Boolean transitivity was checked by the independent parser.
            exclude("road_destination_unreachable", prefix, current, case["destination"], subtree=True)
            return
        if not remaining:
            available = case["initial_energy_kwh"] if not prefix else case["capacity_kwh"]
            terminal_limit = available - case["reserve_kwh"]
            if direct.energy > terminal_limit:
                exclude("terminal_consumption_exceeds_reserve_budget", prefix, current,
                        case["destination"], consumption=direct.energy, limit=terminal_limit)
            else:
                candidates.append((prefix, remaining, current))
                counts["terminal_sequences"] += 1
                charges = sum(effect in ("C", "CS") for _, effect in prefix)
                service = next((effect for _, effect in prefix if effect in ("S", "CS")), None)
                counts["continuous_regimes"] += segment_pairs ** charges * (4 if service == "CS" else 2 if service else 1)
        if len(prefix) == case["H_ref"] or prepared.physical_anchor[current] == prepared.table.destination_anchor:
            return
        for site, effects in case["sites"].items():
            for effect in effects:
                if effect in ("S", "CS") and not remaining:
                    continue
                leg = legs.get((current, site))
                if leg is None:
                    exclude("road_inbound_unreachable", prefix, current, site, effect, subtree=True)
                    continue
                limit = (case["initial_energy_kwh"] if not prefix else case["capacity_kwh"]) - case["minimum_energy_kwh"]
                if leg.energy > limit:
                    exclude("origin_consumption_exceeds_initial_budget" if not prefix else
                            "inter_stop_consumption_exceeds_capacity_budget", prefix, current, site, effect,
                            consumption=leg.energy, limit=limit, subtree=True)
                    continue
                visit(prefix + ((site, effect),), 0 if effect in ("S", "CS") else remaining, site)

    visit((), case["initial_remaining_schedule"], case["origin"])
    return dict(counts=counts, terminal_sequences=candidates, prefixes=records,
                exclusions=excluded, terminal_excluded_sites=prepared.terminal_excluded_sites,
                scope="exact_physical_exclusions_before_continuous_regime_expansion",
                table_sha256=prepared.table.payload_sha256, no_optimization_run=True)


def _replay_real(prepared, sequence, charges):
    case, table, legs = prepared.case, prepared.table, prepared.legs
    sequence = tuple(tuple(event) for event in sequence)
    require(all(len(event) == 2 for event in sequence), "Every stop needs Site ID and semantic effect")
    charges = tuple(number(q, "charge") for q in charges)
    require(len(sequence) <= case["H_ref"] and len(charges) == sum(e in ("C", "CS") for _, e in sequence),
            "Witness stop/charge dimensions violate query")
    current, remaining, index = case["origin"], case["initial_remaining_schedule"], 0
    time, energy = case["start_time_s"], case["initial_energy_kwh"]
    events, route_legs = [], []
    for site, effect in sequence:
        require(site in case["sites"] and effect in case["sites"][site], "Unsupported or terminal Site effect")
        require(prepared.physical_anchor[current] != table.destination_anchor and table.sites[site].anchor_id != table.destination_anchor,
                "Destination road anchor is terminal")
        require(effect not in ("S", "CS") or remaining == 1, "Scheduled requirement already fulfilled")
        leg = legs.get((current, site))
        require(leg is not None, "Witness uses unreachable immutable pair")
        route_legs.append(leg)
        time, energy = time + leg.time, energy - leg.energy
        require(case["minimum_energy_kwh"] <= energy <= case["capacity_kwh"], "Witness violates arrival energy")
        arrival_time, arrival_energy = time, energy
        release = time + case["overhead_s"]
        amount, charge_done, service_start, service_done = R(0), None, None, None
        if effect in ("C", "CS"):
            amount = charges[index]
            index += 1
            require(amount > 0, "C/CS charge must be strictly positive")
            energy += amount
            require(energy <= case["capacity_kwh"], "Witness exceeds capacity")
            duration = sum((max(R(0), min(energy, hi) - max(arrival_energy, lo)) * slope
                            for lo, hi, slope, _ in case["charging_segments"]), R(0))
            charge_done = release + duration
        if effect in ("S", "CS"):
            service_start = max(case["schedule"]["a"], release)
            require(service_start <= case["schedule"]["b"], "Witness misses schedule")
            service_done = service_start + case["schedule"]["D"]
            remaining = 0
        time = max(value for value in (charge_done, service_done) if value is not None)
        events.append(dict(site=site, effect=effect, road_anchor=table.sites[site].anchor_id,
                           arrival_time_s=arrival_time, arrival_kwh=arrival_energy, departure_kwh=energy,
                           completion_s=time, charge_kwh=amount, charge_completion_s=charge_done,
                           schedule_start_s=service_start, schedule_completion_s=service_done,
                           remaining_schedule=remaining))
        current = site
    require(not remaining, "Witness leaves schedule unsatisfied")
    terminal_leg = legs.get((current, case["destination"]))
    require(terminal_leg is not None, "Witness cannot reach destination")
    route_legs.append(terminal_leg)
    time, energy = time + terminal_leg.time, energy - terminal_leg.energy
    require(case["reserve_kwh"] <= energy <= case["capacity_kwh"], "Witness violates terminal reserve")
    J = time - case["start_time_s"] + len(sequence) * case["lambda_stop_s"]
    Q = sum(charges, R(0))
    return dict(J=J, Q_total=Q, H=len(sequence), site_action_tuple=sequence, charges=charges,
                lex_key=(J, Q, len(sequence), sequence), events=events, route_legs=route_legs,
                terminal_time_s=time, terminal_energy_kwh=energy, remaining_schedule=0,
                terminal_road_anchor=table.destination_anchor, witness_replayed=True,
                replay_scope="immutable_selected_leg_constants_and_semantic_events",
                immutable_input_provenance=table.provenance())


def replay_real_witness(query, table, sequence, charges):
    """Reconstruct every leg from the immutable table; no caller drive stream."""
    return _replay_real(prepare_real_case(query, table), sequence, charges)


def estimate_real_regimes(query, table, *, keep_exclusions=True):
    return physical_sequence_preflight(prepare_real_case(query, table), keep_exclusions=keep_exclusions)


def solve_real_case(query, table, *, keep_evidence=True, regime_limit=None):
    """Tree-independent bounded solve. External real-input review remains required.

    Call estimate_real_regimes first and approve a resource plan before using
    large real inputs. An explicit regime_limit is checked before any LP call.
    """
    started = perf_counter()
    envelope = dict(scope=SCOPE, model_domain="immutable_binary64_selected_leg_rationals",
                    H_ref=query.get("H_ref") if isinstance(query, dict) else None,
                    case_id=query.get("case_id") if isinstance(query, dict) else None)
    try:
        prepared = prepare_real_case(query, table)
        preflight = physical_sequence_preflight(prepared)
    except (InvalidInput, TypeError, ValueError) as error:
        return dict(**envelope, result=dict(status="invalid_input", reason=str(error)))
    if regime_limit is not None:
        require(type(regime_limit) is int and regime_limit >= 0, "regime_limit must be a nonnegative integer")
        if preflight["counts"]["continuous_regimes"] > regime_limit:
            return dict(**envelope, result=dict(status="unresolved", reason="Explicit preflight regime budget exceeded"),
                        preflight=preflight, all_regimes_certified=False, optimization_started=False)
    result = solve_prepared_case(prepared.case, prepared.legs,
                                lambda sequence, charges: _replay_real(prepared, sequence, charges),
                                envelope=envelope, keep_evidence=keep_evidence, started=started,
                                enumeration=preflight["terminal_sequences"])
    result.update(preflight=preflight, immutable_input_provenance=table.provenance(), tree_independent=True)
    return result


def query_from_resolved_state(state, table):
    """Independently map the frozen C32 resolved-query export to REF scalars.

    Baselines/windows and initial SOC are verified, not silently recomputed to
    different values. This is preparation only and makes no solver call.
    """
    from .real_input import decode_binary64
    require(isinstance(state, dict), "Resolved state must be an object")
    require(all(type(state.get(key)) is int and state[key] >= 0 for key in
                ("origin_road_anchor", "destination_road_anchor")), "Dense road anchors must be nonnegative integers")
    origin, destination = f"road:{state['origin_road_anchor']}", f"road:{state['destination_road_anchor']}"
    require((origin, destination) == (table.origin_anchor, table.destination_anchor), "Resolved query physical-anchor mismatch")
    reference = state.get("immutable_direct_leg_table")
    require(isinstance(reference, dict) and reference.get("sha256") == table.payload_sha256, "Resolved query table hash mismatch")
    baseline = table.pair(origin, destination)
    time, time_hex = decode_binary64(state.get("accepted_baseline_time_s"))
    length, length_hex = decode_binary64(state.get("accepted_baseline_actual_length_m"))
    require(baseline.reachable and (time, time_hex, length, length_hex) ==
            (baseline.time, baseline.time_hex, baseline.actual_length, baseline.length_hex),
            "Resolved query baseline differs from accepted immutable native row")
    primitive = state.get("charging_primitive")
    require(isinstance(primitive, dict), "Resolved query needs the frozen charging primitive")
    breaks = primitive.get("energy_breakpoints_kwh")
    slopes = primitive.get("slopes_s_per_kwh")
    intercepts = primitive.get("intercepts_s")
    require(all(isinstance(values, list) for values in (breaks, slopes, intercepts)) and
            len(breaks) == len(slopes) + 1 and len(slopes) == len(intercepts), "Malformed resolved charging primitive")
    segments = [[breaks[i], breaks[i+1], slopes[i], intercepts[i]] for i in range(len(slopes))]
    schedule = state.get("schedule")
    if state.get("mode") == "energy_only":
        require(schedule is None, "Energy-only state cannot silently acquire a service requirement")
    else:
        require(state.get("mode") == "energy_and_scheduled" and isinstance(schedule, dict), "Unsupported resolved query mode")
        frozen_time, frozen_hex = decode_binary64(schedule.get("baseline_binary64"))
        require((frozen_time, frozen_hex) == (time, time_hex) and number(schedule.get("baseline_time_s"), "baseline") == time,
                "Scheduled baseline provenance mismatch")
        a, b = number(schedule.get("window_start_s"), "window start"), number(schedule.get("window_end_s"), "window end")
        require(a == R(2,5)*time and b == R(7,10)*time, "Frozen exact baseline/window arithmetic mismatch")
        schedule = dict(a=a, b=b, D=schedule.get("duration_s"))
    initial, capacity = number(state.get("initial_energy_kwh"), "initial energy"), number(state.get("capacity_kwh"), "capacity")
    require(initial == number(state.get("initial_soc"), "initial SOC") * capacity, "Initial SOC/energy mismatch")
    query = dict(case_id=state.get("state_id"), pool_id=state.get("pool_id"), H_ref=state.get("H_ref"),
                 origin=origin, destination=destination, start_time_s=state.get("start_time_s"),
                 initial_energy_kwh=initial, capacity_kwh=capacity,
                 minimum_energy_kwh=state.get("energy_floor_kwh"), reserve_kwh=state.get("terminal_reserve_kwh"),
                 consumption_kwh_per_m=state.get("consumption_kwh_per_m"), overhead_s=state.get("overhead_s"),
                 lambda_stop_s=state.get("stop_penalty_s"), charging_segments=segments, schedule=schedule)
    prepare_real_case(query, table)
    return query
