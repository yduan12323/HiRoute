"""Opt-in historical acceptance assertion; not independent reproduction."""
import json
from pathlib import Path
import unittest
from experiments.dev_coverage_tranche_v1 import bindings
from experiments.mechanism_recovery_v1 import run as base

class ArchivedTrancheReceiptTests(unittest.TestCase):
    def test_link_matches_preserved_completed_gate_receipt(self):
        root = Path(__file__).resolve().parents[1]
        link = bindings.LINKED_GATE
        evidence = json.loads((root/link['evidence']).read_bytes())
        for field in ('manifest_sha256', 'ledger_sha256', 'terminal_audit_sha256'):
            self.assertEqual(link[field], evidence[field])
        self.assertEqual(base.file_hash(root/'validation/dev_coverage_tranche_v1/prerequisite_pair_audit.json'),
                         link['terminal_audit_sha256'])
        self.assertIs(evidence['operational_admission'], True)
        self.assertIs(evidence['all_cleanup_verified'], True)
        self.assertEqual(evidence['declared_slots'], 5)
        self.assertIsNone(evidence['completed_speed_ratio'])
