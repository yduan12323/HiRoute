"""Focused bridge admission tests. Not executed: no certified global test budget."""
import hashlib
import json
import pytest
from experiments.m5e2e_v1 import original_bridge as bridge


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


def test_unknown_costs_block_master_accounting(tmp_path):
    ledger=tmp_path/'phase_ledger.jsonl'; ledger.write_bytes(b'{}')
    account={'schema':bridge.ACCOUNT_SCHEMA,'master_root':str(tmp_path),'budget_root':str(tmp_path),
      'cpu_cap_seconds':bridge.CPU_CAP,'wall_cap_seconds':bridge.WALL_CAP,
      'phase_ledger':{'path':str(ledger),'sha256':hashlib.sha256(b'{}').hexdigest()},
      'external_charges':[],'reservations':[],'unknown_costs':['unresolved'],'unsettled_invocations':[],
      'charged_cpu_seconds':0,'charged_wall_seconds':0,'reserved_cpu_seconds':0,'reserved_wall_seconds':0,
      'remaining_cpu_seconds':bridge.CPU_CAP,'remaining_wall_seconds':bridge.WALL_CAP,'accounting_complete':False}
    path=tmp_path/'account.json'; path.write_bytes(bridge._canonical(account))
    with pytest.raises(bridge.AdmissionError,match='incomplete'):
        bridge.validate_master_accounting(path,hashlib.sha256(path.read_bytes()).hexdigest(),tmp_path)
