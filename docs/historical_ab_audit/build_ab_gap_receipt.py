import gzip,hashlib,json
from collections import Counter,defaultdict
from fractions import Fraction
from pathlib import Path
base=Path(__file__).resolve().parent
tree=base/'ab_evidence_tree/results'
a=tree/'milestone_5_coalescing_prototype/frozen_A'
b=tree/'milestone_5_acceptance_b64/acceptance_populations'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
final=read(a/'FINAL_STAGE_A_RESULTS.json'); rows={r['case_id']:r for r in final['case_rows']}
tr=base/'a_trace_recovered';receipt=read(tr/'a_targeted_trace_receipt.json')
assert receipt['status']=='passed' and receipt['case_count']==28 and receipt['variant_traces']==56
assert receipt['stage_a_result_sha256']==sha(a/'FINAL_STAGE_A_RESULTS.json')
aevents=[];variants=[];counts=Counter();queries=defaultdict(set)
for r in receipt['rows']:
 p=tr/'traces'/r['case_id']/f"D{int(r['dominance'])}.jsonl.gz"
 assert sha(p)==r['trace_sha256']
 with gzip.open(p,'rt') as f: envelopes=[json.loads(s) for s in f]
 assert len([e for e in envelopes if e['kind']=='event'])==r['event_count']
 variants.append({'case_id':r['case_id'],'dominance':r['dominance'],'trace_path':str(p.relative_to(base)),'trace_sha256':sha(p),'source_case_sha256':r['source_case_sha256'],'event_count':r['event_count']})
 saved=rows[r['case_id']]['key_or_infimum'];J=saved.get('J',saved.get('primary_infimum'))
 for e in envelopes:
  if e['kind']!='event' or e['event']['kind'] not in ('region_decision','unreachable'):continue
  v=e['event'];kind=v['kind'];status='unreachable_requires_independent_reachability_check' if kind=='unreachable' else ('global_infimum_sufficient' if J is not None and Fraction(v['lower_bound'])<=Fraction(J) else 'local_superset_proof_required' if v.get('decision')=='prune' else 'no_global_primary_infimum')
  if kind=='region_decision' and J is not None and Fraction(v['lower_bound'])>Fraction(J) and v.get('decision')!='prune':status='local_superset_proof_required'
  counts[status]+=1
  item={'case_id':r['case_id'],'dominance':r['dominance'],'trace_sha256':r['trace_sha256'],'event_index':e['index'],'event_kind':kind,'decision':v.get('decision'),'prefix':v['prefix'],'actions':v['actions'],'lower_bound':v['lower_bound'],'saved_global_primary_infimum':J,'status':status}
  aevents.append(item)
  if status=='local_superset_proof_required':queries[r['case_id']].add((json.dumps(v['prefix'],sort_keys=True),json.dumps(v['actions'],sort_keys=True)))
assert len(variants)==56 and sum(counts.values())==1114 and counts['local_superset_proof_required']==139 and counts['global_infimum_sufficient']==848 and counts['no_global_primary_infimum']==8 and counts['unreachable_requires_independent_reachability_check']==119,counts
assert all(e['decision']=='prune' for e in aevents if e['status']=='local_superset_proof_required')
bout=base/'b64_g8_node_reaudit_20261011.json';bd=read(bout);assert len(bd['nodes'])==1551 and bd['primary_bound_safety_complete']
seen={};bcounts=Counter()
for n in bd['nodes']:
 p=b/'bound_audit/production_trace_v1/runs'/n['case_id']/f"D{int(n['dominance'])}.jsonl.gz"
 assert p.exists() and sha(p)==n['trace_sha256']
 key=(n['case_id'],n['dominance'],n['trace_event']);seen.setdefault(str(p),set()).add(key);bcounts[n['status']]+=1
 rp=b/n['reference_provenance']['path'];assert sha(rp)==n['reference_provenance']['sha256']
 if 'bound_proof_provenance' in n:
  pp=b/n['bound_proof_provenance']['path'];assert sha(pp)==n['bound_proof_provenance']['sha256']
assert dict(bcounts)==bd['status_counts']
for ps,keys in seen.items():
 with gzip.open(ps,'rt') as f:
  actual={(e.get('index'),e.get('event',{}).get('kind')):e for e in map(json.loads,f) if e.get('kind')=='event'}
 for _,_,ix in keys:assert (ix,'region_decision') in actual or (ix,'unreachable') in actual
out={'schema':'hiroute-ab-retained-gap-ledger-v1','source_scope':'Recovered checkpoint patch and bounded new observational trace, no original A stream_execution_v1','a':{'final_report_sha256':sha(a/'FINAL_STAGE_A_RESULTS.json'),'new_trace_receipt_sha256':sha(tr/'a_targeted_trace_receipt.json'),'new_trace_source_manifest_sha256':receipt['trace_source_manifest_sha256'],'variants':variants,'event_status_counts':dict(counts),'events':aevents,'unique_local_superset_queries':[{ 'case_id':cid,'prefix':json.loads(p),'actions':json.loads(actions)} for cid,items in sorted(queries.items()) for p,actions in sorted(items)],'missing_original_files':['execution_freeze.json','h4_registration.json','supplement_registration.json','merge_registration.json','stream_execution_v1/runs/h4/*'],'other_unrecorded_obligations':['dynamic action/refinement events','dominance-deletion continuation certificates'],'estimated_local_query_union_regimes':26155,'estimated_local_query_union_terminal_sequences':150,'regime_estimate_status':'preflight count only; no REF models run'},'b':{'reaudit_sha256':sha(bout),'node_count':len(bd['nodes']),'status_counts':dict(bcounts),'primary_bound_safety_complete':bd['primary_bound_safety_complete'],'exact_node_emptiness_classification_complete':bd['exact_node_emptiness_classification_complete'],'missing_original_report':'bound_audit/g8_current_v3.json','missing_raw_v2_regime_streams':52,'node_evidence_path':'b64_g8_node_reaudit_20261011.json','scope':bd['scope']}}
outp=base/'ab_gap_ledger_20261011.json';outp.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(outp,sha(outp));print('A',counts,'unique queries',len(out['a']['unique_local_superset_queries']));print('B',bcounts)
