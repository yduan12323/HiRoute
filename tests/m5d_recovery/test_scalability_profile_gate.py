"""Tiny native and subprocess observer checks; no production graph is loaded."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from experiments.scalability_profile_v1 import run as gate
from experiments.mechanism_recovery_v1 import run as base
from test_runner import native_test_domain
from timecut5.exact_progress import operation,event


def tiny_domain(path,arm):
    original=native_test_domain(path/'original')
    return gate.ProfileDomain(arm=arm,manifest_binding=base.digest('tiny profile manifest'),
        graph_factory=original.graph_factory,query=json.loads(original.query_bytes),sites=original.sites,
        tree=original.tree,source_hashes=original.source_hashes,cache=path/arm,compiler=original.compiler['compiler'])


def observer(path,interval=.5):
    return gate.ProfileProgress(path,query_sha256='a'*64,domain_sha256='b'*64,source_sha256={},interval=interval)


class ProfileGateTests(unittest.TestCase):
    def test_closed_manifest_fixed_one_factor_and_denominator(self):
        plan=gate.prospective()
        self.assertFalse(plan['launchable']);self.assertFalse(plan['holdout']);self.assertFalse(plan['auto_next_gate'])
        self.assertEqual(plan['denominator']['total_stages'],5);self.assertEqual(plan['candidate_count'],32)
        a,b=[dict(gate.CONFIGS[x]) for x in gate.ARMS]
        a.pop('routing');b.pop('routing');self.assertEqual(a,b)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json';path.write_bytes(base.canonical(plan))
            with self.assertRaisesRegex(ValueError,'not launchable'):gate._manifest(path,base.file_hash(path))
            for field,value in [('observer',{}),('arms',{}),('order',list(reversed(gate.ARMS))),('candidate_count',128)]:
                changed=dict(plan,launchable=True);changed[field]=value;path.write_bytes(base.canonical(changed))
                with self.assertRaisesRegex(ValueError,'policy differs'):gate._manifest(path,base.file_hash(path))

    def test_rate_limit_and_final_snapshot_keep_bounded_output(self):
        with tempfile.TemporaryDirectory() as temp:
            o=observer(Path(temp)/'progress',interval=60)
            @operation('fast_operation')
            def fast():event('count',attempted=1)
            with o:
                for _ in range(2000):fast()
            value=json.loads((o.path/'progress.json').read_bytes())
            self.assertEqual(value['status'],'returned');self.assertEqual(value['active_stack'],[])
            self.assertEqual(value['timings']['fast_operation']['calls'],2000)
            self.assertEqual(value['persist_attempts'],2)
            self.assertGreater(value['rate_limited_calls'],3000)
            self.assertLessEqual(len(value['recent_events']),32)
            self.assertLessEqual((o.path/'progress.json').stat().st_size,262144)
            self.assertIsNone(value['global_open_lower_bound'])

    def test_active_operation_heartbeat_persists_before_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            o=observer(Path(temp)/'progress',interval=.02);observed=[]
            @operation('deliberately_slow_operation')
            def slow():
                time.sleep(.08)
                observed.append(json.loads((o.path/'progress.json').read_bytes()))
            with o:slow()
            self.assertEqual(observed[0]['status'],'running')
            self.assertEqual(observed[0]['active_stack'][-1]['stage'],'deliberately_slow_operation')
            self.assertGreater(observed[0]['persist_attempts'],1)
            self.assertNotIn('deliberately_slow_operation',observed[0]['timings'])
            self.assertIn('deliberately_slow_operation',json.loads((o.path/'progress.json').read_bytes())['timings'])

    def test_hard_kill_keeps_censored_active_stack(self):
        script='''
import sys,time
from pathlib import Path
from experiments.scalability_profile_v1.run import ProfileProgress
from timecut5.exact_progress import operation
p=ProfileProgress(Path(sys.argv[1]),query_sha256='a'*64,domain_sha256='b'*64,source_sha256={},interval=.02)
@operation('blocked_fixture_operation')
def slow():time.sleep(30)
with p:slow()
'''
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'progress'
            process=subprocess.Popen([sys.executable,'-c',script,str(output)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    try:
                        data=json.loads((output/'progress.json').read_bytes())
                        if data['active_stack'] and data['active_stack'][-1]['stage']=='blocked_fixture_operation':break
                    except FileNotFoundError:pass
                    if process.poll() is not None:self.fail(process.stderr.read().decode())
                    time.sleep(.01)
                else:self.fail('No active heartbeat snapshot')
                process.kill();process.wait(timeout=3)
                final=json.loads((output/'progress.json').read_bytes())
                self.assertEqual(process.returncode,-signal.SIGKILL)
                self.assertEqual(final['status'],'running');self.assertTrue(final['active_stack'])
                self.assertNotIn('blocked_fixture_operation',final['timings'])
                self.assertFalse(final['exact_optimum_claimed'])
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=3)
                process.stdout.close();process.stderr.close()

    def test_observer_failure_does_not_change_operation_result(self):
        with tempfile.TemporaryDirectory() as temp:
            o=observer(Path(temp)/'progress')
            @operation('identity')
            def identity():return 42
            with patch('timecut5.exact_progress.os.replace',side_effect=OSError('fixture')):
                with o:self.assertEqual(identity(),42)
            self.assertEqual(o.state['io_error'],'OSError');self.assertEqual(o.state['status'],'returned')

    def test_tiny_native_full_target_common_seed_replay_and_observer(self):
        from timecut5.bounded import _solve_problem
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);domains=[tiny_domain(root,a) for a in gate.ARMS]
            with domains[0].context('verification') as context:
                witness=_solve_problem(domains[0].problem(context),True).result.witness
            seed=domains[0].freeze_seed(witness);keys=[]
            for domain in domains:
                self.assertEqual(domain.freeze_seed(witness),seed)
                with domain.context('verification') as context:self.assertEqual(context.router.mode,'full')
                with domain.context('search') as context:self.assertEqual(context.router.mode,domain.config['routing'])
                output=root/('result-'+domain.arm)
                result=domain.run_arm(domain.arm,seed,output,search_seconds=2)
                recovered=domain.recover_durable(seed,output/'incumbent.json');keys.append(recovered['accepted_key'])
                self.assertEqual(result['accepted_key'],recovered['accepted_key'])
                self.assertEqual(result['Hmax'],seed.max_depth)
                progress=json.loads((output/'progress/progress.json').read_bytes())
                self.assertEqual(progress['status'],'returned');self.assertIsNone(progress['io_error'])
                self.assertEqual(progress['active_stack'],[]);self.assertEqual(progress['configuration'],domain.config)
                self.assertIn('durable_incumbent_callback',progress['timings'])
                self.assertNotIn('source_cache_bytes',progress['postentry_provider_deltas'])
                self.assertIn('source_cache_bytes',progress['provider_end_gauges'])
            self.assertEqual(keys[0],keys[1])
            with self.assertRaises(ValueError):domains[0].recover_durable(seed,root/'result-destination_target_only/incumbent.json')

    def test_receipt_admission_rejects_failed_unknown_mismatched_and_observer_failure(self):
        manifest=dict(gate.prospective(),source=dict(closure_sha256='a'*64))
        stages=[dict(id='prepare-'+gate.CASE,operation='prepare',case=gate.CASE,status='SUCCESS')]
        arms=[]
        for index,strategy in enumerate(gate.ARMS):
            search=dict(status='TIMEOUT',reason='phase_timeout',cleanup_verified=True,phase_entered_monotonic=1,
                phase_budget=dict(seconds=120,identity=dict(case_id=gate.CASE,strategy=strategy,arm_index=str(index),
                    manifest_sha256='sha',source_closure_sha256='a'*64)))
            verified=dict(status='SUCCESS',cleanup_verified=True)
            arms.append(dict(case=gate.CASE,pair=0,strategy=strategy,status='timeout_feasible_only',receipt=search,verification=verified))
            stages.extend([dict(id=f'search-{index}',operation='search',case=gate.CASE,strategy=strategy,status='TIMEOUT'),
                dict(id=f'verify-{index}',operation='verify',case=gate.CASE,strategy=strategy,status='SUCCESS')])
        ledger=dict(status='COMPLETED',denominator=5,stages=stages,arms=arms,
            common={gate.CASE:dict(status='SUCCESS',cleanup_verified=True)})
        mutations=[None,
            lambda x:x['arms'][0]['receipt'].update(status='FAILED'),
            lambda x:x['arms'][1]['receipt'].update(status='UNKNOWN'),
            lambda x:x['stages'][1].update(status='SUCCESS'),
            lambda x:x['arms'][0]['receipt']['phase_budget']['identity'].update(strategy=gate.ARMS[1]),
            lambda x:x['arms'][0]['verification'].update(cleanup_verified=False),
            lambda x:x.update(arms=[]),
        ]
        for mutate in mutations:
            current=copy.deepcopy(ledger)
            if mutate:mutate(current)
            with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest), \
                patch.object(base,'_run_plan',return_value=current), \
                patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only')), \
                patch.object(gate,'read_progress',return_value=dict(status='running')):
                result=gate.run_gate('manifest','sha',temp,2)
            self.assertEqual(result['operational_admission'],mutate is None)
        with tempfile.TemporaryDirectory() as temp,patch.object(gate,'_manifest',return_value=manifest), \
            patch.object(base,'_run_plan',return_value=copy.deepcopy(ledger)), \
            patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only')), \
            patch.object(gate,'read_progress',side_effect=ValueError('Observer failed')):
            result=gate.run_gate('manifest','sha',temp,2)
        self.assertFalse(result['operational_admission']);self.assertEqual(len(result['stages']),5)

    def test_snapshot_requires_bound_identity_and_known_healthy_observer(self):
        manifest=dict(gate.prospective(),source=dict(closure_sha256='c'*64))
        common=dict(query={'x':1},tree_sha256='d'*64,seed=dict(max_depth=2,site_sha256='e'*64,key_bytes='[1, 2, 3, []]',native_sha256='f'*64))
        domain,sources=gate.progress_binding(manifest,gate.ARMS[0],common)
        value=dict(profile_schema=gate.SCHEMA,domain_sha256=domain,source_sha256=sources,arm=gate.ARMS[0],configuration=gate.CONFIGS[gate.ARMS[0]],
            manifest_binding=base.digest(manifest),candidate_count=32,query_sha256=base.digest(common['query']),Hmax=2,
            status='running',io_error=None,sampled_wall_ns=1,active_stack=[{'stage':'active'}],maximum_observed_write_gap_ns=1)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'progress.json';path.write_bytes(base.canonical(value))
            report=gate.read_progress(path,manifest,gate.ARMS[0],common,search_status='TIMEOUT')
            self.assertTrue(report['timeout_snapshot_is_censored']);self.assertFalse(report['terminal_observer_health_proved'])
            for field,bad in [('io_error','OSError'),('heartbeat_error','RuntimeError'),('Hmax',3),('status','error'),('arm',gate.ARMS[1]),('domain_sha256','0'*64),('source_sha256',{})]:
                changed=dict(value);changed[field]=bad;path.write_bytes(base.canonical(changed))
                with self.assertRaises(ValueError):gate.read_progress(path,manifest,gate.ARMS[0],common,search_status='TIMEOUT')


    def test_final_fsync_error_requires_result_health_not_earlier_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            o=observer(Path(temp)/'progress')
            with o:
                pass
            real_fsync=os.fsync
            calls=0
            def fail_directory_fsync(fd):
                nonlocal calls
                calls+=1
                if calls==2:raise OSError('Final directory fsync failed')
                return real_fsync(fd)
            # Recreate exactly the final persist race: file has been replaced,
            # then directory fsync reports failure, latched only after snapshot.
            with patch('timecut5.exact_progress.os.fsync',side_effect=fail_directory_fsync):o.persist()
            disk=json.loads((o.path/'progress.json').read_bytes())
            self.assertEqual(disk['status'],'returned');self.assertIsNone(disk['io_error'])
            self.assertEqual(o.state['io_error'],'OSError')
            manifest=dict(gate.prospective(),source=dict(closure_sha256='c'*64))
            common=dict(query={'x':1},tree_sha256='d'*64,seed=dict(max_depth=2,site_sha256='e'*64,key_bytes='[1, 2, 3, []]',native_sha256='f'*64))
            domain,sources=gate.progress_binding(manifest,gate.ARMS[0],common)
            disk.update(domain_sha256=domain,source_sha256=sources,arm=gate.ARMS[0],configuration=gate.CONFIGS[gate.ARMS[0]],
                manifest_binding=base.digest(manifest),candidate_count=32,query_sha256=base.digest(common['query']),Hmax=2)
            path=o.path/'progress.json';path.write_bytes(base.canonical(disk))
            result=dict(strategy=gate.ARMS[0],configuration=gate.CONFIGS[gate.ARMS[0]],manifest_binding=base.digest(manifest),
                progress_sha256=base.file_hash(path),observer=dict(status='returned',io_error='OSError',heartbeat_error=None))
            with self.assertRaisesRegex(ValueError,'final observer'):
                gate.read_progress(path,manifest,gate.ARMS[0],common,search_status='SUCCESS',completed_result=result)
            result['observer']['io_error']=None
            accepted=gate.read_progress(path,manifest,gate.ARMS[0],common,search_status='SUCCESS',completed_result=result)
            self.assertTrue(accepted['terminal_observer_health_proved'])
            result['progress_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'snapshot hash'):
                gate.read_progress(path,manifest,gate.ARMS[0],common,search_status='SUCCESS',completed_result=result)
            timed=gate.read_progress(path,manifest,gate.ARMS[0],common,search_status='TIMEOUT')
            self.assertTrue(timed['timeout_snapshot_is_censored']);self.assertFalse(timed['terminal_observer_health_proved'])


if __name__=='__main__':unittest.main()
