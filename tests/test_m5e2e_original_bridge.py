"""Focused bridge admission tests. Not executed: no certified global test budget."""
import hashlib
import json
import pytest
from ci import m5e2e_original_bridge as bridge


def test_ledger_rejects_unsettled_attempt():
    with pytest.raises(bridge.AdmissionError, match='unsettled'):
        bridge._ledger_totals(b'{"kind":"start","invocation_id":"x","phase":"ref"}\n')


def test_ledger_rejects_unverified_cleanup():
    rows=[{'kind':'start','invocation_id':'x','phase':'ref'},
          {'kind':'end','invocation_id':'x','phase':'ref','cpu_seconds':0,'wall_seconds':0,'cleanup_verified':False}]
    with pytest.raises(bridge.AdmissionError, match='cleanup'):
        bridge._ledger_totals(b'\n'.join(bridge._canonical(row) for row in rows))


def test_claim_is_create_once_and_root_scoped(tmp_path):
    first=bridge._claim_once(tmp_path,{'schema':'test'})
    assert first==tmp_path/bridge.CLAIM_RELATIVE
    with pytest.raises(FileExistsError):
        bridge._claim_once(tmp_path,{'schema':'different'})
    assert json.loads(first.read_text())=={'schema':'test'}


def test_caller_declared_empty_unknowns_do_not_certify_accounting(tmp_path):
    account={'schema':bridge.ACCOUNT_SCHEMA,'unknown_costs':[],
        'accounting_complete':True,'external_charges':[],'reservations':[]}
    path=tmp_path/'account.json'; path.write_bytes(bridge._canonical(account))
    with pytest.raises(bridge.AdmissionError,match='schema/fields'):
        bridge.validate_master_accounting(path,hashlib.sha256(path.read_bytes()).hexdigest(),
                                          tmp_path,'trusted-run-id')



def test_jsonl_append_round_trips_start_end(tmp_path):
    ledger=tmp_path/'phase_ledger.jsonl'
    start={'kind':'start','invocation_id':'one','phase':'ref'}
    end={'kind':'end','invocation_id':'one','phase':'ref','cpu_seconds':1,
         'wall_seconds':2,'cleanup_verified':True}
    bridge._append_jsonl(ledger,start)
    bridge._append_jsonl(ledger,end)
    raw=ledger.read_bytes()
    assert raw.endswith(b'\\n')
    assert raw.count(b'\\n') == 2
    cpu,wall,starts,ends=bridge._ledger_totals(raw)
    assert (cpu,wall)==(1,2)
    assert set(starts)==set(ends)=={'one'}


def test_accounting_evidence_amount_tampering_is_rejected(tmp_path):
    evidence=tmp_path/'evidence.json'
    record={'schema':'hiroute.m5e2e.accounting_evidence.v1','id':'charge-1',
            'kind':'charge','cpu_seconds':3,'wall_seconds':4}
    raw=bridge._canonical(record)
    evidence.write_bytes(raw)
    row={'id':'charge-1','cpu_seconds':99,'wall_seconds':4,
         'evidence':{'path':str(evidence),'sha256':hashlib.sha256(raw).hexdigest()}}
    with pytest.raises(bridge.AdmissionError,match='content/ID/amount'):
        bridge._verify_evidence(row,'charge')


def test_master_root_change_keeps_same_authoritative_claim_root(tmp_path):
    parent=tmp_path/'original'/'waited_round_receipt.json'
    configuration={'sha256':'a'*64}
    freeze={'continuation_admission':{'parent_waited_receipt':
        {'path':str(parent),'sha256':'b'*64}}}
    first_id,first_root=bridge._trusted_run_identity(freeze,configuration)
    second_id,second_root=bridge._trusted_run_identity(freeze,configuration)
    assert first_id==second_id
    assert first_root==second_root==parent.parent


def test_wrapper_identity_drift_is_rejected(tmp_path):
    package=tmp_path/'venv'/'lib'/'python3.11'/'site-packages'/'ci'
    package.mkdir(parents=True)
    prefix=tmp_path/'venv'/'lib'/'python3.11'/'site-packages'
    parent=b'parent-wrapper'
    worker=b'worker-wrapper'
    (package/'m5e2e_original_bridge.py').write_bytes(parent)
    (package/'m5e2e_original_bridge_worker.py').write_bytes(worker)
    identity={'schema':'hiroute.m5e2e.original_bridge_wrapper.v1','modules':{
        'm5e2e_original_bridge.py':hashlib.sha256(parent).hexdigest(),
        'm5e2e_original_bridge_worker.py':hashlib.sha256(worker).hexdigest()}}
    (package/'original_bridge_identity.json').write_bytes(bridge._canonical(identity))
    assert bridge._verify_wrapper_identity(package,prefix)==hashlib.sha256(
        bridge._canonical(identity)).hexdigest()
    (package/'m5e2e_original_bridge_worker.py').write_bytes(b'drifted-worker')
    with pytest.raises(bridge.AdmissionError,match='identity drift'):
        bridge._verify_wrapper_identity(package,prefix)


def test_worker_command_is_isolated_and_binds_all_inputs():
    command=bridge._ref_worker_command('/venv/bin/python',
        {'path':'/cfg','sha256':'c'*64},{'path':'/manifest','sha256':'m'*64},
        {'path':'/common','sha256':'n'*64},'w'*64)
    assert command[:4]==['/venv/bin/python','-I','-m','ci.m5e2e_original_bridge_worker']
    assert command[-2:]==['--wrapper-identity-sha256','w'*64]
    assert '--configuration-sha256' in command and '--manifest-sha256' in command
    assert '--common-sha256' in command


def test_ref_result_authentication_failure_blocks_followup():
    with pytest.raises(bridge.AdmissionError,match='independent exact authentication'):
        bridge._require_authenticated_ref({'status':'SUCCESS','independent_exact':False})
