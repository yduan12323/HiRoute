"""Four-credit persistent candidate transport. Candidate output is never acceptance.

Only the calling thread iterates input and checks results. A collector thread owns
all pipes, external deadlines, and reaping, even while that caller is blocked.
No numerical results are cached and no complete population is retained.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import math
import os
import queue
import selectors
import subprocess
import sys
import threading
import time
import uuid

from .lp_jobs import (CHILD_AS_BYTES, SOFT_RSS_MIB, MAX_PASSES, LP_SECONDS,
    STDOUT_BYTES, STDERR_BYTES, MODEL_BYTES, THREAD_ENV, ROOT, RSS_SOURCE,
    FRAME_SCHEMA as CANDIDATE_FRAME_SCHEMA, FrameReader, canonical, decode,
    digest, hash_id, require)

SCHEMA = 'hiroute-lp-stream-job-v1'
FRAME_SCHEMA = 'hiroute-lp-stream-frame-v1'
REQUEST_SCHEMA = 'hiroute-lp-stream-request-v1'
INPUT_FRAME_BYTES = MODEL_BYTES + 65536
CONTEXT_BYTES = 16384


def limits():
    return dict(max_passes=MAX_PASSES, wall_seconds=LP_SECONDS,
        as_bytes=CHILD_AS_BYTES, rss_mib=SOFT_RSS_MIB, stdout_bytes=STDOUT_BYTES,
        stderr_bytes=STDERR_BYTES, highs_threads=1, rss_source=RSS_SOURCE)


@dataclass(frozen=True, init=False)
class LPStreamJob:
    """The canonical bytes, including nested model/context values, are immutable."""
    block_id: int
    model_ordinal: int
    model_sha256: str
    _input_bytes: bytes = field(repr=False)
    _model_bytes: bytes = field(repr=False)
    _context_bytes: bytes = field(repr=False)

    def __init__(self, source_context, block_id, model_ordinal, model_sha256, model):
        require(type(source_context) is dict and type(model) is dict, 'context/model objects')
        require(type(block_id) is int and block_id >= 0, 'nonnegative block id')
        require(type(model_ordinal) is int and model_ordinal >= 0, 'nonnegative model ordinal')
        context_raw, model_raw = canonical(source_context), canonical(model)
        require(len(context_raw) <= CONTEXT_BYTES, 'source context byte cap')
        require(len(model_raw) <= MODEL_BYTES, 'model byte cap')
        require(hash_id(model_sha256) and hashlib.sha256(model_raw).hexdigest() == model_sha256,
                'model SHA mismatch')
        raw = canonical(dict(schema=SCHEMA, source_context=source_context, block_id=block_id,
            model_ordinal=model_ordinal, model_sha256=model_sha256, model=model, limits=limits()))
        require(len(raw) < INPUT_FRAME_BYTES - 1024, 'job input byte cap')
        for name, value in dict(block_id=block_id, model_ordinal=model_ordinal,
                model_sha256=model_sha256, _input_bytes=raw, _model_bytes=model_raw,
                _context_bytes=context_raw).items():
            object.__setattr__(self, name, value)

    @property
    def source_context(self):
        return decode(self._context_bytes)

    @property
    def model(self):
        return decode(self._model_bytes)

    @property
    def input_bytes(self):
        return self._input_bytes

    @property
    def input_sha256(self):
        return hashlib.sha256(self._input_bytes).hexdigest()

    @property
    def source_context_sha256(self):
        return hashlib.sha256(self._context_bytes).hexdigest()

    def to_dict(self):
        return decode(self._input_bytes)

    def header(self, generation):
        require(type(generation) is str and len(generation) == 32 and
                all(c in '0123456789abcdef' for c in generation), 'worker generation')
        return dict(schema=SCHEMA, generation=generation,
            source_context_sha256=self.source_context_sha256, block_id=self.block_id,
            model_ordinal=self.model_ordinal, model_sha256=self.model_sha256,
            input_sha256=self.input_sha256, limits=decode(self._input_bytes)['limits'])

    @classmethod
    def from_dict(cls, value):
        require(type(value) is dict, 'stream job object')
        job = cls(**{k: value[k] for k in ('source_context', 'block_id', 'model_ordinal',
                                          'model_sha256', 'model')})
        require(canonical(value) == job.input_bytes, 'complete canonical stream job identity')
        return job


class BoundJob:
    """Compact adapter for the unchanged five-stage candidate FrameReader."""
    def __init__(self, job, generation):
        self.header = job.header(generation)

    def to_dict(self):
        return self.header


class StreamFrameReader(FrameReader):
    def __init__(self, job, generation):
        super().__init__(BoundJob(job, generation))
        self.done = False

    def feed(self, raw):
        super().feed(raw)
        if self.error is None and self.done and self.pending:
            self.error = 'trailing data after done candidate frame'

    def _frame(self, frame):
        require(type(frame) is dict and frame.get('schema') == FRAME_SCHEMA, 'stream frame schema')
        require(canonical(frame.get('job')) == canonical(self.job.to_dict()),
                'response job identity mismatch')
        require(not self.done, 'extra frame after done')
        if frame.get('kind') == 'done':
            require(set(frame) == {'schema', 'job', 'kind'} and self.final is not None,
                    'missing final before done')
            self.done = True
        else:
            super()._frame(dict(frame, schema=CANDIDATE_FRAME_SCHEMA))

    def finish(self):
        super().finish()
        if self.error is None and not self.done:
            self.error = 'missing done candidate frame'
        return self.error


def request_bytes(job, generation, deadline):
    # Avoid decoding and copying the frozen model merely to construct its envelope.
    return (b'{"deadline_monotonic":' + canonical(deadline) + b',"generation":' +
        canonical(generation) + b',"job":' + job.input_bytes + b',"schema":' +
        canonical(REQUEST_SCHEMA) + b'}\n')


def _command(cpu, generation):
    return [sys.executable, '-B', '-m', 'experiments.time_cut_v2.recorded_real.lp_stream_worker',
            '--cpu', str(cpu), '--generation', generation]


@dataclass
class _Active:
    job: LPStreamJob
    reader: StreamFrameReader
    started: float
    deadline: float
    request: bytes
    written: int = 0
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    failure: str | None = None
    published: bool = False


@dataclass
class _Slot:
    cpu: int
    process: object = None
    generation: str | None = None
    active: _Active | None = None
    closing: bool = False
    reaped: bool = False
    killed: bool = False


def _outcome(slot, active):
    reader, process = active.reader, slot.process
    final = reader.final
    reason = active.failure or reader.finish()
    good = reason is None and final is not None
    return dict(schema='hiroute-lp-stream-outcome-v1', job=active.job.to_dict(),
        response_identity=active.job.header(slot.generation),
        status=final['status'] if good else 'unresolved',
        reason=final['reason'] if good else reason, stages=reader.stages,
        result=final['result'] if good else None,
        metrics=final['metrics'] if final else reader.started,
        stdout_base64=base64.b64encode(active.stdout).decode('ascii'),
        stderr_base64=base64.b64encode(active.stderr).decode('ascii'),
        stdout_truncated=active.stdout_truncated, stderr_truncated=active.stderr_truncated,
        pid=process.pid if process else None, cpu=slot.cpu, generation=slot.generation,
        returncode=process.returncode if process else None,
        child_reaped=process is not None and process.returncode is not None,
        started_monotonic=active.started, deadline_monotonic=active.deadline,
        collected_monotonic=time.monotonic(), acceptance=False)


def _collect(cpus, deadline, commands, completed, stop, finished, report):
    slots = [_Slot(cpu) for cpu in cpus]
    selector = selectors.DefaultSelector()
    env = os.environ.copy()
    env.update({name: '1' for name in THREAD_ENV})
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + str(ROOT / 'src')
    shutting_down = False
    shutdown_due = deadline

    def error(reason):
        report['protocol_error_count'] += 1
        if len(report['protocol_errors']) < 16:
            report['protocol_errors'].append(reason[:512])

    def close_pipe(stream):
        if stream is None or stream.closed:
            return
        try:
            selector.unregister(stream)
        except KeyError:
            pass
        stream.close()

    def kill(slot, reason):
        if slot.active is not None and not slot.active.published and slot.active.failure is None:
            slot.active.failure = reason
        if slot.process is not None and slot.process.poll() is None and not slot.killed:
            slot.process.kill()
            slot.killed = True

    def read(slot, name):
        stream = getattr(slot.process, name)
        if stream.closed:
            return False
        active = slot.active
        target = getattr(active, name) if active else None
        cap = STDOUT_BYTES if name == 'stdout' else STDERR_BYTES
        available = cap - len(target) if target is not None else 0
        try:
            raw = os.read(stream.fileno(), min(65536, available + 1))
        except BlockingIOError:
            return False
        if not raw:
            close_pipe(stream)
            return False
        if active is None:
            error('unsolicited ' + name + ' from idle worker')
            kill(slot, 'unsolicited worker output')
            close_pipe(stream)
            return False
        target.extend(raw[:available])
        if name == 'stdout':
            active.reader.feed(raw[:available])
            if active.reader.error:
                if active.failure is None:
                    error(active.reader.error)
                kill(slot, active.reader.error)
        if len(raw) > available:
            setattr(active, name + '_truncated', True)
            if active.failure is None:
                error(name + ' byte cap exceeded')
            kill(slot, name + ' byte cap exceeded')
            close_pipe(stream)
            return False
        return True

    def drain(slot):
        for name in ('stdout', 'stderr'):
            while read(slot, name):
                pass

    def reap(slot):
        process = slot.process
        if process is None or process.poll() is None:
            return False
        if slot.reaped:
            return True
        drain(slot)
        process.wait()
        for name in ('stdin', 'stdout', 'stderr'):
            close_pipe(getattr(process, name))
        report['reaped_processes'] += 1
        slot.reaped = True
        active = slot.active
        if active is not None and not active.published:
            active.failure = active.failure or active.reader.finish()
            if active.failure is None and (not slot.closing or process.returncode != 0):
                active.failure = 'candidate worker exited before reuse'
        elif process.returncode != 0 and not slot.killed:
            error('idle worker exited with code ' + str(process.returncode))
        return True

    def publish(index, slot):
        active = slot.active
        if active is not None and not active.published:
            active.published = True
            completed.put_nowait((index, _outcome(slot, active)))

    def launch(slot):
        slot.generation = uuid.uuid4().hex
        slot.closing = False
        slot.reaped = slot.killed = False
        slot.process = subprocess.Popen(_command(slot.cpu, slot.generation),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=ROOT, bufsize=0, close_fds=True, start_new_session=False)
        report['spawned_processes'] += 1
        for name in ('stdin', 'stdout', 'stderr'):
            stream = getattr(slot.process, name)
            os.set_blocking(stream.fileno(), False)
            if name != 'stdin':
                selector.register(stream, selectors.EVENT_READ, (slot, name))

    def assign(index, job):
        slot = slots[index]
        require(slot.active is None or slot.active.published, 'one outstanding job per worker')
        if slot.process is not None and slot.process.returncode is None:
            drain(slot)
            if slot.active is not None and slot.active.reader.error:
                kill(slot, slot.active.reader.error)
                slot.process.wait()
            if slot.process.poll() is not None:
                reap(slot)
                slot.process = None
        if slot.process is not None and slot.process.returncode is not None:
            slot.process = None
        started = time.monotonic()
        due = min(deadline, started + LP_SECONDS)
        slot.active = None
        try:
            if started >= deadline:
                slot.generation = uuid.uuid4().hex
            elif slot.process is None:
                launch(slot)
            active = _Active(job, StreamFrameReader(job, slot.generation), started, due,
                             request_bytes(job, slot.generation, due))
            slot.active = active
            if started >= deadline:
                active.failure = 'caller absolute deadline exhausted'
                publish(index, slot)
            else:
                selector.register(slot.process.stdin, selectors.EVENT_WRITE, (slot, 'stdin'))
        except Exception as exc:
            if slot.generation is None:
                slot.generation = uuid.uuid4().hex
            slot.active = _Active(job, StreamFrameReader(job, slot.generation), started, due, b'',
                                 failure='candidate launch failed: ' + str(exc)[:512])
            kill(slot, slot.active.failure)
            if slot.process is not None:
                slot.process.wait()
                reap(slot)
            publish(index, slot)

    try:
        while not stop.is_set():
            while True:
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    break
                if command is None:
                    shutting_down = True
                    shutdown_due = min(deadline, time.monotonic() + 1.)
                    for slot in slots:
                        slot.closing = True
                        if slot.process is not None:
                            close_pipe(slot.process.stdin)
                else:
                    assign(*command)
            now = time.monotonic()
            for index, slot in enumerate(slots):
                if slot.process is None:
                    continue
                active = slot.active
                if now >= deadline or (shutting_down and now >= shutdown_due):
                    if not slot.killed and slot.process.poll() is None and (
                            active is None or active.published):
                        error('idle worker failed to exit within collection/shutdown deadline')
                    kill(slot, 'caller absolute deadline exhausted' if now >= deadline else
                         'candidate shutdown deadline exhausted')
                elif active is not None and not active.published and now >= active.deadline:
                    kill(slot, 'candidate subprocess deadline exhausted')
                dead = reap(slot)
                if active is not None and not active.published:
                    if dead:
                        publish(index, slot)
                    elif (not active.request and active.reader.done and
                          not active.reader.pending and not active.reader.error):
                        # Drain ready data before releasing the result. Late output is still
                        # checked while idle, before reuse, and during the final EOF drain.
                        drain(slot)
                        if active.failure is None:
                            publish(index, slot)
                if dead:
                    slot.process = None
            if shutting_down and all(s.process is None for s in slots):
                break
            for key, _ in selector.select(.01):
                slot, name = key.data
                if name != 'stdin':
                    read(slot, name)
                else:
                    active = slot.active
                    try:
                        n = os.write(key.fileobj.fileno(), active.request[active.written:active.written + 65536])
                        active.written += n
                        if active.written == len(active.request):
                            selector.unregister(key.fileobj)
                            active.request = b''
                    except BlockingIOError:
                        pass
                    except BrokenPipeError:
                        close_pipe(key.fileobj)
                        kill(slot, 'candidate input pipe closed')
    except BaseException as exc:
        report['collector_error'] = type(exc).__name__ + ': ' + str(exc)[:512]
    finally:
        for slot in slots:
            kill(slot, 'candidate collection cancelled')
        for slot in slots:
            if slot.process is not None:
                slot.process.wait()
                reap(slot)
                slot.process = None
        selector.close()
        report['all_processes_reaped'] = report['spawned_processes'] == report['reaped_processes']
        finished.set()


def _iterate(jobs, *, cpus, deadline_monotonic,
             coordinator_cpu=None, max_jobs, max_input_bytes):
    """Consume a strictly increasing (possibly gapped) model stream with four credits.

    The caller must independently check candidate evidence; a complete transcript
    never implies mathematical acceptance. Resuming iteration releases that
    slot's credit. Return only a small summary through StopIteration.value;
    success additionally requires clean worker EOF/reaping after input exhaustion.
    Calling-thread coordinator affinity, when requested, persists after return.
    """
    cpus = tuple(cpus)
    inherited = os.sched_getaffinity(0)
    require(len(cpus) == 4 and all(type(c) is int and c >= 0 for c in cpus) and
            len(set(cpus)) == 4 and set(cpus) <= inherited, 'four explicit available CPUs')
    require(type(deadline_monotonic) in (int, float) and math.isfinite(deadline_monotonic),
            'finite absolute deadline')
    require(type(max_jobs) is int and max_jobs > 0, 'positive maximum jobs')
    require(type(max_input_bytes) is int and max_input_bytes > 0, 'positive maximum input bytes')
    if coordinator_cpu is not None:
        require(type(coordinator_cpu) is int and coordinator_cpu in inherited and
                coordinator_cpu not in cpus, 'separate available coordinator CPU')
    source = iter(jobs)
    commands, completed = queue.Queue(maxsize=5), queue.Queue(maxsize=4)
    stop, finished = threading.Event(), threading.Event()
    report = dict(spawned_processes=0, reaped_processes=0, all_processes_reaped=False,
                  protocol_error_count=0, protocol_errors=[], collector_error=None)
    collector = threading.Thread(target=_collect,
        args=(cpus, deadline_monotonic, commands, completed, stop, finished, report),
        name='lp-stream-collector')
    outstanding = {}
    submitted = terminal = complete = unresolved = total_bytes = 0
    previous = -1
    context_sha = None
    input_exhausted = False
    input_digest = hashlib.sha256()

    def submit(index):
        nonlocal submitted, total_bytes, previous, context_sha, input_exhausted
        if input_exhausted or time.monotonic() >= deadline_monotonic:
            return
        try:
            job = next(source)
        except StopIteration:
            input_exhausted = True
            return
        require(type(job) is LPStreamJob, 'LPStreamJob required')
        require(submitted < max_jobs, 'maximum job count exceeded')
        require(job.model_ordinal > previous, 'strictly increasing model ordinals required')
        require(total_bytes + len(job.input_bytes) <= max_input_bytes, 'maximum input bytes exceeded')
        require(context_sha is None or context_sha == job.source_context_sha256,
                'shared source context required')
        context_sha, previous = job.source_context_sha256, job.model_ordinal
        total_bytes += len(job.input_bytes)
        input_digest.update(job.input_bytes + b'\n')
        submitted += 1
        outstanding[index] = job.input_sha256
        commands.put_nowait((index, job))

    collector.start()
    try:
        if coordinator_cpu is not None:
            os.sched_setaffinity(0, {coordinator_cpu})
        for index in range(4):
            submit(index)
        while outstanding:
            try:
                index, value = completed.get(timeout=.05)
            except queue.Empty:
                require(not finished.is_set(), 'collector stopped with missing outcomes: ' +
                        str(report['collector_error']))
                continue
            require(index in outstanding and
                    value['response_identity']['input_sha256'] == outstanding[index],
                    'duplicate or foreign collected job')
            terminal += 1
            complete += value['status'] == 'complete'
            unresolved += value['status'] == 'unresolved'
            yield value
            del outstanding[index]
            submit(index)
        commands.put_nowait(None)
        collector.join()
    finally:
        stop.set()
        collector.join()
    accounted = terminal == submitted
    successful = (input_exhausted and accounted and report['all_processes_reaped'] and
                  not report['collector_error'] and not report['protocol_error_count'])
    return dict(schema='hiroute-lp-stream-summary-v1', status='complete' if successful else 'unresolved',
        input_exhausted=input_exhausted, submitted_count=submitted, terminal_count=terminal,
        complete_count=complete, unresolved_count=unresolved, all_submitted_accounted=accounted,
        input_bytes=total_bytes, ordered_input_sha256=input_digest.hexdigest(),
        acceptance=False, **report)


class ResultStream:
    """Closeable iterator; use a with block when writing/checking may fail.

    summary is None until clean exhaustion. A completed row is provisional until
    the final summary confirms EOF, accounting, and reaping without late frames.
    """
    def __init__(self, iterator):
        self._iterator = iterator
        self.summary = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            if self.summary is None:
                self.summary = exc.value
            raise

    def close(self):
        self._iterator.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def stream_results(jobs, *, cpus, deadline_monotonic, coordinator_cpu=None,
                   max_jobs, max_input_bytes):
    """Stream one outcome per model; retain a credit until iteration resumes.

    Always close this iterator (prefer a with block). Read .summary after full
    exhaustion before treating a streamed evidence artifact as complete.
    """
    return ResultStream(_iterate(jobs, cpus=cpus, deadline_monotonic=deadline_monotonic,
        coordinator_cpu=coordinator_cpu, max_jobs=max_jobs, max_input_bytes=max_input_bytes))


def iter_results(jobs, *, cpus, deadline_monotonic, on_result=None,
                 coordinator_cpu=None, max_jobs, max_input_bytes):
    """Callback convenience wrapper; callbacks execute on the calling thread."""
    with stream_results(jobs, cpus=cpus, deadline_monotonic=deadline_monotonic,
            coordinator_cpu=coordinator_cpu, max_jobs=max_jobs,
            max_input_bytes=max_input_bytes) as results:
        for value in results:
            if on_result is not None:
                on_result(value)
        return results.summary
