"""Mocked audit/controller failures only; no Core or numerical solver imports."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from parity_receipts import atomic_json, run_parity


def inputs():
    return ([dict(id=i) for i in ('a', 'b')],
            [dict(id=i, analytic_match=True, semantic=i) for i in ('a', 'b')])


class ParityReceipts(unittest.TestCase):
    def test_exception_preserves_completed_and_unrun_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def core(case, method):
                calls.append((case['id'], method))
                if len(calls) == 2:
                    live = json.loads((Path(directory) / 'results.json').read_text())
                    self.assertEqual(live['rows'][0]['core'][0]['status'], 'completed')
                    self.assertEqual(live['rows'][0]['core'][1]['status'], 'running')
                    self.assertEqual(len(live['remaining_unrun']), 2)
                    self.assertFalse(live['passed'])
                    raise RuntimeError('mock Core failure')
                return case['id']

            result = run_parity(*inputs(), directory, core, lambda x: x,
                                case_sha256='fixture', independent_ok=True)
            saved = json.loads((Path(directory) / 'results.json').read_text())
            self.assertEqual(saved, result)
            self.assertEqual(len(calls), 2)
            self.assertEqual(saved['rows'][0]['core'][1]['error_type'], 'RuntimeError')
            self.assertEqual(saved['rows'][0]['core'][1]['status'], 'core_error')
            self.assertTrue(saved['finalized'])
            self.assertFalse(saved['parity_complete'])
            self.assertFalse(saved['passed'])
            self.assertEqual(len(saved['remaining_unrun']), 2)

    def test_abrupt_process_exit_keeps_uncertain_active_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            script = '''
import os,sys
from parity_receipts import run_parity
cases=[dict(id=i) for i in ('a','b')]
rows=[dict(id=i,analytic_match=True,semantic=i) for i in ('a','b')]
def core(case,method):
    if method=='scale':os._exit(23)
    return case['id']
run_parity(cases,rows,sys.argv[1],core,lambda x:x,case_sha256='fixture',independent_ok=True)
'''
            child = subprocess.run([sys.executable, '-c', script, directory],
                                   cwd=Path(__file__).resolve().parent,
                                   capture_output=True, timeout=10)
            self.assertEqual(child.returncode, 23, child.stderr)
            saved = json.loads((Path(directory) / 'results.json').read_text())
            self.assertEqual(saved['rows'][0]['core'][0]['status'], 'completed')
            self.assertEqual(saved['rows'][0]['core'][1]['status'], 'running')
            self.assertEqual(saved['uncertain'], [dict(case_id='a', method='scale')])
            self.assertEqual(len(saved['remaining_unrun']), 2)
            self.assertFalse(saved['finalized'])
            self.assertFalse(saved['passed'])

    def test_mismatch_and_interrupt_never_pass(self):
        for outcome in ('wrong', SystemExit(0), KeyboardInterrupt()):
            with self.subTest(outcome=repr(outcome)), tempfile.TemporaryDirectory() as directory:
                def core(case, method):
                    if isinstance(outcome, BaseException):raise outcome
                    return outcome
                saved = run_parity(*inputs(), directory, core, lambda x: x,
                                   case_sha256='fixture', independent_ok=True)
                self.assertFalse(saved['passed'])
                self.assertTrue(saved['finalized'])
                self.assertEqual(len(saved['remaining_unrun']), 3)
                self.assertEqual(saved['rows'][0]['core'][0]['status'],
                                 'core_interrupted' if isinstance(outcome, BaseException) else 'mismatch')

    def test_all_slots_required_for_success(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = run_parity(*inputs(), directory, lambda c, m: c['id'], lambda x: x,
                               case_sha256='fixture', independent_ok=True)
            self.assertTrue(saved['passed'])
            self.assertTrue(saved['finalized'])
            self.assertTrue(saved['parity_complete'])
            self.assertEqual(saved['remaining_unrun'], [])
            self.assertEqual(saved['uncertain'], [])
        with tempfile.TemporaryDirectory() as directory:
            saved = run_parity(*inputs(), directory, lambda c, m: self.fail('called'),
                               lambda x: x, case_sha256='fixture', independent_ok=False)
            self.assertFalse(saved['passed'])
            self.assertEqual(len(saved['remaining_unrun']), 4)
            self.assertEqual(saved['phase'], 'independent_failed')

    def test_failed_atomic_replace_preserves_previous_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / 'results.json'
            atomic_json(receipt, dict(passed=False))
            with patch('parity_receipts.os.replace', side_effect=OSError('mock I/O failure')):
                with self.assertRaises(OSError):atomic_json(receipt, dict(passed=True))
            self.assertEqual(json.loads(receipt.read_text()), dict(passed=False))


if __name__ == '__main__':unittest.main()
