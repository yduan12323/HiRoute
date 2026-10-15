"""Only tiny marker logic and sleeping dummy children; no production runner."""
import sys,os,json,time,resource,tempfile,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from phase_supervisor import PhaseWatchdog,publish_exact_start,atomic
IDENTITY=dict(method='flat',manifest_sha256='a'*64,effective_query_sha256='b'*64,
              domain_sha256='c'*64,source_closure_sha256='d'*64)
class Tests(unittest.TestCase):
 receipts=[]
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.path=self.root/'exact_started.json';self.start=10_000_000_000
 def marker(self,seconds=.2,**changes):
  v=dict(IDENTITY,schema='hiroute.exact_started.v1',worker_pid=1234,parent_pid=os.getpid(),started_monotonic_ns=self.start+int(seconds*1e9));v.update(changes);atomic(self.path,v)
 def watchdog(self):return PhaseWatchdog(self.path,IDENTITY,1,.5)
 def check(self,w,seconds):return w.check(worker_pid=1234,supervisor_started_ns=self.start,now_ns=self.start+int(seconds*1e9))
 def test_early_latched_phase_and_fast_stage_overwrite(self):
  w=self.watchdog();self.marker();self.assertIsNone(self.check(w,.3))
  for text in ['exact_engine_returned','terminal_checked']:(self.root/'stage.json').write_text(text)
  self.assertIsNone(self.check(w,.6));self.assertEqual(self.check(w,.7),'exact_wall_timeout');self.assertEqual(w.started_ns,self.start+200_000_000)
 def test_absent_and_late_marker_preparation_timeout(self):
  self.assertEqual(self.check(self.watchdog(),1),'preparation_wall_timeout')
  self.marker(1.1);self.assertEqual(self.check(self.watchdog(),1.2),'preparation_wall_timeout')
 def test_identity_future_and_old_stamp_invalid(self):
  for changes in [dict(domain_sha256='e'*64),dict(worker_pid=999),dict(parent_pid=999),dict(source_closure_sha256='f'*64),dict(started_monotonic_ns=self.start-1),dict(started_monotonic_ns=self.start+500_000_000)]:
   with self.subTest(changes=changes):
    self.marker(**changes)
    with self.assertRaises(ValueError):self.check(self.watchdog(),.3)
 def test_replacement_and_deletion_never_reset_clock(self):
  w=self.watchdog();self.marker();self.check(w,.3);self.marker(.4)
  with self.assertRaisesRegex(ValueError,'changed'):self.check(w,.5)
  w=self.watchdog();self.check(w,.5);self.path.unlink()
  with self.assertRaisesRegex(ValueError,'disappeared'):self.check(w,.6)
 def test_no_replace_publisher(self):
  publish_exact_start(self.path,IDENTITY);before=self.path.read_bytes()
  with self.assertRaises(FileExistsError):publish_exact_start(self.path,IDENTITY)
  self.assertEqual(self.path.read_bytes(),before)
 def test_oversized_symlink_and_invalid_json(self):
  for data in [b'x'*8193,b'{bad']:
   self.path.write_bytes(data)
   with self.assertRaises(ValueError):self.check(self.watchdog(),.3)
  self.path.unlink();os.mkfifo(self.path)
  with self.assertRaises(ValueError):self.check(self.watchdog(),.3)
  self.path.unlink();target=self.root/'target';target.write_text('{}');self.path.symlink_to(target)
  with self.assertRaises(OSError):self.check(self.watchdog(),.3)
 def test_dummy_worker_timeouts_and_cleanup(self):
  for mode,expected in [('preparation','preparation_wall_timeout'),('exact','exact_wall_timeout'),('invalid','supervisor_exception'),('total','total_wall_timeout'),('missing','missing_exact_start')]:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp);marker=base/'exact_started.json'
    worker=f'''import sys,time,subprocess,resource
sys.path.insert(0,{str(ROOT)!r})
from phase_supervisor import publish_exact_start
assert resource.getrlimit(resource.RLIMIT_CPU)==(3,4)
subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
'''
    if mode not in ('preparation','missing'):
     identity=dict(IDENTITY)
     if mode=='invalid':identity['domain_sha256']='wrong'
     worker+=f'publish_exact_start({str(marker)!r},{identity!r})\n'
    worker+=('time.sleep(.08)\n' if mode=='missing' else 'time.sleep(10)\n')
    code=f'''import sys,os,json,resource
sys.path.insert(0,{str(ROOT)!r})
from phase_supervisor import run,Limits,PhaseWatchdog
w=PhaseWatchdog({str(marker)!r},{IDENTITY!r},.4,.15 if {mode!r}!='total' else 1)
r=run([sys.executable,'-c',{worker!r}],output_dir={str(base/'receipt')!r},limits=Limits(.25 if {mode!r}=='total' else 2,3,128*1024**2,min(os.sched_getaffinity(0)),.5),parent_cpu_limit=(2,3),phase_watchdog=w)
assert r['reason']=={expected!r},r
assert r['cleanup_verified'] and len(r['observed_pids'])>=2,r
assert resource.getrlimit(resource.RLIMIT_CPU)==(2,3)
print(json.dumps(r))
'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=4)
    self.assertEqual(result.returncode,0,result.stderr)
    receipt=json.loads(result.stdout);self.assertTrue(receipt['cleanup_verified']);self.receipts.append(dict(mode=mode,receipt=receipt))
 def test_success_artifacts_without_marker_rejected(self):
  import run_diagnostics as controller
  for name in ['feasible_incumbent.json','landmark_certificate.json','runtime_policy.json','exact_result.json']:
   (self.root/name).write_text('{}')
  with self.assertRaisesRegex(ValueError,'exact-start marker'):controller.setup_state(self.root,success=True)
 def test_new_ledger_reservations_and_no_retry(self):
  from unittest.mock import patch
  import run_diagnostics as controller
  spec=dict(schema='hiroute.exact_search_cache2_phase.v1',progress_enabled=True,
   containment={'rlimit_cpu':[295,296],'preparation_wall_s':180,'exact_wall_s':120,'total_wall_s':300,'parent_cpu':[50,60],'address_space_bytes':8*1024**3,'cleanup_s':3},
   effective_exact_query_sha256='b'*64,domain_binding={'sparse_domain_sha256':'c'*64},source_sha256={})
  manifest=self.root/'diagnostics_manifest.json';atomic(manifest,spec);digest=controller.sha(manifest)
  def fake_run(argv,**kwargs):
   Path(argv[2]).mkdir()
   self.assertEqual(kwargs['limits'].cpu_seconds,295);self.assertEqual(kwargs['limits'].wall_seconds,300)
   self.assertEqual(kwargs['parent_cpu_limit'],(50,60))
   return dict(reason='preparation_wall_timeout',cleanup_verified=True,conservative_wait4_cpu_seconds=.01)
  with patch.object(controller,'ROOT',self.root),patch.object(controller,'run',side_effect=fake_run),patch.object(controller.resource,'setrlimit'),patch.object(controller.os,'sched_setaffinity'),patch.object(controller.signal,'signal'):
   for method in ('flat','hier'):
    with patch.object(controller.sys,'argv',['run_diagnostics.py',method,'--approved-manifest-sha256',digest]):controller.main()
   ledger=json.loads((self.root/'diagnostics_ledger.json').read_text())
   self.assertEqual(ledger['method_reservations'],{'flat':370,'hier':370});self.assertEqual(ledger['total_reserved_and_preparation_cpu_s'],860)
   self.assertEqual([x['method'] for x in ledger['attempts']],['flat','hier']);self.assertFalse(ledger['blocked'])
   with patch.object(controller.sys,'argv',['run_diagnostics.py','flat','--approved-manifest-sha256',digest]):
    with self.assertRaisesRegex(ValueError,'unused reservation'):controller.main()
  self.assertFalse((self.root/'exact_ledger.json').exists())
if __name__=='__main__':
 result=unittest.main(verbosity=2,exit=False)
 (ROOT/'controller_dummy_receipts.json').write_text(json.dumps(Tests.receipts,indent=2))
 sys.exit(not result.result.wasSuccessful())
