"""One frozen C01 eight-Site real-data M5-D diagnostic query.

Run only under systemd_supervisor. This historical C01 input is a fixed
small-domain integration probe, not one of the new 12-OD formal comparisons.
Source verification, graph loading, native routes, landmark proof, seed, and
the paired search all count in the same supervised process group.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from microplan.routing import ExactRouter
from timecut5.deployable import (DomainBinding, LandmarkDistances, QueryDomain,
    RegionBoundProvider,
    RegionLandmarkSummary, SearchOutcome, construct_verified_seed,
    member_set_digest, solve_deployable_pair)
from timecut5.real_adapter import original_region_view
from timecut5.real_legs import ImmutableLegTable, NUMERICS, TIE_POLICY, restrict_frozen_tree
from timecut5.road_landmark import certify_integer_landmark
from timecut5.road_provider import RoadSelectedLegProvider
from validation.reference5.real_input import IndependentLegTable
from validation.reference5.real_solver import query_from_resolved_state


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canon(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def encode(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    return value


def verifier_hashes():
    import validation.reference5 as package
    from validation.reference5 import lp, model, real_input, real_solver, solver
    return {name: sha(Path(inspect.getsourcefile(module))) for name, module in (
        ("package", package), ("real_solver", real_solver), ("real_input", real_input),
        ("model", model), ("solver", solver), ("lp", lp))}


def load_graph(graph_dir: Path, expected_nodes: str, expected_edges: str):
    nodes_path, edges_path = graph_dir / "nodes.parquet", graph_dir / "edges.parquet"
    if sha(nodes_path) != expected_nodes or sha(edges_path) != expected_edges:
        raise ValueError("Road graph source bytes differ from frozen selected legs")
    metadata_path = graph_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    edges = pd.read_parquet(edges_path,
                            columns=["source", "target", "travel_time_s", "length_m"])
    source = np.ascontiguousarray(edges.source.to_numpy(dtype=np.int64))
    target = np.ascontiguousarray(edges.target.to_numpy(dtype=np.int64))
    travel = np.ascontiguousarray(edges.travel_time_s.to_numpy(dtype=np.float64))
    length = np.ascontiguousarray(edges.length_m.to_numpy(dtype=np.float64))
    del edges
    n, m = int(metadata["node_count"]), int(metadata["edge_count"])
    if (len(source) != m or len(target) != m or
            (source < 0).any() or (source >= n).any() or
            (target < 0).any() or (target >= n).any() or
            not np.isfinite(travel).all() or (travel <= 0).any() or
            not np.isfinite(length).all() or (length < 0).any()):
        raise ValueError("Graph arrays violate directed native routing contract")
    return SimpleNamespace(node_count=n, edge_count=m, source=source, target=target,
        weights={"travel_time": travel, "distance": length}), sha(metadata_path)


def run(args):
    started = time.monotonic_ns()
    root, export, graph_dir, output = map(Path,
        (args.repo, args.export_dir, args.graph_dir, args.output_dir))
    if not output.is_dir() or (output / "query_result.json").exists():
        raise ValueError("New existing output directory without a prior result required")
    state_path = export / "query_states_resolved.json"
    if sha(state_path) != args.states_sha256:
        raise ValueError("Frozen resolved-state bytes changed")
    states = json.loads(state_path.read_text())
    state = next((row for row in states if row.get("state_id") == "C01"), None)
    if state is None or state.get("pool_id") != "OD00_energy_only" or state.get("H_ref") != 4:
        raise ValueError("Fixed C01 small-query identity differs")
    reference = state["immutable_direct_leg_table"]
    table_path = export / reference["path"]
    if sha(table_path) != reference["sha256"]:
        raise ValueError("Frozen selected-leg table bytes changed")
    table_bytes = table_path.read_bytes()
    table = ImmutableLegTable.from_bytes(table_bytes, reference["sha256"])
    if len(table.sites) != 8 or len(table.legs) != 81:
        raise ValueError("C01 no longer has the fixed eight-Site domain")
    original = root / "results/milestone_4r_b1/hierarchy.json"
    hierarchy_bytes = original.read_bytes()
    if hashlib.sha256(hierarchy_bytes).hexdigest() != table.hierarchy_sha256:
        raise ValueError("Original Region source changed")
    selection = export / "selection_manifest.json"
    if sha(selection) != table.selection_certificate_sha256:
        raise ValueError("Frozen candidate selection source changed")
    sources = dict(table.source_sha256)
    nodes_sha = sources["data/processed/graphs/slovenia_extended/nodes.parquet"]
    edges_sha = sources["data/processed/graphs/slovenia_extended/edges.parquet"]
    graph, metadata_sha = load_graph(graph_dir, nodes_sha, edges_sha)
    anchor_nodes = {anchor: int(anchor.removeprefix("road:")) for anchor in table.anchors}
    if any(f"road:{node}" != anchor for anchor, node in anchor_nodes.items()):
        raise ValueError("Noncanonical road-anchor identity")
    config = {"compiler": "g++", "compiler_flags": ["-O3", "-std=c++17"]}
    def make_landmark_router(conservative):
        return ExactRouter(conservative, config, output / "landmark_native")
    landmark, landmark_bytes = certify_integer_landmark(graph, anchor_nodes,
        table.origin_anchor, make_landmark_router,
        graph_nodes_sha256=nodes_sha, graph_edges_sha256=edges_sha)
    landmark_sha = hashlib.sha256(landmark_bytes).hexdigest()
    with (output / "landmark_certificate.json").open("xb") as stream:
        stream.write(landmark_bytes)
    native = ExactRouter(graph, config, output / "road_native")
    try:
        road = RoadSelectedLegProvider(graph, native, table, anchor_nodes,
            nodes_sha256=nodes_sha, edges_sha256=edges_sha)
        for source in table.anchors:
            for target in table.anchors:
                road.leg(source, target)
        road_report = {"schema": "hiroute.m5d.road_witnesses.v1",
            "graph_nodes_sha256": nodes_sha, "graph_edges_sha256": edges_sha,
            "native_source_sha256": native.provenance["source_sha256"],
            "table_sha256": table.payload_sha256,
            "source_run_count": road.source_run_count,
            "route_wall_ns": road.route_wall_ns,
            "route_process_cpu_ns": road.route_process_cpu_ns,
            "ordered_pairs": len(road.edge_witnesses),
            "edge_witnesses": {source + "->" + target: list(path) if path is not None else None
                for (source, target), path in sorted(road.edge_witnesses.items())}}
        with (output / "road_witnesses.json").open("x") as stream:
            json.dump(road_report, stream, sort_keys=True)
            stream.write("\n")
        independent = IndependentLegTable.from_bytes(table_bytes, table.payload_sha256)
        query = query_from_resolved_state(state, independent)
        query.update(leg_payload_sha256=table.payload_sha256,
                     selection_certificate_sha256=table.selection_certificate_sha256,
                     hierarchy_sha256=table.hierarchy_sha256)
        query_bytes = canon(encode(query))
        candidate_bytes = canon(sorted(table.sites))
        graph_bytes = canon(dict(nodes_sha256=nodes_sha, edges_sha256=edges_sha,
                                 metadata_sha256=metadata_sha))
        catalog_bytes = canon([dict(site_id=site.site_id, anchor_id=site.anchor_id,
                                    effects=site.effects) for site in table.sites.values()])
        contract_bytes = canon(dict(table_sha256=table.payload_sha256,
            tie_policy=TIE_POLICY, direction_policy=table.direction_policy,
            routing_py_sha256=sha(root / "src/microplan/routing.py"),
            routing_cpp_sha256=sha(root / "src/microplan/routing.cpp"),
            road_provider_sha256=sha(root / "src/timecut5/road_provider.py")))
        bound_bytes = dict(graph_sha256=graph_bytes, site_catalog_sha256=catalog_bytes,
            population_sha256=selection.read_bytes(), hierarchy_sha256=hierarchy_bytes,
            landmark_sha256=landmark_bytes,
            selected_leg_contract_sha256=contract_bytes,
            candidate_set_sha256=candidate_bytes, query_sha256=query_bytes,
            mobility_budget_sha256=b"unrestricted",
            depth_policy_sha256=b"positive_overhead_verified_seed_v1",
            numeric_contract_sha256=NUMERICS.encode())
        binding = DomainBinding.from_verified_bytes({name: (value,
            hashlib.sha256(value).hexdigest()) for name, value in bound_bytes.items()})
        domain = QueryDomain(binding, query_bytes, candidate_bytes,
                             table_bytes, table.payload_sha256)
        distances = LandmarkDistances(dict(landmark.from_landmark),
                                      dict(landmark.to_landmark))
        for site_id, site in table.sites.items():
            distances.from_landmark[site_id] = landmark.from_landmark[site.anchor_id]
            distances.to_landmark[site_id] = landmark.to_landmark[site.anchor_id]
        restriction = restrict_frozen_tree(hierarchy_bytes, table.hierarchy_sha256,
                                           list(table.sites))
        original_root = original_region_view(table, restriction)
        summaries = {}
        def summarize(region):
            if region.members:
                summaries[region.identifier] = RegionLandmarkSummary(
                    member_set_digest(region.members), binding.graph_sha256,
                    binding.landmark_sha256,
                    (min(distances.from_landmark[site] for site in region.members),),
                    (max(distances.to_landmark[site] for site in region.members),))
            for child in region.children:
                summarize(child)
        summarize(original_root)
        provider_setup_started = time.monotonic_ns()
        checked_region_provider = RegionBoundProvider(domain, original_root,
            landmarks=(distances,), summaries=summaries)
        provider_setup_ns = time.monotonic_ns() - provider_setup_started
        hashes = verifier_hashes()
        seed_started = time.monotonic_ns()
        seed = construct_verified_seed(domain, hashes)
        seed_ns = time.monotonic_ns() - seed_started
        if isinstance(seed, SearchOutcome):
            raise ValueError("No independently replayed feasible seed for fixed C01")
        report = {"schema": "hiroute.m5d.fixed_C01_one_query.v1",
            "role": "historical_eight_site_integration_probe_not_formal_12od_comparison",
            "mode": args.mode, "state_sha256": args.states_sha256,
            "table_sha256": table.payload_sha256,
            "binding": {name: getattr(binding, name)
                for name in DomainBinding.__dataclass_fields__},
            "landmark_sha256": landmark_sha,
            "road_witnesses_sha256": sha(output / "road_witnesses.json"),
            "seed_j": str(seed.seed.primary_j), "seed_h": len(seed.sequence),
            "certified_max_depth": seed.max_depth, "seed_elapsed_ns": seed_ns,
            "preflight_region_setup_elapsed_ns": provider_setup_ns,
            "preflight_region_index_entries": checked_region_provider.setup_index_entries,
            "setup_elapsed_ns": time.monotonic_ns() - started}
        if args.mode == "solve":
            solved = solve_deployable_pair(seed, hierarchy_bytes, hashes,
                landmarks=(distances,), summaries=summaries,
                selected_leg_provider=road)
            report.update(status=solved.flat.status.value,
                exact_key={"J": str(solved.flat.j), "Q": str(solved.flat.q),
                           "H": solved.flat.h, "Pi": solved.flat.pi},
                flat_attempted_extensions=solved.flat_attempted_extensions,
                hier_leaf_actions=solved.hier_leaf_actions,
                flat_provider_queries=solved.flat_provider_queries,
                hier_provider_queries=solved.hier_provider_queries,
                hier_online_internal_member_accesses=solved.hier_online_internal_member_accesses,
                hier_online_mask_word_work=solved.hier_online_mask_word_work,
                region_setup_elapsed_ns=solved.region_setup_elapsed_ns)
        report["total_elapsed_ns"] = time.monotonic_ns() - started
        with (output / "query_result.json").open("x") as stream:
            json.dump(report, stream, sort_keys=True)
            stream.write("\n")
        return report
    finally:
        native.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--graph-dir", type=Path, required=True)
    parser.add_argument("--states-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("preflight", "solve"), required=True)
    print(json.dumps(run(parser.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
