"""Sequential real DEV pilot using the existing OS supervisor.

Run preflight first. Each query gets a fresh numerical process, one numerical
thread, an independently enforced internal120s deadline, and a guarded cold-load
allowance. Every failure is kept. No automatic extension, holdout or merging.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import sys

from ..data.queries import domain_rows


from .worker import jsonable, atomic, aliases, loaded_query_watchdog, worker, preserve_live_diagnostics
from .workload import _scope, selected_workload, declared_worker_job


def preflight(args):
    from hiroute.exact.scale import validate_scale_input
    from hiroute.runtime import system_mem_available_bytes
    config = json.loads(Path(args.config).read_text())
    manifest = json.loads(Path(args.preflight).read_text())
    if manifest['selection_uses_solver_results'] or manifest['config'] != config:
        raise ValueError('preflight/config mismatch')
    declared = [od['query_id'] for od in config['selection']['ods']]
    actual = [query['query_id'] for query in manifest['queries']]
    if not declared or len(set(declared)) != len(declared) or actual != declared:
        raise ValueError('pilot requires exactly its declared OD in order')
    if config['resources']['numeric_workers'] != 1 or config['resources']['numeric_threads'] != 1:
        raise ValueError('pilot is single numerical worker/thread')
    if not Path(args.graph_tsv).is_file():
        raise ValueError('real graph TSV not prepared')
    unavailable = []
    for query in manifest['queries']:
        for scenario in config['selection']['scenarios']:
            for n in config['selection']['candidate_counts']:
                rows = domain_rows(query,n,scenario,require_full=False)
                if len(rows) > n:
                    raise ValueError('declared candidate domain exceeds requested N')
                if len(rows) != n:
                    unavailable.append(dict(query_id=query['query_id'],scenario=scenario,
                        requested_N=n,available_N=len(rows),status='input_domain_unavailable'))
                    continue
                if (any(not row['capabilities'] for row in rows) or
                        (scenario=='energy_only' and any('C' not in row['capabilities'] for row in rows))):
                    raise ValueError('declared domain contains a scenario-ineligible Site')
                mapping = aliases(query,n,scenario)
                if len(mapping) != n+2 or len(set(mapping.values())) != len(mapping):
                    raise ValueError('candidate/endpoint aliases overlap')
    if sys.platform == 'darwin':
        import psutil
        available = psutil.virtual_memory().available
    else:
        available = system_mem_available_bytes()
    if available < config['resources']['host_headroom_bytes']+512*1024**2:
        raise ValueError('insufficient host memory before pilot')
    print(json.dumps(dict(preflight='passed', queries=len(actual), domain_counts=config['selection']['candidate_counts'],
        host_available_bytes=available, graph_tsv_bytes=Path(args.graph_tsv).stat().st_size,
        input_domain_unavailable=unavailable,solver_called=False), sort_keys=True), flush=True)


def apply_supervisor_outcome(row, supervised, checkpoint_record=None):
    """Merge enforcement/exit status without treating a written file as success."""
    row = dict(row)
    if checkpoint_record is not None:
        verified = checkpoint_record.get('verified')
        if not isinstance(verified,dict) or verified.get('physical_verified') is not True:
            raise ValueError('incumbent checkpoint is not independently physically verified')
        if not isinstance(row.get('witness'),dict) or row['witness'].get('physical_verified') is not True:
            row['feasible_key'] = checkpoint_record['key']
            row['witness'] = verified
        if row.get('feasible_key') is None:
            row['feasible_key'] = checkpoint_record['key']
        if row.get('time_to_first_feasible_s') is None:
            row['time_to_first_feasible_s'] = checkpoint_record['time_to_first_feasible_s']
    outcome = ('time_limit' if supervised.timed_out else
        'memory_limit' if supervised.memory_limited else
        'host_headroom_limit' if supervised.host_headroom_limited else
        'cpu_limit' if supervised.cpu_limited else
        'worker_error' if supervised.returncode not in (None,0) else None)
    if outcome is not None:
        if 'status' in row:
            row['solver_reported_status'] = row['status']
        row.update(status=outcome,mathematical_status='unknown')
        for key in ('key','primary_value','primary_infimum','secondary_infimum'):
            row.pop(key,None)
        if not isinstance(row.get('witness'),dict) or row['witness'].get('physical_verified') is not True:
            row.pop('feasible_key',None)
            row.pop('witness',None)
    if supervised.returncode not in (None,0):
        row['error'] = supervised.stderr.decode(errors='replace')[-3000:]
    row.update(supervisor_total_s=supervised.elapsed_s,
        process_group_peak_rss_bytes=supervised.rss_peak_bytes,
        host_available_min_bytes=supervised.host_available_min_bytes,
        supervisor_cpu_s=supervised.cpu_peak_s)
    return row


def supervised_main(args):
    from hiroute.runtime import run_supervised
    config = json.loads(Path(args.config).read_text())
    preflight(args)
    if args.preflight_only:
        return
    workload = selected_workload(config,args)
    resources = config['resources']
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(out)
    run_dir = out.parent/(out.stem+'-workers')
    run_dir.mkdir()
    total_cpu = args.development_cpu_s
    env = dict(os.environ, **{key:'1' for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS',
        'MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS')})
    # Optional historical adapters are resolved only by an explicitly declared
    # old configuration. Installed N64 research configs reject these options.
    if config.get('planning_policy') or config.get('cost_diagnostic'):
        import importlib.util
        names = (['planning_value_policy'] if config.get('planning_policy') else []) + (['d04_cost_diagnostic'] if config.get('cost_diagnostic') else [])
        paths = []
        for name in names:
            spec = importlib.util.find_spec(name)
            if spec is None or spec.origin is None:
                raise ValueError('historical adapter unavailable: ' + name)
            paths.append(str(Path(spec.origin).parent))
        env['PYTHONPATH'] = os.pathsep.join([*dict.fromkeys(paths), *([env['PYTHONPATH']] if env.get('PYTHONPATH') else [])])
    for job in workload:
        n,query,scenario,method = (job[key] for key in ('N','query_id','scenario','method'))
        identity = f'{query}-N{n}-{scenario}-{method}'+('-no-bound' if not job['use_bound'] else '')
        result_path = run_dir/(identity+'.json')
        row = dict(query_id=query,N=n,scenario=scenario,method=method,
            bound_enabled=job['use_bound'],solve_limit_s=job['solve_limit_s'],workload_mode=job['mode'])
        # Reserve the complete maximum worker CPU allowance, including cold
        # loading, before starting. Never spend the final budget on a partial run.
        reserve_cpu = args.cold_load_allowance_s+job['solve_limit_s']
        if total_cpu+reserve_cpu > resources['new_solve_and_finite_ref_cpu_budget_s']:
            row.update(status='not_run_cpu_budget',mathematical_status='unknown')
        else:
            argv = [sys.executable,'-m','hiroute.execution.worker','--worker',
                '--config',str(Path(args.config).resolve()),'--preflight',str(Path(args.preflight).resolve()),
                '--graph-tsv',str(Path(args.graph_tsv).resolve()),'--native-cache',str(Path(args.native_cache).resolve()),
                '--query',query,'--n',str(n),'--scenario',scenario,'--method',method,'--output',str(result_path),
                '--solve-limit-seconds',str(job['solve_limit_s'])]
            if not job['use_bound']:
                argv.append('--no-bound')
            if job['mode']=='diagnostic':
                argv.append('--diagnostic')
            elif job['mode']=='ablation':
                argv.append('--ablation')
            receipt_dir = getattr(args,'receipt_directory',None)
            receipt = Path(receipt_dir)/identity if receipt_dir else None
            supervised = run_supervised(argv,timeout_s=reserve_cpu,cpu_limit_s=reserve_cpu,
                cpu_budget_guard=getattr(args,'cpu_budget_guard',None),
                memory_limit_bytes=args.process_memory_gib*1024**3,
                host_min_available_bytes=resources['host_headroom_bytes'],
                memory_poll_s=.1,cwd=str(out.parent.resolve()),env=env,
                receipt_path=None if receipt is None else str(receipt)+'.supervisor.json',
                run_identity=getattr(args,'run_identity',None))
            if receipt is not None:
                # Keep terminal evidence before merging/serializing the row.
                value = asdict(supervised)
                for name in ('stdout','stderr'):
                    value[name] = value[name].decode(errors='replace')
                atomic(str(receipt)+'.outcome.json',value)
            if result_path.exists():
                row.update(json.loads(result_path.read_text()))
            else:
                row.update(status='worker_error',mathematical_status='unknown')
            checkpoint = result_path.with_suffix('.incumbent.json')
            saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
            row = apply_supervisor_outcome(row,supervised,saved)
            # Conservative fresh budget: all observed worker CPU, including
            # cold index load; the separate map TSV export is not charged here.
            total_cpu += max(row.get('worker_cpu_s',0),supervised.cpu_peak_s)
        row['new_total_cpu_s'] = total_cpu
        if getattr(args,'receipt_directory',None):
            atomic(Path(args.receipt_directory)/(identity+'.row.json'),row)
        with out.open('a') as stream:
            stream.write(json.dumps(jsonable(row),sort_keys=True)+'\n')
        print(identity,row['status'],row.get('query_loaded_total_s'),flush=True)


def main(args):
    with ExitStack() as stack:
        if sys.platform == 'darwin':
            from .platform import mac_monitors
            import psutil
            psutil.pids()  # permission preflight before numerical work
            mac_monitors(stack)
        supervised_main(args)


def cli():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('config','preflight','graph-tsv','native-cache','output'):
        p.add_argument('--'+key,required=True)
    p.add_argument('--worker',action='store_true')
    p.add_argument('--preflight-only',action='store_true')
    p.add_argument('--query');p.add_argument('--n',type=int)
    p.add_argument('--scenario');p.add_argument('--method')
    p.add_argument('--domains')
    p.add_argument('--queries');p.add_argument('--scenarios')
    p.add_argument('--methods')
    p.add_argument('--no-bound',action='store_true')
    p.add_argument('--diagnostic',action='store_true')
    p.add_argument('--ablation',action='store_true')
    p.add_argument('--solve-limit-seconds',type=float)
    p.add_argument('--development-cpu-s',type=float,default=0)
    p.add_argument('--cold-load-allowance-s',type=int,default=180)
    p.add_argument('--process-memory-gib',type=int,default=16)
    a=p.parse_args()
    if a.worker and json.loads(Path(a.config).read_text()).get('cost_diagnostic'):
        from d04_cost_diagnostic import instrumented_worker
        instrumented_worker(a,worker)
    else:
        worker(a) if a.worker else main(a)


if __name__ == "__main__":
    cli()
