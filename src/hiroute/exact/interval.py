"""Exact nonempty rational intervals with explicit endpoint attainment."""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from .scalar import exact

@dataclass(frozen=True)
class Interval:
    lo: Fraction
    hi: Fraction
    left_closed: bool = True
    right_closed: bool = True

    def __post_init__(self):
        object.__setattr__(self, "lo", exact(self.lo, "lo"))
        object.__setattr__(self, "hi", exact(self.hi, "hi"))
        if type(self.left_closed) is not bool or type(self.right_closed) is not bool:
            raise TypeError("endpoint closure flags must be bool")
        if self.lo > self.hi or (self.lo == self.hi and not (self.left_closed and self.right_closed)):
            raise ValueError("Empty interval")

    def contains(self, value) -> bool:
        value = exact(value, "value")
        return ((value > self.lo or value == self.lo and self.left_closed)
                and (value < self.hi or value == self.hi and self.right_closed))

    def intersect(self, other: "Interval") -> "Interval | None":
        if not isinstance(other, Interval):
            raise TypeError("other must be Interval")
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        lc, rc = self.contains(lo) and other.contains(lo), self.contains(hi) and other.contains(hi)
        if lo > hi or lo == hi and not (lc and rc):
            return None
        return Interval(lo, hi, lc, rc)

    def affine_infimum(self, slope) -> tuple[Fraction, bool]:
        slope = exact(slope, "slope")
        if slope > 0:
            return self.lo, self.left_closed
        if slope < 0:
            return self.hi, self.right_closed
        return (self.lo + self.hi) / 2, True

    def approach_optimizer(self, slope, epsilon) -> Fraction:
        slope, epsilon = exact(slope, "slope"), exact(epsilon, "epsilon")
        if epsilon <= 0:
            raise ValueError("epsilon must be positive")
        point, included = self.affine_infimum(slope)
        if included or slope == 0:
            return point
        delta = min((self.hi - self.lo) / 2, epsilon / (2 * abs(slope)))
        candidate = point + delta if slope > 0 else point - delta
        if not self.contains(candidate):
            raise ValueError("no interior point approaches this boundary")
        return candidate
