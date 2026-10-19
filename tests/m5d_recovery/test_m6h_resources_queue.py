import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from experiments.m6h_manifest_v1 import resources, queue, supervisor
from experiments.m6h_manifest_v1.contract import plan


class SyntheticAdapter:
    def __init__(self,no_seed=False,contradiction=False):
        self.no_seed=no_seed; self.contradiction=contradiction; self.calls=[]
    def command(self,domain,row,context):
        self.calls.append(row['id'])
        return {'argv':[sys.executable,'-c','pass'], 'phase_budget':
            supervisor.PhaseBudget(1200,{'nonce':'test'}) if row['operation']=='search' else None}
    def admit(self,domain,row,context,receipt,directory):
        if self.contradiction: raise ValueError('full key contradiction')
        if row['operation']=='prepare':
            return {'status':'seed_exhausted_unknown' if self.no_seed else 'common_feasible_seed',
                    'common':None if self.no_seed else {'seed':domain['id']}}
        if row['operation']=='search':
            return {'status':'exact_attained','replay_required':True}
        return {'status':'certified'}


def fake_executor(**kw):
    assert kw['limits'].cpu==5
    assert kw['limits'].address_space_bytes==8*1024**3
    return {'status':'SUCCESS','cleanup_verified':True,'reason':'success'}


