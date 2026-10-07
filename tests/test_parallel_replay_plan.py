"""Source-only renewal checks using tiny immutable exports; no real phase."""
from copy import deepcopy
import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import plan,replay_plan
from tests.test_real_export_input import TestRealExportInput

class ParallelReplayPlan(unittest.TestCase):
 def setUp(self):
  self.fixture=TestRealExportInput();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.root=self.fixture.root;(self.root/'validation').mkdir();(self.root/'validation/__init__.py').write_text('# old\n')
  self.stack=[]
  for target,kw in [('source_commit',dict(return_value='old-commit')),('assert_committed_sources',{})]:
   obj=patch.object(plan,target,**kw);self.stack.append(obj.start());self.addCleanup(obj.stop)
  self.original=plan.prepare_plan(self.root,'.',self.fixture.manifest_hash,'selection.json',self.fixture.selection_hash,'tree.json',state_id='mock')
  self.path=self.root/'old-plan.json';self.path.write_bytes(plan.canonical(self.original)+b'\n');self.sha=plan.pin(self.path)['sha256']
  (self.root/'validation/__init__.py').write_text('# new\n');self.stack[0].return_value='new-commit'
 def renew(self):
  value=replay_plan.renew(self.root,self.path,self.sha);path=self.root/'new-plan.json'
  path.write_bytes(plan.canonical(value)+b'\n');return value,path,plan.pin(path)['sha256']
 def test_renewal_changes_only_current_sources_and_keeps_original_bytes(self):
  raw=self.path.read_bytes();new,path,sha=self.renew()
  old,checked=replay_plan.verify(self.root,path,sha,self.path,self.sha,time.monotonic()+10,require_c01=False)
  self.assertEqual(old,self.original);self.assertEqual(checked,new);self.assertEqual(self.path.read_bytes(),raw)
  self.assertEqual(new['source_commit'],'new-commit');self.assertNotEqual(new['source_sha256'],old['source_sha256'])
  self.assertEqual(new['reference']['status'],'historical_reference_missing')
 def test_any_non_source_scope_change_rejects_even_with_repaired_hash(self):
  new,path,sha=self.renew()
  for key,value in [('state_id','other'),('reference',{'status':'attained'}),('external_incumbent',[]),
   ('query_sha256','0'*64),('inputs',{}),('profiles',{}),('extra',True)]:
   bad=deepcopy(new);bad[key]=value
   with self.subTest(field=key),self.assertRaisesRegex(ValueError,'capture scope'):
    replay_plan.same_capture_scope(self.original,bad)
 def test_historical_bytes_sources_and_inputs_are_bound(self):
  for mutation in ('hash','source','input','digest'):
   with self.subTest(mutation=mutation):
    bad=deepcopy(self.original)
    if mutation=='source':bad['source_sha256']='0'*64
    elif mutation=='input':bad['inputs']['table']['sha256']='0'*64;bad['input_sha256']=plan.digest(bad['inputs'])
    elif mutation=='digest':bad['query_sha256']='0'*64
    path=self.root/('bad-'+mutation+'.json');path.write_bytes(plan.canonical(bad))
    sha='0'*64 if mutation=='hash' else plan.pin(path)['sha256']
    with self.assertRaises(ValueError):replay_plan.historical_plan(self.root,path,sha)
 def test_expired_or_unbound_current_source_rejects(self):
  value,path,sha=self.renew()
  with self.assertRaisesRegex(ValueError,'deadline'):
   replay_plan.verify(self.root,path,sha,self.path,self.sha,time.monotonic()-1,require_c01=False)
  (self.root/'validation/__init__.py').write_text('# changed again\n')
  with self.assertRaisesRegex(ValueError,'source closure'):
   replay_plan.verify(self.root,path,sha,self.path,self.sha,time.monotonic()+10,require_c01=False)
if __name__=='__main__':unittest.main()
