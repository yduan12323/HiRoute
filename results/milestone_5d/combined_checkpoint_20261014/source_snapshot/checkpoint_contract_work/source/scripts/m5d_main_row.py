"""One source-bound M5-D main method row inside a single supervised unit."""
from __future__ import annotations

from fractions import Fraction as R
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.m5d_build_main_queries import canon, sha
from timecut5.bounded import _solve_problem
from timecut5.hierarchy import build_regions, _solve_hierarchical_problem
from timecut5.real_adapter import TableFreeRealProblem, site_catalog_digest
from timecut5.real_legs import RealSite
from timecut5.road_provider import TableFreeRoadSelectedLegProvider, TableFreeRegionBoundProvider
from timecut5.sparse_seed import SparseSeedCatalog, admit_sparse_seed, replay_sparse_seed
from timecut5.live_replay import ExactLayerReplay


def append_phase(out: Path, phase: str, **fields):
    row = {"phase": phase, "monotonic_ns": time.monotonic_ns(),
           "process_cpu_ns": time.process_time_ns(), **fields}
    with (out / "phase.jsonl").open("a") as stream:
        stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def save_status(out: Path, value):
    with (out / "status.json").open("x") as stream:
        json.dump(value, stream, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def save_bytes_atomic(path: Path, data: bytes):
    temporary = path.with_suffix(path.suffix + ".next")
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class DurableLayerReplay:
    def __init__(self, path: Path, *, mode: str, domain_sha256: str,
                 external_source_sha256: dict[str, str], previous_checkpoint=None):
        self.path = path
        self.replay = ExactLayerReplay(mode=mode, domain_sha256=domain_sha256,
            external_source_sha256=external_source_sha256,
            previous_checkpoint=previous_checkpoint)

    def __call__(self, *args):
        self.replay(*args)
        save_bytes_atomic(self.path, self.replay.checkpoint_bytes())

    def finish(self):
        self.replay.finish()


def exact_outcome(result):
    """Record only mathematically defined coordinates of an exact terminal."""
    if result.status == "attained_optimum":
        if result.key is None or result.witness is None:
            raise ValueError("Attained terminal lacks an executable key")
        j, q, h, pi = result.key
        return {"status": "attained_optimum", "J": str(j), "Q": str(q),
                "H": h, "Pi": [list(event) for event in pi],
                "J_attained": True, "Q_attained": True}
    if result.status == "infimum_unattained" and result.unattained_component == "J":
        if result.primary_infimum is None or result.secondary_infimum is not None or result.key is not None:
            raise ValueError("Malformed primary infimum terminal")
        return {"status": "infimum_unattained_J", "J": str(result.primary_infimum),
                "Q": None, "H": None, "Pi": None,
                "J_attained": False, "Q_attained": None}
    if result.status == "infimum_unattained" and result.unattained_component == "Q":
        if (result.primary_infimum is None or result.secondary_infimum is None or
                result.key is not None):
            raise ValueError("Malformed secondary infimum terminal")
        return {"status": "infimum_unattained_Q", "J": str(result.primary_infimum),
                "Q": str(result.secondary_infimum), "H": None, "Pi": None,
                "J_attained": True, "Q_attained": False}
    raise ValueError("Certified seed contradicts infeasible or unknown terminal")


def execute_exact_method(query, sites, provider, catalog, bound, root, seed, method,
                         checkpoint_hook=None):
    """Run the production exact engine and independently replay its terminal."""
    if method not in ("flat", "hier") or seed["status"] != "verified":
        raise ValueError("Exact method requires a verified same-domain seed")
    exact_query = dict(query, H_ref=seed["max_depth"])
    problem = TableFreeRealProblem(exact_query, sites, provider,
        origin_anchor=query["origin"], destination_anchor=query["destination"],
        site_catalog_sha256=catalog.site_catalog_sha256)
    solved = (_solve_problem(problem, verified_primary_upper=seed["lex_key"][0],
        singleton_bound=bound.singleton_bound,
        checkpoint_hook=checkpoint_hook) if method == "flat" else
        _solve_hierarchical_problem(problem, True, root,
            verified_primary_upper=seed["lex_key"][0], bound_provider=bound,
            checkpoint_hook=checkpoint_hook))
    bounded = solved if method == "flat" else solved.bounded
    witness = bounded.result.witness
    if witness is not None:
        charges = tuple(event.departure_energy - event.arrival_energy
            for event in witness.events if event.effect in ("C", "CS"))
        replay = replay_sparse_seed(exact_query, catalog, witness.pi, charges)
        if replay["lex_key"] != bounded.result.key:
            raise ValueError("Independent full-depth terminal replay differs")
    return bounded, witness is not None


def run(source: Path, graph_dir: Path, pool_path: Path, queries_path: Path,
        manifest_path: Path, manifest_sha256: str, row_id: str, out: Path,
        previous_checkpoint_path: Path | None = None):
    from microplan.routing import ExactRouter
    from scripts.m5d_one_query_runner import load_graph
    if sha(manifest_path) != manifest_sha256:
        raise ValueError("Frozen main manifest bytes differ")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("schema") != "hiroute.m5d.frozen_main_phase.v1":
        raise ValueError("Frozen main phase schema required")
    row = next((item for item in manifest["rows"] if item["row_id"] == row_id), None)
    if row is None or row["method"] not in ("flat", "hier") or row["candidate_prefix_count"] not in (32, 128):
        raise ValueError("Unknown fixed main method row")
    for name, expected in manifest["source_sha256"].items():
        if sha(source / name) != expected:
            raise ValueError(f"Main source closure differs at {name}")
    if sha(queries_path) != manifest["input_sha256"]["queries"] or sha(pool_path) != manifest["input_sha256"]["pools"]:
        raise ValueError("Frozen query or population bytes differ")
    queries, pools = json.loads(queries_path.read_bytes()), json.loads(pool_path.read_bytes())
    if queries.get("schema") != "hiroute.m5d.frozen_48_query_payloads.v1":
        raise ValueError("Frozen exact query payload schema differs")
    qrow = next((item for item in queries["queries"] if item["query_id"] == row["query_id"]), None)
    if qrow is None:
        raise ValueError("Fixed query ID absent")
    size = row["candidate_prefix_count"]
    binding = qrow["bindings"][str(size)]
    query = binding["query"]
    if sha(source / "results/milestone_4r_b1/hierarchy.json") != query["hierarchy_sha256"]:
        raise ValueError("Frozen hierarchy bytes differ")
    if hashlib.sha256(canon(query)).hexdigest() != binding["query_sha256"]:
        raise ValueError("Frozen exact query bytes differ")
    pool = next(item for item in pools["pools"] if item["od_id"] == qrow["od_id"])
    selected = pool["sites"][:size]
    if [s["site_id"] for s in selected] != binding["candidate_site_ids"]:
        raise ValueError("Frozen candidate Site identities differ")
    sites = {s["site_id"]: RealSite(s["site_id"], s["anchor_id"], tuple(s["effects"]))
             for s in selected}
    if len(sites) != size or site_catalog_digest(sites) != binding["site_catalog_sha256"]:
        raise ValueError("Frozen complete Site catalog differs")
    origin, destination = query["origin"], query["destination"]
    anchors = list(dict.fromkeys([origin] + [s.anchor_id for s in sites.values()] + [destination]))
    anchor_nodes = {anchor: int(anchor.removeprefix("road:")) for anchor in anchors}
    if hashlib.sha256(canon(anchor_nodes)).hexdigest() != binding["anchor_catalog_sha256"]:
        raise ValueError("Frozen anchor mapping differs")
    append_phase(out, "inputs_verified", row_id=row_id,
                 manifest_sha256=manifest_sha256, query_sha256=binding["query_sha256"])
    graph, metadata_sha = load_graph(graph_dir,
        manifest["input_sha256"]["graph_nodes"], manifest["input_sha256"]["graph_edges"])
    if metadata_sha != manifest["input_sha256"]["graph_metadata"]:
        raise ValueError("Frozen graph metadata bytes differ")
    append_phase(out, "graph_loaded", node_count=graph.node_count,
                 edge_count=graph.edge_count)
    native_config = {"compiler": "g++", "compiler_flags": ["-O3", "-std=c++17"]}
    router = ExactRouter(graph, native_config, out / "road_native")
    try:
        if router.provenance["source_sha256"] != manifest["source_sha256"]["src/microplan/routing.cpp"]:
            raise ValueError("Frozen native router source differs")
        provider = TableFreeRoadSelectedLegProvider(graph, router, anchor_nodes,
            nodes_sha256=manifest["input_sha256"]["graph_nodes"],
            edges_sha256=manifest["input_sha256"]["graph_edges"],
            router_sha256=router.provenance["source_sha256"],
            anchor_catalog_sha256=binding["anchor_catalog_sha256"])
        catalog = SparseSeedCatalog(provider, sites, origin_anchor=origin,
            destination_anchor=destination, nodes_path=graph_dir / "nodes.parquet",
            edges_path=graph_dir / "edges.parquet",
            site_catalog_sha256=binding["site_catalog_sha256"],
            hierarchy_sha256=query["hierarchy_sha256"],
            candidate_sha256=binding["candidate_sha256"])
        if catalog.domain_sha256 != binding["sparse_domain_sha256"]:
            raise ValueError("Frozen sparse source domain differs")
        append_phase(out, "seed_started", source_run_count=provider.source_run_count)
        seed = admit_sparse_seed(query, catalog)
        if seed["status"] != "verified":
            append_phase(out, "seed_failed", status=seed["status"])
            save_status(out, {"row_id": row_id, "status": seed["status"],
                "denominator_included": True, "solver_started": False})
            return
        prewarm = hashlib.sha256(repr(sorted(provider.legs.items())).encode()).hexdigest()
        append_phase(out, "seed_verified", seed_j=str(seed["lex_key"][0]),
            certified_depth=seed["max_depth"], prewarm_sha256=prewarm,
            source_run_count=provider.source_run_count,
            requested_pair_count=len(provider.legs))
        root = build_regions(sites)
        bound = TableFreeRegionBoundProvider(provider, sites, root,
            destination_anchor=destination, landmark_anchor=origin,
            site_catalog_sha256=binding["site_catalog_sha256"],
            router_factory=lambda conservative: ExactRouter(conservative,
                native_config, out / "landmark_native"))
        append_phase(out, "bounds_verified", landmark_sha256=bound.landmark_sha256)
        seed_payload = {"schema": "hiroute.m5d.main_seed.v1", "row_id": row_id,
            "manifest_sha256": manifest_sha256,
            "sparse_domain_sha256": catalog.domain_sha256,
            "query_sha256": binding["query_sha256"],
            "lex_key": str(seed["lex_key"]), "sequence": seed["sequence"],
            "charges": [str(value) for value in seed["charges"]],
            "certified_depth": seed["max_depth"]}
        seed_bytes = canon(seed_payload)
        save_bytes_atomic(out / "seed.json", seed_bytes)
        external = {"graph_nodes": manifest["input_sha256"]["graph_nodes"],
            "graph_edges": manifest["input_sha256"]["graph_edges"],
            "router": hashlib.sha256(canon([router.provenance["source_sha256"],
                sha(out / "road_native/routing.so")])).hexdigest(),
            "anchors": binding["anchor_catalog_sha256"],
            "sites": binding["site_catalog_sha256"],
            "query": binding["query_sha256"],
            "hierarchy": query["hierarchy_sha256"],
            "landmark": bound.landmark_sha256,
            "seed": hashlib.sha256(seed_bytes).hexdigest(),
            "policy": manifest_sha256,
            "runtime": hashlib.sha256(canon([sys.executable, sys.version])).hexdigest()}
        layer_domain = hashlib.sha256(canon({"sparse": catalog.domain_sha256,
            "external": external})).hexdigest()
        previous = (previous_checkpoint_path.read_bytes()
                    if previous_checkpoint_path is not None else None)
        hook = DurableLayerReplay(out / "layer_checkpoint.json",
            mode=row["method"], domain_sha256=layer_domain,
            external_source_sha256=external, previous_checkpoint=previous)
        append_phase(out, "search_started", method=row["method"])
        bounded, witness_replayed = execute_exact_method(query, sites, provider,
            catalog, bound, root, seed, row["method"], checkpoint_hook=hook)
        outcome = exact_outcome(bounded.result)
        append_phase(out, "search_finished", exact_outcome=outcome)
        append_phase(out, "terminal_verified", witness_present=witness_replayed)
        save_status(out, {"row_id": row_id,
            "status": outcome["status"],
            "exact_outcome": outcome,
            "witness_independently_replayed": witness_replayed,
            "seed_j": str(seed["lex_key"][0]),
            "certified_depth": seed["max_depth"],
            "prewarm_sha256": prewarm,
            "source_run_count": provider.source_run_count,
            "requested_pair_count": len(provider.legs),
            "denominator_included": True})
    finally:
        router.close()


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:6]),
        sys.argv[6], sys.argv[7], Path(sys.argv[8]),
        Path(sys.argv[9]) if len(sys.argv) > 9 else None)
