"""Bounded eight-model candidate/certificate calibration, never a query solve."""
import time
ENTRY=time.monotonic()
import argparse,json,math,os,resource,sys
from pathlib import Path
from . import plan as binding,domain,suffix_census
from .hot_jobs import read_pinned
from .runtime import BATCH_REPLAY,PlanContext,BoundedEvidenceWriter,run_phase,worker_failure
from .worker import verify_loaded

SECONDS=480
PAYLOAD_BYTES=64*1024**2
VERIFICATION_SECONDS=30
MODEL_CHECK_BYTES=4*1024**2
CANDIDATE_DOCUMENT_BYTES=6*1024**2

class PayloadWriter:
 """Monotone payload charge within the unchanged guarded evidence writer.

 The group profile additionally accounts its journal and supervisor artifacts.
 Interrupted/failed writes retain their charge and cannot be retried in place.
 """
 def __init__(self,writer,before=lambda:None):self.writer=writer;self.before=before;self.charged=0
 @property
 def files(self):return self.writer.files
 def write(self,name,chunks,*,limit=PAYLOAD_BYTES):
  used=0
  def bounded():
   nonlocal used
   for part in chunks:
    self.before();binding.require(type(part) is bytes,'exact evidence bytes required')
    used+=len(part);self.charged+=len(part)
    binding.require(used<=limit and self.charged<=PAYLOAD_BYTES,'calibration payload byte cap')
    yield part
  return self.writer.write(name,bounded())

def fresh_families(original,original_sha,index,trusted,selected,models,capture_path,pool,writer,before):
 """Rebuild genuine checker authority; authenticated index alone is insufficient."""
 from .family_gate import verify_families
 from validation.family5.checker import _plain
 from validation.suffix5 import convex_model,independent_convex_model
 payload=read_pinned(capture_path,index['capture_sha256'],1024**3)
 binding.require(payload['schema']=='hiroute-recorded-real-capture-v1' and payload['source_plan_sha256']==original_sha,
  'capture schema/plan changed')
 for key in ('source_sha256','input_sha256','query_sha256'):
  suffix_census.same(payload[key],original[key],'capture '+key+' changed')
 suffix_census.same(payload['query'],original['query'],'capture query changed')
 suffix_census.same(payload['variant'],domain.variant(original),'capture variant changed')
 bundle=payload['bundle'];del payload;before()
 start=time.monotonic();ctx,ledger=verify_families(bundle,trusted,pool);del bundle
 binding.require(ctx.summary['bundle_sha256']==index['bundle_sha256'] and ctx.summary['case_sha256']==index['case_sha256'],
  'fresh checked bundle differs from completed trace index')
 suffix_census.same(_plain(ctx.summary['real_input_sources']),trusted.source_snapshot(),'fresh physical sources changed')
 writer.write('batch-ledger.json',domain.chunks(ledger),limit=32*1024**2)
 writer.write('family-summary.json',domain.chunks(dict(checked=_plain(ctx.summary),wall_seconds=time.monotonic()-start)))
 # All selected model bytes are independently rebuilt before any LP child starts.
 for row in selected['bindings']:
  before();identity=row['logical_identity'];ident=identity['family_id']
  binding.require(ident in ctx._pieces,'selected original family missing')
  args=(ctx,ident,identity['word'],identity['arrival_bands'])
  actual=convex_model.build_model(*args);independent=independent_convex_model.build_model(*args)
  suffix_census.same(actual,independent,'independent calibration model differs')
  suffix_census.same(actual,models[row['preview_position']]['model'],'authenticated preview model changed')
  binding.require(binding.digest(actual)==row['model_sha256'],'calibration model digest changed')
 before();return ctx

