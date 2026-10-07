"""Bounded one-shot candidate processes; their output grants no acceptance.

The collector never imports a solver/checker. Its thread owns pipes and child
reaping so a main-thread exact-check callback cannot delay candidate deadlines.
All children remain in the caller's process group, owned by the outer guard.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import selectors
import subprocess
import sys
import threading
import time
from .candidate_memory import SOURCE as RSS_SOURCE

POSITIONS = (0, 63, 64, 159, 160, 223, 224, 255)
STAGES = ('feasibility', 'primary', 'primary_attainment', 'secondary', 'secondary_attainment')
LP_SECONDS = 30.0
MAX_PASSES = 12
CHILD_AS_BYTES = 1024**3
SOFT_RSS_MIB = 768
STDOUT_BYTES = 2 * 1024**2
STDERR_BYTES = 64 * 1024
MODEL_FILE_BYTES = 64 * 1024**2
MODEL_BYTES = 1024**2
THREAD_ENV = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
              'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS',
              'GOTO_NUM_THREADS', 'OMP_THREAD_LIMIT')
SCHEMA = 'hiroute-lp-calibration-job-v1'
FRAME_SCHEMA = 'hiroute-lp-calibration-frame-v1'
ROOT = Path(__file__).resolve().parents[3]


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('nonfinite JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def hash_id(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


@dataclass(frozen=True)
class LPJob:
    calibration_index: int
    preview_position: int
    model_sha256: str
    context_sha256: str
    model_payloads_path: str
    model_payloads_sha256: str
    model_payloads_size_bytes: int

    def __post_init__(self):
        require(type(self.calibration_index) is int and 0 <= self.calibration_index < 8,
                'calibration index')
        require(type(self.preview_position) is int and
                self.preview_position == POSITIONS[self.calibration_index], 'fixed preview position')
        require(all(hash_id(value) for value in (self.model_sha256, self.context_sha256,
                    self.model_payloads_sha256)), 'job SHA binding')
        require(type(self.model_payloads_size_bytes) is int and
                0 < self.model_payloads_size_bytes <= MODEL_FILE_BYTES, 'model file byte cap')
        require(type(self.model_payloads_path) is str and
                Path(self.model_payloads_path).is_absolute(), 'absolute pinned model file')
        require(len(canonical(self._payload())) <= 8192, 'scalar job byte cap')

    def _payload(self):
        return dict(schema=SCHEMA, **vars(self), limits=dict(max_passes=MAX_PASSES,
            wall_seconds=LP_SECONDS, as_bytes=CHILD_AS_BYTES, rss_mib=SOFT_RSS_MIB,
            stdout_bytes=STDOUT_BYTES, stderr_bytes=STDERR_BYTES, highs_threads=1,rss_source=RSS_SOURCE))

    @property
    def job_sha256(self):
        return digest(self._payload())

    def to_dict(self):
        return dict(self._payload(), job_sha256=self.job_sha256)

    @classmethod
    def from_dict(cls, value):
        require(type(value) is dict, 'job object')
        job = cls(**{key: value[key] for key in cls.__dataclass_fields__})
        require(canonical(value) == canonical(job.to_dict()), 'complete canonical job identity')
        return job


def make_jobs(*, model_payloads_path, model_payloads_sha256,
              model_payloads_size_bytes, model_sha256s, context_sha256):
    hashes = tuple(model_sha256s)
    require(len(hashes) == 8, 'exactly eight model hashes')
    return tuple(LPJob(i, p, hashes[i], context_sha256,
        str(Path(model_payloads_path).absolute()), model_payloads_sha256,
        model_payloads_size_bytes) for i, p in enumerate(POSITIONS))


def _metrics(value):
    require(type(value) is dict and set(value) == {'versions', 'cpu_seconds',
            'wall_seconds', 'pass_count', 'peak_rss_bytes','rss_source','rusage_peak_rss_bytes'}, 'candidate metrics fields')
    require(type(value['versions']) is dict and set(value['versions']) == {'python', 'numpy', 'scipy'}
            and all(type(v) is str and 0 < len(v) <= 128 for v in value['versions'].values()),
            'candidate runtime versions')
    for key in ('cpu_seconds', 'wall_seconds'):
        require(type(value[key]) in (float, int) and math.isfinite(value[key]) and value[key] >= 0,
                'candidate timing')
    require(type(value['pass_count']) is int and 0 <= value['pass_count'] <= MAX_PASSES,
            'candidate pass count')
    require(type(value['peak_rss_bytes']) is int and value['peak_rss_bytes'] >= 0, 'candidate RSS')
    require(value['rss_source']==RSS_SOURCE and type(value['rusage_peak_rss_bytes']) is int and
            value['rusage_peak_rss_bytes']>=0,'candidate RSS measurement provenance')


class FrameReader:
    """Strict NDJSON framing. Retain complete prefix stages after any failure."""
    def __init__(self, job):
        self.job = job
        self.pending = bytearray()
        self.stages = []
        self.started = None
        self.final = None
        self.error = None

    def feed(self, raw):
        if self.error is not None:
            return
        self.pending.extend(raw)
        try:
            while b'\n' in self.pending:
                line, _, rest = self.pending.partition(b'\n')
                self.pending = bytearray(rest)
                self._frame(decode(line))
        except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
            self.error = 'malformed candidate output: ' + str(exc)[:512]

    def _frame(self, frame):
        require(type(frame) is dict and frame.get('schema') == FRAME_SCHEMA, 'frame schema')
        require(canonical(frame.get('job')) == canonical(self.job.to_dict()), 'response job identity mismatch')
        require(self.final is None, 'extra frame after final')
        kind = frame.get('kind')
        base = {'schema', 'job', 'kind'}
        if kind == 'started':
            require(set(frame) == base | {'metrics'} and self.started is None and not self.stages,
                    'duplicate or misplaced started frame')
            _metrics(frame['metrics'])
            self.started = frame['metrics']
        elif kind == 'stage':
            require(self.started is not None and set(frame) == base | {'stage_index', 'stage'},
                    'stage framing')
            i = frame['stage_index']
            require(type(i) is int and i == len(self.stages) and i < len(STAGES),
                    'missing extra or duplicate stage')
            stage = frame['stage']
            require(type(stage) is dict and set(stage) == {'name', 'task', 'certificate'} and
                    stage['name'] == STAGES[i], 'stage name/order')
            require(type(stage['task']) is dict and set(stage['task']) == {'c', 'A', 'b', 'equalities'}
                    and type(stage['certificate']) is dict, 'full task/certificate required')
            self.stages.append(stage)
        elif kind == 'final':
            require(self.started is not None and set(frame) == base | {'status', 'stage_count',
                    'stage_sha256s', 'result', 'reason', 'metrics'}, 'final fields')
            require(type(frame['stage_count']) is int and frame['stage_count'] == len(self.stages)
                    and frame['stage_sha256s'] == [digest(s) for s in self.stages], 'final stage coverage')
            _metrics(frame['metrics'])
            if frame['status'] == 'complete':
                require(frame['reason'] is None and type(frame['result']) is dict, 'complete result')
                counts = {'graph_unreachable': 0, 'closed_infeasible': 1, 'strict_infeasible': 1,
                          'primary_unattained': 3, 'secondary_unattained': 5, 'attained_optimum': 5}
                require(counts.get(frame['result'].get('status')) == len(self.stages),
                        'missing or extra result stages')
            else:
                require(frame['status'] == 'unresolved' and frame['result'] is None and
                        type(frame['reason']) is str and 0 < len(frame['reason']) <= 4096,
                        'unresolved reason')
            self.final = frame
        else:
            raise ValueError('unknown frame kind')

    def finish(self):
        if self.error is None:
            if self.pending:
                self.error = 'truncated candidate frame'
            elif self.final is None:
                self.error = 'missing final candidate frame'
        return self.error


@dataclass
class _Running:
    job: LPJob
    cpu: int
    process: object
    started: float
    deadline: float
    reader: FrameReader
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)
    failure: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    killed: bool = False


def _command(job, cpu, deadline):
    return [sys.executable, '-B', '-m', 'experiments.time_cut_v2.recorded_real.lp_worker',
            '--job', canonical(job.to_dict()).decode('ascii'), '--cpu', str(cpu),
            '--deadline', repr(deadline)]


def _outcome(job, *, reason, slot=None):
    reader = slot.reader if slot else None
    final = reader.final if reader else None
    good = slot is not None and reason is None and final is not None
    status = final['status'] if good else 'unresolved'
    return dict(schema='hiroute-lp-calibration-outcome-v1', job=job.to_dict(),
        status=status, reason=(final['reason'] if good else reason),
        stages=reader.stages if reader else [], result=final['result'] if good else None,
        metrics=(final['metrics'] if final else reader.started) if reader else None,
        stdout_base64=base64.b64encode(slot.stdout if slot else b'').decode('ascii'),
        stderr_base64=base64.b64encode(slot.stderr if slot else b'').decode('ascii'),
        stdout_truncated=slot.stdout_truncated if slot else False,
        stderr_truncated=slot.stderr_truncated if slot else False,
        pid=slot.process.pid if slot else None, cpu=slot.cpu if slot else None,
        returncode=slot.process.returncode if slot else None, child_reaped=slot is not None,
        started_monotonic=slot.started if slot else None,
        deadline_monotonic=slot.deadline if slot else None,
        collected_monotonic=time.monotonic(), acceptance=False)


def _collect(jobs, cpus, deadline, completed, stop):
    active = {}
    pending = list(jobs)
    reported = set()
    collection_error = None
    selector = selectors.DefaultSelector()
    env = os.environ.copy()
    env.update({name: '1' for name in THREAD_ENV})
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    # Resolve our modules from this reviewed checkout, independent of caller cwd.
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + str(ROOT / 'src')

    def publish(value):
        reported.add(value['job']['calibration_index'])
        completed.put(value)

    def fail(slot, reason):
        if slot.failure is None:
            slot.failure = reason
        if slot.process.poll() is None:
            slot.process.kill()
            slot.killed = True

    def read(slot, stream, name):
        target = getattr(slot, name)
        cap = STDOUT_BYTES if name == 'stdout' else STDERR_BYTES
        try:
            raw = os.read(stream.fileno(), min(65536, cap - len(target) + 1))
        except BlockingIOError:
            return False
        if not raw:
            selector.unregister(stream)
            stream.close()
            return False
        available = cap - len(target)
        target.extend(raw[:available])
        if name == 'stdout':
            slot.reader.feed(raw[:available])
            if slot.reader.error:
                fail(slot, slot.reader.error)
        if len(raw) > available:
            setattr(slot, name + '_truncated', True)
            fail(slot, name + ' byte cap exceeded')
        return True

    try:
        while pending or active:
            now = time.monotonic()
            if stop.is_set() or now >= deadline:
                reason = 'candidate collection cancelled' if stop.is_set() else 'caller absolute deadline exhausted'
                for job in pending:
                    publish(_outcome(job, reason=reason))
                pending.clear()
                for slot in active.values():
                    fail(slot, reason)
            for cpu in cpus:
                if not pending or cpu in active or stop.is_set() or time.monotonic() >= deadline:
                    continue
                job = pending.pop(0)
                start = time.monotonic()
                due = min(deadline, start + LP_SECONDS)
                try:
                    process = subprocess.Popen(_command(job, cpu, due), stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=ROOT,
                        bufsize=0, close_fds=True, start_new_session=False)
                except Exception as exc:
                    publish(_outcome(job, reason='candidate launch failed: ' + str(exc)[:512]))
                    continue
                slot = _Running(job, cpu, process, start, due, FrameReader(job))
                active[cpu] = slot
                for name in ('stdout', 'stderr'):
                    stream = getattr(process, name)
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, (slot, name))
            now = time.monotonic()
            for slot in active.values():
                if now >= slot.deadline:
                    fail(slot, 'candidate subprocess deadline exhausted')
            for cpu, slot in list(active.items()):
                if slot.process.poll() is None:
                    continue
                # A dead child cannot add bytes. Drain only bounded ready bytes.
                for name in ('stdout', 'stderr'):
                    stream = getattr(slot.process, name)
                    while not stream.closed and read(slot, stream, name):
                        if getattr(slot, name + '_truncated'):
                            break
                    if not stream.closed:
                        selector.unregister(stream)
                        stream.close()
                slot.process.wait()
                reason = slot.failure or slot.reader.finish()
                if reason is None and slot.process.returncode != 0:
                    reason = 'candidate exited with code ' + str(slot.process.returncode)
                publish(_outcome(slot.job, reason=reason, slot=slot))
                del active[cpu]
            if active:
                timeout = max(0., min(0.02, deadline - time.monotonic(),
                              *(s.deadline - time.monotonic() for s in active.values())))
                for key, _ in selector.select(timeout):
                    slot, name = key.data
                    read(slot, key.fileobj, name)
    except BaseException as exc:
        collection_error = 'candidate collector failed: ' + type(exc).__name__ + ': ' + str(exc)[:512]
    finally:
        for slot in active.values():
            if slot.process.poll() is None:
                slot.process.kill()
        for slot in active.values():
            slot.process.wait()
            for name in ('stdout', 'stderr'):
                getattr(slot.process, name).close()
        selector.close()
        for job in jobs:
            if job.calibration_index not in reported:
                slot = next((s for s in active.values() if s.job == job), None)
                publish(_outcome(job, reason=collection_error or 'candidate collection cancelled', slot=slot))
        completed.put(None)


def run_jobs(jobs, *, cpus, deadline_monotonic, on_result=None, coordinator_cpu=None):
    """Run exactly the frozen eight jobs; callbacks execute on the caller thread.

    Complete means a well-formed candidate transcript only. The caller must
    independently reconstruct tasks, check certificates, and lift witnesses.
    The absolute deadline also covers startup, imports and serialization.
    Optional coordinator_cpu narrows only the calling thread after the collector
    inherits its full CPU mask; that calling-thread narrowing persists on return.
    """
    jobs, cpus = tuple(jobs), tuple(cpus)
    require(len(jobs) == 8 and all(type(j) is LPJob for j in jobs) and
            [j.calibration_index for j in jobs] == list(range(8)), 'fixed eight ordered jobs')
    require(len({(j.context_sha256, j.model_payloads_path, j.model_payloads_sha256,
                   j.model_payloads_size_bytes) for j in jobs}) == 1, 'shared pinned job context')
    require(len(cpus) == 4 and all(type(c) is int and c >= 0 for c in cpus) and
            len(set(cpus)) == 4 and set(cpus) <= os.sched_getaffinity(0), 'four explicit available CPUs')
    require(type(deadline_monotonic) in (int, float) and math.isfinite(deadline_monotonic),
            'finite absolute deadline')
    if coordinator_cpu is not None:
        require(type(coordinator_cpu) is int and coordinator_cpu in os.sched_getaffinity(0)
                and coordinator_cpu not in cpus, 'separate available coordinator CPU')
    completed = queue.Queue(maxsize=10)
    stop = threading.Event()
    collector = threading.Thread(target=_collect,
        args=(jobs, cpus, deadline_monotonic, completed, stop), name='lp-candidate-collector')
    outcomes = {}
    collector.start()
    try:
        # The collector inherited the full mask before this main-thread narrowing.
        if coordinator_cpu is not None:
            os.sched_setaffinity(0, {coordinator_cpu})
        while True:
            value = completed.get()
            if value is None:
                break
            if isinstance(value, BaseException):
                raise value
            index = value['job']['calibration_index']
            require(index not in outcomes, 'duplicate collected job')
            outcomes[index] = value
            if on_result is not None:
                on_result(value)
    finally:
        stop.set()
        collector.join()
    require(set(outcomes) == set(range(8)), 'missing collected job')
    return [outcomes[i] for i in range(8)]
