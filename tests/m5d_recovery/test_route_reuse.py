"""Tiny native fixtures only; no road dataset or OD experiment."""
import hashlib, importlib.util, json, resource, sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT.parents[1])]
import ctypes, subprocess
class ExactRouter:
 def __init__(self,graph,config,cache):
  self.graph=graph;source=ROOT/'fixtures/routing.cpp';binary=Path(cache)/'routing.so'
  subprocess.run([config['compiler'],*config['compiler_flags'],'-shared','-fPIC',str(source),'-o',str(binary)],check=True)
  self.provenance={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
  self.lib=ctypes.CDLL(str(binary));ints=np.ctypeslib.ndpointer(dtype=np.int64,flags='C_CONTIGUOUS');doubles=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS')
  self.lib.graph_create.argtypes=[ctypes.c_int64,ctypes.c_int64,ints,ints,doubles,doubles];self.lib.graph_create.restype=ctypes.c_void_p
  self.lib.graph_free.argtypes=[ctypes.c_void_p]
  self.lib.graph_full_edges.argtypes=[ctypes.c_void_p,ctypes.c_int64,ctypes.c_int,doubles,doubles,ints,ints]
  self.handle=self.lib.graph_create(graph.node_count,graph.edge_count,graph.source,graph.target,graph.weights['travel_time'],graph.weights['distance'])
 def full_edges(self,root):
  n=self.graph.node_count;arrays=(np.empty(n),np.empty(n),np.empty(n,dtype=np.int64),np.empty(n,dtype=np.int64))
  self.lib.graph_full_edges(self.handle,root,False,*arrays);return arrays
 def close(self):self.lib.graph_free(self.handle)
from timecut5.road_provider import TableFreeRoadSelectedLegProvider as Cached
spec=importlib.util.spec_from_file_location('timecut5.baseline_provider',ROOT/'fixtures/pinned_road_provider.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
SHA='0'*64
class TestReuse(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory()
  # parallel ties, zero edge, floating addition, disconnected node, length tie break
  cls.graph=SimpleNamespace(node_count=7,edge_count=10,
   source=np.array([0,0,0,1,2,1,3,4,2,5],dtype=np.int64),
   target=np.array([1,1,2,3,3,2,4,5,5,0],dtype=np.int64),
   weights={'travel_time':np.array([.1,.1,.1,.2,.2,0.,.3,.1,.5,1.]),
            'distance':np.array([1.,1.,2.,2.,1.,1.,1.,1.,2.,1.])})
  cls.router=ExactRouter(cls.graph,{'compiler':'g++','compiler_flags':['-O2','-std=c++17']},cls.temp.name)
 @classmethod
 def tearDownClass(cls):cls.router.close();cls.temp.cleanup()
 def provider(self,kind=Cached,**kw):
  anchors={str(i):i for i in range(self.graph.node_count)}
  return kind(self.graph,self.router,anchors,nodes_sha256=SHA,edges_sha256=SHA,
   router_sha256=self.router.provenance['source_sha256'],
   anchor_catalog_sha256=hashlib.sha256(json.dumps(anchors,sort_keys=True,separators=(',',':')).encode()).hexdigest(),**kw)
 def test_all_pairs_exact_and_call_reduction(self):
  baseline=self.provider(base.TableFreeRoadSelectedLegProvider);cached=self.provider()
  for s in range(7):
   for t in range(7):
    key=str(s),str(t)
    self.assertEqual(baseline.leg(*key),cached.leg(*key))
    self.assertEqual(baseline.edge_witnesses[key],cached.edge_witnesses[key])
  self.assertEqual((baseline.source_run_count,cached.source_run_count),(49,7))
  self.assertEqual(cached.edge_witnesses['0','1'],(0,))
  self.assertEqual(cached.edge_witnesses['0','6'],None)
  self.assertEqual(cached.edge_witnesses['6','6'],())
  REPORT['all_pairs']={'baseline_native_calls':49,'cached_native_calls':7,'reduction_percent':100*42/49,'exact_legs_and_full_witnesses':49}
 def test_disabled(self):
  p=self.provider(source_cache_max_bytes=0)
  for t in range(7):p.leg('0',str(t))
  self.assertEqual(p.source_run_count,7);self.assertEqual(p.source_cache_bytes,0)
 def test_lru_eviction(self):
  p=self.provider(source_cache_max_sources=2);b=self.provider(base.TableFreeRoadSelectedLegProvider)
  seq=[('0','1'),('1','2'),('0','3'),('2','3'),('1','4')]
  for key in seq:self.assertEqual(p.leg(*key),b.leg(*key));self.assertEqual(p.edge_witnesses[key],b.edge_witnesses[key])
  self.assertEqual(list(p._source_labels),[2,1]);self.assertEqual(p.source_run_count,4)
  self.assertEqual(p.source_cache_hits,1);self.assertEqual(p.source_cache_evictions,2)
 def test_byte_budget_and_oversized_bypass(self):
  p=self.provider();p.leg('0','1');size=p.source_cache_bytes
  for budget in [1,size-1,size,size*2]:
   q=self.provider(source_cache_max_bytes=budget,source_cache_max_sources=10)
   for source in range(7):
    for target in [0,1]:q.leg(str(source),str(target));self.assertLessEqual(q.source_cache_bytes,budget)
   self.assertLessEqual(len(q._source_labels),budget//size)
  REPORT['source_entry_bytes']=size
 def test_owned_readonly_buffers(self):
  p=self.provider();p.leg('0','1');arrays=p._source_labels[0][0]
  for a in arrays:self.assertTrue(a.flags.owndata);self.assertFalse(a.flags.writeable)
  self.router.full_edges(2)
  self.assertEqual(p.leg('0','4'),self.provider(base.TableFreeRoadSelectedLegProvider).leg('0','4'))
 def test_router_reused_mutable_buffers(self):
  p=self.provider();native=self.router
  class ScratchRouter:
   provenance=native.provenance
   def __init__(self):self.buffers=None
   def full_edges(self,source):
    fresh=native.full_edges(source)
    if self.buffers is None:self.buffers=fresh
    else:
     for old,new in zip(self.buffers,fresh):np.copyto(old,new)
    return self.buffers
  p.router=ScratchRouter()
  p.leg('0','1');p.leg('2','3')
  baseline=self.provider(base.TableFreeRoadSelectedLegProvider)
  self.assertEqual(p.leg('0','4'),baseline.leg('0','4'))
  self.assertEqual(p.edge_witnesses['0','4'],baseline.edge_witnesses['0','4'])
 def test_binding_isolation_and_provenance(self):
  p=self.provider();q=self.provider();p.leg('0','1');q.leg('0','2')
  self.assertIsNot(p._source_labels,q._source_labels);self.assertEqual(q.source_run_count,1)
  self.assertEqual(p.source_sha256,q.source_sha256)
  anchors={'a':0,'b':1}
  with self.assertRaisesRegex(ValueError,'router source'):
   Cached(self.graph,self.router,anchors,nodes_sha256=SHA,edges_sha256=SHA,router_sha256=SHA,
    anchor_catalog_sha256=hashlib.sha256(json.dumps(anchors,sort_keys=True,separators=(',',':')).encode()).hexdigest())
  with self.assertRaisesRegex(ValueError,'catalog bytes'):
   Cached(self.graph,self.router,anchors,nodes_sha256=SHA,edges_sha256=SHA,router_sha256=self.router.provenance['source_sha256'],anchor_catalog_sha256=SHA)
 def test_cross_anchor_binding(self):
  first=self.provider();first.leg('0','1')
  anchors={str(i):6-i for i in range(7)}
  kwargs=dict(nodes_sha256='1'*64,edges_sha256='2'*64,router_sha256=self.router.provenance['source_sha256'],
   anchor_catalog_sha256=hashlib.sha256(json.dumps(anchors,sort_keys=True,separators=(',',':')).encode()).hexdigest())
  second=Cached(self.graph,self.router,anchors,**kwargs)
  baseline=base.TableFreeRoadSelectedLegProvider(self.graph,self.router,anchors,**kwargs)
  for target in ['1','2','6']:
   self.assertEqual(second.leg('0',target),baseline.leg('0',target))
   self.assertEqual(second.edge_witnesses['0',target],baseline.edge_witnesses['0',target])
  self.assertEqual(second.source_run_count,1)
  self.assertNotEqual(first.source_sha256,second.source_sha256)
  self.assertNotEqual(first.leg('0','1'),second.leg('0','1'))
 def test_actual_graph_budget_arithmetic_only(self):
  nodes=5892498
  size=Cached.source_cache_entry_bytes(nodes)
  self.assertEqual(size,32*nodes+520)
  self.assertGreater(size,128*1024*1024)
  self.assertLessEqual(size,256*1024*1024)
  REPORT['actual_graph_budget_arithmetic_only']={
   'nodes':nodes,'source_array_payload_bytes':32*nodes,
   'retained_source_entry_bytes':size,'admitted_at_128_mib':False,
   'recommended_diagnostic_budget_bytes':256*1024*1024,'recommended_max_sources':1,
   'native_plus_copy_payload_peak_bytes':2*32*nodes,
   'label_objects_peak_bytes':2*size,'full_graph_allocated':False}
 def test_evict_before_native_allocation(self):
  p=self.provider(source_cache_max_sources=1);p.leg('0','1')
  native=self.router
  class CheckingRouter:
   provenance=native.provenance
   def full_edges(inner,source):
    self.assertEqual(p.source_cache_bytes,0)
    self.assertEqual(len(p._source_labels),0)
    return native.full_edges(source)
  p.router=CheckingRouter();p.leg('2','3')
  self.assertEqual(p.source_cache_evictions,1)
 def test_bad_limits(self):
  for kwargs in [{'source_cache_max_bytes':-1},{'source_cache_max_sources':True}]:
   with self.assertRaises(ValueError):self.provider(**kwargs)
REPORT={}
if __name__=='__main__':
 resource.setrlimit(resource.RLIMIT_CPU,(50,55))
 started=time.monotonic();before=resource.getrusage(resource.RUSAGE_CHILDREN)
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestReuse))
 own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
 REPORT.update(tests_run=result.testsRun,passed=result.wasSuccessful(),wall_seconds=time.monotonic()-started,
  process_cpu_seconds=own.ru_utime+own.ru_stime,child_cpu_seconds=child.ru_utime+child.ru_stime-before.ru_utime-before.ru_stime,
  real_od_runs=0,compiler='g++ -O2 -std=c++17',native_source_sha256=TestReuse.router.provenance['source_sha256'])
 (ROOT/'ROUTE_REUSE_TEST_RESULTS.json').write_text(json.dumps(REPORT,indent=2)+'\n')
 sys.exit(not result.wasSuccessful())
