"""Directed node/edge envelopes without copying the underlying road graph.

Containment is with respect to the supplied static graph, not road legality.
An envelope is a necessary condition for bounded-cost paths; combinations of
retained edges can still form over-budget walks. No stopping policy is defined.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterable, Iterator, Protocol

import numpy as np

from graph.road_graph import Cost, NoPathError, RoadGraph


class EnvelopeGraph(RoadGraph, Protocol):
    """RoadGraph plus ordered endpoint/cost arrays aligned with exact edge IDs."""
    source: np.ndarray
    target: np.ndarray
    weights: dict[Cost, np.ndarray]

    @property
    def node_count(self) -> int: ...
    @property
    def edge_count(self) -> int: ...


@dataclass(frozen=True)
class NumericalTolerance:
    absolute: float = 1e-8
    relative: float = 1e-10

    def __post_init__(self):
        if not np.isfinite([self.absolute, self.relative]).all() or self.absolute < 0 or self.relative < 0:
            raise ValueError("Tolerance must be finite and nonnegative")

    def allowance(self, budget: float) -> float:
        return self.absolute + self.relative * budget


@dataclass(frozen=True)
class DetourDistances:
    origin: int
    destination: int
    cost: Cost
    unit: str
    baseline_cost: float
    forward_distances: np.ndarray
    reverse_distances: np.ndarray
    node_lower_bounds: np.ndarray
    edge_lower_bounds: np.ndarray
    forward_seconds: float
    reverse_seconds: float
    lower_bound_seconds: float

    @property
    def storage_bytes(self) -> int:
        return sum(array.nbytes for array in [self.forward_distances, self.reverse_distances,
                                             self.node_lower_bounds, self.edge_lower_bounds])


@dataclass(frozen=True)
class SafeDetourEnvelope:
    distances: DetourDistances
    budget: float
    tolerance: NumericalTolerance
    node_mask: np.ndarray
    edge_mask: np.ndarray

    @property
    def origin(self) -> int:
        return self.distances.origin

    @property
    def destination(self) -> int:
        return self.distances.destination

    @property
    def baseline_cost(self) -> float:
        return self.distances.baseline_cost

    @property
    def cost(self) -> Cost:
        return self.distances.cost

    @property
    def unit(self) -> str:
        return self.distances.unit

    @property
    def forward_distances(self) -> np.ndarray:
        return self.distances.forward_distances

    @property
    def reverse_distances(self) -> np.ndarray:
        return self.distances.reverse_distances

    @property
    def mask_bytes(self) -> int:
        return self.node_mask.nbytes + self.edge_mask.nbytes


def _readonly(array: np.ndarray) -> np.ndarray:
    array.setflags(write=False)
    return array


def precompute_detour_distances(graph: EnvelopeGraph, origin: int, destination: int,
                                cost: Cost = "travel_time") -> DetourDistances:
    if cost not in ("travel_time", "distance"):
        raise ValueError(f"Unsupported mobility cost: {cost}")
    for node in [origin, destination]:
        if not isinstance(node, (int, np.integer)) or not 0 <= node < graph.node_count:
            raise ValueError(f"Invalid graph node: {node}")
    costs = graph.weights[cost]
    if costs.shape != (graph.edge_count,) or not np.isfinite(costs).all() or (costs < 0).any():
        raise ValueError("Base edge costs must be finite and nonnegative")
    if graph.source.shape != costs.shape or graph.target.shape != costs.shape:
        raise ValueError("Edge endpoint and cost arrays must align")
    start = time.perf_counter()
    forward = graph.single_source_distances(origin, cost, direction="out")
    forward_seconds = time.perf_counter() - start
    start = time.perf_counter()
    # Traversing incoming edges from d is traversal in G^R, hence d_G(v,d).
    reverse = graph.single_source_distances(destination, cost, direction="in")
    reverse_seconds = time.perf_counter() - start
    for array in [forward, reverse]:
        if array.shape != (graph.node_count,) or np.isnan(array).any() or (array < 0).any():
            raise ValueError("Distance arrays must align with nodes and be nonnegative or +inf")
    baseline = float(forward[destination])
    if not np.isfinite(baseline):
        raise NoPathError(f"No directed path {origin} -> {destination}")
    start = time.perf_counter()
    node_bounds = forward + reverse
    edge_bounds = forward[graph.source] + costs + reverse[graph.target]
    bound_seconds = time.perf_counter() - start
    return DetourDistances(int(origin), int(destination), cost,
                           "seconds" if cost == "travel_time" else "metres", baseline,
                           *map(_readonly, [forward, reverse, node_bounds, edge_bounds]),
                           forward_seconds, reverse_seconds, bound_seconds)


def build_envelope_from_precomputed(distances: DetourDistances, budget: float,
                                   tolerance: NumericalTolerance = NumericalTolerance()) -> SafeDetourEnvelope:
    if not np.isfinite(budget) or budget < distances.baseline_cost:
        raise ValueError("Budget must be finite and at least the baseline cost")
    threshold = budget + tolerance.allowance(budget)
    if not np.isfinite(threshold):
        raise ValueError("Budget plus tolerance must be finite")
    nodes = np.isfinite(distances.node_lower_bounds) & (distances.node_lower_bounds <= threshold)
    edges = np.isfinite(distances.edge_lower_bounds) & (distances.edge_lower_bounds <= threshold)
    return SafeDetourEnvelope(distances, float(budget), tolerance, _readonly(nodes), _readonly(edges))


def compute_safe_detour_envelope(graph: EnvelopeGraph, origin: int, destination: int,
                                budget: float, cost: Cost = "travel_time",
                                tolerance: NumericalTolerance = NumericalTolerance()) -> SafeDetourEnvelope:
    return build_envelope_from_precomputed(precompute_detour_distances(graph, origin, destination, cost), budget, tolerance)


def iter_progressive_envelopes(distances: DetourDistances, budgets: Iterable[float],
                              tolerance: NumericalTolerance = NumericalTolerance()) -> Iterator[SafeDetourEnvelope]:
    """Yield budget views; the caller may inspect each view and explicitly stop.

    This iterator neither estimates utility nor selects a stopping budget.
    Consumers retaining all yielded views retain their masks, not graph copies.
    """
    previous = distances.baseline_cost
    for budget in budgets:
        if budget < previous:
            raise ValueError("Progressive budgets must be nondecreasing")
        envelope = build_envelope_from_precomputed(distances, budget, tolerance)
        yield envelope
        previous = budget
