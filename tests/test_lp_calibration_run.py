"""Tiny admission/checking tests with fixed hand certificates, never an LP."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import base64,tempfile,time,unittest
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import calibration_run as run,calibration_inputs as inputs,model_preview as preview,plan,domain
from validation.suffix5.test_convex_checker import hand_record
from validation.suffix5.calibration import select_calibration
from tests.test_suffix_calibration import binding

def fixed_selection():
 rows=[];models=[]
 for depth,width in enumerate((64,96,64,32)):
  for j in range(width):
   i=len(rows);family=0 if depth==0 else 2*depth-1+int(j>=width//2)
   logical=dict(family_id=f'{family:064x}',word=[[f'site{i}','C']],arrival_bands=[0])
   model=dict(family_bundle_sha256='b'*64,**logical)
   rows.append(dict(position=i,prefix_depth=depth,selection=logical))
   models.append(dict(selection_position=i,model=model,model_sha256=plan.digest(model),
    logical_identity=dict(source_bundle_sha256='b'*64,**logical)))
 return dict(schema='family5-static-model-preview-selection-v1',source_bundle_sha256='b'*64,models=rows),models

class CalibrationRunTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
 def writer(self,name):
  raw=run.BoundedEvidenceWriter(self.root/name,run.BATCH_REPLAY.worker_evidence_bytes,profile_name=run.BATCH_REPLAY.name)
  self.addCleanup(raw.close);return run.PayloadWriter(raw)
 def case(self):
  ctx,record=hand_record('C',1,True);models=[dict(model=deepcopy(record['model'])) for _ in range(8)]
  selected=dict(bindings=[dict(binding(record),calibration_index=i,preview_position=i) for i in range(8)])
  jobs=[SimpleNamespace(to_dict=lambda i=i:dict(calibration_index=i,model_sha256=plan.digest(record['model']))) for i in range(8)]
  outcomes=[dict(job=j.to_dict(),status='complete',child_reaped=True,stages=deepcopy(record['stages']),result=deepcopy(record['result']),
   metrics=dict(pass_count=5)) for j in jobs]
  return ctx,selected,models,jobs,outcomes
 def dispatch(self,outcomes):
  def fake(jobs,**kw):
   for row in reversed(outcomes):kw['on_result'](row)
   return outcomes
  return fake
 def test_eight_bindings_exact_checked_without_optimizer(self):
  ctx,selected,models,jobs,outcomes=self.case();w=self.writer('ok')
  ledger=run.check_candidates(ctx,selected,models,jobs,self.dispatch(outcomes),w,cpus=(1,2,3,4),deadline=time.monotonic()+20)
  self.assertTrue(ledger['complete']);self.assertEqual(ledger['verified_bindings'],8)
  self.assertEqual(ledger['observed_candidate_passes_lower_bound'],40)
  self.assertFalse(ledger['query_optimum_certified']);self.assertFalse(ledger['literal_G8_closed'])
  self.assertEqual(len(w.files),17)
  for row in ledger['bindings']:
   doc=plan.load(self.root/'ok'/row['checked']['path']);self.assertTrue(doc['physical_witness_verified'])
 def test_candidate_exhaustion_and_exact_rejection_remain_unresolved(self):
  ctx,selected,models,jobs,outcomes=self.case()
  outcomes[2].update(status='unresolved',result=None,reason='candidate subprocess deadline exhausted')
  outcomes[5]['result']['J']='999'
  ledger=run.check_candidates(ctx,selected,models,jobs,self.dispatch(outcomes),self.writer('partial'),cpus=(1,2,3,4),deadline=time.monotonic()+20)
  self.assertFalse(ledger['complete']);self.assertEqual(ledger['unresolved_bindings'],2)
  self.assertEqual([r['binding']['calibration_index'] for r in ledger['bindings']],list(range(8)))
  self.assertFalse(ledger['pass_count_complete'])
 def test_missing_duplicate_wrong_job_and_return_change_reject(self):
  for kind in ('missing','duplicate','foreign','returned'):
   ctx,selected,models,jobs,outcomes=self.case()
   def fake(jobs,**kw):
    if kind=='foreign':outcomes[0]['job']['model_sha256']='0'*64
    for row in outcomes[:-1] if kind=='missing' else outcomes:kw['on_result'](row)
    if kind=='duplicate':kw['on_result'](outcomes[0])
    returned=deepcopy(outcomes)
    if kind=='returned':returned[0]['result']['J']='999'
    return returned
   with self.subTest(kind=kind),self.assertRaises(ValueError):
    run.check_candidates(ctx,selected,models,jobs,fake,self.writer(kind),cpus=(1,2,3,4),deadline=time.monotonic()+20)
 def test_exact_check_deadline_retains_candidate_without_acceptance(self):
  ctx,selected,models,jobs,outcomes=self.case()
  with patch('validation.suffix5.calibration.verify_model',side_effect=TimeoutError('exact checker deadline')):
   ledger=run.check_candidates(ctx,selected,models,jobs,self.dispatch(outcomes),self.writer('timeout'),cpus=(1,2,3,4),deadline=time.monotonic()+20)
  self.assertEqual(ledger['unresolved_bindings'],8);self.assertFalse(ledger['complete'])
  self.assertEqual(len(list((self.root/'timeout').glob('candidate-*.json'))),8)
 def test_payload_quota_is_monotone_and_failure_cannot_finalize(self):
  w=self.writer('quota')
  with patch.object(run,'PAYLOAD_BYTES',5):
   w.write('first.json',[b'123'])
   with self.assertRaisesRegex(ValueError,'payload byte cap'):w.write('second.json',[b'456'])
  self.assertEqual(w.charged,6)
  with self.assertRaises(ValueError):w.writer.finalize()
 def test_near_cap_fake_transcript_retains_raw_and_decoded_envelope(self):
  ctx,selected,models,jobs,outcomes=self.case()
  outcomes[0].update(status='unresolved',reason='bounded fake transcript',result=None)
  outcomes[0]['stages']=outcomes[0]['stages'][:1]
  outcomes[0]['stages'][0]['certificate']['padding']='x'*(2*1024**2-8192)
  raw=plan.canonical(outcomes[0]['stages'])+b'\n';self.assertLessEqual(len(raw),2*1024**2)
  outcomes[0]['stdout_base64']=base64.b64encode(raw).decode('ascii')
  outcomes[0]['stderr_base64']=base64.b64encode(b'x'*(64*1024)).decode('ascii')
  expected=plan.canonical(outcomes[0])+b'\n'
  self.assertGreater(len(expected),4*1024**2);self.assertLess(len(expected),run.CANDIDATE_DOCUMENT_BYTES)
  w=self.writer('large')
  ledger=run.check_candidates(ctx,selected,models,jobs,self.dispatch(outcomes),w,cpus=(1,2,3,4),deadline=time.monotonic()+20)
  self.assertEqual((self.root/'large/candidate-00.json').read_bytes(),expected)
  self.assertFalse(ledger['complete']);self.assertEqual(ledger['unresolved_bindings'],1)
  self.assertLess(w.charged,run.PAYLOAD_BYTES)
 def test_fresh_real_families_rebuild_bound_models_before_candidates(self):
  from tests import test_real_model_preview as fixtures
  fx=fixtures.ModelPreview();fx.setUp();self.addCleanup(fx.doCleanups)
  original,trusted,index,logical,path,sha=fx.inputs()
  with fx.pool(sha) as pool,fx.fx.writer('preview-again') as w:
   preview.preview_capture(original,'a'*64,index,trusted,logical,path,sha,pool,w);w.finalize()
  models=plan.load(fx.root/'preview-again/model-payloads.json')
  selected=dict(bindings=[dict(preview_position=0,model_sha256=models[0]['model_sha256'],logical_identity=models[0]['logical_identity'])])
  with fx.pool(sha) as pool:
   ctx=run.fresh_families(original,'a'*64,index,trusted,selected,models,path,pool,self.writer('family'),lambda:None)
  self.assertEqual(ctx.summary['bundle_sha256'],index['bundle_sha256'])
  altered=deepcopy(models);altered[0]['model']['H']+=1
  with fx.pool(sha) as pool,self.assertRaisesRegex(ValueError,'authenticated preview model'):
   run.fresh_families(original,'a'*64,index,trusted,selected,altered,path,pool,self.writer('bad-model'),lambda:None)

class CalibrationPreviewBindingTests(unittest.TestCase):
 setUp=CalibrationRunTests.setUp
 # Runtime process/return authority is injected at one reviewed boundary;
 # consumed source bytes and all domain links below it are checked here.
 def fixture(self):
  selection,models=fixed_selection();attempt=self.root/'preview';root=attempt/'evidence';anchors=dict(capture_sha256='c'*64)
  trusted=SimpleNamespace(source_snapshot=lambda:dict(table='t'));index=dict(bundle_sha256='b'*64,case_sha256='d'*64)
  with run.BoundedEvidenceWriter(root,run.BATCH_REPLAY.worker_evidence_bytes,profile_name=run.BATCH_REPLAY.name) as w:
   specs={}
   for name,value in [('selection.json',selection),('model-payloads.json',models),('task-payloads.json',[]),('batch-ledger.json',{}),
    ('stage-before-family.json',{}),('stage-after-family.json',{})]:specs[name]=w.write(name,domain.chunks(value))
   report=dict(schema='hiroute-structural-model-payload-preview-v1',model_builder_comparison=True,solver_calls=0,
    full_population_complete=False,literal_G8_closed=False,source_sha256='a'*64,selected_models=256,selected_families=7,
    completed_replay=anchors,logical_report_sha256='e'*64,
    family_verification=dict(verified=True,**index,real_input_sources=trusted.source_snapshot()))
   for field,name in [('selection','selection.json'),('model_payloads','model-payloads.json'),('task_payloads','task-payloads.json'),('batch_ledger','batch-ledger.json')]:report[field]=specs[name]
   specs['preview-summary.json']=w.write('preview-summary.json',domain.chunks(report))
   w.write('run-binding.json',domain.chunks(dict(source_sha256='a'*64,completed_replay=anchors,logical_report_sha256='e'*64)));w.finalize()
  returned=self.root/'preview-return.json';returned.write_bytes(b'{}')
  args=SimpleNamespace(preview_return=returned,preview_return_sha=plan.pin(returned)['sha256'],preview_attempt=attempt,
   preview_source_sha='a'*64,replay_plan_sha='f'*64,preview_summary_sha=specs['preview-summary.json']['sha256'],logical_report_sha='e'*64)
  accepted=dict(status='completed',descendants_reaped=True,profile=asdict(run.BATCH_REPLAY),
   context=dict(source_sha256='a'*64,plan_sha256='f'*64),verified_manifest_sha256=plan.pin(root/'__manifest.json')['sha256'])
  return args,anchors,index,trusted,selection,models,accepted
 def test_retained_return_manifest_source_and_selection_are_bound(self):
  args,anchors,index,trusted,selection,models,accepted=self.fixture()
  with patch.object(inputs,'read_phase_result',return_value=accepted),patch.object(preview,'logical_input',return_value={}),\
   patch('validation.suffix5.preview_selection.select_preview',return_value=selection):
   selected,actual,path=inputs.load_preview(args,anchors,index,trusted,{},time.monotonic()+10,lambda:None)
   self.assertEqual(selected['positions'],[0,63,64,159,160,223,224,255]);self.assertEqual(actual,models)
   self.assertEqual(plan.pin(path)['sha256'],selected['model_payloads_file']['sha256'])
   for key in ('preview_return_sha','preview_summary_sha','preview_source_sha','logical_report_sha','replay_plan_sha'):
    bad=SimpleNamespace(**vars(args));setattr(bad,key,'0'*64)
    with self.subTest(key=key),self.assertRaises(ValueError):inputs.load_preview(bad,anchors,index,trusted,{},time.monotonic()+10,lambda:None)
   accepted['status']='unresolved'
   with self.assertRaises(ValueError):inputs.load_preview(args,anchors,index,trusted,{},time.monotonic()+10,lambda:None)

if __name__=='__main__':unittest.main()
