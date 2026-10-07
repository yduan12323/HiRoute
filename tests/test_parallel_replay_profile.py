"""Tiny complete trace differential for optional process batch profiling."""
import json,os,time,unittest
from pathlib import Path
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real.parallel_profile import run_profile
from validation.real5_v2.batch_jobs import BatchExecutor
from validation.real5_v2.shared_replay import verify_coalesced_trace
from validation.real5_v2 import family
from tests.test_recovered_real_family import prepare
from tests.test_recovered_real_coalesced import capture
ROOT=Path(__file__).resolve().parents[1]
class ParallelProfile(unittest.TestCase):
 def test_tiny_traces_preserve_all_queries_counts_and_hooks(self):
  rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
  original=family._verify_bundle
  for row in rows:
   for dominance in (False,True):
    with self.subTest(case=row['case_id'],dominance=dominance):
     data=capture(row,dominance);trusted=prepare(row);baseline=verify_coalesced_trace(data['trace'],data['bundle'],trusted)
     with BatchExecutor(tuple(sorted(os.sched_getaffinity(0)))[:2],float(time.monotonic()+15),'b'*64,worker_as=256*1024**2) as pool:
      after,error,observer=run_profile(data,trusted,pool)
      self.assertIsNone(error);self.assertIsNotNone(after);self.assertTrue(pool.snapshot()['complete'])
      self.assertEqual(baseline.export_queries(),after.export_queries())
      a=dict(baseline.summary);b=dict(after.summary);a.pop('elapsed_s');b.pop('elapsed_s');self.assertEqual(a,b)
      self.assertIs(family._verify_bundle,original)
 def test_tau_kernel_preserves_tiny_complete_traces(self):
  rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
  for row in rows:
   for dominance in (False,True):
    data=capture(row,dominance);trusted=prepare(row);baseline=verify_coalesced_trace(data['trace'],data['bundle'],trusted)
    with BatchExecutor(tuple(sorted(os.sched_getaffinity(0)))[:2],float(time.monotonic()+15),'b'*64,worker_as=256*1024**2,kernel='tau-precompute-v1') as pool:
     after,error,observer=run_profile(data,trusted,pool)
     self.assertIsNone(error);self.assertTrue(pool.snapshot()['complete'])
     self.assertEqual(baseline.export_queries(),after.export_queries())
     a=dict(baseline.summary);b=dict(after.summary);a.pop('elapsed_s');b.pop('elapsed_s');self.assertEqual(a,b)
 def test_interrupted_profile_is_not_a_completed_join(self):
  rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
  data=capture(rows[0],True);trusted=prepare(rows[0]);original=family._verify_bundle
  with BatchExecutor(tuple(sorted(os.sched_getaffinity(0)))[:2],float(time.monotonic()+10),'b'*64,worker_as=256*1024**2) as pool:
   with patch('experiments.time_cut_v2.recorded_real.parallel_profile.MAX_POST_DECODE_SECONDS',.001):
    result,error,observer=run_profile(data,trusted,pool)
   self.assertIsNone(result);self.assertEqual(error['type'],'DiagnosticStop');self.assertFalse(pool.snapshot()['complete'])
  self.assertIs(family._verify_bundle,original)
  self.assertTrue(all(s.process.poll() is not None for s in pool.slots))
if __name__=='__main__':unittest.main()
