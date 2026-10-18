"""Reconstruct frozen table hashes after normalizing only build path fields."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scripts import m5d_pilot_exact_row as runner


class Captured(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(root: Path, graph: Path, out: Path, certificate: Path,
        od_id: str, size: int, activity: str):
    if od_id != "OD02" or size not in (8, 16, 32) or activity not in (
            "energy_only", "energy_and_scheduled"):
        raise ValueError("Only frozen OD02 Pilot rows may be audited")
    fixed = json.loads((root / "results/milestone_5d/continuation_20261011/"
                        "fixed_pilot_summary_20261011.json").read_text())
    row_id = f"{od_id}_{activity}_soc3_10_n{size}"
    baseline = next(row for row in fixed["rows"] if row["row_id"] == row_id)
    original_root = Path("/home/dy/HiRoute/m5d_c01_aab8656")

    def capture(domain, _):
        payload = json.loads(domain.table_bytes)
        with (out / "selected_table.json").open("xb") as stream:
            stream.write(domain.table_bytes)
        command = payload["backend"]["compiler_provenance"]["compiler_command"]
        if (command[-2] != "-o" or
                command[-3] != str(root / "src/microplan/routing.cpp") or
                command[-1] != str(out / "native/routing.so")):
            raise ValueError("Unexpected native compiler provenance shape")
        cases = []
        for method in ("flat", "hier"):
            old_receipt = baseline["methods"][method]["receipt"]
            old_dir = original_root / Path(old_receipt).parent
            new_dir = root / ("postpilot_benchmark_v2_" + row_id + "_" + method)
            for label, source_root, target_dir, marker_dir in (
                    ("original", original_root, old_dir, root / Path(old_receipt).parent),
                    ("corrected", root, new_dir, new_dir)):
                variant = copy.deepcopy(payload)
                argv = variant["backend"]["compiler_provenance"]["compiler_command"]
                argv[-3] = str(source_root / "src/microplan/routing.cpp")
                argv[-1] = str(target_dir / "native/routing.so")
                actual = digest(runner.canon(variant))
                expected = json.loads((marker_dir / "search_started.json").read_text())["table_sha256"]
                if actual != expected:
                    raise ValueError(f"{row_id} {method} {label} table hash is not explained by build paths")
                binary = marker_dir / "native/routing.so"
                cases.append({"method": method, "variant": label,
                    "table_sha256": actual, "native_binary_sha256": digest(binary.read_bytes()),
                    "compiler_source": argv[-3], "compiler_output": argv[-1]})
        if len({item["native_binary_sha256"] for item in cases}) != 1:
            raise ValueError("Native routing binary bytes changed between variants")
        result = {"schema": "hiroute.m5d.path_provenance_audit.v1",
            "row_id": row_id, "captured_table_sha256": domain.table_sha256,
            "captured_table_file_sha256": digest((out / "selected_table.json").read_bytes()),
            "graph_source_sha256": payload["source_sha256"],
            "cases": cases, "all_variant_hashes_reproduced": True}
        with (out / "path_provenance_audit.json").open("x") as stream:
            json.dump(result, stream, sort_keys=True, indent=2)
            stream.write("\n")
        raise Captured

    runner.construct_verified_seed = capture
    try:
        runner.run(root, graph, out, certificate, od_id, size, activity, "flat")
    except Captured:
        return
    raise ValueError("Frozen Pilot table capture hook was not reached")


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:5]), sys.argv[5],
        int(sys.argv[6]), sys.argv[7])
