import json,hashlib,time,collections
from pathlib import Path
from timecut5.bounded import solve_bounded
from timecut5.hierarchy import solve_hierarchical
from validation.reference5.solver import solve_case,jsonable
ROOT=Path('/workspace/shared/navigation_audit/audit_multistop_solver_parity')
PROD=Path('/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut/src/timecut5')
REF=Path('/workspace/shared/navigation_audit/ref5_work/validation/reference5')
files=[PROD/n for n in ['bounded.py','hierarchy.py','pwa.py','probe.py']]+[REF/n for n in ['model.py','solver.py','lp.py']]
def hashes():return {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
start_hashes=hashes();cases=json.loads((ROOT/'seeded_cases_v1.json').read_text())
def key(r):
 if r['status']=='attained_optimum':return r['status'],r['lex_key']
 if r['status']=='primary_unattained':return r['status'],r['primary_infimum']
 if r['status']=='secondary_unattained':return r['status'],r['J'],r['secondary_infimum']
 return r['status'],
counts=collections.Counter();prunes=equalities=checks=0
with (ROOT/'final_revision_results.jsonl').open('x') as out:
 for c in cases:
  env=solve_case(c,keep_evidence=False);ref=jsonable(env['result']);counts[ref['status']]+=1
  rec=dict(case_id=c['case_id'],reference=ref,all_regimes_certified=env['all_regimes_certified'],regime_count=env['regime_count'],comparisons=[])
  assert env['all_regimes_certified']
  for d in [False,True]:
   for name,solver in [('FLAT',solve_bounded),('HIER',solve_hierarchical)]:
    v=solver(c,d);r=jsonable(v.canonical()['result']);entry=dict(solver=name,dominance=d,result=r,matches_reference=key(r)==key(ref))
    if name=='HIER':
     entry.update(pruned_regions=v.pruned_regions,equality_nodes_retained=v.equality_nodes_retained,missing_actions=v.missing_actions,duplicate_actions=v.duplicate_actions)
     if d:prunes+=v.pruned_regions;equalities+=v.equality_nodes_retained
    rec['comparisons'].append(entry);checks+=1
    assert entry['matches_reference'],rec
  out.write(json.dumps(rec)+'\n');out.flush();print(c['case_id'],flush=True)
summary=dict(case_count=len(cases),comparison_count=checks,reference_status_counts=dict(counts),hierarchy_d_on_prunes=prunes,hierarchy_d_on_equalities=equalities,fixture_sha256=hashlib.sha256((ROOT/'seeded_cases_v1.json').read_bytes()).hexdigest(),source_hashes_at_start=start_hashes,source_hashes_at_end=hashes(),sources_unchanged=start_hashes==hashes(),scope='New independently seeded bounded H_ref=2 diagnostic cases, no real-data or scalability claim. Frozen before solving; random population is not a completeness proof.')
(ROOT/'final_revision_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
