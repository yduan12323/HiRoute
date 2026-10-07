"""Opt-in complete same-capture replay with four bounded scalar-check workers."""
import time
ENTRY=time.monotonic()
import argparse,json,math,os,resource,sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from . import domain,plan as binding,replay_plan
from .hot_jobs import read_pinned
from .runtime import BATCH_REPLAY,BoundedEvidenceWriter,PlanContext,run_phase,worker_failure
from .worker import Fence,REPLAY_FILES,prior_capture,verify_loaded

KERNEL='interval-sweep-v1'
KERNELS=(KERNEL,'interval-join-v1')
EXTRA_FILES={'batch-ledger.json','stage-before-family.json','stage-after-family.json','parallel-summary.json'}
CAPTURE_PIN_FIELDS=('capture_manifest_sha','capture_result_sha','capture_decision_sha','capture_return_sha')

def capture_pins(args):
 return {key:getattr(args,key) for key in CAPTURE_PIN_FIELDS}

def input_context(args,original):
 return binding.digest(dict(historical_plan_sha256=args.historical_plan_sha,input_sha256=original['input_sha256'],
  capture_commitments=capture_pins(args),batch_kernel=args.batch_kernel,node_oracle='v3-cached'))

def inputs(args,deadline):
 return replay_plan.verify(binding.ROOT,args.plan,args.plan_sha,args.historical_plan,args.historical_plan_sha,deadline)

def replay(original,current,root,writer,original_sha,current_sha,capture_path,capture_sha,pool,before=lambda:None):
 """Use the complete serial domain path; only scalar selection batches delegate."""
 from validation.real5_v2 import family
 from validation.family5.independent_oracle_v3 import MemoizedOracle
 from validation.family5.checker import VerificationError
 binding.require(pool.kernel in KERNELS,'full replay requires a pinned interval kernel')
 original_verify=family._verify_bundle;memo=MemoizedOracle();calls=0;ledger_commitment=None
 def exact(a,b,reason):
  try:return memo.exact_family_equal(a,b)
  except AssertionError as error:raise VerificationError(f'{reason}: {error}') from error
 def delegated(*a,**kw):
  nonlocal calls,ledger_commitment
  binding.require(calls==0 and 'batch_executor' not in kw,'unexpected repeated family verification');calls+=1
  before();domain.stage(writer,'before-family')
  checked=original_verify(*a,**kw,batch_executor=pool)
  ledger=pool.snapshot();binding.require(ledger['complete'] is True,'incomplete batch ledger')
  encoded=binding.canonical(ledger)+b'\n';binding.require(len(encoded)<=32*1024**2,'complete batch ledger cap')
  ledger_commitment=writer.write('batch-ledger.json',[encoded]);before()
  domain.stage(writer,'after-family',nodes=checked.summary['nodes'],batches=checked.summary['batches'],
   selection_jobs=ledger['completed_count'],checked_affine_cells=checked.summary['checked_affine_cells'])
  return checked
 def capture_load(path):
  binding.require(Path(path)==Path(capture_path),'unexpected full-replay JSON load')
  return read_pinned(path,capture_sha,1024**3)
 with ExitStack() as hooks:
  hooks.enter_context(patch.object(family,'oracle',memo));hooks.enter_context(patch.object(family,'_exact',exact))
  hooks.enter_context(patch.object(family,'_verify_bundle',delegated));hooks.enter_context(patch.object(domain,'load',capture_load))
  summary=domain.replay(original,root,writer,original_sha,capture_path,capture_sha,before)
 binding.require(calls==1 and ledger_commitment is not None and pool.snapshot()['complete'] is True,'missing complete family join')
 files={row['path']:row for row in writer.files}
 result=dict(schema='hiroute-complete-parallel-replay-v1',structural_verified=summary['structural_verified'],
  literal_G8_closed=False,solver_calls=0,suffix_optimizer_calls=0,batch_kernel=pool.kernel,node_oracle='v3-cached',
  historical_plan_sha256=original_sha,current_plan_sha256=current_sha,current_source_sha256=current['source_sha256'],
  input_sha256=original['input_sha256'],capture_sha256=capture_sha,batch_ledger=ledger_commitment,
  structural_summary=files['structural-summary.json'],callback_receipts=files['callback-receipts.json'],
  query_index=files['query-index.json'],reference_comparison=summary['reference_comparison'],node_oracle_cache=memo.snapshot(),
  scope='complete structural replay of the fixed historical capture; no numerical suffix certification')
 writer.write('parallel-summary.json',domain.chunks(result));before()
 return result

