"""Deterministic original-family model ordinals and finite restart blocks.

This is structural enumeration, not a numerical certificate or cold-index
admission. The caller must separately authenticate the completed query proof.
No CheckedTrace is constructed. Every mathematical context below comes from
the genuine fresh CheckedBundle supplied by that admitted caller.
"""
from bisect import bisect_right
from itertools import product,islice
from math import prod
from validation.family5 import CheckedBundle
from validation.family5.checker import require,digest,_plain
from validation.real5_v2.input import TrustedRealCase
from validation.real5_v2.suffix_context import count_language
from .independent_convex_model import enumerate_words,validate_curve,same,exact_json

POLICY='original-family-first-action-word-band-ordinals-v1'
DEFAULT_BLOCK_SIZE=256

def block_ranges(total,block_size=DEFAULT_BLOCK_SIZE):
 require(type(total) is int and total>=0 and type(block_size) is int and block_size>0,'exact finite block dimensions')
 return [dict(block_id=i,start=start,end=min(total,start+block_size),model_count=min(block_size,total-start))
  for i,start in enumerate(range(0,total,block_size))]

def choose_depth_blocks(plan):
 """First distinct block intersecting each depth, with no matrix/outcome input."""
 chosen=[]
 same(plan['blocks'],block_ranges(plan['total_models'],plan['block_size']),'canonical block ranges changed')
 depths=sorted({s['prefix_depth'] for s in plan['segments'] if s['model_count']})
 for depth in depths:
  match=next((b['block_id'] for b in plan['blocks'] if b['block_id'] not in chosen and
   any(s['prefix_depth']==depth and s['start']<b['end'] and b['start']<s['end'] for s in plan['segments'])),None)
  require(match is not None,'not enough distinct depth-covering blocks')
  chosen.append(match)
 return dict(policy='first-distinct-block-per-prefix-depth-v1',depths=depths,
  by_depth_block_ids=chosen,block_ids=sorted(chosen),
  models=sum(plan['blocks'][i]['model_count'] for i in chosen),selection_uses_outcomes=False)

