"""Full tiny replay equivalence and failure checks; no real profile or solver batch."""
from copy import deepcopy
import json,os,subprocess,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import domain,plan,parallel_replay as full
from validation.real5_v2.batch_jobs import BatchExecutor
from tests import test_recorded_real_domain as fixtures

class CompleteParallelReplay(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.RecordedDomain();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.root=self.fixture.root;self.cpus=tuple(sorted(os.sched_getaffinity(0)))[:2]
 def capture(self,row,dominance=True,name='capture'):
  old=self.fixture.make_plan(row,dominance);new=dict(old,source_sha256='e'*64)
  with self.fixture.writer(name) as writer:out=domain.capture(old,self.root,writer,'a'*64);writer.finalize()
  return old,new,self.root/name/'capture.json',out['capture']['sha256']
 def test_ten_full_paths_preserve_every_receipt_query_and_summary(self):
  for i,row in enumerate(self.fixture.rows):
   for d in (False,True):
    with self.subTest(case=i,dominance=d):
     name=f'{i}-{d}';old,new,path,sha=self.capture(row,d,'capture-'+name)
     with self.fixture.writer('serial-'+name) as writer:
      baseline=domain.replay(old,self.root,writer,'a'*64,path,sha);writer.finalize()
     with BatchExecutor(self.cpus,float(time.monotonic()+20),sha,worker_as=256*1024**2,kernel=full.KERNEL) as pool:
      with self.fixture.writer('parallel-'+name) as writer:
       out=full.replay(old,new,self.root,writer,'a'*64,'b'*64,path,sha,pool);writer.finalize()
      self.assertTrue(pool.snapshot()['complete'])
     for file in ('query-index.json','callback-receipts.json'):
      self.assertEqual((self.root/('serial-'+name)/file).read_bytes(),(self.root/('parallel-'+name)/file).read_bytes())
     after=plan.load(self.root/('parallel-'+name)/'structural-summary.json')
     baseline['checked'].pop('elapsed_s');after['checked'].pop('elapsed_s');self.assertEqual(baseline,after)
     self.assertTrue(out['structural_verified']);self.assertFalse(out['literal_G8_closed'])
     self.assertEqual(out['reference_comparison']['status'],'pending_missing_historical_reference')
     ledger=plan.load(self.root/('parallel-'+name)/'batch-ledger.json')
     self.assertEqual(len(ledger['expected']),len(ledger['results']))
     self.assertEqual(out['batch_ledger']['sha256'],plan.pin(self.root/('parallel-'+name)/'batch-ledger.json')['sha256'])

 def test_join_kernel_full_path_preserves_serial_query_and_receipt_bytes(self):
  for i,row in enumerate(self.fixture.rows):
   for dominance in (False,True):
    name=f'join-{i}-{dominance}';old,new,path,sha=self.capture(row,dominance,name)
    with self.fixture.writer(name+'-serial') as writer:
     baseline=domain.replay(old,self.root,writer,'a'*64,path,sha);writer.finalize()
    with BatchExecutor(self.cpus,float(time.monotonic()+20),sha,worker_as=256*1024**2,kernel='interval-join-v1') as pool:
     with self.fixture.writer(name+'-parallel') as writer:
      out=full.replay(old,new,self.root,writer,'a'*64,'b'*64,path,sha,pool);writer.finalize()
    self.assertEqual(out['batch_kernel'],'interval-join-v1')
    for file in ('query-index.json','callback-receipts.json'):
     self.assertEqual((self.root/(name+'-serial')/file).read_bytes(),(self.root/(name+'-parallel')/file).read_bytes())
    after=plan.load(self.root/(name+'-parallel')/'structural-summary.json')
    baseline['checked'].pop('elapsed_s');after['checked'].pop('elapsed_s');self.assertEqual(baseline,after)

 def test_forged_capture_rejects_and_children_reap_without_full_summary(self):
  for mutation in ('bytes','canonical','scope','parent'):
   with self.subTest(mutation=mutation):
    old,new,path,sha=self.capture(self.fixture.rows[0],name='capture-'+mutation)
    payload=plan.load(path)
    if mutation=='canonical':payload['canonical']['result']['charges']=['999']
    elif mutation=='scope':payload['variant']['dominance']=1
    elif mutation=='parent':next(n for n in payload['bundle']['nodes'].values() if n['parents'])['parents'][0]='0'*64
    else:payload['query']['start_time_s']='999'
    path=self.root/('mutated-'+mutation+'.json');path.write_bytes(plan.canonical(payload))
    if mutation!='bytes':sha=plan.pin(path)['sha256']
    with BatchExecutor(self.cpus,float(time.monotonic()+20),sha,worker_as=256*1024**2,kernel=full.KERNEL) as pool:
     with self.fixture.writer('bad-'+mutation) as writer,self.assertRaises(ValueError):
      full.replay(old,new,self.root,writer,'a'*64,'b'*64,path,sha,pool)
    self.assertTrue(all(s.process.poll() is not None for s in pool.slots))
    self.assertFalse((self.root/('bad-'+mutation)/'parallel-summary.json').exists())
 def test_wrong_kernel_or_incomplete_join_rejects(self):
  old,new,path,sha=self.capture(self.fixture.rows[0])
  for kernel,mutation in [('v2',False),(full.KERNEL,True)]:
   with BatchExecutor(self.cpus,float(time.monotonic()+20),sha,worker_as=256*1024**2,kernel=kernel) as pool:
    with self.fixture.writer('wrong-'+kernel) as writer:
     if mutation:
      original=pool.snapshot
      with patch.object(pool,'snapshot',side_effect=lambda:dict(original(),complete=False)),self.assertRaisesRegex(ValueError,'incomplete batch ledger'):
       full.replay(old,new,self.root,writer,'a'*64,'b'*64,path,sha,pool)
     else:
      with self.assertRaisesRegex(ValueError,'pinned interval kernel'):
       full.replay(old,new,self.root,writer,'a'*64,'b'*64,path,sha,pool)
 def test_fresh_producer_blocked_four_worker_protocol_and_output_coverage(self):
  cpus=tuple(sorted(os.sched_getaffinity(0)))[:5]
  if len(cpus)<5:self.skipTest('five CPUs needed for tiny fixed worker protocol')
  old,new,path,sha=self.capture(self.fixture.rows[0]);(self.root/'old.json').write_bytes(plan.canonical(old));(self.root/'new.json').write_bytes(plan.canonical(new))
  script=r'''
import argparse,json,os,sys,time
from pathlib import Path
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import parallel_replay as full,plan
root=Path(sys.argv[1]);cpus=json.loads(sys.argv[2]);os.sched_setaffinity(0,set(cpus))
old=plan.load(root/'old.json');new=plan.load(root/'new.json');capture=root/'capture/capture.json';sha=plan.pin(capture)['sha256']
a=argparse.Namespace(batch_kernel=full.KERNEL,worker_cpus=cpus,deadline=float(time.monotonic()+20),historical_plan_sha='a'*64,plan_sha='b'*64,
 capture_attempt=root/'capture',capture_manifest_sha='c'*64,capture_result_sha='d'*64,capture_decision_sha='e'*64,
 capture_return=root/'return.json',capture_return_sha='f'*64)
env={'HIROUTE_PROFILE':full.BATCH_REPLAY.name,'HIROUTE_EVIDENCE_CAP_BYTES':str(full.BATCH_REPLAY.worker_evidence_bytes),
 'HIROUTE_EVIDENCE_ROOT':str(root/'worker-output')}
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter
# Only source/resource-return admission is replaced by tiny fixture facts here.
# The replay, import fence, four fresh children, affinity, ledger and coverage are real.
with patch.dict(os.environ,env),patch.object(full,'inputs',return_value=(old,new)),patch.object(full,'verify_loaded'),\
 patch.object(full,'prior_capture',return_value=(capture,sha)),patch.object(full.binding,'ROOT',root):
 code=full.worker(a)
if code:raise RuntimeError('tiny complete worker failed')
if os.sched_getaffinity(0)!={cpus[0]}:raise RuntimeError('coordinator affinity changed')
if any(n=='timecut5' or n.startswith(('timecut5.','validation.suffix5','validation.reference5')) for n in sys.modules):raise RuntimeError('producer or optimizer loaded')
manifest=plan.load(root/'worker-output/__manifest.json')
if {x['path'] for x in manifest['files']}!=full.REPLAY_FILES|full.EXTRA_FILES:raise RuntimeError('incomplete outputs')
ledger=plan.load(root/'worker-output/batch-ledger.json')
if ledger['cpus']!=cpus[1:] or ledger['worker_as_bytes']!=1024**3 or ledger['complete'] is not True:raise RuntimeError('wrong workers')
print('complete producer-blocked four-worker replay')
'''
  flags=['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []
  out=subprocess.run([sys.executable,'-B',*flags,'-c',script,str(self.root),json.dumps(cpus)],cwd=plan.ROOT,
   env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=30)
  self.assertEqual(out.returncode,0,out.stderr+out.stdout)
  self.assertIn('complete producer-blocked',out.stdout)
if __name__=='__main__':unittest.main()
