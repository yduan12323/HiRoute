"""One explicitly admitted four-worker, same-capture diagnostic; no solver."""
import time
ENTRY=time.monotonic()
import argparse,json,os,resource,sys
from pathlib import Path
from unittest.mock import patch
from . import plan as binding
from .diagnose import Observer,DiagnosticStop,MAX_POST_DECODE_SECONDS,TOTAL_SECONDS
from .runtime import BATCH_REPLAY,PlanContext,BoundedEvidenceWriter,run_phase,worker_failure

CHANGED={'validation/real5_v2/family.py','experiments/time_cut_v2/recorded_real/runtime.py'}
ADDED={'validation/family5/independent_oracle_v4.py','validation/family5/independent_oracle_v3.py','validation/real5_v2/batch_jobs.py',
 'experiments/time_cut_v2/recorded_real/diagnose.py','experiments/time_cut_v2/recorded_real/parallel_profile.py'}

def inputs(args):
 root=binding.ROOT
 binding.require(binding.pin(args.plan)['sha256']==args.plan_sha,'historical plan changed');value=binding.load(args.plan)
 binding.require(value['schema']=='hiroute-recorded-real-plan-v1' and binding.digest(value['source_files'])==value['source_sha256'],'historical source manifest changed')
 binding.assert_committed_sources(root,value['source_files'],value['source_commit'])
 current=binding.source_inventory(root)
 binding.require(set(current)-set(value['source_files'])==ADDED,'unreviewed added source')
 binding.require(set(value['source_files'])<=set(current),'historical source disappeared')
 changed={name for name,spec in value['source_files'].items() if current[name]!=spec}
 binding.require(changed==CHANGED,'unreviewed changed source')
 binding.require(binding.source_commit(root)==args.source_commit and binding.digest(current)==args.source_sha,'reviewed source snapshot changed')
 binding.assert_committed_sources(root,current,args.source_commit)
 binding.require(binding.digest(value['inputs'])==value['input_sha256'],'historical input manifest changed')
 for spec in value['inputs'].values():binding.require(binding.pin(binding.inside(root,spec['path']))=={k:spec[k] for k in ('sha256','size_bytes')},'historical input changed')
 binding.verify_export_chain(root,value)
 binding.require(binding.pin(args.capture)['sha256']==args.capture_sha,'capture bytes changed')
 return value

class BatchObserver(Observer):
 def __init__(self,pool):super().__init__('v3-cached');self.pool=pool
 def sample(self,signum,frame):
  try:super().sample(signum,frame)
  finally:
   if self.samples:
    self.samples[-1]['batch_progress']=dict(submitted=len(self.pool.submitted),completed=len(self.pool.results),
     in_flight=[s.pending['index'] for s in self.pool.slots if s.pending is not None],
     worker_pids=[s.process.pid for s in self.pool.slots])

def run_profile(payload,trusted,pool):
 from validation.real5_v2 import family
 from validation.real5_v2.shared_replay import verify_coalesced_trace
 original=family._verify_bundle;observer=BatchObserver(pool);result=None;error=None
 def delegated(*a,**kw):
  binding.require('batch_executor' not in kw,'nested batch executor')
  return original(*a,**kw,batch_executor=pool)
 try:
  with patch.object(family,'_verify_bundle',delegated):
   result=observer.run(lambda:verify_coalesced_trace(payload['trace'],payload['bundle'],trusted),MAX_POST_DECODE_SECONDS)
 except DiagnosticStop as exc:error=dict(type=type(exc).__name__,message=str(exc))
 except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc)[:1000])
 return result,error,observer

