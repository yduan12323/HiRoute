"""Tiny exact extraction/profile checks; no real capture is read."""
from copy import deepcopy
from fractions import Fraction as F
import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import hot_jobs as hot
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter
from validation.family5.checker import digest
from validation.family5 import independent_oracle_v2 as v2,independent_oracle_v4 as v4
from validation.real5_v2.batch_jobs import make_job,sha,evaluate

def piece():return v2.Piece(F(0),F(2),True,True,F(1),F(0),True,F(0),(),('o',0,0))
class HotJobDiagnostic(unittest.TestCase):
 def fixture(self):
  p=piece();batch=dict(kind='reduction',parents=['n'],outputs=['n'],params={});bh=digest(batch)
  capture=dict(bundle=dict(nodes={'n':{'output':p.dump()}},batches=[deepcopy(batch) for _ in range(4)],batch_ids=[bh]*4))
  ledgers=[]
  for kernel in ('v2','tau-precompute-v1'):
   rows=[]
   for i in range(4):
    raw=make_job(i,bh,'reduction',[p],[p],'c'*64,kernel=kernel)
    row=dict(index=i,batch_sha256=bh,kind='reduction',context_sha256='c'*64,job_sha256=sha(raw),input_bytes=len(raw))
    if kernel!='v2':row['kernel']=kernel
    rows.append(row)
   ledger=dict(schema='family5-selection-ledger-v1' if kernel=='v2' else 'family5-selection-ledger-v2',context_sha256='c'*64,
    expected=[[i,bh,'reduction'] for i in range(4)],submitted=rows,results=[])
   if kernel!='v2':ledger['kernel']=kernel
   ledgers.append(ledger)
  return capture,*ledgers
 def test_both_original_job_versions_reconcile_exactly(self):
  capture,old,new=self.fixture()
  with tempfile.TemporaryDirectory() as d,patch.object(hot,'HOT_IDS',(0,1,2,3)):
   with BoundedEvidenceWriter(Path(d)/'out',16*1024**2,profile_name='tiny-extract') as writer:
    result=hot.extract(capture,old,new,writer,'c'*64);writer.finalize()
   self.assertFalse(result['acceptance']);self.assertEqual(result['indices'],[0,1,2,3])
   for row in result['jobs']:
    for kernel,spec in row['files'].items():
     raw=(Path(d)/'out'/spec['path']).read_bytes();self.assertEqual(sha(raw),spec['sha256'])
     self.assertEqual(evaluate(raw,expected_kernel=kernel)['cells'],3)
 def test_changed_identity_descriptor_order_or_completed_status_rejects(self):
  for change in ('hash','bytes','context','expected','completed','piece','kernel'):
   capture,old,new=self.fixture()
   if change=='hash':new['submitted'][0]['job_sha256']='0'*64
   elif change=='bytes':new['submitted'][0]['input_bytes']+=1
   elif change=='context':old['context_sha256']='0'*64
   elif change=='expected':old['expected'].reverse()
   elif change=='completed':new['results']=[dict(result=dict(index=0))]
   elif change=='piece':capture['bundle']['nodes']['n']['output']['b']='1'
   else:new['submitted'][0]['kernel']='v2'
   with self.subTest(change=change),tempfile.TemporaryDirectory() as d,patch.object(hot,'HOT_IDS',(0,1,2,3)):
    with BoundedEvidenceWriter(Path(d)/'out',16*1024**2,profile_name='tiny-extract') as writer:
     with self.assertRaises(ValueError):hot.extract(capture,old,new,writer,'c'*64)
     self.assertEqual(writer.files,[])
 def test_json_pin_authenticates_consumed_snapshot_and_caps(self):
  raw=b'{"value":1}'
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'input.json';path.write_bytes(raw)
   self.assertEqual(hot.read_pinned(path,sha(raw),100),{'value':1})
   with patch.object(hot.binding,'load',return_value={'value':999}):
    self.assertEqual(hot.read_pinned(path,sha(raw),100),{'value':1})
   path.write_bytes(b'{"value":2}')
   with self.assertRaisesRegex(ValueError,'hash changed'):hot.read_pinned(path,sha(raw),100)
   with self.assertRaisesRegex(ValueError,'cap'):hot.read_pinned(path,sha(raw),2)
   raw=b'{"x":1,"x":2}';path.write_bytes(raw)
   with self.assertRaisesRegex(ValueError,'duplicate'):hot.read_pinned(path,sha(raw),100)
 def test_profile_reads_only_exact_manifest_bound_bytes(self):
  p=piece();raw=make_job(0,'a'*64,'reduction',[p],[p],'c'*64)
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'job.json';path.write_bytes(raw);spec=dict(size_bytes=len(raw),sha256=sha(raw))
   self.assertEqual(hot.read_job_bytes(path,spec),raw)
   changed=bytearray(raw);changed[0]=ord('[');path.write_bytes(changed)
   with self.assertRaisesRegex(ValueError,'bytes changed'):hot.read_job_bytes(path,spec)
   path.write_bytes(raw+b'x')
   with self.assertRaisesRegex(ValueError,'bytes changed'):hot.read_job_bytes(path,spec)
   with self.assertRaisesRegex(ValueError,'cap'):hot.read_job_bytes(path,dict(spec,size_bytes=8*1024**2+1))
 def test_completed_profile_has_identical_result_and_restores_hooks(self):
  p=piece();original=(v2.arrangement,v2.dominates,v4._dominates,v2._certificate_cell,v4._certificate_cell)
  for kernel in ('v2','tau-precompute-v1'):
   raw=make_job(0,'a'*64,'reduction',[p],[p],'c'*64,kernel=kernel)
   report=hot.profile_job(raw,kernel,1)
   self.assertTrue(report['completed']);self.assertFalse(report['acceptance'])
   self.assertEqual(report['result'],evaluate(raw,expected_kernel=kernel))
   self.assertEqual(report['observations']['cell_completed'],3)
   self.assertEqual(original,(v2.arrangement,v2.dominates,v4._dominates,v2._certificate_cell,v4._certificate_cell))
 def test_sweep_rebind_preserves_inputs_and_reports_exact_certificate(self):
  from validation.family5 import independent_oracle_v5 as sweep
  from validation.real5_v2.batch_jobs import decode
  p=piece();original=make_job(11835,'a'*64,'reduction',[p],[p],'c'*64)
  candidate=hot.rebind_sweep_job(original);a,b=decode(original),decode(candidate)
  self.assertEqual({k:v for k,v in a.items() if k!='schema'},{k:v for k,v in b.items() if k not in ('schema','kernel')})
  init=sweep._CoverSweep.__init__;report=hot.profile_job(candidate,'interval-sweep-v1',1)
  self.assertTrue(report['completed']);self.assertFalse(report['acceptance'])
  expected=evaluate(original,expected_kernel='v2')
  self.assertEqual(report['result']['certificate_sha256'],expected['certificate_sha256'])
  self.assertEqual(report['result']['cells'],expected['cells'])
  self.assertEqual(report['observations']['sweep_work']['certificate_cells'],expected['cells'])
  self.assertIs(sweep._CoverSweep.__init__,init)
  with self.assertRaises(ValueError):hot.rebind_sweep_job(candidate)
  with self.assertRaises(ValueError):hot.rebind_sweep_job(original+b' ')

 def test_timeout_keeps_observations_and_restores_hooks(self):
  p=piece();raw=make_job(0,'a'*64,'reduction',[p],[p],'c'*64)
  original=v2._certificate_cell
  def slow(*args):
   until=time.monotonic()+.05
   while time.monotonic()<until:pass
   return original(*args)
  with patch.object(v2,'_certificate_cell',slow):
   report=hot.profile_job(raw,'v2',.01)
   self.assertFalse(report['completed']);self.assertEqual(report['error']['type'],'SampleEnd')
   self.assertTrue(report['observations']['samples']);self.assertIs(v2._certificate_cell,slow)
  self.assertIs(v2._certificate_cell,original)
if __name__=='__main__':unittest.main()
