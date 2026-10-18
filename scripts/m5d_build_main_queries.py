"""Freeze 48 physical queries and 96 nested candidate bindings, no solver calls."""
from __future__ import annotations

from fractions import Fraction as R
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite, TIE_POLICY, encode_binary64
from timecut5.road_provider import TableFreeRoadSelectedLegProvider
from timecut5.sparse_seed import sparse_domain_digest
from validation.reference5.model import normalize_case


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compile_queries(slate, pools, states, baselines, source_hashes, hierarchy_sha):
    if (len(slate["queries"]) != 48 or len(slate["od"]) != 12 or
            pools["slate_sha256"] != source_hashes["slate"]):
        raise ValueError("Frozen 48-query slate or pool source mismatch")
    pool_by_id = {row["od_id"]: row for row in pools["pools"]}
    if set(pool_by_id) != {row["od_id"] for row in slate["od"]}:
        raise ValueError("Frozen 12-OD candidate pools differ")
    template = {row["mode"]: row for row in states if row.get("state_id") in ("C01", "C02")}
    if set(template) != {"energy_only", "energy_and_scheduled"}:
        raise ValueError("Frozen physical templates missing")
    queries = []
    for ordinal, row in enumerate(slate["queries"]):
        od, activity, soc = row["od_id"], row["activity"], row["soc"]
        pool = pool_by_id[od]
        if len(pool["sites"]) != 128 or pool["prefix_sizes"] != [8, 16, 32, 128]:
            raise ValueError("Nested candidate pool differs")
        t = template[activity]
        origin = f"road:{pool['origin_anchor']}"
        destination = f"road:{pool['destination_anchor']}"
        direct = baselines[od]
        baseline_time = R(*(int(value) for value in direct["time_s"]["ratio"]))
        if R(row["initial_energy_kwh"]) != R(soc) * R(row["capacity_kwh"]):
            raise ValueError("Frozen SOC and battery energy disagree")
        primitive = t["charging_primitive"]
        breaks, slopes, intercepts = (primitive[name] for name in
            ("energy_breakpoints_kwh", "slopes_s_per_kwh", "intercepts_s"))
        if len(breaks) != len(slopes) + 1 or len(slopes) != len(intercepts):
            raise ValueError("Frozen charging primitive differs")
        schedule = (None if activity == "energy_only" else {
            "a": str(R(2, 5) * baseline_time),
            "b": str(R(7, 10) * baseline_time),
            "D": t["schedule"]["duration_s"]})
        query_id = f"{od}_{activity}_soc{soc.replace('/', '_')}"
        base = {"case_id": query_id, "origin": origin,
            "destination": destination, "H_ref": 4,
            "start_time_s": t["start_time_s"],
            "initial_energy_kwh": row["initial_energy_kwh"],
            "capacity_kwh": row["capacity_kwh"],
            "minimum_energy_kwh": t["energy_floor_kwh"],
            "reserve_kwh": row["terminal_reserve_kwh"],
            "consumption_kwh_per_m": row["consumption_kwh_per_m"],
            "overhead_s": t["overhead_s"],
            "lambda_stop_s": t["stop_penalty_s"],
            "charging_segments": [[breaks[i], breaks[i+1], slopes[i], intercepts[i]]
                                  for i in range(len(slopes))],
            "schedule": schedule, "hierarchy_sha256": hierarchy_sha}
        bindings = {}
        for size in (32, 128):
            sites = {s["site_id"]: RealSite(s["site_id"], s["anchor_id"],
                      tuple(s["effects"])) for s in pool["sites"][:size]}
            if len(sites) != size:
                raise ValueError("Duplicate Site ID in fixed candidate prefix")
            anchors = list(dict.fromkeys([origin] + [s.anchor_id for s in sites.values()] + [destination]))
            if anchors[0] != origin or anchors[-1] != destination:
                raise ValueError("Terminal road anchor collides with candidate prefix")
            anchor_nodes = {anchor: int(anchor.removeprefix("road:")) for anchor in anchors}
            anchor_sha = hashlib.sha256(canon(anchor_nodes)).hexdigest()
            site_sha = site_catalog_digest(sites)
            candidate_sha = hashlib.sha256(canon(sorted(sites))).hexdigest()
            graph_sources = {"nodes": source_hashes["graph_nodes"],
                "edges": source_hashes["graph_edges"],
                "router": source_hashes["router_cpp"], "anchors": anchor_sha,
                "tie_policy": hashlib.sha256(TIE_POLICY.encode()).hexdigest()}
            domain_sha = sparse_domain_digest(graph_sources, site_sha, candidate_sha,
                hierarchy_sha, origin, destination)
            bound = dict(base, sparse_domain_sha256=domain_sha)
            normalized = normalize_case(dict(bound,
                sites={sid: list(site.effects) for sid, site in sites.items()}, edges=[]))
            if normalized["H_ref"] != 4 or normalized["initial_remaining_schedule"] != int(schedule is not None):
                raise ValueError("Independent physical input validation differs")
            bindings[str(size)] = {"query": bound,
                "query_sha256": hashlib.sha256(canon(bound)).hexdigest(),
                "candidate_site_ids": [s["site_id"] for s in pool["sites"][:size]],
                "candidate_sha256": candidate_sha,
                "site_catalog_sha256": site_sha,
                "anchor_catalog_sha256": anchor_sha,
                "sparse_domain_sha256": domain_sha}
        queries.append({"query_id": query_id, "slate_index": ordinal,
            "od_id": od, "activity": activity, "soc": soc,
            "baseline_direct_binary64": direct,
            "base_query": base, "base_query_sha256": hashlib.sha256(canon(base)).hexdigest(),
            "bindings": bindings})
    if len(queries) != 48 or len({q["query_id"] for q in queries}) != 48:
        raise ValueError("Frozen query denominator differs")
    return queries


