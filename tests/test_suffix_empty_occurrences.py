"""Historical empty-query extraction against a genuine tiny replay; no LP."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.test_invocation_trace_v1 import capture
from validation.capture5.containers import stream_digest
from validation.family5.checker import _plain
from validation.trace5.checker import verify_trace
from validation.trace5.test_checker_units import hand_trace
from validation.suffix5 import checker, empty_occurrences as bridge


class EmptyOccurrences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        case, _, _ = hand_trace()
        data, _ = capture(case)
        cls.original = data['trace']
        cls.checked = verify_trace(data['trace'], data['bundle'], case)
        cls.original_ids = [row['query_seq'] for row in cls.checked.queries]
        cls.original_rows = _plain(cls.checked.empty_action_queries)
        cls.original_pins = dict(
            trace_sha256=cls.checked.summary['trace_sha256'],
            exact_queries=len(cls.checked.queries),
            empty_action_queries=len(cls.checked.empty_action_queries),
            empty_action_sha256=stream_digest(cls.checked.empty_action_queries))

    def setUp(self):
        self.trace = deepcopy(self.original)
        self.ids = list(self.original_ids)
        self.pins = dict(self.original_pins)

    def recover(self, *, repin_trace=False, **changes):
        pins = dict(self.pins, **changes)
        if repin_trace:
            pins['trace_sha256'] = stream_digest(self.trace)
        return bridge.recover_empty_occurrences(self.trace, self.ids, **pins)

    def query(self, empty):
        return next(event for event in self.trace['events']
                    if event['kind'] == 'query' and bool(event['payload']['actions']) != empty)

    def test_matches_genuine_checked_rows_and_mixed_original_order(self):
        with patch.object(checker, '_bound_audit', wraps=checker._bound_audit) as audit:
            actual = self.recover()
        self.assertEqual(actual['rows'], self.original_rows)
        self.assertEqual(stream_digest(actual['rows']), self.pins['empty_action_sha256'])
        self.assertEqual(audit.call_count, len(self.original_rows))
        for call in audit.call_args_list:
            self.assertEqual(call.args, (None, {'status': 'empty_restricted_family'}))
        expected_ids = [e['seq'] for e in self.trace['events'] if e['kind'] == 'query']
        self.assertEqual(actual['query_ids'], expected_ids)
        self.assertEqual(actual['total_query_events'], len(self.ids) + len(self.original_rows))
        self.assertNotEqual(expected_ids, self.ids + [row['query_seq'] for row in self.original_rows])
        self.assertFalse(set(self.ids) & {row['query_seq'] for row in actual['rows']})
        for row in actual['audits']:
            self.assertEqual(row['result'], {'status': 'empty_restricted_family'})
            self.assertEqual(row['audit']['bound_status'], 'vacuous_empty_restricted_family')
            self.assertTrue(row['audit']['bound_valid'])
        self.assertFalse(actual['execution_authority'])
        self.assertFalse(actual['certificate_authority'])

    def test_returned_rows_do_not_alias_capture(self):
        actual = self.recover()
        actual['rows'][0]['actions'].append(['foreign', 'C'])
        self.assertEqual(self.query(True)['payload']['actions'], [])
        self.query(True)['payload']['group_id'] = 99
        self.assertNotEqual(actual['rows'][0]['group_id'], 99)

    def test_count_hash_and_unrelated_trace_mutations(self):
        for key, value in (('exact_queries', len(self.ids) + 1),
                           ('empty_action_queries', len(self.original_rows) + 1),
                           ('empty_action_sha256', '0' * 64),
                           ('trace_sha256', '0' * 64)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.recover(**{key: value})
        self.trace['events'][-1]['payload']['terminal_family_id'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'historical_trace_digest_mismatch'):
            self.recover()
        self.trace = deepcopy(self.original)
        self.query(True)['payload']['effect'] = 'S'
        with self.assertRaisesRegex(ValueError, 'historical_empty_digest_mismatch'):
            self.recover(repin_trace=True)

    def test_duplicate_missing_reordered_foreign_and_overlapping_index_ids(self):
        candidates = [self.ids[:-1], list(reversed(self.ids)),
                      [self.ids[0]] * len(self.ids),
                      self.ids[:-1] + [len(self.trace['events']) + 1],
                      sorted([self.original_rows[0]['query_seq']] + self.ids[1:])]
        for ids in candidates:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                bridge.recover_empty_occurrences(self.trace, ids, **self.pins)

    def test_duplicate_missing_reordered_and_foreign_event_identity(self):
        for change in ('duplicate', 'missing', 'reorder', 'foreign'):
            self.trace = deepcopy(self.original)
            events = self.trace['events']
            seq = self.query(True)['seq']
            if change == 'duplicate':
                events.insert(seq, deepcopy(events[seq]))
            elif change == 'missing':
                events.pop(seq)
            elif change == 'reorder':
                events[seq], events[seq + 1] = events[seq + 1], events[seq]
            else:
                events[seq]['seq'] = len(events) + 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.recover(repin_trace=True)

    def test_actions_classification_bound_and_serial_must_match_partition(self):
        mutations = [(True, 'actions', ()), (True, 'actions', [['s', 'S']]),
                     (True, 'classification', 'queued'), (True, 'classification', 'unreachable'),
                     (True, 'bound', '0'), (True, 'bound', False),
                     (True, 'queue_serial', 0), (True, 'queue_serial', True),
                     (False, 'classification', 'empty_actions'), (False, 'actions', []),
                     (False, 'actions', [True]), (False, 'actions', [['s', False]]),
                     (False, 'actions', [['s', 'foreign']]),
                     (False, 'bound', None), (False, 'queue_serial', None)]
        for empty, field, value in mutations:
            self.trace = deepcopy(self.original)
            self.query(empty)['payload'][field] = value
            with self.subTest(empty=empty, field=field, value=value), self.assertRaises(ValueError):
                self.recover(repin_trace=True)
        self.trace = deepcopy(self.original)
        self.query(True)['payload']['query_seq'] = 99
        with self.assertRaisesRegex(ValueError, 'query_payload_fields'):
            self.recover(repin_trace=True)

    def test_strict_integer_types_for_pins_index_events_and_payload(self):
        for value in (True, 1.0, '1', -1):
            for field in ('exact_queries', 'empty_action_queries'):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.recover(**{field: value})
            self.ids = [value] + self.original_ids[1:]
            with self.subTest(field='index', value=value), self.assertRaises(ValueError):
                self.recover()
            self.ids = list(self.original_ids)
            self.trace = deepcopy(self.original)
            self.trace['events'][1]['seq'] = value
            with self.subTest(field='seq', value=value), self.assertRaises(ValueError):
                self.recover(repin_trace=True)
            for empty, field in ((True, 'group_id'), (True, 'region_id'),
                                 (False, 'group_id'), (False, 'region_id'),
                                 (False, 'queue_serial')):
                self.trace = deepcopy(self.original)
                self.query(empty)['payload'][field] = value
                with self.subTest(empty=empty, field=field, value=value), self.assertRaises(ValueError):
                    self.recover(repin_trace=True)
            self.trace = deepcopy(self.original)

    def test_empty_and_nonempty_population_cardinalities_are_parametric(self):
        # Pure extraction can check even a synthetic matching partition; it
        # cannot establish that a complete structural replay actually occurred.
        for count in (0, 1, 257):
            events = [dict(seq=seq, kind='query', payload=deepcopy(self.original_rows[0]))
                      for seq in range(count)]
            for event in events:
                del event['payload']['query_seq']
            trace = dict(schema='family5-hier-trace-v1', events=events)
            rows = [dict(query_seq=e['seq'], **e['payload']) for e in events]
            actual = bridge.recover_empty_occurrences(trace, (), trace_sha256=stream_digest(trace),
                exact_queries=0, empty_action_queries=count, empty_action_sha256=stream_digest(rows))
            self.assertEqual(actual['total_query_events'], count)
            self.assertEqual(actual['rows'], rows)
            self.assertFalse(actual['execution_authority'])
        events = [deepcopy(self.query(False))]
        events[0]['seq'] = 0
        trace = dict(schema='family5-hier-trace-v1', events=events)
        actual = bridge.recover_empty_occurrences(trace, [0], trace_sha256=stream_digest(trace),
            exact_queries=1, empty_action_queries=0, empty_action_sha256=stream_digest([]))
        self.assertEqual(actual['total_query_events'], 1)

    def test_hash_bytes_checkpoints_and_cancellation(self):
        calls = []
        value = [dict(text='\u7ebf' * 30000, values=list(range(500))) for _ in range(3)]
        self.assertEqual(bridge._digest(value, lambda: calls.append(None)), stream_digest(value))
        self.assertGreater(len(calls), 3)
        checkpoints = []
        def cancel():
            checkpoints.append(None)
            if len(checkpoints) == 4:
                raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.recover(before=cancel)
        self.assertEqual(len(checkpoints), 4)


class RealCoalescedEmptyOccurrences(unittest.TestCase):
    """Genuine tiny mock captures through the current independent real checker."""
    @classmethod
    def setUpClass(cls):
        from tests.test_recovered_real_coalesced import capture as capture_coalesced
        from tests.test_recovered_real_family import prepare
        from validation.real5_v2.shared_replay import verify_coalesced_trace
        root = Path(__file__).resolve().parents[1]
        row = json.loads((root / 'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
        cls.runs = {}
        for dominance in (False, True):
            data = capture_coalesced(row, dominance)
            checked = verify_coalesced_trace(data['trace'], data['bundle'], prepare(row))
            cls.runs[dominance] = (data['trace'], checked)

    def recover(self, trace, checked, **changes):
        pins = dict(trace_sha256=checked.summary['trace_sha256'],
                    exact_queries=len(checked.queries),
                    empty_action_queries=len(checked.empty_action_queries),
                    empty_action_sha256=stream_digest(checked.empty_action_queries))
        pins.update(changes)
        return bridge.recover_empty_occurrences(trace, [q['query_seq'] for q in checked.queries], **pins)

    def test_both_dominance_modes_preserve_complete_v2_bytes_and_empty_rows(self):
        for dominance, (trace, checked) in self.runs.items():
            with self.subTest(dominance=dominance):
                original = deepcopy(trace)
                self.assertEqual(set(trace), {'schema', 'representation', 'events'})
                self.assertEqual(trace['schema'], 'family5-hier-trace-v2')
                self.assertEqual(trace['representation'], 'exact-adjacent-cut-coalescing-v1')
                self.assertTrue(checked.empty_action_queries)
                actual = self.recover(trace, checked)
                self.assertEqual(actual['rows'], _plain(checked.empty_action_queries))
                self.assertEqual(actual['trace_sha256'], stream_digest(trace))
                self.assertEqual(actual['empty_action_sha256'], stream_digest(actual['rows']))
                self.assertEqual(actual['query_ids'], [e['seq'] for e in trace['events'] if e['kind'] == 'query'])
                self.assertEqual(actual['total_query_events'], len(checked.queries) + len(checked.empty_action_queries))
                self.assertEqual(len(actual['audits']), len(checked.empty_action_queries))
                self.assertFalse(actual['execution_authority'])
                self.assertFalse(actual['certificate_authority'])
                self.assertEqual(trace, original)

    def test_missing_foreign_and_rehashed_representations_reject(self):
        for dominance, (original, checked) in self.runs.items():
            for mutation in ('missing', 'foreign', 'wrong_type', 'extra_field', 'foreign_schema'):
                trace = deepcopy(original)
                if mutation == 'missing':
                    del trace['representation']
                elif mutation == 'foreign':
                    trace['representation'] = 'foreign-coalescing-v1'
                elif mutation == 'wrong_type':
                    trace['representation'] = True
                elif mutation == 'extra_field':
                    trace['extra'] = None
                else:
                    trace['schema'] = 'family5-hier-trace-v3'
                for rehash in (False, True):
                    pins = {'trace_sha256': stream_digest(trace)} if rehash else {}
                    with self.subTest(dominance=dominance, mutation=mutation, rehash=rehash), self.assertRaises(ValueError):
                        self.recover(trace, checked, **pins)

    def test_v2_hash_cannot_use_v1_projection_or_dropped_representation(self):
        for dominance, (trace, checked) in self.runs.items():
            for schema in ('family5-hier-trace-v1', 'family5-hier-trace-v2'):
                projected = dict(schema=schema, events=trace['events'])
                with self.subTest(dominance=dominance, schema=schema), self.assertRaisesRegex(ValueError, 'historical_trace_digest_mismatch'):
                    self.recover(trace, checked, trace_sha256=stream_digest(projected))
        # A v1 header with a representation remains an invalid v1 shape.
        case, bundle, trace = hand_trace()
        checked = verify_trace(trace, bundle, case)
        trace['representation'] = 'exact-adjacent-cut-coalescing-v1'
        with self.assertRaisesRegex(ValueError, 'trace_fields'):
            self.recover(trace, checked, trace_sha256=stream_digest(trace))


if __name__ == '__main__':
    unittest.main()
