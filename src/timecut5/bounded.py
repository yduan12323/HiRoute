"""Diagnostic H_ref-bounded physical FLAT propagation, not global production search.

Input schema is the original B21 hand-case JSON. The explicit stop bound is
part of the comparison domain. Infeasibility here never proves unbounded
infeasibility. No REF, historical frontier, or hierarchy code is imported.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction as R
import heapq
from typing import Mapping

from .probe import ChargingCurve, Cut, Event, Interval, State, TerminalResult, Witness, terminal
from .pwa import CutPiece, charge_pwa, combined_pwa, drive_pwa, reduce_frontier, schedule_pwa


def _rational(value) -> R:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Use exact integer, Fraction, or rational string in the physical schema")
    return R(value)


@dataclass(frozen=True)
class Leg:
    time: R
    energy: R
    path: tuple[str, ...]
    edge_ids: tuple[str, ...] = ()


class Problem:
    """Validated exact physical hand-case and deterministic fastest route table."""
    def __init__(self, case: Mapping):
        self.case = case
        self.origin, self.destination = case["origin"], case["destination"]
        self.start = _rational(case["start_time_s"])
        self.initial = _rational(case["initial_energy_kwh"])
        self.capacity = _rational(case["capacity_kwh"])
        self.floor = _rational(case["minimum_energy_kwh"])
        self.reserve = _rational(case["reserve_kwh"])
        self.overhead = _rational(case["overhead_s"])
        self.penalty = _rational(case["lambda_stop_s"])
        self.rate = _rational(case["consumption_kwh_per_m"])
        self.bound = case["H_ref"]
        self.sites = {str(site): tuple(effects) for site, effects in case["sites"].items()}
        self.schedule = tuple(_rational(case["schedule"][key]) for key in ("a", "b", "D")) if case.get("schedule") else None
        self.initial_remaining = case.get("initial_remaining_schedule", int(self.schedule is not None))
        rows = tuple(tuple(_rational(v) for v in row) for row in case["charging_segments"])
        self.curve = ChargingCurve(rows) if rows else None
        charging_available = any(set(effects) & {"C", "CS"} for effects in self.sites.values())
        if (type(self.bound) is not int or self.bound < 0 or self.overhead <= 0
                or self.penalty < 0 or self.rate < 0 or self.floor < 0 or self.capacity <= 0
                or not self.floor <= self.initial <= self.capacity
                or not self.floor <= self.reserve <= self.capacity
                or self.curve is not None and self.curve.segments[-1][1] != self.capacity
                or charging_available and self.curve is None):
            raise ValueError("Invalid bounded physical query")
        if (type(self.initial_remaining) is not int or self.initial_remaining not in (0, 1)
                or self.initial_remaining and self.schedule is None):
            raise ValueError("Invalid initial schedule state")
        if self.schedule and self.schedule[2] < 0:
            raise ValueError("Negative scheduled duration")
        if any(not set(effects) <= {"C", "S", "CS"} for effects in self.sites.values()):
            raise ValueError("Unknown Site effect")
        self.adjacency = defaultdict(list)
        nodes = {self.origin, self.destination, *self.sites}
        seen_edge_ids = set()
        for index, edge in enumerate(case["edges"]):
            a, b = edge["source"], edge["target"]
            time, length = _rational(edge["time_s"]), _rational(edge["length_m"])
            if time <= 0 or length <= 0:
                raise ValueError("Road edges require positive time and physical length")
            nodes.update((a, b))
            edge_id = edge.get("edge_id", edge.get("id", f"input:{index:08d}"))
            if not isinstance(edge_id, str) or edge_id in seen_edge_ids:
                raise ValueError("Road edge IDs must be unique strings")
            seen_edge_ids.add(edge_id)
            self.adjacency[a].append((b, time, length, edge_id))
        self.legs = {}
        # Positive road times permit exact Dijkstra. Among equal-time routes,
        # node path, then edge-ID path, breaks ties independently of length.
        for source in sorted(nodes):
            queue = [(R(0), (source,), (), R(0), source)]
            best = {source: (R(0), (source,), ())}
            while queue:
                time, path, edge_ids, length, node = heapq.heappop(queue)
                if best.get(node) != (time, path, edge_ids):
                    continue
                self.legs[source, node] = Leg(time, length * self.rate, path, edge_ids)
                for target, dt, dl, edge_id in self.adjacency[node]:
                    candidate = time + dt, path + (target,), edge_ids + (edge_id,)
                    if target not in best or candidate < best[target]:
                        best[target] = candidate
                        heapq.heappush(queue, (*candidate, length + dl, target))

    def initial_piece(self) -> CutPiece:
        state = State(self.origin, self.initial_remaining, 0)
        witness = Witness(self.start, self.initial, -self.initial, (), state,
                          (Event("initial", self.origin, self.start, self.start,
                                 self.initial, self.initial),))
        cut = Cut(self.start, True, self.initial, -self.initial, (), state, lambda eps: witness)
        return CutPiece(Interval(self.initial, self.initial), 0, self.start, True,
                        -self.initial, (), state, lambda energy: cut)

    def advance(self, pieces: tuple[CutPiece, ...], site: str, effect: str) -> tuple[CutPiece, ...]:
        if not pieces:
            return ()
        # Carried-forward physical rule: destination arrival is terminal,
        # never a semantic stop. This does not ban transit through z inside
        # a selected concrete road leg whose stop anchor is elsewhere.
        if site == self.destination or pieces[0].state.anchor == self.destination:
            return ()
        if effect not in self.sites.get(site, ()):
            raise ValueError("Effect is not statically available at this Site")
        if effect in ("S", "CS") and (not self.schedule or pieces[0].state.remaining_schedule != 1):
            return ()
        leg = self.legs.get((pieces[0].state.anchor, site))
        if leg is None:
            return ()
        incoming = drive_pwa(pieces, site, leg.time, leg.energy, self.floor)
        if effect == "C":
            return charge_pwa(incoming, self.curve, self.overhead, site)
        a, b, duration = self.schedule
        if effect == "S":
            return schedule_pwa(incoming, site, a, b, duration, self.overhead)
        return combined_pwa(incoming, self.curve, site, a, b, duration, self.overhead)

    def finish(self, pieces: tuple[CutPiece, ...]) -> tuple[CutPiece, ...]:
        if not pieces or pieces[0].state.remaining_schedule:
            return ()
        if pieces[0].state.anchor == self.destination:
            result = []
            for piece in pieces:
                if piece.domain.hi < self.reserve:
                    continue
                domain = piece.domain.intersect(Interval(self.reserve, max(self.reserve, piece.domain.hi)))
                if domain is not None:
                    result.append(replace(piece, domain=domain))
            return tuple(result)
        leg = self.legs.get((pieces[0].state.anchor, self.destination))
        return drive_pwa(pieces, self.destination, leg.time, leg.energy, self.reserve) if leg else ()


def evaluate_sequence(case: Mapping, sequence: tuple[tuple[str, str], ...]) -> TerminalResult:
    """Optimize continuous decisions for one explicit original-fixture sequence."""
    problem = Problem(case)
    if len(sequence) > problem.bound:
        raise ValueError("Sequence exceeds the explicitly supplied diagnostic bound")
    pieces = (problem.initial_piece(),)
    for site, effect in sequence:
        pieces = problem.advance(pieces, site, effect)
    return terminal(problem.finish(pieces), problem.destination, problem.reserve,
                    problem.start, problem.penalty)


@dataclass(frozen=True)
class BoundedResult:
    result: TerminalResult
    H_ref: int
    dominance: bool
    attempted_extensions: int
    feasible_prefixes: int
    terminal_piece_count: int
    max_layer_piece_count: int
    scope: str = "bounded_H_ref_diagnostic"

    def canonical(self) -> dict:
        """Shared REF/FLAT interchange contract; no fabricated open-face key."""
        result = self.result
        if result.status == "attained_optimum":
            j, q, count, pi = result.key
            payload = dict(status="attained_optimum", J=j, Q_total=q, H=count,
                           site_action_tuple=pi, lex_key=result.key,
                           charges=tuple(e.departure_energy - e.arrival_energy
                                         for e in result.witness.events if e.effect in ("C", "CS")),
                           witness_replayed=True)
        elif result.status == "infimum_unattained" and result.unattained_component == "J":
            payload = dict(status="primary_unattained", primary_infimum=result.primary_infimum)
        elif result.status == "infimum_unattained" and result.unattained_component == "Q":
            payload = dict(status="secondary_unattained", J=result.primary_infimum,
                           secondary_infimum=result.secondary_infimum)
        elif result.status == "infeasible":
            payload = dict(status="infeasible_within_H_ref")
        else:
            raise AssertionError("Unrecognized exact terminal status")
        return dict(scope=self.scope, H_ref=self.H_ref, result=payload)


def _groups(pieces):
    groups = defaultdict(list)
    for p in pieces:
        groups[p.state, p.rho, p.pi].append(p)
    return tuple(tuple(group) for group in groups.values())


def solve_bounded(case: Mapping, dominance: bool = True) -> BoundedResult:
    """Exhaust every legal next action through H_ref; optional safe reduction.

    Repeated Sites and self legs remain allowed. Only unreachable, energy or
    schedule-infeasible extensions are removed; there is no heuristic cap.
    TerminalResult.status is meaningful only inside this returned bound/scope.
    """
    problem = Problem(case)
    layer = ((problem.initial_piece(),),)
    terminals = []
    attempted = 0
    feasible = 1
    maximum = 1
    for depth in range(problem.bound + 1):
        for group in layer:
            terminals.extend(problem.finish(group))
        if depth == problem.bound:
            break
        next_pieces = []
        for group in layer:
            if group[0].state.anchor == problem.destination:
                continue
            for site, effects in sorted(problem.sites.items()):
                if site == problem.destination:
                    continue
                for effect in sorted(set(effects)):
                    if effect in ("S", "CS") and not group[0].state.remaining_schedule:
                        continue
                    attempted += 1
                    output = problem.advance(group, site, effect)
                    if output:
                        feasible += 1
                        next_pieces.extend(output)
        if dominance:
            by_state = defaultdict(list)
            for p in next_pieces:
                by_state[p.state].append(p)
            next_pieces = [p for group in by_state.values() for p in reduce_frontier(group)]
        maximum = max(maximum, len(next_pieces))
        layer = _groups(next_pieces)
        if not layer:
            break
    result = terminal(terminals, problem.destination, problem.reserve, problem.start, problem.penalty)
    if result.witness is not None:
        replay_witness(case, result.witness)
    return BoundedResult(result, problem.bound, dominance, attempted, feasible, len(terminals), maximum)


def replay_witness(case: Mapping, witness: Witness) -> tuple:
    """Independent event replay against the original charging integral and graph.

    This checks the returned physical plan without reading PWA/FM internals.
    It is a witness verifier, not an independent optimization reference.
    """
    # Incumbents affect pruning: legality checks must survive Python -O.
    def _require(condition, message):
        if not condition:
            raise AssertionError(message)

    problem = Problem(case)
    time, energy, anchor = problem.start, problem.initial, problem.origin
    remaining, total_charge, pi = problem.initial_remaining, R(0), ()
    events = witness.events
    expected_initial = Event("initial", anchor, time, time, energy, energy)
    if not events or events[0] != expected_initial:
        raise AssertionError("Witness does not begin at the physical query state")
    # The physical plan has exactly one selected fastest leg before each
    # semantic stop and one selected terminal leg. Consecutive drive events
    # would allow an unmodeled route-shaping via point and can manufacture a
    # false incumbent whose energy differs from the selected direct leg.
    if problem.origin == problem.destination:
        _require(len(events) == 1 and not witness.pi, "Terminal origin has no outgoing plan")
    else:
        _require(len(events) == 2 * len(witness.pi) + 2, "Noncanonical physical leg/stop structure")
        for index, event in enumerate(events[1:], 1):
            _require((event.effect == "D") == (index % 2 == 1), "Drives must alternate with semantic stops")

    def integral(a, b):
        _require(problem.curve is not None, 'Witness violates the physical query or event equations')
        return sum((max(R(0), min(b, hi) - max(a, lo)) * slope
                    for lo, hi, slope, _ in problem.curve.segments), R(0))

    for event in events[1:]:
        _require((event.arrival_time, event.arrival_energy) == (time, energy), 'Witness violates the physical query or event equations')
        _require(anchor != problem.destination, "No semantic continuation from a terminal anchor")
        if event.effect == "D":
            leg = problem.legs[anchor, event.site]
            time += leg.time
            energy -= leg.energy
            anchor = event.site
        else:
            _require(anchor != problem.destination, "Destination is not a semantic stop")
            _require(event.site == anchor and event.effect in problem.sites[anchor], 'Witness violates the physical query or event equations')
            release = time + problem.overhead
            charge_done = schedule_done = release
            if event.effect in ("C", "CS"):
                q = event.departure_energy - energy
                _require(q > 0 and event.departure_energy <= problem.capacity, 'Witness violates the physical query or event equations')
                charge_done += integral(energy, event.departure_energy)
                total_charge += q
                energy = event.departure_energy
            if event.effect in ("S", "CS"):
                _require(remaining == 1 and problem.schedule is not None, 'Witness violates the physical query or event equations')
                a, b, duration = problem.schedule
                start = max(a, release)
                _require(start <= b, 'Witness violates the physical query or event equations')
                schedule_done = start + duration
                remaining = 0
            time = max(charge_done, schedule_done)
            pi += ((anchor, event.effect),)
        _require(problem.floor <= energy <= problem.capacity, 'Witness violates the physical query or event equations')
        _require((event.departure_time, event.departure_energy) == (time, energy), 'Witness violates the physical query or event equations')
    _require(len(pi) <= problem.bound, "Witness exceeds the explicit diagnostic stop bound")
    _require(anchor == problem.destination and remaining == 0 and energy >= problem.reserve, 'Witness violates the physical query or event equations')
    _require((witness.time, witness.energy, witness.charge, witness.pi, witness.state) == (
        time, energy, total_charge, pi, State(anchor, remaining, len(pi))), 'Witness violates the physical query or event equations')
    return time - problem.start + problem.penalty * len(pi), total_charge, len(pi), pi
