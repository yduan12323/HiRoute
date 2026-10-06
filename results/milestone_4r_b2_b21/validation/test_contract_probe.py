"""Regression evidence for the frozen-contract blocker.

The two complete-key assertions deliberately remain ordinary failing tests
when the frozen contracts lose a tie winner. They are not xfailed or waived.
Other tests check the counterexample, exact arithmetic and independent audit.
"""
import ast
import hashlib
import json
from dataclasses import replace
from fractions import Fraction as R
from pathlib import Path

import frontier_probe
import reference_probe
from stopplan4r.models import PiecewiseChargingCurve

OUT = Path(__file__).resolve().parent.parent


def read(name):
    return json.loads((OUT / name).read_text())


def fixture():
    return read("hand_cases.json")[0]


def key(result):
    return (R(result["J"]), R(result["Q_total"]), result["H"],
            tuple(tuple(item) for item in result["site_action_tuple"]))


def test_charging_primitive_and_frozen_curve_identity():
    audit = read("cumulative_primitive_audit.json")
    assert audit["violations"] == 0 and len(audit["cases"]) == 55
    curve = PiecewiseChargingCurve()
    for record in audit["cases"]:
        actual = curve.duration_s(float(R(record["arrival_kwh"])), float(R(record["departure_kwh"])), 60)
        assert abs(actual - float(R(record["expected_s"]))) <= 1e-10


def test_reference_expected_clock_energy_and_original_witness():
    result = read("ref_exact_case_results.json")[0]
    case = fixture()
    expected = case["independent_expected"]
    assert key(result) == key(expected)
    witness = reference_probe.original_witness(case,
        tuple(tuple(item) for item in result["site_action_tuple"]),
        tuple(R(q) for q in result["charges"]), reference_probe.selected_legs(case))
    assert witness["J"] == 44950 and witness["Q_total"] == 76
    assert witness["terminal_energy_kwh"] == 6
    assert all(q > 0 for q in witness["charges"])
    scheduled = witness["events"][-1]
    assert scheduled["schedule_start_s"] == 40000
    assert scheduled["schedule_completion_s"] == 42700


def test_all_bounded_sequences_enumerated_without_repeat_ban():
    case = fixture()
    sequences = list(reference_probe.sequences(case))
    assert len(sequences) == 263
    assert len(sequences) == read("ref_sequence_enumeration_summary.json")["sequences_enumerated"]
    assert max(map(len, sequences)) == 4
    assert (("4r:node/2", "C"), ("4r:node/2", "C"),
            ("4r:node/3", "C"), ("4r:node/4", "S")) in sequences
    assert all(sum(effect == "S" for _, effect in sequence) <= 1 for sequence in sequences)
    assert all(effect in {"C", "S"} for sequence in sequences for _, effect in sequence)


def test_selected_fastest_route_actual_length_is_not_shortest_distance():
    legs = reference_probe.selected_legs(fixture())
    assert legs["origin", "4r:node/3"] == (R(18000), R(45))
    assert legs["origin", "4r:node/2"][0] + legs["4r:node/2", "4r:node/3"][0] == 18600
    assert legs["origin", "4r:node/2"][1] + legs["4r:node/2", "4r:node/3"][1] == 38


def test_exact_primal_dual_and_infeasibility_certificates():
    feasible = reference_probe.exact_lp((R(1),), [(R(-1),), (R(1),)], [R(-3), R(5)])
    assert feasible["objective"] == 3 and feasible["exact_primal_dual_verified"]
    infeasible = reference_probe.exact_lp((R(1),), [(R(-1),), (R(1),)], [R(-3), R(2)])
    assert infeasible["status"] == "infeasible"
    assert infeasible["phase_I_certificate"]["objective"] > 0


def test_strict_positive_charge_has_no_arbitrary_quantum():
    pieces, _ = frontier_probe.prefix_frontier(fixture(), "4r:node/2")
    assert not any(piece.contains(R(0)) for piece in pieces)
    assert any(piece.contains(R(1, 10**50)) for piece in pieces)
    strict = reference_probe.strict_face([(R(-1),), (R(1),)], [R(0), R(0)], 1)
    assert strict["x"][-1] == 0


def test_frontier_merge_intersection_and_closed_singleton_tie():
    pieces, _ = frontier_probe.prefix_frontier(fixture(), "4r:node/1")
    a = replace(pieces[0], low=R(0), high=R(30), left_open=False, right_open=False,
                time_slope=R(1), time_intercept=R(0), charge_slope=R(0), charge_intercept=R(2))
    b = replace(a, piece_id="other", time_slope=R(-1), time_intercept=R(30), charge_intercept=R(1))
    merged = frontier_probe.merge([a, b])
    assert min(p.key(R(10)) for p in merged if p.contains(R(10)))[0] == 10
    assert min(p.key(R(20)) for p in merged if p.contains(R(20)))[0] == 10
    point = [p for p in merged if p.low == p.high == 15]
    assert len(point) == 1 and point[0].charge_intercept == 1


def test_drive_floor_clipping_and_capacity_endpoints():
    pieces, _ = frontier_probe.prefix_frontier(fixture(), "4r:node/2")
    driven = frontier_probe.drive(pieces, "4r:node/4", R(9000), R(40), R(0), R(60))
    assert min(p.low for p in driven) == 0 and max(p.high for p in driven) == 20
    assert any(p.contains(R(0)) for p in driven)
    assert any(p.contains(R(20)) for p in driven)
    assert not any(p.contains(R(-1, 10**50)) for p in driven)


def test_reference_independence_and_no_soc_grid_guard():
    source = Path(reference_probe.__file__).read_text()
    imports = read("reference_independence_manifest.json")["imported_modules"]
    assert not any("frontier" in name or "hierarchy" in name for name in imports)
    assert hashlib.sha256(source.encode()).hexdigest() == read("reference_independence_manifest.json")["sha256"]
    for module in (reference_probe, frontier_probe):
        tree = ast.parse(Path(module.__file__).read_text())
        identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert not identifiers & {"soc_grid", "q_min", "qmin", "linspace", "arange"}


def test_frozen_frontier_preserves_complete_key_after_schedule_waiting():
    probe = frontier_probe.run(fixture())
    reference = read("ref_exact_case_results.json")[0]
    assert key(probe["earliest_frontier_result"]) == key(reference), (
        "T7 earliest-time merge loses the later lower-charge prefix: "
        "both finish at J=44950, but Q is 83 versus the exact 76 kWh")


def test_frozen_strict_cost_dominance_preserves_complete_key():
    probe = frontier_probe.run(fixture())["dominance_witness"]
    assert probe["time_A"] <= probe["time_B"]
    assert probe["energy_A"] >= probe["energy_B"]
    assert probe["g_A"] < probe["g_B"]
    assert key(probe["D_on_point_label_result"]) == key(probe["D_off_point_label_result"]), (
        "T3 authorizes deletion but waiting removes the primary advantage "
        "and the deleted prefix has the better cumulative-charge tie key")
