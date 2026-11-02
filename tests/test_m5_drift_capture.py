"""Parser-only regressions: no mock worker or numerical process is started."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from m5_drift_diagnostic import collect_ledgers,original_assertion_conditions


class DriftCapture(unittest.TestCase):
    def test_auxiliary_supervisor_ledger_is_not_a_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'run/slot-001').mkdir(parents=True)
            (root/'run/ledger.json').write_text(json.dumps(dict(status='INTEGRITY_FAILED',stages=[])))
            (root/'run/slot-001/ledger.json').write_text(json.dumps(dict(status='SUCCESS')))
            self.assertEqual(len(collect_ledgers([root])),1)
            self.assertEqual(collect_ledgers([root])[0]['status'],'INTEGRITY_FAILED')

    def test_missing_queue_is_not_silently_a_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):collect_ledgers([directory])

    def test_offline_conditions_match_both_original_assertions(self):
        ledger=dict(status='INTEGRITY_FAILED',stages=[dict(status='common_feasible_seed'),
            dict(status='INTEGRITY_FAILED'),dict(status='BLOCKED_INTEGRITY_FAILED')])
        self.assertTrue(original_assertion_conditions(ledger))
        ledger['stages'][2]['status']='PENDING'
        self.assertFalse(original_assertion_conditions(ledger))


if __name__=='__main__':unittest.main()
