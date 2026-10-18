"""Synthetic lifecycle/queue endpoints; no real graph or launch."""
import copy
from pathlib import Path
import resource
import tempfile
import unittest
from unittest.mock import patch
from experiments.dev_coverage_tranche_v1 import run as gate,lifecycle,batch
from experiments.dev_coverage_tranche_v1.bindings import QUEUE,PLAN_SHA256
from experiments.mechanism_recovery_v1 import run as base


def manifest(root):
    m=gate.prospective();m.update(repo=str(root),input_directory=str(root),source={'closure_sha256':'a'*64});return m

def memory():
    return dict(available_bytes=8*1024**3,required_bytes=7168*1024**2,admitted=True,sampled_wall_ns=1,reservation=False,aggregate_hard_limit=False)

def no_seed(m):
    spec=gate.spec_for(m,m['case_id']);q=copy.deepcopy(spec['original_binding']['query']);q['sparse_domain_sha256']='b'*64
    return dict(schema=gate.SCHEMA,status='seed_exhausted_unknown',classification='normal_original_proposal_stream_exhaustion',
        case_id=m['case_id'],candidate_count=m['candidate_count'],case_binding_sha256=base.digest(spec),
        original_query_sha256=spec['original_binding']['query_sha256'],runtime_query_sha256=base.digest(q),query=q,
        tree_sha256=base.digest('tiny-tree'),site_catalog_sha256=spec['original_binding']['site_catalog_sha256'],
        prospective_full_selection_sha256=PLAN_SHA256,manifest_sha256=base.digest(m),source=m['source'],inputs=m['inputs'],
        proposal_count=0,replay_rejections=0,stream_exhausted=True,feasibility='unknown',global_infeasibility_claim=False,
        charged_wall_ns=1,seed_policy=gate.development.POLICY['seed_policy'])


