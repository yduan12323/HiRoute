"""Data-only affine cut pieces over exact domains; no solver or family reduction."""
from __future__ import annotations
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable
from .interval import Interval
from .scalar import exact

@dataclass(frozen=True)
class PwaStepWitness:
    effect: str
    site: str
    input_energy: Fraction
    input_time: Fraction
    output_energy: Fraction
    output_time: Fraction
    parameters: tuple
    predecessor: object | None = None


@dataclass(frozen=True)
class AffineCutPiece:
    domain: Interval
    slope: Fraction
    intercept: Fraction
    attained: bool
    rho: Fraction = Fraction(0)
    prefix: tuple[tuple[str, str], ...] = ()
    state_key: tuple[object, ...] = ()
    witness_lifter: Callable[[Fraction, Fraction], object] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.domain, Interval):
            raise TypeError("domain must be Interval")
        for name in ("slope", "intercept", "rho"):
            object.__setattr__(self, name, exact(getattr(self, name), name))
        if type(self.attained) is not bool:
            raise TypeError("attained must be bool")
        object.__setattr__(self, "prefix", tuple(tuple(x) for x in self.prefix))
        object.__setattr__(self, "state_key", tuple(self.state_key))

    def cut_time_at(self, energy) -> Fraction:
        energy = exact(energy, "energy")
        if not self.domain.contains(energy):
            raise ValueError("Energy outside represented PWA subfamily")
        return self.slope * energy + self.intercept

    def infimum(self) -> tuple[Fraction, bool, Fraction]:
        energy, endpoint_attained = self.domain.affine_infimum(self.slope)
        return (self.slope * energy + self.intercept,
                self.attained and endpoint_attained, energy)


def drive_piece(piece: AffineCutPiece, anchor: str, duration, consumption, floor=0):
    """Apply one Drive transition to an affine piece, preserving its subfamily.

    state_key is (anchor, remaining_schedule, stop_count). This is an
    affine cut transform only; it does not construct or replay a route witness.
    """
    if not isinstance(piece, AffineCutPiece):
        raise TypeError("piece must be AffineCutPiece")
    if not isinstance(anchor, str) or not anchor:
        raise ValueError("anchor must be a non-empty string")
    duration, consumption, floor = (exact(duration, "duration"),
                                    exact(consumption, "consumption"),
                                    exact(floor, "floor"))
    if duration < 0 or consumption < 0:
        raise ValueError("Negative drive duration or consumption")
    if len(piece.state_key) != 3:
        raise ValueError("Drive requires state_key=(anchor, remaining_schedule, stop_count)")
    _, remaining_schedule, stop_count = piece.state_key
    if type(remaining_schedule) is not int or remaining_schedule not in (0, 1):
        raise ValueError("Invalid remaining schedule state")
    if type(stop_count) is not int or stop_count < 0:
        raise ValueError("Invalid stop count")
    if len(piece.prefix) != stop_count:
        raise ValueError("Prefix length must equal stop count")
    shifted = Interval(piece.domain.lo - consumption, piece.domain.hi - consumption,
                       piece.domain.left_closed, piece.domain.right_closed)
    if shifted.hi < floor:
        return None
    domain = shifted.intersect(Interval(floor, max(floor, shifted.hi)))
    if domain is None:
        return None
    def lift(output_energy, output_budget):
        output_energy, output_budget = exact(output_energy), exact(output_budget)
        input_energy = output_energy + consumption
        input_time = output_budget - duration
        if input_time < piece.cut_time_at(input_energy):
            raise ValueError("Drive budget is below predecessor cut")
        predecessor = piece.witness_lifter(input_energy, input_time) if piece.witness_lifter else None
        input_time = _actual_time(predecessor, input_time)
        return PwaStepWitness("D", anchor, input_energy, input_time, output_energy, input_time + duration,
                              (duration, consumption, floor), predecessor)
    return AffineCutPiece(
        domain=domain, slope=piece.slope,
        intercept=piece.intercept + piece.slope * consumption + duration,
        attained=piece.attained, rho=piece.rho + consumption,
        prefix=piece.prefix, state_key=(anchor, remaining_schedule, stop_count),
        witness_lifter=lift,
    )


