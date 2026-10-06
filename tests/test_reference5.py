"""Independent REF regression and exact certificate/failure-contract tests."""
from copy import deepcopy
from fractions import Fraction as R
import hashlib
import json
from pathlib import Path

import pytest

from validation.reference5 import InvalidInput, jsonable, normalize_case, replay_witness, selected_legs, solve_case
from validation.reference5 import solver
from validation.reference5.lp import UncertifiedLP, exact_lp, strict_face, verify_certificate
from validation.reference5.model import sequences

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "results/milestone_5_reference/frozen_cases_v2.json"
CASES = json.loads(FROZEN.read_text())


@pytest.fixture(scope="module")
def solved_cases():
    return {case["case_id"]: solve_case(case) for case in CASES}


def test_fixtures_frozen_before_comparison():
    manifest = json.loads((FROZEN.parent / "freeze_manifest_v2.json").read_text())
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest() == manifest["sha256"]
    assert manifest["case_count"] == len(CASES) == 18


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_analytic_expectations_and_valid_witness_replay(case, solved_cases):
    envelope = solved_cases[case["case_id"]]
    assert envelope["scope"] == "bounded_H_ref_diagnostic"
    assert envelope["H_ref"] == case["H_ref"]
    assert envelope["all_regimes_certified"]
    assert envelope["regime_count"] == envelope["certified_regime_count"]
    result = envelope["result"]
    serialized = jsonable(result)
    for field, value in case["independent_expected"].items():
        assert serialized[field] == value
    if result["status"] == "attained_optimum":
        replay = replay_witness(case, result["site_action_tuple"], result["charges"])
        assert replay["lex_key"] == result["lex_key"]
        assert replay["remaining_schedule"] == 0
        assert replay["witness_replayed"]
    else:
        assert "lex_key" not in result
        assert "site_action_tuple" not in result
        assert "H" not in result


def test_original_76_fixture_exhaustively():
    case = json.loads((ROOT / "results/milestone_4r_b2_b21/hand_cases.json").read_text())[0]
    envelope = solve_case(case, keep_evidence=False)
    result = envelope["result"]
    expected = case["independent_expected"]
    assert envelope["all_regimes_certified"]
    assert envelope["sequence_count"] == 41
    assert envelope["terminal_sequence_count"] == 16
    assert envelope["regime_count"] == envelope["certified_regime_count"] == 11072
    assert result["status"] == "attained_optimum"
    assert result["lex_key"] == (R(44950), R(76), 3,
                                  (("4r:node/2", "C"), ("4r:node/3", "C"), ("4r:node/4", "S")))
    assert result["terminal_energy_kwh"] == R(expected["terminal_energy_kwh"])
    valid = replay_witness(case, expected["site_action_tuple"], expected["one_valid_charge_vector"])
    assert valid["lex_key"] == result["lex_key"]


def test_repeats_are_not_forbidden():
    case = normalize_case(next(c for c in CASES if c["case_id"] == "cyclic_directed_graph_repeated_site_positive_v2"))
    enumerated = list(sequences(case, selected_legs(case)))
    assert ((("x", "C"), ("x", "CS")), 0, "x") in enumerated
    assert all(sum(effect in ("S", "CS") for _, effect in sequence) <= 1 for sequence, _, _ in enumerated)


def test_fastest_path_uses_selected_length_not_shortest_distance():
    case = normalize_case(next(c for c in CASES if c["case_id"] == "fastest_leg_actual_length_positive_v2"))
    leg = selected_legs(case)["o", "z"]
    assert (leg.time, leg.length, leg.energy, leg.edges) == (R(1), R(4), R(4), ("fast",))


def test_parallel_edge_order_is_deterministic_under_input_permutation():
    case = deepcopy(next(c for c in CASES if c["case_id"] == "deterministic_parallel_edge_tie_positive_v2"))
    first = selected_legs(normalize_case(case))["o", "z"]
    case["edges"].reverse()
    second = selected_legs(normalize_case(case))["o", "z"]
    assert first == second
    assert first.edges == ("a",) and first.energy == 1


def test_node_path_tie_precedes_physical_length():
    case = deepcopy(next(c for c in CASES if c["case_id"] == "zero_stop_no_station_positive_v2"))
    case["edges"] = [dict(source="o", target="b", time_s=1, length_m="1/4"),
                     dict(source="b", target="z", time_s=1, length_m="1/4"),
                     dict(source="o", target="a", time_s=1, length_m=1),
                     dict(source="a", target="z", time_s=1, length_m=1)]
    leg = selected_legs(normalize_case(case))["o", "z"]
    assert leg.nodes == ("o", "a", "z") and leg.energy == 2


