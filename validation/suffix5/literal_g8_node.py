"""Bounded audit of one original HIER node's inherited continuation family.

This is an evidence consumer for a genuine CheckedTrace, not a population runner
or a source of global G8 acceptance. The independent convex model/checker
reconstruct every family, suffix word, and arrival band. Existing exact LP
certificates may be supplied; absent certificates are solved only within the
caller's explicit small model and solve budgets.
"""
from __future__ import annotations

from validation.family5.checker import digest, require, wire_equal, _plain
from validation.trace5 import CheckedTrace
from validation.suffix5.convex_checker import check_query_ledger
from validation.suffix5.convex_evidence import check_query_witness
from validation.suffix5.independent_convex_model import enumerate_words, build_models
from validation.suffix5.solver import SolveBudget, UnresolvedRegime, solve_model


def source_pins(checked: CheckedTrace, query_seq: int) -> dict:
    """Return pins for review; never infer authority from a retained ledger."""
    require(type(checked) is CheckedTrace and checked.summary['verified'] is True,
            'genuine verified trace required')
    require(type(query_seq) is int and query_seq >= 0, 'exact query sequence required')
    matches = [q for q in checked.queries if q['query_seq'] == query_seq]
    require(len(matches) == 1, 'original node query missing or ambiguous')
    query = matches[0]
    pins = dict(trace_sha256=checked.summary['trace_sha256'],
                bundle_sha256=checked.summary['bundle_sha256'],
                case_sha256=checked.summary['case_sha256'],
                query_sha256=digest(query))
    if 'real_input' in checked.summary:
        pins['real_input'] = _plain(checked.summary['real_input'])
        pins['region_tree_sha256'] = checked.summary['region_tree_sha256']
    return pins


def audit_node(checked: CheckedTrace, query_seq: int, *, expected: dict,
               max_models: int, ledger: dict | None = None,
               budget: SolveBudget | None = None, witness: tuple | None = None) -> dict:
    """Check one exact inherited-family node against its recorded Region bound.

    The result is scoped to this query occurrence. ``ledger`` is optional
    retained evidence, never an authority for model membership. A missing
    ledger requires an explicit numerical budget. No implicit unlimited solve.
    """
    actual = source_pins(checked, query_seq)
    require(type(expected) is dict and set(expected) == set(actual) and
            wire_equal(expected, actual), 'node source/trace/ancestry pins differ')
    require(type(max_models) is int and 0 <= max_models <= 256,
            'small explicit model cap required')
    require(witness is None or type(witness) is tuple and len(witness) == 3,
            'witness must be (slot, evidence, contract)')
    query = next(q for q in checked.export_queries() if q['query_seq'] == query_seq)
    models = []
    try:
        for family_id in query['family_ids']:
            for word in enumerate_words(checked.bundle, family_id, query['actions']):
                for model in build_models(checked.bundle, family_id, word):
                    models.append(model)
                    if len(models) > max_models:
                        return dict(status='unresolved_model_cap', query_seq=query_seq,
                                    model_count_lower_bound=len(models), max_models=max_models,
                                    source=actual, literal_G8_closed=False)
    except ValueError as error:
        return dict(status='unsupported_model_scope', query_seq=query_seq,
                    reason=str(error), source=actual, literal_G8_closed=False)
    if ledger is None:
        require(not models or type(budget) is SolveBudget,
                'fresh model solving requires explicit SolveBudget')
        records = []
        for slot, model in enumerate(models):
            try:
                records.append(solve_model(model, budget))
            except UnresolvedRegime as error:
                return dict(status='unresolved_solver_budget', query_seq=query_seq,
                            failed_slot=slot, reason=str(error), source=actual,
                            literal_G8_closed=False)
        from validation.suffix5.query import aggregate
        ledger = dict(schema='family5-suffix-query-ledger-v2', query_seq=query_seq,
                      query_sha256=actual['query_sha256'],
                      trace_sha256=actual['trace_sha256'],
                      models=records, result=aggregate(records))
    else:
        require(budget is None, 'retained ledger and fresh solve budget are exclusive')
        require(type(ledger) is dict and type(ledger.get('models')) is list and
                len(ledger['models']) == len(models), 'retained ledger lacks exact node model count')
    # Rebuilds every model independently, checks all exact LP certificates,
    # and binds the complete ordered language to the checked trace occurrence.
    checked_result = check_query_ledger(checked, ledger, with_audit=True)
    finding = checked_result['audit']
    if witness is not None:
        require(checked_result['result']['status'] != 'empty_restricted_family',
                'empty node cannot claim a physical witness')
        check_query_witness(checked, ledger, *witness)
    status = ('exact_empty' if checked_result['result']['status'] == 'empty_restricted_family'
              else 'verified_bound' if finding['bound_status'] == 'satisfied'
              else 'bound_counterexample' if finding['bound_status'] == 'violated'
              else 'missing_bound')
    return dict(schema='hiroute-literal-g8-single-node-audit-v1', status=status,
                query_seq=query_seq, region_id=query['region_id'], effect=query['effect'],
                family_ids=list(query['family_ids']), exact_model_count=len(models),
                exact_language_empty=finding['legal_completion_language_empty'],
                exact_result=checked_result['result'], recorded_bound=query['bound'],
                bound_status=finding['bound_status'], bound_gap=finding['bound_gap'],
                source=actual, physical_witness_checked=witness is not None,
                scope='one_original_checked_inherited_family_node',
                literal_G8_closed=False)
