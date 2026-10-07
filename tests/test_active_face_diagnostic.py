"""No-optimizer tests for the two-pass observation wrapper."""
from fractions import Fraction as F
import gzip
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import active_face_diagnostic as d
from validation.suffix5 import vendor_lp as v


def candidate(x, y, status=0):
    return SimpleNamespace(status=status, success=status == 0, message='hand candidate',
        x=x, fun=0, ineqlin=SimpleNamespace(marginals=y, residual=[0]*len(y)),
        eqlin=SimpleNamespace(marginals=[], residual=[]))


class DiagnosticTests(unittest.TestCase):
    def test_exact_candidate_and_hooks_are_preserved(self):
        task=dict(c=['-1'], A=[['1']], b=['2'], equalities=[])
        old=(v.linprog, v.solve_rational_equalities, v.verify_certificate)
        calls=[]
        def native(*args, **kwargs):
            calls.append(kwargs);return candidate([2], [-1])
        result=d.inspect_task(task, v, native)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['options'],dict(primal_feasibility_tolerance=1e-9,
            dual_feasibility_tolerance=1e-9, threads=1, time_limit=25.0))
        self.assertEqual(result['outcome'],'exact_candidate_returned')
        self.assertEqual(result['candidate_certificate']['objective'],'-2')
        self.assertFalse(result['acceptance'])
        self.assertEqual(old,(v.linprog,v.solve_rational_equalities,v.verify_certificate))

    def test_greedy_trap_records_every_failed_check_without_accepting(self):
        # Two nested upper bounds: normalized residual order prefers the looser
        # one, which consumes the final free rank and cannot be corrected.
        task=dict(c=['-1','0'],A=[['1','0'],['0','1'],['0','1']],
                  b=['0','1.000002','1'],equalities=[])
        result=d.inspect_task(task,v,lambda *a,**k:candidate([0,1.000001],[-1,0,0]))
        self.assertEqual(result['outcome'],'unresolved')
        self.assertIn('Exact active-constraint recovery',result['error'])
        self.assertEqual(len(result['native_passes']),1)
        self.assertTrue(result['eliminations'])
        self.assertTrue(any(r.get('violated_inequalities') for r in result['exact_checks']))
        self.assertFalse(result['acceptance'])

    def test_second_native_pass_is_forbidden(self):
        task=dict(c=['1'],A=[['1'],['-1']],b=['0','-1'],equalities=[])
        calls=[]
        def native(*a,**k):
            calls.append(1);return candidate(None,[],status=2)
        result=d.inspect_task(task,v,native)
        self.assertEqual(len(calls),1)
        self.assertIn('second native pass',result['error'])

    def test_exception_restores_all_hooks(self):
        old=(v.linprog,v.solve_rational_equalities,v.verify_certificate)
        def native(*a,**k):raise TimeoutError('fake native expiry')
        result=d.inspect_task(dict(c=['1'],A=[],b=[],equalities=[]),v,native)
        self.assertIn('TimeoutError',result['error'])
        self.assertEqual(old,(v.linprog,v.solve_rational_equalities,v.verify_certificate))

    def test_consumed_archive_and_full_model_pin(self):
        model=dict(example='unicode 雪',nested=[1,2]);sha=hashlib.sha256(d.canonical(model)).hexdigest()
        row=dict(kind='unresolved_model',descriptor=dict(ordinal=7),candidate=dict(job=dict(model=model)))
        raw=gzip.compress(d.canonical(row)+b'\n')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'proof.gz';path.write_bytes(raw)
            with patch.multiple(d,MODEL_PINS={7:sha},ARCHIVE_BYTES=len(raw),
                                ARCHIVE_SHA=hashlib.sha256(raw).hexdigest()):
                self.assertEqual(d.selected_models(path),{7:model})
                changed=bytearray(raw);changed[-1]^=1;path.write_bytes(changed)
                with self.assertRaisesRegex(ValueError,'consumed pilot archive'):
                    d.selected_models(path)

    def test_model_identity_mismatch_rejects_before_native_call(self):
        row=dict(kind='unresolved_model',descriptor=dict(ordinal=7),candidate=dict(job=dict(model={})))
        raw=gzip.compress(d.canonical(row)+b'\n')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'proof.gz';path.write_bytes(raw)
            with patch.multiple(d,MODEL_PINS={7:'0'*64},ARCHIVE_BYTES=len(raw),ARCHIVE_SHA=hashlib.sha256(raw).hexdigest()):
                with self.assertRaisesRegex(ValueError,'model bytes changed'):d.selected_models(path)


if __name__=='__main__':unittest.main()