def _actual_time(witness, budget):
    """A predecessor callback realizes an upper budget, possibly earlier."""
    return exact(getattr(witness, "output_time", getattr(witness, "time", budget)))


@dataclass(frozen=True)
class FixedEnergyCut:
    """Mathematical fixed-output-energy cut; it carries no route witness."""
    tau: Fraction
    attained: bool
    input_energy: Fraction

    def __post_init__(self):
        object.__setattr__(self, "tau", exact(self.tau, "tau"))
        object.__setattr__(self, "input_energy", exact(self.input_energy, "input_energy"))
        if type(self.attained) is not bool:
            raise TypeError("attained must be bool")


def _interval(domain, lo, hi, left_closed, right_closed):
    if lo > hi or lo == hi and not (left_closed and right_closed):
        return None
    return Interval(lo, hi, left_closed, right_closed)


def _affine_half_interval(domain, slope, intercept, bound, *, upper, inclusive):
    """Intersect domain with slope*x+intercept <= bound (or > bound)."""
    slope, intercept, bound = exact(slope), exact(intercept), exact(bound)
    if slope == 0:
        ok = intercept <= bound if upper and inclusive else (
            intercept < bound if upper else intercept > bound)
        return domain if ok else None
    root = (bound - intercept) / slope
    if upper:
        if slope > 0:
            if root < domain.lo:
                return None
            hi = min(domain.hi, root)
            rc = domain.right_closed if root > domain.hi else (
                inclusive if root < domain.hi else domain.right_closed and inclusive)
            return _interval(domain, domain.lo, hi, domain.left_closed, rc)
        if root > domain.hi:
            return None
        lo = max(domain.lo, root)
        lc = domain.left_closed if root < domain.lo else (
            inclusive if root > domain.lo else domain.left_closed and inclusive)
        return _interval(domain, lo, domain.hi, lc, domain.right_closed)
    # Lower half-line: slope*x+intercept > bound, or >= when inclusive.
    if slope > 0:
        if root > domain.hi or root == domain.hi and not inclusive:
            return None
        lo = max(domain.lo, root)
        lc = domain.left_closed if root < domain.lo else (
            inclusive if root > domain.lo else domain.left_closed and inclusive)
        return _interval(domain, lo, domain.hi, lc, domain.right_closed)
    if root < domain.lo or root == domain.lo and not inclusive:
        return None
    hi = min(domain.hi, root)
    rc = domain.right_closed if root > domain.hi else (
        inclusive if root < domain.hi else domain.right_closed and inclusive)
    return _interval(domain, domain.lo, hi, domain.left_closed, rc)


