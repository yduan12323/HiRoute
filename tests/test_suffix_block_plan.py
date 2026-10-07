"""Finite structural enumeration and partitions; no numerical optimizer."""
from copy import deepcopy
import unittest
from tests import test_real_model_preview as fixtures
from experiments.time_cut_v2.recorded_real import plan
from validation.real5_v2.family import verify_bundle
from validation.suffix5.block_plan import OrderedModelPopulation,block_ranges,choose_depth_blocks
from validation.suffix5 import convex_model,independent_convex_model

class BlockPlanTests(unittest.TestCase):
 def setUp(self):
  self.fx=fixtures.ModelPreview();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
  _,self.trusted,_,self.logical,path,_=self.fx.inputs()
  self.ctx=verify_bundle(plan.load(path)['bundle'],self.trusted)
 def test_every_descriptor_matches_both_existing_model_languages(self):
  population=OrderedModelPopulation(self.ctx,self.trusted,self.logical,block_size=7)
  rows=list(population.descriptors());expected=[]
  for group in self.logical['groups']:
   for action in group['first_actions']:
    words=independent_convex_model.enumerate_words(self.ctx,group['family_id'],[action])
    self.assertEqual(words,[list(map(list,w)) for w in convex_model.legal_words(self.ctx,group['family_id'],[action])])
    for word in words:
     independent=independent_convex_model.build_models(self.ctx,group['family_id'],word)
     candidate=convex_model.build_models(self.ctx,group['family_id'],word)
     self.assertEqual(candidate,independent)
     for model in independent:
      expected.append(dict(source_bundle_sha256=self.ctx.summary['bundle_sha256'],
       **{key:model[key] for key in ('family_id','word','arrival_bands')}))
  self.assertEqual([r['logical_identity'] for r in rows],expected)
  self.assertEqual([r['ordinal'] for r in rows],list(range(len(expected))))
  self.assertEqual(len(rows),self.logical['unique_logical_model_slots'])
  self.assertEqual(len({r['logical_identity_sha256'] for r in rows}),len(rows))
 def test_partition_sizes_ranges_and_partial_tail_preserve_all_models(self):
  original=list(OrderedModelPopulation(self.ctx,self.trusted,self.logical).descriptors())
  for size in (1,3,7,256):
   pop=OrderedModelPopulation(self.ctx,self.trusted,self.logical,block_size=size);rows=[]
   for b in pop.plan()['blocks']:
    part=list(pop.block(b['block_id']));self.assertEqual(len(part),b['model_count'])
    pop.check_block_descriptors(b['block_id'],part);rows.extend(part)
   self.assertEqual(rows,original)
  full=block_ranges(695712)
  self.assertEqual(len(full),2718);self.assertEqual(full[-1],dict(block_id=2717,start=695552,end=695712,model_count=160))
  self.assertEqual(sum(b['model_count'] for b in full),695712)
 def test_missing_duplicate_reordered_and_foreign_descriptors_reject(self):
  pop=OrderedModelPopulation(self.ctx,self.trusted,self.logical,block_size=7);rows=list(pop.block(0))
  bads=[rows[:-1],rows+[rows[0]],list(reversed(rows))]
  changed=deepcopy(rows);changed[0]['logical_identity']['family_id']='f'*64;bads.append(changed)
  changed=deepcopy(rows);changed[0]['ordinal']=True;bads.append(changed)
  for bad in bads:
   with self.assertRaises(ValueError):pop.check_block_descriptors(0,bad)
  for start,end in ((-1,0),(0,True),(0,len(list(pop.descriptors()))+1),(2,1)):
   with self.assertRaises(ValueError):list(pop.descriptors(start,end))
 def test_original_context_counts_and_caller_aliases_are_bound(self):
  for change in (lambda x:x['groups'][0]['context'].__setitem__('rho','999'),
   lambda x:x['groups'][0]['counts'].__setitem__('models_per_family',0),
   lambda x:x.__setitem__('source_bundle_sha256','f'*64)):
   bad=deepcopy(self.logical);change(bad)
   with self.assertRaises(ValueError):OrderedModelPopulation(self.ctx,self.trusted,bad)
  pop=OrderedModelPopulation(self.ctx,self.trusted,self.logical,block_size=7)
  snapshot=pop.plan();snapshot['segments'][0]['first_action'][0]='foreign'
  self.assertNotEqual(snapshot,pop.plan())
  iterator=pop.descriptors();first=next(iterator);first['logical_identity']['word'][0][0]='foreign'
  self.assertNotIn('foreign',repr(next(iterator)))
  self.assertNotIn('foreign',repr(list(pop.descriptors())))
 def test_pilot_block_choice_is_only_structural_and_distinct(self):
  segments=[dict(prefix_depth=d,start=a,end=b,model_count=b-a) for d,a,b in
   ((0,0,700),(1,700,900),(2,900,1300),(3,1300,1800))]
  doc=dict(total_models=1800,block_size=256,segments=segments,blocks=block_ranges(1800))
  selected=choose_depth_blocks(doc)
  self.assertEqual(selected['by_depth_block_ids'],[0,2,3,5]);self.assertEqual(selected['models'],1024)
  self.assertFalse(selected['selection_uses_outcomes'])
  doc['blocks'][0]['end']-=1
  with self.assertRaises(ValueError):choose_depth_blocks(doc)

if __name__=='__main__':unittest.main()
