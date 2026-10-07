"""Tiny full-word/band identity oracle for the count-only logical model plan."""
from copy import deepcopy
import unittest,json
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real.logical_models import count_logical_models
from experiments.time_cut_v2.recorded_real import domain,plan
from tests.test_recovered_real_coalesced import capture
from tests.test_recovered_real_family import prepare
from validation.real5_v2.shared_replay_cached import verify_coalesced_trace
from validation.real5_v2.suffix_context import RealSuffixQueries
from validation.family5.checker import _plain
from validation.capture5.containers import stream_digest

class LogicalModels(unittest.TestCase):
 def inputs(self,row):
  data=capture(row,True);trusted=prepare(row);checked=verify_coalesced_trace(data['trace'],data['bundle'],trusted)
  summary=_plain(checked.summary)
  index=dict(schema='hiroute-recorded-query-index-v1',real_input=trusted.source_snapshot(),
   **{k:summary[k] for k in ('bundle_sha256','trace_sha256','query_freeze_sha256','case_sha256')},
   derived_fields=sorted(domain.DERIVED),exact_queries=len(checked.queries),empty_action_queries=len(checked.empty_action_queries),
   empty_action_sha256=stream_digest(checked.empty_action_queries),queries=[_plain(q) for q in domain.thin_queries(checked,lambda:None)])
  return index,trusted,summary,checked
 def rows(self):return json.loads((plan.ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
 def test_every_explicit_word_band_identity_and_occurrence_is_preserved(self):
  rows=self.rows();multiband=deepcopy(rows[1]);multiband['query']['charging_segments']=[[0,2,1,0],[2,5,2,-2]];rows.append(multiband)
  for row in rows:
   index,trusted,summary,checked=self.inputs(row);ctx=RealSuffixQueries(checked,trusted)
   keys=set();bindings=[]
   for q in index['queries']:
    models=list(ctx.models(q['query_seq'],max_models=1000,independent=True))
    raw=[plan.canonical([m['family_bundle_sha256'],m['family_id'],m['word'],m['arrival_bands']]) for m in models]
    keys.update(raw);bindings.append(len(raw))
   # The real implementation does not enumerate words or build either matrix.
   with patch('validation.suffix5.independent_convex_model.build_models',side_effect=RuntimeError('no matrices')),\
    patch('validation.suffix5.independent_convex_model.enumerate_words',side_effect=RuntimeError('no words')):
    result=count_logical_models(index,trusted,summary)
   logical=result['logical_model_plan']
   self.assertEqual(logical.get('unique_logical_model_slots',0),len(keys))
   self.assertEqual(logical['original_occurrence_model_slots'],sum(bindings))
   self.assertEqual([b['model_slots'] for b in logical['occurrence_bindings']],bindings)
   for row,b in zip(index['queries'],logical['occurrence_bindings']):
    self.assertEqual([logical['groups'][i]['family_id'] for i in b['family_groups']],row['family_ids'])
    self.assertEqual(b['first_actions'],row['actions']);self.assertEqual(b['thin_occurrence_sha256'],plan.digest(row))
   self.assertFalse(logical['lp_task_deduplication_measured']);self.assertFalse(logical['numerical_acceptance'])
 def test_equal_scalar_context_does_not_merge_foreign_family_identity(self):
  index,trusted,summary,_=self.inputs(self.rows()[0]);row=index['queries'][0]
  old=count_logical_models(index,trusted,summary)['logical_model_plan']
  repeated=deepcopy(row);repeated['query_seq']=max(q['query_seq'] for q in index['queries'])+1
  repeated['family_ids']=['f'*64];index['queries'].append(repeated);index['exact_queries']+=1;summary['exact_node_queries']+=1
  new=count_logical_models(index,trusted,summary)['logical_model_plan']
  # This direct metadata fixture establishes grouping behavior, not a forged
  # structural acceptance; the guarded runner authenticates the index first.
  self.assertEqual(new['unique_families'],old['unique_families']+1)
  self.assertGreater(new['unique_logical_model_slots'],old['unique_logical_model_slots'])
 def test_duplicate_occurrences_keep_multiplicity_and_conflicting_context_rejects(self):
  index,trusted,summary,_=self.inputs(self.rows()[0]);old=count_logical_models(index,trusted,summary)['logical_model_plan']
  repeated=deepcopy(index['queries'][0]);repeated['query_seq']=max(q['query_seq'] for q in index['queries'])+1
  index['queries'].append(repeated);index['exact_queries']+=1;summary['exact_node_queries']+=1
  new=count_logical_models(index,trusted,summary)['logical_model_plan']
  self.assertEqual(new['unique_logical_model_slots'],old['unique_logical_model_slots'])
  self.assertGreater(new['original_occurrence_model_slots'],old['original_occurrence_model_slots'])
  repeated['rho']='999'
  with self.assertRaisesRegex(ValueError,'conflicting occurrence context'):count_logical_models(index,trusted,summary)
if __name__=='__main__':unittest.main()
