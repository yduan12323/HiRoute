"""Metadata-only intake of the original, byte-pinned A28/B64 population.

This module has no solver, graph, optimizer, or historical runner dependency.
Historical answers describe the recovered checkpoint, not current acceptance.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Mapping


_A = "results/milestone_5_coalescing_prototype/frozen_A/"
_B = "results/milestone_5_acceptance_b64/acceptance_populations/"


@dataclass(frozen=True)
class SourcePin:
    path: str
    sha256: str
    population: str
    count: int


INPUT_PINS = (
    SourcePin(_A + "physical_cases_h4.json",
              "3d79795956e63cf5ada6ac4d73a49e5a70598169701447eda4b226d664b614f2", "h4", 24),
    SourcePin(_A + "physical_supplement.json",
              "1b09f4895df68dd67e0362f88988c9f05c10e9bbf628ded24807bf577bc43a30", "supplement", 3),
    SourcePin(_A + "physical_merge_supplement.json",
              "121770eb0bef153d313dea7b02d7ab8156f846b3331cf896676a3cf72b5b6bd4", "merge", 1),
    SourcePin(_B + "stage_b/cases.json",
              "61a1d3f86da1c750ef127f7827f4ef68d2b5aa21babc314691ce095ed498f037", "B", 64),
)
RESULT_PINS = (
    SourcePin(_A + "FINAL_STAGE_A_RESULTS.json",
              "163949bdf649412ecdd094b07de5ddbd8a436c7db4ca360851fe98d523de5c5c", "A", 28),
    SourcePin(_B + "evaluation_v2/B64_RESULTS.json",
              "a45979a2a49909d61b25df46d35237120f85c46c8c266cf13b78c7ed627bb025", "B", 64),
)
SOURCE_PINS = INPUT_PINS + RESULT_PINS
MAX_SOURCE_BYTES = 1024 * 1024
_SCALARS = ("start_time_s", "initial_energy_kwh", "capacity_kwh", "minimum_energy_kwh",
            "reserve_kwh", "consumption_kwh_per_m", "overhead_s", "lambda_stop_s")
_REQUIRED = set(_SCALARS) | {"case_id", "H_ref", "origin", "destination", "sites",
                            "charging_segments", "edges", "schedule", "independent_expected"}


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _text(value, name):
    _require(type(value) is str and bool(value), f"Nonempty string required: {name}")


def _exact(value, name):
    _require(type(value) in (str, int), f"Exact rational scalar required: {name}")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"Invalid exact rational: {name}") from exc


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    def finite_float(value):
        result = float(value)
        _require(math.isfinite(result), "Nonfinite JSON number")
        return result

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=finite_float)


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if type(value) is list:
        return tuple(_freeze(v) for v in value)
    return value


def _expectation(value, *, extras=False):
    _require(type(value) is dict, "Expected-result object required")
    status = value.get("status")
    _require(type(status) is str, "Expected-result status string required")
    fields = {
        "attained_optimum": {"status", "J", "Q_total", "H", "site_action_tuple"},
        "primary_unattained": {"status", "primary_infimum"},
        "secondary_unattained": {"status", "J", "secondary_infimum"},
        "infeasible_within_H_ref": {"status"},
    }
    _require(status in fields, f"Unknown historical status: {status}")
    required = fields[status]
    _require(required <= value.keys(), "Missing expected-result fields")
    _require(extras or required == value.keys(), "Unexpected historical result fields")
    for key in required - {"status", "H", "site_action_tuple"}:
        _exact(value[key], key)
    if status == "attained_optimum":
        _require(type(value["H"]) is int and 0 <= value["H"] <= 4, "Exact bounded integer H required")
        actions = value["site_action_tuple"]
        _require(type(actions) is list and len(actions) == value["H"], "Site/action tuple length mismatch")
        for action in actions:
            _require(type(action) is list and len(action) == 2, "Site/action pair required")
            _text(action[0], "site action identifier")
            _require(type(action[1]) is str and action[1] in ("C", "S", "CS"), "Unknown site action")
    return _freeze(value)


def _case_rows(raw):
    """Validate input shape/types only; do not evaluate physical feasibility."""
    rows = _json(raw)
    _require(type(rows) is list, "Case array required")
    seen = set()
    for row in rows:
        _require(type(row) is dict and _REQUIRED <= row.keys(), "Missing required case fields")
        case_id = row["case_id"]
        _text(case_id, "case_id")
        _require(case_id not in seen, f"Duplicate case ID: {case_id}")
        seen.add(case_id)
        _require(type(row["H_ref"]) is int and row["H_ref"] == 4, "Exact integer H_ref=4 required")
        for name in ("origin", "destination"):
            _text(row[name], name)
        for name in _SCALARS:
            _exact(row[name], name)
        sites = row["sites"]
        _require(type(sites) is dict, "Site object required")
        for site, effects in sites.items():
            _text(site, "site identifier")
            _require(type(effects) is list and all(type(e) is str and e in ("C", "S", "CS") for e in effects),
                     "Site capabilities must be C/S/CS strings")
            _require(len(set(effects)) == len(effects), "Duplicate site capability")
        schedule = row["schedule"]
        if schedule is not None:
            _require(type(schedule) is dict and set(schedule) == {"a", "b", "D"}, "Malformed schedule")
            for name, value in schedule.items():
                _exact(value, f"schedule.{name}")
        segments = row["charging_segments"]
        _require(type(segments) is list, "Charging segment array required")
        for segment in segments:
            _require(type(segment) is list and len(segment) == 4, "Four charging coefficients required")
            for value in segment:
                _exact(value, "charging coefficient")
        edges = row["edges"]
        _require(type(edges) is list, "Edge array required")
        edge_ids = set()
        required = {"source", "target", "time_s", "length_m"}
        for edge in edges:
            _require(type(edge) is dict and required <= edge.keys() <= required | {"edge_id"}, "Malformed edge")
            for name in ("source", "target"):
                _text(edge[name], name)
            for name in ("time_s", "length_m"):
                _exact(edge[name], name)
            if "edge_id" in edge:
                _text(edge["edge_id"], "edge_id")
                _require(edge["edge_id"] not in edge_ids, "Duplicate edge ID")
                edge_ids.add(edge["edge_id"])
        _expectation(row["independent_expected"], extras=True)
    return rows


@dataclass(frozen=True)
class SourceArtifact:
    pin: SourcePin
    raw_bytes: bytes


@dataclass(frozen=True)
class FrozenCase:
    case_id: str
    population: str
    H_ref: int
    source: SourceArtifact
    source_index: int
    historical_source: SourceArtifact
    historical_expected: Mapping

    def original_case(self):
        """Return a fresh JSON object with original scalar types and metadata."""
        return _json(self.source.raw_bytes)[self.source_index]


@dataclass(frozen=True)
class HierVariant:
    case: FrozenCase
    dominance: bool
    mode: str = "HIER"

    def __post_init__(self):
        _require(type(self.dominance) is bool, "Exact boolean dominance required")
        _require(type(self.mode) is str and self.mode == "HIER", "Registry is HIER-only")

    @property
    def variant_id(self):
        return f"{self.case.case_id}::HIER::D-{'on' if self.dominance else 'off'}"


@dataclass(frozen=True)
class FrozenABRegistry:
    cases: tuple[FrozenCase, ...]
    variants: tuple[HierVariant, ...]
    sources: tuple[SourceArtifact, ...]

    def summary(self):
        return {
            "schema": "hiroute.frozen_ab_registry.v1",
            "status": "metadata_only_intake_validated",
            "physical_cases": len(self.cases), "HIER_variants": len(self.variants), "H_ref": 4,
            "populations": dict(Counter(c.population for c in self.cases)),
            "historical_expected_status_counts": dict(Counter(c.historical_expected["status"] for c in self.cases)),
            "source_sha256": {s.pin.path: s.pin.sha256 for s in self.sources},
            "solver_executed": False, "current_acceptance_established": False,
            "recorded_capture_wrapper": "absent_from_backup_remains_to_reconstruct",
            "A04": "algebra_only_not_a_29th_physical_case",
        }


def _read_source(root, pin):
    root = Path(root).absolute()
    parts = Path(pin.path).parts
    _require(parts and not Path(pin.path).is_absolute() and ".." not in parts,
             "Relative artifact path required")
    directory = None
    try:
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in root.parts[1:] + parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            _require(stat.S_ISREG(info.st_mode), f"Regular nonsymlink artifact required: {pin.path}")
            _require(info.st_size <= MAX_SOURCE_BYTES, f"Frozen artifact exceeds byte limit: {pin.path}")
            raw = stream.read(MAX_SOURCE_BYTES + 1)
            _require(len(raw) <= MAX_SOURCE_BYTES, f"Frozen artifact exceeds byte limit: {pin.path}")
    except OSError as exc:
        raise ValueError(f"Missing, symlinked, or unreadable frozen artifact: {pin.path}") from exc
    finally:
        if directory is not None:
            os.close(directory)
    _require(hashlib.sha256(raw).hexdigest() == pin.sha256, f"Artifact hash mismatch: {pin.path}")
    return SourceArtifact(pin, raw)


def _historical_rows(source):
    document = _json(source.raw_bytes)
    _require(type(document) is dict, "Historical result object required")
    is_a = source.pin.population == "A"
    rows = document.get("case_rows" if is_a else "cases")
    _require(type(rows) is list and len(rows) == source.pin.count, "Historical population count mismatch")
    results = {}
    for row in rows:
        _require(type(row) is dict, "Historical case object required")
        case_id = row.get("case_id")
        _text(case_id, "historical case_id")
        _require(case_id not in results, f"Duplicate historical case ID: {case_id}")
        if is_a:
            _require(type(row.get("H_ref")) is int and row["H_ref"] == 4, "Historical H_ref mismatch")
            expected = row.get("key_or_infimum")
            _require(type(expected) is dict and row.get("status") == expected.get("status"), "Historical A status mismatch")
        else:
            expected = {"status": row.get("status")}
            _require("key" in row, "Missing historical B key")
            if expected["status"] == "attained_optimum":
                key = row["key"]
                _require(type(key) is list and len(key) == 4, "Malformed historical B key")
                expected.update(zip(("J", "Q_total", "H", "site_action_tuple"), key))
            else:
                _require(row["key"] is None, "Unexpected historical B nonattained key")
        results[case_id] = (_expectation(expected), row.get("population") if is_a else "B")
    return results


def load_frozen_ab_registry(input_root):
    """Read six original relative paths and construct all 184 HIER variants.

    No files are written. Pins cannot be supplied by the input bundle. Missing,
    altered, aliased, duplicated, or inconsistent metadata fails closed.
    """
    root = Path(input_root).absolute()
    sources = tuple(_read_source(root, pin) for pin in SOURCE_PINS)
    historical = {s.pin.population: (s, _historical_rows(s)) for s in sources[4:]}
    cases = []
    seen = set()
    for source in sources[:4]:
        rows = _case_rows(source.raw_bytes)
        _require(len(rows) == source.pin.count, "Frozen input population count mismatch")
        group = "B" if source.pin.population == "B" else "A"
        historical_source, expected_rows = historical[group]
        for index, row in enumerate(rows):
            case_id = row["case_id"]
            _require(case_id not in seen, f"Duplicate case ID across inputs: {case_id}")
            _require(case_id in expected_rows, f"Missing historical result: {case_id}")
            expected, population = expected_rows[case_id]
            _require(population == source.pin.population, f"Historical population mismatch: {case_id}")
            seen.add(case_id)
            cases.append(FrozenCase(case_id, group, row["H_ref"], source, index, historical_source, expected))
    for group, (_, expected_rows) in historical.items():
        _require(set(expected_rows) == {c.case_id for c in cases if c.population == group},
                 f"Historical/input case identity mismatch: {group}")
    _require(len(cases) == 92 and Counter(c.population for c in cases) == {"A": 28, "B": 64},
             "Original A28/B64 physical population required")
    variants = tuple(HierVariant(case, dominance) for case in cases for dominance in (False, True))
    _require(len({v.variant_id for v in variants}) == 184, "HIER variant identity collision")
    return FrozenABRegistry(tuple(cases), variants, sources)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(load_frozen_ab_registry(args.input_root).summary(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
