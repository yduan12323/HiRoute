"""Opt-in C-only closed-form boundary and exact constrained midpoint lifting.

The historical Fourier–Motzkin operator remains the default. This module keeps
its redundant boundary-line fan and row ordering; it is not a coalescer.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from fractions import Fraction as R

from .probe import Interval, exact


_active = ContextVar("timecut5_analytic_charge", default=None)


@dataclass(frozen=True)
class AnalyticChargeStatistics:
    enabled: bool
    considered_pairs: int
    support_skipped_pairs: int
    analytic_builds: int
    generic_projection_builds: int
    recorded_fallback_builds: int


class AnalyticCharge:
    """Single-use exact-boolean context; detached, bounded construction counts.

    Counters cover C pairs only. Support-prefilter counts retain their existing
    schema and count actual generic builds. With coextensive contexts, healthy
    combined conservation adds this context's analytic_builds to that identity.
    Live/interrupted snapshots are nontransactional and may not conserve counts.
    """
    def __init__(self, *, enabled=False):
        if type(enabled) is not bool:
            raise ValueError("Analytic charge requires an exact boolean")
        self._enabled = enabled
        self._used = False
        self._token = None
        self._counts = {name: 0 for name in AnalyticChargeStatistics.__dataclass_fields__
                        if name != "enabled"}

    @property
    def enabled(self):
        return self._enabled

    def snapshot(self):
        return AnalyticChargeStatistics(enabled=self.enabled, **self._counts)

    def __enter__(self):
        if self._used:
            raise ValueError("Analytic charge context is single-use")
        self._used = True
        self._token = _active.set(self)
        return self

    def __exit__(self, *exception):
        _active.reset(self._token)
        self._token = None


def _clip(domain, coefficient, rhs, strict):
    """Exact one-dimensional halfspace intersection, including zero rows."""
    if coefficient == 0:
        return domain if (rhs > 0 if strict else rhs >= 0) else None
    edge = rhs / coefficient
    lo, hi = domain.lo, domain.hi
    lc, rc = domain.left_closed, domain.right_closed
    if coefficient > 0:
        if edge < hi:
            hi, rc = edge, not strict
        elif edge == hi:
            rc = rc and not strict
    else:
        if edge > lo:
            lo, lc = edge, not strict
        elif edge == lo:
            lc = lc and not strict
    return (Interval(lo, hi, lc, rc)
            if lo < hi or lo == hi and lc and rc else None)


@dataclass(frozen=True)
class _ChargeProjection:
    """Only the interface consumed by _extract; no generic elimination history."""
    rows: tuple
    source: object
    support: Interval
    incoming: tuple
    outgoing: tuple
    overhead: R

    def lift(self, fixed):
        if set(fixed) != {2, 3}:
            raise ValueError("Analytic C lift requires output energy and budget")
        y, budget = exact(fixed[2]), exact(fixed[3])
        il, ih, im, ic = self.incoming
        ol, oh, om, oc = self.outgoing
        if not ol <= y <= oh:
            raise ValueError("Output outside selected charging segment")
        source = self.source
        delta = source.slope - im
        base = self.overhead + om*y + oc + source.intercept - ic
        fiber = _clip(self.support, R(1), y, True)
        if fiber is not None:
            fiber = _clip(fiber, delta, budget-base, not source.chi)
        if fiber is None:
            raise ValueError("Empty strict analytic C witness fiber")
        # These are exactly the two midpoint choices in the historical
        # Projection.build(..., (1, 0)).lift, including flat-objective ties.
        x = (fiber.lo + fiber.hi) / 2
        lower = source.slope*x + source.intercept
        upper = budget-self.overhead-(om*y+oc)+(im*x+ic)
        time = (lower + upper) / 2
        if (not source.domain.contains(x) or not il <= x <= ih or not x < y
                or time < lower or time == lower and not source.chi
                or time > upper):
            raise AssertionError("Analytic C lift violates original constraints")
        return x, time, y, budget


def _build(source, incoming, outgoing, overhead):
    """Derive the historical projected C line fan without either FM step.

    Retain inactive endpoint lines. Normalizing this constant-size fan with
    the historical routine preserves duplicate strictness and singleton tie
    order; restricting to only the active min-plus branches would not.
    """
    from .pwa import Row, _normalize
    il, ih, im, ic = incoming
    ol, oh, om, oc = outgoing
    support = source.domain.intersect(Interval(il, ih))
    if support is None or support.lo >= oh:
        return None
    delta = source.slope-im
    base = overhead+oc+source.intercept-ic
    rows = [Row((0, 0, -1, 0), -support.lo, True),
            Row((0, 0, -1, 0), -ol), Row((0, 0, 1, 0), oh)]
    def line(slope, intercept, strict):
        rows.append(Row((0, 0, slope, -1), -intercept, strict))
    if delta > 0:
        line(om, base+delta*source.domain.lo,
             not source.chi or not source.domain.left_closed)
        line(om, base+delta*il, not source.chi)
    elif delta < 0:
        line(om, base+delta*source.domain.hi,
             not source.chi or not source.domain.right_closed)
        line(om, base+delta*ih, not source.chi)
        line(om+delta, base, True)
    else:
        line(om, base, not source.chi)
    normalized = _normalize(rows)
    if normalized is None:
        raise AssertionError("Nonempty C support has contradictory boundary rows")
    return _ChargeProjection(normalized, source, support, incoming, outgoing, overhead)
