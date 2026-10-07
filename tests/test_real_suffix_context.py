"""Tiny real occurrence/source/model census tests, without candidate LP calls."""
from dataclasses import replace
from copy import deepcopy
import json,unittest
from pathlib import Path
from unittest.mock import patch
from validation.real5_v2.suffix_context import RealSuffixQueries,count_language
from validation.real5_v2.shared_replay_cached import verify_coalesced_trace
from validation.trace5 import CheckedTrace
from validation.family5.checker import _plain,_freeze,digest
from tests.test_recovered_real_coalesced import capture
from tests.test_recovered_real_family import prepare
ROOT=Path(__file__).resolve().parents[1]

class RealSuffixContext(unittest.TestCase):
 def setUp(self):self.rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
 def checked(self,row):
  data=capture(row,True);trusted=prepare(row)
  return verify_coalesced_trace(data['trace'],data['bundle'],trusted),trusted
 def test_all_mock_occurrences_count_and_build_independently_without_export_all(self):
  total=0
  for row in self.rows:
   checked,trusted=self.checked(row)
   with patch.object(CheckedTrace,'export_queries',side_effect=RuntimeError('whole population expansion forbidden')):
    context=RealSuffixQueries(checked,trusted)
    for seq,q in context.rows.items():
     census=context.census(seq);a=list(context.models(seq,max_models=1000));b=list(context.models(seq,max_models=1000,independent=True))
     self.assertEqual(a,b);self.assertEqual(len(a),census['model_slots']);total+=len(a)
     self.assertEqual(context.query_digest(seq),digest(q))
     if a:
      with self.assertRaises(ValueError):list(context.models(seq,max_models=len(a)-1))
  self.assertGreater(total,0)
 def test_duplicate_foreign_or_repaired_occurrences_reject(self):
  checked,trusted=self.checked(self.rows[0]);original=[_plain(q) for q in checked.queries]
  for field,value in [('query_seq',True),('case_sha256','0'*64),('source_bundle_sha256','0'*64),
   ('region_tree_sha256','0'*64),('family_ids',['0'*64]),('family_ids',[]),('rho','999'),('H_remaining',True)]:
   rows=deepcopy(original);rows[0][field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):RealSuffixQueries(replace(checked,node_queries=_freeze(rows)),trusted)
  with self.assertRaises(ValueError):RealSuffixQueries(replace(checked,node_queries=checked.queries+checked.queries[:1]),trusted)
 def test_real_sources_and_exact_identity_are_mandatory(self):
  checked,trusted=self.checked(self.rows[0]);context=RealSuffixQueries(checked,trusted)
  with self.assertRaises(ValueError):context.query(True)
  with self.assertRaises(ValueError):context.query(10**9)
  source=trusted.source_snapshot();source['table_sha256']='0'*64
  with self.assertRaises(ValueError):RealSuffixQueries(checked,replace(trusted,_sources=_freeze(source)))
  with self.assertRaises(ValueError):RealSuffixQueries({'queries':[]},trusted)
 def test_site_multiplicity_identity_legs_and_graph_exclusion_counts(self):
  for row in self.rows:
   checked,trusted=self.checked(row);context=RealSuffixQueries(checked,trusted)
   for seq,q in context.rows.items():
    counts=context.census(seq);models=list(context.models(seq,max_models=1000,independent=True))
    excluded=sum(m['exclusion'] is not None for m in models)
    self.assertEqual(excluded,counts['family_occurrences']*counts['graph_exclusion_models_per_family'])
    self.assertEqual(len(models)-excluded,counts['family_occurrences']*counts['reachable_band_models_per_family'])
  trusted=self.checked(self.rows[0])[1]
  with self.assertRaises(ValueError):count_language(trusted,(trusted.physics.origin,0,True),[])
if __name__=='__main__':unittest.main()
