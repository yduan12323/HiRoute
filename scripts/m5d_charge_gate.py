"""Read-only M5-D charge-count screen from a declared road-distance lower bound.

Input is a JSON object with `distance_certified` and `states`. Each state has
`state_id`, `od_id`, `road_distance_lower_m`, `initial_energy_kwh`,
`capacity_kwh`, `terminal_reserve_kwh`, and `consumption_kwh_per_m`, all
numbers encoded as decimal or rational strings. No route or optimizer runs.
"""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path


def _fraction(value: object, label: str) -> Fraction:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a decimal or rational string")
    result = Fraction(value)
    if result < 0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def evaluate(payload: dict) -> dict:
    if payload.get("distance_certified") is not False:
        raise ValueError("this screening tool cannot certify road-distance evidence")
    states = payload.get("states")
    if not isinstance(states, list) or not states:
        raise ValueError("states must be a nonempty list")
    result = []
    seen = set()
    for state in states:
        if not isinstance(state, dict):
            raise ValueError("each state must be an object")
        state_id, od_id = state.get("state_id"), state.get("od_id")
        if not isinstance(state_id, str) or not isinstance(od_id, str) or not state_id or not od_id:
            raise ValueError("state_id and od_id must be nonempty strings")
        if state_id in seen:
            raise ValueError(f"duplicate state_id {state_id}")
        seen.add(state_id)
        distance = _fraction(state.get("road_distance_lower_m"), "road_distance_lower_m")
        initial = _fraction(state.get("initial_energy_kwh"), "initial_energy_kwh")
        capacity = _fraction(state.get("capacity_kwh"), "capacity_kwh")
        reserve = _fraction(state.get("terminal_reserve_kwh"), "terminal_reserve_kwh")
        consumption = _fraction(state.get("consumption_kwh_per_m"), "consumption_kwh_per_m")
        if capacity <= 0 or consumption <= 0 or initial > capacity or reserve > capacity:
            raise ValueError("invalid capacity, energy, reserve, or consumption")
        # A stop can add at most one whole battery capacity. This relaxation is
        # deliberately loose, so any positive count is a valid necessity only
        # when the supplied directed road distance is a certified lower bound.
        deficit = consumption * distance - initial + reserve
        minimum = max(0, -(-deficit // capacity))
        result.append({"state_id": state_id, "od_id": od_id,
                       "minimum_charges_from_distance": minimum})
    return {"distance_certified": False,
            "claim_status": "screening_only",
            "state_count": len(result),
            "states_with_minimum_two_charges": sum(row["minimum_charges_from_distance"] >= 2 for row in result),
            "od_ids_with_minimum_two_charges": sorted({row["od_id"] for row in result
                                                      if row["minimum_charges_from_distance"] >= 2}),
            "states": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.input.read_text()))
    if args.output.exists():
        parser.error("output already exists")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
