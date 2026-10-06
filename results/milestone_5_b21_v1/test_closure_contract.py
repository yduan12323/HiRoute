"""Unwaived theorem assertion plus independent exact facts for its counterexample."""
from fractions import Fraction as R
from charging_audit import audit, F
from closure_probe import (inputs, reduce_input_hand_object, C_hand_piece,
                           attained_signature, run)


def test_frozen_charging_primitive_identity():
    assert audit()['violations'] == 0
    assert F(30) == 1080 and F(48) == 2160 and F(60) == 3600


def test_same_energy_safe_input_reduction():
    A, B = inputs()
    assert A.time(R(1, 2)) == 1030 < B.time(R(1, 2)) == 1031
    assert A.rho < B.rho and A.state == B.state
    assert reduce_input_hand_object((A, B)) == (A,)


def test_strict_endpoints_and_exact_unattained_charge_infimum():
    A, B = inputs()
    assert not A.contains(R(0)) and A.contains(R(1))
    a, b = C_hand_piece(A), C_hand_piece(B)
    assert (a.time, a.attained, a.input_energy) == (1336, False, None)
    assert (b.time, b.attained, b.input_energy) == (1349, True, R(1, 2))


def test_no_earliest_attained_realization_in_A_output_family():
    # Universal proof: time(u)-time(u/2)=12u>0 for every u in (0,1).
    slope = inputs()[0].slope - 36
    assert slope == 24 and slope / 2 > 0
    assert inputs()[0].left_open


def test_noninfimal_attained_witness_becomes_attained_after_waiting():
    result = run()
    assert result['witness_time'] == 1342
    assert result['attained_waiting_completion'] == 2100


def test_alg4_mandatory_charge_congruence():
    result = run()
    assert attained_signature(result['left']) == attained_signature(result['right']), (
        'Core v1 ALG-4 fails: safe input reduction removes B; branchwise C stores '
        'only unattained A infimum 1336, while C before reduction retains attained B '
        '1349. Noninfimal attained A outputs are absent from the mandated branch summary.')
