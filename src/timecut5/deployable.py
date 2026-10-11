"""M5-D search-boundary primitives; no graph load or optimization entrypoint.

These contracts are intentionally separate from the accepted v2 solvers. A
future deployable solver must bind and verify them before search starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import hashlib
import json
from math import floor, isfinite, isnan
import re
from typing import Callable, Mapping

from .real_legs import ImmutableLegTable, SelectedLeg

_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _sha(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class DomainBinding:
    graph_sha256: str
    site_catalog_sha256: str
    population_sha256: str
    hierarchy_sha256: str
    landmark_sha256: str
    selected_leg_contract_sha256: str
    candidate_set_sha256: str
    query_sha256: str
    mobility_budget_sha256: str
    depth_policy_sha256: str
    numeric_contract_sha256: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _sha(getattr(self, name), name)


class SolveStatus(str, Enum):
    ATTAINED_OPTIMUM = "attained_optimum"
    INFIMUM_UNATTAINED_J = "infimum_unattained_J"
    INFIMUM_UNATTAINED_Q = "infimum_unattained_Q"
    INFEASIBLE_WITHIN_DECLARED_DOMAIN = "infeasible_within_declared_domain"
    INCUMBENT_SEARCH_FAILED = "incumbent_search_failed"
    TIME_LIMIT = "time_limit"
    MEMORY_LIMIT = "memory_limit"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True)
class SearchOutcome:
    domain: DomainBinding
    status: SolveStatus
    j: Fraction | None = None
    q: Fraction | None = None
    h: int | None = None
    pi: tuple[tuple[str, str], ...] | None = None
    executable_witness_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.domain, DomainBinding) or not isinstance(self.status, SolveStatus):
            raise ValueError("Outcome requires a bound domain and recognized status")
        if self.j is not None and (not isinstance(self.j, Fraction) or self.j < 0):
            raise ValueError("J must be a nonnegative exact rational")
        if self.q is not None and (self.j is None or not isinstance(self.q, Fraction) or self.q < 0):
            raise ValueError("Q requires an attained nonnegative J")
        if self.h is not None and (self.q is None or type(self.h) is not int or self.h < 0):
            raise ValueError("H requires an attained Q")
        if self.pi is not None and (self.h is None or type(self.pi) is not tuple or
                                    len(self.pi) != self.h or any(
                                        type(item) is not tuple or len(item) != 2 or
                                        not isinstance(item[0], str) or not item[0] or
                                        item[1] not in ("C", "S", "CS") for item in self.pi)):
            raise ValueError("Pi requires an attained H and explicit Site identities")
        if self.executable_witness_sha256 is not None:
            _sha(self.executable_witness_sha256, "executable_witness_sha256")
            if self.status is not SolveStatus.ATTAINED_OPTIMUM or self.pi is None:
                raise ValueError("Only a full attained key has an optimal executable witness")
        if self.status is SolveStatus.ATTAINED_OPTIMUM:
            if None in (self.j, self.q, self.h, self.pi, self.executable_witness_sha256):
                raise ValueError("Attained optimum requires full key and verified witness")
        elif self.status is SolveStatus.INFIMUM_UNATTAINED_J:
            if self.j is None or any(x is not None for x in (self.q, self.h, self.pi)):
                raise ValueError("Unattained J has no later lexicographic coordinates")
        elif self.status is SolveStatus.INFIMUM_UNATTAINED_Q:
            if self.j is None or self.q is None or self.h is not None or self.pi is not None:
                raise ValueError("Unattained Q has no executable full-key optimum")
        elif any(x is not None for x in (self.j, self.q, self.h, self.pi,
                                          self.executable_witness_sha256)):
            raise ValueError("Incomplete searches carry bounds/incumbents in a separate receipt")


@dataclass(frozen=True)
class VerifiedSeed:
    domain: DomainBinding
    primary_j: Fraction
    witness_sha256: str
    independent_verifier_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.domain, DomainBinding) or not isinstance(self.primary_j, Fraction) or self.primary_j < 0:
            raise ValueError("Seed must bind a domain and finite nonnegative exact J")
        _sha(self.witness_sha256, "witness_sha256")
        _sha(self.independent_verifier_sha256, "independent_verifier_sha256")


def certified_depth(seed: VerifiedSeed, domain: DomainBinding,
                    minimum_overhead: Fraction, stop_penalty: Fraction) -> int:
    """Apply the accepted v2 depth theorem; equality depth remains included."""
    if not isinstance(seed, VerifiedSeed) or seed.domain != domain:
        raise ValueError("A same-domain independently verified seed is required")
    if (not isinstance(minimum_overhead, Fraction) or not isinstance(stop_penalty, Fraction)
            or minimum_overhead <= 0 or stop_penalty < 0):
        raise ValueError("Require positive minimum overhead and nonnegative penalty")
    return floor(seed.primary_j / (minimum_overhead + stop_penalty))


def constructive_seed_candidates(query: Mapping, table: ImmutableLegTable) -> tuple:
    """Deterministic zero/one-stop proposals for an independent replay checker.

    This only constructs candidate sequences and charge quantities from frozen
    selected legs. It does not read REF/FLAT/HIER outputs, solve a continuous
    optimization problem, or certify that a proposal is feasible.
    """
    if not isinstance(table, ImmutableLegTable) or not isinstance(query, Mapping):
        raise ValueError("Frozen table and exact query required")
    for key, expected in (("origin", table.origin_anchor),
                          ("destination", table.destination_anchor),
                          ("leg_payload_sha256", table.payload_sha256),
                          ("selection_certificate_sha256", table.selection_certificate_sha256),
                          ("hierarchy_sha256", table.hierarchy_sha256)):
        if query.get(key) != expected:
            raise ValueError(f"Unbound seed query field {key}")
    def exact_field(key: str) -> Fraction:
        value = query.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
            raise ValueError(f"Seed scalar {key} must be exact")
        return Fraction(value)
    initial, capacity = exact_field("initial_energy_kwh"), exact_field("capacity_kwh")
    reserve, floor_energy = exact_field("reserve_kwh"), exact_field("minimum_energy_kwh")
    consumption = exact_field("consumption_kwh_per_m")
    bound = query.get("H_ref")
    if (type(bound) is not int or bound < 0 or not 0 <= floor_energy <= initial <= capacity
            or not floor_energy <= reserve <= capacity or consumption <= 0):
        raise ValueError("Invalid seed battery or diagnostic depth domain")
    has_schedule = query.get("schedule") is not None
    result = []
    direct = table.leg(table.origin_anchor, table.destination_anchor)
    if not has_schedule and direct.reachable and initial - direct.energy(consumption) >= reserve:
        result.append(((), ()))
    if bound == 0:
        return tuple(result)
    for site_id in sorted(table.sites):
        site = table.site(site_id)
        if site.anchor_id == table.destination_anchor:
            continue
        inbound = table.leg(table.origin_anchor, site.anchor_id)
        outbound = table.leg(site.anchor_id, table.destination_anchor)
        if not inbound.reachable or not outbound.reachable:
            continue
        arrival = initial - inbound.energy(consumption)
        if arrival < floor_energy:
            continue
        terminal_need = outbound.energy(consumption) + reserve - arrival
        for effect in sorted(site.effects):
            if has_schedule != (effect in ("S", "CS")):
                continue
            if effect == "S":
                if terminal_need <= 0:
                    result.append((((site_id, effect),), ()))
                continue
            if effect not in ("C", "CS"):
                continue
            headroom = capacity - arrival
            if headroom <= 0:
                continue
            amount = max(terminal_need, min(Fraction(1), headroom) / 2)
            if 0 < amount <= headroom:
                result.append((((site_id, effect),), (amount,)))
    return tuple(result)


@dataclass(frozen=True)
class RouteContract:
    graph_sha256: str
    router_sha256: str
    landmark_sha256: str
    tie_policy_sha256: str
    direction_policy_sha256: str
    numerical_contract_sha256: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _sha(getattr(self, name), name)


class SelectedLegCache:
    """One directed selected-route provider call per cache miss, no rerouting."""

    def __init__(self, contract: RouteContract,
                 provider: Callable[[str, str], SelectedLeg]):
        if not isinstance(contract, RouteContract) or not callable(provider):
            raise ValueError("Bound route contract and provider required")
        self.contract = contract
        self._provider = provider
        self._cache: dict[tuple[str, str], SelectedLeg] = {}
        self.hits = 0
        self.misses = 0

    def leg(self, source: str, target: str) -> SelectedLeg:
        if not isinstance(source, str) or not isinstance(target, str) or not source or not target:
            raise ValueError("Road anchors must be nonempty strings")
        key = source, target
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        value = self._provider(source, target)
        if not isinstance(value, SelectedLeg) or (value.source_anchor, value.target_anchor) != key:
            raise ValueError("Provider returned a different directed leg")
        if value.reachable:
            if (not isinstance(value.time, Fraction) or not isinstance(value.actual_length, Fraction)
                    or not isinstance(value.time_hex, str) or not isinstance(value.length_hex, str)
                    or value.time < 0 or value.actual_length < 0):
                raise ValueError("Selected reachable leg lacks its time or actual length")
            try:
                decoded_time = float.fromhex(value.time_hex)
                decoded_length = float.fromhex(value.length_hex)
            except (ValueError, OverflowError) as error:
                raise ValueError("Selected leg has invalid binary64 provenance") from error
            if (not isfinite(decoded_time) or not isfinite(decoded_length)
                    or Fraction.from_float(decoded_time) != value.time
                    or Fraction.from_float(decoded_length) != value.actual_length):
                raise ValueError("Selected leg binary64 provenance disagrees with exact totals")
            if source == target:
                if value.time != 0 or value.actual_length != 0 or value.label_direction != "identity":
                    raise ValueError("Same-anchor selected leg must be zero identity")
            elif (value.time <= 0 or value.actual_length <= 0 or value.label_direction not in
                  ("forward_from_source", "reverse_from_target")):
                raise ValueError("Selected nonidentity leg lacks a valid directed route")
        elif value.time is not None or value.actual_length is not None:
            raise ValueError("Unreachable leg has finite constants")
        self._cache[key] = value
        self.misses += 1
        return value


@dataclass(frozen=True)
class LandmarkDistances:
    """Directed distances for one landmark; infinity means no directed path."""
    from_landmark: Mapping[str, float]
    to_landmark: Mapping[str, float]


@dataclass(frozen=True)
class RegionLandmarkSummary:
    """Offline-certified extrema over *all* Region members, with no online scan."""
    member_set_sha256: str
    graph_sha256: str
    landmark_sha256: str
    min_from_landmark: tuple[float, ...]
    max_to_landmark: tuple[float, ...]

    def __post_init__(self) -> None:
        for name in ("member_set_sha256", "graph_sha256", "landmark_sha256"):
            _sha(getattr(self, name), name)
        if len(self.min_from_landmark) != len(self.max_to_landmark):
            raise ValueError("Landmark summary dimensions differ")
        if any(isnan(x) or x < 0 for x in (*self.min_from_landmark, *self.max_to_landmark)):
            raise ValueError("Region distance extrema must be nonnegative or +infinity")


def member_set_digest(members: tuple[str, ...]) -> str:
    if (not members or any(not isinstance(m, str) or not m for m in members)
            or len(set(members)) != len(members)):
        raise ValueError("Nonempty unique Region member identities required")
    return hashlib.sha256(json.dumps(sorted(members), separators=(",", ":")).encode()).hexdigest()


def check_region_summary_offline(members: tuple[str, ...],
                                 landmarks: tuple[LandmarkDistances, ...],
                                 summary: RegionLandmarkSummary) -> bool:
    """Independent setup check; this member scan must stay outside online search."""
    if (member_set_digest(members) != summary.member_set_sha256 or
            len(landmarks) != len(summary.min_from_landmark)):
        return False
    for i, distances in enumerate(landmarks):
        forward = [distances.from_landmark[m] for m in members]
        reverse = [distances.to_landmark[m] for m in members]
        if any(isnan(x) or x < 0 for x in (*forward, *reverse)):
            return False
        if min(forward) != summary.min_from_landmark[i] or max(reverse) != summary.max_to_landmark[i]:
            return False
    return True


def directed_alt_region_bound(source: str, landmarks: tuple[LandmarkDistances, ...],
                              summary: RegionLandmarkSummary, *, graph_sha256: str,
                              landmark_sha256: str, member_set_sha256: str) -> float:
    """Safe directed ALT bound using only complete precomputed Region extrema.

    Each nonfinite subtraction term is skipped separately. The caller must
    independently certify extrema cover the bound member-set hash.
    """
    if (summary.graph_sha256 != graph_sha256 or summary.landmark_sha256 != landmark_sha256
            or summary.member_set_sha256 != member_set_sha256 or
            len(landmarks) != len(summary.min_from_landmark)):
        raise ValueError("Region ALT graph, landmark or member binding mismatch")
    bound = 0.0
    for i, distances in enumerate(landmarks):
        from_source = distances.from_landmark[source]
        to_source = distances.to_landmark[source]
        low_from = summary.min_from_landmark[i]
        high_to = summary.max_to_landmark[i]
        if any(isnan(x) or x < 0 for x in (from_source, to_source)):
            raise ValueError("Source landmark distances must be nonnegative or +infinity")
        if isfinite(low_from) and isfinite(from_source):
            bound = max(bound, low_from - from_source)
        if isfinite(to_source) and isfinite(high_to):
            bound = max(bound, to_source - high_to)
    return bound