def worker(args):
 writer=None;pool=None;current_stage='binding'
 def before():binding.require(math.isfinite(args.deadline) and time.monotonic()<args.deadline,'absolute replay deadline')
 try:
  before();binding.require(args.batch_kernel in KERNELS,'unreviewed replay kernel')
  binding.require(type(args.worker_cpus) is list and len(args.worker_cpus)==len(set(args.worker_cpus))==5 and
   all(type(cpu) is int for cpu in args.worker_cpus) and set(args.worker_cpus)==os.sched_getaffinity(0),'worker mask differs from guarded group')
  binding.require(os.environ.get('HIROUTE_PROFILE')==BATCH_REPLAY.name and
   int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES'])==BATCH_REPLAY.worker_evidence_bytes,'wrong group profile')
  binding.require(not any(n=='timecut5' or n.startswith(('timecut5.','validation.')) for n in sys.modules),'math imported before replay fence')
  sys.meta_path.insert(0,Fence('replay'));original,current=inputs(args,args.deadline)
  path,sha=prior_capture(original,args.historical_plan_sha,args.capture_attempt,args.capture_manifest_sha,
   args.capture_result_sha,args.capture_decision_sha,args.deadline,successful_return_path=args.capture_return,
   successful_return_sha=args.capture_return_sha)
  writer=BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],BATCH_REPLAY.worker_evidence_bytes,profile_name=BATCH_REPLAY.name)
  writer.write('run-binding.json',domain.chunks(dict(schema='hiroute-parallel-replay-binding-v1',
   historical_plan_sha256=args.historical_plan_sha,current_plan_sha256=args.plan_sha,
   source_sha256=current['source_sha256'],input_sha256=original['input_sha256'],capture_sha256=sha,
   capture_commitments=capture_pins(args),worker_cpus=args.worker_cpus,batch_kernel=args.batch_kernel,
   profile_name=BATCH_REPLAY.name,reference_usage='comparison_after_complete_independent_replay_only')))
  from validation.real5_v2.batch_jobs import BatchExecutor,WORKER_AS
  binding.require(WORKER_AS==1024**3,'reviewed child cap changed')
  # All four fresh workers start before decode, while the five-CPU mask is inherited.
  with BatchExecutor(tuple(args.worker_cpus[1:]),float(args.deadline-10),sha,kernel=args.batch_kernel) as pool:
   binding.require(len(pool.slots)==4 and all(s.process.poll() is None for s in pool.slots),'four live scalar workers required')
   os.sched_setaffinity(0,{args.worker_cpus[0]});current_stage='complete-replay'
   replay(original,current,binding.ROOT,writer,args.historical_plan_sha,args.plan_sha,path,sha,pool,before)
  current_stage='final-binding';verify_loaded(current);inputs(args,args.deadline);before()
  binding.require({row['path'] for row in writer.files}==REPLAY_FILES|EXTRA_FILES,'parallel replay output coverage changed')
  writer.finalize();before();return 0
 except BaseException as error:
  if writer is not None and pool is not None and not any(r['path']=='batch-ledger.json' for r in writer.files):
   try:writer.write('partial-batch-ledger.json',domain.chunks(pool.snapshot()))
   except BaseException:pass # The original failure and any admitted bytes remain authoritative.
  worker_failure(type(error).__name__,str(error)[:4096],current_stage);return 1
 finally:
  if writer is not None:writer.close()

def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true')
 for name in ('plan','historical-plan'):
  p.add_argument('--'+name,type=Path,required=True);p.add_argument('--'+name+'-sha',required=True)
 p.add_argument('--capture-attempt',type=Path,required=True);p.add_argument('--capture-return',type=Path,required=True)
 for name in CAPTURE_PIN_FIELDS:p.add_argument('--'+name.replace('_','-'),required=True)
 p.add_argument('--worker-cpus',type=int,nargs=5,required=True);p.add_argument('--cpu',type=int)
 p.add_argument('--batch-kernel',choices=KERNELS,default=KERNEL)
 p.add_argument('--deadline',type=float);p.add_argument('--attempt-dir',type=Path);args=p.parse_args()
 if args.worker:return worker(args)
 binding.require(args.cpu is not None and args.attempt_dir is not None,'supervisor CPU and fresh attempt required')
 deadline=float(ENTRY+BATCH_REPLAY.wall_seconds)
 soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 binding.require(hard==resource.RLIM_INFINITY or hard>=BATCH_REPLAY.child_as_bytes,'inherited AS ceiling too small')
 resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 original,current=inputs(args,deadline)
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.parallel_replay','--worker','--deadline',repr(deadline),
  '--worker-cpus',*map(str,args.worker_cpus),'--batch-kernel',args.batch_kernel]
 for name in ('plan','historical_plan','capture_attempt','capture_return'):
  argv+=['--'+name.replace('_','-'),str(getattr(args,name).resolve())]
 for name in ('plan_sha','historical_plan_sha',*CAPTURE_PIN_FIELDS):argv+=['--'+name.replace('_','-'),getattr(args,name)]
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=BATCH_REPLAY,cpu=args.cpu,worker_cpus=tuple(args.worker_cpus),
  context=PlanContext(args.plan_sha,current['source_sha256'],input_context(args,original),BATCH_REPLAY.name),
  entry_monotonic=float(ENTRY),deadline_monotonic=deadline)
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
