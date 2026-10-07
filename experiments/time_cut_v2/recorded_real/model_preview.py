"""Fixed small model/task payload preview, with no numerical optimization."""
import time
ENTRY=time.monotonic()
import argparse,json,math,os,resource,sys
from dataclasses import asdict
from pathlib import Path
from . import plan as binding,domain,suffix_census
from .hot_jobs import read_pinned
from .runtime import BATCH_REPLAY,REPLAY,PlanContext,BoundedEvidenceWriter,read_phase_result,run_phase,worker_failure
from .worker import verify_loaded

SECONDS=480
PAYLOAD_BYTES=64*1024**2
FILES={'run-binding.json','selection.json','stage-before-family.json','stage-after-family.json',
 'batch-ledger.json','model-payloads.json','task-payloads.json','preview-summary.json'}

def logical_input(args,anchors,index,trusted,summary,deadline,before):
 successful=read_pinned(args.logical_return,args.logical_return_sha,65536)
 accepted=read_phase_result(args.logical_attempt,successful_return=successful,deadline_monotonic=deadline,resource_check=before)
 binding.require(accepted['status']=='completed' and accepted['descendants_reaped'] is True,'logical count did not complete')
 suffix_census.same(accepted['profile'],asdict(REPLAY),'logical count profile changed')
 binding.require(accepted['context']['plan_sha256']==args.replay_plan_sha and
  accepted['context']['source_sha256']==args.logical_source_sha,'logical count source context changed')
 root=Path(args.logical_attempt)/'evidence'
 manifest=read_pinned(root/'__manifest.json',accepted['verified_manifest_sha256'],1024**2)
 binding.require(len(manifest['files'])==1 and manifest['files'][0]['path']=='suffix-census.json','logical count file coverage')
 spec=manifest['files'][0];binding.require(spec['sha256']==args.logical_report_sha and spec['size_bytes']<=PAYLOAD_BYTES,'logical count report pin')
 report=read_pinned(root/'suffix-census.json',args.logical_report_sha,PAYLOAD_BYTES)
 binding.require(report['schema']=='hiroute-real-suffix-count-v1' and report['literal_G8_closed'] is False and
  report['numerical_suffix_verified'] is False and report['census_source_sha256']==args.logical_source_sha and report['count_only'] is True and
  type(report['solver_calls']) is int and report['solver_calls']==0 and
  type(report['lp_matrix_constructions']) is int and report['lp_matrix_constructions']==0,'logical report scope changed')
 suffix_census.same(report['evidence'],anchors,'logical report changed completed replay source')
 from .logical_models import count_logical_models
 recomputed=count_logical_models(index,trusted,summary['checked'],before)
 for key in ('logical_model_plan','queries','totals','exact_queries','empty_action_queries','empty_action_sha256',
  'query_freeze_sha256','source_bundle_sha256','real_input'):
  suffix_census.same(report[key],recomputed[key],'logical report mismatch: '+key)
 before();return report['logical_model_plan']

def raw_models(rows):
 yield b'['
 for i,row in enumerate(rows):
  if i:yield b','
  yield b'{"base_task_ids":'+binding.canonical(row['base_task_ids'])
  yield b',"logical_identity":'+row['logical_identity']+b',"model":'+row['model_bytes']
  yield b',"model_sha256":'+binding.canonical(row['model_sha256'])
  yield b',"selection_position":'+binding.canonical(row['selection_position'])+b'}'
 yield b']\n'

def raw_tasks(catalog):
 yield b'['
 for i,(key,raw) in enumerate(catalog.payloads.items()):
  if i:yield b','
  yield b'{"sha256":'+binding.canonical(key)+b',"task":'+raw+b'}'
 yield b']\n'

