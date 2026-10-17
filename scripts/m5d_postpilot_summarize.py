"""Source-bound receipt summary for the one corrected frozen Pilot comparison."""
from __future__ import annotations

import hashlib
import json
import copy
from pathlib import Path
import sys


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def receipt(directory: Path):
    rows = list(directory.glob("*.service.receipt.json"))
    if len(rows) != 1:
        raise ValueError(f"Exactly one supervised receipt required in {directory}")
    return rows[0], json.loads(rows[0].read_text())


def main(root: Path):
    fixed_path = root / "results/milestone_5d/continuation_20261011/fixed_pilot_summary_20261011.json"
    fixed = json.loads(fixed_path.read_text())
    rows = []
    cpu_new = cpu_validation = cpu_aborted = cpu_audit = 0
    for baseline in fixed["rows"]:
        if baseline["row_id"].startswith("OD02_"):
            row_id = baseline["row_id"]
            validation_dir = root / ("postpilot_seed_validation_" + row_id)
            validation = json.loads((validation_dir / "seed_revalidation.json").read_text())
            audit_dir = root / ("postpilot_payload_audit_" + row_id)
            audit = json.loads((audit_dir / "path_provenance_audit.json").read_text())
            audit_path, audit_receipt = receipt(audit_dir)
            if audit_receipt["result"] != "success":
                raise ValueError("Frozen payload provenance audit was not supervised to completion")
            cpu_audit += audit_receipt["cpu_usage_ns"]
            captured = json.loads((audit_dir / "selected_table.json").read_text())
            if audit.get("all_variant_hashes_reproduced") is not True:
                raise ValueError("Frozen payload provenance proof failed")
            validation_variant = copy.deepcopy(captured)
            validation_argv = validation_variant["backend"]["compiler_provenance"]["compiler_command"]
            validation_argv[-1] = str(validation_dir / "native/routing.so")
            if hashlib.sha256(canon(validation_variant)).hexdigest() != validation["table_sha256"]:
                raise ValueError("Validation table hash is not explained by its build path")
            normalized = copy.deepcopy(captured)
            normalized_argv = normalized["backend"]["compiler_provenance"]["compiler_command"]
            normalized_argv[-3], normalized_argv[-1] = "<build-source>", "<build-output>"
            normalized_sha = hashlib.sha256(canon(normalized)).hexdigest()
            validation_path, validation_receipt = receipt(validation_dir)
            if (validation_receipt["result"] != "success" or
                    validation["all_proposals_equal"] is not True or
                    validation["seed_status"] != "verified"):
                raise ValueError("Frozen replay validation failed")
            cpu_validation += validation_receipt["cpu_usage_ns"]
            methods = {}
            for method in ("flat", "hier"):
                new_dir = root / ("postpilot_benchmark_v2_" + row_id + "_" + method)
                new_path, new_receipt = receipt(new_dir)
                if new_receipt["memory_limit_bytes"] != 4294967296:
                    raise ValueError("Benchmark memory limit changed")
                new_result = json.loads((new_dir / "replay.json").read_text()) if (
                    new_dir / "replay.json").exists() else None
                new_marker = json.loads((new_dir / "search_started.json").read_text()) if (
                    new_dir / "search_started.json").exists() else None
                old_path = root / baseline["methods"][method]["receipt"]
                old_receipt = json.loads(old_path.read_text())
                old_dir = old_path.parent
                old_marker = json.loads((old_dir / "search_started.json").read_text()) if (
                    old_dir / "search_started.json").exists() else None
                table_sha = new_result["table_sha256"] if new_result else (
                    new_marker["table_sha256"] if new_marker else None)
                variants = {(item["method"], item["variant"]): item
                            for item in audit["cases"]}
                if (table_sha != variants[method, "corrected"]["table_sha256"] or
                    old_marker and old_marker["table_sha256"] !=
                    variants[method, "original"]["table_sha256"]):
                    raise ValueError("Before/after selected-leg payload is unexplained")
                if (old_marker and
                        old_marker["certified_max_depth"] != validation["certified_depth"]):
                    raise ValueError("Certified seed depth changed")
                if new_result:
                    if (new_result.get("terminal_witness_independently_replayed") is not True or
                        new_result["seed_j"] != validation["seed_J"] or
                        new_result["certified_max_depth"] != validation["certified_depth"]):
                        raise ValueError("Corrected runner omitted independent replay or seed equality")
                if (baseline["methods"][method]["exact_key"] is not None and
                    (new_result is None or
                     new_result.get("exact_key") != baseline["methods"][method]["exact_key"])):
                    raise ValueError("Completed Pilot exact key changed")
                cpu_new += new_receipt["cpu_usage_ns"]
                methods[method] = {
                    "before_status": baseline["methods"][method]["status"],
                    "before_cpu_ns": old_receipt["cpu_usage_ns"],
                    "before_setup_ns": old_marker["setup_elapsed_ns"] if old_marker else None,
                    "after_result": new_receipt["result"],
                    "after_status": new_result["exact_outcome_status"] if new_result else None,
                    "after_cpu_ns": new_receipt["cpu_usage_ns"],
                    "after_setup_ns": new_marker["setup_elapsed_ns"] if new_marker else None,
                    "after_memory_peak_bytes": new_receipt["memory_peak_bytes"],
                    "after_exact_key": new_result["exact_key"] if new_result else None,
                    "before_receipt_sha256": sha(old_path),
                    "after_receipt_sha256": sha(new_path)}
            rows.append({"row_id": row_id, "proposal_count": validation["proposal_count"],
                         "path_normalized_selected_payload_sha256": normalized_sha,
                         "path_provenance_audit_sha256": sha(audit_dir / "path_provenance_audit.json"),
                         "path_provenance_receipt_sha256": sha(audit_path),
                         "table_sha256": validation["table_sha256"],
                         "validation_sha256": sha(validation_dir / "seed_revalidation.json"),
                         "validation_receipt_sha256": sha(validation_path),
                         "methods": methods})
    aborted = json.loads((root / "postpilot_wrong_runner_abort.json").read_text())
    for name in aborted["preserved_directories"]:
        for path in (root / name).glob("*.service.receipt.json"):
            cpu_aborted += json.loads(path.read_text())["cpu_usage_ns"]
    summary = {"schema": "hiroute.m5d.postpilot_frozen_comparison.v2",
        "fixed_pilot_summary_sha256": sha(fixed_path),
        "runner_v2_sha256": sha(root / "scripts/m5d_pilot_exact_row_v2.py"),
        "seed_revalidation_runner_sha256": sha(root / "scripts/m5d_seed_revalidate.py"),
        "deployable_source_sha256": sha(root / "src/timecut5/deployable.py"),
        "rows": rows, "retained_failed_seed_rows": fixed["incumbent_search_failed_rows"],
        "validation_cpu_ns": cpu_validation, "payload_audit_cpu_ns": cpu_audit,
        "corrected_benchmark_cpu_ns": cpu_new,
        "aborted_wrong_runner_completed_cpu_ns": cpu_aborted,
        "aborted_partial_unit_conservative_charge_ns": 120_000_000_000,
        "total_new_conservative_cpu_ns": cpu_validation + cpu_audit + cpu_new +
                                         cpu_aborted + 120_000_000_000,
        "wrong_runner_abort_sha256": sha(root / "postpilot_wrong_runner_abort.json")}
    target = root / "postpilot_frozen_comparison_summary_v2.json"
    with target.open("x") as stream:
        json.dump(summary, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({key: summary[key] for key in
        ("validation_cpu_ns", "payload_audit_cpu_ns", "corrected_benchmark_cpu_ns",
         "total_new_conservative_cpu_ns", "retained_failed_seed_rows")}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
