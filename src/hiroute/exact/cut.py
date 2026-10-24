"""Attainment-aware lower time cuts with constructive time-budget witnesses.

This module owns only fixed-context cuts. It does not implement PWA propagation,
family reduction, road routing, or a global solver.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Callable, Hashable, TypeVar
from .scalar import exact

class UnattainedError(ValueError):
    """A requested executable boundary or time budget has no witness."""

@dataclass(frozen=True)
class CutWitness:
    time: Fraction
    context: Hashable
    family_id: str
    events: tuple[object, ...] = ()
    def __post_init__(self):
        object.__setattr__(self, "time", exact(self.time, "witness.time"))
        if not isinstance(self.family_id, str) or not self.family_id:
            raise ValueError("family_id must identify the represented family")

@dataclass(frozen=True)
class TimeCut:
    tau: Fraction
    attained: bool
    context: Hashable
    family_id: str
    _approach: Callable[[Fraction], CutWitness] = field(repr=False, compare=False)
    def __post_init__(self):
        object.__setattr__(self, "tau", exact(self.tau, "tau"))
        if type(self.attained) is not bool:
            raise TypeError("attained must be bool")
        if not isinstance(self.family_id, str) or not self.family_id:
            raise ValueError("family_id must identify the represented family")
    def approach(self, epsilon: Fraction) -> CutWitness:
        epsilon = exact(epsilon, "epsilon")
        if epsilon <= 0:
            raise ValueError("epsilon must be strictly positive")
        witness = self._approach(epsilon)
        if witness.context != self.context or witness.family_id != self.family_id:
            raise ValueError("Witness escaped the represented context or family")
        if not self.tau <= witness.time < self.tau + epsilon:
            raise ValueError("Witness is outside the requested approach budget")
        if self.attained != (witness.time == self.tau):
            raise ValueError("Witness contradicts boundary attainment")
        return witness
    def minimum(self) -> CutWitness:
        if not self.attained:
            raise UnattainedError("Open cut has no executable minimum")
        return self.approach(Fraction(1))
    def realize_le(self, budget: Fraction) -> CutWitness:
        budget = exact(budget, "budget")
        if budget < self.tau or (budget == self.tau and not self.attained):
            raise UnattainedError("No family member meets this time budget")
        return self.minimum() if self.attained else self.approach(budget - self.tau)


def cut_le(a: TimeCut, b: TimeCut) -> bool:
    """Sufficient continuation preorder on lower cuts, preserving open edges."""
    return a.tau < b.tau or (a.tau == b.tau and (a.attained or not b.attained))


def fixed_member(tau: Fraction, *, attained: bool, context: Hashable,
                 family_id: str) -> TimeCut:
    """Convenience constructor for a singleton boundary or an analytic open ray."""
    tau = exact(tau, "tau")
    def approach(epsilon: Fraction) -> CutWitness:
        time = tau if attained else tau + min(Fraction(1), epsilon / 2)
        return CutWitness(time, context, family_id)
    return TimeCut(tau, attained, context, family_id, approach)