class OrderedModelPopulation:
 """Source-bound descriptor enumeration; this class grants no query authority."""
 def __init__(self,ctx,trusted,logical,*,block_size=DEFAULT_BLOCK_SIZE):
  require(type(ctx) is CheckedBundle and type(trusted) is TrustedRealCase,'genuine checked family and physical source required')
  exact_json(logical)
  require(type(logical) is dict and logical['schema']=='hiroute-original-family-logical-model-count-v1','logical population schema')
  require(ctx.summary['verified'] is True and ctx.summary['bundle_sha256']==logical['source_bundle_sha256'],
   'original family bundle identity changed')
  same(_plain(ctx.summary['real_input_sources']),trusted.source_snapshot(),'physical sources changed')
  require(ctx._physics==trusted.physics,'physical model context changed');validate_curve(ctx._physics)
  groups=logical['groups'];require(type(groups) is list,'ordered family groups required')
  self.ctx=ctx;self.trusted=trusted;segments=[];seen=set();ordinal=0;words=0;exclusions=0
  for number,group in enumerate(groups):
   require(type(group['group_index']) is int and group['group_index']==number,'family group order changed')
   ident=group['family_id'];require(type(ident) is str and ident in ctx._pieces and ident not in seen,'duplicate or foreign family group');seen.add(ident)
   piece=ctx._pieces[ident]
   expected=dict(state=_plain(piece.state),rho=str(piece.rho),pi=_plain(piece.pi),H_remaining=trusted.physics.bound-piece.state[2])
   same(group['context'],expected,'original inherited family context changed')
   actions=group['first_actions'];require(type(actions) is list,'first actions required')
   require(actions==sorted(actions) and len({tuple(a) for a in actions})==len(actions),'canonical disjoint first-action order')
   same(group['counts'],count_language(trusted,piece.state,actions),'family language counts changed')
   for action in actions:
    counts=count_language(trusted,piece.state,[action]);size=counts['models_per_family']
    segments.append(dict(segment_id=len(segments),group_index=number,family_id=ident,first_action=list(action),
     prefix_depth=piece.state[2],start=ordinal,end=ordinal+size,model_count=size,
     legal_words=counts['legal_words_per_family'],graph_exclusions=counts['graph_exclusion_models_per_family']))
    ordinal+=size;words+=counts['legal_words_per_family'];exclusions+=counts['graph_exclusion_models_per_family']
  for name,actual in (('unique_families',len(groups)),('unique_family_first_action_pairs',len(segments)),
   ('unique_logical_model_slots',ordinal),('unique_logical_words',words),('unique_graph_exclusions',exclusions),
   ('unique_reachable_band_models',ordinal-exclusions)):
   require(type(logical[name]) is int and logical[name]==actual,'logical population count mismatch: '+name)
  self._segments=tuple(segments);self._starts=tuple(s['start'] for s in segments)
  self._plan=dict(schema='suffix5-original-model-block-plan-v1',policy=POLICY,
   source_bundle_sha256=ctx.summary['bundle_sha256'],case_sha256=ctx.summary['case_sha256'],
   real_input=trusted.source_snapshot(),logical_plan_sha256=digest(logical),block_size=block_size,
   total_models=ordinal,segments=segments,blocks=block_ranges(ordinal,block_size),
   numerical_acceptance=False,literal_G8_closed=False)
  # Own all published scalar metadata; caller mutations cannot alter the plan.
  from validation.capture5.containers import freeze_shared
  self._plan=freeze_shared(self._plan);self._segments=tuple(self._plan['segments'])
  self.plan_sha256=digest(_plain(self._plan))

 def plan(self):return _plain(self._plan)

 def _bands(self,ident,word):
  ph=self.ctx._physics;source=self.ctx._pieces[ident].state[0]
  for target in [ph.anchors[s] for s,_ in word]+[ph.destination]:
   if (source,target) not in ph.legs:return (None,)
   source=target
  choices=[range(len(ph.curve)) if effect!='S' else (None,) for _,effect in word]
  return product(*choices)

 def _segment_slice(self,segment,begin,end):
  ident=segment['family_id'];local=0;emitted=0
  words=enumerate_words(self.ctx,ident,[list(segment['first_action'])])
  for word in words:
   bands=self._bands(ident,word)
   count=1 if type(bands) is tuple else prod(len(self.ctx._physics.curve) if e!='S' else 1 for _,e in word)
   lo=max(0,begin-local);hi=min(count,end-local)
   if lo<hi:
    for offset,band in enumerate(islice(bands,lo,hi),lo):
     identity=dict(source_bundle_sha256=self.ctx.summary['bundle_sha256'],family_id=ident,
      word=[list(action) for action in word],arrival_bands=None if band is None else list(band))
     emitted+=1
     yield dict(ordinal=segment['start']+local+offset,segment_id=segment['segment_id'],
      prefix_depth=segment['prefix_depth'],logical_identity=identity,logical_identity_sha256=digest(identity))
   local+=count
  require(local==segment['model_count'] and emitted==end-begin,'enumerated word/band count differs from finite language')

 def descriptors(self,start=0,end=None):
  total=self._plan['total_models'];end=total if end is None else end
  require(type(start) is int and type(end) is int and 0<=start<=end<=total,'exact model ordinal range required')
  if start==end:return
  position=max(0,bisect_right(self._starts,start)-1);cursor=start
  for segment in self._segments[position:]:
   if segment['start']>=end:break
   lo=max(start,segment['start']);hi=min(end,segment['end'])
   if lo>=hi:continue
   for row in self._segment_slice(segment,lo-segment['start'],hi-segment['start']):
    require(row['ordinal']==cursor,'model ordinal gap or overlap');cursor+=1;yield row
  require(cursor==end,'missing model suffix range')

 def block(self,block_id):
  require(type(block_id) is int and 0<=block_id<len(self._plan['blocks']),'unknown canonical block ID')
  block=self._plan['blocks'][block_id]
  return self.descriptors(block['start'],block['end'])

 def check_block_descriptors(self,block_id,rows):
  expected=list(self.block(block_id));same(rows,expected,'block descriptor population/order/identity changed')
  return dict(plan_sha256=self.plan_sha256,block=_plain(self._plan['blocks'][block_id]),
   descriptors_sha256=digest(expected),numerical_acceptance=False)
