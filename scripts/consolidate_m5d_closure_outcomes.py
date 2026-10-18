#!/usr/bin/env python3
"""Reproduce typed outcome/evidence entrypoints from public projections.

This checks bookkeeping, not optimality, feasibility or original raw provenance.
"""
import argparse, collections, hashlib, json
from pathlib import Path

def digest(raw): return hashlib.sha256(raw).hexdigest()
def read(path):
 raw=path.read_bytes();return raw,json.loads(raw)
def main():
 p=argparse.ArgumentParser();p.add_argument('--main-rows',type=Path,required=True);p.add_argument('--supplement-report',type=Path,required=True);p.add_argument('--supplement-audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 mr=a.main_rows.read_bytes(); m=[json.loads(x) for x in mr.splitlines() if x.strip()]; sr,s=read(a.supplement_report); ar,v=read(a.supplement_audit)
 if len(m)!=192 or len({x['row_id'] for x in m})!=192 or any(x.get('denominator_included') is not True for x in m): raise ValueError('Invalid original-main denominator')
 if collections.Counter(x['status'] for x in m)!={'time_limit':148,'incumbent_search_failed':44}:raise ValueError('Main distribution differs from reviewed evidence')
 if s['schema']!='hiroute.fixed24.report.v2' or s['mode']!='terminal_accounting' or s['pending_rows']!=0 or s['denominator']!=24:raise ValueError('Supplement is not terminal fixed24 projection')
 rows=s['rows']
 if len(rows)!=24 or len({x['row_id'] for x in rows})!=24 or any(x.get('denominator_included') is not True for x in rows):raise ValueError('Invalid supplemental denominator')
 if collections.Counter(x['status'] for x in rows)!={'time_limit':23,'infrastructure_unknown':1}:raise ValueError('Supplement distribution differs from reviewed evidence')
 if v['result']!='PASS' or v['normalized_report_sha256']!=digest(sr) or v['denominator']!=24:raise ValueError('Audit is not bound to this report')
 receipts={x['row_id']:x for x in v['rows']}
 if len(receipts)!=23 or set(receipts)!={x['row_id'] for x in rows if x['status']=='time_limit'}:raise ValueError('Receipt audit does not cover exactly 23 known terminal rows')
 allrows=[];checks=[]
 for x in m:
  allrows.append({'population':'original_main','source_public_projection_sha256':digest(mr),**x})
 for x in rows:
  if x.get('exact_outcome') is not None:raise ValueError('Unexpected exact outcome requires proof-aware consolidation')
  allrows.append({'population':'fixed24_post_start_supplement','source_public_projection_sha256':digest(sr),**x})
  q=receipts.get(x['row_id'])
  if q is not None:
   if q['cleanup_verified'] is not True or x['cleanup_verified'] is not True:raise ValueError('Known terminal cleanup not verified')
   check={'verification_kind':'retained_process_receipt_and_phase_audit','result':'pass','cleanup_verified':True,'receipt_sha256':q['receipt_sha256'],'phase_sha256':q['phase_sha256'],'scope':'Audit projection records original receipt/phase checks; original private bytes are not supplied here.'}
  else:check={'verification_kind':'infrastructure_interruption_accounting','result':'unknown','cleanup_verified':None,'scope':'Prior execution namespace unavailable; this is not a cleanup or solver correctness pass.'}
  checks.append({'population':'fixed24_post_start_supplement','row_id':x['row_id'],'audit_projection_sha256':digest(ar),'solver_witness_verification':'not_available_no_terminal_witness',**check})
 checks.insert(0,{'population':'original_main','verification_kind':'public_projection_denominator_check','result':'pass','denominator':192,'input_sha256':digest(mr),'scope':'Unique row identities, retained denominator and status counts only; does not independently revalidate original server receipts or solver outcomes.'})
 a.output.mkdir(parents=True,exist_ok=False)
 for name,data in [('benchmark_results.jsonl',allrows),('verification_results.jsonl',checks)]:
  (a.output/name).write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in data))
 (a.output/'normalization_manifest.json').write_text(json.dumps({'schema':'hiroute.m5d.closure.normalization.v1','generator_sha256':digest(Path(__file__).read_bytes()),'input_sha256':{'original_main_rows':digest(mr),'fixed24_report':digest(sr),'fixed24_audit':digest(ar)},'population_denominators':{'original_main':192,'fixed24_post_start_supplement':24},'pooled_effect_estimate':None,'original_private_bytes_authenticated':False,'combined_checkpoint_included':False,'result_files_sha256':{n:digest((a.output/n).read_bytes()) for n in ['benchmark_results.jsonl','verification_results.jsonl']}},indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
