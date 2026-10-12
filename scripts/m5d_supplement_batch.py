"""Serial supervisor for a separately approved frozen M5-D supplement."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from timecut5.systemd_supervisor import run_supervised


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".next")
    with temporary.open("x") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def last_phase(row_out):
    path = row_out / "phase.jsonl"
    if not path.exists():
        return None
    lines = path.read_text().splitlines()
    return json.loads(lines[-1])["phase"] if lines else None


def run(source: Path, graph_dir: Path, pools: Path, queries: Path, full: Path,
        manifest_path: Path, main_state_path: Path, reconciliation_path: Path,
        output: Path):
    data = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(data).hexdigest()
    manifest = json.loads(data)
    if (manifest.get("schema") != "hiroute.m5d.frozen_supplement.v1" or
            len(manifest.get("rows", [])) != 24 or
            manifest["total_reservation_cpu_seconds"] != 14640 or
            manifest["wall_seconds"] != 600 or
            manifest["memory_bytes"] != 8 * 1024**3 or
            manifest["cpu_quota_percent"] != 100):
        raise ValueError("Frozen 24-row supplement differs")
    for name, path in (("queries", queries), ("pools", pools),
                       ("full_universes", full)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["input_sha256"][name]:
            raise ValueError(f"Supplemental input differs: {name}")
    main = json.loads(main_state_path.read_bytes())
    if (not main.get("stopped") or len(main.get("rows", {})) != 192 or
            main.get("schema") != "hiroute.m5d.main_batch_state.v1"):
        raise ValueError("Main denominator has not reached terminal state")
    reconciliation = json.loads(reconciliation_path.read_bytes())
    if (reconciliation.get("schema") != "hiroute.m5d.launch_reconciliation.v1" or
            reconciliation.get("main_state_sha256") !=
                hashlib.sha256(main_state_path.read_bytes()).hexdigest() or
            reconciliation.get("main_cgroup_empty") is not True or
            reconciliation.get("outside_main_receipts_reconciled") is not True or
            reconciliation.get("independent_review_approved") is not True or
            reconciliation.get("available_cpu_seconds", 0) < 14640 +
                reconciliation.get("required_margin_cpu_seconds", 0)):
        raise ValueError("Fresh reviewed launch reconciliation absent or insufficient")
    state_path = output / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_bytes())
        if state["manifest_sha256"] != manifest_sha:
            raise ValueError("Cannot resume against changed supplement")
    else:
        state = {"schema": "hiroute.m5d.supplement_batch_state.v1",
            "manifest_sha256": manifest_sha, "reconciliation_sha256":
                hashlib.sha256(reconciliation_path.read_bytes()).hexdigest(),
            "charged_cpu_ns": 0, "rows": {}, "stopped": False}
        save(state_path, state)
    if state["stopped"]:
        return state
    for row in manifest["rows"]:
        row_id = row["row_id"]
        if row_id in state["rows"]:
            continue
        available = reconciliation["available_cpu_seconds"] - state["charged_cpu_ns"] / 1e9
        unspent_reservation = 14640 - state["charged_cpu_ns"] / 1e9
        if min(available - reconciliation["required_margin_cpu_seconds"],
               unspent_reservation) < 610:
            for pending in manifest["rows"]:
                state["rows"].setdefault(pending["row_id"],
                    {"status": "budget_exhausted_unrun", "denominator_included": True})
            state["stopped"] = True
            save(state_path, state)
            return state
        row_out = output / row_id
        if row_out.exists():
            raise ValueError("Incomplete supplemental row requires manual review")
        row_out.mkdir()
        command = ("/home/dy/miniconda3/envs/hiroute/bin/python",
            str(source / "scripts/m5d_supplement_row.py"), str(source), str(graph_dir),
            str(pools), str(queries), str(full), str(manifest_path), manifest_sha,
            row_id, str(row_out))
        try:
            receipt = run_supervised(command, cwd=source, output_dir=row_out,
                wall_seconds=600, memory_bytes=8 * 1024**3,
                pythonpath=source / "src", cpu_quota_percent=100)
        except Exception:
            state["rows"][row_id] = {"status": "supervisor_failed_cpu_unknown",
                "denominator_included": True, "reached_phase": last_phase(row_out)}
            state["stopped"] = True
            save(state_path, state)
            raise
        state["charged_cpu_ns"] += receipt.cpu_usage_ns
        if receipt.result == "success" and receipt.exit_status == 0:
            status_file = row_out / "status.json"
            status = (json.loads(status_file.read_bytes()) if status_file.exists()
                else {"status": "verification_failed_missing_status"})
        elif receipt.result == "timeout":
            status = {"status": "time_limit"}
        elif receipt.result in ("oom-kill", "memory-limit"):
            status = {"status": "memory_limit"}
        else:
            status = {"status": "verification_failed_process_exit",
                "unit_result": receipt.result, "exit_status": receipt.exit_status}
        status.update(denominator_included=True, reached_phase=last_phase(row_out),
            receipt_path=receipt.receipt_path, cgroup_cpu_usage_ns=receipt.cpu_usage_ns)
        if receipt.cpu_quota_percent != 100 or receipt.cpu_usage_ns > 610 * 10**9:
            status["status"] = "verification_failed_cpu_limit"
        if "exact_outcome" in status:
            if row["component"] in ("same_alt_member_scan", "representative_repeat"):
                main_id = (f'{row["query_id"]}_n{row["candidate_count"]}_'
                           f'{row["method"]}')
                control = main["rows"].get(main_id, {})
                if ("exact_outcome" in control and
                        (status["exact_outcome"] != control["exact_outcome"] or
                         status["seed_j"] != control["seed_j"] or
                         status["certified_depth"] != control["certified_depth"] or
                         status["prewarm_sha256"] != control["prewarm_sha256"])):
                    status["status"] = "verification_failed_main_parity"
            elif row["component"] == "full_universe" and row["method"] == "hier":
                flat = state["rows"].get(f'full_{row["ordinal"]:02d}_flat', {})
                if ("exact_outcome" in flat and
                        (status["exact_outcome"] != flat["exact_outcome"] or
                         status["seed_j"] != flat["seed_j"] or
                         status["certified_depth"] != flat["certified_depth"] or
                         status["prewarm_sha256"] != flat["prewarm_sha256"])):
                    status["status"] = "verification_failed_full_pair_parity"
        state["rows"][row_id] = status
        if status["status"].startswith("verification_failed"):
            state["stopped"] = True
            for pending in manifest["rows"]:
                state["rows"].setdefault(pending["row_id"],
                    {"status": "verification_blocked_unrun", "denominator_included": True})
        save(state_path, state)
        if state["stopped"]:
            return state
    state["stopped"] = True
    save(state_path, state)
    return state


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:10]))
