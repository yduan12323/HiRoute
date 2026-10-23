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
REF_SECONDS, FOLLOWUP_RESERVE_SECONDS = 120, 840
MAX_ACCOUNT_BYTES, MAX_EVIDENCE_BYTES = 4*1024**2, 16*1024**2
CLAIM_RELATIVE = Path('.m5e2e_bridge_claims/original-shandong-n8-ref.claim.json')
ORIGINAL_LEDGER_SHA256 = 'ba453f3fcdc72ef5c5b8a0418164672dcaa0446210e74035d46d76140360645f'


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
    if type(evidence) is not dict or set(evidence) != {'path','sha256'}:
        raise AdmissionError(field+' requires exact evidence path and SHA256')
    raw=_read_regular(evidence['path'],MAX_EVIDENCE_BYTES)
    if _hash(raw)!=evidence['sha256']:
        raise AdmissionError(field+' evidence SHA256 mismatch')
    expected={'schema':'hiroute.m5e2e.accounting_evidence.v1','id':row['id'],'kind':field,
        'cpu_seconds':row['cpu_seconds'],'wall_seconds':row['wall_seconds']}
    value=json.loads(raw,object_pairs_hook=_unique_pairs)
    if raw!=_canonical(expected) or value!=expected:
        raise AdmissionError(field+' evidence content/ID/amount differs')


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
    return cpu, wall, starts, ends


def _json_binding(binding, *, limit, canonical=False):
    if type(binding) is not dict or set(binding) != {'path', 'sha256'}:
        raise AdmissionError('exact path/SHA256 evidence binding required')
    raw = _read_regular(binding['path'], limit)
    if _hash(raw) != binding['sha256']:
        raise AdmissionError('bound evidence SHA256 mismatch')
    value = json.loads(raw, object_pairs_hook=_unique_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(AdmissionError('nonfinite evidence JSON')))
    if canonical and raw != _canonical(value):
        raise AdmissionError('bound evidence is not canonical JSON')
    return value, raw


def _number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise AdmissionError(field + ' must be finite and nonnegative')
    return float(value)


