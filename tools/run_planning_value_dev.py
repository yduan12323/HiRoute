"""Frozen four-query policy DEV stage with inclusive, durable admission."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace

import run_n64_coverage_stage as common
import run_real_scale_pilot as pilot
from d04_cost_diagnostic import domain_digest

ROOT = Path(__file__).resolve().parents[1]
load, digest = common.load, common.digest


def recipe(path):
    spec = load(path)
    proposal = ROOT/spec['proposal_file']
    if digest(proposal) != spec['proposal_sha256']:
        raise ValueError('frozen policy proposal changed')
    definition = load(proposal)
    matrix = ROOT/definition['matrix']['file']
    if digest(matrix) != definition['matrix']['sha256']:
        raise ValueError('frozen matrix changed')
    if (spec['gate_cap_cpu_s'] != 3000 or spec['stage_cap_cpu_s'] != 2100 or
            spec['nonstage_precharge_cpu_s'] != 900 or spec['pair_reservation_cpu_s'] != 1240 or
            spec['cleanup_reserve_cpu_s'] != 120 or spec['loaded_limit_s'] != 120 or
            spec['worker_enforced_cpu_s'] != 300 or spec['cold_allowance_s'] != 180 or
            spec['carried_cpu_s'] != 12805.649970329 or spec['original_cap_cpu_s'] != 28800 or
            not spec['execution_authorized']):
        raise ValueError('gate resource authorization mismatch')
    rows = definition['rows']
    expected = [(q,e,p) for e in ('18','48') for q in ('WD01','WD07')
                for p in (definition['policies'] if q=='WD01' else definition['policies'][::-1])]
    if [(r['query_id'],r['initial_energy_kwh'],r['policy']) for r in rows] != expected or len(rows) != 8:
        raise ValueError('frozen policy denominator/order changed')
    return spec, definition, load(matrix)


def prepare(args):
    spec, definition, matrix = recipe(args.config)
    original = load(Path(args.existing_stage)/'preparation.json')
    out = Path(args.output_root).resolve()
    out.mkdir(parents=True, exist_ok=False)
    import psutil
    import shutil
    available, free = psutil.virtual_memory().available, shutil.disk_usage(out).free
    if available < 2684354560 or free < 2*1024**3:
        raise ValueError('host memory/disk preflight failed')
    for name, path in original['inputs'].items():
        if digest(path) != original['input_sha256'][name]:
            raise ValueError('historical real input changed: '+name)
    if (original['input_sha256']['catalog'] != matrix['catalog_sha256'] or
            original['input_sha256']['bindings'] != matrix['bindings_sha256']):
        raise ValueError('frozen source catalog/bindings mismatch')
    configs = {}
    for energy in ('18','48'):
        old = original['configs'][energy]
        if digest(old['config']) != old['config_sha256'] or digest(old['preflight']) != old['preflight_sha256']:
            raise ValueError('historical configuration changed')
        config, manifest = load(old['config']), load(old['preflight'])
        if config['implementation'] != matrix['implementation_profile']:
            raise ValueError('historical implementation profile mismatch')
        expected_model = {**matrix['model'], 'initial_energy_kwh': energy}
        if config['model'] != expected_model or manifest['config'] != config:
            raise ValueError('historical physical snapshot mismatch')
        for row in definition['rows']:
            if row['initial_energy_kwh'] != energy:continue
            q = next(q for q in manifest['queries'] if q['query_id'] == row['query_id'])
            if domain_digest(q,64,'schedule') != row['original_candidate_domain_sha256']:
                raise ValueError('frozen candidate domain mismatch')
        for policy in definition['policies']:
            cfg, pre = copy.deepcopy(config), copy.deepcopy(manifest)
            cfg['planning_policy'] = policy
            cfg['pilot_matrix'] = [dict(N=64,query_ids=['WD01','WD07'],scenarios=['schedule'])]
            pre['config'] = cfg
            cp, pp = out/f'E{energy}.{policy}.config.json', out/f'E{energy}.{policy}.preflight.json'
            pilot.atomic(cp,cfg);pilot.atomic(pp,pre)
            pilot.preflight(SimpleNamespace(config=cp,preflight=pp,graph_tsv=original['inputs']['graph']))
            configs[energy,policy] = dict(config=str(cp),preflight=str(pp),
                config_sha256=digest(cp),preflight_sha256=digest(pp))
    record = dict(source=common.source_identity(),spec=spec,spec_sha256=digest(args.config),
                  definition=definition,inputs=original['inputs'],input_sha256=original['input_sha256'],
                  input_stat={k:dict(size=Path(v).stat().st_size,mtime_ns=Path(v).stat().st_mtime_ns)
                              for k,v in original['inputs'].items()},
                  configs={e+'|'+p:v for (e,p),v in configs.items()},
                  host_available_bytes=available,disk_free_bytes=free,solver_called=False,
                  joint_reference_read=False)
    pilot.atomic(out/'preparation.json',record)


def row_id(row):
    return f"{row['query_id']}-E{row['initial_energy_kwh']}-schedule-N64-{row['policy']}"


def admission(spec, charged):
    need = charged+spec['pair_reservation_cpu_s']+spec['cleanup_reserve_cpu_s']
    return (need <= spec['stage_cap_cpu_s'] and
            spec['carried_cpu_s']+spec['nonstage_precharge_cpu_s']+need <= spec['original_cap_cpu_s'])


def validate_policy_row(row):
    if row['status'] == 'policy_no_eligible_activity':
        if row.get('feasible_key') is not None or not row.get('policy_info'):
            raise ValueError('invalid no-eligible-activity receipt')
        return
    common.validate_row(row)
    if row.get('feasible_key') is not None:
        witness = row['witness']
        if witness.get('policy_verified') is not True or witness.get('original_joint_model_verified') is not True:
            raise ValueError('missing original and policy physical replay')


def run_worker(out, prepared, slot, original_cpu, guard):
    directory = out/'attempts'/row_id(slot)
    directory.mkdir(parents=True,exist_ok=True)
    if (directory/'started.json').exists():
        raise RuntimeError('uncertain prior policy start; inspect receipts, never replay')
    pilot.atomic(directory/'started.json',dict(slot=slot,source=prepared['source'],
                 controller_pid=os.getpid(),started_at=time.time(),worker_reservation_cpu_s=310))
    cfg = prepared['configs'][slot['initial_energy_kwh']+'|'+slot['policy']]
    args = SimpleNamespace(config=cfg['config'],preflight=cfg['preflight'],
        graph_tsv=prepared['inputs']['graph'],native_cache=str(out/'native-cache'),
        output=str(directory/'aggregate.jsonl'),preflight_only=False,domains='64',queries=slot['query_id'],
        scenarios='schedule',methods='flat_bb_strong',diagnostic=False,ablation=False,no_bound=False,
        solve_limit_seconds=None,development_cpu_s=original_cpu,cold_load_allowance_s=180,
        process_memory_gib=8,receipt_directory=str(directory),run_identity=dict(slot_id=row_id(slot),
        source=prepared['source']),cpu_budget_guard=guard)
    pilot.main(args)
    row = common.terminal_row(directory)
    if row is None:raise RuntimeError('missing terminal policy receipt')
    return row


def execute(args):
    started = time.process_time()
    out = Path(args.output_root).resolve()
    with common.controller_lock(out):
        prepared = load(out/'preparation.json')
        spec, definition, _ = recipe(args.config)
        if spec != prepared['spec'] or common.source_identity() != prepared['source']:
            raise ValueError('per-run source/environment/spec changed')
        for record in prepared['configs'].values():
            for name in ('config','preflight'):
                if digest(record[name]) != record[name+'_sha256']:
                    raise ValueError('prepared policy input changed')
        for name,path in prepared['inputs'].items():
            stat = Path(path).stat()
            if dict(size=stat.st_size,mtime_ns=stat.st_mtime_ns) != prepared['input_stat'][name]:
                raise ValueError('real input changed since preflight')
        old = load(out/'status.json') if (out/'status.json').exists() else None
        if old and old['state'] != 'paused_requested':
            raise RuntimeError('terminal, failed or uncertain controller invocation; inspect instead of restarting')
        carried = common.closed_controller_cost(old) if old else 0
        slots = copy.deepcopy(definition['rows'])
        charged = 0
        for slot in slots:
            directory = out/'attempts'/row_id(slot)
            row = common.terminal_row(directory) if directory.exists() else None
            if row is not None:
                slot.update(row,policy=slot['policy'])
                charged += max(row.get('worker_cpu_s',0),row.get('supervisor_cpu_s',0))+1
                validate_policy_row(row)
        for slot in slots:
            if slot['status'] == 'not_started_definition_only':slot['status']='not_run'
        def cpu():return carried+time.process_time()-started
        def total():return charged+cpu()
        def publish(state, error=None):
            pilot.atomic(out/'results.json',dict(rows=slots,query_denominator=4,policy_row_denominator=8))
            pilot.atomic(out/'status.json',dict(state=state,error=error,controller_pid=os.getpid(),
                total_controller_cpu_s=cpu(),worker_cpu_charged_s=charged,
                stage_charged_cpu_s=total(),stage_cap_cpu_s=spec['stage_cap_cpu_s'],
                inclusive_gate_charged_cpu_s=spec['nonstage_precharge_cpu_s']+total(),
                original_total_cpu_s=spec['carried_cpu_s']+spec['nonstage_precharge_cpu_s']+total(),
                source=prepared['source'],joint_reference_read=False))
        pause = [False]
        def request_pause(*_):pause[0]=True
        previous = {sig:signal.signal(sig,request_pause) for sig in (signal.SIGTERM,signal.SIGINT)}
        publish('running')
        try:
            budget_stopped = False
            for index in range(0,8,2):
                pair = slots[index:index+2]
                fresh = [r for r in pair if r['status'] in ('not_run','budget_unrun')]
                if not fresh:continue
                if pause[0] or (out/'pause-request.json').exists():
                    publish('paused_requested');return
                if len(fresh)!=2:
                    raise RuntimeError('partial pair requires inspected reservation recovery; no automatic resume')
                if budget_stopped or not admission(spec,total()):
                    budget_stopped=True
                    for row in fresh:row.update(status='budget_unrun',execution='not_attempted')
                    publish('running');continue
                for slot in pair:
                    slot.update(status='running',execution='fresh')
                    publish('running')
                    last=[-1.]
                    def guard(active_cpu):
                        inclusive=total()+active_cpu
                        allowed=(inclusive+spec['cleanup_reserve_cpu_s'] < spec['stage_cap_cpu_s'] and
                            spec['carried_cpu_s']+spec['nonstage_precharge_cpu_s']+inclusive+
                            spec['cleanup_reserve_cpu_s'] < spec['original_cap_cpu_s'])
                        if time.monotonic()-last[0]>=1 or not allowed:
                            pilot.atomic(out/'budget-live.json',dict(slot_id=row_id(slot),
                                controller_pid=os.getpid(),worker_prior_cpu_s=charged,
                                cumulative_controller_cpu_s=cpu(),active_worker_cpu_s=active_cpu,
                                stage_inclusive_cpu_s=inclusive,cleanup_reserve_cpu_s=120,allowed=allowed))
                            last[0]=time.monotonic()
                        return allowed
                    row=run_worker(out,prepared,slot,
                        spec['carried_cpu_s']+spec['nonstage_precharge_cpu_s']+total(),guard)
                    cost=max(row.get('worker_cpu_s',0),row.get('supervisor_cpu_s',0))+1
                    charged+=cost
                    slot.update(row,execution='fresh',stage_worker_charged_cpu_s=cost,
                                numerical_source=prepared['source'])
                    pilot.atomic(out/'attempts'/row_id(slot)/'final.json',slot)
                    publish('running')
                    if cost>310 or total()+120>spec['stage_cap_cpu_s']:
                        raise RuntimeError('policy accounting/reservation overrun')
                    validate_policy_row(slot)
                print(pair[0]['query_id'],pair[0]['initial_energy_kwh'],
                      [r['status'] for r in pair],total(),flush=True)
            publish('budget_stopped' if budget_stopped else 'complete')
        except BaseException as exc:
            publish('paused',repr(exc));raise
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','execute'))
    parser.add_argument('--config',default=str(ROOT/'configs/planning_value_dev_gate.json'))
    parser.add_argument('--existing-stage')
    parser.add_argument('--output-root',required=True)
    args=parser.parse_args()
    {'prepare':prepare,'execute':execute}[args.action](args)