def preview_capture(original,original_sha,index,trusted,logical,capture_path,capture_sha,pool,writer,before=lambda:None):
 """Tiny-testable domain core; the public worker separately binds fixed C01."""
 from validation.suffix5.preview_selection import select_preview
 from validation.suffix5.task_catalog import TaskCatalog,compile_selected
 from validation.family5.checker import _plain
 from .family_gate import verify_families
 selection=select_preview(logical,trusted)
 selection_pin=writer.write('selection.json',domain.chunks(selection));before()
 # Selection is already frozen before capture decode/family checks or matrices.
 payload=read_pinned(capture_path,capture_sha,1024**3)
 binding.require(payload['schema']=='hiroute-recorded-real-capture-v1' and payload['source_plan_sha256']==original_sha,'capture schema/plan changed')
 for key in ('source_sha256','input_sha256','query_sha256'):suffix_census.same(payload[key],original[key],'capture '+key+' changed')
 suffix_census.same(payload['query'],original['query'],'capture physical query changed')
 suffix_census.same(payload['variant'],domain.variant(original),'capture variant changed')
 bundle=payload['bundle'];del payload # Past full replay, not this phase, covers trace/callback occurrences.
 before();domain.stage(writer,'before-family')
 checked,ledger=verify_families(bundle,trusted,pool)
 del bundle
 binding.require(checked.summary['bundle_sha256']==index['bundle_sha256'] and
  checked.summary['case_sha256']==index['case_sha256'],'fresh checked bundle differs from completed trace index')
 suffix_census.same(_plain(checked.summary['real_input_sources']),trusted.source_snapshot(),'fresh physical sources changed')
 raw=binding.canonical(ledger)+b'\n';binding.require(len(raw)<=32*1024**2,'batch ledger byte cap')
 ledger_pin=writer.write('batch-ledger.json',[raw]);before()
 domain.stage(writer,'after-family',nodes=checked.summary['nodes'],batches=checked.summary['batches'],
  selection_jobs=ledger['completed_count'],checked_affine_cells=checked.summary['checked_affine_cells'])
 for group in selection['selected_families']:
  ident=group['family_id'];binding.require(ident in checked._pieces,'selected original family missing')
  p=checked._pieces[ident];context=logical['groups'][group['group_index']]['context']
  suffix_census.same(context,dict(state=_plain(p.state),rho=str(p.rho),pi=_plain(p.pi),H_remaining=trusted.physics.bound-p.state[2]),
   'selected family differs from index context')
 before();wall=time.monotonic();cpu=time.process_time()
 catalog=TaskCatalog(max_entry_bytes=1024**2,max_total_bytes=32*1024**2,max_tasks=512)
 result=compile_selected(checked,[r['selection'] for r in selection['models']],max_models=256,
  max_model_bytes=1024**2,max_total_model_bytes=32*1024**2,catalog=catalog)
 timing=dict(wall_seconds=time.monotonic()-wall,cpu_seconds=time.process_time()-cpu)
 used=0
 def bounded(chunks):
  nonlocal used
  for chunk in chunks:
   before();used+=len(chunk);binding.require(used<=PAYLOAD_BYTES,'aggregate model/task payload cap');yield chunk
 model_pin=writer.write('model-payloads.json',bounded(raw_models(result['models'])))
 task_pin=writer.write('task-payloads.json',bounded(raw_tasks(catalog)))
 summary=dict(schema='hiroute-structural-model-payload-preview-v1',selection=selection_pin,batch_ledger=ledger_pin,
  model_payloads=model_pin,task_payloads=task_pin,model_builder_comparison=True,construction=timing,
  selected_models=result['selected_models'],selected_families=len(selection['selected_families']),
  original_unique_logical_models=logical['unique_logical_model_slots'],model_bytes=result['model_bytes'],
  task_catalog=result['catalog'],published_payload_bytes=used,
  maximum_model_bytes=max((len(r['model_bytes']) for r in result['models']),default=0),
  maximum_task_bytes=max(map(len,catalog.payloads.values()),default=0),
  family_verification=_plain(checked.summary),capture_sha256=capture_sha,
  solver_calls=0,certificate_reuse_accepted=False,full_population_complete=False,literal_G8_closed=False,
  ordered_trace_replayed_in_this_attempt=False,
  scope='construction cost and exact base-task sharing for the predeclared structural sample only')
 before();return summary

