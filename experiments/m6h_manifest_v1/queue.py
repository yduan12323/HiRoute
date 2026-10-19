"""Fixed-slot serial queue; worker commands and physical admission are separate.

No CLI or bypass of physical root-freeze exists here. The supplied adapter is
trusted frozen source, not a data-selected callback. All rows exist before launch.
"""
from pathlib import Path
from .contract import validate_plan, digest, plan
from .resources import Budget, PHASE_LIMITS
from .runner import ledger_for
from .supervisor import run, Limits, _atomic, _children
import os
import threading


def run_plan(declaration, output, adapter, *, budget=None, executor=run, cpu=0):
    """Execute once, no retry. Test executor injection is not a real launch gate.

    Adapter.command(domain,row,context) returns run kwargs (argv, cwd, optional
    extra_env/phase_budget). Adapter.admit(...) returns status plus common for
    prepare or replay_required for search. It must raise on identity, complete-key,
    attainment or replay contradiction. Admission happens before another launch.
    """
    validate_plan(declaration)
    if executor is run and declaration != plan(6):
        raise ValueError('Real queue requires all six fixed groups; shortage is data-limited')
    if threading.current_thread() is not threading.main_thread() or threading.active_count() != 1:
        raise RuntimeError('Dedicated single-threaded queue required')
    if _children(os.getpid()):
        raise RuntimeError('Queue must own all children and start without children')
    if executor is run and cpu != 0:
        raise ValueError('Real M6-H heavy workers require CPU0')
    if executor is run and budget is None:
        raise ValueError('Real queue requires enclosing budget begun before holdout generation')
    budget = budget or Budget()
    ledger = ledger_for(declaration)
    ledger.update(status='RUNNING', evidence='ADAPTER_ADMITTED', retries=0,
        budget_accounting='dedicated_process_self_plus_reaped_descendants_no_nested_sum',
        aggregate_RSS_stop_implemented=True, aggregate_memory_hard_limit=False,
        global_limits={'cpu_seconds':budget.cpu_seconds,'wall_seconds':budget.wall_seconds},
        accounting_origin={'monotonic':budget.wall_start,'process_cpu_baseline':budget.cpu_start,
                           'scope':'same_process_from_before_first_holdout_generation'},
        domain_reservations=[])
    ledger.pop('reserved_cpu_seconds', None)
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    def save():
        ledger['measured_execution'] = budget.measured()
        _atomic(output/'ledger.json', ledger)
    def block(rows, reason):
        for row in rows:
            if row['status'] in ('PENDING','SEARCH_ADMITTED'):
                row['status'] = 'BLOCKED_' + reason
    def stop(reason):
        ledger['status'] = reason
        block(ledger['stages'],reason); block(ledger['methods'],reason); save()
        return ledger
    save()
    for domain in declaration['domains']:
        rows = [s for s in ledger['stages'] if s['domain'] == domain['id']]
        methods = {m['method']:m for m in ledger['methods'] if m['domain']==domain['id']}
        directory = output/domain['id']
        context = {'common':None, 'search':{}, 'prepare_receipt':None,
                   'domain_directory':str(directory), 'results':{}}
        # Frozen generation failures occupy their original slots. Preflight is
        # source-authenticated adapter work, never a result-based case selector.
        if min(budget.remaining()) <= 0:
            return stop('GLOBAL_BUDGET_EXHAUSTED')
        try:
            hook = getattr(adapter, 'preflight', None)
            preflight = hook(domain, context) if hook is not None else None
            if min(budget.remaining()) <= 0:
                return stop('GLOBAL_BUDGET_EXHAUSTED')
            if preflight is not None:
                if (type(preflight) is not dict or preflight.get('status') != 'FAILED_INPUT'
                    or type(preflight.get('reason_code')) is not str or not preflight['reason_code']):
                    raise ValueError('Malformed input-failure preflight admission')
                digest(preflight)  # Require persistable canonical finite data.
                rows[0].update(status='FAILED_INPUT', admission=preflight)
                block(rows[1:], 'INPUT_FAILED'); block(methods.values(), 'INPUT_FAILED')
                save(); continue
        except Exception as exc:
            rows[0].update(status='INTEGRITY_FAILED', error=str(exc))
            return stop('INTEGRITY_FAILED')
        reservation = budget.reserve_domain(s['operation'] for s in rows)
        ledger['domain_reservations'].append(dict(domain=domain['id'],**reservation)); save()
        if not reservation['admitted']:
            return stop('GLOBAL_BUDGET_BLOCKED')
        directory.mkdir()
        for row in rows:
            operation, method = row['operation'], row['method']
            method_row = methods.get(method)
            if operation != 'prepare' and context['common'] is None:
                row['status']='BLOCKED_NO_COMMON_SEED'; save(); continue
            if operation == 'replay' and not context['search'].get(method,{}).get('replay_required',False):
                row['status']='BLOCKED_SEARCH_FAILED'; save(); continue
            index = domain['method_order'].index(method) if method else None
            name = {'prepare':'prepare','ref':'ref'}.get(operation)
            if name is None: name = ('arm' if operation=='search' else 'verify')+f'-{index:02d}'
            slot_directory = directory/name
            remaining_cpu, remaining_wall = budget.remaining()
            if remaining_cpu <= 0 or remaining_wall <= 0:
                return stop('GLOBAL_BUDGET_EXHAUSTED')
            wall, cpu_seconds = PHASE_LIMITS[operation]
            try:
                command = adapter.command(domain, dict(row), context)
                if set(command)-{'argv','cwd','extra_env','phase_budget'}:
                    raise ValueError('Adapter attempted resource policy override')
                if operation=='search' and (command.get('phase_budget') is None or command['phase_budget'].seconds != 1200):
                    raise ValueError('Search requires frozen 1200-second exact phase')
                remaining_cpu, remaining_wall = budget.remaining()
                if remaining_cpu <= 0 or remaining_wall <= 0:
                    return stop('GLOBAL_BUDGET_EXHAUSTED')
                receipt = executor(**command, output_dir=slot_directory,
                    limits=Limits(wall_seconds=wall,cpu_seconds=cpu_seconds,address_space_bytes=8*1024**3,cpu=cpu),
                    tree_cpu_seconds=cpu_seconds, global_cpu_remaining=remaining_cpu,
                    global_wall_remaining=remaining_wall)
            except MemoryError as exc:
                row.update(status='FAILED_MEMORY_PREFLIGHT',error=str(exc))
                if method_row: method_row['status']=row['status']
                if operation=='prepare': block(methods.values(),'PREPARATION_FAILED')
                save(); continue
            except Exception as exc:
                row.update(status='UNKNOWN',error=str(exc))
                return stop('LAUNCH_OR_CLEANUP_UNKNOWN')
            row['receipt'] = receipt
            if receipt.get('cleanup_verified') is not True:
                row['status']='UNKNOWN'; return stop('CLEANUP_UNKNOWN')
            if receipt.get('reason') in ('global_cpu_timeout','global_wall_timeout'):
                row['status']=receipt['status']; return stop('GLOBAL_BUDGET_EXHAUSTED')
            if receipt.get('reason') in ('worker_failed','supervisor_exception','missing_or_malformed_worker_receipt'):
                row['status']='UNKNOWN'; return stop('UNEXPECTED_WORKER_FAILURE')
            if receipt.get('status') == 'UNKNOWN':
                row['status']='UNKNOWN'; return stop('INTEGRITY_UNKNOWN')
            # Only exact-phase timeouts can carry the adapter's durable incumbent.
            admissible = receipt.get('status')=='SUCCESS' or (operation=='search' and
                receipt.get('status')=='TIMEOUT' and receipt.get('reason')=='phase_timeout')
            if not admissible:
                row['status']=receipt.get('status','UNKNOWN')
                if method_row: method_row['status']=row['status']
                if operation=='prepare': block(methods.values(),'PREPARATION_FAILED')
                save(); continue
            try:
                admitted = adapter.admit(domain, dict(row), context, receipt, slot_directory)
                if not isinstance(admitted,dict) or not isinstance(admitted.get('status'),str):
                    raise ValueError('Missing typed admission')
                if admitted.get('integrity_stop'):
                    raise ValueError('Adapter reported correctness contradiction')
                row['status']=admitted['status']; row['admission']=admitted
                context['results'][row['id']]=admitted
                if operation=='prepare':
                    context['common']=admitted.get('common'); context['prepare_receipt']=receipt
                    if context['common'] is None: block(methods.values(),'NO_COMMON_SEED')
                elif operation=='search':
                    context['search'][method]=dict(admitted,receipt=receipt,directory=str(slot_directory))
                    method_row['status']='SEARCH_ADMITTED' if admitted.get('replay_required') else admitted['status']
                elif operation=='replay': method_row['status']=admitted['status']
            except Exception as exc:
                row.update(status='INTEGRITY_FAILED',error=str(exc)); return stop('INTEGRITY_FAILED')
            save()
    if min(budget.remaining()) <= 0:
        return stop('GLOBAL_BUDGET_EXHAUSTED')
    ledger['status']='FINISHED_WITH_RETAINED_OUTCOMES'; save()
    return ledger
