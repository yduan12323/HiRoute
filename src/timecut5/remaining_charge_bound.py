"""Conditional exact charging-time inequalities; no search integration.

The caller must independently certify the supplied lower bounds and physical
model. This module does not construct or authenticate road potentials, inspect
native arithmetic history, certify a charging curve, or enable any pruning.
In particular, the immediate-finish screen is not an automatic certificate for
the different multi-leg use described here.
"""
from __future__ import annotations

from fractions import Fraction as R
from typing import Iterable

from .probe import Interval, State
from .pwa import CutPiece


def _exact(value, name, *, positive=False, nonnegative=False):
    if type(value) is not R:
        raise TypeError(f"{name} must be an exact Fraction")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _clock_charge_infimum(piece, threshold, alpha):
    """Infimum on an interval, never a claim of endpoint attainability."""
    lo, hi = piece.domain.lo, piece.domain.hi
    points = (lo, hi, threshold) if lo <= threshold <= hi else (lo, hi)
    return min(piece.slope * energy + piece.intercept +
               alpha * max(R(0), threshold - energy) for energy in points)


def remaining_charge_primary_lower_bound(
        pieces: Iterable[CutPiece], *, remaining_energy_lower: R,
        remaining_time_lower: R, terminal_reserve: R,
        min_charge_seconds_per_kwh: R, start_time: R, stop_penalty: R) -> R:
    """Return a conditional, infimum-based primary bound for one physical state.

    Required caller-established assumptions:
    * ``remaining_energy_lower`` bounds TOTAL future selected-leg consumption
      to the destination, including multi-leg suffixes and native rounding.
    * ``remaining_time_lower`` similarly bounds total future driving time.
    * Every legal future charge takes at least ``min_charge_seconds_per_kwh``
      times its energy. This positive global minimum of integral slopes is the
      reciprocal of maximum power in kWh/second, not power in kW.
    * No energy is regenerated. Driving and charging do not overlap. Every
      represented executable prefix has clock >= its piece's affine clock.
      Terminal energy is >= ``terminal_reserve`` and stop penalty is >=0.

    With T=terminal_reserve+remaining_energy_lower and current stop count k,
    the returned value is

        min_{piece,e} [tau_piece(e)+alpha*max(0,T-e)]
        + remaining_time_lower - start_time + stop_penalty*k.

    This accounts for past stop penalties only. It adds no future overhead,
    stop penalty, scheduled duration or waiting, so CS overlap remains relaxed.
    Combine this with another complete lower bound by max, not addition. Even
    after certificate admission, only a STRICT comparison above a verified
    primary upper bound can discard equal-J secondary/prefix competitors.

    Exact closure endpoints and the sole hinge suffice for each piece. Open
    energy/clock faces retain their infimum meaning; no witness is constructed
    or claimed. Runtime is O(number of pieces) exact arithmetic operations.
    Inputs must be Fraction objects, including zero. Syntactic/state validation
    below is not proof that a potential, piece callback or curve is authentic.
    """
    remaining_energy_lower = _exact(remaining_energy_lower, "remaining_energy_lower", nonnegative=True)
    remaining_time_lower = _exact(remaining_time_lower, "remaining_time_lower", nonnegative=True)
    terminal_reserve = _exact(terminal_reserve, "terminal_reserve", nonnegative=True)
    alpha = _exact(min_charge_seconds_per_kwh, "min_charge_seconds_per_kwh", positive=True)
    start_time = _exact(start_time, "start_time")
    stop_penalty = _exact(stop_penalty, "stop_penalty", nonnegative=True)
    pieces = tuple(pieces)
    if not pieces:
        raise ValueError("A nonempty same-state frontier is required")
    state = None
    for piece in pieces:
        if not isinstance(piece, CutPiece) or type(piece.state) is not State:
            raise TypeError("Expected a CutPiece with a physical State")
        if state is None:
            state = piece.state
        elif piece.state != state:
            raise ValueError("No cross-state remaining-charge bound")
        if type(piece.domain) is not Interval:
            raise TypeError("Expected an exact Interval")
        lo = _exact(piece.domain.lo, "energy lower endpoint", nonnegative=True)
        hi = _exact(piece.domain.hi, "energy upper endpoint", nonnegative=True)
        if (type(piece.domain.left_closed) is not bool or
                type(piece.domain.right_closed) is not bool or lo > hi or
                lo == hi and not (piece.domain.left_closed and piece.domain.right_closed)):
            raise ValueError("Invalid energy interval")
        _exact(piece.slope, "piece slope")
        _exact(piece.intercept, "piece intercept")
    threshold = terminal_reserve + remaining_energy_lower
    clock = min(_clock_charge_infimum(piece, threshold, alpha) for piece in pieces)
    return clock + remaining_time_lower - start_time + stop_penalty * state.stop_count


def complete_route_primary_lower_bound(
        *, total_stops: int, initial_energy: R, origin_energy_lower: R,
        origin_time_lower: R, terminal_reserve: R,
        min_charge_seconds_per_kwh: R, stop_overhead: R, stop_penalty: R) -> R:
    """Conditional whole-route bound; does not change Hmax or prune a layer.

    In addition to the certified-potential/charging assumptions above, each
    semantic stop must pay ``stop_overhead`` before any charge/service and
    separately from travel and all other stops. CS may overlap service/waiting
    with charge; this formula adds no service/waiting duration. Query start
    cancels from elapsed time, so it is intentionally not an input.

    For H=total_stops the result is B0+H*(stop_overhead+stop_penalty), where
    B0=origin_time_lower+alpha*max(0,reserve+origin_energy_lower-initial_energy).
    If future integration compares this with a verified U, equality must be
    retained, the declared Hmax/domain must remain recorded, and a cutoff
    inconsistent with the independently replayed seed's H must fail closed.
    This pure helper neither verifies U nor constructs a depth certificate.
    """
    if type(total_stops) is not int:
        raise TypeError("total_stops must be an integer")
    if total_stops < 0:
        raise ValueError("total_stops must be nonnegative")
    initial_energy = _exact(initial_energy, "initial_energy", nonnegative=True)
    origin_energy_lower = _exact(origin_energy_lower, "origin_energy_lower", nonnegative=True)
    origin_time_lower = _exact(origin_time_lower, "origin_time_lower", nonnegative=True)
    terminal_reserve = _exact(terminal_reserve, "terminal_reserve", nonnegative=True)
    alpha = _exact(min_charge_seconds_per_kwh, "min_charge_seconds_per_kwh", positive=True)
    stop_overhead = _exact(stop_overhead, "stop_overhead", positive=True)
    stop_penalty = _exact(stop_penalty, "stop_penalty", nonnegative=True)
    charge = max(R(0), terminal_reserve + origin_energy_lower - initial_energy)
    return origin_time_lower + alpha * charge + total_stops * (stop_overhead + stop_penalty)
