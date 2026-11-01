"""Bounded, durable N64 DEV controller; no solver/profile changes or retries.

Prepare first, then execute the frozen order. A controller lock prevents duplicate
workers. Every attempted method has a write-once start record and atomic terminal
row. An interrupted start without a terminal row pauses for evidence recovery;
it never restarts a possibly executed solve. Completed rows are reconstructed
from durable per-method receipts, not an append-only aggregate offset.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import run_real_scale_pilot as pilot
from d04_cost_diagnostic import domain_digest
from real_scale_inputs import select_domains

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('flat_bb_strong','scale')
COMPLETE = {'attained_optimum','infeasible','primary_unattained','secondary_unattained'}


def load(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def cell_id(cell):
    return f"{cell['query_id']}-E{cell['initial_energy_kwh']}-{cell['scenario']}-N{cell['N']}"


def cells(matrix):
    result = [c for c in matrix['cells'] if c['N']==64]
    expected = [(f'WD{i:02d}',e,s) for i in range(1,13)
                for e in ('18','48') for s in ('energy_only','schedule')]
    if [(c['query_id'],c['initial_energy_kwh'],c['scenario']) for c in result] != expected:
        raise ValueError('frozen N64 denominator/order changed')
    if matrix['methods'] != list(METHODS):
        raise ValueError('paired methods/order changed')
    return result


def same_reuse_cell(cell, spec):
    return all(cell[k]==spec[k] for k in ('query_id','initial_energy_kwh','scenario','N'))


def reserve_pair(spec, charged):
    return (charged+spec['pair_reservation_cpu_s'] <= spec['stage_cap_cpu_s'] and
            spec['carried_cpu_s']+charged+spec['pair_reservation_cpu_s'] <= spec['original_cap_cpu_s'])


def source_identity():
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True):
        raise ValueError('commit tracked changes before a scientific stage')
    return dict(commit=head,python=sys.version,executable=sys.executable,platform=platform.platform())


def validate_spec(spec, matrix):
    if (spec['methods'] != list(METHODS) or spec['loaded_limit_s'] != 120 or
            spec['cold_allowance_s'] != 180 or spec['worker_enforced_cpu_s'] != 300 or
            spec['stage_cap_cpu_s'] != 12000 or spec['original_cap_cpu_s'] != 28800 or
            spec['carried_cpu_s'] != 5226.078454329 or
            spec['worker_reservation_cpu_s'] < 310 or
            spec['pair_reservation_cpu_s'] != 2*spec['worker_reservation_cpu_s']):
        raise ValueError('stage authorization/resource mismatch')
    if matrix['resources']['query_loaded_limit_s'] != spec['loaded_limit_s']:
        raise ValueError('matrix limit mismatch')
    cells(matrix)


def prepare(args):
    started,cpu = time.monotonic(),time.process_time()
    spec_path = Path(args.config).resolve()
    spec = load(spec_path); matrix_path = ROOT/spec['matrix']; matrix = load(matrix_path)
    validate_spec(spec,matrix)
    out = Path(args.output_root).resolve()
    out.mkdir(parents=True,exist_ok=False)
    identity = source_identity()
    catalog = Path(args.catalog).resolve(); graph = Path(args.graph_tsv).resolve()
    inputs = dict(catalog=str(catalog/'shared-sites.json'),bindings=str(catalog/'site-bindings.json'),graph=str(graph))
    hashes = {k:digest(v) for k,v in inputs.items()}
    if hashes['catalog'] != matrix['catalog_sha256'] or hashes['bindings'] != matrix['bindings_sha256']:
        raise ValueError('supplemented input identity changed')
    import psutil
    psutil.pids()  # fail transport/monitor permission checks before any solve
    host = psutil.virtual_memory().available
    free = shutil.disk_usage(out).free
    if host < 2147483648+512*1024**2 or free < 2*1024**3:
        raise ValueError('insufficient host memory or disk headroom')
    sites,bindings = load(inputs['catalog']),load(inputs['bindings'])
    base = load(ROOT/spec['base_config'])
    if base['model'] != matrix['model']:
        raise ValueError('frozen physical model changed')
    configs = {}
    for energy in ('18','48'):
        cfg = copy.deepcopy(base)
        cfg['model']['initial_energy_kwh'] = energy
        cfg['selection'] = copy.deepcopy(matrix['endpoint_and_selection_policy'])
        cfg['selection']['candidate_counts'] = [64]
        cfg['implementation'] = matrix['implementation_profile']
        cfg['pilot_matrix'] = [dict(N=64,query_ids=[c['query_id']],scenarios=[c['scenario']])
                               for c in cells(matrix) if c['initial_energy_kwh']==energy]
        manifest = select_domains(cfg,sites,bindings)
        if {q['query_id']:q['endpoints'] for q in manifest['queries']} != matrix['endpoints']:
            raise ValueError('frozen endpoints changed')
        for cell in cells(matrix):
            if cell['initial_energy_kwh'] != energy:
                continue
            q = next(q for q in manifest['queries'] if q['query_id']==cell['query_id'])
            available = q['scenario_domain_status'][cell['scenario']]['64']=='available'
            if available != (cell['input_status']=='available') or q['scenario_eligible_counts'][cell['scenario']] != cell['qualified_count']:
                raise ValueError('frozen input availability changed')
            if available and domain_digest(q,64,cell['scenario']) != cell['candidate_domain_sha256']:
                raise ValueError('frozen candidate domain changed')
        cp,mp=out/f'E{energy}.config.json',out/f'E{energy}.preflight.json'
        pilot.atomic(cp,cfg);pilot.atomic(mp,manifest)
        configs[energy]=dict(config=str(cp),preflight=str(mp),config_sha256=digest(cp),preflight_sha256=digest(mp))
        pilot.preflight(SimpleNamespace(config=str(cp),preflight=str(mp),graph_tsv=str(graph)))
    used = time.process_time()-cpu
    if spec['preparation_carried_cpu_s']+used > spec['preparation_cap_cpu_s']:
        raise ValueError('preparation budget exhausted')
    record=dict(schema='hiroute.n64.preparation.v1',source=identity,inputs=inputs,input_sha256=hashes,
        input_stat={k:dict(size=Path(v).stat().st_size,mtime_ns=Path(v).stat().st_mtime_ns) for k,v in inputs.items()},
        spec=spec,spec_sha256=digest(spec_path),matrix_sha256=digest(matrix_path),configs=configs,
        preparation_cpu_s=used,preparation_wall_s=time.monotonic()-started,
        total_preparation_cpu_s=spec['preparation_carried_cpu_s']+used,
        host_available_bytes=host,disk_free_bytes=free,solver_called=False,road_query_called=False)
    pilot.atomic(out/'preparation.json',record)
    return record


@contextmanager
def controller_lock(out):
    with (out/'controller.lock').open('a') as stream:
        try:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('another stage controller owns the lock') from None
        yield


def terminal_row(directory):
    final = directory/'final.json'
    if final.exists():
        return load(final)
    # The pilot atomically persists its merged result before JSONL append.
    saved = list(directory.glob('*.row.json'))
    if len(saved)==1:
        return load(saved[0])
    if (directory/'started.json').exists():
        raise RuntimeError(f'uncertain attempt; inspect supervisor receipt/PID before recovery: {directory}')
    return None


def validate_row(row):
    if row['status'] not in COMPLETE|{'time_limit'}:
        raise RuntimeError('unexpected worker outcome: '+row['status'])
    if row.get('failed_phase'):
        raise RuntimeError('unexpected cold/input failure: '+row['failed_phase'])
    if row['status']=='time_limit' and (row.get('key') is not None or row.get('mathematical_status','unknown')!='unknown'):
        raise RuntimeError('resource outcome is not a mathematical completion')
    if row.get('feasible_key') is not None or row.get('key') is not None:
        if not isinstance(row.get('witness'),dict) or row['witness'].get('physical_verified') is not True:
            raise RuntimeError('feasible result without physical replay')
    if row['status']=='attained_optimum' and (row.get('key') is None or row.get('key')!=row.get('feasible_key')):
        raise RuntimeError('attained result missing full key')
    if ((row['status'] in COMPLETE and not row.get('depth_contract')) or
            (row.get('depth_contract') and row['depth_contract']['mode']!='unrestricted')):
        raise RuntimeError('incomplete depth contract')
    values=[row.get('worker_cpu_s',0),row.get('supervisor_cpu_s',0)]
    if any(not math.isfinite(v) or v<0 for v in values):
        raise RuntimeError('invalid CPU evidence')


def compare_pair(rows):
    if [r['method'] for r in rows] != list(METHODS):
        raise RuntimeError('incomplete method pair')
    if all(r['status'] in COMPLETE for r in rows):
        fields=('status','key','primary_value','primary_infimum','secondary_infimum')
        if tuple(rows[0].get(k) for k in fields)!=tuple(rows[1].get(k) for k in fields):
            raise RuntimeError('completed pair full-key/attainment mismatch')
    if all(r.get('seed_key') is not None for r in rows) and rows[0]['seed_key']!=rows[1]['seed_key']:
        raise RuntimeError('paired seed mismatch')


def reused_rows(cell,spec,matrix):
    if not same_reuse_cell(cell,spec['reuse']):
        return None
    old=load(ROOT/spec['reuse']['file'])
    prior=load(ROOT/'configs/existing_domain_transfer_dev.json')
    if (prior['model'] != matrix['model'] or prior['model']['initial_energy_kwh'] != cell['initial_energy_kwh'] or
            prior['profiles']['current_queue_profile'] != matrix['implementation_profile']):
        raise ValueError('reuse model/initial-energy/profile mismatch')
    rows=[copy.deepcopy(r) for r in old['rows'] if r['domain_id']==spec['reuse']['domain_id']]
    if len(rows)!=2 or {r['method'] for r in rows}!=set(METHODS):
        raise ValueError('reuse pair unavailable')
    for row in rows:
        if (row['N']!=64 or row['scenario']!='energy_only' or
                row['candidate_domain_sha256']!=cell['candidate_domain_sha256'] or
                row['implementation']!=matrix['implementation_profile'] or row['solve_limit_s']!=120):
            raise ValueError('reuse scientific identity mismatch')
        validate_row(row)
        row.update(query_id=cell['query_id'],initial_energy_kwh=cell['initial_energy_kwh'],
            execution='reused',stage_charged_cpu_s=0,reuse_source=dict(file=spec['reuse']['file'],
            numerical_source_commit=old['numerical_source_commit'],original_query_id='SD01'))
    rows.sort(key=lambda r:METHODS.index(r['method']))
    compare_pair(rows)
    return rows


def unavailable_rows(cell,status):
    return [{**cell,'method':method,'status':status,'mathematical_status':'unknown',
             'execution':'not_attempted','stage_charged_cpu_s':0} for method in METHODS]


def run_worker(out,prepared,cell,method,total):
    directory=out/'attempts'/cell_id(cell)/method
    directory.mkdir(parents=True,exist_ok=True)
    recovered=terminal_row(directory)
    if recovered is not None:
        return recovered
    pilot.atomic(directory/'started.json',dict(cell=cell,method=method,controller_pid=os.getpid(),
        source=prepared['source'],started_at=time.time(),reserved_cpu_s=310))
    config=prepared['configs'][cell['initial_energy_kwh']]
    args=SimpleNamespace(config=config['config'],preflight=config['preflight'],
        graph_tsv=prepared['inputs']['graph'],native_cache=str(out/'native-cache'),
        output=str(directory/'aggregate.jsonl'),preflight_only=False,domains='64',queries=cell['query_id'],
        scenarios=cell['scenario'],methods=method,diagnostic=False,ablation=False,no_bound=False,
        solve_limit_seconds=None,development_cpu_s=total,cold_load_allowance_s=180,process_memory_gib=8,
        receipt_directory=str(directory),run_identity=dict(cell_id=cell_id(cell),method=method,**prepared['source']))
    pilot.main(args)
    row=terminal_row(directory)
    if row is None:
        raise RuntimeError('guarded worker produced no durable row')
    return row


def execute(args):
    out=Path(args.output_root).resolve()
    with controller_lock(out):
        prepared=load(out/'preparation.json'); spec=prepared['spec']; matrix=load(ROOT/spec['matrix'])
        validate_spec(spec,matrix)
        if prepared['source']!=source_identity() or prepared['matrix_sha256']!=digest(ROOT/spec['matrix']):
            raise ValueError('run source/environment/matrix identity changed')
        for cfg in prepared['configs'].values():
            if digest(cfg['config'])!=cfg['config_sha256'] or digest(cfg['preflight'])!=cfg['preflight_sha256']:
                raise ValueError('prepared input identity changed')
        for name,record in prepared.get('input_stat',{}).items():
            path=Path(prepared['inputs'][name])
            if dict(size=path.stat().st_size,mtime_ns=path.stat().st_mtime_ns)!=record:
                raise ValueError('scientific input changed after preparation')
        charged=spec['development_and_reporting_precharge_cpu_s']; rows=[]; stopped=False
        stage_started=time.process_time()
        def publish(state,error=None):
            pilot.atomic(out/'results.json',dict(rows=rows,denominator_cells=cells(matrix)))
            uncertain=[str(p.parent) for p in (out/'attempts').glob('*/*/started.json')
                       if not (p.parent/'final.json').exists() and not list(p.parent.glob('*.row.json'))]
            pilot.atomic(out/'status.json',dict(state=state,error=error,controller_pid=os.getpid(),
                stage_charged_cpu_s=charged,total_charged_cpu_s=spec['carried_cpu_s']+charged,
                uncertain_attempts=uncertain,uncertain_reserved_cpu_s=len(uncertain)*spec['worker_reservation_cpu_s'],
                stage_cap_cpu_s=spec['stage_cap_cpu_s'],original_cap_cpu_s=spec['original_cap_cpu_s'],
                method_rows=len(rows),controller_cpu_s=time.process_time()-stage_started))
        try:
            for cell in cells(matrix):
                if cell['input_status']!='available':
                    rows.extend(unavailable_rows(cell,'input_domain_unavailable'));publish('running');continue
                reuse=reused_rows(cell,spec,matrix)
                if reuse is not None:
                    rows.extend(reuse);publish('running');continue
                directories=[out/'attempts'/cell_id(cell)/m for m in METHODS]
                saved=[terminal_row(d) if d.exists() else None for d in directories]
                # A partially completed pair already holds its original reservation.
                needed=sum(r is None for r in saved)*spec['worker_reservation_cpu_s']
                observed=sum(max(r.get('worker_cpu_s',0),r.get('supervisor_cpu_s',0))+1 for r in saved if r)
                if stopped or (not any(saved) and not reserve_pair(spec,charged)):
                    stopped=True;rows.extend(unavailable_rows(cell,'not_run_cpu_budget'));publish('running');continue
                if charged+observed+needed > spec['stage_cap_cpu_s'] or spec['carried_cpu_s']+charged+observed+needed > spec['original_cap_cpu_s']:
                    raise RuntimeError('pending pair reservation cannot be honored')
                pair=[]
                for method,saved_row in zip(METHODS,saved):
                    row=saved_row or run_worker(out,prepared,cell,method,spec['carried_cpu_s']+charged)
                    cost=max(row.get('worker_cpu_s',0),row.get('supervisor_cpu_s',0))+1
                    charged+=cost
                    row.update(initial_energy_kwh=cell['initial_energy_kwh'],execution='fresh',
                        candidate_domain_sha256=cell['candidate_domain_sha256'],stage_charged_cpu_s=cost,
                        stage_cumulative_cpu_s=charged,total_cumulative_cpu_s=spec['carried_cpu_s']+charged)
                    # Charge/persist before validating, so a failing row is never free.
                    pilot.atomic(out/'attempts'/cell_id(cell)/method/'final.json',row)
                    rows.append(row);publish('running')
                    if cost>spec['worker_reservation_cpu_s'] or charged>spec['stage_cap_cpu_s'] or spec['carried_cpu_s']+charged>spec['original_cap_cpu_s']:
                        raise RuntimeError('enforcement/accounting reserve exceeded')
                    validate_row(row);pair.append(row)
                compare_pair(pair)
                print(cell_id(cell),'pair recorded',charged,flush=True)
            if len(rows)!=96:
                raise RuntimeError('N64 denominator lost')
            publish('budget_stopped' if stopped else 'complete')
        except BaseException as exc:
            publish('paused',repr(exc));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','execute'))
    p.add_argument('--config',default=str(ROOT/'configs/n64_coverage_stage.json'))
    p.add_argument('--catalog');p.add_argument('--graph-tsv');p.add_argument('--output-root',required=True)
    a=p.parse_args()
    prepare(a) if a.action=='prepare' else execute(a)
