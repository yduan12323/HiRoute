"""Frozen small-domain checks. No performance conclusions; fresh bounded worker per row."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time,resource
R=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan_path=R/'PREREGISTERED_PLAN.json'
assert sha(plan_path)==(R/'PREREGISTERED_PLAN.sha256').read_text().strip()
P=json.loads(plan_path.read_text())
for p,h in P['runtime_sources'].items():assert sha(R/p)==h,p
cp=R/'source/results/milestone_5_reference/frozen_cases_v2.json'
assert sha(cp)==P['cases_sha256']
cases={c['case_id']:c for c in json.loads(cp.read_text())}
if len(sys.argv)>1:
 row=P['rows'][int(sys.argv[1])];resource.setrlimit(resource.RLIMIT_AS,(P['correctness']['row_address_space_bytes'],)*2)
 resource.setrlimit(resource.RLIMIT_CPU,(29,30));sys.path.insert(0,str(R/'runtime'))
 from fractions import Fraction as F
 from timecut5.bounded import solve_bounded,replay_witness
 from timecut5.hierarchy import solve_hierarchical
 from timecut5.coalesced_solver import solve_bounded_coalesced,solve_hierarchical_coalesced
 fn={('flat',False):solve_bounded,('hier',False):solve_hierarchical,('flat',True):solve_bounded_coalesced,('hier',True):solve_hierarchical_coalesced}[row['method'],row['coalescing']]
 case=cases[row['case_id']];result=fn(case,dominance=row['reduction']);actual=result.canonical()['result'];expected=case['independent_expected']
 def signature(d):
  s=d['status']
  if s=='attained_optimum':return s,F(d['J']),F(d['Q_total']),d['H'],tuple(map(tuple,d['site_action_tuple']))
  if s=='primary_unattained':return s,F(d['primary_infimum'])
  if s=='secondary_unattained':return s,F(d['J']),F(d['secondary_infimum'])
  return (s,)
 assert signature(actual)==signature(expected),(row,actual,expected)
 inner=result.inner if row['coalescing'] else result
 bounded=inner.bounded if hasattr(inner,'bounded') else inner
 if bounded.result.witness is not None:assert replay_witness(case,bounded.result.witness)==bounded.result.key
 print(json.dumps(dict(**row,status='pass',outcome=actual,coalescing_statistics=result.canonical().get('coalescing_statistics')),default=str));sys.exit()
output=R/'CORRECTNESS_RESULTS.jsonl'
if output.exists():raise SystemExit('Refusing overwrite; preserve old results')
start=time.monotonic()
with output.open('w') as f:
 for i,row in enumerate(P['rows']):
  left=P['correctness']['total_wall_seconds']-(time.monotonic()-start)
  if left<=0:record=dict(**row,status='unscheduled_after_batch_limit')
  else:
   try:
    result=subprocess.run([sys.executable,__file__,str(i)],capture_output=True,text=True,timeout=min(left,P['correctness']['row_wall_seconds']))
    record=json.loads(result.stdout) if result.returncode==0 else dict(**row,status='worker_failed',returncode=result.returncode,stderr=result.stderr[-4000:])
   except subprocess.TimeoutExpired:record=dict(**row,status='time_limit')
  f.write(json.dumps(record)+'\n');f.flush()
records=[json.loads(x) for x in output.read_text().splitlines()]
summary=dict(plan_sha256=sha(plan_path),scheduled=len(records),passed=sum(x['status']=='pass' for x in records),elapsed_wall_seconds=time.monotonic()-start,performance_run=False)
(R/'CORRECTNESS_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
