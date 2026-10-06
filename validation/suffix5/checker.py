"""Exact restricted-suffix acceptance, independent of every LP optimizer.

All matrices and faces are independently reconstructed.  The recorded primal
and dual vectors are proof witnesses, never solver status assertions.  Infeasible
tasks need an independently reconstructed positive Phase-I optimum.
"""
from fractions import Fraction as F
import json

from .independent_model import (SuffixVerificationError, api, build_model,
    closed_task, strict_task, exact_json, require, same, rational, enumerate_words)


def _vector(value, length, reason):
    require(type(value) is list and len(value) == length, reason)
    return [rational(x) for x in value]


def _task(value):
    require(type(value) is dict and set(value) == {'c', 'A', 'b', 'equalities'}, 'LP_task_fields')
    require(type(value['c']) is list and type(value['A']) is list
            and type(value['b']) is list and type(value['equalities']) is list, 'LP_task_containers')
    n = len(value['c'])
    c = _vector(value['c'], n, 'LP_objective_dimension')
    A = [_vector(row, n, 'LP_inequality_dimension') for row in value['A']]
    b = _vector(value['b'], len(A), 'LP_rhs_dimension')
    equalities = []
    for pair in value['equalities']:
        require(type(pair) is list and len(pair) == 2, 'LP_equality_pair')
        equalities.append((_vector(pair[0], n, 'LP_equality_dimension'), rational(pair[1])))
    return c, A, b, equalities


def _dot(left, right):
    require(len(left) == len(right), 'dot_dimension')
    return sum((a*b for a, b in zip(left, right)), F(0))


def _metadata(certificate, inequality_count):
    if 'exact_primal_dual_verified' in certificate:
        same(certificate['exact_primal_dual_verified'], True, 'invalid_backend_verified_annotation')
    recovery = {'candidate_recovery', 'recovery_inequality_rows', 'recovery_dual_support'}
    present = recovery.intersection(certificate)
    require(not present or present == recovery, 'partial_backend_recovery_annotation')
    if present:
        same(certificate['candidate_recovery'], 'exact_active_constraints', 'unknown_backend_recovery')
        for name in ('recovery_inequality_rows', 'recovery_dual_support'):
            values = certificate[name]
            require(type(values) is list and all(type(i) is int and 0 <= i < inequality_count for i in values),
                    'backend_recovery_index_type_or_range')
            require(len(values) == len(set(values)), 'duplicate_backend_recovery_index')
    if 'initial_candidate_failure' in certificate:
        require(present and type(certificate['initial_candidate_failure']) is str,
                'invalid_backend_failure_annotation')


def _optimal(c, A, b, equalities, certificate):
    required = {'status', 'x', 'objective', 'inequality_dual', 'equality_dual'}
    optional = {'exact_primal_dual_verified', 'candidate_recovery', 'recovery_inequality_rows',
                'recovery_dual_support', 'initial_candidate_failure'}
    require(type(certificate) is dict and required <= set(certificate)
            and set(certificate) <= required | optional, 'optimal_certificate_fields')
    same(certificate['status'], 'optimal', 'not_an_optimal_certificate')
    _metadata(certificate, len(A))
    n = len(c)
    x = _vector(certificate['x'], n, 'primal_dimension')
    y = _vector(certificate['inequality_dual'], len(A), 'inequality_dual_dimension')
    z = _vector(certificate['equality_dual'], len(equalities), 'equality_dual_dimension')
    objective = rational(certificate['objective'])
    require(all(_dot(row, x) <= rhs for row, rhs in zip(A, b)), 'primal_inequality_infeasible')
    require(all(_dot(row, x) == rhs for row, rhs in equalities), 'primal_equality_infeasible')
    require(all(value <= 0 for value in y), 'wrong_inequality_dual_sign')
    for j in range(n):
        combined = sum((row[j]*dual for row, dual in zip(A, y)), F(0))
        combined += sum((row[j]*dual for (row, _), dual in zip(equalities, z)), F(0))
        require(combined == c[j], 'dual_stationarity_failure')
    primal = _dot(c, x)
    dual = _dot(b, y)+_dot([rhs for _, rhs in equalities], z)
    require(primal == objective and dual == objective, 'strong_duality_failure')
    return dict(status='optimal', objective=str(objective), x=list(map(str, x)))


