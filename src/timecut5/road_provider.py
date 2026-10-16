"""Source-bound selected-road-leg provider with native edge witnesses.

The graph-file hashes must be verified by the caller before arrays are loaded.
Each new source runs the accepted forward native policy once, reconstructs all
declared target paths by edge identity, and compares exact binary64 totals with
the frozen table. It caches only selected target legs and witnesses.
"""
from __future__ import annotations

from . import exact_progress as progress

from functools import wraps
from collections import OrderedDict
from fractions import Fraction
import sys
import hashlib
import json
import math
import time
from typing import Mapping

from .real_legs import ImmutableLegTable, SelectedLeg, TIE_POLICY


def _guard_selected_routing(function):
    """Opt-in arithmetic-history guard, including cached returns and replay.

    Default-off behavior is the original call. A guard is attached only before
    first use, and errors never turn a partial route into trusted cache history.
    """
    @wraps(function)
    def guarded(self, *args, **kwargs):
        guard = getattr(self, '_terminal_energy_route_guard', None)
        if guard is None:
            return function(self, *args, **kwargs)
        guard.begin(self)
        try:
            result = function(self, *args, **kwargs)
            guard.end(self)
            return result
        except BaseException:
            guard.abort()
            raise
    return guarded


class TableFreeRoadSelectedLegProvider:
    """Route selected anchors from the graph without constructing a leg table.

    The caller supplies a byte-bound anchor catalog and graph/router identities.
    Requested target legs retain the exact native predecessor-edge witness.
    A bounded, provider-local LRU can reuse owned source labels between targets.
    Set source_cache_max_bytes=0 to retain the original uncached behavior.
    Graph arrays and the router must remain immutable for the provider lifetime,
    as already required by the selected-leg cache and byte bindings.
    """

    def __init__(self, graph, router, anchor_nodes: Mapping[str, int], *,
                 nodes_sha256: str, edges_sha256: str, router_sha256: str,
                 anchor_catalog_sha256: str,
                 source_cache_max_bytes: int = 128 * 1024 * 1024,
                 source_cache_max_sources: int = 2):
        import re
        if (type(source_cache_max_bytes) is not int or source_cache_max_bytes < 0 or
                type(source_cache_max_sources) is not int or source_cache_max_sources < 0):
            raise ValueError("Source cache limits must be nonnegative integers")
        hashes = (nodes_sha256, edges_sha256, router_sha256, anchor_catalog_sha256)
        if any(type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
               for value in hashes):
            raise ValueError("Complete graph, router and anchor byte bindings required")
        anchors = dict(anchor_nodes)
        if (not anchors or len(set(anchors.values())) != len(anchors) or
                any(type(name) is not str or not name or type(node) is not int or
                    not 0 <= node < graph.node_count for name, node in anchors.items())):
            raise ValueError("Invalid or duplicate road anchors")
        catalog = json.dumps(anchors, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(catalog).hexdigest() != anchor_catalog_sha256:
            raise ValueError("Road anchor catalog bytes differ from binding")
        provenance = getattr(router, "provenance", None)
        if not isinstance(provenance, dict) or provenance.get("source_sha256") != router_sha256:
            raise ValueError("Native router source differs from binding")
        self.graph, self.router, self.anchor_nodes = graph, router, anchors
        self.source_sha256 = dict(nodes=nodes_sha256, edges=edges_sha256,
                                  router=router_sha256, anchors=anchor_catalog_sha256,
                                  tie_policy=hashlib.sha256(TIE_POLICY.encode()).hexdigest())
        # The legacy full-only source map stays byte-for-byte compatible. New
        # explicit role contexts bind the authenticated native semantics/build.
        if getattr(router, "role", None) is not None:
            verify = getattr(router, "verify_artifact", None)
            if not callable(verify) or not callable(getattr(router, "validate_binding", None)):
                raise ValueError("Owned native boundary required for explicit roles")
            verify()
            artifact = getattr(router, "artifact", None)
            if (not isinstance(artifact, dict) or
                    any(type(artifact.get(k)) is not str or
                        re.fullmatch(r"[0-9a-f]{64}", artifact[k]) is None
                        for k in ("semantic_contract_sha256", "artifact_identity_sha256"))):
                raise ValueError("Authenticated explicit-role native identity required")
            self.source_sha256.update(
                settlement_policy=artifact["semantic_contract_sha256"],
                native_artifact=artifact["artifact_identity_sha256"])
        self.legs: dict[tuple[str, str], SelectedLeg] = {}
        self.edge_witnesses: dict[tuple[str, str], tuple[int, ...] | None] = {}
        self.source_cache_max_bytes = source_cache_max_bytes
        self.source_cache_max_sources = source_cache_max_sources
        self._source_labels = OrderedDict()
        self.source_cache_bytes = 0
        self.source_cache_hits = 0
        self.source_cache_evictions = 0
        self.source_cache_skips = 0
        self.source_run_count = 0
        self.target_run_count = 0
        self.route_wall_ns = 0
        self.route_process_cpu_ns = 0

    @staticmethod
    def source_cache_entry_bytes(node_count):
        """Retained bytes for four native arrays, including ndarray/tuple objects."""
        import numpy as np
        if type(node_count) is not int or node_count < 0:
            raise ValueError("Node count must be a nonnegative integer")
        return (32 * node_count + 4 * sys.getsizeof(np.empty(0, dtype=np.float64))
                + sys.getsizeof((None, None, None, None)))

    def _evict_source_labels(self, size):
        while self._source_labels and (
                self.source_cache_bytes + size > self.source_cache_max_bytes or
                len(self._source_labels) >= self.source_cache_max_sources):
            _, (_, old_size) = self._source_labels.popitem(last=False)
            self.source_cache_bytes -= old_size
            self.source_cache_evictions += 1

    @progress.operation('road_labels')
    @_guard_selected_routing
    def _labels(self, source_node):
        cached = self._source_labels.pop(source_node, None)
        if cached is not None:
            self._source_labels[source_node] = cached
            self.source_cache_hits += 1
            return cached[0]
        if self.source_cache_max_bytes and self.source_cache_max_sources:
            expected_size = self.source_cache_entry_bytes(self.graph.node_count)
            if expected_size <= self.source_cache_max_bytes:
                # Release the replacement entry before native output allocation,
                # not merely before copying it. A failing route may lose only
                # this performance cache, never selected-leg semantic state.
                self._evict_source_labels(expected_size)
        labels = self.router.full_edges(source_node)
        self.source_run_count += 1
        if not self.source_cache_max_bytes or not self.source_cache_max_sources:
            return labels
        # Only native, owned-copy-compatible binary64/int64 arrays are admitted.
        # Never retain a caller's view or mutable scratch buffers. The budget
        # includes each ndarray object and its data, not merely logical nbytes.
        import numpy as np
        expected = (np.dtype('float64'), np.dtype('float64'),
                    np.dtype('int64'), np.dtype('int64'))
        if len(labels) != 4 or any(
                not isinstance(a, np.ndarray) or a.shape != (self.graph.node_count,) or
                a.dtype != dtype for a, dtype in zip(labels, expected)):
            self.source_cache_skips += 1
            return labels
        size = self.source_cache_entry_bytes(self.graph.node_count)
        if size > self.source_cache_max_bytes:
            self.source_cache_skips += 1
            return labels
        # Retain the guard for custom/native output subclasses as well.
        self._evict_source_labels(size)
        owned = tuple(a.copy(order='C') for a in labels)
        for a in owned:
            a.flags.writeable = False
        actual_size = sys.getsizeof(owned) + sum(sys.getsizeof(a) for a in owned)
        if actual_size > self.source_cache_max_bytes:
            self.source_cache_skips += 1
            return labels
        while self._source_labels and self.source_cache_bytes + actual_size > self.source_cache_max_bytes:
            _, (_, old_size) = self._source_labels.popitem(last=False)
            self.source_cache_bytes -= old_size
            self.source_cache_evictions += 1
        self._source_labels[source_node] = owned, actual_size
        self.source_cache_bytes += actual_size
        return owned

    @progress.operation('road_labels')
    def _target_labels(self, source_node, target_node):
        # A full-source cache hit is already final for every target. Reuse it,
        # preserving the original hit counter and LRU promotion behavior.
        cached = self._source_labels.pop(source_node, None)
        if cached is not None:
            self._source_labels[source_node] = cached
            self.source_cache_hits += 1
            return cached[0]
        labels = self.router.target_edges(source_node, target_node)
        self.target_run_count += 1
        # Never admit partial labels into the source-label LRU.
        return labels

    @progress.operation('road_path')
    def _path(self, source_node, target_node, parent, parent_edge):
        if source_node == target_node:
            return ()
        backward = []
        node = target_node
        while node != source_node:
            prior, edge = int(parent[node]), int(parent_edge[node])
            if (prior < 0 or not 0 <= edge < self.graph.edge_count or
                    int(self.graph.source[edge]) != prior or
                    int(self.graph.target[edge]) != node or
                    len(backward) >= self.graph.node_count):
                raise ValueError("Native selected predecessor edge is invalid")
            backward.append(edge)
            node = prior
        return tuple(reversed(backward))

    @progress.operation('road_leg')
    @_guard_selected_routing
    def leg(self, source: str, target: str, *, target_only: bool = False) -> SelectedLeg:
        if type(target_only) is not bool:
            raise ValueError("Explicit target boolean required")
        if getattr(self.router, "role", None) is not None:
            self.router.validate_binding()
        if target_only and (getattr(self.router, "role", None) != "search" or
                            getattr(self.router, "mode", None) != "destination_target"):
            raise ValueError("Target execution is search-only and opt-in")
        if source not in self.anchor_nodes or target not in self.anchor_nodes:
            raise ValueError("Unknown road anchor")
        key = source, target
        if key in self.legs:
            return self.legs[key]
        started_wall, started_cpu = time.monotonic_ns(), time.process_time_ns()
        source_node, target_node = self.anchor_nodes[source], self.anchor_nodes[target]
        costs, lengths, parents, edges = (self._target_labels(source_node, target_node)
            if target_only else self._labels(source_node))
        cost, length = float(costs[target_node]), float(lengths[target_node])
        if math.isinf(cost) and math.isinf(length):
            if int(parents[target_node]) != -1 or int(edges[target_node]) != -1:
                raise ValueError("Unreachable target has a predecessor")
            leg = SelectedLeg(source, target, False, None, None,
                              "forward_from_source", None, None)
            path = None
        elif math.isfinite(cost) and math.isfinite(length) and cost >= 0 and length >= 0:
            path = self._path(source_node, target_node, parents, edges)
            replay_time = replay_length = 0.0
            for edge in path:
                replay_time += float(self.graph.weights["travel_time"][edge])
                replay_length += float(self.graph.weights["distance"][edge])
            if (replay_time, replay_length) != (cost, length):
                raise ValueError("Selected edge witness does not replay native labels")
            leg = SelectedLeg(source, target, True,
                Fraction(*cost.as_integer_ratio()), Fraction(*length.as_integer_ratio()),
                "identity" if source == target else "forward_from_source",
                cost.hex(), length.hex())
        else:
            raise ValueError("Native selected labels have invalid reachability")
        self.legs[key], self.edge_witnesses[key] = leg, path
        self.route_wall_ns += time.monotonic_ns() - started_wall
        self.route_process_cpu_ns += time.process_time_ns() - started_cpu
        return leg


class TableFreeRegionBoundProvider:
    """Indexed ALT bounds certified from graph edges, without selected-leg minima."""

    def __init__(self, leg_provider: TableFreeRoadSelectedLegProvider, sites: Mapping,
                 root, *, destination_anchor: str, landmark_anchor: str,
                 site_catalog_sha256: str, router_factory):
        from .deployable import RegionLandmarkSummary, member_set_digest
        from .road_landmark import certify_integer_landmark
        from .hierarchy import Region
        from .real_adapter import site_catalog_digest
        if (not isinstance(root, Region) or set(root.members) != set(sites) or
                destination_anchor not in leg_provider.anchor_nodes):
            raise ValueError("Table-free Region root must cover every Site")
        if any(sid != site.site_id or site.anchor_id not in leg_provider.anchor_nodes or
               not site.effects or not set(site.effects) <= {"C", "S", "CS"}
               for sid, site in sites.items()):
            raise ValueError("Invalid table-free Region Site catalog")
        if site_catalog_digest(sites) != site_catalog_sha256:
            raise ValueError("Table-free Region Site catalog binding mismatch")
        self.leg_provider, self.sites, self.root = leg_provider, dict(sites), root
        self.graph_sha256 = hashlib.sha256((leg_provider.source_sha256["nodes"] +
            leg_provider.source_sha256["edges"]).encode()).hexdigest()
        distances, certificate = certify_integer_landmark(leg_provider.graph,
            leg_provider.anchor_nodes, landmark_anchor, router_factory,
            graph_nodes_sha256=leg_provider.source_sha256["nodes"],
            graph_edges_sha256=leg_provider.source_sha256["edges"])
        self.landmark_certificate = certificate
        self.landmark_sha256 = hashlib.sha256(certificate).hexdigest()
        self.landmarks = (distances,)
        self._summary = {}
        self._regions = {}
        self._member_hash = {}
        def visit(region):
            if region.identifier in self._regions or len(set(region.members)) != len(region.members):
                raise ValueError("Duplicate Region identity or Site")
            self._regions[region.identifier] = region
            if region.children:
                covered = [site for child in region.children for site in child.members]
                if len(covered) != len(set(covered)) or set(covered) != set(region.members):
                    raise ValueError("Region children do not partition their parent")
            for child in region.children:
                visit(child)
            if region.members:
                member_hash = member_set_digest(region.members)
                summary = RegionLandmarkSummary(member_hash,
                    self.graph_sha256, self.landmark_sha256,
                    (min(distances.from_landmark[self.sites[s].anchor_id]
                         for s in region.members),),
                    (max(distances.to_landmark[self.sites[s].anchor_id]
                         for s in region.members),))
                self._summary[region.identifier] = summary
                self._member_hash[region.identifier] = member_hash
        visit(root)
        self._action_bits = {action: 1 << index for index, action in enumerate(
            (site, effect) for site in sorted(sites)
            for effect in sorted(sites[site].effects)
            if sites[site].anchor_id != destination_anchor)}
        self._actions, self._action_masks = {}, {}
        for region_id, region in self._regions.items():
            for remaining in (0, 1):
                for effect in ("C", "S", "CS"):
                    selected = (() if effect in ("S", "CS") and not remaining else
                        tuple((site, effect) for site in region.members
                              if (site, effect) in self._action_bits))
                    self._actions[region_id, effect, remaining] = selected
                    self._action_masks[region_id, effect, remaining] = sum(
                        self._action_bits[action] for action in selected)
        self.online_queries = self.online_internal_member_accesses = 0
        self.online_leaf_action_reads = self.online_mask_word_work = 0

    def _incoming(self, source, region):
        from math import floor
        from .deployable import directed_alt_region_bound
        self._check_region(region)
        value = directed_alt_region_bound(source, self.landmarks,
            self._summary[region.identifier], graph_sha256=self.graph_sha256,
            landmark_sha256=self.landmark_sha256,
            member_set_sha256=self._member_hash[region.identifier])
        return Fraction(floor(value))

    def _check_region(self, region):
        if self._regions.get(region.identifier) is not region:
            raise ValueError("Region identity differs from bound candidate universe")

    @progress.operation('road_bound')
    def bound(self, problem, pieces, region, effect):
        self.online_queries += 1
        if not pieces or not self.action_mask(region, effect, pieces[0].state.remaining_schedule):
            return None, 0
        state = pieces[0].state
        lower_time = min(p.slope * p.domain.affine_infimum(p.slope)[0] + p.intercept
                         for p in pieces)
        time = lower_time + self._incoming(state.anchor, region) + problem.overhead
        if effect in ("S", "CS"):
            a, _, duration = problem.schedule
            time = max(a, time) + duration
        return time - problem.start + problem.penalty * (state.stop_count + 1), 0

    @progress.operation('road_singleton_bound')
    def singleton_bound(self, problem, pieces, site, effect):
        if not pieces:
            return None
        if (site, effect) not in self._action_bits:
            raise ValueError("Unknown table-free Site action")
        self.online_queries += 1
        state = pieces[0].state
        if effect in ("S", "CS") and not state.remaining_schedule:
            return None
        source = state.anchor
        distance = self.landmarks[0]
        terms = [0]
        anchor = problem.site_anchor(site)
        for left, right in ((distance.from_landmark[anchor],
                            distance.from_landmark[source]),
                            (distance.to_landmark[source],
                             distance.to_landmark[anchor])):
            if math.isfinite(left) and math.isfinite(right):
                terms.append(left - right)
        lower_time = min(p.slope * p.domain.affine_infimum(p.slope)[0] + p.intercept
                         for p in pieces)
        time = lower_time + Fraction(max(terms)) + problem.overhead
        if effect in ("S", "CS"):
            a, _, duration = problem.schedule
            time = max(a, time) + duration
        return time - problem.start + problem.penalty * (state.stop_count + 1)

    def action_mask(self, region, effect, remaining):
        self._check_region(region)
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
        self._check_region(region)
        if region.children:
            self.online_internal_member_accesses += 1
            raise ValueError("Internal Region member expansion is forbidden")
        self.online_leaf_action_reads += 1
        return self._actions[region.identifier, effect, remaining]

    def action_bit(self, action):
        return self._action_bits[action]


class RoadSelectedLegProvider:
    def __init__(self, graph, router, table: ImmutableLegTable,
                 anchor_nodes: Mapping[str, int], *, nodes_sha256: str,
                 edges_sha256: str):
        if not isinstance(table, ImmutableLegTable) or table.direction_policy != "forward_per_source_v1":
            raise ValueError("Frozen forward selected-leg table required")
        sources = dict(table.source_sha256)
        if (sources.get("data/processed/graphs/slovenia_extended/nodes.parquet") != nodes_sha256 or
                sources.get("data/processed/graphs/slovenia_extended/edges.parquet") != edges_sha256 or
                set(anchor_nodes) != set(table.anchors) or
                any(type(node) is not int or not 0 <= node < graph.node_count
                    for node in anchor_nodes.values()) or
                len(set(anchor_nodes.values())) != len(anchor_nodes)):
            raise ValueError("Road graph, source hash or anchor binding differs from table")
        self.graph, self.router, self.table = graph, router, table
        self.anchor_nodes = dict(anchor_nodes)
        self.legs: dict[tuple[str, str], SelectedLeg] = {}
        self.edge_witnesses: dict[tuple[str, str], tuple[int, ...] | None] = {}
        self.source_run_count = 0
        self.route_wall_ns = 0
        self.route_process_cpu_ns = 0
        self.policy_sha256 = hashlib.sha256(TIE_POLICY.encode()).hexdigest()

    @progress.operation('road_path')
    def _path(self, source_node, target_node, parent, parent_edge):
        if source_node == target_node:
            return ()
        backward = []
        node = target_node
        while node != source_node:
            prior, edge = int(parent[node]), int(parent_edge[node])
            if (prior < 0 or not 0 <= edge < self.graph.edge_count or
                    int(self.graph.source[edge]) != prior or
                    int(self.graph.target[edge]) != node or
                    len(backward) >= self.graph.node_count):
                raise ValueError("Native selected predecessor edge is invalid")
            backward.append(edge)
            node = prior
        return tuple(reversed(backward))

    def _fill_source(self, source: str):
        started_wall, started_cpu = time.monotonic_ns(), time.process_time_ns()
        source_node = self.anchor_nodes[source]
        costs, lengths, parents, edges = self.router.full_edges(source_node)
        produced = {}
        witnesses = {}
        for target in self.table.anchors:
            target_node = self.anchor_nodes[target]
            cost, length = float(costs[target_node]), float(lengths[target_node])
            if math.isinf(cost) and math.isinf(length):
                if int(parents[target_node]) != -1 or int(edges[target_node]) != -1:
                    raise ValueError("Unreachable target has a predecessor")
                leg = SelectedLeg(source, target, False, None, None,
                                  "forward_from_source", None, None)
                path = None
            elif math.isfinite(cost) and math.isfinite(length) and cost >= 0 and length >= 0:
                path = self._path(source_node, target_node, parents, edges)
                replay_time = replay_length = 0.0
                for edge in path:
                    replay_time += float(self.graph.weights["travel_time"][edge])
                    replay_length += float(self.graph.weights["distance"][edge])
                if (replay_time, replay_length) != (cost, length):
                    raise ValueError("Selected edge witness does not replay native labels")
                leg = SelectedLeg(source, target, True,
                    Fraction(*cost.as_integer_ratio()), Fraction(*length.as_integer_ratio()),
                    "identity" if source == target else "forward_from_source",
                    cost.hex(), length.hex())
            else:
                raise ValueError("Native selected labels have invalid reachability")
            frozen = self.table.leg(source, target)
            if leg != frozen:
                raise ValueError("Native selected route differs from the frozen exact leg")
            produced[source, target], witnesses[source, target] = leg, path
        self.legs.update(produced)
        self.edge_witnesses.update(witnesses)
        self.source_run_count += 1
        self.route_wall_ns += time.monotonic_ns() - started_wall
        self.route_process_cpu_ns += time.process_time_ns() - started_cpu

    @progress.operation('road_leg')
    def leg(self, source: str, target: str) -> SelectedLeg:
        if source not in self.anchor_nodes or target not in self.anchor_nodes:
            raise ValueError("Unknown road anchor")
        if (source, target) not in self.legs:
            self._fill_source(source)
        return self.legs[source, target]
