"""Independent no-LP complete-result infeasibility for 13 fixed H4 cases."""
import argparse,hashlib,json,sys,time
from fractions import Fraction as R
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True);a=p.parse_args();root=Path(a.root).resolve()
sys.path.insert(0,str(root/'independent_model'));sys.path.insert(0,str(root/'src'))
from model import normalize_case,selected_legs,sequences
from timecut5.bounded import Problem
from timecut5 import provenance
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b_ids=('B21','B22','B29','B30','B37','B38','B45','B46','B53','B54','B61','B62')
cases={x['case_id']:x for n in ('physical_cases_h4.json','b_cases.json') for x in json.loads((root/n).read_text())}
selected=('S07_effect_free_via_site_excluded',)+b_ids
ar=json.loads((root/'current_a28_receipt.json').read_text());br=json.loads((root/'current_b64_receipt.json').read_text());rows=[];start=time.monotonic()
for cid in selected:
 raw=cases[cid];c=normalize_case(raw);legs=selected_legs(c);problem=Problem(raw)
 for key,leg in legs.items():
  got=problem.legs[key];assert (leg.time,leg.energy,leg.nodes,leg.edges)==(got.time,got.energy,got.path,got.edge_ids)
 enumerated=list(sequences(c,legs));terminal=[(seq,remaining,current) for seq,remaining,current in enumerated if not remaining and (current,c['destination']) in legs]
 if cid.startswith('B'):
  assert not terminal,(cid,terminal)
  reason='no reachable service-complete static sequence with final selected leg'
  detail={'enumerated_prefixes':len(enumerated),'terminal_discrete_sequences':0}
 else:
  assert len(terminal)==1 and terminal[0][0]==(),terminal
  leg=legs[c['origin'],c['destination']]
  assert leg.energy>c['initial_energy_kwh']-c['minimum_energy_kwh']
  assert not any(c['sites'].values()) and c['charging_segments']==()
  reason='only empty stop sequence; selected direct leg exceeds initial energy above floor'
  detail={'enumerated_prefixes':len(enumerated),'terminal_discrete_sequences':1,'direct_time':str(leg.time),'direct_energy':str(leg.energy),'initial_energy':str(c['initial_energy_kwh']),'floor':str(c['minimum_energy_kwh']),'excluded_effect_free_site':'v'}
 match=[r for r in (br if cid.startswith('B') else ar)['rows'] if r['case_id']==cid]
 assert len(match)==4 and all(r['status']=='infeasible_within_H_ref' for r in match)
 rows.append({'case_id':cid,'case_object_sha256':hashlib.sha256(provenance.encoded(raw).encode()).hexdigest(),'reason':reason,'detail':detail,'current_four_modes':[r['mode'] for r in match],'status':'independent_structural_infeasibility'})
receipt={'schema':'hiroute-no-lp-structural-final-v1','source_commit':'d51367ca5a8a109d3a76c35ebbc55ac4edc361bf','source_sha256':{p.name:sha(p) for p in sorted((root/'src/timecut5').glob('*.py'))},'independent_model_sha256':sha(root/'independent_model/model.py'),'input_sha256':{n:sha(root/n) for n in ('physical_cases_h4.json','b_cases.json')},'four_mode_receipt_sha256':{'A':sha(root/'current_a28_receipt.json'),'B':sha(root/'current_b64_receipt.json')},'rows':rows,'case_count':len(rows),'elapsed_seconds':time.monotonic()-start,'status':'passed'}
Path(a.output).write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n');print(json.dumps({'cases':len(rows),'seconds':receipt['elapsed_seconds'],'status':'passed'}))