def schedule_piece(piece: AffineCutPiece, site: str, a, b, duration, overhead):
    """Migrate one exact S transition, splitting waiting plateau and active time.

    This is a one-piece mathematical transform. It does not materialize a
    physical witness or perform a PWA family envelope.
    """
    if not isinstance(piece, AffineCutPiece):
        raise TypeError("piece must be AffineCutPiece")
    if not isinstance(site, str) or not site:
        raise ValueError("site must be a non-empty string")
    a, b, duration, overhead = map(exact, (a, b, duration, overhead))
    if duration < 0 or overhead <= 0:
        raise ValueError("Require positive overhead and nonnegative duration")
    if a > b:
        return ()
    if len(piece.state_key) != 3:
        raise ValueError("S requires state_key=(anchor, remaining_schedule, stop_count)")
    _, remaining, stops = piece.state_key
    if remaining != 1 or type(stops) is not int or stops < 0:
        raise ValueError("S requires one remaining schedule and a valid stop count")
    if len(piece.prefix) != stops:
        raise ValueError("Prefix length must equal stop count")

    # Latest-start feasibility: tau <= b-h, with equality only for a closed cut.
    legal = _affine_half_interval(piece.domain, piece.slope, piece.intercept,
                                  b - overhead, upper=True,
                                  inclusive=piece.attained)
    if legal is None:
        return ()
    threshold = a - overhead
    plateau = _affine_half_interval(legal, piece.slope, piece.intercept,
                                    threshold, upper=True,
                                    inclusive=piece.attained)
    active = _affine_half_interval(legal, piece.slope, piece.intercept,
                                   threshold, upper=False,
                                   inclusive=not piece.attained)
    prefix = piece.prefix + ((site, "S"),)
    key = (site, 0, stops + 1)
    result = []
    if plateau is not None:
        def plateau_lift(energy, budget, piece=piece, site=site, a=a, b=b,
                         duration=duration, overhead=overhead):
            energy, budget = exact(energy), exact(budget)
            input_time = (piece.cut_time_at(energy) if piece.attained else a - overhead)
            if input_time > a - overhead or input_time > b - overhead:
                raise ValueError("Schedule plateau has no predecessor witness")
            predecessor = piece.witness_lifter(energy, input_time) if piece.witness_lifter else None
            input_time = _actual_time(predecessor, input_time)
            output_time = max(a + duration, input_time + overhead + duration)
            return PwaStepWitness("S", site, energy, input_time, energy, output_time,
                                  (a, b, duration, overhead), predecessor)
        result.append(AffineCutPiece(
            plateau, Fraction(0), a + duration, True, piece.rho,
            prefix, key, plateau_lift))
    if active is not None:
        def active_lift(energy, budget, piece=piece, site=site, a=a, b=b,
                        duration=duration, overhead=overhead):
            energy, budget = exact(energy), exact(budget)
            input_time = budget - overhead - duration
            if input_time < piece.cut_time_at(energy) or input_time > b - overhead:
                raise ValueError("Schedule active witness is infeasible")
            predecessor = piece.witness_lifter(energy, input_time) if piece.witness_lifter else None
            input_time = _actual_time(predecessor, input_time)
            output_time = max(a + duration, input_time + overhead + duration)
            return PwaStepWitness("S", site, energy, input_time, energy, output_time,
                                  (a, b, duration, overhead), predecessor)
        result.append(AffineCutPiece(
            active, piece.slope, piece.intercept + overhead + duration,
            piece.attained, piece.rho, prefix, key, active_lift))
    return tuple(result)


def _curve_value(curve_segments, energy):
    energy = exact(energy, "energy")
    matches = []
    for lo, hi, slope, intercept in curve_segments:
        lo, hi, slope, intercept = map(exact, (lo, hi, slope, intercept))
        if lo <= energy <= hi:
            matches.append(slope * energy + intercept)
    if not matches:
        raise ValueError("Energy outside charging-curve domain")
    if any(value != matches[0] for value in matches[1:]):
        raise ValueError("Charging curve is discontinuous at segment boundary")
    return matches[0]


def charge_fixed(piece: AffineCutPiece, output_energy, curve_segments, overhead):
    """Exact C infimum for one predecessor piece at one fixed output energy.

    Returns only the mathematical cut and minimizing predecessor energy. Full
    output-energy partitions, family reduction, and witness lifting remain
    outside this bounded operator.
    """
    if not isinstance(piece, AffineCutPiece):
        raise TypeError("piece must be AffineCutPiece")
    output_energy, overhead = exact(output_energy), exact(overhead)
    if overhead <= 0:
        raise ValueError("Charging overhead must be positive")
    curve_segments = tuple(curve_segments)
    output_curve = _curve_value(curve_segments, output_energy)
    candidates = []
    for lo, hi, rate, intercept in curve_segments:
        lo, hi, rate, intercept = map(exact, (lo, hi, rate, intercept))
        overlap = piece.domain.intersect(Interval(lo, hi))
        if overlap is None or overlap.lo >= output_energy:
            continue
        top = min(overlap.hi, output_energy)
        right_closed = overlap.right_closed if overlap.hi < output_energy else False
        domain = _interval(overlap, overlap.lo, top, overlap.left_closed, right_closed)
        if domain is None:
            continue
        objective_slope = piece.slope - rate
        objective_intercept = piece.intercept - intercept
        energy, endpoint_attained = domain.affine_infimum(objective_slope)
        value = objective_slope * energy + objective_intercept
        attained = piece.attained and endpoint_attained
        candidates.append((value, attained, energy))
    if not candidates:
        raise ValueError("No admissible strictly lower predecessor energy")
    minimum = min(candidate[0] for candidate in candidates)
    tied = [candidate for candidate in candidates if candidate[0] == minimum]
    chosen = next((candidate for candidate in tied if candidate[1]), tied[0])
    return FixedEnergyCut(overhead + output_curve + minimum,
                          any(candidate[1] for candidate in tied),
                          chosen[2])


