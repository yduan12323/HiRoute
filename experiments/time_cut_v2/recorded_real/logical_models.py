"""Exact logical-model reuse counts from an authenticated thin query index.

No model matrix or LP task is built. Distinct full identities are
(source bundle, original family ID, complete action word, arrival bands).
Words with different first actions are disjoint, so a family/action union and
the existing finite-language recurrence count those identities exactly.
"""
from collections import Counter
import json
from . import plan as binding
from .suffix_census import census
from validation.real5_v2.suffix_context import count_language

def count_logical_models(index,trusted,checked_summary,before=lambda:None):
 result=census(index,trusted,checked_summary,before)
 groups=[];by_family={};bindings=[]
 totals=Counter(dict(unique_logical_model_slots=0,unique_logical_words=0,unique_graph_exclusions=0,
  unique_reachable_band_models=0,unique_family_first_action_pairs=0));by_depth={}
 for position,row in enumerate(index['queries']):
  before();family_groups=[]
  context={k:row[k] for k in ('state','rho','pi','H_remaining')}
  context_bytes=binding.canonical(context)
  actions=tuple(map(tuple,row['actions']))
  for ident in row['family_ids']:
   if ident not in by_family:
    by_family[ident]=len(groups)
    groups.append(dict(family_id=ident,context=json.loads(context_bytes),context_bytes=context_bytes,
     first_actions=set(),family_occurrences=0))
   g=groups[by_family[ident]]
   # Equality is checked on the full bytes, not a newly introduced digest key.
   binding.require(g['context_bytes']==context_bytes,'one original family has conflicting occurrence context')
   g['first_actions'].update(actions);g['family_occurrences']+=1;family_groups.append(by_family[ident])
  counted=result['queries'][position]
  bindings.append(dict(query_index_position=position,query_seq=row['query_seq'],
   family_groups=family_groups,first_actions=[list(a) for a in actions],model_slots=counted['model_slots'],
   ancestry_bundle_sha256=row['ancestry_bundle_sha256'],thin_occurrence_sha256=counted['thin_occurrence_sha256']))
 for number,g in enumerate(groups):
  before();g.pop('context_bytes');actions=[list(a) for a in sorted(g['first_actions'])]
  g['first_actions']=actions;g['group_index']=number
  counts=count_language(trusted,g['context']['state'],actions);g['counts']=counts
  totals['unique_logical_model_slots']+=counts['models_per_family']
  totals['unique_logical_words']+=counts['legal_words_per_family']
  totals['unique_graph_exclusions']+=counts['graph_exclusion_models_per_family']
  totals['unique_reachable_band_models']+=counts['reachable_band_models_per_family']
  totals['unique_family_first_action_pairs']+=len(actions)
  depth=g['context']['state'][2];d=by_depth.setdefault(depth,Counter())
  d['unique_families']+=1;d['unique_words']+=counts['legal_words_per_family'];d['unique_models']+=counts['models_per_family']
 original=result['totals']['model_slots'];unique=totals['unique_logical_model_slots']
 binding.require(sum(len(b['family_groups']) for b in bindings)==result['totals']['family_occurrences'],
  'logical plan lost an original family occurrence')
 binding.require(sum(b['model_slots'] for b in bindings)==original and unique<=original,
  'logical count does not cover original model population')
 result['logical_model_plan']=dict(schema='hiroute-original-family-logical-model-count-v1',
  identity_fields=['source_bundle_sha256','family_id','complete_suffix_word','arrival_bands'],
  source_bundle_sha256=index['bundle_sha256'],unique_families=len(groups),**dict(totals),
  original_occurrence_model_slots=original,repeated_model_occurrences=original-unique,
  depths={str(k):dict(v) for k,v in sorted(by_depth.items())},groups=groups,occurrence_bindings=bindings,
  original_order='query index order, then original family order, first-action order, legal word order, arrival-band order',
  graph_exclusion_bands=None,
  compression='disjoint first-action languages per original family; occurrence bindings expand deterministically through original index',
  hash_deduplication_used=False,lp_task_deduplication_measured=False,matrices_constructed=0,solver_calls=0,
  numerical_acceptance=False,literal_G8_closed=False)
 return result
