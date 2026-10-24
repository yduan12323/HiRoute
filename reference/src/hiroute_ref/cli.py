"""Solve one explicit ProblemSnapshot with the independent bounded REF."""
import argparse
import hashlib
import json
from pathlib import Path

from .solver import jsonable, solve_case


def snapshot_case(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("schema") != "hiroute.problem_snapshot.v1":
        raise ValueError("Expected a hiroute.problem_snapshot.v1 object")
    identity = {key: value for key, value in snapshot.items() if key != "semantic_problem_id"}
    semantic_id = hashlib.sha256((json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":")) + "\n").encode()).hexdigest()
    if snapshot.get("semantic_problem_id") != semantic_id:
        raise ValueError("Snapshot semantic_problem_id does not match its content")
    # The REF owns its admission contract independently; unsupported identifiers
    # must not be silently interpreted as the bounded time-cut model.
    supported = {
        "model_contract_id": "hiroute.time_cut_v2.bounded",
        "numerical_contract_id": "exact_rational_inputs_v1",
        "selected_leg_contract": "positive_time_node_path_edge_path_tie_v1",
        "depth_mode": "diagnostic_cap",
    }
    for field, expected in supported.items():
        if snapshot.get(field) != expected:
            raise ValueError(f"unsupported REF input: {field}={snapshot.get(field)!r}")
    case = {
        "case_id": snapshot["semantic_problem_id"],
        "H_ref": snapshot["depth_limit"], "origin": snapshot["origin"],
        "destination": snapshot["destination"], "start_time_s": snapshot["departure_time_s"],
        "initial_energy_kwh": snapshot["initial_energy_kwh"],
        "capacity_kwh": snapshot["capacity_kwh"],
        "minimum_energy_kwh": snapshot["minimum_energy_kwh"],
        "reserve_kwh": snapshot["destination_reserve_kwh"],
        "consumption_kwh_per_m": snapshot["consumption_kwh_per_m"],
        "overhead_s": snapshot["stop_overhead_s"],
        "lambda_stop_s": snapshot["stop_penalty_s"],
        "schedule": snapshot["schedule"],
        "initial_remaining_schedule": snapshot["initial_remaining_schedule"],
        "sites": {site: list(effects) for site, effects in snapshot["site_capabilities"].items()},
        "charging_segments": snapshot["charging_curve"],
        "edges": [{k: row[k] for k in ("source", "target", "time_s", "length_m", "edge_id") if k in row}
                  for row in snapshot["directed_edges"]],
    }
    required = {"case_id", "H_ref", "origin", "destination", "start_time_s",
                "initial_energy_kwh", "capacity_kwh", "minimum_energy_kwh", "reserve_kwh",
                "consumption_kwh_per_m", "overhead_s", "lambda_stop_s", "schedule",
                "initial_remaining_schedule", "sites", "charging_segments", "edges"}
    if set(case) != required:
        raise ValueError("Snapshot is missing a field required by the independent model")
    return case, semantic_id


def main(argv=None):
    parser = argparse.ArgumentParser(prog="hiroute-ref")
    parser.add_argument("--problem", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--certificates", action="store_true")
    args = parser.parse_args(argv)
    raw = args.problem.read_bytes()
    source = json.loads(raw)
    case, semantic_id = snapshot_case(source)
    solved = solve_case(case, keep_evidence=args.certificates)
    report = {"schema": "hiroute_ref.report.v1", "semantic_problem_id": semantic_id,
              "oracle": "independent_hiroute_ref", "fixture_sha256": hashlib.sha256(raw).hexdigest(),
              "result": solved}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(jsonable(report), output, ensure_ascii=False, sort_keys=True, indent=2)
        output.write("\n")
    print(json.dumps({"semantic_problem_id": semantic_id,
                      "status": solved["result"]["status"], "output": str(args.output)}, sort_keys=True))
    return 2 if solved["result"]["status"] in ("invalid_input", "unresolved") else 0


if __name__ == "__main__":
    raise SystemExit(main())
