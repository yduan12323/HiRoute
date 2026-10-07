"""Small instrumentation tests; no real capture or diagnostic phase run."""
import json,signal,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.time_cut_v2.recorded_real.diagnose import Observer,DiagnosticStop
from tests.test_recovered_real_family import prepare
from tests.test_recovered_real_coalesced import capture
from validation.real5_v2.shared_replay import verify_coalesced_trace

class Diagnostic(unittest.TestCase):
 def test_tiny_results_queries_and_sources_are_unchanged(self):
  rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
  from validation.real5_v2 import family
  from validation.family5 import independent_oracle_v2 as oracle
  originals=(family._verify_bundle,oracle.exact_family_equal)
  for row in rows:
   for dominance in (False,True):
    with self.subTest(case=row['case_id'],dominance=dominance):
     data=capture(row,dominance);trusted=prepare(row)
     before=verify_coalesced_trace(data['trace'],data['bundle'],trusted)
     observer=Observer();after=observer.run(lambda:verify_coalesced_trace(data['trace'],data['bundle'],trusted),1)
     self.assertEqual(before.export_queries(),after.export_queries())
     a=dict(before.summary);b=dict(after.summary);a.pop('elapsed_s');b.pop('elapsed_s');self.assertEqual(a,b)
     self.assertEqual(originals,(family._verify_bundle,oracle.exact_family_equal))
     self.assertEqual(observer.calls['family_validation']['completed'],1)
     self.assertEqual(observer.calls['trace_walk']['completed'],1)
     self.assertEqual(observer.active,[])
     optimized=Observer('v3-cached');fast=optimized.run(lambda:verify_coalesced_trace(data['trace'],data['bundle'],trusted),1)
     self.assertEqual(before.export_queries(),fast.export_queries())
     c=dict(fast.summary);c.pop('elapsed_s');self.assertEqual(a,c)
     self.assertEqual(originals,(family._verify_bundle,oracle.exact_family_equal))
     self.assertLessEqual(optimized.memo.stored_bytes,8*1024**2)
 def test_budget_interruption_restores_all_hooks_and_alarm(self):
  from validation.real5_v2 import family
  original=family._verify_bundle;handler=signal.getsignal(signal.SIGALRM);observer=Observer()
  def busy():
   while True:pass
  with self.assertRaises(DiagnosticStop):observer.run(busy,.02)
  self.assertIs(family._verify_bundle,original);self.assertEqual(signal.getsignal(signal.SIGALRM),handler)
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertTrue(observer.samples)
 def test_exception_and_sampling_preserve_return_values(self):
  observer=Observer();observer.deadline=time.monotonic()+5
  def answer(value):observer.sample(None,sys._getframe());return value
  item=object();self.assertIs(observer.wrap('sampled',answer)(item),item)
  def fail():raise ValueError('retained')
  with self.assertRaisesRegex(ValueError,'retained'):observer.wrap('failing',fail)()
  self.assertEqual(observer.calls['failing']['completed'],0);self.assertEqual(observer.active,[])
  self.assertEqual(observer.samples[0]['active'],['sampled'])
  self.assertLessEqual(len(observer.samples[0]['stack']),24)
 def test_existing_alarm_is_not_silently_replaced(self):
  with patch('signal.getitimer',return_value=(10.,1.)):
   with self.assertRaisesRegex(ValueError,'existing alarm'):Observer().run(lambda:None,1)

if __name__=='__main__':unittest.main()
