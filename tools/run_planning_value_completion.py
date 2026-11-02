"""Prospective completion of exactly the two historical budget-unrun slots.

This controller never resumes the closed predecessor or reads joint values.
Its worker and live cumulative admission are the existing policy controller.
"""
import argparse
import copy
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import run_planning_value_dev as stage

ROOT = stage.ROOT


def recipe(path):
    spec = stage.load(path)
    expected = dict(schema='hiroute.planning_value_completion.v1',
        carried_cpu_s=14708.280547741, original_cap_cpu_s=28800,
        gate_cap_cpu_s=1600, nonstage_precharge_cpu_s=120, stage_cap_cpu_s=1480,
        pair_reservation_cpu_s=1240, cleanup_reserve_cpu_s=120,
        loaded_limit_s=120, cold_allowance_s=180, worker_enforced_cpu_s=300,
        worker_reservation_cpu_s=310, process_memory_gib=8, threads=1, workers=1,
        execution_authorized=True,preflight_min_available_bytes=2684354560)
    if any(spec.get(k) != v for k,v in expected.items()):
        raise ValueError('completion allocation/resource authorization mismatch')
    _, full, matrix = stage.recipe(ROOT/'configs/planning_value_dev_gate.json')
    if stage.digest(ROOT/'configs/planning_value_baselines_dev.json') != spec['proposal_sha256']:
        raise ValueError('original frozen proposal changed')
    selected = copy.deepcopy(full)
    selected['rows'] = copy.deepcopy(full['rows'][-2:])
    if [(r['query_id'],r['initial_energy_kwh'],r['policy']) for r in selected['rows']] != [
            ('WD07','48','activity_first_fixed_site'),('WD07','48','separated_no_overlap')]:
        raise ValueError('only-unrun pair/order changed')
    if any(r['N']!=64 or r['scenario']!='schedule' for r in selected['rows']):
        raise ValueError('completion workload changed')
    for row in selected['rows']:
        row.update(status='not_started_definition_only',historical_status='budget_unrun')
    return spec, selected, matrix


def predecessor(root, spec):
    root = Path(root).resolve()
    for name, expected in spec['predecessor_sha256'].items():
        if name not in ('preparation.json','results.json','status.json') or stage.digest(root/name) != expected:
            raise ValueError('historical raw artifact changed: '+name)
    if set(spec['predecessor_sha256']) != {'preparation.json','results.json','status.json'}:
        raise ValueError('incomplete historical identity')
    status = stage.load(root/'status.json')
    if status['state'] != 'budget_stopped' or stage.common.active_pid(status['controller_pid']):
        raise ValueError('predecessor is not confirmed terminal')
    prepared = stage.load(root/'preparation.json')
    rows = stage.load(root/'results.json')['rows']
    full = prepared['definition']['rows']
    if len(rows)!=8 or [stage.row_id(r) for r in rows] != [stage.row_id(r) for r in full]:
        raise ValueError('historical denominator/order changed')
    receipts = {}
    for row in rows[:6]:
        stage.validate_policy_row(row)
        receipt = root/'attempts'/stage.row_id(row)/'final.json'
        if stage.load(receipt) != row:
            raise ValueError('historical terminal row/receipt mismatch')
        receipts[stage.row_id(row)] = stage.digest(receipt)
    for row in rows[6:]:
        if row['status'] != 'budget_unrun' or (root/'attempts'/stage.row_id(row)).exists():
            raise ValueError('completion slot may already have started; never replay')
    return prepared, dict(root=str(root),sha256=spec['predecessor_sha256'],
                          numerical_source=prepared['source'],six_terminal_sha256=receipts,
                          prior_setup_cost_already_inside_carried_charge=True)


def prepare(args):
    spec, definition, matrix = recipe(args.config)
    original, prior = predecessor(args.previous_stage,spec)
    out = Path(args.output_root).resolve()
    out.mkdir(parents=True,exist_ok=False)
    import psutil
    psutil.pids()  # same monitor permission requirement, before any start
    available, free = psutil.virtual_memory().available, shutil.disk_usage(out).free
    if available < spec['preflight_min_available_bytes'] or free < 2*1024**3:
        raise ValueError('completion host memory/disk preflight failed')
    stage.dependency_preflight(original)
    from hiroute.exact.road_index import _load_native_library
    _load_native_library(out/'dependency-preflight')  # compile only, no graph/query
    for name,path in original['inputs'].items():
        if stage.digest(path) != original['input_sha256'][name]:
            raise ValueError('historical real input changed: '+name)
    if (original['input_sha256']['catalog'] != matrix['catalog_sha256'] or
            original['input_sha256']['bindings'] != matrix['bindings_sha256']):
        raise ValueError('frozen catalog/bindings mismatch')
    if original['definition'] != stage.load(ROOT/'configs/planning_value_baselines_dev.json'):
        raise ValueError('predecessor proposal identity mismatch')
    configs = {}
    for row in definition['rows']:
        key = row['initial_energy_kwh']+'|'+row['policy']
        record = original['configs'][key]
        for name in ('config','preflight'):
            if stage.digest(record[name]) != record[name+'_sha256']:
                raise ValueError('historical policy configuration changed')
        config,manifest = stage.load(record['config']),stage.load(record['preflight'])
        if (config['implementation'] != matrix['implementation_profile'] or
                config['model'] != {**matrix['model'],'initial_energy_kwh':'48'} or
                config['planning_policy'] != row['policy'] or manifest['config'] != config):
            raise ValueError('policy/model/profile mismatch')
        query = next(q for q in manifest['queries'] if q['query_id']=='WD07')
        if stage.domain_digest(query,64,'schedule') != row['original_candidate_domain_sha256']:
            raise ValueError('frozen WD07 candidate domain changed')
        stage.pilot.preflight(SimpleNamespace(config=record['config'],
            preflight=record['preflight'],graph_tsv=original['inputs']['graph']))
        configs[key] = record
    stage.pilot.atomic(out/'preparation.json',dict(source=stage.common.source_identity(),
        spec=spec,spec_sha256=stage.digest(args.config),definition=definition,
        inputs=original['inputs'],input_sha256=original['input_sha256'],
        input_stat={k:dict(size=Path(v).stat().st_size,mtime_ns=Path(v).stat().st_mtime_ns)
                    for k,v in original['inputs'].items()},
        configs=configs,predecessor=prior,host_available_bytes=available,disk_free_bytes=free,
        prior_failed_setup_cpu_s=0,solver_called=False,joint_reference_read=False,
        dependency_environment=dict(CPATH=os.environ.get('CPATH'),compiler=shutil.which('c++'),
            process_inventory_preflight=True,native_compile_preflight=True)))


def execute(args):
    out = Path(args.output_root)
    attempts = out/'attempts'
    if not (out/'status.json').is_file() and attempts.exists() and any(attempts.iterdir()):
        raise RuntimeError('prior attempts without controller ledger; inspect, never restart')
    prepared = stage.load(out/'preparation.json')
    _,prior = predecessor(prepared['predecessor']['root'],prepared['spec'])
    if prior != prepared['predecessor']:
        raise ValueError('historical predecessor changed since completion preflight')
    stage.execute(args,recipe_loader=recipe)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','execute'))
    parser.add_argument('--config',default=str(ROOT/'configs/planning_value_completion.json'))
    parser.add_argument('--previous-stage')
    parser.add_argument('--output-root',required=True)
    args=parser.parse_args()
    {'prepare':prepare,'execute':execute}[args.action](args)
