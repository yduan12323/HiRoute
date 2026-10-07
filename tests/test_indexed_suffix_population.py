"""Cold-admission boundary and exact original occurrence projections; no LP."""
from copy import deepcopy
from types import SimpleNamespace
import time,unittest
from unittest.mock import patch
from tests import test_real_model_preview as fixtures
from experiments.time_cut_v2.recorded_real import plan,indexed_population as admitted
from validation.real5_v2.family import verify_bundle
from validation.suffix5.independent_convex_model import enumerate_words,build_models

class IndexedPopulationTests(unittest.TestCase):
 def setUp(self):
  self.fx=fixtures.ModelPreview();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
  _,self.trusted,self.index,self.logical,path,_=self.fx.inputs()
  self.ctx=verify_bundle(plan.load(path)['bundle'],self.trusted)
  self.anchors={'capture_sha256':self.index['capture_sha256']}
 def admit(self,index=None,logical=None):
  with patch.object(admitted.suffix_census,'completed_inputs',return_value=(index or self.index,self.trusted,{},self.anchors)),\
   patch.object(admitted.model_preview,'logical_input',return_value=logical or self.logical):
   return admitted.admit_population(self.fx.root,SimpleNamespace(),self.ctx,time.monotonic()+10)
 def test_direct_index_flags_do_not_create_authority(self):
  with self.assertRaisesRegex(ValueError,'cold replay admission'):
   admitted.AdmittedSuffixPopulation(self.ctx,self.trusted,self.index,self.logical,self.anchors)
  with patch.object(admitted.suffix_census,'completed_inputs',side_effect=ValueError('cold proof failed')),self.assertRaises(ValueError):
   admitted.admit_population(self.fx.root,SimpleNamespace(),self.ctx,time.monotonic()+10)
 def test_every_original_query_order_projects_to_independent_model_language(self):
  pop=self.admit();total=0
  for row in self.index['queries']:
   projection=pop.query_projection(row['query_seq']);actual=[];expected=[]
   for span in projection['ranges']:
    self.assertEqual(len(actual),span['query_start'])
    actual.extend(x['logical_identity'] for x in pop.population.descriptors(span['logical_start'],span['logical_end']))
    self.assertEqual(len(actual),span['query_end'])
   for ident in row['family_ids']:
    for word in enumerate_words(self.ctx,ident,row['actions']):
     for model in build_models(self.ctx,ident,word):
      expected.append(dict(source_bundle_sha256=self.ctx.summary['bundle_sha256'],
       **{key:model[key] for key in ('family_id','word','arrival_bands')}))
   self.assertEqual(actual,expected);total+=len(actual)
  commitment=pop.commitment()
  self.assertEqual(total,commitment['original_model_occurrences'])
  self.assertEqual(commitment['queries'],len(self.index['queries']))
  self.assertFalse(commitment['numerical_acceptance']);self.assertFalse(commitment['literal_G8_closed'])
 def test_stale_or_reordered_query_bindings_fail_closed(self):
  for field in ('rho','ancestry_bundle_sha256'):
   bad=deepcopy(self.index);bad['queries'][0][field]='999'
   with self.subTest(field=field),self.assertRaises(ValueError):self.admit(index=bad)
  bad=deepcopy(self.logical);bad['occurrence_bindings'][0]['family_groups']=[999]
  with self.assertRaises(ValueError):self.admit(logical=bad)
  bad=deepcopy(self.index);bad['bundle_sha256']='f'*64
  with self.assertRaises(ValueError):self.admit(index=bad)
 def test_owned_index_and_returned_projection_do_not_alias_callers(self):
  pop=self.admit();seq=pop.query_ids()[0];first=pop.query_projection(seq)
  self.index['queries'][0]['rho']='999';self.logical['occurrence_bindings'][0]['model_slots']=-1
  first['actions'][0][0]='foreign';first['ranges'][0]['logical_start']=-1
  self.assertNotIn('foreign',repr(pop.query_projection(seq)))
  self.assertGreaterEqual(pop.query_projection(seq)['ranges'][0]['logical_start'],0)
  with self.assertRaises(ValueError):pop.query_projection(True)

if __name__=='__main__':unittest.main()
