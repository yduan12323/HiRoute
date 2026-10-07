"""Small actual fork/exec memory regressions; no optimization or real data."""
import json,os,resource,subprocess,sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import candidate_memory as memory,lp_jobs
from validation.suffix5.solver import SolveBudget,BudgetExceeded

class CandidateMemoryTests(unittest.TestCase):
 def test_strict_kernel_status_schema_and_units(self):
  raw=b'Name:\tpython\nPid:\t123\nVmHWM:\t20 kB\nVmRSS:\t10 kB\n'
  self.assertEqual(memory.parse_status(raw,123),20*1024)
  self.assertEqual(memory.parse_status(raw.replace(b'20 kB',b'5 kB'),123),10*1024)
  for bad in (raw.replace(b'20 kB',b'20 MB'),raw.replace(b'20 kB',b'-1 kB'),raw.replace(b'20 kB',b'1.5 kB'),
   raw.replace(b'20 kB',b'0 kB'),raw.replace(b'VmHWM:',b'NoHWM:'),raw+b'VmHWM: 2 kB\n',
   raw.replace(b'123',b'124'),raw+b'x'*memory.STATUS_BYTES):
   with self.subTest(bad=bad[:80]),self.assertRaises(ValueError):memory.parse_status(bad,123)
 def test_default_rusage_budget_stays_unchanged_and_reader_is_exact_bytes(self):
  with patch('validation.suffix5.solver.resource.getrusage',return_value=SimpleNamespace(ru_maxrss=1024)):
   SolveBudget(rss_mib=1).check()
   with self.assertRaises(BudgetExceeded):SolveBudget(rss_mib=.5).check()
   SolveBudget(rss_mib=.5,rss_reader=lambda:512*1024).check()
   with self.assertRaises(BudgetExceeded):SolveBudget(rss_mib=.5,rss_reader=lambda:512*1024+1).check()
  for invalid in (-1,True,0.0,float('inf'),None,'123'):
   with self.subTest(invalid=invalid),self.assertRaises(BudgetExceeded):SolveBudget(rss_reader=lambda:invalid).check()
  with self.assertRaises(ValueError):SolveBudget(rss_reader=0)
 def test_observation_failure_never_falls_back_to_zero_or_rusage(self):
  def fail():raise OSError('procfs unavailable')
  with self.assertRaises(OSError):SolveBudget(rss_reader=fail).check()
  with patch.object(memory,'open',side_effect=OSError('procfs unavailable'),create=True),self.assertRaises(OSError):memory.peak_rss_bytes()
 def test_new_metric_and_job_pin_identify_measurement_scope(self):
  from tests.test_lp_calibration_jobs import METRICS,make_fixture
  import tempfile
  with tempfile.TemporaryDirectory() as root:
   jobs,_=make_fixture(root);self.assertEqual(jobs[0].to_dict()['limits']['rss_source'],memory.SOURCE)
   changed=jobs[0].to_dict();changed['limits']['rss_source']='inherited-rusage'
   with self.assertRaises(ValueError):lp_jobs.LPJob.from_dict(changed)
  lp_jobs._metrics(METRICS)
  changed=dict(METRICS,rss_source='inherited-rusage')
  with self.assertRaises(ValueError):lp_jobs._metrics(changed)
 @unittest.skipUnless(sys.platform.startswith('linux'),'Linux exec memory accounting required')
 def test_live_parent_highwater_does_not_reject_small_exec_but_own_peak_does(self):
  # All actual allocations are under 100 MiB each. The real worker's unchanged
  # 768 MiB/1 GiB limits use this same byte comparator and hard-AS mechanism.
  parent=bytearray(96*1024**2)
  for i in range(0,len(parent),4096):parent[i]=1
  code='''
import gc,json,resource
from experiments.time_cut_v2.recorded_real.candidate_memory import peak_rss_bytes
from validation.suffix5.solver import SolveBudget,BudgetExceeded
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
out=dict(rusage_before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,exec_peak_before=peak_rss_bytes())
try:SolveBudget(rss_mib=64).check();out['old_rejected']=False
except BudgetExceeded:out['old_rejected']=True
SolveBudget(rss_mib=64,rss_reader=peak_rss_bytes).check();out['new_small_passed']=True
data=bytearray(96*1024**2)
for i in range(0,len(data),4096):data[i]=1
out['own_peak_allocated']=peak_rss_bytes()
del data;gc.collect();out['own_peak_after_free']=peak_rss_bytes()
try:SolveBudget(rss_mib=64,rss_reader=peak_rss_bytes).check();out['own_peak_rejected']=False
except BudgetExceeded:out['own_peak_rejected']=True
print(json.dumps(out,sort_keys=True))
'''
  result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,timeout=10,check=True,text=True)
  observed=json.loads(result.stdout)
  self.assertGreater(observed['rusage_before'],64*1024**2)
  self.assertLess(observed['exec_peak_before'],64*1024**2)
  self.assertTrue(observed['old_rejected']);self.assertTrue(observed['new_small_passed'])
  self.assertGreater(observed['own_peak_after_free'],64*1024**2);self.assertTrue(observed['own_peak_rejected'])

if __name__=='__main__':unittest.main()
