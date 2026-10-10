"""Whole original-node domain index is complete and fails closed on edits."""
import json
import unittest

from validation.trace5 import CheckedTrace
from validation.real5_v2.coalesced import verify_coalesced_trace
from experiments.time_cut_v2.recorded_real.node_domain_batch import check_domains
from tests.test_recovered_real_coalesced import ROOT, capture, prepare


class NodeDomainBatch(unittest.TestCase):
    def checked(self):
        row = json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
        captured = capture(row, True)
        return verify_coalesced_trace(captured['trace'], captured['bundle'], prepare(row))

    def test_complete_nonempty_and_empty_original_order(self):
        checked = self.checked()
        def projection(seq):
            row = next(q for q in checked.queries if q['query_seq'] == seq)
            from validation.family5.checker import _plain
            roots = _plain(row['family_ids']); actions = _plain(row['actions'])
            ranges = [dict(family_position=f, action_position=a, logical_start=0,
                           logical_end=1, query_start=f*len(actions)+a,
                           query_end=f*len(actions)+a+1)
                      for f in range(len(roots)) for a in range(len(actions))]
            return dict(query_seq=seq, family_ids=_plain(row['family_ids']),
                        actions=_plain(row['actions']), recorded_bound=row['bound'],
                        classification=row['classification'],
                        ancestry_bundle_sha256=row['ancestry_bundle_sha256'],
                        model_slots=len(ranges), ranges=ranges)
        result = check_domains(checked, projection)
        self.assertEqual(result['checked_queries'], len(checked.queries))
        self.assertEqual(result['checked_empty_action_events'], len(checked.empty_action_queries))
        self.assertGreater(result['admitted_model_occurrences'], 0)

    def test_missing_empty_event_and_tampered_projection_fail(self):
        checked = self.checked()
        wrong = CheckedTrace(checked._trace, checked.bundle, checked.summary,
                             checked.node_queries, checked.empty_action_queries[:-1])
        with self.assertRaises(ValueError):
            check_domains(wrong)
        def projection(seq):
            row = next(q for q in checked.queries if q['query_seq'] == seq)
            from validation.family5.checker import _plain
            return dict(query_seq=seq, family_ids=_plain(row['family_ids']),
                        actions=[], recorded_bound=row['bound'],
                        classification=row['classification'], model_slots=1)
        with self.assertRaises(ValueError):
            check_domains(checked, projection)

    def test_occurrence_range_gap_fails(self):
        checked = self.checked()
        def projection(seq):
            row = next(q for q in checked.queries if q['query_seq'] == seq)
            from validation.family5.checker import _plain
            roots = _plain(row['family_ids']); actions = _plain(row['actions'])
            ranges = [dict(family_position=f, action_position=a,
                           logical_start=0, logical_end=1,
                           query_start=f*len(actions)+a,
                           query_end=f*len(actions)+a+1)
                      for f in range(len(roots)) for a in range(len(actions))]
            ranges[-1]['query_end'] += 1
            return dict(query_seq=seq, family_ids=roots, actions=actions,
                        recorded_bound=row['bound'], classification=row['classification'],
                        ancestry_bundle_sha256=row['ancestry_bundle_sha256'],
                        model_slots=len(ranges), ranges=ranges)
        with self.assertRaises(ValueError):
            check_domains(checked, projection)
