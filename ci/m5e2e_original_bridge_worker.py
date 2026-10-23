"""Installed supervised worker for the pinned original M6 inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from ci.m5e2e_original_bridge import (
    AdmissionError, _canonical, _hash, _read_regular, _sha256_file,
    _trusted_run_identity, _verify_wrapper_identity,
)


def _load_invocation(args):
    raw = _read_regular(args.invocation_freeze, 128 * 1024)
    if _hash(raw) != args.freeze_sha256:
        raise AdmissionError('invocation freeze digest changed')
    frozen = json.loads(raw)
    if raw != _canonical(frozen):
        raise AdmissionError('invocation freeze must be canonical')
    expected_keys = {'schema', 'run_identity', 'wrapper_identity_sha256',
        'interpreter_path', 'interpreter_sha256', 'source_identity_sha256',
        'configuration', 'manifest', 'common', 'master_accounting_sha256',
        'phase_ledger_sha256', 'run_root', 'source_root', 'planned_method_order'}
    if type(frozen) is not dict or set(frozen) != expected_keys:
        raise AdmissionError('invocation freeze fields differ')
    if frozen['schema'] != 'hiroute.m5e2e.original_bridge_invocation.v1':
        raise AdmissionError('invocation freeze schema differs')
    run_root = Path(frozen['run_root']).resolve()
    if (not run_root.is_absolute() or frozen['planned_method_order'] != ['flat', 'hier']):
        raise AdmissionError('invocation freeze method plan differs')
    if args.operation == 'ref':
        if args.strategy is not None or Path(args.attestation).resolve() != run_root/'ref'/'worker-attestation.json':
            raise AdmissionError('REF worker paths differ from invocation freeze')
    else:
        if args.strategy not in frozen['planned_method_order']:
            raise AdmissionError('method is not in the frozen original N8 plan')
        expected_stage = run_root/args.strategy/('search' if args.operation == 'arm' else 'verify')
        if Path(args.attestation).resolve() != expected_stage/'worker-attestation.json':
            raise AdmissionError('method worker path differs from invocation freeze')
        if args.operation == 'verify' and Path(args.search_directory).resolve() != run_root/args.strategy/'search':
            raise AdmissionError('fresh verifier search binding differs from invocation freeze')
    if _verify_wrapper_identity() != args.wrapper_identity_sha256:
        raise AdmissionError('installed bridge wrapper identity changed')
    interpreter = Path(sys.executable).resolve()
    if (frozen['interpreter_path'] != str(interpreter)
            or frozen['interpreter_sha256'] != _sha256_file(interpreter)):
        raise AdmissionError('worker interpreter differs from frozen invocation')
    if frozen['run_identity'] != args.run_identity:
        raise AdmissionError('worker run identity differs from parent freeze')
    if frozen['wrapper_identity_sha256'] != args.wrapper_identity_sha256:
        raise AdmissionError('worker wrapper identity differs from parent freeze')
    for name in ('configuration', 'manifest', 'common'):
        supplied = getattr(args, name)
        digest = getattr(args, name + '_sha256')
        if frozen[name] != {'path': supplied, 'sha256': digest}:
            raise AdmissionError('worker ' + name + ' binding differs from parent freeze')
    return frozen


def _write_worker_attestation(path, frozen, freeze_sha256, operation, strategy):
    value = {'schema': 'hiroute.m5e2e.original_bridge_attestation.v1',
        'run_identity': frozen['run_identity'],
        'wrapper_identity_sha256': frozen['wrapper_identity_sha256'],
        'invocation_freeze_sha256': freeze_sha256, 'operation': operation,
        'strategy': strategy, 'worker_returned': True}
    raw = _canonical(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--operation', choices=('ref', 'arm', 'verify'), default='ref')
    p.add_argument('--configuration', required=True)
    p.add_argument('--configuration-sha256', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--common', required=True)
    p.add_argument('--common-sha256', required=True)
    p.add_argument('--wrapper-identity-sha256', required=True)
    p.add_argument('--run-identity', required=True)
    p.add_argument('--invocation-freeze', required=True)
    p.add_argument('--freeze-sha256', required=True)
    p.add_argument('--attestation', required=True)
    p.add_argument('--strategy')
    p.add_argument('--search-directory')
    p.add_argument('--search-receipt-sha256')
    a = p.parse_args(argv)
    frozen = _load_invocation(a)
    from experiments.m6h_manifest_v1 import recovery_runtime, physical
    config = {'path': a.configuration, 'sha256': a.configuration_sha256}
    trusted = recovery_runtime.activate(config)
    run_identity, _ = _trusted_run_identity(trusted, config)
    module_root = Path(recovery_runtime.__file__).resolve().parents[2]
    if (module_root != Path(frozen['source_root']).resolve()
            or Path(trusted['repo']).resolve() != module_root):
        raise AdmissionError('isolated worker source overlay differs from invocation freeze')
    if run_identity != a.run_identity or _hash(_canonical(trusted['source'])) != frozen['source_identity_sha256']:
        raise AdmissionError('old source closure or run identity differs from invocation freeze')
    manifest = physical._manifest(a.manifest, a.manifest_sha256)
    if a.operation == 'ref':
        from experiments.m6h_manifest_v1 import reference
        reference.worker(a.manifest, a.manifest_sha256, 'N8', a.common, a.common_sha256)
    else:
        if (a.strategy not in physical.ARMS or a.strategy not in frozen['planned_method_order']):
            raise AdmissionError('bridge method must be a pinned FLAT/HIER arm')
        from experiments.mechanism_recovery_v1 import run as base
        raw = _read_regular(a.common, 16 * 1024**2)
        if _hash(raw) != a.common_sha256:
            raise AdmissionError('original common seed digest differs')
        common = json.loads(raw)
        if raw != base.canonical(common):
            raise AdmissionError('original common seed must be canonical')
        physical.validate_common(common, 'N8', manifest)
        factory = lambda m, q, sites, cache: physical.domain_factory(
            m, q, sites, cache, arm=a.strategy, case_id='N8',
            admitted_hmax=common['seed']['max_depth'])
        with physical.historical_operators():
            base.worker(manifest, a.operation, 'N8', a.common, a.common_sha256,
                a.strategy, a.search_directory, a.search_receipt_sha256,
                domain_factory=factory)
        physical._manifest(a.manifest, a.manifest_sha256)
        result_path = Path(os.environ['HIROUTE_WORKER_RECEIPT'])
        result = physical.result_envelope(os.environ['HIROUTE_OUTPUT_DIR'],
            a.operation, 'N8', a.strategy)
        result_path.write_bytes(base.canonical(dict(status='COMPLETED', result=result)))
    physical._manifest(a.manifest, a.manifest_sha256)
    _write_worker_attestation(a.attestation, frozen, a.freeze_sha256, a.operation, a.strategy)


if __name__ == '__main__':
    raise SystemExit(main())
