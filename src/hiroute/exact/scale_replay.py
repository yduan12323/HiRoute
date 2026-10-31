"""Independent physical ledger for a scale solver's concrete witness.

This verifier does not import the transition pipeline or an optimizer. It
checks a recorded edge path and proposed positive charges against the original
physical equations. Selected-fastest/tie semantics require a separate routing
audit; physical replay alone is not an independent optimality certificate.
"""
from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
import re


_RATIONAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?$")


def _number(value):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("physical replay requires exact rational values")
    if isinstance(value, (int, Fraction)):
        return Fraction(value)
    if isinstance(value, str) and _RATIONAL.fullmatch(value):
        return Fraction(value)
    raise ValueError("physical replay requires exact rational values")


def _field(value, name, fallback=None):
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        if fallback is not None and fallback in value:
            return value[fallback]
    elif hasattr(value, name):
        return getattr(value, name)
    raise ValueError("recorded leg is missing " + name)


def _key(value):
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("witness key must contain J,Q,H,Pi")
    if type(value[2]) is not int or value[2] < 0:
        raise ValueError("invalid witness stop count")
    plan = tuple(tuple(row) for row in value[3])
    if any(len(row) != 2 for row in plan):
        raise ValueError("invalid witness action tuple")
    return (_number(value[0]), _number(value[1]), value[2], plan)


def _charging_curve(snapshot):
    curve = tuple(tuple(_number(v) for v in row) for row in snapshot.charging_curve)
    capacity = _number(snapshot.capacity_kwh)
    if not curve or curve[0][0] != 0 or curve[-1][1] != capacity:
        raise ValueError("physical charging curve must cover the battery domain")
    for i, row in enumerate(curve):
        if len(row) != 4:
            raise ValueError("invalid physical charging segment")
        lo, hi, slope, intercept = row
        if lo >= hi or slope < 0:
            raise ValueError("charging curve must be ordered and nondecreasing")
        if i:
            previous = curve[i-1]
            if previous[1] != lo or previous[2]*lo+previous[3] != slope*lo+intercept:
                raise ValueError("physical charging curve must be contiguous and continuous")
    return curve


def _charge_time(curve, before, after):
    def value(energy):
        matches = [slope*energy+intercept for lo,hi,slope,intercept in curve
                   if lo <= energy <= hi]
        if not matches or any(x != matches[0] for x in matches):
            raise ValueError("charge endpoint is outside the physical curve")
        return matches[0]
    return value(after)-value(before)


