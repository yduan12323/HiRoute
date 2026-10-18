"""Six fixed OD02 replay rows, each in an isolated finite cgroup."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from timecut5.systemd_supervisor import run_supervised


def main(root: Path):
    python = "/home/dy/miniconda3/envs/hiroute/bin/python"
    graph = "/home/dy/HiRoute/project/data/processed/graphs/slovenia_extended"
    cert = root / "preflight_20261011_alt_gate/landmark_certificate.json"
    manifest = json.loads((root / "pilot_six_input_manifest.json").read_text())
    rows = [row for row in manifest["rows"] if row["od_id"] == "OD02"]
    if len(rows) != 6 or {row["candidate_prefix_count"] for row in rows} != {8, 16, 32}:
        raise ValueError("Frozen six-row OD02 replay selection changed")
    for row in rows:
        out = root / ("postpilot_seed_validation_" + row["row_id"])
        out.mkdir(exist_ok=False)
        command = (python, str(root / "scripts/m5d_seed_revalidate.py"),
            str(root), graph, str(out), str(cert), row["od_id"],
            str(row["candidate_prefix_count"]), row["activity"])
        receipt = run_supervised(command, cwd=root, output_dir=out,
            wall_seconds=180, memory_bytes=4294967296, pythonpath=str(root / "src"))
        record = out / "seed_revalidation.json"
        print(json.dumps({"row_id": row["row_id"], "result": receipt.result,
            "cpu_usage_ns": receipt.cpu_usage_ns,
            "memory_peak_bytes": receipt.memory_peak_bytes,
            "matched": json.loads(record.read_text()).get("all_proposals_equal")
                       if record.exists() else None}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
