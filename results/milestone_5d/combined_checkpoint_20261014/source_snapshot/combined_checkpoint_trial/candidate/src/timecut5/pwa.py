"""Finite rational PWA cut operators via exact strict budget projection.

See docs/MILESTONE_5_TIME_CUT_PWA_DESIGN_V2.md. This is an operator prototype,
not a route solver or independent REF. A projected time is a budget and is
always lifted through a constrained predecessor before becoming a witness.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction as R
from itertools import combinations
from typing import Callable, Iterable

from . import provenance as prov

from .probe import (
    AffineFamily, ChargingCurve, Cut, Interval, State, Witness, _event,
    drive, exact, reduce_cuts,
)


@dataclass(frozen=True)
class Row:
    """coefficients dot variables <= rhs; strict=True changes <= to <."""
    coefficients: tuple[R, ...]
    rhs: R
    strict: bool = False

    def __post_init__(self):
        object.__setattr__(self, "coefficients", tuple(map(exact, self.coefficients)))
        object.__setattr__(self, "rhs", exact(self.rhs))
        if type(self.strict) is not bool:
            raise TypeError("Strictness must be boolean")

    def holds(self, point: tuple[R, ...]) -> bool:
        if len(point) != len(self.coefficients):
            raise ValueError("Wrong point dimension")
        value = sum((a * exact(x) for a, x in zip(self.coefficients, point)), R(0))
        return value < self.rhs if self.strict else value <= self.rhs


def _normalize(rows: Iterable[Row]) -> tuple[Row, ...] | None:
    """Positive normalization, exact duplicate removal, constant contradictions."""
    result = {}
    dimension = None
    for row in rows:
        if dimension is not None and len(row.coefficients) != dimension:
            raise ValueError("Inconsistent row dimensions")
        dimension = len(row.coefficients)
        first = next((a for a in row.coefficients if a), None)
        if first is None:
            if row.rhs < 0 or row.rhs == 0 and row.strict:
                return None
            continue
        scale = abs(first)
        coefficients = tuple(a / scale for a in row.coefficients)
        rhs = row.rhs / scale
        key = coefficients, rhs
        result[key] = result.get(key, False) or row.strict
    return tuple(Row(c, b, strict) for (c, b), strict in sorted(result.items()))


def eliminate(rows: Iterable[Row], variable: int) -> tuple[Row, ...] | None:
    """Existential strict Fourier–Motzkin step, with no approximation/caps."""
    rows = _normalize(rows)
    if rows is None:
        return None
    positive, negative, zero = [], [], []
    for row in rows:
        coefficient = row.coefficients[variable]
        (positive if coefficient > 0 else negative if coefficient < 0 else zero).append(row)
    output = list(zero)
    for upper in positive:
        for lower in negative:
            up, down = upper.coefficients[variable], -lower.coefficients[variable]
            output.append(Row(
                tuple(a / up + b / down for a, b in zip(upper.coefficients, lower.coefficients)),
                upper.rhs / up + lower.rhs / down,
                upper.strict or lower.strict,
            ))
    return _normalize(output)


def _choose(bounds: Iterable[tuple[R, R, bool]]) -> R:
    """Choose from exact a*x <= b rows, preserving tied strict endpoints."""
    lower = upper = None
    ls = us = False
    for a, b, strict in bounds:
        if a == 0:
            if b < 0 or b == 0 and strict:
                raise ValueError("Infeasible zero row in witness fiber")
            continue
        value = b / a
        if a < 0:
            if lower is None or value > lower:
                lower, ls = value, strict
            elif value == lower:
                ls = ls or strict
        else:
            if upper is None or value < upper:
                upper, us = value, strict
            elif value == upper:
                us = us or strict
    if lower is not None and upper is not None:
        if lower > upper or lower == upper and (ls or us):
            raise ValueError("Empty strict witness fiber")
        return (lower + upper) / 2
    if lower is not None:
        return lower + 1 if ls else lower
    if upper is not None:
        return upper - 1 if us else upper
    return R(0)


@dataclass(frozen=True)
class Projection:
    original: tuple[Row, ...]
    rows: tuple[Row, ...]
    history: tuple[tuple[int, tuple[Row, ...]], ...]

    @classmethod
    def build(cls, rows: Iterable[Row], variables: Iterable[int]) -> Projection | None:
        original = _normalize(rows)
        if original is None:
            return None
        current, history = original, []
        variables = tuple(variables)
        if len(set(variables)) != len(variables):
            raise ValueError("Cannot eliminate a variable twice")
        for variable in variables:
            history.append((variable, current))
            current = eliminate(current, variable)
            if current is None:
                return None
        return cls(original, current, tuple(history))

    def lift(self, fixed: dict[int, R]) -> tuple[R, ...]:
        """Back-substitute a projected point and verify every original row."""
        values = {i: exact(value) for i, value in fixed.items()}
        for variable, rows in reversed(self.history):
            if variable in values:
                raise ValueError("An eliminated variable was already fixed")
            bounds = []
            for row in rows:
                residual = row.rhs
                for i, coefficient in enumerate(row.coefficients):
                    if i == variable or not coefficient:
                        continue
                    if i not in values:
                        raise ValueError("Missing retained coordinate during lifting")
                    residual -= coefficient * values[i]
                bounds.append((row.coefficients[variable], residual, row.strict))
            values[variable] = _choose(bounds)
        dimension = len(self.original[0].coefficients) if self.original else len(values)
        point = tuple(values[i] for i in range(dimension))
        if not all(row.holds(point) for row in self.original):
            raise AssertionError("Lifted point violates its original strict system")
        return point


@dataclass(frozen=True)
class CutPiece:
    domain: Interval
    slope: R
    intercept: R
    chi: bool
    rho: R
    pi: tuple[tuple[str, str], ...]
    state: State
    _point: Callable[[R], Cut] = field(repr=False, compare=False)
    _family: prov.FamilyRef | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        for name in ("slope", "intercept", "rho"):
            object.__setattr__(self, name, exact(getattr(self, name)))
        if type(self.chi) is not bool:
            raise TypeError("Attainment must be boolean")
        if len(self.pi) != self.state.stop_count:
            raise ValueError("Prefix length must equal stop count")

    @classmethod
    def from_affine(cls, family: AffineFamily) -> CutPiece:
        return cls(family.domain, family.slope, family.intercept, family.chi,
                   family.rho, family.pi, family.state, family.at)

    def at(self, energy: R) -> Cut:
        if self._family is not None:
            self._family.check_binding(self)
        energy = exact(energy)
        if not self.domain.contains(energy):
            raise ValueError("Energy outside represented predecessor subfamily")
        cut = self._point(energy)
        expected = (self.slope * energy + self.intercept, self.chi, energy,
                    self.rho, self.pi, self.state)
        actual = cut.tau, cut.chi, cut.energy, cut.rho, cut.pi, cut.state
        if expected != actual:
            raise AssertionError("Point witness disagrees with the PWA piece")
        if self._family is not None:
            base = cut
            def observed(epsilon):
                witness = base.approach(epsilon)
                prov.observe_witness(self, witness, epsilon, energy)
                return witness
            return replace(cut, _approach=observed)
        return cut


def _cells(domain: Interval, knots: Iterable[R]) -> tuple[Interval, ...]:
    order = sorted({domain.lo, domain.hi} | {e for e in knots if domain.lo < e < domain.hi})
    cells = []
    for i, e in enumerate(order):
        if domain.contains(e):
            cells.append(Interval(e, e))
        if i + 1 < len(order):
            cells.append(Interval(e, order[i + 1], False, False))
    return tuple(cells)


def _point(domain: Interval) -> R:
    return (domain.lo + domain.hi) / 2


def _arrangement(pieces: tuple[CutPiece, ...]) -> tuple[Interval, ...]:
    if not pieces:
        return ()
    knots = {p.domain.lo for p in pieces} | {p.domain.hi for p in pieces}
    for a, b in combinations(pieces, 2):
        slope = a.slope - b.slope
        if slope:
            e = (b.intercept - a.intercept) / slope
            if max(a.domain.lo, b.domain.lo) <= e <= min(a.domain.hi, b.domain.hi):
                knots.add(e)
    return _cells(Interval(min(knots), max(knots)), knots)


def _same_family(pieces: tuple[CutPiece, ...]):
    if pieces:
        context = pieces[0].state, pieces[0].rho, pieces[0].pi
        if any((p.state, p.rho, p.pi) != context for p in pieces):
            raise ValueError("Operate on each discrete-prefix family separately")


def lower_envelope(pieces: Iterable[CutPiece]) -> tuple[CutPiece, ...]:
    """Exact union of one family's cuts, OR-ing attainment at tied minima."""
    pieces = tuple(pieces)
    _same_family(pieces)
    result = []
    for cell in _arrangement(pieces):
        e = _point(cell)
        candidates = [p for p in pieces if p.domain.contains(e)]
        if not candidates:
            continue
        minimum = min(p.slope * e + p.intercept for p in candidates)
        tied = [p for p in candidates if p.slope * e + p.intercept == minimum]
        chosen = next((p for p in tied if p.chi), tied[0])
        result.append(prov.select(chosen, pieces, cell, next(i for i, p in enumerate(pieces) if p is chosen), "union"))
    prov.batch("union", pieces, result)
    return tuple(result)


