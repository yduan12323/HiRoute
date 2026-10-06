import json,hashlib
from pathlib import Path
from validation.reference5.solver import solve_case,jsonable
from timecut5.bounded import solve_bounded,evaluate_sequence,replay_witness
from timecut5.hierarchy import solve_hierarchical
root=Path('/workspace/shared/navigation_audit/solver_audit');cases=json.loads((root/'targeted_attainment_cases_v1.json').read_text());results=[]
for c in cases:
 exp=c['independent_expected'];ref=solve_case(c,keep_evidence=False);rr=jsonable(ref['result']);assert ref['all_regimes_certified'];assert all(rr[k]==v for k,v in exp.items()),(c['case_id'],rr)
 rec=dict(case_id=c['case_id'],reference=rr,comparisons=[])
 incumbent=evaluate_sequence(c,tuple(map(tuple,c['external_incumbent_sequence']))).witness
 assert incumbent is not None
 rec['external_incumbent_key']=jsonable(replay_witness(c,incumbent))
 for d in [False,True]:
  f=jsonable(solve_bounded(c,d).canonical()['result']);assert all(f[k]==v for k,v in exp.items());rec['comparisons'].append(dict(solver='FLAT',dominance=d,result=f))
  for external in [False,True]:
   h=solve_hierarchical(c,d,incumbent=incumbent if external else None);r=jsonable(h.canonical()['result']);assert all(r[k]==v for k,v in exp.items()),(c['case_id'],r)
   rec['comparisons'].append(dict(solver='HIER',dominance=d,external_incumbent=external,result=r,equality_nodes_retained=h.equality_nodes_retained,pruned_regions=h.pruned_regions))
 results.append(rec)
(root/'targeted_attainment_results_final.json').write_text(json.dumps(results,indent=2)+'\n');print('PASS: 6 REF cases, 12 FLAT and 24 HIER comparisons, all exact statuses/full attained keys match analytic expectations.')