@api
def verify_lp_certificate(task, certificate):
    """Accept an exact primal/dual or exact Phase-I proof; never run an LP."""
    exact_json(task)
    exact_json(certificate)
    c, A, b, equalities = _task(task)
    require(type(certificate) is dict and type(certificate.get('status')) is str,
            'LP_certificate_status')
    if certificate['status'] == 'optimal':
        return _optimal(c, A, b, equalities, certificate)
    same(certificate['status'], 'infeasible', 'unsupported_LP_status')
    if not c and set(certificate) == {'status', 'constant_constraints_verified'}:
        same(certificate['constant_constraints_verified'], True, 'constant_certificate_flag')
        require(any(rhs < 0 for rhs in b) or any(rhs != 0 for _, rhs in equalities),
                'constant_constraints_are_feasible')
        return dict(status='infeasible')
    require(set(certificate) == {'status', 'phase_I_certificate'}, 'infeasible_certificate_fields')
    # A single common nonnegative violation variable relaxes all inequalities,
    # including both signs of every equality.  A positive proved minimum
    # excludes a feasible point of the original closed task.
    phase_A, phase_b = [], []
    for row, rhs in zip(A, b):
        phase_A.append(row+[F(-1)])
        phase_b.append(rhs)
    for row, rhs in equalities:
        phase_A.extend([row+[F(-1)], [-value for value in row]+[F(-1)]])
        phase_b.extend([rhs, -rhs])
    phase_A.append([F(0)]*len(c)+[F(-1)])
    phase_b.append(F(0))
    phase = _optimal([F(0)]*len(c)+[F(1)], phase_A, phase_b, [], certificate['phase_I_certificate'])
    require(F(phase['objective']) > 0, 'nonpositive_Phase_I_optimum')
    return dict(status='infeasible', phase_I_objective=phase['objective'])


@api
def check_regime(ctx, record, *, with_audit=False):
    """Verify one original-family word, returning its independently derived result.

The caller binds family_id and word to the intended query.  The query-ledger
checker must additionally prove exhaustive ordered word coverage.  An optional
audit returns validated named primal points for physical-witness binding.
"""
    require(type(with_audit) is bool, 'with_audit_type')
    exact_json(record)
    require(type(record) is dict and set(record) == {'model', 'stages', 'result'}, 'regime_record_fields')
    supplied = record['model']
    require(type(supplied) is dict, 'regime_model_type')
    model = build_model(ctx, supplied['family_id'], supplied['word'])
    same(supplied, model, 'independent_semantic_model_mismatch')
    require(type(record['stages']) is list, 'regime_stages_type')
    cursor = 0
    audited = []
    faces = []

    def stage(name, task, *, optimal=False):
        nonlocal cursor
        require(cursor < len(record['stages']), 'missing_required_stage:'+name)
        evidence = record['stages'][cursor]
        require(type(evidence) is dict and set(evidence) == {'name', 'task', 'certificate'}, 'stage_fields')
        same(evidence['name'], name, 'stage_name_or_order_mismatch')
        same(evidence['task'], task, 'independent_stage_task_mismatch:'+name)
        outcome = verify_lp_certificate(task, evidence['certificate'])
        if optimal:
            same(outcome['status'], 'optimal', 'feasible_face_claimed_infeasible:'+name)
        audited.append(dict(name=name, **outcome))
        cursor += 1
        return outcome

    def finish(status, **values):
        expected = dict(status=status, **values)
        require(cursor == len(record['stages']), 'extra_regime_stages')
        same(record['result'], expected, 'independently_derived_result_mismatch')
        if with_audit:
            return dict(result=expected, audit=dict(stages=audited, faces=faces))
        return expected

    if model['exclusion'] is not None:
        return finish('graph_unreachable')
    feasible = stage('feasibility', strict_task(model))
    if feasible['status'] == 'infeasible':
        return finish('closed_infeasible')
    require(F(feasible['objective']) <= 0, 'impossible_negative_strict_margin')
    if F(feasible['objective']) == 0:
        return finish('strict_infeasible')
    primary = stage('primary', closed_task(model, 'J'), optimal=True)
    J = str(F(primary['objective'])+F(model['lp']['J']['constant']))
    faces.append([list(model['lp']['J']['coefficients']), primary['objective']])
    primary_face = stage('primary_attainment', strict_task(model, faces), optimal=True)
    require(F(primary_face['objective']) <= 0, 'impossible_primary_face_margin')
    if F(primary_face['objective']) == 0:
        return finish('primary_unattained', primary_infimum=J)
    secondary = stage('secondary', closed_task(model, 'Q', faces), optimal=True)
    Q = str(F(secondary['objective'])+F(model['lp']['Q']['constant']))
    faces.append([list(model['lp']['Q']['coefficients']), secondary['objective']])
    secondary_face = stage('secondary_attainment', strict_task(model, faces), optimal=True)
    require(F(secondary_face['objective']) <= 0, 'impossible_secondary_face_margin')
    if F(secondary_face['objective']) == 0:
        return finish('secondary_unattained', J=J, secondary_infimum=Q)
    return finish('attained_optimum', J=J, Q_total=Q, H=model['H'],
                  site_action_tuple=model['pi'], lex_key=[J, Q, model['H'], model['pi']])


