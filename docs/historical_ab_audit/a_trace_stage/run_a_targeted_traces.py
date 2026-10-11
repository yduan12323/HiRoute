"""New observational A trace recovery, never represented as the original A stream."""
import hashlib,json,resource,signal,sys,time
from fractions import Fraction as R
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
STAGE=ROOT/'a_trace_stage'
A=STAGE/'results/milestone_5_coalescing_prototype/frozen_A'
TRACE=STAGE/'results/milestone_5_acceptance_b64/acceptance_populations/bound_audit/production_trace_v1'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stop(*_):raise TimeoutError('A targeted trace exceeded 180 seconds')
signal.signal(signal.SIGALRM,stop);signal.alarm(180)
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
start=time.monotonic();sys.path.insert(0,str(TRACE))
import trace_runner as t
t.verify_freeze()
from frozen_reference5 import lp,solver
calls=[]
def forbidden(*args,**kwargs):
 calls.append(1);raise RuntimeError('NoOptimization: REF LP entrypoint called')
lp.linprog=lp.exact_lp=solver.exact_lp=forbidden
files=['physical_cases_h4.json','physical_supplement.json','physical_merge_supplement.json'];case_sha={n:sha(A/n) for n in files}
cases=sum((json.loads((A/n).read_text()) for n in files),[])
summary=json.loads((A/'FINAL_STAGE_A_RESULTS.json').read_text());expected={x['case_id']:x for x in summary['case_rows']}
assert len(cases)==len(expected)==28 and {c['case_id'] for c in cases}==set(expected)
rows=[];totals={'region_decisions':0,'partitions':0,'prunes':0,'unreachable':0,'coverage_groups':0}
for c in cases:
 case_id=c['case_id'];saved=expected[case_id]
 for dom in (False,True):
  out=ROOT/'traces'/case_id/f'D{int(dom)}.jsonl.gz';out.parent.mkdir(parents=True,exist_ok=True)
  row=t.run(c,dom,out);actual=row['result']['result'];prior=saved['key_or_infimum']
  assert actual['status']==prior['status']==saved['status'],case_id
  for field,value in prior.items():
   if field=='status':continue
   if field=='site_action_tuple':assert tuple(map(tuple,actual[field]))==tuple(map(tuple,value)),(case_id,field)
   elif field in ('H',):assert actual[field]==value,(case_id,field)
   else:assert R(actual[field])==R(value),(case_id,field)
  assert row['complete_output_equivalence'] is True
  for k in totals:totals[k]+=row['trace_audit'][k]
  rows.append({'case_id':case_id,'dominance':dom,'source_case_sha256':t.sha_object(c),'trace_sha256':sha(out),'event_count':row['events'],'audit':row['trace_audit'],'saved_status_key_match':True,'frozen_vs_observational_equivalent':True})
assert len(rows)==56 and not calls
receipt={'schema':'hiroute-stage-a-targeted-new-observational-traces-v1','scope':'28 retained H4 A cases, two HIER dominance modes; new trace evidence under B frozen 579c6db source, not original stream_execution_v1','status':'passed','case_count':28,'variant_traces':56,'source_input_sha256':case_sha,'stage_a_result_sha256':sha(A/'FINAL_STAGE_A_RESULTS.json'),'trace_source_manifest_sha256':sha(TRACE/'trace_freeze.json'),'rows':rows,'totals':totals,'optimizer_calls':len(calls),'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
with (ROOT/'a_targeted_trace_receipt.json').open('x') as f:json.dump(receipt,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:receipt[k] for k in ('status','case_count','variant_traces','totals','optimizer_calls','elapsed_seconds','peak_rss_kib')},sort_keys=True))
