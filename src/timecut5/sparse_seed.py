"""Sparse real seed admission against complete graph and Site source bindings.

Only proposal legs are routed. Missing pairs remain unknown, never unreachable.
The replay below reads edge identities and physical inputs independently of the
formal FLAT/HIER adapter and does not invoke a continuous optimizer.
"""
from __future__ import annotations

from fractions import Fraction as R
import hashlib
import json
from pathlib import Path
from typing import Mapping

from .real_adapter import site_catalog_digest
from .road_provider import TableFreeRoadSelectedLegProvider


class SeedInfeasible(ValueError):
    """A finite proposal failed physical replay; source failures stay fatal."""


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SparseSeedCatalog:
    def __init__(self, provider: TableFreeRoadSelectedLegProvider, sites: Mapping,
                 *, origin_anchor: str, destination_anchor: str,
                 nodes_path, edges_path, site_catalog_sha256: str,
                 hierarchy_sha256: str, candidate_sha256: str):
        if not isinstance(provider, TableFreeRoadSelectedLegProvider):
            raise ValueError("Native selected-edge provider required")
        if (_hash(nodes_path) != provider.source_sha256["nodes"] or
                _hash(edges_path) != provider.source_sha256["edges"]):
            raise ValueError("Original graph bytes differ from loaded-array binding")
        self.sites = dict(sites)
        if (site_catalog_digest(self.sites) != site_catalog_sha256 or
                origin_anchor not in provider.anchor_nodes or
                destination_anchor not in provider.anchor_nodes or
                any(site.site_id != sid or site.anchor_id not in provider.anchor_nodes
                    for sid, site in self.sites.items())):
            raise ValueError("Full Site and anchor universe binding mismatch")
        candidates = json.dumps(sorted(self.sites), separators=(",", ":")).encode()
        if hashlib.sha256(candidates).hexdigest() != candidate_sha256:
            raise ValueError("Complete candidate universe binding mismatch")
        self.provider = provider
        self.origin_anchor, self.destination_anchor = origin_anchor, destination_anchor
        self.site_catalog_sha256 = site_catalog_sha256
        self.hierarchy_sha256 = hierarchy_sha256
        self.candidate_sha256 = candidate_sha256
        self.domain_sha256 = hashlib.sha256(json.dumps({
            "graph": provider.source_sha256, "sites": site_catalog_sha256,
            "candidates": candidate_sha256, "hierarchy": hierarchy_sha256,
            "origin": origin_anchor, "destination": destination_anchor},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def site(self, site_id):
        return self.sites[site_id]

    def leg(self, source, target):
        return self.provider.leg(source, target)


def validate_sparse_query(query: Mapping, catalog: SparseSeedCatalog):
    """Apply the independent full physical-input checks without a leg table."""
    from validation.reference5.model import normalize_case
    def has_float(value):
        if type(value) is float:
            return True
        if isinstance(value, Mapping):
            return any(has_float(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(has_float(item) for item in value)
        return False
    if (not isinstance(query, Mapping) or "sites" in query or "edges" in query or
            has_float(query)):
        raise ValueError("Sparse query must not override the bound Site/edge domain or use floats")
    declared = {sid: list(site.effects) for sid, site in catalog.sites.items()}
    return normalize_case(dict(query, sites=declared, edges=[]))


def replay_sparse_seed(query: Mapping, catalog: SparseSeedCatalog, sequence, charges):
    """Independently replay exact physical events and every selected edge."""
    if (query.get("sparse_domain_sha256") != catalog.domain_sha256 or
            query.get("origin") != catalog.origin_anchor or
            query.get("destination") != catalog.destination_anchor or
            query.get("hierarchy_sha256") != catalog.hierarchy_sha256):
        raise ValueError("Sparse query differs from full source domain")
    validate_sparse_query(query, catalog)
    sequence, charges = tuple(map(tuple, sequence)), tuple(map(R, charges))
    if len(sequence) > query["H_ref"] or len(charges) != sum(
            effect in ("C", "CS") for _, effect in sequence):
        raise SeedInfeasible("Seed event dimensions differ from query")
    f = lambda name: R(query[name])
    capacity, floor, reserve = f("capacity_kwh"), f("minimum_energy_kwh"), f("reserve_kwh")
    energy, time = f("initial_energy_kwh"), f("start_time_s")
    rate, overhead = f("consumption_kwh_per_m"), f("overhead_s")
    if not 0 <= floor <= energy <= capacity or not floor <= reserve <= capacity:
        raise ValueError("Invalid physical battery domain")
    schedule = query.get("schedule")
    pending = query.get("initial_remaining_schedule", int(schedule is not None))
    if pending not in (0, 1) or pending and schedule is None:
        raise ValueError("Invalid schedule state")
    segments = tuple(tuple(map(R, row)) for row in query["charging_segments"])
    current, charge_index = catalog.origin_anchor, 0
    edges_used = []

    def edge_leg(source, target):
        leg = catalog.leg(source, target)
        path = catalog.provider.edge_witnesses[source, target]
        if not leg.reachable or path is None:
            raise SeedInfeasible("Proposed leg is unreachable")
        node = catalog.provider.anchor_nodes[source]
        total_time = total_length = 0.0
        graph = catalog.provider.graph
        for edge in path:
            if int(graph.source[edge]) != node:
                raise ValueError("Selected edge chain is broken")
            node = int(graph.target[edge])
            total_time += float(graph.weights["travel_time"][edge])
            total_length += float(graph.weights["distance"][edge])
        if (node != catalog.provider.anchor_nodes[target] or
                R(*total_time.as_integer_ratio()) != leg.time or
                R(*total_length.as_integer_ratio()) != leg.actual_length):
            raise ValueError("Selected edge replay differs from native label")
        edges_used.append(tuple(path))
        return leg.time, leg.actual_length * rate

    for site_id, effect in sequence:
        if site_id not in catalog.sites:
            raise SeedInfeasible("Unknown Site")
        site = catalog.sites[site_id]
        if (effect not in site.effects or site.anchor_id == catalog.destination_anchor or
                current == catalog.destination_anchor or
                effect in ("S", "CS") and pending != 1):
            raise SeedInfeasible("Unsupported or terminal Site effect")
        travel, consumption = edge_leg(current, site.anchor_id)
        time, energy = time + travel, energy - consumption
        if not floor <= energy <= capacity:
            raise SeedInfeasible("Arrival energy infeasible")
        release = time + overhead
        done = []
        if effect in ("C", "CS"):
            amount = charges[charge_index]
            charge_index += 1
            if amount <= 0 or energy + amount > capacity:
                raise SeedInfeasible("Charge infeasible")
            before = energy
            energy += amount
            duration = sum((max(R(0), min(energy, hi) - max(before, lo)) * slope
                            for lo, hi, slope, _ in segments), R(0))
            done.append(release + duration)
        if effect in ("S", "CS"):
            start = max(R(schedule["a"]), release)
            if start > R(schedule["b"]):
                raise SeedInfeasible("Schedule infeasible")
            done.append(start + R(schedule["D"]))
            pending = 0
        time = max(done)
        current = site.anchor_id
    if pending:
        raise SeedInfeasible("Schedule unfulfilled")
    travel, consumption = edge_leg(current, catalog.destination_anchor)
    time, energy = time + travel, energy - consumption
    if not reserve <= energy <= capacity:
        raise SeedInfeasible("Terminal reserve infeasible")
    key = (time - f("start_time_s") + len(sequence) * f("lambda_stop_s"),
           sum(charges, R(0)), len(sequence), sequence)
    return {"lex_key": key, "edge_witnesses": tuple(edges_used),
            "domain_sha256": catalog.domain_sha256, "source_run_count": catalog.provider.source_run_count}


def admit_sparse_seed(query: Mapping, catalog: SparseSeedCatalog):
    """Select the best independently replayed deterministic proposal and depth."""
    from .deployable import constructive_seed_candidates
    validate_sparse_query(query, catalog)
    accepted = []
    proposals = constructive_seed_candidates(query, catalog)
    for sequence, charges in proposals:
        try:
            result = replay_sparse_seed(query, catalog, sequence, charges)
        except SeedInfeasible:
            continue
        accepted.append((result["lex_key"], sequence, charges))
    if not accepted:
        return {"status": "incumbent_search_failed", "proposal_count": len(proposals),
                "domain_sha256": catalog.domain_sha256}
    key, sequence, charges = min(accepted)
    fresh = replay_sparse_seed(query, catalog, sequence, charges)
    if fresh["lex_key"] != key:
        raise ValueError("Fresh selected-edge seed replay disagrees")
    minimum = R(query["overhead_s"]) + R(query["lambda_stop_s"])
    if minimum <= 0:
        raise ValueError("Positive stop lower cost required for depth certification")
    depth = key[0] // minimum
    return {"status": "verified", "lex_key": key, "sequence": sequence,
            "charges": charges, "max_depth": depth,
            "proposal_count": len(proposals), "accepted_count": len(accepted),
            "domain_sha256": catalog.domain_sha256,
            "source_run_count": catalog.provider.source_run_count,
            "fresh_edge_witnesses": fresh["edge_witnesses"]}
