"""Exact reference certificate/failure differentials for interval sweeping."""
from dataclasses import replace
from fractions import Fraction as F
from itertools import product
import json,random,unittest
from unittest.mock import patch
from validation.family5 import independent_oracle_v2 as old,independent_oracle_v5 as new

def p(**kw):return replace(old.Piece(F(0),F(2),True,True,F(1),F(0),True,F(0),(),('o',0,0)),**kw)
def outcome(fn,*args):
 try:return ('return',fn(*args))
 except AssertionError as exc:return ('reject',exc.args)
class IntervalSweep(unittest.TestCase):
 def test_seeded_all_cells_and_rejection_order(self):
  rng=random.Random(71031)
  for _ in range(700):
   def family():
    rows=[]
    for i in range(rng.randrange(7)):
     lo,hi=sorted(rng.choices(range(5),k=2));h=rng.randrange(2)
     rows.append(p(lo=F(lo),hi=F(hi),lc=bool(rng.randrange(2)),rc=bool(rng.randrange(2)),
      m=F(rng.randrange(-3,4)),b=F(rng.randrange(-3,4)),chi=bool(rng.randrange(2)),rho=F(rng.randrange(3)),
      pi=((str(rng.randrange(3)),'C'),) if h else (),state=(str(rng.randrange(2)),0,h)))
    return rows
   a=family();b=list(a) if rng.randrange(2) else family()
   self.assertEqual(outcome(old.equivalent,a,b),outcome(new.equivalent,a,b))
   self.assertEqual(outcome(old.antichain,a),outcome(new.antichain,a))
   result=outcome(new.equivalent_compact,a,b);expected=outcome(old.equivalent,a,b)
   if expected[0]=='return':expected=('return',{k:v for k,v in expected[1].items() if k!='certificate'})
   self.assertEqual(result,expected)
 def test_every_endpoint_and_attainment_combination(self):
  for lc,rc,qc,qr,chi,qchi in product((False,True),repeat=6):
   a=[p(lc=lc,rc=rc,chi=chi),p(lo=F(1),hi=F(1))]
   b=[p(lo=F(1),hi=F(3),lc=qc,rc=qr,m=F(-1),b=F(2),chi=qchi)]
   self.assertEqual(outcome(old.equivalent,a,b),outcome(new.equivalent,a,b))
   self.assertEqual(outcome(old.antichain,a+b),outcome(new.antichain,a+b))
 def test_duplicate_first_indices_stream_hash_and_owned_lists(self):
  a=[p(),p(),p(b=F(1))];b=[p(),p()]
  result=new.equivalent(a,b);expected=old.equivalent(a,b)
  self.assertEqual(result,expected)
  compact=new.equivalent_compact(a,b);self.assertEqual(compact['sha256'],expected['sha256'])
  result['certificate'][0]['left_support'].clear()
  self.assertEqual(result['certificate'][1]['left_support'],expected['certificate'][1]['left_support'])
  self.assertEqual(json.dumps(new.equivalent(a,b),sort_keys=True),json.dumps(expected,sort_keys=True))
 def test_irrelevant_crossings_reuse_vectors_without_dropping_cells(self):
  # Inferior lines cross one another; an earlier piece still covers every one.
  a=[p(m=F(0),b=F(-100))]+[p(m=F(i),b=F(20-i*i)) for i in range(1,9)]
  b=[a[0]];value,work=new.equivalent_work(a,b)
  self.assertEqual(value,{k:v for k,v in old.equivalent(a,b).items() if k!='certificate'})
  self.assertEqual(work['certificate_cells'],value['cells'])
  self.assertLess(work['vector_states'],value['cells'])
 def test_resource_limits_are_incomplete_and_chunks_are_bounded(self):
  a=[p(),p(b=F(1))];b=[p()]
  for limit,value in (('MAX_PAIR_TESTS',0),('MAX_LINE_PAIRS',0),('MAX_INTERVALS',0),('MAX_CELLS',0),('MAX_ARRAY_BYTES',0)):
   with self.subTest(limit=limit),patch.object(new,limit,value),self.assertRaises(new.SweepResourceLimit):new.equivalent_compact(a,b)
  sweep=new._CoverSweep(a,b)
  with patch.object(new,'MAX_HASH_CHUNK',3):
   chunks=[]
   for cell,arrays in sweep.rows():
    for chunk in new._row_bytes(cell,arrays):
     self.assertLessEqual(len(chunk),3)
     chunks.append(chunk)
  self.assertTrue(chunks)

 def test_huge_coefficients_empty_and_full_keys(self):
  for a,b in (([p(m=F(10)**5000)],[p(m=F(10)**5000)]),([],[]),
   ([p(rho=F(1))],[p()]),([p(state=('x',0,0))],[p()]),
   ([p(pi=(('a','C'),),state=('o',0,1))],[p(pi=(('z','C'),),state=('o',0,1))])):
   self.assertEqual(outcome(old.equivalent,a,b),outcome(new.equivalent,a,b))
if __name__=='__main__':unittest.main()
