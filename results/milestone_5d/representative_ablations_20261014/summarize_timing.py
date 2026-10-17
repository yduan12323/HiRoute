from pathlib import Path
import json,statistics as st
R=Path(__file__).resolve().parent
rows=[json.loads(x) for x in (R/'TIMING_RESULTS.jsonl').read_text().splitlines()]
lookup={(x['case_id'],x['method'],x['reduction'],x['coalescing'],x['repeat']):x for x in rows}
report=[]
for case in dict.fromkeys(x['case_id'] for x in rows):
 for method in ['flat','hier']:
  for axis in ['reduction','coalescing']:
   ratios=[]
   for rep in range(3):
    # OFAT around reduction-on / coalescing-off anchor.
    a=lookup[case,method,False if axis=='reduction' else True,False,rep]
    b=lookup[case,method,True,True if axis=='coalescing' else False,rep]
    if a['status']==b['status']=='pass' and b['solver_wall_ns']>0:ratios.append(a['solver_wall_ns']/b['solver_wall_ns'])
   report.append(dict(case=case,method=method,axis=axis,paired_repeats=len(ratios),median_off_over_on=st.median(ratios) if ratios else None))
ok=[r for r in rows if r['status']=='pass'];aggregate=dict(scheduled=len(rows),passed=len(ok),solver_wall_seconds=sum(x['solver_wall_ns'] for x in ok)/1e9,solver_cpu_seconds=sum(x['solver_cpu_ns'] for x in ok)/1e9,independent_check_wall_seconds=sum(x['audit_wall_ns'] for x in ok)/1e9,setup_import_wall_seconds=sum(x['setup_ns'] for x in ok)/1e9,parent_row_total_wall_seconds=sum(x['parent_row_total_wall_ns'] for x in rows)/1e9,peak_worker_rss_kib=max(x['peak_rss_kib'] for x in ok),note='Aggregated accounting totals, not paired performance estimates. Solver call includes Problem construction/routing and internal terminal work. Audit is frozen expected-key checking and witness replay, not a new independent REF solve.',pairs=report)
(R/'TIMING_ANALYSIS.json').write_text(json.dumps(aggregate,indent=2)+'\n');print(json.dumps({k:v for k,v in aggregate.items() if k!='pairs'},indent=2))