def worker(args):
 from .worker import Fence
 binding.require(type(args.worker_cpus) is list and len(args.worker_cpus)==len(set(args.worker_cpus))==5 and
  all(type(cpu) is int for cpu in args.worker_cpus) and set(args.worker_cpus)==os.sched_getaffinity(0),'worker mask differs from guarded group')
 sys.meta_path.insert(0,Fence('replay'));value=inputs(args)
 from . import domain
 from validation.family5.checker import wire_equal
 from validation.real5_v2.batch_jobs import BatchExecutor
 binding.require(os.environ.get('HIROUTE_PROFILE')==BATCH_REPLAY.name and
  int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES'])==BATCH_REPLAY.worker_evidence_bytes,'wrong group profile')
 binding.require(type(args.deadline) is float and time.monotonic()+MAX_POST_DECODE_SECONDS+20<args.deadline,'insufficient absolute diagnostic budget')
 # Spawn before loading the 835 MB capture: no child inherits its live registry.
 with BatchExecutor(tuple(args.worker_cpus[1:]),args.deadline-10,args.capture_sha,kernel=args.batch_kernel) as pool:
  os.sched_setaffinity(0,{args.worker_cpus[0]})
  before=time.monotonic();payload=binding.load(args.capture);decode=time.monotonic()-before
  binding.require(payload['schema']=='hiroute-recorded-real-capture-v1' and payload['source_plan_sha256']==args.plan_sha,'capture plan changed')
  for key in ('source_sha256','input_sha256','query_sha256'):binding.require(payload[key]==value[key],'capture context changed')
  binding.require(wire_equal(payload['variant'],domain.variant(value)) and wire_equal(payload['query'],value['query']),'capture scope changed')
  trusted=domain.trusted_case(value,binding.ROOT)
  result,error,observer=run_profile(payload,trusted,pool)
  ledger=pool.snapshot()
 report=dict(schema='hiroute-parallel-replay-diagnostic-v1',acceptance=False,structural_verified=False,solver_calls=0,
  suffix_optimizer_calls=0,oracle_version='v3-parent-'+args.batch_kernel+'-complete-batch-v1',batch_kernel=args.batch_kernel,capture_sha256=args.capture_sha,
  plan_sha256=args.plan_sha,diagnostic_source_commit=args.source_commit,diagnostic_source_sha256=args.source_sha,
  worker_cpus=args.worker_cpus,decode_seconds=decode,checker_returned=result is not None,error=error,
  post_decode_budget_seconds=MAX_POST_DECODE_SECONDS,observations=observer.snapshot(),family_jobs_complete=ledger['complete'],
  captured_population=dict(nodes=len(payload['bundle']['nodes']),batches=len(payload['bundle']['batches']),
   events=len(payload['trace']['events']),callbacks=len(payload['callback_requests'])),callback_checks_started=False)
 raw_ledger=binding.canonical(ledger)+b'\n';raw_report=binding.canonical(report)+b'\n'
 binding.require(len(raw_ledger)<=32*1024**2 and len(raw_report)<=1024**2,'diagnostic evidence cap')
 with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],BATCH_REPLAY.worker_evidence_bytes,profile_name=BATCH_REPLAY.name) as writer:
  writer.write('batch-ledger.json',[raw_ledger]);writer.write('diagnostic.json',[raw_report]);writer.finalize()
 return 0

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true')
 for name in ('plan','capture'):parser.add_argument('--'+name,type=Path,required=True);parser.add_argument('--'+name+'-sha',required=True)
 parser.add_argument('--source-commit',required=True);parser.add_argument('--source-sha',required=True)
 parser.add_argument('--worker-cpus',type=int,nargs=5,required=True);parser.add_argument('--cpu',type=int)
 parser.add_argument('--batch-kernel',choices=('v2','tau-precompute-v1'),default='v2')
 parser.add_argument('--deadline',type=float);parser.add_argument('--attempt-dir',type=Path);args=parser.parse_args()
 if args.worker:
  try:return worker(args)
  except BaseException as exc:worker_failure(type(exc).__name__,str(exc)[:4096],'parallel-diagnostic');return 1
 binding.require(args.cpu is not None and args.attempt_dir is not None,'supervisor CPU and new attempt required')
 soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 binding.require(hard==resource.RLIM_INFINITY or hard>=BATCH_REPLAY.child_as_bytes,'inherited AS ceiling too small')
 resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 value=inputs(args);deadline=float(ENTRY+TOTAL_SECONDS)
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.parallel_profile','--worker',
  '--plan',str(args.plan.resolve()),'--plan-sha',args.plan_sha,'--capture',str(args.capture.resolve()),'--capture-sha',args.capture_sha,
  '--source-commit',args.source_commit,'--source-sha',args.source_sha,'--deadline',repr(deadline),
  '--worker-cpus',*map(str,args.worker_cpus),'--batch-kernel',args.batch_kernel]
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=BATCH_REPLAY,cpu=args.cpu,worker_cpus=tuple(args.worker_cpus),
  context=PlanContext(args.plan_sha,args.source_sha,binding.digest(dict(input_sha256=value['input_sha256'],capture_sha256=args.capture_sha)),BATCH_REPLAY.name),
  entry_monotonic=float(ENTRY),deadline_monotonic=deadline)
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
