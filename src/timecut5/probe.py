"""Rational lower cuts with constructive witnesses, contract v2.

This miniature handles fixed-energy cuts and one-dimensional affine input
families. It does not construct general output-energy PWA frontiers, enumerate
routes, implement hierarchy search, or establish the SQ-1..SQ-8 theorem gates.
Seed families are explicit analytic assumptions, not inferred physical routes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction as R
from typing import Callable, Iterable


def exact(value: int | R) -> R:
    """Reject binary64 and bool inputs rather than silently rationalizing them."""
    if isinstance(value, bool) or not isinstance(value, (int, R)):
        raise TypeError("Use int or Fraction for exact quantities")
    return R(value)


class UnattainedError(ValueError):
    """An executable minimum was requested for an open cut."""


@dataclass(frozen=True)
class Interval:
    lo: R
    hi: R
    left_closed: bool = True
    right_closed: bool = True

    def __post_init__(self):
        object.__setattr__(self, "lo", exact(self.lo))
        object.__setattr__(self, "hi", exact(self.hi))
        if self.lo > self.hi or (self.lo == self.hi and not (
                self.left_closed and self.right_closed)):
            raise ValueError("Empty interval")

    def contains(self, value: R) -> bool:
        value = exact(value)
        return ((value > self.lo or value == self.lo and self.left_closed)
                and (value < self.hi or value == self.hi and self.right_closed))

    def intersect(self, other: Interval) -> Interval | None:
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        lc = self.contains(lo) and other.contains(lo)
        rc = self.contains(hi) and other.contains(hi)
        if lo > hi or lo == hi and not (lc and rc):
            return None
        return Interval(lo, hi, lc, rc)

    def affine_infimum(self, slope: R) -> tuple[R, bool]:
        """Return an optimizer in the closure and whether it is in the domain."""
        if slope > 0:
            return self.lo, self.left_closed
        if slope < 0:
            return self.hi, self.right_closed
        return (self.lo + self.hi) / 2, True

    def approach_optimizer(self, slope: R, epsilon: R) -> R:
        point, included = self.affine_infimum(slope)
        if included:
            return point
        # The affine objective gap is strictly below epsilon. This is an
        # analytic witness chosen on demand, never a grid or a charge quantum.
        delta = min((self.hi - self.lo) / 2, epsilon / (2 * abs(slope)))
        return point + delta if slope > 0 else point - delta


@dataclass(frozen=True)
class State:
    anchor: str
    remaining_schedule: int
    stop_count: int

    def __post_init__(self):
        if (type(self.remaining_schedule) is not int or type(self.stop_count) is not int
                or self.remaining_schedule not in (0, 1) or self.stop_count < 0):
            raise ValueError("Invalid discrete state")


@dataclass(frozen=True)
class Event:
    effect: str
    site: str
    arrival_time: R
    departure_time: R
    arrival_energy: R
    departure_energy: R

    def __post_init__(self):
        for name in ("arrival_time", "departure_time", "arrival_energy", "departure_energy"):
            object.__setattr__(self, name, exact(getattr(self, name)))


@dataclass(frozen=True)
class Witness:
    time: R
    energy: R
    rho: R
    pi: tuple[tuple[str, str], ...]
    state: State
    events: tuple[Event, ...] = ()

    def __post_init__(self):
        for name in ("time", "energy", "rho"):
            object.__setattr__(self, name, exact(getattr(self, name)))

    @property
    def charge(self) -> R:
        return self.energy + self.rho


@dataclass(frozen=True)
class Cut:
    tau: R
    chi: bool
    energy: R
    rho: R
    pi: tuple[tuple[str, str], ...]
    state: State
    _approach: Callable[[R], Witness] = field(repr=False, compare=False)

    def __post_init__(self):
        for name in ("tau", "energy", "rho"):
            object.__setattr__(self, name, exact(getattr(self, name)))
        if type(self.chi) is not bool:
            raise TypeError("Attainment must be boolean")
        if len(self.pi) != self.state.stop_count:
            raise ValueError("Prefix length must equal stop count")

    def approach(self, epsilon: R) -> Witness:
        epsilon = exact(epsilon)
        if epsilon <= 0:
            raise ValueError("Approach budget must be strictly positive")
        witness = self._approach(epsilon)
        if (witness.energy, witness.rho, witness.pi, witness.state) != (
                self.energy, self.rho, self.pi, self.state):
            raise AssertionError("Witness context mismatch")
        if not self.tau <= witness.time < self.tau + epsilon:
            raise AssertionError("Witness failed its exact approach budget")
        if self.chi != (witness.time == self.tau):
            raise AssertionError("Witness contradicts boundary attainment")
        return witness

    def minimum(self) -> Witness:
        if not self.chi:
            raise UnattainedError("The infimum is not an executable minimum")
        return self.approach(R(1))

    def realize_le(self, budget: R) -> Witness:
        """Reconstruct a real member at or before budget, if one exists."""
        budget = exact(budget)
        if budget < self.tau or budget == self.tau and not self.chi:
            raise UnattainedError("No executable member meets this time budget")
        return self.minimum() if self.chi else self.approach(budget - self.tau)


@dataclass(frozen=True)
class AffineFamily:
    """Explicit analytic seed: {tau(E)} if closed, (tau(E),tau(E)+1] if open.

    The upper endpoint of an open seed is immaterial to its lower cut but
    witnesses really belong to this stated family. Seed events mark the
    supplied prefix as assumed; they do not claim a road/charging replay.
    """
    domain: Interval
    slope: R
    intercept: R
    chi: bool
    rho: R
    pi: tuple[tuple[str, str], ...]
    state: State

    def __post_init__(self):
        for name in ("slope", "intercept", "rho"):
            object.__setattr__(self, name, exact(getattr(self, name)))
        if type(self.chi) is not bool:
            raise TypeError("Attainment must be boolean")
        if len(self.pi) != self.state.stop_count:
            raise ValueError("Prefix length must equal stop count")

    def at(self, energy: R) -> Cut:
        energy = exact(energy)
        if not self.domain.contains(energy):
            raise ValueError("Energy is outside the executable seed domain")
        tau = self.slope * energy + self.intercept

        def approach(epsilon):
            t = tau if self.chi else tau + min(R(1), epsilon / 2)
            return Witness(t, energy, self.rho, self.pi, self.state,
                           (Event("analytic_seed", self.state.anchor, t, t, energy, energy),))

        return Cut(tau, self.chi, energy, self.rho, self.pi, self.state, approach)


def cut_le(a: Cut, b: Cut) -> bool:
    return a.tau < b.tau or a.tau == b.tau and (a.chi or not b.chi)


def dominates(a: Cut, b: Cut) -> bool:
    """Same-(v,E,r,k) continuation preorder; no cross-energy deletion."""
    return (a.state == b.state and a.energy == b.energy and cut_le(a, b)
            and a.rho <= b.rho and (a.rho != b.rho or a.pi <= b.pi))


def reduce_cuts(cuts: Iterable[Cut]) -> tuple[Cut, ...]:
    """Stable finite point antichain, retaining the first equivalent witness."""
    result: list[Cut] = []
    for candidate in cuts:
        if any(dominates(old, candidate) for old in result):
            continue
        result = [old for old in result if not dominates(candidate, old)]
        result.append(candidate)
    return tuple(result)


def continuation_equivalent(a: Iterable[Cut], b: Iterable[Cut]) -> bool:
    """Mutual coverage under the sufficient preorder, not attained-record equality.

    This is not a decision procedure for every possible semantic continuation
    equivalence; it certifies equivalence when this same-state preorder covers
    both finite point families.
    """
    a, b = tuple(a), tuple(b)
    return (all(any(dominates(x, y) for x in a) for y in b)
            and all(any(dominates(y, x) for y in b) for x in a))


def _event(w: Witness, effect: str, site: str, time: R, energy: R,
           rho: R, state: State) -> Witness:
    pi = w.pi if effect == "D" else w.pi + ((site, effect),)
    return Witness(time, energy, rho, pi, state, w.events + (
        Event(effect, site, w.time, time, w.energy, energy),))


def drive(cut: Cut, anchor: str, duration: R, consumption: R,
          floor: R = R(0)) -> Cut | None:
    duration, consumption, floor = map(exact, (duration, consumption, floor))
    if duration < 0 or consumption < 0:
        raise ValueError("Negative drive duration or consumption")
    energy, rho = cut.energy - consumption, cut.rho + consumption
    if energy < floor:
        return None
    state = State(anchor, cut.state.remaining_schedule, cut.state.stop_count)

    def approach(epsilon):
        w = cut.approach(epsilon)
        return _event(w, "D", anchor, w.time + duration, energy, rho, state)

    return Cut(cut.tau + duration, cut.chi, energy, rho, cut.pi, state, approach)


def _scheduled(cut: Cut, site: str, a: R, b: R, duration: R,
               overhead: R, charge_duration: R | None = None,
               output_energy: R | None = None) -> Cut | None:
    a, b, duration, overhead = map(exact, (a, b, duration, overhead))
    if cut.state.remaining_schedule != 1:
        raise ValueError("Schedule has already been satisfied")
    if duration < 0 or overhead <= 0:
        raise ValueError("Require nonnegative service duration and positive overhead")
    latest = b - overhead
    # Clip the executable input family BEFORE propagating its boundary.
    if a > b or cut.tau > latest or cut.tau == latest and not cut.chi:
        return None
    combined = charge_duration is not None
    m = max(duration, charge_duration) if combined else duration
    plateau, offset = a + duration, overhead + m
    tau = max(plateau, cut.tau + offset)
    chi = cut.chi or cut.tau < plateau - offset
    energy = output_energy if combined else cut.energy
    effect = "CS" if combined else "S"
    pi = cut.pi + ((site, effect),)
    state = State(site, 0, cut.state.stop_count + 1)

    def approach(epsilon):
        if cut.chi:
            w = cut.minimum()
        else:
            budget = min(epsilon, latest - cut.tau)
            if chi:
                budget = min(budget, plateau - offset - cut.tau)
            w = cut.approach(budget)
        assert max(a, w.time + overhead) <= b
        return _event(w, effect, site, max(plateau, w.time + offset),
                      energy, cut.rho, state)

    return Cut(tau, chi, energy, cut.rho, pi, state, approach)


def schedule(cut: Cut, site: str, a: R, b: R, duration: R, overhead: R) -> Cut | None:
    return _scheduled(cut, site, a, b, duration, overhead)


@dataclass(frozen=True)
class ChargingCurve:
    """Continuous integral with positive affine slopes on closed segments."""
    segments: tuple[tuple[R, R, R, R], ...]

    def __post_init__(self):
        rows = tuple(tuple(map(exact, row)) for row in self.segments)
        if not rows:
            raise ValueError("An empty charging primitive is invalid")
        previous = None
        for lo, hi, slope, intercept in rows:
            if lo < 0 or lo >= hi or slope <= 0:
                raise ValueError("Invalid charging segment")
            if previous is not None:
                plo, phi, ps, pc = previous
                if lo != phi or slope * lo + intercept != ps * lo + pc:
                    raise ValueError("Charging primitive must be continuous and contiguous")
            previous = lo, hi, slope, intercept
        if rows[0][0] != 0 or rows[0][3] != 0:
            raise ValueError("Require F(0)=0 and domain starting at zero")
        object.__setattr__(self, "segments", rows)

    def at(self, energy: R) -> R:
        energy = exact(energy)
        for lo, hi, slope, intercept in self.segments:
            if lo <= energy <= hi:
                return slope * energy + intercept
        raise ValueError("Energy outside charging primitive")


FROZEN_CURVE = ChargingCurve(((0, 30, 36, 0), (30, 48, 60, -720),
                              (48, 60, 120, -3600)))


def charge_point(cut: Cut, output_energy: R, curve: ChargingCurve,
                 overhead: R, site: str) -> Cut:
    output_energy, overhead = map(exact, (output_energy, overhead))
    if output_energy <= cut.energy or overhead <= 0:
        raise ValueError("C requires strictly positive charge and overhead")
    extra = overhead + curve.at(output_energy) - curve.at(cut.energy)
    state = State(site, cut.state.remaining_schedule, cut.state.stop_count + 1)

    def approach(epsilon):
        w = cut.approach(epsilon)
        return _event(w, "C", site, w.time + extra, output_energy, cut.rho, state)

    return Cut(cut.tau + extra, cut.chi, output_energy, cut.rho,
               cut.pi + ((site, "C"),), state, approach)


def combined_point(cut: Cut, output_energy: R, curve: ChargingCurve,
                   site: str, a: R, b: R, duration: R, overhead: R) -> Cut | None:
    output_energy = exact(output_energy)
    if output_energy <= cut.energy:
        raise ValueError("CS requires strictly positive charge")
    charge_duration = curve.at(output_energy) - curve.at(cut.energy)
    return _scheduled(cut, site, a, b, duration, overhead, charge_duration, output_energy)


def charge_at(families: Iterable[AffineFamily], output_energy: R,
              curve: ChargingCurve, overhead: R, site: str) -> Cut | None:
    """Exact C cut at ONE Ed, optimizing finite affine input regimes.

    Families must be pieces of the same discrete prefix and conservation
    coordinate. Closed charging-integral breakpoints can be duplicated;
    strict Ea<Ed is never closed during minimization or witness replay.
    """
    families = tuple(families)
    output_energy, overhead = map(exact, (output_energy, overhead))
    fd = curve.at(output_energy)
    if overhead <= 0:
        raise ValueError("Require positive overhead")
    if not families or output_energy == 0:
        return None
    first = families[0]
    context = first.state, first.rho, first.pi
    if any((f.state, f.rho, f.pi) != context for f in families):
        raise ValueError("Charge each discrete-prefix family separately")
    regimes = []
    for family in families:
        for lo, hi, slope, intercept in curve.segments:
            domain = family.domain.intersect(Interval(lo, hi))
            domain = domain.intersect(Interval(0, output_energy, True, False)) if domain else None
            if domain is None:
                continue
            gs = family.slope - slope
            point, included = domain.affine_infimum(gs)
            tau = overhead + fd + gs * point + family.intercept - intercept
            regimes.append((tau, included and family.chi, family, domain, gs))
    if not regimes:
        return None
    tau = min(r[0] for r in regimes)
    minimizers = [r for r in regimes if r[0] == tau]
    chosen = next((r for r in minimizers if r[1]), minimizers[0])
    _, chi, family, domain, slope = chosen
    state = State(site, first.state.remaining_schedule, first.state.stop_count + 1)

    def approach(epsilon):
        energy = domain.approach_optimizer(slope, epsilon / 2)
        incoming = family.at(energy)
        return charge_point(incoming, output_energy, curve, overhead, site).approach(epsilon / 2)

    return Cut(tau, chi, output_energy, first.rho, first.pi + ((site, "C"),), state, approach)


@dataclass(frozen=True)
class TerminalResult:
    status: str
    primary_infimum: R | None = None
    secondary_infimum: R | None = None
    unattained_component: str | None = None
    key: tuple | None = None
    witness: Witness | None = None


def terminal(families: Iterable[AffineFamily], destination: str, reserve: R,
             start_time: R = R(0), stop_penalty: R = R(0)) -> TerminalResult:
    """Sequential attained-face optimization for a finite affine terminal union.

    If J is not attained, Q is deliberately absent. If J is attained but its
    best Q is not, the result has no executable key or witness. This does not
    manufacture a full lexicographic limit tuple for an open primary face.
    """
    reserve, start_time, stop_penalty = map(exact, (reserve, start_time, stop_penalty))
    if stop_penalty < 0:
        raise ValueError("Negative stop penalty")
    feasible = []
    for f in families:
        if f.state.anchor != destination or f.state.remaining_schedule != 0:
            continue
        if reserve > f.domain.hi:
            continue
        domain = f.domain.intersect(Interval(reserve, max(reserve, f.domain.hi)))
        if domain is None:
            continue
        e, included = domain.affine_infimum(f.slope)
        j = f.slope * e + f.intercept - start_time + stop_penalty * f.state.stop_count
        feasible.append((j, f, domain, e, included and f.chi))
    if not feasible:
        return TerminalResult("infeasible")
    j = min(row[0] for row in feasible)
    primary = [row for row in feasible if row[0] == j and row[4]]
    if not primary:
        return TerminalResult("infimum_unattained", j, unattained_component="J")
    secondary = []
    for _, f, domain, e, _ in primary:
        energy = domain.lo if f.slope == 0 else e
        included = domain.contains(energy)
        secondary.append((energy + f.rho, f, energy, included))
    q = min(row[0] for row in secondary)
    winners = [row for row in secondary if row[0] == q and row[3]]
    if not winners:
        return TerminalResult("infimum_unattained", j, q, "Q")
    _, f, energy, _ = min(winners, key=lambda row: (row[1].state.stop_count, row[1].pi))
    witness = f.at(energy).minimum()
    return TerminalResult("attained_optimum", j, q, key=(j, q, f.state.stop_count, f.pi),
                          witness=witness)
