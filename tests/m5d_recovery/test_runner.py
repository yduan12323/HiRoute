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
        self.assertTrue(all(x['status']=='BLOCKED_COMMON_PREPARATION' for x in result['arms']))
        self.assertEqual(setlimit.call_args.args[1][1],resource.RLIM_INFINITY)

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
