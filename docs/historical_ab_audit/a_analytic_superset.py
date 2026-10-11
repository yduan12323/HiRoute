import json,sys,hashlib
from pathlib import Path
from fractions import Fraction as R
from collections import defaultdict,Counter
B=Path(__file__).resolve().parent
sys.path.insert(0,str(B/'ab_evidence_tree/results/milestone_5_acceptance_b64/acceptance_populations/bound_audit/v2'))
from frozen_reference5.model import normalize_case,selected_legs,sequences
sys.path.insert(0,str(B/'ab_evidence_tree/results/milestone_5_acceptance_b64/acceptance_populations/bound_audit/production_trace_v1'))
from traced_timecut5.bounded import Problem
D=json.load(open(B/'ab_gap_ledger_20261011.json'))
A=B/'ab_evidence_tree/results/milestone_5_coalescing_prototype/frozen_A'
raw=sum((json.load(open(A/n)) for n in ['physical_cases_h4.json','physical_supplement.json','physical_merge_supplement.json']),[])
cases={c['case_id']:normalize_case(c) for c in raw}
queries=defaultdict(list)
for q in D['a']['unique_local_superset_queries']:queries[q['case_id']].append((tuple(map(tuple,q['prefix'])),tuple(map(tuple,q['actions']))))
result={};status=Counter()
for cid,qs in queries.items():
 c=cases[cid];legs=selected_legs(c);actual_legs=Problem(next(r for r in raw if r['case_id']==cid)).legs
 for pair,leg in legs.items():
  other=actual_legs[pair]
  assert (leg.time,leg.energy,leg.nodes,leg.edges)==(other.time,other.energy,other.path,other.edge_ids)
 terminal=[]
 for seq,remaining,current in sequences(c,legs):
  if remaining or (current,c['destination']) not in legs:continue
  t=R(0);energy=R(0);pos=c['origin']
  for site,effect in seq:
   leg=legs[pos,site];t+=leg.time;energy+=leg.energy;pos=site
  leg=legs[pos,c['destination']];t+=leg.time;energy+=leg.energy
  charge=max(R(0),energy+c['reserve_kwh']-c['initial_energy_kwh'])
  slope=min((s[2] for s in c['charging_segments']),default=R(0))
  charge_duration=slope*charge
  service=[(i,effect) for i,(_,effect) in enumerate(seq) if effect in ('S','CS')]
  base=t+len(seq)*(c['overhead_s']+c['lambda_stop_s'])
  if service:
   si,se=service[0];duration=c['schedule']['D']
   lb=base+(charge_duration+duration if se=='S' else max(charge_duration,duration))
   # A service cannot finish before a+D. Remaining legs and stop overhead
   # follow it, while all lambda penalties remain due.
   pos=c['origin'];tail=t
   for i,(site,effect) in enumerate(seq):
    leg=legs[pos,site]
    if i<=si:tail-=leg.time
    pos=site
   later_overhead=(len(seq)-si-1)*c['overhead_s']
   absolute=c['schedule']['a']+duration-c['start_time_s']+tail+later_overhead+len(seq)*c['lambda_stop_s']
   lb=max(lb,absolute)
  else:lb=base+charge_duration
  terminal.append((seq,lb,str(t),str(energy),str(charge),str(charge_duration),str(base),str(absolute) if service else None))
 for prefix,actions in qs:
  matches=[(seq,lb,t,e,q,d,base,absolute) for seq,lb,t,e,q,d,base,absolute in terminal if len(seq)>len(prefix) and seq[:len(prefix)]==prefix and seq[len(prefix)] in actions]
  key=(cid,prefix,actions);bound=min((r[1] for r in matches),default=None)
  result[key]={'case_id':cid,'prefix':[list(x) for x in prefix],'actions':[list(x) for x in actions],'terminal_superset_sequences':len(matches),'sequence_certificates':[{'sequence':[list(x) for x in seq],'lower_bound':str(lb),'drive_time':t,'road_energy':e,'required_charge':q,'charge_duration_lower_bound':d,'drive_stop_base':base,'service_absolute_lower_bound':absolute} for seq,lb,t,e,q,d,base,absolute in matches],'lower_bound':str(bound) if bound is not None else None,'proof':'sum selected-leg road times + H*(overhead+lambda) + minimum charging slope*max(0,total road energy + reserve - initial energy). Every exact candidate projects to one enumerated terminal sequence; dropped waits, schedule duration, and battery intermediate constraints.'}
rows=[]
for ev in D['a']['events']:
 if ev['status']!='local_superset_proof_required':continue
 key=(ev['case_id'],tuple(map(tuple,ev['prefix'])),tuple(map(tuple,ev['actions'])));bound=result[key]['lower_bound']
 ok=bound is None or R(ev['lower_bound'])<=R(bound)
 rows.append({'case_id':ev['case_id'],'dominance':ev['dominance'],'trace_sha256':ev['trace_sha256'],'event_index':ev['event_index'],'region_lower_bound':ev['lower_bound'],'analytic_superset_lower_bound':bound,'certified':ok,'query_index':list(result).index(key)})
 status['certified' if ok else 'open']+=1
assert len(result)==74 and len(rows)==139 and status['certified']==139 and status['open']==0
out={'schema':'hiroute-a-analytic-sequence-superset-v1','queries':list(result.values()),'events':rows,'event_status_counts':dict(status),'source_hashes':{n:hashlib.sha256((A/n).read_bytes()).hexdigest() for n in ['physical_cases_h4.json','physical_supplement.json','physical_merge_supplement.json','FINAL_STAGE_A_RESULTS.json']},'trace_source_manifest_sha256':hashlib.sha256((B/'ab_evidence_tree/results/milestone_5_acceptance_b64/acceptance_populations/bound_audit/production_trace_v1/trace_freeze.json').read_bytes()).hexdigest(),'scope':'Conservative exact-rational sequence superset from independently matching frozen selected legs; no LP solves'}
p=B/'a_analytic_superset_result.json';p.write_text(json.dumps(out,indent=2)+'\n');print(p);print(status,len(result));print([(r['case_id'],r['region_lower_bound'],r['analytic_superset_lower_bound']) for r in rows if not r['certified']][:15])
