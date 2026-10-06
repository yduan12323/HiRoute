"""Memory-bounded accepted-router export. Never constructs or optimizes a leg graph.

See README.md for the provenance, numerical, and memory contract. This module
owns only compact selected pairs plus exactly four full native input arrays.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
import gc
import hashlib
import json
import math
from pathlib import Path
import resource
import shutil
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from microplan.routing import ExactRouter
from timecut5.real_legs import ImmutableLegTable, NUMERICS, SCHEMA, TIE_POLICY, encode_binary64, restrict_frozen_tree

GIB = 1024 ** 3
MAX_FINITE = sys.float_info.max
DEFAULT_SELECTION_SHA256 = "0e39ad906c01e05b4a4b764b3270360e309c24d1ae67d7a2e3533b6dca8af06a"


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(data)
    temp.replace(path)
    return hashlib.sha256(data).hexdigest()


def memory_snapshot():
    meminfo = {line.split(":")[0]: int(line.split()[1]) * 1024
               for line in Path("/proc/meminfo").read_text().splitlines()}
    status = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            status[line.split(":")[0]] = int(line.split()[1]) * 1024
    limits = []
    for limit_path, current_path in [
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ]:
        if Path(limit_path).exists() and Path(current_path).exists():
            limit = Path(limit_path).read_text().strip()
            if limit != "max":
                limits.append(max(0, int(limit) - int(Path(current_path).read_text())))
    available = min([meminfo["MemAvailable"], *limits])
    return {"available_bytes": available, "host_available_bytes": meminfo["MemAvailable"],
            "cgroup_available_bytes": limits, "rss_bytes": status.get("VmRSS"),
            "high_water_rss_bytes": max(status.get("VmHWM", 0),
                                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)}


def estimate_memory(node_count, edge_count, margin_bytes=2 * GIB):
    if not (0 < node_count <= 2 ** 32 - 1 and 0 <= edge_count <= 2 ** 32 - 1):
        raise ValueError("Native graph dimensions are outside uint32 domain")
    values = {"input_arrays_bytes": 32 * edge_count,
              "native_persistent_index_bytes": 56 * node_count + 16 + 8 * edge_count,
              "native_constructor_offset_copies_bytes": 16 * (node_count + 1),
              "one_full_calibration_output_bytes": 24 * node_count,
              "queue_arrow_python_margin_bytes": margin_bytes}
    # Conservative sum: constructor copies and calibration outputs are not live together.
    values["planned_peak_increment_bytes"] = sum(values.values())
    return values


def require_memory(plan, snapshot=None):
    snapshot = memory_snapshot() if snapshot is None else snapshot
    if snapshot["available_bytes"] < plan["planned_peak_increment_bytes"]:
        raise MemoryError("Insufficient available memory for conservative native-load preflight")
    return snapshot


@dataclass
class ArrayOwner:
    """Only pointer-owning arrays needed by unchanged microplan.ExactRouter."""
    node_count: int
    edge_count: int
    source: np.ndarray
    target: np.ndarray
    weights: dict[str, np.ndarray]

    @property
    def array_bytes(self):
        return self.source.nbytes + self.target.nbytes + sum(a.nbytes for a in self.weights.values())


def _column(batch, name, expected_type):
    array = batch.column(batch.schema.get_field_index(name))
    if array.type != expected_type or array.null_count:
        raise ValueError(f"{name} must be nonnull {expected_type}")
    return array.to_numpy(zero_copy_only=True)


def load_native_arrays(nodes_path, edges_path, node_count, edge_count, batch_size=65536):
    """Project five edge columns, never sort/rebuild adjacency or construct Igraph."""
    if batch_size <= 0:
        raise ValueError("Positive batch size required")
    estimate_memory(node_count, edge_count)
    nodes = pq.ParquetFile(nodes_path)
    edges = pq.ParquetFile(edges_path)
    if nodes.metadata.num_rows != node_count or edges.metadata.num_rows != edge_count:
        raise ValueError("Parquet row counts disagree with frozen graph metadata")
    offset = 0
    for batch in nodes.iter_batches(batch_size=batch_size, columns=["node_id"], use_threads=False):
        ids = _column(batch, "node_id", pa.int64())
        if not np.array_equal(ids, np.arange(offset, offset + len(ids), dtype=np.int64)):
            raise ValueError("Node IDs must be contiguous in original table order")
        offset += len(ids)
    source, target = np.empty(edge_count, np.int64), np.empty(edge_count, np.int64)
    cost, length = np.empty(edge_count, np.float64), np.empty(edge_count, np.float64)
    offset = 0
    columns = ["edge_id", "source", "target", "length_m", "travel_time_s"]
    for batch in edges.iter_batches(batch_size=batch_size, columns=columns, use_threads=False):
        ids = _column(batch, "edge_id", pa.int64())
        if not np.array_equal(ids, np.arange(offset, offset + len(ids), dtype=np.int64)):
            raise ValueError("Edge IDs must be contiguous in original table order")
        for name, dest in [("source", source), ("target", target)]:
            values = _column(batch, name, pa.int64())
            if len(values) and (values.min() < 0 or values.max() >= node_count):
                raise ValueError(f"{name} outside node domain")
            dest[offset:offset + len(values)] = values
        for name, dest in [("travel_time_s", cost), ("length_m", length)]:
            values = _column(batch, name, pa.float64())
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError(f"{name} must contain finite nonnegative binary64 values")
            dest[offset:offset + len(values)] = values
        offset += len(ids)
    if offset != edge_count:
        raise ValueError("Incomplete edge stream")
    return ArrayOwner(node_count, edge_count, source, target,
                      {"travel_time": cost, "distance": length})


def anchor(node):
    if type(node) is not int or node < 0:
        raise ValueError("Road anchor must be a nonnegative integer node ID")
    return f"road:{node}"


def selected_requests(manifest, catalog, ods):
    """Use frozen population only; no weights or router output is consulted."""
    sites = {s["site_id"]: s for s in catalog["sites"]}
    if len(sites) != len(catalog["sites"]):
        raise ValueError("Duplicate Site identity")
    by_od = {o["instance_id"]: o for o in ods}
    requests, pools = {}, []
    for pool in manifest["pools"]:
        od = by_od[pool["instance_id"]]
        if pool["selected_site_ids"] != [s["site_id"] for s in pool["chosen"]]:
            raise ValueError("Selected Site order disagrees with chosen rows")
        ids = pool["selected_site_ids"]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate selected Site")
        nodes = sorted({od["origin_node"], od["destination_node"], *[sites[s]["access_node"] for s in ids]})
        entries = []
        for chosen in pool["chosen"]:
            site = sites[chosen["site_id"]]
            if chosen["access_node"] != site["access_node"]:
                raise ValueError("Chosen anchor differs from frozen Site catalog")
            effects = chosen["eligible_actions"]
            if not effects or len(effects) != len(set(effects)) or any(
                e not in ("C", "S", "CS") or not site[f"can_{e}"] for e in effects
            ):
                raise ValueError("Chosen eligible actions contradict static capability")
            if site["access_node"] == od["destination_node"]:
                raise ValueError("Terminal-anchor Site escaped frozen selector")
            entries.append({"site_id": site["site_id"], "anchor_id": anchor(site["access_node"]),
                            "effects": effects})
        for source in nodes:
            requests.setdefault(source, set()).update(nodes)
        pools.append({"pool_id": pool["pool_id"], "instance_id": pool["instance_id"],
                      "origin_anchor": anchor(od["origin_node"]),
                      "destination_anchor": anchor(od["destination_node"]),
                      "anchors": [anchor(n) for n in nodes], "nodes": nodes, "sites": entries})
    return {s: sorted(ts) for s, ts in sorted(requests.items())}, pools


def leg_row(source, target, cost, length):
    cost, length = float(cost), float(length)
    row = {"source_anchor": anchor(source), "target_anchor": anchor(target),
           "label_direction": "identity" if source == target else "forward_from_source"}
    if math.isinf(cost) and cost > 0 and math.isinf(length) and length > 0:
        if source == target:
            raise ValueError("Identity cannot be unreachable")
        row.update(reachable=False, time_s=None, actual_length_m=None)
    elif math.isfinite(cost) and math.isfinite(length):
        if source == target and (cost != 0 or length != 0):
            raise ValueError("Identity must have zero native labels")
        if source != target and (cost <= 0 or length <= 0):
            raise ValueError("Distinct-anchor nonpositive native leg violates immutable contract")
        row.update(reachable=True, time_s=encode_binary64(cost), actual_length_m=encode_binary64(length))
    else:
        raise ValueError("Native time/actual-length labels disagree on finite reachability")
    return row


def calibrate(router, requests, source_count=3):
    sources = list(requests)
    if not sources or source_count < 1:
        raise ValueError("Nonempty calibration required")
    # Source selection depends only on frozen node IDs, never on routing outcomes.
    indices = sorted(set(np.linspace(0, len(sources) - 1, min(source_count, len(sources)), dtype=int)))
    reports = []
    for index in indices:
        source = sources[index]
        targets = sorted(set([source, 0, router.graph.node_count - 1, *requests[source]]))
        started = time.perf_counter()
        costs, lengths, parents = router.full(source, reverse=False)
        expected_costs, expected_lengths = costs[targets].copy(), lengths[targets].copy()
        del costs, lengths, parents
        pair_costs, pair_lengths = router.pairs(np.full(len(targets), source, dtype=np.int64),
                                               targets, MAX_FINITE)
        if not np.array_equal(pair_costs.view(np.uint64), expected_costs.view(np.uint64)) or not np.array_equal(
            pair_lengths.view(np.uint64), expected_lengths.view(np.uint64)
        ):
            raise ValueError(f"Real pair/full binary64 calibration mismatch for source {source}")
        reports.append({"source": source, "targets": targets, "pair_count": len(targets),
                        "time_and_actual_length_bitwise_equal": True,
                        "elapsed_seconds": time.perf_counter() - started,
                        "memory": memory_snapshot(),
                        "labels": [leg_row(source, t, c, l) for t, c, l in
                                   zip(targets, pair_costs, pair_lengths)]})
    return {"passed": True, "direction": "forward_from_source", "cutoff_hex": MAX_FINITE.hex(),
            "cutoff_meaning": "largest finite binary64; no finite time label excluded",
            "pair_count": sum(r["pair_count"] for r in reports), "sources": reports}


def export_selected_pairs(router, requests, checkpoint_path=None):
    """One native source at a time; keep only requested ordered pairs."""
    result, timings = {}, []
    stream = Path(checkpoint_path).open("w") if checkpoint_path else None
    try:
        for index, (source, targets) in enumerate(requests.items(), 1):
            started = time.perf_counter()
            costs, lengths = router.pairs(np.full(len(targets), source, dtype=np.int64), targets, MAX_FINITE)
            rows = [leg_row(source, t, c, l) for t, c, l in zip(targets, costs, lengths)]
            result.update({(source, t): row for t, row in zip(targets, rows)})
            timing = {"source": source, "pair_count": len(rows), "elapsed_seconds": time.perf_counter()-started,
                      "memory": memory_snapshot()}
            timings.append(timing)
            if stream:
                stream.write(json.dumps({"timing": timing, "legs": rows}, allow_nan=False) + "\n")
                stream.flush()
            print(json.dumps({"event": "source_exported", "index": index, "sources": len(requests), **timing}), flush=True)
    finally:
        if stream:
            stream.close()
    return result, timings


def export_restrictions(tree_path, hierarchy_sha256, selection_sha256, pools, output):
    """Keep every original Region, even when its selected membership is empty."""
    data = Path(tree_path).read_bytes()
    files = {}
    for pool in pools:
        restriction = restrict_frozen_tree(data, hierarchy_sha256,
                                           [s["site_id"] for s in pool["sites"]])
        payload = {"schema": "hiroute.original_tree_restriction.v1", **asdict(restriction),
                   "selection_certificate_sha256": selection_sha256, "pool_id": pool["pool_id"]}
        path = Path(output) / "restrictions" / (pool["pool_id"] + ".json")
        digest = write_json(path, payload)
        files[pool["pool_id"]] = {"path": "restrictions/" + path.name, "sha256": digest,
                                  "region_count": len(restriction.regions),
                                  "empty_region_count": sum(not r.site_ids for r in restriction.regions),
                                  "original_sha256": hierarchy_sha256}
    return files


def verify_files(entries):
    verified = []
    for entry in entries:
        path = Path(entry.get("local_path", entry.get("path", "")))
        digest = sha256(path)
        expected = entry.get("sha256", entry.get("expected_sha256"))
        if digest != expected or ("size_bytes" in entry and path.stat().st_size != entry["size_bytes"]):
            raise ValueError(f"Frozen source hash/size mismatch: {path}")
        verified.append({"path": str(path), "sha256": digest, "size_bytes": path.stat().st_size})
    return verified


def validate_physical_states(states):
    expected = {"consumption_kwh_per_m": "1/6250", "capacity_kwh": "60", "terminal_reserve_kwh": "6",
                "energy_floor_kwh": "0", "overhead_s": "300", "stop_penalty_s": "600", "start_time_s": "0"}
    curve = {"energy_breakpoints_kwh": ["0", "30", "48", "60"],
             "slopes_s_per_kwh": ["36", "60", "120"], "intercepts_s": ["0", "-720", "-3600"],
             "label": "canonical_synthetic_PWA_cumulative"}
    for state in states:
        if any(state.get(k) != v for k, v in expected.items()) or state["charging_primitive"] != curve:
            raise ValueError("Unfrozen physical constants or canonical curve")
        if state["schedule"] is not None and state["schedule"]["duration_s"] != "2700":
            raise ValueError("Unexpected scheduled duration")


def resolved_states(states, ods, rows, table_files):
    validate_physical_states(states)
    by_od = {o["instance_id"]: o for o in ods}
    result = []
    for original in states:
        state = json.loads(json.dumps(original))
        od = by_od[state["instance_id"]]
        baseline = rows[od["origin_node"], od["destination_node"]]
        if not baseline["reachable"]:
            raise ValueError("Frozen OD has no accepted finite baseline")
        ratio = baseline["time_s"]["ratio"]
        exact_time = Fraction(int(ratio[0]), int(ratio[1]))
        state["accepted_baseline_time_s"] = baseline["time_s"]
        state["accepted_baseline_actual_length_m"] = baseline["actual_length_m"]
        state["immutable_direct_leg_table_status"] = "exported_hash_verified_preparation_only"
        state["immutable_direct_leg_table"] = table_files[state["pool_id"]]
        if state["schedule"] is not None:
            schedule = state["schedule"]
            schedule.pop("pending_reason", None)
            schedule.update(baseline_time_s=str(exact_time), window_start_s=str(Fraction(2, 5)*exact_time),
                            window_end_s=str(Fraction(7, 10)*exact_time),
                            baseline_binary64=baseline["time_s"])
        result.append(state)
    return result


def run(args):
    started = time.perf_counter()
    root, out, selection = Path(args.repo).resolve(), Path(args.output).resolve(), Path(args.selection).resolve()
    out.mkdir(parents=True, exist_ok=True)
    status = {"started_utc": utc(), "mode": args.mode, "no_optimization": True}
    write_json(out / "status.json", status)
    verification = read_json(args.verification)
    if verification["verified_count"] != 6 or any(x["status"] != "verified" for x in verification["files"]):
        raise ValueError("All six source inputs must be verified before preparation")
    source_verification = verify_files(verification["files"])
    selection_path = selection / "selection_manifest.json"
    if sha256(selection_path) != args.selection_sha256:
        raise ValueError("Frozen selection manifest hash mismatch")
    selection_verification = verify_files(read_json(selection / "output_hashes.json")["files"])
    manifest = read_json(selection_path)
    freeze = read_json(selection / "preselection_freeze.json")
    if sha256(selection / "preselection_freeze.json") != manifest["preselection_freeze_sha256"]:
        raise ValueError("Selection prefreeze hash mismatch")
    verify_files(freeze["policy_files"] + freeze["reference_files"])
    catalog, ods = read_json(selection / "chosen_site_catalog.json"), read_json(selection / "od_anchors.json")
    states = read_json(selection / "query_states.json")
    validate_physical_states(states)
    requests, pools = selected_requests(manifest, catalog, ods)
    source_files = {e["name"]: e for e in verification["files"]}
    metadata = read_json(source_files["metadata.json"]["local_path"])
    n, m = metadata["node_count"], metadata["edge_count"]
    if any(s >= n or any(t >= n for t in ts) for s, ts in requests.items()):
        raise ValueError("Selected road anchor outside graph")
    plan = estimate_memory(n, m)
    before = require_memory(plan)
    router_paths = ["src/microplan/routing.py", "src/microplan/routing.cpp", "configs/microplan.yaml"]
    router_hashes = {path: sha256(root / path) for path in router_paths}
    source_hashes = {e["repository_target_path"]: e["sha256"] for e in verification["files"]}
    source_hashes.update(router_hashes)
    tree_references = [e for e in freeze["reference_files"] if Path(e["path"]).name == "hierarchy.json"]
    if len(tree_references) != 1 or tree_references[0]["sha256"] != manifest["original_hierarchy_sha256"]:
        raise ValueError("Original hierarchy reference missing or inconsistent")
    tree_path = tree_references[0]["path"]
    source_hashes["results/milestone_4r_b1/hierarchy.json"] = manifest["original_hierarchy_sha256"]
    restrictions = export_restrictions(tree_path, manifest["original_hierarchy_sha256"],
                                       args.selection_sha256, pools, out)
    for e in selection_verification:
        source_hashes["acceptance_populations/stage_c/concrete_selection/" + Path(e["path"]).name] = e["sha256"]
    source_hashes["acceptance_populations/stage_c/concrete_selection/selection_manifest.json"] = args.selection_sha256
    preflight = {"passed": True, "created_utc": utc(), "node_count": n, "edge_count": m,
                 "memory_plan": plan, "memory": before, "source_verification": source_verification,
                 "selection_verification": selection_verification, "router_source_sha256": router_hashes,
                 "selection_certificate_sha256": args.selection_sha256,
                 "unique_source_count": len(requests), "requested_pair_count": sum(map(len, requests.values())),
                 "pool_count": len(pools), "state_count": len(states), "direction_policy": "forward_per_source_v1",
                 "cutoff_hex": MAX_FINITE.hex(), "no_optimization": True,
                 "script_sha256": sha256(__file__), "runtime": {"python": sys.version, "numpy": np.__version__, "pyarrow": pa.__version__}}
    write_json(out / "preflight.json", preflight)
    write_json(out / "request_plan.json", {"sources": [{"source": s, "targets": t} for s, t in requests.items()], "pools": pools})
    print(json.dumps({"event": "preflight_passed", "memory": before, "memory_plan": plan,
                      "sources": len(requests), "pairs": sum(map(len, requests.values()))}), flush=True)
    if args.mode == "preflight":
        return preflight
    # Recheck immediately before allocation, after all selection/source parsing.
    require_memory(plan)
    load_started = time.perf_counter()
    graph = load_native_arrays(source_files["nodes.parquet"]["local_path"], source_files["edges.parquet"]["local_path"], n, m, args.batch_size)
    load_report = {"elapsed_seconds": time.perf_counter() - load_started, "array_bytes": graph.array_bytes,
                   "original_order_preserved": True, "node_ids_contiguous": True, "edge_ids_contiguous": True,
                   "endpoint_domain_checked": True, "finite_nonnegative_weights_checked": True, "memory": memory_snapshot()}
    write_json(out / "array_load.json", load_report)
    print(json.dumps({"event": "arrays_loaded", **load_report}), flush=True)
    config = yaml.safe_load((root / "configs/microplan.yaml").read_text())
    native_started = time.perf_counter()
    router = ExactRouter(graph, config, out / "native_cache")
    try:
        native_report = {"elapsed_seconds": time.perf_counter()-native_started, "memory": memory_snapshot(),
                         "provenance": router.provenance, "binary_sha256": sha256(out / "native_cache/routing.so"),
                         "source_sha256": router_hashes,
                         "compiler_executable": str(Path(shutil.which(config["compiler"])).resolve()),
                         "compiler_executable_sha256": sha256(shutil.which(config["compiler"])),
                         "configuration": {"compiler": config["compiler"], "compiler_flags": config["compiler_flags"]}}
        write_json(out / "native_router.json", native_report)
        calibration = calibrate(router, requests, args.calibration_sources)
        calibration.update(native_router_sha256=sha256(out / "native_router.json"),
                           graph_edges_sha256=source_files["edges.parquet"]["sha256"],
                           graph_nodes_sha256=source_files["nodes.parquet"]["sha256"])
        write_json(out / "real_pair_full_calibration.json", calibration)
        print(json.dumps({"event": "real_calibration_passed", "pair_count": calibration["pair_count"], "memory": memory_snapshot()}), flush=True)
        if args.mode == "calibrate":
            return calibration
        rows, timings = export_selected_pairs(router, requests, out / "selected_source_rows.jsonl")
        table_files = {}
        backend = {"name": "accepted_microplan_native_ExactRouter", "tie_policy": TIE_POLICY,
                   "direction_policy": "forward_per_source_v1", "source_sha256": router_hashes,
                   "compiler_provenance": router.provenance, "binary_sha256": native_report["binary_sha256"],
                   "pair_cutoff_hex": MAX_FINITE.hex(), "real_calibration_sha256": sha256(out / "real_pair_full_calibration.json")}
        for pool in pools:
            payload = {"schema": SCHEMA, "numerical_contract": NUMERICS, "anchors": pool["anchors"],
                       "origin_anchor": pool["origin_anchor"], "destination_anchor": pool["destination_anchor"],
                       "sites": pool["sites"], "backend": backend, "source_sha256": source_hashes,
                       "selection_certificate_sha256": args.selection_sha256,
                       "hierarchy_sha256": manifest["original_hierarchy_sha256"],
                       "legs": [rows[s, t] for s in pool["nodes"] for t in pool["nodes"]]}
            path = out / "tables" / (pool["pool_id"] + ".json")
            digest = write_json(path, payload)
            parsed = ImmutableLegTable.from_bytes(path.read_bytes(), digest)
            if len(parsed.sites) != len(pool["sites"]):
                raise ValueError("Site identity loss in table")
            table_files[pool["pool_id"]] = {"path": "tables/" + path.name, "sha256": digest,
                                           "anchor_count": len(parsed.anchors), "site_count": len(parsed.sites),
                                           "ordered_pair_count": len(parsed.legs)}
        resolved = resolved_states(states, ods, rows, table_files)
        for state in resolved:
            state["original_tree_restriction"] = restrictions[state["pool_id"]]
        write_json(out / "query_states_resolved.json", resolved)
        # Detect mutation during extraction. Hash-check never implies route optimality.
        verify_files(verification["files"])
        verify_files(read_json(selection / "output_hashes.json")["files"])
        if sha256(selection_path) != args.selection_sha256 or any(sha256(root / p) != h for p, h in router_hashes.items()):
            raise ValueError("Source or router changed during export")
        report = {"status": "export_complete_preparation_only", "no_optimization": True, "completed_utc": utc(),
                  "elapsed_seconds": time.perf_counter()-started, "memory": memory_snapshot(),
                  "preflight_sha256": sha256(out / "preflight.json"), "native_router_sha256": sha256(out / "native_router.json"),
                  "calibration_sha256": sha256(out / "real_pair_full_calibration.json"),
                  "selection_certificate_sha256": args.selection_sha256,
                  "hierarchy_sha256": manifest["original_hierarchy_sha256"], "source_count": len(requests),
                  "requested_pair_count": len(rows), "unreachable_pair_count": sum(not r["reachable"] for r in rows.values()),
                  "identity_pair_count": sum(s == t for s, t in rows), "tables": table_files,
                  "original_hierarchy_path": tree_path, "restrictions": restrictions,
                  "query_states_resolved_sha256": sha256(out / "query_states_resolved.json"), "source_timings": timings,
                  "limitations": ["Preparation only; no REF, FLAT, HIER or Stage C optimization has run.",
                                  "Frozen binary64 selected totals are exact rational constants, not exact edge-sum reals or a metric guarantee.",
                                  "Real pair/full calibration establishes equality only for its reported subset.",
                                  "Canonical rational physical model is explicitly frozen; no bitwise old evaluator equivalence is claimed.",
                                  "Leg export records selected totals and accepted router provenance; no full road-path edge witness is serialized."]}
        write_json(out / "export_manifest.json", report)
        write_json(out / "status.json", {**status, "status": report["status"], "completed_utc": utc()})
        return report
    finally:
        router.close()
        del graph
        gc.collect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--verification", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--selection-sha256", default=DEFAULT_SELECTION_SHA256)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=("preflight", "calibrate", "export"), default="preflight")
    parser.add_argument("--batch-size", type=int, default=65536)
    parser.add_argument("--calibration-sources", type=int, default=3)
    args = parser.parse_args()
    try:
        result = run(args)
        print(json.dumps({"event": "complete", "mode": args.mode, "output": str(Path(args.output).resolve()),
                          "status": result.get("status", "passed")}), flush=True)
    except Exception as error:
        write_json(Path(args.output) / "failure.json", {"utc": utc(), "error_type": type(error).__name__, "error": str(error),
                                                        "no_optimization": True, "memory": memory_snapshot()})
        raise


if __name__ == "__main__":
    main()
