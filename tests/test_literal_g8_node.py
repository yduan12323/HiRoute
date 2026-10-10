"""Scoped original-node G8 evidence and fail-closed binding checks."""
from copy import deepcopy
import json
import resource
import sys
import unittest
from unittest.mock import patch

from validation.suffix5.literal_g8_node import audit_node, source_pins, reconstruct_node_domain
from validation.suffix5.test_convex_checker import hand_ledger
from tests.test_recovered_real_coalesced import ROOT, capture, prepare
from validation.real5_v2.coalesced import verify_coalesced_trace
from validation.suffix5.independent_convex_model import build_model
from validation.suffix5.convex_checker import check_regime, aggregate_records
from validation.suffix5.test_convex_checker import hand_record
from validation.suffix5.test_certificate_checker import inherited_open_context
from tests.test_restricted_suffix_v2 import foreign_context
from validation.suffix5.solver import SolveBudget
from tests.test_recovered_real_family import capture as baseline_capture
from validation.real5_v2 import verify_trace as verify_baseline_trace
from validation.trace5.coalesced import _connected_components


class LiteralG8NodeTests(unittest.TestCase):
    def test_strict_unattained_equality_stays_scoped(self):
        checked, ledger = hand_ledger()
        with patch.object(type(checked), 'export_queries',
                          side_effect=AssertionError('whole query population detached')):
            result = audit_node(checked, ledger['query_seq'],
                                expected=source_pins(checked, ledger['query_seq']),
                                max_models=3, ledger=ledger, indexed_only=True)
        self.assertEqual(result['status'], 'indexed_verified_bound')
        self.assertEqual(result['exact_result'],
                         {'status': 'primary_unattained', 'primary_infimum': '2'})
        self.assertEqual(result['exact_model_count'], 3)
        self.assertFalse(result['literal_G8_closed'])

    def test_missing_or_tampered_evidence_rejects(self):
        checked, ledger = hand_ledger()
        seq = ledger['query_seq']
        pins = source_pins(checked, seq)
        bad = deepcopy(pins)
        bad['query_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            audit_node(checked, seq, expected=bad, max_models=3, ledger=ledger, indexed_only=True)
        for change in ('drop', 'duplicate', 'swap'):
            wrong = deepcopy(ledger)
            if change == 'drop':
                wrong['models'].pop()
            elif change == 'duplicate':
                wrong['models'][1] = deepcopy(wrong['models'][0])
            else:
                wrong['models'][0], wrong['models'][1] = wrong['models'][1], wrong['models'][0]
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit_node(checked, seq, expected=pins, max_models=3, ledger=wrong, indexed_only=True)
        with self.assertRaises(ValueError):
            audit_node(checked, seq, expected=pins, max_models=3, indexed_only=True)

    def test_model_cap_is_unresolved(self):
        checked, ledger = hand_ledger()
        seq = ledger['query_seq']
        result = audit_node(checked, seq, expected=source_pins(checked, seq),
                            max_models=2, ledger=ledger, indexed_only=True)
        self.assertEqual(result['status'], 'unresolved_model_cap')
        self.assertFalse(result['literal_G8_closed'])

    def test_guarded_coalesced_exact_empty_and_source_binding(self):
        row = json.loads((ROOT / 'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
        captured = capture(row, True)
        checked = verify_coalesced_trace(captured['trace'], captured['bundle'], prepare(row))
        nonempty = next(q for q in checked.export_queries() if q['query_seq'] == 7)
        domain = reconstruct_node_domain(checked, 7, nonempty['family_ids'],
                                         nonempty['actions'])
        self.assertEqual(domain['actions'], [['A', 'C']])
        # Darwin reports ru_maxrss in bytes; retain the established 256 MiB cap.
        rss_scale = 1 if sys.platform == 'darwin' else 1024
        rss_bytes = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * rss_scale
        budget = SolveBudget(max_passes=30, wall_seconds=30, rss_mib=256,
                             rss_reader=rss_bytes)
        bounded = audit_node(checked, 7, expected=source_pins(checked, 7),
                             max_models=1, budget=budget)
        self.assertEqual((bounded['status'], bounded['exact_model_count'],
                          bounded['exact_result']['J'], bounded['recorded_bound']),
                         ('verified_bound', 1, '14', '3'))
        self.assertLessEqual(rss_bytes(), 256 * 1024**2)
        with self.assertRaises(ValueError):
            reconstruct_node_domain(checked, 7, nonempty['family_ids'], [])
        other_family = next(q for q in checked.export_queries() if q['query_seq'] == 46)['family_ids']
        self.assertNotEqual(nonempty['family_ids'], other_family)
        with self.assertRaises(ValueError):
            reconstruct_node_domain(checked, 7, other_family, nonempty['actions'])
        self.assertEqual(next(q for q in checked.export_queries() if q['query_seq'] == 46)['query_seq'], 46)
        pins = source_pins(checked, 46)
        with (patch.object(type(checked), 'snapshot', side_effect=AssertionError('whole trace detached')),
              patch.object(type(checked), 'export_queries', side_effect=AssertionError('whole query population detached')),
              patch.object(type(checked.bundle), 'snapshot', side_effect=AssertionError('whole bundle detached'))):
            result = audit_node(checked, 46, expected=pins, max_models=0)
        self.assertEqual(result['status'], 'exact_empty')
        self.assertEqual(result['exact_model_count'], 0)
        self.assertFalse(result['literal_G8_closed'])
        wrong = deepcopy(pins)
        wrong['region_tree_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            audit_node(checked, 46, expected=wrong, max_models=0)

        # Both are genuine, distinct zero-model queries from this checked trace.
        other = source_pins(checked, 50)
        foreign_ledger = dict(schema='family5-suffix-query-ledger-v2', query_seq=50,
                              query_sha256=other['query_sha256'],
                              trace_sha256=other['trace_sha256'], models=[],
                              result={'status': 'empty_restricted_family'})
        self.assertEqual(audit_node(checked, 50, expected=other, max_models=0,
                                    ledger=foreign_ledger)['status'], 'exact_empty')
        with self.assertRaises(ValueError):
            audit_node(checked, 46, expected=pins, max_models=0,
                       ledger=foreign_ledger)

    def test_baseline_real_trace_is_explicitly_unsupported(self):
        row = json.loads((ROOT / 'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
        captured = baseline_capture(row, True)
        checked = verify_baseline_trace(captured['trace'], captured['bundle'], prepare(row))
        seq = checked.export_queries()[0]['query_seq']
        result = audit_node(checked, seq, expected={}, max_models=0)
        self.assertEqual(result['status'], 'unsupported_original_node_domain')
        self.assertFalse(result['literal_G8_closed'])

    def test_distinct_ancestry_and_inherited_energy_are_preserved(self):
        ctx, ids = foreign_context()
        self.assertNotEqual(ids[0], ids[1])
        # Identical singleton cuts with separate guarded histories form one
        # connected component under the supported coalescing grammar.
        self.assertEqual(ctx.snapshot()['nodes'][ids[0]]['output'],
                         ctx.snapshot()['nodes'][ids[1]]['output'])
        self.assertEqual([members for members, _ in
                          _connected_components([ctx._pieces[fid] for fid in ids])],
                         [[0, 1]])
        models = [build_model(ctx, fid, [['c', 'C']], [0]) for fid in ids]
        self.assertNotEqual(models[0], models[1])
        self.assertEqual([model['family_id'] for model in models], ids)
        inherited, fid = inherited_open_context()
        model = build_model(inherited, fid, [['o', 'C']], [0])
        self.assertEqual([row['strict'] for row in model['lp']['rows'][:3]],
                         [True, True, True])
        self.assertEqual([row['rhs'] for row in model['lp']['rows'][:3]],
                         ['-3', '4', '-11'])

    def test_secondary_unattained_remains_distinct_from_primary(self):
        ctx, record = hand_record('CS', 0)
        self.assertEqual(check_regime(ctx, record)['status'],
                         'secondary_unattained')
        self.assertEqual(record['result']['secondary_infimum'], '0')

    def test_all_infeasible_models_have_empty_result_but_nonempty_language(self):
        ctx, record = hand_record('C', 2)
        self.assertEqual(check_regime(ctx, record)['status'], 'closed_infeasible')
        self.assertEqual(aggregate_records([record])['status'], 'empty_restricted_family')
        self.assertEqual(len([record]), 1)


if __name__ == '__main__':
    unittest.main()
