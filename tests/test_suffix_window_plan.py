"""Deterministic complete catalogue coverage; no LP, server, or certificates."""
from copy import deepcopy
from itertools import chain
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from validation.capture5.containers import detach_json
from validation.family5.checker import digest
from validation.suffix5.block_plan import POLICY as POPULATION_POLICY, block_ranges
from validation.suffix5.window_plan import check_window_plan, coverage_plan, next_window


SEEDS = [0, 1352, 2535, 2687]


def population(total=695712, sizes=None):
    """Structural test data only; a hash of it does not establish admission."""
    sizes = [total] if sizes is None else sizes
    segments, cursor = [], 0
    for ident, size in enumerate(sizes):
        segments.append(dict(segment_id=ident, group_index=ident, family_id=f'family-{ident}',
                             first_action=[f'site-{ident}', 'C'], prefix_depth=ident % 4,
                             start=cursor, end=cursor+size, model_count=size,
                             legal_words=size, graph_exclusions=0))
        cursor += size
    return dict(schema='suffix5-original-model-block-plan-v1', policy=POPULATION_POLICY,
                source_bundle_sha256='a'*64, case_sha256='b'*64, real_input={'synthetic': True},
                logical_plan_sha256='c'*64, block_size=256, total_models=total,
                segments=segments, blocks=block_ranges(total), numerical_acceptance=False,
                literal_G8_closed=False)


def window(plan, completed=()):
    return next_window(plan, completed, population_plan_sha256=digest(plan))


