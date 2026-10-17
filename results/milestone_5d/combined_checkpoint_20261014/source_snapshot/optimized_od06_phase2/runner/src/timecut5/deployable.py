"""M5-D search-boundary primitives; no graph load or optimization entrypoint.

These contracts are intentionally separate from the accepted v2 solvers. A
future deployable solver must bind and verify them before search starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import hashlib
import inspect
import json
from math import floor, isfinite, isnan
from pathlib import Path
import re
import sys
import time
from typing import Callable, Mapping

from .real_legs import ImmutableLegTable, NUMERICS, SelectedLeg, TIE_POLICY

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MOBILITY_POLICY = b"unrestricted"
_DEPTH_POLICY = b"positive_overhead_verified_seed_v1"


def _json_object(data: bytes) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key in bound query")
            result[key] = value
        return result
    try:
        result = json.loads(data, object_pairs_hook=unique_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid query bytes") from error
    if type(result) is not dict:
        raise ValueError("Query must be a JSON object")
    return result


def _sha(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _verified_sources(sources: Mapping, fields: set[str]) -> dict[str, str]:
    if not isinstance(sources, Mapping) or set(sources) != fields:
        raise ValueError("Complete exact source set required")
    result = {}
    for name, pair in sources.items():
        if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not bytes:
            raise ValueError(f"{name} requires bytes and declared digest")
        _sha(pair[1], name)
        actual = hashlib.sha256(pair[0]).hexdigest()
        if actual != pair[1]:
            raise ValueError(f"{name} byte closure mismatch")
        result[name] = actual
    return result


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

    @classmethod
    def from_verified_bytes(cls, sources: Mapping) -> DomainBinding:
        return cls(**_verified_sources(sources, set(cls.__dataclass_fields__)))


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


@dataclass(frozen=True)
class QueryDomain:
    """Byte-closed query and selected-leg table for seed construction.

    The full graph/policy/population closure is supplied by DomainBinding;
    this boundary additionally checks the concrete query, candidate IDs and
    immutable selected-leg payload before any seed proposal is made.
    """
    binding: DomainBinding
    query_bytes: bytes
    candidate_bytes: bytes
    table_bytes: bytes
    table_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.binding, DomainBinding) or any(type(x) is not bytes for x in
              (self.query_bytes, self.candidate_bytes, self.table_bytes)):
            raise ValueError("Query domain requires a bound source and immutable bytes")
        _sha(self.table_sha256, "table_sha256")
        for value, expected in ((self.query_bytes, self.binding.query_sha256),
                                (self.candidate_bytes, self.binding.candidate_set_sha256),
                                (self.table_bytes, self.table_sha256)):
            if hashlib.sha256(value).hexdigest() != expected:
                raise ValueError("Query domain byte closure mismatch")
        if (self.binding.mobility_budget_sha256 != hashlib.sha256(_MOBILITY_POLICY).hexdigest()
                or self.binding.depth_policy_sha256 != hashlib.sha256(_DEPTH_POLICY).hexdigest()):
            raise ValueError("Only unrestricted mobility and verified-seed depth are implemented")
        query, table = self.open()
        if (table.hierarchy_sha256 != self.binding.hierarchy_sha256 or
                query.get("leg_payload_sha256") != table.payload_sha256 or
                query.get("selection_certificate_sha256") != table.selection_certificate_sha256):
            raise ValueError("Query, table or hierarchy provenance mismatch")
        try:
            candidates = json.loads(self.candidate_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid candidate set bytes") from error
        if (type(candidates) is not list or candidates != sorted(table.sites) or
                len(set(candidates)) != len(candidates)):
            raise ValueError("Candidate IDs differ from the immutable table")

    def open(self) -> tuple[dict, ImmutableLegTable]:
        return _json_object(self.query_bytes), ImmutableLegTable.from_bytes(
            self.table_bytes, self.table_sha256)


@dataclass(frozen=True)
class SeedDepthCertificate:
    domain: QueryDomain
    seed: VerifiedSeed
    max_depth: int
    sequence: tuple[tuple[str, str], ...]
    charges: tuple[Fraction, ...]

    def __post_init__(self) -> None:
        query, table = self.domain.open()
        def scalar(name):
            value = query.get(name)
            if type(value) not in (str, int):
                raise ValueError(f"Non-exact {name} in bound query")
            return Fraction(value)
        if (self.seed.domain != self.domain.binding or type(self.max_depth) is not int or
                self.max_depth < 0 or len(self.sequence) > self.max_depth or
                len(self.charges) != sum(effect in ("C", "CS") for _, effect in self.sequence)):
            raise ValueError("Seed depth certificate is inconsistent")
        witness_bytes = json.dumps({"sequence": self.sequence,
                                    "charges": [str(value) for value in self.charges]},
                                   sort_keys=True, separators=(",", ":")).encode()
        if (self.max_depth != certified_depth(self.seed, self.domain.binding,
                            scalar("overhead_s"), scalar("lambda_stop_s")) or
                self.seed.witness_sha256 != hashlib.sha256(witness_bytes).hexdigest() or
                any(site not in table.sites or effect not in table.site(site).effects
                    for site, effect in self.sequence)):
            raise ValueError("Seed depth, witness digest or Site membership mismatch")


def construct_verified_seed(domain: QueryDomain, verifier_source_sha256: Mapping[str, str]
                            ) -> SeedDepthCertificate | SearchOutcome:
    """Construct, independently replay, then certify an equality-inclusive depth.

    A failed finite proposal search is explicitly inconclusive. The replay
    implementation is the fixed tree-independent REF replay entrypoint and
    its exact source dependencies; no REF optimizer or solver result is read.
    """
    if not isinstance(domain, QueryDomain) or set(verifier_source_sha256) != {
            "package", "real_solver", "real_input", "model", "solver", "lp"}:
        raise ValueError("Complete approved verifier source closure required")
    import validation.reference5 as package
    from validation.reference5 import lp, model, real_input, real_solver, solver
    modules = {"package": package, "real_solver": real_solver,
               "real_input": real_input, "model": model, "solver": solver, "lp": lp}
    for name, module in modules.items():
        declared = verifier_source_sha256[name]
        _sha(declared, name)
        source = inspect.getsourcefile(module)
        if source is None or hashlib.sha256(Path(source).read_bytes()).hexdigest() != declared:
            raise ValueError("Approved verifier source closure mismatch")
    replay = real_solver.replay_real_witness_bytes
    prepared_replay = real_solver._replay_real
    if (replay.__module__ != real_solver.__name__ or
            inspect.getsourcefile(replay) != inspect.getsourcefile(real_solver) or
            prepared_replay.__module__ != real_solver.__name__ or
            inspect.getsourcefile(prepared_replay) != inspect.getsourcefile(real_solver)):
        raise ValueError("Approved verifier entrypoint changed")
    query, table = domain.open()
    proposals = constructive_seed_candidates(query, table)
    # Parse the independently reviewed REF table and physical case once. Its
    # replay function reads the prepared case but does not mutate it. A fresh
    # byte-level REF parse/replay below rechecks the chosen winner before any
    # bound or depth certificate is issued.
    independent_table = real_input.IndependentLegTable.from_bytes(
        domain.table_bytes, domain.table_sha256)
    prepared = real_solver.prepare_real_case(_json_object(domain.query_bytes),
                                             independent_table)
    accepted = []
    for sequence, charges in proposals:
        try:
            result = prepared_replay(prepared, sequence, charges)
        except (ValueError, AssertionError):
            continue
        if (type(result) is not dict or result.get("witness_replayed") is not True
                or result.get("H") != len(sequence)
                or result.get("site_action_tuple") != sequence or
                result.get("charges") != charges or
                type(result.get("J")) is not Fraction or result["J"] < 0 or
                type(result.get("Q_total")) is not Fraction or
                result["Q_total"] != sum(charges, Fraction(0)) or
                result.get("lex_key") != (result["J"], result["Q_total"],
                                          len(sequence), sequence)):
            raise ValueError("Independent replay returned an inconsistent witness")
        accepted.append((result["J"], result["Q_total"], len(sequence), sequence, charges))
    if not accepted:
        return SearchOutcome(domain.binding, SolveStatus.INCUMBENT_SEARCH_FAILED)
    j, _, _, sequence, charges = min(accepted)
    winner = replay(_json_object(domain.query_bytes), domain.table_bytes,
                    domain.table_sha256, sequence, charges)
    if (type(winner) is not dict or winner.get("witness_replayed") is not True or
            winner.get("lex_key") != (j, sum(charges, Fraction(0)), len(sequence), sequence) or
            winner.get("charges") != charges):
        raise ValueError("Fresh-byte independent seed replay disagrees with prepared replay")
    witness_bytes = json.dumps({"sequence": sequence,
                               "charges": [str(value) for value in charges]},
                              sort_keys=True, separators=(",", ":")).encode()
    closure_bytes = json.dumps(dict(sorted(verifier_source_sha256.items())),
                               sort_keys=True, separators=(",", ":")).encode()
    seed = VerifiedSeed(domain.binding, j, hashlib.sha256(witness_bytes).hexdigest(),
                        hashlib.sha256(closure_bytes).hexdigest())
    def exact(name: str) -> Fraction:
        value = _json_object(domain.query_bytes).get(name)
        if type(value) not in (str, int):
            raise ValueError(f"Non-exact {name} in bound query")
        return Fraction(value)
    depth = certified_depth(seed, domain.binding, exact("overhead_s"), exact("lambda_stop_s"))
    return SeedDepthCertificate(domain, seed, depth, sequence, charges)


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
    """Compatibility API: exhaust the same finite proposal stream into a tuple.

    Validation and source errors are raised before this eager call returns, as
    before. Iterator callers receive those errors when advancing the stream.
    """
    return tuple(iter_constructive_seed_candidates(query, table))


def iter_constructive_seed_candidates(query: Mapping, table: ImmutableLegTable):
    """Deterministic bounded proposals for an independent replay checker.

    This only constructs candidate sequences and charge quantities from frozen
    selected legs. It does not read REF/FLAT/HIER outputs, solve a continuous
    optimization problem, or certify that a proposal is feasible.
    """
    from .sparse_seed import SparseSeedCatalog
    if not isinstance(table, (ImmutableLegTable, SparseSeedCatalog)) or not isinstance(query, Mapping):
        raise ValueError("Bound selected-leg source and exact query required")
    bindings = (("origin", table.origin_anchor),
                ("destination", table.destination_anchor),
                ("hierarchy_sha256", table.hierarchy_sha256))
    if isinstance(table, ImmutableLegTable):
        bindings += (("leg_payload_sha256", table.payload_sha256),
                     ("selection_certificate_sha256", table.selection_certificate_sha256))
    else:
        bindings += (("sparse_domain_sha256", table.domain_sha256),)
    for key, expected in bindings:
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
    remaining = query.get("initial_remaining_schedule", int(has_schedule))
    if type(remaining) is not int or remaining not in (0, 1) or (remaining and not has_schedule):
        raise ValueError("Invalid initial remaining schedule state")
    direct = table.leg(table.origin_anchor, table.destination_anchor)
    if not remaining and direct.reachable and initial - direct.energy(consumption) >= reserve:
        yield ((), ())
    if bound == 0:
        return
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
            if (effect in ("S", "CS")) != bool(remaining):
                continue
            if effect == "S":
                if terminal_need <= 0:
                    yield (((site_id, effect),), ())
                continue
            if effect not in ("C", "CS"):
                continue
            headroom = capacity - arrival
            if headroom <= 0:
                continue
            amount = max(terminal_need, min(Fraction(1), headroom) / 2)
            if 0 < amount <= headroom:
                yield (((site_id, effect),), (amount,))
    if bound < 2:
        return
    # A small deterministic beam explores physical progress for a feasible
    # multi-charge seed. This is only a proposal generator: independent replay
    # checks the exact service/charge clock and all physical constraints.
    schedule = query.get("schedule")
    overhead = exact_field("overhead_s")
    segments = tuple(tuple(Fraction(value) for value in row)
                     for row in query.get("charging_segments", ()))
    def charge_time(lo: Fraction, hi: Fraction) -> Fraction:
        return sum((max(Fraction(0), min(hi, b) - max(lo, a)) * slope
                    for a, b, slope, _ in segments), Fraction(0))
    frontier = [(table.origin_anchor, initial, exact_field("start_time_s"),
                 remaining, (), ())]
    for depth in range(1, min(bound, 8) + 1):
        expanded = []
        for anchor, energy, clock, pending, sequence, charges in frontier:
            for site_id in sorted(table.sites):
                if site_id in (event[0] for event in sequence):
                    continue
                site = table.site(site_id)
                if site.anchor_id == table.destination_anchor:
                    continue
                inbound = table.leg(anchor, site.anchor_id)
                if not inbound.reachable:
                    continue
                arrival = energy - inbound.energy(consumption)
                if arrival < floor_energy:
                    continue
                release = clock + inbound.time + overhead
                for effect in sorted(site.effects):
                    if effect in ("S", "CS") and not pending:
                        continue
                    amounts = (Fraction(0),) if effect == "S" else (
                        capacity - arrival, min(Fraction(1), capacity - arrival) / 2)
                    for amount in amounts:
                        if effect != "S" and amount <= 0:
                            continue
                        done = release + (charge_time(arrival, arrival + amount)
                                          if effect != "S" else 0)
                        if effect in ("S", "CS"):
                            a, b, duration = (Fraction(schedule[k]) for k in ("a", "b", "D"))
                            service_start = max(a, release)
                            if service_start > b:
                                continue
                            done = max(done, service_start + duration)
                        new_pending = 0 if effect in ("S", "CS") else pending
                        new_sequence = sequence + ((site_id, effect),)
                        new_charges = charges + ((amount,) if effect != "S" else ())
                        new_energy = arrival + amount
                        outbound = table.leg(site.anchor_id, table.destination_anchor)
                        if (not new_pending and outbound.reachable and
                                new_energy - outbound.energy(consumption) >= reserve):
                            yield (new_sequence, new_charges)
                        if depth < bound:
                            progress = (outbound.actual_length if outbound.reachable
                                        else Fraction(10**30))
                            expanded.append(((new_pending, progress, done, -new_energy,
                                              new_sequence, new_charges),
                                             (site.anchor_id, new_energy, done, new_pending,
                                              new_sequence, new_charges)))
        expanded.sort(key=lambda row: row[0])
        frontier = [state for _, state in expanded[:64]]
        if not frontier:
            break
    return


@dataclass(frozen=True)
class RouteContract:
    graph_sha256: str
    router_sha256: str
    landmark_sha256: str
    tie_policy_sha256: str
    direction_policy_sha256: str
    numerical_contract_sha256: str
    tie_policy: str = TIE_POLICY
    direction_policy: str = "forward_per_source_v1"
    numerical_contract: str = NUMERICS

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if name.endswith("_sha256"):
                _sha(getattr(self, name), name)
        if (self.tie_policy != TIE_POLICY or self.direction_policy not in
                ("forward_per_source_v1", "explicit_per_leg_v1") or
                self.numerical_contract != NUMERICS):
            raise ValueError("Unrecognized selected-leg route policy")

    @classmethod
    def from_verified_bytes(cls, sources: Mapping, *, direction_policy: str) -> RouteContract:
        fields = {name for name in cls.__dataclass_fields__ if name.endswith("_sha256")}
        digests = _verified_sources(sources, fields)
        for name, literal in (("tie_policy_sha256", TIE_POLICY),
                              ("direction_policy_sha256", direction_policy),
                              ("numerical_contract_sha256", NUMERICS)):
            if sources[name][0] != literal.encode():
                raise ValueError(f"{name} bytes do not encode the declared policy")
        return cls(**digests, direction_policy=direction_policy)


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
            if (source != target and self.contract.direction_policy == "forward_per_source_v1"
                    and value.label_direction != "forward_from_source"):
                raise ValueError("Selected leg violates forward-per-source route policy")
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


class RegionBoundProvider:
    """Offline-checked directed Region bounds; online lookup scans no members.

    Optional ALT is capped by the immutable table's exact minimum selected-leg
    time for every source/Region/effect. This makes the online bound safe even
    if an external landmark source has a rounding or graph-policy mismatch.
    """

    def __init__(self, domain: QueryDomain, root, *,
                 landmarks: tuple[LandmarkDistances, ...] = (),
                 summaries: Mapping[int, RegionLandmarkSummary] | None = None):
        setup_started_ns = time.perf_counter_ns()
        from .hierarchy import Region
        if not isinstance(domain, QueryDomain) or not isinstance(root, Region):
            raise ValueError("Bound query and original Region root required")
        _, table = domain.open()
        summaries = {} if summaries is None else summaries
        self.domain = domain
        self.root = root
        self.online_queries = 0
        self.online_member_leg_lookups = 0
        regions = {}
        def visit(region):
            if region.identifier in regions or len(set(region.members)) != len(region.members):
                raise ValueError("Invalid Region identity or duplicate member")
            regions[region.identifier] = region
            if region.children:
                covered = [site for child in region.children for site in child.members]
                if len(covered) != len(set(covered)) or set(covered) != set(region.members):
                    raise ValueError("Children do not partition parent Region")
            for child in region.children:
                visit(child)
        visit(root)
        nonempty_ids = {region_id for region_id, region in regions.items() if region.members}
        if set(root.members) != set(table.sites) or set(summaries) not in (set(), nonempty_ids):
            raise ValueError("Region or summary coverage differs from candidate domain")
        if summaries:
            for region_id, region in regions.items():
                if not region.members:
                    continue
                summary = summaries[region_id]
                if (summary.graph_sha256 != domain.binding.graph_sha256 or
                        summary.landmark_sha256 != domain.binding.landmark_sha256 or
                        not check_region_summary_offline(region.members, landmarks, summary)):
                    raise ValueError("Uncertified Region landmark extrema")
            for distances in landmarks:
                for value in (*distances.from_landmark.values(), *distances.to_landmark.values()):
                    if not isinstance(value, (int, float)) or isnan(value) or value < 0 or (
                            isfinite(value) and (value > 2**53 or value != floor(value))):
                        raise ValueError("ALT distances require exact nonnegative integer seconds")
        self._action_bits = {action: 1 << index for index, action in enumerate(
            (site, effect) for site in sorted(table.sites)
            for effect in sorted(table.site(site).effects)
            if table.site(site).anchor_id != table.destination_anchor)}
        self._actions = {}
        self._action_masks = {}
        self.online_internal_member_accesses = 0
        self.online_leaf_action_reads = 0
        self.online_mask_word_work = 0
        for region_id, region in regions.items():
            for remaining in (0, 1):
                for effect in ("C", "S", "CS"):
                    selected = (() if effect in ("S", "CS") and not remaining else
                        tuple((site, effect) for site in region.members
                              if (site, effect) in self._action_bits))
                    self._actions[region_id, effect, remaining] = selected
                    self._action_masks[region_id, effect, remaining] = sum(
                        self._action_bits[action] for action in selected)
        self._bounds = {}
        self._single_incoming = {}
        for source in table.anchors:
            for site_id, effect in self._action_bits:
                leg = table.leg(source, table.site(site_id).anchor_id)
                self._single_incoming[source, site_id, effect] = leg.time if leg.reachable else None
            for region_id, region in regions.items():
                for effect in ("C", "S", "CS"):
                    candidates = []
                    for site_id in region.members:
                        site = table.site(site_id)
                        if effect not in site.effects or site.anchor_id == table.destination_anchor:
                            continue
                        incoming = table.leg(source, site.anchor_id)
                        if incoming.reachable:
                            candidates.append(incoming.time)
                    if not candidates:
                        self._bounds[source, region_id, effect] = None
                        continue
                    min_in = min(candidates)
                    if summaries:
                        alt = directed_alt_region_bound(source, landmarks,
                            summaries[region_id], graph_sha256=domain.binding.graph_sha256,
                            landmark_sha256=domain.binding.landmark_sha256,
                            member_set_sha256=member_set_digest(region.members))
                        incoming_bound = Fraction(floor(alt))
                        if incoming_bound > min_in:
                            raise ValueError("ALT exceeds an immutable selected-leg minimum")
                    else:
                        incoming_bound = min_in
                    # A selected Site->destination leg is not an onward bound:
                    # later semantic stops may yield a shorter nonmetric route.
                    self._bounds[source, region_id, effect] = incoming_bound
        self.setup_elapsed_ns = time.perf_counter_ns() - setup_started_ns
        self.setup_index_entries = (len(self._action_masks) + len(self._bounds) +
                                    len(self._single_incoming))
        self.setup_index_shallow_bytes = sum(map(sys.getsizeof,
            (self._action_bits, self._actions, self._action_masks,
             self._bounds, self._single_incoming)))

    def bound(self, problem, pieces, region, effect):
        if not pieces:
            return None, 0
        self.online_queries += 1
        state = pieces[0].state
        if effect in ("S", "CS") and not state.remaining_schedule:
            return None, 0
        incoming = self._bounds.get((state.anchor, region.identifier, effect))
        if incoming is None:
            return None, 0
        lower_time = min(p.slope * p.domain.affine_infimum(p.slope)[0] + p.intercept
                         for p in pieces)
        time = lower_time + incoming + problem.overhead
        if effect in ("S", "CS"):
            a, _, duration = problem.schedule
            time = max(a, time) + duration
        return (time - problem.start + problem.penalty * (state.stop_count + 1), 0)

    def singleton_bound(self, problem, pieces, site, effect):
        """Same safe next-action clock bound, indexed by one Site/effect."""
        self.online_queries += 1
        state = pieces[0].state
        incoming = self._single_incoming[state.anchor, site, effect]
        if incoming is None:
            return None
        lower_time = min(p.slope * p.domain.affine_infimum(p.slope)[0] + p.intercept
                         for p in pieces)
        time = lower_time + incoming + problem.overhead
        if effect in ("S", "CS"):
            a, _, duration = problem.schedule
            time = max(a, time) + duration
        return time - problem.start + problem.penalty * (state.stop_count + 1)

    def action_mask(self, region, effect, remaining):
        mask = self._action_masks[region.identifier, effect, remaining]
        self.online_mask_word_work += max(1, (mask.bit_length() + 63) // 64)
        return mask

    def mask_or(self, left, right):
        self.online_mask_word_work += max(1, (max(left, right).bit_length() + 63) // 64)
        return left | right

    def mask_overlap(self, left, right):
        self.online_mask_word_work += max(1, (max(left, right).bit_length() + 63) // 64)
        return bool(left & right)

    def mask_equal(self, left, right):
        self.online_mask_word_work += max(1, (max(left, right).bit_length() + 63) // 64)
        return left == right

    def leaf_actions(self, region, effect, remaining):
        if region.children:
            self.online_internal_member_accesses += 1
            raise ValueError("Internal Region member expansion is forbidden")
        self.online_leaf_action_reads += 1
        return self._actions[region.identifier, effect, remaining]

    def action_bit(self, action):
        return self._action_bits[action]


@dataclass(frozen=True)
class DeployablePairResult:
    certificate: SeedDepthCertificate
    flat: SearchOutcome
    hier: SearchOutcome
    flat_attempted_extensions: int
    hier_leaf_actions: int
    hier_bound_member_scans: int
    flat_provider_queries: int
    hier_provider_queries: int
    hier_online_internal_member_accesses: int
    hier_online_leaf_action_reads: int
    hier_online_mask_word_work: int
    region_setup_elapsed_ns: int
    region_setup_index_entries: int
    region_setup_index_shallow_bytes: int
    shared_seed_cache_misses: int
    flat_cache_hits: int
    flat_cache_misses: int
    hier_cache_hits: int
    hier_cache_misses: int


def prepared_checkpoint_bytes(certificate: SeedDepthCertificate,
                              hierarchy_bytes: bytes) -> bytes:
    """Fail-closed restart token before OPEN exists; no partial-state resume."""
    if not isinstance(certificate, SeedDepthCertificate) or type(hierarchy_bytes) is not bytes:
        raise ValueError("Bound seed certificate and original hierarchy bytes required")
    if hashlib.sha256(hierarchy_bytes).hexdigest() != certificate.domain.binding.hierarchy_sha256:
        raise ValueError("Hierarchy differs from checkpoint domain")
    payload = {"schema": "hiroute.m5d.prepared_restart.v1",
               "phase": "before_search_no_open_state",
               "domain": {name: getattr(certificate.domain.binding, name)
                          for name in DomainBinding.__dataclass_fields__},
               "table_sha256": certificate.domain.table_sha256,
               "seed_witness_sha256": certificate.seed.witness_sha256,
               "verifier_closure_sha256": certificate.seed.independent_verifier_sha256,
               "certified_max_depth": certificate.max_depth,
               "hierarchy_sha256": certificate.domain.binding.hierarchy_sha256}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _outcome_from_terminal(binding: DomainBinding, bounded) -> SearchOutcome:
    from . import provenance
    result = bounded.result
    if result.status == "attained_optimum":
        j, q, h, pi = result.key
        if result.witness is None:
            raise ValueError("Attained key lacks executable witness")
        payload = json.dumps(provenance.witness_dict(result.witness),
                             sort_keys=True, separators=(",", ":")).encode()
        return SearchOutcome(binding, SolveStatus.ATTAINED_OPTIMUM, j, q, h, pi,
                             hashlib.sha256(payload).hexdigest())
    if result.status == "infimum_unattained" and result.unattained_component == "J":
        return SearchOutcome(binding, SolveStatus.INFIMUM_UNATTAINED_J,
                             j=result.primary_infimum)
    if result.status == "infimum_unattained" and result.unattained_component == "Q":
        return SearchOutcome(binding, SolveStatus.INFIMUM_UNATTAINED_Q,
                             j=result.primary_infimum, q=result.secondary_infimum)
    raise ValueError("Certified seed contradicts empty or unknown terminal result")


def same_exact_outcome(left: SearchOutcome, right: SearchOutcome) -> bool:
    """Compare mathematical status/key, not equally valid witness encodings."""
    return (left.domain == right.domain and
            (left.status, left.j, left.q, left.h, left.pi) ==
            (right.status, right.j, right.q, right.h, right.pi))


def _independent_attained_replay(domain: QueryDomain, bounded,
                                 outcome: SearchOutcome, max_depth: int) -> None:
    if outcome.status is not SolveStatus.ATTAINED_OPTIMUM:
        return
    from validation.reference5.real_solver import replay_real_witness_bytes
    witness = bounded.result.witness
    if outcome.h > max_depth:
        raise ValueError("Attained witness exceeds certified search depth")
    charges = tuple(event.departure_energy - event.arrival_energy
                    for event in witness.events if event.effect in ("C", "CS"))
    query = _json_object(domain.query_bytes)
    query["H_ref"] = max(query["H_ref"], outcome.h)
    replay = replay_real_witness_bytes(query,
        domain.table_bytes, domain.table_sha256, witness.pi, charges)
    if (replay["J"], replay["Q_total"], replay["H"], replay["site_action_tuple"]) != (
            outcome.j, outcome.q, outcome.h, outcome.pi):
        raise ValueError("Independent witness replay disagrees with exact outcome")


def solve_deployable_pair(certificate: SeedDepthCertificate, hierarchy_bytes: bytes,
                          verifier_source_sha256: Mapping[str, str], *,
                          landmarks: tuple[LandmarkDistances, ...] = (),
                          summaries: Mapping[int, RegionLandmarkSummary] | None = None,
                          selected_leg_provider=None,
                          prepared_checkpoint: bytes | None = None
                          ) -> DeployablePairResult:
    """Run exact FLAT/HIER over the same certified finite-depth domain.

    Rebuild the seed proof from immutable bytes before search. No external
    certificate field is trusted as a search cap or pruning incumbent. The
    accepted bounded solvers retain their old diagnostic public entrypoints.
    """
    from .bounded import _solve_problem
    from .hierarchy import _solve_hierarchical_problem
    from .real_adapter import RealProblem, original_region_view
    from .real_legs import restrict_frozen_tree
    if not isinstance(certificate, SeedDepthCertificate) or type(hierarchy_bytes) is not bytes:
        raise ValueError("Verified seed and frozen original hierarchy bytes required")
    domain = certificate.domain
    fresh = construct_verified_seed(domain, verifier_source_sha256)
    if not isinstance(fresh, SeedDepthCertificate) or fresh != certificate:
        raise ValueError("Seed certificate failed independent replay or depth recheck")
    if prepared_checkpoint is not None and (
            type(prepared_checkpoint) is not bytes or
            prepared_checkpoint != prepared_checkpoint_bytes(fresh, hierarchy_bytes)):
        raise ValueError("Checkpoint cannot resume an unverified or partial OPEN state")
    query, table = domain.open()
    restriction = restrict_frozen_tree(hierarchy_bytes, domain.binding.hierarchy_sha256,
                                       list(table.sites))
    root = original_region_view(table, restriction)
    bounded_query = dict(query, H_ref=fresh.max_depth)
    provider = RegionBoundProvider(domain, root, landmarks=landmarks, summaries=summaries)
    if selected_leg_provider is not None:
        from .road_provider import RoadSelectedLegProvider
        if (not isinstance(selected_leg_provider, RoadSelectedLegProvider) or
                selected_leg_provider.table.payload_sha256 != table.payload_sha256):
            raise ValueError("Road provider must bind the identical frozen table")
    def selected_leg(source, target):
        leg = (table.leg(source, target) if selected_leg_provider is None
               else selected_leg_provider.leg(source, target))
        if leg != table.leg(source, target):
            raise ValueError("Road provider disagrees with the bound selected leg")
        return leg
    route_contract = RouteContract(domain.binding.graph_sha256,
        hashlib.sha256(json.dumps(table.router_sha256, sort_keys=True).encode()).hexdigest(),
        domain.binding.landmark_sha256, hashlib.sha256(TIE_POLICY.encode()).hexdigest(),
        hashlib.sha256(table.direction_policy.encode()).hexdigest(),
        hashlib.sha256(NUMERICS.encode()).hexdigest(), direction_policy=table.direction_policy)
    flat_cache = SelectedLegCache(route_contract, selected_leg)
    hier_cache = SelectedLegCache(route_contract, selected_leg)
    current = table.origin_anchor
    for site_id, _ in fresh.sequence:
        target = table.site(site_id).anchor_id
        flat_cache.leg(current, target)
        hier_cache.leg(current, target)
        current = target
    flat_cache.leg(current, table.destination_anchor)
    hier_cache.leg(current, table.destination_anchor)
    if (flat_cache.misses, flat_cache.hits) != (hier_cache.misses, hier_cache.hits):
        raise ValueError("FLAT/HIER seed cache preparation differs")
    shared_seed_cache_misses = flat_cache.misses
    flat = _solve_problem(RealProblem(bounded_query, table, leg_cache=flat_cache),
                          verified_primary_upper=fresh.seed.primary_j,
                          singleton_bound=provider.singleton_bound)
    flat_provider_queries = provider.online_queries
    hier = _solve_hierarchical_problem(RealProblem(bounded_query, table, leg_cache=hier_cache), True, root,
                                       verified_primary_upper=fresh.seed.primary_j,
                                       bound_provider=provider)
    flat_outcome = _outcome_from_terminal(domain.binding, flat)
    hier_outcome = _outcome_from_terminal(domain.binding, hier.bounded)
    _independent_attained_replay(domain, flat, flat_outcome, fresh.max_depth)
    _independent_attained_replay(domain, hier.bounded, hier_outcome, fresh.max_depth)
    if not same_exact_outcome(flat_outcome, hier_outcome):
        raise ValueError("FLAT/HIER exact outcomes disagree in the certified domain")
    return DeployablePairResult(fresh, flat_outcome, hier_outcome,
                                flat.attempted_extensions, hier.leaf_actions,
                                hier.bound_member_scans, flat_provider_queries,
                                provider.online_queries - flat_provider_queries,
                                provider.online_internal_member_accesses,
                                provider.online_leaf_action_reads,
                                provider.online_mask_word_work,
                                provider.setup_elapsed_ns,
                                provider.setup_index_entries,
                                provider.setup_index_shallow_bytes,
                                shared_seed_cache_misses,
                                flat_cache.hits, flat_cache.misses,
                                hier_cache.hits, hier_cache.misses)
