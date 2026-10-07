"""One lossless bounded JSONL/gzip archive for independently checked blocks."""
import base64,hashlib,json,time,zlib
from . import plan as binding,domain
from .runtime import ENTRY_CHARGE

EVIDENCE_BYTES=512*1024**2
RAW_ARCHIVE_BYTES=512*1024**2
RAW_ROW_BYTES=8*1024**2

class QuotaWriter:
 """Use the existing writer's full conservative charge as the subquota."""
 def __init__(self,writer,before):self.writer=writer;self.before=before
 @property
 def files(self):return self.writer.files
 def write(self,name,chunks):
  binding.require(self.writer.charged_bytes+ENTRY_CHARGE<=EVIDENCE_BYTES,'block evidence charge exhausted')
  def bounded():
   for part in chunks:
    self.before();binding.require(type(part) is bytes and len(part)<=65536,'bounded immutable evidence chunk required')
    binding.require(self.writer.charged_bytes+2*len(part)<=EVIDENCE_BYTES,'block evidence charge exhausted');yield part
  return self.writer.write(name,bounded())

class ArchiveEncoding:
 def __init__(self):self.raw_bytes=0;self.rows=0;self._sha=hashlib.sha256();self.complete=False
 def chunks(self,rows):
  compressor=zlib.compressobj(level=6,wbits=31)
  for row in rows:
   row_bytes=0
   for part in domain.chunks(row):
    row_bytes+=len(part);binding.require(row_bytes<=RAW_ROW_BYTES,'individual proof archive row cap')
    self.raw_bytes+=len(part);binding.require(self.raw_bytes<=RAW_ARCHIVE_BYTES,'uncompressed block archive cap')
    self._sha.update(part);encoded=compressor.compress(part)
    for i in range(0,len(encoded),65536):yield encoded[i:i+65536]
   self.rows+=1
   if row.get('kind')=='block_certificate_checkpoint':
    # Make each complete block recoverable from a process-interrupted gzip
    # prefix. Recovery still requires fresh exact certificate replay; a
    # checkpoint flag alone grants no authority or physical-witness claim.
    encoded=compressor.flush(zlib.Z_SYNC_FLUSH)
    for i in range(0,len(encoded),65536):yield encoded[i:i+65536]
  tail=compressor.flush()
  for i in range(0,len(tail),65536):yield tail[i:i+65536]
  self.complete=True
 def summary(self):
  return dict(complete=self.complete,uncompressed_bytes=self.raw_bytes,uncompressed_sha256=self._sha.hexdigest(),
   rows=self.rows,encoding='canonical-jsonl-gzip-v1')

def checked_records(ctx,blocks,source_context,outcomes,*,deadline,before=lambda:None):
 """Yield every received model proof; completeness needs the final pool summary.

The transport's outcome is untrusted. This iterator independently reconstructs
each regime. Successful records retain full model/task/certificate bytes once;
failed candidates retain their bounded raw transcripts for diagnosis.
"""
 from .lp_stream_jobs import LPStreamJob
 from validation.suffix5.block_certificates import BlockCertificates
 from validation.suffix5.calibration import verification_deadline,verify_model
 certifier=BlockCertificates(ctx,blocks)
 expected={r['ordinal']:block['range']['block_id'] for block in blocks for r in block['descriptors']}
 yield dict(kind='header',schema='hiroute-suffix-block-proof-archive-v1',source_context=source_context,
  expected_models=len(expected),blocks=[b['range'] for b in blocks],certificate_reuse_enabled=False)
 accepted=0
 for outcome in outcomes:
  before();job=LPStreamJob.from_dict(outcome['job']);ordinal=job.model_ordinal
  binding.require(ordinal in expected and job.block_id==expected[ordinal],'foreign streamed block/model identity')
  binding.require(binding.canonical(job.source_context)==binding.canonical(source_context),'foreign streamed source context')
  binding.require(binding.canonical(outcome['response_identity'])==binding.canonical(job.header(outcome['generation'])),
   'stream response identity changed')
  descriptor=certifier.descriptor(ordinal)
  binding.require(job.model_sha256==binding.digest(job.model),'streamed model bytes changed')
  record=dict(model=job.model,stages=outcome['stages'],result=outcome['result'])
  verification=None;failure=outcome.get('reason');started=time.monotonic();cpu=time.process_time()
  if outcome['status']=='complete':
   try:
    with verification_deadline(float(min(deadline-10,time.monotonic()+30))):verification=certifier.check(ordinal,record)
   except (ValueError,TimeoutError,MemoryError) as error:
    # check() may have published its disposition before a deadline is raised
    # by the context manager's exit check. That is not an accepted archived
    # receipt: abort the outer attempt instead of using the stale return value.
    if verification is not None:raise
    failure=type(error).__name__+': '+str(error)[:2048]
  else:binding.require(outcome['status']=='unresolved','unknown streamed candidate status')
  timings=dict(exact_check_wall_seconds=time.monotonic()-started,exact_check_cpu_seconds=time.process_time()-cpu)
  if verification is None:
   certifier.unresolved(ordinal,failure or 'uncertified candidate')
   yield dict(kind='unresolved_model',descriptor=descriptor,candidate=outcome,timings=timings)
  else:
   accepted+=1
   yield dict(kind='model_certificate',descriptor=descriptor,record=record,verification=verification,
    candidate_identity=outcome['response_identity'],candidate_metrics=outcome['metrics'],timings=timings,
    stdout_sha256=hashlib.sha256(base64.b64decode(outcome['stdout_base64'],validate=True)).hexdigest(),
    stderr_base64=outcome['stderr_base64'])
  checkpoint=certifier.summary(job.block_id)
  if checkpoint['complete_certificates']:
   yield dict(kind='block_certificate_checkpoint',report=checkpoint,transport_finalized=False,
    acceptance=False,cold_certificate_replay_required=True)
 pool=outcomes.summary
 binding.require(type(pool) is dict,'persistent transport did not finish')
 transport_complete=(pool['status']=='complete' and pool['input_exhausted'] is True and pool['all_submitted_accounted'] is True and
  pool['all_processes_reaped'] is True and pool['submitted_count']==len(expected) and
  pool['terminal_count']==len(expected) and pool['protocol_error_count']==0 and pool['collector_error'] is None)
 reports=[]
 for block in blocks:
  before();number=block['range']['block_id'];report=certifier.summary(number);witness=None
  if transport_complete and report['complete_certificates']:
   winner=certifier.winner(number)
   if winner is not None:
    try:
     with verification_deadline(float(min(deadline-10,time.monotonic()+30))):
      witness=verify_model(ctx,dict(block_id=number,model_ordinal=winner['model_ordinal'],
       model_sha256=binding.digest(winner['record']['model']),logical_identity=winner['descriptor']['logical_identity']),winner['record'])
     report['physical_witness_verified']=True
    except (ValueError,TimeoutError,MemoryError) as error:
     witness=None
     report['witness_failure']=type(error).__name__+': '+str(error)[:2048]
   else:report['physical_witness_not_required']=True
  report['complete']=(transport_complete and report['complete_certificates'] and
   (report['physical_witness_verified'] or report.get('physical_witness_not_required',False)))
  yield dict(kind='block_report',report=report,winner_witness=witness)
  reports.append(report)
 complete=transport_complete and accepted==len(expected) and all(r['complete'] for r in reports)
 yield dict(kind='footer',schema='hiroute-suffix-block-proof-footer-v1',complete=complete,
  verified_models=accepted,expected_models=len(expected),transport=pool,blocks=reports,
  query_optimum_certified=False,full_population_complete=False,literal_G8_closed=False)
