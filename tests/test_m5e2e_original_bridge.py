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
    assert raw.endswith(b'\n')
    assert raw.count(b'\n') == 2
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
    waited={'path':str(parent),'sha256':'b'*64}
    admission={'schema':'hiroute.m6h.parent_receipt_continuation.v1',
        'parent_waited_receipt':waited}
    raw=bridge._canonical(admission)
    admission_path=tmp_path/'continuation-admission.json'
    admission_path.write_bytes(raw)
    freeze={'continuation_admission':{'path':str(admission_path),
        'sha256':hashlib.sha256(raw).hexdigest()}}
    configuration={'sha256':'a'*64}
    # Caller-selected master roots do not enter this identity derivation.
    first_id,first_root=bridge._trusted_run_identity(freeze,configuration)
    alternate_requested_master_root=tmp_path/'different-master-root'
    second_id,second_root=bridge._trusted_run_identity(freeze,configuration)
    assert alternate_requested_master_root != first_root
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
        {'path':'/common','sha256':'n'*64},'w'*64,'r'*64,'/freeze.json','f'*64,
        '/attestation.json',operation='arm',strategy='flat')
    assert command[:4]==['/venv/bin/python','-I','-m','ci.m5e2e_original_bridge_worker']
    assert command[4:6]==['--operation','arm']
    assert command[-2:]==['--strategy','flat']
    assert '--invocation-freeze' in command and '--freeze-sha256' in command
    assert '--wrapper-identity-sha256' in command
    assert '--configuration-sha256' in command and '--manifest-sha256' in command
    assert '--common-sha256' in command


def test_ref_result_authentication_failure_blocks_followup():
    with pytest.raises(bridge.AdmissionError,match='independent exact authentication'):
        bridge._require_authenticated_ref({'status':'SUCCESS','independent_exact':False})



def test_original_method_phase_is_exactly_external_300():
    class Physical:
        @staticmethod
        def phase_identity(manifest, manifest_sha256, strategy, common_sha256):
            return {'case_id':'N8','strategy':strategy,
                    'manifest_sha256':manifest_sha256,'common_sha256':common_sha256}
    identity=bridge._method_phase_identity(Physical,{},'m'*64,'c'*64,'flat','r'*64)
    assert identity['strategy']=='flat'
    receipt={'status':'SUCCESS','cleanup_verified':True,
             'phase_budget':{'seconds':300,'identity':identity}}
    assert bridge._classify_300_second_method_receipt(receipt,identity)=='SUCCESS'


def test_original_method_300_timeout_is_not_legacy_phase_timeout():
    identity={'nonce':'n','run_identity_sha256':'r'}
    receipt={'status':'TIMEOUT','cleanup_verified':True,
             'phase_budget':{'seconds':300,'identity':identity}}
    assert bridge._classify_300_second_method_receipt(receipt,identity)=='EXTERNAL_LIMIT_UNVERIFIED'
    legacy={'status':'PHASE_TIMEOUT','cleanup_verified':True,
            'phase_budget':{'seconds':1200,'identity':identity}}
    assert bridge._classify_300_second_method_receipt(legacy,identity)=='IDENTITY_MISMATCH'


def test_invocation_freeze_is_immutable_and_canonical(tmp_path):
    path=tmp_path/'invocation-freeze.json'
    frozen={'schema':'hiroute.m5e2e.original_bridge_invocation.v1',
        'run_identity':'r'*64,'wrapper_identity_sha256':'w'*64}
    digest=bridge._write_frozen_invocation(path,frozen)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    assert json.loads(path.read_bytes())==frozen
    with pytest.raises(FileExistsError):
        bridge._write_frozen_invocation(path,frozen)


def test_worker_invocation_loader_uses_passed_arguments_not_main_global(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from ci import m5e2e_original_bridge_worker as worker

    freeze = {
        'schema': 'hiroute.m5e2e.original_bridge_invocation.v1',
        'run_identity': 'r' * 64,
        'wrapper_identity_sha256': 'w' * 64,
        'interpreter_path': str(__import__('pathlib').Path(__import__('sys').executable).resolve()),
        'interpreter_sha256': 'i' * 64,
        'source_identity_sha256': 's' * 64,
        'configuration': {'path': '/cfg', 'sha256': 'c' * 64},
        'manifest': {'path': '/manifest', 'sha256': 'm' * 64},
        'common': {'path': '/common', 'sha256': 'n' * 64},
        'master_accounting_sha256': 'a' * 64,
        'phase_ledger_sha256': 'l' * 64,
        'run_root': str(tmp_path.resolve()),
        'planned_method_order': ['flat', 'hier'],
    }
    raw = bridge._canonical(freeze)
    path = tmp_path / 'invocation.json'
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(worker, '_verify_wrapper_identity', lambda: 'w' * 64)
    monkeypatch.setattr(worker, '_sha256_file', lambda _: 'i' * 64)
    args = SimpleNamespace(
        invocation_freeze=str(path), freeze_sha256=digest, operation='ref',
        attestation=str(tmp_path / 'ref' / 'worker-attestation.json'),
        strategy=None, wrapper_identity_sha256='w' * 64,
        configuration='/cfg', configuration_sha256='c' * 64,
        manifest='/manifest', manifest_sha256='m' * 64,
        common='/common', common_sha256='n' * 64, run_identity='r' * 64,
    )
    assert worker._load_invocation(args) == freeze


def test_incomplete_ref_status_is_recorded_before_authentication_failure():
    report = {'ref_status': 'NOT_RUN'}
    bridge._store_ref_result(report, {'status': 'UNKNOWN', 'reason': 'receipt incomplete'})
    with pytest.raises(bridge.AdmissionError, match='independent exact authentication'):
        bridge._require_authenticated_ref({'status': 'UNKNOWN', 'reason': 'receipt incomplete'})
    assert report['ref_status'] == 'UNKNOWN'
    assert report['ref_reason'] == 'receipt incomplete'


def test_changed_post_ref_ledger_snapshot_blocks_followup(tmp_path):
    ledger = tmp_path / 'phase_ledger.jsonl'
    ledger.write_bytes(b'{}\\n')
    with pytest.raises(bridge.AdmissionError, match='ledger changed after REF'):
        bridge._verify_locked_ledger_snapshot(ledger, '0' * 64)


def test_bridge_complete_is_a_successful_cli_exit():
    assert bridge._exit_code('BRIDGE_COMPLETE') == 0
    assert bridge._exit_code('REF_ATTEMPT_CONSUMED_INCOMPLETE') == 2
