"""Original bindings and prospective full selection; no input or graph load."""
import hashlib
import json
from pathlib import Path
from experiments.mechanism_recovery_v1 import run as base

PLAN_PATH=Path(__file__).resolve().parents[2]/'docs/dev_coverage_prospective_selection_20261017.json'
PLAN_SHA256='6bd0445d1559148116b195d23582b6faa83aee65a9d4438cec4dc605cebc918a'
A_CASES=tuple('OD'+n+'_energy_and_scheduled_soc19_25' for n in ('01','03','04','05'))
B_CASES=('OD08_energy_and_scheduled_soc19_25','OD09_energy_and_scheduled_soc19_25',
    'OD06_energy_and_scheduled_soc3_10','OD07_energy_and_scheduled_soc3_10')

def selection():
    raw=PLAN_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PLAN_SHA256:raise ValueError('Prospective eight-query selection changed')
    value=json.loads(raw)
    if tuple(c['query_id'] for c in value['cases'])!=A_CASES+B_CASES:raise ValueError('Prespecified membership differs')
    for case in value['cases']:
        domains=case['domains']
        if [d['candidate_count'] for d in domains]!=[32,128]:raise ValueError('Original N order differs')
        for d in domains:
            b=d['original_binding']
            hashes=(d['original_pool_prefix_sha256'],b['candidate_site_ids_sha256'],b['candidate_sha256'])
            if (b['query']['case_id']!=case['query_id'] or
                base.digest(b['query'])!=b['query_sha256'] or
                any(type(h) is not str or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in hashes)):
                raise ValueError('Original prespecified domain binding differs')
    return value

PLAN=selection()
LINKED_GATE_DOMAIN=('OD06_energy_and_scheduled_soc3_10',128)
QUEUE=tuple((case,n) for n in (32,128) for case in B_CASES if (case,n)!=LINKED_GATE_DOMAIN)
LINKED_GATE=dict(case_id=LINKED_GATE_DOMAIN[0],candidate_count=128,expected_hmax=39,
    operational_slots=5,method_rows=2,rerun=False,included_in_new_denominator=False,
    evidence='validation/dev_coverage_tranche_v1/prerequisite_pair.json',
    manifest_sha256='2ceabaff97baae82e50e33e2f3ca10cf6df168eb6582be72d32da75f9b0fe151',
    ledger_sha256='939fdcb0bbe07687161c549b2664be552fdf3fa7db89179b36f5a59e2aa0bc27',
    terminal_audit_sha256='c1c839be4aa37ac5d16a1c6f1c5d369a8dabfe7b6427e9b7b632271b01125e9b',
    full_grid_coverage_status='separate_existing_gate_pending_equivalence_authentication',
    mismatch_policy='unqualified_coverage_never_replacement')

def spec_for(manifest,case_id):
    n=manifest.get('candidate_count')
    if case_id not in B_CASES or type(n) is not int or (case_id,n) not in QUEUE or manifest.get('case_id')!=case_id:
        raise ValueError('Outside runnable Tranche B case/N allowlist')
    row=next(c for c in PLAN['cases'] if c['query_id']==case_id)
    spec=next(d for d in row['domains'] if d['candidate_count']==n)
    if manifest.get('case_binding')!=spec:raise ValueError('Manifest exact original case/N binding differs')
    return spec
