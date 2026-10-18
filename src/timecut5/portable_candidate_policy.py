"""Nonlaunchable, per-query selected-leg candidate proposal, without observations.

The caller MUST authenticate the graph bytes and loaded native implementation,
keep graph/native state immutable, supply a fresh router, and independently
recompute the complete eligible charging catalog using the original corridor
rule for this actual OD. Supplied hashes bind those inputs; they do NOT prove
native provenance, source-file authenticity, or catalog completeness here.

This helper constructs the unchanged TableFreeRoadSelectedLegProvider, makes
at most one fixed-origin full-source request, and clears each reconstructed
witness immediately. It never starts seed/exact search or runtime admission.
A proposed union requires a newly derived sparse-domain identity and fresh
physical seed replay under the existing production guard before any execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import hashlib
import json
import math
import re

from timecut5.road_provider import TableFreeRoadSelectedLegProvider

SCHEMA = "hiroute.portable_reachable_candidate_policy.v1"
RULE_VERSION = "baseline_union_all_eligible_omitted_selected_leg_floor_pass.v1"
ELIGIBILITY_SCHEMA = "hiroute.complete_eligible_charging_catalog.v1"
ELIGIBILITY_POLICY = "original_corridor_progress_0_1_radius_endpoint_exclusions.v1"
ENERGY_KEYS = ("initial_energy_kwh", "minimum_energy_kwh", "reserve_kwh",
               "consumption_kwh_per_m")
ROUTE_KEYS = frozenset({"road_reachable", "arrival_energy_kwh", "minimum_floor_pass",
                        "reserve_pass", "selected_distance_m", "edge_path_sha256"})


class PolicyError(ValueError):
    """An input or invariant cannot establish this complete proposal."""


class ProposalStatus(str, Enum):
    PROPOSED_COMPLETE = "proposed_complete"
    FALLBACK_REQUIRED = "fallback_required"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PortableResult:
    """Immutable result; as_dict returns a detached, nonlaunchable JSON value."""
    status: ProposalStatus
    payload_bytes: bytes

    def as_dict(self):
        return json.loads(self.payload_bytes)


def _require(condition, message):
    if not condition:
        raise PolicyError(message)


def _json_types(value):
    if type(value) in (str, int, bool, type(None)):
        return
    if type(value) is float:
        _require(math.isfinite(value), "Non-finite JSON number")
    elif type(value) is list:
        for child in value:
            _json_types(child)
    elif type(value) is dict:
        _require(all(type(key) is str for key in value), "JSON object keys must be strings")
        for child in value.values():
            _json_types(child)
    else:
        raise PolicyError("Only plain finite JSON values are supported")


def canonical(value):
    _json_types(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _sha(value, label):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             "Invalid SHA256: " + label)
    return value


def _fraction(value, label):
    _require(type(value) in (str, int), "Non-exact rational: " + label)
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        raise PolicyError("Invalid rational: " + label) from exc


def _road_node(value, count, label):
    _require(type(value) is str and re.fullmatch(r"road:(0|[1-9][0-9]*)", value) is not None,
             "Invalid road anchor: " + label)
    node = int(value[5:])
    _require(0 <= node < count, "Road anchor outside loaded graph: " + label)
    return node


def _site_rows(rows, count, label):
    _require(type(rows) is list, label + " must be a list")
    indexed = {}
    for row in rows:
        _require(type(row) is dict, "Invalid site row: " + label)
        sid = row.get("site_id")
        _require(type(sid) is str and bool(sid) and sid not in indexed,
                 "Invalid or duplicate site ID: " + label)
        node = row.get("access_node")
        _require(type(node) is int and 0 <= node < count, "Invalid access node: " + sid)
        _require(row.get("anchor_id") == "road:" + str(node), "Anchor drift: " + sid)
        effects = row.get("effects")
        _require(type(effects) is list and bool(effects)
                 and all(type(e) is str and e in {"C", "S", "CS"} for e in effects)
                 and len(set(effects)) == len(effects), "Invalid original effects: " + sid)
        _require("CS" not in effects or {"C", "S"} <= set(effects),
                 "Combined effect lacks component support: " + sid)
        if "charging_supported" in row:
            _require(type(row["charging_supported"]) is bool
                     and row["charging_supported"] == ("C" in effects),
                     "Charging support/effects drift: " + sid)
        _require(not ROUTE_KEYS.intersection(row), "Caller-provided reachability verdict: " + sid)
        indexed[sid] = row
    return indexed


def _source_mapping(value, label, required):
    _require(type(value) is dict and required <= set(value), "Incomplete " + label)
    for key, sha in value.items():
        _require(type(key) is str and bool(key), "Invalid source key")
        _sha(sha, label + "." + key)


def _graph_signature(graph):
    """O(1) structural/read-only guard, NOT graph-content authentication.

    The caller's authenticated immutable graph contract remains essential:
    this does not protect against hostile native writes or writable aliases.
    """
    import numpy as np
    n, m = graph.node_count, graph.edge_count
    _require(type(n) is int and n > 0 and type(m) is int and m >= 0,
             "Invalid loaded graph counts")
    weights = graph.weights
    _require(type(weights) is dict and {"distance", "travel_time"} <= set(weights),
             "Missing original graph weights")
    arrays = (graph.source, graph.target, weights["travel_time"], weights["distance"])
    expected = (np.dtype("int64"), np.dtype("int64"), np.dtype("float64"), np.dtype("float64"))
    for a, dtype in zip(arrays, expected):
        _require(type(a) is np.ndarray and a.dtype == dtype and a.shape == (m,)
                 and a.flags.c_contiguous and not a.flags.writeable,
                 "Loaded graph arrays must be immutable contiguous int64/float64 arrays")
    return (n, m, id(weights), tuple((id(a), a.ctypes.data, a.shape, a.dtype.str) for a in arrays))


class OneSourceRouter:
    """A one-call guard, not a native authenticator or router freshness proof."""
    def __init__(self, router, origin, provenance_sha256, check_graph):
        _require(type(origin) is int and origin >= 0, "Invalid fixed source")
        _sha(provenance_sha256, "native_provenance_sha256")
        _require(type(getattr(router, "provenance", None)) is dict, "Missing native provenance")
        _require(callable(getattr(router, "full_edges", None)), "Missing native full_edges")
        self.router, self.origin, self.calls = router, origin, 0
        self._provenance_bytes = canonical(router.provenance)
        _require(digest(self._provenance_bytes) == provenance_sha256, "Native provenance binding drift")
        self.provenance = json.loads(self._provenance_bytes)
        self._full_edges = router.full_edges
        self._check_graph = check_graph

    def check(self):
        _require(canonical(self.router.provenance) == self._provenance_bytes,
                 "Native provenance changed during query")
        _require(self.router.full_edges == self._full_edges, "Native source method changed during query")
        self._check_graph()

    def full_edges(self, node):
        _require(type(node) is int and node == self.origin and self.calls == 0,
                 "Exactly one fixed-origin native source call allowed")
        self.check()
        self.calls += 1
        labels = self._full_edges(node)
        self.check()
        return labels


def _result(status, **fields):
    payload = dict(schema=SCHEMA, rule_version=RULE_VERSION, status=status.value,
                   complete=False, launchable=False, runtime_admission_complete=False,
                   loaded_sparse_domain_sha256=None, candidate_ids=None, sites=None,
                   descriptor=None, domain_sha256=None, candidate_sha256=None,
                   complete_journey_feasibility_established=False,
                   native_provenance_authenticated_here=False,
                   catalog_completeness_authenticated_here=False,
                   caller_must_authenticate_graph_native_catalog_and_fresh_seed_replay=True)
    payload.update(fields)
    return PortableResult(status, canonical(payload))


def build_portable_domain(*, graph, router, baseline_sites, eligible_charging_sites,
                          eligibility, query, bindings, cap=256):
    """Propose the complete baseline/floor-positive eligible-charger union.

    Inputs are plain JSON except the already authenticated graph/router.
    No observations, reachability flags, or externally supplied legs are read.

    bindings requires source_sha256 (nodes/edges/router), catalog_source_sha256
    (sites/pools/geo/slate), baseline_domain_sha256, baseline_candidate_sha256,
    baseline_sites_sha256, eligible_catalog_sha256, eligibility_sha256,
    query_sha256, native_provenance_sha256. The content hashes use canonical
    inputs exactly as supplied; baseline_candidate_sha256 uses sorted IDs.

    eligibility has exactly: schema=ELIGIBILITY_SCHEMA,
    policy_version=ELIGIBILITY_POLICY, complete=True, source_sha256 matching
    catalog_source_sha256, query_sha256, origin, destination, od_id,
    origin_site_id, destination_site_id, radius_m, eligible_charging_count,
    eligible_candidate_sha256 (sorted IDs), eligible_sites_sha256 (rows).
    This is the caller's recomputed full original corridor eligibility identity,
    not a reachability verdict. This core cannot independently authenticate it.

    A successful result is only a proposal. All baseline rows and their effects
    survive, even if unreachable. Reserve is reported separately, never used to
    exclude a floor-positive addition. Overflow contains no candidate domain;
    no cap-prefix truncation or automatic fallback is performed.
    """
    provider = one = None
    phase = "input_validation"
    completed_anchors = 0
    inputs = dict(baseline_sites=baseline_sites, eligible_charging_sites=eligible_charging_sites,
                  eligibility=eligibility, query=query, bindings=bindings)
    try:
        original = canonical(inputs)
        detached = json.loads(original)
        baseline_sites = detached["baseline_sites"]
        eligible_charging_sites = detached["eligible_charging_sites"]
        eligibility, query, bindings = (detached[k] for k in ("eligibility", "query", "bindings"))
        _require(type(cap) is int and cap > 0, "Candidate cap must be a positive integer")
        _require(all(type(v) is dict for v in (eligibility, query, bindings)),
                 "Invalid eligibility, query or bindings")
        signature = _graph_signature(graph)
        n = graph.node_count
        sources, catalog_sources = bindings.get("source_sha256"), bindings.get("catalog_source_sha256")
        _source_mapping(sources, "source_sha256", {"nodes", "edges", "router"})
        _source_mapping(catalog_sources, "catalog_source_sha256", {"sites", "pools", "geo", "slate"})
        for key in ("baseline_domain_sha256", "baseline_candidate_sha256", "baseline_sites_sha256",
                    "eligible_catalog_sha256", "eligibility_sha256", "query_sha256", "native_provenance_sha256"):
            _sha(bindings.get(key), key)
        for key, value in (("baseline_sites_sha256", baseline_sites),
                           ("eligible_catalog_sha256", eligible_charging_sites),
                           ("eligibility_sha256", eligibility), ("query_sha256", query)):
            _require(digest(canonical(value)) == bindings[key], "Canonical input drift: " + key)
        _require(query.get("sparse_domain_sha256") == bindings["baseline_domain_sha256"],
                 "Baseline domain/query drift")
        _require(type(query.get("case_id")) is str and bool(query["case_id"]), "Missing actual query ID")
        origin = _road_node(query.get("origin"), n, "origin")
        destination = _road_node(query.get("destination"), n, "destination")
        initial, floor, reserve, consumption = (_fraction(query.get(k), k) for k in ENERGY_KEYS)
        _require(0 <= floor <= reserve and initial >= floor and consumption > 0,
                 "Invalid original energy policy")
        if "capacity_kwh" in query:
            capacity = _fraction(query["capacity_kwh"], "capacity_kwh")
            _require(initial <= capacity and reserve <= capacity, "Energy policy exceeds capacity")
        baseline = _site_rows(baseline_sites, n, "baseline_sites")
        catalog = _site_rows(eligible_charging_sites, n, "eligible_charging_sites")
        _require(bool(baseline), "Empty baseline candidate domain")
        baseline_ids = sorted(baseline)
        _require(digest(canonical(baseline_ids)) == bindings["baseline_candidate_sha256"],
                 "Baseline candidate identity drift")
        expected_keys = {"schema", "policy_version", "complete", "source_sha256", "query_sha256",
                         "origin", "destination", "od_id", "origin_site_id", "destination_site_id",
                         "radius_m", "eligible_charging_count", "eligible_candidate_sha256", "eligible_sites_sha256"}
        _require(set(eligibility) == expected_keys, "Incomplete or unsupported eligibility identity")
        _require(eligibility["schema"] == ELIGIBILITY_SCHEMA
                 and eligibility["policy_version"] == ELIGIBILITY_POLICY
                 and eligibility["complete"] is True, "Unsupported or incomplete original eligibility")
        for key, value in (("source_sha256", catalog_sources), ("query_sha256", bindings["query_sha256"]),
                           ("origin", query["origin"]), ("destination", query["destination"]),
                           ("eligible_sites_sha256", bindings["eligible_catalog_sha256"]),
                           ("eligible_candidate_sha256", digest(canonical(sorted(catalog))))):
            _require(eligibility[key] == value, "Eligibility identity drift: " + key)
        _require(type(eligibility["eligible_charging_count"]) is int
                 and eligibility["eligible_charging_count"] == len(catalog), "Eligible catalog count drift")
        _require(all(type(eligibility[k]) is str and bool(eligibility[k])
                     for k in ("od_id", "origin_site_id", "destination_site_id")), "Missing OD endpoint identity")
        _require(_fraction(eligibility["radius_m"], "radius_m") >= 0, "Invalid original corridor radius")
        for sid, row in catalog.items():
            _require("C" in row["effects"], "Non-charging site in eligible charging catalog: " + sid)
            _require(row["access_node"] not in (origin, destination)
                     and sid not in (eligibility["origin_site_id"], eligibility["destination_site_id"]),
                     "Eligible charger violates original endpoint exclusion: " + sid)
            if sid in baseline:
                _require(row == baseline[sid], "Baseline/catalog original row drift: " + sid)
        _require(all(sid in catalog for sid, row in baseline.items() if "C" in row["effects"]),
                 "Original charging baseline missing from complete eligible catalog")

        def check_graph():
            _require(_graph_signature(graph) == signature, "Loaded graph changed during query")

        one = OneSourceRouter(router, origin, bindings["native_provenance_sha256"], check_graph)
        _require(one.provenance.get("source_sha256") == sources["router"], "Router source binding drift")
        anchors = {"road:" + str(node): node for node in sorted({origin} | {r["access_node"] for r in catalog.values()})}
        provider = TableFreeRoadSelectedLegProvider(
            graph, one, anchors, nodes_sha256=sources["nodes"], edges_sha256=sources["edges"],
            router_sha256=sources["router"], anchor_catalog_sha256=digest(canonical(anchors)),
            source_cache_max_bytes=TableFreeRoadSelectedLegProvider.source_cache_entry_bytes(n) + 4096,
            source_cache_max_sources=1)
        phase = "selected_leg_observation"
        verdicts = {}
        for node in sorted({r["access_node"] for r in catalog.values()}):
            name = "road:" + str(node)
            key = (query["origin"], name)
            try:
                one.check()
                leg = provider.leg(*key)
                _require(one.calls == provider.source_run_count == 1, "One-source accounting drift")
                _require(len(provider._source_labels) == 1 and provider.source_cache_skips == 0
                         and provider.source_cache_evictions == 0, "Native source labels were not retained once")
                arrival = initial - leg.actual_length * consumption if leg.reachable else None
                path = provider.edge_witnesses[key]
                verdicts[node] = dict(anchor_node=node, road_reachable=leg.reachable,
                    selected_distance_m=str(leg.actual_length) if leg.reachable else None,
                    arrival_energy_kwh=str(arrival) if arrival is not None else None,
                    minimum_floor_pass=arrival is not None and arrival >= floor,
                    reserve_pass=arrival is not None and arrival >= reserve,
                    edge_path_sha256=digest(canonical(list(path) if path is not None else None)))
                completed_anchors += 1
                one.check()
            finally:
                provider.legs.pop(key, None)
                provider.edge_witnesses.pop(key, None)
        phase = "completion_validation"
        one.check()
        _require(canonical(inputs) == original, "Caller inputs changed during query")
        _require(one.calls == (1 if catalog else 0), "Completed source-call count drift")
        added_ids = sorted(sid for sid, row in catalog.items()
                           if sid not in baseline and verdicts[row["access_node"]]["minimum_floor_pass"])
        candidate_ids = sorted(set(baseline) | set(added_ids))
        counts = dict(baseline=len(baseline), eligible_chargers=len(catalog),
                      unique_eligible_anchors=len(verdicts), completed_anchors=completed_anchors,
                      added=len(added_ids), total=len(candidate_ids),
                      added_unique_anchors=len({catalog[sid]["access_node"] for sid in added_ids}),
                      added_floor_pass_reserve_fail=sum(not verdicts[catalog[sid]["access_node"]]["reserve_pass"]
                                                       for sid in added_ids))
        accounting = dict(source_runs=one.calls, source_completed_runs=provider.source_run_count,
                          source_cache_max_sources=1, source_cache_max_bytes=provider.source_cache_max_bytes,
                          per_target_witnesses_cleared=True, source_labels_released_on_return=True)
        if len(candidate_ids) > cap:
            return _result(ProposalStatus.FALLBACK_REQUIRED, complete=True, reason_code="candidate_cap_overflow",
                           reason="Complete union exceeds cap; no truncated candidate domain is returned",
                           cap=cap, counts=counts, bindings=bindings, **accounting)
        sites = [baseline[sid] if sid in baseline else catalog[sid] for sid in candidate_ids]
        candidate_sha = digest(canonical(candidate_ids))
        descriptor = dict(schema=SCHEMA, rule_version=RULE_VERSION, state="proposed_complete",
                          candidate_ids=candidate_ids, candidate_sha256=candidate_sha,
                          baseline_ids=baseline_ids, added_ids=added_ids,
                          complete_site_rows_sha256=digest(canonical(sites)), bindings=bindings,
                          eligibility=eligibility, cap=cap, cap_role="resource_guard_never_truncation",
                          inclusion_threshold="original_minimum_energy_kwh", reserve_role="evidence_only",
                          query_sha256=bindings["query_sha256"],
                          anchor_verdicts_sha256=digest(canonical([verdicts[node] for node in sorted(verdicts)])),
                          loaded_sparse_domain_sha256=None, runtime_admission_complete=False, launchable=False)
        return _result(ProposalStatus.PROPOSED_COMPLETE, complete=True, reason_code="complete_union",
                       reason="Complete proposal requires guarded domain derivation and fresh physical seed replay",
                       candidate_ids=candidate_ids, sites=sites, descriptor=descriptor,
                       domain_sha256=digest(canonical(descriptor)),
                       domain_sha256_meaning="proposal_descriptor_only_not_loaded_sparse_domain",
                       candidate_sha256=candidate_sha, baseline_ids=baseline_ids, added_ids=added_ids,
                       counts=counts, cap=cap, bindings=bindings, unchanged_query=query,
                       anchor_verdicts=[verdicts[node] for node in sorted(verdicts)], **accounting)
    except Exception as exc:
        return _result(ProposalStatus.UNKNOWN, reason_code="incomplete_" + phase,
                       reason=type(exc).__name__ + ": " + str(exc), completed_anchors=completed_anchors,
                       source_runs=0 if one is None else one.calls,
                       source_completed_runs=0 if provider is None else provider.source_run_count)
    finally:
        if provider is not None:
            provider.legs.clear()
            provider.edge_witnesses.clear()
            provider._source_labels.clear()
            provider.source_cache_bytes = 0