def _result(row):
    """Parse the small result algebra, independently of candidate annotations."""
    require(type(row) is dict, 'aggregate_result_type')
    fields = {
        'graph_unreachable': {'status'}, 'closed_infeasible': {'status'}, 'strict_infeasible': {'status'},
        'primary_unattained': {'status', 'primary_infimum'},
        'secondary_unattained': {'status', 'J', 'secondary_infimum'},
        'attained_optimum': {'status', 'J', 'Q_total', 'H', 'site_action_tuple', 'lex_key'}}
    status = row.get('status')
    require(type(status) is str and status in fields and set(row) == fields[status], 'aggregate_result_fields')
    if status in ('graph_unreachable', 'closed_infeasible', 'strict_infeasible'):
        return None
    J = rational(row['primary_infimum'] if status == 'primary_unattained' else row['J'])
    if status == 'primary_unattained':
        return J, None, None
    Q = rational(row['secondary_infimum'] if status == 'secondary_unattained' else row['Q_total'])
    if status == 'secondary_unattained':
        return J, Q, None
    H, pi = row['H'], row['site_action_tuple']
    require(type(H) is int and H >= 0 and type(pi) is list and len(pi) == H, 'aggregate_H_or_pi_type')
    require(all(type(a) is list and len(a) == 2 and type(a[0]) is str
                and type(a[1]) is str and a[1] in ('C', 'S', 'CS') for a in pi), 'aggregate_pi_action')
    same(row['lex_key'], [str(J), str(Q), H, pi], 'aggregate_lex_key')
    return J, Q, (H, tuple(map(tuple, pi)))


@api
def aggregate_records(records, *, with_audit=False):
    """Aggregate already verified records, taking Q only on attained J faces.

This arithmetic combinator does not certify its inputs.  A public ledger must
call check_regime for each independently enumerated original family/word first.
"""
    require(type(with_audit) is bool, 'with_audit_type')
    exact_json(records)
    require(type(records) is list, 'aggregate_records_type')
    candidates = []
    for i, record in enumerate(records):
        require(type(record) is dict and 'result' in record, 'aggregate_record_result_missing')
        parsed = _result(record['result'])
        if parsed is not None:
            candidates.append((i, *parsed))
    audit = dict(primary_tied_regimes=[], secondary_tied_regimes=[], winning_regimes=[],
                 exclusion_counts={status: sum(record['result']['status'] == status for record in records)
                                   for status in ('graph_unreachable', 'closed_infeasible', 'strict_infeasible')})
    if not candidates:
        result = dict(status='empty_restricted_family')
    else:
        J = min(row[1] for row in candidates)
        primary = [row for row in candidates if row[1] == J]
        audit['primary_tied_regimes'] = [row[0] for row in primary]
        attained_J = [row for row in primary if row[2] is not None]
        if not attained_J:
            result = dict(status='primary_unattained', primary_infimum=str(J))
        else:
            Q = min(row[2] for row in attained_J)
            secondary = [row for row in attained_J if row[2] == Q]
            audit['secondary_tied_regimes'] = [row[0] for row in secondary]
            attained_Q = [row for row in secondary if row[3] is not None]
            if not attained_Q:
                result = dict(status='secondary_unattained', J=str(J), secondary_infimum=str(Q))
            else:
                key = min(row[3] for row in attained_Q)
                winners = [row[0] for row in attained_Q if row[3] == key]
                audit['winning_regimes'] = winners
                result = json.loads(json.dumps(records[winners[0]]['result']))
    return dict(result=result, audit=audit) if with_audit else result


