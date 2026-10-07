"""Differential v3 tests against unchanged independent v2; no real experiments."""
from dataclasses import replace
from fractions import Fraction as F
import random,sys,unittest
from unittest.mock import patch
from validation.family5 import independent_oracle_v2 as old
from validation.family5 import independent_oracle_v3 as new

def piece(**kw):
 return replace(old.Piece(F(0),F(2),True,True,F(1),F(0),True,F(0),(),('o',0,0)),**kw)
def outcome(fn,a,b):
 try:return ('return',fn(a,b))
 except AssertionError as e:return ('reject',e.args)

class OracleV3(unittest.TestCase):
 def test_differential_complete_cells_and_rejections(self):
  rng=random.Random(10317);memo=new.MemoizedOracle()
  for _ in range(300):
   a=[piece(lo=F(lo),hi=F(hi),lc=bool(rng.randrange(2)),rc=bool(rng.randrange(2)),
      m=F(rng.randrange(-2,3)),b=F(rng.randrange(-2,3)),chi=bool(rng.randrange(2)),rho=F(rng.randrange(2)))
      for lo,hi in (sorted(rng.sample(range(5),2)) for __ in range(rng.randrange(5)))]
   b=list(a) if rng.randrange(2) else [piece(m=F(rng.randrange(-2,3)),b=F(rng.randrange(3)))]
   self.assertEqual(outcome(old.exact_family_equal,a,b),outcome(new.exact_family_equal,a,b))
   self.assertEqual(outcome(old.exact_family_equal,a,b),outcome(memo.exact_family_equal,a,b))
 def test_one_arrangement_and_no_unused_coverage(self):
  with patch.object(old,'arrangement',wraps=old.arrangement) as arrangement,patch.object(old,'_certificate_cell',side_effect=RuntimeError('unused work')):
   self.assertEqual(new.exact_family_equal([piece()],[piece()]),3)
   self.assertEqual(arrangement.call_count,1)
 def test_full_semantic_keys_attainment_endpoints_crossings_and_family(self):
  memo=new.MemoizedOracle();p=piece()
  self.assertEqual(memo.exact_family_equal([p],[p]),3)
  variants=[replace(p,lc=False),replace(p,rc=False),replace(p,chi=False),replace(p,rho=F(1)),
   replace(p,pi=(('s','C'),),state=('o',0,1)),replace(p,state=('s',0,0)),replace(p,m=F(-1)),
   replace(p,b=F(1)),replace(p,lo=F(1)),replace(p,hi=F(3)),replace(p,lo=F(1),hi=F(1))]
  for q in variants:
   self.assertEqual(outcome(old.exact_family_equal,[p],[q]),outcome(memo.exact_family_equal,[p],[q]))
  # Endpoint-only attainment and disconnected coverage stay visible.
  a=[replace(p,rc=False),replace(p,lo=F(2),hi=F(2),chi=False)]
  self.assertEqual(outcome(old.exact_family_equal,a,[p]),outcome(memo.exact_family_equal,a,[p]))
 def test_certificate_ownership_and_input_order(self):
  memo=new.MemoizedOracle();a=[piece(),piece(b=F(1))];expected=old.equivalent(a,a)
  value=memo.equivalent(a,a);value['certificate'][0]['left_support'].clear()
  self.assertEqual(memo.equivalent(a,a),expected);self.assertEqual(memo.stats['hits'],1)
  self.assertEqual(memo.equivalent(list(reversed(a)),a),old.equivalent(list(reversed(a)),a))
  self.assertEqual(memo.stats['misses'],2)
  self.assertGreater(memo.stats['max_key_bytes_equivalent'],0)
  self.assertGreater(memo.stats['max_value_bytes_equivalent'],0)
 def test_bounded_eviction_bypass_and_no_negative_cache(self):
  memo=new.MemoizedOracle(max_bytes=2048,max_entries=2,max_entry_bytes=1024)
  for n in range(20):
   p=piece(b=F(n));memo.exact_family_equal([p],[p])
   self.assertLessEqual(memo.stored_bytes,2048);self.assertLessEqual(len(memo.cache),2)
  self.assertGreater(memo.stats['evictions'],0)
  no_cache=new.MemoizedOracle(max_bytes=0)
  self.assertEqual(no_cache.exact_family_equal([piece()],[piece()]),3);self.assertFalse(no_cache.cache)
  for _ in range(2):
   with self.assertRaises(AssertionError):memo.exact_family_equal([piece()],[piece(chi=False)])
  self.assertEqual(memo.stats['hits'],0)
 def test_interrupted_cache_publication_has_exact_accounting_on_reuse(self):
  class Interrupted(BaseException):pass
  p=piece();probe=new.MemoizedOracle();probe.exact_family_equal([p],[p]);size=probe.stored_bytes
  memo=new.MemoizedOracle(max_bytes=size,max_entry_bytes=size);fired=[]
  def interrupt(frame,event,arg):
   if frame.f_code is new.MemoizedOracle._call.__code__:
    frame.f_trace_opcodes=True
    if event=='opcode' and memo.cache and not fired:
     fired.append(True);raise Interrupted()
   return interrupt
  previous=sys.gettrace();sys.settrace(interrupt)
  try:
   with self.assertRaises(Interrupted):memo.exact_family_equal([p],[p])
  finally:sys.settrace(previous)
  self.assertEqual(memo.stored_bytes,sum(len(k)+len(v) for k,v in memo.cache.items()))
  memo.exact_family_equal([piece(b=F(1))],[piece(b=F(1))])
  self.assertLessEqual(memo.stored_bytes,size);self.assertLessEqual(len(memo.cache),1)

 def test_key_serialization_failure_preserves_uncached_exact_result(self):
  p=piece(m=F(10)**5000);memo=new.MemoizedOracle()
  self.assertEqual(old.exact_family_equal([p],[p]),memo.exact_family_equal([p],[p]))
  self.assertEqual(old.equivalent([p],[p]),memo.equivalent([p],[p]))
  with patch.object(new,'_wire',side_effect=ValueError('key serialization unavailable')):
   self.assertEqual(memo.exact_family_equal([piece()],[piece()]),3)
   self.assertEqual(memo.equivalent([piece()],[piece()]),old.equivalent([piece()],[piece()]))
  self.assertGreater(memo.stats['key_bypasses'],0)

 def test_exact_limit_types(self):
  for value in (True,-1,1.0):
   with self.assertRaises(ValueError):new.MemoizedOracle(max_entries=value)

if __name__=='__main__':unittest.main()
