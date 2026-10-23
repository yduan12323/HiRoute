"""One shared sequential budget for both clean builds and optional bridge."""
import fcntl
import json
import os
from pathlib import Path
import time
import uuid
from .common import canonical
from experiments.m6h_manifest_v1.supervisor import Limits, run

CPU_CAP = 8 * 3600
WALL_CAP = 12 * 3600


def totals(entries):
    starts = {e['invocation_id'] for e in entries if e['kind'] == 'start'}
    ends = {e['invocation_id'] for e in entries if e['kind'] == 'end'}
    if any(e.get('cleanup_verified') is not True for e in entries if e['kind']=='end'):
        raise RuntimeError('Prior cleanup unverified; no continuation permitted')
    if starts != ends:
        raise RuntimeError('Unsettled prior invocation; inspect/terminate descendants before continuation')
    return (sum(e['cpu_seconds'] for e in entries if e['kind'] == 'end'),
            sum(e['wall_seconds'] for e in entries if e['kind'] == 'end'))


def execute(argv, *, budget_root, output_dir, phase, wall_seconds=120, cpu_seconds=120,
            memory_bytes=4 * 1024**3, preprocessing=False):
    budget_root = Path(budget_root); budget_root.mkdir(parents=True, exist_ok=True)
    with (budget_root/'exclusive.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = budget_root/'phase_ledger.jsonl'
        entries = [json.loads(s) for s in ledger.read_text().splitlines()] if ledger.exists() else []
        cpu, wall = totals(entries)
        if phase in ('prepare','freeze') and sum(e['kind']=='start' and e['phase']==phase for e in entries)>=2:
            raise RuntimeError('At most two raw preprocessing/freeze attempts in this round')
        if cpu + cpu_seconds > CPU_CAP or wall + wall_seconds > WALL_CAP:
            raise RuntimeError('M5-E2E aggregate reservation exceeds remaining budget')
        invocation = uuid.uuid4().hex
        def append(value):
            with ledger.open('ab') as f:
                f.write(canonical(value)+b'\n'); f.flush(); os.fsync(f.fileno())
        append(dict(kind='start', invocation_id=invocation, phase=phase, argv=argv,
                    cpu_reserved=cpu_seconds, wall_reserved=wall_seconds, timestamp=time.time()))
        started = time.monotonic(); parent_started = time.process_time()
        try:
            receipt = run(argv, output_dir=output_dir,
                limits=Limits(wall_seconds=wall_seconds, cpu_seconds=cpu_seconds,
                    address_space_bytes=memory_bytes, cpu=min(os.sched_getaffinity(0)),
                    file_output_bytes=(24 if preprocessing else 2)*1024**3,
                    max_output_entries=10000, max_processes=16),
                tree_rss_stop_bytes=memory_bytes, available_stop_bytes=10*1024**3,
                prelaunch_available_bytes=10*1024**3+memory_bytes,
                tree_cpu_seconds=cpu_seconds, global_cpu_remaining=CPU_CAP-cpu,
                global_wall_remaining=WALL_CAP-wall, owned_temp=True,
                extra_env={'PYTHONPATH':'', 'PYTHONNOUSERSITE':'1'})
        except BaseException as exc:
            # No numerical success claim; conservative reservation retained when
            # supervisor did not provide final cleanup/accounting receipt.
            append(dict(kind='end', invocation_id=invocation, phase=phase,
                        cpu_seconds=cpu_seconds, wall_seconds=max(wall_seconds,time.monotonic()-started),
                        measured_cpu_seconds=None, charge_kind='conservative_reservation',
                        cleanup_verified=False, error=type(exc).__name__+': '+str(exc)))
            raise
        measured = receipt['accounted_owned_cpu_seconds']
        append(dict(kind='end', invocation_id=invocation, phase=phase,
                    cpu_seconds=measured, measured_cpu_seconds=measured,
                    wall_seconds=receipt['wall_seconds'], charge_kind='outer_owned_tree',
                    nested_inclusive_not_added=True, cleanup_verified=receipt['cleanup_verified'],
                    receipt=str(Path(output_dir)/'receipt.json'), status=receipt['status']))
        if not receipt['cleanup_verified']:
            raise RuntimeError('Worker cleanup unverified; stop entire suite')
        return receipt
