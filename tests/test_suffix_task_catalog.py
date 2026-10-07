"""Tiny task-byte and model-binding checks only; no optimizer or real inputs."""
from copy import deepcopy
import json,unittest
from unittest.mock import patch
from validation.suffix5.task_catalog import TaskCatalog,compile_selected,bounded_bytes
from validation.real5_v2.suffix_context import RealSuffixQueries
from validation.real5_v2.shared_replay_cached import verify_coalesced_trace
from tests.test_recovered_real_family import prepare,repin
from tests.test_recovered_real_coalesced import capture
from experiments.time_cut_v2.recorded_real.plan import ROOT

class CatalogTests(unittest.TestCase):
 def catalog(self,**kw):return TaskCatalog(**dict(dict(max_entry_bytes=65536,max_total_bytes=1024**2,max_tasks=256),**kw))
 def task(self):return dict(c=['1','0'],A=[['-1','0'],['0','1']],b=['0','4'],equalities=[])
 def test_full_payload_equality_order_faces_and_ownership(self):
  c=self.catalog();task=self.task();key=c.intern(task);original=c.payloads[key]
  self.assertEqual(c.intern(deepcopy(task)),key)
  task['b'][0]='1';self.assertEqual(c.payloads[key],original);self.assertNotEqual(c.intern(task),key)
  changed=self.task();changed['A'].reverse();changed['b'].reverse();self.assertNotEqual(c.intern(changed),key)
  changed=self.task();changed['equalities']=[[['1','0'],'2']];self.assertNotEqual(c.intern(changed),key)
  with self.assertRaises(TypeError):c.payloads[key]=b'foreign'
 def test_collisions_and_caps_fail_without_merging_or_stale_accounting(self):
  raw=bounded_bytes(self.task(),65536);c=self.catalog(max_total_bytes=len(raw),max_tasks=1)
  key=c.intern(self.task());self.assertEqual(c.snapshot(),dict(unique_tasks=1,retained_bytes=len(raw)))
  changed=self.task();changed['b'][0]='1'
  with self.assertRaises(ValueError):c.intern(changed)
  with patch('validation.suffix5.task_catalog.hashlib.sha256',return_value=type('Collision',(),{'hexdigest':lambda self:key})()):
   with self.assertRaisesRegex(ValueError,'collision'):c.intern(changed)
  self.assertEqual(c.snapshot()['retained_bytes'],len(raw))
  with self.assertRaises(ValueError):self.catalog(max_entry_bytes=1).intern(self.task())
 def test_noncanonical_numbers_and_incomplete_task_payload_reject(self):
  for field,value in [('c',[True,'0']),('c',['1.0','0']),('b',['0']),('equalities',[[['0'],'1']])]:
   bad=self.task();bad[field]=value
   with self.assertRaises(ValueError):self.catalog().intern(bad)
  bad=self.task();bad['unknown']=0
  with self.assertRaises(ValueError):self.catalog().intern(bad)
 def test_tiny_real_models_keep_original_identity_and_match_both_builders(self):
  row=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[1]
  data=capture(row,True);trusted=prepare(row);checked=verify_coalesced_trace(data['trace'],data['bundle'],trusted)
  context=RealSuffixQueries(checked,trusted);selections=[];seen=set()
  for seq in context.rows:
   for model in context.models(seq,max_models=100):
    choice={k:model[k] for k in ('family_id','word','arrival_bands')};raw=bounded_bytes(choice,65536)
    if raw not in seen:selections.append(choice);seen.add(raw)
  catalog=self.catalog();result=compile_selected(checked.bundle,selections,max_models=100,
   max_model_bytes=65536,max_total_model_bytes=1024**2,catalog=catalog)
  self.assertEqual(result['selected_models'],len(selections));self.assertFalse(result['full_population_complete'])
  for choice,record in zip(selections,result['models']):
   model=json.loads(record['model_bytes']);self.assertEqual({k:model[k] for k in choice},choice)
   for key in record['base_task_ids'].values():self.assertIn(key,catalog.payloads)
  with self.assertRaises(ValueError):compile_selected(checked.bundle,selections,max_models=1,
   max_model_bytes=65536,max_total_model_bytes=1024**2,catalog=self.catalog())
  with self.assertRaises(ValueError):compile_selected(checked.bundle,selections[:1]*2,max_models=2,
   max_model_bytes=65536,max_total_model_bytes=1024**2,catalog=self.catalog())
 def test_same_tasks_keep_distinct_site_words_and_model_bytes(self):
  row=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
  row['query']['schedule']=None;row['table']['sites'][1]['effects']=['C'];repin(row)
  data=capture(row,True);checked=verify_coalesced_trace(data['trace'],data['bundle'],prepare(row))
  family=next(q['family_ids'][0] for q in checked.queries if q['state'][2]==0)
  selections=[dict(family_id=family,word=[[site,'C']],arrival_bands=[0]) for site in ('A','B')]
  result=compile_selected(checked.bundle,selections,max_models=2,max_model_bytes=65536,
   max_total_model_bytes=1024**2,catalog=self.catalog())
  a,b=result['models'];self.assertEqual(a['base_task_ids'],b['base_task_ids'])
  self.assertNotEqual(a['logical_identity'],b['logical_identity']);self.assertNotEqual(a['model_bytes'],b['model_bytes'])
  self.assertEqual(json.loads(a['model_bytes'])['pi'],[['A','C']]);self.assertEqual(json.loads(b['model_bytes'])['pi'],[['B','C']])
if __name__=='__main__':unittest.main()
