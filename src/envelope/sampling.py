"""Seeded waypoint-induced directed walks for structural containment audits.

This optional sampling adapter uses igraph batched path extraction. The core
envelope implementation depends only on EnvelopeGraph. Walks may contain cycles;
the containment theorem applies to walks as well as simple paths.
"""
from dataclasses import dataclass
import hashlib
import math

import numpy as np

from graph.road_graph import Cost, IgraphRoadGraph
from .safe_detour import DetourDistances


@dataclass(frozen=True)
class SampledPath:
    sample_id: int
    method: str
    waypoint: int | None
    nodes: np.ndarray
    edges: np.ndarray
    base_cost: float
    fingerprint: str


def sample_waypoint_paths(graph: IgraphRoadGraph, distances: DetourDistances,
                          seed: int, waypoint_count: int, waypoint_ratios: list[float]) -> list[SampledPath]:
    if waypoint_count < 1:
        raise ValueError("At least one waypoint is required")
    if not waypoint_ratios or not np.isfinite(waypoint_ratios).all() or min(waypoint_ratios) < 1 or (np.diff(waypoint_ratios) <= 0).any():
        raise ValueError("Waypoint sampling ratios must be finite and strictly increasing")
    rng = np.random.default_rng(seed)
    baseline = distances.baseline_cost
    waypoints = []
    minimum = baseline
    for ratio in waypoint_ratios:
        maximum = baseline * ratio
        candidates = np.flatnonzero(np.isfinite(distances.node_lower_bounds) &
                                   (distances.node_lower_bounds >= minimum) & (distances.node_lower_bounds <= maximum))
        candidates = candidates[(candidates != distances.origin) & (candidates != distances.destination)]
        if len(candidates):
            waypoints.append(int(rng.choice(candidates)))
        minimum = maximum
    eligible = np.flatnonzero(np.isfinite(distances.node_lower_bounds))
    eligible = eligible[(eligible != distances.origin) & (eligible != distances.destination)]
    if len(eligible):
        # Guarantee an over-cap witness when one exists, not over-budget rejection
        # for every sampled walk. Bounds on concatenated shortest walks are exact.
        far = eligible[distances.node_lower_bounds[eligible] > baseline * waypoint_ratios[-1]]
        if len(far):
            waypoints.append(int(rng.choice(far)))
        while len(set(waypoints)) < min(waypoint_count, len(eligible)):
            waypoints.append(int(rng.choice(eligible)))
    waypoints = list(dict.fromkeys(waypoints))[:waypoint_count]
    origin, destination, cost = distances.origin, distances.destination, distances.cost
    weights = graph._weights(cost)
    outgoing = graph._graph.get_shortest_paths(origin, to=[destination, *waypoints], weights=weights, mode="out", output="epath")
    incoming = graph._graph.get_shortest_paths(destination, to=waypoints, weights=weights, mode="in", output="epath") if waypoints else []
    sequences = [outgoing[0], *(first + list(reversed(second)) for first, second in zip(outgoing[1:], incoming))]
    result = []
    for index, sequence in enumerate(sequences):
        edges = np.asarray(sequence, dtype=np.int64)
        nodes = np.concatenate(([origin], graph.target[edges]))
        if nodes[-1] != destination or not np.array_equal(graph.source[edges], nodes[:-1]):
            raise RuntimeError("Invalid sampled directed walk; check incoming path reversal")
        base_cost = math.fsum(graph.weights[cost][edges])
        fingerprint = hashlib.sha256(edges.astype("<i8", copy=False).tobytes()).hexdigest()
        result.append(SampledPath(index, "baseline" if index == 0 else "waypoint_shortest_walk",
                                  None if index == 0 else waypoints[index - 1], nodes, edges, base_cost, fingerprint))
    return result
