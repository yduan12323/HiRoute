"""Synthetic-only recovery gates: no real PBF, registry or experiments."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/shandong_preprocessing_v1')]
from bounded_io import literal_exclusions, progress, DENSE_FORMAT
from registry_worker import validate
from experiments.m6h_manifest_v1.resources import ContinuationBudget, conservative_transition_debit


class RecoveryTests(unittest.TestCase):
    def test_literal_pushdown_is_subset_not_substring(self):
        self.assertEqual(literal_exclusions({'access':['private'],'highway':['service']}),
                         ['w/access=private','w/highway=service'])
        for value in ('*private*','private,delivery','private;delivery','private=foo'):
            with self.assertRaises(ValueError):literal_exclusions({'access':[value]})
        self.assertIn('pbf_dense_nodes=true',DENSE_FORMAT)

    def test_progress_atomic_bounded_and_previous_survives_error(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'progress.json';progress(p,'before');progress(p,'after',count=2)
            before=p.read_bytes()
            self.assertEqual(json.loads(before)['stage'],'after')
            with self.assertRaises(ValueError):progress(p,'oversize',data='x'*16384)
            self.assertEqual(before,p.read_bytes())
            self.assertEqual(list(Path(d).iterdir()),[p])

    def test_continuation_debit_charged_once_and_deadline(self):
        with patch('time.time',return_value=1000),patch('time.monotonic',return_value=100),patch('experiments.m6h_manifest_v1.resources.cpu_total',return_value=50):
            b=ContinuationBudget(transition_cpu_capacity=9,carried_cpu_seconds=100,transition_utc='1970-01-01T00:16:40Z',deadline_utc='1970-01-01T00:33:20Z')
        with patch('time.time',return_value=1010),patch('time.monotonic',return_value=110),patch('experiments.m6h_manifest_v1.resources.cpu_total',return_value=55):
            self.assertEqual(b.measured()['cpu_seconds'],105)
            self.assertEqual(b.remaining(),(144000-105,990))
            self.assertEqual(b.remaining(),(144000-105,990))
        with patch('time.time',return_value=2001),patch('time.monotonic',return_value=111),patch('experiments.m6h_manifest_v1.resources.cpu_total',return_value=55):
            self.assertLess(b.remaining()[1],0)
        with patch('time.time',return_value=1011),patch('time.monotonic',return_value=112),patch('experiments.m6h_manifest_v1.resources.cpu_total',return_value=55):
            self.assertLess(b.remaining()[1],0)

    def test_exhausted_cpu_and_invalid_transition_cannot_reset(self):
        kw=dict(transition_cpu_capacity=9,carried_cpu_seconds=144000,
                transition_utc='1970-01-01T00:16:40Z',deadline_utc='1970-01-01T00:33:20Z')
        with patch('time.time',return_value=1000),patch('time.monotonic',return_value=100),patch('experiments.m6h_manifest_v1.resources.cpu_total',return_value=50):
            b=ContinuationBudget(**kw)
            self.assertEqual(b.remaining()[0],0)
            for bad in (dict(carried_cpu_seconds=-1),dict(transition_cpu_capacity=0),
                        dict(transition_utc='1970-01-01T00:16:41Z')):
                with self.assertRaises(ValueError):ContinuationBudget(**{**kw,**bad})
        with patch('time.time',return_value=1001),patch('time.monotonic',return_value=101),patch('experiments.m6h_manifest_v1.resources.cpu_total',return_value=51):
            self.assertEqual(b.remaining()[0],-1)

    def test_envelope_explicit_capacity_rounds_up(self):
        kw=dict(prior_debit=10,active_since_utc='2026-01-01T00:00:00Z',transition_utc='2026-01-01T00:00:01.1Z',cpu_capacity=9)
        self.assertEqual(conservative_transition_debit(**kw),28)
        kw['transition_utc']='2025-01-01T00:00:00Z'
        with self.assertRaises(ValueError):conservative_transition_debit(**kw)
        kw['cpu_capacity']=0
        with self.assertRaises(ValueError):conservative_transition_debit(**kw)

    def test_registry_hash_and_schema_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'registry.json';p.write_text('{}')
            sha=hashlib.sha256(p.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'byte digest'):validate(p,'0'*64,sha,1024)
            with self.assertRaisesRegex(ValueError,'canonical'):validate(p,sha,'0'*64,1024)
            with self.assertRaisesRegex(ValueError,'schema'):validate(p,sha,sha,1024)
            with self.assertRaisesRegex(ValueError,'bound'):validate(p,sha,sha,1)

    def test_nested_kill_retains_unbuffered_progress(self):
        # The outer process is disposable: shared supervisor requires no existing children.
        with tempfile.TemporaryDirectory() as d:
            code='''import os,sys
from pathlib import Path
from experiments.m6h_manifest_v1.supervisor import run,Limits,PhaseBudget
worker="import subprocess,sys,time,os; from experiments.m6h_manifest_v1.supervisor import publish_phase_entry; from pathlib import Path; from experiments.shandong_preprocessing_v1.bounded_io import progress; progress(Path(os.environ['HIROUTE_OUTPUT_DIR'])/'graph_progress.json','parser_started'); print('before nested kill'); subprocess.Popen([sys.executable,'-c', 'import time; time.sleep(30)']); publish_phase_entry(); time.sleep(30)"
r=run([sys.executable,'-c',worker],output_dir=sys.argv[1],limits=Limits(wall_seconds=5,cpu_seconds=3,address_space_bytes=2**30,cpu=min(os.sched_getaffinity(0)),cleanup_seconds=1),phase_budget=PhaseBudget(seconds=.2,identity={"nonce":"synthetic-nested-kill"}),owned_temp=True,prelaunch_available_bytes=1,available_stop_bytes=1)
assert r['cleanup_verified'], r
assert r['status']!='SUCCESS' and r['reason']=='phase_timeout',r
assert 'before nested kill' in (Path(sys.argv[1])/'stdout.txt').read_text()
assert 'parser_started' in (Path(sys.argv[1])/'artifacts/graph_progress.json').read_text()
assert (Path(sys.argv[1])/'artifacts/scratch').stat().st_mode & 0o777 == 0o700
'''
            subprocess.run([sys.executable,'-c',code,str(Path(d)/'run')],cwd=ROOT,check=True,timeout=10)


class RegistrySuccessTests(unittest.TestCase):
    def test_one_shot_bound_registry_does_not_return_payload(self):
        categories=['all_geographic_screens','all_route_screen_pairs','all_dev_queries','all_diagnostics','all_candidate_selection']
        endpoint=dict(site_id='synthetic',access_node=0,lat=36,lon=118)
        obj=dict(schema='hiroute.m6h.exposure_registry.v1',
                 coverage=dict(status='complete',reviewer='synthetic-only',scope='recovered_project_development_artifacts',known_missing_artifacts=[],included_categories=categories),
                 sources=[dict(source_id='synthetic',sha256='0'*64)],
                 records=[dict(source_id='synthetic',reason='synthetic',origin=endpoint,destination=endpoint)])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'registry.json';p.write_text(json.dumps(obj))
            byte=hashlib.sha256(p.read_bytes()).hexdigest()
            canonical=hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            result=validate(p,byte,canonical,16384)
            self.assertEqual(result['exposure_pairs'],1)
            self.assertNotIn('records',result)
            env={**os.environ,'HIROUTE_WORKER_RECEIPT':str(Path(d)/'receipt.json')}
            subprocess.run([sys.executable,str(ROOT/'experiments/shandong_preprocessing_v1/registry_worker.py'),'--path',str(p),'--sha256',byte,'--canonical-sha256',canonical,'--max-bytes','16384'],env=env,check=True)
            self.assertEqual(json.loads((Path(d)/'receipt.json').read_text())['result'],result)

if __name__=='__main__':unittest.main()
