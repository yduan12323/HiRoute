"""Lossless immutable proof streaming with hand certificates; no LP."""
import base64,gzip,hashlib,io,json,tempfile,time,unittest,zlib
from contextlib import redirect_stdout,contextmanager
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
from tests.test_suffix_block_certificates import declaration
from validation.suffix5.test_convex_checker import hand_record
from experiments.time_cut_v2.recorded_real import plan,domain,block_archive as archive,block_pilot as pilot
from experiments.time_cut_v2.recorded_real.lp_stream_jobs import LPStreamJob
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter,BATCH_REPLAY

class FakeResults:
 def __init__(self,rows):
  self.rows=rows;self.summary=dict(status='complete',input_exhausted=True,all_processes_reaped=True,
   all_submitted_accounted=True,submitted_count=len(rows),terminal_count=len(rows),protocol_error_count=0,collector_error=None)
 def __iter__(self):return iter(self.rows)

def outcomes(records,context):
 rows=[]
 for i,record in enumerate(records):
  job=LPStreamJob(context,0,i,plan.digest(record['model']),record['model']);generation='a'*32
  rows.append(dict(job=job.to_dict(),response_identity=job.header(generation),generation=generation,
   status='complete',reason=None,stages=record['stages'],result=record['result'],metrics={},
   stdout_base64=base64.b64encode(b'hand proof\n').decode(),stderr_base64=''))
 return rows

class BlockArchiveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def test_archive_preserves_all_certificates_and_physical_winner(self):
  ctx,a=hand_record('C',0,True);_,b=hand_record('C',1,True);_,c=hand_record('C',2,True)
  records=[a,b,c];source=dict(bundle=ctx.summary['bundle_sha256']);rows=outcomes(records,source)
  with BoundedEvidenceWriter(self.root/'evidence',BATCH_REPLAY.worker_evidence_bytes,profile_name=BATCH_REPLAY.name) as w:
   proof=pilot.publish_proofs(ctx,dict(blocks=declaration(records)),source,archive.QuotaWriter(w,lambda:None),
    FakeResults(rows[::-1]),deadline=time.monotonic()+30);w.finalize()
  raw=gzip.decompress((self.root/'evidence/model-proofs.jsonl.gz').read_bytes())
  documents=[json.loads(line) for line in raw.splitlines()]
  restored={row['descriptor']['ordinal']:row['record'] for row in documents if row['kind']=='model_certificate'}
  self.assertEqual(restored,dict(enumerate(records)))
  self.assertEqual(hashlib.sha256(raw).hexdigest(),proof['encoding']['uncompressed_sha256'])
  self.assertTrue(proof['footer']['complete']);self.assertEqual(proof['footer']['verified_models'],3)
  block=next(r for r in documents if r['kind']=='block_report')
  self.assertTrue(block['report']['physical_witness_verified']);self.assertTrue(block['winner_witness']['physical_witness_verified'])
  self.assertFalse(proof['footer']['literal_G8_closed'])
 def test_candidate_failure_bad_certificate_and_pool_error_are_incomplete(self):
  for mode in ('candidate','certificate','pool','missing'):
   ctx,record=hand_record('C',1,True);source=dict(bundle=ctx.summary['bundle_sha256']);rows=outcomes([record],source)
   if mode=='candidate':rows[0].update(status='unresolved',result=None,reason='candidate deadline')
   if mode=='certificate':rows[0]['result']=dict(rows[0]['result'],J='999')
   stream=FakeResults([] if mode=='missing' else rows)
   if mode=='pool':stream.summary.update(status='unresolved',protocol_error_count=1)
   docs=list(archive.checked_records(ctx,declaration([record]),source,stream,deadline=time.monotonic()+30))
   self.assertFalse(docs[-1]['complete'],mode)
   if mode!='pool':self.assertFalse(next(r for r in docs if r['kind']=='block_report')['report']['complete_certificates'])
 def test_foreign_context_or_duplicate_model_cannot_finish_archive(self):
  ctx,record=hand_record('C',1,True);source=dict(bundle=ctx.summary['bundle_sha256']);rows=outcomes([record],source)
  for supplied,context in ((rows,dict(bundle='f'*64)),(rows*2,source)):
   with self.assertRaises(ValueError):list(archive.checked_records(ctx,declaration([record]),context,FakeResults(supplied),deadline=time.monotonic()+30))
 def test_late_verification_deadline_cannot_publish_a_stale_receipt(self):
  ctx,record=hand_record('C',1,True);source=dict(bundle=ctx.summary['bundle_sha256'])
  @contextmanager
  def late(deadline):
   yield
   raise TimeoutError('late exact-check deadline')
  seen=[]
  with patch('validation.suffix5.calibration.verification_deadline',late),self.assertRaises(TimeoutError):
   for row in archive.checked_records(ctx,declaration([record]),source,FakeResults(outcomes([record],source)),deadline=time.monotonic()+30):
    seen.append(row)
  self.assertEqual([r['kind'] for r in seen],['header'])
 def test_late_physical_deadline_keeps_block_incomplete_without_stale_witness(self):
  ctx,record=hand_record('C',1,True);source=dict(bundle=ctx.summary['bundle_sha256']);calls=[]
  @contextmanager
  def second_late(deadline):
   calls.append(deadline);yield
   if len(calls)==2:raise TimeoutError('late physical deadline')
  with patch('validation.suffix5.calibration.verification_deadline',second_late):
   docs=list(archive.checked_records(ctx,declaration([record]),source,FakeResults(outcomes([record],source)),deadline=time.monotonic()+30))
  block=next(row for row in docs if row['kind']=='block_report')
  self.assertIsNone(block['winner_witness']);self.assertFalse(block['report']['physical_witness_verified'])
  self.assertFalse(block['report']['complete']);self.assertFalse(docs[-1]['complete'])
 def test_complete_block_boundary_survives_an_interrupted_gzip_prefix(self):
  saved=[];encoding=archive.ArchiveEncoding()
  def rows():
   yield dict(kind='header',value='proof')
   yield dict(kind='block_certificate_checkpoint',acceptance=False,cold_certificate_replay_required=True)
   raise TimeoutError('later block interrupted')
  with self.assertRaises(TimeoutError):
   for chunk in encoding.chunks(rows()):saved.append(chunk)
  decoder=zlib.decompressobj(wbits=31);raw=decoder.decompress(b''.join(saved))
  docs=[json.loads(line) for line in raw.splitlines()]
  self.assertEqual(docs[-1]['kind'],'block_certificate_checkpoint')
  self.assertFalse(decoder.eof);self.assertFalse(encoding.complete);self.assertFalse(docs[-1]['acceptance'])
 def test_row_and_conservative_evidence_charge_caps_fail_closed(self):
  with patch.object(archive,'RAW_ROW_BYTES',8),self.assertRaisesRegex(ValueError,'row cap'):
   b''.join(archive.ArchiveEncoding().chunks([{'long':'x'*100}]))
  with BoundedEvidenceWriter(self.root/'cap',BATCH_REPLAY.worker_evidence_bytes,profile_name=BATCH_REPLAY.name) as w:
   with patch.object(archive,'EVIDENCE_BYTES',w.charged_bytes+1),self.assertRaisesRegex(ValueError,'charge'):
    archive.QuotaWriter(w,lambda:None).write('x.json',domain.chunks({'x':1}))
 def test_controller_binds_900_seconds_and_fixed_group_before_worker(self):
  argv=['block_pilot']
  for name in ('historical-plan','replay-plan','replay-attempt','replay-return','logical-attempt','logical-return','capture'):
   argv+=['--'+name,str(self.root/name)]
  for name in ('historical-plan-sha','replay-plan-sha','replay-return-sha','replay-manifest-sha','replay-result-sha',
   'replay-decision-sha','query-index-sha','source-commit','source-sha','logical-return-sha','logical-report-sha','logical-source-sha'):
   argv+=['--'+name,'a'*64]
  argv+=['--worker-cpus','1','2','3','4','5','--cpu','0','--attempt-dir',str(self.root/'attempt')]
  with patch.object(pilot.sys,'argv',argv),patch.object(pilot.suffix_census,'check_sources'),\
   patch.object(pilot.resource,'getrlimit',return_value=(1024**3,pilot.resource.RLIM_INFINITY)),\
   patch.object(pilot.resource,'setrlimit'),patch.object(pilot,'run_phase',return_value={'status':'completed'}) as phase,\
   redirect_stdout(io.StringIO()):
   self.assertEqual(pilot.main(),0)
  args=phase.call_args;self.assertEqual(args.kwargs['deadline_monotonic']-args.kwargs['entry_monotonic'],900)
  self.assertIs(args.kwargs['profile'],BATCH_REPLAY);self.assertEqual(args.kwargs['worker_cpus'],(1,2,3,4,5))
  command=args.args[0];self.assertEqual(command[command.index('--deadline')+1],repr(pilot.ENTRY+900))

if __name__=='__main__':unittest.main()