def combined_fixed(piece: AffineCutPiece, input_energy, output_energy,
                   curve_segments, site: str, a, b, duration, overhead):
    """Exact fixed-(Ea,Ed) CS cut; no energy optimizer or route witness."""
    if not isinstance(piece, AffineCutPiece):
        raise TypeError("piece must be AffineCutPiece")
    if not isinstance(site, str) or not site:
        raise ValueError("site must be a non-empty string")
    input_energy, output_energy, a, b, duration, overhead = map(
        exact, (input_energy, output_energy, a, b, duration, overhead))
    if output_energy <= input_energy:
        raise ValueError("Combined charge requires Ed > Ea")
    if overhead <= 0 or duration < 0:
        raise ValueError("Require positive overhead and nonnegative duration")
    if len(piece.state_key) != 3 or piece.state_key[1] != 1:
        raise ValueError("CS requires one remaining schedule")
    if len(piece.prefix) != piece.state_key[2]:
        raise ValueError("Prefix length must equal stop count")
    tau = piece.cut_time_at(input_energy)
    latest = b - overhead
    if tau > latest or tau == latest and not piece.attained:
        raise ValueError("Input cut cannot meet latest schedule start")
    curve_segments = tuple(curve_segments)
    delta = _curve_value(curve_segments, output_energy) - _curve_value(
        curve_segments, input_energy)
    if delta <= 0:
        raise ValueError("Combined charge must make positive progress")
    offset = overhead + max(delta, duration)
    plateau = a + duration
    threshold = plateau - offset
    value = max(plateau, tau + offset)
    attained = piece.attained or tau < threshold
    return FixedEnergyCut(value, attained, input_energy)


def reduce_family_pieces(pieces):
    """Conservative whole-piece antichain within one inherited family only.

    A piece is removed only when another piece covers its full energy domain,
    has the same discrete state and inherited prefix, and pointwise dominates
    both the attained-time order and (rho, prefix) order. This does not split
    energy domains, merge families, or construct/lift physical witnesses.
    """
    pieces = tuple(pieces)
    for piece in pieces:
        if not isinstance(piece, AffineCutPiece):
            raise TypeError("all pieces must be AffineCutPiece")

    def covers(outer, inner):
        left_ok = (outer.domain.lo < inner.domain.lo or
                   outer.domain.lo == inner.domain.lo and
                   (not inner.domain.left_closed or outer.domain.left_closed))
        right_ok = (outer.domain.hi > inner.domain.hi or
                    outer.domain.hi == inner.domain.hi and
                    (not inner.domain.right_closed or outer.domain.right_closed))
        return left_ok and right_ok

    def dominates(outer, inner):
        if (outer.state_key, outer.prefix) != (inner.state_key, inner.prefix):
            return False
        if not covers(outer, inner) or outer.rho > inner.rho:
            return False
        slope = outer.slope - inner.slope
        intercept = outer.intercept - inner.intercept
        lo_value = slope * inner.domain.lo + intercept
        hi_value = slope * inner.domain.hi + intercept
        if lo_value > 0 or hi_value > 0:
            return False
        if not outer.attained and inner.attained:
            if slope == 0:
                if lo_value == 0:
                    return False
            else:
                crossing = -intercept / slope
                if inner.domain.contains(crossing):
                    return False
        strict_time = (lo_value < 0 or hi_value < 0 or
                       slope != 0 and inner.domain.lo < -intercept / slope < inner.domain.hi)
        strict = (outer.rho < inner.rho or strict_time or
                  outer.attained and not inner.attained and lo_value == hi_value == 0)
        return strict or pieces.index(outer) < pieces.index(inner)

    return tuple(piece for i, piece in enumerate(pieces)
                 if not any(j != i and dominates(other, piece)
                            for j, other in enumerate(pieces)))