def _bound_audit(bound, result):
    """Report a valid counterexample without discarding its exact proof."""
    if result['status'] == 'empty_restricted_family':
        return dict(bound_valid=True, bound_status='vacuous_empty_restricted_family',
                    bound_gap=None, recorded_bound=bound, primary_infimum=None)
    infimum = result['primary_infimum'] if result['status'] == 'primary_unattained' else result['J']
    if bound is None:
        return dict(bound_valid=False, bound_status='missing_bound_for_nonempty_family',
                    bound_gap=None, recorded_bound=None, primary_infimum=infimum)
    gap = rational(infimum)-rational(bound)
    return dict(bound_valid=gap >= 0, bound_status='satisfied' if gap >= 0 else 'violated',
                bound_gap=str(gap), recorded_bound=bound, primary_infimum=infimum)


@api
def check_query_ledger(checked_trace, ledger, *, with_audit=False):
    """Bind every record to the entire exact original public query language."""
    from validation.trace5 import CheckedTrace
    from validation.family5.checker import digest

    require(type(checked_trace) is CheckedTrace, 'requires_trusted_CheckedTrace')
    require(type(with_audit) is bool, 'with_audit_type')
    exact_json(ledger)
    fields = {'schema', 'query_seq', 'query_sha256', 'trace_sha256', 'models', 'result'}
    require(type(ledger) is dict and set(ledger) == fields, 'query_ledger_fields')
    same(ledger['schema'], 'family5-suffix-query-ledger-v1', 'query_ledger_schema')
    sequence = ledger['query_seq']
    require(type(sequence) is int and sequence >= 0, 'query_sequence_type')
    queries = [q for q in checked_trace.export_queries() if q['query_seq'] == sequence]
    require(len(queries) == 1, 'query_not_in_original_checked_population')
    query = queries[0]
    same(ledger['query_sha256'], digest(query), 'original_query_digest_mismatch')
    same(ledger['trace_sha256'], checked_trace.summary['trace_sha256'], 'original_trace_digest_mismatch')
    require(type(ledger['models']) is list, 'ledger_models_type')
    expected = [(family_id, word) for family_id in query['family_ids']
                for word in enumerate_words(checked_trace.bundle, family_id, query['actions'])]
    require(len(ledger['models']) == len(expected), 'ledger_exact_regime_count')
    regimes = []
    for record, (family_id, word) in zip(ledger['models'], expected):
        require(type(record) is dict and type(record.get('model')) is dict, 'ledger_regime_type')
        same(record['model'].get('family_id'), family_id, 'ledger_original_family_or_order')
        same(record['model'].get('word'), word, 'ledger_original_word_or_order')
        regimes.append(check_regime(checked_trace.bundle, record, with_audit=True))
    aggregate = aggregate_records(regimes, with_audit=True)
    same(ledger['result'], aggregate['result'], 'ledger_independent_aggregate_mismatch')
    if with_audit:
        return dict(result=aggregate['result'], audit=dict(
            query_seq=sequence, regime_count=len(expected), regimes=regimes,
            original_query_classification=query['classification'],
            legal_completion_language_empty=not expected,
            **aggregate['audit'], **_bound_audit(query['bound'], aggregate['result'])))
    return aggregate['result']
