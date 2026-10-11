"""Serial, durable M5-D main denominator with a hard charged-CPU stop."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from timecut5.systemd_supervisor import run_m5d_phase


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".next")
    with temporary.open("x") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def completed_pair_agrees(flat, hier):
    """Compare exact coordinates only when both solver rows completed."""
    if "exact_outcome" not in flat or "exact_outcome" not in hier:
        return None
    return (flat.get("seed_j"), flat.get("certified_depth"), flat.get("prewarm_sha256"),
            flat["exact_outcome"]) == (hier.get("seed_j"), hier.get("certified_depth"),
            hier.get("prewarm_sha256"), hier["exact_outcome"])


def run(source: Path, graph_dir: Path, pool_path: Path, queries_path: Path,
        phase_path: Path, output: Path):
    data = phase_path.read_bytes()
    phase_sha = hashlib.sha256(data).hexdigest()
    phase = json.loads(data)
    if (phase.get("schema") != "hiroute.m5d.frozen_main_phase.v1" or
            len(phase.get("rows", [])) != 192 or
            phase["wall_seconds"] != 600 or
            phase["memory_bytes"] != 8 * 1024**3 or
            phase["main_cpu_seconds_ceiling"] != 117000 or
            phase["max_concurrent_rows"] != 2 or
            phase["initial_concurrency"] != 1):
        raise ValueError("Complete frozen main phase and denominator required")
    state_path = output / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_bytes())
        if state["phase_sha256"] != phase_sha:
            raise ValueError("Cannot resume against changed frozen phase")
    else:
        state = {"schema": "hiroute.m5d.main_batch_state.v1",
            "phase_sha256": phase_sha, "charged_cpu_ns": 0, "rows": {},
            "stopped": False}
        save(state_path, state)
    if state["stopped"]:
        return state
    for row in phase["rows"]:
        row_id = row["row_id"]
        if row_id in state["rows"]:
            continue
        # The 10-second per-row guard covers cgroup CPU above a nominal 600s
        # wall limit. The 32.5-hour main allocation includes 0.5 h margin.
        remaining = 117000 - state["charged_cpu_ns"] / 1e9
        total_remaining = (48 - phase["conservative_cpu_hours_before_main"])
        total_remaining = total_remaining * 3600 - state["charged_cpu_ns"] / 1e9
        if remaining < 610 or total_remaining < 610 + phase["outside_main_reserve_seconds"]:
            for pending in phase["rows"]:
                state["rows"].setdefault(pending["row_id"],
                    {"status": "budget_exhausted_unrun", "denominator_included": True})
            state["stopped"] = True
            save(state_path, state)
            return state
        row_out = output / row_id
        if row_out.exists():
            raise ValueError("Existing incomplete row directory requires manual review")
        row_out.mkdir()
        command = ("/home/dy/miniconda3/envs/hiroute/bin/python",
            str(source / "scripts/m5d_main_row.py"), str(source), str(graph_dir),
            str(pool_path), str(queries_path), str(phase_path), phase_sha,
            row_id, str(row_out))
        try:
            receipt = run_m5d_phase(command, cwd=source, output_dir=row_out,
                wall_seconds=600, memory_bytes=8 * 1024**3, phase="main",
                frozen_main_phase=(data, phase_sha),
                remaining_cpu_seconds=int(remaining), pythonpath=source / "src")
        except Exception:
            state["rows"][row_id] = {"status": "supervisor_failed_cpu_unknown",
                "denominator_included": True}
            state["stopped"] = True
            save(state_path, state)
            raise
        state["charged_cpu_ns"] += receipt.cpu_usage_ns
        if receipt.cpu_quota_percent != 100 or receipt.cpu_usage_ns > 610 * 10**9:
            state["rows"][row_id] = {"status": "verification_failed_cpu_limit",
                "denominator_included": True, "receipt_path": receipt.receipt_path,
                "cgroup_cpu_usage_ns": receipt.cpu_usage_ns}
            state["stopped"] = True
            for pending in phase["rows"]:
                state["rows"].setdefault(pending["row_id"],
                    {"status": "verification_blocked_unrun", "denominator_included": True})
            save(state_path, state)
            return state
        if receipt.result == "success" and receipt.exit_status == 0:
            status_file = row_out / "status.json"
            row_status = (json.loads(status_file.read_bytes()) if status_file.exists()
                          else {"status": "verification_failed_missing_status"})
            row_status["denominator_included"] = True
        elif receipt.result == "timeout":
            row_status = {"status": "time_limit", "denominator_included": True}
        elif receipt.result in ("oom-kill", "memory-limit"):
            row_status = {"status": "memory_limit", "denominator_included": True}
        else:
            row_status = {"status": "verification_failed_process_exit",
                "denominator_included": True, "exit_status": receipt.exit_status,
                "unit_result": receipt.result}
        row_status["receipt_path"] = receipt.receipt_path
        row_status["cgroup_cpu_usage_ns"] = receipt.cpu_usage_ns
        state["rows"][row_id] = row_status
        if row["method"] == "hier":
            flat_id = row_id.removesuffix("_hier") + "_flat"
            flat_status = state["rows"].get(flat_id, {})
            agreement = completed_pair_agrees(flat_status, row_status)
            if agreement is False:
                state["rows"][flat_id]["status"] = "verification_failed_method_disagreement"
                row_status["status"] = "verification_failed_method_disagreement"
        if row_status["status"].startswith("verification_failed"):
            state["stopped"] = True
            for pending in phase["rows"]:
                state["rows"].setdefault(pending["row_id"],
                    {"status": "verification_blocked_unrun", "denominator_included": True})
        save(state_path, state)
        if state["stopped"]:
            return state
    state["stopped"] = True
    save(state_path, state)
    return state


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:7]))
