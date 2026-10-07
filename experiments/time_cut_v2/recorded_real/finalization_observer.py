"""Observe only exact query/trace finalization after unchanged ordered traversal."""
import time,weakref
from .trace_observer import TraceObserver

class FinalizationObserver(TraceObserver):
 def __init__(self,*,on_start=lambda:None,seconds=180):
  super().__init__(seconds=seconds,stop_after=False,on_start=on_start)
  self.stage=None;self.history=[];self.encoder_ref=None;self.final_metrics=None;self.query_sha=None
 def metrics(self):
  value=self.encoder_ref() if self.encoder_ref else None
  return value.snapshot() if value is not None else self.final_metrics
 def observe(self,stage,**fields):
  if stage=='after_ordered_trace':
   self.replay_ref=weakref.ref(fields['replay']);self.terminal_snapshot=self.location();self.start()
  self.stage=stage;self.active[:]=[stage]
  if 'encoder' in fields:self.encoder_ref=weakref.ref(fields['encoder'])
  if 'metrics' in fields:self.final_metrics=dict(fields['metrics'])
  if 'query_sha256' in fields:self.query_sha=fields['query_sha256']
  if len(self.history)<16:self.history.append(dict(stage=stage,elapsed_seconds=time.monotonic()-self.started))
 def sample(self,signum,frame):
  try:super().sample(signum,frame)
  finally:
   if self.samples:self.samples[-1].update(finalization_stage=self.stage,query_digest=self.metrics())
 def snapshot(self):
  return dict(window_seconds=self.seconds,finalization_started=self.started is not None,
   finalization_returned=self.stage=='finalization_returned',stage=self.stage,stage_history=self.history,
   elapsed_seconds=None if self.started is None else (self.ended or time.monotonic())-self.started,
   location=self.location(),samples=self.samples,query_digest=self.metrics(),query_freeze_sha256=self.query_sha,
   scope='bounded finalization observation; expanded canonical bytes still all feed the legacy SHA-256')
