"""Immutable real-leg input contract utilities, deliberately not solver wiring.

No graph construction, shortest-path call, metric completion, Site collapse or
Stage C optimization occurs here. Provenance hashes identify inputs; separate
review must establish routing and selection validity before real search.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as R
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Mapping

from .probe import State, exact

SCHEMA = "hiroute.immutable_selected_legs.v1"
NUMERICS = "binary64_totals_as_exact_rationals_v1"
TIE_POLICY = "min_time_then_actual_length_then_first_discovery"
DIRECTIONS = {"forward_from_source", "reverse_from_target"}


def _object(value, label):
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _array(value, label):
    if type(value) is not list:
        raise ValueError(f"{label} must be an array")
    return value


def _loads(data):
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON object key: {key}")
            result[key]=value
        return result
    return _object(json.loads(data,object_pairs_hook=unique_object),"Root")


def _identifier(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Identity must be a nonempty string")
    return value


def _digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected lowercase SHA-256")
    return value


def _hashes(value):
    if not isinstance(value, dict) or not value:
        raise ValueError("Explicit nonempty source-hash map required")
    result = []
    for path, digest in value.items():
        path = _identifier(path)
        if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise ValueError("Provenance paths must be repository-relative")
        result.append((path, _digest(digest)))
    return tuple(sorted(result))


def encode_binary64(value: float) -> dict:
    if type(value) is not float or not math.isfinite(value) or value < 0:
        raise ValueError("Expected a finite nonnegative binary64 float")
    numerator, denominator = value.as_integer_ratio()
    return {"hex":value.hex(), "ratio":[str(numerator),str(denominator)]}


def decode_binary64(record: Mapping) -> R:
    if not isinstance(record, dict) or set(record) != {"hex", "ratio"}:
        raise ValueError("Binary64 record requires exactly hex and ratio")
    text, ratio = record["hex"], record["ratio"]
    if not isinstance(text, str) or not isinstance(ratio, list) or len(ratio) != 2:
        raise ValueError("Malformed binary64 encoding")
    if any(not isinstance(v, str) or re.fullmatch(r"-?(0|[1-9][0-9]*)", v) is None for v in ratio):
        raise ValueError("Integer-ratio values must be decimal integer strings")
    try:
        value = float.fromhex(text)
        numerator, denominator = map(int, ratio)
    except (ValueError, OverflowError) as error:
        raise ValueError("Invalid binary64 encoding") from error
    if (not math.isfinite(value) or value < 0 or value.hex() != text
            or ratio != [str(numerator),str(denominator)]
            or denominator <= 0 or (numerator,denominator) != value.as_integer_ratio()):
        raise ValueError("Hex and canonical exact ratio disagree")
    return R(numerator, denominator)


@dataclass(frozen=True)
class RealSite:
    site_id: str
    anchor_id: str
    effects: tuple[str, ...]


@dataclass(frozen=True)
class SelectedLeg:
    source_anchor: str
    target_anchor: str
    reachable: bool
    time: R | None
    actual_length: R | None
    label_direction: str
    time_hex: str | None
    length_hex: str | None

    def energy(self, kappa: R) -> R | None:
        kappa = exact(kappa)
        if kappa < 0:
            raise ValueError("Negative consumption coefficient")
        return None if self.actual_length is None else kappa * self.actual_length


@dataclass(frozen=True)
class ImmutableLegTable:
    anchors: tuple[str, ...]
    origin_anchor: str
    destination_anchor: str
    sites: Mapping[str, RealSite]
    legs: Mapping[tuple[str, str], SelectedLeg]
    source_sha256: tuple[tuple[str, str], ...]
    router_sha256: tuple[tuple[str, str], ...]
    backend_name: str
    direction_policy: str
    selection_certificate_sha256: str
    hierarchy_sha256: str
    payload_sha256: str

    @classmethod
    def from_bytes(cls, data: bytes, expected_sha256: str) -> ImmutableLegTable:
        digest = hashlib.sha256(data).hexdigest()
        if digest != _digest(expected_sha256):
            raise ValueError("Frozen leg payload hash mismatch")
        payload = _loads(data)
        if payload.get("schema") != SCHEMA or payload.get("numerical_contract") != NUMERICS:
            raise ValueError("Unsupported real-leg numerical schema")
        if "edges" in payload:
            raise ValueError("An immutable leg table must not masquerade as a graph")
        anchors = tuple(_identifier(a) for a in _array(payload["anchors"],"anchors"))
        if not anchors or len(set(anchors)) != len(anchors):
            raise ValueError("Road-anchor identities must be unique")
        origin, destination = _identifier(payload["origin_anchor"]), _identifier(payload["destination_anchor"])
        if origin not in anchors or destination not in anchors:
            raise ValueError("Query anchors must occur in the complete table")
        backend = _object(payload["backend"],"backend")
        if backend["tie_policy"] != TIE_POLICY:
            raise ValueError("Real selected-leg tie policy must be explicit")
        direction_policy = backend["direction_policy"]
        if direction_policy not in ("forward_per_source_v1", "explicit_per_leg_v1"):
            raise ValueError("Unfrozen forward/reverse label policy")
        source_hashes = _hashes(payload["source_sha256"])
        router_hashes = _hashes(backend["source_sha256"])
        sites = {}
        for item in _array(payload["sites"],"sites"):
            item=_object(item,"Site")
            sid, anchor = _identifier(item["site_id"]), _identifier(item["anchor_id"])
            effects = tuple(_identifier(effect) for effect in _array(item["effects"],"Site effects"))
            if sid in sites or anchor not in anchors or len(set(effects)) != len(effects) or not set(effects) <= {"C","S","CS"}:
                raise ValueError("Invalid Site identity, anchor or explicit effects")
            sites[sid] = RealSite(sid,anchor,effects)
        legs = {}
        for row in _array(payload["legs"],"legs"):
            row=_object(row,"Leg")
            a,b = _identifier(row["source_anchor"]),_identifier(row["target_anchor"])
            if a not in anchors or b not in anchors or (a,b) in legs:
                raise ValueError("Duplicate or undeclared ordered leg pair")
            reachable = row["reachable"]
            if type(reachable) is not bool:
                raise ValueError("Reachability must be explicit boolean")
            direction = _identifier(row["label_direction"])
            if a == b:
                if direction != "identity" or not reachable:
                    raise ValueError("Same-anchor leg must be a reachable identity")
            elif direction not in DIRECTIONS or (direction_policy == "forward_per_source_v1" and direction != "forward_from_source"):
                raise ValueError("Leg direction violates frozen direction policy")
            time_record, length_record = row["time_s"],row["actual_length_m"]
            if reachable:
                time, length = decode_binary64(time_record),decode_binary64(length_record)
                if (a == b and (time or length)) or (a != b and (time <= 0 or length <= 0)):
                    raise ValueError("Only same-road-anchor movement has zero cost")
                time_hex, length_hex = time_record["hex"],length_record["hex"]
            else:
                if time_record is not None or length_record is not None:
                    raise ValueError("Unreachable legs have no finite numeric substitute")
                time=length=time_hex=length_hex=None
            legs[a,b] = SelectedLeg(a,b,reachable,time,length,direction,time_hex,length_hex)
        if set(legs) != {(a,b) for a in anchors for b in anchors}:
            raise ValueError("Incomplete directed leg table; missing is not unreachable")
        # Reachability is a topological relation even when rounded totals are
        # non-metric. Reject a complete table claiming a->b and b->c exist but
        # a->c does not. No numeric shortest paths or metric closure is computed.
        reachable_targets={a:{b for b in anchors if legs[a,b].reachable} for a in anchors}
        if any(not reachable_targets[b] <= reachable_targets[a]
               for a in anchors for b in reachable_targets[a]):
            raise ValueError("Road reachability is not transitively consistent")
        source_map=dict(source_hashes)
        if any(path in source_map and source_map[path] != digest for path,digest in router_hashes):
            raise ValueError("Conflicting declared provenance hashes")
        return cls(anchors,origin,destination,MappingProxyType(sites),MappingProxyType(legs),
                   source_hashes,router_hashes,_identifier(backend["name"]),direction_policy,
                   _digest(payload["selection_certificate_sha256"]),_digest(payload["hierarchy_sha256"]),digest)

    def leg(self, source_anchor: str, target_anchor: str) -> SelectedLeg:
        return self.legs[source_anchor,target_anchor]

    def site(self, site_id: str) -> RealSite:
        return self.sites[site_id]

    def action_sites(self, current_anchor: str, effect: str, remaining_schedule: int,
                     candidates=None) -> tuple[RealSite, ...]:
        if current_anchor not in self.anchors or effect not in {"C","S","CS"} or type(remaining_schedule) is not int or remaining_schedule not in (0,1):
            raise ValueError("Invalid physical state or effect")
        if candidates is not None and not isinstance(candidates,(list,tuple)):
            raise ValueError("Candidate Site IDs require an explicit list or tuple")
        identities = tuple(self.sites) if candidates is None else tuple(candidates)
        if len(set(identities)) != len(identities) or any(s not in self.sites for s in identities):
            raise ValueError("Candidate Site IDs must be unique and known")
        if current_anchor == self.destination_anchor or effect in ("S","CS") and not remaining_schedule:
            return ()
        return tuple(self.sites[s] for s in identities
                     if self.sites[s].anchor_id != self.destination_anchor
                     and effect in self.sites[s].effects
                     and self.leg(current_anchor,self.sites[s].anchor_id).reachable)


@dataclass(frozen=True)
class WeakBound:
    value: R | None
    site_ids: tuple[str, ...]
    inbound_minimum: R | None
    onward_lower_bound: R = R(0)
    scope: str = "nonmetric_immediate_action_only"


def weak_action_bound(table: ImmutableLegTable, state: State, candidates, effect: str,
                      tau_infimum: R, start_time: R, overhead: R,
                      stop_penalty: R, schedule=None) -> WeakBound:
    """Assumes tau is a proved frontier lower bound and h is common or proved h_min."""
    tau,start,h,penalty = map(exact,(tau_infimum,start_time,overhead,stop_penalty))
    if h <= 0 or penalty < 0:
        raise ValueError("Positive overhead and nonnegative future penalties required")
    sites = table.action_sites(state.anchor,effect,state.remaining_schedule,candidates)
    if not sites:
        return WeakBound(None,(),None)
    incoming = min(table.leg(state.anchor,s.anchor_id).time for s in sites)
    completion = tau+incoming+h
    if effect in ("S","CS"):
        if schedule is None or len(schedule) != 3:
            raise ValueError("Scheduled effect requires an explicit window/duration")
        a,b,d = map(exact,schedule)
        if d < 0:
            raise ValueError("Negative service duration")
        if a > b:
            return WeakBound(None,(),None)
        completion = max(a,completion)+d
    return WeakBound(completion-start+penalty*(state.stop_count+1),
                     tuple(s.site_id for s in sites),incoming)


@dataclass(frozen=True)
class RestrictedRegion:
    region_id: int
    parent_id: int
    child_ids: tuple[int, ...]
    site_ids: tuple[str, ...]


@dataclass(frozen=True)
class RestrictedTree:
    original_sha256: str
    selected_site_ids: tuple[str, ...]
    regions: tuple[RestrictedRegion, ...]


def restrict_frozen_tree(data: bytes, expected_sha256: str, selected_site_ids) -> RestrictedTree:
    digest = hashlib.sha256(data).hexdigest()
    if digest != _digest(expected_sha256):
        raise ValueError("Original hierarchy hash mismatch")
    tree = _loads(data)
    ids = tuple(_identifier(s) for s in _array(tree["site_ids"],"Original Site IDs"))
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate original Site identity")
    if not isinstance(selected_site_ids,(list,tuple)):
        raise ValueError("Selected Site IDs require an explicit list or tuple")
    selected = tuple(_identifier(s) for s in selected_site_ids)
    if len(set(selected)) != len(selected) or not set(selected) <= set(ids):
        raise ValueError("Selected Sites must be unique original members")
    rows = tuple(_object(r,"Region") for r in _array(tree["regions"],"regions"))
    if not rows or rows[0]["parent"] != -1:
        raise ValueError("Original root must have parent -1")
    members = []
    for row in rows:
        if type(row["parent"]) is not int:
            raise ValueError("Region parent identity must be an integer array index")
        values = tuple(_array(row["members"],"Region members"))
        if any(type(i) is not int or i < 0 or i >= len(ids) for i in values) or len(set(values)) != len(values):
            raise ValueError("Invalid original membership indices")
        members.append(set(values))
    if members[0] != set(range(len(ids))):
        raise ValueError("Root does not cover original Site universe")
    seen=set()
    def visit(index):
        if index in seen:
            raise ValueError("Hierarchy is not a rooted tree")
        seen.add(index)
        children=tuple(_array(rows[index]["children"],"Region children"))
        if len(set(children)) != len(children) or any(type(c) is not int or c<0 or c>=len(rows) for c in children):
            raise ValueError("Invalid original child indices")
        if children:
            union=set()
            for child in children:
                if rows[child]["parent"] != index or union.intersection(members[child]):
                    raise ValueError("Child parentage or disjointness violated")
                union.update(members[child]); visit(child)
            if union != members[index]:
                raise ValueError("Children fail exact original membership partition")
    visit(0)
    if seen != set(range(len(rows))):
        raise ValueError("Unreachable original Region")
    selected_set=set(selected)
    restricted=tuple(RestrictedRegion(i,row["parent"],tuple(row["children"]),
                       tuple(ids[j] for j in row["members"] if ids[j] in selected_set))
                     for i,row in enumerate(rows))
    return RestrictedTree(digest,tuple(s for s in ids if s in selected_set),restricted)


def verify_source_files(table: ImmutableLegTable, actual_paths: Mapping[str, Path]) -> dict:
    """Only hash explicitly supplied local paths; absent inputs remain missing."""
    expected=dict(table.source_sha256)
    for path,digest in table.router_sha256:
        if path in expected and expected[path] != digest:
            raise ValueError("Conflicting declared provenance hashes")
        expected[path]=digest
    verified,missing,mismatched=[],[],[]
    for name,digest in expected.items():
        path=actual_paths.get(name)
        if path is None or not Path(path).is_file():
            missing.append(name);continue
        h=hashlib.sha256()
        with Path(path).open("rb") as stream:
            for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
        (verified if h.hexdigest()==digest else mismatched).append(name)
    return {"verified":tuple(verified),"missing":tuple(missing),"mismatched":tuple(mismatched),
            "complete":not missing and not mismatched}
