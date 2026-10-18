"""Run fixed Pilot input qualification rows serially under separate cgroups."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from timecut5.systemd_supervisor import run_supervised


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(root):
    manifest=root/"pilot_six_input_manifest.json"
    records=json.loads(manifest.read_text())
    source=root/"results/milestone_5d/continuation_20261011"
    if (records["pool_sha256"]!=sha(root/"formal_pools_20261011_v2/pools.json") or
        records["slate_sha256"]!=sha(source/"fixed_12od_candidate_slate.json")):
        raise ValueError("Frozen Pilot source binding failed")
    python="/home/dy/miniconda3/envs/hiroute/bin/python"
    graph="/home/dy/HiRoute/project/data/processed/graphs/slovenia_extended"
    cert=root/"preflight_20261011_alt_gate/landmark_certificate.json"
    for row in records["rows"]:
        out=root/("pilot_gate_"+row["row_id"])
        out.mkdir(exist_ok=False)
        cmd=(python,str(root/"scripts/m5d_pilot_input_gate.py"),str(root),graph,str(out),str(cert),
             row["od_id"],str(row["candidate_prefix_count"]),row["activity"])
        receipt=run_supervised(cmd,cwd=root,output_dir=out,wall_seconds=120,
            memory_bytes=4294967296,pythonpath=str(root/"src"))
        result=out/"replay.json"
        record={"row_id":row["row_id"],"result":receipt.result,
            "cpu_usage_ns":receipt.cpu_usage_ns,"memory_peak_bytes":receipt.memory_peak_bytes,
            "replay_sha256":sha(result) if result.exists() else None}
        print(json.dumps(record),flush=True)


if __name__=="__main__":main(Path(sys.argv[1]))
