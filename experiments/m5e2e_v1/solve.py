"""Diagnostic immutable-real E2E workers, separate from M6-H admission.

The caller must run each invocation in a fresh externally supervised process.
This module neither claims resource control nor reads any previous result when
solving. REF imports no production optimizer; FLAT/HIER use their own search.
"""
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

SCHEMA = 'hiroute.m5e2e.method_receipt.v1'
DOMAIN = 'real_map_microdomain_v1'
METHODS = ('REF', 'FLAT', 'HIER')


def primitive(value):
    if isinstance(value, F):
        return str(value)
    if is_dataclass(value):
        return primitive(asdict(value))
    if isinstance(value, dict):
        return {str(k): primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    return value


def canonical(value):
    return json.dumps(primitive(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def normalize_result(result):
    """Compare only defined lexicographic components; never witness vectors."""
    status = result.get('status')
    if status == 'attained_optimum':
        key = [str(F(result['J'])), str(F(result['Q_total'])), result['H'],
               [list(p) for p in result['site_action_tuple']]]
        raw_key = result['lex_key']
        other = [str(F(raw_key[0])), str(F(raw_key[1])), raw_key[2],
                 [list(p) for p in raw_key[3]]]
        if key != other or type(key[2]) is not int or key[2] != len(key[3]):
            raise ValueError('Attained result has inconsistent complete key')
        return dict(status=status, lex_key=key)
    if status == 'primary_unattained':
        return dict(status=status, primary_infimum=str(F(result['primary_infimum'])), first_unattained='J')
    if status == 'secondary_unattained':
        return dict(status=status, J=str(F(result['J'])),
                    secondary_infimum=str(F(result['secondary_infimum'])), first_unattained='Q')
    if status == 'infeasible_within_H_ref':
        return dict(status='infeasible_within_declared_domain')
    return None


def _admit(query, table, binding, hierarchy_sha256):
    if (binding.get('validation_domain') != DOMAIN or
            binding.get('depth_mode') != 'declared_diagnostic_cap' or
            binding.get('exposure_class') != 'DEV_E2E' or
            type(binding.get('H_ref')) is not int or binding['H_ref'] != 3 or
            type(query.get('H_ref')) is not int or query['H_ref'] != 3):
        raise ValueError('Explicit DEV diagnostic H_ref=3 admission required')
    ids = list(table.sites)
    if (not 1 <= len(ids) <= 4 or type(binding.get('candidate_count')) is not int or
            binding.get('candidate_count') != len(ids) or
            binding.get('candidate_site_ids') != ids or binding.get('candidate_sha256') != digest(ids)):
        raise ValueError('Frozen microdomain candidate identity/order differs')
    if (binding.get('case_id') not in ('E01', 'E02', 'E03') or
            query.get('case_id') != binding['case_id'] or
            binding.get('query_sha256') != digest(query) or
            binding.get('legs_sha256') != table.payload_sha256 or
            binding.get('hierarchy_sha256') != hierarchy_sha256 or
            table.hierarchy_sha256 != hierarchy_sha256):
        raise ValueError('Frozen E2E input identities differ')
    graph = binding.get('graph_identity')
    if (type(graph) is not dict or set(graph) != {'nodes_sha256', 'edges_sha256'} or
            any(table.source_sha256.get(name[:-7]) != value for name, value in graph.items())):
        raise ValueError('Graph identity is not bound to immutable selected legs')


def _independent_replay(query, table, result):
    from validation.reference5.real_input import IndependentLegTable
    from validation.reference5.real_solver import replay_real_witness
    if result.get('status') != 'attained_optimum':
        return None
    fresh = IndependentLegTable.from_bytes(table.raw_bytes, table.payload_sha256)
    replay = replay_real_witness(query, fresh, result['site_action_tuple'], result['charges'])
    if normalize_result(dict(status='attained_optimum', **replay)) != normalize_result(result):
        raise ValueError('Independent witness replay contradicts complete key')
    return primitive(replay)


def solve_method(method, query, leg_bytes, *, legs_sha256, hierarchy_bytes,
                 hierarchy_sha256, domain_binding):
    """One bounded method, with immutable inputs only and no result-file input.

    The receipt's ``resource_supervised`` remains false: only the external
    supervisor can bind measured resource limits and worker cleanup.
    """
    if method not in METHODS:
        raise ValueError('Unknown E2E method')
    from validation.reference5.real_input import IndependentLegTable
    independent = IndependentLegTable.from_bytes(leg_bytes, legs_sha256)
    _admit(query, independent, domain_binding, hierarchy_sha256)
    if hashlib.sha256(hierarchy_bytes).hexdigest() != hierarchy_sha256:
        raise ValueError('Hierarchy bytes differ')
    evidence = None
    production_witness = None
    if method == 'REF':
        from validation.reference5.real_solver import solve_real_case
        solved = solve_real_case(query, independent, keep_evidence=True, regime_limit=None)
        certified = solved.get('all_regimes_certified') is True
        result = solved['result']
        evidence = primitive(solved)
        api = 'validation.reference5.real_solver.solve_real_case'
    else:
        from timecut5.real_legs import ImmutableLegTable, restrict_frozen_tree
        from timecut5.real_adapter import solve_bounded_real, solve_hierarchical_real, replay_real_witness
        from timecut5.provenance import witness_dict
        table = ImmutableLegTable.from_bytes(leg_bytes, legs_sha256)
        tree = restrict_frozen_tree(hierarchy_bytes, hierarchy_sha256, list(table.sites))
        function = solve_bounded_real if method == 'FLAT' else solve_hierarchical_real
        solved = function(query, table, tree, dominance=True)
        result = solved.canonical()['result']
        inner = solved.inner.bounded if hasattr(solved.inner, 'bounded') else solved.inner
        if inner.result.witness is not None:
            if replay_real_witness(query, table, inner.result.witness) != inner.result.key:
                raise ValueError('Production witness replay differs from result key')
            production_witness = witness_dict(inner.result.witness)
        certified = normalize_result(result) is not None
        api = 'timecut5.real_adapter.' + function.__name__
    outcome = normalize_result(result)
    replay = _independent_replay(query, independent, result) if outcome else None
    return primitive(dict(schema=SCHEMA, method=method, case_id=query['case_id'],
        domain_binding=domain_binding, domain_binding_sha256=digest(domain_binding),
        operation_status='SUCCESS' if certified and outcome is not None else 'UNKNOWN',
        mathematical_status=outcome['status'] if certified and outcome else 'UNKNOWN',
        exactness_scope=DOMAIN + ':candidate_set_and_declared_H3_only',
        canonical_outcome=outcome if certified else None,
        solver_entrypoint=api, production_layer='bounded_real_api' if method != 'REF' else None,
        seed_policy='own_search_without_external_incumbent' if method != 'REF' else 'no_seed_diagnostic_depth',
        ref_entrypoint=api if method == 'REF' else None,
        ref_completed=certified and outcome is not None if method == 'REF' else None,
        all_regimes_certified=certified if method == 'REF' else None,
        result=result, witness_replayed=replay is not None,
        witness=production_witness, independent_replay=replay,
        actual_positive_charge_count=sum(F(q) > 0 for q in replay['charges']) if replay else None,
        necessary_charge_lower_bound_or_unknown='UNKNOWN',
        schedule_covered=bool(replay and query.get('schedule') is not None and
                              any(e['effect'] in ('S', 'CS') for e in replay['events'])),
        reference_evidence=evidence, resource_supervised=False,
        road_replay_scope='immutable_leg_constants_only; separate graph replay required'))


def compare_receipts(receipts):
    """Fail closed on missing/unknown methods or any physical-domain mismatch."""
    if len(receipts) != 3 or {r.get('method') for r in receipts} != set(METHODS):
        raise ValueError('Exactly one receipt per REF/FLAT/HIER is required')
    if len({r.get('domain_binding_sha256') for r in receipts}) != 1:
        raise ValueError('Methods did not solve the same physical domain')
    for r in receipts:
        if r.get('schema') != SCHEMA or r.get('domain_binding_sha256') != digest(r.get('domain_binding')):
            raise ValueError('Invalid receipt binding')
        if r.get('operation_status') == 'SUCCESS':
            if normalize_result(r.get('result', {})) != r.get('canonical_outcome'):
                raise ValueError('Receipt normalized result differs from source result')
            if r.get('canonical_outcome', {}).get('status') == 'attained_optimum':
                replay = r.get('independent_replay')
                if type(replay) is not dict or normalize_result(dict(replay, status='attained_optimum')) != r['canonical_outcome']:
                    raise ValueError('Receipt independent replay differs from source result')
    ref = next(r for r in receipts if r['method'] == 'REF')
    certified = (all(r.get('operation_status') == 'SUCCESS' and r.get('canonical_outcome') is not None
                     for r in receipts) and ref.get('ref_completed') is True and
                 ref.get('all_regimes_certified') is True)
    if not certified:
        return dict(status='PARTIAL', reference_match=None, reason='missing_independent_certification')
    if any(r['canonical_outcome']['status'] == 'attained_optimum' and r.get('witness_replayed') is not True
           for r in receipts):
        raise ValueError('Attained method lacks independent replay')
    match = all(r['canonical_outcome'] == ref['canonical_outcome'] for r in receipts)
    return dict(status='MATCH' if match else 'CORRECTNESS_FAILED', reference_match=match,
                actual_positive_charge_count=ref.get('actual_positive_charge_count'),
                schedule_covered=ref.get('schedule_covered'))


def _rational_certificate(certificate):
    result = dict(certificate)
    for key in ('x', 'inequality_dual', 'equality_dual'):
        if key in result:
            result[key] = tuple(F(v) for v in result[key])
    if 'objective' in result:
        result['objective'] = F(result['objective'])
    return result


def _check_lp(c, A, b, equalities, certificate):
    """Use existing exact primal/dual checker, including its Phase-I model."""
    from validation.reference5.lp import verify_certificate
    c = tuple(map(F, c)); A = [tuple(map(F, row)) for row in A]
    b = list(map(F, b)); eq = [(tuple(map(F, row)), F(rhs)) for row, rhs in equalities]
    cert = _rational_certificate(certificate)
    if cert['status'] == 'optimal':
        verify_certificate(c, A, b, eq, cert)
    elif cert['status'] == 'infeasible':
        n = len(c)
        if n == 0:
            if not (any(rhs < 0 for rhs in b) or any(rhs != 0 for _, rhs in eq)):
                raise ValueError('False constant infeasibility certificate')
        else:
            rows, rhs = list(A), list(b)
            for row, value in eq:
                rows.extend((row, tuple(-v for v in row))); rhs.extend((value, -value))
            phase = _rational_certificate(cert['phase_I_certificate'])
            if phase.get('status') != 'optimal' or phase.get('objective', F(0)) <= 0:
                raise ValueError('Missing positive Phase-I certificate')
            verify_certificate((F(0),) * n + (F(1),),
                [row + (F(-1),) for row in rows] + [(F(0),) * n + (F(-1),)],
                rhs + [F(0)], (), phase)
    else:
        raise ValueError('Uncertified LP status')
    return cert


@contextmanager
def _certificate_replay(certificates):
    """Fresh-process cold checker: no optimization, no production imports.

    Existing independent enumeration/regime construction is reused; every LP
    call consumes and exactly verifies the next saved certificate. The caller
    must not run this process-local substitution concurrently with another REF.
    """
    from validation.reference5 import lp, solver
    index = 0
    original_lp, original_solver_lp = lp.exact_lp, solver.exact_lp
    def checked(c, A, b, equalities=(), **kwargs):
        nonlocal index
        if index >= len(certificates):
            raise ValueError('Missing saved LP certificate')
        cert = _check_lp(c, A, b, equalities, certificates[index]); index += 1
        return cert
    try:
        lp.exact_lp = solver.exact_lp = checked
        yield
        if index != len(certificates):
            raise ValueError('Unconsumed saved LP certificates')
    finally:
        lp.exact_lp, solver.exact_lp = original_lp, original_solver_lp


def check_reference_evidence(query, leg_bytes, legs_sha256, evidence):
    """Cold-check complete enumeration and LP certificates, without linprog."""
    from validation.reference5.real_input import IndependentLegTable
    from validation.reference5.real_solver import solve_real_case
    if evidence.get('all_regimes_certified') is not True or type(evidence.get('regimes')) is not list:
        raise ValueError('Complete retained REF evidence required')
    fields = ('primary_certificate', 'strict_feasibility_certificate', 'primary_face_certificate',
              'secondary_certificate', 'secondary_face_certificate')
    certs = [row[field] for row in evidence['regimes'] for field in fields if field in row]
    table = IndependentLegTable.from_bytes(leg_bytes, legs_sha256)
    with _certificate_replay(certs):
        checked = solve_real_case(query, table, keep_evidence=True, regime_limit=None)
    if checked.get('all_regimes_certified') is not True:
        raise ValueError('Cold certificate check did not certify every regime')
    # Ignore wall measurement, never a physical/numerical field.
    old, new = dict(evidence), primitive(checked)
    old.pop('elapsed_seconds', None); new.pop('elapsed_seconds', None)
    if old != new:
        raise ValueError('Cold evidence enumeration/result differs')
    return dict(status='VERIFIED', checker='independent_enumeration_plus_existing_exact_lp_checker',
                optimization_invoked=False, regimes_checked=len(evidence['regimes']))