@pytest.mark.parametrize("change", [
    {"H_ref": -1}, {"H_ref": True}, {"initial_remaining_schedule": 2},
    {"initial_remaining_schedule": 1, "schedule": None}, {"initial_energy_kwh": 6},
    {"reserve_kwh": -1}, {"minimum_energy_kwh": 3}, {"overhead_s": -1},
    {"overhead_s": 0}, {"lambda_stop_s": -1}, {"consumption_kwh_per_m": "nan"}, {"start_time_s": float("inf")},
    {"schedule": {"a": 2, "b": 1, "D": 1}}, {"schedule": {"a": 1, "b": 2, "D": -1}},
    {"sites": {"x": ["C", "C"]}}, {"sites": {"x": ["unknown"]}},
    {"charging_segments": []}, {"charging_segments": [[0, 5, 0, 0]]},
    {"charging_segments": [[0, 2, 1, 0], [2, 5, 3, 0]]},
    {"charging_segments": [[0, 1, 1, 0], [2, 5, 1, 0]]},
    {"edges": [dict(source="o", target="z", time_s=0, length_m=1)]},
    {"edges": [dict(source="o", target="z", time_s=1, length_m=0)]},
    {"edges": [dict(source="o", target="z", time_s=-1, length_m=0)]},
    {"edges": [dict(source="o", target="z", time_s=1, length_m=-1)]},
    {"edges": [dict(source="o", target="z", time_s=1, length_m=0, edge_id="a"),
               dict(source="o", target="z", time_s=2, length_m=0, edge_id="a")]},
])
def test_invalid_input_is_not_infeasibility(change):
    case = deepcopy(CASES[0])
    case.update(change)
    result = solve_case(case)["result"]
    assert result["status"] == "invalid_input"
    assert "lex_key" not in result


def test_uncertified_regime_invalidates_case_even_after_valid_candidate(monkeypatch):
    actual = solver.exact_lp
    calls = 0

    def sometimes_uncertified(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 6:
            raise UncertifiedLP("deliberate certificate failure")
        return actual(*args, **kwargs)

    monkeypatch.setattr(solver, "exact_lp", sometimes_uncertified)
    case = next(c for c in CASES if c["case_id"] == "deterministic_site_tuple_tie_positive_v2")
    envelope = solver.solve_case(case)
    assert envelope["certified_regime_count"] == 4  # Site a already supplied an attained candidate.
    assert envelope["result"]["status"] == "unresolved"
    assert not envelope["all_regimes_certified"]
    assert "lex_key" not in envelope["result"]
    assert "deliberate certificate failure" in envelope["result"]["reason"]


def test_exact_lp_verifies_optimum_and_detects_tampered_certificate():
    c, A, b = (R(1),), [(-R(1),), (R(1),)], [-R(1, 3), R(2)]
    certificate = exact_lp(c, A, b)
    assert certificate["x"] == (R(1, 3),)
    assert verify_certificate(c, A, b, (), certificate)
    bad = dict(certificate, x=(R(0),))
    with pytest.raises(UncertifiedLP, match="Primal"):
        verify_certificate(c, A, b, (), bad)


def test_phase_one_certifies_infeasible_equalities():
    result = exact_lp((R(0),), [], [], [((R(1),), R(0)), ((R(1),), R(1))])
    assert result["status"] == "infeasible"
    assert result["phase_I_certificate"]["objective"] == R(1, 2)
    assert result["phase_I_certificate"]["exact_primal_dual_verified"]


def test_strict_feasibility_has_no_charge_quantum():
    # The exact positive common slack is far below one; no arbitrary q_min is
    # used to classify the strict face. The constraint is q<=1/10000000.
    tiny = R(1, 10_000_000)
    certificate = strict_face([(-R(1),), (R(1),)], [R(0), tiny], 1)
    assert certificate["x"][-1] == tiny
    boundary = strict_face([(-R(1),), (R(1),)], [R(0), tiny], 1, [((R(1),), R(0))])
    assert boundary["x"][-1] == 0


@pytest.mark.parametrize("sequence,charges", [
    ((("x", "CS"),), (R(0),)), ((("x", "CS"),), (R(1),)),
    ((("x", "CS"),), (R(10),)), ((("x", "S"),), ()),
    ((), ()), ((("unknown", "CS"),), (R(2),)),
    ((("x", "CS"), ("x", "CS")), (R(1), R(1))),
])
def test_witness_replay_rejects_invalid_actions_and_energy(sequence, charges):
    with pytest.raises(InvalidInput):
        replay_witness(CASES[0], sequence, charges)


def test_primary_unattained_regime_does_not_supply_secondary_value():
    witness = dict(J=R(1), Q_total=R(7), H=1, site_action_tuple=(("x", "CS"),), charges=(R(7),),
                   lex_key=(R(1), R(7), 1, (("x", "CS"),)))
    result = solver.choose_result([
        dict(primary_infimum=R(1), primary_attained=False),
        dict(primary_infimum=R(1), primary_attained=True, secondary_infimum=R(7),
             secondary_attained=True, witness=witness),
    ])
    assert result["status"] == "attained_optimum" and result["Q_total"] == 7


def test_open_lower_secondary_face_blocks_larger_attained_charge():
    result = solver.choose_result([
        dict(primary_infimum=R(1), primary_attained=True, secondary_infimum=R(0), secondary_attained=False),
        dict(primary_infimum=R(1), primary_attained=True, secondary_infimum=R(2), secondary_attained=True,
             witness=dict(H=1, site_action_tuple=(("x", "CS"),), charges=(R(2),))),
    ])
    assert result == dict(status="secondary_unattained", J=R(1), primary_infimum=R(1),
                          secondary_infimum=R(0), unattained_component="Q")


def test_reference_has_no_production_dependencies():
    import ast
    for source in (ROOT / "validation/reference5").glob("*.py"):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("timecut5", "stopplan4r"))
            elif isinstance(node, ast.Import):
                assert all(not alias.name.startswith(("timecut5", "stopplan4r")) for alias in node.names)


