"""Experimental exact charge/count relaxation; no live search integration.

Admission here checks a mathematical curve snapshot, not the physical query,
road potentials, native arithmetic history, or frontier provenance. The caller
must establish those external contracts. No function realizes a witness,
decides pruning, changes Hmax, or claims that an infimum is attained.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as R
from typing import Iterable

from .probe import ChargingCurve, Interval, State
from .pwa import CutPiece


def _exact(value, name, *, nonnegative=False, positive=False):
    if type(value) is not R:
        raise TypeError(f"{name} must be an exact Fraction")
    if (nonnegative and value < 0) or (positive and value <= 0):
        raise ValueError(f"Invalid {name}")
    return value


def _count(value, name):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _physical_interval(minimum_energy, capacity):
    _exact(minimum_energy, "minimum_energy", nonnegative=True)
    _exact(capacity, "capacity", positive=True)
    if minimum_energy > capacity:
        raise ValueError("minimum_energy exceeds capacity")


def _segments_convex(segments, minimum_energy, capacity):
    """Validate exact physical rows and check convexity on the usable interval."""
    if type(segments) is not tuple or not segments:
        raise TypeError("A nonempty exact segment tuple is required")
    previous = None
    active_slopes = []
    for row in segments:
        if type(row) is not tuple or len(row) != 4:
            raise TypeError("Expected four-value exact segment tuples")
        for value in row:
            _exact(value, "charging segment quantity")
        lo, hi, slope, intercept = row
        if lo < 0 or lo >= hi or slope <= 0:
            raise ValueError("Invalid charging segment")
        if previous is None:
            if lo != 0 or intercept != 0:
                raise ValueError("Require charging domain starting at zero and F(0)=0")
        else:
            _, end, old_slope, old_intercept = previous
            if end != lo or old_slope * lo + old_intercept != slope * lo + intercept:
                raise ValueError("Charging primitive must be continuous and contiguous")
        if lo < capacity and hi > minimum_energy:
            active_slopes.append(slope)
        previous = row
    if segments[-1][1] < capacity:
        raise ValueError("Charging primitive does not cover usable capacity")
    return all(a <= b for a, b in zip(active_slopes, active_slopes[1:]))


@dataclass(frozen=True)
class SharedConvexCurveAdmissionV1:
    """Immutable mathematical snapshot, never an authenticated runtime receipt.

    An active value verifies positive continuous PWA rows and nondecreasing
    slopes on [minimum_energy, capacity]. The caller must independently verify
    that this is the shared charging primitive for every future charge.
    """
    status: str
    minimum_energy: R
    capacity: R
    segments: tuple | None
    reason: str | None = None

    def __post_init__(self):
        _physical_interval(self.minimum_energy, self.capacity)
        if self.status == "active":
            if self.reason is not None:
                raise ValueError("Active curve admission cannot have a disabled reason")
            if not _segments_convex(self.segments, self.minimum_energy, self.capacity):
                raise ValueError("Active curve admission requires convexity")
        elif (self.status != "unsupported" or self.segments is not None or
              self.reason not in ("no_charging_curve", "nonconvex_charging_curve")):
            raise ValueError("Unsupported curve admission requires a known reason and no rows")


def admit_shared_convex_curve(curve, *, minimum_energy: R,
                             capacity: R) -> SharedConvexCurveAdmissionV1:
    """Explicitly check the proposed shared curve, without authenticating it.

    A missing or nonconvex curve is unsupported, not a proof of infeasibility.
    Malformed quantities/types raise rather than becoming a disabled result.
    Convexity need only hold on the usable energy interval. A degenerate usable
    interval minimum_energy == capacity is allowed, with zero charge capacity.
    """
    _physical_interval(minimum_energy, capacity)
    if curve is None:
        return SharedConvexCurveAdmissionV1("unsupported", minimum_energy,
            capacity, None, "no_charging_curve")
    if type(curve) is not ChargingCurve:
        raise TypeError("Exact shared ChargingCurve or None required")
    if not _segments_convex(curve.segments, minimum_energy, capacity):
        return SharedConvexCurveAdmissionV1("unsupported", minimum_energy,
            capacity, None, "nonconvex_charging_curve")
    return SharedConvexCurveAdmissionV1("active", minimum_energy, capacity, curve.segments)


@dataclass(frozen=True)
class ChargeCountBoundResultV1:
    """Conditional primary infimum; unsupported and empty relaxation differ."""
    status: str
    primary_lower_bound: R | None
    original_hmax: int
    reason: str | None = None

    def __post_init__(self):
        _count(self.original_hmax, "original_hmax")
        if self.status == "active":
            _exact(self.primary_lower_bound, "primary_lower_bound")
            if self.reason is not None:
                raise ValueError("Active bound cannot have a disabled reason")
        elif self.status == "unsupported":
            if (self.primary_lower_bound is not None or self.reason not in
                    ("no_charging_curve", "nonconvex_charging_curve")):
                raise ValueError("Unsupported bound requires a known reason and no value")
        elif self.status == "infeasible":
            if (self.primary_lower_bound is not None or self.reason not in
                    ("no_legal_future_count", "no_feasible_future_count")):
                raise ValueError("Empty relaxation requires a known reason and no value")
        else:
            raise ValueError("Unknown charge/count bound status")


def _curve_at(segments, energy):
    for lo, hi, slope, intercept in segments:
        if lo <= energy <= hi:
            return slope * energy + intercept
    raise ValueError("Energy outside the admitted charging primitive")


def _piece_count_infimum(piece, *, threshold, h, admission, delta,
                         floor_value, breakpoints):
    floor, capacity = admission.minimum_energy, admission.capacity
    lower = threshold - h * (capacity - floor)
    if lower > piece.domain.hi:
        return None
    domain = piece.domain.intersect(Interval(lower, piece.domain.hi))
    if domain is None:
        return None
    points = {domain.lo, domain.hi}
    if domain.lo <= threshold <= domain.hi:
        points.add(threshold)
    values = []
    for energy in points:
        value = piece.slope * energy + piece.intercept + h * delta
        if h:
            deficit = max(R(0), threshold - energy)
            value += h * (_curve_at(admission.segments, floor + deficit / h) - floor_value)
        values.append(value)
    if h:
        # Stored curve increments avoid a segment scan for every breakpoint.
        for x, increment in breakpoints:
            energy = threshold - h * (x - floor)
            if domain.lo <= energy <= domain.hi:
                values.append(piece.slope * energy + piece.intercept + h * (delta + increment))
    return min(values)


def charge_count_primary_lower_bound(
        pieces: Iterable[CutPiece], *, admission: SharedConvexCurveAdmissionV1,
        remaining_energy_lower: R, remaining_time_lower: R,
        terminal_reserve: R, start_time: R, stop_overhead: R,
        stop_penalty: R, original_hmax: int,
        minimum_future_stops: int = 0) -> ChargeCountBoundResultV1:
    """Bound trusted same-state frontiers using all relaxed future stop counts.

    Required external contracts, not established by this pure helper:
    * admission describes the actual shared charging primitive and usable energy
      interval for every future charge of this exact physical query.
    * Suffix energy/time inputs certify TOTAL future selected-leg consumption
      and driving time, including native rounding/history and multi-leg resets.
      No unsupported free energy is introduced; driving and charging are disjoint.
    * Every represented executable prefix clock is at least its affine piece.
      Each future semantic stop pays overhead separately before charge/service,
      and adds stop_penalty to the primary objective. Charge may overlap service.
    * original_hmax is the unchanged declared stop domain. If nonzero,
      minimum_future_stops is a separately justified continuation condition
      (for example one when conditioning on a next stop), not a heuristic.

    For q(e)=max(0,reserve+suffix_energy-e), enumerate every integer future
    count h from max(pending_schedule,minimum_future_stops) to Hmax-k. Treat
    every stop as charge-capable, including zero charge, as a relaxation.
    At h>0 require q<=h*(capacity-floor) and add
        h*(F(floor+q/h)-F(floor)) + h*(overhead+penalty).
    At h=0 allow only q=0. Jointly minimize with each affine prefix clock,
    then add suffix driving time-start_time+past_stop_penalty*k.

    Empty flagged intersections are skipped BEFORE taking closure infima.
    Rational endpoints, the deficit hinge, and transformed F breakpoints give
    the exact infimum, including open energy/clock faces. No witness or
    attainment is returned. Combine with other COMPLETE bounds by max, not
    addition; any later pruning must retain equality and use strict > against
    an independently verified feasible primary upper bound.

    unsupported means no admitted convex curve; infeasible means this admitted
    relaxation has no continuation under the caller's certified assumptions.
    Neither status is a runtime/source/provenance certificate. Work is bounded
    by O(pieces * allowed_counts * curve_segments), with no graph or routing.
    """
    if type(admission) is not SharedConvexCurveAdmissionV1:
        raise TypeError("Explicit SharedConvexCurveAdmissionV1 required")
    admission.__post_init__()
    for name, value in (("remaining_energy_lower", remaining_energy_lower),
                        ("remaining_time_lower", remaining_time_lower),
                        ("terminal_reserve", terminal_reserve),
                        ("stop_penalty", stop_penalty)):
        _exact(value, name, nonnegative=True)
    _exact(start_time, "start_time")
    _exact(stop_overhead, "stop_overhead", positive=True)
    _count(original_hmax, "original_hmax")
    _count(minimum_future_stops, "minimum_future_stops")
    if not admission.minimum_energy <= terminal_reserve <= admission.capacity:
        raise ValueError("Terminal reserve outside the usable energy interval")
    pieces = tuple(pieces)
    if not pieces:
        raise ValueError("A nonempty same-state frontier is required")
    state = None
    for piece in pieces:
        if type(piece) is not CutPiece or type(piece.state) is not State:
            raise TypeError("Exact CutPiece with physical State required")
        if state is None:
            state = piece.state
        elif state != piece.state:
            raise ValueError("No cross-state charge/count bound")
        if type(piece.domain) is not Interval:
            raise TypeError("Exact Interval required")
        lo = _exact(piece.domain.lo, "energy lower endpoint")
        hi = _exact(piece.domain.hi, "energy upper endpoint")
        if (type(piece.domain.left_closed) is not bool or
                type(piece.domain.right_closed) is not bool or lo > hi or
                lo == hi and not (piece.domain.left_closed and piece.domain.right_closed)):
            raise ValueError("Invalid energy interval")
        if lo < admission.minimum_energy or hi > admission.capacity:
            raise ValueError("Frontier energy outside the usable interval")
        _exact(piece.slope, "piece slope")
        _exact(piece.intercept, "piece intercept")
    if (type(state.anchor) is not str or type(state.remaining_schedule) is not int or
            state.remaining_schedule not in (0, 1)):
        raise ValueError("Invalid physical state")
    _count(state.stop_count, "state stop_count")
    if state.stop_count > original_hmax:
        raise ValueError("State exceeds the original declared Hmax")
    if admission.status != "active":
        return ChargeCountBoundResultV1("unsupported", None, original_hmax, admission.reason)
    first = max(state.remaining_schedule, minimum_future_stops)
    last = original_hmax - state.stop_count
    if first > last:
        return ChargeCountBoundResultV1("infeasible", None, original_hmax,
                                       "no_legal_future_count")
    floor, capacity = admission.minimum_energy, admission.capacity
    floor_value = _curve_at(admission.segments, floor)
    breakpoint_values = {floor: R(0),
        capacity: _curve_at(admission.segments, capacity) - floor_value}
    for lo, hi, slope, intercept in admission.segments:
        for energy in (lo, hi):
            if floor <= energy <= capacity:
                breakpoint_values[energy] = slope * energy + intercept - floor_value
    breakpoints = tuple(breakpoint_values.items())
    threshold = terminal_reserve + remaining_energy_lower
    best = None
    for piece in pieces:
        for h in range(first, last + 1):
            value = _piece_count_infimum(piece, threshold=threshold, h=h,
                admission=admission, delta=stop_overhead + stop_penalty,
                floor_value=floor_value, breakpoints=breakpoints)
            if value is not None and (best is None or value < best):
                best = value
    if best is None:
        return ChargeCountBoundResultV1("infeasible", None, original_hmax,
                                       "no_feasible_future_count")
    return ChargeCountBoundResultV1("active", best + remaining_time_lower -
        start_time + state.stop_count * stop_penalty, original_hmax)
