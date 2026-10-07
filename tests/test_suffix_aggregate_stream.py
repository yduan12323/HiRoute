"""Tiny exact differential checks; no LPs, server jobs, or physical inputs."""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import unittest

from validation.suffix5.aggregate_stream import (
    EXCLUSIONS, RANGES, StreamAggregator, bound_audit, finalize_summary,
    merge_summaries, summarize_records,
)
from validation.suffix5.checker import aggregate_records, _bound_audit
from validation.suffix5.independent_model import SuffixVerificationError


def attained(J='7/3', Q='5/7', pi=None):
    pi = [['a', 'C']] if pi is None else pi
    return dict(status='attained_optimum', J=J, Q_total=Q, H=len(pi),
                site_action_tuple=deepcopy(pi), lex_key=[J, Q, len(pi), deepcopy(pi)])


def primary(J='7/3'):
    return dict(status='primary_unattained', primary_infimum=J)


def secondary(J='7/3', Q='5/7'):
    return dict(status='secondary_unattained', J=J, secondary_infimum=Q)


def records(*results):
    return [dict(result=result) for result in results]


def expand(summary, offset=0):
    audit = summary['audit']
    names = ('primary_tied_regimes', 'secondary_tied_regimes', 'winning_regimes')
    return dict(result=summary['result'], audit=dict(
        {name: [i-offset for lo, hi in audit[key] for i in range(lo, hi)]
         for name, key in zip(names, RANGES)}, exclusion_counts=audit['exclusion_counts']))


