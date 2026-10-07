"""Opt-in bounded replay profiling; never an acceptance result or solver run."""
import time
ENTRY=time.monotonic()
import argparse,hashlib,json,os,resource,signal,sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from . import plan as binding
from .runtime import REPLAY,PlanContext,BoundedEvidenceWriter,run_phase,worker_failure

MAX_POST_DECODE_SECONDS=180
TOTAL_SECONDS=300
MAX_REPORT_BYTES=1024*1024

class DiagnosticStop(BaseException):
 pass

class Observer:
 """Temporary call counters and 1-Hz stacks; never replaces a check result."""
 def __init__(self):
  self.calls={};self.active=[];self.samples=[];self.transitions=[];self.started=time.monotonic();self.deadline=None
 def wrap(self,name,fn):
  def observed(*args,**kwargs):
   row=self.calls.setdefault(name,dict(calls=0,completed=0,elapsed_seconds=0.,max_first_input_items=0))
   row['calls']+=1
   if args and isinstance(args[0],(list,tuple,dict)):row['max_first_input_items']=max(row['max_first_input_items'],len(args[0]))
   if args and type(args[0]) is dict and type(args[0].get('parents')) in (list,tuple):
    row['max_parent_items']=max(row.get('max_parent_items',0),len(args[0]['parents']))
   start=time.monotonic();self.active.append(name)
   if len(self.transitions)<128:self.transitions.append(dict(event='enter',name=name,at_seconds=start-self.started))
   try:
    result=fn(*args,**kwargs);row['completed']+=1;return result
   finally:
    row['elapsed_seconds']+=time.monotonic()-start;self.active.pop()
  return observed
 def sample(self,signum,frame):
  now=time.monotonic();stack=[]
  while frame is not None and len(stack)<24:
   filename=frame.f_code.co_filename
   try:filename=str(Path(filename).relative_to(binding.ROOT))
   except ValueError:filename=Path(filename).name
   local=frame.f_locals;progress={}
   if frame.f_code.co_name in ('_verify_bundle','visit'):
    for key in ('checked_cells','i'):
     if type(local.get(key)) is int:progress[key]=local[key]
    for key in ('pieces','colors','order','regime_cache'):
     if type(local.get(key)) in (dict,list):progress[key+'_items']=len(local[key])
    if type(local.get('ident')) is str:progress['node_id']=local['ident'][:64]
   owner=local.get('self');fields=getattr(owner,'__dict__',{})
   if type(fields) is dict:
    for key in ('cursor','batch_cursor','invocation_id','coalescing_id'):
     if type(fields.get(key)) is int:progress[key]=fields[key]
   stack.append(dict(file=filename,function=frame.f_code.co_name,line=frame.f_lineno,progress=progress));frame=frame.f_back
  if len(self.samples)<MAX_POST_DECODE_SECONDS+2:
   self.samples.append(dict(at_seconds=now-self.started,active=list(self.active),stack=stack,
    cpu_seconds=time.process_time(),kernel_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024))
  if self.deadline is not None and now>=self.deadline:raise DiagnosticStop('post-decode diagnostic budget exhausted')
 def snapshot(self):
  return dict(calls=self.calls,stack_samples=self.samples,transitions=self.transitions,
   timing_scope='inclusive overlapping wall times, not additive; sampled stacks are observations',
   elapsed_seconds=time.monotonic()-self.started)

 def hooks(self):
  from validation.real5_v2 import family,shared_replay,trace
  from validation.family5 import independent_oracle_v2 as oracle
  from validation.trace5.checker import _Replay
  stack=ExitStack()
  targets=[(family,'_verify_bundle','family_validation'),(family,'verify_physical_states','physical_phase'),
   (_Replay,'__init__','trace_setup'),(trace.RealPhysicsReplayMixin,'run','trace_walk'),
   (shared_replay.RealCoalescedReplay,'ancestry','query_ancestry'),
   (shared_replay,'query_digest','query_freeze_hash'),(shared_replay,'freeze_shared','query_freeze_storage'),
   (family,'canonical','family_canonical'),(family,'digest','family_hash'),(family,'_freeze','family_freeze'),
   (oracle,'exact_family_equal','exact_family_equal'),(oracle,'equivalent','dominance_equivalence'),
   (oracle,'antichain','antichain'),(oracle,'arrangement','affine_arrangement')]
  for obj,name,label in targets:stack.enter_context(patch.object(obj,name,self.wrap(label,getattr(obj,name))))
  return stack

 def run(self,call,seconds):
  binding.require(type(seconds) in (int,float) and 0<seconds<=MAX_POST_DECODE_SECONDS,'diagnostic budget')
  binding.require(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'existing alarm cannot be replaced')
  old=signal.getsignal(signal.SIGALRM);self.deadline=time.monotonic()+seconds
  try:
   with self.hooks():
    signal.signal(signal.SIGALRM,self.sample);signal.setitimer(signal.ITIMER_REAL,min(1.,seconds),1.)
    return call()
  finally:
   signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)


