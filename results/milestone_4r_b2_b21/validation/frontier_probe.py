"""Exact rational frontier operator probe for the frozen T7 representation.

It intentionally follows earliest-time merge with Q tied only among earliest
prefixes. A failing composition is evidence against that frozen contract, not
authorization to patch it. No LP optimizer or REF module is used here.
"""
from dataclasses import asdict, dataclass, replace
from fractions import Fraction as R
from itertools import combinations


@dataclass(frozen=True)
class Piece:
    piece_id: str
    anchor: str
    remaining_schedule: int
    stop_count: int
    low: R
    high: R
    left_open: bool
    right_open: bool
    time_slope: R
    time_intercept: R
    charge_slope: R
    charge_intercept: R
    attained: bool
    predecessor_piece_id: str
    predecessor_energy_rule: str
    site_id: str
    effect: str
    schedule_branch: str
    witness: tuple

    def contains(self, energy):
        return ((energy > self.low if self.left_open else energy >= self.low)
                and (energy < self.high if self.right_open else energy <= self.high))

    def key(self, energy):
        return (self.time_slope * energy + self.time_intercept,
                self.charge_slope * energy + self.charge_intercept,
                self.stop_count, self.witness)


def merge(pieces):
    """Exact affine lower envelope including singleton endpoints and Q ties."""
    knots = {piece.low for piece in pieces} | {piece.high for piece in pieces}
    for p, q in combinations(pieces, 2):
        low, high = max(p.low, q.low), min(p.high, q.high)
        if low > high:
            continue
        slope, intercept = p.time_slope - q.time_slope, p.time_intercept - q.time_intercept
        if slope:
            energy = -intercept / slope
            if low <= energy <= high:
                knots.add(energy)
        elif not intercept:
            slope = p.charge_slope - q.charge_slope
            if slope:
                energy = (q.charge_intercept - p.charge_intercept) / slope
                if low <= energy <= high:
                    knots.add(energy)
    order = sorted(knots)
    result = []
    for i, energy in enumerate(order):
        candidates = [p for p in pieces if p.contains(energy)]
        if candidates:
            p = min(candidates, key=lambda p: p.key(energy))
            result.append(replace(p, piece_id=f"merge-point-{i}-{p.piece_id}",
                predecessor_piece_id=p.piece_id, predecessor_energy_rule="identity",
                low=energy, high=energy, left_open=False, right_open=False))
        if i + 1 < len(order):
            low, high = energy, order[i + 1]
            # This is an analytic arrangement cell, not an energy grid: all
            # affine intersections and domain boundaries are already included.
            interior = (low + high) / 2
            candidates = [p for p in pieces if p.contains(interior)]
            if candidates:
                p = min(candidates, key=lambda p: p.key(interior))
                result.append(replace(p, piece_id=f"merge-interval-{i}-{p.piece_id}",
                    predecessor_piece_id=p.piece_id, predecessor_energy_rule="identity",
                    low=low, high=high, left_open=True, right_open=True))
    return result


def clip(pieces, floor, capacity):
    result = []
    for p in pieces:
        low, high = max(p.low, floor), min(p.high, capacity)
        if low > high:
            continue
        left_open = p.left_open if low == p.low else False
        right_open = p.right_open if high == p.high else False
        if low == high and (left_open or right_open):
            continue
        result.append(replace(p, low=low, high=high, left_open=left_open, right_open=right_open))
    return result


def drive(pieces, anchor, time, consumption, floor, capacity):
    shifted = [replace(p, piece_id="drive-" + p.piece_id, anchor=anchor,
        low=p.low - consumption, high=p.high - consumption,
        time_intercept=p.time_intercept + p.time_slope * consumption + time,
        charge_intercept=p.charge_intercept + p.charge_slope * consumption,
        predecessor_piece_id=p.piece_id, predecessor_energy_rule=f"E+{consumption}") for p in pieces]
    return clip(shifted, floor, capacity)


def schedule(pieces, site, a, b, duration, overhead):
    result = []
    for p in pieces:
        cuts = {p.low, p.high}
        if p.time_slope:
            crossing = (a - overhead - p.time_intercept) / p.time_slope
            deadline = (b - overhead - p.time_intercept) / p.time_slope
            for energy in (crossing, deadline):
                if p.low < energy < p.high:
                    cuts.add(energy)
        boundaries = sorted(cuts)
        cells = [(e, e, False, False) for e in boundaries if p.contains(e)]
        cells.extend((low, high, True, True) for low, high in zip(boundaries, boundaries[1:]))
        for index, (low, high, left_open, right_open) in enumerate(cells):
            interior = (low + high) / 2
            release = p.time_slope * interior + p.time_intercept + overhead
            if max(a, release) > b:
                continue
            early = release <= a
            result.append(replace(p, piece_id=f"S-{index}-" + p.piece_id,
                low=low, high=high, left_open=left_open, right_open=right_open,
                remaining_schedule=0, stop_count=p.stop_count + 1,
                time_slope=R(0) if early else p.time_slope,
                time_intercept=a + duration if early else p.time_intercept + overhead + duration,
                site_id=site, effect="S", schedule_branch="early" if early else "late",
                predecessor_piece_id=p.piece_id, predecessor_energy_rule="identity",
                witness=p.witness + ((site, "S"),)))
    return result