def verify_scale_witness(snapshot, record, site_to_road=None):
    """Recompute a concrete record's physical route and full objective key.

    ``record`` contains ``key``, ``plan``, ``legs`` and ``replay`` (including its
    complete event trace). A leg can be a dataclass or serialized mapping. With
    Site aliases, ``site_to_road`` maps each logical endpoint to its physical
    road vertex; leg headers may use logical or road IDs, but every edge chain
    must connect the mapped physical endpoints. No graph search is performed.
    """
    aliases = {} if site_to_road is None else dict(site_to_road)
    plan = tuple(tuple(row) for row in record["plan"])
    if any(len(row) != 2 for row in plan):
        raise ValueError("invalid physical action sequence")
    claimed_key = _key(record["key"])
    if claimed_key[2:] != (len(plan), plan):
        raise ValueError("witness key and action sequence disagree")
    legs = tuple(record["legs"])
    if len(legs) != len(plan)+1:
        raise ValueError("witness requires one selected leg per drive")
    replay = record["replay"]
    trace = tuple(replay["trace"])
    if len(trace) != 2*len(plan)+1:
        raise ValueError("physical event trace length disagrees with actions")

    energy, time = _number(snapshot.initial_energy_kwh), _number(snapshot.departure_time_s)
    initial_energy, start_time = energy, time
    floor, capacity, reserve = (_number(snapshot.minimum_energy_kwh),
                                _number(snapshot.capacity_kwh),
                                _number(snapshot.destination_reserve_kwh))
    overhead, penalty, rate = (_number(snapshot.stop_overhead_s),
                               _number(snapshot.stop_penalty_s),
                               _number(snapshot.consumption_kwh_per_m))
    if (capacity <= 0 or floor < 0 or not floor <= energy <= capacity or
            not floor <= reserve <= capacity or overhead <= 0 or min(penalty, rate) < 0):
        raise ValueError("invalid physical vehicle or stop parameters")
    pending = snapshot.initial_remaining_schedule
    if type(pending) is not int or pending not in (0,1):
        raise ValueError("invalid initial physical schedule state")
    if snapshot.schedule is None:
        if pending:
            raise ValueError("pending physical activity has no schedule")
        schedule = None
    else:
        schedule = tuple(_number(snapshot.schedule[k]) for k in ("a", "b", "D"))
        if schedule[0] > schedule[1] or schedule[2] < 0:
            raise ValueError("invalid physical schedule window")
    curve = _charging_curve(snapshot) if any(effect in {"C", "CS"} for _,effect in plan) else ()
    # The initial cut is upward closed: a witness may wait at the origin
    # before its first drive. This is an explicit feasible choice, charged in
    # elapsed time. Later event times must connect without unexplained gaps.
    if len(trace[0]) != 6:
        raise ValueError("invalid initial physical drive event")
    initial_drive_time = _number(trace[0][3])
    if initial_drive_time < start_time:
        raise ValueError("physical witness departs before the declared start")
    time = initial_drive_time
    initial_wait = time-start_time
    total_distance = total_drive_time = total_charge = Fraction(0)
    charges = []
    anchor = snapshot.origin
    trace_index = 0

    def event(effect, site, before_energy, before_time, after_energy, after_time):
        nonlocal trace_index
        row = trace[trace_index]
        trace_index += 1
        if len(row) != 6 or tuple(row[:2]) != (effect, site):
            raise ValueError("physical event order or Site differs from witness")
        if tuple(_number(x) for x in row[2:]) != (
                before_energy, before_time, after_energy, after_time):
            raise ValueError("physical event equation disagrees with witness")

    destinations = tuple(site for site,_ in plan)+(snapshot.destination,)
    for index, (leg, target) in enumerate(zip(legs, destinations)):
        physical_source, physical_target = aliases.get(anchor, anchor), aliases.get(target, target)
        if (_field(leg, "source") not in {anchor, physical_source} or
                _field(leg, "target") not in {target, physical_target}):
            raise ValueError("recorded leg endpoints disagree with physical actions")
        duration = length = Fraction(0)
        node = physical_source
        edges = tuple(_field(leg, "edges"))
        for edge in edges:
            if _field(edge, "source") != node:
                raise ValueError("recorded physical road path is not contiguous")
            node = _field(edge, "target")
            edge_time = _number(_field(edge, "time_s"))
            edge_length = _number(_field(edge, "length_m"))
            if edge_time <= 0 or edge_length <= 0:
                raise ValueError("physical road edges require positive weights")
            duration += edge_time
            length += edge_length
        if node != physical_target:
            raise ValueError("recorded physical road path ends at the wrong anchor")
        if (duration != _number(_field(leg, "time_s")) or
                length != _number(_field(leg, "length_m", "actual_length_m"))):
            raise ValueError("recorded leg totals differ from its physical road path")
        before_energy, before_time = energy, time
        energy, time = energy-rate*length, time+duration
        if energy < floor:
            raise ValueError("physical drive violates battery floor")
        event("D", target, before_energy, before_time, energy, time)
        total_distance += length
        total_drive_time += duration
        anchor = target
        if index == len(plan):
            break

        site, effect = plan[index]
        if site not in snapshot.site_capabilities or effect not in snapshot.site_capabilities[site]:
            raise ValueError("physical action is not a declared Site capability")
        if effect not in {"C", "S", "CS"}:
            raise ValueError("unknown physical action")
        before_energy, before_time = energy, time
        charge_duration = Fraction(0)
        if effect in {"C", "CS"}:
            row = trace[trace_index]
            if len(row) != 6:
                raise ValueError("invalid physical charge event")
            output_energy = _number(row[4])
            if not energy < output_energy <= capacity:
                raise ValueError("physical charge must be strictly positive and respect capacity")
            charge_duration = _charge_time(curve, energy, output_energy)
            charge = output_energy-energy
            energy = output_energy
            charges.append(charge)
            total_charge += charge
        if effect == "C":
            time += overhead+charge_duration
        else:
            if not pending or schedule is None:
                raise ValueError("physical service must complete the one pending activity")
            a,b,activity_duration = schedule
            if time > b-overhead:
                raise ValueError("physical service violates latest start")
            time = max(a+activity_duration,
                       time+overhead+max(charge_duration, activity_duration))
            pending = 0
        event(effect, site, before_energy, before_time, energy, time)
    if pending or energy < reserve:
        raise ValueError("physical terminal violates activity completion or battery reserve")
    independent_key = (time-start_time+penalty*len(plan), total_charge, len(plan), plan)
    if independent_key != claimed_key:
        raise ValueError("independent physical objective key disagrees with witness")
    # Check redundant summaries too; they must not conceal a changed trace.
    for name, expected in (("energy", energy), ("time", time),
                           ("rho", total_charge-energy)):
        if name in replay and _number(replay[name]) != expected:
            raise ValueError("physical replay summary disagrees on " + name)
    if "events" in replay and tuple(tuple(row) for row in replay["events"]) != plan:
        raise ValueError("physical replay action summary disagrees")
    if "key" in replay and _key(replay["key"]) != independent_key:
        raise ValueError("physical replay key summary disagrees")
    # Conservation is a separate check on accumulated charge and drive energy.
    if energy != initial_energy+total_charge-rate*total_distance:
        raise ValueError("physical energy conservation failed")
    return dict(physical_verified=True, total_distance_m=total_distance,
                driving_time_s=total_drive_time, elapsed_time_s=time-start_time,
                initial_wait_s=initial_wait,
                positive_charge_count=len(charges), charges_kwh=tuple(charges),
                independent_key=independent_key, terminal_energy_kwh=energy)
