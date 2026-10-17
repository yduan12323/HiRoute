"""One frozen supplemental row, run only inside the serial resource supervisor."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.m5d_build_main_queries import canon, sha
from scripts.m5d_main_row import (append_phase, save_status, save_bytes_atomic,
    DurableLayerReplay, execute_exact_method, exact_outcome)
from scripts.m5d_supplement_alt import SameALTMemberScan
from timecut5.hierarchy import build_regions
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite, TIE_POLICY
from timecut5.road_provider import (TableFreeRoadSelectedLegProvider,
    TableFreeRegionBoundProvider)
from timecut5.sparse_seed import (SparseSeedCatalog, admit_sparse_seed,
    sequential_no_overlap_baseline, sparse_domain_digest)


def bound_input(row, qrow, pool, full, input_hashes):
    size, component = row["candidate_count"], row["component"]
    if component == "full_universe":
        universe = full["universes_by_od"][qrow["od_id"]]
        selected = universe["sites"]
        if (len(selected) != size or
                hashlib.sha256(canon(selected)).hexdigest() != universe["site_rows_sha256"]):
            raise ValueError("Full Site universe differs")
        base = qrow["base_query"]
    else:
        selected = pool["sites"][:size]
        binding = qrow["bindings"][str(size)]
        if [s["site_id"] for s in selected] != binding["candidate_site_ids"]:
            raise ValueError("Fixed candidate prefix differs")
        base = qrow["base_query"]
    sites = {s["site_id"]: RealSite(s["site_id"], s["anchor_id"],
             tuple(s["effects"])) for s in selected}
    if len(sites) != size:
        raise ValueError("Duplicate Site in supplemental universe")
    site_sha = site_catalog_digest(sites)
    candidate_sha = hashlib.sha256(canon(sorted(sites))).hexdigest()
    anchors = list(dict.fromkeys([base["origin"]] +
        [s.anchor_id for s in sites.values()] + [base["destination"]]))
    anchor_nodes = {anchor: int(anchor.removeprefix("road:")) for anchor in anchors}
    anchor_sha = hashlib.sha256(canon(anchor_nodes)).hexdigest()
    graph_sources = {"nodes": input_hashes["graph_nodes"],
        "edges": input_hashes["graph_edges"], "router": input_hashes["router_cpp"],
        "anchors": anchor_sha,
        "tie_policy": hashlib.sha256(TIE_POLICY.encode()).hexdigest()}
    domain = sparse_domain_digest(graph_sources, site_sha, candidate_sha,
        base["hierarchy_sha256"], base["origin"], base["destination"])
    query = dict(base, sparse_domain_sha256=domain)
    if component != "full_universe":
        for key, actual in (("site_catalog_sha256", site_sha),
                            ("candidate_sha256", candidate_sha),
                            ("anchor_catalog_sha256", anchor_sha),
                            ("sparse_domain_sha256", domain),
                            ("query_sha256", hashlib.sha256(canon(query)).hexdigest())):
            if qrow["bindings"][str(size)][key] != actual:
                raise ValueError(f"Fixed prefix binding differs: {key}")
    return query, sites, anchor_nodes, site_sha, candidate_sha, anchor_sha, domain


def run(source: Path, graph_dir: Path, pool_path: Path, queries_path: Path,
        full_path: Path, manifest_path: Path, manifest_sha: str, row_id: str, out: Path):
    from microplan.routing import ExactRouter
    from scripts.m5d_one_query_runner import load_graph
    if sha(manifest_path) != manifest_sha:
        raise ValueError("Supplemental manifest bytes differ")
    manifest = json.loads(manifest_path.read_bytes())
    if (manifest.get("schema") != "hiroute.m5d.frozen_supplement.v1" or
            len(manifest.get("rows", [])) != 24):
        raise ValueError("Complete frozen supplement required")
    if (manifest["runtime_sha256"] != hashlib.sha256(canon(
            [sys.executable, sys.version])).hexdigest() or
            manifest["compiler_version_sha256"] != hashlib.sha256(
                subprocess.check_output(["g++", "--version"])).hexdigest() or
            manifest["compiler_flags"] != ["-O3", "-std=c++17"]):
        raise ValueError("Frozen runtime or native compiler differs")
    row = next((r for r in manifest["rows"] if r["row_id"] == row_id), None)
    if row is None:
        raise ValueError("Unknown supplemental row")
    for name, expected in manifest["source_sha256"].items():
        if sha(source / name) != expected:
            raise ValueError(f"Supplemental source differs: {name}")
    for key, path in (("queries", queries_path), ("pools", pool_path),
                      ("full_universes", full_path)):
        if sha(path) != manifest["input_sha256"][key]:
            raise ValueError(f"Supplemental input differs: {key}")
    queries, pools, full = (json.loads(p.read_bytes()) for p in
        (queries_path, pool_path, full_path))
    qrow = queries["queries"][row["ordinal"]]
    if qrow["query_id"] != row["query_id"]:
        raise ValueError("Frozen query ordinal differs")
    pool = next(p for p in pools["pools"] if p["od_id"] == qrow["od_id"])
    hashes = dict(manifest["input_sha256"],
        router_cpp=manifest["source_sha256"]["src/microplan/routing.cpp"])
    query, sites, anchor_nodes, site_sha, candidate_sha, anchor_sha, domain = (
        bound_input(row, qrow, pool, full, hashes))
    if sha(source / "results/milestone_4r_b1/hierarchy.json") != query["hierarchy_sha256"]:
        raise ValueError("Frozen hierarchy bytes differ")
    append_phase(out, "inputs_verified", row_id=row_id, manifest_sha256=manifest_sha,
        query_sha256=hashlib.sha256(canon(query)).hexdigest(), domain_sha256=domain)
    graph, metadata_sha = load_graph(graph_dir,
        hashes["graph_nodes"], hashes["graph_edges"])
    if metadata_sha != hashes["graph_metadata"]:
        raise ValueError("Frozen graph metadata differs")
    append_phase(out, "graph_loaded", node_count=graph.node_count,
        edge_count=graph.edge_count)
    native_config = {"compiler": "g++", "compiler_flags": ["-O3", "-std=c++17"]}
    router = ExactRouter(graph, native_config, out / "road_native")
    try:
        if router.provenance["source_sha256"] != hashes["router_cpp"]:
            raise ValueError("Native router source differs")
        provider = TableFreeRoadSelectedLegProvider(graph, router, anchor_nodes,
            nodes_sha256=hashes["graph_nodes"], edges_sha256=hashes["graph_edges"],
            router_sha256=hashes["router_cpp"], anchor_catalog_sha256=anchor_sha)
        catalog = SparseSeedCatalog(provider, sites,
            origin_anchor=query["origin"], destination_anchor=query["destination"],
            nodes_path=graph_dir / "nodes.parquet", edges_path=graph_dir / "edges.parquet",
            site_catalog_sha256=site_sha,
            hierarchy_sha256=query["hierarchy_sha256"], candidate_sha256=candidate_sha)
        if catalog.domain_sha256 != domain:
            raise ValueError("Supplemental domain differs")
        append_phase(out, "seed_started")
        if row["component"] == "sequential_feasible":
            result = sequential_no_overlap_baseline(query, catalog)
            append_phase(out, "sequential_finished", status=result["status"])
            outcome = {"status": result["status"],
                "proposal_count": result["proposal_count"],
                "domain_sha256": result["domain_sha256"]}
            if result["status"] == "feasible":
                j, q, h, pi = result["lex_key"]
                outcome.update(J=str(j), Q=str(q), H=h,
                    Pi=[list(event) for event in pi],
                    proposal_ordinal=result["proposal_ordinal"],
                    accepted_count=result["accepted_count"])
            save_status(out, {"row_id": row_id, "status": result["status"],
                "sequential_outcome": outcome,
                "denominator_included": True})
            return
        seed = admit_sparse_seed(query, catalog)
        if seed["status"] != "verified":
            append_phase(out, "seed_failed", status=seed["status"])
            save_status(out, {"row_id": row_id, "status": seed["status"],
                "denominator_included": True, "solver_started": False})
            return
        prewarm = hashlib.sha256(repr(sorted(provider.legs.items())).encode()).hexdigest()
        append_phase(out, "seed_verified", seed_j=str(seed["lex_key"][0]),
            certified_depth=seed["max_depth"], prewarm_sha256=prewarm)
        root = build_regions(sites)
        cls = SameALTMemberScan if row["component"] == "same_alt_member_scan" else TableFreeRegionBoundProvider
        bound = cls(provider, sites, root, destination_anchor=query["destination"],
            landmark_anchor=query["origin"], site_catalog_sha256=site_sha,
            router_factory=lambda conservative: ExactRouter(conservative,
                native_config, out / "landmark_native"))
        append_phase(out, "bounds_verified", landmark_sha256=bound.landmark_sha256)
        seed_payload = {"row_id": row_id, "manifest_sha256": manifest_sha,
            "domain_sha256": domain, "lex_key": str(seed["lex_key"]),
            "sequence": seed["sequence"], "charges": [str(v) for v in seed["charges"]],
            "certified_depth": seed["max_depth"]}
        seed_bytes = canon(seed_payload)
        save_bytes_atomic(out / "seed.json", seed_bytes)
        external = {"graph_nodes": hashes["graph_nodes"],
            "graph_edges": hashes["graph_edges"],
            "router": hashlib.sha256(canon([router.provenance["source_sha256"],
                sha(out / "road_native/routing.so")])).hexdigest(),
            "anchors": anchor_sha, "sites": site_sha,
            "query": hashlib.sha256(canon(query)).hexdigest(),
            "hierarchy": query["hierarchy_sha256"], "landmark": bound.landmark_sha256,
            "seed": hashlib.sha256(seed_bytes).hexdigest(), "policy": manifest_sha,
            "runtime": hashlib.sha256(canon([sys.executable, sys.version])).hexdigest()}
        layer_domain = hashlib.sha256(canon({"sparse": domain, "external": external})).hexdigest()
        hook = DurableLayerReplay(out / "layer_checkpoint.json", mode=row["method"],
            domain_sha256=layer_domain, external_source_sha256=external)
        append_phase(out, "search_started", method=row["method"])
        bounded, replayed = execute_exact_method(query, sites, provider, catalog,
            bound, root, seed, row["method"], checkpoint_hook=hook)
        outcome = exact_outcome(bounded.result)
        append_phase(out, "search_finished", exact_outcome=outcome)
        append_phase(out, "terminal_verified", witness_present=replayed)
        counters = ({"member_scan_reads": bound.member_scan_reads,
            "member_scan_summary_queries": bound.member_scan_summary_queries,
            "member_scan_mask_queries": bound.member_scan_mask_queries}
            if isinstance(bound, SameALTMemberScan) else {})
        save_status(out, {"row_id": row_id, "status": outcome["status"],
            "exact_outcome": outcome, "seed_j": str(seed["lex_key"][0]),
            "certified_depth": seed["max_depth"], "prewarm_sha256": prewarm,
            "witness_independently_replayed": replayed,
            "denominator_included": True, **counters})
    finally:
        router.close()


if __name__ == "__main__":
    run(*(Path(v) for v in sys.argv[1:7]), sys.argv[7], sys.argv[8], Path(sys.argv[9]))
