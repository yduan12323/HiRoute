"""Nonuniform exact expanded-byte counts, not a runtime or uniformity model."""
import random,unittest
from validation.capture5.canonical_lengths import query_lengths
from validation.capture5.containers import freeze_shared,canonical_chunks,query_digest
from validation.capture5.query_dag_digest import QueryDagEncoder

class CanonicalQueryLengths(unittest.TestCase):
 def check(self,value):
  frozen=freeze_shared(value);counts=query_lengths(frozen);raw=b''.join(canonical_chunks(value))
  self.assertEqual(counts['total_bytes'],len(raw));offset=1
  for i,q in enumerate(value):
   n=len(b''.join(canonical_chunks(q)));self.assertEqual(counts['query_bytes'][i],n)
   offset+=n+int(i>0);self.assertEqual(counts['prefix_bytes'][i+1],offset)
  encoder=QueryDagEncoder(value);self.assertEqual(encoder.measure_lengths(),counts)
  self.assertEqual(encoder.digest(),query_digest(value));self.assertEqual(encoder.snapshot()['logical_query_bytes_remaining'],0)
 def test_empty_unicode_signed_zero_and_skewed_shared_queries(self):
  self.check([])
  node={'text':'é\n\\"','floats':[-0.0,0.0,1.5],'exact':'1'+'0'*5000+'/3'}
  self.check([{'tiny':None},True,1,{'ancestry_nodes':{'a':node}},{'large':[node]*100}])
 def test_seeded_dag_lengths_equal_every_expanded_byte(self):
  rng=random.Random(1214)
  for _ in range(150):
   shared=[{'x':[rng.choice([None,True,1,0.0,-0.0,'ø']) for _ in range(rng.randrange(8))]} for i in range(5)]
   self.check([{'q':i,'shared':[rng.choice(shared) for _ in range(rng.randrange(8))]} for i in range(rng.randrange(10))])
 def test_progress_reports_exact_skewed_remainder(self):
  rows=[{'x':'tiny'},{'x':'z'*100000},None];encoder=QueryDagEncoder(rows);lengths=encoder.measure_lengths();seen=[]
  encoder.progress=lambda:seen.append(encoder.snapshot())
  self.assertEqual(encoder.digest(),query_digest(rows));first=next(x for x in seen if x['queries_completed']==1)
  self.assertEqual(first['remaining_bytes_after_completed_queries'],lengths['total_bytes']-lengths['prefix_bytes'][1])
  self.assertGreater(first['logical_query_bytes_remaining'],100000)
 def test_mutable_or_nonfinite_inputs_reject(self):
  for rows in ([{}],({'mutable':[]},),(float('nan'),)):
   with self.assertRaises(ValueError):query_lengths(rows)
if __name__=='__main__':unittest.main()
