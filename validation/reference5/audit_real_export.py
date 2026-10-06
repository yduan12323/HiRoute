"""Verify frozen C32 primitives and count physically admissible REF regimes.

Preparation only: this program imports no router, production parser, tree
optimizer, or LP solver entry point. It never runs a real case optimization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .real_input import IndependentLegTable, require
from .real_solver import estimate_real_regimes, query_from_resolved_state
from .solver import jsonable


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_export(export_root, expected_manifest_sha, selection_path, expected_selection_sha, production_root):
    export_root, selection_path, production_root = map(Path, (export_root, selection_path, production_root))
    require(file_sha(export_root / "export_manifest.json") == expected_manifest_sha, "Export manifest hash mismatch")
    require(file_sha(selection_path) == expected_selection_sha, "Selection manifest hash mismatch")
    manifest = json.loads((export_root / "export_manifest.json").read_text())
    selection = json.loads(selection_path.read_text())
    require(manifest["selection_certificate_sha256"] == expected_selection_sha, "Export selection identity mismatch")
    auxiliary = {"preflight.json": manifest["preflight_sha256"],
                 "native_router.json": manifest["native_router_sha256"],
                 "real_pair_full_calibration.json": manifest["calibration_sha256"],
                 "query_states_resolved.json": manifest["query_states_resolved_sha256"]}
    for name, expected in auxiliary.items():
        require(file_sha(export_root / name) == expected, f"Auxiliary artifact hash mismatch: {name}")
    native = json.loads((export_root / "native_router.json").read_text())
    binary_path = Path(native["provenance"]["compiler_command"][-1])
    require(file_sha(binary_path) == native["binary_sha256"], "Native binary hash mismatch")
    require(file_sha(manifest["original_hierarchy_path"]) == manifest["hierarchy_sha256"], "Original hierarchy hash mismatch")
    pools = {pool["pool_id"]: pool for pool in selection["pools"]}
    tables, source_claims, unique_pairs, table_reports = {}, {}, {}, []
    for pool_id, info in sorted(manifest["tables"].items()):
        table = IndependentLegTable.from_bytes((export_root / info["path"]).read_bytes(), info["sha256"])
        require(table.selection_certificate_sha256 == expected_selection_sha and table.hierarchy_sha256 == manifest["hierarchy_sha256"],
                "Table selection/hierarchy provenance mismatch")
        expected_sites = {row["site_id"]: (f"road:{row['access_node']}", tuple(sorted(row["eligible_actions"])))
                          for row in pools[pool_id]["chosen"]}
        require({site_id: (site.anchor_id, site.effects) for site_id, site in table.sites.items()} == expected_sites,
                "Selected Site identity/anchor/effects changed in export")
        expected_anchors = {table.origin_anchor, table.destination_anchor, *(anchor for anchor, _ in expected_sites.values())}
        require(set(table.anchors) == expected_anchors, "Export anchor population changed")
        require(len(table.pairs) == info["ordered_pair_count"] and len(table.anchors) == info["anchor_count"] and
                len(table.sites) == info["site_count"], "Table count metadata mismatch")
        for name, digest in {**table.source_sha256, **table.router_source_sha256}.items():
            require(name not in source_claims or source_claims[name] == digest, "Contradictory inter-table source hashes")
            source_claims[name] = digest
        for key, pair in table.pairs.items():
            require(key not in unique_pairs or unique_pairs[key] == pair, "Shared immutable pair differs across pools")
            unique_pairs[key] = pair
        restriction = manifest["restrictions"][pool_id]
        require(file_sha(export_root / restriction["path"]) == restriction["sha256"], "Restriction file hash mismatch")
        require(restriction["original_sha256"] == table.hierarchy_sha256, "Restriction original hierarchy mismatch")
        tables[pool_id] = table
        table_reports.append(dict(pool_id=pool_id, payload_sha256=table.payload_sha256, sites=len(table.sites),
                                  physical_anchors=len(table.anchors), ordered_pairs=len(table.pairs),
                                  identity_pairs=sum(a == b for a, b in table.pairs),
                                  unreachable_pairs=sum(not row.reachable for row in table.pairs.values()),
                                  restriction_hash_verified_only=True))
    require(len(unique_pairs) == manifest["requested_pair_count"], "Unique pair count mismatch")
    require(sum(a == b for a, b in unique_pairs) == manifest["identity_pair_count"], "Identity pair count mismatch")
    require(sum(not row.reachable for row in unique_pairs.values()) == manifest["unreachable_pair_count"], "Unreachable pair count mismatch")
    # File paths come from the frozen restoration/selection provenance; large
    # graph artifacts are streaming-hashed, never parsed or loaded as a graph.
    physical_paths = {row["repository_target_path"]: Path(row["local_path"]) for row in selection["sources"]}
    physical_paths["results/milestone_4r_b1/hierarchy.json"] = Path(manifest["original_hierarchy_path"])
    audit_root = selection_path.parents[3]
    source_reports = []
    for name, expected in sorted(source_claims.items()):
        if name.startswith("acceptance_populations/"):
            path = audit_root / name
        elif name in physical_paths:
            path = physical_paths[name]
        else:
            path = production_root / name
        actual = file_sha(path)
        require(actual == expected, f"Actual source hash mismatch: {name}")
        source_reports.append(dict(name=name, path=str(path), sha256=actual, size_bytes=path.stat().st_size))
    states = json.loads((export_root / "query_states_resolved.json").read_text())
    original_states = {row["state_id"]: row for row in json.loads((selection_path.parent / "query_states.json").read_text())}
    state_reports = []
    preserved_fields = ("H_ref", "state_id", "pool_id", "mode", "instance_id", "origin_road_anchor", "destination_road_anchor",
                        "initial_soc", "initial_energy_kwh", "capacity_kwh", "energy_floor_kwh", "terminal_reserve_kwh",
                        "consumption_kwh_per_m", "overhead_s", "stop_penalty_s", "start_time_s", "charging_primitive")
    for state in states:
        require(all(state[key] == original_states[state["state_id"]][key] for key in preserved_fields),
                "Frozen physical query changed during export")
        table = tables[state["pool_id"]]
        query = query_from_resolved_state(state, table)
        preflight = estimate_real_regimes(query, table)
        state_reports.append(dict(state_id=state["state_id"], pool_id=state["pool_id"], query=query,
                                  counts=preflight["counts"], exclusions=preflight["exclusions"],
                                  terminal_excluded_sites=preflight["terminal_excluded_sites"],
                                  table_sha256=table.payload_sha256))
    require(len(states) == selection["state_count"] == 32, "Frozen state population mismatch")
    return dict(scope="independent_immutable_parser_and_exact_physical_preflight_only", no_real_optimization_run=True,
                no_graph_loaded=True, no_native_router_run=True, no_tree_optimizer_or_parser_used=True,
                export_manifest_sha256=expected_manifest_sha, selection_manifest_sha256=expected_selection_sha,
                query_states_sha256=manifest["query_states_resolved_sha256"], native_binary_sha256=native["binary_sha256"],
                auxiliary_hashes=auxiliary, verified_sources=source_reports, tables=table_reports,
                unique_pair_count=len(unique_pairs), states=state_reports,
                regimes_after_exact_physical_exclusions=sum(row["counts"]["continuous_regimes"] for row in state_reports),
                limitations=["Payload/source identity is independently checked; native route optimality is not re-proved.",
                             "Full road-edge path witnesses are not supplied by the selected-pair format.",
                             "Hierarchy restriction hashes are checked, but REF does not consume tree topology.",
                             "No runtime estimate or Stage C acceptance claim; resource plan required before large LP run."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--production-root", type=Path, required=True, help="Read-only source-file provenance, not imported code")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_export(args.export_root, args.manifest_sha256, args.selection_manifest,
                          args.selection_sha256, args.production_root)
    with args.output.open("x") as handle:
        json.dump(jsonable(report), handle, indent=2)
        handle.write("\n")
    print(json.dumps(dict(independent_tables=len(report["tables"]), states=len(report["states"]),
                          source_hashes_verified=len(report["verified_sources"]),
                          post_exclusion_regimes=report["regimes_after_exact_physical_exclusions"])))


if __name__ == "__main__":
    main()
