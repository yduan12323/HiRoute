"""Versioned public problem, solver, result, witness, and run contracts.

This module uses only the Python standard library. Numeric inputs are exact
integers or rational strings; binary64 values are rejected at the boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

SNAPSHOT_SCHEMA = "hiroute.problem_snapshot.v1"
SOLVER_SCHEMA = "hiroute.solver_config.v1"
RESULT_SCHEMA = "hiroute.solve_result.v1"
WITNESS_SCHEMA = "hiroute.witness.v1"
MANIFEST_SCHEMA = "hiroute.run_manifest.v1"
_RATIONAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?$")


def exact(value: Any, name: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{name} must be an integer or exact rational string")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str) and _RATIONAL.fullmatch(value):
        return Fraction(value)
    raise TypeError(f"{name} must be an integer or canonical rational string")


def rational_text(value: Any, name: str) -> str:
    return str(exact(value, name))


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def content_id(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class ProblemSnapshot:
    model_contract_id: str
    numerical_contract_id: str
    origin: str
    destination: str
    departure_time_s: str
    initial_energy_kwh: str
    capacity_kwh: str
    minimum_energy_kwh: str
    destination_reserve_kwh: str
    stop_overhead_s: str
    stop_penalty_s: str
    consumption_kwh_per_m: str
    schedule: Mapping[str, str] | None
    initial_remaining_schedule: int
    candidate_order: tuple[str, ...]
    site_capabilities: Mapping[str, tuple[str, ...]]
    charging_curve: tuple[tuple[str, str, str, str], ...]
    directed_edges: tuple[Mapping[str, str], ...]
    selected_leg_contract: str
    graph_or_leg_identity: str
    depth_mode: str
    depth_limit: int
    depth_certificate_reference: str | None = None
    semantic_problem_id: str = field(default="", compare=True)

    def __post_init__(self) -> None:
        for key in ("model_contract_id", "numerical_contract_id", "origin",
                    "destination", "selected_leg_contract", "graph_or_leg_identity"):
            _identifier(getattr(self, key), key)
        if self.schedule is not None:
            object.__setattr__(self, "schedule", MappingProxyType(dict(self.schedule)))
        object.__setattr__(self, "candidate_order", tuple(self.candidate_order))
        object.__setattr__(self, "site_capabilities", MappingProxyType(
            {str(k): tuple(v) for k, v in self.site_capabilities.items()}))
        object.__setattr__(self, "charging_curve", tuple(tuple(row) for row in self.charging_curve))
        object.__setattr__(self, "directed_edges", tuple(
            MappingProxyType(dict(row)) for row in self.directed_edges))
        numeric = ("departure_time_s", "initial_energy_kwh", "capacity_kwh",
                   "minimum_energy_kwh", "destination_reserve_kwh",
                   "stop_overhead_s", "stop_penalty_s", "consumption_kwh_per_m")
        for name in numeric:
            rational_text(getattr(self, name), name)
        initial = exact(self.initial_energy_kwh, "initial_energy_kwh")
        capacity = exact(self.capacity_kwh, "capacity_kwh")
        floor = exact(self.minimum_energy_kwh, "minimum_energy_kwh")
        reserve = exact(self.destination_reserve_kwh, "destination_reserve_kwh")
        if capacity <= 0 or floor < 0 or not floor <= initial <= capacity:
            raise ValueError("Energy values violate floor/capacity bounds")
        if not floor <= reserve <= capacity:
            raise ValueError("Destination reserve is outside floor/capacity")
        if exact(self.stop_overhead_s, "stop_overhead_s") <= 0:
            raise ValueError("Stop overhead must be positive")
        if exact(self.stop_penalty_s, "stop_penalty_s") < 0:
            raise ValueError("Stop penalty must be nonnegative")
        if exact(self.consumption_kwh_per_m, "consumption_kwh_per_m") < 0:
            raise ValueError("Consumption rate must be nonnegative")
        if self.schedule is None:
            if self.initial_remaining_schedule != 0:
                raise ValueError("Schedule state cannot be pending without a schedule")
        else:
            if set(self.schedule) != {"a", "b", "D"}:
                raise ValueError("Schedule requires exactly a, b, D")
            for key, value in self.schedule.items():
                rational_text(value, f"schedule.{key}")
            a, b, duration = (exact(self.schedule[k], f"schedule.{k}") for k in ("a", "b", "D"))
            if a > b or duration < 0:
                raise ValueError("Invalid schedule window or duration")
        if type(self.initial_remaining_schedule) is not int or self.initial_remaining_schedule not in (0, 1):
            raise ValueError("initial_remaining_schedule must be 0 or 1")
        if len(set(self.candidate_order)) != len(self.candidate_order):
            raise ValueError("candidate_order must be unique; an empty candidate set is valid")
        if set(self.candidate_order) != set(self.site_capabilities):
            raise ValueError("Candidate order and Site capability identities differ")
        for site, effects in self.site_capabilities.items():
            _identifier(site, "site id")
            if not effects or len(set(effects)) != len(effects) or not set(effects) <= {"C", "S", "CS"}:
                raise ValueError(f"Invalid effect set for Site {site}")
        if self.depth_mode not in {"diagnostic_cap", "seed_derived"}:
            raise ValueError("depth_mode must explicitly declare diagnostic_cap or seed_derived")
        if type(self.depth_limit) is not int or self.depth_limit < 0:
            raise ValueError("depth_limit must be a nonnegative integer")
        if self.depth_certificate_reference is not None and not isinstance(self.depth_certificate_reference, str):
            raise ValueError("depth_certificate_reference must be a string")
        if self.depth_mode == "seed_derived" and not self.depth_certificate_reference:
            raise ValueError("seed_derived depth requires a certificate reference")
        if self.depth_mode == "diagnostic_cap" and self.depth_certificate_reference is not None:
            raise ValueError("diagnostic cap cannot carry a seed certificate")
        for i, segment in enumerate(self.charging_curve):
            if len(segment) != 4:
                raise ValueError(f"Charging segment {i} must have four rational values")
            for j, value in enumerate(segment):
                rational_text(value, f"charging_curve[{i}][{j}]")
        edge_ids = set()
        for i, edge in enumerate(self.directed_edges):
            if set(edge) - {"source", "target", "time_s", "length_m", "edge_id"}:
                raise ValueError(f"Unknown directed edge field at index {i}")
            for key in ("source", "target"):
                _identifier(edge.get(key), f"directed_edges[{i}].{key}")
            identity = edge.get("edge_id", f"input:{i:08d}")
            _identifier(identity, f"directed_edges[{i}].edge_id")
            if identity in edge_ids:
                raise ValueError("Directed edge IDs must be unique")
            edge_ids.add(identity)
            for key in ("time_s", "length_m"):
                if exact(edge.get(key), f"directed_edges[{i}].{key}") <= 0:
                    raise ValueError(f"Directed edge {key} must be positive")
        computed = content_id(self._identity_payload())
        # The identifier is derived locally from the validated problem. A
        # caller may omit it; an old serialized value is informational only.
        object.__setattr__(self, "semantic_problem_id", computed)

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "model_contract_id": self.model_contract_id,
            "numerical_contract_id": self.numerical_contract_id,
            "origin": self.origin, "destination": self.destination,
            "departure_time_s": rational_text(self.departure_time_s, "departure_time_s"),
            "initial_energy_kwh": rational_text(self.initial_energy_kwh, "initial_energy_kwh"),
            "capacity_kwh": rational_text(self.capacity_kwh, "capacity_kwh"),
            "minimum_energy_kwh": rational_text(self.minimum_energy_kwh, "minimum_energy_kwh"),
            "destination_reserve_kwh": rational_text(self.destination_reserve_kwh, "destination_reserve_kwh"),
            "stop_overhead_s": rational_text(self.stop_overhead_s, "stop_overhead_s"),
            "stop_penalty_s": rational_text(self.stop_penalty_s, "stop_penalty_s"),
            "consumption_kwh_per_m": rational_text(self.consumption_kwh_per_m, "consumption_kwh_per_m"),
            "schedule": None if self.schedule is None else {
                k: rational_text(self.schedule[k], f"schedule.{k}") for k in ("a", "b", "D")},
            "initial_remaining_schedule": self.initial_remaining_schedule,
            "candidate_order": list(self.candidate_order),
            "site_capabilities": {k: list(self.site_capabilities[k]) for k in sorted(self.site_capabilities)},
            "charging_curve": [[rational_text(x, "charging_curve") for x in row] for row in self.charging_curve],
            "directed_edges": [dict(row) for row in self.directed_edges],
            "selected_leg_contract": self.selected_leg_contract,
            "graph_or_leg_identity": self.graph_or_leg_identity,
            "depth_mode": self.depth_mode, "depth_limit": self.depth_limit,
            "depth_certificate_reference": self.depth_certificate_reference,
        }

    def to_dict(self) -> dict[str, Any]:
        value = self._identity_payload()
        value["semantic_problem_id"] = self.semantic_problem_id
        return value

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "ProblemSnapshot":
        required = {
            "schema", "model_contract_id", "numerical_contract_id", "origin", "destination",
            "departure_time_s", "initial_energy_kwh", "capacity_kwh", "minimum_energy_kwh",
            "destination_reserve_kwh", "stop_overhead_s", "stop_penalty_s",
            "consumption_kwh_per_m", "schedule", "initial_remaining_schedule",
            "candidate_order", "site_capabilities", "charging_curve", "directed_edges",
            "selected_leg_contract", "graph_or_leg_identity", "depth_mode", "depth_limit",
            "depth_certificate_reference",
        }
        allowed = required | {"semantic_problem_id"}
        if set(obj) - allowed or not required <= set(obj):
            raise ValueError("Snapshot fields must exactly match the declared schema")
        if obj["schema"] != SNAPSHOT_SCHEMA:
            raise ValueError("Unsupported snapshot schema")
        return cls(
            model_contract_id=obj["model_contract_id"],
            numerical_contract_id=obj["numerical_contract_id"],
            origin=obj["origin"], destination=obj["destination"],
            departure_time_s=rational_text(obj["departure_time_s"], "departure_time_s"),
            initial_energy_kwh=rational_text(obj["initial_energy_kwh"], "initial_energy_kwh"),
            capacity_kwh=rational_text(obj["capacity_kwh"], "capacity_kwh"),
            minimum_energy_kwh=rational_text(obj["minimum_energy_kwh"], "minimum_energy_kwh"),
            destination_reserve_kwh=rational_text(obj["destination_reserve_kwh"], "destination_reserve_kwh"),
            stop_overhead_s=rational_text(obj["stop_overhead_s"], "stop_overhead_s"),
            stop_penalty_s=rational_text(obj["stop_penalty_s"], "stop_penalty_s"),
            consumption_kwh_per_m=rational_text(obj["consumption_kwh_per_m"], "consumption_kwh_per_m"),
            schedule=None if obj["schedule"] is None else {
                k: rational_text(obj["schedule"][k], f"schedule.{k}") for k in ("a", "b", "D")},
            initial_remaining_schedule=obj["initial_remaining_schedule"],
            candidate_order=tuple(obj["candidate_order"]),
            site_capabilities={k: tuple(v) for k, v in obj["site_capabilities"].items()},
            charging_curve=tuple(tuple(rational_text(x, "charging_curve") for x in row)
                                 for row in obj["charging_curve"]),
            directed_edges=tuple({**row,
                                  "time_s": rational_text(row["time_s"], "edge.time_s"),
                                  "length_m": rational_text(row["length_m"], "edge.length_m")}
                                 for row in obj["directed_edges"]),
            selected_leg_contract=obj["selected_leg_contract"],
            graph_or_leg_identity=obj["graph_or_leg_identity"],
            depth_mode=obj["depth_mode"], depth_limit=obj["depth_limit"],
            depth_certificate_reference=obj["depth_certificate_reference"],
            semantic_problem_id=obj.get("semantic_problem_id", ""),
        )


@dataclass(frozen=True)
class SolverConfig:
    method: str
    reduction_profile: str
    charging_operator_profile: str
    coalescing_profile: str
    bound_profile: str
    seed_policy: str
    deterministic_tie_policy: str

    def __post_init__(self) -> None:
        if self.method not in {"flat", "flat_bb", "hier"}:
            raise ValueError("method must be flat, flat_bb or hier")
        for key in ("reduction_profile", "charging_operator_profile", "coalescing_profile",
                    "bound_profile", "seed_policy", "deterministic_tie_policy"):
            _identifier(getattr(self, key), key)

    def to_dict(self) -> dict[str, str]:
        return {"schema": SOLVER_SCHEMA, "method": self.method,
                "reduction_profile": self.reduction_profile,
                "charging_operator_profile": self.charging_operator_profile,
                "coalescing_profile": self.coalescing_profile,
                "bound_profile": self.bound_profile, "seed_policy": self.seed_policy,
                "deterministic_tie_policy": self.deterministic_tie_policy}

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "SolverConfig":
        if obj.get("schema") != SOLVER_SCHEMA or set(obj) != {
            "schema", "method", "reduction_profile", "charging_operator_profile",
            "coalescing_profile", "bound_profile", "seed_policy", "deterministic_tie_policy"}:
            raise ValueError("SolverConfig fields must exactly match v1 schema")
        return cls(**{k: obj[k] for k in (
            "method", "reduction_profile", "charging_operator_profile", "coalescing_profile",
            "bound_profile", "seed_policy", "deterministic_tie_policy")})


@dataclass(frozen=True)
class Witness:
    actions: tuple[tuple[str, str], ...]
    charges_kwh: tuple[str, ...]
    route_legs: tuple[Mapping[str, Any], ...]
    events: tuple[Mapping[str, Any], ...]
    witness_schema: str = WITNESS_SCHEMA

    def __post_init__(self) -> None:
        if self.witness_schema != WITNESS_SCHEMA:
            raise ValueError("Unsupported witness schema")
        if len(self.charges_kwh) != sum(a in {"C", "CS"} for _, a in self.actions):
            raise ValueError("Charge vector and action dimensions differ")
        for charge in self.charges_kwh:
            if exact(charge, "charge") <= 0:
                raise ValueError("Every C/CS witness charge must be strictly positive")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.witness_schema, "actions": [list(x) for x in self.actions],
                "charges_kwh": list(self.charges_kwh),
                "route_legs": [dict(x) for x in self.route_legs],
                "events": [dict(x) for x in self.events]}


@dataclass(frozen=True)
class SolveResult:
    execution_status: str
    mathematical_status: str
    verification_status: str
    semantic_problem_id: str
    representation_id: str
    build_id: str
    run_id: str
    key: tuple[Any, ...] | None = None
    witness: Witness | None = None
    primary_infimum: str | None = None
    secondary_infimum: str | None = None
    backend: str = "core"
    backend_evidence: Mapping[str, Any] = field(default_factory=dict)
    schema: str = RESULT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != RESULT_SCHEMA:
            raise ValueError("Unsupported result schema")
        executions = {"completed", "time_limit", "memory_limit", "interrupted",
                      "invalid_input", "unsupported_model", "error"}
        mathematics = {"attained_optimum", "primary_unattained", "secondary_unattained",
                       "infeasible_within_declared_domain", "unknown"}
        verifications = {"not_run", "witness_verified", "independently_optimality_verified", "failed"}
        if self.execution_status not in executions:
            raise ValueError("Unknown execution status")
        if self.mathematical_status not in mathematics:
            raise ValueError("Unknown mathematical status")
        if self.verification_status not in verifications:
            raise ValueError("Unknown verification status")
        for name in ("semantic_problem_id", "representation_id", "build_id", "run_id", "backend"):
            _identifier(getattr(self, name), name)
        if not isinstance(self.backend_evidence, Mapping):
            raise TypeError("backend_evidence must be a mapping")
        object.__setattr__(self, "backend_evidence", MappingProxyType(dict(self.backend_evidence)))
        if self.execution_status != "completed" and self.mathematical_status != "unknown":
            raise ValueError("Non-completed execution cannot claim a mathematical conclusion")
        if self.execution_status in {"invalid_input", "unsupported_model", "error"} and self.witness is not None:
            raise ValueError("Rejected or errored execution cannot carry a feasible witness")
        if self.mathematical_status == "attained_optimum":
            if self.execution_status != "completed" or self.key is None:
                raise ValueError("An attained optimum requires completed execution and its full key")
            if not isinstance(self.key, (tuple, list)) or len(self.key) != 4:
                raise ValueError("An attained optimum key must contain (J,Q,H,Pi)")
            j, q, h, actions = self.key
            normalized = (rational_text(j, "key.J"), rational_text(q, "key.Q"), h,
                          tuple(tuple(pair) for pair in actions))
            if type(h) is not int or h < 0:
                raise ValueError("Key H must be a nonnegative integer")
            if any(len(pair) != 2 or not all(isinstance(x, str) and x for x in pair)
                   for pair in normalized[3]):
                raise ValueError("Key Pi must contain node/action string pairs")
            if any(action not in {"C", "S", "CS"} for _, action in normalized[3]):
                raise ValueError("Key Pi contains an unsupported Site action")
            if h != len(normalized[3]):
                raise ValueError("Key H must equal the number of Site actions in Pi")
            object.__setattr__(self, "key", normalized)
            if self.witness is not None and tuple(self.witness.actions) != normalized[3]:
                raise ValueError("Attained key Pi must match the replayed witness actions")
        elif self.key is not None:
            raise ValueError("Only an attained optimum may carry a complete lexicographic key")
        if self.mathematical_status == "primary_unattained":
            if self.execution_status != "completed" or self.primary_infimum is None:
                raise ValueError("Primary nonattainment requires completed execution and its infimum")
            if self.secondary_infimum is not None:
                raise ValueError("Primary nonattainment cannot claim a secondary infimum")
        elif self.primary_infimum is not None and self.mathematical_status != "secondary_unattained":
            raise ValueError("Primary infimum is only defined when the primary value is known")
        if self.mathematical_status == "secondary_unattained":
            if (self.execution_status != "completed" or self.witness is not None
                    or self.primary_infimum is None or self.secondary_infimum is None):
                raise ValueError("Secondary nonattainment requires the attained primary value, secondary infimum, and no witness")
        elif self.secondary_infimum is not None:
            raise ValueError("Secondary infimum is only defined for secondary_unattained")
        if self.mathematical_status == "infeasible_within_declared_domain":
            if self.execution_status != "completed" or self.key is not None or self.witness is not None:
                raise ValueError("Infeasibility requires completed execution and cannot carry a witness or key")
        if self.verification_status == "witness_verified" and self.witness is None:
            raise ValueError("witness_verified requires a witness")
        if self.verification_status == "independently_optimality_verified" and self.mathematical_status != "attained_optimum":
            raise ValueError("Independent optimality verification requires an attained optimum")
        if self.verification_status == "failed" and self.mathematical_status != "unknown":
            raise ValueError("Failed verification cannot accompany a mathematical conclusion")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "execution_status": self.execution_status,
                "mathematical_status": self.mathematical_status,
                "verification_status": self.verification_status,
                "semantic_problem_id": self.semantic_problem_id,
                "representation_id": self.representation_id, "build_id": self.build_id,
                "run_id": self.run_id, "key": self.key,
                "witness": None if self.witness is None else self.witness.to_dict(),
                "primary_infimum": self.primary_infimum, "secondary_infimum": self.secondary_infimum,
                "backend": self.backend, "backend_evidence": dict(self.backend_evidence)}


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    source_commit: str
    source_dirty: bool
    build_artifact_hash: str
    effective_code_identity: str
    dependency_lock_identity: str
    native_toolchain_identity: str
    problem_id: str
    solver_config_id: str
    input_artifact_ids: tuple[str, ...]
    host_scope: str
    resource_policy: Mapping[str, Any]
    started_at: str
    finished_at: str | None = None
    output_index: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MANIFEST_SCHEMA, **self.__dict__,
                "input_artifact_ids": list(self.input_artifact_ids),
                "resource_policy": dict(self.resource_policy)}
