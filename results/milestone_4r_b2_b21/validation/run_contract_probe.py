"""Run the first frozen hand-case contract probe, with independent REF evidence."""
import ast
import csv
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from time import perf_counter

import frontier_probe
import reference_probe

OUT = Path(__file__).resolve().parent.parent


def serial(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {str(key): serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    return value


def write(name, data):
    with (OUT / name).open("x") as stream:
        json.dump(serial(data), stream, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    contract = json.loads((OUT / "numerical_contract.json").read_text())
    assert contract["frozen_before_comparison"]
    cases = json.loads((OUT / "hand_cases.json").read_text())
    manifest = json.loads((OUT / "case_construction_manifest.json").read_text())
    assert hashlib.sha256((OUT / "hand_cases.json").read_bytes()).hexdigest() == manifest["case_file_sha256"]
    case = cases[0]
    reference = reference_probe.solve(case)
    write("ref_sequence_enumeration_summary.json", dict(H_ref=case["H_ref"],
        sequences_enumerated=reference["sequence_count"], sequences=reference["sequences"],
        all_static_effect_labelled_sequences_enumerated=True,
        self_legs_retained=True, repeat_site_ban=False,
        independent_analytic_certificate=case["analytic_certificate"]))
    write("ref_regime_enumeration_evidence.json", dict(regime_count=reference["regime_count"],
        strict_feasible_regime_count=reference["strict_feasible_regime_count"],
        rational_primal_dual_certificates=True, regimes=reference["regimes"]))
    result = reference["result"]
    expected = case["independent_expected"]
    assert result["J"] == Fraction(expected["J"])
    assert result["Q_total"] == Fraction(expected["Q_total"])
    assert result["H"] == expected["H"]
    assert serial(result["site_action_tuple"]) == expected["site_action_tuple"]
    assert result["terminal_energy_kwh"] == Fraction(expected["terminal_energy_kwh"])
    write("ref_exact_case_results.json", [dict(case_id=case["case_id"], **result)])
    started = perf_counter()
    probe = frontier_probe.run(case)
    frontier_seconds = perf_counter() - started
    write("frontier_traces_hand_cases.json", dict(case_id=case["case_id"], **probe))
    assert probe["primary_equal"]
    assert probe["charge_gap"] == 7
    assert probe["retain_alternatives_result"]["Q_total"] == result["Q_total"]
    actual = probe["earliest_frontier_result"]
    write("operator_audits.json", dict(case_id=case["case_id"], status="failed",
        theorem="T7-4 / earliest-time merge closure under scheduled waiting",
        expression="S(merge(A,B)) loses the charge winner present in merge(S(A),S(B))",
        reference=result, earliest_frontier=actual,
        primary_mismatches=0, cumulative_charge_mismatches=1, discrete_witness_mismatches=1,
        primary_equal=True, charge_gap_kwh=probe["charge_gap"],
        source_contract="T7 audit Sections 3, 6, 16-20; B21 protocol Sections 4, 14-15, 21-23",
        contract_failure=True, implementation_patch_applied=False))
    write("attainment_audits.json", dict(case_id=case["case_id"], reference_status=result["status"],
        frontier_status=actual["status"], status_agrees=True, scope="blocking probe only",
        all_C_witness_quantities_strictly_positive=True))
    write("tie_witness_audits.json", dict(case_id=case["case_id"], reference=result,
        earliest_frontier=actual, key_equal=False,
        failure="The minimum-charge history is not an earliest-time history at the preceding anchor."))
    write("dominance_deletion_witnesses.json", [probe["dominance_witness"]])
    write("dominance_on_off_comparison.json", dict(case_id=case["case_id"],
        scope="exact point-label continuation theorem probe, not completed FLAT-F modes",
        mismatch_count=1, **probe["dominance_witness"]))
    source = Path(reference_probe.__file__)
    tree = ast.parse(source.read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module)
    assert not any("frontier" in name or "hierarchy" in name for name in imports)
    write("reference_independence_manifest.json", dict(
        implementation="validation/reference_probe.py", sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        imported_modules=imports, frontier_calls=0, region_bound_calls=0,
        optimizer="independent explicit charging-segment / schedule-branch regime LPs with exact certificates",
        scope="C/S blocking hand case; full B21 REF not completed after hard stop"))
    with (OUT / "runtime_table.csv").open("x") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "component", "seconds", "scope"])
        writer.writeheader()
        for component, seconds in [("REF_sequence_enumeration", reference["enumeration_seconds"]),
            ("REF_continuous_regime_optimization", reference["optimization_seconds"]),
            ("REF_total", reference["total_seconds"]), ("frontier_operator_probe", frontier_seconds)]:
            writer.writerow(dict(case_id=case["case_id"], component=component, seconds=seconds,
                scope="blocking contract probe only; no performance interpretation"))
    pieces = probe["pieces"]
    with (OUT / "frontier_complexity_table.csv").open("x") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "operation", "output_piece_count", "open_endpoints", "limit_only_pieces", "distinct_breakpoints"])
        writer.writeheader()
        for name, group in pieces.items():
            writer.writerow(dict(case_id=case["case_id"], operation=name,
                output_piece_count=len(group), open_endpoints=sum(p["left_open"] + p["right_open"] for p in group),
                limit_only_pieces=sum(not p["attained"] for p in group),
                distinct_breakpoints=len({p["low"] for p in group} | {p["high"] for p in group})))
    write("semantic_coverage_matrix.json", dict(executed_cases=[case["case_id"]],
        demonstrated=["C", "S", "C-C", "C-C-S", "reserve-tight destination", "positive charge", "repeated Site enumeration retained"],
        remaining_coverage="not evaluated after the failed tie/dominance contract probe"))
    write("contract_probe_decision.json", dict(status="hard_stop_correctness_failure",
        case_id=case["case_id"], G2_violations=1, G4_mismatches=1,
        T3_tie_safety_counterexamples=1, stage_A_executed=1, stage_A_planned=20,
        stage_B_executed=0, stage_C_executed=0, full_REF_FLAT_HIER_comparison_run=False,
        decision="B2-1 blocked; do not proceed to deployable/long-haul scaling.",
        frozen_theory_changed=False, numerical_or_semantic_patch=False))
    print(json.dumps(serial(dict(reference=result, earliest_frontier=actual,
        sequences=reference["sequence_count"], regimes=reference["regime_count"],
        charge_gap_kwh=probe["charge_gap"], hard_stop=True)), indent=2))


if __name__ == "__main__":
    main()
