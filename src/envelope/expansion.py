"""Caller-controlled budget expansion; no decision-value stopping rule."""
from dataclasses import dataclass
from typing import Iterator, Protocol, runtime_checkable

import numpy as np

from .safe_detour import (DetourDistances, NumericalTolerance, SafeDetourEnvelope,
                          build_envelope_from_precomputed)


@runtime_checkable
class EnvelopeExpansionPolicy(Protocol):
    def next_budget(self, baseline_cost: float, current: SafeDetourEnvelope | None) -> float | None: ...
    def should_stop(self, current: SafeDetourEnvelope) -> bool: ...


@dataclass(frozen=True)
class FixedSchedulePolicy:
    """Visit every specified ratio, stopping only when the schedule is exhausted.

    For zero baseline cost all ratios yield the same zero budget, so only one
    view is needed. This is budget equivalence, not a utility stopping rule.
    """
    ratios: tuple[float, ...]
    max_ratio: float

    def __post_init__(self):
        ratios = np.asarray(self.ratios, dtype=float)
        if (not len(ratios) or not np.isfinite(ratios).all() or (ratios < 1).any()
                or (np.diff(ratios) <= 0).any() or not np.isfinite(self.max_ratio)
                or ratios[-1] > self.max_ratio):
            raise ValueError("Invalid fixed schedule or cap")
        object.__setattr__(self, 'ratios', tuple(map(float, ratios)))

    def next_budget(self, baseline_cost, current):
        for ratio in self.ratios:
            budget = ratio * baseline_cost
            if current is None or budget > current.budget:
                return budget
        return None

    def should_stop(self, current):
        return current.budget >= self.ratios[-1] * current.baseline_cost


def iter_policy_envelopes(distances: DetourDistances, policy: EnvelopeExpansionPolicy,
                          max_budget: float,
                          tolerance: NumericalTolerance = NumericalTolerance()) -> Iterator[SafeDetourEnvelope]:
    """Enforce the cap independently of a supplied manual/future policy."""
    if not np.isfinite(max_budget) or max_budget < distances.baseline_cost:
        raise ValueError("Invalid expansion cap")
    current = None
    while True:
        budget = policy.next_budget(distances.baseline_cost, current)
        if budget is None:
            return
        if not np.isfinite(budget) or budget > max_budget or (current is not None and budget <= current.budget):
            raise ValueError("Policy must increase finite budgets within the cap")
        current = build_envelope_from_precomputed(distances, budget, tolerance)
        yield current
        if policy.should_stop(current):
            return
