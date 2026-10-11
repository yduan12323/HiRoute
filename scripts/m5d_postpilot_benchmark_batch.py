"""One fixed before/after Pilot comparison under the original cgroup limits."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from timecut5.systemd_supervisor import run_supervised


def main(root: Path):
    manifest = json.loads((root / "pilot_six_input_manifest.json").read_text())
    rows = [row for row in manifest["rows"] if row["od_id"] == "OD02"]
    if len(rows) != 6:
        raise ValueError("Frozen six-row benchmark selection changed")
    for row in rows:
        record = root / ("postpilot_seed_validation_" + row["row_id"]) / "seed_revalidation.json"
        if (not record.is_file() or
                json.loads(record.read_text()).get("all_proposals_equal") is not True):
            raise ValueError("All frozen seed replay rows must pass before benchmarking")
    python = "/home/dy/miniconda3/envs/hiroute/bin/python"
    graph = "/home/dy/HiRoute/project/data/processed/graphs/slovenia_extended"
    cert = root / "preflight_20261011_alt_gate/landmark_certificate.json"
    for row in rows:
        for method in ("flat", "hier"):
            out = root / ("postpilot_benchmark_v2_" + row["row_id"] + "_" + method)
            out.mkdir(exist_ok=False)
            command = (python, str(root / "scripts/m5d_pilot_exact_row_v2.py"),
                str(root), graph, str(out), str(cert), row["od_id"],
                str(row["candidate_prefix_count"]), row["activity"], method)
            receipt = run_supervised(command, cwd=root, output_dir=out,
                wall_seconds=120, memory_bytes=4294967296, pythonpath=str(root / "src"))
            result = out / "replay.json"
            outcome = json.loads(result.read_text()) if result.exists() else None
            print(json.dumps({"row_id": row["row_id"], "method": method,
                "result": receipt.result, "cpu_usage_ns": receipt.cpu_usage_ns,
                "memory_peak_bytes": receipt.memory_peak_bytes,
                "exact_outcome_status": outcome.get("exact_outcome_status") if outcome else None,
                "setup_elapsed_ns": json.loads((out / "search_started.json").read_text()).get(
                    "setup_elapsed_ns") if (out / "search_started.json").exists() else None}),
                flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
