"""Independent finite-regime reference for the blocking C/C/S hand case.

This is a diagnostic reference, not a completed B21 REF implementation. It
enumerates every static effect-labelled sequence at H <= 4 and certifies its
continuous C/S regimes in rational arithmetic. No frontier code is imported.
"""
from dataclasses import dataclass
from fractions import Fraction as R
from itertools import product
from time import perf_counter

import numpy as np
from scipy.optimize import linprog


@dataclass(frozen=True)
class Affine:
    coefficients: tuple
    constant: R = R(0)

    def __add__(self, other):
        if not isinstance(other, Affine):
            other = Affine((R(0),) * len(self.coefficients), R(other))
        return Affine(tuple(a + b for a, b in zip(self.coefficients, other.coefficients)),
                      self.constant + other.constant)

    __radd__ = __add__

    def __mul__(self, scalar):
        return Affine(tuple(c * scalar for c in self.coefficients), self.constant * scalar)

    __rmul__ = __mul__

    def __sub__(self, other):
        return self + (other * -1 if isinstance(other, Affine) else -R(other))

    def at(self, values):
        return self.constant + sum((c * x for c, x in zip(self.coefficients, values)), R(0))


def dot(a, b):
    return sum((x * y for x, y in zip(a, b)), R(0))


def rational(value):
    return R(str(float(value))).limit_denominator(1_000_000_000)


def exact_lp(c, A, b, equality=None):
    """Discover an LP basis with HiGHS, then verify exact primal/dual equality.

    All variable bounds are explicit rows; there are no implicit q thresholds.
    A rational positive Phase-I optimum certifies closed-regime infeasibility.
    """
    n = len(c)
    equality = equality or []
    ae = [row for row, _ in equality]
    be = [rhs for _, rhs in equality]
    result = linprog(np.array(c, float), A_ub=np.array(A, float), b_ub=np.array(b, float),
                     A_eq=np.array(ae, float) if ae else None,
                     b_eq=np.array(be, float) if be else None,
                     bounds=[(None, None)] * n, method="highs",
                     options={"primal_feasibility_tolerance": 1e-9,
                              "dual_feasibility_tolerance": 1e-9})
    if result.status == 2:
        assert not equality, "Unexpected infeasible optimal face"
        phase_A = [tuple(row) + (R(-1),) for row in A]
        phase_A.append((R(0),) * n + (R(-1),))
        phase = exact_lp((R(0),) * n + (R(1),), phase_A, list(b) + [R(0)])
        assert phase["objective"] > 0
        return dict(status="infeasible", phase_I_certificate=phase)
    if not result.success:
        raise ArithmeticError(f"Unverified LP result: {result.message}")
    x = tuple(map(rational, result.x))
    y = tuple(map(rational, result.ineqlin.marginals))
    z = tuple(map(rational, result.eqlin.marginals))
    assert all(dot(row, x) <= rhs for row, rhs in zip(A, b)), "Primal infeasible"
    assert all(dot(row, x) == rhs for row, rhs in equality), "Equality infeasible"
    assert all(v <= 0 for v in y), "Dual sign invalid"
    assert all(sum((row[j] * v for row, v in zip(A, y)), R(0))
               + sum((row[j] * v for row, v in zip(ae, z)), R(0)) == c[j]
               for j in range(n)), "Dual infeasible"
    primal = dot(c, x)
    dual = dot(b, y) + dot(be, z)
    assert primal == dual, "Strong duality not verified"
    return dict(status="optimal", x=x, objective=primal, inequality_dual=y, equality_dual=z,
                exact_primal_dual_verified=True)


def strict_face(A, b, n, equalities=()):
    # Auxiliary common slack is a strict-feasibility certificate. Its cap of
    # one merely bounds this auxiliary maximization; no charge is required to
    # reach one, and arbitrarily small positive slack is accepted exactly.
    rows = [tuple(row) + (R(0),) for row in A]
    rhs = list(b)
    for j in range(n):
        row = [R(0)] * (n + 1)
        row[j], row[-1] = R(-1), R(1)
        rows.append(tuple(row))
        rhs.append(R(0))
    rows.extend([(R(0),) * n + (R(-1),), (R(0),) * n + (R(1),)])
    rhs.extend([R(0), R(1)])
    eq = [(tuple(row) + (R(0),), value) for row, value in equalities]
    return exact_lp((R(0),) * n + (R(-1),), rows, rhs, eq)


