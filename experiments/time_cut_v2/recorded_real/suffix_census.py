"""Count the complete recorded suffix language, without matrices or LP calls.

The thin index has evidence authority only through a cold-verified completed
replay and its separately retained successful return. It is never converted to
a CheckedTrace. A later numerical phase must use the actual checked families.
"""
import time
ENTRY=time.monotonic()
import argparse,hashlib,importlib.abc,json,math,os,resource,sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
from . import plan as binding,domain,replay_plan
from .hot_jobs import read_pinned
from .runtime import REPLAY,BATCH_REPLAY,PlanContext,BoundedEvidenceWriter,read_phase_result,run_phase,worker_failure

SECONDS=180
WORKER_AS=2*1024**3
INDEX_LIMIT=128*1024**2
QUERY_LIMIT=200000
OUTPUT_LIMIT=64*1024**2

class NoOptimization(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name=='timecut5' or name.startswith(('timecut5.','validation.reference5')) or name.split('.')[0] in ('scipy','numpy','sympy') or name in (
   'validation.suffix5.solver','validation.suffix5.vendor_lp','validation.suffix5.convex_query','validation.suffix5.query'):
   raise ImportError('count-only phase forbids producer/optimizer '+name)
  return None

def source_inventory(root):
 result=binding.source_inventory(root)
 result.update({p.relative_to(root).as_posix():binding.pin(p) for p in (root/'validation/suffix5').rglob('*.py')})
 return dict(sorted(result.items()))

def check_sources(root,commit,expected):
 sources=source_inventory(root)
 binding.require(binding.source_commit(root)==commit and binding.digest(sources)==expected,'census source changed')
 binding.assert_committed_sources(root,sources,commit)
 return sources

def same(a,b,why):binding.require(binding.canonical(a)==binding.canonical(b),why)
def count(value,name):
 binding.require(type(value) is int and value>=0,'invalid exact count: '+name);return value

def census(index,trusted,checked_summary,before=lambda:None):
 """Count authenticated index metadata; no family trust object is fabricated."""
 from validation.real5_v2.suffix_context import count_language
 from validation.family5.checker import _plain
 sources=trusted.source_snapshot();same(index['real_input'],sources,'index physical sources changed')
 binding.require(index['schema']=='hiroute-recorded-query-index-v1' and checked_summary['verified'] is True,
  'complete replay index required')
 for key in ('bundle_sha256','trace_sha256','query_freeze_sha256','case_sha256'):
  same(index[key],checked_summary[key],'checked index '+key+' changed')
 same(index['derived_fields'],sorted(domain.DERIVED),'thin index derived-field contract changed')
 rows=index['queries'];binding.require(type(rows) is list and len(rows)<=QUERY_LIMIT,'query count cap')
 binding.require(len(rows)==count(index['exact_queries'],'index')==count(checked_summary['exact_node_queries'],'checked'),
  'complete query population count changed')
 binding.require(count(index['empty_action_queries'],'empty index')==count(checked_summary['empty_action_queries'],'empty checked'),
  'empty-action population count changed')
 regions={}
 def region(node):
  regions[node['id']]=node
  for child in node['children']:region(child)
 region(trusted.regions)
 seen=set();memo={};out=[];totals=Counter(dict(family_occurrences=0,model_slots=0,graph_exclusions=0,reachable_band_models=0));classifications=Counter();ph=trusted.physics
 for row in rows:
  before();seq=row['query_seq'];binding.require(type(seq) is int and seq>=0 and seq not in seen,'duplicate/invalid original query identity');seen.add(seq)
  binding.require(row['schema']=='family5-exact-real-node-query-v2' and not domain.DERIVED.intersection(row),'invalid thin occurrence schema')
  for key,value in (('source_bundle_sha256',index['bundle_sha256']),('case_sha256',sources['case_sha256']),('region_tree_sha256',sources['region_tree_sha256'])):
   same(row[key],value,'query source changed: '+key)
  state=row['state'];binding.require(type(state) is list and len(state)==3 and type(state[0]) is str and
   type(state[1]) is int and state[1] in (0,1) and type(state[2]) is int and 0<=state[2]<ph.bound,'query state shape')
  families=row['family_ids'];binding.require(type(families) is list and families and all(type(x) is str and len(x)==64 and all(c in '0123456789abcdef' for c in x) for x in families),'original family IDs required')
  binding.require(type(row['H_remaining']) is int and type(state[2]) is int and row['H_remaining']==ph.bound-state[2],'remaining stop bound changed')
  rid=row['region_id'];binding.require(type(rid) is int and rid in regions,'original Region identity changed')
  same(row['region_members'],_plain(regions[rid]['members']),'original Region members changed')
  effect=row['effect'];binding.require(type(effect) is str and effect in ('C','S','CS'),'query effect')
  expected=[[site,effect] for site in regions[rid]['members'] if effect in ph.sites[site] and
   ph.anchors[site]!=ph.destination and (effect=='C' or state[1]==1)]
  same(row['actions'],expected,'complete original Region action set changed')
  binding.require(bool(expected),'empty-action occurrences must use the separate frozen population')
  key=(tuple(state),tuple(map(tuple,expected)))
  if key not in memo:memo[key]=count_language(trusted,state,expected)
  counts=memo[key];n=len(families);models=n*counts['models_per_family']
  totals['family_occurrences']+=n;totals['model_slots']+=models
  totals['graph_exclusions']+=n*counts['graph_exclusion_models_per_family']
  totals['reachable_band_models']+=n*counts['reachable_band_models_per_family']
  binding.require(type(row['classification']) is str and row['classification'] in ('queued','unreachable'),'nonempty query classification')
  classifications[row['classification']]+=1
  out.append(dict(query_seq=seq,query_index_position=len(out),family_occurrences=n,model_slots=models,
   graph_exclusions=n*counts['graph_exclusion_models_per_family'],reachable_band_models=n*counts['reachable_band_models_per_family'],
   ancestry_bundle_sha256=row['ancestry_bundle_sha256'],thin_occurrence_sha256=binding.digest(row)))
 return dict(schema='hiroute-real-suffix-count-v1',count_only=True,solver_calls=0,lp_matrix_constructions=0,
  numerical_suffix_verified=False,literal_G8_closed=False,exact_queries=len(rows),
  empty_action_queries=index['empty_action_queries'],empty_action_sha256=index['empty_action_sha256'],
  query_freeze_sha256=index['query_freeze_sha256'],source_bundle_sha256=index['bundle_sha256'],
  real_input=sources,totals=dict(totals),classifications=dict(sorted(classifications.items())),
  distinct_count_states=len(memo),maximum_occurrence_models=max((r['model_slots'] for r in out),default=0),queries=out,
  scope='all original family/word/arrival-band slots, including graph exclusions; no energy-feasibility pruning or LP execution')

def completed_inputs(root,args,deadline,before=lambda:None):
 """Authenticate the completed replay before loading its thin occurrence index."""
 original=replay_plan.historical_plan(root,args.historical_plan,args.historical_plan_sha)
 replay=replay_plan.historical_plan(root,args.replay_plan,args.replay_plan_sha)
 replay_plan.same_capture_scope(original,replay)
 attempt=Path(args.replay_attempt);evidence=attempt/'evidence'
 successful=read_pinned(args.replay_return,args.replay_return_sha,65536)
 for name,sha in (('result.json',args.replay_result_sha),('decision.json',args.replay_decision_sha)):
  read_pinned(attempt/name,sha,65536)
 result=read_phase_result(attempt,successful_return=successful,deadline_monotonic=deadline,resource_check=before)
 binding.require(result['status']=='completed' and result['descendants_reaped'] is True,'replay successful return or cold evidence incomplete')
 same(result['profile'],asdict(BATCH_REPLAY),'completed replay resource profile changed')
 manifest=read_pinned(evidence/'__manifest.json',args.replay_manifest_sha,1024**2)
 binding.require(result['verified_manifest_sha256']==args.replay_manifest_sha,'completed replay manifest binding changed')
 files={r['path']:r for r in manifest['files']}
 binding.require(len(files)==len(manifest['files']),'duplicate replay manifest file')
 def read(name,limit=4*1024**2):
  spec=files[name];binding.require(type(spec['size_bytes']) is int and spec['size_bytes']<=limit,'evidence size cap '+name)
  value=read_pinned(evidence/name,spec['sha256'],limit);before();return value
 run=read('run-binding.json');summary=read('structural-summary.json');parallel=read('parallel-summary.json')
 binding.require(run['schema']=='hiroute-parallel-replay-binding-v1' and parallel['schema']=='hiroute-complete-parallel-replay-v1',
  'complete parallel replay schemas required')
 binding.require(run.get('shared_query_digest')=='owned-canonical-node-cache-v1' and run['batch_kernel']=='interval-join-v1',
  'expected complete cached endpoint-join replay required')
 for doc in (run,parallel):
  same(doc['historical_plan_sha256'],args.historical_plan_sha,'historical plan binding changed')
  same(doc['current_plan_sha256'],args.replay_plan_sha,'completed replay plan binding changed')
  same(doc['input_sha256'],original['input_sha256'],'completed physical input changed')
 same(run['source_sha256'],replay['source_sha256'],'run source binding changed')
 same(parallel['current_source_sha256'],replay['source_sha256'],'parallel source binding changed')
 from .parallel_replay import input_context
 context_args=SimpleNamespace(historical_plan_sha=args.historical_plan_sha,batch_kernel=run['batch_kernel'],
  shared_query_digest=True,**run['capture_commitments'])
 expected=dict(plan_sha256=args.replay_plan_sha,source_sha256=replay['source_sha256'],
  input_sha256=input_context(context_args,original),profile_name=BATCH_REPLAY.name)
 same(result['context'],expected,'runtime return does not bind this complete replay')
 binding.require(summary['structural_verified'] is True and parallel['structural_verified'] is True and
  summary['literal_G8_closed'] is False and parallel['literal_G8_closed'] is False,'structural completion flags changed')
 same(summary['source_plan_sha256'],args.historical_plan_sha,'structural historical plan changed')
 same(summary['source_sha256'],original['source_sha256'],'structural historical source changed')
 same(summary['input_sha256'],original['input_sha256'],'structural physical input changed')
 same(summary['variant'],domain.variant(original),'original solver variant changed')
 for field,name in (('structural_summary','structural-summary.json'),('batch_ledger','batch-ledger.json'),
  ('query_index','query-index.json'),('callback_receipts','callback-receipts.json')):
  same(parallel[field],files[name],'complete output binding changed: '+field)
 for field,name in (('query_index','query-index.json'),('callback_receipts','callback-receipts.json')):
  same(summary[field],files[name],'structural output binding changed: '+field)
 binding.require(files['query-index.json']['sha256']==args.query_index_sha,'pinned original query index changed')
 index=read('query-index.json',INDEX_LIMIT)
 same(index['source_plan_sha256'],args.historical_plan_sha,'index historical plan changed')
 binding.require(index['capture_sha256']==run['capture_sha256']==summary['capture_sha256']==parallel['capture_sha256'],
  'original capture identity changed')
 trusted=domain.trusted_case(original,root)
 same(summary['checked']['real_input'],trusted.source_snapshot(),'checked physical source changed')
 anchors=dict(replay_plan_sha256=args.replay_plan_sha,
  historical_plan_sha256=args.historical_plan_sha,successful_return_sha256=args.replay_return_sha,
  manifest_sha256=args.replay_manifest_sha,query_index=files['query-index.json'],
  structural_summary=files['structural-summary.json'],parallel_summary=files['parallel-summary.json'],
  capture_sha256=index['capture_sha256'],reference_comparison=summary['reference_comparison'])
 from .variant_scope import D0_PLAN_SCHEMA,physical_scope,D0,REPRESENTATION
 if original['schema']==D0_PLAN_SCHEMA:
  physical_scope(original)
  anchors.update(variant_id=D0,dominance=False,representation=REPRESENTATION)
 before();return index,trusted,summary,anchors

def worker(args):
 writer=None
 def before():binding.require(math.isfinite(args.deadline) and time.monotonic()<args.deadline,'count deadline')
 try:
  binding.require(os.environ.get('HIROUTE_PROFILE')==REPLAY.name and
   os.environ.get('HIROUTE_EVIDENCE_CAP_BYTES')==str(REPLAY.worker_evidence_bytes),'count requires exact reviewed phase guard')
  binding.require(not any(n=='validation' or n.startswith(('validation.','timecut5')) or
   n.split('.')[0] in ('numpy','scipy','sympy') for n in sys.modules),'mathematics imported before count fence')
  _,hard=resource.getrlimit(resource.RLIMIT_AS);resource.setrlimit(resource.RLIMIT_AS,(WORKER_AS,hard))
  sys.meta_path.insert(0,NoOptimization());sources=check_sources(binding.ROOT,args.source_commit,args.source_sha);before()
  index,trusted,summary,anchors=completed_inputs(binding.ROOT,args,args.deadline,before)
  if getattr(args,'logical_model_plan',False):
   from .logical_models import count_logical_models
   result=count_logical_models(index,trusted,summary['checked'],before)
  else:result=census(index,trusted,summary['checked'],before)
  result.update(evidence=anchors,census_source_commit=args.source_commit,census_source_sha256=args.source_sha,
   resource_scope=dict(worker_as_bytes=WORKER_AS,absolute_seconds=SECONDS))
  raw=binding.canonical(result)+b'\n';binding.require(len(raw)<=OUTPUT_LIMIT,'count report byte cap')
  writer=BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],REPLAY.worker_evidence_bytes,profile_name=REPLAY.name)
  writer.write('suffix-census.json',[raw])
  from .worker import verify_loaded
  verify_loaded({'source_files':sources})
  check_sources(binding.ROOT,args.source_commit,args.source_sha);before()
  writer.finalize();return 0
 except BaseException as error:worker_failure(type(error).__name__,str(error)[:4096],'suffix-count-only');return 1
 finally:
  if writer is not None:writer.close()

