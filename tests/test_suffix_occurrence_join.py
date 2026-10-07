"""Tiny independent differential joins; synthetic results only, no LP/server."""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import unittest
from unittest.mock import patch

from validation.suffix5.aggregate_stream import EXCLUSIONS, RANGES, summarize_records
from validation.suffix5.checker import _bound_audit, aggregate_records
from validation.suffix5.independent_model import SuffixVerificationError
from validation.suffix5.occurrence_join import join_projection


def attained(J='7/3', Q='5/7', pi=None):
    pi = [['a', 'C']] if pi is None else pi
    return dict(status='attained_optimum', J=J, Q_total=Q, H=len(pi),
                site_action_tuple=deepcopy(pi), lex_key=[J, Q, len(pi), deepcopy(pi)])


def primary(J='7/3'):
    return dict(status='primary_unattained', primary_infimum=J)


def secondary(J='7/3', Q='5/7'):
    return dict(status='secondary_unattained', J=J, secondary_infimum=Q)


def fixture(result_groups, order=None, *, family_ids=None, actions=None, bound='7/3'):
    """Build an admitted-projection-shaped fixture with separated global spans."""
    order = list(range(len(result_groups))) if order is None else order
    family_ids = ['family'] if family_ids is None else family_ids
    actions = [[f'action-{i}', 'C'] for i in range(len(order))] if actions is None else actions
    segments, records, start = {}, {}, 31
    for ident, results in enumerate(result_groups):
        records[ident] = [dict(result=deepcopy(result)) for result in results]
        summary = summarize_records(records[ident], start=start)
        segments[ident] = dict(segment_id=ident, complete_certificates=True, aggregate=summary)
        start = summary['end']+7
    spans, offset = [], 0
    for position, ident in enumerate(order):
        summary = segments[ident]['aggregate']
        size = summary['end']-summary['start']
        family_position, action_position = divmod(position, len(actions))
        spans.append(dict(family_position=family_position, action_position=action_position,
                          segment_id=ident, logical_start=summary['start'],
                          logical_end=summary['end'], query_start=offset, query_end=offset+size))
        offset += size
    projection = dict(query_seq=47, thin_occurrence_sha256='a'*64,
                      ancestry_bundle_sha256='b'*64, family_ids=family_ids, actions=actions,
                      classification='synthetic', recorded_bound=bound, model_slots=offset,
                      legal_completion_language_empty=offset == 0, ranges=spans)
    original_records = [deepcopy(row) for ident in order for row in records[ident]]
    return projection, segments, original_records


def expanded(summary):
    names = ('primary_tied_regimes', 'secondary_tied_regimes', 'winning_regimes')
    return dict(result=summary['result'], audit=dict(
        {name: [i for lo, hi in summary['audit'][key] for i in range(lo, hi)]
         for name, key in zip(names, RANGES)},
        exclusion_counts=summary['audit']['exclusion_counts']))


