"""Tiny configuration/semantic tests; no production native or exact invocation."""
import ast,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'src'),str(ROOT.parent/'sparse_feasible_handoff_work')]
from fixture_source import fixture
from timecut5.road_provider import TableFreeRoadSelectedLegProvider
class Tests(unittest.TestCase):
 def test_actual_worker_cache_configuration(self):
  tree=ast.parse((ROOT/'experimental_exact_worker.py').read_text())
  node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='cache_configuration');namespace={}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'worker_cache_helper','exec'),namespace)
  fn=namespace['cache_configuration'];expected=dict(source_cache_max_bytes=512*1024**2,source_cache_max_sources=2)
  self.assertEqual(fn(dict(cache=expected)),expected)
  for bad in [dict(expected,source_cache_max_sources=1),dict(expected,source_cache_max_bytes=256*1024**2),dict(expected,source_cache_max_sources=True)]:
   with self.assertRaises(ValueError):fn(dict(cache=bad))
  call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='TableFreeRoadSelectedLegProvider')
  self.assertTrue(any(k.arg is None and isinstance(k.value,ast.Call) and k.value.func.id=='cache_configuration' for k in call.keywords))
  self.assertFalse(any(k.arg in expected for k in call.keywords))
 def test_two_sources_preserve_selected_paths(self):
  with tempfile.TemporaryDirectory() as tmp:
   _,c,_=fixture(tmp);base=c.provider;providers=[]
   for count,limit in [(1,256*1024**2),(2,512*1024**2)]:
    p=TableFreeRoadSelectedLegProvider(base.graph,base.router,base.anchor_nodes,nodes_sha256=base.source_sha256['nodes'],edges_sha256=base.source_sha256['edges'],router_sha256=base.source_sha256['router'],anchor_catalog_sha256=base.source_sha256['anchors'],source_cache_max_sources=count,source_cache_max_bytes=limit)
    for pair in [('A','B'),('B','D'),('A','X'),('B','X')]:p.leg(*pair)
    providers.append(p)
   a,b=providers;self.assertEqual(a.legs,b.legs);self.assertEqual(a.edge_witnesses,b.edge_witnesses)
   self.assertEqual(a.source_run_count,4);self.assertEqual(b.source_run_count,2)
   self.assertEqual(a.source_cache_evictions,3);self.assertEqual(b.source_cache_evictions,0)
 def test_all_solver_and_observer_sources_identical(self):
  baseline=ROOT.parent/'exact_search_diagnostics_work/src/timecut5'
  for p in (ROOT/'src/timecut5').glob('*.py'):self.assertEqual(p.read_bytes(),(baseline/p.name).read_bytes(),p.name)
if __name__=='__main__':unittest.main(verbosity=2)
