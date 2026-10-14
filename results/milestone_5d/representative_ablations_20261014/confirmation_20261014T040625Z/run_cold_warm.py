"""Tiny routing-cache ablation below a fresh verified admission boundary."""
from pathlib import Path
import hashlib,json,sys,time,subprocess,resource,tempfile,os
R=Path(__file__).resolve().parent
sha_file=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mp=R/'COLD_WARM_EXECUTION_PLAN.json';M=json.loads(mp.read_text())
if sha_file(mp)!=(R/'COLD_WARM_EXECUTION_PLAN.sha256').read_text().strip():raise ValueError('Plan changed')
for name,h in M['files'].items():
 if sha_file(R/name)!=h:raise ValueError(name)
if len(sys.argv)>1:
 row=M['rows'][int(sys.argv[1])];resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2);resource.setrlimit(resource.RLIMIT_CPU,(29,30))
 sys.path[:0]=[str(R/'runtime'),str(R/'source')]
 from fractions import Fraction as F
 from fixture_source import fixture,Router
 from timecut5.sparse_seed import replay_sparse_seed
 from timecut5.streaming_seed_diagnostic import StreamingSeedObserver
 from timecut5.feasible_incumbent import canonical,sha,verifier_sources
 from timecut5.sparse_feasible_execution import experimental_policy,admit_sparse_feasible,_check_policy
 from timecut5.road_provider import TableFreeRegionBoundProvider
 from timecut5.real_adapter import TableFreeRealProblem
 from timecut5.hierarchy import build_regions,_solve_hierarchical_problem
 from timecut5.bounded import _solve_problem
 protocol=json.loads((R/'COLD_WARM_PROTOCOL.json').read_text());seed=protocol['initial_seed'][row['case_id']]
 with tempfile.TemporaryDirectory() as d:
  d=Path(d);q,c,paths=fixture(d/'input',row['case_id']);sequence=tuple(map(tuple,seed['sequence']));charges=tuple(map(F,seed['charges']))
  replay=replay_sparse_seed(q,c,sequence,charges)
  observer=StreamingSeedObserver(q,c,output_dir=d/'checkpoint',provenance={'fixture':row['case_id']})
  observer('incumbent',sequence=sequence,charges=charges,lex_key=replay['lex_key'],edge_witnesses=replay['edge_witnesses'],status='replayed_feasible_incumbent');observer.journal.close();c.provider.router.close()
  # Snapshot fabrication uses a separate provider. The measured row admits fresh bytes.
  setup=time.perf_counter_ns();q,c,paths=fixture(d/'input',row['case_id']);provider=c.provider
  if provider.legs or provider.source_run_count:raise ValueError('Not cold before admission')
  checkpoint=d/'checkpoint/snapshot.json';policy=experimental_policy(canonical(q),c)
  inputs=dict(checkpoint_path=checkpoint,expected_checkpoint_sha256=sha(checkpoint.read_bytes()),query_bytes=canonical(q),catalog=c,approved_verifier_sha256=verifier_sources(),**paths)
  a=admit_sparse_feasible(recovery_inputs=inputs,policy_bytes=policy,expected_policy_sha256=sha(policy))
  initial_cache=sha(canonical(sorted((u,v,str(leg.time),str(leg.actual_length),provider.edge_witnesses[u,v]) for (u,v),leg in provider.legs.items())))
  if provider.source_cache_max_bytes!=0:raise ValueError('Source label cache unexpectedly enabled')
  root=build_regions(c.sites,leaf_size=1)
  bound=TableFreeRegionBoundProvider(provider,c.sites,root,destination_anchor=c.destination_anchor,landmark_anchor=c.origin_anchor,site_catalog_sha256=c.site_catalog_sha256,router_factory=Router)
  query=dict(json.loads(a.incumbent.query_bytes),H_ref=a.incumbent.max_depth)
  initial=dict(primary_upper=str(a.incumbent.primary_upper),depth=a.incumbent.max_depth,cache_sha256=initial_cache,landmark_sha256=bound.landmark_sha256)
  setup_ns=time.perf_counter_ns()-setup
  def counts():return dict(source_runs=provider.source_run_count,selected_pairs=len(provider.legs),routing_wall_ns=provider.route_wall_ns,routing_cpu_ns=provider.route_process_cpu_ns)
  def diff(a,b):return {k:b[k]-a[k] for k in a}
  def execute():
   _check_policy(policy,sha(policy),inputs)
   before=counts();t=time.perf_counter_ns();cpu=time.process_time_ns()
   problem=TableFreeRealProblem(query,c.sites,provider,origin_anchor=query['origin'],destination_anchor=query['destination'],site_catalog_sha256=c.site_catalog_sha256)
   value=(_solve_problem(problem,verified_primary_upper=a.incumbent.primary_upper,singleton_bound=bound.singleton_bound) if row['method']=='flat' else _solve_hierarchical_problem(problem,True,root,verified_primary_upper=a.incumbent.primary_upper,bound_provider=bound).bounded)
   solver_ns=time.perf_counter_ns()-t;solver_cpu=time.process_time_ns()-cpu;after=counts();t=time.perf_counter_ns()
   if value.result.status!='attained_optimum' or value.result.witness is None:raise ValueError('Fixture expected attained terminal')
   w=value.result.witness;ch=tuple(e.departure_energy-e.arrival_energy for e in w.events if e.effect in ('C','CS'))
   checked=replay_sparse_seed(query,c,w.pi,ch)
   if checked['lex_key']!=value.result.key or value.result.key[0]>a.incumbent.primary_upper:raise ValueError('Terminal replay/upper mismatch')
   audit_ns=time.perf_counter_ns()-t;replayed=counts();_check_policy(policy,sha(policy),inputs)
   return dict(solver_wall_ns=solver_ns,solver_cpu_ns=solver_cpu,audit_wall_ns=audit_ns,engine_routing_delta=diff(before,after),replay_routing_delta=diff(after,replayed),key=value.result.key,cache_before=before,cache_after=replayed)
  warmup=execute() if row['condition']=='warm_after_same_method_solve' else None
  measured=execute()
  if warmup and warmup['key']!=measured['key']:raise ValueError('Warm key changed')
  provider.router.close()
  print(json.dumps(dict(**row,status='pass',initial=initial,setup_ns=setup_ns,warmup=warmup,measured=measured,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),default=str));sys.exit()
