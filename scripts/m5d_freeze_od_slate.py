"""Freeze a geographically stratified 12-OD slate from existing D4 evidence.

Physical preselection only: no leg export, Site-pool selection, LP, or holdout.
If any frozen OD fails a later input gate, report the failure; do not silently
replace it using optimization results.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "results/milestone_5d/continuation_20261011"
RESOLVED = ROOT / "results/milestone_5_real_export/query_states_resolved.json"
OUT = EVIDENCE / "fixed_12od_candidate_slate.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise ValueError("Candidate slate already exists; do not overwrite")
    aggregate_path = EVIDENCE / "grid14_aggregate.json"
    aggregate = json.loads(aggregate_path.read_text())
    if (aggregate["schema"] != "hiroute.m5d.grid14_fixed_screen_aggregate.v1" or
            aggregate["independent_checked_long_pairs"] != 140):
        raise ValueError("Fixed physical screen or independent check missing")
    for name, digest in aggregate["source_sha256"].items():
        if sha(EVIDENCE / name) != digest:
            raise ValueError(f"Source changed: {name}")
    geographic = json.loads((EVIDENCE / "geographic_screen_v5_grid14.json").read_text())
    sites = {row["site_id"]: row for row in geographic["fixed_grid_candidates"]}
    if len(sites) != 158:
        raise ValueError("Frozen geographic screen changed")
    rows = []
    for index in range(4):
        part = json.loads((EVIDENCE / f"grid14_distance_p{index}.json").read_text())
        proof = json.loads((EVIDENCE / f"grid14_potential_p{index}.json").read_text())
        if (proof["pair_screen_sha256"] != sha(EVIDENCE / f"grid14_distance_p{index}.json")
                or not proof["one_metre_margin_passed"]):
            raise ValueError("Independent partition proof mismatch")
        rows.extend(row for row in part["pairs"] if row["integer_micrometers"] is not None
                    and row["integer_micrometers"] > 450001000000)
    if len(rows) != 140:
        raise ValueError("Long-pair population changed")
    retained = json.loads(RESOLVED.read_text())
    parameters = {(row["initial_soc"], row["initial_energy_kwh"], row["capacity_kwh"])
                  for row in retained}
    if parameters != {("3/10", "18", "60"), ("19/25", "228/5", "60")}:
        raise ValueError("Inherited SOC states changed")
    by_origin = {}
    for row in rows:
        by_origin.setdefault(row["origin_site"], []).append(row)
    bands = ((0, 3), (4, 6), (7, 9), (10, 13))
    chosen = []
    for low, high in bands:
        origins = sorted((site for site in by_origin if low <= sites[site]["lat_cell"] <= high),
                         key=lambda site: (sites[site]["lat_cell"], sites[site]["lon_cell"], site))
        if len(origins) < 3:
            raise ValueError("Insufficient prespecified origins in geographic band")
        for origin in origins[:3]:
            row = min(by_origin[origin], key=lambda item: (
                sites[item["destination_site"]]["lat_cell"],
                sites[item["destination_site"]]["lon_cell"], item["destination_site"]))
            chosen.append({"origin_site": origin, "origin_anchor": row["origin_anchor"],
                           "origin_grid_cell": [sites[origin]["lat_cell"], sites[origin]["lon_cell"]],
                           "destination_site": row["destination_site"],
                           "destination_anchor": row["destination_anchor"],
                           "destination_grid_cell": [sites[row["destination_site"]]["lat_cell"],
                                                     sites[row["destination_site"]]["lon_cell"]],
                           "certified_road_distance_lower_bound_micrometers": row["integer_micrometers"]})
    if len(chosen) != 12 or len({row["origin_site"] for row in chosen}) != 12:
        raise ValueError("Exactly 12 prespecified origins required")
    queries = []
    for index, od in enumerate(chosen):
        od_id = f"OD{index:02d}"
        od["od_id"] = od_id
        for soc, initial in (("3/10", "18"), ("19/25", "228/5")):
            for activity in ("energy_only", "energy_and_scheduled"):
                queries.append({"od_id": od_id, "soc": soc, "initial_energy_kwh": initial,
                                "activity": activity, "capacity_kwh": "60",
                                "terminal_reserve_kwh": "6",
                                "consumption_kwh_per_m": "1/6250",
                                "minimum_required_charges_by_distance":
                                    "at_least_2" if soc == "3/10" else "unknown",
                                "eligible_nested_32_128_site_pools": "unknown",
                                "schedule_support": "not_applicable" if activity == "energy_only" else "unknown",
                                "executable_multi_charge_witness": "unknown",
                                "qualification": "input_gate_pending"})
    payload = {"schema": "hiroute.m5d.fixed_12od_candidate_slate.v1",
               "source_sha256": {"grid14_aggregate.json": sha(aggregate_path),
                                  "query_states_resolved.json": sha(RESOLVED),
                                  "tool": sha(Path(__file__))},
               "selection_rule": "three lexicographically earliest geographic-grid origins in each fixed latitude band 0-3, 4-6, 7-9, 10-13; for each choose the lexicographically earliest destination grid cell among independently proved >450001m directed pairs",
               "no_replacement_after_exact_results": True,
               "not_final_holdout": True,
               "no_optimization_or_route_calls": True,
               "od_count": len(chosen), "query_count": len(queries),
               "qualified_multi_charge_query_count": 0,
               "qualification_count_is_pending_not_negative": True,
               "od": chosen, "queries": queries}
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(OUT, sha(OUT))


if __name__ == "__main__":
    main()
