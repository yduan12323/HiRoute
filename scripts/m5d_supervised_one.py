"""Launch the fixed C01 diagnostic under one 120-second/4-GiB cgroup."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from timecut5.systemd_supervisor import run_supervised


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--graph-dir", type=Path, required=True)
    parser.add_argument("--states-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--mode", choices=("preflight", "solve"), required=True)
    args = parser.parse_args()
    root = args.repo.resolve(strict=True)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=False)
    command = (str(args.python.resolve(strict=True)),
        str(root / "scripts/m5d_one_query_runner.py"),
        "--repo", str(root), "--export-dir", str(args.export_dir.resolve(strict=True)),
        "--graph-dir", str(args.graph_dir.resolve(strict=True)),
        "--states-sha256", args.states_sha256,
        "--output-dir", str(output.resolve(strict=True)), "--mode", args.mode)
    receipt = run_supervised(command, cwd=root, output_dir=output,
        wall_seconds=120, memory_bytes=4 * 1024**3, pythonpath=root / "src")
    query_path = output / "query_result.json"
    result = {"schema": "hiroute.m5d.one_query_supervision.v1",
        "scope": "fixed_historical_C01_eight_site_diagnostic_not_formal_12od",
        "command": command, "mode": args.mode,
        "supervisor": asdict(receipt),
        "supervisor_receipt_sha256": hashlib.sha256(
            Path(receipt.receipt_path).read_bytes()).hexdigest(),
        "query_result_sha256": hashlib.sha256(query_path.read_bytes()).hexdigest()
            if query_path.is_file() else None}
    with (output / "supervision_summary.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