out=R/'COLD_WARM_RESULTS.jsonl'
if out.exists():raise ValueError('Refusing overwrite')
start=time.monotonic()
with out.open('w') as f:
 for i,row in enumerate(M['rows']):
  left=180-(time.monotonic()-start);t=time.perf_counter_ns()
  if left<=0:record=dict(**row,status='unscheduled_after_batch_limit')
  else:
   try:
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    p=subprocess.run([sys.executable,__file__,str(i)],capture_output=True,text=True,timeout=min(30,left),env=env)
    record=json.loads(p.stdout) if p.returncode==0 else dict(**row,status='worker_failed',stderr=p.stderr[-4000:],returncode=p.returncode)
   except subprocess.TimeoutExpired:record=dict(**row,status='time_limit')
  record['parent_row_total_wall_ns']=time.perf_counter_ns()-t;f.write(json.dumps(record)+'\n');f.flush()
rows=[json.loads(x) for x in out.read_text().splitlines()];passed=[x for x in rows if x['status']=='pass']
checks=[]
for case in M['cases']:
 for rep in range(3):
  group=[x for x in passed if x['case_id']==case and x['repeat']==rep]
  checks.append(dict(case=case,repeat=rep,four_rows=len(group)==4,equal_initial=len({json.dumps(x['initial'],sort_keys=True) for x in group})==1,equal_terminal=len({json.dumps(x['measured']['key']) for x in group})==1))
summary=dict(scheduled=len(rows),passed=len(passed),wall_seconds=time.monotonic()-start,paired_checks=checks,all_pair_checks_pass=all(all(x[k] for k in ['four_rows','equal_initial','equal_terminal']) for x in checks))
(R/'COLD_WARM_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
