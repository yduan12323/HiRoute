"""Four fixed depth-covering blocks; retained proofs contribute to full work."""
import time
ENTRY=time.monotonic()
import argparse,json,math,os,resource,sys
from pathlib import Path
from . import plan as binding,domain,suffix_census
from .hot_jobs import read_pinned
from .runtime import BATCH_REPLAY,PlanContext,BoundedEvidenceWriter,run_phase,worker_failure
from .worker import verify_loaded
from .block_archive import QuotaWriter,ArchiveEncoding,checked_records,EVIDENCE_BYTES,RAW_ARCHIVE_BYTES

SECONDS=900
MAX_MODELS=1024
MAX_INPUT_BYTES=64*1024**2

def freeze_selection(admitted):
 from validation.suffix5.block_plan import choose_depth_blocks
 population=admitted.population;plan=population.plan();pilot=choose_depth_blocks(plan)
 binding.require(plan['block_size']==256 and plan['total_models']==695712 and
  admitted.commitment()['original_model_occurrences']==7652832,'fixed full C01 numerical population changed')
 binding.require(pilot['depths']==[0,1,2,3] and len(pilot['block_ids'])==4 and pilot['models']==MAX_MODELS,
  'fixed four depth-covering blocks required')
 blocks=[]
 for number in pilot['block_ids']:
  rows=list(population.block(number));population.check_block_descriptors(number,rows)
  blocks.append(dict(range=plan['blocks'][number],descriptors=rows))
 return dict(schema='hiroute-four-block-resource-selection-v1',population=admitted.commitment(),
  pilot=pilot,blocks=blocks,selection_uses_outcomes=False,numerical_cache_enabled=False,
  maximum_candidate_passes=MAX_MODELS*12,maximum_logical_stages=MAX_MODELS*5)

def model_jobs(ctx,selection,source_context,before):
 from validation.suffix5 import convex_model,independent_convex_model
 from .lp_stream_jobs import LPStreamJob
 for block in selection['blocks']:
  for descriptor in block['descriptors']:
   before();identity=descriptor['logical_identity'];args=(ctx,identity['family_id'],identity['word'],identity['arrival_bands'])
   model=convex_model.build_model(*args);independent=independent_convex_model.build_model(*args)
   suffix_census.same(model,independent,'independent streamed model differs')
   yield LPStreamJob(source_context,block['range']['block_id'],descriptor['ordinal'],binding.digest(model),model)

def publish_proofs(ctx,selection,source_context,writer,results,*,deadline,before=lambda:None):
 encoding=ArchiveEncoding();footer={}
 def rows():
  for row in checked_records(ctx,selection['blocks'],source_context,results,deadline=deadline,before=before):
   before()
   if row['kind']=='footer':footer.update(row)
   yield row
 pin=writer.write('model-proofs.jsonl.gz',encoding.chunks(rows()))
 binding.require(encoding.complete and footer.get('kind')=='footer','incomplete proof archive')
 return dict(archive=pin,encoding=encoding.summary(),footer=footer)

