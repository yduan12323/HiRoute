"""Fixed tiny cold-process timing only; routing cold/warm remains separate."""
from pathlib import Path
import hashlib,json,subprocess,sys,time,resource
R=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mp=R/'TIMING_PLAN.json';M=json.loads(mp.read_text())
if sha(mp)!=(R/'TIMING_PLAN.sha256').read_text().strip():raise ValueError('Timing plan hash changed')
if sha(Path(__file__))!=M['runner_sha256']:raise ValueError('Runner changed')
base=R/'PREREGISTERED_PLAN.json'
if sha(base)!=M['base_plan_sha256']:raise ValueError('Base plan changed')
P=json.loads(base.read_text())
for p,h in P['runtime_sources'].items():
 if sha(R/p)!=h:raise ValueError(p)
cp=R/'source/results/milestone_5_reference/frozen_cases_v2.json'
if sha(cp)!=P['cases_sha256']:raise ValueError('Cases changed')
if len(sys.argv)>1:
 setup=time.perf_counter_ns();row=M['rows'][int(sys.argv[1])]
 resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2);resource.setrlimit(resource.RLIMIT_CPU,(29,30))
 sys.path.insert(0,str(R/'runtime'))
 from fractions import Fraction as F
 from timecut5.bounded import solve_bounded,replay_witness
 from timecut5.hierarchy import solve_hierarchical
 from timecut5.coalesced_solver import solve_bounded_coalesced,solve_hierarchical_coalesced
 case=next(c for c in json.loads(cp.read_text()) if c['case_id']==row['case_id'])
 fn={('flat',False):solve_bounded,('hier',False):solve_hierarchical,('flat',True):solve_bounded_coalesced,('hier',True):solve_hierarchical_coalesced}[row['method'],row['coalescing']]
 setup_ns=time.perf_counter_ns()-setup;t=time.perf_counter_ns();cpu=time.process_time_ns()
 result=fn(case,dominance=row['reduction'])
 solver_cpu_ns=time.process_time_ns()-cpu;solver_wall_ns=time.perf_counter_ns()-t
 audit=time.perf_counter_ns();actual=result.canonical()['result'];expected=case['independent_expected']
 def sig(d):
  s=d['status']
  if s=='attained_optimum':return s,F(d['J']),F(d['Q_total']),d['H'],tuple(map(tuple,d['site_action_tuple']))
  if s=='primary_unattained':return s,F(d['primary_infimum'])
  if s=='secondary_unattained':return s,F(d['J']),F(d['secondary_infimum'])
  return (s,)
 if sig(actual)!=sig(expected):raise ValueError('Frozen independent expected mismatch')
 inner=result.inner if row['coalescing'] else result;bounded=inner.bounded if hasattr(inner,'bounded') else inner
 if bounded.result.witness is not None and replay_witness(case,bounded.result.witness)!=bounded.result.key:raise ValueError('Witness mismatch')
 audit_ns=time.perf_counter_ns()-audit
 print(json.dumps(dict(**row,status='pass',setup_ns=setup_ns,solver_wall_ns=solver_wall_ns,solver_cpu_ns=solver_cpu_ns,audit_wall_ns=audit_ns,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,outcome=actual,coalescing_statistics=result.canonical().get('coalescing_statistics')),default=str));sys.exit()
out=R/'TIMING_RESULTS.jsonl'
if out.exists():raise ValueError('Refusing overwrite')
start=time.monotonic()
with out.open('w') as f:
 for i,row in enumerate(M['rows']):
  left=M['total_wall_seconds']-(time.monotonic()-start);t=time.perf_counter_ns()
  if left<=0:record=dict(**row,status='unscheduled_after_batch_limit')
  else:
   try:
    p=subprocess.run([sys.executable,__file__,str(i)],capture_output=True,text=True,timeout=min(30,left))
    record=json.loads(p.stdout) if p.returncode==0 else dict(**row,status='worker_failed',stderr=p.stderr[-3000:],returncode=p.returncode)
   except subprocess.TimeoutExpired:record=dict(**row,status='time_limit')
  record['parent_row_total_wall_ns']=time.perf_counter_ns()-t;f.write(json.dumps(record)+'\n');f.flush()
rows=[json.loads(x) for x in out.read_text().splitlines()]
summary=dict(plan_sha256=sha(mp),scheduled=len(rows),passed=sum(x['status']=='pass' for x in rows),batch_wall_seconds=time.monotonic()-start,cold_warm_routing_executed=False)
(R/'TIMING_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
