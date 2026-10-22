"""Synthetic adapter tests only; never substitutes for real E2E acceptance."""
from copy import deepcopy
import hashlib
from unittest.mock import patch

import pytest

from experiments.m5e2e_v1.solve import (canonical, digest, solve_method, compare_receipts,
    check_reference_evidence, normalize_result)


def fixture(schedule=False):
    ids = ['A', 'B']
    tree = dict(site_ids=ids, regions=[dict(parent=-1, children=[1, 2], members=[0, 1]),
                                    dict(parent=0, children=[], members=[0]),
                                    dict(parent=0, children=[], members=[1])])
    hierarchy = canonical(tree); hierarchy_hash = hashlib.sha256(hierarchy).hexdigest()
    def encoded(value):
        value = float(value); n, d = value.as_integer_ratio()
        return dict(hex=value.hex(), ratio=[str(n), str(d)])
    anchors = ['o', 'a', 'b', 'z']
    values = {('o','a'): (1, 1), ('a','b'): (1, 2), ('b','z'): (1, 2),
              ('o','b'): (2, 3), ('o','z'): (3, 5), ('a','z'): (2, 4)}
    legs = []
    for a in anchors:
        for b in anchors:
            value = (0, 0) if a == b else values.get((a, b))
            legs.append(dict(source_anchor=a, target_anchor=b, reachable=value is not None,
                time_s=encoded(value[0]) if value else None,
                actual_length_m=encoded(value[1]) if value else None,
                label_direction='identity' if a == b else 'forward_from_source'))
    payload = dict(schema='hiroute.immutable_selected_legs.v1',
        numerical_contract='binary64_totals_as_exact_rationals_v1', anchors=anchors,
        origin_anchor='o', destination_anchor='z',
        sites=[dict(site_id='A', anchor_id='a', effects=['C']),
               dict(site_id='B', anchor_id='b', effects=['C', 'CS', 'S'] if schedule else ['C'])],
        legs=legs, source_sha256=dict(nodes='1'*64, edges='2'*64),
        selection_certificate_sha256='3'*64, hierarchy_sha256=hierarchy_hash,
        backend=dict(name='explicit_synthetic_test_only',
            tie_policy='min_time_then_actual_length_then_first_discovery',
            direction_policy='forward_per_source_v1', source_sha256={'router':'4'*64}))
    raw = canonical(payload); leg_hash = hashlib.sha256(raw).hexdigest()
    query = dict(case_id='E02' if schedule else 'E03', H_ref=3, origin='o', destination='z',
        start_time_s='0', initial_energy_kwh='1', capacity_kwh='2', minimum_energy_kwh='0',
        reserve_kwh='0', consumption_kwh_per_m='1', overhead_s='1', lambda_stop_s='0',
        charging_segments=[['0','2','1','0']],
        schedule=dict(a='0', b='100', D='1') if schedule else None)
    binding = dict(validation_domain='real_map_microdomain_v1', depth_mode='declared_diagnostic_cap',
        exposure_class='DEV_E2E', H_ref=3, case_id=query['case_id'], candidate_count=2,
        candidate_site_ids=ids, candidate_sha256=digest(ids), query_sha256=digest(query),
        legs_sha256=leg_hash, hierarchy_sha256=hierarchy_hash,
        graph_identity=dict(nodes_sha256='1'*64, edges_sha256='2'*64))
    return query, raw, dict(legs_sha256=leg_hash, hierarchy_bytes=hierarchy,
                           hierarchy_sha256=hierarchy_hash, domain_binding=binding)


@pytest.mark.parametrize('schedule', [False, True])
def test_independent_complete_key_multicharge_and_schedule(schedule):
    query, raw, kwargs = fixture(schedule)
    receipts = [solve_method(method, query, raw, **kwargs) for method in ('REF','FLAT','HIER')]
    comparison = compare_receipts(receipts)
    assert comparison['reference_match'] is True
    assert comparison['actual_positive_charge_count'] == 2
    assert comparison['schedule_covered'] is schedule
    assert all(r['resource_supervised'] is False for r in receipts)
    assert receipts[1]['production_layer'] == 'bounded_real_api'
    assert receipts[2]['seed_policy'] == 'own_search_without_external_incumbent'
    evidence = receipts[0]['reference_evidence']
    with patch('validation.reference5.lp.linprog', side_effect=AssertionError('No LP solving in cold checker')):
        checked = check_reference_evidence(query, raw, kwargs['legs_sha256'], evidence)
    assert checked['status'] == 'VERIFIED'
    assert checked['optimization_invoked'] is False


@pytest.mark.parametrize('field,value', [
    ('validation_domain','m6h'), ('depth_mode','seed_derived'), ('H_ref', 2),
    ('candidate_count',8), ('candidate_site_ids',['B','A']), ('query_sha256','0'*64),
    ('exposure_class','HOLDOUT'), ('case_id','E04'), ('hierarchy_sha256','0'*64)])
def test_fail_closed_on_frozen_binding(field, value):
    query, raw, kwargs = fixture(); kwargs['domain_binding'][field] = value
    with pytest.raises(ValueError):
        solve_method('REF', query, raw, **kwargs)


