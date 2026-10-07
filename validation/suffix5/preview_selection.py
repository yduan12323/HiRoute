"""Static, outcome-free small model selection from a verified logical plan."""
import json
from functools import lru_cache
from validation.family5.checker import require
from validation.real5_v2.input import TrustedRealCase
from .task_catalog import bounded_bytes

POLICY='first-two-families-per-depth-all-first-actions-lengths-extreme-bands-v1'
MAX_MODELS=256

def select_preview(logical,trusted):
 """Select before reading matrices, feasibility, objectives or certificates.

The caller authenticates/recomputes the logical plan first. This metadata
function never creates a CheckedBundle or establishes family validity.
"""
 require(type(trusted) is TrustedRealCase and type(logical) is dict,'trusted physical input and logical plan required')
 require(logical['schema']=='hiroute-original-family-logical-model-count-v1','logical plan schema')
 ph=trusted.physics;require(ph.bound<=4 and len(ph.sites)<=8,'small-preview physical population cap')
 require(type(logical['groups']) is list and type(logical['unique_families']) is int and
  logical['unique_families']==len(logical['groups']),'logical family count')
 all_actions=sorted((s,e) for s,effects in ph.sites.items() for e in effects if ph.anchors[s]!=ph.destination)
 def choices(r):return [a for a in all_actions if a[1]=='C' or r==1 and ph.schedule is not None]
 @lru_cache(None)
 def tail(r,length):
  if length==0:return () if r==0 else None
  for action in choices(r):
   rest=tail(r if action[1]=='C' else 0,length-1)
   if rest is not None:return (action,)+rest
  return None
 chosen={};seen=set();rows=[];families=[]
 for index,group in enumerate(logical['groups']):
  require(type(group['family_id']) is str and len(group['family_id'])==64 and
   all(c in '0123456789abcdef' for c in group['family_id']) and
   type(group['group_index']) is int and group['group_index']==index and group['family_id'] not in seen,
   'logical family order/identity changed');seen.add(group['family_id'])
  state=group['context']['state'];require(type(state) is list and len(state)==3 and type(state[0]) is str and type(state[2]) is int and
   type(state[1]) is int and state[1] in (0,1) and 0<=state[2]<ph.bound,'logical prefix state')
  depth=state[2]
  if chosen.get(depth,0)>=2:continue
  chosen[depth]=chosen.get(depth,0)+1;families.append(dict(group_index=index,family_id=group['family_id'],depth=depth))
  first=group['first_actions'];require(type(first) is list and all(type(a) is list and len(a)==2 and
   all(type(x) is str for x in a) for a in first) and len(first)==len({tuple(a) for a in first}),'first-action set')
  for action in first:
   require(type(action) is list and len(action)==2 and tuple(action) in choices(state[1]),'illegal mandatory first action')
   for length in range(1,ph.bound-depth+1):
    remaining=state[1] if action[1]=='C' else 0;rest=tail(remaining,length-1)
    if rest is None:continue
    word=[list(action)]+[list(a) for a in rest];source=state[0];reachable=True
    for target in [ph.anchors[s] for s,_ in word]+[ph.destination]:
     reachable=reachable and (source,target) in ph.legs;source=target
    if not reachable:bands=[None]
    else:
     low=[None if e=='S' else 0 for _,e in word]
     high=[None if e=='S' else len(ph.curve)-1 for _,e in word]
     bands=[low] if low==high else [low,high]
    for assignment in bands:
     require(len(rows)<MAX_MODELS,'small-preview model count cap')
     selection=dict(family_id=group['family_id'],word=word,arrival_bands=assignment)
     rows.append(dict(position=len(rows),group_index=index,prefix_depth=depth,word_length=length,
      selection=json.loads(bounded_bytes(selection,1024**2))))
 identities=[bounded_bytes(r['selection'],1024**2) for r in rows]
 require(len(identities)==len(set(identities)),'duplicate preview logical identity')
 return dict(schema='family5-static-model-preview-selection-v1',policy=POLICY,source_bundle_sha256=logical['source_bundle_sha256'],
  original_unique_models=logical['unique_logical_model_slots'],selected_families=families,selected_models=len(rows),models=rows,
  selection_uses_outcomes=False,full_population_coverage=False,matrices_constructed=0,solver_calls=0)
