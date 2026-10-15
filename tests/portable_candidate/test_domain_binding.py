import copy,unittest
from .test_portable_policy import fixture,rebind,canonical,digest,build_portable_domain
from timecut5.portable_candidate_binding import derive_binding
from timecut5.real_legs import RealSite
from timecut5.real_adapter import site_catalog_digest
from timecut5.sparse_seed import sparse_domain_digest

def actual_fixture():
 f=fixture();q=f['query'];q['hierarchy_sha256']='9'*64
 sites={x['site_id']:RealSite(x['site_id'],x['anchor_id'],tuple(x['effects'])) for x in f['baseline_sites']}
 sources=f['bindings']['source_sha256']
 q['sparse_domain_sha256']=sparse_domain_digest(sources,site_catalog_digest(sites),digest(canonical(sorted(sites))),q['hierarchy_sha256'],q['origin'],q['destination'])
 return rebind(f)
def call(f,p,**changes):
 args=dict(proposal=p,expected_payload_sha256=digest(p.payload_bytes),baseline_query=f['query'],baseline_sites=f['baseline_sites'],baseline_provider_sources=f['bindings']['source_sha256']);args.update(changes);return derive_binding(**args)
class DomainBindingTests(unittest.TestCase):
 def test_dynamic_domain_preserves_physical_query(self):
  f=actual_fixture();p=build_portable_domain(**f);b=call(f,p)
  self.assertNotEqual(b['sparse_domain_sha256'],f['query']['sparse_domain_sha256'])
  self.assertEqual({k:v for k,v in b['query'].items() if k!='sparse_domain_sha256'},{k:v for k,v in f['query'].items() if k!='sparse_domain_sha256'})
  self.assertEqual(b['candidate_count'],6);self.assertFalse(b['runtime_admission_complete']);self.assertFalse(b['launchable'])
 def test_incomplete_or_overflow_cannot_bind(self):
  for cap in (1,False):
   f=actual_fixture();f['cap']=cap;p=build_portable_domain(**f)
   with self.assertRaises(ValueError):call(f,p)
 def test_pin_source_and_query_tamper_rejected(self):
  f=actual_fixture();p=build_portable_domain(**f)
  for change in [dict(expected_payload_sha256='0'*64),dict(baseline_query=dict(f['query'],reserve_kwh='7')),dict(baseline_provider_sources=dict(f['bindings']['source_sha256'],nodes='0'*64))]:
   with self.subTest(change=change),self.assertRaises(ValueError):call(f,p,**change)
if __name__=='__main__':unittest.main()