def test_no_real_input_fallback_and_no_graph_substitution():
    query, raw, kwargs = fixture()
    with pytest.raises(ValueError):
        solve_method('REF', query, b'{}', **kwargs)
    query['edges'] = []; kwargs['domain_binding']['query_sha256'] = digest(query)
    receipt = solve_method('REF', query, raw, **kwargs)
    assert receipt['operation_status'] == 'UNKNOWN'
    assert receipt['mathematical_status'] == 'UNKNOWN'
    assert receipt['canonical_outcome'] is None


def test_cold_check_rejects_removed_forged_or_extra_evidence():
    query, raw, kwargs = fixture()
    evidence = solve_method('REF', query, raw, **kwargs)['reference_evidence']
    bad = deepcopy(evidence); bad['regimes'].pop()
    with pytest.raises(ValueError):
        check_reference_evidence(query, raw, kwargs['legs_sha256'], bad)
    bad = deepcopy(evidence)
    cert = next(r['primary_certificate'] for r in bad['regimes'] if r['primary_certificate']['status'] == 'optimal')
    cert['objective'] = '99999'
    with pytest.raises((ValueError, ArithmeticError)):
        check_reference_evidence(query, raw, kwargs['legs_sha256'], bad)
    bad = deepcopy(evidence); bad['all_regimes_certified'] = False
    with pytest.raises(ValueError):
        check_reference_evidence(query, raw, kwargs['legs_sha256'], bad)


def test_unresolved_never_means_infeasible_or_agreement():
    query, raw, kwargs = fixture()
    with patch('validation.reference5.real_solver.solve_real_case', return_value={
            'result':dict(status='unresolved'), 'all_regimes_certified':False}):
        unknown = solve_method('REF', query, raw, **kwargs)
    others = [dict(unknown, method=method) for method in ('FLAT','HIER')]
    assert compare_receipts([unknown, *others])['reference_match'] is None
    assert unknown['operation_status'] == 'UNKNOWN'
    assert normalize_result(dict(status='secondary_unattained', J='1', secondary_infimum='0')) == {
        'status':'secondary_unattained', 'J':'1', 'secondary_infimum':'0', 'first_unattained':'Q'}
    assert 'lex_key' not in normalize_result(dict(status='primary_unattained', primary_infimum='1'))


def test_comparison_rejects_changed_physical_domain_and_complete_key_mismatch():
    query, raw, kwargs = fixture()
    receipts = [solve_method(method, query, raw, **kwargs) for method in ('REF','FLAT','HIER')]
    bad = deepcopy(receipts); bad[1]['domain_binding_sha256'] = '0'*64
    with pytest.raises(ValueError): compare_receipts(bad)
    bad = deepcopy(receipts); bad[1]['canonical_outcome']['lex_key'][1] = '99'
    with pytest.raises(ValueError): compare_receipts(bad)


@pytest.mark.parametrize('field', [
    'primary_certificate', 'strict_feasibility_certificate', 'primary_face_certificate',
    'secondary_certificate', 'secondary_face_certificate'])
def test_each_optimal_lp_certificate_class_is_checked(field):
    query, raw, kwargs = fixture()
    evidence = solve_method('REF', query, raw, **kwargs)['reference_evidence']
    candidates = [r[field] for r in evidence['regimes'] if field in r and r[field]['status'] == 'optimal']
    assert candidates, 'Synthetic coverage must include this certificate class'
    candidates[0]['objective'] = '1000000'
    with pytest.raises((ValueError, ArithmeticError)):
        check_reference_evidence(query, raw, kwargs['legs_sha256'], evidence)


def test_extra_and_reordered_regimes_rejected():
    query, raw, kwargs = fixture(True)
    evidence = solve_method('REF', query, raw, **kwargs)['reference_evidence']
    assert len(evidence['regimes']) > 1
    bad = deepcopy(evidence); bad['regimes'].append(deepcopy(bad['regimes'][0]))
    with pytest.raises((ValueError, ArithmeticError)):
        check_reference_evidence(query, raw, kwargs['legs_sha256'], bad)
    bad = deepcopy(evidence); bad['regimes'].reverse()
    with pytest.raises((ValueError, ArithmeticError)):
        check_reference_evidence(query, raw, kwargs['legs_sha256'], bad)


def test_same_key_allows_distinct_legal_charging_vectors():
    from validation.reference5.real_input import IndependentLegTable
    from validation.reference5.real_solver import replay_real_witness
    query, raw, kwargs = fixture()
    query['capacity_kwh'] = '3'; query['charging_segments'] = [['0','3','1','0']]
    kwargs['domain_binding']['query_sha256'] = digest(query)
    table = IndependentLegTable.from_bytes(raw, kwargs['legs_sha256'])
    first = replay_real_witness(query, table, [('A','C'),('B','C')], ['2','2'])
    second = replay_real_witness(query, table, [('A','C'),('B','C')], ['3','1'])
    assert first['charges'] != second['charges']
    assert normalize_result(dict(first, status='attained_optimum')) == normalize_result(dict(second, status='attained_optimum'))
