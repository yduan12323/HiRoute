"""OS-level supervision and durable incumbent receipts for bounded workers."""
from __future__ import annotations

import hashlib
import json
import math
import os
import resource
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

RECEIPT_SCHEMA = "hiroute.incumbent_receipt.v1"


class ReceiptError(ValueError):
    """A checkpoint is malformed, corrupt, or belongs to another problem."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReceiptError("receipt payload must be finite JSON data") from exc


def save_incumbent_receipt(path: str | os.PathLike[str], *,
                           semantic_problem_id: str,
                           payload: Mapping[str, Any]) -> None:
    """Durably replace a checksummed checkpoint after an attained incumbent.

    The caller must pass a JSON-safe payload containing the full defined key and
    replayable witness. This function records identity and integrity; it does not
    certify the mathematics. Recovery must replay the witness before use.
    """
    if not isinstance(semantic_problem_id, str) or not semantic_problem_id:
        raise ReceiptError("semantic_problem_id is required")
    body = {"schema": RECEIPT_SCHEMA,
            "semantic_problem_id": semantic_problem_id,
            "payload": dict(payload)}
    envelope = {**body, "sha256": hashlib.sha256(_canonical(body)).hexdigest()}
    encoded = _canonical(envelope) + b"\n"
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                     dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def load_incumbent_receipt(path: str | os.PathLike[str], *,
                           expected_semantic_problem_id: str) -> dict[str, Any]:
    """Cold-read a receipt, rejecting truncation, tampering, or wrong identity."""
    try:
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("receipt cannot be decoded") from exc
    if not isinstance(envelope, dict) or set(envelope) != {
            "schema", "semantic_problem_id", "payload", "sha256"}:
        raise ReceiptError("receipt envelope has invalid fields")
    if envelope["schema"] != RECEIPT_SCHEMA:
        raise ReceiptError("unsupported receipt schema")
    if envelope["semantic_problem_id"] != expected_semantic_problem_id:
        raise ReceiptError("receipt belongs to a different semantic problem")
    if not isinstance(envelope["payload"], dict):
        raise ReceiptError("receipt payload must be an object")
    body = {key: envelope[key] for key in ("schema", "semantic_problem_id", "payload")}
    actual = hashlib.sha256(_canonical(body)).hexdigest()
    if not isinstance(envelope["sha256"], str) or envelope["sha256"] != actual:
        raise ReceiptError("receipt checksum mismatch")
    return envelope["payload"]


@dataclass(frozen=True)
class SupervisedRun:
    returncode: int | None
    timed_out: bool
    term_sent: bool
    kill_sent: bool
    process_group_id: int
    stdout: bytes
    stderr: bytes
    elapsed_s: float
    memory_limited: bool = False
    rss_peak_bytes: int = 0
    cpu_limited: bool = False
    cpu_peak_s: float = 0.0
    vm_size_peak_bytes: int = 0
    host_headroom_limited: bool = False
    host_available_min_bytes: int | None = None
    host_monitor_error: str | None = None


def system_mem_available_bytes() -> int:
    """Return Linux MemAvailable in bytes, failing closed if it cannot be read."""
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        if line.startswith("MemAvailable:"):
            fields = line.split()
            if len(fields) >= 2 and fields[1].isdecimal():
                return int(fields[1]) * 1024
            break
    raise OSError("MemAvailable is unavailable in /proc/meminfo")


def _group_rss_bytes(pgid: int) -> int:
    """Aggregate VmRSS for live Linux members of one process group."""
    total = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            stat = (entry / "stat").read_text()
            fields = stat[stat.rfind(")") + 2:].split()
            if len(fields) < 3 or int(fields[2]) != pgid:
                continue
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1]) * 1024
                    break
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
    return total


def _group_vmsize_bytes(pgid: int) -> int:
    """Aggregate VmSize for live Linux members; diagnostic only, not enforcement."""
    total = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            stat = (entry / "stat").read_text()
            fields = stat[stat.rfind(")") + 2:].split()
            if len(fields) < 3 or int(fields[2]) != pgid:
                continue
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("VmSize:"):
                    total += int(line.split()[1]) * 1024
                    break
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
    return total


def _group_cpu_seconds(pgid: int) -> float:
    """Aggregate user+system CPU time for live Linux members of one process group."""
    ticks = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            stat = (entry / "stat").read_text()
            fields = stat[stat.rfind(")") + 2:].split()
            if len(fields) < 13 or int(fields[2]) != pgid:
                continue
            ticks += int(fields[11]) + int(fields[12])
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
    return ticks / os.sysconf("SC_CLK_TCK")


def _atomic_run_receipt(path: str | os.PathLike[str], record: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical(dict(record)) + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                     dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def run_supervised(argv: Sequence[str], *, timeout_s: float, term_grace_s: float = 1.0,
                   cwd: str | None = None,
                   env: Mapping[str, str] | None = None,
                   memory_limit_bytes: int | None = None,
                   process_address_space_limit_bytes: int | None = None,
                   cpu_limit_s: float | None = None,
                   host_min_available_bytes: int | None = None,
                   memory_poll_s: float = 0.02,
                   receipt_path: str | os.PathLike[str] | None = None,
                   run_identity: Mapping[str, Any] | None = None) -> SupervisedRun:
    """Supervise one process group with wall, aggregate-RSS, and CPU limits.

    Group RSS/CPU and host MemAvailable are sampled monitors, not aggregate
    kernel hard caps. The optional RLIMIT_AS and RLIMIT_CPU also apply per
    process. When receipt_path is supplied, the parent atomically records the
    attempt and terminal enforcement state, not solver correctness.
    """
    if (not argv or isinstance(argv, (str, bytes))
            or not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or timeout_s <= 0
            or not isinstance(term_grace_s, (int, float)) or not math.isfinite(term_grace_s) or term_grace_s < 0
            or not isinstance(memory_poll_s, (int, float)) or not math.isfinite(memory_poll_s) or memory_poll_s <= 0):
        raise ValueError("argv and positive finite time limits required")
    if cpu_limit_s is not None and (
            not isinstance(cpu_limit_s, (int, float)) or not math.isfinite(cpu_limit_s) or cpu_limit_s <= 0):
        raise ValueError("cpu_limit_s must be positive and finite")
    if run_identity is not None and not isinstance(run_identity, Mapping):
        raise TypeError("run_identity must be a mapping")
    if memory_limit_bytes is not None and (type(memory_limit_bytes) is not int or memory_limit_bytes < 1):
        raise ValueError("memory_limit_bytes must be a positive integer")
    if process_address_space_limit_bytes is not None and (type(process_address_space_limit_bytes) is not int or process_address_space_limit_bytes < 1):
        raise ValueError("process_address_space_limit_bytes must be a positive integer")
    if host_min_available_bytes is not None and (type(host_min_available_bytes) is not int or host_min_available_bytes < 1):
        raise ValueError("host_min_available_bytes must be a positive integer")
    host_available_min = None
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    audit = None
    if receipt_path is not None:
        audit = {
            "schema": "hiroute.supervised_run.v1",
            "status": "starting",
            "argv": list(argv),
            "cwd": cwd,
            "started_at": started_at,
            "finished_at": None,
            "wall_limit_s": timeout_s,
            "term_grace_s": term_grace_s,
            "memory_limit_bytes": memory_limit_bytes,
            "process_address_space_limit_bytes": process_address_space_limit_bytes,
            "cpu_limit_s": cpu_limit_s,
            "host_min_available_bytes": host_min_available_bytes,
            "host_available_min_bytes": host_available_min,
            "host_monitor_error": None,
            "memory_poll_s": memory_poll_s,
            "run_identity": dict(run_identity or {}),
            "pid": None,
            "process_group_id": None,
        }
        _atomic_run_receipt(receipt_path, audit)
    if host_min_available_bytes is not None:
        try:
            host_available_min = system_mem_available_bytes()
        except OSError as exc:
            if audit is not None:
                audit.update({"status": "host_monitor_error",
                              "finished_at": datetime.now(timezone.utc).isoformat(),
                              "host_monitor_error": f"{type(exc).__name__}: {exc}"})
                _atomic_run_receipt(receipt_path, audit)
            raise RuntimeError("cannot read host MemAvailable before launch") from exc
        if host_available_min < host_min_available_bytes:
            if audit is not None:
                audit.update({"status": "host_headroom_blocked",
                              "finished_at": datetime.now(timezone.utc).isoformat(),
                              "host_available_min_bytes": host_available_min})
                _atomic_run_receipt(receipt_path, audit)
            raise RuntimeError("host MemAvailable is below the configured minimum")
    try:
        def apply_process_limits():
            # Per-process ceilings complement, but do not replace, sampled
            # aggregate process-group RSS/CPU enforcement by the parent.
            if process_address_space_limit_bytes is not None:
                resource.setrlimit(resource.RLIMIT_AS,
                                   (process_address_space_limit_bytes, process_address_space_limit_bytes))
            if cpu_limit_s is not None:
                seconds = max(1, int(cpu_limit_s + 0.999999))
                resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))

        child = subprocess.Popen(list(argv), cwd=cwd,
                                 env=None if env is None else dict(env),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, start_new_session=True,
                                 preexec_fn=apply_process_limits)
    except BaseException as exc:
        if audit is not None:
            audit.update({"status": "launch_error",
                          "finished_at": datetime.now(timezone.utc).isoformat(),
                          "launch_error": type(exc).__name__ + ": " + str(exc)})
            _atomic_run_receipt(receipt_path, audit)
        raise
    if audit is not None:
        audit.update({"status": "running", "pid": child.pid,
                      "process_group_id": child.pid})
        _atomic_run_receipt(receipt_path, audit)
    timed_out = memory_limited = cpu_limited = host_headroom_limited = term_sent = kill_sent = False
    host_monitor_error = None
    rss_peak = 0
    cpu_peak = 0.0
    vm_size_peak = 0
    deadline = started + timeout_s
    while True:
        rss = _group_rss_bytes(child.pid) if memory_limit_bytes is not None else 0
        vm_size = _group_vmsize_bytes(child.pid)
        cpu = _group_cpu_seconds(child.pid) if cpu_limit_s is not None else 0.0
        rss_peak = max(rss_peak, rss)
        vm_size_peak = max(vm_size_peak, vm_size)
        cpu_peak = max(cpu_peak, cpu)
        if host_min_available_bytes is not None:
            try:
                host_available = system_mem_available_bytes()
            except OSError as exc:
                host_monitor_error = f"{type(exc).__name__}: {exc}"
                host_headroom_limited = True
                break
            host_available_min = min(host_available_min, host_available)
            if host_available < host_min_available_bytes:
                host_headroom_limited = True
                break
        if memory_limit_bytes is not None and rss > memory_limit_bytes:
            memory_limited = True
            break
        if cpu_limit_s is not None and cpu > cpu_limit_s:
            cpu_limited = True
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        try:
            stdout, stderr = child.communicate(timeout=min(memory_poll_s, remaining))
            break
        except subprocess.TimeoutExpired:
            continue
    if timed_out or memory_limited or cpu_limited or host_headroom_limited:
        term_sent = True
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = child.communicate(timeout=term_grace_s)
        except subprocess.TimeoutExpired:
            kill_sent = True
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = child.communicate()
        # A leader can exit on TERM while a descendant ignores it.
        try:
            os.killpg(child.pid, signal.SIGKILL)
            kill_sent = True
        except ProcessLookupError:
            pass
        if child.poll() is None:
            child.wait()
    result = SupervisedRun(child.returncode, timed_out, term_sent, kill_sent,
                           child.pid, stdout, stderr, time.monotonic()-started,
                           memory_limited, rss_peak, cpu_limited, cpu_peak, vm_size_peak,
                           host_headroom_limited, host_available_min, host_monitor_error)
    if audit is not None:
        status = ("host_headroom_limit" if host_headroom_limited else
                  "memory_limit" if memory_limited else
                  "cpu_limit" if cpu_limited else
                  "time_limit" if timed_out else "completed")
        audit.update({
            "status": status,
            "execution_status": ("host_headroom_limit" if host_headroom_limited else
                                 "time_limit" if timed_out else
                                 "memory_limit" if memory_limited else
                                 "cpu_limit" if cpu_limited else "completed"),
            "mathematical_status": "unknown" if (timed_out or memory_limited or cpu_limited or host_headroom_limited) else None,
            "verification_status": "not_run" if (timed_out or memory_limited or cpu_limited or host_headroom_limited) else None,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "returncode": child.returncode,
            "term_sent": term_sent,
            "kill_sent": kill_sent,
            "rss_peak_bytes": rss_peak,
            "vm_size_peak_bytes": vm_size_peak,
            "cpu_peak_s": cpu_peak,
            "host_min_available_bytes": host_min_available_bytes,
            "host_available_min_bytes": host_available_min,
            "host_monitor_error": host_monitor_error,
            "elapsed_wall_s": result.elapsed_s,
            "stdout_bytes": len(stdout),
            "stderr_bytes": len(stderr),
        })
        _atomic_run_receipt(receipt_path, audit)
    return result
