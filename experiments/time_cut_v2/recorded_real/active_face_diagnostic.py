"""Two frozen first-feasibility candidate passes, diagnostic only.

The existing task builder, native options and exact recovery remain unchanged.
Hooks only retain their inputs/outputs; a second native pass for either model
is prohibited. This is not a candidate retry or a regime acceptance command.
"""
import time
ENTRY = time.monotonic()
import argparse
from contextlib import contextmanager
from fractions import Fraction
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import signal
import stat

ARCHIVE_SHA = 'e7371f1ec32492ff05a05907b52261d9d10ab20112be9222f5aad1d3eb8360cc'
ARCHIVE_BYTES = 756356
MODEL_PINS = {687940: '881b4cb7e681938fa88323567a569c4f05451b14824d6e6eb33042139d6ba7c5',
              687941: '2bdf894e31c7567faa61352163b7a47e7813a300a6afd5ee20e627de9d870246'}
SOURCE_PINS = {'validation/suffix5/vendor_lp.py': 'c60a93ee484f381565f312b38b9ec9ae4e53147efa40b184d8b4a32a24e2900b',
               'validation/suffix5/solver.py': '57baeaffca06d142bf0e1f1ddb8d07a927b517653e6473ac13f9e0af5d2f6a4b'}
MAX_OUTPUT = 1024**2