class StreamAggregateTests(unittest.TestCase):
    def assert_reference(self, rows, *, start=0):
        expected = aggregate_records(rows, with_audit=True)
        summary = summarize_records(iter(rows), start=start)
        self.assertEqual(expand(summary, start), expected)
        self.assertEqual(finalize_summary(summary), expected['result'])
        self.assertEqual(finalize_summary(summary, with_audit=True),
                         dict(result=summary['result'], audit=summary['audit']))
        self.assertEqual((summary['start'], summary['end']), (start, start+len(rows)))
        for bound in (None, '-5', '7/3', '10/3'):
            self.assertEqual(bound_audit(bound, summary), _bound_audit(bound, expected['result']))
        return summary

    def test_each_of_the_six_statuses_and_empty_language(self):
        for row in [*(dict(status=status) for status in EXCLUSIONS),
                    primary(), secondary(), attained()]:
            with self.subTest(status=row['status']):
                self.assert_reference(records(row))
        empty = self.assert_reference([])
        excluded = self.assert_reference(records(*(dict(status=status) for status in EXCLUSIONS)))
        self.assertEqual(empty['result'], excluded['result'])
        self.assertEqual(empty['end']-empty['start'], 0)
        self.assertEqual(excluded['end']-excluded['start'], 3)
        self.assertEqual(excluded['audit']['exclusion_counts'], dict.fromkeys(EXCLUSIONS, 1))

    def test_lower_unattained_primary_dominates_attained_higher_J(self):
        rows = records(attained('3', '0'), primary('7/3'), secondary('5/2', '-100'),
                       primary('7/3'), attained('4', '-1000', []))
        result = self.assert_reference(rows)
        self.assertEqual(result['result'], primary('7/3'))
        self.assertEqual(result['audit'][RANGES[0]], [[1, 2], [3, 4]])
        self.assertEqual(result['audit'][RANGES[1]], [])

    def test_attained_alternative_on_equal_primary_and_secondary_faces(self):
        rows = records(primary(), attained(Q='6/7'), secondary(), attained(), primary())
        summary = self.assert_reference(rows, start=19)
        self.assertEqual(summary['result'], attained())
        self.assertEqual(summary['audit'][RANGES[0]], [[19, 24]])
        self.assertEqual(summary['audit'][RANGES[1]], [[21, 23]])
        self.assertEqual(summary['audit'][RANGES[2]], [[22, 23]])

    def test_secondary_nonattainment_precedes_H_and_pi(self):
        rows = records(attained(Q='1', pi=[]), secondary(Q='2/3'), primary(),
                       secondary(Q='2/3'), attained(Q='3/4', pi=[]))
        summary = self.assert_reference(rows)
        self.assertEqual(summary['result'], secondary(Q='2/3'))
        self.assertEqual(summary['audit'][RANGES[2]], [])

    def test_H_then_pi_and_all_tie_runs(self):
        winner = attained(pi=[['a', 'CS']])
        rows = records(attained(pi=[['0', 'C'], ['0', 'C']]),
                       attained(pi=[['z', 'C']]), winner, deepcopy(winner),
                       dict(status='strict_infeasible'), attained(pi=[['a', 'S']]),
                       winner, primary(), secondary())
        summary = self.assert_reference(rows)
        self.assertEqual(summary['result'], winner)
        self.assertEqual(summary['audit'][RANGES[2]], [[2, 4], [6, 7]])

    def test_exact_fractions_not_float_ordering(self):
        tiny = Fraction(1, 10**80)
        J, Q = Fraction(1, 3), Fraction(2, 7)
        rows = records(attained(str(J+tiny), '-100'), primary(str(J)),
                       attained(str(J), str(Q+tiny), []),
                       secondary(str(J), str(Q)), attained(str(J), str(Q)))
        summary = self.assert_reference(rows)
        self.assertEqual(summary['result'], attained(str(J), str(Q)))

    def test_every_split_and_merge_association_preserves_ranges(self):
        rows = records(primary(), attained(Q='1'), attained(), secondary(),
                       dict(status='closed_infeasible'), attained(),
                       primary('5'), attained(J='4', Q='-8'))
        full = self.assert_reference(rows, start=23)
        for i in range(len(rows)+1):
            for j in range(i, len(rows)+1):
                a = summarize_records(rows[:i], start=23)
                b = summarize_records(rows[i:j], start=23+i)
                c = summarize_records(rows[j:], start=23+j)
                saved = deepcopy((a, b, c))
                self.assertEqual(merge_summaries(merge_summaries(a, b), c), full)
                self.assertEqual(merge_summaries(a, merge_summaries(b, c)), full)
                self.assertEqual((a, b, c), saved)
        stream = StreamAggregator(23)
        for i, row in enumerate(rows, 23):
            stream.add(i, row['result'])
        self.assertEqual(stream.summary(), full)

    def test_small_exhaustive_differential_sequences(self):
        choices = [*(dict(status=status) for status in EXCLUSIONS), primary('1'),
                   primary('2'), secondary('1', '2'), attained('1', '2'),
                   attained('1', '3', []), attained('2', '0')]
        for sequence in product(choices, repeat=3):
            rows = records(*sequence)
            summary = summarize_records(iter(rows))
            self.assertEqual(expand(summary), aggregate_records(rows, with_audit=True))
            left = summarize_records(rows[:1])
            right = summarize_records(rows[1:], start=1)
            self.assertEqual(merge_summaries(left, right), summary)

    def test_stream_is_single_pass_compact_and_detached(self):
        class Once:
            def __init__(self):
                self.used = False

            def __iter__(self):
                if self.used:
                    raise AssertionError('second pass')
                self.used = True
                for _ in range(1000):
                    yield dict(result=attained())

        summary = summarize_records(Once())
        for name in RANGES:
            self.assertEqual(summary['audit'][name], [[0, 1000]])
        row = attained()
        stream = StreamAggregator()
        stream.add(0, row)
        expected = stream.summary()
        row['site_action_tuple'][0][0] = 'mutated input'
        snapshot = stream.summary()
        snapshot['result']['lex_key'][3][0][0] = 'mutated output'
        snapshot['audit'][RANGES[0]][0][1] = 100
        self.assertEqual(stream.summary(), expected)

    def test_invalid_result_fields_rejected_like_reference_without_state_change(self):
        invalid = [None, [], dict(status='empty_restricted_family'), dict(status='unknown'),
                   dict(status='primary_unattained'), dict(status='primary_unattained', primary_infimum=1),
                   dict(status='primary_unattained', primary_infimum='2/2'),
                   dict(status='primary_unattained', primary_infimum='nan'),
                   dict(status='primary_unattained', primary_infimum='1/0'),
                   dict(status='secondary_unattained', J='1', secondary_infimum=1.5)]
        for field, value in [('H', True), ('H', -1), ('H', 2), ('site_action_tuple', [['a', 'X']]),
                             ('site_action_tuple', [['a', 'C', 'extra']]),
                             ('site_action_tuple', [[0, 'C']]), ('lex_key', ['7/3', '5/7', True, [['a', 'C']]]),
                             ('extra', 1)]:
            bad = attained()
            bad[field] = value
            invalid.append(bad)
        stream = StreamAggregator()
        before = stream.summary()
        for row in invalid:
            with self.subTest(row=row):
                with self.assertRaises(SuffixVerificationError):
                    aggregate_records(records(row))
                with self.assertRaises(SuffixVerificationError):
                    stream.add(0, row)
                self.assertEqual(stream.summary(), before)
        with self.assertRaises(SuffixVerificationError):
            summarize_records([{}])
        with self.assertRaises(SuffixVerificationError):
            finalize_summary(before, with_audit=1)

    def test_explicit_ids_and_partition_gaps_duplicates_and_order_rejected(self):
        for start in (-1, True, 0.0, '0'):
            with self.assertRaises(SuffixVerificationError):
                StreamAggregator(start)
        stream = StreamAggregator(4)
        stream.add(4, attained())
        before = stream.summary()
        for ident in (4, 3, 6, True, '5', 5.0):
            with self.assertRaises(SuffixVerificationError):
                stream.add(ident, attained())
            self.assertEqual(stream.summary(), before)
        left = summarize_records(records(attained()), start=4)
        for start in (3, 4, 6):
            right = summarize_records(records(attained()), start=start)
            with self.assertRaises(SuffixVerificationError):
                merge_summaries(left, right)
            with self.assertRaises(SuffixVerificationError):
                stream.extend_summary(right)
            self.assertEqual(stream.summary(), before)

    def test_malformed_summaries_and_noncanonical_ranges_rejected(self):
        good = summarize_records(records(attained(), attained(), primary()), start=4)
        bad_summaries = []
        for field, value in [('schema', 'wrong'), ('start', True), ('start', 8), ('end', '7'),
                             ('result', dict(status='graph_unreachable')), ('extra', None)]:
            bad = deepcopy(good)
            bad[field] = value
            bad_summaries.append(bad)
        for runs in ([[4, 4]], [[3, 5]], [[4, 8]], [[5, 4]], [[True, 5]], [[4, 5, 6]],
                     [[4, 6], [5, 7]], [[5, 7], [4, 5]], [[4, 5], [5, 7]],
                     [[4, 5], [4, 5]], [[4.0, 7]], []):
            bad = deepcopy(good)
            bad['audit'][RANGES[0]] = runs
            bad_summaries.append(bad)
        for counts in ({}, dict.fromkeys(EXCLUSIONS, True), dict.fromkeys(EXCLUSIONS, -1),
                       dict.fromkeys(EXCLUSIONS, 2)):
            bad = deepcopy(good)
            bad['audit']['exclusion_counts'] = counts
            bad_summaries.append(bad)
        bad = deepcopy(good)
        bad['audit'][RANGES[2]] = [[6, 7]]
        bad_summaries.append(bad)
        bad = deepcopy(good)
        bad['result'] = primary()
        bad_summaries.append(bad)
        for bad in bad_summaries:
            with self.subTest(summary=bad):
                with self.assertRaises(SuffixVerificationError):
                    finalize_summary(bad)
                with self.assertRaises(SuffixVerificationError):
                    merge_summaries(summarize_records([], start=4), bad)


if __name__ == '__main__':
    unittest.main()
