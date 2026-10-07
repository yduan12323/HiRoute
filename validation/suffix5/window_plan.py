"""Pure, bounded work selection over an independently admitted population.

The caller must authenticate the population-plan hash and every *fully*
completed block ID. This module checks structural consistency, not certificates
or admission. A partial block must remain outstanding: its complete span is
selected again, and an executor must cold-check retained proofs before filling
its missing models. No outcomes, attempts, source versions, LPs, or caches enter
selection. Plans describe budgets; they do not enforce execution resources.
"""
from copy import deepcopy

from validation.capture5.containers import detach_json, freeze_shared
from validation.family5.checker import digest
from .block_plan import DEFAULT_BLOCK_SIZE, POLICY as POPULATION_POLICY, block_ranges
from .independent_model import api, exact_json, require, same


SCHEMA = 'suffix5-original-model-window-plan-v1'
POLICY = 'first-32-outstanding-canonical-blocks-v1'
MAX_BLOCKS = 32
MAX_MODELS = 8192
SECONDS = 900
EVIDENCE_BYTES = 512 * 1024**2


def _natural(value):
    require(type(value) is int and value >= 0, 'window_nonnegative_integer_required')


def _sha256(value):
    require(type(value) is str and len(value) == 64
            and all(char in '0123456789abcdef' for char in value), 'window_sha256_required')


def _population(population_plan, population_plan_sha256):
    exact_json(population_plan)
    fields = {'schema', 'policy', 'source_bundle_sha256', 'case_sha256', 'real_input',
              'logical_plan_sha256', 'block_size', 'total_models', 'segments', 'blocks',
              'numerical_acceptance', 'literal_G8_closed'}
    require(type(population_plan) is dict and set(population_plan) == fields,
            'window_population_fields')
    _sha256(population_plan_sha256)
    same(digest(population_plan), population_plan_sha256, 'window_population_hash_changed')
    plan = deepcopy(population_plan)
    same(plan['schema'], 'suffix5-original-model-block-plan-v1', 'window_population_schema')
    same(plan['policy'], POPULATION_POLICY, 'window_population_policy')
    same(plan['block_size'], DEFAULT_BLOCK_SIZE, 'window_requires_canonical_256_model_blocks')
    same(plan['numerical_acceptance'], False, 'window_population_is_not_numerical_authority')
    same(plan['literal_G8_closed'], False, 'window_population_is_not_closure_authority')
    for key in ('source_bundle_sha256', 'case_sha256', 'logical_plan_sha256'):
        _sha256(plan[key])
    require(type(plan['real_input']) is dict, 'window_real_input_mapping_required')
    _natural(plan['total_models'])
    same(plan['blocks'], block_ranges(plan['total_models'], plan['block_size']),
         'window_catalogue_gap_duplicate_foreign_or_changed_span')
    require(type(plan['segments']) is list, 'window_segments_required')
    cursor, keys = 0, set()
    segment_fields = {'segment_id', 'group_index', 'family_id', 'first_action', 'prefix_depth',
                      'start', 'end', 'model_count', 'legal_words', 'graph_exclusions'}
    for position, segment in enumerate(plan['segments']):
        require(type(segment) is dict and set(segment) == segment_fields, 'window_segment_fields')
        for key in segment_fields - {'family_id', 'first_action'}:
            _natural(segment[key])
        require(segment['segment_id'] == position and segment['start'] == cursor
                and segment['end']-cursor == segment['model_count'],
                'window_segment_gap_duplicate_or_changed_span')
        require(type(segment['family_id']) is str, 'window_segment_family_required')
        action = segment['first_action']
        require(type(action) is list and len(action) == 2
                and all(type(value) is str for value in action), 'window_segment_action_required')
        key = (segment['group_index'], tuple(action))
        require(key not in keys, 'window_duplicate_family_action_segment')
        keys.add(key)
        require(segment['graph_exclusions'] <= segment['model_count']
                and segment['legal_words'] <= segment['model_count'], 'window_segment_count_mismatch')
        cursor = segment['end']
    require(cursor == plan['total_models'], 'window_segment_total_changed')
    return plan


def _completed(plan, completed_block_ids):
    # Sets are convenient after joining disjoint authenticated batches. Lists
    # and tuples retain duplicate detection instead of silently normalizing it.
    require(type(completed_block_ids) in (list, tuple, set, frozenset),
            'window_completed_ids_container')
    values = tuple(completed_block_ids)
    for ident in values:
        require(type(ident) is int and 0 <= ident < len(plan['blocks']),
                'window_completed_id_noninteger_or_foreign')
    require(len(values) == len(set(values)), 'window_duplicate_completed_block')
    return sorted(values)


def _binding(plan, population_plan_sha256):
    return dict(block_plan_sha256=population_plan_sha256,
                catalogue_sha256=digest(plan['blocks']),
                logical_plan_sha256=plan['logical_plan_sha256'],
                source_bundle_sha256=plan['source_bundle_sha256'],
                case_sha256=plan['case_sha256'], total_models=plan['total_models'],
                total_blocks=len(plan['blocks']), block_size=plan['block_size'])


def _budget():
    return dict(absolute_seconds=SECONDS, evidence_charge_bytes=EVIDENCE_BYTES,
                uncompressed_archive_bytes=EVIDENCE_BYTES,
                maximum_blocks=MAX_BLOCKS, maximum_models=MAX_MODELS,
                numerical_cache_enabled=False)