def reduce_frontier(pieces: Iterable[CutPiece]) -> tuple[CutPiece, ...]:
    """Same-state exact energy arrangement antichain; no scalar time merge."""
    pieces = tuple(pieces)
    if pieces and any(p.state != pieces[0].state for p in pieces):
        raise ValueError("No cross-state reduction")
    result = []
    for cell in _arrangement(pieces):
        e = _point(cell)
        candidates = [p for p in pieces if p.domain.contains(e)]
        cuts = [p.at(e) for p in candidates]
        kept = reduce_cuts(cuts)
        for p, cut in zip(candidates, cuts):
            if any(cut is winner for winner in kept):
                result.append(prov.select(p, pieces, cell, next(i for i, candidate in enumerate(pieces) if candidate is p), "reduction"))
    prov.batch("reduction", pieces, result)
    return tuple(result)


def _interval_rows(domain: Interval, variable: int) -> tuple[Row, Row]:
    lo, hi = [R(0)] * 4, [R(0)] * 4
    lo[variable], hi[variable] = R(-1), R(1)
    return (Row(tuple(lo), -domain.lo, not domain.left_closed),
            Row(tuple(hi), domain.hi, not domain.right_closed))


def _extract(projection: Projection, source: CutPiece, effect: str, site: str,
             overhead: R, curve: ChargingCurve | None = None,
             a: R = R(0), b: R = R(0), duration: R = R(0),
             in_segment=None, out_segment=None) -> tuple[CutPiece, ...]:
    lower = upper = None
    lc = rc = True
    lines = []
    for row in projection.rows:
        x, t, energy_coefficient, budget_coefficient = row.coefficients
        if x or t or budget_coefficient > 0:
            raise AssertionError("Projection is not a budget epigraph")
        if budget_coefficient < 0:
            lines.append((-energy_coefficient / budget_coefficient,
                          row.rhs / budget_coefficient, row.strict))
        elif energy_coefficient:
            bound = row.rhs / energy_coefficient
            if energy_coefficient < 0:
                if lower is None or bound > lower:
                    lower, lc = bound, not row.strict
                elif bound == lower:
                    lc = lc and not row.strict
            else:
                if upper is None or bound < upper:
                    upper, rc = bound, not row.strict
                elif bound == upper:
                    rc = rc and not row.strict
        elif not row.holds((R(0),) * 4):
            return ()
    if lower is None or upper is None or not lines:
        raise AssertionError("Expected bounded energy domain and finite lower-time cut")
    if lower > upper or lower == upper and not (lc and rc):
        return ()
    domain = Interval(lower, upper, lc, rc)
    knots = set()
    for (m, c, _), (n, d, _) in combinations(lines, 2):
        if m != n:
            knots.add((d - c) / (m - n))
    pi = source.pi + ((site, effect),)
    state = State(site, source.state.remaining_schedule if effect == "C" else 0,
                  source.state.stop_count + 1)
    result = []
    for cell in _cells(domain, knots):
        e = _point(cell)
        tau = max(m * e + c for m, c, _ in lines)
        active = [(m, c, strict) for m, c, strict in lines if m * e + c == tau]
        slope, intercept, _ = active[0]
        chi = not any(strict for _, _, strict in active)

        def at(energy, slope=slope, intercept=intercept, chi=chi):
            value = slope * energy + intercept

            def approach(epsilon):
                budget = value if chi else value + epsilon / 2
                ea, time_budget, ed, _ = projection.lift({2: energy, 3: budget})
                incoming = source.at(ea).realize_le(time_budget)
                if effect in ("C", "CS"):
                    if not ea < ed:
                        raise AssertionError("Projected witness violates strict charging")
                    charge_done = incoming.time + overhead + curve.at(ed) - curve.at(ea)
                if effect in ("S", "CS"):
                    start = max(a, incoming.time + overhead)
                    if start > b:
                        raise AssertionError("Projected witness violates latest schedule start")
                    schedule_done = start + duration
                time = (charge_done if effect == "C" else schedule_done if effect == "S"
                        else max(charge_done, schedule_done))
                if time > budget:
                    raise AssertionError("Real action exceeded projected output budget")
                return _event(incoming, effect, site, time, ed, source.rho, state)

            return Cut(value, chi, energy, source.rho, pi, state, approach)

        output = CutPiece(cell, slope, intercept, chi, source.rho, pi, state, at)
        result.append(prov.bind(output, "stop", (source,), effect=effect, site=site,
                                h=overhead, a=a, b=b, D=duration,
                                curve=curve.segments if curve else [],
                                in_segment=in_segment, out_segment=out_segment))
    return tuple(result)


