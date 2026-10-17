"""Six fixed path-provenance audits with independent cgroup receipts."""
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
        raise ValueError("Frozen OD02 audit set changed")
    python = "/home/dy/miniconda3/envs/hiroute/bin/python"
    graph = "/home/dy/HiRoute/project/data/processed/graphs/slovenia_extended"
    cert = root / "preflight_20261011_alt_gate/landmark_certificate.json"
    for row in rows:
        out = root / ("postpilot_payload_audit_" + row["row_id"])
        out.mkdir(exist_ok=False)
        command = (python, str(root / "scripts/m5d_payload_provenance_audit.py"),
            str(root), graph, str(out), str(cert), row["od_id"],
            str(row["candidate_prefix_count"]), row["activity"])
        receipt = run_supervised(command, cwd=root, output_dir=out,
            wall_seconds=180, memory_bytes=4294967296, pythonpath=str(root / "src"))
        proof = out / "path_provenance_audit.json"
        matched = json.loads(proof.read_text()).get("all_variant_hashes_reproduced") if proof.exists() else None
        print(json.dumps({"row_id": row["row_id"], "result": receipt.result,
            "cpu_usage_ns": receipt.cpu_usage_ns,
            "matched": matched}), flush=True)
        if receipt.result != "success" or matched is not True:
            raise ValueError("Frozen path provenance audit failed; remaining rows were not started")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
