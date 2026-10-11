"""Directed road-distance screen for a geographically frozen extreme pair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from graph.road_graph import IgraphRoadGraph


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", type=Path, required=True)
    parser.add_argument("--geographic-screen", type=Path, required=True)
    parser.add_argument("--geographic-screen-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    started = time.monotonic()
    if sha(args.geographic_screen) != args.geographic_screen_sha256:
        raise ValueError("Geographic pair preselection hash mismatch")
    chosen = json.loads(args.geographic_screen.read_text())
    if chosen.get("schema") != "hiroute.m5d.geographic_screen.v1":
        raise ValueError("Unexpected preselection schema")
    node_sha = sha(args.graph_dir / "nodes.parquet")
    edge_sha = sha(args.graph_dir / "edges.parquet")
    if node_sha != chosen["nodes_sha256"]:
        raise ValueError("Graph nodes differ from geographic preselection")
    graph = IgraphRoadGraph.load(args.graph_dir)
    first, second = chosen["farthest_extrema_pair_sites"]
    a, b = int(first["access_node"]), int(second["access_node"])
    out = graph.shortest_path_cost(a, b, "distance")
    back = graph.shortest_path_cost(b, a, "distance")
    result = {"schema": "hiroute.m5d.extrema_distance_screen.v1",
              "tool_sha256": sha(Path(__file__)),
              "geographic_screen_sha256": args.geographic_screen_sha256,
              "graph_nodes_sha256": node_sha, "graph_edges_sha256": edge_sha,
              "selected_pair": [first, second],
              "directed_road_shortest_distance_m": {"first_to_second": out,
                                                     "second_to_first": back},
              "elapsed_seconds": time.monotonic() - started,
              "floating_distance_not_independent_exact_certificate": True,
              "no_route_performance_comparison_or_optimizer_calls": True}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
