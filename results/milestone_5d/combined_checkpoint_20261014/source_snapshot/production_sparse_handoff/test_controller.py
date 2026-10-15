"""Controller-only tests. No graph loading, native build, or solver."""
import sys,os,json,tempfile,subprocess,resource,time,unittest,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT.parent/'optimized_od06_phase2/runner')]
from run_exact import setup_state,compare_rows
class Tests(unittest.TestCase):
 def test_missing_setup_fails_after_engine(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'phases.jsonl').write_text(json.dumps({'stage':'exact_engine_started'})+'\n')
   with self.assertRaises(ValueError):setup_state(p)
 def test_preparation_censor_not_called_equal(self):
  with tempfile.TemporaryDirectory() as d:
   a,b=Path(d)/'a',Path(d)/'b';a.mkdir();b.mkdir()
   self.assertEqual(compare_rows(a,b)['initial_state_comparison'],'unavailable_preparation_censored')
 def test_terminal_disagreement_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   a,b=Path(d)/'a',Path(d)/'b'
   for p in [a,b]:
    p.mkdir()
    for name,value in [('feasible_incumbent.json',{'initial_witness_cache_sha256':'same'}),('landmark_certificate.json',{'certificate':'same'}),('runtime_policy.json',{'region_tree_sha256':'same'}),('exact_result.json',dict(status='attained_optimum',key=['3','1',1,[]],primary_infimum=None,secondary_infimum=None,unattained_component=None))]:
     (p/name).write_text(json.dumps(value))
   self.assertEqual(compare_rows(a,b)['terminal_comparison'],'equal')
   r=json.loads((b/'exact_result.json').read_text());r['key'][0]='4';(b/'exact_result.json').write_text(json.dumps(r))
   with self.assertRaises(ValueError):compare_rows(a,b)
 def test_supervisor_signal_cleanup_and_limit_split(self):
  for sig in ['SIGTERM','SIGXCPU']:
   with self.subTest(signal=sig),tempfile.TemporaryDirectory() as d:
    out=Path(d)/'inner'
    code=f'''import sys,os,signal,threading,time,resource
sys.path.insert(0,{str(ROOT.parent/'optimized_od06_phase2/runner')!r})
from cloud_adapter import run,Limits
def stop():
 time.sleep(.25);os.kill(os.getpid(),signal.{sig})
threading.Thread(target=stop,daemon=True).start()
r=run([sys.executable,'-c','import resource,subprocess,sys,time;assert resource.getrlimit(resource.RLIMIT_CPU)==(3,4);subprocess.Popen([sys.executable,"-c","import time;time.sleep(20)"]);time.sleep(20)'],output_dir={str(out)!r},limits=Limits(3,3,128*1024**2,min(os.sched_getaffinity(0)),.5),parent_cpu_limit=(1,2))
assert r['reason']=='supervisor_exception' and r['cleanup_verified'] and len(r['observed_pids'])>=2
assert resource.getrlimit(resource.RLIMIT_CPU)==(1,2)
'''
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=5)
    self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':
 resource.setrlimit(resource.RLIMIT_CPU,(5,6));unittest.main(verbosity=2)
