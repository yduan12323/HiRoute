import sys,json
from pathlib import Path
from fractions import Fraction as R
P=Path(sys.argv[1]).resolve();sys.path.insert(0,str(P/'independent_model'))
from model import normalize_case,selected_legs,sequences,replay_witness
import gzip,hashlib
L=json.load(open(P/'ref_authority_updated_ledger.json'))['rows']; wanted={x['case_id']:x for x in L if x['missing_final_result_authority']}
cases={x['case_id']:x for n in ['physical_cases_h4.json','physical_supplement.json','physical_merge_supplement.json','b_cases.json'] for x in json.load(open(P/n))}
for label in ('a','b'):
 tr=json.load(open(P/('current_'+label+'_trace_receipt.json')))
 for name,digest in tr['input_sha256'].items():assert hashlib.sha256((P/name).read_bytes()).hexdigest()==digest
 br=json.load(open(P/('current_'+label+'_bound_receipt.json')))
 assert hashlib.sha256((P/'independent_model/model.py').read_bytes()).hexdigest()==br['independent_model_sha256']
closed=[];open_rows=[]
for cid,source in cases.items():
 if cid not in wanted:continue
 c=normalize_case(source);legs=selected_legs(c);lo=[];n=0
 for seq,remaining,current in sequences(c,legs):
  if remaining or (current,c['destination']) not in legs:continue
  n+=1;drive=energy=R(0);pos=c['origin'];prefix_drive=[]
  for site,effect in seq:
   leg=legs[pos,site];drive+=leg.time;energy+=leg.energy;prefix_drive.append(drive);pos=site
  leg=legs[pos,c['destination']];drive+=leg.time;energy+=leg.energy
  charge=max(R(0),energy+c['reserve_kwh']-c['initial_energy_kwh']);slope=min((s[2] for s in c['charging_segments']),default=R(0));D=slope*charge
  base=drive+len(seq)*(c['overhead_s']+c['lambda_stop_s']);service=next(((i,e) for i,(_,e) in enumerate(seq) if e in ('S','CS')),None)
  if service:
   i,e=service;duration=c['schedule']['D'];lb=base+(D+duration if e=='S' else max(D,duration));tail=drive-prefix_drive[i];absolute=c['schedule']['a']+duration-c['start_time_s']+tail+(len(seq)-i-1)*c['overhead_s']+len(seq)*c['lambda_stop_s'];lb=max(lb,absolute)
  else:lb=base+D
  lo.append((lb,seq,charge))
 target=wanted[cid].get('key_or_infimum',wanted[cid].get('key'));J=R(target['J']) if isinstance(target,dict) and target.get('J') is not None else R(target[0]) if isinstance(target,list) else None
 mini=min((x[0] for x in lo),default=None)

 if J is None or mini!=J or wanted[cid]['status']!='attained_optimum':
  open_rows.append({'case_id':cid,'minimum_lower_bound':str(mini),'retained_J':str(J),'reason':'bound_gap_or_unattained'})
  continue
 expected=(R(target['J']),R(target['Q_total']),target['H'],tuple(map(tuple,target['site_action_tuple']))) if isinstance(target,dict) else (R(target[0]),R(target[1]),target[2],tuple(map(tuple,target[3])))
 critical=[];safe=True
 for lb,seq,q in lo:
  if lb!=J:continue
  # For a fixed sequence, q is a universal lower bound on total charge.
  # If q ties at zero but any C/CS exists, exact q=0 is forbidden by strict positivity.
  possible_equal_q=not(q==0 and any(e in ('C','CS') for _,e in seq))
  min_key=(lb,q,len(seq),seq)
  if q<expected[1] or (q==expected[1] and possible_equal_q and (len(seq),seq)<expected[2:]):safe=False
  critical.append({'sequence':[list(a) for a in seq],'J_bound':str(lb),'Q_bound':str(q),'strict_positive_charge_excludes_Q_zero':not possible_equal_q,'lex_floor_is_not_smaller':q>expected[1] or (q==expected[1] and (not possible_equal_q or (len(seq),seq)>=expected[2:]))})
 if not safe:
  open_rows.append({'case_id':cid,'minimum_lower_bound':str(mini),'retained_J':str(J),'reason':'lex_lower_bound_gap','critical':critical});continue
 pop='B64' if cid.startswith('B') else 'A28';file='current_b_traces' if pop=='B64' else 'current_a_traces';tp=P/file/cid/'D0.jsonl.gz'
 trace_receipt=json.load(open(P/('current_b_trace_receipt.json' if pop=='B64' else 'current_a_trace_receipt.json')))
 assert any(row['case_id']==cid and row['dominance'] is False and row['trace_sha256']==hashlib.sha256(tp.read_bytes()).hexdigest() for row in trace_receipt['rows'])
 with gzip.open(tp,'rt') as f:
  last=None
  for line in f:last=json.loads(line)
 assert last['kind']=='run_end'
 result=last['payload']['canonical']['result'];seq=tuple(map(tuple,result['site_action_tuple']));charges=result['charges']
 witness=replay_witness(source,seq,charges,legs=legs)
 actual=witness['lex_key'];assert actual==expected,(cid,actual,expected)
 assert (R(result['J']),R(result['Q_total']),result['H'],seq)==expected
 closed.append({'case_id':cid,'source_case_sha256':hashlib.sha256(json.dumps(source,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'trace_sha256':hashlib.sha256(tp.read_bytes()).hexdigest(),'status':'attained_optimum','full_key':[str(actual[0]),str(actual[1]),actual[2],[list(a) for a in actual[3]]],'terminal_sequence_count':n,'global_J_lower_bound':str(mini),'critical_sequences':critical,'witness_charges':[str(x) for x in witness['charges']],'witness_replayed_independently':True})
 print(cid,'CLOSED',len(critical),flush=True)
import hashlib as _h
out={'schema':'hiroute-analytic-66-no-lp-complete-result-proof-v1','input_ledger_sha256':_h.sha256((P/'ref_authority_updated_ledger.json').read_bytes()).hexdigest(),'independent_model_sha256':_h.sha256((P/'independent_model/model.py').read_bytes()).hexdigest(),'closed':closed,'open':open_rows,'summary':{'closed':len(closed),'open':len(open_rows)}}
outp=Path(sys.argv[2]);outp.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('TOTAL',out['summary'])