class QueueTests(unittest.TestCase):
    def run_queue(self,adapter,**kw):
        with tempfile.TemporaryDirectory() as d:
            return queue.run_plan(plan(),Path(d)/'out',adapter,cpu=5,executor=fake_executor,**kw)
    def test_all_fixed_slots_and_balanced_order(self):
        a=SyntheticAdapter(); ledger=self.run_queue(a)
        self.assertEqual(len(a.calls),156)
        self.assertEqual(len(ledger['methods']),60)
        self.assertEqual(sum(s['operation']=='ref' for s in ledger['stages']),6)
        self.assertEqual(ledger['status'],'FINISHED_WITH_RETAINED_OUTCOMES')
        self.assertEqual([d['candidate_count'] for d in plan()['domains']], [8]*6+[32]*12+[128]*12)
        main=[d for d in plan()['domains'] if not d['ref']]
        self.assertEqual(sum(d['method_order'][0]=='flat' for d in main),12)
    def test_no_seed_keeps_denominators(self):
        a=SyntheticAdapter(no_seed=True); r=self.run_queue(a)
        self.assertEqual(len(a.calls),30)
        self.assertEqual(sum(s['status']=='BLOCKED_NO_COMMON_SEED' for s in r['stages']),126)
        self.assertEqual(len(r['methods']),60)
    def test_contradiction_stops_without_retry(self):
        a=SyntheticAdapter(contradiction=True); r=self.run_queue(a)
        self.assertEqual(len(a.calls),1)
        self.assertEqual(r['status'],'INTEGRITY_FAILED')
    def test_budget_reserves_whole_domain_before_launch(self):
        a=SyntheticAdapter(); r=self.run_queue(a,budget=resources.Budget(100,100))
        self.assertEqual(a.calls,[])
        self.assertEqual(r['status'],'GLOBAL_BUDGET_BLOCKED')
        self.assertEqual(len(r['stages']),156)
    def test_ordinary_timeout_retained_next_method_runs(self):
        a=SyntheticAdapter(); calls=[]
        def execute(**kw):
            calls.append(kw)
            if len(calls)==2:return {'status':'TIMEOUT','reason':'tree_cpu_timeout','cleanup_verified':True}
            return fake_executor(**kw)
        with tempfile.TemporaryDirectory() as d:
            r=queue.run_plan(plan(),Path(d)/'out',a,cpu=5,executor=execute)
        self.assertEqual(r['stages'][1]['status'],'TIMEOUT')
        self.assertEqual(r['stages'][2]['status'],'BLOCKED_SEARCH_FAILED')
        self.assertEqual(r['stages'][3]['status'],'exact_attained')
        self.assertEqual(len(calls),155)
    def test_unknown_cleanup_stops_all(self):
        with tempfile.TemporaryDirectory() as d:
            r=queue.run_plan(plan(),Path(d)/'out',SyntheticAdapter(),cpu=5,
                executor=lambda **kw:{'status':'FAILED','cleanup_verified':False})
        self.assertEqual(r['status'],'CLEANUP_UNKNOWN')
    def test_reservations_do_not_debit_actual_cpu(self):
        with patch.object(resources,'cpu_total',return_value=100),patch.object(resources.time,'monotonic',return_value=100):
            b=resources.Budget(); r=b.reserve_domain(['prepare','search','replay','search','replay','ref'])
            self.assertTrue(r['admitted']); self.assertEqual(r['cpu_seconds'],4080)
            self.assertEqual(b.measured(),{'cpu_seconds':0,'wall_seconds':0})
    def test_untyped_worker_failure_stops(self):
        with tempfile.TemporaryDirectory() as d:
            r=queue.run_plan(plan(),Path(d)/'out',SyntheticAdapter(),cpu=5,
                executor=lambda **kw:{'status':'FAILED','reason':'worker_failed','cleanup_verified':True})
        self.assertEqual(r['status'],'UNEXPECTED_WORKER_FAILURE')
    def test_real_entry_requires_enclosing_budget(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'enclosing budget'):
                queue.run_plan(plan(),Path(d)/'out',SyntheticAdapter())
    def test_input_failure_retains_slots_without_reservation(self):
        a=SyntheticAdapter(); seen=[]
        def preflight(domain,context):
            seen.append(domain['id'])
            if domain['id']==plan()['domains'][0]['id']:
                return {'status':'FAILED_INPUT','reason_code':'insufficient_candidates'}
        a.preflight=preflight
        r=self.run_queue(a)
        self.assertEqual(len(seen),30)
        self.assertEqual(len(a.calls),150)
        self.assertEqual(len(r['domain_reservations']),29)
        self.assertEqual(r['stages'][0]['status'],'FAILED_INPUT')
        self.assertTrue(all(x['status']=='BLOCKED_INPUT_FAILED' for x in r['stages'][1:6]))
        self.assertTrue(all(x['status']=='BLOCKED_INPUT_FAILED' for x in r['methods'][:2]))
        self.assertEqual(len(r['stages']),156)
        self.assertEqual(len(r['methods']),60)
        self.assertEqual(r['status'],'FINISHED_WITH_RETAINED_OUTCOMES')
    def test_malformed_preflight_stops(self):
        for result in ({'status':'SUCCESS'}, {'status':'FAILED_INPUT'}, False,
                       {'status':'FAILED_INPUT','reason_code':'x','value':float('nan')}):
            with self.subTest(result=result):
                a=SyntheticAdapter(); a.preflight=lambda d,c:result
                r=self.run_queue(a)
                self.assertEqual(a.calls,[])
                self.assertEqual(r['domain_reservations'],[])
                self.assertEqual(r['status'],'INTEGRITY_FAILED')
    def test_preflight_drift_stops(self):
        a=SyntheticAdapter()
        def preflight(domain,context): raise ValueError('Frozen record changed')
        a.preflight=preflight
        self.assertEqual(self.run_queue(a)['status'],'INTEGRITY_FAILED')
        self.assertEqual(a.calls,[])
    def test_preflight_cpu_is_charged_even_when_input_failed(self):
        with patch.object(resources,'cpu_total',return_value=0) as measured_cpu:
            budget=resources.Budget(10,100)
            a=SyntheticAdapter(); calls=[]
            def preflight(domain,context):
                calls.append(domain['id']); measured_cpu.return_value=11
                return {'status':'FAILED_INPUT','reason_code':'insufficient_candidates'}
            a.preflight=preflight
            r=self.run_queue(a,budget=budget)
            self.assertEqual(len(calls),1)
            self.assertEqual(a.calls,[])
            self.assertEqual(r['domain_reservations'],[])
            self.assertEqual(r['status'],'GLOBAL_BUDGET_EXHAUSTED')
    def test_exhausted_budget_skips_preflight(self):
        with patch.object(resources,'cpu_total',return_value=0) as measured_cpu:
            budget=resources.Budget(10,100); measured_cpu.return_value=11
            a=SyntheticAdapter(); a.preflight=lambda d,c:self.fail('Must not run preflight')
            r=self.run_queue(a,budget=budget)
            self.assertEqual(r['status'],'GLOBAL_BUDGET_EXHAUSTED')
    def test_budget_expansion_forbidden(self):
        with self.assertRaises(ValueError):resources.Budget(144001,172800)


