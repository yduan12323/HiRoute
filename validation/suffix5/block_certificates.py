"""Exact certificates for a predeclared finite set of model blocks.

Descriptor/language admission belongs to the cold indexed-population adapter.
This object never accepts a candidate flag as a certificate, never aggregates
unresolved models as exclusions, and retains only small result rows plus one
representative winning record per block. Full certificates must be streamed to
the caller's immutable evidence archive as each check returns.
"""
import json
from validation.family5 import CheckedBundle
from validation.family5.checker import digest,require
from .independent_convex_model import exact_json,same
from .convex_checker import check_regime
from .checker import aggregate_records
from .aggregate_stream import StreamAggregator

MAX_RECORD_BYTES=4*1024**2
EXCLUDED={'graph_unreachable','closed_infeasible','strict_infeasible'}

def _bytes(value):
 return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

class BlockCertificates:
 def __init__(self,ctx,blocks):
  require(type(ctx) is CheckedBundle,'genuine checked family bundle required')
  exact_json(blocks);require(type(blocks) is list and bool(blocks),'predeclared model blocks required')
  self.ctx=ctx;self._blocks={};self._expected={};self._entries={};self._best={}
  previous=-1
  for block in blocks:
   require(type(block) is dict and set(block)=={'range','descriptors'},'block declaration fields')
   span=block['range'];require(type(span) is dict and set(span)=={'block_id','start','end','model_count'},'canonical block range fields')
   require(all(type(span[k]) is int for k in span) and span['block_id']>=0 and
    previous<span['start']<span['end'] and span['end']-span['start']==span['model_count']<=256,'ordered finite block ranges')
   previous=span['end']-1;ident=span['block_id'];require(ident not in self._blocks,'duplicate canonical block ID')
   rows=block['descriptors'];require(type(rows) is list and len(rows)==span['model_count'],'block descriptor count')
   for ordinal,row in zip(range(span['start'],span['end']),rows):
    require(type(row) is dict and set(row)=={'ordinal','segment_id','prefix_depth','logical_identity','logical_identity_sha256'},'descriptor fields')
    require(type(row['ordinal']) is int and row['ordinal']==ordinal and type(row['segment_id']) is int and row['segment_id']>=0 and
     type(row['prefix_depth']) is int and row['prefix_depth']>=0,'descriptor ordinal/context')
    identity=row['logical_identity'];require(type(identity) is dict and
     set(identity)=={'source_bundle_sha256','family_id','word','arrival_bands'},'full logical model identity')
    require(identity['source_bundle_sha256']==ctx.summary['bundle_sha256'] and digest(identity)==row['logical_identity_sha256'],
     'descriptor family source/hash changed')
    require(identity['family_id'] in ctx._pieces and row['prefix_depth']==ctx._pieces[identity['family_id']].state[2],
     'descriptor inherited family depth changed')
    self._expected[ordinal]=(ident,_bytes(row))
   self._blocks[ident]=json.loads(_bytes(block))

 def descriptor(self,ordinal):
  require(type(ordinal) is int and ordinal in self._expected,'foreign model ordinal')
  return json.loads(self._expected[ordinal][1])

 def check(self,ordinal,record):
  descriptor=self.descriptor(ordinal);require(ordinal not in self._entries,'duplicate model disposition')
  exact_json(record);model=record['model']
  identity=dict(source_bundle_sha256=model['family_bundle_sha256'],**{k:model[k] for k in ('family_id','word','arrival_bands')})
  same(identity,descriptor['logical_identity'],'candidate differs from declared original model')
  outcome=check_regime(self.ctx,record,with_audit=True)
  result=outcome['result'];owned_result=_bytes(result);block=self._expected[ordinal][0]
  if result['status'] not in EXCLUDED:
   previous=self._best.get(block)
   choose=previous is None
   if previous is not None:
    old=json.loads(previous[1]);combined=aggregate_records([{'result':old['result']},{'result':result}])
    choose=result==combined and (old['result']!=combined or ordinal<previous[0])
   if choose:
    raw=_bytes(record);require(len(raw)<=MAX_RECORD_BYTES,'winning certificate record byte cap')
    self._best[block]=(ordinal,raw)
  # The disposition map is the sole population accounting authority. If a
  # caller's deadline interrupts publication, it must fail the outer attempt.
  self._entries[ordinal]=('verified',owned_result)
  return dict(model_ordinal=ordinal,block_id=block,logical_identity_sha256=descriptor['logical_identity_sha256'],
   model_sha256=digest(model),record_sha256=digest(record),result=json.loads(owned_result),
   checked_stage_count=len(record['stages']),independent_certificate_verified=True,
   physical_witness_verified=False,query_optimum_certified=False,literal_G8_closed=False)

 def unresolved(self,ordinal,reason):
  self.descriptor(ordinal);require(ordinal not in self._entries,'duplicate model disposition')
  require(type(reason) is str and 0<len(reason)<=4096,'bounded unresolved reason required')
  self._entries[ordinal]=('unresolved',reason)

 def summary(self,block_id):
  require(type(block_id) is int and block_id in self._blocks,'foreign block ID')
  declaration=self._blocks[block_id];span=declaration['range'];ordinals=range(span['start'],span['end'])
  missing=[i for i in ordinals if i not in self._entries]
  failed=[i for i in ordinals if i in self._entries and self._entries[i][0]=='unresolved']
  aggregate=None;segments=[]
  if not missing and not failed:
   folded=StreamAggregator(start=span['start']);current=None;part=None
   for row in declaration['descriptors']:
    ordinal=row['ordinal'];result=json.loads(self._entries[ordinal][1]);folded.add(ordinal,result)
    if current!=row['segment_id']:
     if part is not None:segments.append(dict(segment_id=current,aggregate=part.summary()))
     current=row['segment_id'];part=StreamAggregator(start=ordinal)
    part.add(ordinal,result)
   if part is not None:segments.append(dict(segment_id=current,aggregate=part.summary()))
   aggregate=folded.summary()
  return dict(schema='suffix5-checked-block-certificates-v1',range=dict(span),
   complete_certificates=not missing and not failed,verified_models=span['model_count']-len(missing)-len(failed),
   unresolved_ordinals=failed,unsubmitted_ordinals=missing,aggregate=aggregate,segment_summaries=segments,
   physical_witness_verified=False,query_optimum_certified=False,literal_G8_closed=False)

 def winner(self,block_id):
  summary=self.summary(block_id);require(summary['complete_certificates'],'incomplete block has no certified aggregate')
  best=self._best.get(block_id)
  if best is None:
   require(summary['aggregate']['result']['status']=='empty_restricted_family','missing block winning record')
   return None
  ordinal,raw=best;record=json.loads(raw)
  same(record['result'],summary['aggregate']['result'],'winning record differs from exact block aggregate')
  return dict(model_ordinal=ordinal,descriptor=self.descriptor(ordinal),record=record)
