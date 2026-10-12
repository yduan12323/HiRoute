"""Freeze the prespecified 24-row supplemental denominator without solving."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_for(queries, full):
    ids = [q["query_id"] for q in queries["queries"]]
    if len(ids) != 48 or len(set(ids)) != 48 or full["target_query_ids"] != ids[:6]:
        raise ValueError("Frozen query order or six full universes differ")
    rows = []
    for ordinal in range(6):
        for method in ("flat", "hier"):
            rows.append({"row_id": f"full_{ordinal:02d}_{method}",
                "query_id": ids[ordinal], "ordinal": ordinal,
                "component": "full_universe", "method": method,
                "candidate_count": full["universes_by_od"][queries["queries"][ordinal]["od_id"]]["site_count"]})
    for ordinal in (8, 47):
        for size in (32, 128):
            rows.append({"row_id": f"scan_{ordinal:02d}_n{size}_hier",
                "query_id": ids[ordinal], "ordinal": ordinal,
                "component": "same_alt_member_scan", "method": "hier",
                "candidate_count": size})
    for ordinal in (8, 47):
        for method in ("flat", "hier"):
            rows.append({"row_id": f"repeat_{ordinal:02d}_n32_{method}",
                "query_id": ids[ordinal], "ordinal": ordinal,
                "component": "representative_repeat", "method": method,
                "candidate_count": 32})
    for ordinal in (8, 47):
        for size in (32, 128):
            rows.append({"row_id": f"sequential_{ordinal:02d}_n{size}",
                "query_id": ids[ordinal], "ordinal": ordinal,
                "component": "sequential_feasible", "method": "sequential",
                "candidate_count": size})
    if len(rows) != 24 or len({r["row_id"] for r in rows}) != 24:
        raise ValueError("Supplemental denominator differs")
    return rows


def freeze(root: Path, main_path: Path, queries_path: Path, pools_path: Path,
           full_path: Path, reservation_path: Path, out: Path):
    main, queries, full, reservation = [json.loads(p.read_bytes()) for p in
        (main_path, queries_path, full_path, reservation_path)]
    if (main["schema"] != "hiroute.m5d.frozen_main_phase.v1" or
            main["input_sha256"]["queries"] != digest(queries_path) or
            main["input_sha256"]["pools"] != digest(pools_path) or
            main["input_sha256"]["full_universes"] != digest(full_path) or
            reservation["reserved_supplement_cpu_seconds"] != 14640):
        raise ValueError("Frozen main inputs or reservation differ")
    for name, expected in main["source_sha256"].items():
        if digest(root / name) != expected:
            raise ValueError(f"Frozen main numerical source differs: {name}")
    new_paths = ("scripts/m5d_supplement_alt.py", "scripts/m5d_supplement_freeze.py",
                 "scripts/m5d_supplement_row.py", "scripts/m5d_supplement_batch.py")
    source = dict(main["source_sha256"])
    source.update({name: digest(root / name) for name in new_paths})
    result = {"schema": "hiroute.m5d.frozen_supplement.v1",
        "status": "frozen_unrun", "rows": rows_for(queries, full),
        "source_sha256": source,
        "input_sha256": {"main": digest(main_path), "queries": digest(queries_path),
            "pools": digest(pools_path), "full_universes": digest(full_path),
            "reservation": digest(reservation_path), **{
                key: main["input_sha256"][key] for key in
                ("graph_nodes", "graph_edges", "graph_metadata", "hierarchy")}},
        "wall_seconds": 600, "memory_bytes": 8 * 1024**3,
        "cpu_quota_percent": 100, "row_reservation_cpu_seconds": 610,
        "total_reservation_cpu_seconds": 14640,
        "main_reservation_transfer_permitted": False,
        "selection_policy": "fixed_ordinals_0_to_5_8_47_no_replacement",
        "launch_policy": "review_required_main_terminal_fresh_cpu_reconciliation"}
    with out.open("x") as stream:
        json.dump(result, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")


if __name__ == "__main__":
    freeze(*(Path(value) for value in sys.argv[1:8]))
