"""Independent exact fixture semantics, directed legs and replay for REF5."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as R
from itertools import product
import math


class InvalidInput(ValueError):
    pass


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, R)):
        raise InvalidInput(f"{name} must be a finite rational number")
    try:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError()
        return R(str(value))
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise InvalidInput(f"{name} must be a finite rational number") from exc


def normalize_case(source, *, allow_nonnegative_extension=False):
    """Validate the original JSON fixture schema; do not mutate its contents.

    Added optional field initial_remaining_schedule is r in {0,1}. Its default
    is 1 when schedule is supplied, else 0. Sites list allowed effects explicitly;
    [C,S] does not silently grant CS. Empty capability lists are valid.
    """
    if not isinstance(source, dict):
        raise InvalidInput("Case must be an object")
    c = dict(source)
    for key in ("origin", "destination"):
        if not isinstance(c.get(key), str) or not c[key]:
            raise InvalidInput(f"{key} must be a nonempty string")
    if type(c.get("H_ref")) is not int or c["H_ref"] < 0:
        raise InvalidInput("H_ref must be an explicit nonnegative integer diagnostic bound")
    for key in ("start_time_s", "initial_energy_kwh", "capacity_kwh", "minimum_energy_kwh",
                "reserve_kwh", "consumption_kwh_per_m", "overhead_s", "lambda_stop_s"):
        if key not in c:
            raise InvalidInput(f"Missing {key}")
        c[key] = number(c[key], key)
    lo, cap = c["minimum_energy_kwh"], c["capacity_kwh"]
    if not (0 <= lo <= c["initial_energy_kwh"] <= cap and lo <= c["reserve_kwh"] <= cap):
        raise InvalidInput("Invalid battery bounds, initial energy, or terminal reserve")
    if any(c[key] < 0 for key in ("consumption_kwh_per_m", "overhead_s", "lambda_stop_s")):
        raise InvalidInput("Consumption, overhead and stop penalty must be nonnegative")
    if not allow_nonnegative_extension and c["overhead_s"] <= 0:
        raise InvalidInput("Production domain requires positive stop overhead")
    sites = c.get("sites")
    if not isinstance(sites, dict):
        raise InvalidInput("sites must map string identities to explicit action lists")
    for site, actions in sites.items():
        if not isinstance(site, str) or not site or not isinstance(actions, (list, tuple)):
            raise InvalidInput("Invalid site/capability list")
        if any(action not in ("C", "S", "CS") for action in actions) or len(set(actions)) != len(actions):
            raise InvalidInput("Unknown or duplicate site action")
    c["sites"] = {site: tuple(sorted(actions)) for site, actions in sorted(sites.items())}
    schedule = c.get("schedule")
    if schedule is not None:
        if not isinstance(schedule, dict) or any(k not in schedule for k in ("a", "b", "D")):
            raise InvalidInput("schedule requires a, b and D")
        schedule = {k: number(schedule[k], f"schedule.{k}") for k in ("a", "b", "D")}
        if schedule["a"] > schedule["b"] or schedule["D"] < 0:
            raise InvalidInput("Invalid service window or duration")
    c["schedule"] = schedule
    r = c.get("initial_remaining_schedule", int(schedule is not None))
    if type(r) is not int or r not in (0, 1) or r and schedule is None:
        raise InvalidInput("initial_remaining_schedule must be 0 or 1, and r=1 needs a schedule")
    c["initial_remaining_schedule"] = r
    segments = c.get("charging_segments", [])
    if not isinstance(segments, (list, tuple)):
        raise InvalidInput("charging_segments must be a list")
    parsed = []
    for segment in segments:
        if not isinstance(segment, (list, tuple)) or len(segment) != 4:
            raise InvalidInput("Each charging segment is [lo, hi, slope, intercept]")
        left, right, slope, intercept = (number(v, "charging segment") for v in segment)
        if not left < right or slope <= 0:
            raise InvalidInput("Charging segments need nonempty domains and positive slopes")
        if parsed and (left != parsed[-1][1] or slope * left + intercept != parsed[-1][2] * left + parsed[-1][3]):
            raise InvalidInput("Charging primitive must have contiguous domains and be continuous")
        parsed.append((left, right, slope, intercept))
    has_charge = any(action in ("C", "CS") for actions in c["sites"].values() for action in actions)
    if (has_charge or parsed) and (not parsed or parsed[0][0] > lo or parsed[-1][1] < cap):
        raise InvalidInput("Charging primitive must cover the full battery domain")
    c["charging_segments"] = tuple(parsed)
    edges = c.get("edges")
    if not isinstance(edges, (list, tuple)):
        raise InvalidInput("edges must be a list")
    c["edges"] = []
    edge_ids = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict) or any(key not in edge for key in ("source", "target", "time_s", "length_m")):
            raise InvalidInput("Each edge requires source, target, time_s and length_m")
        if any(not isinstance(edge[key], str) or not edge[key] for key in ("source", "target")):
            raise InvalidInput("Road vertex identities must be nonempty strings")
        t, length = number(edge["time_s"], "edge time"), number(edge["length_m"], "edge length")
        if t < 0 or length < 0:
            raise InvalidInput("Road time and physical length must be nonnegative")
        if not allow_nonnegative_extension and (t <= 0 or length <= 0):
            raise InvalidInput("Production domain requires positive road-edge time and length")
        identity = edge.get("edge_id", edge.get("id", f"input:{index:08d}"))
        if not isinstance(identity, str) or identity in edge_ids:
            raise InvalidInput("Edge IDs must be unique strings")
        edge_ids.add(identity)
        c["edges"].append(dict(source=edge["source"], target=edge["target"], time_s=t,
                               length_m=length, id=identity))
    return c


@dataclass(frozen=True)
class Leg:
    time: R
    length: R
    energy: R
    nodes: tuple[str, ...]
    edges: tuple[str, ...]


def selected_legs(case):
    """Enumerate simple directed paths in a small graph, including cyclic graphs.

    Frozen deterministic tie rule is (time, node tuple, edge-ID tuple). Physical
    length is read from exactly that chosen fastest path; it is never optimized.
    Self legs select the zero-length route. Nonnegative costs ensure a fastest
    simple path exists, even with zero-time cycles. This intentionally slow
    independent algorithm is for bounded diagnostics, not an OSM router.
    """
    adjacency = {}
    for edge in case["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)
    anchors = {case["origin"], case["destination"], *case["sites"]}
    legs = {}
    for start in sorted(anchors):
        legs[start, start] = Leg(R(0), R(0), R(0), (start,), ())
        stack = [(start, R(0), R(0), (start,), ())]
        while stack:
            node, time, length, nodes, edges = stack.pop()
            for edge in adjacency.get(node, ()):
                target = edge["target"]
                if target in nodes:
                    continue
                path = nodes + (target,)
                identities = edges + (edge["id"],)
                t, distance = time + edge["time_s"], length + edge["length_m"]
                if target in anchors:
                    previous = legs.get((start, target))
                    if previous is None or (t, path, identities) < (previous.time, previous.nodes, previous.edges):
                        legs[start, target] = Leg(t, distance, distance * case["consumption_kwh_per_m"], path, identities)
                stack.append((target, t, distance, path, identities))
    return legs


def sequences(case, legs):
    """All reachable static site/action sequences up to H_ref, with repeats.

    Prefixes with an unsatisfied service or no final directed leg are recorded
    by the caller; they are not terminal candidates. Destination is terminal.
    """
    def visit(prefix, remaining, current):
        yield prefix, remaining, current
        if len(prefix) == case["H_ref"] or current == case["destination"]:
            return
        for site, actions in case["sites"].items():
            if site == case["destination"] or (current, site) not in legs:
                continue
            for effect in actions:
                if effect in ("S", "CS") and not remaining:
                    continue
                yield from visit(prefix + ((site, effect),),
                                 0 if effect in ("S", "CS") else remaining, site)
    yield from visit((), case["initial_remaining_schedule"], case["origin"])


@dataclass(frozen=True)
class Affine:
    coefficients: tuple[R, ...]
    constant: R = R(0)

    def __add__(self, other):
        if not isinstance(other, Affine):
            other = Affine((R(0),) * len(self.coefficients), R(other))
        return Affine(tuple(a + b for a, b in zip(self.coefficients, other.coefficients)), self.constant + other.constant)

    __radd__ = __add__

    def __mul__(self, scalar):
        return Affine(tuple(c * scalar for c in self.coefficients), self.constant * scalar)

    __rmul__ = __mul__

    def __sub__(self, other):
        return self + (other * -1 if isinstance(other, Affine) else -R(other))

    def at(self, values):
        return self.constant + sum((c * x for c, x in zip(self.coefficients, values)), R(0))


def assignments(case, sequence):
    count = sum(effect in ("C", "CS") for _, effect in sequence)
    service = next((effect for _, effect in sequence if effect in ("S", "CS")), None)
    for segments in product(range(len(case["charging_segments"])), repeat=2 * count):
        for schedule_branch in ("early", "late") if service else (None,):
            for completion_branch in ("charge", "service") if service == "CS" else (None,):
                yield segments, schedule_branch, completion_branch


def regime_model(case, sequence, legs, assignment):
    segments, schedule_branch, completion_branch = assignment
    n = sum(effect in ("C", "CS") for _, effect in sequence)
    zero = Affine((R(0),) * n)
    time, energy = zero + case["start_time_s"], zero + case["initial_energy_kwh"]
    A, b = [], []

    def le(left, right):
        expression = left - right
        A.append(expression.coefficients)
        b.append(-expression.constant)

    variables = []
    for j in range(n):
        unit = [R(0)] * n
        unit[j] = R(1)
        variables.append(Affine(tuple(unit)))
        le(zero, variables[-1])
    current, index = case["origin"], 0
    for site, effect in sequence:
        leg = legs[current, site]
        time, energy = time + leg.time, energy - leg.energy
        le(zero + case["minimum_energy_kwh"], energy)
        le(energy, zero + case["capacity_kwh"])
        release = time + case["overhead_s"]
        charged, completed_service = None, None
        if effect in ("C", "CS"):
            departure = energy + variables[index]
            lo_a, hi_a, slope_a, intercept_a = case["charging_segments"][segments[2 * index]]
            lo_d, hi_d, slope_d, intercept_d = case["charging_segments"][segments[2 * index + 1]]
            le(zero + lo_a, energy)
            le(energy, zero + hi_a)
            le(zero + lo_d, departure)
            le(departure, zero + hi_d)
            charged = release + departure * slope_d + intercept_d - energy * slope_a - intercept_a
            energy = departure
            index += 1
        if effect in ("S", "CS"):
            schedule = case["schedule"]
            if schedule_branch == "early":
                le(release, zero + schedule["a"])
                start = zero + schedule["a"]
            else:
                le(zero + schedule["a"], release)
                start = release
            le(start, zero + schedule["b"])
            completed_service = start + schedule["D"]
        if effect == "CS":
            if completion_branch == "charge":
                le(completed_service, charged)
                time = charged
            else:
                le(charged, completed_service)
                time = completed_service
        else:
            time = charged if effect == "C" else completed_service
        le(energy, zero + case["capacity_kwh"])
        current = site
    leg = legs[current, case["destination"]]
    terminal = energy - leg.energy
    le(zero + case["reserve_kwh"], terminal)
    objective = time + leg.time - case["start_time_s"] + len(sequence) * case["lambda_stop_s"]
    return A, b, objective


def replay_witness(source, sequence, charges, legs=None, *, allow_nonnegative_extension=False):
    """Validate a concrete witness against original piecewise/max semantics."""
    case = normalize_case(source, allow_nonnegative_extension=allow_nonnegative_extension)
    independently_selected = selected_legs(case)
    if legs is not None and legs != independently_selected:
        raise InvalidInput("Supplied witness legs differ from independently selected fastest routes")
    legs = independently_selected
    sequence, charges = tuple(tuple(event) for event in sequence), tuple(number(q, "charge") for q in charges)
    if len(sequence) > case["H_ref"] or len(charges) != sum(effect in ("C", "CS") for _, effect in sequence):
        raise InvalidInput("Witness stop or charge-vector dimension mismatch")
    time, energy = case["start_time_s"], case["initial_energy_kwh"]
    current, index, remaining = case["origin"], 0, case["initial_remaining_schedule"]
    events, route_legs = [], []
    for site, effect in sequence:
        if current == case["destination"] or site == case["destination"]:
            raise InvalidInput("Destination is terminal, not a stop")
        if site not in case["sites"] or effect not in case["sites"][site]:
            raise InvalidInput("Site does not support witness action")
        if effect in ("S", "CS") and not remaining:
            raise InvalidInput("Witness repeats an already satisfied service")
        if (current, site) not in legs:
            raise InvalidInput("Witness has an unreachable directed leg")
        leg = legs[current, site]
        route_legs.append(leg)
        time, energy = time + leg.time, energy - leg.energy
        if not case["minimum_energy_kwh"] <= energy <= case["capacity_kwh"]:
            raise InvalidInput("Witness violates arrival battery bounds")
        arrival_time, arrival_energy = time, energy
        release = time + case["overhead_s"]
        amount, charge_completion, start, service_completion = R(0), None, None, None
        if effect in ("C", "CS"):
            amount = charges[index]
            index += 1
            if amount <= 0:
                raise InvalidInput("C and CS require strictly positive charge")
            energy += amount
            if energy > case["capacity_kwh"]:
                raise InvalidInput("Witness exceeds capacity")
            duration = sum((max(R(0), min(energy, hi) - max(arrival_energy, lo)) * slope
                            for lo, hi, slope, _ in case["charging_segments"]), R(0))
            charge_completion = release + duration
        if effect in ("S", "CS"):
            start = max(case["schedule"]["a"], release)
            if start > case["schedule"]["b"]:
                raise InvalidInput("Witness misses hard service window")
            service_completion = start + case["schedule"]["D"]
            remaining = 0
        time = max(value for value in (charge_completion, service_completion) if value is not None)
        events.append(dict(site=site, effect=effect, charge_kwh=amount, arrival_time_s=arrival_time,
                           arrival_kwh=arrival_energy, departure_kwh=energy, completion_s=time,
                           charge_completion_s=charge_completion, schedule_start_s=start,
                           schedule_completion_s=service_completion, remaining_schedule=remaining))
        current = site
    if remaining:
        raise InvalidInput("Witness leaves the hard service requirement unsatisfied")
    if (current, case["destination"]) not in legs:
        raise InvalidInput("Witness destination is unreachable")
    leg = legs[current, case["destination"]]
    route_legs.append(leg)
    terminal, terminal_time = energy - leg.energy, time + leg.time
    if not case["reserve_kwh"] <= terminal <= case["capacity_kwh"]:
        raise InvalidInput("Witness violates terminal battery/reserve")
    J = terminal_time - case["start_time_s"] + len(sequence) * case["lambda_stop_s"]
    Q = sum(charges, R(0))
    return dict(J=J, Q_total=Q, H=len(sequence), site_action_tuple=sequence, charges=charges,
                events=events, terminal_energy_kwh=terminal, terminal_time_s=terminal_time,
                remaining_schedule=remaining, route_legs=route_legs,
                lex_key=(J, Q, len(sequence), sequence), witness_replayed=True)
