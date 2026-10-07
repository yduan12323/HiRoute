"""Exact expanded bytes and ownership checks for shared-DAG query encoding."""
from copy import deepcopy
import hashlib,json,random,unittest
from types import MappingProxyType
from validation.capture5.containers import canonical_chunks,query_digest,detach_json
from validation.capture5.query_dag_digest import QueryDagEncoder,freeze_query_digest

def fixture():
 node={'kind':'select','parents':['parent']*30,'output':{'chi':True,'domain':['0','1',True,False]},'params':{'chosen':0}}
 ancestor={'z':node,'a':{'kind':'initial','parents':[],'output':{'text':'é\n\\"'},'params':{}}}
 ids=['a','z'];case={'value':1,'flag':True}
 return [dict(query_seq=i,ancestry_nodes=ancestor,ancestry_node_ids=ids,trusted_case=case,actions=[] if i%2 else [['s','C']]) for i in range(8)]
class QueryDagDigest(unittest.TestCase):
 def test_identical_complete_bytes_hash_and_shared_owned_result(self):
  queries=fixture();expected=b''.join(canonical_chunks(queries));encoder=QueryDagEncoder(queries)
  chunks=list(encoder.chunks());self.assertEqual(b''.join(chunks),expected)
  self.assertTrue(all(len(x)<=65536 for x in chunks));self.assertGreater(encoder.stats['cache_hits'],0)
  frozen,digest,stats=freeze_query_digest(queries)
  self.assertEqual(digest,query_digest(queries));self.assertEqual(digest,hashlib.sha256(expected).hexdigest())
  self.assertEqual(stats['emitted_bytes'],len(expected));self.assertEqual(stats['distinct_ancestries'],1)
  self.assertEqual(stats['query_count'],8);self.assertEqual(stats['queries_started'],8);self.assertEqual(stats['queries_completed'],8)
  self.assertGreater(stats['cached_bytes_emitted'],0);self.assertLess(stats['encoded_bytes'],stats['emitted_bytes'])
  self.assertIs(frozen[0]['ancestry_nodes'],frozen[1]['ancestry_nodes'])
  queries[0]['ancestry_nodes']['z']['parents'].append('changed')
  self.assertEqual(b''.join(QueryDagEncoder(detach_json(frozen)).chunks()),expected)
 def test_external_mapping_proxy_and_scalar_aliases_cannot_poison_cache(self):
  node={'x':[True,1,1.0,None,'1']};shared=MappingProxyType(node)
  queries=[{'ancestry_nodes':{'n':shared}}]*3;encoder=QueryDagEncoder(queries)
  expected=b''.join(canonical_chunks(queries));node['x'][0]=False
  self.assertEqual(b''.join(encoder.chunks()),expected)
  encoder.queries[0]['ancestry_nodes']['n']['x'] # Immutable, detached children.
  with self.assertRaises(TypeError):encoder.queries[0]['ancestry_nodes']['n']['x'][0]=99
 def test_exact_fallback_for_zero_small_and_oversized_caches(self):
  queries=fixture();queries[0]['ancestry_nodes']['big']={'text':'x'*140000}
  expected=query_digest(queries)
  for cache,entry,keys in ((0,0,0),(17,17,0),(200000,10,64),(200000,180000,2048)):
   with self.subTest(limits=(cache,entry,keys)):
    frozen,digest,stats=freeze_query_digest(queries,cache_bytes=cache,entry_bytes=entry,key_bytes=keys)
    self.assertEqual(digest,expected);self.assertLessEqual(stats['cache_bytes'],cache);self.assertLessEqual(stats['key_tuple_bytes'],keys)
 def test_seeded_shared_and_unshared_equivalence(self):
  rng=random.Random(1033)
  for _ in range(120):
   nodes=[{'n':rng.randrange(10),'p':[rng.choice([True,False,None,'x','é',3]) for _ in range(rng.randrange(8))]} for j in range(5)]
   roots=[{str(i):nodes[rng.randrange(5)] for i in range(rng.randrange(6))} for k in range(3)]
   queries=[{'ancestry_nodes':rng.choice(roots),'query_seq':i,'data':[rng.randrange(3)]} for i in range(rng.randrange(10))]
   self.assertEqual(freeze_query_digest(queries)[1],query_digest(queries))
   self.assertEqual(freeze_query_digest(deepcopy(queries))[1],query_digest(queries))
 def test_large_exact_rational_strings_and_nonobject_fallback(self):
  queries=[{'ancestry_nodes':None,'exact':('1'+'0'*10000)+'/3'},['leaf',True,1],None,
   {'ancestry_nodes':{'n':{'exact':'-'+'9'*100000+'/17'}}}]
  result=freeze_query_digest(queries,cache_bytes=1024,entry_bytes=100)
  self.assertEqual(result[1],query_digest(queries));self.assertLessEqual(result[2]['cache_bytes'],1024)
  self.assertEqual(result[2]['logical_query_bytes'],len(b''.join(canonical_chunks(queries))))
 def test_mutation_during_consumption_cannot_change_owned_bytes(self):
  queries=fixture();expected=b''.join(canonical_chunks(queries));encoder=QueryDagEncoder(queries)
  stream=encoder.chunks();first=next(stream);queries[0]['ancestry_nodes'].clear();queries.clear()
  self.assertEqual(first+b''.join(stream),expected)
  with self.assertRaises(AttributeError):encoder.queries=[]

 def test_interleaved_readers_share_only_charged_cache_entries(self):
  queries=fixture();encoder=QueryDagEncoder(queries,cache_bytes=1400,entry_bytes=1400)
  expected=b''.join(canonical_chunks(queries));a=encoder.chunks();prefix=[]
  for _ in range(30):prefix.append(next(a))
  self.assertEqual(encoder.snapshot()['distinct_ancestries'],1)
  self.assertGreater(encoder.snapshot()['queries_started'],encoder.snapshot()['queries_completed'])
  self.assertEqual(b''.join(encoder.chunks()),expected)
  self.assertEqual(b''.join(prefix)+b''.join(a),expected)
  stats=encoder.snapshot();self.assertLessEqual(stats['cache_bytes'],stats['reserved_cache_bytes'])
  self.assertLessEqual(stats['reserved_cache_bytes'],1400)

 def test_invalid_cycles_nonfinite_limits_and_iterators_reject(self):
  cycle=[];cycle.append(cycle)
  for value in ([{'ancestry_nodes':{'x':cycle}}],[{'x':float('nan')}],[{1:'nonstring'}]):
   with self.assertRaises(ValueError):QueryDagEncoder(value)
  with self.assertRaises(ValueError):QueryDagEncoder(iter(fixture()))
  for limit in (-1,True,10**20):
   with self.assertRaises(ValueError):QueryDagEncoder(fixture(),cache_bytes=limit)
if __name__=='__main__':unittest.main()
