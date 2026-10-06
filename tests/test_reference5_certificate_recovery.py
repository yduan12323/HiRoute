"""Post-discovery B07 regression: exact active-face recovery, never tolerance."""
from fractions import Fraction as R
import hashlib
import json
from pathlib import Path

import pytest

from validation.reference5.lp import (UncertifiedLP, dot, exact_lp, recover_certificate,
                                      solve_rational_equalities, verify_certificate)
from validation.reference5.model import normalize_case, regime_model, selected_legs

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "results/milestone_5_reference/certificate_recovery"


def saved_problem():
    data = json.loads((EVIDENCE / "b07_rejected_certificate.json").read_text())["captured"][0]
    c = tuple(map(R, data["c"]))
    A = [tuple(map(R, row)) for row in data["A"]]
    b = list(map(R, data["b"]))
    saved = data["certificate"]
    certificate = dict(status="optimal", x=tuple(map(R, saved["x"])), objective=R(saved["objective"]),
                       inequality_dual=tuple(map(R, saved["inequality_dual"])), equality_dual=())
    return c, A, b, certificate


def test_rejected_evidence_and_fixture_are_preserved():
    manifest = json.loads((EVIDENCE / "freeze_manifest.json").read_text())
    for filename, expected in manifest["files"].items():
        assert hashlib.sha256((EVIDENCE / filename).read_bytes()).hexdigest() == expected


def test_original_b07_candidate_still_fails_exact_verifier():
    c, A, b, rejected = saved_problem()
    with pytest.raises(UncertifiedLP, match="Primal infeasible"):
        verify_certificate(c, A, b, (), rejected)
    excess = [dot(row, rejected["x"]) - rhs for row, rhs in zip(A, b)
              if dot(row, rejected["x"]) > rhs]
    assert excess == [R(1, 3034993939105)] * 4


def test_b07_phase_one_recovery_has_independent_rational_certificate():
    c, A, b, rejected = saved_problem()
    recovered = recover_certificate(c, A, b, (), rejected)
    assert recovered["x"] == (R(141516, 3035), R(4408, 3035), R(0), R(99792, 3035))
    assert recovered["objective"] == R(99792, 3035) > 0
    # Check every row and the dual equations directly, independently of the
    # implementation's verify_certificate helper and the candidate solver.
    x, y = recovered["x"], recovered["inequality_dual"]
    assert all(sum(a * value for a, value in zip(row, x)) <= rhs for row, rhs in zip(A, b))
    assert all(value <= 0 for value in y)
    assert tuple(sum(row[j] * value for row, value in zip(A, y)) for j in range(len(c))) == c
    assert sum(ci * value for ci, value in zip(c, x)) == sum(rhs * value for rhs, value in zip(b, y))
    assert sum(rhs * value for rhs, value in zip(b, y)) == R(99792, 3035)
    assert recovered["candidate_recovery"] == "exact_active_constraints"


def test_minimal_three_row_regression_and_dual_lower_bound():
    problem = json.loads((EVIDENCE / "b07_minimal_lp.json").read_text())
    c = tuple(map(R, problem["c"]))
    A = [tuple(map(R, row)) for row in problem["A"]]
    b = list(map(R, problem["b"]))
    y = tuple(map(R, problem["valid_inequality_dual"]))
    rejected = dict(x=tuple(map(R, problem["rejected_primal"])), inequality_dual=y,
                    equality_dual=(), objective=R(problem["rejected_primal"][-1]))
    result = recover_certificate(c, A, b, (), rejected)
    assert result["x"] == tuple(map(R, problem["independent_expected"]["x"]))
    assert result["objective"] == sum(rhs * value for rhs, value in zip(b, y)) == R(99792, 3035)


def test_failing_b07_regime_is_certifiably_infeasible_without_model_change():
    case = normalize_case(json.loads((EVIDENCE / "b07_frozen_input.json").read_text()))
    sequence = (("u", "C"), ("u", "CS"), ("u", "C"))
    assignment = ((0, 1, 0, 2, 0, 0), "early", "charge")
    A, b, objective = regime_model(case, sequence, selected_legs(case), assignment)
    result = exact_lp(objective.coefficients, A, b)
    assert result["status"] == "infeasible"
    phase = result["phase_I_certificate"]
    assert phase["objective"] == R(99792, 3035)
    assert phase["exact_primal_dual_verified"]


def test_recovery_reconstructs_dual_stationarity_as_well_as_primal():
    epsilon = R(1, 10**12)
    candidate = dict(x=(R(99792, 607) + epsilon,), inequality_dual=(-R(1, 607) + epsilon,),
                     equality_dual=(), objective=R(99792, 607) + epsilon)
    result = recover_certificate((R(1),), [(-R(607),)], [-R(99792)], (), candidate)
    assert result["x"] == (R(99792, 607),)
    assert result["inequality_dual"] == (-R(1, 607),)


def test_recovery_handles_degenerate_free_coordinate_using_another_active_row():
    candidate = dict(x=(R(1), R(1) - R(1, 10**12)), inequality_dual=(-R(1), R(0)),
                     equality_dual=(), objective=R(1))
    result = recover_certificate((R(1), R(0)), [(-R(1), R(0)), (R(0), -R(1))],
                                 [-R(1), -R(1)], (), candidate)
    assert result["x"] == (R(1), R(1))


def test_recovery_handles_exact_equalities():
    candidate = dict(x=(R(1) + R(1, 10**12), R(2) - R(1, 10**12)),
                     inequality_dual=(-R(1),), equality_dual=(R(0),), objective=R(2) - R(1, 10**12))
    result = recover_certificate((R(0), R(1)), [(R(0), -R(1))], [-R(2)],
                                 [((R(1), R(1)), R(3))], candidate)
    assert result["x"] == (R(1), R(2))


def test_recovery_does_not_turn_infeasible_candidate_into_certified_result():
    candidate = dict(x=(R(1),), inequality_dual=(R(0), R(0)), equality_dual=(), objective=R(0))
    # Impossible interval: x<=0 and x>=1. No recovery hint can relax these rows.
    with pytest.raises(UncertifiedLP):
        recover_certificate((R(0),), [(R(1),), (-R(1),)], [R(0), -R(1)], (), candidate)


def test_exact_elimination_rejects_inconsistent_equalities():
    with pytest.raises(UncertifiedLP, match="Inconsistent"):
        solve_rational_equalities([(R(1),), (R(1),)], [R(0), R(1)], (R(0),))
