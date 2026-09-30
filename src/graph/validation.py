"""Check exact edge IDs, coordinates and cost sums without visual inspection."""
from __future__ import annotations

import numpy as np
from pyproj import Geod
import shapely

from .road_graph import IgraphRoadGraph, Route

GEOD = Geod(ellps="WGS84")


def validate_geometry(graph: IgraphRoadGraph, route: Route, geometry_wkb) -> None:
    graph.validate_route(route)
    for index, edge in enumerate(route.edge_ids):
        geometry = shapely.from_wkb(geometry_wkb[edge])
        if geometry.geom_type != "LineString" or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Invalid geometry for edge {edge}")
        coordinates = np.asarray(geometry.coords)
        if not np.isfinite(coordinates).all():
            raise ValueError("Nonfinite path geometry")
        for coordinate, node in [(coordinates[0], route.nodes[index]), (coordinates[-1], route.nodes[index + 1])]:
            row = graph.nodes.iloc[node]
            _, _, error_m = GEOD.inv(coordinate[0], coordinate[1], row.lon, row.lat)
            if error_m > 0.5:
                raise ValueError(f"Edge {edge} geometry misses node {node} by {error_m} metres")