def _outstanding(plan, completed):
    complete = set(completed)
    return [block for block in plan['blocks'] if block['block_id'] not in complete]


def _join_ranges(plan, blocks):
    # Preserve full logical segment bounds for query_projection/join_projection;
    # selected intersections never stand in for full certified segment results.
    ranges = []
    for segment in plan['segments']:
        selected = [[max(segment['start'], block['start']), min(segment['end'], block['end'])]
                    for block in blocks
                    if segment['start'] < segment['end']
                    and segment['start'] < block['end'] and block['start'] < segment['end']]
        if selected:
            ranges.append(dict(segment_id=segment['segment_id'], group_index=segment['group_index'],
                               family_id=segment['family_id'], first_action=segment['first_action'],
                               prefix_depth=segment['prefix_depth'], logical_start=segment['start'],
                               logical_end=segment['end'], selected_ranges=selected,
                               selected_model_count=sum(hi-lo for lo, hi in selected)))
    require(sum(row['selected_model_count'] for row in ranges)
            == sum(block['model_count'] for block in blocks), 'window_join_coverage_changed')
    return dict(segments=ranges, requires_authenticated_full_segment_certificates=True,
                preserve_original_query_occurrence_order=True, partial_segments_are_complete=False)


def _window(plan, population_plan_sha256, completed):
    outstanding = _outstanding(plan, completed)
    blocks = outstanding[:MAX_BLOCKS]
    count = sum(block['model_count'] for block in blocks)
    require(count <= MAX_MODELS, 'window_model_budget_exceeded')
    identity = dict(schema=SCHEMA, policy=POLICY, population=_binding(plan, population_plan_sha256),
                    blocks=blocks, block_ids=[block['block_id'] for block in blocks],
                    expected_model_count=count,
                    expected_ordinal_ranges=[[block['start'], block['end']] for block in blocks],
                    operation_budget=_budget())
    return freeze_shared(dict(identity, window_id=digest(identity) if blocks else None,
                              status='ready' if blocks else 'terminal_empty',
                              launch_required=bool(blocks), completed_block_ids=completed,
                              outstanding_block_count=len(outstanding),
                              outstanding_model_count=sum(b['model_count'] for b in outstanding),
                              query_join=_join_ranges(plan, blocks), selection_uses_outcomes=False,
                              numerical_acceptance=False, literal_G8_closed=False))


@api
def next_window(population_plan, completed_block_ids, *, population_plan_sha256):
    """Select the first <=32 outstanding whole blocks in immutable catalogue order.

    Supply ``admitted.population.plan()`` and its independently authenticated
    ``plan_sha256``. The standard 256-model block catalogue is required; the
    population may have any finite size, including zero. Completed IDs may be
    noncontiguous and in any order, but must be unique, exact integers belonging
    to this population. They are caller-authenticated claims, never proofs here.

    The result owns all nested data and is read-only. ``detach_json(result)``
    makes a JSON-compatible copy for persistence. Ranges are half-open original
    logical model ordinals. The ID binds only the population, selected work and
    fixed policy/budget, so retry history, completion batch partition, and source
    version cannot change it. All-completed input returns no runnable window ID.
    """
    plan = _population(population_plan, population_plan_sha256)
    return _window(plan, population_plan_sha256, _completed(plan, completed_block_ids))


@api
def check_window_plan(window, population_plan, completed_block_ids, *, population_plan_sha256):
    """Recompute the exact plan before consuming a persisted window; no admission."""
    actual = detach_json(window)
    exact_json(actual)
    expected = next_window(population_plan, completed_block_ids,
                           population_plan_sha256=population_plan_sha256)
    same(actual, detach_json(expected), 'window_plan_changed')
    return expected


@api
def coverage_plan(population_plan, completed_block_ids, *, population_plan_sha256):
    """Count the deterministic partition if every planned block finishes once.

    These are structural counts, not run-time or certificate-completion claims.
    Interrupted windows can require additional attempts without adding models.
    """
    plan = _population(population_plan, population_plan_sha256)
    completed = _completed(plan, completed_block_ids)
    outstanding = _outstanding(plan, completed)
    windows = []
    for offset in range(0, len(outstanding), MAX_BLOCKS):
        blocks = outstanding[offset:offset+MAX_BLOCKS]
        count = sum(block['model_count'] for block in blocks)
        require(count <= MAX_MODELS, 'window_model_budget_exceeded')
        windows.append(dict(block_ids=[block['block_id'] for block in blocks],
                            expected_ordinal_ranges=[[block['start'], block['end']] for block in blocks],
                            expected_model_count=count))
    complete_count = sum(plan['blocks'][ident]['model_count'] for ident in completed)
    remaining_count = sum(window['expected_model_count'] for window in windows)
    require(complete_count+remaining_count == plan['total_models'], 'window_partition_total_changed')
    return freeze_shared(dict(schema='suffix5-original-model-window-coverage-v1', policy=POLICY,
                              population=_binding(plan, population_plan_sha256),
                              completed_block_ids=completed, completed_model_count=complete_count,
                              remaining_block_count=len(outstanding), remaining_model_count=remaining_count,
                              window_count=len(windows),
                              full_window_count=sum(w['expected_model_count'] == MAX_MODELS for w in windows),
                              final_window_model_count=windows[-1]['expected_model_count'] if windows else 0,
                              windows=windows, operation_budget=_budget(),
                              numerical_acceptance=False, literal_G8_closed=False))
