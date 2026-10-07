"""Independent finite-language enumeration for the declared preview policy."""
from copy import deepcopy
import json,unittest
from validation.suffix5.preview_selection import select_preview
from validation.suffix5 import independent_convex_model as independent
from tests.test_logical_suffix_models import LogicalModels
from experiments.time_cut_v2.recorded_real.logical_models import count_logical_models
from experiments.time_cut_v2.recorded_real.plan import ROOT

class PreviewSelection(unittest.TestCase):
 def fixture(self):
  row=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[1]
  row['query']['H_ref']=4;row['query']['charging_segments']=[[0,2,1,0],[2,4,2,-2],[4,5,3,-6]]
  index,trusted,summary,checked=LogicalModels().inputs(row)
  return trusted,checked,count_logical_models(index,trusted,summary)['logical_model_plan']
 def test_selection_matches_explicit_word_band_enumeration(self):
  trusted,checked,logical=self.fixture();actual=select_preview(logical,trusted);expected=[];seen_depth={}
  for group in logical['groups']:
   depth=group['context']['state'][2]
   if seen_depth.get(depth,0)==2:continue
   seen_depth[depth]=seen_depth.get(depth,0)+1
   for action in group['first_actions']:
    words=independent.enumerate_words(checked.bundle,group['family_id'],[action])
    for length in range(1,5-depth):
     same_length=[w for w in words if len(w)==length]
     if not same_length:continue
     word=min(same_length);models=independent.build_models(checked.bundle,group['family_id'],word)
     endpoints=[models[0]] if len(models)==1 else [models[0],models[-1]]
     expected.extend({k:m[k] for k in ('family_id','word','arrival_bands')} for m in endpoints)
  self.assertEqual([r['selection'] for r in actual['models']],expected)
  self.assertLessEqual(actual['selected_models'],256);self.assertFalse(actual['selection_uses_outcomes'])
 def test_fixed_c01_shape_gives_exactly_256_distinct_models(self):
  # Pure structural count fixture: no original C01 family claim and no matrices.
  trusted,_,logical=self.fixture();from dataclasses import replace
  from types import MappingProxyType
  sites={f'S{i}':('C',) for i in range(8)};anchors={s:trusted.physics.origin for s in sites}
  trusted=replace(trusted,physics=replace(trusted.physics,sites=MappingProxyType(sites),anchors=MappingProxyType(anchors)))
  groups=[]
  for depth in range(4):
   for j in range(1 if depth==0 else 3):
    n=len(groups);groups.append(dict(group_index=n,family_id=f'{n:064x}',context=dict(state=[trusted.physics.origin,0,depth]),
     first_actions=[[s,'C'] for s in sites]))
  logical=dict(logical,groups=groups,unique_families=len(groups));selected=select_preview(logical,trusted)
  self.assertEqual(selected['selected_models'],256);self.assertEqual(len(selected['selected_families']),7)
  self.assertEqual([sum(r['prefix_depth']==d for r in selected['models']) for d in range(4)],[64,96,64,32])
 def test_reordered_or_duplicate_groups_and_bad_actions_reject(self):
  trusted,_,logical=self.fixture()
  for mutate in (lambda x:x['groups'].reverse(),lambda x:x['groups'][0].update(group_index=True),
   lambda x:x['groups'][0].update(first_actions=[['missing','C']]),
   lambda x:x['groups'][0]['context']['state'].__setitem__(2,True)):
   bad=deepcopy(logical);mutate(bad)
   with self.assertRaises(ValueError):select_preview(bad,trusted)
if __name__=='__main__':unittest.main()
