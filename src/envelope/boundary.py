"""Approximate extract-edge diagnostics using a separately frozen polygon.

The polygon acquisition date need not equal the PBF date. It is a diagnostic
proxy, never a certificate of global geographic or legal completeness.
"""
from pathlib import Path

import numpy as np
from pyproj import Transformer
import shapely
from shapely.geometry import Polygon


def read_poly(path: str | Path):
    lines = Path(path).read_text().splitlines()
    sections, index = [], 1
    while index < len(lines):
        label = lines[index].strip()
        index += 1
        if label == "END":
            break
        if not label:
            continue
        coordinates = []
        while index < len(lines) and lines[index].strip() != "END":
            coordinates.append(tuple(map(float, lines[index].split())))
            index += 1
        if index == len(lines) or len(coordinates) < 3:
            raise ValueError("Malformed extract polygon section")
        sections.append((label.startswith("!"), Polygon(coordinates)))
        index += 1
    shells = [polygon for hole, polygon in sections if not hole]
    holes = [polygon for hole, polygon in sections if hole]
    if not shells:
        raise ValueError("Extract polygon has no outer rings")
    polygon = shapely.union_all(shells)
    if holes:
        polygon = polygon.difference(shapely.union_all(holes))
    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("Extract polygon is empty or invalid")
    return polygon


def boundary_node_risk(lat: np.ndarray, lon: np.ndarray, polygon,
                       projection: str, margin_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not np.isfinite(margin_m) or margin_m < 0:
        raise ValueError("Boundary margin must be finite and nonnegative")
    transform = Transformer.from_crs("EPSG:4326", projection, always_xy=True)
    x, y = transform.transform(lon, lat)
    projected = shapely.transform(polygon, transform.transform, interleaved=False)
    interior = projected.buffer(-margin_m)
    # GEOS prepared XY containment avoids millions of Python Point objects.
    shapely.prepare(interior)
    risk = ~shapely.contains_xy(interior, x, y)
    return risk, np.asarray(x), np.asarray(y)