def run(inputs: Path, graph_dir: Path, cert_path: Path, output: Path):
    from microplan.routing import ExactRouter
    from scripts.m5d_one_query_runner import load_graph
    slate_path = inputs / "results/milestone_5d/continuation_20261011/fixed_12od_candidate_slate.json"
    pool_path = inputs / "formal_pools_20261011_v2/pools.json"
    state_path = inputs / "results/milestone_5_real_export/query_states_resolved.json"
    hierarchy_path = inputs / "results/milestone_4r_b1/hierarchy.json"
    slate, pools, states = (json.loads(path.read_bytes()) for path in
                            (slate_path, pool_path, state_path))
    cert = json.loads(cert_path.read_bytes())
    nodes_sha, edges_sha = cert["graph_nodes_sha256"], cert["graph_edges_sha256"]
    graph, metadata_sha = load_graph(graph_dir, nodes_sha, edges_sha)
    router = ExactRouter(graph, {"compiler": "g++", "compiler_flags": ["-O3", "-std=c++17"]},
                         output / "native")
    try:
        baselines = {}
        for od in slate["od"]:
            origin, destination = (f"road:{od[name]}" for name in
                ("origin_anchor", "destination_anchor"))
            anchors = {origin: od["origin_anchor"], destination: od["destination_anchor"]}
            provider = TableFreeRoadSelectedLegProvider(graph, router, anchors,
                nodes_sha256=nodes_sha, edges_sha256=edges_sha,
                router_sha256=router.provenance["source_sha256"],
                anchor_catalog_sha256=hashlib.sha256(canon(anchors)).hexdigest())
            leg = provider.leg(origin, destination)
            if not leg.reachable:
                raise ValueError("Frozen OD direct road baseline is unreachable")
            baselines[od["od_id"]] = {"time_s": encode_binary64(float.fromhex(leg.time_hex)),
                "actual_length_m": encode_binary64(float.fromhex(leg.length_hex)),
                "selected_edges": list(provider.edge_witnesses[origin, destination])}
        source_hashes = {"slate": sha(slate_path), "pools": sha(pool_path),
            "states": sha(state_path), "hierarchy": sha(hierarchy_path),
            "graph_nodes": nodes_sha, "graph_edges": edges_sha,
            "graph_metadata": metadata_sha,
            "router_cpp": router.provenance["source_sha256"],
            "router_binary": sha(output / "native/routing.so")}
        queries = compile_queries(slate, pools, states, baselines,
                                  source_hashes, source_hashes["hierarchy"])
        result = {"schema": "hiroute.m5d.frozen_48_query_payloads.v1",
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"],
                text=True).strip(), "source_sha256": source_hashes,
            "query_count": 48, "binding_count": 96, "queries": queries,
            "no_lp_or_exact_search_run": True}
        with (output / "queries.json").open("x") as stream:
            json.dump(result, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
    finally:
        router.close()


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:5]))
