"""Tiny native integration tests; never load or launch recovered road graph."""
from dataclasses import replace
from fractions import Fraction as R
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
from experiments.mechanism_recovery_v1.run import (NativeDomain, canonical, digest,
    file_hash, original_tree, tree_value, verify_inputs, INPUT_NAMES, depth_bound)
from timecut5.real_legs import RealSite
from timecut5.bounded import _solve_problem
from timecut5.durable_incumbent import load_verified


def graph():
    rows = [(0,1,1,1),(1,2,1,1),(0,2,5,5),(2,0,5,5),(1,0,1,1),(2,1,1,1)]
    arrays = [np.ascontiguousarray([r[i] for r in rows],dtype=np.int64 if i<2 else np.float64) for i in range(4)]
    for array in arrays: array.flags.writeable=False
    return SimpleNamespace(node_count=3,edge_count=len(rows),source=arrays[0],target=arrays[1],weights=dict(travel_time=arrays[2],distance=arrays[3]))


def tree_bytes():
    return canonical(dict(site_ids=['s'],regions=[dict(parent=-1,children=[1,2],members=[0]),dict(parent=0,children=[],members=[]),dict(parent=0,children=[],members=[0])]))


def native_test_domain(path):
    import hashlib
    q=dict(origin='road:0',destination='road:2',H_ref=2,start_time_s=0,
        initial_energy_kwh=1,capacity_kwh=5,minimum_energy_kwh=0,reserve_kwh=1,
        consumption_kwh_per_m=1,overhead_s=2,lambda_stop_s=1,
        charging_segments=[[0,5,1,0]],schedule=None)
    raw=tree_bytes();tree=original_tree(raw,hashlib.sha256(raw).hexdigest(),['s'])
    return NativeDomain(graph_factory=graph,query=q,sites=dict(s=RealSite('s','road:1',('C',))),tree=tree,
        source_hashes=dict(nodes=digest('tiny nodes'),edges=digest('tiny edges')),cache=Path(path))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)

    def test_exact_six_hashes_fail_closed(self):
        bindings={}
        for name in INPUT_NAMES:
            p=self.path/name;p.write_bytes(name.encode());bindings[name]=dict(size=p.stat().st_size,sha256=file_hash(p))
        verify_inputs(self.path,bindings)
        (self.path/'metadata.json').write_bytes(b'bad')
        with self.assertRaises(ValueError):verify_inputs(self.path,bindings)
        bindings.pop('nodes.parquet')
        with self.assertRaises(ValueError):verify_inputs(self.path,bindings)

    def test_original_hierarchy_keeps_empty_nodes_and_ids(self):
        import hashlib
        raw=tree_bytes(); tree=original_tree(raw,hashlib.sha256(raw).hexdigest(),['s'])
        self.assertEqual(tree_value(tree),[0,['s'],[[1,[],[]],[2,['s'],[]]]])
        with self.assertRaises(ValueError):original_tree(raw,'0'*64,['s'])
        with self.assertRaises(ValueError):original_tree(raw,hashlib.sha256(raw).hexdigest(),['s','s'])

    def test_depth_requires_positive_overhead(self):
        self.assertEqual(depth_bound(dict(overhead_s=2,lambda_stop_s=1),(R(8),)),2)
        with self.assertRaises(ValueError):depth_bound(dict(overhead_s=0,lambda_stop_s=1),(R(8),))

    def test_prospective_manifest_is_not_launchable(self):
        from experiments.mechanism_recovery_v1.run import _manifest
        path=Path(__file__).resolve().parents[2]/'experiments/mechanism_recovery_v1/manifest.json'
        with self.assertRaisesRegex(ValueError,'not launchable'):
            _manifest(path,file_hash(path))

    def test_batch_preserves_hard_limit_and_blocked_denominator(self):
        import os,resource
        from unittest.mock import patch
        from experiments.mechanism_recovery_v1.run import run_batch
        manifest=dict(repo=str(self.path),source=dict(closure_sha256='0'*64))
        with patch('experiments.mechanism_recovery_v1.run._manifest',return_value=manifest), \
             patch('experiments.mechanism_recovery_v1.supervisor.run',return_value=dict(status='FAILED')) as launch, \
             patch('os.sched_getaffinity',return_value={0}),patch('os.sched_setaffinity'), \
             patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)), \
             patch('resource.setrlimit') as setlimit,patch('signal.signal'):
            result=run_batch('closed.json','0'*64,self.path/'batch',0)
        self.assertEqual(launch.call_count,3)
        self.assertEqual(len(result['arms']),12)
        self.assertEqual(result['scope'],'full_batch');self.assertEqual(result['denominator'],27)
        self.assertTrue(all(x['status']=='BLOCKED_COMMON_PREPARATION' for x in result['arms']))
        self.assertEqual(setlimit.call_args.args[1][1],resource.RLIM_INFINITY)

    def test_compact_large_artifact_contract(self):
        from experiments.mechanism_recovery_v1.run import result_envelope, load_worker_result
        import copy
        root=self.path/'compact'; artifacts=root/'artifacts'
        (artifacts/'prepared').mkdir(parents=True)
        path=artifacts/'prepared/common.json'
        value=dict(status='common_feasible_seed', sites=[{}]*128, seed=dict(max_depth=33), payload='x'*80000)
        path.write_bytes(canonical(value))
        envelope=result_envelope(artifacts,'prepare','OD02')
        receipt=dict(worker_receipt=dict(status='COMPLETED',result=envelope))
        self.assertLess(len(canonical(receipt)),4096)
        from experiments.mechanism_recovery_v1.supervisor import _json_receipt
        oversized=root/'old-worker.json'
        oversized.write_bytes(canonical(dict(status='COMPLETED',result=value)))
        with self.assertRaises(ValueError):_json_receipt(oversized)
        self.assertEqual(load_worker_result(root,receipt,'prepare','OD02'),value)
        for key,bad in [('path','../common.json'),('path','prepared/other.json'),('size',True),('sha256',0)]:
            changed=copy.deepcopy(receipt);changed['worker_receipt']['result']['artifact'][key]=bad
            with self.assertRaises(ValueError):load_worker_result(root,changed,'prepare','OD02')
        path.write_bytes(canonical(dict(value,payload='y'*80000)))
        with self.assertRaises(ValueError):load_worker_result(root,receipt,'prepare','OD02')
        path.unlink()
        with self.assertRaises(ValueError):load_worker_result(root,receipt,'prepare','OD02')

    def test_cache_capacity_real_metadata_and_policy(self):
        from experiments.mechanism_recovery_v1.run import CACHE_POLICY, cache_capacity
        result=cache_capacity(CACHE_POLICY,5892498)
        self.assertEqual(result['entry_bytes'],188560456)
        self.assertEqual(result['required_bytes'],377120912)
        self.assertEqual(result['byte_capacity'],5)
        for policy in [dict(CACHE_POLICY,source_cache_max_bytes=128*1024**2),
                       dict(CACHE_POLICY,source_cache_max_bytes=0),
                       dict(CACHE_POLICY,source_cache_max_sources=1)]:
            with self.assertRaises(ValueError):cache_capacity(policy,5892498)
        d=native_test_domain(self.path/'cache-readback')
        with d.context('verification') as context:
            for key,value in CACHE_POLICY.items():self.assertEqual(getattr(context.provider,key),value)
        d.cache_policy['source_cache_max_bytes']=1
        with self.assertRaises(ValueError):d.context('verification')

    def gate_call(self, name, replies, artifact_error_at=None):
        import resource
        from unittest.mock import patch
        from experiments.mechanism_recovery_v1.run import run_gate
        manifest=dict(repo=str(self.path),source=dict(closure_sha256='0'*64))
        count=[0]
        def admitted(*args):
            count[0]+=1
            if count[0]==artifact_error_at:raise ValueError('Result artifact digest differs')
            return dict(status='timeout_feasible_only')
        with patch('experiments.mechanism_recovery_v1.run._manifest',return_value=manifest), \
             patch('experiments.mechanism_recovery_v1.run.file_hash',return_value='a'*64), \
             patch('experiments.mechanism_recovery_v1.run.load_worker_result',side_effect=admitted), \
             patch('experiments.mechanism_recovery_v1.supervisor.run',side_effect=replies) as launch, \
             patch('os.sched_getaffinity',return_value={0}),patch('os.sched_setaffinity'), \
             patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)), \
             patch('resource.setrlimit'),patch('signal.signal'):
            result=run_gate('full-closed.json','b'*64,self.path/name,0)
        return result,launch.call_args_list

    def test_gate_artifact_failure_marks_attempted_stage_unknown(self):
        for index in range(1,6):
            result,calls=self.gate_call('artifact-error-'+str(index),[dict(status='SUCCESS')]*index,index)
            self.assertEqual(len(calls),index)
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertEqual(result['stages'][index-1]['status'],'UNKNOWN')
            self.assertEqual(result['stages'][index-1]['reason'],'artifact_admission_failed')
            self.assertTrue(all(row['status']=='PENDING' for row in result['stages'][index:]))

    def test_terminal_cli_exit_status(self):
        from unittest.mock import patch
        from experiments.mechanism_recovery_v1.run import main
        for status,code in [('COMPLETED',0),('UNKNOWN',1),('FAILED_VERIFICATION',1),('PARENT_CPU_BUDGET_EXHAUSTED',1)]:
            with patch('sys.argv',['run','--gate','--output','fresh','--cpu','0']), \
                 patch('experiments.mechanism_recovery_v1.run.run_gate',return_value=dict(status=status)):
                self.assertEqual(main(),code)

    def test_gate_fixed_five_stages_same_common_and_limits(self):
        success=dict(status='SUCCESS')
        verified=dict(status='SUCCESS',worker_receipt=dict(result=dict(status='timeout_feasible_only')))
        result,calls=self.gate_call('gate',[success,dict(status='TIMEOUT'),verified,success,verified])
        self.assertEqual(result['scope'],'od02_gate');self.assertEqual(result['denominator'],5)
        self.assertEqual(result['status'],'COMPLETED')
        self.assertEqual([x['operation'] for x in result['stages']],['prepare','search','verify','search','verify'])
        self.assertEqual([c.args[0][c.args[0].index('--worker')+1] for c in calls],['prepare','arm','verify','arm','verify'])
        for c in calls:self.assertEqual(c.args[0][c.args[0].index('--case')+1],'OD02_energy_only_soc3_10')
        self.assertEqual([c.args[0][c.args[0].index('--strategy')+1] for c in calls[1:]],['indexed','indexed','recompute','recompute'])
        self.assertEqual(calls[1].kwargs['phase_budget'].seconds,120)
        self.assertEqual(calls[3].kwargs['phase_budget'].identity['common_sha256'],calls[1].kwargs['phase_budget'].identity['common_sha256'])
        self.assertNotEqual(calls[3].kwargs['phase_budget'].identity['nonce'],calls[1].kwargs['phase_budget'].identity['nonce'])
        self.assertEqual([c.kwargs['limits'].wall_seconds for c in calls],[600,600,180,600,180])
        self.assertEqual([c.kwargs['limits'].cpu_seconds for c in calls],[600,600,120,600,120])
        self.assertTrue(all(c.kwargs['limits'].address_space_bytes==8*1024**3 for c in calls))
        self.assertEqual(len({str(c.kwargs['output_dir']) for c in calls}),5)
        with self.assertRaises(FileExistsError):self.gate_call('gate',[])

    def test_gate_unknown_stops_preserving_five_stage_denominator(self):
        success=dict(status='SUCCESS')
        for index in range(3):
            with self.subTest(stage=index):
                result,calls=self.gate_call('unknown-'+str(index),[success]*index+[dict(status='UNKNOWN')])
                self.assertEqual(result['status'],'UNKNOWN')
                self.assertEqual(result['denominator'],5)
                self.assertEqual(len(calls),index+1)
                self.assertEqual(sum(x['status']=='PENDING' for x in result['stages']),4-index)

    def test_gate_failed_verification_blocks_second_arm(self):
        result,calls=self.gate_call('failed-verify',[dict(status='SUCCESS'),dict(status='TIMEOUT'),dict(status='FAILED')])
        self.assertEqual(len(calls),3)
        self.assertEqual(result['status'],'FAILED_VERIFICATION')
        self.assertEqual([x['status'] for x in result['stages'][-2:]],['BLOCKED','BLOCKED'])
        result,calls=self.gate_call('failed-prepare',[dict(status='FAILED')])
        self.assertEqual(len(calls),1);self.assertEqual(result['status'],'FAILED_COMMON_PREPARATION')
        self.assertEqual(sum(x['status']=='BLOCKED' for x in result['stages']),4)

    def test_snapshot_missing_or_changed_blob_rejected(self):
        from experiments.mechanism_recovery_v1.run import source_identity
        repo=self.path/'snapshot';(repo/'src/timecut5').mkdir(parents=True)
        (repo/'src/timecut5/a.py').write_text('pass\n')
        publication=dict(commit='1'*40,tree='2'*40,blobs={})
        with self.assertRaisesRegex(ValueError,'closure'):
            source_identity(repo,published_commit='1'*40,publication=publication)
        publication['blobs']['src/timecut5/a.py']='0'*40
        with self.assertRaisesRegex(ValueError,'published blob'):
            source_identity(repo,published_commit='1'*40,publication=publication)

    def test_native_block_timeout_then_separate_verification(self):
        import os,sys,timecut5
        package_parent=Path(timecut5.__file__).resolve().parent.parent
        child_env={'PYTHONPATH':'', 'HIROUTE_TEST_PACKAGE_FILE':str(Path(timecut5.__file__).resolve())}
        from experiments.mechanism_recovery_v1.supervisor import run,Limits,PhaseBudget
        root=Path(__file__).resolve().parents[2]
        child_env['PYTHONPATH']=str(root)+':'+str(package_parent)
        limits=Limits(wall_seconds=30,cpu_seconds=20,address_space_bytes=2*1024**3,cpu=min(os.sched_getaffinity(0)))
        search_code = r"""
import ctypes,json,os
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from tests.m5d_recovery.test_runner import native_test_domain
import timecut5
if str(Path(timecut5.__file__).resolve()) != os.environ['HIROUTE_TEST_PACKAGE_FILE']:raise RuntimeError('Child package provenance differs')
from timecut5.bounded import _solve_problem
out=Path(os.environ['HIROUTE_OUTPUT_DIR'])
d=native_test_domain(out/'native')
with d.context('generation') as c:w=_solve_problem(d.problem(c)).result.witness
seed=d.freeze_seed(w);record=asdict(seed)
for name in ('witness_bytes','key_bytes'):record[name]=record[name].decode()
(out/'seed.json').write_text(json.dumps(record))
def native_block(problem,*args,**kwargs):
    if problem._terminal_energy_screen is None:raise RuntimeError('Energy not active')
    ctypes.CDLL(None).sleep(30)
    raise RuntimeError('Native block should have been killed')
with patch('timecut5.hierarchy._solve_hierarchical_problem',side_effect=native_block):
    d.run_arm('indexed',seed,out/'arm',external_phase=True)
"""
        searched=run([sys.executable,'-c',search_code],output_dir=self.path/'search',limits=limits,cwd=root,
            phase_budget=PhaseBudget(seconds=.1,identity=dict(nonce='tiny-test-owned-nonce',case='tiny',seed='frozen-tiny')),
            extra_env=child_env)
        self.assertEqual(searched['status'],'TIMEOUT');self.assertEqual(searched['reason'],'phase_timeout')
        self.assertTrue(searched['cleanup_verified'])
        verify_code = r"""
import json,os,sys
from pathlib import Path
from tests.m5d_recovery.test_runner import native_test_domain
import timecut5
if str(Path(timecut5.__file__).resolve()) != os.environ['HIROUTE_TEST_PACKAGE_FILE']:raise RuntimeError('Child package provenance differs')
from experiments.mechanism_recovery_v1.run import FrozenSeed
out=Path(os.environ['HIROUTE_OUTPUT_DIR']);source=Path(sys.argv[1])
d=native_test_domain(out/'native');v=json.loads((source/'seed.json').read_text())
for name in ('witness_bytes','key_bytes'):v[name]=v[name].encode()
result=d.recover_durable(FrozenSeed(**v),source/'arm/incumbent.json')
Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_text(json.dumps(dict(status='COMPLETED',result=result)))
"""
        verified=run([sys.executable,'-c',verify_code,str(self.path/'search/artifacts')],output_dir=self.path/'verify',limits=limits,cwd=root,
            extra_env=child_env)
        self.assertEqual(verified['status'],'SUCCESS',verified)
        accepted=verified['worker_receipt']['result']
        self.assertEqual(accepted['accepted_key'],accepted['seed_key'])
        self.assertFalse(accepted['optimality_claim'])

    def test_actual_energy_hier_both_arms_and_fresh_replay(self):
        import hashlib
        q=dict(origin='road:0',destination='road:2',H_ref=2,start_time_s=0,
            initial_energy_kwh=1,capacity_kwh=5,minimum_energy_kwh=0,reserve_kwh=1,
            consumption_kwh_per_m=1,overhead_s=2,lambda_stop_s=1,
            charging_segments=[[0,5,1,0]],schedule=None)
        raw=tree_bytes();tree=original_tree(raw,hashlib.sha256(raw).hexdigest(),['s'])
        domain=NativeDomain(graph_factory=graph,query=q,sites=dict(s=RealSite('s','road:1',('C',))),tree=tree,source_hashes=dict(nodes=digest('tiny nodes'),edges=digest('tiny edges')),cache=self.path/'native')
        with domain.context('generation') as context:
            self.assertIsNone(domain.problem(context)._terminal_energy_screen)
            witness=_solve_problem(domain.problem(context)).result.witness
        seed=domain.freeze_seed(witness)
        with self.assertRaises(ValueError):domain.validate_seed(replace(seed,max_depth=seed.max_depth+1))
        with self.assertRaises(ValueError):domain.validate_seed(replace(seed,native_sha256='0'*64))
        with self.assertRaises(ValueError):domain.validate_seed(replace(seed,query_sha256='0'*64))
        with self.assertRaises(ValueError):domain.validate_seed(replace(seed,key_bytes=b'[]'))
        with domain.context('search') as context:
            self.assertIsNotNone(domain.problem(context)._terminal_energy_screen)
        a=domain.run_arm('indexed',seed,self.path/'indexed')
        b=domain.run_arm('recompute',seed,self.path/'recompute')
        self.assertEqual(a['status'],'attained_optimum')
        self.assertEqual(a['result']['result'],b['result']['result'])
        self.assertEqual(a['seed_key'],b['seed_key'])
        self.assertEqual(a['Hmax'],b['Hmax'])
        self.assertIsNone(a['alt_member_reads']);self.assertIsNone(b['alt_member_reads'])
        record=json.loads((self.path/'indexed/incumbent.json').read_bytes())
        contexts=[]
        def factory():
            c=domain.context('verification');contexts.append(c);return domain.problem(c,seed.max_depth)
        try:
            recovered,key=load_verified(self.path/'indexed/incumbent.json',problem_factory=factory,binding_supplier=lambda:record['payload']['binding'])
            self.assertEqual(recovered.pi,witness.pi)
            self.assertEqual(canonical([str(key[0]),str(key[1]),key[2],[list(p) for p in key[3]]]),seed.key_bytes)
        finally:
            for c in contexts:c.close()
        self.assertTrue(a['durable_writes']>=1)
        import signal, time
        from unittest.mock import patch
        previous=signal.getsignal(signal.SIGALRM)
        with patch('timecut5.hierarchy._solve_hierarchical_problem',side_effect=lambda *a,**kw:time.sleep(.1)):
            timeout=domain.run_arm('indexed',seed,self.path/'timeout',search_seconds=.01)
        self.assertEqual(timeout['status'],'timeout_feasible_only')
        self.assertFalse(timeout['optimality_claim'])
        self.assertFalse(timeout['feasible_improvement'])
        self.assertEqual(timeout['accepted_key'],timeout['seed_key'])
        self.assertEqual(signal.getsignal(signal.SIGALRM),previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))


if __name__=='__main__':unittest.main()
