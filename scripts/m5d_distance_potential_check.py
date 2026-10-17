"""Independently check native integer-distance labels by edge inequalities.

For every reached edge u->v, p[v] <= p[u]+w and p[source]=0 imply
p[target] is a lower bound on every directed source-target path. Weights are
nonnegative integer micrometers below 2**53. This checks the native output;
it does not call a time-cut/LP optimizer or assume shortest-path correctness.
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
    parser.add_argument("--pair-screen", type=Path, required=True)
    parser.add_argument("--pair-screen-sha256", required=True)
    parser.add_argument("--native-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.native_cache.exists():
        parser.error("output and native cache must be new")
    start = time.monotonic()
    if sha(args.pair_screen) != args.pair_screen_sha256:
        raise ValueError("Pair-screen hash mismatch")
    screen = json.loads(args.pair_screen.read_text())
    if screen.get("distance_mode") != "integer_micrometer_lower_bound":
        raise ValueError("Require integer-micrometer pair screen")
    nodes_path = args.graph_dir / "nodes.parquet"
    edges_path = args.graph_dir / "edges.parquet"
    if sha(nodes_path) != screen["graph_nodes_sha256"] or sha(edges_path) != screen["graph_edges_sha256"]:
        raise ValueError("Road graph differs from screened graph")
    metadata = json.loads((args.graph_dir / "metadata.json").read_text())
    edges = pd.read_parquet(edges_path, columns=["source", "target", "length_m", "travel_time_s"])
    source = np.ascontiguousarray(edges.source.to_numpy(dtype=np.int64))
    target = np.ascontiguousarray(edges.target.to_numpy(dtype=np.int64))
    lengths = np.ascontiguousarray(edges.length_m.to_numpy(dtype=np.float64))
    times = np.ascontiguousarray(edges.travel_time_s.to_numpy(dtype=np.float64))
    if (len(source) != int(metadata["edge_count"]) or not np.isfinite(lengths).all()
            or (lengths < 0).any() or not np.isfinite(times).all() or (times <= 0).any()):
        raise ValueError("Invalid graph edge arrays")
    weight = np.ascontiguousarray(np.maximum(0, np.floor(np.nextafter(lengths * 1000000, -np.inf))))
    if (weight >= 10000000000000).any() or (weight != np.floor(weight)).any():
        raise ValueError("Integer edge weight exceeds exact summation domain")
    graph = SimpleNamespace(node_count=int(metadata["node_count"]), edge_count=len(source),
                            source=source, target=target,
                            weights={"travel_time": weight, "distance": weight})
    long_rows = [row for row in screen["pairs"] if row["integer_micrometers"] is not None
                 and row["integer_micrometers"] > 450001000000]
    roots = sorted({row["origin_anchor"] for row in long_rows})
    if not roots:
        raise ValueError("No geographically prespecified long candidates")
    router = ExactRouter(graph, {"compiler": "g++", "compiler_flags": ["-O3", "-std=c++17"]},
                         args.native_cache)
    audits = []
    try:
        for root in roots:
            labels, _, _ = router.full(root)
            finite = np.isfinite(labels)
            if (labels[root] != 0 or (labels[finite] < 0).any() or
                    (labels[finite] != np.floor(labels[finite])).any() or
                    (labels[finite].max() + weight.max() >= 2**53)):
                raise ValueError(f"Root {root} has non-exact or invalid distance labels")
            checked = 0
            for begin in range(0, len(source), 1000000):
                sl = slice(begin, min(begin + 1000000, len(source)))
                u = source[sl]
                v = target[sl]
                reached = finite[u]
                if not np.isfinite(labels[v[reached]]).all():
                    raise ValueError(f"Root {root} has a reached-to-unreached edge")
                if (labels[v[reached]] > labels[u[reached]] + weight[sl][reached]).any():
                    raise ValueError(f"Root {root} violates an edge potential inequality")
                checked += int(reached.sum())
            rows = [row for row in screen["pairs"] if row["origin_anchor"] == root]
            for row in rows:
                value = labels[row["destination_anchor"]]
                expected = row["integer_micrometers"]
                if (expected is None) != (not math.isfinite(float(value))) or (
                        expected is not None and int(value) != expected):
                    raise ValueError(f"Root {root} label differs from earlier pair screen")
            audits.append({"root": root, "reached_node_count": int(finite.sum()),
                           "checked_reached_edges": checked,
                           "label_sha256": hashlib.sha256(labels.tobytes()).hexdigest(),
                           "matched_screened_targets": len(rows)})
    finally:
        router.close()
    gamma = ((graph.node_count - 1) * (2**-53)) / (1 - (graph.node_count - 1) * (2**-53))
    # A one-charge route has at most two simple selected fastest legs. Their
    # combined rounded length is at most 450 km under the frozen energy
    # parameters. The standard positive-sum error bound is far below 1 m.
    rounding_error_upper_m = 450000 * gamma / (1 - gamma)
    if rounding_error_upper_m >= 1:
        raise ValueError("One-metre selected-leg rounding margin is not proved")
    result = {"schema": "hiroute.m5d.distance_potential_check.v1",
              "tool_sha256": sha(Path(__file__)), "pair_screen_sha256": args.pair_screen_sha256,
              "graph_nodes_sha256": screen["graph_nodes_sha256"],
              "graph_edges_sha256": screen["graph_edges_sha256"],
              "native_router_sha256": router.provenance["source_sha256"],
              "verified_root_count": len(audits), "verified_long_pair_count": len(long_rows),
              "selected_leg_rounding_error_upper_m": rounding_error_upper_m,
              "one_metre_margin_passed": True, "audits": audits,
              "elapsed_seconds": time.monotonic() - start,
              "no_time_cut_or_lp_optimizer_calls": True}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
