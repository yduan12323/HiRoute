"""Cold-admitted real suffix population, distinct from a live CheckedTrace.

Admission authenticates the completed structural replay and logical count via
their retained returns/manifests, then binds the original index to a genuine
fresh CheckedBundle. No flags or index rows construct a CheckedTrace.
"""
from . import plan as binding,suffix_census,model_preview
_ADMISSION=object()

class AdmittedSuffixPopulation:
 def __init__(self,ctx,trusted,index,logical,anchors,*,_token=None):
  binding.require(_token is _ADMISSION,'cold replay admission required')
  from validation.suffix5.block_plan import OrderedModelPopulation
  from validation.capture5.containers import freeze_shared
  from validation.family5.checker import _plain
  binding.require(ctx.summary['bundle_sha256']==index['bundle_sha256'] and
   ctx.summary['case_sha256']==index['case_sha256'],'fresh family differs from completed query source')
  self.population=OrderedModelPopulation(ctx,trusted,logical)
  self.ctx=ctx;self.trusted=trusted
  self._index=freeze_shared(index);self._logical=freeze_shared(logical);self._anchors=freeze_shared(anchors)
  self._segments={(s['group_index'],tuple(s['first_action'])):s for s in self.population._segments}
  self._rows={};self._bindings={}
  binding.require(len(index['queries'])==len(logical['occurrence_bindings']),'original occurrence binding count changed')
  total=0
  for position,(row,link) in enumerate(zip(index['queries'],logical['occurrence_bindings'])):
   sequence=row['query_seq'];binding.require(type(sequence) is int and sequence not in self._rows,'original query identity changed')
   binding.require(type(link['query_index_position']) is int and link['query_index_position']==position and
    type(link['query_seq']) is int and link['query_seq']==sequence,'query occurrence order changed')
   suffix_census.same(link['thin_occurrence_sha256'],binding.digest(row),'original query bytes changed')
   suffix_census.same(link['ancestry_bundle_sha256'],row['ancestry_bundle_sha256'],'original ancestry changed')
   suffix_census.same(link['first_actions'],row['actions'],'original query action order changed')
   binding.require(len(link['family_groups'])==len(row['family_ids']),'original family multiplicity changed')
   for ident,number in zip(row['family_ids'],link['family_groups']):
    binding.require(type(number) is int and 0<=number<len(logical['groups']) and
     logical['groups'][number]['family_id']==ident,'foreign family occurrence')
    p=ctx._pieces[ident]
    for key,value in (('state',_plain(p.state)),('rho',str(p.rho)),('pi',_plain(p.pi)),
     ('H_remaining',trusted.physics.bound-p.state[2])):
     suffix_census.same(row[key],value,'original query family context changed: '+key)
   self._rows[sequence]=self._index['queries'][position]
   self._bindings[sequence]=self._logical['occurrence_bindings'][position]
   total+=link['model_slots']
  binding.require(type(logical['original_occurrence_model_slots']) is int and
   total==logical['original_occurrence_model_slots'],'original full model occurrence count changed')

 def commitment(self):
  from validation.family5.checker import _plain
  value=dict(schema='hiroute-cold-admitted-suffix-population-v1',completed_replay=_plain(self._anchors),
   block_plan_sha256=self.population.plan_sha256,logical_plan_sha256=self.population._plan['logical_plan_sha256'],
   source_bundle_sha256=self._index['bundle_sha256'],case_sha256=self._index['case_sha256'],
   query_freeze_sha256=self._index['query_freeze_sha256'],queries=len(self._rows),
   original_model_occurrences=self._logical['original_occurrence_model_slots'],
   unique_logical_models=self.population._plan['total_models'],
   empty_action_queries=self._index['empty_action_queries'],empty_action_sha256=self._index['empty_action_sha256'],
    numerical_acceptance=False,literal_G8_closed=False)
  from .variant_scope import with_variant
  return with_variant(value,_plain(self._anchors))

 def query_ids(self):return tuple(self._rows)

 def query_projection(self,sequence):
  """Map global logical ranges into this original ordered query's regime IDs."""
  from validation.family5.checker import _plain
  binding.require(type(sequence) is int and sequence in self._rows,'foreign original query')
  row=self._rows[sequence];link=self._bindings[sequence];offset=0;ranges=[]
  for family_position,group in enumerate(link['family_groups']):
   for action_position,action in enumerate(link['first_actions']):
    key=(group,tuple(action));binding.require(key in self._segments,'missing original first-action language')
    segment=self._segments[key];count=segment['model_count']
    ranges.append(dict(family_position=family_position,action_position=action_position,
     segment_id=segment['segment_id'],logical_start=segment['start'],logical_end=segment['end'],
     query_start=offset,query_end=offset+count))
    offset+=count
  binding.require(offset==link['model_slots'],'query projection lost or duplicated model slots')
  return dict(query_seq=sequence,thin_occurrence_sha256=link['thin_occurrence_sha256'],
   ancestry_bundle_sha256=link['ancestry_bundle_sha256'],family_ids=_plain(row['family_ids']),
   actions=_plain(row['actions']),classification=row['classification'],recorded_bound=row['bound'],
   model_slots=offset,legal_completion_language_empty=offset==0,ranges=ranges)

def admit_population(root,args,ctx,deadline,before=lambda:None):
 index,trusted,summary,anchors=suffix_census.completed_inputs(root,args,deadline,before)
 logical=model_preview.logical_input(args,anchors,index,trusted,summary,deadline,before)
 result=AdmittedSuffixPopulation(ctx,trusted,index,logical,anchors,_token=_ADMISSION)
 before();return result
