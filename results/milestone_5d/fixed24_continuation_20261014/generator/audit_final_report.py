"""Independent terminal ledger/receipt reconciliation; no experiment execution."""
import json,hashlib
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'supplement_report_work/final_v2_20261014_0845'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_bytes())
r=load(OUT/'public_report.json');original=load(ROOT/'fixed_supplement_work/ORIGINAL_NUMERICAL_MANIFEST.json')
assert len(r['rows'])==24 and r['denominator']==24 and r['pending_rows']==0
assert [{k:x[k] for k in ident} for x,ident in zip(r['rows'],original['rows'])]==original['rows']
assert r['rows'][1]['status']=='infrastructure_unknown' and r['rows'][1]['last_durable_phase']=='seed_started'
assert all(x['exact_outcome'] is None for x in r['rows'])
assert all(x['flat_over_hier_wall_ratio'] is None for x in r['pairs'])
rows=[];charge=Decimal(0);controller=Decimal(0);child=Decimal(0)
for base in ('fixed_supplement_work','fixed_supplement_recovery_work'):
 ledger=load(ROOT/base/'ledger.json');assert ledger['blocked'] is False
 for a in ledger['attempts']:
  i=a['index'];ident=original['rows'][i];assert a['row_id']==ident['row_id']
  receipt_path=ROOT/base/'receipts'/a['row_id']/'receipt.json';receipt=load(receipt_path)
  if i==1:
   assert a['state']=='reserved' and receipt['complete'] is False
   continue
  assert a['state']=='finished' and receipt==a['receipt']
  assert receipt['complete'] is True and receipt['cleanup_verified'] is True
  assert receipt['reason']=='wall_timeout' and a['status'] is None
  assert 600<=receipt['wall_seconds']<610
  assert a['charged_conservative_cpu_s']<=670
  assert abs(a['charged_conservative_cpu_s']-a['controller_cpu_s']-receipt['conservative_wait4_cpu_seconds'])<.1
  phase_path=ROOT/base/'runs'/a['row_id']/'phase.jsonl'
  phases=[json.loads(line) for line in phase_path.read_text().splitlines() if line.strip()]
  assert phases[-1]==a['last_durable_phase'] and phases[-1]['phase']=='seed_started'
  assert not (ROOT/base/'runs'/a['row_id']/'status.json').exists()
  assert r['rows'][i]['status']=='time_limit' and r['rows'][i]['cleanup_verified'] is True
  charge+=Decimal(str(a['charged_conservative_cpu_s']));controller+=Decimal(str(a['controller_cpu_s']));child+=Decimal(str(receipt['conservative_wait4_cpu_seconds']))
  rows.append({'index':i,'row_id':a['row_id'],'receipt_sha256':digest(receipt_path),'phase_sha256':digest(phase_path),'cleanup_verified':True})
assert len(rows)==23 and {x['index'] for x in rows}==set(range(24))-{1}
assert abs(Decimal(str(r['continuation_accounting']['known_row_conservative_charges_seconds']))-charge)<Decimal('0.000000001')
audit={'schema':'hiroute.fixed24.final_receipt_audit.v1','result':'PASS','audit_source_sha256':digest(Path(__file__)),'normalized_report_sha256':digest(OUT/'public_report.json'),
 'denominator':24,'verified_clean_wall_timeouts':23,'infrastructure_unknown':1,'all_recorded_terminal_phases':'seed_started','exact_results':0,'comparable_exact_pairs':0,
 'transportation_evidence':'unavailable; no sequential feasible claim; conditional regeneration skipped',
 'combined_checkpoint_trial':'separate ongoing evidence; not in fixed24',
 'known_row_conservative_charge_decimal_seconds':str(charge),'measured_controller_decimal_seconds':str(controller),'wait4_conservative_decimal_seconds':str(child),
 'unknown_row_reservation_seconds':670,'preparation_conservative_seconds':480,'conservative_accounted_total_decimal_seconds':str(charge+670+480),
 'unique_measured_total_CPU':'unavailable; wait4 may double-count descendants; unknown row and preparation are allocations',
 'historical_48h_host_tail':'still unresolved; unchanged','rows':rows}
(OUT/'public_receipt_audit.json').write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in audit.items() if k!='rows'},indent=2))
