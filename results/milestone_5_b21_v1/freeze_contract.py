"""Freeze the numerical policy and analytic hand object before evaluating it."""
from preflight import OUT, digest, write

write('numerical_contract.json', dict(
    version='B21-v1-rational-hand-contract-v1', scope='Analytic operator/theorem probe only; no full solvers',
    arithmetic='fractions.Fraction for all branch, dominance, endpoint and witness semantics',
    equality_policy='Exact rational equality; zero semantic and full-key tolerance',
    breakpoint_ordering='Exact rational ascending order',
    endpoints='Open is strict > or <; singleton requires both endpoints closed',
    affine_intersections='Exact quotient of rational slope/intercept differences; coincident pieces compared by metadata',
    hand_cases='Exact analytic endpoint minimization; no numerical optimizer',
    lower_bound_rounding='Rational bounds require no adjustment; binary64 evaluator audit tolerance cannot establish feasibility',
    strict_charge='E_a < E_d exactly; no charge quantum and no endpoint snapping',
    executable_witness_recheck='Original rational input branch, strict charge and frozen integral F(b)-F(a)',
    semantic_comparator='Exact attained (t,rho,pi) label sets at an analytic witness energy; one difference disproves global equivalence',
    binary64_use='Unchanged frozen charging evaluator audit only, absolute 1e-10 seconds error threshold',
    no_soc_grid=True, no_heuristic_branch_cap=True))

write('alg_case_manifest.json', dict(
    version='B21-v1-algebra-population-v1', seed=52101,
    intended_generated_counts=dict(Drive=50, S=50, C=50, CS=50, three_way_merge=50),
    generated_population_status='Not yet generated; first exact closure hand object precedes generation',
    generator_policy='Rational finite PWA intervals, exact open/closed endpoints, multiple rho and tuple branches',
    first_hand_case='ALG4_open_input_minimum_and_attained_dominated_family',
    input_A=dict(state=['v', 1, 1], interval=['0', '1'], left_open=True, right_open=False,
                 time_slope='60', time_intercept='1000', rho='0', pi=[[1, 'C']], attained=True),
    input_B=dict(state=['v', 1, 1], interval=['1/2', '1/2'], left_open=False, right_open=False,
                 time_slope='0', time_intercept='1031', rho='1', pi=[[2, 'C']], attained=True),
    next_C=dict(site=3, overhead_s='300', output_energy='1', primitive_on_input_output='36 E'),
    required_ALG4_equivalence=True))

write('expected_result_certificates.json', dict(
    frozen_before_probe=True, method='Analytic exact rational derivation',
    safe_input_deletion=dict(energy='1/2', t_A='1030', t_B='1031', rho_A='0', rho_B='1',
                             identical_state=True, safely_dominated='B'),
    C_A=dict(value='1336', attained=False, expression='1336 + 24 E_a, 0 < E_a < 1'),
    C_B=dict(value='1349', attained=True, input_energy='1/2', charge='1/2'),
    noninfimal_A_witness=dict(input_energy='1/4', charge='3/4', time='1342', rho='0'),
    expected_represented_attained_sets=dict(reduce_then_C=[], C_then_reduce=['B']),
    mandatory_law_expected_violations=0,
    predicted_contract_discrepancy='Branchwise infimal-time closure retains no attained A at E_d=1; limit-only A cannot delete attained B',
    finite_representation_obstruction='Every attained A at fixed E_d=1 has an earlier attained A using half its positive input energy; no earliest attained A exists',
    waiting_suffix=dict(a='2000', b='2100', D='100', h='300',
                        attained_A_completion='2100', attained_A_input='1/4'),
    authority_sections=['Core Theory sections 18-20, 23, 26, 28',
                        'Core Audit sections 5, 9-11, 18-19',
                        'Protocol sections 7-9, 14, 28, 37']))

write('contract_freeze_manifest.json', {n: digest(OUT / n) for n in [
    'numerical_contract.json', 'alg_case_manifest.json', 'expected_result_certificates.json']})