class WindowPlanTests(unittest.TestCase):
    def test_first_authorized_window_and_fixed_budgets(self):
        plan = population()
        result = window(plan, SEEDS)
        self.assertEqual(result['block_ids'], tuple(range(1, 33)))
        self.assertEqual(result['expected_model_count'], 8192)
        self.assertEqual(detach_json(result['blocks']), plan['blocks'][1:33])
        self.assertEqual(result['expected_ordinal_ranges'],
                         tuple((i*256, (i+1)*256) for i in range(1, 33)))
        self.assertEqual(result['operation_budget'], dict(
            absolute_seconds=900, evidence_charge_bytes=512*1024**2,
            uncompressed_archive_bytes=512*1024**2,
            maximum_blocks=32, maximum_models=8192, numerical_cache_enabled=False))
        self.assertEqual(result['population']['block_plan_sha256'], digest(plan))
        self.assertEqual(result['population']['catalogue_sha256'], digest(plan['blocks']))
        self.assertEqual(result['population']['logical_plan_sha256'], plan['logical_plan_sha256'])
        self.assertEqual(result['status'], 'ready')
        self.assertTrue(result['launch_required'])
        self.assertFalse(result['selection_uses_outcomes'])
        self.assertFalse(result['numerical_acceptance'])
        self.assertFalse(result['literal_G8_closed'])

    def test_coverage_counts_are_derived_and_exact(self):
        plan = population()
        result = coverage_plan(plan, SEEDS, population_plan_sha256=digest(plan))
        self.assertEqual(result['completed_model_count'], 1024)
        self.assertEqual(result['remaining_block_count'], 2714)
        self.assertEqual(result['remaining_model_count'], 694688)
        self.assertEqual(result['window_count'], 85)
        self.assertEqual(result['full_window_count'], 84)
        self.assertEqual(result['final_window_model_count'], 6560)
        self.assertEqual([w['expected_model_count'] for w in result['windows']],
                         [8192]*84+[6560])
        self.assertEqual(result['windows'][-1]['block_ids'], tuple(range(2692, 2718)))
        self.assertEqual(sum(w['expected_model_count'] for w in result['windows'])+1024, 695712)

    def test_progressive_full_coverage_has_no_missing_duplicate_or_extra_ordinal(self):
        plan = population()
        completed = list(SEEDS)
        seen = bytearray(plan['total_models'])

        def admit_blocks(blocks):
            for block in blocks:
                for ordinal in range(block['start'], block['end']):
                    self.assertEqual(seen[ordinal], 0)
                    seen[ordinal] = 1

        admit_blocks([plan['blocks'][ident] for ident in completed])
        expected = coverage_plan(plan, completed, population_plan_sha256=digest(plan))
        ids = []
        for row in expected['windows']:
            selected = window(plan, completed)
            self.assertEqual(selected['block_ids'], row['block_ids'])
            self.assertEqual(selected['expected_model_count'], row['expected_model_count'])
            self.assertEqual(selected['expected_ordinal_ranges'], row['expected_ordinal_ranges'])
            self.assertNotIn(selected['window_id'], ids)
            ids.append(selected['window_id'])
            admit_blocks(selected['blocks'])
            completed.extend(selected['block_ids'])
        self.assertEqual(len(ids), 85)
        self.assertEqual(sum(seen), 695712)
        self.assertEqual(sorted(completed), list(range(2718)))
        terminal = window(plan, completed)
        self.assertEqual(terminal['status'], 'terminal_empty')
        self.assertFalse(terminal['launch_required'])
        self.assertIsNone(terminal['window_id'])
        self.assertEqual(terminal['blocks'], ())
        self.assertEqual(terminal['expected_ordinal_ranges'], ())
        self.assertEqual(terminal['expected_model_count'], 0)
        self.assertEqual(terminal['outstanding_block_count'], 0)
        self.assertEqual(terminal['outstanding_model_count'], 0)

    def test_completed_order_and_receipt_partition_do_not_change_plan(self):
        plan = population()
        expected = window(plan, SEEDS)
        batches = [[[0], [1352], [2535], [2687]], [[2687, 1352], [0, 2535]],
                   [list(reversed(SEEDS))], [[], SEEDS, []]]
        for partitions in batches:
            completed = list(chain.from_iterable(partitions))
            self.assertEqual(window(plan, completed), expected)
            self.assertEqual(window(plan, tuple(completed)), expected)
            self.assertEqual(window(plan, set(completed)), expected)
            self.assertEqual(window(plan, frozenset(completed)), expected)
        # Unrelated later completion alters progress bookkeeping, not this ID.
        self.assertEqual(window(plan, SEEDS+[100])['window_id'], expected['window_id'])
        # There is no attempt/source-version input to contaminate a retry ID.
        for attempt, source_version in (('first', 'v1'), ('retry', 'v2')):
            envelope = dict(attempt=attempt, source_version=source_version,
                            selection=detach_json(window(plan, SEEDS)))
            self.assertEqual(envelope['selection']['window_id'], expected['window_id'])

    def test_every_partial_block_remains_whole_and_outstanding(self):
        plan = population(1000)
        partial_ordinals = [256, 257, 259]  # Never passed as completed block IDs.
        result = window(plan, [0])
        self.assertEqual(result['block_ids'], (1, 2, 3))
        self.assertEqual(result['blocks'][0], plan['blocks'][1])
        self.assertTrue(set(partial_ordinals) <= set(range(*result['expected_ordinal_ranges'][0])))
        with self.assertRaises(ValueError):
            window(plan, [dict(block_id=1, completed_models=partial_ordinals)])

    def test_last_partial_block_is_exact(self):
        plan = population()
        result = window(plan, list(range(2717)))
        self.assertEqual(result['block_ids'], (2717,))
        self.assertEqual(result['blocks'][0], dict(block_id=2717, start=695552,
                                                 end=695712, model_count=160))
        self.assertEqual(result['expected_model_count'], 160)
        self.assertEqual(result['expected_ordinal_ranges'], ((695552, 695712),))

    def test_empty_population_is_terminal_and_has_no_windows(self):
        plan = population(0, [])
        selected = window(plan)
        self.assertEqual(selected['status'], 'terminal_empty')
        self.assertIsNone(selected['window_id'])
        self.assertEqual(selected['query_join']['segments'], ())
        coverage = coverage_plan(plan, [], population_plan_sha256=digest(plan))
        self.assertEqual(coverage['window_count'], 0)
        self.assertEqual(coverage['full_window_count'], 0)
        self.assertEqual(coverage['final_window_model_count'], 0)
        self.assertEqual(coverage['windows'], ())

    def test_missing_duplicate_reordered_spurious_and_foreign_catalogue_blocks_reject(self):
        plan = population(1000)
        mutations = [lambda p: p['blocks'].pop(1),
                     lambda p: p['blocks'].append(deepcopy(p['blocks'][0])),
                     lambda p: p['blocks'].reverse(),
                     lambda p: p['blocks'][1].update(block_id=99),
                     lambda p: p['blocks'][1].update(block_id=True),
                     lambda p: p['blocks'][1].update(block_id=1.0),
                     lambda p: p['blocks'][1].update(start=255),
                     lambda p: p['blocks'][1].update(end=511),
                     lambda p: p['blocks'][1].update(model_count=255),
                     lambda p: p['blocks'][1].update(extra='spurious'),
                     lambda p: p.update(total_models=999),
                     lambda p: p.update(total_models=True),
                     lambda p: p.update(block_size=128)]
        for mutate in mutations:
            bad = deepcopy(plan)
            mutate(bad)
            with self.subTest(plan=bad), self.assertRaises(ValueError):
                window(bad)

    def test_bad_completed_ids_reject_but_legitimate_gaps_are_allowed(self):
        plan = population(1000)
        for completed in ([0, 0], [1, True], [1.0], ['1'], [-1], [4], [2717],
                          [None], {1: True}, '1', None):
            with self.subTest(completed=completed), self.assertRaises(ValueError):
                window(plan, completed)
        self.assertEqual(window(plan, [3, 0])['block_ids'], (1, 2))

    def test_stale_population_hash_and_identity_changes_reject(self):
        original = population(1000)
        for mutate in (lambda p: p.update(source_bundle_sha256='d'*64),
                       lambda p: p.update(case_sha256='d'*64),
                       lambda p: p.update(logical_plan_sha256='d'*64),
                       lambda p: p['real_input'].update(synthetic=False),
                       lambda p: p['segments'][0].update(family_id='foreign')):
            bad = deepcopy(original)
            mutate(bad)
            with self.assertRaisesRegex(ValueError, 'population_hash_changed'):
                next_window(bad, [], population_plan_sha256=digest(original))
        for pin in (None, 7, 'a', 'G'*64, 'a'*63):
            with self.assertRaises(ValueError):
                next_window(original, [], population_plan_sha256=pin)
        changed = deepcopy(original)
        changed['logical_plan_sha256'] = 'd'*64
        self.assertNotEqual(window(original)['window_id'], window(changed)['window_id'])

    def test_segment_gaps_duplicates_counts_and_bad_types_reject(self):
        plan = population(1000, [300, 0, 700])
        mutations = [lambda p: p['segments'].pop(0),
                     lambda p: p['segments'].reverse(),
                     lambda p: p['segments'][1].update(segment_id=0),
                     lambda p: p['segments'][0].update(end=299),
                     lambda p: p['segments'][2].update(start=301),
                     lambda p: p['segments'][2].update(model_count=701),
                     lambda p: p['segments'][0].update(model_count=True),
                     lambda p: p['segments'][0].update(legal_words=301),
                     lambda p: p['segments'][0].update(graph_exclusions=301),
                     lambda p: p['segments'][0].update(prefix_depth=-1),
                     lambda p: p['segments'][0].update(first_action=['site']),
                     lambda p: p['segments'][0].update(unexpected=True)]
        for mutate in mutations:
            bad = deepcopy(plan)
            mutate(bad)
            with self.subTest(plan=bad), self.assertRaises(ValueError):
                window(bad)
        self.assertEqual([s['segment_id'] for s in window(plan)['query_join']['segments']], [0, 2])

    def test_results_are_recursively_immutable_and_detached(self):
        plan, completed = population(1000), [0]
        result = window(plan, completed)
        saved = detach_json(result)
        completed.append(1)
        plan['blocks'][1]['start'] = 99
        plan['segments'][0]['first_action'][0] = 'foreign'
        self.assertEqual(detach_json(result), saved)
        with self.assertRaises(TypeError):
            result['expected_model_count'] = 0
        with self.assertRaises(TypeError):
            result['blocks'][0]['start'] = 99
        with self.assertRaises(TypeError):
            result['query_join']['segments'][0]['first_action'][0] = 'foreign'
        saved['blocks'][0]['start'] = 77
        self.assertEqual(result['blocks'][0]['start'], 256)
        coverage = coverage_plan(population(1000), [], population_plan_sha256=digest(population(1000)))
        with self.assertRaises(TypeError):
            coverage['windows'][0]['expected_model_count'] = 0

    def test_persisted_window_spans_totals_ids_budgets_and_join_metadata_recheck(self):
        plan = population(1000, [300, 700])
        original = window(plan, [0])
        self.assertEqual(check_window_plan(original, plan, [0], population_plan_sha256=digest(plan)), original)
        self.assertEqual(check_window_plan(detach_json(original), plan, [0],
                                           population_plan_sha256=digest(plan)), original)
        mutations = [lambda w: w['blocks'].pop(),
                     lambda w: w['block_ids'].append(99),
                     lambda w: w['blocks'][0].update(start=257),
                     lambda w: w.update(expected_model_count=743),
                     lambda w: w['expected_ordinal_ranges'][0].__setitem__(1, 511),
                     lambda w: w.update(window_id='0'*64),
                     lambda w: w['operation_budget'].update(maximum_blocks=33),
                     lambda w: w['operation_budget'].update(numerical_cache_enabled=True),
                     lambda w: w['query_join']['segments'][0].update(logical_end=299),
                     lambda w: w.update(numerical_acceptance=True)]
        for mutate in mutations:
            bad = detach_json(original)
            mutate(bad)
            with self.subTest(window=bad), self.assertRaises(ValueError):
                check_window_plan(bad, plan, [0], population_plan_sha256=digest(plan))

    def test_query_join_metadata_uses_global_segment_bounds_and_only_selected_intersections(self):
        plan = population(1000, [300, 0, 700])
        joined = detach_json(window(plan, [0, 2])['query_join'])
        first, second = joined['segments']
        self.assertEqual((first['segment_id'], first['logical_start'], first['logical_end']), (0, 0, 300))
        self.assertEqual(first['selected_ranges'], [[256, 300]])
        self.assertEqual(first['selected_model_count'], 44)
        self.assertEqual((second['segment_id'], second['logical_start'], second['logical_end']), (2, 300, 1000))
        self.assertEqual(second['selected_ranges'], [[300, 512], [768, 1000]])
        self.assertEqual(second['selected_model_count'], 444)
        self.assertTrue(joined['requires_authenticated_full_segment_certificates'])
        self.assertTrue(joined['preserve_original_query_occurrence_order'])
        self.assertFalse(joined['partial_segments_are_complete'])

    def test_genuine_population_projection_is_compatible_with_existing_query_join(self):
        from tests import test_real_model_preview as fixtures
        from experiments.time_cut_v2.recorded_real import indexed_population as admitted, plan as binding
        from validation.real5_v2.family import verify_bundle
        from validation.suffix5.aggregate_stream import summarize_records
        from validation.suffix5.occurrence_join import join_projection

        fx = fixtures.ModelPreview()
        fx.setUp()
        self.addCleanup(fx.doCleanups)
        _, trusted, index, logical, path, _ = fx.inputs()
        ctx = verify_bundle(binding.load(path)['bundle'], trusted)
        anchors = {'capture_sha256': index['capture_sha256']}
        with patch.object(admitted.suffix_census, 'completed_inputs', return_value=(index, trusted, {}, anchors)), \
                patch.object(admitted.model_preview, 'logical_input', return_value=logical):
            admitted_population = admitted.admit_population(fx.root, SimpleNamespace(), ctx, time.monotonic()+10)
        pop = admitted_population.population
        selected = next_window(pop.plan(), [], population_plan_sha256=pop.plan_sha256)
        metadata = {s['segment_id']: s for s in selected['query_join']['segments']}
        # This tiny fixture fits one window; synthetic excluded summaries test
        # only arithmetic compatibility, never claim actual model certificates.
        self.assertEqual(selected['expected_model_count'], pop.plan()['total_models'])
        summaries = {}
        for segment in pop.plan()['segments']:
            count = segment['model_count']
            if count:
                data = metadata[segment['segment_id']]
                self.assertEqual((data['logical_start'], data['logical_end']),
                                 (segment['start'], segment['end']))
                self.assertEqual(data['selected_model_count'], count)
            summaries[segment['segment_id']] = dict(segment_id=segment['segment_id'],
                complete_certificates=True, aggregate=summarize_records(
                    [dict(result=dict(status='closed_infeasible')) for _ in range(count)], start=segment['start']))
        for ident in admitted_population.query_ids():
            projection = admitted_population.query_projection(ident)
            for span in projection['ranges']:
                if span['logical_start'] < span['logical_end']:
                    segment = metadata[span['segment_id']]
                    self.assertEqual((span['logical_start'], span['logical_end']),
                                     (segment['logical_start'], segment['logical_end']))
            result = join_projection(projection, summaries)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['aggregate']['end'], projection['model_slots'])
            self.assertEqual(result['projection'], projection)


if __name__ == '__main__':
    unittest.main()