def check_candidates(ctx,selected,models,jobs,run_jobs,writer,*,cpus,deadline,coordinator_cpu=None,before=lambda:None):
 """Retain every selected binding, including unresolved candidate/check attempts."""
 from validation.suffix5.calibration import verify_model,verification_deadline
 expected=selected['bindings'];binding.require(len(expected)==len(jobs)==8,'exact eight-job calibration required')
 outcomes={};rows={}
 def consume(outcome):
  index=outcome['job']['calibration_index']
  before();binding.require(type(index) is int and 0<=index<8 and index not in outcomes,'foreign/duplicate calibration completion')
  suffix_census.same(outcome['job'],jobs[index].to_dict(),'candidate job binding changed')
  binding.require(outcome['status'] in ('complete','unresolved'),'unknown candidate disposition')
  binding.require(outcome['status']!='complete' or outcome['child_reaped'] is True,'candidate process not reaped')
  outcomes[index]=outcome
  candidate_pin=writer.write(f'candidate-{index:02d}.json',domain.chunks(outcome),limit=CANDIDATE_DOCUMENT_BYTES)
  row=dict(binding=expected[index],candidate=candidate_pin,status='unresolved',independently_verified=False)
  rows[index]=row
  if outcome['status']!='complete':row['reason']=outcome.get('reason','candidate incomplete');return
  record=dict(model=models[expected[index]['preview_position']]['model'],stages=outcome['stages'],result=outcome['result'])
  checked=None
  try:
   with verification_deadline(float(min(deadline-10,time.monotonic()+VERIFICATION_SECONDS))):
    checked=verify_model(ctx,expected[index],record)
    raw=domain.chunks(checked)
    pin=writer.write(f'checked-{index:02d}.json',raw,limit=MODEL_CHECK_BYTES)
   row.update(status=checked['result']['status'],independently_verified=True,checked=pin,
    logical_stages=checked['checked_stage_count'],timings=checked['timings'])
  except (ValueError,TimeoutError,MemoryError) as error:
   # A writer failure cannot be turned into completed evidence. Its enclosing
   # attempt remains poisoned and final publication consequently fails closed.
   row['reason']=type(error).__name__+': '+str(error)[:2048]
 result=run_jobs(jobs,cpus=cpus,deadline_monotonic=float(deadline-10),on_result=consume,coordinator_cpu=coordinator_cpu)
 binding.require(len(result)==8 and set(outcomes)==set(range(8)),'missing calibration outcome')
 for i,value in enumerate(result):suffix_census.same(value,outcomes[i],'returned candidate differs from callback')
 ordered=[rows[i] for i in range(8)];verified=sum(r['independently_verified'] for r in ordered)
 stages=sum(r.get('logical_stages',0) for r in ordered)
 retained_stages=sum(len(r['stages']) for r in outcomes.values())
 observed_passes=sum(r['metrics']['pass_count'] for r in outcomes.values() if r['metrics'] is not None)
 binding.require(stages<=retained_stages<=40 and observed_passes<=96,'candidate budget population exceeded')
 ledger=dict(schema='hiroute-eight-model-calibration-ledger-v1',selection_sha256=binding.digest(selected),
  expected_bindings=8,verified_bindings=verified,unresolved_bindings=8-verified,bindings=ordered,
  complete=verified==8,maximum_candidate_passes=96,maximum_logical_stage_slots=40,
  verified_logical_stage_slots=stages,retained_logical_stage_slots=retained_stages,
  observed_candidate_passes_lower_bound=observed_passes,pass_count_complete=all(r['status']=='complete' for r in outcomes.values()),
  certificate_reuse_enabled=False,query_optimum_certified=False,
  full_population_complete=False,literal_G8_closed=False)
 writer.write('calibration-ledger.json',domain.chunks(ledger));before();return ledger

