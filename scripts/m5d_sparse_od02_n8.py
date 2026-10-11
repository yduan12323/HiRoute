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


def run(inputs: Path, graph_dir: Path, cert_path: Path, out: Path,
        recover: bool = False, boundary_seed_receipt: Path | None = None,
        old_checkpoint: Path | None = None):
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
        if boundary_seed_receipt is None:
            admission = admit_sparse_seed(query, catalog)
        else:
            from timecut5.sparse_seed import replay_sparse_seed
            prior = json.loads(boundary_seed_receipt.read_bytes())
            if (prior.get("sparse_domain_sha256") != catalog.domain_sha256 or
                    prior.get("query_sha256") != hashlib.sha256(canon(query)).hexdigest() or
                    prior.get("candidate_sha256") != candidate_sha or
                    prior.get("loaded_graph_arrays_sha256") != loaded_arrays_sha or
                    prior.get("status") != "verified"):
                raise ValueError("Prior seed proposal differs from complete source domain")
            sequence = tuple(tuple(event) for event in prior["seed"]["sequence"])
            charges = tuple(R(value) for value in prior["seed"]["charges"])
            fresh = replay_sparse_seed(query, catalog, sequence, charges)
            depth = fresh["lex_key"][0] // (R(query["overhead_s"]) + R(query["lambda_stop_s"]))
            if (str(fresh["lex_key"][0]) != prior["seed"]["lex_key"][0] or
                    depth != prior["seed"]["max_depth"]):
                raise ValueError("Fresh sparse seed differs from retained proposal")
            admission = {"status": "verified", "lex_key": fresh["lex_key"],
                "sequence": sequence, "charges": charges, "max_depth": depth,
                "proposal_count": 1, "accepted_count": 1}
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
        if recover or boundary_seed_receipt is not None:
            from timecut5.bounded import _solve_problem, prefix_primary_lower_bound
            from timecut5.hierarchy import build_regions
            from timecut5.live_replay import ExactLayerReplay, LayerCheckpointStop, source_manifest
            from timecut5.real_adapter import TableFreeRealProblem
            from timecut5.road_provider import TableFreeRegionBoundProvider
            from timecut5.real_legs import TIE_POLICY
            if admission["status"] != "verified":
                raise ValueError("No verified seed for exact recovery probe")
            root = build_regions(sites)
            root_sha = hashlib.sha256(repr(root).encode()).hexdigest()
            bound = TableFreeRegionBoundProvider(provider, sites, root,
                destination_anchor=destination, landmark_anchor=origin,
                site_catalog_sha256=catalog.site_catalog_sha256,
                router_factory=lambda conservative: ExactRouter(conservative,
                    {"compiler": "g++", "compiler_flags": ["-O3", "-std=c++17"]},
                    out / "landmark_native"))
            runtime_sha = hashlib.sha256(canon([sys.executable, sys.version])).hexdigest()
            seed_sha = hashlib.sha256(canon([str(admission["lex_key"]),
                str(admission["sequence"]), str(admission["charges"])])).hexdigest()
            external = {"graph_nodes": nodes_sha, "graph_edges": edges_sha,
                "router": hashlib.sha256(canon([router.provenance["source_sha256"],
                    sha(out / "native/routing.so")])).hexdigest(),
                "anchors": anchor_sha, "sites": catalog.site_catalog_sha256,
                "query": hashlib.sha256(canon(query)).hexdigest(),
                "hierarchy": root_sha,
                "landmark": bound.landmark_sha256, "seed": seed_sha,
                "policy": hashlib.sha256(TIE_POLICY.encode()).hexdigest(),
                "runtime": runtime_sha}
            domain_sha = hashlib.sha256(canon({"sparse": catalog.domain_sha256,
                "arrays": loaded_arrays_sha, "external": external})).hexdigest()
            exact_query = dict(query, H_ref=admission["max_depth"])

            def solve(hook):
                problem = TableFreeRealProblem(exact_query, sites, provider,
                    origin_anchor=origin, destination_anchor=destination,
                    site_catalog_sha256=catalog.site_catalog_sha256)
                return _solve_problem(problem, checkpoint_hook=hook,
                    verified_primary_upper=admission["lex_key"][0],
                    singleton_bound=bound.singleton_bound)

            if boundary_seed_receipt is not None:
                if old_checkpoint is not None:
                    old = json.loads(old_checkpoint.read_bytes())
                    if old.get("search_source_sha256") == source_manifest():
                        raise ValueError("Historical checkpoint unexpectedly shares current source")
                    try:
                        ExactLayerReplay(mode="flat", domain_sha256=domain_sha,
                            external_source_sha256=external,
                            previous_checkpoint=old_checkpoint.read_bytes())
                    except ValueError:
                        pass
                    else:
                        raise ValueError("Old source checkpoint was unexpectedly admitted")
                class BoundaryRecorder:
                    def __init__(self, hook):
                        self.hook, self.rows = hook, []
                    def __call__(self, depth, layer, terminals, incumbent, counters):
                        problem = TableFreeRealProblem(exact_query, sites, provider,
                            origin_anchor=origin, destination_anchor=destination,
                            site_catalog_sha256=catalog.site_catalog_sha256)
                        lb = min((prefix_primary_lower_bound(problem, group)
                                  for group in layer), default=None)
                        self.rows.append({"depth": depth,
                            "open_sha256": hashlib.sha256(repr(layer).encode()).hexdigest(),
                            "terminals_sha256": hashlib.sha256(repr(terminals).encode()).hexdigest(),
                            "incumbent": str(incumbent), "open_prefix_lb": str(lb),
                            "counters": counters})
                        self.hook(depth, layer, terminals, incumbent, counters)
                def stop_at(depth, previous=None):
                    hook = ExactLayerReplay(mode="flat", domain_sha256=domain_sha,
                        external_source_sha256=external,
                        previous_checkpoint=previous, stop_after_depth=depth)
                    recorder = BoundaryRecorder(hook)
                    started_cpu = time.process_time_ns()
                    try:
                        solve(recorder)
                    except LayerCheckpointStop as stopped:
                        return stopped.checkpoint_bytes, recorder.rows, hook.replayed_restore_layers, time.process_time_ns()-started_cpu
                    raise ValueError("Early exact layer boundary was not reached")
                reference, reference_rows, _, reference_cpu = stop_at(2)
                first, first_rows, _, first_cpu = stop_at(1)
                (out / "layer_checkpoint.json").write_bytes(first)
                resumed, resumed_rows, replayed, replay_cpu = stop_at(2, first)
                if reference != resumed or reference_rows != resumed_rows or first_rows != reference_rows[:2] or replayed != 2:
                    raise ValueError("Same-engine early layer replay differs from uninterrupted boundary")
                result = {"schema": "hiroute.m5d.od02_n8_early_layer_recovery.v1",
                    "status": "boundary_verified_no_optimum_claim",
                    "source_commit": report["source_commit"], "domain_sha256": domain_sha,
                    "external_source_sha256": external,
                    "checkpoint_sha256": hashlib.sha256(first).hexdigest(),
                    "reference_boundary_sha256": hashlib.sha256(reference).hexdigest(),
                    "resumed_boundary_sha256": hashlib.sha256(resumed).hexdigest(),
                    "reference_rows": reference_rows, "resumed_rows": resumed_rows,
                    "replayed_restore_layers": replayed,
                    "reference_process_cpu_ns": reference_cpu,
                    "interrupted_process_cpu_ns": first_cpu,
                    "replay_process_cpu_ns": replay_cpu,
                    "total_search_process_cpu_ns": reference_cpu+first_cpu+replay_cpu,
                    "source_run_count": provider.source_run_count,
                    "requested_pair_count": len(provider.legs)}
                with (out / "early_recovery_receipt.json").open("x") as stream:
                    json.dump(result, stream, sort_keys=True, default=str)
                    stream.write("\n")
                print(json.dumps(result, sort_keys=True, default=str), flush=True)
                return

            def key_and_replay(solved):
                key = solved.result.key
                witness = solved.result.witness
                if witness is not None:
                    charges = tuple(event.departure_energy - event.arrival_energy
                        for event in witness.events if event.effect in ("C", "CS"))
                    replay = replay_sparse_seed(query, catalog, witness.pi, charges)
                    if replay["lex_key"] != key:
                        raise ValueError("Independent selected-edge terminal replay differs")
                return key

            from timecut5.sparse_seed import replay_sparse_seed
            baseline_cpu = time.process_time_ns()
            baseline = solve(None)
            baseline_cpu = time.process_time_ns() - baseline_cpu
            baseline_key = key_and_replay(baseline)
            interrupt = ExactLayerReplay(mode="flat", domain_sha256=domain_sha,
                external_source_sha256=external, stop_after_depth=1)
            interrupted_cpu = time.process_time_ns()
            try:
                solve(interrupt)
            except LayerCheckpointStop as stopped:
                checkpoint = stopped.checkpoint_bytes
            else:
                raise ValueError("Safe layer interruption was not reached")
            interrupted_cpu = time.process_time_ns() - interrupted_cpu
            (out / "layer_checkpoint.json").write_bytes(checkpoint)
            restored = ExactLayerReplay(mode="flat", domain_sha256=domain_sha,
                external_source_sha256=external, previous_checkpoint=checkpoint)
            replay_cpu = time.process_time_ns()
            resumed = solve(restored)
            replay_cpu = time.process_time_ns() - replay_cpu
            resumed_key = key_and_replay(resumed)
            if (baseline.result.status != resumed.result.status or
                    baseline_key != resumed_key or
                    baseline.attempted_extensions != resumed.attempted_extensions or
                    baseline.feasible_extensions != resumed.feasible_extensions):
                raise ValueError("Interrupted exact search differs from uninterrupted same-domain search")
            recovery = {"schema": "hiroute.m5d.od02_n8_same_engine_recovery.v1",
                "status": "passed", "source_commit": report["source_commit"],
                "domain_sha256": domain_sha, "external_source_sha256": external,
                "checkpoint_sha256": hashlib.sha256(checkpoint).hexdigest(),
                "checkpoint_layers": len(interrupt.layers),
                "replayed_restore_layers": restored.replayed_restore_layers,
                "baseline_status": baseline.result.status,
                "resumed_status": resumed.result.status,
                "baseline_key": str(baseline_key), "resumed_key": str(resumed_key),
                "baseline_process_cpu_ns": baseline_cpu,
                "interrupted_process_cpu_ns": interrupted_cpu,
                "replay_process_cpu_ns": replay_cpu,
                "total_search_process_cpu_ns": baseline_cpu + interrupted_cpu + replay_cpu,
                "source_run_count": provider.source_run_count,
                "requested_pair_count": len(provider.legs)}
            with (out / "recovery_receipt.json").open("x") as stream:
                json.dump(recovery, stream, sort_keys=True)
                stream.write("\n")
            print(json.dumps(recovery, sort_keys=True), flush=True)
    finally:
        router.close()


if __name__ == "__main__":
    if len(sys.argv) == 5:
        run(*(Path(value) for value in sys.argv[1:5]))
    elif len(sys.argv) == 6 and sys.argv[5] == "recover":
        run(*(Path(value) for value in sys.argv[1:5]), recover=True)
    elif len(sys.argv) == 7:
        run(*(Path(value) for value in sys.argv[1:5]),
            boundary_seed_receipt=Path(sys.argv[5]), old_checkpoint=Path(sys.argv[6]))
    else:
        raise ValueError("Expected fixed OD02 paths and optional recovery inputs")
