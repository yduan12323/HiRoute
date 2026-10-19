"""Fixed-denominator synthetic process harness, not a holdout execution adapter.

Uses reviewed process-tree cleanup/phase supervision without importing DEV run.py.
No caller-supplied commands, input paths, solver callbacks, or authorization flags.
"""
from pathlib import Path
import secrets
import sys
import time
from experiments.mechanism_recovery_v1.supervisor import run, Limits, PhaseBudget, _atomic
from .contract import BoundSyntheticInput, admit, canonical, digest, validate_plan

SCENARIOS = {'success','no_seed','timeout','crash', 'startup_delay','drift','wrong_key'}


def ledger_for(declaration):
    validate_plan(declaration)
    stages = []
    methods = []
    for d in declaration['domains']:
        def stage(op, method=None):
            stages.append(dict(id=f"{d['id']}:{op}:{method or '-'}", domain=d['id'],
                operation=op, method=method, status='PENDING'))
        stage('prepare')
        for method in d['method_order']:
            stage('search', method); stage('replay', method)
            methods.append(dict(domain=d['id'], method=method, status='PENDING'))
        if d['ref']: stage('ref')
    return dict(status='MOCK_RUNNING', evidence='MOCK_ONLY', declaration_sha256=digest(declaration),
        denominator=declaration['denominator'], stages=stages, methods=methods,
        budget_accounting='worst_case_reservation_not_measured_CPU', reserved_cpu_seconds=0,
        aggregate_memory_hard_limit=False, aggregate_RSS_stop_implemented=False)


def run_mock_plan(declaration, output, *, scenarios=None, cpu_budget=1000, wall_budget=1000):
    """Exercise synthetic slots at CPU3, 1-second CPU / 5-second startup-inclusive wall each.

    Full-domain worst-case reservation includes a conservative parent CPU allowance.
    These are harness ceilings, NOT the 40 CPU-hour final protocol implementation.
    """
    from .contract import positive
    validate_plan(declaration)
    positive(cpu_budget, 'cpu_budget'); positive(wall_budget, 'wall_budget')
    scenarios = dict(scenarios or {})
    ledger = ledger_for(declaration)
    ids = {s['id'] for s in ledger['stages']}
    if not set(scenarios) <= ids or not set(scenarios.values()) <= SCENARIOS:
        raise ValueError('Unknown predetermined mock slot/scenario')
    output = Path(output); output.mkdir(exist_ok=False, parents=True)
    started = time.monotonic()
    def save(): _atomic(output/'ledger.json', ledger)
    def block(rows, reason):
        for row in rows:
            if row['status'] in ('PENDING', 'SEARCH_ADMITTED'): row['status'] = reason
    def stop(reason):
        ledger['status'] = reason
        block(ledger['stages'], 'BLOCKED_' + reason)
        block(ledger['methods'], 'BLOCKED_' + reason)
        save()
        return ledger
    save()
    for domain in declaration['domains']:
        rows = [s for s in ledger['stages'] if s['domain'] == domain['id']]
        methods = [s for s in ledger['methods'] if s['domain'] == domain['id']]
        # RLIMIT_CPU hard ceiling is soft+1 per process; this mock cannot fork.
        reserve = len(rows)*3 + 1
        if (ledger['reserved_cpu_seconds'] + reserve > cpu_budget or
            time.monotonic() - started + len(rows)*7 > wall_budget):
            return stop('BUDGET_BLOCKED')
        ledger['reserved_cpu_seconds'] += reserve; save()
        bound = BoundSyntheticInput.fixture(domain); common = None
        for row in rows:
            method_row = next((m for m in methods if m['method'] == row['method']), None)
            if row['operation'] != 'prepare' and common is None:
                row['status'] = 'BLOCKED_NO_COMMON_SEED'; save(); continue
            if row['operation'] == 'replay' and method_row['status'] != 'SEARCH_ADMITTED':
                row['status'] = 'BLOCKED_SEARCH_FAILED'; save(); continue
            request = dict(domain=domain, operation=row['operation'], method=row['method'],
                common=common, scenario=scenarios.get(row['id'],'success'))
            argv = [sys.executable, '-m', 'experiments.m6h_manifest_v1.mock_worker', canonical(request).decode()]
            phase = None
            if row['operation'] == 'search':
                phase = PhaseBudget(seconds=.2, identity=dict(nonce=secrets.token_hex(16),
                    input_sha256=bound.sha256, common_sha256=digest(common),
                    method=row['method'], declaration_sha256=digest(declaration)))
            try:
                receipt = run(argv, output_dir=output/f"slot-{ledger['stages'].index(row):03d}",
                    cwd=Path(__file__).resolve().parents[2],
                    limits=Limits(wall_seconds=5, cpu_seconds=1, address_space_bytes=256*1024**2, cpu=3),
                    phase_budget=phase)
            except Exception as exc:
                row.update(status='UNKNOWN', error=str(exc))
                return stop('LAUNCH_OR_CLEANUP_UNKNOWN')
            row['receipt'] = receipt
            if receipt.get('cleanup_verified') is not True:
                row['status'] = 'UNKNOWN'; return stop('CLEANUP_UNKNOWN')
            if receipt['status'] != 'SUCCESS':
                row['status'] = receipt['status']
                if method_row: method_row['status'] = receipt['status']
                if row['operation'] == 'prepare': block(methods, 'BLOCKED_PREPARATION_FAILED')
                if receipt['status'] == 'UNKNOWN': return stop('INTEGRITY_UNKNOWN')
                save(); continue
            try:
                value = admit(receipt['worker_receipt']['result'], bound,
                    row['operation'], row['method'], common)
                if row['operation'] == 'search' and receipt.get('phase_entered_monotonic') is None:
                    raise ValueError('Missing search phase')
            except (ValueError, TypeError, KeyError) as exc:
                row.update(status='INTEGRITY_FAILED', error=str(exc)); return stop('INTEGRITY_FAILED')
            row['status'] = value['outcome']
            if row['operation'] == 'prepare':
                if value['outcome'] == 'common_feasible_seed': common = value
                else: block(methods, 'BLOCKED_NO_COMMON_SEED')
            elif row['operation'] == 'search':
                method_row['status'] = 'SEARCH_ADMITTED' if value['outcome'] == 'exact_attained' else value['outcome']
            elif row['operation'] == 'replay': method_row['status'] = 'MOCK_CERTIFIED'
            save()
    ledger['status'] = 'MOCK_FINISHED_WITH_RETAINED_OUTCOMES'; save()
    return ledger