class TrancheLifecycleTests(unittest.TestCase):
    def test_typed_no_seed_exact_schema_identity_and_error_text_rejection(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);m=manifest(root);note=no_seed(m);(root/'hierarchy.json').write_bytes(b'{}')
            with patch.object(gate,'extract_case',return_value=(note['query'], {}, 'tiny-tree')),patch.object(base,'tree_value',return_value='tiny-tree'):
                gate.validate_no_seed(note,m['case_id'],m)
                for change in (dict(status='ValueError incumbent_search_failed'),dict(classification='arbitrary_error'),dict(stream_exhausted=False),
                    dict(proposal_count=1),dict(global_infeasibility_claim=True),dict(manifest_sha256='0'*64),dict(candidate_count=128),dict(error='stream exhausted')):
                    bad=copy.deepcopy(note);bad.update(change)
                    with self.assertRaises(ValueError):gate.validate_no_seed(bad,m['case_id'],m)

    def test_prepare_artifact_envelope_tamper_identity_and_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);m=manifest(root);note=no_seed(m);a=root/'artifacts';(a/'prepared').mkdir(parents=True)
            p=a/'prepared/common.json';p.write_bytes(base.canonical(note));env=gate.result_envelope(a,'prepare',m['case_id']);r=dict(worker_receipt=dict(result=env))
            self.assertEqual(gate.load_worker_result(root,r,'prepare',m['case_id']),note)
            with self.assertRaises(ValueError):gate.load_worker_result(root,r,'prepare',QUEUE[1][0])
            p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(ValueError):gate.load_worker_result(root,r,'prepare',m['case_id'])
            p.unlink();target=root/'other';target.write_bytes(base.canonical(note));p.symlink_to(target)
            with self.assertRaises(ValueError):gate.load_worker_result(root,r,'prepare',m['case_id'])

    def pipeline(self,root,*,exhausted=False,bad_artifact=False,cleanup_at=None,memory_at=None,status_at=None,launch_at=None,cpu=0,hard=resource.RLIM_INFINITY,timeout_reason=None,method_error=False):
        m=manifest(root);seen=[];observed=[]
        def observe(policy):
            r=memory()
            if len(observed)==memory_at:r.update(admitted=False,available_bytes=1)
            observed.append(r);return r
        def launch(argv,*,output_dir,limits,cwd,phase_budget=None):
            i=len(seen);seen.append((argv,limits,phase_budget))
            if i==launch_at:raise RuntimeError('synthetic failure')
            output_dir.mkdir(parents=True)
            if i==0:
                p=output_dir/'artifacts/prepared/common.json';p.parent.mkdir(parents=True);p.write_bytes(b'{}')
            (output_dir/'receipt.json').write_bytes(b'{}')
            return dict(status='TIMEOUT' if i==1 and timeout_reason else 'FAILED' if i==status_at else 'SUCCESS',cleanup_verified=i!=cleanup_at,wall_seconds=1,
                reason=timeout_reason if i==1 and timeout_reason else 'success',phase_entered_monotonic=1,
                phase_budget=None if phase_budget is None else dict(seconds=phase_budget.seconds,identity=phase_budget.identity))
        def load(directory,receipt,op,case,strategy=None):
            if bad_artifact:raise ValueError('incumbent_search_failed: fixed proposal stream exhausted')
            return dict(status='seed_exhausted_unknown' if exhausted and op=='prepare' else 'common_feasible_seed' if op=='prepare' else 'attained_optimum')
        with patch.object(lifecycle,'run',side_effect=launch),patch.object(lifecycle,'available_memory_admission',side_effect=observe), \
            patch.object(gate,'load_worker_result',side_effect=load),patch.object(gate,'validate_no_seed'),patch.object(gate,'validate_common'),patch.object(gate,'admit_method',side_effect=ValueError('synthetic observer failure') if method_error else None), \
            patch.object(lifecycle.os,'sched_getaffinity',return_value={0,3}),patch.object(lifecycle.os,'sched_setaffinity'), \
            patch.object(lifecycle.resource,'getrlimit',return_value=(resource.RLIM_INFINITY,hard)),patch.object(lifecycle.resource,'setrlimit'), \
            patch.object(lifecycle.signal,'signal'),patch.object(lifecycle.threading,'active_count',return_value=1):
            out=lifecycle.run_plan('synthetic.json','f'*64,root/'pair',cpu,manifest_loader=lambda *a:m,expected_limits=gate.LIMITS)
        return out,seen,observed

    def test_five_slots_exact_phase_limits_and_every_worker_memory_gate(self):
        with tempfile.TemporaryDirectory() as t:r,seen,obs=self.pipeline(Path(t))
        self.assertEqual(r['status'],'COMPLETED');self.assertEqual((len(seen),len(obs)),(5,5))
        self.assertEqual([a[a.index('--worker')+1] for a,_,_ in seen],['prepare','arm','verify','arm','verify'])
        self.assertEqual([a[a.index('--strategy')+1] for a,_,_ in seen if '--strategy' in a],['flat','flat','hier','hier'])
        self.assertEqual([(l.wall_seconds,l.cpu_seconds,l.cpu,l.address_space_bytes) for _,l,_ in seen],
            [(600,600,0,8*1024**3),(1500,1500,0,8*1024**3),(180,120,0,8*1024**3),(1500,1500,0,8*1024**3),(180,120,0,8*1024**3)])
        for i in (1,3):self.assertEqual((seen[i][2].seconds,seen[i][2].identity['candidate_count']),(1200,'32'))

    def test_clean_no_seed_is_one_failed_slot_and_four_blocked_descendants(self):
        with tempfile.TemporaryDirectory() as t:r,seen,obs=self.pipeline(Path(t),exhausted=True)
        self.assertEqual((len(seen),len(obs)),(1,1));self.assertEqual(r['status'],'FAILED_PREPARATION_NO_SEED')
        self.assertEqual([s['status'] for s in r['stages']],['FAILED_NO_SEED']+['BLOCKED_NO_COMMON_SEED']*4)
        self.assertEqual([s['status'] for s in r['arms']],['BLOCKED_NO_COMMON_SEED']*2)

    def test_arbitrary_failure_cleanup_memory_and_unknown_stop_without_retry(self):
        for kwargs,status,count in [({'bad_artifact':True},'UNKNOWN',1),({'cleanup_at':0},'UNKNOWN',1),({'memory_at':0},'BLOCKED_MEMORY_PLANNING',0),
            ({'memory_at':2},'BLOCKED_MEMORY_PLANNING',2),({'status_at':0},'FAILED_COMMON_PREPARATION',1),({'launch_at':0},'UNKNOWN',1),
            ({'cpu':3},'UNKNOWN',0),({'hard':1500},'UNKNOWN',0)]:
            with self.subTest(kwargs=kwargs),tempfile.TemporaryDirectory() as t:
                r,seen,_=self.pipeline(Path(t),**kwargs);self.assertEqual((r['status'],len(seen)),(status,count))
                self.assertEqual(len(r['stages']),5);self.assertNotIn('PENDING',[s['status'] for s in r['stages']])

    def test_only_phase_timeout_can_start_replay_and_method_integrity_precedes_HIER(self):
        for reason,status,count in [('phase_timeout','COMPLETED',5),('wall_timeout','FAILED_SEARCH_PHASE_ADMISSION',2),('cpu_limit','FAILED_SEARCH_PHASE_ADMISSION',2)]:
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as t:
                r,seen,_=self.pipeline(Path(t),timeout_reason=reason);self.assertEqual((r['status'],len(seen)),(status,count))
        with tempfile.TemporaryDirectory() as t:
            r,seen,_=self.pipeline(Path(t),method_error=True)
            self.assertEqual((r['status'],len(seen)),('FAILED_METHOD_INTEGRITY_ADMISSION',3))
            self.assertEqual([s['status'] for s in r['stages'][3:]],['BLOCKED_METHOD_INTEGRITY_ADMISSION']*2)

    def test_failed_no_seed_admission_is_scientific_failure_and_cleanup_required(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);m=manifest(root);c=m['case_id'];r=lifecycle.pair_ledger('f'*64,c,32)
            r.update(status='FAILED_PREPARATION_NO_SEED',common={c:dict(status='SUCCESS',cleanup_verified=True)})
            r['stages'][0]['status']='FAILED_NO_SEED'
            for s in r['stages'][1:]+r['arms']:s['status']='BLOCKED_NO_COMMON_SEED'
            r['memory_admissions']=[dict(stage='prepare-'+c,**memory())]
            with patch.object(gate,'load_worker_result',return_value=no_seed(m)),patch.object(gate,'validate_no_seed'),patch.object(base,'file_hash',return_value='a'*64):
                o=gate.admit_no_seed_pair(r,m,'f'*64,root);self.assertTrue(o['clean_expected_no_seed']);self.assertFalse(o['operational_admission'])
                self.assertFalse(o['both_authenticated_complete']);self.assertEqual((o['blocked_searches'],o['blocked_replays'],o['feasibility']),(2,2,'unknown'))
                r['common'][c]['cleanup_verified']=False;self.assertFalse(gate.admit_no_seed_pair(r,m,'f'*64,root)['clean_expected_no_seed'])

    def queue(self,root,unsafe_at=None,unclean_at=None,overrun_at=None):
        ds=[dict(index=i,case_id=c,candidate_count=n,manifest=f'/synthetic/{i}.json',sha256=str(i)*64) for i,(c,n) in enumerate(QUEUE)]
        m=dict(queue=ds,repo=str(root));seen=[]
        def launch(argv,*,output_dir,cwd,limits,extra_env):
            i=len(seen);seen.append((argv,limits,extra_env));p=output_dir/'artifacts/pair';p.mkdir(parents=True);(p/'ledger.json').write_bytes(b'{}')
            return dict(status='SUCCESS',cleanup_verified=i!=unclean_at,wall_seconds=4321 if i==overrun_at else 1)
        def load(directory,receipt):
            if receipt['cleanup_verified'] is not True:raise ValueError('cleanup unknown')
            i=len(seen)-1;c,n=QUEUE[i];r=lifecycle.pair_ledger(str(i)*64,c,n)
            for s in r['stages']:s['status']='SYNTHETIC_TERMINAL'
            return r
        def admit(ledger,d,m,directory):
            i=d['index'];return dict(status='scientifically_failed_preparation_seed_exhausted_unknown' if i==0 else 'operational_partial_or_timeouts',
                operational_admission=i!=0,both_authenticated_complete=False,clean_expected_no_seed=i==0),i!=unsafe_at
        with patch.object(batch,'_manifest',return_value=m),patch.object(batch,'run',side_effect=launch),patch.object(batch,'load_pair',side_effect=load), \
            patch.object(batch,'admit_pair_ledger',side_effect=admit),patch.object(batch.os,'sched_getaffinity',return_value={0,3}),patch.object(batch.os,'sched_setaffinity'), \
            patch.object(batch.resource,'getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)),patch.object(batch.resource,'setrlimit'),patch.object(batch.signal,'signal'):
            r=batch.run_batch('/synthetic/batch.json','f'*64,root/'batch',0)
        return r,seen

    def test_queue_continues_expected_no_seed_fixed_seven_pairs_and_conservative_budget(self):
        with tempfile.TemporaryDirectory() as t:r,seen=self.queue(Path(t))
        self.assertEqual((r['status'],len(seen),r['conservative_CPU_charge_seconds']),('COMPLETED_DECLARED_TRANCHE_B',7,31680))
        self.assertEqual(sum(len(p['stages']) for p in r['pairs']),35);self.assertEqual(r['linked_existing_gate']['operational_slots'],5)
        self.assertLess(67680,batch.AGGREGATE_CHARGE_CEILING_SECONDS)
        for i,(a,l,e) in enumerate(seen):
            self.assertEqual(a[a.index('--manifest')+1],f'/synthetic/{i}.json');self.assertIn('--pair-driver',a)
            self.assertEqual((l.wall_seconds,l.cpu_seconds,l.cpu,l.poll_seconds),(4200,1500,0,0.2));self.assertEqual(set(e.values()),{'1'})

    def test_parent_caps_are_absolute_and_queue_cap_precedes_manifest_preflight(self):
        with patch.object(lifecycle.os,'sched_getaffinity',return_value={0}),patch.object(lifecycle.os,'sched_setaffinity'), \
            patch.object(lifecycle.resource,'getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)), \
            patch.object(lifecycle.resource,'setrlimit') as cap,patch.object(lifecycle.signal,'signal'),patch.object(lifecycle.threading,'active_count',return_value=1):
            self.assertEqual(lifecycle.install_parent_limits(0,gate.LIMITS),180)
            self.assertIn(unittest.mock.call(resource.RLIMIT_CPU,(180,resource.RLIM_INFINITY)),cap.call_args_list)
        with tempfile.TemporaryDirectory() as t,patch.object(batch.os,'sched_getaffinity',return_value={0}),patch.object(batch.os,'sched_setaffinity'), \
            patch.object(batch.resource,'getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)), \
            patch.object(batch.resource,'setrlimit') as cap,patch.object(batch.signal,'signal'),patch.object(batch.time,'process_time',return_value=27.5):
            def preflight(*args):
                self.assertIn(unittest.mock.call(resource.RLIMIT_CPU,(1440,resource.RLIM_INFINITY)),cap.call_args_list)
                raise ValueError('synthetic preflight block')
            with patch.object(batch,'_manifest',side_effect=preflight):
                r=batch.run_batch('/synthetic/m.json','f'*64,Path(t)/'batch',0)
            self.assertEqual(r['queue_parent_CPU_seconds'],27.5)
            self.assertEqual(r['status'],'UNKNOWN_HALTED_NO_NEW_STARTS')
            self.assertEqual(sum(len(p['stages']) for p in r['pairs']),35)
            self.assertTrue(all(p['status']=='PLANNED_NOT_LAUNCHED' for p in r['pairs']))

    def test_queue_unsafe_unknown_cleanup_and_charge_overrun_retain_unstarted_slots(self):
        for kwargs,count,status in [({'unsafe_at':2},3,'BLOCKED_PAIR_INTEGRITY_CLEANUP_RESOURCE_OR_CORRECTNESS'),
            ({'unclean_at':1},2,'UNKNOWN_HALTED_NO_NEW_STARTS'),({'overrun_at':0},1,'BLOCKED_CONSERVATIVE_CPU_CHARGE_OVERRUN')]:
            with self.subTest(kwargs=kwargs),tempfile.TemporaryDirectory() as t:
                r,seen=self.queue(Path(t),**kwargs);self.assertEqual((len(seen),r['status']),(count,status));self.assertEqual(sum(len(p['stages']) for p in r['pairs']),35)
                self.assertTrue(all(p['status']=='PLANNED_NOT_LAUNCHED' for p in r['pairs'][count:]));self.assertNotIn('STARTED',[p['status'] for p in r['pairs']])

if __name__=='__main__':unittest.main()