def available_fixture_cpu():
    """Positive subprocess fixtures follow host cpusets; real CPU0 stays fixed."""
    allowed=os.sched_getaffinity(0)
    if not allowed:raise RuntimeError('No CPU available for positive fixture')
    return min(allowed)


class SupervisorTests(unittest.TestCase):
    def test_positive_fixture_respects_restricted_cpuset(self):
        with patch.object(os,'sched_getaffinity',return_value={2,3}):
            self.assertEqual(available_fixture_cpu(),2)
        with patch.object(os,'sched_getaffinity',return_value={0,1}):
            self.assertEqual(available_fixture_cpu(),0)
    def test_unavailable_affinity_still_rejected(self):
        unavailable=max(os.sched_getaffinity(0))+1
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'out'
            with self.assertRaisesRegex(ValueError,'Unavailable CPU'):
                supervisor.run([sys.executable,'-c','pass'],output_dir=path,
                    limits=supervisor.Limits(1,1,256*1024**2,unavailable))
            self.assertFalse(path.exists())
    def run_worker(self,source,**kw):
        with tempfile.TemporaryDirectory() as d:
            return supervisor.run([sys.executable,'-c',source],output_dir=Path(d)/'out',
                limits=supervisor.Limits(2,1,256*1024**2,available_fixture_cpu()),
                prelaunch_available_bytes=1,available_stop_bytes=1,**kw)
    def test_fresh_subprocess_measured(self):
        source="import os,json; open(os.environ['HIROUTE_WORKER_RECEIPT'],'w').write(json.dumps({'status':'COMPLETED'}))"
        r=self.run_worker(source)
        self.assertEqual(r['status'],'SUCCESS'); self.assertTrue(r['cleanup_verified'])
        self.assertGreater(r['accounted_owned_cpu_seconds'],0)
        self.assertFalse(r['aggregate_memory_hard_limit'])
    def test_sampled_tree_rss_abort(self):
        r=self.run_worker('import time; time.sleep(5)',tree_rss_stop_bytes=1)
        self.assertEqual(r['reason'],'sampled_tree_rss_limit'); self.assertTrue(r['cleanup_verified'])
    def test_global_cpu_abort(self):
        r=self.run_worker('while True: pass',global_cpu_remaining=.02)
        self.assertEqual(r['reason'],'global_cpu_timeout'); self.assertTrue(r['cleanup_verified'])
    def test_memory_preflight_no_output_or_launch(self):
        with tempfile.TemporaryDirectory() as d,patch.object(supervisor,'memory_available',return_value=0):
            path=Path(d)/'out'
            with self.assertRaises(MemoryError):
                supervisor.run([sys.executable,'-c','pass'],output_dir=path,limits=supervisor.Limits(1,1,256*1024**2,available_fixture_cpu()))
            self.assertFalse(path.exists())
    def test_nested_accounting_not_receipt_sum(self):
        source="import subprocess,sys,os,json; subprocess.run([sys.executable,'-c','sum(range(2000000))']); open(os.environ['HIROUTE_WORKER_RECEIPT'],'w').write(json.dumps({'status':'COMPLETED'}))"
        r=self.run_worker(source)
        self.assertEqual(r['status'],'SUCCESS'); self.assertTrue(r['cleanup_verified'])
        self.assertGreater(r['accounted_owned_cpu_seconds'],.01)

if __name__=='__main__':unittest.main()
