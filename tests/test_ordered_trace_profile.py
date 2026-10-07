"""Tiny unchanged-result and bounded ordered-trace observations; no real run."""
import argparse,gc,json,os,signal,time,unittest
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import domain,plan,parallel_replay as full
from experiments.time_cut_v2.recorded_real.trace_observer import TraceObserver,TraceObservationEnd
from validation.real5_v2.shared_replay import verify_coalesced_trace
from validation.real5_v2.batch_jobs import BatchExecutor
from validation.real5_v2 import trace
from validation.trace5 import checker,coalesced
from tests import test_recorded_real_domain as fixtures
from tests.test_recovered_real_coalesced import capture
from tests.test_recovered_real_family import prepare

class OrderedTraceProfile(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.RecordedDomain();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.root=self.fixture.root
 def bindings(self):
  return (checker._Replay.selection,checker._dispatch_cells,checker._Replay.node,checker.digest,
   trace.RealPhysicsReplayMixin.run,trace.RealPhysicsReplayMixin.bound,coalesced.CoalescedReplay.compact)
 def test_ten_complete_results_queries_and_hooks_are_unchanged(self):
  originals=self.bindings();handler=signal.getsignal(signal.SIGALRM)
  for row in self.fixture.rows:
   for dominance in (False,True):
    data=capture(row,dominance);trusted=prepare(row);before=verify_coalesced_trace(data['trace'],data['bundle'],trusted)
    observer=TraceObserver(stop_after=False)
    with observer.hooks():after=verify_coalesced_trace(data['trace'],data['bundle'],trusted)
    self.assertEqual(before.export_queries(),after.export_queries())
    a,b=dict(before.summary),dict(after.summary);a.pop('elapsed_s');b.pop('elapsed_s');self.assertEqual(a,b)
    snapshot=observer.snapshot();self.assertTrue(snapshot['trace_returned']);self.assertEqual(snapshot['final_location']['cursor'],after.summary['events'])
    self.assertEqual(self.bindings(),originals);self.assertEqual(signal.getsignal(signal.SIGALRM),handler)
    self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));gc.collect();self.assertIsNone(observer.replay_ref())
 def test_timeout_and_checker_failure_restore_alarm_and_all_hooks(self):
  row=self.fixture.rows[0];data=capture(row,True);trusted=prepare(row);bindings=self.bindings();handler=signal.getsignal(signal.SIGALRM)
  observer=TraceObserver(seconds=.001)
  original=trace.RealPhysicsReplayMixin._run_original_tree
  def slow(obj):
   end=time.monotonic()+.02
   while time.monotonic()<end:pass
   return original(obj)
  with patch.object(trace.RealPhysicsReplayMixin,'_run_original_tree',slow),observer.hooks(),self.assertRaises(TraceObservationEnd):
   verify_coalesced_trace(data['trace'],data['bundle'],trusted)
  self.assertTrue(observer.snapshot()['samples']);self.assertFalse(observer.returned)
  failed=TraceObserver()
  with patch.object(trace.RealPhysicsReplayMixin,'_run_original_tree',side_effect=RuntimeError('sentinel')):
   with failed.hooks(),self.assertRaisesRegex(RuntimeError,'sentinel'):verify_coalesced_trace(data['trace'],data['bundle'],trusted)
  self.assertEqual(self.bindings(),bindings);self.assertEqual(signal.getsignal(signal.SIGALRM),handler)
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
 def test_complete_family_revalidated_then_diagnostic_stops_before_callbacks(self):
  row=self.fixture.rows[0];old=self.fixture.make_plan(row);new=dict(old,source_sha256='e'*64)
  with self.fixture.writer('capture') as writer:cap=domain.capture(old,self.root,writer,'a'*64);writer.finalize()
  path=self.root/'capture/capture.json';sha=cap['capture']['sha256'];cpus=tuple(sorted(os.sched_getaffinity(0)))[:2]
  with BatchExecutor(cpus,float(time.monotonic()+20),sha,worker_as=256*1024**2,kernel='interval-join-v1') as pool:
   with self.fixture.writer('observed') as writer:
    writer.write('run-binding.json',domain.chunks({'tiny_fixture':True}))
    with patch.object(domain,'receipt_rows',side_effect=RuntimeError('callbacks must not start')):
     result=full.observe_trace(old,new,self.root,writer,'a'*64,'b'*64,path,sha,pool)
    self.assertEqual({x['path'] for x in writer.files},full.PROFILE_FILES);writer.finalize()
  self.assertTrue(result['family_jobs_complete']);self.assertTrue(result['observations']['trace_returned'])
  self.assertFalse(result['structural_verified']);self.assertFalse(result['acceptance'])
  self.assertFalse((self.root/'observed/structural-summary.json').exists())
  self.assertTrue(plan.load(self.root/'observed/batch-ledger.json')['complete'])
 def test_post_family_window_covers_setup_and_preserves_preexisting_alarm(self):
  handler=signal.getsignal(signal.SIGALRM);observer=TraceObserver(seconds=.001)
  with self.assertRaises(TraceObservationEnd):
   with observer.hooks():
    observer.start()
    until=time.monotonic()+.02
    while time.monotonic()<until:pass
  self.assertIsNone(observer.run_started);self.assertTrue(observer.snapshot()['post_family_window_started'])
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
  signal.signal(signal.SIGALRM,lambda *a:None);signal.setitimer(signal.ITIMER_REAL,60)
  try:
   other=TraceObserver()
   with other.hooks(),self.assertRaisesRegex(ValueError,'existing alarm'):other.start()
   self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],59)
  finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,handler)

 def test_mode_context_is_bound_and_window_is_finite(self):
  a=argparse.Namespace(historical_plan_sha='a'*64,batch_kernel='interval-join-v1',
   capture_manifest_sha='b'*64,capture_result_sha='c'*64,capture_decision_sha='d'*64,capture_return_sha='e'*64)
  old={'input_sha256':'f'*64};normal=full.input_context(a,old);a.ordered_trace_profile=True
  self.assertNotEqual(full.input_context(a,old),normal);a.ordered_trace_profile=False;self.assertEqual(full.input_context(a,old),normal)
  for seconds in (True,0,181,float('inf'),float('nan')):
   with self.subTest(seconds=seconds),self.assertRaises(ValueError):TraceObserver(seconds=seconds)
if __name__=='__main__':unittest.main()