def _stop(pieces: Iterable[CutPiece], effect: str, site: str, overhead: R,
          curve: ChargingCurve | None = None, a: R = R(0), b: R = R(0),
          duration: R = R(0)) -> tuple[CutPiece, ...]:
    pieces = tuple(pieces)
    _same_family(pieces)
    overhead, a, b, duration = map(exact, (overhead, a, b, duration))
    if overhead <= 0 or duration < 0:
        raise ValueError("Require positive overhead and nonnegative service duration")
    if effect in ("S", "CS"):
        if any(p.state.remaining_schedule != 1 for p in pieces):
            raise ValueError("Schedule has already been satisfied")
        if a > b:
            prov.batch("stop", pieces, (), effect=effect, site=site, h=overhead,
                       a=a, b=b, D=duration, curve=curve.segments if curve else [])
            return ()
    result = []
    for source in pieces:
        seed = [*_interval_rows(source.domain, 0),
                Row((source.slope, -1, 0, 0), -source.intercept, not source.chi)]
        if effect in ("S", "CS"):
            seed.extend((Row((0, 1, 0, 0), b - overhead),
                         Row((0, 0, 0, -1), -a - duration),
                         Row((0, 1, 0, -1), -overhead - duration)))
        if effect == "S":
            rows = seed + [Row((1, 0, -1, 0), 0), Row((-1, 0, 1, 0), 0)]
            projected = Projection.build(rows, (1, 0))
            if projected is not None:
                result.extend(_extract(projected, source, effect, site, overhead,
                                       a=a, b=b, duration=duration))
        else:
            for il, ih, im, ic in curve.segments:
                for ol, oh, om, oc in curve.segments:
                    rows = seed + [*_interval_rows(Interval(il, ih), 0),
                                   *_interval_rows(Interval(ol, oh), 2),
                                   Row((1, 0, -1, 0), 0, True),
                                   Row((-im, 1, om, -1), -overhead - oc + ic)]
                    projected = Projection.build(rows, (1, 0))
                    if projected is not None:
                        result.extend(_extract(projected, source, effect, site, overhead,
                                               curve, a, b, duration,
                                               (il, ih, im, ic), (ol, oh, om, oc)))
    prov.batch("stop", pieces, result, effect=effect, site=site, h=overhead,
               a=a, b=b, D=duration, curve=curve.segments if curve else [])
    return lower_envelope(result)


