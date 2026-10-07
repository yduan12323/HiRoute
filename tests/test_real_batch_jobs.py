"""Tiny process jobs only; no remote/C01 execution."""
from dataclasses import replace
from fractions import Fraction as F
import json,os,time,unittest
from pathlib import Path
from unittest.mock import patch
from validation.real5_v2.batch_jobs import BatchExecutor,BatchIncomplete,make_job,evaluate,check_result,decode,wire,sha,read_piece,encode_piece
from validation.family5 import independent_oracle_v2 as oracle
from tests.test_recovered_real_family import prepare
from tests.test_recovered_real_coalesced import capture
from validation.real5_v2 import family
ROOT=Path(__file__).resolve().parents[1]
def piece():return oracle.Piece(F(0),F(2),True,True,F(1),F(0),True,F(0),(),('o',0,0))
class BatchJobs(unittest.TestCase):
 def cpus(self):return tuple(sorted(os.sched_getaffinity(0)))[:2]
 def test_wire_roundtrip_and_exact_complete_certificate(self):
  p=piece()
  for q in (p,replace(p,m=F(10)**5000),replace(p,lc=False,chi=False)):
   self.assertEqual(read_piece(encode_piece(q)),q)
  for kind in ('union','reduction'):
   raw=make_job(4,'a'*64,kind,[p],[p],'b'*64);result=evaluate(raw)
   job=dict(index=4,batch_sha256='a'*64,kind=kind,context_sha256='b'*64,job_sha256=sha(raw))
   self.assertEqual(check_result(result,job),3)
   if kind=='reduction':self.assertEqual(result['certificate_sha256'],oracle.equivalent([p],[p])['sha256'])
 def test_explicit_kernel_pin_and_identical_certificate(self):
  p=piece();baseline=evaluate(make_job(4,'a'*64,'reduction',[p],[p],'b'*64))
  raw=make_job(4,'a'*64,'reduction',[p],[p],'b'*64,kernel='tau-precompute-v1')
  result=evaluate(raw,expected_kernel='tau-precompute-v1')
  self.assertEqual(result['certificate_sha256'],baseline['certificate_sha256'])
  self.assertEqual(result['cells'],baseline['cells']);self.assertEqual(result['kernel'],'tau-precompute-v1')
  job=dict(index=4,batch_sha256='a'*64,kind='reduction',context_sha256='b'*64,job_sha256=sha(raw),kernel='tau-precompute-v1')
  self.assertEqual(check_result(result,job),3)
  with self.assertRaises(ValueError):evaluate(raw,expected_kernel='v2')
  with self.assertRaises(ValueError):check_result(dict(result,kernel='v2'),job)
  with self.assertRaises(ValueError):evaluate(make_job(4,'a'*64,'reduction',[p],[p],'b'*64),expected_kernel='tau-precompute-v1')
  with BatchExecutor(self.cpus(),float(time.monotonic()+10),'b'*64,worker_as=256*1024**2,kernel='tau-precompute-v1') as pool:
   pool.start([(4,'a'*64,'reduction')]);pool.submit(4,'a'*64,'reduction',[p],[p]);self.assertEqual(pool.finish(),3)
   self.assertEqual(pool.snapshot()['kernel'],'tau-precompute-v1')
   self.assertEqual(pool.results[4]['result']['certificate_sha256'],baseline['certificate_sha256'])
 def test_missing_duplicate_wrong_hash_and_repaired_piece_negatives(self):
  p=piece();raw=make_job(0,'a'*64,'union',[p],[p],'b'*64);result=evaluate(raw)
  job=dict(index=0,batch_sha256='a'*64,kind='union',context_sha256='b'*64,job_sha256=sha(raw))
  for field,value in (('index',True),('cells',True),('job_sha256','0'*64),('batch_sha256','0'*64),('context_sha256','0'*64)):
   with self.subTest(field=field),self.assertRaises(ValueError):check_result(dict(result,**{field:value}),job)
  bad=decode(raw);bad['right'][0]['chi']=False
  with self.assertRaises(AssertionError):evaluate(wire(bad))
  with self.assertRaises(ValueError):evaluate(b'{"x":1,"x":2}')
 def test_two_fresh_workers_join_exact_ids_and_reap(self):
  p=piece();expected=[(i,hex(i+1)[2:].zfill(64),'reduction' if i%2 else 'union') for i in range(6)]
  with BatchExecutor(self.cpus(),float(time.monotonic()+10),'b'*64,worker_as=256*1024**2) as pool:
   pool.start(expected)
   for i,h,k in expected:pool.submit(i,h,k,[p],[p])
   self.assertEqual(pool.finish(),18);self.assertTrue(pool.snapshot()['complete'])
   self.assertEqual(set(pool.results),set(range(6)))
   self.assertTrue(all(s.process.poll()==0 for s in pool.slots))
 def test_missing_duplicate_timeout_and_dead_worker_fail_closed(self):
  p=piece()
  with BatchExecutor(self.cpus(),float(time.monotonic()+10),'b'*64,worker_as=256*1024**2) as pool:
   pool.start([(0,'a'*64,'union')])
   with self.assertRaises(ValueError):pool.finish()
   pool.submit(0,'a'*64,'union',[p],[p])
   with self.assertRaises(ValueError):pool.submit(0,'a'*64,'union',[p],[p])
   pool.deadline=time.monotonic()-1
   with self.assertRaises(BatchIncomplete):pool.pump()
  self.assertTrue(all(s.process.poll() is not None for s in pool.slots))
  with BatchExecutor(self.cpus(),float(time.monotonic()+10),'b'*64,worker_as=256*1024**2) as pool:
   pool.slots[0].process.kill();pool.slots[0].process.wait()
   with self.assertRaises(BatchIncomplete):pool.pump()
 def test_nonfinite_deadlines_reject_before_worker_start(self):
  for deadline in (float('inf'),float('-inf'),float('nan')):
   with self.subTest(deadline=deadline),self.assertRaises(ValueError):
    BatchExecutor(self.cpus(),deadline,'b'*64)
 def test_job_cap_before_submission(self):
  with BatchExecutor(self.cpus(),float(time.monotonic()+10),'b'*64,worker_as=256*1024**2) as pool:
   pool.start([(0,'a'*64,'union')])
   with patch('validation.real5_v2.batch_jobs.JOB_LIMIT',1),self.assertRaisesRegex(ValueError,'cap'):
    pool.submit(0,'a'*64,'union',[piece()],[piece()])
   self.assertEqual(pool.submitted,{})
 def test_complete_family_result_matches_serial(self):
  rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
  for row in rows[:2]:
   for dominance in (False,True):
    with self.subTest(case=row['case_id'],dominance=dominance):
     data=capture(row,dominance);trusted=prepare(row)
     baseline=family._verify_bundle(data['bundle'],trusted.case_snapshot(),trusted.physics)
     with BatchExecutor(self.cpus(),float(time.monotonic()+10),'b'*64,worker_as=256*1024**2) as pool:
      checked=family._verify_bundle(data['bundle'],trusted.case_snapshot(),trusted.physics,batch_executor=pool)
      self.assertEqual(checked.snapshot(),baseline.snapshot())
      a=dict(checked.summary);b=dict(baseline.summary);a.pop('elapsed_s');b.pop('elapsed_s');self.assertEqual(a,b)
      self.assertTrue(pool.snapshot()['complete'])

if __name__=='__main__':unittest.main()
