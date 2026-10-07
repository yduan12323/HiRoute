from fractions import Fraction
import hashlib,json
from types import MappingProxyType
import unittest
from validation.capture5.containers import detach_json,freeze_shared,canonical_chunks,stream_digest,query_digest

class CaptureContainers(unittest.TestCase):
 def test_detach_shares_only_immutable_leaves(self):
  ident='a'*64;source={'parents':[ident,ident],'guard':[0,True]};copy=detach_json(MappingProxyType(source))
  self.assertIs(copy['parents'][0],ident);copy['guard'][0]=99;self.assertEqual(source['guard'][0],0)
 def test_freeze_preserves_sharing_but_detaches_external_backing(self):
  node={'guard':[1,True],'parents':['a'*64]};source={'a':node,'b':node};proxy=MappingProxyType(source)
  frozen=freeze_shared(proxy);self.assertIs(frozen['a'],frozen['b']);node['guard'][0]=99
  self.assertEqual(frozen['a']['guard'],(1,True));source.clear();self.assertEqual(set(frozen),{'a','b'})
  with self.assertRaises(TypeError):frozen['a']['guard'][0]=0
 def test_cycles_and_foreign_values_reject(self):
  cycle=[];cycle.append(cycle)
  for value in (cycle,object(),{'a':float('inf')},{1:'x'}):
   with self.assertRaises(ValueError):freeze_shared(value)
  for value in (object(),float('nan'),{1:'x'}):
   with self.assertRaises(ValueError):detach_json(value)
 def test_stream_is_exact_for_unfrozen_and_frozen(self):
  values=[dict(x='线'*50000,y=[-0.0,True,None,3]),{'parents':['a'*64]*10000},[]]
  for value in values:
   expected=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
   for current in (value,freeze_shared(value)):
    chunks=list(canonical_chunks(current));self.assertLessEqual(max(map(len,chunks)),65536)
    self.assertEqual(b''.join(chunks),expected);self.assertEqual(stream_digest(current),hashlib.sha256(expected).hexdigest())
  self.assertNotEqual(stream_digest([True]),stream_digest([1]))
 def test_one_pass_population_hash_and_fraction_match_legacy(self):
  values=[{'x':[1,'1',True]},{'x':[]}]
  self.assertEqual(query_digest(iter(values)),stream_digest(values))
  self.assertEqual(stream_digest({'x':Fraction(1,3)}),stream_digest({'x':'1/3'}))

if __name__=='__main__':unittest.main()