def selected_legs(case):
    """Enumerate paths in this directed acyclic fixture; select fastest time.

    Actual length belongs to the selected path. It is never minimized as a
    distance metric. Self legs are the accepted zero-length route.
    """
    adjacency = {}
    nodes = {case["origin"], case["destination"], *case["sites"]}
    for edge in case["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)
    legs = {}
    for start in sorted(nodes):
        legs[start, start] = (R(0), R(0))
        stack = [(start, R(0), R(0), (start,))]
        best = {}
        while stack:
            node, time, length, path = stack.pop()
            for edge in adjacency.get(node, []):
                target = edge["target"]
                assert target not in path, "Probe expects an acyclic directed graph"
                candidate = (time + R(edge["time_s"]), length + R(edge["length_m"]), path + (target,))
                if target not in best or (candidate[0], candidate[2]) < (best[target][0], best[target][2]):
                    best[target] = candidate
                stack.append((target, *candidate))
        for target, (time, length, _) in best.items():
            legs[start, target] = (time, length * R(case["consumption_kwh_per_m"]))
    return legs


def sequences(case):
    def visit(prefix, remaining):
        yield prefix
        if len(prefix) == case["H_ref"]:
            return
        for site, capabilities in sorted(case["sites"].items()):
            for effect in capabilities:
                assert effect in {"C", "S"}, "This blocking probe uses only C/S"
                if effect == "S" and not remaining:
                    continue
                yield from visit(prefix + ((site, effect),), remaining and effect != "S")
    yield from visit((), True)


def regime_model(case, sequence, legs, assignment, schedule_branch):
    n = sum(effect == "C" for _, effect in sequence)
    zero = Affine((R(0),) * n)
    time, energy = zero + R(case["start_time_s"]), zero + R(case["initial_energy_kwh"])
    A, b = [], []

    def le(left, right):
        expression = left - right
        A.append(expression.coefficients)
        b.append(-expression.constant)

    for j in range(n):
        unit = [R(0)] * n
        unit[j] = R(1)
        le(zero, Affine(tuple(unit)))
    current, charge_index = case["origin"], 0
    segments = case["charging_segments"]
    for site, effect in sequence:
        drive, consumption = legs[current, site]
        time, energy = time + drive, energy - consumption
        le(zero + R(case["minimum_energy_kwh"]), energy)
        release = time + R(case["overhead_s"])
        if effect == "C":
            vector = [R(0)] * n
            vector[charge_index] = R(1)
            departure = energy + Affine(tuple(vector))
            lo_a, hi_a, slope_a, intercept_a = map(R, segments[assignment[2 * charge_index]])
            lo_d, hi_d, slope_d, intercept_d = map(R, segments[assignment[2 * charge_index + 1]])
            le(zero + lo_a, energy)
            le(energy, zero + hi_a)
            le(zero + lo_d, departure)
            le(departure, zero + hi_d)
            time = release + departure * slope_d + intercept_d - energy * slope_a - intercept_a
            energy = departure
            charge_index += 1
        else:
            if schedule_branch == "early":
                le(release, zero + R(case["schedule"]["a"]))
                start = zero + R(case["schedule"]["a"])
            else:
                le(zero + R(case["schedule"]["a"]), release)
                start = release
            le(start, zero + R(case["schedule"]["b"]))
            time = start + R(case["schedule"]["D"])
        le(energy, zero + R(case["capacity_kwh"]))
        current = site
    drive, consumption = legs[current, case["destination"]]
    terminal = energy - consumption
    le(zero + R(case["reserve_kwh"]), terminal)
    objective = time + drive - R(case["start_time_s"]) + len(sequence) * R(case["lambda_stop_s"])
    return A, b, objective


def original_witness(case, sequence, q, legs):
    """Recheck a continuous witness in the original piecewise/max semantics."""
    def charging(a, b):
        assert b > a, "A C effect must add strictly positive charge"
        total = R(0)
        for lo, hi, slope, _ in case["charging_segments"]:
            total += max(R(0), min(b, R(hi)) - max(a, R(lo))) * R(slope)
        return total
    time, energy = R(case["start_time_s"]), R(case["initial_energy_kwh"])
    current, index = case["origin"], 0
    events = []
    for site, effect in sequence:
        drive, consumption = legs[current, site]
        time, energy = time + drive, energy - consumption
        assert energy >= R(case["minimum_energy_kwh"])
        arrival = energy
        release = time + R(case["overhead_s"])
        if effect == "C":
            amount = q[index]
            index += 1
            assert amount > 0
            energy += amount
            assert energy <= R(case["capacity_kwh"])
            time = release + charging(arrival, energy)
            events.append(dict(site=site, effect=effect, charge_kwh=amount,
                               completion_s=time, arrival_kwh=arrival, departure_kwh=energy))
        else:
            start = max(R(case["schedule"]["a"]), release)
            assert start <= R(case["schedule"]["b"])
            time = start + R(case["schedule"]["D"])
            events.append(dict(site=site, effect=effect, charge_kwh=R(0),
                schedule_start_s=start, schedule_completion_s=time, completion_s=time,
                arrival_kwh=arrival, departure_kwh=energy))
        current = site
    drive, consumption = legs[current, case["destination"]]
    terminal = energy - consumption
    assert terminal >= R(case["reserve_kwh"])
    objective = time + drive - R(case["start_time_s"]) + len(sequence) * R(case["lambda_stop_s"])
    return dict(J=objective, Q_total=sum(q, R(0)), H=len(sequence), site_action_tuple=sequence,
                charges=q, events=events, terminal_energy_kwh=terminal, terminal_time_s=time + drive)


def solve(case):
    started = perf_counter()
    legs = selected_legs(case)
    enumeration = list(sequences(case))
    enumeration_seconds = perf_counter() - started
    regimes, sequence_records, contenders = [], [], []
    optimization_started = perf_counter()
    for sequence in enumeration:
        record = dict(sequence=sequence)
        if not any(effect == "S" for _, effect in sequence):
            record["rejection"] = "unsatisfied_hard_schedule"
            sequence_records.append(record)
            continue
        anchors = (case["origin"],) + tuple(site for site, _ in sequence) + (case["destination"],)
        if any((a, b) not in legs for a, b in zip(anchors, anchors[1:])):
            record["rejection"] = "directed_route_unreachable"
            sequence_records.append(record)
            continue
        n = sum(effect == "C" for _, effect in sequence)
        if not n:
            record["rejection"] = "uncharged_origin_to_schedule_consumption_exceeds_initial_energy"
            assert legs[case["origin"], sequence[0][0]][1] > R(case["initial_energy_kwh"])
            sequence_records.append(record)
            continue
        record["regimes"] = 0
        record["strict_feasible_regimes"] = 0
        for assignment in product(range(len(case["charging_segments"])), repeat=2 * n):
            for branch in ("early", "late"):
                A, b, objective = regime_model(case, sequence, legs, assignment, branch)
                primary = exact_lp(objective.coefficients, A, b)
                evidence = dict(sequence=sequence, segments=assignment, schedule_branch=branch,
                                primary_certificate=primary)
                record["regimes"] += 1
                if primary["status"] == "infeasible":
                    evidence["status"] = "closed_regime_infeasible"
                    regimes.append(evidence)
                    continue
                feasibility = strict_face(A, b, n)
                evidence["strict_feasibility_certificate"] = feasibility
                if feasibility["x"][-1] == 0:
                    evidence["status"] = "empty_strict_regime"
                    regimes.append(evidence)
                    continue
                record["strict_feasible_regimes"] += 1
                face = [(objective.coefficients, primary["objective"])]
                attained = strict_face(A, b, n, face)
                evidence["primary_face_certificate"] = attained
                J = primary["objective"] + objective.constant
                if attained["x"][-1] == 0:
                    evidence.update(status="infimum_unattained", J=J)
                    contenders.append(dict(status="infimum_unattained", J=J))
                    regimes.append(evidence)
                    continue
                secondary = exact_lp((R(1),) * n, A, b, face)
                evidence["secondary_certificate"] = secondary
                tie_face = strict_face(A, b, n, face + [((R(1),) * n, secondary["objective"])])
                evidence["tie_face_certificate"] = tie_face
                if tie_face["x"][-1] == 0:
                    # A single closed segment regime can attain primary time
                    # while only approaching its secondary infimum. Preserve
                    # that open face; another regime may attain the same Q.
                    evidence.update(status="primary_attained_secondary_infimum_unattained",
                                    J=J, Q_total=secondary["objective"])
                    contenders.append(dict(status=evidence["status"], J=J,
                        Q_total=secondary["objective"], H=len(sequence), site_action_tuple=sequence))
                    regimes.append(evidence)
                    continue
                witness = original_witness(case, sequence, tie_face["x"][:-1], legs)
                assert witness["J"] == J and witness["Q_total"] == secondary["objective"]
                winner = dict(status="attained_optimum", **witness)
                contenders.append(winner)
                evidence.update(status="attained_optimum", J=J, Q_total=witness["Q_total"])
                regimes.append(evidence)
        sequence_records.append(record)
    assert contenders
    infimum = min(result["J"] for result in contenders)
    executable = [r for r in contenders if r["J"] == infimum and r["status"] == "attained_optimum"]
    winner = min(executable, key=lambda r: (r["Q_total"], r["H"], r["site_action_tuple"], r["charges"]))
    assert not any(r["J"] == infimum and r["status"] == "primary_attained_secondary_infimum_unattained"
                   and r["Q_total"] < winner["Q_total"] for r in contenders), "Global lexicographic non-attainment"
    return dict(result=winner, sequences=sequence_records, regimes=regimes,
        sequence_count=len(enumeration), regime_count=len(regimes),
        strict_feasible_regime_count=sum(r.get("strict_feasible_regimes", 0) for r in sequence_records),
        enumeration_seconds=enumeration_seconds,
        optimization_seconds=perf_counter() - optimization_started,
        total_seconds=perf_counter() - started, legs=legs)