def validate_master_accounting(path, expected_sha256, expected_root, expected_run_identity):
    """Require a closed, hash-checked inventory and append-only ledger lineage."""
    path=Path(path)
    if path.is_symlink():raise AdmissionError('master accounting symlink is forbidden')
    path=path.resolve(); raw=_read_regular(path,MAX_ACCOUNT_BYTES)
    if _hash(raw)!=expected_sha256:raise AdmissionError('master accounting SHA256 mismatch')
    account=json.loads(raw,object_pairs_hook=_unique_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(AdmissionError('nonfinite accounting JSON')))
    if raw!=_canonical(account):raise AdmissionError('master accounting must be canonical JSON')
    fields={'schema','run_identity','master_root','budget_root','cpu_cap_seconds','wall_cap_seconds',
        'phase_ledger','ledger_lineage','accounting_inventory','external_charges','reservations',
        'charged_cpu_seconds','charged_wall_seconds','reserved_cpu_seconds','reserved_wall_seconds',
        'remaining_cpu_seconds','remaining_wall_seconds'}
    if type(account) is not dict or set(account)!=fields or account.get('schema')!=ACCOUNT_SCHEMA:
        raise AdmissionError('master accounting schema/fields differ')
    root=Path(expected_root).resolve()
    if account['run_identity']!=expected_run_identity:
        raise AdmissionError('master accounting belongs to another original run identity')
    if account['master_root']!=str(root) or account['budget_root']!=str(root):
        raise AdmissionError('master_root and budget_root must equal the selected fixed root')
    if account['cpu_cap_seconds']!=CPU_CAP or account['wall_cap_seconds']!=WALL_CAP:
        raise AdmissionError('original 8 CPU-hour / 12 wall-hour caps required')
    ledger=account['phase_ledger']
    if type(ledger) is not dict or set(ledger)!={'path','sha256'}:
        raise AdmissionError('exact phase ledger binding required')
    ledger_path=Path(ledger['path'])
    if ledger_path.resolve()!=root/'phase_ledger.jsonl' or ledger_path.is_symlink():
        raise AdmissionError('phase ledger must be the fixed ledger under master_root')
    ledger_raw=_read_regular(ledger_path,MAX_EVIDENCE_BYTES)
    if _hash(ledger_raw)!=ledger['sha256']:raise AdmissionError('phase ledger SHA256 mismatch')
    ledger_cpu,ledger_wall,starts,ends=_ledger_totals(ledger_raw)
    lineage_binding=account['ledger_lineage']
    lineage,lineage_raw=_json_binding(lineage_binding,limit=MAX_ACCOUNT_BYTES,canonical=True)
    lf={'schema','run_identity','origin_ledger_sha256','snapshots'}
    if type(lineage) is not dict or set(lineage)!=lf or lineage.get('schema')!='hiroute.m5e2e.ledger_lineage.v1':
        raise AdmissionError('append-only ledger lineage schema differs')
    if lineage['run_identity']!=expected_run_identity or lineage['origin_ledger_sha256']!=ORIGINAL_LEDGER_SHA256:
        raise AdmissionError('ledger lineage is not rooted in the original master snapshot')
    snapshots=lineage['snapshots']
    if type(snapshots) is not list or not snapshots:
        raise AdmissionError('ledger lineage snapshots are required')
    raws=[]; prior=None
    for item in snapshots:
        if type(item) is not dict or set(item)!={'path','sha256'}:
            raise AdmissionError('ledger lineage snapshot binding differs')
        snap=Path(item['path'])
        data=_read_regular(snap,MAX_EVIDENCE_BYTES)
        if _hash(data)!=item['sha256']:raise AdmissionError('ledger lineage snapshot hash mismatch')
        if prior is not None and not data.startswith(prior):
            raise AdmissionError('ledger lineage is not append-only')
        raws.append(data); prior=data
    if _hash(raws[0])!=ORIGINAL_LEDGER_SHA256 or raws[-1]!=ledger_raw:
        raise AdmissionError('ledger lineage does not reach the pinned original/current ledger')
    inventory_binding=account['accounting_inventory']
    inventory,inventory_raw=_json_binding(inventory_binding,limit=MAX_ACCOUNT_BYTES,canonical=True)
    inf={'schema','run_identity','master_root','closed_world','source_ids','unresolved_sources','records'}
    if type(inventory) is not dict or set(inventory)!=inf or inventory.get('schema')!='hiroute.m5e2e.accounting_inventory.v1':
        raise AdmissionError('accounting source inventory schema differs')
    if inventory['run_identity']!=expected_run_identity or inventory['master_root']!=str(root):
        raise AdmissionError('accounting source inventory root identity differs')
    if inventory['closed_world'] is not True or inventory['unresolved_sources']!=[]:
        raise AdmissionError('accounting source inventory is open or has unresolved items')
    records=inventory['records']
    if type(records) is not list:raise AdmissionError('accounting source records must be a list')
    by_id={}
    for row in records:
        if type(row) is not dict or set(row)!={'id','kind','cpu_seconds','wall_seconds','evidence'}:
            raise AdmissionError('accounting source record schema differs')
        if type(row['id']) is not str or not row['id'] or row['id'] in by_id:
            raise AdmissionError('accounting source IDs must be unique')
        by_id[row['id']]=row
    ext=account['external_charges']; reserves=account['reservations']
    if type(ext) is not list or type(reserves) is not list:
        raise AdmissionError('external charges and reservations must be lists')
    extids=set(); reserveids=set(); charge_cpu=charge_wall=reserve_cpu=reserve_wall=0.0
    for label,rows in (('charge',ext),('reservation',reserves)):
        for row in rows:
            if type(row) is not dict or set(row)!={'id','cpu_seconds','wall_seconds','evidence'}:
                raise AdmissionError(label+' schema differs')
            if type(row['id']) is not str or not row['id']:
                raise AdmissionError(label+' ID missing')
            (_verify_evidence(row,label))
            target=extids if label=='charge' else reserveids
            if row['id'] in target:raise AdmissionError('duplicate '+label+' ID')
            target.add(row['id'])
            inv=by_id.get(row['id'])
            if inv is None or inv['kind']!=label or inv['cpu_seconds']!=row['cpu_seconds'] or inv['wall_seconds']!=row['wall_seconds'] or inv['evidence']!=row['evidence']:
                raise AdmissionError(label+' is missing/mismatched in the closed source inventory')
            c,w=_number(row['cpu_seconds'],label+' cpu_seconds'),_number(row['wall_seconds'],label+' wall_seconds')
            if label=='charge':charge_cpu+=c;charge_wall+=w
            else:reserve_cpu+=c;reserve_wall+=w
    for invocation,end in ends.items():
        inv=by_id.get(invocation)
        start=starts[invocation]
        if inv is None or inv['cpu_seconds']!=end['cpu_seconds'] or inv['wall_seconds']!=end['wall_seconds']:
            raise AdmissionError('worker/carry end is missing from source inventory')
        evidence=inv['evidence']
        raw=_read_regular(evidence['path'],MAX_EVIDENCE_BYTES)
        if _hash(raw)!=evidence['sha256']:raise AdmissionError('ledger source evidence SHA256 mismatch')
        value=json.loads(raw,object_pairs_hook=_unique_pairs)
        if inv['kind']=='worker':
            if end.get('record_type')=='accounting_transfer_not_worker':
                raise AdmissionError('carry row misclassified as worker')
            if end.get('receipt')!=evidence['path']:
                raise AdmissionError('ledger worker receipt path differs from source inventory')
            if end.get('receipt_sha256') != evidence['sha256']:
                raise AdmissionError('ledger receipt SHA256 differs from source inventory')
            if (value.get('cleanup_verified') is not True or
                not math.isclose(_number(value.get('accounted_owned_cpu_seconds'),'receipt cpu'),_number(end['cpu_seconds'],'ledger cpu'),rel_tol=0,abs_tol=1e-6) or
                not math.isclose(_number(value.get('wall_seconds'),'receipt wall'),_number(end['wall_seconds'],'ledger wall'),rel_tol=0,abs_tol=1e-6)):
                raise AdmissionError('supervisor receipt cleanup/cost differs from ledger')
        elif inv['kind']=='carry':
            if end.get('record_type')!='accounting_transfer_not_worker':
                raise AdmissionError('non-worker transfer misclassified')
            expected={'schema':'hiroute.m5e2e.accounting_transfer.v1','run_identity':expected_run_identity,
                'invocation_id':invocation,'previous_ledger_sha256':end.get('previous_ledger_sha256'),
                'cpu_seconds':end['cpu_seconds'],'wall_seconds':end['wall_seconds']}
            if (value!=expected or raw!=_canonical(expected) or
                expected['previous_ledger_sha256'] not in {item['sha256'] for item in snapshots}):
                raise AdmissionError('carry transfer evidence/lineage differs')
        else:
            raise AdmissionError('ledger invocation has unknown inventory kind')
    ledger_ids=set(ends)
    expected_ids=ledger_ids|extids|reserveids
    if set(by_id)!=expected_ids or sorted(inventory['source_ids'])!=sorted(expected_ids):
        raise AdmissionError('source inventory omits or adds an accounting record')
    if len(inventory['source_ids'])!=len(set(inventory['source_ids'])):
        raise AdmissionError('duplicate ID in source catalog')
    charged_cpu,charged_wall=ledger_cpu+charge_cpu,ledger_wall+charge_wall
    remaining_cpu,remaining_wall=CPU_CAP-charged_cpu-reserve_cpu,WALL_CAP-charged_wall-reserve_wall
    calculated={'charged_cpu_seconds':charged_cpu,'charged_wall_seconds':charged_wall,
        'reserved_cpu_seconds':reserve_cpu,'reserved_wall_seconds':reserve_wall,
        'remaining_cpu_seconds':remaining_cpu,'remaining_wall_seconds':remaining_wall}
    for key,value in calculated.items():
        if not math.isclose(_number(account[key],key),value,rel_tol=0,abs_tol=1e-6):
            raise AdmissionError('master accounting arithmetic mismatch: '+key)
    if min(remaining_cpu,remaining_wall)<REF_SECONDS+FOLLOWUP_RESERVE_SECONDS:
        raise AdmissionError('verified remaining budget cannot reserve REF and taskbook follow-up')
    return dict(account=account,account_sha256=_hash(raw if False else _canonical(account)),
        ledger_path=ledger_path,ledger_sha256=_hash(ledger_raw),ledger_cpu_seconds=ledger_cpu,
        ledger_wall_seconds=ledger_wall,charged_cpu_seconds=charged_cpu,charged_wall_seconds=charged_wall,
        reserved_cpu_seconds=reserve_cpu,reserved_wall_seconds=reserve_wall,remaining_cpu_seconds=remaining_cpu,
        remaining_wall_seconds=remaining_wall,master_root=root,run_identity=expected_run_identity)


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


