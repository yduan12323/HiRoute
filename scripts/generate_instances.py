"""Generate seeded, city-anchored driving ODs in three distance bands."""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from _common import ROOT, configs, load_graph, record_run, sha256
from graph.road_graph import NoPathError
from graph.validation import GEOD, validate_geometry


def generate(graph, geometry, configuration: dict) -> pd.DataFrame:
    rng = np.random.default_rng(configuration["seed"])
    cities = list(configuration["cities"].items())
    bands = configuration["bands_km"]
    counts = [0] * len(bands)
    per_band = configuration["per_band"]
    allowed_nodes = np.zeros(graph.node_count, dtype=bool)
    allowed_nodes[graph.largest_strong_component_nodes()] = True
    seen, records = set(), []
    for attempt in range(configuration["max_attempts"]):
        if all(count == per_band for count in counts):
            break
        selected = rng.choice(len(cities), size=2, replace=False)
        points, mapped, names = [], [], []
        for index in selected:
            name, (lat, lon) = cities[index]
            radius_m = configuration["jitter_km"] * 1000 * np.sqrt(rng.random())
            lon, lat, _ = GEOD.fwd(lon, lat, rng.uniform(0, 360), radius_m)
            node = graph.nearest_graph_node(lat, lon)
            snapped = graph.nodes.iloc[node]
            _, _, snap_m = GEOD.inv(lon, lat, snapped.lon, snapped.lat)
            points.append((lat, lon, snap_m))
            mapped.append(node)
            names.append(name)
        origin, destination = mapped
        if origin == destination or (origin, destination) in seen or not all(allowed_nodes[mapped]):
            continue
        if any(point[2] > configuration["max_snap_m"] for point in points):
            continue
        try:
            shortest_distance = graph.shortest_path_cost(origin, destination, cost="distance")
            band = next((i for i, (lo, hi) in enumerate(bands) if lo * 1000 <= shortest_distance < hi * 1000), None)
            if band is None or counts[band] >= per_band:
                continue
            start = time.perf_counter()
            route = graph.shortest_path(origin, destination, cost="travel_time")
            runtime = time.perf_counter() - start
        except NoPathError:
            continue
        validate_geometry(graph, route, geometry)
        optimum = graph.shortest_path_cost(origin, destination, cost="travel_time")
        if not np.isclose(optimum, route.travel_time_s):
            raise ValueError("Travel-time path disagrees with shortest-path cost")
        seen.add((origin, destination))
        counts[band] += 1
        records.append({"instance_id": len(records), "seed": configuration["seed"],
                        "distance_band_km": f"{bands[band][0]}-{bands[band][1]}",
                        "origin_city": names[0], "destination_city": names[1],
                        "origin_lat": points[0][0], "origin_lon": points[0][1],
                        "destination_lat": points[1][0], "destination_lon": points[1][1],
                        "origin_snap_m": points[0][2], "destination_snap_m": points[1][2],
                        "origin_node": origin, "destination_node": destination,
                        "shortest_path_distance_m": shortest_distance,
                        "shortest_path_travel_time_s": route.travel_time_s,
                        "fastest_path_distance_m": route.distance_m,
                        "path_nodes": list(route.nodes), "path_edges": list(route.edge_ids),
                        "query_runtime_s": runtime, "validated": True})
        print(f"Accepted {len(records)} / {per_band * len(bands)}: {names[0]} -> {names[1]}, {shortest_distance / 1000:.1f} km", flush=True)
    if any(count != per_band for count in counts):
        raise RuntimeError(f"Could not fill distance bands: {counts}; do not silently reduce benchmark")
    return pd.DataFrame.from_records(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-config", default="configs/data.yaml")
    parser.add_argument("--routing-config", default="configs/routing.yaml")
    args = parser.parse_args()
    data, routing = configs(args.data_config, args.routing_config)
    run = record_run("generate_instances", data, routing, routing["instances"]["seed"])
    graph = load_graph(data, routing)
    geometry = pd.read_parquet(ROOT / data["graph_dir"] / "edges.parquet", columns=["geometry_wkb"]).geometry_wkb.to_numpy()
    instances = generate(graph, geometry, routing["instances"])
    instances["dataset_sha256"] = data["dataset"]["sha256"]
    graph_metadata = json.loads((ROOT / data["graph_dir"] / "metadata.json").read_text())
    instances["graph_edges_sha256"] = graph_metadata["files"]["edges.parquet"]["sha256"]
    path = ROOT / data["instances_path"]
    instances.to_parquet(path, index=False, compression="zstd")
    path.with_suffix(".metadata.json").write_text(json.dumps({"run": run, "count": len(instances), "sha256": sha256(path),
        "distance_definition": "Bands use distance-optimal driving cost; fastest-path distance recorded separately.",
        "sampling": "Distinct city anchors with seeded uniform-area jitter, snap to nearest node, reject outside largest SCC; graph retains all components."}, indent=2) + "\n")


if __name__ == "__main__":
    main()