def worker(args):
 writer=None;pool=None;stage='binding'
 def before():binding.require(math.isfinite(args.deadline) and time.monotonic()<args.deadline,'preview absolute deadline')
 try:
  binding.require(os.environ.get('HIROUTE_PROFILE')==BATCH_REPLAY.name and
   os.environ.get('HIROUTE_EVIDENCE_CAP_BYTES')==str(BATCH_REPLAY.worker_evidence_bytes),'wrong group guard')
  binding.require(len(args.worker_cpus)==5 and len(set(args.worker_cpus))==5 and
   os.sched_getaffinity(0)==set(args.worker_cpus),'five inherited coordinator/worker CPUs required')
  binding.require(not any(n=='validation' or n.startswith(('validation.','timecut5')) or n.split('.')[0] in ('numpy','scipy','sympy') for n in sys.modules),
   'mathematics imported before preview fence')
  sys.meta_path.insert(0,suffix_census.NoOptimization())
  sources=suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha);before()
  index,trusted,summary,anchors=suffix_census.completed_inputs(binding.ROOT,args,args.deadline,before)
  original=read_pinned(args.historical_plan,args.historical_plan_sha,4*1024**2)
  binding.require(original['state_id']=='C01' and original['H_ref']==4 and original['sites']==8 and original['regions']==2047 and
   original['dominance'] is True and original['external_incumbent'] is None,'fixed original C01 population required')
  logical=logical_input(args,anchors,index,trusted,summary,args.deadline,before)
  from validation.suffix5.preview_selection import select_preview
  selected=select_preview(logical,trusted)
  binding.require(selected['selected_models']==256 and len(selected['selected_families'])==7 and
   [sum(row['prefix_depth']==d for row in selected['models']) for d in range(4)]==[64,96,64,32],
   'fixed preview population changed')
  writer=BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],BATCH_REPLAY.worker_evidence_bytes,profile_name=BATCH_REPLAY.name)
  run_binding=dict(schema='hiroute-model-preview-binding-v1',source_commit=args.source_commit,source_sha256=args.source_sha,
   completed_replay=anchors,logical_report_sha256=args.logical_report_sha,logical_return_sha256=args.logical_return_sha,
   logical_source_sha256=args.logical_source_sha,preview_policy=selected['policy'],worker_cpus=args.worker_cpus,
   seconds=SECONDS,payload_cap_bytes=PAYLOAD_BYTES,solver_calls=0)
  writer.write('run-binding.json',domain.chunks(run_binding))
  from validation.real5_v2.batch_jobs import BatchExecutor,WORKER_AS
  binding.require(WORKER_AS==1024**3,'scalar child cap changed')
  stage='fresh-family-and-model-preview'
  with BatchExecutor(tuple(args.worker_cpus[1:]),float(args.deadline-10),index['capture_sha256'],kernel='interval-join-v1') as pool:
   binding.require(len(pool.slots)==4 and all(s.process.poll() is None for s in pool.slots),'four fresh scalar children required')
   os.sched_setaffinity(0,{args.worker_cpus[0]})
   result=preview_capture(original,args.historical_plan_sha,index,trusted,logical,args.capture,index['capture_sha256'],pool,writer,before)
  result.update(completed_replay=anchors,logical_report_sha256=args.logical_report_sha,source_sha256=args.source_sha)
  writer.write('preview-summary.json',domain.chunks(result));stage='final-binding'
  verify_loaded({'source_files':sources});suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha);before()
  again=suffix_census.completed_inputs(binding.ROOT,args,args.deadline,before)
  suffix_census.same(again[3],anchors,'completed replay binding changed during preview')
  logical_input(args,again[3],again[0],again[1],again[2],args.deadline,before)
  binding.require(binding.pin(args.capture)['sha256']==index['capture_sha256'],'capture changed during preview');before()
  binding.require({r['path'] for r in writer.files}==FILES,'preview output coverage changed');writer.finalize();before();return 0
 except BaseException as error:
  if writer is not None and pool is not None and not any(r['path']=='batch-ledger.json' for r in writer.files):
   try:writer.write('partial-batch-ledger.json',domain.chunks(pool.snapshot()))
   except BaseException:pass
  worker_failure(type(error).__name__,str(error)[:4096],stage);return 1
 finally:
  if writer is not None:writer.close()

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
 binding.require(args.cpu is not None and args.attempt_dir is not None,'supervisor CPU and fresh attempt required')
 deadline=float(ENTRY+SECONDS);soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 binding.require(hard==resource.RLIM_INFINITY or hard>=BATCH_REPLAY.child_as_bytes,'inherited AS ceiling too small')
 resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 suffix_census.check_sources(binding.ROOT,args.source_commit,args.source_sha)
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.model_preview','--worker','--deadline',repr(deadline),
  '--worker-cpus',*map(str,args.worker_cpus)]
 for key,value in vars(args).items():
  if key not in ('worker','deadline','worker_cpus','cpu','attempt_dir'):argv+=['--'+key.replace('_','-'),str(value)]
 context=binding.digest({k:str(v) for k,v in vars(args).items() if k not in ('worker','deadline','cpu','attempt_dir')})
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=BATCH_REPLAY,cpu=args.cpu,worker_cpus=tuple(args.worker_cpus),
  context=PlanContext(args.replay_plan_sha,args.source_sha,context,BATCH_REPLAY.name),entry_monotonic=float(ENTRY),deadline_monotonic=deadline)
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