def _verify_wrapper_identity(package_dir=None, prefix=None):
    package_dir = Path(package_dir or Path(__file__).resolve().parent).resolve()
    prefix = Path(prefix or sys.prefix).resolve()
    parent = package_dir / 'm5e2e_original_bridge.py'
    worker = package_dir / 'm5e2e_original_bridge_worker.py'
    manifest_path = package_dir / 'original_bridge_identity.json'
    if not package_dir.is_relative_to(prefix):
        raise AdmissionError('bridge wrapper is not loaded from the installed tools environment')
    raw = _read_regular(manifest_path, 64 * 1024)
    value = json.loads(raw, object_pairs_hook=_unique_pairs)
    expected = {'schema': 'hiroute.m5e2e.original_bridge_wrapper.v1', 'modules': {
        'm5e2e_original_bridge.py': _hash(_read_regular(parent, 2 * 1024**2)),
        'm5e2e_original_bridge_worker.py': _hash(_read_regular(worker, 2 * 1024**2)),
    }}
    if raw != _canonical(value) or value != expected:
        raise AdmissionError('installed bridge wrapper identity drift')
    return _hash(raw)


def _admit_inputs(configuration, manifest_binding, common_binding, source_root):
    wrapper_identity_sha256 = _verify_wrapper_identity()
    source_root=Path(source_root).resolve()
    adapter_root=Path(__file__).resolve().parents[1]
    if not source_root.is_dir() or source_root == adapter_root:
        raise AdmissionError('separate existing original source checkout required')
    for name,module in tuple(sys.modules.items()):
        if name == 'experiments' or name.startswith('experiments.'):
            location=getattr(module,'__file__',None)
            if location and not Path(location).resolve().is_relative_to(source_root):
                raise AdmissionError('an incompatible experiments module was imported before admission')
    if str(source_root) not in {str(Path(p or '.').resolve()) for p in sys.path}:
        raise AdmissionError('original source checkout must be naturally importable; path injection is forbidden')
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
    module_root = Path(recovery_runtime.__file__).resolve().parents[2]
    if repo != module_root or repo != source_root:
        raise AdmissionError('trusted recovery source layout differs from supplied original checkout')
    interpreter=Path(freeze['toolchain']['interpreter']['requested_executable']).resolve()
    if not interpreter.is_file() or interpreter != Path(sys.executable).resolve():
        raise AdmissionError('current Python executable differs from the trusted recovery toolchain')
    if manifest.get('case_id') not in ('N8', None):
        raise AdmissionError('manifest identity differs from original N8')
    return freeze, manifest, common, module_root, wrapper_identity_sha256


def _trusted_run_identity(freeze, configuration):
    admission_binding = freeze.get('continuation_admission')
    admission, _ = _json_binding(admission_binding, limit=128 * 1024, canonical=True)
    if (type(admission) is not dict
            or admission.get('schema') != 'hiroute.m6h.parent_receipt_continuation.v1'):
        raise AdmissionError('root-verified continuation admission schema differs')
    parent = admission.get('parent_waited_receipt')
    if type(parent) is not dict or set(parent) != {'path', 'sha256'}:
        raise AdmissionError('verified continuation lacks its parent waited receipt binding')
    identity = _hash(_canonical({
        'schema': 'hiroute.m5e2e.original_run_identity.v1',
        'configuration_sha256': configuration['sha256'],
        'continuation_admission_sha256': admission_binding['sha256'],
        'parent_waited_receipt': parent,
    }))
    return identity, Path(parent['path']).resolve().parent


def _require_authenticated_ref(result):
    if (type(result) is not dict or result.get('status') != 'SUCCESS'
            or result.get('independent_exact') is not True):
        raise AdmissionError('REF result lacks independent exact authentication')
    return result


