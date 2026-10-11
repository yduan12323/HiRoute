"""Fixed OD02 N8 sparse seed admission; no all-pairs table construction."""
from __future__ import annotations

from fractions import Fraction as R
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from microplan.routing import ExactRouter
from scripts.m5d_one_query_runner import load_graph, sha
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite
from timecut5.road_provider import TableFreeRoadSelectedLegProvider
from timecut5.sparse_seed import SparseSeedCatalog, admit_sparse_seed


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def array_hash(graph):
    digest = hashlib.sha256()
    for name, array in (("source", graph.source), ("target", graph.target),
                        ("travel_time", graph.weights["travel_time"]),
                        ("distance", graph.weights["distance"])):
        digest.update(canon([name, str(array.dtype), list(array.shape)]))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def run(inputs: Path, graph_dir: Path, cert_path: Path, out: Path):
    started = time.monotonic_ns()
    pools_path = inputs / "formal_pools_20261011_v2/pools.json"
    slate_path = inputs / "results/milestone_5d/continuation_20261011/fixed_12od_candidate_slate.json"
    pools = json.loads(pools_path.read_bytes())
    if pools["slate_sha256"] != sha(slate_path):
        raise ValueError("Frozen population/slate binding differs")
    pool = next(row for row in pools["pools"] if row["od_id"] == "OD02")
    site_rows = pool["sites"][:8]
    if len(site_rows) != 8 or len({row["site_id"] for row in site_rows}) != 8:
        raise ValueError("Fixed OD02 N8 Site universe differs")
    sites = {row["site_id"]: RealSite(row["site_id"], row["anchor_id"],
                                      tuple(row["effects"])) for row in site_rows}
    origin = f"road:{pool['origin_anchor']}"
    destination = f"road:{pool['destination_anchor']}"
    anchors = list(dict.fromkeys([origin] + [row["anchor_id"] for row in site_rows] + [destination]))
    if len(anchors) != 10 or anchors[0] != origin or anchors[-1] != destination:
        raise ValueError("Fixed Site/endpoint physical anchors collide")
    anchor_nodes = {anchor: int(anchor.removeprefix("road:")) for anchor in anchors}
    if any(f"road:{node}" != anchor for anchor, node in anchor_nodes.items()):
        raise ValueError("Noncanonical dense road anchor")
    cert = json.loads(cert_path.read_bytes())
    nodes_sha, edges_sha = cert["graph_nodes_sha256"], cert["graph_edges_sha256"]
    graph, metadata_sha = load_graph(graph_dir, nodes_sha, edges_sha)
    loaded_arrays_sha = array_hash(graph)
    anchor_sha = hashlib.sha256(canon(anchor_nodes)).hexdigest()
    candidate_sha = hashlib.sha256(canon(sorted(sites))).hexdigest()
    hierarchy_sha = sha(inputs / "results/milestone_4r_b1/hierarchy.json")
    router = ExactRouter(graph, {"compiler": "g++", "compiler_flags": ["-O3", "-std=c++17"]},
                         out / "native")
    try:
        provider = TableFreeRoadSelectedLegProvider(graph, router, anchor_nodes,
            nodes_sha256=nodes_sha, edges_sha256=edges_sha,
            router_sha256=router.provenance["source_sha256"],
            anchor_catalog_sha256=anchor_sha)
        if provider.graph is not graph:
            raise ValueError("Native provider lost verified loader graph object")
        catalog = SparseSeedCatalog(provider, sites, origin_anchor=origin,
            destination_anchor=destination, nodes_path=graph_dir / "nodes.parquet",
            edges_path=graph_dir / "edges.parquet",
            site_catalog_sha256=site_catalog_digest(sites),
            hierarchy_sha256=hierarchy_sha, candidate_sha256=candidate_sha)
        states = json.loads((inputs / "results/milestone_5_real_export/query_states_resolved.json").read_bytes())
        state = next(row for row in states if row.get("state_id") == "C01")
        if (state["mode"] != "energy_only" or state["initial_soc"] != "3/10" or
                state["H_ref"] != 4 or state["schedule"] is not None):
            raise ValueError("Frozen query template differs")
        primitive = state["charging_primitive"]
        breaks, slopes, intercepts = (primitive[name] for name in
            ("energy_breakpoints_kwh", "slopes_s_per_kwh", "intercepts_s"))
        if len(breaks) != len(slopes) + 1 or len(slopes) != len(intercepts):
            raise ValueError("Frozen charging primitive differs")
        query = dict(case_id="OD02_energy_only_soc3_10_n8", origin=origin,
            destination=destination, H_ref=4, start_time_s=state["start_time_s"],
            initial_energy_kwh=state["initial_energy_kwh"],
            capacity_kwh=state["capacity_kwh"],
            minimum_energy_kwh=state["energy_floor_kwh"],
            reserve_kwh=state["terminal_reserve_kwh"],
            consumption_kwh_per_m=state["consumption_kwh_per_m"],
            overhead_s=state["overhead_s"], lambda_stop_s=state["stop_penalty_s"],
            schedule=None, charging_segments=[[breaks[i], breaks[i+1], slopes[i],
                intercepts[i]] for i in range(len(slopes))],
            sparse_domain_sha256=catalog.domain_sha256,
            hierarchy_sha256=hierarchy_sha)
        admission = admit_sparse_seed(query, catalog)
        report = {"schema": "hiroute.m5d.od02_n8_sparse_seed_probe.v1",
            "status": admission["status"], "row_id": query["case_id"],
            "source_commit": __import__("subprocess").check_output(
                ["git", "rev-parse", "HEAD"], text=True).strip(),
            "graph_nodes_sha256": nodes_sha, "graph_edges_sha256": edges_sha,
            "graph_metadata_sha256": metadata_sha,
            "loaded_graph_arrays_sha256": loaded_arrays_sha,
            "loader_source_sha256": sha(Path(__import__("scripts.m5d_one_query_runner",
                fromlist=["load_graph"]).__file__)),
            "router_source_sha256": router.provenance["source_sha256"],
            "router_binary_sha256": sha(out / "native/routing.so"),
            "anchor_catalog_sha256": anchor_sha,
            "site_catalog_sha256": catalog.site_catalog_sha256,
            "candidate_sha256": candidate_sha,
            "population_sha256": sha(pools_path), "slate_sha256": sha(slate_path),
            "hierarchy_sha256": hierarchy_sha,
            "query_sha256": hashlib.sha256(canon(query)).hexdigest(),
            "sparse_domain_sha256": catalog.domain_sha256,
            "candidate_count": len(sites), "requested_pair_count": len(provider.legs),
            "source_run_count": provider.source_run_count,
            "route_process_cpu_ns": provider.route_process_cpu_ns,
            "elapsed_ns": time.monotonic_ns() - started,
            "seed": {k: str(v) if isinstance(v, R) else v
                     for k, v in admission.items() if k in ("status", "max_depth",
                        "proposal_count", "accepted_count", "lex_key", "sequence", "charges")}}
        with (out / "presearch_receipt.json").open("x") as stream:
            json.dump(report, stream, sort_keys=True, default=str)
            stream.write("\n")
        print(json.dumps(report, sort_keys=True, default=str), flush=True)
    finally:
        router.close()


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:5]))
