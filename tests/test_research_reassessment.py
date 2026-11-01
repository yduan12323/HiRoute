"""Historical scientific-artifact integrity checks; never launch a solver."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'reassessment', ROOT / 'tools/reassess_hierarchy_evidence.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReassessmentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT / 'docs/n64_coverage_stage_results.json').read_text())
        self.matrix = json.loads((ROOT / 'configs/charging_coverage_dev_matrix.json').read_text())
        self.coverage = json.loads((ROOT / 'docs/shandong_charging_coverage_results.json').read_text())

    def reduce(self, source=None):
        return MODULE.reduce_evidence(
            self.source if source is None else source, self.matrix, self.coverage)

    def test_committed_reduction_reproduces_all_denominators_and_tradeoffs(self):
        committed = json.loads((ROOT / 'docs/hierarchy_reassessment_evidence.json').read_text())
        for relative, expected in committed.pop('input_sha256').items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected)
        self.assertEqual(self.reduce(), committed)
        for method in MODULE.METHODS:
            outcome = committed['outcomes'][method]
            self.assertEqual(sum(outcome['status_counts'].values()), 48)
        common = committed['populations']['common_exact']
        self.assertEqual(common['bound_queries']['scale_less'], 36)
        self.assertEqual(common['heap_pushes']['scale_more'], 36)
        self.assertEqual(committed['new_real_solver_rows'], 0)

    def test_rejects_lost_duplicate_or_substituted_cells(self):
        variants = []
        lost = deepcopy(self.source); lost['rows'].pop(); variants.append(lost)
        duplicate = deepcopy(self.source); duplicate['rows'].append(duplicate['rows'][0]); variants.append(duplicate)
        substitute = deepcopy(self.source)
        for row in substitute['rows']:
            if row['query_id'] == 'WD01':
                row['query_id'] = 'OTHER'
        variants.append(substitute)
        for source in variants:
            with self.subTest(), self.assertRaises(ValueError):
                self.reduce(source)

    def test_rejects_paired_domain_and_full_key_changes(self):
        for field, value in [('candidate_domain_sha256', 'other'), ('key', ['other'])]:
            source = deepcopy(self.source)
            source['rows'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.reduce(source)


if __name__ == '__main__':
    unittest.main()
