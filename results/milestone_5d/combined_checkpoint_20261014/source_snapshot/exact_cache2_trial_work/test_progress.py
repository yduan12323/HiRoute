"""Tiny-only deterministic equivalence, durability, boundedness and errors."""
import sys, json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from fractions import Fraction as R
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'src'),str(ROOT.parent/'sparse_feasible_handoff_work'),str(ROOT.parent/'optimized_od06_phase2/runner')]
from timecut5.exact_progress import ExactSearchProgress, operation, event
from timecut5.bounded import _solve_problem
from timecut5.hierarchy import _solve_hierarchical_problem,build_regions
from timecut5.real_adapter import TableFreeRealProblem
from timecut5.road_provider import TableFreeRegionBoundProvider
from timecut5.feasible_incumbent import canonical,sha
from fixture_source import fixture,Router

class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.i=0
 def context(self,case='nonbest'):
  self.i+=1;q,c,_=fixture(self.root/f'fixture{self.i}',case)
  p=TableFreeRealProblem(q,c.sites,c.provider,origin_anchor=q['origin'],destination_anchor=q['destination'],site_catalog_sha256=c.site_catalog_sha256)
  root=build_regions(c.sites)
  b=TableFreeRegionBoundProvider(c.provider,c.sites,root,destination_anchor=c.destination_anchor,landmark_anchor=c.origin_anchor,site_catalog_sha256=c.site_catalog_sha256,router_factory=Router)
  o=ExactSearchProgress(self.root/f'observer{self.i}',query_sha256=sha(canonical(q)),domain_sha256=c.domain_sha256,source_sha256=c.provider.source_sha256,provider=c.provider,interval=.01,max_events=8)
  return p,b,root,o
 def run_case(self,case,method,enabled):
  p,b,root,o=self.context(case);order=[]
  advance=p.advance
  def observed(pieces,site,effect):
   order.append((tuple(x.pi for x in pieces),site,effect));return advance(pieces,site,effect)
  p.advance=observed
  hook=o if enabled else None
  if method=='flat':r=_solve_problem(p,singleton_bound=b.singleton_bound,progress_hook=hook)
  else:r=_solve_hierarchical_problem(p,True,root,bound_provider=b,progress_hook=hook).bounded
  return r.canonical(),order,o
 def test_keys_status_and_action_order(self):
  for case in ('nonbest','charge_required','equality'):
   for method in ('flat','hier'):
    with self.subTest(case=case,method=method):
     off,order,_=self.run_case(case,method,False);on,order2,o=self.run_case(case,method,True)
     self.assertEqual(off,on);self.assertEqual(order,order2)
     s=json.loads((o.path/'progress.json').read_text());self.assertEqual(s['status'],'returned');self.assertIsNone(s['io_error'])
     self.assertLessEqual(len(s['recent_events']),8);self.assertEqual(s['active_stack'],[])
     self.assertIsNone(s['global_open_lower_bound']);self.assertNotIn('gap',s)
     self.assertIn('attempted',s['counters']);self.assertIn('initial_piece',s['timings'])
 def test_exception_identity_and_first_slow_operation(self):
  for method in ('flat','hier'):
   p,b,root,o=self.context();failure=RuntimeError('sentinel');snapshots=[]
   @operation('slow_initial_fixture')
   def slow():
    time.sleep(.05);snapshots.append(json.loads((o.path/'progress.json').read_text()));raise failure
   p.initial_piece=slow
   try:
    if method=='flat':_solve_problem(p,progress_hook=o)
    else:_solve_hierarchical_problem(p,True,root,progress_hook=o)
   except RuntimeError as actual:self.assertIs(actual,failure)
   else:self.fail('expected error')
   self.assertEqual(snapshots[0]['active_stack'][-1]['stage'],'slow_initial_fixture')
   self.assertEqual(json.loads((o.path/'progress.json').read_text())['status'],'error')
 def test_io_error_does_not_change_solver(self):
  p,b,root,o=self.context()
  with patch('timecut5.exact_progress.os.replace',side_effect=OSError('fixture failure')):
   result=_solve_problem(p,progress_hook=o)
  self.assertEqual(result.result.status,'attained_optimum');self.assertEqual(o.state['io_error'],'OSError')
 def test_bounded_recent_journal_and_metrics(self):
  p,b,root,o=self.context()
  baseline=p.legs.provider.source_run_count if hasattr(p.legs,'provider') else 0
  with o:
   for i in range(2000):event('test_counter',attempted=i)
  self.assertEqual(len(o.history),8);self.assertLess((o.path/'progress.json').stat().st_size,20000)
  s=json.loads((o.path/'progress.json').read_text());self.assertTrue(all(v==0 for v in s['postentry_provider_deltas'].values()))
 def test_nested_boundaries_durable_without_heartbeat(self):
  p,b,root,o=self.context();o.interval=60
  seen=[]
  @operation('projection_build')
  def inner():
   seen.append(json.loads((o.path/'progress.json').read_text()))
  @operation('test_outer')
  def outer():
   inner();seen.append(json.loads((o.path/'progress.json').read_text()))
  with o:
   outer();seen.append(json.loads((o.path/'progress.json').read_text()))
  self.assertEqual(seen[0]['active_stack'][-1]['stage'],'projection_build')
  self.assertEqual(seen[1]['active_stack'][-1]['stage'],'test_outer')
  self.assertEqual(seen[1]['last_completed_operation']['stage'],'projection_build')
  self.assertEqual(seen[2]['active_stack'],[])
  self.assertEqual(seen[2]['last_completed_operation']['stage'],'test_outer')
 def test_production_factory_is_last_setup_and_single_entry(self):
  import production_boundary as boundary
  from test_sparse_feasible_execution import Tests as Helpers
  from timecut5.feasible_incumbent import recover_feasible_incumbent
  h=Helpers();h.setUp();self.addCleanup(h.doCleanups)
  for method in ('flat','hier'):
   admission,path=h.admission('nonbest');inputs=h.inputs('nonbest',path);c=inputs['catalog']
   recover_feasible_incumbent(**inputs)
   root=build_regions(c.sites,leaf_size=1)
   b=TableFreeRegionBoundProvider(c.provider,c.sites,root,destination_anchor=c.destination_anchor,landmark_anchor=c.origin_anchor,site_catalog_sha256=c.site_catalog_sha256,router_factory=Router)
   calls=[];observers=[];baseline=c.provider.source_run_count
   def factory(query,provider):
    calls.append('factory');self.assertEqual(query['H_ref'],admission.incumbent.max_depth);self.assertIs(provider,c.provider)
    o=ExactSearchProgress(self.root/f'production-{method}',query_sha256=sha(canonical(query)),domain_sha256=c.domain_sha256,source_sha256=provider.source_sha256,provider=provider)
    observers.append(o);return o
   result=boundary._execute_admitted(admission=admission,catalog=c,provider=c.provider,bound=b,root=root,method=method,initial='fixture',spec={'region_tree_sha256':'fixture'},stage=lambda name,**kw:calls.append(name),policy_check=lambda:None,progress_factory=factory)
   self.assertEqual(calls[:2],['factory','exact_engine_started']);self.assertEqual(len(observers),1)
   self.assertEqual(observers[0].state['entry_provider_metrics']['source_run_count'],baseline)
   self.assertEqual(result['status'],'attained_optimum')
 def test_actual_experimental_worker_factory_hashes_query_bytes(self):
  import ast,hashlib
  from types import SimpleNamespace
  q,c,_=fixture(self.root/'worker-fixture','nonbest');events=[]
  source=(ROOT/'experimental_exact_worker.py').read_text()
  node=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='progress_factory')
  spec=dict(source_sha256=c.provider.source_sha256,progress_interval_seconds=.25,progress_max_events=8,effective_exact_query_sha256=hashlib.sha256(canonical(q)).hexdigest())
  environment=dict(out=self.root/'worker-output',spec=spec,catalog=c,canonical=canonical,hashlib=hashlib,sys=SimpleNamespace(argv=['fixture','out','a'*64,'flat']),stage=lambda *args,**kw:events.append((args,kw)))
  wrapper=ast.FunctionDef(name='make_factory',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=[ast.Assign(targets=[ast.Name(id='phase_identity',ctx=ast.Store())],value=ast.Constant(value=None)),node,ast.Return(value=ast.Name(id='progress_factory',ctx=ast.Load()))],decorator_list=[])
  module=ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[]))
  exec(compile(module,str(ROOT/'experimental_exact_worker.py'),'exec'),environment)
  observer=environment['make_factory']()(q,c.provider)
  expected=hashlib.sha256(canonical(q)).hexdigest()
  self.assertEqual(observer.state['query_sha256'],expected)
  self.assertEqual(events[0][1]['effective_query_sha256'],expected)
  with observer:pass
 def test_thread_start_failure_is_noninterfering(self):
  p,b,root,o=self.context()
  with patch('timecut5.exact_progress.threading.Thread.start',side_effect=RuntimeError('thread start failed')):
   result=_solve_problem(p,progress_hook=o)
  self.assertEqual(result.result.status,'attained_optimum')
  self.assertEqual(o.state['heartbeat_error'],'RuntimeError')
  from timecut5.exact_progress import _active
  self.assertIsNone(_active.get())
 def test_snapshot_byte_cap(self):
  p,b,root,o=self.context()
  with o:
   for i in range(200):event('large_scalar',sample='x'*50000)
  data=(o.path/'progress.json').read_bytes()
  self.assertLessEqual(len(data),262144)
  self.assertEqual(json.loads(data)['counters']['sample']['unavailable'],'telemetry_scalar_character_limit')

if __name__=='__main__':unittest.main(verbosity=2)