def worker(args):
 raw_writer=None;writer=None;pool=None;stage='binding'
 def before():binding.require(math.isfinite(args.deadline) and time.monotonic()<args.deadline,'calibration absolute deadline')
 try:
  binding.require(os.environ.get('HIROUTE_PROFILE')==BATCH_REPLAY.name and
   os.environ.get('HIROUTE_EVIDENCE_CAP_BYTES')==str(BATCH_REPLAY.worker_evidence_bytes),'wrong calibration group guard')
  binding.require(len(args.worker_cpus)==5 and len(set(args.worker_cpus))==5 and
   os.sched_getaffinity(0)==set(args.worker_cpus),'five inherited coordinator/worker CPUs required')
  binding.require(not any(n=='validation' or n.startswith(('validation.','timecut5')) or
   n.split('.')[0] in ('numpy','scipy','sympy') for n in sys.modules),'mathematics imported before calibration fence')
  sys.meta_path.insert(0,suffix_census.NoOptimization())
  sources=suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha);before()
  index,trusted,summary,anchors=suffix_census.completed_inputs(binding.ROOT,args,args.deadline,before)
  original=read_pinned(args.historical_plan,args.historical_plan_sha,4*1024**2)
  binding.require(original['state_id']=='C01' and original['H_ref']==4 and original['sites']==8 and original['regions']==2047 and
   original['dominance'] is True and original['external_incumbent'] is None,'fixed original C01 population required')
  from .calibration_inputs import load_preview
  selected,models,model_path=load_preview(args,anchors,index,trusted,summary,args.deadline,before)
  raw_writer=BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],BATCH_REPLAY.worker_evidence_bytes,profile_name=BATCH_REPLAY.name)
  writer=PayloadWriter(raw_writer,before)
  run=dict(schema='hiroute-eight-model-calibration-binding-v1',source_commit=args.source_commit,source_sha256=args.source_sha,
   completed_replay=anchors,logical_report_sha256=args.logical_report_sha,preview_summary_sha256=args.preview_summary_sha,
   preview_return_sha256=args.preview_return_sha,selection_sha256=binding.digest(selected),worker_cpus=args.worker_cpus,
   absolute_seconds=SECONDS,payload_cap_bytes=PAYLOAD_BYTES,per_candidate_seconds=30,per_verification_seconds=30,
   maximum_candidate_passes=96,certificate_reuse_enabled=False,query_optimum_certified=False,literal_G8_closed=False)
  writer.write('run-binding.json',domain.chunks(run));writer.write('calibration-selection.json',domain.chunks(selected))
  from validation.real5_v2.batch_jobs import BatchExecutor,WORKER_AS
  binding.require(WORKER_AS==1024**3,'scalar child cap changed');stage='fresh-family-and-model-binding'
  with BatchExecutor(tuple(args.worker_cpus[1:]),float(args.deadline-10),index['capture_sha256'],kernel='interval-join-v1') as pool:
   binding.require(len(pool.slots)==4 and all(s.process.poll() is None for s in pool.slots),'four fresh scalar children required')
   os.sched_setaffinity(0,{args.worker_cpus[0]})
   ctx=fresh_families(original,args.historical_plan_sha,index,trusted,selected,models,args.capture,pool,writer,before)
  binding.require(all(s.process.poll() is not None for s in pool.slots),'family children not reaped')
  from .lp_jobs import make_jobs,run_jobs
  spec=selected['model_payloads_file']
  jobs=make_jobs(model_payloads_path=model_path,model_payloads_sha256=spec['sha256'],model_payloads_size_bytes=spec['size_bytes'],
   model_sha256s=[r['model_sha256'] for r in selected['bindings']],context_sha256=binding.digest(run))
  # A new collector thread inherits this mask; its children are pinned to four
  # disjoint CPUs. The collector then narrows the main thread explicitly.
  os.sched_setaffinity(0,set(args.worker_cpus));stage='candidate-and-independent-calibration'
  ledger=check_candidates(ctx,selected,models,jobs,run_jobs,writer,cpus=tuple(args.worker_cpus[1:]),deadline=args.deadline,coordinator_cpu=args.worker_cpus[0],before=before)
  os.sched_setaffinity(0,{args.worker_cpus[0]});stage='final-binding'
  verify_loaded({'source_files':sources});suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha);before()
  again=suffix_census.completed_inputs(binding.ROOT,args,args.deadline,before)
  suffix_census.same(again[3],anchors,'completed replay changed during calibration')
  final_selected,_,_=load_preview(args,again[3],again[0],again[1],again[2],args.deadline,before)
  suffix_census.same(final_selected,selected,'completed preview changed during calibration')
  binding.require(binding.pin(args.capture)['sha256']==index['capture_sha256'],'capture changed during calibration')
  summary=dict(schema='hiroute-eight-model-calibration-summary-v1',completed_replay=anchors,source_sha256=args.source_sha,
   selection_sha256=binding.digest(selected),verified_bindings=ledger['verified_bindings'],unresolved_bindings=ledger['unresolved_bindings'],
   complete=ledger['complete'],candidate_optimization_enabled=True,independent_checking_optimizer_free=True,
   maximum_candidate_passes=96,certificate_reuse_enabled=False,query_optimum_certified=False,full_population_complete=False,
   literal_G8_closed=False,charged_payload_bytes_before_summary=writer.charged)
  writer.write('calibration-summary.json',domain.chunks(summary));before()
  mandatory={'run-binding.json','calibration-selection.json','batch-ledger.json','family-summary.json',
   'calibration-ledger.json','calibration-summary.json'}|{f'candidate-{i:02d}.json' for i in range(8)}
  optional={f'checked-{i:02d}.json' for i in range(8)}
  actual={r['path'] for r in writer.files}
  binding.require(len(actual)==len(writer.files) and mandatory<=actual<=mandatory|optional and
   (not ledger['complete'] or actual==mandatory|optional),'calibration output coverage changed')
  raw_writer.finalize();before();return 0 if ledger['complete'] else 1
 except BaseException as error:
  if writer is not None and pool is not None and not any(r['path']=='batch-ledger.json' for r in writer.files):
   try:writer.write('partial-batch-ledger.json',domain.chunks(pool.snapshot()))
   except BaseException:pass
  worker_failure(type(error).__name__,str(error)[:4096],stage);return 1
 finally:
  if raw_writer is not None:raw_writer.close()

