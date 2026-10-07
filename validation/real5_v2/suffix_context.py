"""Source-bound real suffix occurrences and a finite census without LP calls.

A query index alone never constructs a CheckedTrace. This adapter accepts the
actual independently checked object and separately pinned immutable real case.
"""
from functools import lru_cache
from types import MappingProxyType
import hashlib
from validation.family5.checker import require,_plain,wire_equal
from validation.trace5 import CheckedTrace
from validation.capture5.query_dag_digest import QueryDagEncoder
from .input import TrustedRealCase


def count_language(trusted,state,first_actions):
 """Exact model-slot counts: reachable band products plus graph exclusions."""
 require(type(trusted) is TrustedRealCase,'trusted immutable real case required')
 from validation.suffix5.independent_convex_model import validate_curve
 ph=trusted.physics;validate_curve(ph)
 require(type(state) in (list,tuple) and len(state)==3 and type(state[0]) is str and
  type(state[1]) is int and state[1] in (0,1) and type(state[2]) is int and 0<=state[2]<ph.bound,
  'invalid suffix census state')
 anchor,remaining,depth=state
 require(anchor!=ph.destination and (anchor,anchor) in ph.legs,'invalid original physical prefix anchor')
 require(type(first_actions) in (list,tuple),'first actions must be an ordered array')
 def normalize(action,r):
  require(type(action) in (list,tuple) and len(action)==2 and all(type(x) is str for x in action),'suffix action shape')
  site,effect=action
  require(site in ph.sites and effect in ph.sites[site] and effect in ('C','S','CS') and
   ph.anchors[site]!=ph.destination,'unavailable suffix action')
  require(effect=='C' or r==1 and ph.schedule is not None,'invalid suffix service state')
  require(effect=='S' or bool(ph.curve),'charging suffix lacks curve')
  return site,effect
 first=tuple(normalize(a,remaining) for a in first_actions)
 require(len(first)==len(set(first)),'duplicate mandatory first action')
 @lru_cache(None)
 def continuations(source,r,slots):
  total=int(r==0);reachable=int(r==0 and (source,ph.destination) in ph.legs);weighted=reachable
  if slots:
   actions=sorted((s,e) for s,effects in ph.sites.items() for e in set(effects)
    if ph.anchors[s]!=ph.destination and (e=='C' or r==1))
   for action in actions:
    s,e=normalize(action,r);target=ph.anchors[s];nr=r if e=='C' else 0
    child=continuations(target,nr,slots-1);total+=child[0]
    if (source,target) in ph.legs:
     reachable+=child[1];weighted+=(1 if e=='S' else len(ph.curve))*child[2]
  return total,reachable,weighted
 total=reachable=weighted=0
 for site,effect in first:
  target=ph.anchors[site];r=remaining if effect=='C' else 0
  child=continuations(target,r,ph.bound-depth-1);total+=child[0]
  if (anchor,target) in ph.legs:
   reachable+=child[1];weighted+=(1 if effect=='S' else len(ph.curve))*child[2]
 excluded=total-reachable
 return dict(legal_words_per_family=total,reachable_words_per_family=reachable,
  graph_exclusion_models_per_family=excluded,reachable_band_models_per_family=weighted,
  models_per_family=weighted+excluded,dp_states=continuations.cache_info().currsize)


class RealSuffixQueries:
 def __init__(self,checked,trusted):
  require(type(checked) is CheckedTrace and type(trusted) is TrustedRealCase,'original checked trace and trusted case required')
  sources=trusted.source_snapshot();summary=_plain(checked.summary);bundle=checked.bundle
  require(summary.get('verified') is True and summary.get('schema')=='family5-real-coalesced-hier-trace-check-v2','complete real coalesced trace required')
  require(wire_equal(summary['real_input'],sources) and wire_equal(_plain(bundle.summary)['real_input_sources'],sources),'real source provenance mismatch')
  require(bundle._physics==trusted.physics and summary['case_sha256']==sources['case_sha256'] and
   summary['region_tree_sha256']==sources['region_tree_sha256'] and summary['bundle_sha256']==bundle.summary['bundle_sha256'],
   'real suffix case/bundle/tree mismatch')
  rows={};positions={}
  for position,row in enumerate(checked.queries):
   sequence=row['query_seq'];require(type(sequence) is int and sequence>=0 and sequence not in rows,'duplicate or invalid query occurrence')
   require(row['schema']=='family5-exact-real-node-query-v2' and
    row['case_sha256']==summary['case_sha256'] and row['source_bundle_sha256']==summary['bundle_sha256'] and
    row['region_tree_sha256']==summary['region_tree_sha256'] and wire_equal(_plain(row['real_input']),sources),
    'query occurrence source mismatch')
   require(type(row['family_ids']) in (list,tuple) and bool(row['family_ids']) and
    all(type(x) is str and x in bundle._pieces for x in row['family_ids']),'foreign or empty original query family')
   require(type(row['H_remaining']) is int and type(row['rho']) is str,'invalid query context types')
   for ident in row['family_ids']:
    p=bundle._pieces[ident]
    require(wire_equal(_plain(p.state),_plain(row['state'])) and str(p.rho)==row['rho'] and
     wire_equal(_plain(p.pi),_plain(row['pi'])) and row['H_remaining']==trusted.physics.bound-p.state[2],
     'query differs from inherited original family')
   rows[sequence]=row;positions[sequence]=position
  require(type(summary['exact_node_queries']) is int and len(rows)==summary['exact_node_queries'],'query population count mismatch')
  self.checked=checked;self.trusted=trusted;self.rows=MappingProxyType(rows);self.positions=MappingProxyType(positions)
  self._encoder=None;self._digests={}
 def query(self,sequence):
  require(type(sequence) is int and sequence in self.rows,'unknown original query occurrence')
  return self.rows[sequence]
 def query_digest(self,sequence):
  self.query(sequence)
  if sequence not in self._digests:
   if self._encoder is None:self._encoder=QueryDagEncoder(self.checked.queries)
   h=hashlib.sha256()
   for chunk in self._encoder.query(self._encoder.queries[self.positions[sequence]]):h.update(chunk)
   self._digests[sequence]=h.hexdigest()
  return self._digests[sequence]
 def census(self,sequence):
  row=self.query(sequence);counts=count_language(self.trusted,row['state'],row['actions']);families=len(row['family_ids'])
  return dict(query_seq=sequence,family_occurrences=families,**counts,model_slots=families*counts['models_per_family'],
   numerical_suffix_optimization=False,source_bundle_sha256=row['source_bundle_sha256'],ancestry_bundle_sha256=row['ancestry_bundle_sha256'])
 def models(self,sequence,*,max_models,independent=False):
  require(type(max_models) is int and max_models>=0 and type(independent) is bool,'explicit finite model budget required')
  row=self.query(sequence);count=self.census(sequence)['model_slots']
  require(count<=max_models,'model census exceeds declared budget; numerical work unresolved')
  if independent:
   from validation.suffix5.independent_convex_model import enumerate_words as words,build_models
  else:
   from validation.suffix5.convex_model import legal_words as words,build_models
  actions=_plain(row['actions']);emitted=0
  for ident in row['family_ids']:
   for word in words(self.checked.bundle,ident,actions):
    for model in build_models(self.checked.bundle,ident,_plain(word)):
     emitted+=1;yield model
  require(emitted==count,'finite language census disagrees with model enumeration')