def charge_pwa(pieces: Iterable[CutPiece], curve: ChargingCurve,
               overhead: R, site: str) -> tuple[CutPiece, ...]:
    return _stop(pieces, "C", site, overhead, curve)


def combined_pwa(pieces: Iterable[CutPiece], curve: ChargingCurve, site: str,
                 a: R, b: R, duration: R, overhead: R) -> tuple[CutPiece, ...]:
    return _stop(pieces, "CS", site, overhead, curve, a, b, duration)


def schedule_pwa(pieces: Iterable[CutPiece], site: str, a: R, b: R,
                 duration: R, overhead: R) -> tuple[CutPiece, ...]:
    return _stop(pieces, "S", site, overhead, a=a, b=b, duration=duration)


def drive_pwa(pieces: Iterable[CutPiece], anchor: str, duration: R,
              consumption: R, floor: R = R(0)) -> tuple[CutPiece, ...]:
    pieces = tuple(pieces)
    duration, consumption, floor = map(exact, (duration, consumption, floor))
    if duration < 0 or consumption < 0:
        raise ValueError("Negative drive duration or consumption")
    result = []
    for source in pieces:
        old = source.domain
        shifted = Interval(old.lo - consumption, old.hi - consumption,
                           old.left_closed, old.right_closed)
        if shifted.hi < floor:
            continue
        domain = shifted.intersect(Interval(floor, max(floor, shifted.hi)))
        if domain is None:
            continue
        state = State(anchor, source.state.remaining_schedule, source.state.stop_count)
        output = CutPiece(
            domain, source.slope, source.intercept + source.slope * consumption + duration,
            source.chi, source.rho + consumption, source.pi, state,
            lambda energy, source=source: drive(source.at(energy + consumption), anchor,
                                                duration, consumption, floor),
        )
        result.append(prov.bind(output, "drive", (source,), site=anchor,
                                duration=duration, consumption=consumption, floor=floor))
    prov.batch("drive", pieces, result, site=anchor, duration=duration,
               consumption=consumption, floor=floor)
    return tuple(result)
