"""Observe three pinned window-.051 first-feasibility calls; never accept a regime.

The native candidate and existing exact recovery run unchanged. Telemetry samples
are bounded independently of backend progress, and may never stop recovery.
"""
import time
ENTRY = time.monotonic()
import argparse
from collections import deque
from contextlib import contextmanager
from fractions import Fraction as F
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import sys

from .plan import canonical, digest

INPUT_BYTES = 15593
INPUT_SHA = '82569746f926588db80ffb8f2170336c367772149283d8792ec7053df790e3e7'
ARCHIVE_SHA = '35c23a251ac67f3a502bdad044e1ca2d1e5703d2f09879996f14a317430a7c23'
MODEL_PINS = {
    411229: 'd7907fccf77af692c12e6461ea3efc3c833d9069480210f463df7bbcad43de1d',
    411238: '42cb0dbdd68141bb4c34ad4dce4c8ab834fc3ed13829bdecd54df7188346d1ad',
    412024: '0751c5b99298931f9eacdca9182ac8ef7ac2e912191e1b4d0cb2369fcf65008c'}
DESCRIPTOR_PINS = {
    411229: '49203c83669a252942c3cb8d6f77de116f5465fe384518c6349185adef9a9c77',
    411238: '9800c6a2b73916fe94d8a0e707f074666a2674f025104276975634c27aad2cd3',
    412024: '6f9825bafee920bd477d9497138817081e596ff6ccfc280b29a2d0f92c64d5be'}
SOURCE_PINS = {
    'validation/suffix5/vendor_lp.py': 'e613e2c5c416625e22eccdf305f8e9401f315abdae74521b777b33aaa2e39c92',
    'validation/suffix5/solver.py': '57baeaffca06d142bf0e1f1ddb8d07a927b517653e6473ac13f9e0af5d2f6a4b',
    'validation/suffix5/basis_exchange.py': 'ceefcecaf7a1dc313b3cf4caa293c8e06e4ce23cbc2fadf5eb80ba1aa1a88626',
    'experiments/time_cut_v2/recorded_real/candidate_memory.py': '05a2b31e9ae03edbdc16431666fe0f682a77e1fb06f2b7b5fa955872c893deca'}
