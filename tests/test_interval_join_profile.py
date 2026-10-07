"""Tiny fixed-payload rebinding and exact new-kernel profile checks."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import join_profile as pilot,hot_jobs as hot
from validation.real5_v2.batch_jobs import make_job,evaluate,decode,wire,sha
from tests.test_independent_oracle_v5 import p

class JoinProfile(unittest.TestCase):
 def fixture(self,raw):
  stack=ExitStack();stack.enter_context(patch.object(pilot,'JOB_SHA',sha(raw)))
  stack.enter_context(patch.object(pilot,'JOB_BYTES',len(raw)));return stack
 def test_exact_rebind_profile_certificate_and_false_acceptance(self):
  raw=make_job(pilot.INDEX,pilot.BATCH_SHA,'reduction',[p()],[p()],pilot.CAPTURE_SHA,kernel='interval-sweep-v1')
  with self.fixture(raw):candidate=pilot.rebind(raw)
  a,b=decode(raw),decode(candidate)
  self.assertEqual({k:v for k,v in a.items() if k!='kernel'},{k:v for k,v in b.items() if k!='kernel'})
  result=hot.profile_job(candidate,pilot.KERNEL,1);old=evaluate(raw)
  self.assertTrue(result['completed']);self.assertFalse(result['acceptance']);self.assertFalse(result['structural_verified'])
  self.assertEqual(result['result']['certificate_sha256'],old['certificate_sha256'])
  self.assertEqual(result['observations']['sweep_work']['certificate_cells'],old['cells'])
 def test_repaired_payload_cannot_change_index_context_batch_kind_or_version(self):
  raw=make_job(pilot.INDEX,pilot.BATCH_SHA,'reduction',[p()],[p()],pilot.CAPTURE_SHA,kernel='interval-sweep-v1')
  for field,value in [('index',11841),('index',11840.0),('context_sha256','0'*64),('batch_sha256','0'*64),('kind','union'),('kernel','v2')]:
   data=decode(raw);data[field]=value;bad=wire(data)
   with self.subTest(field=field),self.fixture(bad),self.assertRaises(ValueError):pilot.rebind(bad)
  with self.fixture(raw),self.assertRaises(ValueError):pilot.rebind(raw+b' ')
 def test_join_worker_kernel_pin_is_mandatory(self):
  raw=make_job(0,'a'*64,'reduction',[p()],[p()],'b'*64,kernel=pilot.KERNEL)
  with self.assertRaisesRegex(ValueError,'kernel mismatch'):evaluate(raw,expected_kernel='interval-sweep-v1')
  self.assertEqual(evaluate(raw,expected_kernel=pilot.KERNEL)['kernel'],pilot.KERNEL)
if __name__=='__main__':unittest.main()
