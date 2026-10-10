"""Fixed D0/D1 retained-node profile selection from pinned collector receipts."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from experiments.time_cut_v2.recorded_real import g8_node_batch, plan, runtime


class RetainedProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'acceptance.json'

    def select(self, receipt):
        self.path.write_bytes(plan.canonical(receipt) + b'\n')
        return g8_node_batch.profile_for(SimpleNamespace(
            collector_acceptance=self.path,
            collector_acceptance_sha=plan.pin(self.path)['sha256']))

    def test_exact_variant_bound_d0_and_legacy_d1_profiles(self):
        d0 = dict(variant_id='C01::HIER::D-off', dominance=False,
                  population_freeze_sha256='f2f5d282b226b69a686d694663089594b7db613436bd266cddea219d91f80b07')
        self.assertIs(self.select(d0), runtime.RETAINED_NODE_AUDIT_D0)
        self.assertIs(self.select({}), runtime.RETAINED_NODE_AUDIT)
        self.assertEqual(runtime.RETAINED_NODE_AUDIT.evidence_bytes, 2 * runtime.GiB)
        self.assertEqual(runtime.RETAINED_NODE_AUDIT_D0.evidence_bytes, 4 * runtime.GiB)
        self.assertEqual(runtime.RETAINED_NODE_AUDIT_D0.worker_evidence_bytes,
                         4 * runtime.GiB - 16 * runtime.MiB)
        for key, value in (('dominance', True), ('population_freeze_sha256', '0'*64),
                           ('variant_id', 'C01::FLAT::D-off')):
            wrong = dict(d0, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.select(wrong)
        with self.assertRaises(ValueError):
            self.select(dict(variant_id='C01::HIER::D-on', dominance=True))

    def test_receipt_bytes_remain_pinned(self):
        self.path.write_text('{}\n')
        with self.assertRaises(ValueError):
            g8_node_batch.profile_for(SimpleNamespace(
                collector_acceptance=self.path, collector_acceptance_sha='0'*64))


if __name__ == '__main__':
    unittest.main()
