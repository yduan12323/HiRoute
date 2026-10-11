"""Freeze reviewed M5-D main rows, source closure and global budget."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(root: Path, candidate_path: Path, queries_path: Path,
        pool_path: Path, full_path: Path, charged_before: float, out: Path):
    candidate, queries, pools, full = (json.loads(path.read_bytes()) for path in
        (candidate_path, queries_path, pool_path, full_path))
    if (candidate["query_count"] != queries["query_count"] != 48 or
            queries["binding_count"] != 96 or len(candidate["rows"]) != 192 or
            full["target_query_ids"] != candidate["true_full_universe_query_ids"] or
            full["source_sha256"]["queries"] != sha(queries_path) or
            full["source_sha256"]["pools"] != sha(pool_path) or
            pools["slate_sha256"] != candidate["input_sha256"]["slate"]):
        raise ValueError("Fixed main query, candidate or full-universe closure differs")
    query_by_id = {row["query_id"]: row for row in queries["queries"]}
    if (len(query_by_id) != 48 or
            [row["query_id"] for row in queries["queries"]] !=
            [row["query_id"] for row in candidate["query_order"]]):
        raise ValueError("Fixed query ID/order differs")
    for row in candidate["rows"]:
        if (row["query_id"] not in query_by_id or
                str(row["candidate_prefix_count"]) not in query_by_id[row["query_id"]]["bindings"] or
                row["method"] not in ("flat", "hier")):
            raise ValueError("Main method row is not bound to a complete query")
    for query_id in full["target_query_ids"]:
        od = query_by_id[query_id]["od_id"]
        if (full["universes_by_od"][od]["site_count"] !=
                candidate["true_full_universe_candidate_counts"][query_id] or
                full["universes_by_od"][od]["site_count"] <= 128):
            raise ValueError("Full eligible Site universe is a subset or differs")
    source_paths = (sorted((root / "src/timecut5").glob("*.py")) +
        sorted((root / "validation/reference5").glob("*.py")) +
        [root / name for name in ("src/microplan/routing.py",
            "src/microplan/routing.cpp", "scripts/m5d_main_row.py",
            "scripts/m5d_main_batch.py", "scripts/m5d_build_main_queries.py",
            "scripts/m5d_full_universe_inputs.py",
            "scripts/m5d_one_query_runner.py")])
    source_hashes = {str(path.relative_to(root)): sha(path) for path in source_paths}
    if any(not path.exists() for path in source_paths) or len(source_hashes) != len(source_paths):
        raise ValueError("Incomplete source closure")
    if type(charged_before) is not float or not 0 <= charged_before < 48:
        raise ValueError("Measured conservative pre-main CPU debit required")
    outside_seconds = round((48 - charged_before - 32.5) * 3600, 6)
    if outside_seconds < 0:
        raise ValueError("Main allocation exceeds aggregate CPU ceiling")
    result = {"schema": "hiroute.m5d.frozen_main_phase.v1",
        "status": "frozen_exact_192_row_denominator",
        "source_commit_at_freeze": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_sha256": source_hashes,
        "input_sha256": {"queries": sha(queries_path), "pools": sha(pool_path),
            "full_universes": sha(full_path),
            "slate": candidate["input_sha256"]["slate"],
            "graph_nodes": queries["source_sha256"]["graph_nodes"],
            "graph_edges": queries["source_sha256"]["graph_edges"],
            "graph_metadata": queries["source_sha256"]["graph_metadata"],
            "hierarchy": queries["source_sha256"]["hierarchy"]},
        "query_count": 48, "binding_count": 96,
        "rows": [{k: row[k] for k in ("row_id", "query_id",
            "candidate_prefix_count", "method")} for row in candidate["rows"]],
        "six_full_universe_query_ids": full["target_query_ids"],
        "six_full_universe_site_hashes": {query_id:
            full["universes_by_od"][query_by_id[query_id]["od_id"]]["site_rows_sha256"]
            for query_id in full["target_query_ids"]},
        "full_universe_status": "frozen_inputs_unrun_separate_budget",
        "wall_seconds": 600, "memory_bytes": 8 * 1024**3,
        "max_concurrent_rows": 2, "initial_concurrency": 1,
        "main_cpu_seconds_ceiling": 117000,
        "conservative_cpu_hours_before_main": charged_before,
        "outside_main_reserve_seconds": outside_seconds,
        "timeout_policy": "time_limit_censored_keep_denominator",
        "memory_policy": "memory_limit_censored_keep_denominator",
        "failed_seed_policy": "incumbent_search_failed_skip_solver_keep_both_method_rows",
        "budget_stop_policy": "budget_exhausted_unrun_keep_denominator",
        "cache_policy": "empty_each_method_before_seed_identical_deterministic_prewarm_digest",
        "unit_scope": "graph_load_route_seed_landmark_search_independent_terminal_replay",
        "holdout": "excluded"}
    with out.open("x") as stream:
        json.dump(result, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:6]),
        float(sys.argv[6]), Path(sys.argv[7]))
