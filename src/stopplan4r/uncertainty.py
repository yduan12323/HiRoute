"""Minimal non-Bayesian decision/query contracts, not the Go-2 acquisition policy."""
from dataclasses import dataclass
from enum import Enum
from math import isfinite, isnan
from typing import Callable


class EvidenceState(str, Enum):
    PRESENT = 'present'
    UNKNOWN = 'unknown'
    ABSENT = 'absent'


@dataclass(frozen=True)
class ChargerEvidence:
    existence: EvidenceState
    usability: EvidenceState

    @property
    def conditionally_viable(self):
        return self.existence != EvidenceState.ABSENT and self.usability != EvidenceState.ABSENT


@dataclass(frozen=True)
class CostInterval:
    lower: float
    upper: float

    def __post_init__(self):
        if isnan(self.lower) or isnan(self.upper) or self.lower < 0 or self.lower > self.upper:
            raise ValueError('Invalid cost interval')


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    costs: CostInterval
    charger: ChargerEvidence


@dataclass(frozen=True)
class Query:
    target: str
    cost_s: float
    latency_s: float
    reliability: float

    def __post_init__(self):
        if not all(isfinite(x) for x in (self.cost_s, self.latency_s, self.reliability)) or min(self.cost_s, self.latency_s) < 0 or not 0 <= self.reliability <= 1:
            raise ValueError('Invalid query metadata')


def decision_pruned(costs, incumbent, epsilon_dec=0.0):
    if not isfinite(epsilon_dec) or epsilon_dec < 0 or not isfinite(incumbent.upper):
        raise ValueError('Pruning requires a finite guaranteed incumbent')
    return costs.lower >= incumbent.upper - epsilon_dec


def query_allowed(candidate, incumbent, query, fallback_feasible_after: Callable[[float], bool],
                  epsilon_dec=0.0, minimum_reliability=1.0):
    """Order is feasibility -> bounds/pruning -> query -> fallback latency.

    Reliability is a supplied quality field, never a probability of usability.
    The fallback callback must propagate location/time/energy while waiting.
    """
    if not candidate.charger.conditionally_viable:
        return False, 'known_absent'
    if decision_pruned(candidate.costs, incumbent, epsilon_dec):
        return False, 'decision_pruned'
    if query.target != candidate.candidate_id:
        return False, 'unrelated_query'
    if candidate.charger.usability != EvidenceState.UNKNOWN and candidate.charger.existence != EvidenceState.UNKNOWN:
        return False, 'no_unknown_charger_state'
    if query.reliability < minimum_reliability:
        return False, 'insufficient_reliability'
    if not fallback_feasible_after(query.latency_s):
        return False, 'fallback_expires'
    return True, 'conditionally_viable'


def resolve_query(candidate, incumbent, query, observed_usability, fallback_id,
                  fallback_feasible_after, epsilon_dec=0.0):
    allowed, reason = query_allowed(candidate, incumbent, query, fallback_feasible_after, epsilon_dec)
    if not allowed:
        return fallback_id if fallback_feasible_after(0.0) else None, reason
    if observed_usability == EvidenceState.ABSENT:
        return fallback_id, 'unfavorable_fallback'
    if observed_usability == EvidenceState.PRESENT:
        return candidate.candidate_id, 'commit_candidate'
    return None, 'unresolved'
