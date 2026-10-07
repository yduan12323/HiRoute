"""Exact v2/v4 certificate and rejection equivalence, no real workload."""
from dataclasses import replace
from fractions import Fraction as F
from itertools import product
import json,random,unittest
from unittest.mock import patch
from validation.family5 import independent_oracle_v2 as old,independent_oracle_v4 as new

def p(**kw):return replace(old.Piece(F(0),F(2),True,True,F(1),F(0),True,F(0),(),('o',0,0)),**kw)
def outcome(fn,*args):
 try:return ('return',fn(*args))
 except AssertionError as error:return ('reject',error.args)
class TauPrecompute(unittest.TestCase):
 def test_seeded_complete_certificate_bytes_and_rejections(self):
  rng=random.Random(10617)
  for _ in range(400):
   def family():
    rows=[]
    for i in range(rng.randrange(7)):
     lo,hi=sorted(rng.sample(range(6),2));h=rng.randrange(2)
     rows.append(p(lo=F(lo),hi=F(hi),lc=bool(rng.randrange(2)),rc=bool(rng.randrange(2)),
      m=F(rng.randrange(-3,4)),b=F(rng.randrange(-4,5)),rho=F(rng.randrange(-1,3)),chi=bool(rng.randrange(2)),
      state=('o' if rng.randrange(3) else 's',0,h),pi=(('s','C'),) if h else ()))
    return rows
   a=family();b=list(a) if rng.randrange(2) else family()
   self.assertEqual(outcome(old.equivalent,a,b),outcome(new.equivalent,a,b))
   self.assertEqual(outcome(old.antichain,a),outcome(new.antichain,a))
 def test_endpoint_attainment_crossings_and_first_support_order(self):
  for lc,rc,chi in product((False,True),repeat=3):
   a=[p(lc=lc,rc=rc,chi=chi),p(m=F(-1),b=F(2)),p(lo=F(1),hi=F(1))]
   b=list(reversed(a))
   self.assertEqual(outcome(old.equivalent,a,b),outcome(new.equivalent,a,b))
   for lo,hi,e in old.arrangement(a+b):self.assertEqual(old._certificate_cell(a,b,lo,hi,e),new._certificate_cell(a,b,lo,hi,e))
  a=[p(),p(),p(b=F(1))];b=[p(),p()]
  value=new.equivalent(a,b)
  self.assertEqual(value,old.equivalent(a,b))
  self.assertEqual(value['certificate'][0]['left_covers_right'],[0,0])
  self.assertEqual(json.dumps(value,sort_keys=True,separators=(',',':')),json.dumps(old.equivalent(a,b),sort_keys=True,separators=(',',':')))
 def test_full_key_disconnected_singleton_and_large_rationals(self):
  cases=[([p(hi=F(1),rc=False),p(lo=F(2),hi=F(3))],[p()]),
   ([p(lo=F(1),hi=F(1),chi=False)],[p(lo=F(1),hi=F(1))]),
   ([p(rho=F(1))],[p()]),([p(pi=(('a','C'),),state=('o',0,1))],[p(pi=(('z','C'),),state=('o',0,1))]),
   ([p(m=F(10)**5000)],[p(m=F(10)**5000)]),([],[])]
  for a,b in cases:self.assertEqual(outcome(old.equivalent,a,b),outcome(new.equivalent,a,b))
 def test_tau_evaluated_once_per_active_occurrence(self):
  a=[p(b=F(i)) for i in range(12)];b=list(reversed(a));original=old.Piece.tau;calls=[]
  def count(piece,e):calls.append((piece,e));return original(piece,e)
  with patch.object(old.Piece,'tau',count):
   new._certificate_cell(a,b,F(0),F(2),F(1));self.assertEqual(len(calls),24)
   calls.clear();old._certificate_cell(a,b,F(0),F(2),F(1));self.assertGreater(len(calls),24)
  unique=[p(rho=F(i),pi=((str(i),'C'),),state=('o',0,1)) for i in range(8)]
  with patch.object(old.Piece,'tau',count):
   calls.clear();outcome(new.antichain,unique)
   self.assertLessEqual(len(calls),len(unique)*len(old.arrangement(unique)))
if __name__=='__main__':unittest.main()
