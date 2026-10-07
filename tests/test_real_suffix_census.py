"""Count-only occurrence and completed-evidence binding; tiny synthetic fixtures."""
from copy import deepcopy
from dataclasses import asdict
import json,time,unittest,os,sys,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import suffix_census as census,plan,domain,parallel_replay
from tests.test_recorded_real_domain import RecordedDomain
from tests.test_recovered_real_family import prepare
from validation.real5_v2.shared_replay_cached import verify_coalesced_trace
from validation.real5_v2.suffix_context import RealSuffixQueries

class RealSuffixCensus(unittest.TestCase):
 def setUp(self):
  self.fx=RecordedDomain();self.fx.setUp();self.addCleanup(self.fx.doCleanups);self.root=self.fx.root
 def make(self,row=None):
  row=row or self.fx.rows[0];old=self.fx.make_plan(row)
  with self.fx.writer('capture') as w:cap=domain.capture(old,self.root,w,'a'*64);w.finalize()
  path=self.root/'capture/capture.json';payload=plan.load(path);trusted=prepare(row)
  with self.fx.writer('replay') as w:summary=domain.replay(old,self.root,w,'a'*64,path,cap['capture']['sha256']);w.finalize()
  index=plan.load(self.root/'replay/query-index.json')
  checked=verify_coalesced_trace(payload['trace'],payload['bundle'],trusted)
  return old,summary,index,trusted,checked
 def test_every_tiny_occurrence_matches_real_models_without_all_query_export(self):
  for i,row in enumerate(self.fx.rows):
   child=RecordedDomain();child.setUp()
   try:
    with patch.object(self,'fx',child),patch.object(self,'root',child.root):old,summary,index,trusted,checked=self.make(row)
    out=census.census(index,trusted,summary['checked']);ctx=RealSuffixQueries(checked,trusted)
    self.assertEqual(out['exact_queries'],len(ctx.rows));self.assertFalse(out['literal_G8_closed'])
    for counted in out['queries']:
     expected=ctx.census(counted['query_seq']);self.assertEqual(counted['model_slots'],expected['model_slots'])
     self.assertEqual(counted['thin_occurrence_sha256'],plan.digest(index['queries'][counted['query_index_position']]))
    self.assertEqual(out['totals'].get('model_slots',0),sum(ctx.census(seq)['model_slots'] for seq in ctx.rows))
   finally:child.doCleanups()
 def test_changed_identity_scope_actions_and_type_aliases_reject(self):
  _,summary,index,trusted,_=self.make()
  mutations=[lambda x:x['queries'].append(deepcopy(x['queries'][0])),
   lambda x:x['queries'][0].update(query_seq=True),lambda x:x['queries'][0]['state'].__setitem__(1,True),
   lambda x:x['queries'][0].update(actions=[]),lambda x:x['queries'][0].update(family_ids=[]),
   lambda x:x['queries'][0].update(region_members=[]),lambda x:x['queries'][0].update(source_bundle_sha256='0'*64),
   lambda x:x.update(empty_action_queries=True),lambda x:x.update(query_freeze_sha256='0'*64),
   lambda x:x.update(real_input={})]
  for change in mutations:
   bad=deepcopy(index);change(bad)
   with self.assertRaises(ValueError):census.census(bad,trusted,summary['checked'])
 def test_completed_return_manifest_and_original_index_are_all_required(self):
  old,summary,index,trusted,_=self.make();new=dict(old,source_sha256='e'*64)
  attempt=self.root/'complete';attempt.mkdir();evidence=attempt/'evidence'
  pins=dict(capture_manifest_sha='1'*64,capture_result_sha='2'*64,capture_decision_sha='3'*64,capture_return_sha='4'*64)
  run=dict(schema='hiroute-parallel-replay-binding-v1',historical_plan_sha256='a'*64,current_plan_sha256='b'*64,
   source_sha256=new['source_sha256'],input_sha256=old['input_sha256'],capture_sha256=index['capture_sha256'],
   shared_query_digest='owned-canonical-node-cache-v1',batch_kernel='interval-join-v1',capture_commitments=pins)
  with census.BoundedEvidenceWriter(evidence,census.BATCH_REPLAY.worker_evidence_bytes,profile_name=census.BATCH_REPLAY.name) as w:
   w.write('run-binding.json',domain.chunks(run))
   q=w.write('query-index.json',domain.chunks(index));cb=w.write('callback-receipts.json',[b'[]']);bl=w.write('batch-ledger.json',[b'{}'])
   summary.update(query_index=q,callback_receipts=cb);ss=w.write('structural-summary.json',domain.chunks(summary))
   parallel=dict(schema='hiroute-complete-parallel-replay-v1',structural_verified=True,literal_G8_closed=False,
    historical_plan_sha256='a'*64,current_plan_sha256='b'*64,current_source_sha256=new['source_sha256'],
    input_sha256=old['input_sha256'],capture_sha256=index['capture_sha256'],structural_summary=ss,
    batch_ledger=bl,callback_receipts=cb,query_index=q)
   w.write('parallel-summary.json',domain.chunks(parallel));w.finalize()
  for name in ('result.json','decision.json','return.json'):(attempt/name).write_bytes(b'{}')
  args=SimpleNamespace(historical_plan=self.root/'old',historical_plan_sha='a'*64,replay_plan=self.root/'new',replay_plan_sha='b'*64,
   replay_attempt=attempt,replay_return=attempt/'return.json',replay_return_sha=plan.pin(attempt/'return.json')['sha256'],
   replay_result_sha=plan.pin(attempt/'result.json')['sha256'],replay_decision_sha=plan.pin(attempt/'decision.json')['sha256'],
   replay_manifest_sha=plan.pin(evidence/'__manifest.json')['sha256'],query_index_sha=q['sha256'])
  expected=dict(status='completed',descendants_reaped=True,profile=asdict(census.BATCH_REPLAY),verified_manifest_sha256=args.replay_manifest_sha,
   context=dict(plan_sha256='b'*64,source_sha256=new['source_sha256'],profile_name=census.BATCH_REPLAY.name,
    input_sha256=parallel_replay.input_context(SimpleNamespace(historical_plan_sha='a'*64,batch_kernel='interval-join-v1',shared_query_digest=True,**pins),old)))
  # Actual runtime receipt/manifest checks have independent process tests. Inject
  # only that boundary here to exercise all additional source/index links.
  with patch.object(census.replay_plan,'historical_plan',side_effect=lambda root,path,sha:old if sha=='a'*64 else new),\
    patch.object(census,'read_phase_result',return_value=expected) as accept:
   out=census.completed_inputs(self.root,args,time.monotonic()+10)
   self.assertEqual(out[0],index);self.assertEqual(accept.call_args.kwargs['successful_return'],{})
   for field in ('query_index_sha','replay_return_sha','replay_manifest_sha','replay_result_sha','replay_decision_sha'):
    bad=SimpleNamespace(**vars(args));setattr(bad,field,'0'*64)
    with self.subTest(field=field),self.assertRaises(ValueError):census.completed_inputs(self.root,bad,time.monotonic()+10)
   expected['status']='unresolved'
   with self.assertRaises(ValueError):census.completed_inputs(self.root,args,time.monotonic()+10)
 def test_import_fence_blocks_producer_and_optimizer_but_not_independent_count(self):
  fence=census.NoOptimization()
  for name in ('timecut5','timecut5.pwa','validation.reference5.lp','validation.suffix5.solver','scipy'):
   with self.assertRaises(ImportError):fence.find_spec(name)
  self.assertIsNone(fence.find_spec('validation.suffix5.independent_convex_model'))
 def test_worker_requires_clean_modules_and_exact_guard_cap_before_any_input(self):
  script=r'''
import os,sys
from types import SimpleNamespace
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real import suffix_census as c
os.environ['HIROUTE_PROFILE']=c.REPLAY.name
os.environ['HIROUTE_EVIDENCE_CAP_BYTES']=str(c.REPLAY.worker_evidence_bytes)
if sys.argv[1]=='module':sys.modules['validation.preloaded_foreign']=SimpleNamespace(__file__='/wrong')
else:os.environ['HIROUTE_EVIDENCE_CAP_BYTES']='1'
with patch.object(c,'check_sources',side_effect=RuntimeError('source work must not start')) as source,patch.object(c,'worker_failure') as failure:
 if c.worker(SimpleNamespace())!=1 or source.called:raise RuntimeError('invalid admission reached source work')
 if sys.argv[1]=='module' and 'before count fence' not in failure.call_args.args[1]:raise RuntimeError('missing preload rejection')
 if sys.argv[1]=='cap' and 'phase guard' not in failure.call_args.args[1]:raise RuntimeError('missing cap rejection')
'''
  flags=['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []
  for mode in ('module','cap'):
   out=subprocess.run([sys.executable,'-B',*flags,'-c',script,mode],cwd=plan.ROOT,
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=10)
   self.assertEqual(out.returncode,0,out.stderr+out.stdout)
if __name__=='__main__':unittest.main()
