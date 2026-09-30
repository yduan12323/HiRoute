"""Rebuild the static driving graph from the checksum-verified frozen PBF."""
from __future__ import annotations

import argparse
import json
import resource
import time

from pyrosm import OSM

from _common import ROOT, configs, record_run, sha256, verified_dataset
from graph.preprocessing import ATTRIBUTES, normalize_network
from graph.road_graph import IgraphRoadGraph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-config", default="configs/data.yaml")
    parser.add_argument("--routing-config", default="configs/routing.yaml")
    parser.add_argument("--output-dir", help="Override processed output directory, e.g. for rebuild validation")
    args = parser.parse_args()
    data, routing = configs(args.data_config, args.routing_config)
    dataset = verified_dataset(data)
    run = record_run("build_graph", data, routing, data["seed"])
    directory = ROOT / (args.output_dir or data["graph_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    osm = OSM(str(ROOT / data["dataset"]["raw_path"]), workers=1)
    nodes, edges = osm.get_network(network_type="driving", nodes=True, extra_attributes=ATTRIBUTES)
    parse_seconds = time.perf_counter() - start
    print(f"Parsed {len(nodes):,} nodes / {len(edges):,} segments in {parse_seconds:.2f}s", flush=True)
    print("Parsed road classes: " + json.dumps(edges.highway.value_counts().to_dict()), flush=True)
    nodes, edges, audit = normalize_network(nodes, edges, routing)
    graph = IgraphRoadGraph(nodes, edges)
    nodes.to_parquet(directory / "nodes.parquet", index=False, compression="zstd")
    edges.to_parquet(directory / "edges.parquet", index=False, compression="zstd")
    metadata = {
        "schema_version": 1, "crs": "EPSG:4326", "units": {"length": "metres", "travel_time": "seconds", "speed": "km/h"},
        "backend": "igraph", "directed": True, "parallel_edges": True,
        "all_components_retained": True, "simplified": False,
        "dataset": dataset, "run": run, "audit": audit,
        "node_count": graph.node_count, "edge_count": graph.edge_count,
        "largest_strong_component_nodes": len(graph.largest_strong_component_nodes()),
        "parse_seconds": parse_seconds, "preprocessing_seconds": time.perf_counter() - start,
        "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "files": {name: {"sha256": sha256(directory / name), "size_bytes": (directory / name).stat().st_size}
                  for name in ["nodes.parquet", "edges.parquet"]},
        "limitations": ["Static passenger-car public-road approximation; no traffic or intersection-delay model.",
                        "Turn-restriction relations, node barriers and vehicle-specific dimensions are not enforced.",
                        "Conditional access/oneway ways excluded; conditional maxspeed retained only in raw PBF.",
                        "Extract boundaries truncate cross-border routes; no completeness claim outside extract."]}
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({key: metadata[key] for key in ["node_count", "edge_count", "preprocessing_seconds", "process_peak_rss_mib"]}, indent=2))


if __name__ == "__main__":
    main()
