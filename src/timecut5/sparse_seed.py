"""Sparse real seed admission against complete graph and Site source bindings.

Only proposal legs are routed. Missing pairs remain unknown, never unreachable.
The replay below reads edge identities and physical inputs independently of the
formal FLAT/HIER adapter and does not invoke a continuous optimizer.
"""
from __future__ import annotations

from fractions import Fraction as R
import hashlib
import json
import time
from pathlib import Path
from typing import Mapping

from .real_adapter import site_catalog_digest
from .road_provider import TableFreeRoadSelectedLegProvider


class SeedInfeasible(ValueError):
    """A finite proposal failed physical replay; source failures stay fatal."""


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sparse_domain_digest(source_hashes, site_catalog_sha256, candidate_sha256,
                         hierarchy_sha256, origin_anchor, destination_anchor):
    return hashlib.sha256(json.dumps({
        "graph": source_hashes, "sites": site_catalog_sha256,
        "candidates": candidate_sha256, "hierarchy": hierarchy_sha256,
        "origin": origin_anchor, "destination": destination_anchor},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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
        self.domain_sha256 = sparse_domain_digest(provider.source_sha256,
            site_catalog_sha256, candidate_sha256, hierarchy_sha256,
            origin_anchor, destination_anchor)

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


def replay_sparse_seed(query: Mapping, catalog: SparseSeedCatalog, sequence, charges,
                       *, sequential_no_overlap=False, include_events=False):
    """Independently replay exact physical events and every selected edge."""
    if (query.get("sparse_domain_sha256") != catalog.domain_sha256 or
            query.get("origin") != catalog.origin_anchor or
            query.get("destination") != catalog.destination_anchor or
            query.get("hierarchy_sha256") != catalog.hierarchy_sha256):
        raise ValueError("Sparse query differs from full source domain")
    validate_sparse_query(query, catalog)
    charges = tuple(charges)
    if any(type(amount) not in (int, str, R) for amount in charges):
        raise ValueError("Seed charge quantities must be exact non-boolean rationals")
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
    events = []
    total_distance = R(0)

    def edge_leg(source, target):
        nonlocal total_distance
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
        total_distance += leg.actual_length
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
        arrival_time, arrival_energy = time, energy
        release = time + overhead
        charge_start = charge_done = service_start = service_done = None
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
            charge_start, charge_done = release, release + duration
            done.append(charge_done)
        if effect in ("S", "CS"):
            service_release = done[0] if sequential_no_overlap and effect == "CS" else release
            start = max(R(schedule["a"]), service_release)
            if start > R(schedule["b"]):
                raise SeedInfeasible("Schedule infeasible")
            service_start, service_done = start, start + R(schedule["D"])
            done.append(service_done)
            pending = 0
        time = max(done)
        if include_events:
            overlap = (max(R(0), min(charge_done, service_done) -
                           max(charge_start, service_start))
                       if effect == "CS" else R(0))
            events.append(dict(site_id=site_id, effect=effect, arrival=arrival_time,
                release=release, charge_start=charge_start, charge_done=charge_done,
                service_start=service_start, service_done=service_done, departure=time,
                arrival_energy_kwh=arrival_energy, departure_energy_kwh=energy,
                window_margin_s=(R(schedule["b"]) - service_start
                                 if service_start is not None else None),
                overlap_s=overlap))
        current = site.anchor_id
    if pending:
        raise SeedInfeasible("Schedule unfulfilled")
    travel, consumption = edge_leg(current, catalog.destination_anchor)
    time, energy = time + travel, energy - consumption
    if not reserve <= energy <= capacity:
        raise SeedInfeasible("Terminal reserve infeasible")
    key = (time - f("start_time_s") + len(sequence) * f("lambda_stop_s"),
           sum(charges, R(0)), len(sequence), sequence)
    result = {"lex_key": key, "edge_witnesses": tuple(edges_used),
              "domain_sha256": catalog.domain_sha256,
              "source_run_count": catalog.provider.source_run_count}
    if include_events:
        result.update(events=tuple(events), distance_m=total_distance,
                      elapsed_s=time - f("start_time_s"), arrival_time_s=time,
                      terminal_energy_kwh=energy,
                      overlap_s=sum((event["overlap_s"] for event in events), R(0)))
    return result


def sequential_no_overlap_baseline(query: Mapping, catalog: SparseSeedCatalog):
    """Best feasible fixed proposal with charging completed before service starts.

    This is a deterministic construction baseline, not an exact solver. Every
    candidate is replayed with the same selected road edges and battery rules.
    """
    from .deployable import constructive_seed_candidates
    validate_sparse_query(query, catalog)
    proposals = constructive_seed_candidates(query, catalog)
    accepted = []
    for ordinal, (sequence, charges) in enumerate(proposals):
        try:
            replay = replay_sparse_seed(query, catalog, sequence, charges,
                                        sequential_no_overlap=True)
        except SeedInfeasible:
            continue
        accepted.append((replay["lex_key"], ordinal, sequence, charges,
                         replay["edge_witnesses"]))
    if not accepted:
        return {"status": "no_feasible_proposal", "proposal_count": len(proposals),
                "domain_sha256": catalog.domain_sha256}
    key, ordinal, sequence, charges, witnesses = min(accepted)
    return {"status": "feasible", "proposal_ordinal": ordinal,
            "proposal_count": len(proposals), "accepted_count": len(accepted),
            "lex_key": key, "sequence": sequence, "charges": charges,
            "domain_sha256": catalog.domain_sha256,
            "edge_witnesses": witnesses,
            "source_run_count": catalog.provider.source_run_count}


def first_sequential_feasible(query: Mapping, catalog: SparseSeedCatalog, *, observer=None):
    """Stop at the first sequentially feasible member of the fixed candidate stream.

    This opt-in construction does not change the generator's concurrent CS
    clock, ordering or beam pruning. It is neither a sequential search nor a
    finite-stream minimum. Only finite proposal infeasibility is skipped;
    invalid inputs, source/generation failures and observer errors propagate.
    Exhaustion means unknown, never proof of infeasibility.

    ``observer("first_feasible", **snapshot)`` is called immediately after
    replay, before any further generation. The snapshot contains the complete
    exact replay payload and source/query provenance for caller-owned durable
    storage and subsequent replay with an independently loaded fresh provider.
    No persistence or fresh-provider verification is claimed by this function.
    """
    from copy import deepcopy
    from .deployable import iter_constructive_seed_candidates

    validate_sparse_query(query, catalog)
    query_payload = json.loads(json.dumps(query, sort_keys=True, default=str))
    provenance = {
        "construction": "fixed_candidate_stream_sequential_feasibility",
        "generator": "iter_constructive_seed_candidates",
        "generator_cs_clock": "concurrent",
        "replay_policy": "sequential_no_overlap",
        "source_sha256": dict(catalog.provider.source_sha256),
        "site_catalog_sha256": catalog.site_catalog_sha256,
        "candidate_sha256": catalog.candidate_sha256,
        "hierarchy_sha256": catalog.hierarchy_sha256,
        "site_count": len(catalog.sites),
        "origin_anchor": catalog.origin_anchor,
        "destination_anchor": catalog.destination_anchor,
        "query": query_payload,
        "query_sha256": hashlib.sha256(json.dumps(
            query_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
    common = dict(domain_sha256=catalog.domain_sha256, provenance=provenance,
                  exact_optimum_claimed=False, finite_stream_minimum_claimed=False,
                  fresh_provider_verified=False)
    proposal_count = 0
    proposals = iter_constructive_seed_candidates(query, catalog)
    for ordinal, (sequence, charges) in enumerate(proposals):
        proposal_count += 1
        # Freeze the payload before replay and preserve exact rational charges.
        sequence, charges = tuple(map(tuple, sequence)), tuple(charges)
        try:
            replay = replay_sparse_seed(query, catalog, sequence, charges,
                                        sequential_no_overlap=True)
        except SeedInfeasible:
            continue
        result = dict(common, status="first_feasible", generation_complete=False,
                      proposal_ordinal=ordinal, proposal_count=proposal_count,
                      accepted_count=1, sequence=sequence,
                      charges=tuple(map(R, charges)), lex_key=replay["lex_key"],
                      edge_witnesses=replay["edge_witnesses"],
                      source_run_count=catalog.provider.source_run_count)
        if observer is not None:
            observer("first_feasible", **deepcopy(result))
        return result
    return dict(common, status="unknown", reason="no_sequential_feasible_proposal",
                generation_complete=True, proposal_count=proposal_count,
                accepted_count=0, source_run_count=catalog.provider.source_run_count)


def admit_sparse_seed(query: Mapping, catalog: SparseSeedCatalog, *, observer=None):
    """Replay proposals as generated, retaining the original finite-stream minimum.

    Optional ``observer(event, **snapshot)`` receives immutable proposal tuples
    and independent dictionaries. An ``incumbent`` event is an independently
    replayed feasible upper bound, not the final finite-stream selection or an
    exact optimum. Generation/source errors (including interruption) propagate;
    no partial incumbent is silently returned as a completed seed certificate.
    Observer errors also propagate. With no observer the return schema is
    unchanged. The fresh final replay and depth check still occur only after
    the entire proposal stream has completed successfully.
    """
    from .deployable import iter_constructive_seed_candidates
    validate_sparse_query(query, catalog)
    proposal_count = accepted_count = 0
    best = None

    def notify(event, **extra):
        if observer is not None:
            snapshot = dict(proposal_count=proposal_count,
                            accepted_count=accepted_count,
                            generation_complete=False,
                            domain_sha256=catalog.domain_sha256,
                            source_run_count=catalog.provider.source_run_count,
                            exact_optimum_claimed=False)
            snapshot.update(extra)
            observer(event, **snapshot)

    def measured(event, action):
        notify(event + "_begin")
        started = time.monotonic_ns(), time.process_time_ns()
        try:
            value = action()
        except BaseException as error:
            elapsed = dict(wall_ns=time.monotonic_ns() - started[0],
                           cpu_ns=time.process_time_ns() - started[1])
            try:
                notify(event, outcome="end" if isinstance(error, StopIteration) else "error",
                       error_type=type(error).__name__, error_message=str(error), **elapsed)
            except BaseException as observer_error:
                if isinstance(error, (StopIteration, SeedInfeasible)):
                    raise
                error.add_note("Streaming observer failed: " + repr(observer_error))
            return None, error
        elapsed = dict(wall_ns=time.monotonic_ns() - started[0],
                       cpu_ns=time.process_time_ns() - started[1])
        notify(event, outcome="success", **elapsed)
        return value, None

    notify("generation_begin")
    proposals = iter_constructive_seed_candidates(query, catalog)
    while True:
        proposal, error = measured("generation_step", lambda: next(proposals))
        if isinstance(error, StopIteration):
            break
        if error is not None:
            raise error
        sequence, charges = proposal
        proposal_count += 1
        notify("proposal", sequence=sequence, charges=charges)
        notify("replay_attempt")
        result, error = measured("replay_step", lambda: replay_sparse_seed(
            query, catalog, sequence, charges))
        if isinstance(error, SeedInfeasible):
            notify("replay_rejected", reason=str(error))
            continue
        if error is not None:
            raise error
        accepted_count += 1
        candidate = (result["lex_key"], sequence, charges)
        if best is None or candidate < best:
            best = candidate
            notify("incumbent", lex_key=result["lex_key"], sequence=sequence,
                   charges=charges, edge_witnesses=result["edge_witnesses"],
                   status="replayed_feasible_incumbent")
        else:
            notify("replay_accepted")
    notify("generation_end", generation_complete=True)
    if best is None:
        return {"status": "incumbent_search_failed", "proposal_count": proposal_count,
                "domain_sha256": catalog.domain_sha256}
    key, sequence, charges = best
    fresh, error = measured("fresh_replay_step", lambda: replay_sparse_seed(
        query, catalog, sequence, charges))
    if error is not None:
        raise error
    if fresh["lex_key"] != key:
        raise ValueError("Fresh selected-edge seed replay disagrees")
    minimum = R(query["overhead_s"]) + R(query["lambda_stop_s"])
    if minimum <= 0:
        raise ValueError("Positive stop lower cost required for depth certification")
    depth = key[0] // minimum
    result = {"status": "verified", "lex_key": key, "sequence": sequence,
            "charges": charges, "max_depth": depth,
            "proposal_count": proposal_count, "accepted_count": accepted_count,
            "domain_sha256": catalog.domain_sha256,
            "source_run_count": catalog.provider.source_run_count,
            "fresh_edge_witnesses": fresh["edge_witnesses"]}
    notify("seed_verified", generation_complete=True, lex_key=key,
           sequence=sequence, charges=charges, max_depth=depth)
    return result


def first_feasible_proposal_baseline(query: Mapping, catalog: SparseSeedCatalog):
    """Deterministic feasible construction comparator, with no optimum claim.

    It uses the same fixed proposal stream and independent physical replay as
    seed admission, returning the first feasible proposal rather than searching
    for the best key. Proposal-generation and routing cost remain chargeable.
    """
    from .deployable import constructive_seed_candidates
    validate_sparse_query(query, catalog)
    proposals = constructive_seed_candidates(query, catalog)
    for ordinal, (sequence, charges) in enumerate(proposals):
        try:
            replay = replay_sparse_seed(query, catalog, sequence, charges)
        except SeedInfeasible:
            continue
        return {"status": "feasible", "proposal_ordinal": ordinal,
            "proposal_count": len(proposals), "lex_key": replay["lex_key"],
            "sequence": sequence, "charges": charges,
            "domain_sha256": catalog.domain_sha256,
            "edge_witnesses": replay["edge_witnesses"],
            "source_run_count": catalog.provider.source_run_count}
    return {"status": "no_feasible_proposal", "proposal_count": len(proposals),
            "domain_sha256": catalog.domain_sha256}
