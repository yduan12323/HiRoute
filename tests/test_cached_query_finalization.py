"""Exact finalization/reference comparisons and bounded diagnostic integration."""
from copy import deepcopy
import argparse,os,signal,time,unittest
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import domain,plan,parallel_replay as full
from experiments.time_cut_v2.recorded_real.finalization_observer import FinalizationObserver
from experiments.time_cut_v2.recorded_real.trace_observer import TraceObservationEnd
from validation.real5_v2 import shared_replay,shared_replay_cached as cached
from validation.real5_v2.batch_jobs import BatchExecutor
from validation.capture5.query_dag_digest import QueryDagEncoder
from validation.capture5.containers import query_digest
from tests import test_recorded_real_domain as fixtures
from tests.test_recovered_real_coalesced import capture
from tests.test_recovered_real_family import prepare

class CachedQueryFinalization(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.RecordedDomain();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root
 def test_ten_checked_traces_queries_and_full_legacy_hashes_match(self):
  for row in self.fixture.rows:
   for dominance in (False,True):
    with self.subTest(case=row['case_id'],dominance=dominance):
     data=capture(row,dominance);trusted=prepare(row);old=shared_replay.verify_coalesced_trace(data['trace'],data['bundle'],trusted)
     metrics={};stages=[];new=cached.verify_coalesced_trace(data['trace'],data['bundle'],trusted,
      metrics=metrics,on_stage=lambda name,**kw:stages.append(name))
     self.assertEqual(new.export_queries(),old.export_queries());self.assertEqual(new.snapshot(),old.snapshot())
     a,b=dict(new.summary),dict(old.summary);a.pop('elapsed_s');b.pop('elapsed_s');self.assertEqual(a,b)
     self.assertEqual(new.summary['query_freeze_sha256'],query_digest(new.queries))
     self.assertEqual(stages,['after_ordered_trace','trace_digest','query_freeze','query_digest','summary','trace_and_summary_freeze','finalization_returned'])
     self.assertGreater(metrics['logical_query_bytes'],0)
 def test_complete_opt_in_replay_keeps_every_query_and_callback_receipt(self):
  row=self.fixture.rows[0];old=self.fixture.make_plan(row);new=dict(old,source_sha256='e'*64)
  with self.fixture.writer('capture') as writer:cap=domain.capture(old,self.root,writer,'a'*64);writer.finalize()
  path=self.root/'capture/capture.json';sha=cap['capture']['sha256'];cpus=tuple(sorted(os.sched_getaffinity(0)))[:2]
  with self.fixture.writer('serial') as writer:domain.replay(old,self.root,writer,'a'*64,path,sha);writer.finalize()
  with BatchExecutor(cpus,float(time.monotonic()+20),sha,worker_as=256*1024**2,kernel='interval-join-v1') as pool:
   with self.fixture.writer('cached') as writer:
    out=full.replay(old,new,self.root,writer,'a'*64,'b'*64,path,sha,pool,shared_query_digest=True);writer.finalize()
  for name in ('query-index.json','callback-receipts.json'):
   self.assertEqual((self.root/'serial'/name).read_bytes(),(self.root/'cached'/name).read_bytes())
  self.assertTrue(out['structural_verified']);self.assertFalse(out['literal_G8_closed']);self.assertGreater(out['query_digest_cache']['cache_hits'],0)
 def test_finalization_profile_is_bounded_and_never_starts_callbacks(self):
  row=self.fixture.rows[0];old=self.fixture.make_plan(row);new=dict(old,source_sha256='e'*64)
  with self.fixture.writer('capture') as writer:cap=domain.capture(old,self.root,writer,'a'*64);writer.finalize()
  path=self.root/'capture/capture.json';sha=cap['capture']['sha256'];cpus=tuple(sorted(os.sched_getaffinity(0)))[:2]
  with BatchExecutor(cpus,float(time.monotonic()+20),sha,worker_as=256*1024**2,kernel='interval-join-v1') as pool:
   with self.fixture.writer('profile') as writer:
    writer.write('run-binding.json',domain.chunks({'fixture':True}))
    with patch.object(domain,'receipt_rows',side_effect=RuntimeError('callbacks must not start')):
     out=full.observe_finalization(old,new,self.root,writer,'a'*64,'b'*64,path,sha,pool)
    self.assertEqual({x['path'] for x in writer.files},full.FINALIZATION_FILES);writer.finalize()
  self.assertTrue(out['observations']['finalization_returned']);self.assertTrue(out['family_jobs_complete'])
  self.assertFalse(out['acceptance']);self.assertFalse(out['structural_verified'])
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
 def test_finalization_interruption_restores_alarm_and_preserves_math_failure(self):
  row=self.fixture.rows[0];data=capture(row,True);trusted=prepare(row);observer=FinalizationObserver(seconds=.001)
  original=QueryDagEncoder.digest;handler=signal.getsignal(signal.SIGALRM)
  def slow(obj):
   until=time.monotonic()+.02
   while time.monotonic()<until:pass
   return original(obj)
  try:
   with patch.object(QueryDagEncoder,'digest',slow),self.assertRaises(TraceObservationEnd):
    cached.verify_coalesced_trace(data['trace'],data['bundle'],trusted,on_stage=observer.observe)
  finally:observer.close()
  self.assertTrue(observer.samples);self.assertEqual(signal.getsignal(signal.SIGALRM),handler)
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
  bad=deepcopy(data);bad['trace']['events'][-1]['payload']['canonical']['result']['charges']=['999']
  with self.assertRaises(ValueError):cached.verify_coalesced_trace(bad['trace'],bad['bundle'],trusted)
 def test_context_binds_both_opt_in_modes(self):
  args=argparse.Namespace(historical_plan_sha='a'*64,batch_kernel='interval-join-v1',capture_manifest_sha='b'*64,
   capture_result_sha='c'*64,capture_decision_sha='d'*64,capture_return_sha='e'*64)
  old={'input_sha256':'f'*64};base=full.input_context(args,old)
  args.shared_query_digest=True;optimized=full.input_context(args,old);self.assertNotEqual(base,optimized)
  args.query_finalization_profile=True;self.assertNotEqual(optimized,full.input_context(args,old))
if __name__=='__main__':unittest.main()
