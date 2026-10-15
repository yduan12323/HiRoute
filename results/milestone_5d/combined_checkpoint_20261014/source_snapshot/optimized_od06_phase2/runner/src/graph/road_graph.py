"""Typed routing contract; public node IDs are stable contiguous table indices."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, Sequence
import warnings

import igraph as ig
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

Cost = Literal["travel_time", "distance"]
Direction = Literal["out", "in"]


class NoPathError(ValueError):
    """The destination is unreachable in the directed graph."""


@dataclass(frozen=True)
class Route:
    nodes: tuple[int, ...]
    edge_ids: tuple[int, ...]
    distance_m: float
    travel_time_s: float
    optimized_cost: Cost


class RoadGraph(Protocol):
    def shortest_path(self, origin: int, destination: int, cost: Cost = "travel_time") -> Route: ...
    def shortest_path_cost(self, origin: int, destination: int, cost: Cost = "travel_time") -> float: ...
    def nearest_graph_node(self, lat: float, lon: float) -> int: ...
    def single_source_distances(self, origin: int, cost: Cost = "travel_time", direction: Direction = "out") -> np.ndarray: ...
    def multi_source_distances(self, origins: Sequence[int], cost: Cost = "travel_time", direction: Direction = "out") -> np.ndarray: ...


def unit_sphere(lat, lon) -> np.ndarray:
    lat, lon = np.deg2rad(lat), np.deg2rad(lon)
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


class IgraphRoadGraph:
    """Directed multigraph with C-backed Dijkstra and a spherical nearest-node index.

    Distances use metres, travel times seconds. ``in`` computes d(v, origin)
    on directed edges. All components are retained; unreachable costs are inf.
    """

    def __init__(self, nodes: pd.DataFrame, edges: pd.DataFrame):
        if not np.array_equal(nodes.node_id.to_numpy(), np.arange(len(nodes))):
            raise ValueError("Node IDs must be contiguous and table ordered")
        if not np.array_equal(edges.edge_id.to_numpy(), np.arange(len(edges))):
            raise ValueError("Edge IDs must be contiguous and table ordered")
        self.nodes = nodes[["node_id", "osm_node_id", "lat", "lon"]].copy()
        coords = self.nodes[["lat", "lon"]].to_numpy()
        if not np.isfinite(coords).all() or (np.abs(coords[:, 0]) > 90).any() or (np.abs(coords[:, 1]) > 180).any():
            raise ValueError("Invalid WGS84 graph coordinates")
        self.source = edges.source.to_numpy(dtype=np.int64)
        self.target = edges.target.to_numpy(dtype=np.int64)
        self.weights = {"distance": edges.length_m.to_numpy(dtype=float),
                        "travel_time": edges.travel_time_s.to_numpy(dtype=float)}
        for costs in self.weights.values():
            if not np.isfinite(costs).all() or (costs < 0).any():
                raise ValueError("Edge costs must be finite and nonnegative")
        ends = np.column_stack((self.source, self.target))
        if ends.size and ((ends < 0).any() or (ends >= len(nodes)).any()):
            raise ValueError("Invalid edge endpoint")
        self._graph = ig.Graph(n=len(nodes), edges=ends, directed=True)
        self._weight_lists = {key: values.tolist() for key, values in self.weights.items()}
        self._tree = cKDTree(unit_sphere(self.nodes.lat, self.nodes.lon))

    @classmethod
    def load(cls, directory: str | Path) -> IgraphRoadGraph:
        directory = Path(directory)
        nodes = pd.read_parquet(directory / "nodes.parquet")
        edges = pd.read_parquet(directory / "edges.parquet", columns=["edge_id", "source", "target", "length_m", "travel_time_s"])
        return cls(nodes, edges)

    @property
    def node_count(self) -> int:
        return self._graph.vcount()

    @property
    def edge_count(self) -> int:
        return self._graph.ecount()

    def largest_strong_component_nodes(self) -> np.ndarray:
        components = self._graph.connected_components(mode="strong")
        largest = int(np.argmax(components.sizes()))
        return np.flatnonzero(np.asarray(components.membership) == largest)

    def _node(self, node: int) -> int:
        if not isinstance(node, (int, np.integer)) or not 0 <= node < self.node_count:
            raise ValueError(f"Invalid graph node: {node}")
        return int(node)

    def _weights(self, cost: Cost) -> list[float]:
        if cost not in self._weight_lists:
            raise ValueError(f"Unknown cost: {cost}")
        return self._weight_lists[cost]

    def nearest_graph_node(self, lat: float, lon: float) -> int:
        if not np.isfinite([lat, lon]).all() or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Coordinates must be finite WGS84 latitude/longitude")
        if self.node_count == 0:
            raise ValueError("Cannot snap to an empty graph")
        _, node = self._tree.query(unit_sphere([lat], [lon])[0])
        return int(node)

    def shortest_path(self, origin: int, destination: int, cost: Cost = "travel_time") -> Route:
        origin, destination = self._node(origin), self._node(destination)
        weights = self._weights(cost)
        if origin == destination:
            return Route((origin,), (), 0.0, 0.0, cost)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Couldn't reach some vertices.*", category=RuntimeWarning)
            edges = self._graph.get_shortest_paths(origin, to=destination, weights=weights, mode="out", output="epath")[0]
        if not edges:
            raise NoPathError(f"No directed path {origin} -> {destination}")
        node_sequence = (origin, *(int(self.target[e]) for e in edges))
        return Route(node_sequence, tuple(edges), float(self.weights["distance"][edges].sum()),
                     float(self.weights["travel_time"][edges].sum()), cost)

    def shortest_path_cost(self, origin: int, destination: int, cost: Cost = "travel_time") -> float:
        return float(self._graph.distances(source=[self._node(origin)], target=[self._node(destination)],
                                           weights=self._weights(cost), mode="out")[0][0])

    def single_source_distances(self, origin: int, cost: Cost = "travel_time", direction: Direction = "out") -> np.ndarray:
        if direction not in ("out", "in"):
            raise ValueError("Direction must be out or in")
        return np.asarray(self._graph.distances(source=[self._node(origin)], weights=self._weights(cost), mode=direction)[0])

    def multi_source_distances(self, origins: Sequence[int], cost: Cost = "travel_time", direction: Direction = "out") -> np.ndarray:
        self._weights(cost)
        if direction not in ("out", "in"):
            raise ValueError("Direction must be out or in")
        # O(V) result memory, not a dense |origins| x |V| matrix.
        result = np.full(self.node_count, np.inf)
        for origin in origins:
            np.minimum(result, self.single_source_distances(origin, cost, direction), out=result)
        return result

    def validate_route(self, route: Route) -> None:
        if len(route.nodes) != len(route.edge_ids) + 1:
            raise ValueError("Invalid route sequence length")
        for node in route.nodes:
            self._node(node)
        for i, edge in enumerate(route.edge_ids):
            if not 0 <= edge < self.edge_count or self.source[edge] != route.nodes[i] or self.target[edge] != route.nodes[i + 1]:
                raise ValueError("Route edge does not match directed node sequence")
        edges = list(route.edge_ids)
        if not np.isclose(route.distance_m, self.weights["distance"][edges].sum()) or not np.isclose(route.travel_time_s, self.weights["travel_time"][edges].sum()):
            raise ValueError("Route totals differ from edge sums")
