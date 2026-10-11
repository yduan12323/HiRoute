"""Bounded read-only distance-cost screen using the existing native router.

This is a physical input screen, not the selected-fastest-leg export or a
formal exact shortest-distance certificate. It loads edge arrays without an
igraph object and substitutes distance weights for both native cost arrays.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np
import pandas as pd

from microplan.routing import ExactRouter


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
    parser.add_argument("--native-cache", type=Path, required=True)
    parser.add_argument("--all-fixed-extrema", action="store_true")
    parser.add_argument("--micrometer-lower-bound", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.native_cache.exists():
        parser.error("output and native cache must be new")
    start = time.monotonic()
    if sha(args.geographic_screen) != args.geographic_screen_sha256:
        raise ValueError("Geographic pair preselection hash mismatch")
    chosen = json.loads(args.geographic_screen.read_text())
    if chosen.get("schema") != "hiroute.m5d.geographic_screen.v1":
        raise ValueError("Unsupported preselection schema")
    node_sha = sha(args.graph_dir / "nodes.parquet")
    edge_sha = sha(args.graph_dir / "edges.parquet")
    if node_sha != chosen["nodes_sha256"]:
        raise ValueError("Graph nodes differ from preselection")
    metadata = json.loads((args.graph_dir / "metadata.json").read_text())
    edges = pd.read_parquet(args.graph_dir / "edges.parquet",
                            columns=["source", "target", "length_m", "travel_time_s"])
    source = np.ascontiguousarray(edges.source.to_numpy(dtype=np.int64))
    target = np.ascontiguousarray(edges.target.to_numpy(dtype=np.int64))
    length = np.ascontiguousarray(edges.length_m.to_numpy(dtype=np.float64))
    travel_time = np.ascontiguousarray(edges.travel_time_s.to_numpy(dtype=np.float64))
    if (len(source) != int(metadata["edge_count"]) or not np.isfinite(length).all()
            or (length < 0).any() or not np.isfinite(travel_time).all()
            or (travel_time <= 0).any()):
        raise ValueError("Invalid graph edge length arrays")
    if args.micrometer_lower_bound:
        # For each nonnegative binary64 edge length x, the predecessor of
        # round(x*1e6) is no greater than exact(x*1e6). Integer path sums
        # below the 1e13 cutoff are exact in binary64 (< 2**53).
        length = np.ascontiguousarray(np.maximum(0, np.floor(
            np.nextafter(length * 1000000, -np.inf))))
        if (length > 10000000000000).any():
            raise ValueError("An edge exceeds the exact-integer distance cutoff")
    graph = SimpleNamespace(node_count=int(metadata["node_count"]), edge_count=len(source),
                            source=source, target=target,
                            weights={"travel_time": length, "distance": length})
    router = ExactRouter(graph, {"compiler": "g++", "compiler_flags": ["-O3", "-std=c++17"]},
                         args.native_cache)
    try:
        if args.all_fixed_extrema:
            candidates = chosen["fixed_small_extrema_candidates"]
            pairs = [(a, b) for a in candidates for b in candidates if a["site_id"] != b["site_id"]]
        else:
            first, second = chosen["farthest_extrema_pair_sites"]
            pairs = [(first, second), (second, first)]
        cutoff = 10000000000000 if args.micrometer_lower_bound else np.finfo(np.float64).max
        costs, _ = router.pairs([int(a["access_node"]) for a, _ in pairs],
                                [int(b["access_node"]) for _, b in pairs],
                                cutoff)
    finally:
        router.close()
    if args.micrometer_lower_bound and any(float(x) != math.floor(float(x)) for x in costs if math.isfinite(float(x))):
        raise ValueError("Integer micrometer route cost lost exact representability")
    result = {"schema": "hiroute.m5d.extrema_native_distance_screen.v1",
              "tool_sha256": sha(Path(__file__)),
              "geographic_screen_sha256": args.geographic_screen_sha256,
              "graph_nodes_sha256": node_sha, "graph_edges_sha256": edge_sha,
              "native_router_sha256": router.provenance["source_sha256"],
              "compiler_command": router.provenance["compiler_command"],
              "candidate_mode": "all_fixed_extrema" if args.all_fixed_extrema else "farthest_pair",
              "distance_mode": "integer_micrometer_lower_bound" if args.micrometer_lower_bound else "float_distance_cost",
              "candidate_count": len(candidates) if args.all_fixed_extrema else 2,
              "pair_count": len(pairs),
              "finite_pair_count": int(np.isfinite(costs).sum()),
              "pairs_over_450km": int(sum(math.isfinite(float(cost)) and bool(cost >
                            (450001000000 if args.micrometer_lower_bound else 450000)) for cost in costs)),
              "pairs": [{"origin_site": a["site_id"], "destination_site": b["site_id"],
                         "origin_anchor": int(a["access_node"]),
                         "destination_anchor": int(b["access_node"]),
                         "distance_cost_m": float(cost) / 1000000 if args.micrometer_lower_bound and math.isfinite(float(cost))
                         else (float(cost) if math.isfinite(float(cost)) else None),
                         "integer_micrometers": int(cost) if args.micrometer_lower_bound and math.isfinite(float(cost)) else None}
                        for (a, b), cost in zip(pairs, costs)],
              "elapsed_seconds": time.monotonic() - start,
              "distance_cost_weight_substitution": True,
              "integer_cutoff_micrometers": 10000000000000 if args.micrometer_lower_bound else None,
              "one_metre_selected_route_rounding_margin": args.micrometer_lower_bound,
              "floating_distance_not_independent_exact_certificate": True,
              "no_optimizer_or_performance_comparison_calls": True}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