def inputs(args):
 root=binding.ROOT
 binding.require(binding.pin(args.plan)['sha256']==args.plan_sha,'historical plan changed')
 value=binding.load(args.plan)
 binding.require(value['schema']=='hiroute-recorded-real-plan-v1','historical plan schema')
 binding.require(binding.digest(value['source_files'])==value['source_sha256'],'historical source inventory changed')
 for name,spec in value['source_files'].items():binding.require(binding.pin(binding.inside(root,name))==spec,'historical checker source changed: '+name)
 binding.assert_committed_sources(root,value['source_files'],value['source_commit'])
 current=binding.source_inventory(root)
 binding.require(set(current)-set(value['source_files'])=={'experiments/time_cut_v2/recorded_real/diagnose.py'},'unexpected diagnostic source delta')
 binding.require(binding.source_commit(root)==args.source_commit,'diagnostic commit changed')
 binding.assert_committed_sources(root,current,args.source_commit)
 binding.require(binding.digest(current)==args.source_sha,'diagnostic source hash changed')
 binding.require(binding.digest(value['inputs'])==value['input_sha256'],'historical input inventory changed')
 for spec in value['inputs'].values():binding.require(binding.pin(binding.inside(root,spec['path']))=={k:spec[k] for k in ('sha256','size_bytes')},'historical input changed')
 binding.verify_export_chain(root,value)
 binding.require(binding.pin(args.capture)['sha256']==args.capture_sha,'capture bytes changed')
 return value


def worker(args):
 from .worker import Fence
 sys.meta_path.insert(0,Fence('replay'))
 value=inputs(args)
 from . import domain
 from validation.family5.checker import wire_equal
 from validation.real5_v2.shared_replay import verify_coalesced_trace
 observer=Observer();before=time.monotonic();payload=binding.load(args.capture);decode=time.monotonic()-before
 binding.require(payload['schema']=='hiroute-recorded-real-capture-v1' and payload['source_plan_sha256']==args.plan_sha,'capture source plan changed')
 for key in ('source_sha256','input_sha256','query_sha256'):binding.require(payload[key]==value[key],'capture context changed')
 binding.require(wire_equal(payload['variant'],domain.variant(value)) and wire_equal(payload['query'],value['query']),'capture query changed')
 trusted=domain.trusted_case(value,binding.ROOT)
 result=None;error=None
 try:
  result=observer.run(lambda:verify_coalesced_trace(payload['trace'],payload['bundle'],trusted),MAX_POST_DECODE_SECONDS)
 except DiagnosticStop as exc:error=dict(type=type(exc).__name__,message=str(exc))
 except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc)[:1000])
 report=dict(schema='hiroute-replay-diagnostic-v1',acceptance=False,structural_verified=False,suffix_optimizer_calls=0,
  solver_calls=0,post_decode_budget_seconds=MAX_POST_DECODE_SECONDS,plan_sha256=args.plan_sha,
  capture_sha256=args.capture_sha,diagnostic_source_sha256=args.source_sha,diagnostic_source_commit=args.source_commit,
  decode_seconds=decode,checker_returned=result is not None,error=error,observations=observer.snapshot(),
  population=dict(nodes=len(payload['bundle']['nodes']),batches=len(payload['bundle']['batches']),events=len(payload['trace']['events']),callbacks=len(payload['callback_requests'])),
  callback_checks_started=False)
 raw=binding.canonical(report)+b'\n';binding.require(len(raw)<=MAX_REPORT_BYTES,'diagnostic report exceeded fixed bound')
 with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES']),profile_name=REPLAY.name) as writer:
  writer.write('diagnostic.json',[raw]);writer.finalize()
 return 0


def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true')
 for name in ('plan','capture'):p.add_argument('--'+name,type=Path,required=True);p.add_argument('--'+name+'-sha',required=True)
 p.add_argument('--source-commit',required=True);p.add_argument('--source-sha',required=True)
 p.add_argument('--attempt-dir',type=Path);p.add_argument('--cpu',type=int);args=p.parse_args()
 if args.worker:
  try:return worker(args)
  except BaseException as exc:worker_failure(type(exc).__name__,str(exc)[:4096],'diagnostic');return 1
 binding.require(args.attempt_dir is not None and args.cpu is not None,'fresh attempt and explicit CPU required')
 soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 binding.require(hard==resource.RLIM_INFINITY or hard>=REPLAY.child_as_bytes,'inherited AS ceiling too small')
 resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 value=inputs(args)
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.diagnose','--worker',
  '--plan',str(args.plan.resolve()),'--plan-sha',args.plan_sha,'--capture',str(args.capture.resolve()),'--capture-sha',args.capture_sha,
  '--source-commit',args.source_commit,'--source-sha',args.source_sha]
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=REPLAY,cpu=args.cpu,
  context=PlanContext(args.plan_sha,args.source_sha,binding.digest(dict(input_sha256=value['input_sha256'],capture_sha256=args.capture_sha)),REPLAY.name),
  entry_monotonic=float(ENTRY),deadline_monotonic=float(ENTRY+TOTAL_SECONDS))
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
