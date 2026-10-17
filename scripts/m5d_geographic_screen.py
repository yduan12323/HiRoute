"""Read-only attached-Site extent screen on the retained regional map."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import numpy as np


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument("--grid-size", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if args.grid_size < 2 or args.grid_size > 20:
        parser.error("grid-size must be between 2 and 20")
    nodes = pd.read_parquet(args.nodes, columns=["node_id", "lat", "lon"])
    sites = pd.read_parquet(args.sites, columns=["site_id", "access_node", "transport_capabilities"])
    sites = sites[sites.access_node.notna()].copy()
    sites["access_node"] = sites.access_node.astype("int64")
    attached = sites.merge(nodes, left_on="access_node", right_on="node_id", how="inner")
    regions = {"northwest": (attached.lat > 47.1) & (attached.lon < 13.1),
               "southeast": (attached.lat < 45.15) & (attached.lon > 16.9),
               "west": attached.lon < 12.8, "east": attached.lon > 17.1}
    rows = {}
    for name, mask in regions.items():
        subset = attached[mask].sort_values("site_id")
        rows[name] = {"count": len(subset), "first_five": subset[["site_id", "access_node", "lat", "lon"]]
                      .head(5).to_dict(orient="records")}
    # Geographic extrema are an input-coverage screen, never a route or
    # performance-based query selection. Keep a fixed 20 per compass axis.
    candidates = []
    small_candidates = []
    for lat_weight, lon_weight in ((1, 0), (-1, 0), (0, 1), (0, -1),
                                   (1, 1), (1, -1), (-1, 1), (-1, -1)):
        score = lat_weight * attached.lat + lon_weight * attached.lon
        candidates.extend(attached.loc[score.nlargest(20).index,
                                        ["site_id", "access_node", "lat", "lon"]].to_dict("records"))
        small_candidates.extend(attached.loc[score.nlargest(4).index,
                                              ["site_id", "access_node", "lat", "lon"]].to_dict("records"))
    candidates = {row["site_id"]: row for row in candidates}
    small_candidates = {row["site_id"]: row for row in small_candidates}
    def haversine(a, b):
        lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
        delta_lat = lat2 - lat1
        delta_lon = math.radians(b["lon"] - a["lon"])
        x = math.sin(delta_lat / 2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(delta_lon / 2)**2
        return 6371000 * 2 * math.asin(min(1, math.sqrt(x)))
    values = list(candidates.values())
    farthest = max(((haversine(a, b), a, b) for i, a in enumerate(values) for b in values[i+1:]),
                   key=lambda row: row[0])
    # Independent grid rule, fixed before any new route query: one attached
    # Site nearest the centre of each populated bounding-grid cell.
    lat_min, lat_max = attached.lat.min(), attached.lat.max()
    lon_min, lon_max = attached.lon.min(), attached.lon.max()
    size = args.grid_size
    lat_step, lon_step = (lat_max - lat_min) / size, (lon_max - lon_min) / size
    attached["lat_cell"] = np.minimum(size - 1, np.floor((attached.lat - lat_min) / lat_step)).astype(int)
    attached["lon_cell"] = np.minimum(size - 1, np.floor((attached.lon - lon_min) / lon_step)).astype(int)
    attached["cell_offset"] = (((attached.lat - (lat_min + (attached.lat_cell + .5) * lat_step)) / lat_step)**2
                               + ((attached.lon - (lon_min + (attached.lon_cell + .5) * lon_step)) / lon_step)**2)
    grid = (attached.sort_values(["cell_offset", "site_id"])
            .drop_duplicates(["lat_cell", "lon_cell"])
            .sort_values(["lat_cell", "lon_cell"]))
    grid_rows = grid[["site_id", "access_node", "lat", "lon", "lat_cell", "lon_cell"]].to_dict("records")
    result = {"schema": "hiroute.m5d.geographic_screen.v1", "tool_sha256": sha(Path(__file__)),
              "nodes_sha256": sha(args.nodes), "sites_sha256": sha(args.sites),
              "attached_site_count": len(attached),
              "bounds": {k: {"min": float(attached[k].min()), "max": float(attached[k].max())}
                         for k in ("lat", "lon")}, "regions": rows,
              "extrema_candidate_count": len(values),
              "fixed_small_extrema_candidates": [small_candidates[key] for key in sorted(small_candidates)],
              "fixed_grid_rule": f"one_nearest_attached_site_per_populated_cell_in_{size}x{size}_lat_lon_bounds",
              "fixed_grid_candidates": grid_rows,
              "fixed_grid_candidate_count": len(grid_rows),
              "farthest_extrema_pair_geodesic_m": farthest[0],
              "farthest_extrema_pair_sites": [farthest[1], farthest[2]],
              "geodesic_is_not_certified_road_distance": True,
              "no_route_or_optimizer_calls": True}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
