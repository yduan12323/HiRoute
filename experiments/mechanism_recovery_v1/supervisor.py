"""Bounded Linux experiment worker; per-process limits, never cgroup accounting.

Call from a dedicated, single-threaded process with no existing children. Do not
start unrelated children during run(). Artifacts must stay under HIROUTE_OUTPUT_DIR.
The worker writes status SUCCESS, COMPLETED, or FEASIBLE to HIROUTE_WORKER_RECEIPT.
Supervisor SUCCESS means physical completion only, not mathematical verification.
Sampled tree RSS/file totals are observations, not hard aggregate limits. RLIMIT_AS,
CPU and FSIZE apply independently to every inheriting process. No hostile-code
sandbox or protection against deliberate limit changes is claimed.
"""
from dataclasses import asdict, dataclass
import ctypes
import errno
import json
import math
import os
from pathlib import Path
import resource
import selectors
import signal
import stat
import subprocess
import threading
import time

THREAD_ENV = {k: '1' for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
    'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS',
    'BLIS_NUM_THREADS', 'ARROW_NUM_THREADS')}
SCHEMA = 'hiroute.mechanism_recovery.supervisor.v1'


class SupervisorCancellation(RuntimeError):
    """Signal cancellation that selectors must never interpret as EINTR."""


@dataclass(frozen=True)
class Limits:
    wall_seconds: float
    cpu_seconds: int
    address_space_bytes: int
    cpu: int
    stdout_bytes: int = 1024 * 1024
    stderr_bytes: int = 1024 * 1024
    file_output_bytes: int = 16 * 1024 * 1024
    cleanup_seconds: float = 3.0
    poll_seconds: float = 0.02
    max_processes: int = 128
    max_output_entries: int = 1024

    def validate(self):
        for name in ('wall_seconds', 'cleanup_seconds', 'poll_seconds'):
            x = getattr(self, name)
            if type(x) not in (int, float) or not math.isfinite(x) or x <= 0:
                raise ValueError('Invalid ' + name)
        if self.cleanup_seconds > 30 or self.poll_seconds > 1:
            raise ValueError('Unbounded polling/cleanup interval')
        for name in ('cpu_seconds', 'address_space_bytes', 'stdout_bytes',
                     'stderr_bytes', 'file_output_bytes', 'max_processes', 'max_output_entries'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError('Invalid ' + name)
        if type(self.cpu) is not int or self.cpu not in os.sched_getaffinity(0):
            raise ValueError('Unavailable CPU affinity')
        for which, needed in ((resource.RLIMIT_CPU, self.cpu_seconds + 1),
                              (resource.RLIMIT_AS, self.address_space_bytes),
                              (resource.RLIMIT_FSIZE, self.file_output_bytes)):
            hard = resource.getrlimit(which)[1]
            if hard != resource.RLIM_INFINITY and hard < needed:
                raise ValueError('Inherited hard resource limit is too restrictive')


PHASE_SCHEMA = 'hiroute.mechanism_recovery.phase_entry.v1'


@dataclass(frozen=True)
class PhaseBudget:
    """One exact-entry phase; identity must bind nonce and immutable inputs."""
    seconds: float
    identity: dict
    marker_name: str = 'search_entry.json'

    def validate(self):
        if (type(self.seconds) not in (int, float) or not math.isfinite(self.seconds)
                or self.seconds <= 0):
            raise ValueError('Invalid phase duration')
        if (not isinstance(self.identity, dict) or not self.identity.get('nonce')
                or any(not isinstance(k, str) or not isinstance(v, str) or not v
                       for k, v in self.identity.items())):
            raise ValueError('Phase identity requires nonempty string bindings and nonce')
        if (not isinstance(self.marker_name, str) or '/' in self.marker_name
                or self.marker_name in ('', '.', '..', 'worker_receipt.json')
                or len(self.marker_name) > 128):
            raise ValueError('Invalid phase marker name')
        if len(json.dumps(self.identity).encode()) > 3000:
            raise ValueError('Phase identity exceeds marker budget')


def publish_phase_entry():
    """Worker calls immediately before phase entry; publish once, never update."""
    identity = json.loads(os.environ['HIROUTE_PHASE_IDENTITY'])
    path = Path(os.environ['HIROUTE_PHASE_MARKER'])
    if path.exists():
        raise FileExistsError('Phase marker already published')
    entered = time.monotonic()
    _atomic(path, dict(schema=PHASE_SCHEMA, identity=identity, entered_monotonic=entered))
    return entered


def _phase_observation(path, expected, launched, now, previous):
    """Bounded parse once. Later observations compare only immutable stat identity."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        if previous is not None:
            raise ValueError('Previously published phase marker disappeared')
        return None
    def identity(st):
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 4096:
        raise ValueError('Invalid phase marker type or size')
    fingerprint = identity(info)
    if previous is not None:
        if fingerprint != previous[0]:
            raise ValueError('Published phase marker changed')
        return previous
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if identity(before) != fingerprint:
            raise ValueError('Phase marker changed during opening')
        raw = os.read(fd, 4097)
        if len(raw) > 4096 or identity(os.fstat(fd)) != fingerprint:
            raise ValueError('Phase marker changed during reading')
    finally:
        os.close(fd)
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate phase marker key')
            result[key] = value
        return result
    data = json.loads(raw, object_pairs_hook=unique)
    if (not isinstance(data, dict) or set(data) != {'schema', 'identity', 'entered_monotonic'}
            or data['schema'] != PHASE_SCHEMA or data['identity'] != expected):
        raise ValueError('Phase marker identity mismatch')
    entered = data['entered_monotonic']
    if (type(entered) not in (int, float) or not math.isfinite(entered)
            or entered < launched or entered > now):
        raise ValueError('Stale or future phase entry timestamp')
    return fingerprint, entered


def _atomic(path, data):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('x') as f:
        json.dump(data, f, sort_keys=True, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _stat(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return (int(fields[19]), fields[0], int(fields[21]) * os.sysconf('SC_PAGE_SIZE'))
    except (FileNotFoundError, ProcessLookupError):
        return None


def _snapshot():
    # Some Linux-compatible hosts omit /proc/PID/task/TID/children. PPID from
    # stat works there too; take one snapshot rather than rescanning per node.
    found = {}
    with os.scandir('/proc') as entries:
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            pid = int(entry.name)
            try:
                fields = Path(entry.path, 'stat').read_text().rsplit(')', 1)[1].split()
                found[pid] = (int(fields[1]), int(fields[19]), fields[0],
                              int(fields[21]) * os.sysconf('SC_PAGE_SIZE'))
            except (FileNotFoundError, ProcessLookupError):
                pass
    return found


def _children(pid):
    return {child for child, info in _snapshot().items() if info[0] == pid}


def _tree(cap):
    snapshot = _snapshot(); children = {}
    for pid, info in snapshot.items():
        children.setdefault(info[0], []).append(pid)
    pending = list(children.get(os.getpid(), ())); found = {}
    while pending:
        pid = pending.pop()
        if pid in found:
            continue
        found[pid] = snapshot[pid][1:]
        if len(found) >= cap:
            return found, True
        pending.extend(children.get(pid, ()))
    return found, False


def _files(root, cap):
    """Sample owned output without following links or racing temporary deletion.

    Builds legitimately remove temporary entries during this observational scan.
    Only ENOENT for descendant entries is ignored. Directory descriptors anchor
    traversal so a queued path cannot be replaced with a link outside the root.
    """
    total = count = 0
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    stack = []
    def descend(name, *, parent=None, expected=None):
        fd = os.open(name, flags, dir_fd=parent)
        try:
            if expected is not None:
                actual = os.fstat(fd)
                if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                    raise ValueError('Output directory identity changed during sampling')
            entries = os.scandir(fd)
        except BaseException:
            os.close(fd)
            raise
        stack.append((fd, entries))
    try:
        # Losing/replacing the owned root is not ordinary temporary-file churn.
        descend(root)
        while stack:
            parent, entries = stack[-1]
            entry = next(entries, None)
            if entry is None:
                entries.close(); os.close(parent); stack.pop()
                continue
            count += 1
            if count > cap:
                return total, 'output_entry_limit'
            try:
                info = os.stat(entry.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                return total, 'output_symlink'
            if stat.S_ISDIR(info.st_mode):
                try:
                    descend(entry.name, parent=parent, expected=info)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    # O_DIRECTORY|O_NOFOLLOW reports ENOTDIR for a symlink on
                    # Linux. Never follow it, and do not hide unrelated errors.
                    if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                        return total, 'output_directory_changed'
                    raise
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
            else:
                return total, 'output_special_file'
        return total, None
    finally:
        for fd, entries in reversed(stack):
            entries.close(); os.close(fd)


def _json_receipt(path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('Duplicate receipt key')
            out[k] = v
        return out
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('Missing or oversized worker receipt')
    with path.open('rb') as f:
        raw = f.read(65537)
    if len(raw) > 65536:
        raise ValueError('Oversized worker receipt')
    value = json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    if not isinstance(value, dict) or value.get('status') not in ('SUCCESS', 'COMPLETED', 'FEASIBLE'):
        raise ValueError('Malformed or unsuccessful worker receipt')
    return value


def read_result(output_dir):
    """Missing, interrupted or unverifiable terminal receipts are UNKNOWN."""
    try:
        path = Path(output_dir) / 'receipt.json'
        with path.open('rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Oversized terminal receipt')
        value = json.loads(raw)
        if (isinstance(value, dict) and value.get('schema') == SCHEMA
                and value.get('complete') is True and value.get('cleanup_verified') is True
                and isinstance(value.get('effective_child_limits'), dict)):
            status = value.get('status'); reason = value.get('reason'); rc = value.get('returncode')
            if status == 'SUCCESS':
                worker = value.get('worker_receipt')
                if (reason == 'success' and type(rc) is int and rc == 0
                        and isinstance(worker, dict)
                        and worker.get('status') in ('SUCCESS', 'COMPLETED', 'FEASIBLE')):
                    return value
            elif status == 'TIMEOUT' and (reason in ('wall_timeout', 'phase_timeout')
                    or (reason == 'cpu_limit' and rc == -signal.SIGXCPU)):
                return value
            elif status == 'FAILED' and isinstance(reason, str) and reason != 'success':
                return value
    except (OSError, ValueError, AttributeError):
        pass
    return {'schema': SCHEMA, 'status': 'UNKNOWN', 'complete': False,
            'reason': 'missing_or_unverified_terminal_receipt'}


def run(argv, *, output_dir, limits, cwd=None, extra_env=None, phase_budget=None):
    """Run one worker and return a fresh, atomic terminal receipt.

    Resource limits are set ONLY in the child, never on the parent. A too-low
    inherited hard limit fails before launch instead of silently clipping it.
    """
    limits.validate()
    if phase_budget is not None:
        phase_budget.validate()
        phase_budget = PhaseBudget(phase_budget.seconds, dict(phase_budget.identity), phase_budget.marker_name)
    if not argv or not Path(argv[0]).is_absolute():
        raise ValueError('Absolute executable required')
    if threading.current_thread() is not threading.main_thread() or threading.active_count() != 1:
        raise RuntimeError('Dedicated single-threaded supervisor required')
    if _children(os.getpid()):
        raise RuntimeError('Supervisor must have no pre-existing children')
    out = Path(output_dir).resolve(); out.mkdir(parents=True, exist_ok=False)
    artifacts = out / 'artifacts'; artifacts.mkdir()
    worker_receipt = artifacts / 'worker_receipt.json'
    initial = dict(schema=SCHEMA, complete=False, status='UNKNOWN', argv=list(argv),
                   limits=asdict(limits), thread_environment=THREAD_ENV,
                   cgroup_enforced=False, aggregate_memory_hard_limit=False,
                   memory_limit_kind='per_process_virtual_address_space',
                   cpu_limit_kind='per_process_CPU_and_one_core_affinity',
                   file_limit_kind='per_file_FSIZE_and_sampled_artifact_total',
                   cleanup_verified=False,
                   phase_budget=None if phase_budget is None else asdict(phase_budget))
    _atomic(out / 'ledger.json', initial)
    started = time.monotonic(); parent_cpu = time.process_time()
    proc = None; reason = None; error = None; cleanup_ok = False
    peak_rss = peak_files = 0; rc = None; worker_data = None
    libc = ctypes.CDLL(None, use_errno=True); old = ctypes.c_int(); enabled = False
    sel = selectors.DefaultSelector(); streams = []; counts = {'stdout': 0, 'stderr': 0}
    handlers = {}; cleaning = False
    setup_read = setup_write = None; effective_limits = None
    phase_seen = None; worker_started = None
    phase_path = None if phase_budget is None else artifacts / phase_budget.marker_name

    def interrupt(signum, frame):
        if not cleaning:
            raise SupervisorCancellation('Supervisor signal ' + str(signum))

    def prepare():
        os.sched_setaffinity(0, {limits.cpu})
        resource.setrlimit(resource.RLIMIT_AS, (limits.address_space_bytes,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits.file_output_bytes,) * 2)
        actual = {'cpu': list(resource.getrlimit(resource.RLIMIT_CPU)),
                  'address_space': list(resource.getrlimit(resource.RLIMIT_AS)),
                  'file_size': list(resource.getrlimit(resource.RLIMIT_FSIZE)),
                  'affinity': sorted(os.sched_getaffinity(0))}
        os.write(setup_write, json.dumps(actual).encode())
        os.close(setup_write)

    def reap():
        nonlocal rc
        for pid in _children(os.getpid()):
            try:
                got, status = os.waitpid(pid, os.WNOHANG)
                if got and proc is not None and got == proc.pid:
                    rc = os.waitstatus_to_exitcode(status); proc.returncode = rc
            except ChildProcessError:
                pass

    try:
        if libc.prctl(37, ctypes.byref(old), 0, 0, 0) or libc.prctl(36, 1, 0, 0, 0):
            raise OSError(ctypes.get_errno(), 'Linux subreaper required')
        enabled = True
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGXCPU):
            handlers[sig] = signal.getsignal(sig); signal.signal(sig, interrupt)
        env = os.environ.copy(); env.update(extra_env or {}); env.update(THREAD_ENV)
        env.update(HIROUTE_OUTPUT_DIR=str(artifacts), HIROUTE_WORKER_RECEIPT=str(worker_receipt))
        if phase_budget is not None:
            env['HIROUTE_PHASE_IDENTITY'] = json.dumps(phase_budget.identity, sort_keys=True)
            env['HIROUTE_PHASE_MARKER'] = str(phase_path)
        setup_read, setup_write = os.pipe()
        worker_started = time.monotonic()
        proc = subprocess.Popen(list(argv), cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True, preexec_fn=prepare, pass_fds=(setup_write,))
        os.close(setup_write); setup_write = None
        effective_limits = json.loads(os.read(setup_read, 4096))
        os.close(setup_read); setup_read = None
        expected = {'cpu': [limits.cpu_seconds, limits.cpu_seconds + 1],
                    'address_space': [limits.address_space_bytes] * 2,
                    'file_size': [limits.file_output_bytes] * 2, 'affinity': [limits.cpu]}
        if effective_limits != expected:
            raise RuntimeError('Child resource-limit readback mismatch')
        root = _stat(proc.pid)
        _atomic(out / 'worker.json', {'pid': proc.pid, 'start_ticks': None if root is None else root[0]})
        for name, pipe in (('stdout', proc.stdout), ('stderr', proc.stderr)):
            os.set_blocking(pipe.fileno(), False)
            stream = (out / (name + '.txt')).open('wb'); streams.append(stream)
            sel.register(pipe, selectors.EVENT_READ, (name, stream))
        while True:
            now = time.monotonic()
            if phase_budget is not None:
                try:
                    phase_seen = _phase_observation(phase_path, phase_budget.identity,
                                                    worker_started, now, phase_seen)
                except (OSError, ValueError, RecursionError) as exc:
                    reason = 'invalid_phase_marker'; error = str(exc); break
                if phase_seen is not None and now - phase_seen[1] >= phase_budget.seconds:
                    reason = 'phase_timeout'; break
            tree, overflow = _tree(limits.max_processes)
            peak_rss = max(peak_rss, sum(v[2] for v in tree.values()))
            if overflow:
                reason = 'process_count_limit'; break
            size, file_reason = _files(artifacts, limits.max_output_entries)
            peak_files = max(peak_files, size)
            if file_reason or size > limits.file_output_bytes:
                reason = file_reason or 'file_output_limit'; break
            for key, _ in sel.select(limits.poll_seconds):
                name, stream = key.data
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    sel.unregister(key.fileobj); key.fileobj.close(); continue
                cap = getattr(limits, name + '_bytes')
                remaining = cap - counts[name]
                stream.write(chunk[:remaining]); counts[name] += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    reason = name + '_limit'; break
            if reason:
                break
            # Recheck after blocking I/O wait, before accepting terminal completion.
            now = time.monotonic()
            if phase_budget is not None:
                try:
                    phase_seen = _phase_observation(phase_path, phase_budget.identity,
                                                    worker_started, now, phase_seen)
                except (OSError, ValueError, RecursionError) as exc:
                    reason = 'invalid_phase_marker'; error = str(exc); break
                if phase_seen is not None and now - phase_seen[1] >= phase_budget.seconds:
                    reason = 'phase_timeout'; break
            if now - started >= limits.wall_seconds:
                reason = 'wall_timeout'; break
            reap()
            if rc is not None:
                # Stop descendants even if they inherited the worker's pipe handles.
                descendants, _ = _tree(limits.max_processes)
                for pid, identity in descendants.items():
                    current = _stat(pid)
                    if current and current[0] == identity[0]:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
            if rc is not None and not sel.get_map():
                break
            if time.monotonic() - started >= limits.wall_seconds:
                reason = 'wall_timeout'; break
    except BaseException as exc:
        reason = 'supervisor_exception'; error = type(exc).__name__ + ': ' + str(exc)
    finally:
        cleaning = True
        for fd in (setup_read, setup_write):
            if fd is not None:
                os.close(fd)
        deadline = time.monotonic() + limits.cleanup_seconds
        try:
            while enabled and time.monotonic() < deadline:
                tree, overflow = _tree(limits.max_processes)
                for pid, identity in tree.items():
                    current = _stat(pid)
                    if current and current[0] == identity[0]:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                reap()
                if not _children(os.getpid()):
                    cleanup_ok = True; break
                time.sleep(limits.poll_seconds)
        except (OSError, ValueError) as exc:
            cleanup_ok = False
            error = 'Cleanup inspection failed: ' + str(exc)
        for key in list(sel.get_map().values()):
            key.fileobj.close()
        sel.close()
        for stream in streams:
            stream.close()
        if enabled and cleanup_ok:
            libc.prctl(36, old.value, 0, 0, 0)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    if cleanup_ok:
        try:
            size, file_reason = _files(artifacts, limits.max_output_entries)
            peak_files = max(peak_files, size)
            if file_reason or size > limits.file_output_bytes:
                reason = reason or file_reason or 'file_output_limit'
        except OSError as exc:
            reason = reason or 'output_inspection_failed'; error = str(exc)
    if cleanup_ok and phase_budget is not None:
        try:
            phase_seen = _phase_observation(phase_path, phase_budget.identity,
                                            worker_started, time.monotonic(), phase_seen)
            if phase_seen is None and reason is None and rc == 0:
                reason = 'missing_phase_marker'
        except (OSError, ValueError, RecursionError, TypeError) as exc:
            reason = 'invalid_phase_marker'; error = str(exc)
    if not cleanup_ok:
        status = 'UNKNOWN'; reason = 'cleanup_unverified'
    elif reason in ('invalid_phase_marker', 'missing_phase_marker'):
        status = 'UNKNOWN'
    elif reason:
        status = 'TIMEOUT' if reason in ('wall_timeout', 'phase_timeout') else 'FAILED'
    elif rc != 0:
        reason = 'cpu_limit' if rc == -signal.SIGXCPU else 'worker_failed'
        status = 'TIMEOUT' if reason == 'cpu_limit' else 'FAILED'
    else:
        try:
            worker_data = _json_receipt(worker_receipt)
            status = 'SUCCESS'; reason = 'success'
        except (OSError, ValueError, RecursionError) as exc:
            status = 'UNKNOWN'; reason = 'missing_or_malformed_worker_receipt'; error = str(exc)
    result = dict(initial, complete=True, status=status, reason=reason, error=error,
        cleanup_verified=cleanup_ok, returncode=rc, worker_receipt=worker_data,
        wall_seconds=time.monotonic() - started, parent_cpu_seconds=time.process_time() - parent_cpu,
        sampled_process_tree_peak_rss_bytes=peak_rss, sampled_artifact_peak_bytes=peak_files,
        captured_bytes=counts, effective_child_limits=effective_limits,
        phase_entered_monotonic=None if phase_seen is None else phase_seen[1])
    _atomic(out / 'receipt.json', result)
    return result
