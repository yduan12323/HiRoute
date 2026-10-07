"""A single bounded candidate. No trusted bundle or independent acceptance."""
import time
ENTRY = time.monotonic()
import argparse
import hashlib
import importlib.abc
import os
import resource
import stat
import sys

from .lp_jobs import (LPJob, CHILD_AS_BYTES, SOFT_RSS_MIB, MAX_PASSES, LP_SECONDS,
                      STDOUT_BYTES, MODEL_BYTES, FRAME_SCHEMA, STAGES, THREAD_ENV,
                      canonical, decode, digest, require)


class CandidateFence(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == 'timecut5' or name.startswith(('timecut5.', 'validation.reference5')):
            raise ImportError('candidate forbids production/reference implementation ' + name)
        return None


def load_model(job):
    """Hash the exact consumed file and the selected canonical model bytes."""
    fd = os.open(job.model_payloads_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size == job.model_payloads_size_bytes,
                'pinned regular model file size')
        raw = stream.read(job.model_payloads_size_bytes + 1)
    require(len(raw) == job.model_payloads_size_bytes and
            hashlib.sha256(raw).hexdigest() == job.model_payloads_sha256, 'model file SHA mismatch')
    rows = decode(raw)
    require(type(rows) is list and len(rows) == 256, 'fixed 256-model preview')
    row = rows[job.preview_position]
    require(type(row) is dict and type(row.get('selection_position')) is int and
            row['selection_position'] == job.preview_position, 'selected model position')
    model = row['model']
    require(type(model) is dict, 'selected model object')
    model_raw = canonical(model)
    require(len(model_raw) <= MODEL_BYTES and hashlib.sha256(model_raw).hexdigest() ==
            row['model_sha256'] == job.model_sha256, 'selected model SHA mismatch')
    return model


def execute_candidate(job, *, deadline_monotonic, emit, solve=None, budget_factory=None,
                      versions=None):
    """Injection seam for hand-certificate tests; the CLI has no injection option."""
    started = time.monotonic()
    cpu_started = time.process_time()
    stages = []
    budget = None
    versions = versions or dict(python=sys.version.split()[0], numpy='unavailable', scipy='unavailable')

    def metrics():
        return dict(versions=versions, cpu_seconds=time.process_time() - cpu_started,
            wall_seconds=time.monotonic() - started, pass_count=budget.passes if budget else 0,
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)

    def frame(kind, **value):
        emit(dict(schema=FRAME_SCHEMA, job=job.to_dict(), kind=kind, **value))

    def stage(value):
        require(len(stages) < 5 and value['name'] == STAGES[len(stages)], 'candidate stage order')
        frame('stage', stage_index=len(stages), stage=value)
        stages.append(value)

    native = None
    original = None
    announced = False
    try:
        require(time.monotonic() < deadline_monotonic, 'candidate absolute deadline exhausted')
        model = load_model(job)
        if solve is None:
            import numpy
            import scipy
            from validation.suffix5 import solver, vendor_lp
            versions = dict(python=sys.version.split()[0], numpy=numpy.__version__, scipy=scipy.__version__)
            solve, budget_factory = solver.solve_model, solver.SolveBudget
            native, original = vendor_lp, vendor_lp.linprog

            def single_thread(*args, **kwargs):
                options = dict(kwargs.get('options', {}))
                options['threads'] = 1
                kwargs['options'] = options
                return original(*args, **kwargs)
            native.linprog = single_thread
        require(budget_factory is not None, 'candidate budget factory required')
        remaining = min(LP_SECONDS, deadline_monotonic - time.monotonic())
        require(remaining > 0, 'candidate import/startup deadline exhausted')
        budget = budget_factory(max_passes=MAX_PASSES, wall_seconds=remaining, rss_mib=SOFT_RSS_MIB)
        frame('started', metrics=metrics())
        announced = True
        record = solve(model, budget=budget, on_stage=stage)
        budget.check()
        require(time.monotonic() < deadline_monotonic, 'candidate serialization deadline exhausted')
        require(canonical(record['model']) == canonical(model) and
                canonical(record['stages']) == canonical(stages), 'candidate record/stage coverage changed')
        frame('final', status='complete', stage_count=len(stages),
              stage_sha256s=[digest(s) for s in stages], result=record['result'], reason=None, metrics=metrics())
    except Exception as exc:
        # Completed stage frames remain available even if recovery or serialization fails.
        if not announced:
            frame('started', metrics=metrics())
        frame('final', status='unresolved', stage_count=len(stages),
              stage_sha256s=[digest(s) for s in stages], result=None,
              reason=(type(exc).__name__ + ': ' + str(exc))[:4096], metrics=metrics())
    finally:
        if native is not None:
            native.linprog = original


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--cpu', type=int, required=True)
    parser.add_argument('--deadline', type=float, required=True)
    args = parser.parse_args()
    require(len(args.job.encode('utf-8')) <= 16384, 'scalar job argument cap')
    job = LPJob.from_dict(decode(args.job))
    require(args.cpu in os.sched_getaffinity(0), 'candidate CPU outside inherited allowed mask')
    os.sched_setaffinity(0, {args.cpu})
    resource.setrlimit(resource.RLIMIT_AS, (CHILD_AS_BYTES, CHILD_AS_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    require(all(os.environ.get(name) == '1' for name in THREAD_ENV), 'single-thread BLAS environment required')
    require(not any(name == 'timecut5' or name.startswith(('timecut5.', 'validation.reference5'))
                    for name in sys.modules), 'forbidden module imported before candidate fence')
    sys.meta_path.insert(0, CandidateFence())
    require(args.deadline <= ENTRY + LP_SECONDS, 'parent absolute deadline exceeds candidate cap')
    used = 0

    def emit(value):
        nonlocal used
        raw = canonical(value) + b'\n'
        require(used + len(raw) <= STDOUT_BYTES, 'candidate output byte cap exhausted')
        used += len(raw)
        view = memoryview(raw)
        while view:
            written = os.write(sys.stdout.fileno(), view)
            view = view[written:]

    execute_candidate(job, deadline_monotonic=args.deadline, emit=emit)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
