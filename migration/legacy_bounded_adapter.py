"""Separate-process R1 adapter around the historical bounded FLAT implementation.

This adapter is not included in the hiroute wheel. Its only protocol is one
ProblemSnapshot JSON object on stdin and one result JSON object on stdout.
"""
from __future__ import annotations

from fractions import Fraction
import json
import os
from pathlib import Path
import sys


def rational(value):
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("adapter accepts exact integer/rational inputs only")
    return Fraction(value)


def main() -> int:
    source_root = os.environ.get("HIROUTE_LEGACY_SOURCE_ROOT")
    if not source_root:
        raise RuntimeError("HIROUTE_LEGACY_SOURCE_ROOT must be explicit")
    sys.path.insert(0, str(Path(source_root).resolve()))
    from timecut5.bounded import solve_bounded, replay_witness

    snapshot = json.load(sys.stdin)
    if snapshot.get("schema") != "hiroute.problem_snapshot.v1":
        raise ValueError("Unsupported snapshot schema")
    case = {
        "H_ref": snapshot["depth_limit"],
        "origin": snapshot["origin"],
        "destination": snapshot["destination"],
        "start_time_s": snapshot["departure_time_s"],
        "initial_energy_kwh": snapshot["initial_energy_kwh"],
        "capacity_kwh": snapshot["capacity_kwh"],
        "minimum_energy_kwh": snapshot["minimum_energy_kwh"],
        "reserve_kwh": snapshot["destination_reserve_kwh"],
        "consumption_kwh_per_m": snapshot["consumption_kwh_per_m"],
        "overhead_s": snapshot["stop_overhead_s"],
        "lambda_stop_s": snapshot["stop_penalty_s"],
        "schedule": snapshot["schedule"],
        "initial_remaining_schedule": snapshot["initial_remaining_schedule"],
        "sites": snapshot["site_capabilities"],
        "charging_segments": snapshot["charging_curve"],
        "edges": snapshot["directed_edges"],
    }
    bounded = solve_bounded(case)
    solved = bounded.result
    witness = None
    replayed = False
    if solved.status == "attained_optimum" and solved.witness is not None:
        replayed_key = replay_witness(case, solved.witness)
        if replayed_key != solved.key:
            raise RuntimeError("Legacy physical replay differs from solver key")
        witness = {
            "schema": "hiroute.witness.v1",
            "actions": [list(x) for x in solved.witness.pi],
            "charges_kwh": [str(e.departure_energy - e.arrival_energy)
                            for e in solved.witness.events if e.effect in ("C", "CS")],
            "events": [dict(effect=e.effect, site=e.site, arrival_time_s=str(e.arrival_time),
                            departure_time_s=str(e.departure_time),
                            arrival_energy_kwh=str(e.arrival_energy),
                            departure_energy_kwh=str(e.departure_energy))
                       for e in solved.witness.events],
            "route_legs": [],
        }
        replayed = True
    status = ("primary_unattained" if solved.status == "infimum_unattained" and
              solved.unattained_component == "J" else
              "secondary_unattained" if solved.status == "infimum_unattained" and
              solved.unattained_component == "Q" else
              "infeasible_within_H_ref" if solved.status == "infeasible" else solved.status)
    result_data = {
        "status": status,
        "key": None if solved.key is None else [
            str(solved.key[0]), str(solved.key[1]), solved.key[2],
            [list(x) for x in solved.key[3]]],
        "primary_infimum": None if solved.primary_infimum is None else str(solved.primary_infimum),
        "secondary_infimum": None if solved.secondary_infimum is None else str(solved.secondary_infimum),
        "scope": bounded.scope,
        "H_ref": bounded.H_ref,
    }
    print(json.dumps({"backend": "legacy_migration_adapter",
                      "result": result_data, "witness": witness,
                      "witness_replayed": replayed},
                     ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
