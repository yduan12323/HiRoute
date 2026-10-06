"""Compare physical FLAT/HIER with separately generated exact REF evidence.

Example, from the repository root:
  python experiments/time_cut_v2/run_bounded_validation.py \
    --cases results/milestone_5_reference/frozen_cases_v2.json \
    --reference results/milestone_5_reference/analytic_cases_ref_v2.json \
    --output results/milestone_5_time_cut_v2/solver_parity_v2.json

This imports no REF optimization implementation and never rewrites its inputs.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from fractions import Fraction as R
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from timecut5.bounded import solve_bounded
from timecut5.hierarchy import solve_hierarchical


def signature(result):
    status = result["status"]
    if status == "attained_optimum":
        return status, R(result["J"]), R(result["Q_total"]), result["H"], tuple(tuple(x) for x in result["site_action_tuple"])
    if status == "primary_unattained":
        return status, R(result["primary_infimum"])
    if status == "secondary_unattained":
        return status, R(result.get("J", result.get("primary_infimum"))), R(result["secondary_infimum"])
    if status == "infeasible_within_H_ref":
        return (status,)
    raise ValueError(f"Unresolved/invalid reference result cannot certify parity: {status}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cases_path: Path, reference_path: Path, output_path: Path):
    fixture_bytes, reference_bytes = cases_path.read_bytes(), reference_path.read_bytes()
    cases = json.loads(fixture_bytes, parse_float=R)
    data = json.loads(reference_bytes, parse_float=R)
    reference_rows = data.get("results", [data]) if isinstance(data, dict) else data
    references = {row["case_id"]: row for row in reference_rows}
    comparisons = []
    for case in cases:
        reference = references[case["case_id"]]
        if reference["scope"] != "bounded_H_ref_diagnostic" or reference["H_ref"] != case["H_ref"]:
            raise ValueError("Reference and candidate comparison domains differ")
        expected = signature(reference["result"])
        for name, solver in (("FLAT", solve_bounded), ("HIER", solve_hierarchical)):
            for dominance in (False, True):
                start = perf_counter()
                result = solver(case, dominance=dominance)
                canonical = result.canonical()
                actual = signature(canonical["result"])
                row = dict(case_id=case["case_id"], engine=name, dominance=dominance,
                           equal=actual == expected, canonical=canonical,
                           expected_signature=expected, actual_signature=actual,
                           seconds=perf_counter()-start, evidence=asdict(result))
                comparisons.append(row)
                print(case["case_id"], name, f"D={dominance}", canonical["result"]["status"],
                      "PASS" if row["equal"] else "MISMATCH", flush=True)
    report = dict(scope="bounded_H_ref_diagnostic", cases=len(cases), comparisons=len(comparisons),
                  mismatches=sum(not row["equal"] for row in comparisons),
                  fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest(),
                  reference_sha256=hashlib.sha256(reference_bytes).hexdigest(),
                  source_sha256={str(p.relative_to(ROOT)):digest(p) for p in
                                 (ROOT/"src/timecut5").glob("*.py")},
                  rows=comparisons)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, default=str, indent=2)+"\n")
    if report["mismatches"]:
        raise AssertionError("Bounded solver parity failed; see saved report")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.cases, args.reference, args.output)
