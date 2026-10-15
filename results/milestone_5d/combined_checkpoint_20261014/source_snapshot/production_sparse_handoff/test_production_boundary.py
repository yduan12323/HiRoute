"""Tiny exact helper regression and production guard tests; no real graph loading."""
import sys,unittest,resource
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
R=Path(__file__).resolve().parent;S=R.parent/'sparse_feasible_handoff_work'
sys.path[:0]=[str(R),str(S),str(S/'src')]
resource.setrlimit(resource.RLIMIT_CPU,(60,61))
import production_boundary as p
from test_sparse_feasible_execution import Tests as FixtureHelpers,Router,e
from timecut5.feasible_incumbent import recover_feasible_incumbent
from timecut5.hierarchy import build_regions
from timecut5.road_provider import TableFreeRegionBoundProvider
class Tests(unittest.TestCase):
 def setUp(self):
  self.h=FixtureHelpers();self.h.setUp();self.addCleanup(self.h.doCleanups)
 def context(self,case):
  a,path=self.h.admission(case);inputs=self.h.inputs(case,path);c=inputs['catalog']
  inc=recover_feasible_incumbent(**inputs);self.assertEqual(inc,a.incumbent)
  root=build_regions(c.sites,leaf_size=1)
  bound=TableFreeRegionBoundProvider(c.provider,c.sites,root,destination_anchor=c.destination_anchor,landmark_anchor=c.origin_anchor,site_catalog_sha256=c.site_catalog_sha256,router_factory=Router)
  return a,path,inputs,dict(admission=a,catalog=c,provider=c.provider,bound=bound,root=root,initial='unit-test-only',spec={'region_tree_sha256':'unit-test-only'},stage=lambda *a,**k:None,policy_check=lambda:None)
 def test_tiny_exact_helpers_match_prior_entry(self):
  for case in ['nonbest','charge_required','equality']:
   for method in ['flat','hier']:
    with self.subTest(case=case,method=method):
     a,path,inputs,kw=self.context(case)
     result=p._execute_admitted(method=method,**kw)
     old=self.h.solve(a,path,case,method)
     self.assertEqual(result['status'],old.bounded.result.status);self.assertEqual(result['key'],old.bounded.result.key)
     self.assertTrue(result['terminal_replayed'])
 def test_production_gate_rejects_fixture_before_recovery(self):
  path=self.h.saved('nonbest');inputs=self.h.inputs('nonbest',path)
  with patch.object(p,'recover_feasible_incumbent',side_effect=AssertionError('recovered fixture')):
   with self.assertRaisesRegex(ValueError,'explicitly frozen production'):
    p.run_production(inputs=inputs,spec={},native={},method='flat',router_factory=Router,stage=lambda *a,**k:None,save=lambda *a:None,closure_check=lambda:None)
 def test_production_gate_rejects_unknown_method(self):
  with self.assertRaisesRegex(ValueError,'Unknown method'):
   p.run_production(inputs={},spec={},native={},method='bad',router_factory=None,stage=None,save=None,closure_check=None)
 def test_impossible_terminal_rejected(self):
  a,path,inputs,kw=self.context('nonbest')
  fake=SimpleNamespace(result=SimpleNamespace(status='infeasible',witness=None))
  with patch.object(p,'_solve_problem',return_value=fake):
   with self.assertRaisesRegex(ValueError,'contradicts infeasible'):
    p._execute_admitted(method='flat',**kw)
if __name__=='__main__':unittest.main(verbosity=2)
