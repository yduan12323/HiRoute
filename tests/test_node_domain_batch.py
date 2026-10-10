"""Whole original-node domain index is complete, including zero languages."""
import json
import unittest

from validation.trace5 import CheckedTrace
from validation.real5_v2.coalesced import verify_coalesced_trace
from validation.real5_v2.suffix_context import count_language
from validation.family5.checker import _plain
from experiments.time_cut_v2.recorded_real.node_domain_batch import check_domains
from tests.test_recovered_real_coalesced import ROOT, prepare


class NodeDomainBatch(unittest.TestCase):
    def fixture(self):
        item = json.loads((ROOT/'tests/fixtures/g8_node_batch_fixture.json').read_text())
        trusted = prepare(item['row'])
        evidence = item['evidence']
        checked = verify_coalesced_trace(evidence['trace'], evidence['bundle'], trusted)
        return checked, trusted

    @staticmethod
    def projection(checked, trusted, seq):
        row = next(q for q in checked.queries if q['query_seq'] == seq)
        roots, actions = _plain(row['family_ids']), _plain(row['actions'])
        counts = [count_language(trusted, row['state'], [action])['models_per_family']
                  for action in actions]
        offset = 0
        ranges = []
        for family_position in range(len(roots)):
            for action_position, count in enumerate(counts):
                ranges.append(dict(family_position=family_position,
                    action_position=action_position, logical_start=0,
                    logical_end=count, query_start=offset, query_end=offset+count))
                offset += count
        return dict(query_seq=seq, family_ids=roots, actions=actions,
            recorded_bound=row['bound'], classification=row['classification'],
            ancestry_bundle_sha256=row['ancestry_bundle_sha256'],
            model_slots=offset, legal_completion_language_empty=offset==0,
            ranges=ranges)

    def test_complete_nonempty_actions_with_zero_completion_language(self):
        checked, trusted = self.fixture()
        projected = lambda seq: self.projection(checked, trusted, seq)
        self.assertTrue(next(q for q in checked.queries if q['query_seq'] == 46)['actions'])
        self.assertEqual(projected(46)['model_slots'], 0)
        self.assertEqual(projected(46)['ranges'][0]['query_start'],
                         projected(46)['ranges'][0]['query_end'])
        result = check_domains(checked, projected)
        self.assertEqual(result['checked_queries'], len(checked.queries))
        self.assertEqual(result['checked_empty_action_events'], len(checked.empty_action_queries))
        self.assertEqual(result['admitted_model_occurrences'],
                         sum(projected(q['query_seq'])['model_slots'] for q in checked.queries))

    def test_missing_empty_event_and_tampered_projection_fail(self):
        checked, trusted = self.fixture()
        wrong = CheckedTrace(checked._trace, checked.bundle, checked.summary,
                             checked.node_queries, checked.empty_action_queries[:-1])
        with self.assertRaises(ValueError):
            check_domains(wrong)
        def projection(seq):
            value = self.projection(checked, trusted, seq)
            value['actions'] = []
            return value
        with self.assertRaises(ValueError):
            check_domains(checked, projection)

    def test_occurrence_range_gap_and_false_zero_flag_fail(self):
        checked, trusted = self.fixture()
        def gap(seq):
            value = self.projection(checked, trusted, seq)
            value['ranges'][-1]['query_end'] += 1
            return value
        with self.assertRaises(ValueError):
            check_domains(checked, gap)
        def false_zero(seq):
            value = self.projection(checked, trusted, seq)
            value['legal_completion_language_empty'] = not value['legal_completion_language_empty']
            return value
        with self.assertRaises(ValueError):
            check_domains(checked, false_zero)
