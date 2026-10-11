"""Produce the fixed M5-D main denominator without running routes or solvers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def build(root: Path, pool_path: Path):
    slate_path = root / "results/milestone_5d/continuation_20261011/fixed_12od_candidate_slate.json"
    slate, pools = json.loads(slate_path.read_bytes()), json.loads(pool_path.read_bytes())
    if (len(slate["od"]) != 12 or len(slate["queries"]) != 48 or
            pools["slate_sha256"] != sha(slate_path) or
            [row["od_id"] for row in pools["pools"]] !=
            [row["od_id"] for row in slate["od"]]):
        raise ValueError("Fixed 12-OD slate or pool order differs")
    pool_by_od = {row["od_id"]: row for row in pools["pools"]}
    queries, rows = [], []
    for index, source in enumerate(slate["queries"]):
        od, soc, activity = source["od_id"], source["soc"], source["activity"]
        query_id = f"{od}_{activity}_soc{soc.replace('/', '_')}"
        pool = pool_by_od[od]
        if (len(pool["sites"]) != 128 or pool["prefix_sizes"] != [8, 16, 32, 128] or
                pool["eligible_capable_site_count"] < 128):
            raise ValueError("Frozen nested candidate universe differs")
        queries.append({"query_id": query_id, "slate_index": index,
            "od_id": od, "soc": soc, "activity": activity,
            "initial_energy_kwh": source["initial_energy_kwh"],
            "eligible_capable_site_count": pool["eligible_capable_site_count"],
            "schedule_window_rule": "exact_[2/5,7/10]_of_direct_binary64_baseline"
                if activity == "energy_and_scheduled" else None})
        for size in (32, 128):
            for method in ("flat", "hier"):
                rows.append({"row_id": f"{query_id}_n{size}_{method}",
                    "query_id": query_id, "candidate_prefix_count": size,
                    "method": method, "status": "not_started_preregistration",
                    "denominator_included": True})
    if len({row["row_id"] for row in rows}) != 192:
        raise ValueError("Main comparison denominator differs")
    source_files = ["src/timecut5/sparse_seed.py", "src/timecut5/road_provider.py",
        "src/timecut5/real_adapter.py", "src/timecut5/bounded.py",
        "src/timecut5/hierarchy.py", "src/timecut5/live_replay.py",
        "src/timecut5/systemd_supervisor.py", "scripts/m5d_sparse_od02_n8.py",
        "scripts/m5d_one_query_runner.py", "src/microplan/routing.py",
        "src/microplan/routing.cpp", "validation/reference5/model.py"]
    return {"schema": "hiroute.m5d.main_preregistration_review_candidate.v1",
        "status": "review_candidate_not_executable_do_not_launch",
        "source_commit_at_generation": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_sha256": {name: sha(root / name) for name in source_files},
        "input_sha256": {"slate": sha(slate_path), "pools": sha(pool_path),
            "graph_nodes": "7424eea357d98b54c4652062440a1d287d509f1b7250f7eabbcc5185cde923b5",
            "graph_edges": "37f0f75e71de97e0b045d53af23b181e034e6c3262a1a4079d582f37471bb1b8",
            "graph_metadata": "268d09781c5e51a486c0d6574b7439e964b6293aef2df07f64cc5772c6dfaadd",
            "landmark_certificate": "d1992e7edd1a7e333695578b8979d6c9ee9ee7e44e6fba0ec3899f2075c56e4c"},
        "query_count": 48, "method_row_count": 192,
        "query_order": queries, "rows": rows,
        "true_full_universe_query_ids": [q["query_id"] for q in queries[:6]],
        "true_full_universe_candidate_counts": {q["query_id"]:
            q["eligible_capable_site_count"] for q in queries[:6]},
        "limits": {"main_wall_seconds_per_row": 600,
            "main_memory_bytes_per_row": 8 * 1024**3,
            "max_concurrent_rows": 2, "aggregate_memory_bytes": 16 * 1024**3,
            "concurrency_start": 1, "total_cpu_hours": 48,
            "conservative_cpu_hours_charged_before_main_rounded_up": 10.515432,
            "main_phase_cpu_hours_ceiling": 32.5,
            "input_qualification_reserve_cpu_hours": 2.5,
            "full_universe_and_host_reserve_cpu_hours": 1.48887,
            "functionality_remaining_reserve_cpu_hours": 0.838884,
            "optimization_remaining_reserve_cpu_hours": 0.156814},
        "execution_contract": {"unit_scope": "whole_source_load_route_seed_search_witness",
            "seed": "fresh_same_domain_independent_replay_each_method",
            "routing_cache": "empty_before_seed_each_method_then_identical_deterministic_seed_prewarm",
            "method_order": ["flat", "hier"],
            "timeout_memory_failure": "censored_denominator_row",
            "failed_seed": "incumbent_search_failed_skip_solver_keep_both_method_rows",
            "budget_stop": "mark_unstarted_rows_budget_exhausted_unrun_no_replacement",
            "full_universe": "separate_complete_eligible_site_set_not_128_prefix",
            "holdout": "excluded"},
        "unmet_freeze_gates": ["construct_and_hash_all_48_exact_query_payloads",
            "implement_one_whole-unit_real_row_driver_for_both_methods",
            "independent_full-depth_terminal_replay_on_real_row",
            "freeze_and_hash_main_phase_manifest_with_cpu_headroom_check",
            "review_six_full_universe_input_construction"]}


if __name__ == "__main__":
    root, pool_path, output = (Path(value) for value in sys.argv[1:4])
    with output.open("x") as stream:
        json.dump(build(root, pool_path), stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
