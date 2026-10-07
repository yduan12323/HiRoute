"""Tiny fresh-family preview and byte commitments; no C01 or LP launch."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
import json,os,time,unittest
from unittest.mock import patch
from tests import test_recorded_real_domain as fixtures
from tests.test_recovered_real_family import prepare
from validation.real5_v2.shared_replay_cached import verify_coalesced_trace
from validation.real5_v2.batch_jobs import BatchExecutor
from validation.family5.checker import _plain
from experiments.time_cut_v2.recorded_real import plan,domain,model_preview as preview
from experiments.time_cut_v2.recorded_real.logical_models import count_logical_models
from validation.suffix5.preview_selection import select_preview

class ModelPreview(unittest.TestCase):
 def setUp(self):
  self.fx=fixtures.RecordedDomain();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
  self.root=self.fx.root;self.cpus=tuple(sorted(os.sched_getaffinity(0)))[:2]
 def inputs(self):
  row=deepcopy(self.fx.rows[1]);row['query']['charging_segments']=[[0,2,1,0],[2,5,2,-2]]
  original=self.fx.make_plan(row);trusted=prepare(row)
  with self.fx.writer('capture') as w:cap=domain.capture(original,self.root,w,'a'*64);w.finalize()
  path=self.root/'capture/capture.json';payload=plan.load(path)
  with self.fx.writer('replay') as w:
   summary=domain.replay(original,self.root,w,'a'*64,path,cap['capture']['sha256']);w.finalize()
  index=plan.load(self.root/'replay/query-index.json')
  logical=count_logical_models(index,trusted,summary['checked'])['logical_model_plan']
  return original,trusted,index,logical,path,cap['capture']['sha256']
 def pool(self,sha):return BatchExecutor(self.cpus,float(time.monotonic()+30),sha,worker_as=256*1024**2,kernel='interval-join-v1')
 def test_genuine_family_recheck_selection_and_payload_bytes(self):
  original,trusted,index,logical,path,sha=self.inputs()
  with self.pool(sha) as pool,self.fx.writer('preview') as w:
   result=preview.preview_capture(original,'a'*64,index,trusted,logical,path,sha,pool,w);w.finalize()
  self.assertTrue(pool.snapshot()['complete']);self.assertTrue(all(s.process.poll() is not None for s in pool.slots))
  self.assertEqual(result['selected_models'],select_preview(logical,trusted)['selected_models'])
  self.assertFalse(result['literal_G8_closed']);self.assertFalse(result['full_population_complete'])
  models=plan.load(self.root/'preview/model-payloads.json');tasks=plan.load(self.root/'preview/task-payloads.json')
  task_ids={t['sha256'] for t in tasks}
  for t in tasks:self.assertEqual(plan.digest(t['task']),t['sha256'])
  for row in models:
   self.assertEqual(plan.digest(row['model']),row['model_sha256'])
   self.assertTrue(set(row['base_task_ids'].values())<=task_ids)
   self.assertEqual(row['model']['family_id'],row['logical_identity']['family_id'])
   self.assertEqual(row['model']['word'],row['logical_identity']['word'])
  self.assertEqual(result['published_payload_bytes'],sum((self.root/'preview'/x).stat().st_size for x in ('model-payloads.json','task-payloads.json')))
 def test_capture_and_fresh_family_binding_fail_closed(self):
  original,trusted,index,logical,path,sha=self.inputs()
  with self.pool(sha) as pool,self.fx.writer('bad-capture') as w,self.assertRaises(ValueError):
   preview.preview_capture(original,'a'*64,index,trusted,logical,path,'0'*64,pool,w)
  index['bundle_sha256']='0'*64
  with self.pool(sha) as pool,self.fx.writer('bad-bundle') as w,self.assertRaisesRegex(ValueError,'fresh checked bundle'):
   preview.preview_capture(original,'a'*64,index,trusted,logical,path,sha,pool,w)
  self.assertFalse((self.root/'bad-bundle/model-payloads.json').exists())
 def test_selector_freezes_before_any_model_and_wrong_builder_rejects(self):
  original,trusted,index,logical,path,sha=self.inputs()
  from validation.suffix5 import task_catalog
  original_builder=task_catalog.candidate.build_model
  def wrong(*a,**k):
   self.assertTrue((self.root/'wrong-builder/selection.json').is_file())
   value=original_builder(*a,**k);value['H']+=1;return value
  with self.pool(sha) as pool,self.fx.writer('wrong-builder') as w,patch.object(task_catalog.candidate,'build_model',side_effect=wrong),self.assertRaises(ValueError):
   preview.preview_capture(original,'a'*64,index,trusted,logical,path,sha,pool,w)
  self.assertFalse((self.root/'wrong-builder/model-payloads.json').exists())
 def test_combined_payload_cap_cannot_yield_complete_preview(self):
  original,trusted,index,logical,path,sha=self.inputs()
  with self.pool(sha) as pool,self.fx.writer('cap') as w,patch.object(preview,'PAYLOAD_BYTES',1),self.assertRaisesRegex(ValueError,'payload cap'):
   preview.preview_capture(original,'a'*64,index,trusted,logical,path,sha,pool,w)
  self.assertFalse((self.root/'cap/model-payloads.json').exists())
 def test_logical_count_return_source_report_and_recomputed_plan_binding(self):
  original,trusted,index,logical,path,sha=self.inputs()
  summary=plan.load(self.root/'replay/structural-summary.json');anchors={'capture_sha256':sha}
  report=count_logical_models(index,trusted,summary['checked'])
  report.update(census_source_sha256='e'*64,evidence=anchors)
  attempt=self.root/'logical';attempt.mkdir();evidence=attempt/'evidence'
  with preview.BoundedEvidenceWriter(evidence,preview.REPLAY.worker_evidence_bytes,profile_name=preview.REPLAY.name) as w:
   spec=w.write('suffix-census.json',domain.chunks(report));w.finalize()
  returned=self.root/'logical-return.json';returned.write_bytes(b'{"retained_fixture":true}')
  args=SimpleNamespace(logical_return=returned,logical_return_sha=plan.pin(returned)['sha256'],logical_attempt=attempt,
   logical_report_sha=spec['sha256'],logical_source_sha='e'*64,replay_plan_sha='b'*64)
  accepted=dict(status='completed',descendants_reaped=True,profile=asdict(preview.REPLAY),
   context=dict(plan_sha256='b'*64,source_sha256='e'*64),verified_manifest_sha256=plan.pin(evidence/'__manifest.json')['sha256'])
  # The existing runtime's process/return proofs are injected only at this
  # boundary; all logical report/index/source checks below are exercised.
  with patch.object(preview,'read_phase_result',return_value=accepted) as cold:
   actual=preview.logical_input(args,anchors,index,trusted,summary,time.monotonic()+10,lambda:None)
   self.assertEqual(actual,logical);self.assertEqual(cold.call_args.kwargs['successful_return'],{'retained_fixture':True})
   for key in ('logical_return_sha','logical_report_sha','logical_source_sha'):
    bad=SimpleNamespace(**vars(args));setattr(bad,key,'0'*64)
    with self.subTest(key=key),self.assertRaises(ValueError):preview.logical_input(bad,anchors,index,trusted,summary,time.monotonic()+10,lambda:None)
   altered=deepcopy(index);altered['queries'][0]['family_ids']=['f'*64]
   with self.assertRaises(ValueError):preview.logical_input(args,anchors,altered,trusted,summary,time.monotonic()+10,lambda:None)
   accepted['status']='unresolved'
   with self.assertRaises(ValueError):preview.logical_input(args,anchors,index,trusted,summary,time.monotonic()+10,lambda:None)
if __name__=='__main__':unittest.main()
