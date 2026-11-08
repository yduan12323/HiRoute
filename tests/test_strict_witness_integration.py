from fractions import Fraction as F
from pathlib import Path
import json,sys,tempfile,time,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from strict_bound_decision import decide_real
from strict_bound_witness import extract,publish_verified_result
from exact_physical_adapter import Engine,Unknown,replay
from exact_physical_fixtures import case,tiny_table

class IntegrationTests(unittest.TestCase):
    def data(self,name):
        f=case(name);t=tiny_table(f)[0];w=f['upper_witness']
        b=replay(t,f['physics'],w['plan'],w['charges'],w.get('initial_wait',0))['key'][0]
        return (t,f['physics'],w),b
    def run_case(self,data,b,path):return decide_real(lambda check:data,b,path,time.monotonic()+8,extract_witness=True)

    def test_sat_closure_extraction_replay_and_separate_receipts(self):
        data,b=self.data('primary_unattained')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'audit';r=self.run_case(data,b,path)
            self.assertEqual(r['status'],'attained_improvement');self.assertFalse(r['optimality_certified'])
            w=r['witness'];checked=replay(data[0],data[1],w['plan'],w['charges'],w['initial_wait'])
            self.assertLess(checked['key'][0],b);self.assertEqual(str(checked['key'][0]),r['primary_value'])
            self.assertEqual(json.loads((path/'candidate.unverified.json').read_text())['status'],'UNVERIFIED_CANDIDATE')
            saved=json.loads((path/'witness.verified.json').read_text())
            self.assertTrue(saved['requires_successful_consumer_terminal'])
            self.assertEqual(saved['result_sha256'],r['verified_witness_receipt']['result_sha256'])

    def test_unsat_unknown_and_wrong_bound(self):
        data,b=self.data('empty_prefix_terminal')
        with tempfile.TemporaryDirectory() as d:
            r=self.run_case(data,b,Path(d)/'unsat');self.assertEqual(r['status'],'primary_optimal_only')
            self.assertFalse((Path(d)/'unsat/witness.verified.json').exists())
            with patch.object(Engine,'feasible',side_effect=Unknown('solver unknown')):
                self.assertEqual(self.run_case(data,b,Path(d)/'unknown')['status'],'unknown')
            with patch.object(Engine,'feasible',side_effect=AssertionError('must reject before solver')):
                self.assertEqual(self.run_case(data,b+1,Path(d)/'wrong')['status'],'unknown')

    def test_extraction_deadline_and_publication_failure_leave_no_verified_result(self):
        data,b=self.data('primary_unattained')
        def late(*args,**kwargs):
            result=extract(*args,**kwargs);args[-1].__self__.deadline=time.monotonic()-1;return result
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'late'
            with patch('strict_bound_witness.extract',side_effect=late):
                self.assertEqual(self.run_case(data,b,path)['status'],'unknown')
            self.assertTrue((path/'candidate.unverified.json').exists());self.assertFalse((path/'witness.verified.json').exists())
            with patch('strict_bound_witness.publish_verified_result',side_effect=OSError('publication failure')):
                path=Path(d)/'failure';self.assertEqual(self.run_case(data,b,path)['status'],'unknown')
                self.assertFalse((path/'witness.verified.json').exists())

    def test_partial_and_post_link_expiry_cleanup_exclusive_output(self):
        payload={'status':'VERIFIED_ATTAINED_IMPROVEMENT','optimality_certified':False}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'verified.json'
            def broken(value,stream,**kwargs):stream.write('{');raise OSError('partial write')
            with patch('strict_bound_witness.json.dump',side_effect=broken):
                with self.assertRaises(OSError):publish_verified_result(path,payload,lambda:None)
            self.assertFalse(path.exists());self.assertEqual(list(Path(d).iterdir()),[])
            calls=[]
            def late():
                calls.append(1)
                if len(calls)==3:raise TimeoutError('post-link deadline')
            with self.assertRaises(TimeoutError):publish_verified_result(path,payload,late)
            self.assertFalse(path.exists());self.assertEqual(list(Path(d).iterdir()),[])
            path.write_text('prior')
            with self.assertRaises(FileExistsError):publish_verified_result(path,payload,lambda:None)
            self.assertEqual(path.read_text(),'prior')
