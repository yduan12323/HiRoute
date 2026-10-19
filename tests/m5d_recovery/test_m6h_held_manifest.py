"""CPU3, stdlib synthetic contracts/processes only; no graph/native imports."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from experiments.m6h_manifest_v1 import contract as c
from experiments.m6h_manifest_v1.mock_worker import result
from experiments.m6h_manifest_v1.runner import ledger_for, run_mock_plan

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.plan=c.plan(1)
        self.bound=c.BoundSyntheticInput.fixture(self.plan['domains'][0])
        self.common=result(self.bound,'prepare',None,None,'success')

    def test_denominators_order_and_held(self):
        value=c.plan(); ledger=ledger_for(value)
        self.assertEqual(value['denominator'],dict(domains=30,operational_slots=156,method_results=60,reference_results=6,main_domains=24,main_method_results=48))
        self.assertEqual(len(ledger['stages']),156); self.assertEqual(len(ledger['methods']),60)
        for n in (32,128):
            self.assertEqual([d['method_order'][0] for d in value['domains'] if d['candidate_count']==n],['flat','hier']*6)
        for name in ('freeze','consume','generate','execute'):
            with self.assertRaises(PermissionError): getattr(c,name)('/never/open',approved=True)

    def test_plan_drift(self):
        for field,new in [('launchable',True),('retries',1),('max_heavy_workers',True)]:
            damaged=copy.deepcopy(self.plan); damaged[field]=new
            with self.assertRaises(ValueError): c.validate_plan(damaged)
        damaged=copy.deepcopy(self.plan); damaged['domains'].reverse()
        with self.assertRaises(ValueError): c.validate_plan(damaged)

    def test_snapshot_cannot_follow_mutation(self):
        value=self.bound.value(); value['query']['overhead_s']='999'
        self.assertEqual(self.bound.value()['query']['overhead_s'],'2')
        with self.assertRaises(ValueError): c.BoundSyntheticInput(c.canonical(value)).value()

    def test_seed_depth_and_no_seed(self):
        c.admit(self.common,self.bound,'prepare')
        for field,new in [('hmax',3),('fresh_replays',1),('seed','changed')]:
            damaged=copy.deepcopy(self.common); damaged[field]=new
            with self.assertRaises(ValueError): c.admit(damaged,self.bound,'prepare')
        no_seed=result(self.bound,'prepare',None,None,'no_seed'); c.admit(no_seed,self.bound,'prepare')
        no_seed['stream_exhausted']=False
        with self.assertRaises(ValueError): c.admit(no_seed,self.bound,'prepare')
        for overhead,penalty,key in [('0','1','12'),('2','-2','12'),('2','1','-1')]:
            with self.assertRaises(ValueError): c.depth(dict(overhead_s=overhead,lambda_stop_s=penalty),key)

    def test_full_identity_and_replay(self):
        value=result(self.bound,'replay','flat',self.common,'success'); c.admit(value,self.bound,'replay','flat',self.common)
        for field in value['identity']:
            damaged=copy.deepcopy(value); damaged['identity'][field]='changed'
            with self.assertRaises(ValueError): c.admit(damaged,self.bound,'replay','flat',self.common)
        for field,new in [('hmax',3),('common_sha256','x'),('attained',False),('fresh_process_replay',False),('key',['13','0',0,[]])]:
            damaged=copy.deepcopy(value); damaged[field]=new
            with self.assertRaises(ValueError): c.admit(damaged,self.bound,'replay','flat',self.common)

    def run_plan(self,scenarios=None,**kw):
        with tempfile.TemporaryDirectory() as root:
            return run_mock_plan(self.plan,Path(root)/'run',scenarios=scenarios,**kw)

    def test_real_supervisor_success(self):
        ledger=self.run_plan()
        self.assertEqual(len(ledger['stages']),26)
        self.assertTrue(all(m['status']=='MOCK_CERTIFIED' for m in ledger['methods']))
        self.assertTrue(all(s['receipt']['cleanup_verified'] for s in ledger['stages']))
        self.assertEqual(sum(s['operation']=='ref' for s in ledger['stages']),1)

    def test_no_seed_retains_slots_and_continues(self):
        ledger=self.run_plan({'n8-g0-s3_10:prepare:-':'no_seed'})
        self.assertEqual(ledger['stages'][0]['status'],'seed_exhausted_unknown')
        self.assertTrue(all(s['status']=='BLOCKED_NO_COMMON_SEED' for s in ledger['stages'][1:6]))
        self.assertEqual(ledger['methods'][2]['status'],'MOCK_CERTIFIED')

    def test_timeout_cleanup_and_sibling_continuation(self):
        ledger=self.run_plan({'n8-g0-s3_10:search:flat':'timeout'})
        self.assertEqual(ledger['stages'][1]['status'],'TIMEOUT')
        self.assertEqual(ledger['stages'][1]['receipt']['reason'],'phase_timeout')
        self.assertTrue(ledger['stages'][1]['receipt']['cleanup_verified'])
        self.assertEqual(ledger['stages'][2]['status'],'BLOCKED_SEARCH_FAILED')
        self.assertEqual(ledger['methods'][1]['status'],'MOCK_CERTIFIED')

    def test_mock_startup_delay_precedes_exact_phase(self):
        ledger=self.run_plan({'n8-g0-s3_10:search:flat':'startup_delay'})
        stage=ledger['stages'][1]
        self.assertEqual(stage['status'],'exact_attained',stage.get('receipt'))
        self.assertIsNotNone(stage['receipt']['phase_entered_monotonic'])

    def test_drift_stops_whole_queue(self):
        ledger=self.run_plan({'n8-g0-s3_10:search:flat':'drift'})
        self.assertEqual(ledger['status'],'INTEGRITY_FAILED')
        self.assertTrue(all(s['status']=='BLOCKED_INTEGRITY_FAILED' for s in ledger['stages'][2:]))

    def test_reservation_blocks_without_launch(self):
        with patch('experiments.m6h_manifest_v1.runner.run') as launch:
            ledger=self.run_plan(cpu_budget=1); launch.assert_not_called()
        self.assertEqual(ledger['status'],'BUDGET_BLOCKED'); self.assertEqual(len(ledger['stages']),26)

    def test_strict_numeric_and_boolean_contract_types(self):
        for field,new in [('fresh_replays',2.0),('fresh_replays',True),('hmax',4.0),
                          ('hmax',True),('key',['12','0',False,[]]),('key',['12','0',0.0,[]])]:
            damaged=copy.deepcopy(self.common); damaged[field]=new
            with self.subTest(operation='prepare',field=field,value=new):
                with self.assertRaises(ValueError): c.admit(damaged,self.bound,'prepare')
        for op,method in [('search','flat'),('replay','hier'),('ref',None)]:
            value=result(self.bound,op,method,self.common,'success')
            for field,new in [('hmax',4.0),('hmax',True),('key',['12','0',False,[]]),('key',['12','0',0.0,[]])]:
                damaged=copy.deepcopy(value); damaged[field]=new
                with self.subTest(operation=op,field=field,value=new):
                    with self.assertRaises(ValueError): c.admit(damaged,self.bound,op,method,self.common)

    def test_direct_contract_rejects_out_of_scope_domains_and_depth_types(self):
        for field,new in [('candidate_count',7),('candidate_count',8.0),('group_slot',True),('id','arbitrary-real-label')]:
            domain=copy.deepcopy(self.plan['domains'][0]); domain[field]=new
            with self.assertRaises(ValueError): c.BoundSyntheticInput.fixture(domain)
        for field in ('overhead_s','lambda_stop_s'):
            for new in (True,2.0):
                query=dict(overhead_s='2',lambda_stop_s='1'); query[field]=new
                with self.assertRaises(ValueError): c.depth(query,'12')
        for primary in (True,12.0):
            with self.assertRaises(ValueError): c.depth(dict(overhead_s='2',lambda_stop_s='1'),primary)

    def test_infeasibility_contradicts_admitted_seed(self):
        for op,method in [('search','flat'),('ref',None)]:
            value=result(self.bound,op,method,self.common,'success'); value['outcome']='proven_infeasible'
            with self.assertRaises(ValueError): c.admit(value,self.bound,op,method,self.common)

    def test_operation_and_method_vocabulary_is_closed(self):
        for op,method in [('invented',None),('search',None),('replay','ref'),('prepare','flat'),('ref','hier')]:
            value=result(self.bound,op,method,self.common,'success')
            with self.assertRaises(ValueError): c.admit(value,self.bound,op,method,self.common)

    def test_reference_has_own_slot_and_shared_full_depth(self):
        value=result(self.bound,'ref',None,self.common,'success')
        c.admit(value,self.bound,'ref',None,self.common)
        self.assertEqual(c.depth(dict(overhead_s='2',lambda_stop_s='1'),'15'),5)
        for field,new in [('hmax',3),('implementation','replay_is_ref'),('key',['13','0',0,[]])]:
            damaged=copy.deepcopy(value); damaged[field]=new
            with self.assertRaises(ValueError): c.admit(damaged,self.bound,'ref',None,self.common)

    def test_reference_resource_failure_retained(self):
        ledger=self.run_plan({'n8-g0-s3_10:ref:-':'crash'})
        self.assertEqual(ledger['stages'][5]['status'],'FAILED')
        self.assertEqual(ledger['methods'][2]['status'],'MOCK_CERTIFIED')
        self.assertEqual(len(ledger['stages']),26)

    def test_replay_mismatch_blocks_search_admitted_method(self):
        ledger=self.run_plan({'n8-g0-s3_10:replay:flat':'wrong_key'})
        self.assertEqual(ledger['status'],'INTEGRITY_FAILED')
        self.assertEqual(ledger['methods'][0]['status'],'BLOCKED_INTEGRITY_FAILED')

    def test_unverified_cleanup_blocks_whole_queue(self):
        with patch('experiments.m6h_manifest_v1.runner.run',return_value=dict(cleanup_verified=False)) as launch:
            ledger=self.run_plan()
        self.assertEqual(launch.call_count,1); self.assertEqual(ledger['status'],'CLEANUP_UNKNOWN')

if __name__=='__main__': unittest.main()
