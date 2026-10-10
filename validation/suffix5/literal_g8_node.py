"""Bounded audit of one checked indexed HIER query's inherited family.

This is an evidence consumer for a genuine CheckedTrace, not a population runner
or a source of original-node domain completeness or global G8 acceptance. The independent convex model/checker
reconstruct every family, suffix word, and arrival band. Existing exact LP
certificates may be supplied; absent certificates are solved only within the
caller's explicit small model and solve budgets.
"""
from __future__ import annotations

from validation.family5.checker import digest, require, wire_equal, _plain
from validation.trace5 import CheckedTrace
from validation.suffix5.convex_checker import check_query_ledger
from validation.suffix5.checker import aggregate_records
from validation.suffix5.convex_evidence import check_query_witness
from validation.suffix5.independent_convex_model import enumerate_words, build_models
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from validation.suffix5.solver import SolveBudget


def reconstruct_node_domain(checked: CheckedTrace, query_seq: int,
                            family_ids: list, actions: list) -> dict:
    """For a checked immutable-leg trace, derive node domain without query fields.

    The layer occurrence binds the exact guarded ancestry roots; the verified
    Region tree and immutable physics bind legal actions. Unsupported traces
    are unresolved rather than silently adopting indexed query fields.
    """
    require('real_input' in checked.summary, 'unsupported_non_real_trace_domain')
    events = checked.snapshot()['events']
    starts = [e for e in events if e['kind'] == 'run_start']
    require(len(starts) == 1, 'missing_original_region_tree')
    groups = [group for e in events if e['kind'] == 'layer_start' and e['seq'] < query_seq
              for group in e['payload']['groups']]
    queries = [e for e in events if e['seq'] == query_seq and e['kind'] == 'query']
    require(len(queries) == 1, 'missing_original_query_event')
    event = queries[0]['payload']
    groups = [group for group in groups if group['group_id'] == event['group_id']]
    require(len(groups) == 1 and groups[0]['families'], 'missing_original_layer_group')
    original_families = groups[0]['families']
    nodes = checked.bundle.snapshot()['nodes']
    states = [nodes[fid]['output']['state'] for fid in original_families]
    require(all(state == states[0] for state in states), 'mixed_group_states')
    def region(node):
        if node['id'] == event['region_id']:
            return node
        matches = [found for child in node['children'] if (found := region(child)) is not None]
        require(len(matches) <= 1, 'ambiguous_original_region')
        return matches[0] if matches else None
    selected = region(starts[0]['payload']['regions'])
    require(selected is not None, 'missing_original_region')
    physics = checked.bundle._physics
    effect = event['effect']
    original_actions = ([] if effect in ('S', 'CS') and not states[0][1] else
                        [[site, effect] for site in selected['members']
                         if physics.anchors[site] != physics.destination and
                         effect in physics.sites[site]])
    require(wire_equal(family_ids, original_families), 'original_ancestry_roots_differ')
    require(wire_equal(actions, original_actions), 'original_region_actions_differ')
    return dict(family_ids=original_families, actions=original_actions,
                region_id=selected['id'], effect=effect, state=states[0])


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
               budget: SolveBudget | None = None, witness: tuple | None = None,
               indexed_only: bool = False) -> dict:
    """Check one exact inherited-family node against its recorded Region bound.

    The result is scoped to this query occurrence. ``ledger`` is optional
    retained evidence, never an authority for model membership. A missing
    ledger requires an explicit numerical budget. No implicit unlimited solve.
    ``max_models`` limits accepted models, not eager enumeration memory/time.
    An empty result may contain certified infeasible models; only
    ``exact_language_empty`` means zero enumerated models.
    """
    require(type(indexed_only) is bool, 'indexed_only_type')
    supported = (checked.summary.get('schema') ==
                 'family5-real-coalesced-hier-trace-check-v2' and
                 'real_input' in checked.summary)
    if not supported and not indexed_only:
        return dict(status='unsupported_original_node_domain', query_seq=query_seq,
                    trace_schema=checked.summary.get('schema'),
                    literal_G8_closed=False)
    require(not indexed_only or not supported,
            'indexed_only_is_for_unsupported_trace_grammar')
    actual = source_pins(checked, query_seq)
    require(type(expected) is dict and set(expected) == set(actual) and
            wire_equal(expected, actual), 'node source/trace/ancestry pins differ')
    require(type(max_models) is int and 0 <= max_models <= 256,
            'small explicit model cap required')
    require(witness is None or type(witness) is tuple and len(witness) == 3,
            'witness must be (slot, evidence, contract)')
    query = next(q for q in checked.export_queries() if q['query_seq'] == query_seq)
    domain = (reconstruct_node_domain(checked, query_seq,
                                     query['family_ids'], query['actions'])
              if supported else None)
    if domain is not None:
        require(query['region_id'] == domain['region_id'] and
                query['effect'] == domain['effect'] and
                wire_equal(query['state'], domain['state']),
                'indexed_query_differs_from_original_node')
    family_ids = domain['family_ids'] if domain is not None else query['family_ids']
    actions = domain['actions'] if domain is not None else query['actions']
    models = []
    try:
        for family_id in family_ids:
            for word in enumerate_words(checked.bundle, family_id, actions):
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
        if models:
            from validation.suffix5.solver import SolveBudget, UnresolvedRegime, solve_model
            require(type(budget) is SolveBudget,
                    'fresh model solving requires explicit SolveBudget')
        records = []
        for slot, model in enumerate(models):
            try:
                records.append(solve_model(model, budget))
            except UnresolvedRegime as error:
                return dict(status='unresolved_solver_budget', query_seq=query_seq,
                            failed_slot=slot, reason=str(error), source=actual,
                            literal_G8_closed=False)
        ledger = dict(schema='family5-suffix-query-ledger-v2', query_seq=query_seq,
                      query_sha256=actual['query_sha256'],
                      trace_sha256=actual['trace_sha256'],
                      models=records, result=aggregate_records(records))
    else:
        require(budget is None, 'retained ledger and fresh solve budget are exclusive')
        require(type(ledger) is dict and ledger.get('query_seq') == query_seq and
                ledger.get('query_sha256') == actual['query_sha256'] and
                ledger.get('trace_sha256') == actual['trace_sha256'],
                'retained ledger belongs to a different query occurrence')
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
    if indexed_only:
        status = 'indexed_' + status
    return dict(schema='hiroute-literal-g8-single-node-audit-v1', status=status,
                query_seq=query_seq, region_id=query['region_id'], effect=query['effect'],
                family_ids=list(query['family_ids']), exact_model_count=len(models),
                exact_language_empty=finding['legal_completion_language_empty'],
                exact_result=checked_result['result'], recorded_bound=query['bound'],
                bound_status=finding['bound_status'], bound_gap=finding['bound_gap'],
                source=actual, physical_witness_checked=witness is not None,
                scope='one_checked_indexed_inherited_family_query',
                literal_G8_closed=False)
