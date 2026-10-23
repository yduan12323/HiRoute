"""Fail-closed adapter for one original-Shandong N8 REF attempt.

The existing M6 root gate is preserved and rechecked in the supervised worker.
No claim is made until strict accounting, source/config, and original-input
admission all pass. The permanent claim is bound to the fixed master root.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

SCHEMA = 'hiroute.m5e2e.original_bridge_admission.v1'
ACCOUNT_SCHEMA = 'hiroute.m5e2e.master_accounting.v1'
CPU_CAP, WALL_CAP = 8 * 3600, 12 * 3600
REF_SECONDS, FOLLOWUP_RESERVE_SECONDS = 120, 600
MAX_ACCOUNT_BYTES, MAX_EVIDENCE_BYTES = 4*1024**2, 16*1024**2
CLAIM_RELATIVE = Path('.m5e2e_bridge_claims/original-shandong-n8-ref.claim.json')


class AdmissionError(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionError('duplicate JSON key')
        result[key] = value
    return result


def _read_regular(path, limit):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise AdmissionError('binding must be an absolute non-symlink regular file')
    size = path.stat().st_size
    if not 0 < size <= limit:
        raise AdmissionError('binding size outside fixed limit')
    raw = path.read_bytes()
    if len(raw) != size or len(raw) > limit:
        raise AdmissionError('binding changed while reading')
    return raw


def _verify_evidence(row, field):
    evidence = row.get('evidence')
    if type(evidence) is not dict or set(evidence) != {'path', 'sha256'}:
        raise AdmissionError(field + ' requires exact evidence path and SHA256')
    if _hash(_read_regular(evidence['path'], MAX_EVIDENCE_BYTES)) != evidence['sha256']:
        raise AdmissionError(field + ' evidence SHA256 mismatch')


def _ledger_totals(raw):
    entries = []
    for line in raw.splitlines():
        if line:
            entries.append(json.loads(line, object_pairs_hook=_unique_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(AdmissionError('nonfinite ledger JSON'))))
    starts, ends = {}, {}
    for row in entries:
        if type(row) is not dict or row.get('kind') not in ('start', 'end'):
            raise AdmissionError('unknown budget ledger row')
        invocation = row.get('invocation_id')
        target = starts if row['kind'] == 'start' else ends
        if type(invocation) is not str or not invocation or invocation in target:
            raise AdmissionError('missing or duplicate invocation identity')
        target[invocation] = row
    if set(starts) != set(ends):
        raise AdmissionError('unsettled budget invocation')
    cpu = wall = 0.0
    for invocation, end in ends.items():
        if starts[invocation].get('phase') != end.get('phase'):
            raise AdmissionError('start/end phase mismatch')
        if end.get('cleanup_verified') is not True:
            raise AdmissionError('worker cleanup not verified')
        cpu += _number(end.get('cpu_seconds'), 'ledger cpu_seconds')
        wall += _number(end.get('wall_seconds'), 'ledger wall_seconds')
    return cpu, wall


def _number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise AdmissionError(field + ' must be finite and nonnegative')
    return float(value)


def validate_master_accounting(path, expected_sha256, expected_root):
    """Validate the complete external master account against hashed evidence."""
    path = Path(path).resolve()
    raw = _read_regular(path, MAX_ACCOUNT_BYTES)
    if _hash(raw) != expected_sha256:
        raise AdmissionError('master accounting SHA256 mismatch')
    account = json.loads(raw, object_pairs_hook=_unique_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(AdmissionError('nonfinite accounting JSON')))
    if raw != _canonical(account):
        raise AdmissionError('master accounting must be canonical JSON')
    fields = {'schema','master_root','budget_root','cpu_cap_seconds','wall_cap_seconds',
        'phase_ledger','external_charges','reservations','unknown_costs','unsettled_invocations',
        'charged_cpu_seconds','charged_wall_seconds','reserved_cpu_seconds','reserved_wall_seconds',
        'remaining_cpu_seconds','remaining_wall_seconds','accounting_complete'}
    if type(account) is not dict or set(account) != fields or account.get('schema') != ACCOUNT_SCHEMA:
        raise AdmissionError('master accounting schema/fields differ')
    root = Path(expected_root).resolve()
    if account['master_root'] != str(root) or account['budget_root'] != str(root):
        raise AdmissionError('master_root and budget_root must equal the fixed supplied root')
    if account['cpu_cap_seconds'] != CPU_CAP or account['wall_cap_seconds'] != WALL_CAP:
        raise AdmissionError('original 8 CPU-hour / 12 wall-hour caps required')
    if account['accounting_complete'] is not True or account['unknown_costs'] != [] or account['unsettled_invocations'] != []:
        raise AdmissionError('master accounting incomplete, unknown, or unsettled')
    ledger = account['phase_ledger']
    if type(ledger) is not dict or set(ledger) != {'path','sha256'}:
        raise AdmissionError('exact phase ledger binding required')
    ledger_path = Path(ledger['path'])
    if ledger_path.resolve() != root/'phase_ledger.jsonl' or ledger_path.is_symlink():
        raise AdmissionError('phase ledger must be the fixed ledger under master_root')
    ledger_raw = _read_regular(ledger_path, MAX_EVIDENCE_BYTES)
    if _hash(ledger_raw) != ledger['sha256']:
        raise AdmissionError('phase ledger SHA256 mismatch')
    ledger_cpu, ledger_wall = _ledger_totals(ledger_raw)
    if type(account['external_charges']) is not list or type(account['reservations']) is not list:
        raise AdmissionError('charge and reservation lists required')
    ids = set()
    charge_cpu = charge_wall = reserve_cpu = reserve_wall = 0.0
    for label, rows in (('charge', account['external_charges']), ('reservation', account['reservations'])):
        for row in rows:
            if type(row) is not dict or set(row) != {'id','cpu_seconds','wall_seconds','evidence'}:
                raise AdmissionError(label + ' schema differs')
            if type(row['id']) is not str or not row['id'] or row['id'] in ids:
                raise AdmissionError('charge/reservation IDs must be unique')
            ids.add(row['id']); _verify_evidence(row, label)
            c, w = _number(row['cpu_seconds'],label+' cpu_seconds'), _number(row['wall_seconds'],label+' wall_seconds')
            if label == 'charge':
                charge_cpu += c; charge_wall += w
            else:
                reserve_cpu += c; reserve_wall += w
    charged_cpu, charged_wall = ledger_cpu+charge_cpu, ledger_wall+charge_wall
    remaining_cpu, remaining_wall = CPU_CAP-charged_cpu-reserve_cpu, WALL_CAP-charged_wall-reserve_wall
    calculated = {'charged_cpu_seconds':charged_cpu,'charged_wall_seconds':charged_wall,
        'reserved_cpu_seconds':reserve_cpu,'reserved_wall_seconds':reserve_wall,
        'remaining_cpu_seconds':remaining_cpu,'remaining_wall_seconds':remaining_wall}
    for key, value in calculated.items():
        if not math.isclose(_number(account[key],key), value, rel_tol=0.0, abs_tol=1e-6):
            raise AdmissionError('master accounting arithmetic mismatch: '+key)
    if remaining_cpu < REF_SECONDS+FOLLOWUP_RESERVE_SECONDS or remaining_wall < REF_SECONDS+FOLLOWUP_RESERVE_SECONDS:
        raise AdmissionError('verified remaining budget cannot reserve REF and taskbook follow-up')
    return dict(account=account, account_sha256=_hash(raw), ledger_path=ledger_path,
        ledger_sha256=_hash(ledger_raw), ledger_cpu_seconds=ledger_cpu, ledger_wall_seconds=ledger_wall,
        charged_cpu_seconds=charged_cpu, charged_wall_seconds=charged_wall,
        reserved_cpu_seconds=reserve_cpu, reserved_wall_seconds=reserve_wall,
        remaining_cpu_seconds=remaining_cpu, remaining_wall_seconds=remaining_wall, master_root=root)


def _write_report(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as f:
            f.write(_canonical(value)+b'\n'); f.flush(); os.fsync(f.fileno())
    finally:
        os.close(fd)
    dfd = os.open(path.parent, os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try: os.fsync(dfd)
    finally: os.close(dfd)


def _claim_once(root, payload):
    claim = Path(root)/CLAIM_RELATIVE
    claim.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(claim, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0), 0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:
            f.write(_canonical(payload)+b'\n'); f.flush(); os.fsync(f.fileno())
    finally: os.close(fd)
    dfd = os.open(claim.parent, os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return claim


def _admit_inputs(configuration, manifest_binding, common_binding):
    from experiments.m6h_manifest_v1 import recovery_runtime
    freeze = recovery_runtime.activate(configuration)
    from experiments.m6h_manifest_v1 import physical, reference
    manifest = physical._manifest(manifest_binding['path'], manifest_binding['sha256'])
    raw = _read_regular(common_binding['path'], MAX_EVIDENCE_BYTES)
    if _hash(raw) != common_binding['sha256']:
        raise AdmissionError('original common seed SHA256 mismatch')
    common = json.loads(raw, object_pairs_hook=_unique_pairs)
    if raw != reference.canonical(common):
        raise AdmissionError('original common seed must use canonical bytes')
    physical.validate_common(common, 'N8', manifest)
    query = common['query']
    if Fraction(str(query['initial_energy_kwh']))/Fraction(str(query['capacity_kwh'])) != Fraction(3,10):
        raise AdmissionError('original N8 query is not SOC 0.30')
    if common['seed'].get('max_depth') != 10:
        raise AdmissionError('original seed-derived N8 depth is not the recorded depth 10')
    repo = Path(freeze['repo']).resolve()
    module_root = Path(__file__).resolve().parents[2]
    if repo != module_root:
        raise AdmissionError('trusted recovery source layout differs from active module root')
    if manifest.get('case_id') not in ('N8', None):
        raise AdmissionError('manifest identity differs from original N8')
    return freeze, manifest, common, module_root


def _admission(configuration, manifest_binding, common_binding, account_path, account_sha, master_root):
    if type(configuration) is not dict or set(configuration) != {'path','sha256'}:
        raise AdmissionError('exact trusted recovery configuration binding required')
    if type(manifest_binding) is not dict or set(manifest_binding) != {'path','sha256'}:
        raise AdmissionError('exact original manifest binding required')
    if type(common_binding) is not dict or set(common_binding) != {'path','sha256'}:
        raise AdmissionError('exact original common seed binding required')
    account = validate_master_accounting(account_path, account_sha, master_root)
    freeze, manifest, common, module_root = _admit_inputs(configuration, manifest_binding, common_binding)
    return account, freeze, manifest, common, module_root


def run_bridge(*, configuration, manifest_binding, common_binding, account_path, account_sha,
               master_root, report_path, run_root):
    report = dict(schema=SCHEMA,status='NOT_RUN_DEPENDENCY',reason='admission_not_completed',
        numerical_worker_started=False,claim_created=False,ref_status='NOT_RUN',
        legacy_root_gate='UNCHANGED_AND_RECHECKED_IN_WORKER',post_ref_methods_status='NOT_ADMITTED')
    try:
        account, freeze, manifest, common, module_root = _admission(configuration,manifest_binding,
            common_binding,account_path,account_sha,master_root)
    except Exception as exc:
        report['reason'] = type(exc).__name__+': '+str(exc)
        _write_report(report_path, report); return report
    root = account['master_root']; output = Path(run_root).resolve()
    if output.is_relative_to(root) or output.is_relative_to(module_root):
        report['reason']='run_root_must_be_outside_master_root_and_source_checkout'
        _write_report(report_path,report); return report
    claim = root/CLAIM_RELATIVE
    claim_payload = dict(schema='hiroute.m5e2e.original_bridge_claim.v1',case_id='N8',
        candidate_count=8,soc='3/10',seed_depth=10,master_root=str(root),
        master_accounting_sha256=account['account_sha256'],phase_ledger_sha256=account['ledger_sha256'],
        recovery_configuration_sha256=configuration['sha256'],manifest_sha256=manifest_binding['sha256'],
        common_sha256=common_binding['sha256'],created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    state={'claim':False,'started':False}
    def claim_under_budget_lock(*,ledger_path,entries,cpu,wall):
        latest=validate_master_accounting(account_path,account_sha,root)
        if latest['ledger_path']!=Path(ledger_path).resolve() or latest['ledger_sha256']!=account['ledger_sha256']:
            raise AdmissionError('master ledger changed after admission')
        if min(latest['remaining_cpu_seconds'],latest['remaining_wall_seconds']) < REF_SECONDS+FOLLOWUP_RESERVE_SECONDS:
            raise AdmissionError('global budget reserve changed before claim')
        _claim_once(root,claim_payload)
        state['claim']=True
    try:
        from experiments.m5e2e_v1.budget import execute
        output.mkdir(parents=True,exist_ok=False)
        command=[sys.executable,'-m','experiments.m5e2e_v1.original_bridge_worker',
            '--configuration',configuration['path'],'--configuration-sha256',configuration['sha256'],
            '--manifest',manifest_binding['path'],'--manifest-sha256',manifest_binding['sha256'],
            '--common',common_binding['path'],'--common-sha256',common_binding['sha256']]
        receipt=execute(command,budget_root=root,output_dir=output/'ref',phase='original-shandong-n8-ref',
            cpu_seconds=REF_SECONDS,wall_seconds=REF_SECONDS,memory_bytes=4*1024**3,
            preprocessing=False,before_start=claim_under_budget_lock)
        state['started']=state['claim']
        report.update(numerical_worker_started=state['started'],claim_created=state['claim'],
            claim_path=str(claim),supervisor_status=receipt.get('status'),
            cleanup_verified=receipt.get('cleanup_verified'),supervisor_receipt=str(output/'ref'/'receipt.json'))
        from experiments.m6h_manifest_v1 import reference
        result=reference.load_worker_result(output/'ref',receipt,'N8',common=common,manifest=manifest)
        report['ref_status']=result['status']
        if result['status']=='SUCCESS' and result.get('independent_exact') is True:
            report.update(status='REF_AUTHENTICATED_SUCCESS',
                post_ref_methods_status='ELIGIBLE_ONLY_AFTER_TASKBOOK_COMPATIBLE_METHOD_ADAPTER',
                post_ref_methods_admitted=True)
        else:
            report.update(status='REF_ATTEMPT_CONSUMED_INCOMPLETE',reason=result.get('reason','REF_NOT_EXACT'),
                post_ref_methods_status='NOT_ADMITTED',post_ref_methods_admitted=False)
    except Exception as exc:
        report.update(reason=type(exc).__name__+': '+str(exc),claim_created=state['claim'],
            claim_path=str(claim) if state['claim'] else None,
            numerical_worker_started=state['started'],
            status=('REF_ATTEMPT_CONSUMED_INCOMPLETE' if state['claim'] else 'NOT_RUN_DEPENDENCY'),
            post_ref_methods_status='NOT_ADMITTED',post_ref_methods_admitted=False)
    _write_report(report_path,report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',required=True,type=Path)
    p.add_argument('--run-root',type=Path); p.add_argument('--master-root',type=Path)
    p.add_argument('--master-accounting',type=Path); p.add_argument('--master-accounting-sha256')
    p.add_argument('--configuration'); p.add_argument('--configuration-sha256')
    p.add_argument('--manifest'); p.add_argument('--manifest-sha256')
    p.add_argument('--common'); p.add_argument('--common-sha256')
    a=p.parse_args(argv)
    supplied={'run_root':a.run_root,'master_root':a.master_root,'account_path':a.master_accounting,
        'account_sha':a.master_accounting_sha256,
        'configuration':({'path':a.configuration,'sha256':a.configuration_sha256}
            if a.configuration and a.configuration_sha256 else None),
        'manifest_binding':({'path':a.manifest,'sha256':a.manifest_sha256}
            if a.manifest and a.manifest_sha256 else None),
        'common_binding':({'path':a.common,'sha256':a.common_sha256}
            if a.common and a.common_sha256 else None)}
    missing=[key for key,value in supplied.items() if value is None]
    if missing:
        result=dict(schema=SCHEMA,status='NOT_RUN_DEPENDENCY',
            reason='missing_arguments:'+','.join(missing),numerical_worker_started=False,
            claim_created=False,ref_status='NOT_RUN',post_ref_methods_status='NOT_ADMITTED')
        _write_report(a.report,result); print(json.dumps(result,indent=2,sort_keys=True)); return 2
    result=run_bridge(report_path=a.report,**supplied)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result['status']=='REF_AUTHENTICATED_SUCCESS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
