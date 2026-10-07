"""Bounded immutable observations for a full cached replay; no acceptance logic."""
import os,time,weakref
from . import plan as binding

INTERVAL_SECONDS=60
MAX_RECORDS=48
MAX_RECORD_BYTES=16384
INDEX='progress/index.json'

class FullProgress:
 def __init__(self,writer,before=lambda:None):
  self.writer=writer;self.before=before;self.records=[];self.last=None;self.phase=None
  self.encoder_ref=None;self.digest_metrics=None;self.query_sha=None;self.counters={}
 def snapshot(self):
  encoder=self.encoder_ref() if self.encoder_ref else None
  return dict(schema='hiroute-full-replay-progress-v1',observational_only=True,
   stage=self.phase,monotonic=time.monotonic(),pid=os.getpid(),counters=dict(self.counters),
   query_digest=encoder.snapshot() if encoder is not None else self.digest_metrics,
   query_freeze_sha256=self.query_sha)
 def emit(self,force=False):
  now=time.monotonic()
  if not force and self.last is not None and now-self.last<INTERVAL_SECONDS:return
  self.before();binding.require(len(self.records)<MAX_RECORDS,'bounded progress record limit')
  raw=binding.canonical(self.snapshot())+b'\n';binding.require(len(raw)<=MAX_RECORD_BYTES,'bounded progress byte limit')
  name=f'progress/{len(self.records):06d}.json'
  self.records.append(self.writer.write(name,[raw]));self.last=time.monotonic()
 def stage(self,name,**fields):
  self.phase=name
  if 'encoder' in fields:self.encoder_ref=weakref.ref(fields['encoder'])
  if 'metrics' in fields:self.digest_metrics=dict(fields['metrics'])
  if 'query_sha256' in fields:self.query_sha=fields['query_sha256']
  self.counters={};self.emit(True)
 def tick(self):self.emit()
 def rows(self,phase,rows,total):
  self.phase=phase;self.counters=dict(completed=0,total=total);self.emit(True)
  for row in rows:
   self.counters['completed']+=1;self.tick();yield row
  self.phase=phase+'_complete';self.emit(True)
 def finish(self):
  raw=binding.canonical(dict(schema='hiroute-full-replay-progress-index-v1',observational_only=True,
   records=self.records,record_count=len(self.records),interval_seconds=INTERVAL_SECONDS,
   max_records=MAX_RECORDS,max_record_bytes=MAX_RECORD_BYTES))+b'\n'
  return self.writer.write(INDEX,[raw])

def expected_files(writer):
 records=sorted((r for r in writer.files if r['path'].startswith('progress/') and r['path']!=INDEX),key=lambda r:r['path'])
 binding.require(len(records)<=MAX_RECORDS and all(r['size_bytes']<=MAX_RECORD_BYTES for r in records),'progress inventory cap')
 binding.require([r['path'] for r in records]==[f'progress/{i:06d}.json' for i in range(len(records))],'progress sequence changed')
 index=binding.load(writer.root/INDEX)
 expected=dict(schema='hiroute-full-replay-progress-index-v1',observational_only=True,
  records=records,record_count=len(records),interval_seconds=INTERVAL_SECONDS,max_records=MAX_RECORDS,max_record_bytes=MAX_RECORD_BYTES)
 binding.require(binding.canonical(index)==binding.canonical(expected),'progress index changed')
 return {r['path'] for r in records}|{INDEX}