MAX_OUTPUT = 4 * 1024**2
MAX_PEAK = 768 * 1024**2
SAMPLE_END = 16
DENIALS = dict(acceptance=False, query_complete=False, G8=False,
              full_population_complete=False, certificate_stages_accepted=0)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def plain(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    return value


def error(exc):
    return type(exc).__name__ + ': ' + str(exc)


def selected_models(path):
    """Parse the very bytes authenticated, rejecting ambiguous JSON identities."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size == INPUT_BYTES,
                'pinned regular extracted-model input required')
        raw = stream.read(INPUT_BYTES + 1)
    require(len(raw) == INPUT_BYTES and hashlib.sha256(raw).hexdigest() == INPUT_SHA,
            'consumed model input hash/size changed')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    rows = json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'nonfinite JSON'))
    require(type(rows) is list and len(rows) == len(MODEL_PINS), 'three fixed models required')
    chosen = {}
    for row in rows:
        require(type(row) is dict and set(row) == {'ordinal', 'canonical_model_sha256', 'descriptor', 'model'},
                'extracted-model fields changed')
        ordinal = row['ordinal']
        require(type(ordinal) is int and ordinal in MODEL_PINS and ordinal not in chosen,
                'missing, duplicate or unexpected model ordinal')
        require(row['canonical_model_sha256'] == MODEL_PINS[ordinal] and
                digest(row['model']) == MODEL_PINS[ordinal], 'canonical model pin changed')
        descriptor = row['descriptor']
        require(type(descriptor) is dict and type(descriptor.get('ordinal')) is int and
                descriptor['ordinal'] == ordinal and digest(descriptor) == DESCRIPTOR_PINS[ordinal],
                'descriptor pin changed')
        chosen[ordinal] = row
    require(set(chosen) == set(MODEL_PINS), 'three fixed model identities required')
    return chosen


@contextmanager
def deadline(at):
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    previous = signal.getsignal(signal.SIGALRM)
    prior_deadline = getattr(previous, '_window_diagnostic_deadline', None)
    require(previous_timer == (0.0, 0.0) or
            (prior_deadline is not None and previous_timer[1] == 0 and at <= prior_deadline),
            'foreign or looser nested diagnostic timer')
    def expired(*_):
        raise TimeoutError('fixed window-face diagnostic deadline')
    expired._window_diagnostic_deadline = at
    try:
        signal.signal(signal.SIGALRM, expired)
        remaining = at - time.monotonic()
        require(remaining > 0, 'diagnostic deadline expired')
        signal.setitimer(signal.ITIMER_REAL, remaining)
        yield
        require(time.monotonic() < at, 'diagnostic exceeded its deadline')
    finally:
        # A pending deadline signal must not interrupt cleanup or be delivered
        # to the restored default handler. Consume it while blocked, then raise.
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        pending = False
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
            pending = signal.SIGALRM in signal.sigpending()
            if pending:
                signal.sigwait({signal.SIGALRM})
            signal.signal(signal.SIGALRM, previous)
            if prior_deadline is not None and previous_timer[0] > 0:
                signal.setitimer(signal.ITIMER_REAL, max(0.000001, prior_deadline-time.monotonic()))
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        if pending:
            raise TimeoutError('fixed window-face diagnostic deadline during timer cleanup')


class Samples:
    """A complete stream hash/count and bounded disjoint first/last observations."""
    def __init__(self):
        self.count = 0
        self.first = []
        self.last = deque(maxlen=SAMPLE_END)
        self.hasher = hashlib.sha256()

    def add(self, entry):
        self.count += 1
        entry = dict(entry, observation=self.count)
        self.hasher.update(canonical(entry) + b'\n')
        if len(self.first) < SAMPLE_END:
            self.first.append(entry)
        else:
            self.last.append(entry)

    def report(self):
        retained = len(self.first) + len(self.last)
        return dict(total=self.count, retained=retained, omitted=self.count-retained,
                    truncated=self.count > retained, stream_sha256=self.hasher.hexdigest(),
                    stream_encoding='canonical-json-lines-v1', first=self.first, last=list(self.last))


def matrix_hash(rows, rhs, seed):
    """Hash incrementally, without retaining a second coefficient graph."""
    h = hashlib.sha256()
    for label, values in [('rows', rows), ('rhs', (rhs,)), ('seed', (seed,))]:
        h.update(label.encode() + b'\n')
        for row in values:
            h.update(canonical([str(v) for v in row]) + b'\n')
    return h.hexdigest()


def violations(A, b, eq, x, dot):
    return dict(violated_inequalities=[[i, str(dot(row, x)-rhs)]
                    for i, (row, rhs) in enumerate(zip(A, b)) if dot(row, x) > rhs],
                violated_equalities=[[i, str(dot(row, x)-rhs)]
                    for i, (row, rhs) in enumerate(eq) if dot(row, x) != rhs])


def inspect_task(task, backend, exchange, native, remaining_seconds):
    """Injectable fake-native harness; hooks observe but never retry or truncate work."""
    originals = (backend.linprog, backend.solve_rational_equalities,
                 backend.verify_certificate, exchange.recover_exchange)
    old_native, old_eq, old_check, old_exchange = originals
    eliminations, checks = Samples(), Samples()
    passes, exchanges = [], []
    report = dict(native_passes=passes, exchange_entries=exchanges,
                  outcome='unresolved', candidate_certificate=None, **DENIALS)
    c = tuple(map(F, task['c']))
    A = [tuple(map(F, r)) for r in task['A']]
    b = list(map(F, task['b']))
    eq = [(tuple(map(F, r)), F(v)) for r, v in task['equalities']]
    row_lookup = {}
    for label, pairs in (('a', zip(A, b)), ('e', eq)):
        for index, (row, rhs) in enumerate(pairs):
            row_lookup.setdefault((tuple(row), rhs), []).append(f'{label}:{index}')
    active = []
    attempted_passes = 0

    def one_pass(*args, **kwargs):
        nonlocal attempted_passes
        attempted_passes += 1
        require(not passes, 'second native pass / Phase-I prohibited')
        require(kwargs.get('method') == 'highs' and kwargs.get('bounds') == [(None, None)]*len(c),
                'native method/bounds changed')
        require(kwargs.get('options') == {'primal_feasibility_tolerance': 1e-9,
                                         'dual_feasibility_tolerance': 1e-9}, 'native tolerances/options changed')
        seconds = remaining_seconds()
        require(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 30,
                'invalid remaining native budget')
        options = dict(kwargs['options'], time_limit=seconds)
        entry = dict(started=True, options=options)
        passes.append(entry)
        result = native(*args, **dict(kwargs, options=options))
        def number(value):
            if value is None:
                return None
            v = float(value)
            return v if math.isfinite(v) else str(v)
        def array(value):
            return None if value is None else [number(v) for v in value]
        entry.update(status=int(result.status), success=bool(result.success), message=str(result.message),
                     x=array(result.x), fun=number(result.fun))
        for name in ('ineqlin', 'eqlin', 'lower', 'upper'):
            block = getattr(result, name, None)
            entry[name] = {key: array(getattr(block, key, None)) for key in ('marginals', 'residual')}
        require(result.status != 2, 'Phase-I prohibited after native infeasibility hint')
        return result

    def eliminate(rows, rhs, seed):
        caller = sys._getframe(1)
        identities = [row_lookup.get((tuple(row), value), []) for row, value in zip(rows, rhs)]
        state = caller.f_locals
        is_stationarity = any(rows is state.get(name) for name in ('stationarity', 'transpose'))
        is_primal = (not is_stationarity and len(seed) == len(c) and
                     len(rows) == len(rhs) and all(identities))
        entry = dict(matrix_rhs_seed_sha256=matrix_hash(rows, rhs, seed),
                     rows=len(rows), variables=len(seed), phase='legacy',
                     kind='stationarity' if is_stationarity else 'primal' if is_primal else 'unmatched',
                     task_row_identities=identities if is_primal else None)
        if active and caller.f_code is old_exchange.__code__:
            state = caller.f_locals
            entry['phase'] = 'exchange'
            current = active[-1]
            if 'rest' in state:
                current.update(basis=list(state['basis']), rest=list(state['rest']))
            trial = state.get('trials', 0)
            current['trials_observed'] = max(current['trials_observed'], trial)
            entry.update(trial=trial, proposed=list(state.get('proposed', [])),
                         position=state.get('position'), entering=state.get('entering'))
        del caller
        try:
            result = old_eq(rows, rhs, seed)
            entry.update(result=plain(result[0]), rank=result[1])
            if is_primal:
                entry.update(violations(A, b, eq, result[0], backend.dot))
                entry['classification'] = ('rank_deficient' if result[1] < len(c)
                    else 'primal_infeasible' if entry['violated_inequalities'] or entry['violated_equalities']
                    else 'primal_feasible')
            else:
                entry['classification'] = 'stationarity_result' if is_stationarity else 'unmatched_result'
            return result
        except BaseException as exc:
            entry['error'] = error(exc)
            entry['classification'] = ('inconsistent_equalities'
                if str(exc) == 'Inconsistent candidate active equalities' else 'interrupted_or_failed')
            raise
        finally:
            eliminations.add(entry)

    def verify(c_, A_, b_, eq_, certificate):
        entry = dict(certificate=plain(certificate))
        try:
            result = old_check(c_, A_, b_, eq_, certificate)
            entry['verified'] = True
            return result
        except BaseException as exc:
            entry.update(verified=False, error=error(exc))
            entry.update(violations(A_, b_, eq_, certificate['x'], backend.dot))
            raise
        finally:
            checks.add(entry)

    def recover(c_, A_, b_, eq_, candidate, selected_rows):
        entry = dict(selected_rows=list(selected_rows), seed=plain(candidate['x']),
                     candidate=plain(candidate), trials_observed=0,
                     configured_trial_cap=exchange.MAX_EXCHANGE_TRIALS)
        exchanges.append(entry)
        active.append(entry)
        try:
            result = old_exchange(c_, A_, b_, eq_, candidate, selected_rows)
            entry['outcome'] = 'exact_candidate_returned'
            return result
        except BaseException as exc:
            entry['error'] = error(exc)
            entry['outcome'] = ('trial_cap_exhausted' if str(exc) == 'Exact basis-exchange trial cap exhausted'
                                else 'neighborhood_exhausted' if str(exc) == 'Exact basis-exchange neighborhood did not certify the candidate'
                                else 'interrupted_or_failed')
            raise
        finally:
            active.pop()

    try:
        backend.linprog, backend.solve_rational_equalities = one_pass, eliminate
        backend.verify_certificate, exchange.recover_exchange = verify, recover
        cert = backend.exact_lp(c, A, b, eq)
        report.update(candidate_certificate=plain(cert), outcome='exact_candidate_returned')
    except Exception as exc:
        report['error'] = error(exc)
    finally:
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        try:
            (backend.linprog, backend.solve_rational_equalities,
             backend.verify_certificate, exchange.recover_exchange) = originals
            report.update(eliminations=eliminations.report(), exact_checks=checks.report(),
                          native_pass_attempts=attempted_passes)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
    return report


def source_pins(root, modules=()):
    observed = {}
    for name, sha in SOURCE_PINS.items():
        path = root / name
        require(not path.is_symlink(), 'symlinked diagnostic source')
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == sha, 'pinned diagnostic source changed: ' + name)
        observed[name] = dict(sha256=sha, size_bytes=len(raw))
    for module in modules:
        path = Path(module.__file__).resolve()
        require(path.is_relative_to(root), 'loaded source outside pinned checkout')
        name = path.relative_to(root).as_posix()
        require(name in observed and hashlib.sha256(path.read_bytes()).hexdigest() == observed[name]['sha256'],
                'loaded diagnostic source changed')
    return observed


def checked_peak(reader):
    peak = reader()
    require(type(peak) is int and 0 < peak <= MAX_PEAK, 'candidate own-exec VmHWM cap or invalid observation')
    return peak


def write_report(path, report):
    raw = canonical(report) + b'\n'
    require(len(raw) <= MAX_OUTPUT, 'bounded diagnostic output')
    with Path(path).open('xb') as stream:
        stream.write(raw)
    return dict(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))


def _main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu', type=int, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists() and not args.output.is_symlink(), 'fresh exclusive output required')
    require(args.cpu in os.sched_getaffinity(0), 'diagnostic CPU unavailable')
    os.sched_setaffinity(0, {args.cpu})
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    require(all(os.environ.get(k) == '1' for k in
                ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')),
            'single-thread native environment required')
    root = Path(__file__).resolve().parents[3]
    report = dict(schema='hiroute-window051-face-diagnostic-v1',
                  input=dict(sha256=INPUT_SHA, size_bytes=INPUT_BYTES),
                  original_archive_sha256=ARCHIVE_SHA, model_pins=MODEL_PINS,
                  descriptor_pins=DESCRIPTOR_PINS, input_verified=False, models=[], **DENIALS)
    modules = ()
    reader = None
    try:
        with deadline(ENTRY + 105):
            report['sources_before'] = source_pins(root)
            models = selected_models(args.models)
            report['input_verified'] = True
            from . import candidate_memory
            from validation.suffix5 import solver, vendor_lp, basis_exchange
            import numpy, scipy
            modules = (solver, vendor_lp, basis_exchange, candidate_memory)
            reader = candidate_memory.peak_rss_bytes
            report['loaded_sources_before'] = source_pins(root, modules)
            report['versions'] = dict(numpy=numpy.__version__, scipy=scipy.__version__)
            report['memory_source'] = candidate_memory.SOURCE
            # Restore the enclosing total timer before entering each model's timer.
        for ordinal in sorted(models):
            at = min(ENTRY + 105, time.monotonic() + 30)
            with deadline(at):
                before = checked_peak(reader)
                task = solver.strict_task(models[ordinal]['model'])
                require(len(models[ordinal]['model']['lp']['variables']) == 8 and
                        len(models[ordinal]['model']['lp']['rows']) == 28,
                        'fixed model dimensions changed')
                row = dict(ordinal=ordinal, model_sha256=MODEL_PINS[ordinal],
                           descriptor_sha256=DESCRIPTOR_PINS[ordinal], task=task,
                           task_sha256=digest(task), peak_before_bytes=before)
                report['models'].append(row)
                row['diagnostic'] = inspect_task(task, vendor_lp, basis_exchange, vendor_lp.linprog,
                                                lambda: at-time.monotonic())
                row['peak_after_bytes'] = checked_peak(reader)
                require(len(row['diagnostic']['native_passes']) == 1 and
                        row['diagnostic']['native_pass_attempts'] == 1,
                        'exactly one native feasibility pass required')
        report['status'] = 'diagnostic_complete'
    except Exception as exc:
        report.update(status='diagnostic_incomplete', error=error(exc))
    try:
        report['sources_after'] = source_pins(root, modules)
        if reader is not None:
            report['peak_rss_bytes'] = checked_peak(reader)
        require(time.monotonic() - ENTRY <= 105, 'diagnostic total deadline exceeded')
    except Exception as exc:
        report.update(status='diagnostic_incomplete', final_verification_error=error(exc))
    report['wall_seconds'] = time.monotonic()-ENTRY
    result = write_report(args.output, report)
    print(json.dumps(dict(status=report['status'], output=result, **DENIALS)))
    return 0 if report['status'] == 'diagnostic_complete' else 1


def main(argv=None):
    # Includes imports, validation, all observations, final pins and report writing.
    with deadline(ENTRY + 105):
        return _main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
