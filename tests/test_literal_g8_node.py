"""Scoped original-node G8 evidence and fail-closed binding checks."""
from copy import deepcopy
import json
import unittest

from validation.suffix5.literal_g8_node import audit_node, source_pins
from validation.suffix5.test_convex_checker import hand_ledger
from tests.test_recovered_real_coalesced import ROOT, capture, prepare
from validation.real5_v2.coalesced import verify_coalesced_trace


class LiteralG8NodeTests(unittest.TestCase):
    def test_strict_unattained_equality_stays_scoped(self):
        checked, ledger = hand_ledger()
        result = audit_node(checked, ledger['query_seq'],
                            expected=source_pins(checked, ledger['query_seq']),
                            max_models=3, ledger=ledger)
        self.assertEqual(result['status'], 'verified_bound')
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
            audit_node(checked, seq, expected=bad, max_models=3, ledger=ledger)
        for change in ('drop', 'duplicate', 'swap'):
            wrong = deepcopy(ledger)
            if change == 'drop':
                wrong['models'].pop()
            elif change == 'duplicate':
                wrong['models'][1] = deepcopy(wrong['models'][0])
            else:
                wrong['models'][0], wrong['models'][1] = wrong['models'][1], wrong['models'][0]
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit_node(checked, seq, expected=pins, max_models=3, ledger=wrong)
        with self.assertRaises(ValueError):
            audit_node(checked, seq, expected=pins, max_models=3)

    def test_model_cap_is_unresolved(self):
        checked, ledger = hand_ledger()
        seq = ledger['query_seq']
        result = audit_node(checked, seq, expected=source_pins(checked, seq),
                            max_models=2, ledger=ledger)
        self.assertEqual(result['status'], 'unresolved_model_cap')
        self.assertFalse(result['literal_G8_closed'])

    def test_guarded_coalesced_exact_empty_and_source_binding(self):
        row = json.loads((ROOT / 'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
        captured = capture(row, True)
        checked = verify_coalesced_trace(captured['trace'], captured['bundle'], prepare(row))
        self.assertEqual(next(q for q in checked.export_queries() if q['query_seq'] == 46)['query_seq'], 46)
        pins = source_pins(checked, 46)
        result = audit_node(checked, 46, expected=pins, max_models=0)
        self.assertEqual(result['status'], 'exact_empty')
        self.assertEqual(result['exact_model_count'], 0)
        self.assertFalse(result['literal_G8_closed'])
        wrong = deepcopy(pins)
        wrong['region_tree_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            audit_node(checked, 46, expected=wrong, max_models=0)


if __name__ == '__main__':
    unittest.main()
