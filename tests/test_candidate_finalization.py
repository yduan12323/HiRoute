import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from finalize_candidate_verification import finalize,canonical
from import_strict_candidate import verify_candidate
from run_grounded_lookup_consumer import PRODUCER
from run_shared_leg_pilot import source
from tests import test_import_strict_candidate as import_tests

class FinalizationTests(unittest.TestCase):
    def setUp(self):
        for name in ('Solver','Optimize','Tactic','parse_smt2_file','parse_smt2_string'):
            guard=patch('z3.'+name,side_effect=AssertionError('solver-free'));guard.start();self.addCleanup(guard.stop)
    def fixture(self,root,name='empty_prefix_terminal'):
        args=import_tests.ImportTests().setup_case(root,name);audit=root/'verification'
        comparison=verify_candidate(args[0],args[1],audit,*args[2:])
        ad=dict(expected_import=args[1],bound=str(args[2].upper),consumer_source=source(),producer_source=dict(commit=PRODUCER,dirty=False))
        old={'source':ad['producer_source']}
        return comparison,ad,old,args[5],args[6],audit
    def call(self,args,check=lambda:None,finish=lambda:None):return finalize(*args,check,finish)
    def test_tuple_list_roundtrip_final_paths_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            args=self.fixture(Path(d));self.assertIsInstance(args[0]['result']['witness']['plan'],tuple)
            with patch('finalize_candidate_verification.raw_replay',return_value=['checked']) as paths:
                finish=Mock();result=self.call(args,finish=finish)
                self.assertEqual(result['status'],'COMPLETE');paths.assert_called_once();finish.assert_called_once()
                self.assertEqual(result['output_path_checks'],['checked']);self.assertFalse(result['original_run_completed_in_budget']);self.assertEqual(result['original_run_status'],'UNKNOWN');self.assertFalse(result['optimality_certified'])
                converted=(json.loads(canonical(args[0])),*args[1:]);self.assertEqual(self.call(converted)['status'],'COMPLETE')
            self.assertEqual(canonical({'x':(1,2)}),canonical({'x':[1,2]}))
            with self.assertRaises(ValueError):canonical({'x':float('nan')})
    def test_missing_fields_hash_tampering_and_semantic_tampering(self):
        for mode in ('missing','hash','semantic','provenance'):
            with tempfile.TemporaryDirectory() as d:
                args=self.fixture(Path(d));path=args[-1]/'separate-witness.verified.json';saved=json.loads(path.read_text())
                if mode=='missing':del saved['requires_successful_consumer_terminal']
                elif mode=='hash':saved['result_sha256']='bad'
                else:
                    if mode=='semantic':saved['result']['witness']['initial_wait']='999'
                    else:saved['result']['original_source']={'commit':'wrong','dirty':False}
                    saved['result_sha256']=hashlib.sha256(canonical(saved['result'])).hexdigest();args[0]['result']=saved['result'];args[0]['receipt']['result_sha256']=saved['result_sha256']
                path.write_text(json.dumps(saved))
                with patch('finalize_candidate_verification.raw_replay',side_effect=AssertionError('reject before paths')):
                    with self.assertRaises((ValueError,KeyError)):self.call(args)
    def test_deadlines_and_final_path_failure_never_accept(self):
        with tempfile.TemporaryDirectory() as d:
            args=self.fixture(Path(d));finish=Mock()
            def expired():raise TimeoutError('deadline')
            with self.assertRaises(TimeoutError):self.call(args,expired,finish)
            finish.assert_not_called()
            with patch('finalize_candidate_verification.raw_replay',side_effect=ValueError('raw path discrepancy')) as paths:
                with self.assertRaises(ValueError):self.call(args,finish=finish)
                paths.assert_called_once()
            finish.assert_not_called()
            state={'expired':False}
            def check():
                if state['expired']:raise TimeoutError('final input deadline')
            def ending():state['expired']=True
            with patch('finalize_candidate_verification.raw_replay',return_value=[]):
                with self.assertRaises(TimeoutError):self.call(args,check,ending)
    def test_pending_service_final_paths(self):
        with tempfile.TemporaryDirectory() as d:
            args=self.fixture(Path(d),'directed_unreachable')
            with patch('finalize_candidate_verification.raw_replay',return_value=['verified']) as paths:
                result=self.call(args)
                self.assertEqual(result['status'],'COMPLETE');paths.assert_called_once()
                self.assertEqual(len(paths.call_args.args[2]),2)

    def test_versioned_consumer_import_has_no_execution_side_effect(self):
        import run_separate_candidate_verification as consumer
        self.assertTrue(callable(consumer.run));self.assertTrue(callable(consumer.main))
