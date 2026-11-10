"""Fresh, bounded N64 runs. Historical accounting is never resumed here."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

from ..data.artifacts import digest, read_json, verify_manifest
from ..data.identity import domain_digest
from ..data.queries import select_domains
from .config import METHODS, load_config, n64_cells
from .provenance import identity as source_identity


def write_new(path, value):
    from ..cli import _atomic_new_file
    _atomic_new_file(Path(path), (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode())


def prepare(config_path, artifact_root, manifest_path, output, *, check_only=False):
    loaded = load_config(config_path)
    source = source_identity()
    manifest = read_json(manifest_path)
    report = verify_manifest(artifact_root, manifest)
    frozen = dict(graph=loaded['config']['graph_sha256'], catalog=loaded['matrix']['catalog_sha256'],
                  bindings=loaded['matrix']['bindings_sha256'])
    for row in report['files']:
        if row['status'] == 'verified' and row['role'] in frozen and row['sha256'] != frozen[row['role']]:
            report['errors'].append(dict(role=row['role'], path=row['path'], status='frozen_input_mismatch'))
    report['verified'] = not report['errors']
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / 'input-verification.json', report)
    if not report['verified']:
        raise ValueError('input closure incomplete: ' + json.dumps(report['errors'], ensure_ascii=False))
    if check_only:
        return report
    started = time.process_time()
    inputs = {row['role']: row['resolved_path'] for row in report['files']}
    matrix = loaded['matrix']
    if digest(inputs['graph']) != loaded['config']['graph_sha256']:
        raise ValueError('historical graph identity changed; do not substitute a newer map')
    for role, field in (('catalog', 'catalog_sha256'), ('bindings', 'bindings_sha256')):
        if digest(inputs[role]) != matrix[field]:
            raise ValueError(f'frozen {role} changed')
    # A graph is accepted only with its independently supplied manifest digest.
    sites, bindings = read_json(inputs['catalog']), read_json(inputs['bindings'])
    configs = {}
    from .pilot import preflight
    for energy, config in loaded['configs'].items():
        candidates = select_domains(config, sites, bindings)
        if {q['query_id']: q['endpoints'] for q in candidates['queries']} != matrix['endpoints']:
            raise ValueError('frozen endpoints changed')
        for cell in n64_cells(matrix):
            if cell['initial_energy_kwh'] != energy:
                continue
            q = next(q for q in candidates['queries'] if q['query_id'] == cell['query_id'])
            available = q['scenario_domain_status'][cell['scenario']]['64'] == 'available'
            if (available != (cell['input_status'] == 'available') or
                    q['scenario_eligible_counts'][cell['scenario']] != cell['qualified_count']):
                raise ValueError('frozen candidate availability changed')
            if available and domain_digest(q, 64, cell['scenario']) != cell['candidate_domain_sha256']:
                raise ValueError('frozen candidate identity/order changed')
        cp, pp = out / f'E{energy}.config.json', out / f'E{energy}.preflight.json'
        write_new(cp, config); write_new(pp, candidates)
        preflight(SimpleNamespace(config=cp, preflight=pp, graph_tsv=inputs['graph']))
        configs[energy] = dict(config=cp.name, preflight=pp.name,
                               config_sha256=digest(cp), preflight_sha256=digest(pp))
    effective = dict(schema='hiroute.prepared_research.v1', run_id=str(uuid.uuid4()),
                     source=source, inputs=inputs, artifact_root=str(Path(artifact_root).resolve()),
                     artifact_manifest=manifest, config=loaded['config'], matrix=matrix, configs=configs,
                     input_config_sha256=loaded['input_config_sha256'], base_config_sha256=loaded['base_config_sha256'],
                     preparation_cpu_s=time.process_time() - started, solver_called=False)
    validate_prepared(out, effective)
    write_new(out / 'prepared.json', effective)
    write_new(out / 'preparation.receipt.json', dict(prepared_sha256=digest(out / 'prepared.json')))
    return effective


def validate_prepared(directory, prepared):
    if prepared['schema'] != 'hiroute.prepared_research.v1':
        raise ValueError('unsupported prepared research schema')
    if prepared['source'] != source_identity():
        raise ValueError('code/environment changed within this run; prepare a new directory')
    n64_cells(prepared['matrix'])
    report = verify_manifest(prepared['artifact_root'], prepared['artifact_manifest'])
    if not report['verified']:
        raise ValueError('prepared inputs no longer verify: ' + json.dumps(report['errors']))
    if {r['role']: r['resolved_path'] for r in report['files']} != prepared['inputs']:
        raise ValueError('prepared input path binding changed')
    for cfg in prepared['configs'].values():
        for key in ('config', 'preflight'):
            path = (directory / cfg[key]).resolve()
            if not path.is_relative_to(directory) or digest(path) != cfg[key + '_sha256']:
                raise ValueError('prepared configuration/candidate identity changed')


def cell_id(cell):
    return f"{cell['query_id']}-E{cell['initial_energy_kwh']}-{cell['scenario']}-N{cell['N']}"


def validate_result(row):
    from ..evaluation.cohort import COMPLETE
    if row['status'] not in COMPLETE and row.get('mathematical_status', 'unknown') != 'unknown':
        raise ValueError('non-completion cannot certify a mathematical result')
    if row.get('key') is not None or row.get('feasible_key') is not None:
        witness = row.get('witness')
        if not isinstance(witness, dict) or witness.get('physical_verified') is not True:
            raise ValueError('feasible result requires independent physical replay')
        if witness['independent_key'] != row.get('feasible_key'):
            raise ValueError('full replay key mismatch')
    if row['status'] == 'attained_optimum' and (row.get('key') is None or row['key'] != row.get('feasible_key')):
        raise ValueError('attained optimum missing complete key')
    if row['status'] in COMPLETE and (row.get('depth_contract') or {}).get('mode') != 'unrestricted':
        raise ValueError('completion requires unrestricted depth certificate')
    for key in ('worker_cpu_s', 'supervisor_cpu_s'):
        if not math.isfinite(row.get(key, 0)) or row.get(key, 0) < 0:
            raise ValueError('invalid CPU receipt')


def compare_pair(rows):
    from ..evaluation.cohort import COMPLETE
    if [r['method'] for r in rows] != list(METHODS):
        raise ValueError('incomplete method pair')
    if all(r['status'] in COMPLETE for r in rows):
        fields = ('status', 'key', 'primary_value', 'primary_infimum', 'secondary_infimum')
        if tuple(rows[0].get(k) for k in fields) != tuple(rows[1].get(k) for k in fields):
            raise ValueError('completed pair full-key/attainment mismatch')
    if all(r.get('seed_key') is not None for r in rows) and rows[0]['seed_key'] != rows[1]['seed_key']:
        raise ValueError('paired seed mismatch')


def run_slot(prepared_dir, prepared, out, cell, method, charged, guard):
    from . import pilot
    directory = out / 'attempts' / cell_id(cell) / method
    directory.mkdir(parents=True, exist_ok=False)
    write_new(directory / 'started.json', dict(cell=cell, method=method, source=prepared['source'],
              run_id=prepared['run_id'], controller_pid=os.getpid(), started_at=time.time()))
    cfg = prepared['configs'][cell['initial_energy_kwh']]
    resources = prepared['config']['resources']
    args = SimpleNamespace(config=str(prepared_dir / cfg['config']), preflight=str(prepared_dir / cfg['preflight']),
        graph_tsv=prepared['inputs']['graph'], native_cache=str(out / 'native-cache'),
        output=str(directory / 'aggregate.jsonl'), preflight_only=False, domains='64', queries=cell['query_id'],
        scenarios=cell['scenario'], methods=method, diagnostic=False, ablation=False, no_bound=False,
        solve_limit_seconds=resources['loaded_limit_s'], development_cpu_s=charged,
        cold_load_allowance_s=resources['cold_allowance_s'], process_memory_gib=resources['process_memory_bytes'] // 1024**3,
        receipt_directory=str(directory), run_identity=dict(run_id=prepared['run_id'], cell_id=cell_id(cell),
        method=method, source=prepared['source']), cpu_budget_guard=guard)
    pilot.main(args)
    paths = list(directory.glob('*.row.json'))
    if len(paths) != 1:
        raise RuntimeError('worker has no unique durable terminal row; inspect receipts, do not retry')
    row = {**cell, **read_json(paths[0]), 'initial_energy_kwh': cell['initial_energy_kwh'], 'execution': 'new'}
    validate_result(row)
    return row


def benchmark(prepared_dir, output):
    validation_started = time.process_time()
    prepared_dir, out = Path(prepared_dir).resolve(), Path(output).resolve()
    prepared = read_json(prepared_dir / 'prepared.json')
    if digest(prepared_dir / 'prepared.json') != read_json(prepared_dir / 'preparation.receipt.json')['prepared_sha256']:
        raise ValueError('preparation receipt mismatch')
    validate_prepared(prepared_dir, prepared)
    validation_cpu = time.process_time() - validation_started
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / 'prepared.json', prepared)
    write_new(out / 'started.json', dict(pid=os.getpid(), prepared_sha256=digest(prepared_dir / 'prepared.json'),
                                        run_id=prepared['run_id'], time=time.time()))
    started = time.process_time()
    resources = prepared['config']['resources']
    charged = resources['development_reporting_cpu_s']
    rows, receipts, stopped, error = [], {}, False, None
    uncertain_reserved = 0
    def total():
        return charged + time.process_time() - started
    def guard(worker_cpu):
        return total() + worker_cpu + 30 < resources['stage_cpu_s']
    try:
        for cell in n64_cells(prepared['matrix']):
            status = None
            if cell['input_status'] != 'available':
                status = 'input_domain_unavailable'
            elif stopped or total() + 2 * (resources['worker_reservation_cpu_s'] + resources['controller_reservation_cpu_s']) > resources['stage_cpu_s']:
                stopped, status = True, 'not_run_cpu_budget'
            pair = []
            for method in METHODS:
                if status:
                    row = {**cell, 'method': method, 'status': status, 'mathematical_status': 'unknown',
                           'execution': 'not_attempted', 'stage_charged_cpu_s': 0}
                else:
                    uncertain_reserved = resources['worker_reservation_cpu_s'] + resources['controller_reservation_cpu_s']
                    row = run_slot(prepared_dir, prepared, out, cell, method, total(), guard)
                    cost = max(row.get('worker_cpu_s', 0), row.get('supervisor_cpu_s', 0)) + 1
                    charged += cost
                    uncertain_reserved = 0
                    row['stage_charged_cpu_s'] = cost
                receipt = Path('rows') / (cell_id(cell) + '-' + method + '.json')
                write_new(out / receipt, row)
                receipts[str(receipt)] = digest(out / receipt)
                rows.append(row); pair.append(row)
                if row['status'] in {'worker_error', 'host_headroom_limit'}:
                    raise RuntimeError('worker/system failure; inspect the retained slot receipts')
            compare_pair(pair)
        validate_prepared(prepared_dir, prepared)
    except Exception as exc:
        error = repr(exc)
    state = 'failed' if error else 'budget_stopped' if stopped else 'complete'
    write_new(out / 'results.json', dict(rows=rows))
    write_new(out / 'terminal.json', dict(schema='hiroute.research_terminal.v1', state=state, error=error,
        run_id=prepared['run_id'], source=prepared['source'], receipts=receipts,
        prepared_sha256=digest(out / 'prepared.json'), results_sha256=digest(out / 'results.json'),
        worker_and_development_cpu_s=charged, controller_cpu_s=time.process_time() - started,
        uncertain_reserved_cpu_s=uncertain_reserved,
        conservative_total_cpu_s=charged + uncertain_reserved + math.ceil(time.process_time() - started) + 2,
        input_validation_cpu_s=validation_cpu,
        cap_cpu_s=resources['stage_cpu_s'], historical_carried_cpu_s=0))
    if error:
        raise RuntimeError(error)
    return dict(state=state, slots=len(rows), output=str(out))
