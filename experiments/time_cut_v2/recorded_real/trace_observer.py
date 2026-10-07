"""Bounded, opt-in observation of ordered replay; never an acceptance shortcut."""
from contextlib import ExitStack
from pathlib import Path
import math,resource,signal,time,weakref
from unittest.mock import patch
from . import plan as binding

TRACE_SECONDS=180
TOTAL_SECONDS=480
class TraceObservationEnd(BaseException):pass

class TraceObserver:
 def __init__(self,*,seconds=TRACE_SECONDS,stop_after=True,on_start=lambda:None):
  binding.require(type(seconds) in (int,float) and math.isfinite(seconds) and 0<seconds<=TRACE_SECONDS,'trace observation budget')
  self.seconds=seconds;self.stop_after=stop_after;self.on_start=on_start
  self.calls={};self.active=[];self.samples=[];self.selections=[];self.replay_ref=None
  self.started=None;self.ended=None;self.returned=False;self.terminal_snapshot=None;self.handler=None;self.run_started=None
 def location(self):
  obj=self.replay_ref() if self.replay_ref else None
  if obj is None:return self.terminal_snapshot
  result={name:getattr(obj,name) for name in ('cursor','batch_cursor','invocation_id','coalescing_id','group_id')
   if type(getattr(obj,name,None)) is int}
  result.update(queries=len(obj.node_queries),empty_queries=len(obj.empty_queries),ancestry_cache_entries=len(obj.ancestries))
  if obj.batch_cursor<len(obj.data['batch_ids']):result['next_batch_sha256']=obj.data['batch_ids'][obj.batch_cursor]
  return result
 def wrap(self,name,fn,*,method=False):
  def call(*args,**kwargs):
   label=name
   if name=='selection':label+='_'+str(args[2])
   row=self.calls.setdefault(label,dict(entered=0,completed=0,wall_seconds=0.,cpu_seconds=0.,max_items=0))
   row['entered']+=1;pos=1 if method else 0
   if len(args)>pos and isinstance(args[pos],(list,tuple,dict)):row['max_items']=max(row['max_items'],len(args[pos]))
   if name=='selection' and len(self.selections)<64:
    self.selections.append(dict(mode=args[2],parents=len(args[1]),location=self.location()))
   if name=='ancestry':
    row['cache_hits']=row.get('cache_hits',0)+int(tuple(args[1]) in args[0].ancestries)
   if name=='node_hash' and args and type(args[0]) is dict and type(args[0].get('parents')) is list:
    row['max_parent_items']=max(row.get('max_parent_items',0),len(args[0]['parents']))
   if name=='ancestry_hash' and args and type(args[0]) is dict and type(args[0].get('nodes')) is dict:
    row['max_ancestry_nodes']=max(row.get('max_ancestry_nodes',0),len(args[0]['nodes']))
   wall,cpu=time.monotonic(),time.process_time();self.active.append(label)
   try:
    result=fn(*args,**kwargs);row['completed']+=1
    if name=='dispatch_cells':
     row['total_cells']=row.get('total_cells',0)+len(result);row['max_cells']=max(row.get('max_cells',0),len(result))
    return result
   finally:
    row['wall_seconds']+=time.monotonic()-wall;row['cpu_seconds']+=time.process_time()-cpu;self.active.pop()
  return call
 def sample(self,signum,frame):
  stack=[]
  while frame is not None and len(stack)<24:
   local=frame.f_locals;progress={}
   if frame.f_code.co_name=='selection':
    for key in ('parents','ps','eligible','retained','chosen'):
     if type(local.get(key)) is list:progress[key+'_items']=len(local[key])
    if type(local.get('i')) is int:progress['piece_index']=local['i']
    if local.get('mode') in ('union','reduction'):progress['mode']=local['mode']
   stack.append(dict(file=Path(frame.f_code.co_filename).name,function=frame.f_code.co_name,line=frame.f_lineno,progress=progress))
   frame=frame.f_back
  now=time.monotonic()
  if len(self.samples)<TRACE_SECONDS+2:
   self.samples.append(dict(elapsed_seconds=now-self.started,active=list(self.active),location=self.location(),stack=stack,
    cpu_seconds=time.process_time(),kernel_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024))
  if now>=self.started+self.seconds:raise TraceObservationEnd('ordered trace observation window ended')
 def start(self):
  binding.require(self.started is None,'post-family observation entered twice')
  binding.require(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'existing alarm cannot be replaced')
  self.on_start();self.started=time.monotonic();self.handler=signal.getsignal(signal.SIGALRM)
  signal.signal(signal.SIGALRM,self.sample);signal.setitimer(signal.ITIMER_REAL,min(1.,self.seconds),1.)
 def close(self):
  if self.handler is not None:
   signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,self.handler);self.handler=None
  if self.started is not None and self.ended is None:self.ended=time.monotonic()
 def run_wrapper(self,fn):
  def run(obj,*args,**kwargs):
   binding.require(self.run_started is None,'ordered trace entered twice')
   self.replay_ref=weakref.ref(obj)
   if self.started is None:self.start()
   self.run_started=time.monotonic()
   try:
    result=fn(obj,*args,**kwargs);self.returned=True
    if self.stop_after:raise TraceObservationEnd('ordered trace returned; later phases intentionally not profiled')
    return result
   finally:
    self.terminal_snapshot=self.location();self.close()
  return run
 def hooks(self):
  from validation.trace5 import checker,coalesced
  from validation.real5_v2 import family,trace,shared_replay
  stack=ExitStack();stack.callback(self.close)
  targets=[(family,'verify_physical_states','physical_phase',False),(checker._Replay,'__init__','trace_setup',True),(coalesced.CoalescedReplay,'__init__','coalesced_setup',True),
   (checker._Replay,'selection','selection',True),(checker,'_dispatch_cells','dispatch_cells',False),
   (checker._Replay,'node','node',True),(checker,'digest','node_hash',False),
   (checker._Replay,'candidate','candidate',True),(checker._Replay,'expand','region_expansion',True),
   (coalesced.CoalescedReplay,'compact','compact',True),
   (trace.RealPhysicsReplayMixin,'bound','bound',True),(trace.RealPhysicsReplayMixin,'freeze_query','query',True),
   (shared_replay.RealCoalescedReplay,'ancestry','ancestry',True),(shared_replay,'stream_digest','ancestry_hash',False)]
  for obj,name,label,method in targets:stack.enter_context(patch.object(obj,name,self.wrap(label,getattr(obj,name),method=method)))
  stack.enter_context(patch.object(trace.RealPhysicsReplayMixin,'run',self.run_wrapper(trace.RealPhysicsReplayMixin.run)))
  return stack
 def snapshot(self):
  return dict(post_family_window_started=self.started is not None,trace_started=self.run_started is not None,
   trace_returned=self.returned,window_seconds=self.seconds,
   setup_seconds=None if self.run_started is None else self.run_started-self.started,
   elapsed_seconds=None if self.started is None else (self.ended or time.monotonic())-self.started,
   calls=self.calls,samples=self.samples,selection_entries=self.selections,final_location=self.location(),
   scope='observational counters and sampled stacks; inclusive timings overlap; no per-pair hooks',
   retained_graph_reference='weak; counters and samples contain only bounded scalar metadata')
