"""Gate lifecycle only; integration must exercise actual deterministic verifier."""
from unittest.mock import patch
import pytest
from experiments.m6h_manifest_v1 import physical, physical_inputs, physical_queue_adapter
from experiments.m6h_manifest_v1 import synthetic_worker as worker


def test_unverified_fixture_never_enters_gate():
    with patch.object(worker, '_verify', side_effect=ValueError('not independently synthetic')):
        with pytest.raises(ValueError, match='independently'):
            with worker._verified_scope([dict(path='/not/read',sha256='a'*64)]):
                pytest.fail('unverified scope entered')
    for module in (physical,physical_inputs,physical_queue_adapter):
        with pytest.raises(PermissionError):module.require_root_freeze()


def test_private_scope_restores_gate_after_exception():
    # Unit lifecycle test only: this mock is not an executable fixture admission.
    modules=(physical,physical_inputs,physical_queue_adapter)
    original=[m.require_root_freeze for m in modules]
    with patch.object(worker, '_verify') as verifier:
        with pytest.raises(RuntimeError):
            with worker._verified_scope([dict(path='/not/read',sha256='a'*64)]):
                for module in modules:module.require_root_freeze()
                raise RuntimeError('worker failed')
        verifier.assert_called_once()
    for module,gate in zip(modules,original):
        assert module.require_root_freeze is gate
        with pytest.raises(PermissionError):module.require_root_freeze()


def test_other_threads_reject_before_verification_or_gate_changes():
    with patch.object(worker.threading,'active_count',return_value=2), patch.object(worker,'_verify') as verify:
        with pytest.raises(ValueError,match='single-threaded'):
            with worker._verified_scope([dict(path='/not/read',sha256='a'*64)]):
                pytest.fail('concurrent scope entered')
        verify.assert_not_called()
    for module in (physical,physical_inputs,physical_queue_adapter):
        with pytest.raises(PermissionError):module.require_root_freeze()