class OccurrenceJoinTests(unittest.TestCase):
    def assert_reference(self, projection, segments, rows):
        saved = deepcopy((projection, segments))
        joined = join_projection(projection, segments)
        expected = aggregate_records(rows, with_audit=True)
        self.assertEqual(joined['status'], 'complete')
        self.assertEqual(joined['unresolved_segment_ids'], [])
        self.assertEqual(joined['projection'], projection)
        self.assertEqual(expanded(joined['aggregate']), expected)
        self.assertEqual(joined['aggregate']['start'], 0)
        self.assertEqual(joined['aggregate']['end'], len(rows))
        self.assertEqual(joined['bound_audit'], _bound_audit(projection['recorded_bound'],
                                                         expected['result']))
        self.assertEqual((projection, segments), saved)
        return joined

    def test_six_statuses_and_zero_length_languages(self):
        choices = [*(dict(status=status) for status in EXCLUSIONS), primary(), secondary(), attained()]
        for result in choices:
            with self.subTest(result=result):
                self.assert_reference(*fixture([[result]]))
        projection, segments, rows = fixture([], order=[], actions=[])
        empty = self.assert_reference(projection, segments, rows)
        projection, segments, rows = fixture([[], []], order=[1, 0])
        self.assert_reference(projection, {}, rows)  # No model proofs exist or are needed.
        excluded = self.assert_reference(*fixture([[dict(status=s) for s in EXCLUSIONS]]))
        self.assertEqual(empty['aggregate']['result'], excluded['aggregate']['result'])
        self.assertEqual(empty['projection']['model_slots'], 0)
        self.assertTrue(empty['projection']['legal_completion_language_empty'])
        self.assertEqual(excluded['projection']['model_slots'], 3)
        self.assertFalse(excluded['projection']['legal_completion_language_empty'])
        self.assertEqual(excluded['aggregate']['audit']['exclusion_counts'], dict.fromkeys(EXCLUSIONS, 1))
        self.assertEqual(empty['bound_audit']['bound_status'], 'vacuous_empty_restricted_family')

    def test_original_family_action_order_and_repeated_logical_segments(self):
        groups = [[primary(), attained()], [dict(status='closed_infeasible'), attained()],
                  [attained(pi=[['z', 'C']]), secondary()], [attained(), primary()]]
        for order in ([3, 1, 2, 0], [1, 0, 1, 0]):
            with self.subTest(order=order):
                values = fixture(groups, order, family_ids=['family-z', 'family-a'],
                                 actions=[['z', 'S'], ['a', 'C']])
                joined = self.assert_reference(*values)
                self.assertEqual(joined['projection']['ranges'][0]['segment_id'], order[0])
        joined = self.assert_reference(*fixture([[attained()], [attained()]], [1, 0, 1, 0],
                                                family_ids=['same', 'same'],
                                                actions=[['z', 'C'], ['a', 'C']]))
        for name in RANGES:
            self.assertEqual(joined['aggregate']['audit'][name], [[0, 4]])

    def test_exact_primary_and_secondary_nonattainment_across_segments(self):
        first = self.assert_reference(*fixture([[attained('3', '0'), primary()],
                                                [secondary('5/2', '-100'), primary()]], [1, 0]))
        self.assertEqual(first['aggregate']['result'], primary())
        second = self.assert_reference(*fixture([[attained(Q='1', pi=[]), secondary(Q='2/3')],
                                                 [primary(), secondary(Q='2/3'), attained(Q='3/4')]], [1, 0]))
        self.assertEqual(second['aggregate']['result'], secondary(Q='2/3'))
        self.assertEqual(second['aggregate']['audit'][RANGES[2]], [])

    def test_H_then_pi_and_all_ties_survive_reordered_join(self):
        winner = attained(pi=[['a', 'CS']])
        groups = [[attained(pi=[['0', 'C'], ['0', 'C']]), winner, winner],
                  [winner, dict(status='strict_infeasible'), attained(pi=[['a', 'S']])],
                  [attained(pi=[['z', 'C']]), primary(), secondary()]]
        joined = self.assert_reference(*fixture(groups, [1, 2, 0, 1]))
        self.assertEqual(joined['aggregate']['result'], winner)
        self.assertEqual(joined['aggregate']['audit'][RANGES[2]], [[0, 1], [7, 10]])

    def test_fraction_differences_too_small_for_float_comparison(self):
        tiny, J, Q = Fraction(1, 10**80), Fraction(1, 3), Fraction(2, 7)
        groups = [[attained(str(J+tiny), '-100'), primary(str(J))],
                  [attained(str(J), str(Q+tiny), [])],
                  [secondary(str(J), str(Q)), attained(str(J), str(Q))]]
        joined = self.assert_reference(*fixture(groups, [2, 0, 1, 2]))
        self.assertEqual(joined['aggregate']['result'], attained(str(J), str(Q)))

    def test_small_exhaustive_differential_with_repetition_and_reordering(self):
        choices = [*(dict(status=status) for status in EXCLUSIONS), primary('1'), primary('2'),
                   secondary('1', '2'), attained('1', '2'), attained('1', '3', []), attained('2', '0')]
        for sequence in product(choices, repeat=3):
            self.assert_reference(*fixture([[row] for row in sequence], [2, 0, 1, 2]))

    def test_bound_is_audited_separately_for_each_original_query(self):
        projection, segments, rows = fixture([[attained()]])
        with patch('validation.suffix5.occurrence_join._bound_audit', wraps=_bound_audit) as audit:
            for sequence, bound, status in ((47, None, 'missing_bound_for_nonempty_family'),
                                            (48, '10/3', 'violated'), (49, '7/3', 'satisfied')):
                projection['query_seq'], projection['recorded_bound'] = sequence, bound
                joined = self.assert_reference(projection, segments, rows)
                self.assertEqual(joined['bound_audit']['bound_status'], status)
                self.assertEqual(joined['aggregate']['result'], attained())
            self.assertEqual(audit.call_count, 3)

    def test_missing_incomplete_partial_or_foreign_segment_never_yields_partial_aggregate(self):
        projection, segments, _ = fixture([[attained(), attained()], [primary()]], [0, 1, 0])
        bad_maps = []
        for value in (None, dict(segment_id=0, complete_certificates=False, aggregate=segments[0]['aggregate']),
                      dict(segment_id=0, complete_certificates=True, aggregate=None)):
            changed = deepcopy(segments)
            if value is None:
                del changed[0]
            else:
                changed[0] = value
            bad_maps.append(changed)
        changed = deepcopy(segments)
        changed[0]['aggregate'] = summarize_records([dict(result=attained())], start=31)
        bad_maps.append(changed)
        changed = deepcopy(segments)
        changed[0]['aggregate'] = summarize_records([dict(result=attained()), dict(result=attained())], start=32)
        bad_maps.append(changed)
        with patch('validation.suffix5.occurrence_join._bound_audit') as audit:
            for changed in bad_maps:
                joined = join_projection(projection, changed)
                self.assertEqual(joined['status'], 'unresolved')
                self.assertEqual(joined['unresolved_segment_ids'], [0])
                self.assertIsNone(joined['aggregate'])
                self.assertIsNone(joined['bound_audit'])
            audit.assert_not_called()
        changed = deepcopy(segments)
        changed[0]['segment_id'] = 99
        with self.assertRaisesRegex(SuffixVerificationError, 'foreign_segment_id'):
            join_projection(projection, changed)

    def test_gapped_overlapping_reordered_truncated_and_foreign_spans_reject(self):
        projection, segments, _ = fixture([[attained()], [primary()]])
        mutations = [lambda p: p['ranges'][1].update(query_start=2, query_end=3),
                     lambda p: p['ranges'][1].update(query_start=0, query_end=1),
                     lambda p: p['ranges'][1].update(logical_end=999),
                     lambda p: p['ranges'][1].update(action_position=0),
                     lambda p: p['ranges'].reverse(),
                     lambda p: p['ranges'].pop(),
                     lambda p: p.update(model_slots=3),
                     lambda p: p.update(legal_completion_language_empty=True),
                     lambda p: p['ranges'][1].update(logical_start=31, logical_end=32),
                     lambda p: p['ranges'][1].update(segment_id=0),
                     lambda p: p['ranges'][0].update(segment_id=True)]
        for mutate in mutations:
            changed = deepcopy(projection)
            mutate(changed)
            with self.subTest(projection=changed), self.assertRaises(SuffixVerificationError):
                join_projection(changed, segments)
        changed = deepcopy(projection)
        changed['ranges'][0]['segment_id'] = 999
        self.assertEqual(join_projection(changed, segments)['status'], 'unresolved')

    def test_compact_audit_validation_detachment_and_irrelevant_incomplete_segment(self):
        projection, segments, rows = fixture([[attained()]*1000])
        segments[99] = dict(segment_id=99, complete_certificates=False, aggregate=None)
        joined = self.assert_reference(projection, segments, rows)
        for name in RANGES:
            self.assertEqual(joined['aggregate']['audit'][name], [[0, 1000]])
        joined['projection']['actions'][0][0] = 'changed'
        joined['aggregate']['audit'][RANGES[0]][0][1] = 999999
        joined['aggregate']['result']['site_action_tuple'][0][0] = 'changed'
        self.assert_reference(projection, segments, rows)
        for field, value in [('complete_certificates', 1), ('segment_id', True)]:
            changed = deepcopy(segments)
            changed[0][field] = value
            with self.assertRaises(SuffixVerificationError):
                join_projection(projection, changed)
        for runs in ([[30, 1031]], [[31, 500], [500, 1031]], [[31, 100], [99, 1031]]):
            changed = deepcopy(segments)
            changed[0]['aggregate']['audit'][RANGES[0]] = runs
            with self.assertRaises(SuffixVerificationError):
                join_projection(projection, changed)


if __name__ == '__main__':
    unittest.main()
