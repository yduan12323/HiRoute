"""Serial exact FLAT/HIER Pilot runs for seed-qualified fixed rows only."""
from __future__ import annotations
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from timecut5.systemd_supervisor import run_supervised


def main(root):
    manifest=json.loads((root/"pilot_six_input_manifest.json").read_text())
    python="/home/dy/miniconda3/envs/hiroute/bin/python"
    graph="/home/dy/HiRoute/project/data/processed/graphs/slovenia_extended"
    cert=root/"preflight_20261011_alt_gate/landmark_certificate.json"
    for row in manifest["rows"]:
        if row["od_id"]!="OD02":continue
        row_id=row["row_id"]
        gate=(root/("pilot_gate_"+row_id) if row["candidate_prefix_count"]==8
              else root/("pilot_gate_repair_"+row_id))
        check=json.loads((gate/"replay.json").read_text())
        if check["qualification"]!="independently_replayed_multi_stop_seed":
            raise ValueError("Fixed input row lacks verified same-domain seed")
        for method in ("flat","hier"):
            if row_id=="OD02_energy_only_soc3_10_n8" and method=="flat":continue
            out=root/("pilot_exact_v2_"+row_id+"_"+method)
            out.mkdir(exist_ok=False)
            cmd=(python,str(root/"scripts/m5d_pilot_exact_row_v2.py"),str(root),graph,str(out),str(cert),
                row["od_id"],str(row["candidate_prefix_count"]),row["activity"],method)
            receipt=run_supervised(cmd,cwd=root,output_dir=out,wall_seconds=120,
                memory_bytes=4294967296,pythonpath=str(root/"src"))
            result=out/"replay.json"
            outcome=json.loads(result.read_text()) if result.exists() else None
            print(json.dumps({"row_id":row_id,"method":method,"result":receipt.result,
                "cpu_usage_ns":receipt.cpu_usage_ns,"memory_peak_bytes":receipt.memory_peak_bytes,
                "exact_outcome_status":outcome.get("exact_outcome_status") if outcome else None}),flush=True)


if __name__=="__main__":main(Path(sys.argv[1]))