@pytest.mark.parametrize("case", json.loads((FROZEN.parent / "frozen_cases.json").read_text()),
                         ids=lambda c: "preserved_exploratory_" + c["case_id"])
def test_preserved_v1_requires_explicit_exploratory_domain(case):
    result = solve_case(case, allow_nonnegative_extension=True)
    assert result["model_domain"] == "exploratory_nonnegative_extension"
    for key, expected in case["independent_expected"].items():
        assert jsonable(result["result"])[key] == expected
    if case["overhead_s"] == 0 or any(edge["time_s"] <= 0 or edge["length_m"] <= 0 for edge in case["edges"]):
        assert solve_case(case)["result"]["status"] == "invalid_input"


@pytest.mark.parametrize("case", json.loads((FROZEN.parent / "audit_regression_cases.json").read_text()),
                         ids=lambda c: c["case_id"])
def test_destination_policy_audit_regressions(case):
    path = FROZEN.parent / "audit_regression_cases.json"
    manifest = json.loads((FROZEN.parent / "audit_regression_freeze.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["sha256"]
    result = solve_case(case)
    assert result["all_regimes_certified"]
    for key, expected in case["independent_expected"].items():
        assert jsonable(result["result"])[key] == expected
    if result["result"]["status"] == "attained_optimum":
        assert result["result"]["route_legs"][0].nodes == ("o", "z", "s")
        replay_witness(case, result["result"]["site_action_tuple"], result["result"]["charges"])


def test_destination_stop_witness_is_rejected():
    case = json.loads((FROZEN.parent / "audit_regression_cases.json").read_text())[0]
    with pytest.raises(InvalidInput, match="Destination is terminal"):
        replay_witness(case, (("z", "S"),), ())


def test_zero_stop_witness_cannot_insert_drive_waypoint_or_fake_selected_legs():
    from validation.reference5.model import Leg
    path = FROZEN.parent / "audit_route_grammar_cases.json"
    manifest = json.loads((FROZEN.parent / "audit_route_grammar_freeze.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["sha256"]
    case = json.loads(path.read_text())[0]
    assert solve_case(case)["result"]["status"] == "infeasible_within_H_ref"
    with pytest.raises(InvalidInput, match="reserve"):
        replay_witness(case, (), ())
    # The LP solver may pass its computed leg map for checking, but a caller
    # cannot replace the fixed fastest leg with an energy-cheaper detour.
    legs = selected_legs(normalize_case(case))
    assert legs["o", "z"].nodes == ("o", "z")
    forged = dict(legs)
    forged["o", "z"] = Leg(R(2), R(2), R(2), ("o", "x", "z"), ("input:00000001", "input:00000002"))
    with pytest.raises(InvalidInput, match="independently selected fastest"):
        replay_witness(case, (), (), forged)
    case["H_ref"] = 1
    with pytest.raises(InvalidInput, match="support witness action"):
        replay_witness(case, (("x", "D"),), ())


def test_replay_stop_bound_is_not_bypassed_by_valid_energy_and_actions():
    case = deepcopy(CASES[0])
    case["H_ref"] = 0
    with pytest.raises(InvalidInput, match="stop or charge-vector dimension"):
        replay_witness(case, (("x", "CS"),), (R(2),))