def worker(args):
 raw_writer=None;writer=None;pool=None;stage='binding'
 def before():binding.require(math.isfinite(args.deadline) and time.monotonic()<args.deadline,'block pilot absolute deadline')
 try:
  binding.require(os.environ.get('HIROUTE_PROFILE')==BATCH_REPLAY.name and
   os.environ.get('HIROUTE_EVIDENCE_CAP_BYTES')==str(BATCH_REPLAY.worker_evidence_bytes),'wrong block group guard')
  binding.require(len(args.worker_cpus)==5 and len(set(args.worker_cpus))==5 and
   os.sched_getaffinity(0)==set(args.worker_cpus),'five inherited CPUs required')
  binding.require(not any(n=='validation' or n.startswith(('validation.','timecut5')) or
   n.split('.')[0] in ('numpy','scipy','sympy') for n in sys.modules),'mathematics imported before block fence')
  sys.meta_path.insert(0,suffix_census.NoOptimization())
  sources=suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha);before()
  index,trusted,checked,anchors=suffix_census.completed_inputs(binding.ROOT,args,args.deadline,before)
  original=read_pinned(args.historical_plan,args.historical_plan_sha,4*1024**2)
  binding.require(original['state_id']=='C01' and original['H_ref']==4 and original['sites']==8 and original['regions']==2047 and
   original['dominance'] is True and original['external_incumbent'] is None,'fixed C01 physical population required')
  raw_writer=BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],BATCH_REPLAY.worker_evidence_bytes,profile_name=BATCH_REPLAY.name)
  writer=QuotaWriter(raw_writer,before)
  resource_plan=dict(name='C01-four-block-persistent-resource-v1',absolute_seconds=SECONDS,
   evidence_charge_bytes=EVIDENCE_BYTES,uncompressed_archive_bytes=RAW_ARCHIVE_BYTES,
   maximum_input_bytes=MAX_INPUT_BYTES,models=MAX_MODELS,block_size=256,persistent_workers=4,
   candidate_as_bytes=1024**3,candidate_peak_rss_bytes=768*1024**2,seconds_per_model=30,maximum_passes_per_model=12,
   maximum_candidate_passes=MAX_MODELS*12,numerical_cache_enabled=False,worker_cpus=args.worker_cpus)
  writer.write('run-binding.json',domain.chunks(dict(schema='hiroute-suffix-block-run-binding-v1',
   source_commit=args.source_commit,source_sha256=args.source_sha,completed_replay=anchors,
   logical_report_sha256=args.logical_report_sha,resource_plan=resource_plan)))
  stage='fresh-family'
  payload=read_pinned(args.capture,index['capture_sha256'],1024**3)
  binding.require(payload['schema']=='hiroute-recorded-real-capture-v1' and payload['source_plan_sha256']==args.historical_plan_sha,
   'capture identity changed')
  for key in ('source_sha256','input_sha256','query_sha256'):
   suffix_census.same(payload[key],original[key],'capture '+key+' changed')
  suffix_census.same(payload['query'],original['query'],'capture query changed')
  suffix_census.same(payload['variant'],domain.variant(original),'capture variant changed')
  bundle=payload['bundle'];del payload;before()
  from validation.real5_v2.batch_jobs import BatchExecutor,WORKER_AS
  from .family_gate import verify_families
  from validation.family5.checker import _plain
  binding.require(WORKER_AS==1024**3,'scalar child cap changed')
  started=time.monotonic()
  with BatchExecutor(tuple(args.worker_cpus[1:]),float(args.deadline-10),index['capture_sha256'],kernel='interval-join-v1') as pool:
   binding.require(len(pool.slots)==4 and all(s.process.poll() is None for s in pool.slots),'four family workers required')
   os.sched_setaffinity(0,{args.worker_cpus[0]});ctx,ledger=verify_families(bundle,trusted,pool)
  del bundle
  binding.require(all(s.process.poll() is not None for s in pool.slots),'family workers not reaped')
  writer.write('batch-ledger.json',domain.chunks(ledger))
  writer.write('family-summary.json',domain.chunks(dict(checked=_plain(ctx.summary),wall_seconds=time.monotonic()-started)))
  stage='cold-population-and-selection'
  from .indexed_population import admit_population
  admitted=admit_population(binding.ROOT,args,ctx,args.deadline,before);selection=freeze_selection(admitted)
  writer.write('block-plan.json',domain.chunks(admitted.population.plan()))
  selection_pin=writer.write('pilot-selection.json',domain.chunks(selection));before()
  # All identities and original bands are now immutable before model matrices
  # or candidate LPs. A block is a storage/work partition, never a new sample.
  source_context=dict(schema='hiroute-suffix-block-work-context-v1',source_sha256=args.source_sha,
   source_bundle_sha256=ctx.summary['bundle_sha256'],capture_sha256=index['capture_sha256'],
   block_plan_sha256=admitted.population.plan_sha256,selection_sha256=selection_pin['sha256'],
   original_query_freeze_sha256=index['query_freeze_sha256'],resource_plan_sha256=binding.digest(resource_plan))
  from .lp_stream_jobs import stream_results
  os.sched_setaffinity(0,set(args.worker_cpus));stage='persistent-candidates-and-exact-checks'
  started=time.monotonic()
  with stream_results(model_jobs(ctx,selection,source_context,before),cpus=tuple(args.worker_cpus[1:]),
   coordinator_cpu=args.worker_cpus[0],deadline_monotonic=float(args.deadline-10),max_jobs=MAX_MODELS,
   max_input_bytes=MAX_INPUT_BYTES) as results:
   proof=publish_proofs(ctx,selection,source_context,writer,results,deadline=args.deadline,before=before)
  numerical_wall=time.monotonic()-started;stage='final-binding'
  verify_loaded({'source_files':sources});suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha);before()
  final_admitted=admit_population(binding.ROOT,args,ctx,args.deadline,before)
  suffix_census.same(final_admitted.commitment(),admitted.commitment(),'original query population changed during block work')
  binding.require(binding.pin(args.capture)['sha256']==index['capture_sha256'],'capture changed during block work')
  summary=dict(schema='hiroute-four-block-resource-summary-v1',source_context=source_context,resource_plan=resource_plan,
   population=admitted.commitment(),selection=selection_pin,proof_archive=proof['archive'],encoding=proof['encoding'],
   complete=proof['footer']['complete'],verified_models=proof['footer']['verified_models'],
   blocks=proof['footer']['blocks'],transport=proof['footer']['transport'],numerical_wall_seconds=numerical_wall,
   query_optimum_certified=False,full_population_complete=False,literal_G8_closed=False)
  writer.write('block-summary.json',domain.chunks(summary));before()
  binding.require({r['path'] for r in writer.files}=={'run-binding.json','batch-ledger.json','family-summary.json',
   'block-plan.json','pilot-selection.json','model-proofs.jsonl.gz','block-summary.json'},'block output coverage changed')
  raw_writer.finalize();before();return 0 if summary['complete'] else 1
 except BaseException as error:
  if writer is not None and pool is not None and not any(r['path']=='batch-ledger.json' for r in writer.files):
   try:writer.write('partial-batch-ledger.json',domain.chunks(pool.snapshot()))
   except BaseException:pass
  worker_failure(type(error).__name__,str(error)[:4096],stage);return 1
 finally:
  if raw_writer is not None:raw_writer.close()

