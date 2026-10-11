import hashlib,json,sys
from pathlib import Path
from collections import Counter
B=Path(__file__).resolve().parent
sys.path.insert(0,str(B/'ab_evidence_tree/results/milestone_5_acceptance_b64/acceptance_populations/bound_audit/v2'))
from frozen_reference5.model import normalize_case,selected_legs
D=json.load(open(B/'ab_gap_ledger_20261011.json'))
A=B/'ab_evidence_tree/results/milestone_5_coalescing_prototype/frozen_A'
raw=sum((json.load(open(A/n)) for n in ['physical_cases_h4.json','physical_supplement.json','physical_merge_supplement.json']),[])
cases={c['case_id']:normalize_case(c) for c in raw}
legs={k:selected_legs(c) for k,c in cases.items()}
rows=[];counts=Counter()
for ev in D['a']['events']:
 if ev['status'] not in ('no_global_primary_infimum','unreachable_requires_independent_reachability_check'):continue
 c=cases[ev['case_id']];l=legs[ev['case_id']]
 if ev['event_kind']=='unreachable':
  current=ev['prefix'][-1][0] if ev['prefix'] else c['origin']
  checks=[{'site':s,'effect':a,'current_to_site_exists':(current,s) in l,'site_to_destination_exists':(s,c['destination']) in l} for s,a in ev['actions']]
  ok=all(not x['current_to_site_exists'] or not x['site_to_destination_exists'] for x in checks)
  kind='independent_directed_leg_reachability'
  row={'case_id':ev['case_id'],'dominance':ev['dominance'],'trace_sha256':ev['trace_sha256'],'event_index':ev['event_index'],'kind':kind,'checks':checks,'certified':ok}
 else:
  assert ev['case_id']=='A18_capacity_overflow_infeasible'
  direct=l[c['origin'],c['destination']].energy;from_site=l['x',c['destination']].energy
  ok=direct>c['initial_energy_kwh'] and from_site>c['capacity_kwh']
  row={'case_id':ev['case_id'],'dominance':ev['dominance'],'trace_sha256':ev['trace_sha256'],'event_index':ev['event_index'],'kind':'global_capacity_impossibility','direct_origin_destination_energy':str(direct),'initial_energy':str(c['initial_energy_kwh']),'site_destination_energy':str(from_site),'capacity':str(c['capacity_kwh']),'certified':ok}
 counts[(kind if ev['event_kind']=='unreachable' else 'global_capacity_impossibility',ok)]+=1;rows.append(row)
assert counts[('independent_directed_leg_reachability',True)]==119 and counts[('global_capacity_impossibility',True)]==8 and not any(not row['certified'] for row in rows)
out={'schema':'hiroute-a-residual-no-lp-checks-v1','rows':rows,'counts':{str(k):v for k,v in counts.items()},'source_case_sha256':{r['case_id']:hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest() for r in raw}}
p=B/'a_residual_result.json';p.write_text(json.dumps(out,indent=2)+'\n');print(counts)
