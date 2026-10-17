"""Independent lossless immutable-leg input adapter; no routing or hierarchy.

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

from .model import InvalidInput

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
            sites[site_id] = ReferenceSite(site_id, anchor, tuple(sorted(effects)))
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