def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--deadline',type=float)
 for name in ('historical-plan','replay-plan','replay-attempt','replay-return','logical-attempt','logical-return',
  'preview-attempt','preview-return','capture'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('historical-plan-sha','replay-plan-sha','replay-return-sha','replay-manifest-sha','replay-result-sha',
  'replay-decision-sha','query-index-sha','source-commit','source-sha','logical-return-sha','logical-report-sha','logical-source-sha',
  'preview-return-sha','preview-summary-sha','preview-source-sha'):p.add_argument('--'+name,required=True)
 p.add_argument('--worker-cpus',type=int,nargs=5,required=True);p.add_argument('--cpu',type=int);p.add_argument('--attempt-dir',type=Path)
 args=p.parse_args()
 if args.worker:return worker(args)
 binding.require(args.cpu is not None and args.attempt_dir is not None,'supervisor CPU and fresh attempt required')
 deadline=float(ENTRY+SECONDS);soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 binding.require(hard==resource.RLIM_INFINITY or hard>=BATCH_REPLAY.child_as_bytes,'inherited AS ceiling too small')
 resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha)
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.calibration_run','--worker','--deadline',repr(deadline),
  '--worker-cpus',*map(str,args.worker_cpus)]
 for key,value in vars(args).items():
  if key not in ('worker','deadline','worker_cpus','cpu','attempt_dir'):argv+=['--'+key.replace('_','-'),str(value)]
 context=binding.digest({k:str(v) for k,v in vars(args).items() if k not in ('worker','deadline','cpu','attempt_dir')})
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=BATCH_REPLAY,cpu=args.cpu,worker_cpus=tuple(args.worker_cpus),
  context=PlanContext(args.replay_plan_sha,args.source_sha,context,BATCH_REPLAY.name),entry_monotonic=float(ENTRY),deadline_monotonic=deadline)
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