def _admission(configuration, manifest_binding, common_binding, account_path, account_sha, master_root, source_root):
    if type(configuration) is not dict or set(configuration) != {'path','sha256'}:
        raise AdmissionError('exact trusted recovery configuration binding required')
    if type(manifest_binding) is not dict or set(manifest_binding) != {'path','sha256'}:
        raise AdmissionError('exact original manifest binding required')
    if type(common_binding) is not dict or set(common_binding) != {'path','sha256'}:
        raise AdmissionError('exact original common seed binding required')
    freeze, manifest, common, module_root, wrapper_identity_sha256 = _admit_inputs(configuration, manifest_binding, common_binding, source_root)
    run_identity, claim_root = _trusted_run_identity(freeze, configuration)
    account = validate_master_accounting(account_path, account_sha, master_root, run_identity)
    return account, freeze, manifest, common, module_root, run_identity, claim_root, wrapper_identity_sha256


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write_frozen_invocation(path, value):
    path = Path(path)
    raw = _canonical(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return _hash(raw)


def _append_jsonl(path, row):
    path = Path(path)
    with path.open('ab') as stream:
        stream.write(_canonical(row) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def _ref_worker_command(interpreter, configuration, manifest, common,
                        wrapper_identity_sha256, run_identity, freeze_path, freeze_sha256, attestation_path,
                        operation='ref', strategy=None, search_directory=None, search_receipt_sha256=None):
    command=[str(interpreter), '-I', '-m', 'ci.m5e2e_original_bridge_worker',
        '--operation', operation,
        '--configuration', configuration['path'], '--configuration-sha256', configuration['sha256'],
        '--manifest', manifest['path'], '--manifest-sha256', manifest['sha256'],
        '--common', common['path'], '--common-sha256', common['sha256'],
        '--wrapper-identity-sha256', wrapper_identity_sha256,
        '--run-identity', run_identity, '--invocation-freeze', str(freeze_path),
        '--freeze-sha256', freeze_sha256, '--attestation', str(attestation_path)]
    if strategy is not None:
        command.extend(['--strategy', strategy])
    if search_directory is not None:
        command.extend(['--search-directory', str(search_directory)])
    if search_receipt_sha256 is not None:
        command.extend(['--search-receipt-sha256', search_receipt_sha256])
    return command


def _method_phase_identity(physical, manifest, manifest_sha256, common_sha256, strategy, run_identity):
    if strategy not in ('flat', 'hier'):
        raise AdmissionError('only the original FLAT/HIER arms are admitted')
    identity = physical.phase_identity(manifest, manifest_sha256, strategy, common_sha256)
    identity['run_identity_sha256'] = run_identity
    identity['nonce'] = __import__('uuid').uuid4().hex
    return identity


def _classify_300_second_method_receipt(receipt, expected_identity):
    if type(receipt) is not dict or receipt.get('cleanup_verified') is not True:
        return 'INCOMPLETE'
    phase = receipt.get('phase_budget')
    if (type(phase) is not dict or phase.get('seconds') != 300
            or phase.get('identity') != expected_identity):
        return 'IDENTITY_MISMATCH'
    if receipt.get('status') == 'TIMEOUT':
        return 'EXTERNAL_LIMIT_UNVERIFIED'
    if receipt.get('status') != 'SUCCESS':
        return 'INCOMPLETE'
    return 'SUCCESS'


def _admit_method_300(physical, manifest, manifest_sha256, common, common_sha256,
                       strategy, search_output, search_receipt, verify_output, verify_receipt,
                       expected_phase_identity):
    """Authenticate early-success FLAT/HIER results without rewriting M6's 1200s gate."""
    from experiments.mechanism_recovery_v1 import run as base
    phase_status = _classify_300_second_method_receipt(search_receipt, expected_phase_identity)
    if phase_status != 'SUCCESS':
        raise AdmissionError('300-second outer method phase is not certifiable: ' + phase_status)
    if (verify_receipt.get('status') != 'SUCCESS'
            or verify_receipt.get('cleanup_verified') is not True):
        raise AdmissionError('fresh 120-second method replay did not complete cleanly')
    completed = base.load_worker_result(search_output, search_receipt, 'arm', 'N8', strategy)
    full = base.load_worker_result(verify_output, verify_receipt, 'verify', 'N8', strategy)
    if base.canonical(completed.get('seed_key')).decode() != common['seed']['key_bytes']:
        raise AdmissionError('method result did not retain the original common seed')
    terminal = physical.validate_terminal(completed, full, strategy, common['seed']['max_depth'])
    return dict(terminal=terminal, completed=completed, replay=full,
        search_receipt_sha256=_hash(_read_regular(Path(search_output)/'receipt.json', MAX_EVIDENCE_BYTES)),
        verify_receipt_sha256=_hash(_read_regular(Path(verify_output)/'receipt.json', MAX_EVIDENCE_BYTES)),
        outer_phase_seconds=300, fresh_verify_seconds=120,
        legacy_internal_phase_seconds=1200, legacy_phase_gate_changed=False)


def _run_method_search_300(command, *, output_dir, cwd, identity, cpu,
                           global_cpu_remaining, global_wall_remaining):
    from experiments.m6h_manifest_v1.supervisor import Limits, PhaseBudget, run
    return run(command, output_dir=output_dir, cwd=cwd,
        limits=Limits(wall_seconds=300, cpu_seconds=300, address_space_bytes=4*1024**3,
            cpu=cpu, file_output_bytes=2*1024**3, max_output_entries=10000, max_processes=16),
        phase_budget=PhaseBudget(seconds=300, identity=identity, marker_name='m5_method_entry.json'),
        tree_rss_stop_bytes=4*1024**3, available_stop_bytes=10*1024**3,
        prelaunch_available_bytes=14*1024**3, tree_cpu_seconds=300,
        global_cpu_remaining=global_cpu_remaining, global_wall_remaining=global_wall_remaining,
        owned_temp=True, extra_env={'PYTHONNOUSERSITE':'1'})


def _run_method_verify_120(command, *, output_dir, cwd, cpu,
                           global_cpu_remaining, global_wall_remaining):
    from experiments.m6h_manifest_v1.supervisor import Limits, run
    return run(command, output_dir=output_dir, cwd=cwd,
        limits=Limits(wall_seconds=120, cpu_seconds=120, address_space_bytes=4*1024**3,
            cpu=cpu, file_output_bytes=2*1024**3, max_output_entries=10000, max_processes=16),
        tree_rss_stop_bytes=4*1024**3, available_stop_bytes=10*1024**3,
        prelaunch_available_bytes=14*1024**3, tree_cpu_seconds=120,
        global_cpu_remaining=global_cpu_remaining, global_wall_remaining=global_wall_remaining,
        owned_temp=True, extra_env={'PYTHONNOUSERSITE':'1'})


def _execute_claimed(command, *, master_root, claim_root, run_identity, wrapper_identity_sha256, freeze_sha256, source_root, account_path, account_sha, run_output,
                     claim_payload, state):
    """Run the existing supervisor while holding the same global budget lock."""
    import fcntl
    from experiments.m6h_manifest_v1.supervisor import Limits, run
    root=Path(master_root); root.mkdir(parents=True,exist_ok=True)
    ledger=root/'phase_ledger.jsonl'
    with (root/'exclusive.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        entries=[json.loads(line) for line in ledger.read_text().splitlines()]
        cpu,wall,_,_=_ledger_totals(ledger.read_bytes())
        if cpu+REF_SECONDS>CPU_CAP or wall+REF_SECONDS>WALL_CAP:
            raise AdmissionError('shared phase ledger no longer has REF capacity')
        latest=validate_master_accounting(account_path,account_sha,root,run_identity)
        if latest['ledger_sha256']!=_hash(ledger.read_bytes()):
            raise AdmissionError('master ledger changed before locked claim')
        if min(latest['remaining_cpu_seconds'],latest['remaining_wall_seconds']) < REF_SECONDS+FOLLOWUP_RESERVE_SECONDS:
            raise AdmissionError('global budget reserve changed before claim')
        _claim_once(claim_root,claim_payload)
        state['claim']=True
        invocation=__import__('uuid').uuid4().hex
        def append(row):
            _append_jsonl(ledger, row)
        append(dict(kind='start',invocation_id=invocation,phase='original-shandong-n8-ref',
            argv=command,cpu_reserved=REF_SECONDS,wall_reserved=REF_SECONDS,timestamp=time.time()))
        started=time.monotonic()
        try:
            state['started']='UNKNOWN_AFTER_CLAIM'
            receipt=run(command,output_dir=run_output,cwd=source_root,
                limits=Limits(wall_seconds=REF_SECONDS,cpu_seconds=REF_SECONDS,
                    address_space_bytes=4*1024**3,cpu=min(os.sched_getaffinity(0)),
                    file_output_bytes=2*1024**3,max_output_entries=10000,max_processes=16),
                tree_rss_stop_bytes=4*1024**3,available_stop_bytes=10*1024**3,
                prelaunch_available_bytes=14*1024**3,tree_cpu_seconds=REF_SECONDS,
                global_cpu_remaining=latest['remaining_cpu_seconds'],global_wall_remaining=latest['remaining_wall_seconds'],
                owned_temp=True,extra_env={'PYTHONNOUSERSITE':'1'})
        except BaseException as exc:
            append(dict(kind='end',invocation_id=invocation,phase='original-shandong-n8-ref',
                cpu_seconds=REF_SECONDS,wall_seconds=max(REF_SECONDS,time.monotonic()-started),
                measured_cpu_seconds=None,charge_kind='conservative_reservation',
                cleanup_verified=False,error=type(exc).__name__+': '+str(exc)))
            raise
        state['started']=True
        if receipt.get('argv') != command:
            raise AdmissionError('supervisor receipt command differs from the frozen invocation')
        attestation_path=Path(run_output)/'worker-attestation.json'
        attestation_raw=_read_regular(attestation_path,64*1024)
        attestation=json.loads(attestation_raw,object_pairs_hook=_unique_pairs)
        expected_attestation={'schema':'hiroute.m5e2e.original_bridge_attestation.v1',
            'run_identity':run_identity,'wrapper_identity_sha256':wrapper_identity_sha256,
            'invocation_freeze_sha256':freeze_sha256,'operation':'ref','strategy':None,'worker_returned':True}
        if attestation_raw!=_canonical(expected_attestation) or attestation!=expected_attestation:
            raise AdmissionError('worker final attestation does not match frozen parent invocation')
        measured=receipt['accounted_owned_cpu_seconds']
        receipt_path=Path(run_output)/'receipt.json'
        receipt_sha256=_hash(_read_regular(receipt_path,MAX_EVIDENCE_BYTES))
        append(dict(kind='end',invocation_id=invocation,phase='original-shandong-n8-ref',
            cpu_seconds=measured,measured_cpu_seconds=measured,wall_seconds=receipt['wall_seconds'],
            charge_kind='outer_owned_tree',nested_inclusive_not_added=True,
            cleanup_verified=receipt['cleanup_verified'],receipt=str(receipt_path),receipt_sha256=receipt_sha256,
            worker_attestation=str(attestation_path),worker_attestation_sha256=_hash(attestation_raw),
            invocation_freeze_sha256=freeze_sha256,wrapper_identity_sha256=wrapper_identity_sha256,
            status=receipt['status']))
        if not receipt['cleanup_verified']:
            raise RuntimeError('Worker cleanup unverified; stop all work')
        return receipt


def _run_original_methods_after_ref(*, ref_result, physical, manifest, manifest_binding,
                                    common, common_binding, run_identity, wrapper_identity_sha256,
                                    freeze_path, freeze_sha256, run_root, master_root,
                                    expected_ledger_sha256, remaining_cpu, remaining_wall):
    """Run only the original N8 FLAT/HIER pair after authenticated REF success."""
    _require_authenticated_ref(ref_result)
    if ref_result['status'] != 'SUCCESS':
        return {'status': 'NOT_ADMITTED_REF_INCOMPLETE', 'methods': []}
    import fcntl
    root = Path(master_root)
    ledger = root/'phase_ledger.jsonl'
    results = []
    with (root/'exclusive.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        current = _read_regular(ledger, MAX_EVIDENCE_BYTES)
        if _hash(current) != expected_ledger_sha256:
            raise AdmissionError('master ledger changed after REF; method continuation is blocked')
        _ledger_totals(current)
        for strategy in ('flat', 'hier'):
            identity = _method_phase_identity(physical, manifest, manifest_binding['sha256'],
                common_binding['sha256'], strategy, run_identity)
            search_dir = Path(run_root)/strategy/'search'
            verify_dir = Path(run_root)/strategy/'verify'
            if min(remaining_cpu, remaining_wall) < 420:
                results.append({'strategy':strategy,'status':'NOT_RUN_BUDGET'})
                continue
            search_attestation = search_dir/'worker-attestation.json'
            freeze_value, _ = _json_binding({'path':str(freeze_path),'sha256':freeze_sha256},
                limit=128*1024, canonical=True)
            search_command = _ref_worker_command(Path(sys.executable).resolve(),
                freeze_value['configuration'], manifest_binding, common_binding,
                wrapper_identity_sha256, run_identity, freeze_path, freeze_sha256,
                search_attestation, operation='arm', strategy=strategy)
            search_invocation = __import__('uuid').uuid4().hex
            _append_jsonl(ledger, {'kind':'start','invocation_id':search_invocation,
                'phase':'original-shandong-n8-'+strategy+'-outer-300','argv':search_command,
                'cpu_reserved':300,'wall_reserved':300,'timestamp':time.time()})
            try:
                search_receipt = _run_method_search_300(search_command, output_dir=search_dir,
                    cwd=manifest['repo'], identity=identity, cpu=min(os.sched_getaffinity(0)),
                    global_cpu_remaining=remaining_cpu, global_wall_remaining=remaining_wall)
            except BaseException as exc:
                _append_jsonl(ledger, {'kind':'end','invocation_id':search_invocation,
                    'phase':'original-shandong-n8-'+strategy+'-outer-300','cpu_seconds':300,
                    'measured_cpu_seconds':None,'wall_seconds':300,'cleanup_verified':False,
                    'charge_kind':'conservative_reservation','error':type(exc).__name__})
                raise
            search_path = search_dir/'receipt.json'
            search_raw = _read_regular(search_path, MAX_EVIDENCE_BYTES)
            _append_jsonl(ledger, {'kind':'end','invocation_id':search_invocation,
                'phase':'original-shandong-n8-'+strategy+'-outer-300',
                'cpu_seconds':search_receipt['accounted_owned_cpu_seconds'],
                'measured_cpu_seconds':search_receipt['accounted_owned_cpu_seconds'],
                'wall_seconds':search_receipt['wall_seconds'],
                'cleanup_verified':search_receipt['cleanup_verified'],
                'receipt':str(search_path),'receipt_sha256':_hash(search_raw),
                'wrapper_identity_sha256':wrapper_identity_sha256,
                'invocation_freeze_sha256':freeze_sha256,'status':search_receipt['status']})
            remaining_cpu -= search_receipt['accounted_owned_cpu_seconds']
            remaining_wall -= search_receipt['wall_seconds']
            phase_status = _classify_300_second_method_receipt(search_receipt, identity)
            row={'strategy':strategy,'outer_status':phase_status,
                'search_receipt_sha256':_hash(search_raw),'external_seconds':300,
                'legacy_internal_seconds':1200,'fresh_verify_seconds':120}
            if not search_receipt.get('cleanup_verified'):
                raise AdmissionError('method worker cleanup unverified; stop all further work')
            if phase_status != 'SUCCESS':
                row['status']=phase_status
                results.append(row)
                continue
            if search_receipt.get('argv') != search_command:
                raise AdmissionError('method search supervisor argv differs from freeze')
            attestation_raw=_read_regular(search_attestation,64*1024)
            expected_att={'schema':'hiroute.m5e2e.original_bridge_attestation.v1',
                'run_identity':run_identity,'wrapper_identity_sha256':wrapper_identity_sha256,
                'invocation_freeze_sha256':freeze_sha256,'operation':'arm','strategy':strategy,
                'worker_returned':True}
            if attestation_raw != _canonical(expected_att):
                raise AdmissionError('method worker attestation differs from frozen search')
            if min(remaining_cpu,remaining_wall) < 120:
                row['status']='NOT_RUN_VERIFY_BUDGET'
                results.append(row)
                continue
            verify_attestation=verify_dir/'worker-attestation.json'
            search_sha=_hash(search_raw)
            verify_command=_ref_worker_command(Path(sys.executable).resolve(),
                freeze_value['configuration'],manifest_binding,common_binding,
                wrapper_identity_sha256,run_identity,freeze_path,freeze_sha256,
                verify_attestation,operation='verify',strategy=strategy,
                search_directory=search_dir,search_receipt_sha256=search_sha)
            verify_invocation=__import__('uuid').uuid4().hex
            _append_jsonl(ledger, {'kind':'start','invocation_id':verify_invocation,
                'phase':'original-shandong-n8-'+strategy+'-fresh-verify-120','argv':verify_command,
                'cpu_reserved':120,'wall_reserved':120,'timestamp':time.time()})
            try:
                verify_receipt=_run_method_verify_120(verify_command,output_dir=verify_dir,
                    cwd=manifest['repo'],cpu=min(os.sched_getaffinity(0)),
                    global_cpu_remaining=remaining_cpu,global_wall_remaining=remaining_wall)
            except BaseException as exc:
                _append_jsonl(ledger, {'kind':'end','invocation_id':verify_invocation,
                    'phase':'original-shandong-n8-'+strategy+'-fresh-verify-120',
                    'cpu_seconds':120,'measured_cpu_seconds':None,'wall_seconds':120,
                    'cleanup_verified':False,'charge_kind':'conservative_reservation',
                    'error':type(exc).__name__})
                raise
            verify_path=verify_dir/'receipt.json'
            verify_raw=_read_regular(verify_path,MAX_EVIDENCE_BYTES)
            _append_jsonl(ledger, {'kind':'end','invocation_id':verify_invocation,
                'phase':'original-shandong-n8-'+strategy+'-fresh-verify-120',
                'cpu_seconds':verify_receipt['accounted_owned_cpu_seconds'],
                'measured_cpu_seconds':verify_receipt['accounted_owned_cpu_seconds'],
                'wall_seconds':verify_receipt['wall_seconds'],
                'cleanup_verified':verify_receipt['cleanup_verified'],
                'receipt':str(verify_path),'receipt_sha256':_hash(verify_raw),
                'wrapper_identity_sha256':wrapper_identity_sha256,
                'invocation_freeze_sha256':freeze_sha256,'status':verify_receipt['status']})
            remaining_cpu -= verify_receipt['accounted_owned_cpu_seconds']
            remaining_wall -= verify_receipt['wall_seconds']
            if verify_receipt.get('status') != 'SUCCESS' or not verify_receipt.get('cleanup_verified'):
                row['status']='FRESH_VERIFY_INCOMPLETE'
                results.append(row)
                if not verify_receipt.get('cleanup_verified'):
                    raise AdmissionError('fresh verification cleanup unverified; stop')
                continue
            if verify_receipt.get('argv') != verify_command:
                raise AdmissionError('fresh verify supervisor argv differs from freeze')
            verify_att_raw=_read_regular(verify_attestation,64*1024)
            expected_verify={'schema':'hiroute.m5e2e.original_bridge_attestation.v1',
                'run_identity':run_identity,'wrapper_identity_sha256':wrapper_identity_sha256,
                'invocation_freeze_sha256':freeze_sha256,'operation':'verify','strategy':strategy,
                'worker_returned':True}
            if verify_att_raw != _canonical(expected_verify):
                raise AdmissionError('fresh verifier attestation differs from frozen plan')
            admitted=_admit_method_300(physical,manifest,manifest_binding['sha256'],
                common,common_binding['sha256'],strategy,search_dir,search_receipt,
                verify_dir,verify_receipt,identity)
            match = physical.base.canonical(admitted['terminal']) == physical.base.canonical(ref_result['canonical_outcome'])
            row.update(status='MATCH' if match else 'REPRODUCTION_MISMATCH',
                accepted_key=admitted['terminal'],comparison_complete=True,
                fresh_verify_receipt_sha256=_hash(verify_raw))
            results.append(row)
    final_status='MATCH' if len(results)==2 and all(r.get('status')=='MATCH' for r in results) else 'PARTIAL'
    return {'status':final_status,'methods':results,
        'remaining_cpu_seconds':remaining_cpu,'remaining_wall_seconds':remaining_wall,
        'budget_account_snapshot':'requires_reconciliation_before_any_further_admission'}


def run_bridge(*, configuration, manifest_binding, common_binding, account_path, account_sha,
               master_root, source_root, report_path, run_root):
    report=dict(schema=SCHEMA,status='NOT_RUN_DEPENDENCY',reason='admission_not_completed',
        numerical_worker_started=False,claim_created=False,ref_status='NOT_RUN',
        legacy_root_gate='UNCHANGED_AND_RECHECKED_IN_WORKER',post_ref_methods_status='NOT_ADMITTED')
    try:
        account,freeze,manifest,common,module_root,run_identity,claim_root,wrapper_identity_sha256=_admission(configuration,manifest_binding,
            common_binding,account_path,account_sha,master_root,source_root)
    except Exception as exc:
        report['reason']=type(exc).__name__+': '+str(exc)
        _write_report(report_path,report); return report
    root=account['master_root']; output=Path(run_root).resolve(); report_file=Path(report_path).resolve()
    adapter_root=Path(__file__).resolve().parents[1]
    if report_file.is_relative_to(root) or report_file.is_relative_to(module_root) or report_file.is_relative_to(adapter_root):
        report['reason']='report_must_be_outside_master_root_and_source_checkout'
        _write_report(report_path,report); return report
    if output.is_relative_to(root) or output.is_relative_to(module_root) or output.is_relative_to(adapter_root):
        report['reason']='run_root_must_be_outside_master_root_and_source_checkout'
        _write_report(report_path,report); return report
    claim=claim_root/CLAIM_RELATIVE
    state={'claim':False,'started':False}
    try:
        output.mkdir(parents=True,exist_ok=False)
        interpreter=Path(freeze['toolchain']['interpreter']['requested_executable']).resolve()
        invocation_freeze={'schema':'hiroute.m5e2e.original_bridge_invocation.v1',
            'run_identity':run_identity,'wrapper_identity_sha256':wrapper_identity_sha256,
            'interpreter_path':str(interpreter),'interpreter_sha256':_sha256_file(interpreter),
            'source_identity_sha256':_hash(_canonical(freeze['source'])),
            'configuration':configuration,'manifest':manifest_binding,'common':common_binding,
            'run_root':str(output),'planned_method_order':['flat','hier'],
            'master_accounting_sha256':account['account_sha256'],'phase_ledger_sha256':account['ledger_sha256']}
        freeze_path=output/'invocation-freeze.json'
        freeze_sha256=_write_frozen_invocation(freeze_path,invocation_freeze)
        attestation_path=output/'ref'/'worker-attestation.json'
        payload=dict(schema='hiroute.m5e2e.original_bridge_claim.v1',run_identity=run_identity,
            wrapper_identity_sha256=wrapper_identity_sha256,invocation_freeze_sha256=freeze_sha256,
            case_id='N8',candidate_count=8,soc='3/10',seed_depth=10,master_root=str(root),
            master_accounting_sha256=account['account_sha256'],phase_ledger_sha256=account['ledger_sha256'],
            recovery_configuration_sha256=configuration['sha256'],manifest_sha256=manifest_binding['sha256'],
            common_sha256=common_binding['sha256'],created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        command=_ref_worker_command(interpreter,configuration,manifest_binding,common_binding,
            wrapper_identity_sha256,run_identity,freeze_path,freeze_sha256,attestation_path)
        receipt=_execute_claimed(command,master_root=root,claim_root=claim_root,run_identity=run_identity,
            wrapper_identity_sha256=wrapper_identity_sha256,freeze_sha256=freeze_sha256,
            source_root=module_root,account_path=account_path,account_sha=account_sha,run_output=output/'ref',
            claim_payload=payload,state=state)
        report.update(numerical_worker_started=state['started'],claim_created=True,claim_path=str(claim),
            invocation_freeze=str(freeze_path),invocation_freeze_sha256=freeze_sha256,
            supervisor_status=receipt.get('status'),cleanup_verified=receipt.get('cleanup_verified'),
            supervisor_receipt=str(output/'ref'/'receipt.json'),
            worker_attestation_sha256=_hash(_read_regular(attestation_path,64*1024)))
        from experiments.m6h_manifest_v1 import reference
        result=reference.load_worker_result(output/'ref',receipt,'N8',common=common,manifest=manifest)
        report['ref_status']=result.get('status','UNKNOWN')
        report['ref_reason']=result.get('reason')
        _require_authenticated_ref(result)
        if result['status']=='SUCCESS' and result.get('independent_exact') is True:
            report.update(status='REF_AUTHENTICATED_SUCCESS',
                post_ref_methods_status='METHODS_PENDING')
            try:
                current_ledger=_read_regular(account['ledger_path'],MAX_EVIDENCE_BYTES)
                method_report=_run_original_methods_after_ref(
                    ref_result=result,physical=__import__('experiments.m6h_manifest_v1.physical',fromlist=['physical']),
                    manifest=manifest,manifest_binding=manifest_binding,common=common,
                    common_binding=common_binding,run_identity=run_identity,
                    wrapper_identity_sha256=wrapper_identity_sha256,freeze_path=freeze_path,
                    freeze_sha256=freeze_sha256,run_root=output,master_root=root,
                    expected_ledger_sha256=_hash(current_ledger),
                    remaining_cpu=account['remaining_cpu_seconds']-receipt['accounted_owned_cpu_seconds'],
                    remaining_wall=account['remaining_wall_seconds']-receipt['wall_seconds'])
                report['method_report']=method_report
                report['post_ref_methods_status']=method_report['status']
                report['status']='BRIDGE_COMPLETE' if method_report['status']=='MATCH' else 'PARTIAL'
            except Exception as method_exc:
                report.update(status='REF_AUTHENTICATED_METHODS_BLOCKED',
                    post_ref_methods_status='NOT_RUN_DEPENDENCY',
                    method_failure=type(method_exc).__name__+': '+str(method_exc))
        else:
            report.update(status='REF_ATTEMPT_CONSUMED_INCOMPLETE',
                reason=result.get('reason','REF_NOT_EXACT'),post_ref_methods_status='NOT_ADMITTED')
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
    p.add_argument('--run-root',type=Path); p.add_argument('--master-root',type=Path); p.add_argument('--source-root',type=Path)
    p.add_argument('--master-accounting',type=Path); p.add_argument('--master-accounting-sha256')
    p.add_argument('--configuration'); p.add_argument('--configuration-sha256')
    p.add_argument('--manifest'); p.add_argument('--manifest-sha256')
    p.add_argument('--common'); p.add_argument('--common-sha256')
    a=p.parse_args(argv)
    supplied={'run_root':a.run_root,'master_root':a.master_root,'source_root':a.source_root,'account_path':a.master_accounting,
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