def prefix_frontier(case, branch):
    """Construct the exact two-C frontier through a strict prefix minimum.

    Arrival at the second charger is x in [0, capacity-consumption]. The
    input time is T+h+F(x+consumption)-F(initial_after_first_drive).
    Its time-minus-F(x) slope is strictly positive on each exact interval.
    Therefore the strict-prefix optimizer is attained at x=0 for every E>0.
    """
    first = case["edges"][0 if branch == "4r:node/1" else 2]
    second = case["edges"][1 if branch == "4r:node/1" else 3]
    capacity = R(case["capacity_kwh"])
    consumption = R(second["length_m"]) * R(case["consumption_kwh_per_m"])
    first_arrival = R(case["initial_energy_kwh"]) - R(first["length_m"]) * R(case["consumption_kwh_per_m"])
    segments = [tuple(map(R, row)) for row in case["charging_segments"]]

    def F(energy):
        for low, high, slope, intercept in segments:
            if low <= energy <= high:
                return slope * energy + intercept
        raise ValueError("Energy outside frozen charging primitive")

    arrival_breakpoints = {R(0), capacity - consumption}
    for low, high, _, _ in segments:
        for energy in (low, high, low - consumption, high - consumption):
            if R(0) < energy < capacity - consumption:
                arrival_breakpoints.add(energy)
    arrival_order = sorted(arrival_breakpoints)
    input_trace = []
    for low, high in zip(arrival_order, arrival_order[1:]):
        x = (low + high) / 2
        slope_in = next(slope for a, b, slope, _ in segments if a < x + consumption < b)
        slope_F = next(slope for a, b, slope, _ in segments if a < x < b)
        assert slope_in - slope_F > 0
        input_trace.append(dict(low=low, high=high, time_minus_F_slope=slope_in - slope_F,
                                optimizer_arrival_energy=R(0), optimizer_attained=True))
    intercept = R(first["time_s"]) + R(second["time_s"]) + 2 * R(case["overhead_s"]) + F(consumption) - F(first_arrival)
    initial_charge = consumption - first_arrival
    result = []
    for index, (low, high, slope, constant) in enumerate(segments):
        result.append(Piece(f"C-{branch}-{index}", "4r:node/3", 1, 2,
            low, high, low == 0, False, slope, intercept + constant,
            R(1), initial_charge, True, f"arrival-{branch}-x=0", "constant 0",
            "4r:node/3", "C", "absent", ((branch, "C"), ("4r:node/3", "C"))))
    return result, input_trace


def finish(case, pieces):
    arrival = drive(pieces, "4r:node/4", R(9000), R(40), R(0), R(60))
    after_S = schedule(arrival, "4r:node/4", R(case["schedule"]["a"]), R(case["schedule"]["b"]),
                       R(case["schedule"]["D"]), R(case["overhead_s"]))
    terminal = drive(after_S, case["destination"], R(450), R(2), R(case["reserve_kwh"]), R(60))
    candidates = [(p, p.low) for p in terminal if p.contains(p.low)]
    p, energy = min(candidates, key=lambda pair: (
        pair[0].key(pair[1])[0] + pair[0].stop_count * R(case["lambda_stop_s"]),
        *pair[0].key(pair[1])[1:]))
    key = p.key(energy)
    return dict(status="attained_optimum", J=key[0] + p.stop_count * R(case["lambda_stop_s"]),
        Q_total=key[1], H=p.stop_count, site_action_tuple=p.witness, terminal_energy_kwh=energy), after_S, terminal


def run(case):
    A, trace_A = prefix_frontier(case, "4r:node/1")
    B, trace_B = prefix_frontier(case, "4r:node/2")
    earliest_merge = merge(A + B)
    actual, after_S, terminal = finish(case, earliest_merge)
    complete_A, schedule_A, _ = finish(case, A)
    complete_B, schedule_B, _ = finish(case, B)
    retained_alternative_merge = merge(schedule_A + schedule_B)
    expected = min((complete_A, complete_B), key=lambda r: (r["J"], r["Q_total"], r["H"], r["site_action_tuple"]))
    energy = R(48)
    a = next(p for p in A if p.contains(energy))
    b = next(p for p in B if p.contains(energy))
    time_A, charge_A, _, _ = a.key(energy)
    time_B, charge_B, _, _ = b.key(energy)
    g_A = time_A + 2 * R(case["lambda_stop_s"])
    g_B = time_B + 2 * R(case["lambda_stop_s"])
    assert time_A <= time_B and g_A < g_B
    dominance = dict(anchor="4r:node/3", remaining_schedule=1, stop_count=2, energy_A=energy,
        energy_B=energy, time_A=time_A, time_B=time_B, g_A=g_A, g_B=g_B,
        Q_A=charge_A, Q_B=charge_B, time_relation="A < B", energy_relation="A = B",
        strict_primary_cost_relation="g_A < g_B", frozen_rule_authorizes_deletion=True,
        D_off_point_label_result=expected, D_on_point_label_result=complete_A,
        primary_tie_after_wait=complete_A["J"] == complete_B["J"],
        secondary_tie_lost=complete_A["Q_total"] > complete_B["Q_total"])
    return dict(earliest_frontier_result=actual, retain_alternatives_result=expected,
        primary_equal=actual["J"] == expected["J"], charge_gap=actual["Q_total"] - expected["Q_total"],
        dominance_witness=dominance, strict_charge_input_traces=[trace_A, trace_B],
        pieces=dict(branch_A=[asdict(p) for p in A], branch_B=[asdict(p) for p in B],
            earliest_merge=[asdict(p) for p in earliest_merge], after_schedule=[asdict(p) for p in after_S],
            terminal=[asdict(p) for p in terminal], alternative_schedule_merge=[asdict(p) for p in retained_alternative_merge]))
