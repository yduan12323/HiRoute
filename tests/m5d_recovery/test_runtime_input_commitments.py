"""Source-only plans require external artifacts; toy inputs test integrity only."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.dev_cohort_v1 import run as cohort, runtime_inputs as runtime
from experiments.dev_coverage_tranche_v1 import run as tranche, bindings
from experiments.mechanism_recovery_v1 import run as base
from synthetic_runtime_inputs import toy_spec, toy_prefix, toy_binding


class RuntimeInputCommitmentTests(unittest.TestCase):
    def test_published_plans_have_commitments_without_real_pool_records(self):
        specs = list(cohort.SPECS.values()) + [d for c in bindings.PLAN['cases'] for d in c['domains']]
        for spec in specs:
            with self.subTest(case=spec['case_id']):
                self.assertNotIn('original_pool_prefix', spec)
                self.assertNotIn('candidate_site_ids', spec['original_binding'])
                self.assertRegex(spec['original_pool_prefix_sha256'], r'^[0-9a-f]{64}$')
                self.assertRegex(spec['original_binding']['candidate_site_ids_sha256'], r'^[0-9a-f]{64}$')

    def test_runtime_commitments_bind_order_count_anchor_and_effects(self):
        spec = toy_spec(next(iter(cohort.SPECS.values())))
        prefix = toy_prefix(spec)
        self.assertEqual(runtime.compact_binding(toy_binding(spec)), spec['original_binding'])
        runtime.require_prefix(prefix, spec)
        for change in (lambda p: p.reverse(), lambda p: p.pop(),
                       lambda p: p[0].update(anchor_id='different-toy-anchor'),
                       lambda p: p[0].update(effects=['S']),
                       lambda p: p[0].update(site_id=p[1]['site_id'])):
            bad = copy.deepcopy(prefix)
            change(bad)
            with self.assertRaises(ValueError):
                runtime.require_prefix(bad, spec)
        self.assertFalse(runtime.ordered_candidates_match(reversed(toy_binding(spec)['candidate_site_ids']), spec))

    def test_missing_artifacts_fail_before_graph_load_without_writing_fallback(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(base, 'load_graph') as graph:
            root = Path(temp)
            plan = tranche.prospective()
            for extract in (lambda: cohort.extract_case(root, cohort.CASES[0], cohort.COHORT['inputs']),
                            lambda: tranche.extract_case(root, plan['case_id'], plan['inputs'], plan)):
                with self.assertRaisesRegex(FileNotFoundError, 'docs/REPRODUCING.md'):
                    extract()
                self.assertEqual(list(root.iterdir()), [])
            graph.assert_not_called()