def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--deadline',type=float)
 for name in ('historical-plan','replay-plan','replay-attempt','replay-return'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('historical-plan-sha','replay-plan-sha','replay-return-sha','replay-manifest-sha','replay-result-sha',
  'replay-decision-sha','query-index-sha','source-commit','source-sha'):p.add_argument('--'+name,required=True)
 p.add_argument('--cpu',type=int);p.add_argument('--attempt-dir',type=Path)
 p.add_argument('--logical-model-plan',action='store_true');args=p.parse_args()
 if args.worker:return worker(args)
 binding.require(args.cpu is not None and args.attempt_dir is not None,'explicit CPU and fresh attempt required')
 deadline=float(ENTRY+SECONDS);check_sources(binding.ROOT,args.source_commit,args.source_sha)
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.suffix_census','--worker','--deadline',repr(deadline)]
 for key,value in vars(args).items():
  if key not in ('worker','deadline','cpu','attempt_dir','logical_model_plan'):argv+=['--'+key.replace('_','-'),str(value)]
 if args.logical_model_plan:argv.append('--logical-model-plan')
 context=binding.digest({k:str(v) for k,v in vars(args).items() if k not in ('worker','deadline','cpu','attempt_dir')})
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=REPLAY,cpu=args.cpu,
  context=PlanContext(args.replay_plan_sha,args.source_sha,context,REPLAY.name),entry_monotonic=float(ENTRY),deadline_monotonic=deadline)
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
