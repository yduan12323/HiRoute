"""Reconstructed real-input checker foundation above published PR7.

The immutable-leg parser is adapted from the published independent REF input
parser, without importing its package or optimizer. This is new reconstructed
source, not recovery or acceptance of any unpublished historical hash.

Independent lossless immutable-leg input adapter; no routing.

This parser implements the shared serialized physical-input contract, without
importing the production parser or any timecut5 helper. Hash identity alone
is not proof that the external native router or selection is correct.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as R
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType

from validation.family5.checker import (
    VerificationError, _Physics, _freeze, _plain, canonical, digest, rational,
)

InvalidInput = VerificationError

SCHEMA = "hiroute.immutable_selected_legs.v1"
NUMERICS = "binary64_totals_as_exact_rationals_v1"
TIE_POLICY = "min_time_then_actual_length_then_first_discovery"


def require(condition, reason):
    if not condition:
        raise InvalidInput(reason)


def checked_hash(value, field):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            f"{field} must be a lowercase SHA256 digest")
    return value


def identity(value, field):
    require(isinstance(value, str) and bool(value), f"{field} must be a nonempty string")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def decode_binary64(record):
    """Return exact rational value and retained canonical binary64 hex string."""
    require(isinstance(record, dict) and set(record) == {"hex", "ratio"}, "Invalid binary64 record")
    text, ratio = record["hex"], record["ratio"]
    require(isinstance(text, str), "Binary64 hex must be a string")
    require(isinstance(ratio, list) and len(ratio) == 2 and all(type(v) is str for v in ratio),
            "Binary64 ratio must contain two integer strings")
    try:
        numbers = tuple(int(v) for v in ratio)
        value = float.fromhex(text)
    except (ValueError, OverflowError) as error:
        raise InvalidInput("Invalid binary64 encoding") from error
    require(all(str(v) == original for v, original in zip(numbers, ratio)), "Noncanonical integer ratio")
    require(math.isfinite(value) and value >= 0, "Binary64 leg total must be finite and nonnegative")
    require(value.hex() == text, "Binary64 hex must preserve the canonical encoding")
    require(numbers[1] > 0 and value.as_integer_ratio() == numbers, "Binary64 hex/ratio mismatch")
    return R(*numbers), text


@dataclass(frozen=True)
class ReferenceSite:
    site_id: str
    anchor_id: str
    effects: tuple[str, ...]


@dataclass(frozen=True)
class ImmutablePair:
    source_anchor: str
    target_anchor: str
    reachable: bool
    time: R | None
    actual_length: R | None
    time_hex: str | None
    length_hex: str | None
    label_direction: str


@dataclass(frozen=True)
class IndependentLegTable:
    payload_sha256: str
    raw_bytes: bytes
    anchors: tuple[str, ...]
    origin_anchor: str
    destination_anchor: str
    sites: object
    pairs: object
    source_sha256: object
    router_source_sha256: object
    backend_name: str
    direction_policy: str
    selection_certificate_sha256: str
    hierarchy_sha256: str

    @classmethod
    def from_bytes(cls, data, expected_sha256):
        require(type(data) is bytes, "Immutable payload must be bytes")
        checked_hash(expected_sha256, "Expected payload hash")
        actual = hashlib.sha256(data).hexdigest()
        require(actual == expected_sha256, "Immutable payload SHA256 mismatch")
        try:
            value = json.loads(data, object_pairs_hook=unique_object,
                               parse_constant=lambda text: (_ for _ in ()).throw(InvalidInput(f"Nonfinite JSON constant: {text}")))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidInput("Invalid immutable-leg JSON") from error
        require(isinstance(value, dict), "Immutable payload must be an object")
        require(value.get("schema") == SCHEMA and value.get("numerical_contract") == NUMERICS,
                "Unsupported immutable-leg schema or numerical contract")
        require("edges" not in value, "Immutable pairs are not graph edges and cannot be rerouted")
        anchors = value.get("anchors")
        require(isinstance(anchors, list) and bool(anchors), "anchors must be a nonempty array")
        for anchor in anchors:
            identity(anchor, "anchor")
        require(len(set(anchors)) == len(anchors), "Duplicate physical anchor")
        anchor_set = set(anchors)
        origin = identity(value.get("origin_anchor"), "origin_anchor")
        destination = identity(value.get("destination_anchor"), "destination_anchor")
        require(origin in anchor_set and destination in anchor_set, "Missing origin/destination anchor")
        backend = value.get("backend")
        require(isinstance(backend, dict), "backend must be an object")
        name = identity(backend.get("name"), "backend.name")
        require(backend.get("tie_policy") == TIE_POLICY, "Unaccepted native router tie policy")
        direction = backend.get("direction_policy")
        require(direction in ("forward_per_source_v1", "explicit_per_leg_v1"), "Unspecified routing direction policy")

        def hashes(mapping, label):
            require(isinstance(mapping, dict) and bool(mapping), f"{label} must be a nonempty hash map")
            return MappingProxyType({identity(k, label): checked_hash(v, label) for k, v in mapping.items()})

        source_hashes = hashes(value.get("source_sha256"), "source_sha256")
        router_hashes = hashes(backend.get("source_sha256"), "backend.source_sha256")
        require(all(source_hashes[key] == digest for key, digest in router_hashes.items() if key in source_hashes),
                "Contradictory source hash claims")
        selection_hash = checked_hash(value.get("selection_certificate_sha256"), "selection certificate")
        hierarchy_hash = checked_hash(value.get("hierarchy_sha256"), "hierarchy")
        raw_sites = value.get("sites")
        require(isinstance(raw_sites, list), "sites must be an array")
        sites = {}
        for site in raw_sites:
            require(isinstance(site, dict), "Each Site must be an object")
            site_id = identity(site.get("site_id"), "site_id")
            require(site_id not in sites, "Duplicate Site identity")
            anchor = identity(site.get("anchor_id"), "Site anchor_id")
            require(anchor in anchor_set, "Site refers to undeclared physical anchor")
            effects = site.get("effects")
            require(isinstance(effects, list) and all(type(e) is str and e in ("C", "S", "CS") for e in effects),
                    "Site effects must be an explicit effect array")
            require(len(effects) == len(set(effects)), "Duplicate Site effect")
            sites[site_id] = ReferenceSite(site_id, anchor, tuple(effects))
        rows = value.get("legs")
        require(isinstance(rows, list) and len(rows) == len(anchors) ** 2, "Require exactly one row for every ordered pair")
        pairs = {}
        for row in rows:
            require(isinstance(row, dict), "Leg row must be an object")
            source = identity(row.get("source_anchor"), "source_anchor")
            target = identity(row.get("target_anchor"), "target_anchor")
            require(source in anchor_set and target in anchor_set, "Leg uses undeclared anchor")
            require((source, target) not in pairs, "Duplicate ordered leg pair")
            reachable = row.get("reachable")
            label = identity(row.get("label_direction"), "label_direction")
            require(type(reachable) is bool, "Leg reachability must be boolean")
            if source == target:
                require(reachable and label == "identity", "Identity leg must be reachable with identity provenance")
            else:
                allowed = {"forward_from_source"} if direction == "forward_per_source_v1" else {"forward_from_source", "reverse_from_target"}
                require(label in allowed, "Leg direction contradicts frozen direction policy")
            if reachable:
                time, time_hex = decode_binary64(row.get("time_s"))
                length, length_hex = decode_binary64(row.get("actual_length_m"))
                require((time == length == 0) if source == target else (time > 0 and length > 0),
                        "Only physical identity legs may have zero totals")
            else:
                require(row.get("time_s") is None and row.get("actual_length_m") is None,
                        "Unreachable row cannot have finite substitute totals")
                time = length = time_hex = length_hex = None
            pairs[source, target] = ImmutablePair(source, target, reachable, time, length, time_hex, length_hex, label)
        for source in anchors:
            for middle in anchors:
                if not pairs[source, middle].reachable:
                    continue
                for target in anchors:
                    require(not pairs[middle, target].reachable or pairs[source, target].reachable,
                            "Contradictory non-transitive road reachability")
        return cls(actual, data, tuple(anchors), origin, destination, MappingProxyType(sites),
                   MappingProxyType(pairs), source_hashes, router_hashes, name, direction,
                   selection_hash, hierarchy_hash)

    def pair(self, source_anchor, target_anchor):
        try:
            return self.pairs[source_anchor, target_anchor]
        except KeyError as error:
            raise InvalidInput("Lookup uses an undeclared physical anchor") from error

    def provenance(self):
        return dict(payload_sha256=self.payload_sha256, schema=SCHEMA, numerical_contract=NUMERICS,
                    backend_name=self.backend_name, tie_policy=TIE_POLICY, direction_policy=self.direction_policy,
                    source_sha256=dict(self.source_sha256), router_source_sha256=dict(self.router_source_sha256),
                    selection_certificate_sha256=self.selection_certificate_sha256, hierarchy_sha256=self.hierarchy_sha256,
                    payload_identity_verified=True, external_source_validity_not_implied=True)


def verify_source_files(table, actual_paths):
    """Explicitly hash supplied local artifacts; loader hash claims are separate."""
    claims = {**table.source_sha256, **table.router_source_sha256}
    missing, mismatched, verified = [], [], []
    for name, expected in sorted(claims.items()):
        if name not in actual_paths or not Path(actual_paths[name]).is_file():
            missing.append(name)
            continue
        digest = hashlib.sha256()
        with Path(actual_paths[name]).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        (verified if digest.hexdigest() == expected else mismatched).append(name)
    return dict(complete=not missing and not mismatched, verified=verified, missing=missing, mismatched=mismatched)


def _exact_json(value):
    """Query numbers are exact integers/rational strings, never floats/bools."""
    if type(value) is dict:
        require(all(type(k) is str for k in value), "Non-string query key")
        for child in value.values():
            _exact_json(child)
    elif type(value) is list:
        for child in value:
            _exact_json(child)
    else:
        require(type(value) in (str, int, bool, type(None)), "Non-exact query JSON")


def _regions(data, expected_sha256, selected):
    require(type(data) is bytes, "Original Region tree must be bytes")
    checked_hash(expected_sha256, "Expected original tree hash")
    require(hashlib.sha256(data).hexdigest() == expected_sha256, "Original tree SHA256 mismatch")
    try:
        tree = json.loads(data, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidInput("Invalid original tree JSON") from error
    require(type(tree) is dict and set(tree) == {"site_ids", "regions"}, "Original tree fields")
    ids, rows = tree["site_ids"], tree["regions"]
    require(type(ids) is list and all(type(s) is str and s for s in ids), "Original Site IDs")
    require(len(ids) == len(set(ids)), "Duplicate original Site ID")
    require(set(selected) <= set(ids), "Selected Site missing from original tree")
    require(type(rows) is list and bool(rows), "Missing original Regions")
    member_sets = []
    for row in rows:
        require(type(row) is dict and set(row) == {"parent", "children", "members"}, "Original Region fields")
        require(type(row["parent"]) is int, "Original parent must be an integer")
        for field, bound in (("children", len(rows)), ("members", len(ids))):
            values = row[field]
            require(type(values) is list and all(type(v) is int and 0 <= v < bound for v in values),
                    "Invalid original Region indices")
            require(len(values) == len(set(values)), "Duplicate original Region indices")
        member_sets.append(set(row["members"]))
    require(rows[0]["parent"] == -1, "Original root parent")
    require(member_sets[0] == set(range(len(ids))), "Original root Site coverage")
    visited = set()

    def visit(index):
        require(index not in visited, "Original Region cycle or repeated child")
        visited.add(index)
        row, covered, children = rows[index], set(), []
        for child in row["children"]:
            require(rows[child]["parent"] == index, "Original Region parent mismatch")
            require(not covered.intersection(member_sets[child]), "Overlapping original Region partition")
            covered.update(member_sets[child])
            children.append(visit(child))
        require(not children or covered == member_sets[index], "Incomplete original Region partition")
        # Original IDs, child order, member order and empty children survive.
        return dict(id=index, members=[ids[i] for i in row["members"] if ids[i] in selected], children=children)

    root = visit(0)
    require(visited == set(range(len(rows))), "Disconnected original Region")
    return _freeze(root)


def _physics(case, table):
    values = [rational(case[k]) for k in (
        "start_time_s", "initial_energy_kwh", "minimum_energy_kwh", "reserve_kwh",
        "capacity_kwh", "overhead_s", "consumption_kwh_per_m", "lambda_stop_s")]
    start, initial, floor, reserve, capacity, overhead, rate, penalty = values
    bound = case["H_ref"]
    require(type(bound) is int and bound >= 0 and overhead > 0 and rate >= 0 and penalty >= 0
            and capacity > 0 and 0 <= floor <= initial <= capacity and floor <= reserve <= capacity,
            "Invalid exact physical query bounds")
    sites = {sid: site.effects for sid, site in table.sites.items()}
    anchors = {sid: site.anchor_id for sid, site in table.sites.items()}
    rows = case["charging_segments"]
    require(type(rows) is list and all(type(row) is list and len(row) == 4 for row in rows), "Invalid curve rows")
    curve = tuple(tuple(map(rational, row)) for row in rows)
    if curve:
        require(all(lo < hi and m > 0 for lo, hi, m, b in curve), "Invalid curve segments")
        require(curve[0][0] == 0 and curve[-1][1] == capacity, "Curve capacity coverage")
        require(all(a[1] == b[0] and a[2]*a[1]+a[3] == b[2]*b[0]+b[3]
                    for a, b in zip(curve, curve[1:])), "Curve discontinuity")
    require(curve or not any(set(effects) & {"C", "CS"} for effects in sites.values()), "Missing charging curve")
    raw_schedule = case.get("schedule")
    require(raw_schedule is None or type(raw_schedule) is dict and set(raw_schedule) == {"a", "b", "D"},
            "Invalid schedule fields")
    schedule = tuple(rational(raw_schedule[k]) for k in ("a", "b", "D")) if raw_schedule is not None else None
    require(schedule is None or schedule[2] >= 0, "Negative service duration")
    remaining = case.get("initial_remaining_schedule", int(schedule is not None))
    require(type(remaining) is int and remaining in (0, 1) and (not remaining or schedule is not None), "Invalid schedule state")
    # Pair totals are already selected physical primitives. No graph, closure,
    # route selection or metric inequality is introduced by this adapter.
    legs = {(a, b): (leg.time, leg.actual_length*rate, (), ())
            for (a, b), leg in table.pairs.items() if leg.reachable}
    return _Physics(_freeze(case), table.origin_anchor, table.destination_anchor, start, initial, floor,
                    reserve, capacity, overhead, bound, remaining, MappingProxyType(sites),
                    MappingProxyType(anchors), curve, schedule, MappingProxyType(legs))


@dataclass(frozen=True)
class TrustedRealCase:
    """Separately pinned immutable physical query, pair table and original tree."""
    physics: object
    regions: object
    table: IndependentLegTable
    _sources: object

    def case_snapshot(self):
        return _plain(self.physics.case)

    def source_snapshot(self):
        return _plain(self._sources)


def prepare_real_case(query, expected_query_sha256, table_bytes, expected_table_sha256,
                      original_tree_bytes, expected_tree_sha256):
    """Pin each caller-supplied source independently before reading evidence.

    The query digest uses canonical JSON (sorted keys, compact separators).
    Table/tree digests bind exact bytes. Provenance declarations alone do not
    establish external routing, source-artifact or selection validity.
    """
    try:
        require(type(query) is dict, "Query must be a JSON object")
        _exact_json(query)
        checked_hash(expected_query_sha256, "Expected query hash")
        require(digest(query) == expected_query_sha256, "Query SHA256 mismatch")
        detached = json.loads(canonical(query))
        require("edges" not in detached, "Immutable selected legs cannot be graph edges")
        table = IndependentLegTable.from_bytes(table_bytes, expected_table_sha256)
        require(expected_tree_sha256 == table.hierarchy_sha256, "Table and original hierarchy pins disagree")
        sites = {sid: list(site.effects) for sid, site in table.sites.items()}
        checks = dict(origin=table.origin_anchor, destination=table.destination_anchor, sites=sites,
                      leg_payload_sha256=table.payload_sha256,
                      selection_certificate_sha256=table.selection_certificate_sha256,
                      hierarchy_sha256=table.hierarchy_sha256)
        for key, expected in checks.items():
            require(key not in detached or canonical(detached[key]) == canonical(expected), f"Query conflicts with immutable {key}")
        expected_anchors = {sid: site.anchor_id for sid, site in table.sites.items()}
        require("site_anchors" not in detached or detached["site_anchors"] == expected_anchors,
                "Query conflicts with immutable Site anchors")
        case = dict(detached, origin=table.origin_anchor, destination=table.destination_anchor, sites=sites)
        regions = _regions(original_tree_bytes, expected_tree_sha256, set(sites))
        physics = _physics(case, table)
        sources = dict(query_sha256=expected_query_sha256, table_sha256=expected_table_sha256,
                       original_tree_sha256=expected_tree_sha256, case_sha256=digest(case),
                       region_tree_sha256=digest(regions), provenance=table.provenance(),
                       reconstructed_checker=True, historical_unpublished_source_accepted=False)
        return TrustedRealCase(physics, regions, table, _freeze(sources))
    except (KeyError, TypeError, IndexError, AttributeError, RecursionError) as error:
        raise InvalidInput(f"Malformed trusted real input: {type(error).__name__}: {error}") from error