def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--deadline',type=float)
 for name in ('historical-plan','replay-plan','replay-attempt','replay-return','logical-attempt','logical-return','capture'):
  p.add_argument('--'+name,type=Path,required=True)
 for name in ('historical-plan-sha','replay-plan-sha','replay-return-sha','replay-manifest-sha','replay-result-sha',
  'replay-decision-sha','query-index-sha','source-commit','source-sha','logical-return-sha','logical-report-sha','logical-source-sha'):
  p.add_argument('--'+name,required=True)
 p.add_argument('--worker-cpus',type=int,nargs=5,required=True);p.add_argument('--cpu',type=int);p.add_argument('--attempt-dir',type=Path)
 args=p.parse_args()
 if args.worker:return worker(args)
 binding.require(args.cpu is not None and args.attempt_dir is not None,'supervisor CPU and fresh block attempt required')
 deadline=float(ENTRY+SECONDS);soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 binding.require(hard==resource.RLIM_INFINITY or hard>=BATCH_REPLAY.child_as_bytes,'inherited AS ceiling too small')
 resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha)
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.block_pilot','--worker','--deadline',repr(deadline),
  '--worker-cpus',*map(str,args.worker_cpus)]
 for key,value in vars(args).items():
  if key not in ('worker','deadline','worker_cpus','cpu','attempt_dir'):argv+=['--'+key.replace('_','-'),str(value)]
 context=binding.digest({k:str(v) for k,v in vars(args).items() if k not in ('worker','deadline','cpu','attempt_dir')})
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=BATCH_REPLAY,cpu=args.cpu,worker_cpus=tuple(args.worker_cpus),
  context=PlanContext(args.replay_plan_sha,args.source_sha,context,BATCH_REPLAY.name),entry_monotonic=float(ENTRY),deadline_monotonic=deadline)
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
