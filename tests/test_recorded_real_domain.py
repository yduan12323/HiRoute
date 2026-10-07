"""Small domain/plan checks only; the fixed real runtime is never launched."""
from copy import deepcopy
from dataclasses import asdict
import hashlib,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.time_cut_v2.recorded_real import domain,plan,runtime
from tests.test_recovered_real_family import blob,prepare
from validation.real5_v2.shared_replay import verify_coalesced_trace
from validation.family5.checker import _plain

class RecordedDomain(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
 def make_plan(self,row,d=True):
  (self.root/'table.json').write_bytes(blob(row['table']));(self.root/'tree.json').write_bytes(blob(row['original_tree']))
  inputs={role:dict(path=name,**plan.pin(self.root/name)) for role,name in [('table','table.json'),('original_tree','tree.json')]}
  return dict(state_id='MOCK',pool_id='mock',H_ref=row['query']['H_ref'],sites=len(row['table']['sites']),
   regions=len(row['original_tree']['regions']),dominance=d,representation=domain.REPRESENTATION,external_incumbent=None,
   query=row['query'],query_sha256=plan.digest(row['query']),source_sha256='b'*64,input_sha256=plan.digest(inputs),inputs=inputs,
   reference=dict(status='historical_reference_missing',raw_certificates_replayed=False))
 def writer(self,name):return runtime.BoundedEvidenceWriter(self.root/name,16*1024**2,profile_name='synthetic-domain-test')
 def test_all_mocks_full_capture_replay_and_lossless_query_index(self):
  for i,row in enumerate(self.rows):
   for d in (False,True):
    with self.subTest(case=i,dominance=d):
     value=self.make_plan(row,d)
     with self.writer(f'capture-{i}-{d}') as writer:
      cap=domain.capture(value,self.root,writer,'a'*64);writer.finalize()
     path=self.root/f'capture-{i}-{d}/capture.json';payload=plan.load(path)
     with self.writer(f'replay-{i}-{d}') as writer:
      out=domain.replay(value,self.root,writer,'a'*64,path,cap['capture']['sha256']);writer.finalize()
     self.assertTrue(out['structural_verified']);self.assertFalse(out['literal_G8_closed'])
     self.assertEqual(out['reference_comparison']['status'],'pending_missing_historical_reference')
     checked=verify_coalesced_trace(payload['trace'],payload['bundle'],prepare(row))
     index=plan.load(self.root/f'replay-{i}-{d}/query-index.json')
     expander=domain.QueryExpander(checked)
     self.assertEqual([expander.expand(q) for q in index['queries']],checked.export_queries())
     receipts=plan.load(self.root/f'replay-{i}-{d}/callback-receipts.json')['receipts']
     self.assertEqual(len(receipts),len(payload['callback_requests']))
 def test_wrong_reference_is_never_an_incumbent_and_preserves_capture(self):
  row=self.rows[0];value=self.make_plan(row);value['reference']=dict(status='historical_result_available',expected_key=['-999','0',0,[]])
  from timecut5 import coalesced_solver
  original=coalesced_solver.solve_hierarchical_real_coalesced;seen=[]
  def observe(*a,**kw):seen.append(kw);return original(*a,**kw)
  with self.writer('wrong-reference') as writer,patch.object(coalesced_solver,'solve_hierarchical_real_coalesced',side_effect=observe):
   with self.assertRaisesRegex(ValueError,'historical result'):domain.capture(value,self.root,writer,'a'*64)
  self.assertTrue((self.root/'wrong-reference/capture.json').exists())
  self.assertEqual(len(seen),1);self.assertNotIn('incumbent',seen[0])
 def test_capture_pins_canonical_and_scope_mutations_reject(self):
  value=self.make_plan(self.rows[0])
  with self.writer('capture') as writer:cap=domain.capture(value,self.root,writer,'a'*64);writer.finalize()
  original=plan.load(self.root/'capture/capture.json')
  for i,field in enumerate(('canonical','source','scope','parent')):
   bad=deepcopy(original)
   if field=='canonical':bad['canonical']['result']['charges']=['999']
   elif field=='source':bad['source_plan_sha256']='0'*64
   elif field=='scope':bad['variant']['dominance']=1
   else:next(n for n in bad['bundle']['nodes'].values() if n['parents'])['parents'][0]='0'*64
   path=self.root/f'bad{i}.json';path.write_bytes(plan.canonical(bad))
   with self.writer(f'bad-replay{i}') as writer,self.subTest(field=field),self.assertRaises(ValueError):
    domain.replay(value,self.root,writer,'a'*64,path,plan.pin(path)['sha256'])
 def test_prior_capture_pins_profile_context_and_complete_file_coverage(self):
  from experiments.time_cut_v2.recorded_real.worker import prior_capture
  value=self.make_plan(self.rows[0]);attempt=self.root/'prior';attempt.mkdir()
  with runtime.BoundedEvidenceWriter(attempt/'evidence',runtime.CAPTURE.worker_evidence_bytes,profile_name=runtime.CAPTURE.name) as writer:
   writer.write('run-binding.json',domain.chunks({'synthetic_fixture':True}))
   cap=domain.capture(value,self.root,writer,'a'*64);writer.finalize()
  result=dict(status='completed',descendants_reaped=True,profile=asdict(runtime.CAPTURE),
   context=dict(plan_sha256='a'*64,source_sha256=value['source_sha256'],input_sha256=value['input_sha256'],profile_name=runtime.CAPTURE.name))
  path=attempt/'result.json';path.write_bytes(plan.canonical(result));mh=plan.pin(attempt/'evidence/__manifest.json')['sha256'];rh=plan.pin(path)['sha256']
  decision=attempt/'decision.json';decision.write_bytes(b'{"synthetic_boundary_fixture":true}');dh=plan.pin(decision)['sha256']
  result.update(verified_manifest_sha256=mh,verified_manifest_size_bytes=plan.pin(attempt/'evidence/__manifest.json')['size_bytes'])
  # Runtime terminal receipts have their own real tiny-process tests. Here the
  # validated return is injected only to exercise the domain's additional pins.
  receipt=self.root/'observed-launcher-return.json';receipt.write_bytes(plan.canonical({'observed_return_fixture':True}))
  receipt_kw=dict(successful_return_path=receipt,successful_return_sha=plan.pin(receipt)['sha256'])
  with patch('experiments.time_cut_v2.recorded_real.worker.read_phase_result',return_value=result) as accepted:
   source,sha=prior_capture(value,'a'*64,attempt,mh,rh,dh,time.monotonic()+10,**receipt_kw)
   self.assertEqual(sha,cap['capture']['sha256']);self.assertEqual(source,attempt/'evidence/capture.json')
   self.assertEqual(accepted.call_args.kwargs['successful_return'],{'observed_return_fixture':True})
   with self.assertRaisesRegex(ValueError,'launcher return changed'):
    prior_capture(value,'a'*64,attempt,mh,rh,dh,time.monotonic()+10,successful_return_path=receipt,successful_return_sha='0'*64)
   with self.assertRaisesRegex(ValueError,'resource report changed'):prior_capture(value,'a'*64,attempt,mh,'0'*64,dh,time.monotonic()+10,**receipt_kw)
   with self.assertRaisesRegex(ValueError,'final decision changed'):prior_capture(value,'a'*64,attempt,mh,rh,'0'*64,time.monotonic()+10,**receipt_kw)
   result['profile']['wall_seconds']=999
   with self.assertRaisesRegex(ValueError,'profile changed'):prior_capture(value,'a'*64,attempt,mh,rh,dh,time.monotonic()+10,**receipt_kw)
 def test_complete_domain_replay_with_producer_and_optimizer_imports_blocked(self):
  value=self.make_plan(self.rows[0]);source=self.root/'plan.json';source.write_bytes(plan.canonical(value))
  with self.writer('capture-fenced') as writer:cap=domain.capture(value,self.root,writer,'a'*64);writer.finalize()
  script=r"""
import sys,json
from pathlib import Path
from experiments.time_cut_v2.recorded_real.worker import Fence
sys.meta_path.insert(0,Fence('replay'))
from experiments.time_cut_v2.recorded_real import domain,plan,runtime
root=Path(sys.argv[1]);p=plan.load(root/'plan.json');capture=root/'capture-fenced/capture.json'
with runtime.BoundedEvidenceWriter(root/'replay-fenced',16*1024**2,profile_name='synthetic-domain-test') as writer:
 result=domain.replay(p,root,writer,'a'*64,capture,plan.pin(capture)['sha256'])
 writer.finalize()
 if result['structural_verified'] is not True:raise RuntimeError('incomplete')
print('independent full domain replay')
"""
  flags=['-'+('O'*sys.flags.optimize)] if sys.flags.optimize else []
  result=subprocess.run([sys.executable,'-B',*flags,'-c',script,str(self.root)],cwd=ROOT,capture_output=True,text=True,
   env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),timeout=20)
  self.assertEqual(result.returncode,0,result.stderr);self.assertIn('independent full domain',result.stdout)
 def test_query_closure_tamper_rejects(self):
  from tests.test_recovered_real_coalesced import capture
  row=self.rows[0];data=capture(row,True);checked=verify_coalesced_trace(data['trace'],data['bundle'],prepare(row))
  q=next(domain.thin_queries(checked,lambda:None));q['ancestry_bundle_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'query occurrence'):domain.expand_query(q,checked)
  q=next(domain.thin_queries(checked,lambda:None));q['cuts']=[]
  with self.assertRaisesRegex(ValueError,'derived query fields'):domain.expand_query(q,checked)

class RecordedPlan(unittest.TestCase):
 def test_prepare_verify_and_source_input_mutations(self):
  from tests.test_real_export_input import TestRealExportInput
  fixture=TestRealExportInput();fixture.setUp();self.addCleanup(fixture.doCleanups)
  root=fixture.root;(root/'validation').mkdir();source=root/'validation/__init__.py';source.write_text('# synthetic source\n')
  with patch.object(plan,'source_commit',return_value='fixture-commit'),patch.object(plan,'assert_committed_sources'):
   value=plan.prepare_plan(root,'.',fixture.manifest_hash,'selection.json',fixture.selection_hash,'tree.json',state_id='mock')
   self.assertEqual(value['reference']['status'],'historical_reference_missing')
   target=root/'plan.json';target.write_bytes(plan.canonical(value));sha=plan.pin(target)['sha256']
   plan.verify_plan(root,target,sha,time.monotonic()+10,require_c01=False)
   with self.assertRaisesRegex(ValueError,'fixed C01'):plan.verify_plan(root,target,sha,time.monotonic()+10)
   source.write_text('# changed\n')
   with self.assertRaisesRegex(ValueError,'source closure'):plan.verify_plan(root,target,sha,time.monotonic()+10,require_c01=False)
 def test_repaired_plan_query_cannot_replace_frozen_resolved_state(self):
  from tests.test_real_export_input import TestRealExportInput
  fixture=TestRealExportInput();fixture.setUp();self.addCleanup(fixture.doCleanups)
  root=fixture.root;(root/'validation').mkdir();(root/'validation/__init__.py').write_text('# test source\n')
  with patch.object(plan,'source_commit',return_value='fixture-commit'),patch.object(plan,'assert_committed_sources'):
   value=plan.prepare_plan(root,'.',fixture.manifest_hash,'selection.json',fixture.selection_hash,'tree.json',state_id='mock')
   value['query']['initial_energy_kwh']='5';value['query_sha256']=plan.digest(value['query'])
   target=root/'plan.json';target.write_bytes(plan.canonical(value));sha=plan.pin(target)['sha256']
   with self.assertRaisesRegex(ValueError,'resolved state'):plan.verify_plan(root,target,sha,time.monotonic()+10,require_c01=False)
 def test_original_root_order_does_not_replace_global_selected_id_order(self):
  from tests.test_real_export_input import TestRealExportInput
  from timecut5.real_legs import restrict_frozen_tree
  fixture=TestRealExportInput();fixture.setUp();self.addCleanup(fixture.doCleanups);root=fixture.root
  tree=plan.load(root/'tree.json');tree['regions'][0]['members'].reverse()
  th=fixture.write('tree.json',tree);raw=(root/'tree.json').read_bytes()
  selection=plan.load(root/'selection.json');selection['original_hierarchy_sha256']=th
  sh=fixture.write('selection.json',selection);fixture.selection_hash=sh
  table=plan.load(root/'table.json');table.update(hierarchy_sha256=th,selection_certificate_sha256=sh)
  fixture.table_spec['sha256']=fixture.write('table.json',table)
  restricted=restrict_frozen_tree(raw,th,[s['site_id'] for s in table['sites']])
  restriction=dict(schema='hiroute.original_tree_restriction.v1',original_sha256=th,selection_certificate_sha256=sh,
   pool_id='p',selected_site_ids=list(restricted.selected_site_ids),regions=[dict(region_id=r.region_id,parent_id=r.parent_id,
   child_ids=list(r.child_ids),site_ids=list(r.site_ids)) for r in restricted.regions])
  self.assertNotEqual(restriction['selected_site_ids'],restriction['regions'][0]['site_ids'])
  fixture.r_spec['sha256']=fixture.write('restriction.json',restriction)
  fixture.manifest.update(hierarchy_sha256=th,selection_certificate_sha256=sh);fixture.refresh()
  (root/'validation').mkdir();(root/'validation/__init__.py').write_text('# test source\n')
  with patch.object(plan,'source_commit',return_value='fixture-commit'),patch.object(plan,'assert_committed_sources'):
   value=plan.prepare_plan(root,'.',fixture.manifest_hash,'selection.json',sh,'tree.json',state_id='mock')
   target=root/'plan.json';target.write_bytes(plan.canonical(value))
   plan.verify_plan(root,target,plan.pin(target)['sha256'],time.monotonic()+10,require_c01=False)

 def test_repaired_derived_payload_cannot_sever_manifest_links(self):
  from tests.test_real_export_input import TestRealExportInput
  for mutation in ('states','table_path','table_hash','restriction_hash','selection_hash','tree_hash','population','restriction_rows','selection_effects','baseline','soc'):
   with self.subTest(mutation=mutation):
    fixture=TestRealExportInput();fixture.setUp();self.addCleanup(fixture.doCleanups);root=fixture.root
    (root/'validation').mkdir();(root/'validation/__init__.py').write_text('# test source\n')
    with patch.object(plan,'source_commit',return_value='fixture-commit'),patch.object(plan,'assert_committed_sources'):
     value=plan.prepare_plan(root,'.',fixture.manifest_hash,'selection.json',fixture.selection_hash,'tree.json',state_id='mock')
     if mutation=='states':
      fixture.state['initial_energy_kwh']='5';fixture.write('query_states_resolved.json',[fixture.state])
     elif mutation=='table_path':
      (root/'other.json').write_bytes((root/'table.json').read_bytes())
      fixture.table_spec['path']='other.json';fixture.refresh()
     elif mutation in ('table_hash','restriction_hash'):
      (fixture.table_spec if mutation=='table_hash' else fixture.r_spec)['sha256']='0'*64;fixture.refresh()
     elif mutation in ('selection_hash','tree_hash'):
      fixture.manifest['selection_certificate_sha256' if mutation=='selection_hash' else 'hierarchy_sha256']='0'*64;fixture.refresh()
     elif mutation=='population':value['regions']+=1
     elif mutation=='restriction_rows':
      row=plan.load(root/'restriction.json');row['regions'][0]['site_ids']=[]
      fixture.r_spec['sha256']=fixture.write('restriction.json',row);fixture.refresh()
     elif mutation=='selection_effects':
      row=plan.load(root/'selection.json');row['pools'][0]['chosen'][0]['eligible_actions']=[]
      new_sha=fixture.write('selection.json',row);fixture.manifest['selection_certificate_sha256']=new_sha
      table=plan.load(root/'table.json');table['selection_certificate_sha256']=new_sha
      fixture.table_spec['sha256']=fixture.write('table.json',table);fixture.refresh()
     else:
      if mutation=='soc':fixture.state['initial_soc']='1/2'
      else:fixture.state['accepted_baseline_time_s']={'hex':'0x1.8000000000000p+1','ratio':['3','1']}
      fixture.refresh()
     for spec in value['inputs'].values():spec.update(plan.pin(root/spec['path']))
     value['input_sha256']=plan.digest(value['inputs'])
     value['query']=plan.resolved_query(fixture.state,value['inputs']);value['query_sha256']=plan.digest(value['query'])
     target=root/'plan.json';target.write_bytes(plan.canonical(value))
     with self.assertRaises(ValueError):plan.verify_plan(root,target,plan.pin(target)['sha256'],time.monotonic()+10,require_c01=False)

 def test_exact_reference_numbers(self):
  for value in (True,1.0):
   with self.subTest(value=value),self.assertRaises(ValueError):plan.result_key(dict(status='attained_optimum',J=value,Q_total='0',H=0,site_action_tuple=[]))

if __name__=='__main__':unittest.main()
