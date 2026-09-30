"""Validate every OD and record Milestone 1 performance and technical report."""
from __future__ import annotations

import json
import resource
import time
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from _common import ROOT, configs, load_graph, record_run, sha256
from graph.validation import validate_geometry


def main():
    data, routing = configs()
    run = record_run("benchmark", data, routing, routing["benchmark"]["seed"])
    start = time.perf_counter()
    graph = load_graph(data, routing)
    loading_seconds = time.perf_counter() - start
    directory = ROOT / data["graph_dir"]
    graph_metadata = json.loads((directory / "metadata.json").read_text())
    path = ROOT / data["instances_path"]
    instances = pd.read_parquet(path)
    instance_metadata = json.loads(path.with_suffix(".metadata.json").read_text())
    if sha256(path) != instance_metadata["sha256"]:
        raise ValueError("OD file checksum mismatch")
    if not instances.dataset_sha256.eq(data["dataset"]["sha256"]).all() or not instances.graph_edges_sha256.eq(graph_metadata["files"]["edges.parquet"]["sha256"]).all():
        raise ValueError("OD instances refer to different dataset/graph")
    geometry = pd.read_parquet(directory / "edges.parquet", columns=["geometry_wkb"]).geometry_wkb.to_numpy()
    validation_rows = []
    for row in instances.itertuples():
        start = time.perf_counter()
        route = graph.shortest_path(int(row.origin_node), int(row.destination_node))
        runtime = time.perf_counter() - start
        validate_geometry(graph, route, geometry)
        if not np.isclose(route.travel_time_s, row.shortest_path_travel_time_s) or not np.isclose(route.distance_m, row.fastest_path_distance_m):
            raise ValueError("OD route costs disagree with graph")
        if not np.isclose(graph.shortest_path_cost(int(row.origin_node), int(row.destination_node)), route.travel_time_s):
            raise ValueError("Route is not time optimal")
        if not np.isclose(graph.shortest_path_cost(int(row.origin_node), int(row.destination_node), "distance"), row.shortest_path_distance_m):
            raise ValueError("Recorded minimum distance is incorrect")
        validation_rows.append({"instance_id": row.instance_id, "connected": True, "nonnegative_costs": True,
                                "directed_sequence_valid": True, "geometry_valid": True, "query_runtime_s": runtime,
                                "path_edge_count": len(route.edge_ids)})
    result_dir = ROOT / data["results_dir"]
    pd.DataFrame(validation_rows).to_parquet(result_dir / "route_validation.parquet", index=False)
    warmup = routing["benchmark"]["warmup_queries"]
    for row in instances.head(warmup).itertuples():
        graph.shortest_path(int(row.origin_node), int(row.destination_node))
    rng = np.random.default_rng(routing["benchmark"]["seed"])
    measurements = []
    for repeat in range(routing["benchmark"]["repeats"]):
        for index in rng.permutation(len(instances)):
            row = instances.iloc[index]
            start = time.perf_counter()
            route = graph.shortest_path(int(row.origin_node), int(row.destination_node))
            duration = time.perf_counter() - start
            graph.validate_route(route)
            measurements.append({"repeat": repeat, "instance_id": int(row.instance_id), "query_seconds": duration})
    durations = np.asarray([row["query_seconds"] for row in measurements])
    pd.DataFrame(measurements).to_parquet(result_dir / "query_timings.parquet", index=False)
    dataset = graph_metadata["dataset"]
    stats = {
        "run": run, "node_count": graph.node_count, "edge_count": graph.edge_count,
        "largest_strong_component_nodes": graph_metadata["largest_strong_component_nodes"],
        "raw_pbf_bytes": dataset["size_bytes"],
        "processed_graph_bytes": sum(p.stat().st_size for p in directory.iterdir() if p.is_file()),
        "preprocessing_seconds": graph_metadata["preprocessing_seconds"],
        "verified_graph_loading_seconds": loading_seconds,
        "shortest_path_query_median_ms": float(np.median(durations) * 1000),
        "shortest_path_query_p95_ms": float(np.quantile(durations, .95) * 1000),
        "query_count": len(durations), "od_count": len(instances), "validated_od_count": len(validation_rows),
        "preprocessing_peak_rss_mib": graph_metadata["process_peak_rss_mib"],
        "benchmark_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "distance_bands": instances.groupby("distance_band_km").size().to_dict(),
        "minimum_shortest_distance_km": float(instances.shortest_path_distance_m.min() / 1000),
        "maximum_shortest_distance_km": float(instances.shortest_path_distance_m.max() / 1000),
    }
    tests_path = result_dir / "tests.xml"
    if tests_path.exists():
        suites = ET.parse(tests_path).getroot().findall("testsuite")
        stats["tests"] = {key: sum(int(suite.get(key, "0")) for suite in suites) for key in ["tests", "failures", "errors", "skipped"]}
    rebuild_path = result_dir / "deterministic_rebuild.json"
    stats["deterministic_rebuild_passed"] = json.loads(rebuild_path.read_text())["passed"] if rebuild_path.exists() else False
    (result_dir / "benchmark.json").write_text(json.dumps(stats, indent=2) + "\n")
    audit = graph_metadata["audit"]
    report = f'''# Milestone 1 technical report

Executed at {run['timestamp_utc']}. Only initial infrastructure and the road-graph milestone are implemented. `RESEARCH_SPEC.md` is unchanged (SHA256 `{run['research_spec_sha256']}`). All later research directories remain placeholders.

## Environment and data

Python {run['python'].split()[0]}, Pyrosm {run['packages'].get('pyrosm')}, igraph {run['packages'].get('igraph')}; isolated Mamba environment `hiroute`. `environment-linux-64.lock` pins exact Conda package URLs and SHA256 hashes; `environment.yml` records the portable package intent. Hardware details are in [SERVER_ENVIRONMENT.md](SERVER_ENVIRONMENT.md).

Dataset: **{dataset['region']}**, [{dataset['file_name']}]({dataset['source_url']}). OSM header snapshot: **{dataset['osm_snapshot_timestamp']}**. Downloaded: {dataset['downloaded_at_utc']}. Size: {dataset['size_bytes']:,} bytes. SHA256: `{dataset['sha256']}`. Publisher MD5 also verified. Raw PBF is read-only and downloader refuses replacements. Attribution: OpenStreetMap contributors / Geofabrik; ODbL 1.0. Full metadata is in `data/raw/DATA_MANIFEST.yaml`.

## Graph and cost model

Directed igraph multigraph with **{graph.node_count:,} nodes** and **{graph.edge_count:,} edges**. Largest strongly connected component has {stats['largest_strong_component_nodes']:,} nodes; all components are retained in the graph. No graph simplification, corridor selection or geographical buffering occurs. Stable sorted OSM IDs map to contiguous node/edge indices. Parquet stores WGS84 nodes, directed edge geometry as WKB, source tags, metres and seconds.

Free-flow speed is the configured road-class estimate capped by parsed numeric/directional/symbolic posted maxspeed. Numeric mph is converted to km/h; semicolon values use the minimum. Missing or unsupported tags explicitly fall back to class speed and remain identifiable. Time is `length_m * 3.6 / speed_kph`. Posted-cap edges: {audit.get('speed_posted_cap', 0):,}; class-fallback edges: {audit.get('speed_class_fallback', 0):,}. Full defaults are in `configs/routing.yaml`.

Pyrosm applies its driving filter. Additional static access policy uses motorcar → motor_vehicle → vehicle → access. Restricted, destination-only and unknown tagged access are excluded; conditional access and conditional one-way ways are excluded. One-way direction, reverse one-way, and implicit motorway/roundabout one-way are handled. Toll and dimension tags remain nullable; absence is not interpreted as a known negative. Filter counts are in graph metadata.

## Instances and validation

{len(instances)} ODs: {routing['instances']['per_band']} each in 50–100, 100–200 and 200–400 km bands. Seed: {routing['instances']['seed']}. Fixed city anchors receive uniform-area jitter and nearest-node snapping; unsuitable snaps, duplicate pairs and nodes outside the largest SCC are rejected. This biases the smoke benchmark toward connected city travel, rather than claiming population-representative sampling.

Bands use distance-optimal paths ({stats['minimum_shortest_distance_km']:.1f}–{stats['maximum_shortest_distance_km']:.1f} km); distance of the travel-time-optimal path is separately recorded. Every OD passes finite/nonnegative edge checks, directed sequence and exact parallel-edge validation, geometry endpoint checks (0.5 m tolerance), cost-sum checks and shortest-cost agreement. `route_validation.parquet` records per-OD validation and runtime. Test results: {stats.get('tests', 'not recorded')}. Separate full-PBF rebuild byte-identical: **{stats['deterministic_rebuild_passed']}**.

## Measured performance

| Measure | Result |
| --- | ---: |
| Raw PBF | {stats['raw_pbf_bytes'] / 2**20:.2f} MiB |
| Processed graph (tables + metadata) | {stats['processed_graph_bytes'] / 2**20:.2f} MiB |
| Preprocessing including parsing, conversion, writes and SCC computation | {stats['preprocessing_seconds']:.2f} s |
| Verified graph loading including table checksums and spatial index | {loading_seconds:.2f} s |
| Median fastest-path query | {stats['shortest_path_query_median_ms']:.2f} ms |
| p95 fastest-path query | {stats['shortest_path_query_p95_ms']:.2f} ms |
| Preprocessing peak process RSS | {stats['preprocessing_peak_rss_mib']:.1f} MiB |
| Benchmark peak process RSS | {stats['benchmark_peak_rss_mib']:.1f} MiB |

Query timings cover {stats['query_count']} calls after {warmup} warmup calls, with seeded shuffled OD order over {routing['benchmark']['repeats']} repeats. They include Dijkstra, path extraction and cost sums, and exclude geometry validation. OS page cache is not cleared; loading is a warm-cache measurement. RSS is Linux process high-water memory, not whole-server usage. Raw timings and full software/configuration/source fingerprints are saved under `results/milestone_1/`.

## Limits and later envelope concerns

This is a static passenger-car graph for infrastructure tests. Turn-restriction relations, node barriers, conditional speed rules, vehicle height/weight restrictions, traffic, intersection delays and ferry scheduling are not modeled. Thus structural shortest-path validity is verified, but real-world legal feasibility is not certified. These constraints must be represented before later hard-feasibility claims; a turn-aware state graph may alter the vertex definition for later envelope work.

Regional boundaries can remove cross-border alternatives, particularly in Slovenia. Future geographically complete envelopes need larger extracts or explicit boundary diagnostics. Class-speed assumptions affect mobility budgets and need sensitivity analysis. Disconnected vertices remain available and have infinite directed costs. `single_source_distances(..., direction="in")` supports destination-side reverse distances. Multi-source distances use O(V) output memory but run one Dijkstra per source; batch scaling needs measurement. Full graph retention and explicit nonnegative static costs provide the base for later envelope work; no envelope is implemented here.

## Reproduction

See [README.md](../README.md) for exact environment, download, graph, OD, test, rebuild and benchmark commands. Commands record Git commit and dirty state, source hashes, timestamp, configuration, seed, dataset metadata and package versions. Raw PBF is never edited in place; processed data can be regenerated. No live routing APIs, semantic modules, charging optimization, user models or dashboards were added.
'''
    (ROOT / "docs/MILESTONE_1_REPORT.md").write_text(report)
    print(json.dumps({key: value for key, value in stats.items() if key != "run"}, indent=2))


if __name__ == "__main__":
    main()
