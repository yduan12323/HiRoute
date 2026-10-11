"""Source-bound selected-road-leg provider with native edge witnesses.

The graph-file hashes must be verified by the caller before arrays are loaded.
Each new source runs the accepted forward native policy once, reconstructs all
declared target paths by edge identity, and compares exact binary64 totals with
the frozen table. It caches only selected target legs and witnesses.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import math
import time
from typing import Mapping

from .real_legs import ImmutableLegTable, SelectedLeg, TIE_POLICY


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

    def leg(self, source: str, target: str) -> SelectedLeg:
        if source not in self.anchor_nodes or target not in self.anchor_nodes:
            raise ValueError("Unknown road anchor")
        if (source, target) not in self.legs:
            self._fill_source(source)
        return self.legs[source, target]
