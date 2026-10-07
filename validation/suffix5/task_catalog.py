"""Bounded, count-only catalog of complete ordered LP task bytes.

This constructs no certificates and grants no numerical acceptance. Model
selection and any real execution admission belong to a separately bound runner.
"""
import hashlib,threading
from types import MappingProxyType
from validation.capture5.containers import canonical_chunks
from validation.family5 import CheckedBundle
from validation.family5.checker import require
from . import convex_model as candidate,independent_convex_model as independent

def bounded_bytes(value,limit):
 require(type(limit) is int and limit>0,'positive canonical entry cap required')
 chunks=[];size=0
 for chunk in canonical_chunks(value):
  size+=len(chunk);require(size<=limit,'canonical payload exceeds preview cap');chunks.append(chunk)
 return b''.join(chunks)

def validate_task(task):
 independent.exact_json(task)
 require(type(task) is dict and set(task)=={'c','A','b','equalities'},'complete ordered LP task required')
 require(type(task['c']) is list and bool(task['c']),'LP objective vector required')
 n=len(task['c'])
 def vector(row):
  require(type(row) is list and len(row)==n,'LP vector dimension changed')
  for value in row:independent.rational(value)
 vector(task['c']);require(type(task['A']) is list and type(task['b']) is list and len(task['A'])==len(task['b']),'LP inequality dimensions')
 for row,value in zip(task['A'],task['b']):vector(row);independent.rational(value)
 require(type(task['equalities']) is list,'LP equality array required')
 for pair in task['equalities']:
  require(type(pair) is list and len(pair)==2,'LP equality pair required');vector(pair[0]);independent.rational(pair[1])

class TaskCatalog:
 """Single-owner immutable payload store; every digest hit compares full bytes.

Caps concern retained canonical bytes, not Python/transient heap. A surrounding
process guard is still mandatory for a real preview. No floating normalization,
row sorting or mathematical equivalence is substituted for exact wire equality.
"""
 def __init__(self,*,max_entry_bytes,max_total_bytes,max_tasks):
  require(all(type(v) is int and v>0 for v in (max_entry_bytes,max_total_bytes,max_tasks)),
   'explicit finite catalog caps required')
  self.max_entry_bytes=max_entry_bytes;self.max_total_bytes=max_total_bytes;self.max_tasks=max_tasks
  self._payloads={};self._lock=threading.Lock()
 @property
 def payloads(self):return MappingProxyType(self._payloads)
 def snapshot(self):return dict(unique_tasks=len(self._payloads),retained_bytes=sum(map(len,self._payloads.values())))
 def intern(self,task):
  require(self._lock.acquire(blocking=False),'concurrent or reentrant catalog call')
  try:
   validate_task(task);raw=bounded_bytes(task,self.max_entry_bytes);key=hashlib.sha256(raw).hexdigest()
   if key in self._payloads:
    require(self._payloads[key]==raw,'LP task digest collision; no reuse permitted');return key
   require(len(self._payloads)<self.max_tasks,'unique task count cap exhausted')
   require(sum(map(len,self._payloads.values()))+len(raw)<=self.max_total_bytes,'task catalog byte cap exhausted')
   # The dictionary is the accounting authority. An interrupted insertion has
   # no separate byte counter to become stale on reuse.
   self._payloads[key]=raw;return key
  finally:self._lock.release()

def compile_selected(ctx,selections,*,max_models,max_model_bytes,max_total_model_bytes,catalog):
 """Compare both existing model builders on an explicitly selected tiny set.

Only feasibility and unconstrained-primary tasks are available before solving.
Primary/secondary optimal-face tasks depend on preceding exact certificates and
are deliberately not counted here. The returned raw models preserve constants,
H, pi and original-family identities even when a base LP task is shared.
"""
 require(type(ctx) is CheckedBundle and type(catalog) is TaskCatalog,'genuine checked bundle and catalog required')
 require(type(selections) is list and type(max_models) is int and max_models>0 and len(selections)<=max_models,
  'explicit bounded preview selection required')
 require(all(type(v) is int and v>0 for v in (max_model_bytes,max_total_model_bytes)),'explicit model byte caps required')
 rows=[];model_bytes=0;seen=set()
 for position,selection in enumerate(selections):
  independent.exact_json(selection)
  require(type(selection) is dict and set(selection)=={'family_id','word','arrival_bands'},'full logical identity required')
  identity=bounded_bytes(dict(source_bundle_sha256=ctx.summary['bundle_sha256'],**selection),max_model_bytes)
  require(identity not in seen,'duplicate selected logical model');seen.add(identity)
  args=ctx,selection['family_id'],selection['word'],selection['arrival_bands']
  model=candidate.build_model(*args);reference=independent.build_model(*args)
  independent.same(model,reference,'independent preview model mismatch')
  raw=bounded_bytes(model,max_model_bytes);model_bytes+=len(raw)
  require(model_bytes<=max_total_model_bytes,'total preview model byte cap exhausted')
  tasks={}
  if model['exclusion'] is None:
   tasks['feasibility']=catalog.intern(independent.strict_task(reference))
   tasks['primary']=catalog.intern(independent.closed_task(reference,'J'))
  rows.append(dict(selection_position=position,logical_identity=identity,model_bytes=raw,
   model_sha256=hashlib.sha256(raw).hexdigest(),base_task_ids=tasks))
 return dict(schema='family5-explicit-model-task-preview-v1',models=rows,model_bytes=model_bytes,
  selected_models=len(rows),catalog=catalog.snapshot(),model_builders_equal=True,
  available_task_kinds=['feasibility','primary'],later_face_task_count='unknown_before_exact_results',
  full_population_complete=False,solver_calls=0,certificate_reuse_accepted=False,literal_G8_closed=False)
