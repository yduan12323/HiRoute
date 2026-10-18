"""Opt-in historical comparator receipt check; not independent reproduction."""
import hashlib
import json
from pathlib import Path
import unittest
from experiments.sequential_transport_gate_v1 import run as gate

class ArchivedComparatorTests(unittest.TestCase):
    def test_fixed_comparator_is_first_od07_indexed(self):
        m = json.loads(gate.TEMPLATE.read_bytes())
        repo = Path(__file__).resolve().parents[1]
        ref = m['comparator']
        bundle = repo/ref['bundle_path']
        self.assertEqual(gate.file_hash(bundle), ref['bundle_sha256'])
        raw = json.loads(bundle.read_bytes())['files'][ref['artifact_path']].encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['artifact_sha256'])
        results = json.loads((bundle.parent/'results.json').read_bytes())['arms']
        arm = next(a for a in results if a['case'] == m['case_id'] and a['strategy'] == 'indexed')
        self.assertEqual(arm['index'], 3)
        sequence, charges, old = gate.comparator_plan(dict(m, repo=str(repo)))
        self.assertTrue(sequence); self.assertTrue(charges)
        self.assertIn('source_sha256', old)
