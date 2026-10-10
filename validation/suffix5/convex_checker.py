"""Exact v2 convex suffix acceptance; no candidate or optimizer imports.

The existing rational primal/dual verifier and finite-union result algebra are
reused unchanged. Every convex semantic row and ordered band slot is rebuilt
independently before those certificates are considered.
"""
from fractions import Fraction as F

from .independent_convex_model import (SuffixVerificationError, api, build_model,
    build_models, closed_task, strict_task, exact_json, require, same, rational,
    enumerate_words)
from .checker import verify_lp_certificate, aggregate_records, _bound_audit


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
    model = build_model(ctx, supplied['family_id'], supplied['word'], supplied['arrival_bands'])
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


@api
def check_query_ledger(checked_trace, ledger, *, with_audit=False):
    """Bind every record to the entire exact original public query language."""
    from validation.trace5 import CheckedTrace
    from validation.family5.checker import digest, _plain

    require(type(checked_trace) is CheckedTrace, 'requires_trusted_CheckedTrace')
    require(type(with_audit) is bool, 'with_audit_type')
    exact_json(ledger)
    fields = {'schema', 'query_seq', 'query_sha256', 'trace_sha256', 'models', 'result'}
    require(type(ledger) is dict and set(ledger) == fields, 'query_ledger_fields')
    same(ledger['schema'], 'family5-suffix-query-ledger-v2', 'query_ledger_schema')
    sequence = ledger['query_seq']
    require(type(sequence) is int and sequence >= 0, 'query_sequence_type')
    queries = [q for q in checked_trace.queries if q['query_seq'] == sequence]
    require(len(queries) == 1, 'query_not_in_original_checked_population')
    query = _plain(queries[0])
    same(ledger['query_sha256'], digest(query), 'original_query_digest_mismatch')
    same(ledger['trace_sha256'], checked_trace.summary['trace_sha256'], 'original_trace_digest_mismatch')
    require(type(ledger['models']) is list, 'ledger_models_type')
    expected = [model for family_id in query['family_ids']
                for word in enumerate_words(checked_trace.bundle, family_id, query['actions'])
                for model in build_models(checked_trace.bundle, family_id, word)]
    require(len(ledger['models']) == len(expected), 'ledger_exact_regime_count')
    regimes = []
    for record, model in zip(ledger['models'], expected):
        require(type(record) is dict and type(record.get('model')) is dict, 'ledger_regime_type')
        same(record['model'], model, 'ledger_original_family_word_band_or_order')
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
