"""Installed, separately supervised candidate verification; fresh outputs only."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .io import load, sha
from .verify import canonical


def write_new(path, value):
    with Path(path).open('xb') as stream:
        stream.write(canonical(value) + b'\n')
        stream.flush(); os.fsync(stream.fileno())


def supervise(args):
    import psutil
    import resource
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (args.wall_s, args.cpu_s, args.memory_bytes)):
        raise ValueError('positive finite verification limits required')
    if args.host_headroom_bytes < 0:
        raise ValueError('nonnegative host headroom required')
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / 'admission.json', dict(bundle=str(Path(args.bundle).resolve()), artifact_root=str(Path(args.artifact_root).resolve()),
        wall_s=args.wall_s, cpu_s=args.cpu_s, memory_bytes=args.memory_bytes, host_headroom_bytes=args.host_headroom_bytes))
    start = time.monotonic()
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    before_cpu = usage.ru_utime + usage.ru_stime
    reason, child, peak_cpu, peak_rss = None, None, 0., 0
    code = None
    env = dict(os.environ, **{k: '1' for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')})
    try:
        if psutil.virtual_memory().available < args.host_headroom_bytes:
            raise RuntimeError('host headroom blocked')
        argv = [sys.executable, '-m', 'hiroute_compare.cli', '_verify', '--bundle', str(Path(args.bundle).resolve()),
                '--artifact-root', str(Path(args.artifact_root).resolve()), '--output', str(out),
                '--wall-s', str(args.wall_s), '--cpu-s', str(args.cpu_s), '--memory-bytes', str(args.memory_bytes)]
        with (out / 'worker.stdout').open('xb') as stdout, (out / 'worker.stderr').open('xb') as stderr:
            child = subprocess.Popen(argv, start_new_session=True, env=env, cwd=out, stdout=stdout, stderr=stderr)
            write_new(out / 'started.json', dict(pid=child.pid, controller_pid=os.getpid(), argv=argv))
            while child.poll() is None:
                try:
                    process = psutil.Process(child.pid)
                    group = [process, *process.children(recursive=True)]
                    cpu = sum(p.cpu_times().user + p.cpu_times().system for p in group)
                    rss = sum(p.memory_info().rss for p in group)
                    peak_cpu, peak_rss = max(peak_cpu, cpu), max(peak_rss, rss)
                except psutil.NoSuchProcess:
                    continue
                if time.monotonic() - start >= args.wall_s: reason = 'time_limit'
                elif peak_cpu >= args.cpu_s: reason = 'cpu_limit'
                elif peak_rss > args.memory_bytes: reason = 'memory_limit'
                elif psutil.virtual_memory().available < args.host_headroom_bytes: reason = 'host_headroom_limit'
                if reason:
                    break
                time.sleep(.05)
            if child.poll() is not None:
                code = child.returncode
    except Exception as exc:
        reason = repr(exc)
    finally:
        if child is not None:
            # Always clean the group, including descendants left by an exited leader.
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait()
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    measured_cpu = usage.ru_utime + usage.ru_stime - before_cpu
    if reason is None and measured_cpu > args.cpu_s:
        reason = 'cpu_limit'
    body = out / 'body-result.json'
    result = None
    try:
        result = load(body) if body.is_file() else None
        if result is not None and result.get('status') == 'COMPLETE':
            witness = out / 'verification/separate-witness.verified.json'
            saved = load(witness)
            if (sha(witness) != result['verified_witness_file_sha256'] or
                    canonical(saved['result']) != canonical(result['comparison']) or
                    hashlib.sha256(canonical(saved['result'])).hexdigest() != result['verified_payload_sha256'] or
                    saved['result_sha256'] != result['verified_payload_sha256'] or
                    saved['requires_successful_consumer_terminal'] is not True):
                raise ValueError('terminal witness receipt mismatch')
    except (ValueError, OSError, KeyError, TypeError) as exc:
        reason = repr(exc)
    if reason is None and (code != 0 or result is None or result.get('status') != 'COMPLETE'):
        reason = 'worker did not complete verification'
    if reason is None and time.monotonic() - start >= args.wall_s:
        reason = 'time_limit'
    terminal = dict(schema='hiroute.compare_terminal.v1', status='COMPLETE' if reason is None else 'UNKNOWN',
                    reason=reason, returncode=code, elapsed_s=time.monotonic() - start,
                    sampled_cpu_peak_s=peak_cpu, sampled_rss_peak_bytes=peak_rss,
                    waited_child_cpu_s=measured_cpu,
                    body_sha256=sha(body) if body.is_file() else None, original_run_status='UNKNOWN',
                    original_run_completed_in_budget=False, optimality_certified=False,
                    scope='Independent feasible improvement; inspect body and witness receipts together')
    write_new(out / 'terminal.json', terminal)
    print(json.dumps(terminal, sort_keys=True))
    return 0 if reason is None else 75


def main(argv=None):
    p = argparse.ArgumentParser(prog='hiroute-compare')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('verify', '_verify'):
        parser = sub.add_parser(name)
        parser.add_argument('--bundle', required=True)
        parser.add_argument('--artifact-root', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--wall-s', type=float, default=120)
        parser.add_argument('--cpu-s', type=float, default=120)
        parser.add_argument('--memory-bytes', type=int, default=8 * 1024**3)
        parser.add_argument('--host-headroom-bytes', type=int, default=2 * 1024**3)
    args = p.parse_args(argv)
    try:
        if args.command == 'verify':
            return supervise(args)
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(args.cpu_s), math.ceil(args.cpu_s) + 1))
        resource.setrlimit(resource.RLIMIT_AS, (args.memory_bytes, args.memory_bytes))
        from .verify import verify_bundle
        result = verify_bundle(args.bundle, args.artifact_root, args.output, args.wall_s)
        write_new(Path(args.output) / 'body-result.json', result)
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        print('hiroute-compare: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