def require(ok, text):
    if not ok:
        raise ValueError(text)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def plain(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    return value


def selected_models(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size == ARCHIVE_BYTES, 'pinned regular pilot archive required')
        raw = stream.read(ARCHIVE_BYTES + 1)
    require(len(raw) == ARCHIVE_BYTES and hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA,
            'consumed pilot archive hash/size changed')
    chosen = {}
    total = 0
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        while True:
            line = stream.readline(8*1024**2 + 1)
            if not line:
                break
            total += len(line)
            require(len(line) <= 8*1024**2 and total <= 16*1024**2, 'bounded archive decode')
            row = json.loads(line)
            if row.get('kind') != 'unresolved_model':
                continue
            ordinal = row['descriptor']['ordinal']
            if ordinal not in MODEL_PINS:
                continue
            require(type(ordinal) is int and ordinal not in chosen, 'duplicate frozen model ordinal')
            model = row['candidate']['job']['model']
            require(hashlib.sha256(canonical(model)).hexdigest() == MODEL_PINS[ordinal], 'frozen model bytes changed')
            chosen[ordinal] = model
    require(set(chosen) == set(MODEL_PINS), 'both original unresolved models required')
    return chosen


@contextmanager
def deadline(at):
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'nested diagnostic timer')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise TimeoutError('fixed active-face diagnostic deadline')
    signal.signal(signal.SIGALRM, expired)
    try:
        require(time.monotonic() < at, 'diagnostic deadline expired')
        signal.setitimer(signal.ITIMER_REAL, at-time.monotonic())
        yield
        require(time.monotonic() < at, 'diagnostic exceeded its deadline')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def inspect_task(task, backend, native):
    """Source-preserving instrumentation; injectable tiny backend for tests."""
    original_eq, original_check = backend.solve_rational_equalities, backend.verify_certificate
    original_native = backend.linprog
    passes = []
    eliminations = []
    checks = []
    report = dict(native_passes=passes, eliminations=eliminations, exact_checks=checks,
                  candidate_certificate=None, outcome='unresolved', acceptance=False)
    def one_pass(*args, **kwargs):
        require(not passes, 'second native pass prohibited for fixed diagnostic')
        require(kwargs.get('method') == 'highs' and kwargs.get('bounds') == [(None, None)]*len(task['c']),
                'native method/bounds changed')
        require(kwargs.get('options') == {'primal_feasibility_tolerance': 1e-9,
                                        'dual_feasibility_tolerance': 1e-9}, 'native tolerance settings changed')
        options = dict(kwargs['options'], threads=1, time_limit=25.0)
        kwargs = dict(kwargs, options=options)
        passes.append(dict(started=True, options=options))
        result = native(*args, **kwargs)
        def array(value):
            return None if value is None else [float(v) for v in value]
        passes[-1].update(status=int(result.status), success=bool(result.success), message=str(result.message),
                         x=array(result.x), fun=None if result.fun is None else float(result.fun),
                         inequality_marginals=array(result.ineqlin.marginals),
                         inequality_residuals=array(result.ineqlin.residual),
                         equality_marginals=array(result.eqlin.marginals), equality_residuals=array(result.eqlin.residual))
        return result
    def eliminate(rows, rhs, seed):
        require(len(eliminations) < 64, 'bounded recovery elimination observations')
        entry = dict(rows=plain(rows), rhs=plain(rhs), seed=plain(seed))
        eliminations.append(entry)
        try:
            result = original_eq(rows, rhs, seed)
            entry.update(result=plain(result[0]), rank=result[1])
            return result
        except Exception as exc:
            entry['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
    def verify(c, A, b, eq, certificate):
        require(len(checks) < 64, 'bounded exact-check observations')
        entry = dict(certificate=plain(certificate))
        checks.append(entry)
        try:
            result = original_check(c, A, b, eq, certificate)
            entry['verified'] = True
            return result
        except Exception as exc:
            entry.update(verified=False, error=type(exc).__name__ + ': ' + str(exc))
            x = certificate['x']
            entry['violated_inequalities'] = [[i, str(backend.dot(row, x)-rhs)]
                for i, (row, rhs) in enumerate(zip(A, b)) if backend.dot(row, x) > rhs]
            raise
    backend.linprog = one_pass
    backend.solve_rational_equalities = eliminate
    backend.verify_certificate = verify
    try:
        cert = backend.exact_lp(tuple(map(Fraction, task['c'])), [tuple(map(Fraction, r)) for r in task['A']],
            list(map(Fraction, task['b'])), [(tuple(map(Fraction, r)), Fraction(v)) for r, v in task['equalities']])
        report.update(candidate_certificate=plain(cert), outcome='exact_candidate_returned')
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        backend.linprog = original_native
        backend.solve_rational_equalities = original_eq
        backend.verify_certificate = original_check
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cpu', type=int, required=True)
    args = p.parse_args()
    require(not args.output.exists(), 'fresh diagnostic output required')
    require(args.cpu in os.sched_getaffinity(0), 'diagnostic CPU unavailable')
    os.sched_setaffinity(0, {args.cpu})
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    require(all(os.environ.get(k) == '1' for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')),
            'single-thread native environment required')
    root = Path(__file__).resolve().parents[3]
    for name, sha in SOURCE_PINS.items():
        require(hashlib.sha256((root/name).read_bytes()).hexdigest() == sha, 'unchanged candidate source required')
    from .candidate_memory import peak_rss_bytes
    report = dict(schema='hiroute-two-active-face-diagnostic-v1', archive_sha256=ARCHIVE_SHA,
                  source_pins=SOURCE_PINS, models=[], acceptance=False, full_population_complete=False)
    try:
        models = selected_models(args.archive)
        from validation.suffix5 import solver, vendor_lp
        import numpy, scipy
        for module in (solver, vendor_lp):
            path = Path(module.__file__).resolve()
            name = path.relative_to(root).as_posix()
            require(name in SOURCE_PINS and hashlib.sha256(path.read_bytes()).hexdigest() == SOURCE_PINS[name],
                    'loaded candidate source differs from pinned checkout')
        report['versions'] = dict(numpy=numpy.__version__, scipy=scipy.__version__)
        for ordinal in sorted(models):
            require(peak_rss_bytes() <= 768*1024**2, 'candidate own-exec peak cap')
            task = solver.strict_task(models[ordinal])
            row = dict(ordinal=ordinal, model_sha256=MODEL_PINS[ordinal], task=task,
                       task_sha256=hashlib.sha256(canonical(task)).hexdigest())
            report['models'].append(row)
            with deadline(min(ENTRY+75, time.monotonic()+30)):
                row['diagnostic'] = inspect_task(task, vendor_lp, vendor_lp.linprog)
            row['peak_rss_bytes'] = peak_rss_bytes()
            require(row['peak_rss_bytes'] <= 768*1024**2, 'candidate own-exec peak cap')
        report['status'] = 'diagnostic_complete'
    except Exception as exc:
        report.update(status='diagnostic_incomplete', error=type(exc).__name__+': '+str(exc))
    report['wall_seconds'] = time.monotonic()-ENTRY
    report['peak_rss_bytes'] = peak_rss_bytes()
    for name, sha in SOURCE_PINS.items():
        require(hashlib.sha256((root/name).read_bytes()).hexdigest() == sha, 'candidate source changed during diagnostic')
    raw = canonical(report)+b'\n'
    require(len(raw) <= MAX_OUTPUT, 'bounded diagnostic output')
    with args.output.open('xb') as stream:
        stream.write(raw)
    print(json.dumps(dict(status=report['status'], sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), acceptance=False)))
    return 0 if report['status'] == 'diagnostic_complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
