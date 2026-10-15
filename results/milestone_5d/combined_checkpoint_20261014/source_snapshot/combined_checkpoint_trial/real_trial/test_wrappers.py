"""Tiny wrapper/ledger tests. Never loads a production graph or native binary."""
import ast,importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import run_stage as runner
from phase_supervisor import atomic

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'trial';self.root.mkdir()
        self.spec=dict(schema='hiroute.combined_checkpoint_launch.v1',launchable=True,source_sha256={},effective_exact_query_sha256='a'*64,
            domain_binding={'sparse_domain_sha256':'b'*64})
        atomic(self.root/'launch_manifest.json',self.spec);self.digest=runner.sha(self.root/'launch_manifest.json');self.calls=[]
    def fake_run(self,argv,**kw):
        out=Path(argv[2]);out.mkdir();method,mode=argv[4],argv[6]
        guard=json.loads(os.read(kw['pass_fds'][0],16384))
        self.assertEqual(guard,dict(parent_pid=os.getpid(),manifest_sha256=self.digest,method=method,mode=mode))
        limits=kw['limits'];self.calls.append((method,mode,limits,kw))
        self.assertEqual(limits.address_space_bytes,8*1024**3)
        if mode=='search':
            self.assertEqual((limits.wall_seconds,limits.cpu_seconds),(300,295));self.assertIsNotNone(kw['phase_watchdog'])
            atomic(out/'exact_result.json',{'status':'attained_optimum'})
        else:
            self.assertEqual((limits.wall_seconds,limits.cpu_seconds),(120,115));self.assertIsNone(kw['phase_watchdog'])
            atomic(out/'verification_result.json',{'status':'verified_feasible_only'})
        return dict(reason='success',conservative_wait4_cpu_seconds=.01,cleanup_verified=True,phase_watchdog={'marker':{'validated':True}})
    def invoke(self,method,mode,run=None):
        with patch.object(runner,'ROOT',self.root),patch.object(runner.resource,'setrlimit'),patch.object(runner.os,'sched_setaffinity'),\
             patch.object(runner,'run',side_effect=run or self.fake_run),patch.object(sys,'argv',['run_stage.py',method,mode,'--approved-manifest-sha256',self.digest,'--exclusive-slot-granted']):
            runner.main()
    def test_all_four_stages_unique_sequential_separately_charged(self):
        for method,mode in runner.ORDER:self.invoke(method,mode)
        ledger=json.loads((self.root/'ledger.json').read_bytes())
        self.assertFalse(ledger['blocked']);self.assertEqual(len(ledger['attempts']),4)
        self.assertEqual([r['reserved_cpu_s'] for r in ledger['attempts']],[370,150,370,150])
        self.assertEqual(ledger['total_reserved_cpu_s'],1160)
        with self.assertRaises(ValueError):self.invoke('flat','search')
    def test_wrong_order_and_failed_cleanup_block_later_stages(self):
        with self.assertRaises(ValueError):self.invoke('hier','search')
        def bad(*a,**kw):
            receipt=self.fake_run(*a,**kw);receipt['cleanup_verified']=False;return receipt
        self.invoke('flat','search',bad)
        with self.assertRaises(ValueError):self.invoke('flat','verify')
    def test_timeout_is_censored_not_exact_completion(self):
        def timeout(argv,**kw):
            Path(argv[2]).mkdir()
            return dict(reason='exact_wall_timeout',conservative_wait4_cpu_seconds=.01,cleanup_verified=True)
        self.invoke('flat','search',timeout)
        row=json.loads((self.root/'ledger.json').read_bytes())['attempts'][0]
        self.assertEqual(row['status'],'resource_censored_incomplete');self.assertIsNone(row['result'])
        self.invoke('flat','verify')
    def test_verifier_timeout_preserves_separate_witness_result(self):
        self.invoke('flat','search')
        def timeout(argv,**kw):
            out=Path(argv[2]);out.mkdir()
            atomic(out/'witness_verification_result.json',{'status':'verified_feasible_only','record_sha256':'c'*64})
            return dict(reason='wall_timeout',conservative_wait4_cpu_seconds=.01,cleanup_verified=True)
        self.invoke('flat','verify',timeout)
        row=json.loads((self.root/'ledger.json').read_bytes())['attempts'][-1]
        self.assertEqual(row['separately_verified_witness']['status'],'verified_feasible_only')
        self.assertFalse(row['layer_recovery_complete']);self.assertIsNone(row['result'])
    def test_success_without_result_blocks(self):
        def missing(argv,**kw):
            Path(argv[2]).mkdir()
            return dict(reason='success',conservative_wait4_cpu_seconds=.01,cleanup_verified=True,phase_watchdog={'marker':{}})
        with self.assertRaises(ValueError):self.invoke('flat','search',missing)
        ledger=json.loads((self.root/'ledger.json').read_bytes());self.assertTrue(ledger['blocked'])
        row=ledger['attempts'][-1];self.assertGreater(row['charged_conservative_cpu_s'],0)
        self.assertIsNotNone(row['receipt']);self.assertEqual(row['charge_kind'],'measured_conservative_receipt_plus_parent')
    def test_prelaunch_failure_preserves_reservation_and_debit(self):
        self.spec['source_sha256']={'does-not-exist.py':'a'*64}
        atomic(self.root/'launch_manifest.json',self.spec);self.digest=runner.sha(self.root/'launch_manifest.json')
        with self.assertRaises(FileNotFoundError):self.invoke('flat','search')
        row=json.loads((self.root/'ledger.json').read_bytes())['attempts'][0]
        self.assertEqual(row['state'],'failed');self.assertEqual(row['reserved_cpu_s'],370)
        self.assertEqual(row['charged_conservative_cpu_s'],370)
        self.assertEqual(row['charge_kind'],'full_reservation_debit_measurement_unavailable')
    def test_worker_syntax_and_mode_guard_paths(self):
        source=(ROOT/'worker.py').read_text();tree=ast.parse(source);compile(tree,str(ROOT/'worker.py'),'exec')
        self.assertIn("sys.argv[5]=='verify'",source)
        self.assertIn("checkpoint_factory=checkpoint_factory",source)
        self.assertIn("load_verified(saved_witness",source)
        self.assertIn("if verifier_router is not None:verifier_router.close()",source)
        self.assertIn("if router is not None:router.close()",source)
        self.assertIn("source_cache_max_bytes=0,source_cache_max_sources=1",source)
        self.assertIn("['-O3','-std=c++17']",source)

if __name__=='__main__':unittest.main(verbosity=2)
