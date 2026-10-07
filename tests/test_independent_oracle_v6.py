"""Exact empty-domain filtering and unchanged full sweep certificate tests."""
from dataclasses import replace
from fractions import Fraction as F
from itertools import product,combinations
import random,unittest
from unittest.mock import patch
from validation.family5 import independent_oracle_v2 as v2,independent_oracle_v5 as v5,independent_oracle_v6 as v6
from tests.test_independent_oracle_v5 import p,outcome

class IntervalJoin(unittest.TestCase):
 def expected(self,a,b=None):
  rows=combinations(range(len(a)),2) if b is None else product(range(len(a)),range(len(b)))
  return {(i,j):v5._overlap(a[i],(a if b is None else b)[j]) for i,j in rows
   if a[i].state==(a if b is None else b)[j].state and v5._overlap(a[i],(a if b is None else b)[j]) is not None}
 def actual(self,a,b=None):
  rows=list(v6.overlapping_pairs(a,b));self.assertEqual(len(rows),len({(i,j) for i,j,o in rows}))
  return {(i,j):o for i,j,o in rows}
 def test_all_endpoint_flags_singletons_empty_duplicates_and_states(self):
  rows=[p(lo=F(lo),hi=F(hi),lc=lc,rc=rc,state=(state,0,0))
   for lo in range(3) for hi in range(lo,3) for lc,rc,state in product((False,True),(False,True),('a','b'))]
  self.assertEqual(self.actual(rows,rows),self.expected(rows,rows))
  self.assertEqual(self.actual(rows),self.expected(rows))
  shuffled=list(reversed(rows));self.assertEqual(self.actual(rows,shuffled),self.expected(rows,shuffled))
 def test_seeded_complete_certificate_and_first_failure_order(self):
  rng=random.Random(71840)
  for _ in range(400):
   def family():
    rows=[]
    for _ in range(rng.randrange(8)):
     lo,hi=sorted(rng.choices(range(5),k=2));h=rng.randrange(2)
     rows.append(p(lo=F(lo),hi=F(hi),lc=bool(rng.randrange(2)),rc=bool(rng.randrange(2)),
      m=F(rng.randrange(-3,4)),b=F(rng.randrange(-3,4)),chi=bool(rng.randrange(2)),rho=F(rng.randrange(3)),
      pi=((str(rng.randrange(3)),'C'),) if h else (),state=(str(rng.randrange(2)),0,h)))
    return rows
   a=family();b=list(a) if rng.randrange(2) else family()
   self.assertEqual(self.actual(a,b),self.expected(a,b))
   self.assertEqual(outcome(v6.equivalent,a,b),outcome(v2.equivalent,a,b))
   self.assertEqual(outcome(v6.antichain,a),outcome(v2.antichain,a))
 def test_raw_cartesian_limit_does_not_reject_empty_domain_work(self):
  rows=[p(lo=F(3*i),hi=F(3*i+1)) for i in range(20)]
  with patch.object(v5,'MAX_PAIR_TESTS',20),self.assertRaises(v5.SweepResourceLimit):v5.equivalent_compact(rows,rows)
  with patch.object(v6,'MAX_CANDIDATE_PAIRS',20):result,work=v6.equivalent_work(rows,rows)
  self.assertEqual(result,v5.equivalent_compact(rows,rows));self.assertEqual(work['pair_intersections'],20)
  self.assertEqual(work['cartesian_pairs'],400)
  with patch.object(v6,'MAX_CANDIDATE_PAIRS',19),self.assertRaises(v6.SweepResourceLimit):v6.equivalent_compact(rows,rows)
  with patch.object(v6,'MAX_INTERVALS',1),self.assertRaises(v6.SweepResourceLimit):v6.equivalent_compact(rows,rows)
 def test_duplicate_cover_order_stream_digest_and_array_ownership(self):
  a=[p(),p(),p(b=F(1))];b=[p(),p()]
  self.assertEqual(v6.equivalent(a,b),v5.equivalent(a,b))
  self.assertEqual(v6.equivalent_compact(a,b),v5.equivalent_compact(a,b))
  result=v6.equivalent(a,b);result['certificate'][0]['left_support'].clear()
  self.assertEqual(result['certificate'][1]['left_support'],[0,1,2])
if __name__=='__main__':unittest.main()
