"""Opt-in bounded search telemetry. No bounds are computed by this observer.

Heartbeat snapshots may lag by interval + scheduling/I/O delay. A killed run's
snapshot is evidence of its last observed stage, never an exact kill-time stack.
"""
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from collections import deque
import json
import os
import threading
import time

_active = ContextVar('exact_search_progress', default=None)


def operation(name):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            observer = _active.get()
            if observer is None:
                return fn(*args, **kwargs)
            started = observer.begin(name)
            try:
                value = fn(*args, **kwargs)
            except BaseException as error:
                observer.end(name, started, type(error).__name__)
                raise
            observer.end(name, started)
            return value
        return wrapped
    return decorate


def solver(fn):
    @wraps(fn)
    def wrapped(*args, progress_hook=None, **kwargs):
        if progress_hook is None:
            return fn(*args, **kwargs)
        with progress_hook:
            return fn(*args, **kwargs)
    return wrapped


def event(kind, **values):
    observer = _active.get()
    if observer is not None:
        observer.event(kind, **values)


class ExactSearchProgress:
    """One run, bounded recent journal, atomic fsynced latest snapshot.

    Failure to write diagnostics is recorded in memory and must not change the
    solver's status, exception, action order, or pruning. Check io_error afterward.
    CPU timings are calling-thread CPU; operation timers are inclusive/nested.
    """
    def __init__(self, output_dir, *, query_sha256, domain_sha256,
                 source_sha256, provider=None, interval=0.25, max_events=64):
        if not isinstance(interval, (int, float)) or not 0.01 <= interval <= 60:
            raise ValueError('interval must be 0.01..60 seconds')
        if type(max_events) is not int or not 2 <= max_events <= 256:
            raise ValueError('max_events must be 2..256')
        for value in (query_sha256, domain_sha256, *source_sha256.values()):
            if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('SHA-256 identities required')
        if any(not isinstance(k,str) or len(k)>256 for k in source_sha256):
            raise ValueError('Source identity names must be at most 256 characters')
        if len(source_sha256) > 128:
            raise ValueError('At most 128 source identities')
        self.path = Path(output_dir)
        self.path.mkdir(parents=True, exist_ok=False)
        self.provider = provider
        self.interval = interval
        self.lock = threading.RLock()
        self.persist_lock = threading.Lock()
        self.stop = threading.Event()
        self.history = deque(maxlen=max_events)
        self.state = dict(schema='hiroute.exact_search_progress.v1',
            query_sha256=query_sha256, domain_sha256=domain_sha256,
            source_sha256=dict(source_sha256), status='not_started',
            active_stack=[], timings={}, counters={}, journal_total=0,
            global_open_lower_bound=None,
            global_open_lower_bound_reason='Layered search has no global OPEN API; local Region queue bounds are not global certificates.',
            exact_optimum_claimed=False, io_error=None, observer_io_wall_ns=0,
            observer_io_cpu_ns=0, observer_io_scope='Persistence only; full hook overhead requires enabled/disabled measurement',
            max_snapshot_bytes=262144, snapshot_interval_seconds=interval,
            snapshot_semantics='Last sampled active stack; not exact timeout stack. Heartbeat may be delayed by GIL-held work or I/O.',
            synchronous_operation_boundaries='Every outermost operation, road_labels and projection_build start/end; other nested stages heartbeat-sampled',
            timer_semantics='inclusive nested wall and calling-thread CPU; do not sum categories')
        self.used = False
        self.first_operation = True

    def metrics(self):
        if self.provider is None:
            return {}
        result = {n:getattr(self.provider,n) for n in ('source_run_count',
            'source_cache_bytes','source_cache_hits','source_cache_evictions',
            'source_cache_skips') if hasattr(self.provider,n)}
        result['selected_pairs'] = len(self.provider.legs)
        return result

    def __enter__(self):
        if self.used or _active.get() is not None:
            raise ValueError('One non-nested solver run per progress observer')
        self.used = True
        self.baseline = self.metrics()
        self.state['entry_provider_metrics'] = self.baseline
        self.state['status'] = 'running'
        self.token = _active.set(self)
        self.event('run_start')
        self.thread_started = False
        try:
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
            self.thread_started = True
        except Exception as error:
            self.state['heartbeat_error'] = type(error).__name__
            self.persist()
        return self

    def __exit__(self, cls, error, tb):
        self.stop.set()
        if self.thread_started:
            self.thread.join()
        self.state.update(status='error' if cls else 'returned',
                          exception_type=cls.__name__ if cls else None)
        self.event('run_error' if cls else 'run_returned')
        _active.reset(self.token)

    def _heartbeat(self):
        while not self.stop.wait(self.interval):
            self.persist()

    def begin(self, name):
        stamp = (time.monotonic_ns(), time.thread_time_ns())
        with self.lock:
            self.state['active_stack'].append(dict(stage=name, start_wall_ns=stamp[0]))
            first = self.first_operation
            self.first_operation = False
        if first or len(self.state['active_stack']) == 1 or name in ('road_labels','projection_build'):
            self.persist()
        return stamp

    def end(self, name, started, error=None):
        wall, cpu = time.monotonic_ns()-started[0], time.thread_time_ns()-started[1]
        with self.lock:
            self.state['active_stack'].pop()
            item = self.state['timings'].setdefault(name, dict(calls=0, wall_ns=0, cpu_ns=0, errors=0))
            item['calls'] += 1; item['wall_ns'] += wall; item['cpu_ns'] += cpu
            item['errors'] += error is not None
            self.state['last_completed_operation'] = dict(stage=name, wall_ns=wall, cpu_ns=cpu, exception_type=error)
            durable = not self.state['active_stack'] or name in ('road_labels','projection_build')
        if durable:
            self.persist()

    def event(self, kind, **values):
        # Fixed scalar call sites only; no PWA pieces, witnesses or full queues.
        with self.lock:
            if kind == 'layer_start':
                self.state['counters']['pending_next_pieces'] = 0
                self.state['last_layer_start'] = dict(wall_ns=time.monotonic_ns(), **values)
            elif kind == 'layer_end':
                self.state['last_layer_end'] = dict(wall_ns=time.monotonic_ns(), **values)
            self.state['counters'].update(values)
            self.state['journal_total'] += 1
            self.history.append(dict(sequence=self.state['journal_total'], event=kind,
                                     wall_ns=time.monotonic_ns(), **values))
        if kind in ('run_start','layer_start','layer_end','run_error','run_returned'):
            self.persist()

    def persist(self):
        started = time.monotonic_ns(), time.thread_time_ns()
        try:
            with self.persist_lock:
                with self.lock:
                    metrics = self.metrics()
                    snapshot = dict(self.state, sampled_wall_ns=time.monotonic_ns(),
                        provider_metrics=metrics,
                        postentry_provider_deltas={k:v-self.baseline[k] for k,v in metrics.items()},
                        recent_events=list(self.history))
                    snapshot = _bounded_value(snapshot)
                    data = json.dumps(snapshot, sort_keys=True).encode()
                    while len(data)>self.state['max_snapshot_bytes'] and snapshot['recent_events']:
                        snapshot['recent_events'].pop(0)
                        snapshot['journal_byte_trimmed'] = True
                        data = json.dumps(snapshot,sort_keys=True).encode()
                    if len(data)>self.state['max_snapshot_bytes']:
                        raise ValueError('Fixed snapshot fields exceed byte cap')
                temp = self.path/'progress.tmp'
                with temp.open('wb') as out:
                    out.write(data); out.flush(); os.fsync(out.fileno())
                os.replace(temp, self.path/'progress.json')
                fd = os.open(self.path, os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
        except Exception as error:
            self.state['io_error'] = type(error).__name__
        finally:
            with self.lock:
                self.state['observer_io_wall_ns'] += time.monotonic_ns()-started[0]
                self.state['observer_io_cpu_ns'] += time.thread_time_ns()-started[1]


def layer(kind, depth, groups, terminal_pieces, attempted, feasible, incumbent):
    observer = _active.get()
    if observer is not None:
        observer.event(kind, depth=depth, frontier_groups=len(groups),
            frontier_pieces=sum(map(len, groups)), terminal_pieces=terminal_pieces,
            attempted=attempted, feasible=feasible,
            incumbent_primary_upper=incumbent)
        if kind == 'layer_start':
            observer.first_operation = True


def generated(count):
    observer = _active.get()
    if observer is not None:
        with observer.lock:
            counters=observer.state['counters']
            counters['generated_advance_pieces']=counters.get('generated_advance_pieces',0)+count


def expanded():
    observer = _active.get()
    if observer is not None:
        with observer.lock:
            counters = observer.state['counters']
            counters['expanded_prefix_groups'] = counters.get('expanded_prefix_groups',0)+1


def enabled():
    return _active.get() is not None


def _bounded_value(value):
    # Only telemetry is abbreviated; rational search values remain untouched.
    if isinstance(value, dict):
        return {str(k):_bounded_value(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [_bounded_value(v) for v in value]
    if value is None or isinstance(value,(bool,float)):
        return value
    if isinstance(value,int) and value.bit_length()<=128:
        return value
    try:
        text = str(value)
    except ValueError:
        return {'unavailable':'integer_string_conversion_limit'}
    if len(text)>4096:
        return {'unavailable':'telemetry_scalar_character_limit','characters':len(text)}
    return text
