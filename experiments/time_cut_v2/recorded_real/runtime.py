"""Opt-in Linux phase guard. This module supplies no authority to run a phase.

The caller freezes inputs/sources and obtains execution approval separately. Its
entry/deadline must precede that work. Workers are trusted, pinned programs, not
hostile code: AS/FSIZE are per-process kernel limits; group RSS and host reserves
are sampled, and the evidence charge is local to one cooperative writer. This is
not a cgroup, disk quota, or security sandbox. No C01 run is performed on import.
"""
from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time
from typing import Callable, Iterable

MiB = 1024 ** 2
GiB = 1024 ** 3
CHUNK_BYTES = 64 * 1024
MAX_FILES = 64
METADATA_BYTES = 64 * 1024
WRITER_HEADROOM = 3 * METADATA_BYTES
ENTRY_CHARGE = 2048
FAILURE_SLOT_BYTES = 8 * 1024
DECISION_BYTES = 2048
_NOFOLLOW = os.O_NOFOLLOW | os.O_CLOEXEC


def _integer(value: object, name: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an exact integer >= {minimum}")
    return value


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    child_as_bytes: int
    group_rss_bytes: int
    wall_seconds: int
    evidence_bytes: int
    supervisor_evidence_bytes: int
    host_reserve_bytes: int
    disk_floor_bytes: int
    supervisor_as_bytes: int = 512 * MiB
    poll_ms: int = 50
    max_sample_gap_ms: int = 1000

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name:
            raise ValueError("profile name must be a nonempty string")
        for key, value in asdict(self).items():
            if key != "name":
                _integer(value, key)
        if self.supervisor_as_bytes > 512 * MiB:
            raise ValueError("supervisor AS exceeds 512 MiB")
        if self.worker_evidence_bytes <= WRITER_HEADROOM:
            raise ValueError("insufficient worker evidence headroom")
        if self.poll_ms >= self.max_sample_gap_ms:
            raise ValueError("poll interval must be below maximum sample gap")

    @property
    def worker_evidence_bytes(self) -> int:
        return self.evidence_bytes - self.supervisor_evidence_bytes


CAPTURE = RuntimeProfile("capture-v1", 8 * GiB, 8 * GiB, 1200, 4 * GiB,
                         16 * MiB, 16 * GiB, 20 * GiB)
REPLAY = RuntimeProfile("replay-v1", 16 * GiB, 16 * GiB, 1800, 8 * GiB,
                        16 * MiB, 16 * GiB, 20 * GiB)
BATCH_REPLAY = RuntimeProfile("batch-replay-v1", 16 * GiB, 20 * GiB, 1800, 8 * GiB,
                              16 * MiB, 16 * GiB, 20 * GiB)
TINY_TEST = RuntimeProfile("tiny-test-v1", 256 * MiB, 256 * MiB, 2, 2 * MiB,
                          64 * 1024, MiB, MiB)
PROFILES = {p.name: p for p in (CAPTURE, REPLAY, BATCH_REPLAY, TINY_TEST)}


@dataclass(frozen=True)
class PlanContext:
    """Pinned context only; this record is explicitly not user approval."""
    plan_sha256: str
    source_sha256: str
    input_sha256: str
    profile_name: str

    def __post_init__(self) -> None:
        for key in ("plan_sha256", "source_sha256", "input_sha256"):
            value = getattr(self, key)
            if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{key} must be a lowercase SHA-256 digest")
        if type(self.profile_name) is not str or self.profile_name not in PROFILES:
            raise ValueError("unknown context profile")


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _directory(path: Path, *, create: bool = False) -> int:
    """Open each component without following symlinks, including root parents."""
    path = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _relative(value: str) -> tuple[str, ...]:
    if type(value) is not str or len(value.encode()) > 512 or "\\" in value:
        raise ValueError("invalid evidence path")
    parts = tuple(value.split("/"))
    if not parts or any(p in ("", ".", "..") or p.startswith("__") for p in parts):
        raise ValueError("evidence paths must be relative, normalized, and nonreserved")
    return parts


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise OSError("short write")
        view = view[count:]


def _exclusive_json(path: Path, value: object, limit: int = METADATA_BYTES,
                    *, before_publish: Callable[[], None] | None = None) -> int:
    data = _json(value)
    if len(data) > limit:
        raise ValueError("metadata exceeds reserved bound")
    partial = path.with_name(path.name + ".partial")
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o400)
    try:
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    if before_publish is not None:
        before_publish()
    os.link(partial, path, follow_symlinks=False)
    partial.unlink()
    parent = _directory(path.parent)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return len(data)


def worker_failure(error_type: str, message: str, stage: str) -> bool:
    """Best-effort single diagnostic slot, independent of a poisoned writer.

    The supervisor reserves this slot in its own allowance. It never authorizes
    completion. Duplicate calls cannot replace the first failure, and allocation
    failure may prevent even this small diagnostic from being written.
    """
    try:
        if any(type(value) is not str for value in (error_type, message, stage)):
            return False
        path = Path(os.environ["HIROUTE_FAILURE_PATH"])
        if path.name != "worker-failure.json":
            return False
        claim = os.open(path.with_suffix(".claim"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o400)
        os.close(claim)
        payload = {"schema": "hiroute-worker-failure-v1", "error_type": error_type[:128],
                   "message": message[:1024], "stage": stage[:128]}
        while len(_json(payload)) > FAILURE_SLOT_BYTES:
            payload["message"] = payload["message"][:len(payload["message"]) // 2]
        _exclusive_json(path, payload, FAILURE_SLOT_BYTES)
        return True
    except Exception:
        return False


def _read_worker_failure(attempt: Path) -> dict | None:
    try:
        fd = os.open(attempt / "worker-failure.json", os.O_RDONLY | _NOFOLLOW)
    except FileNotFoundError:
        if (attempt / "worker-failure.claim").exists() or (attempt / "worker-failure.json.partial").exists():
            raise ValueError("incomplete worker failure diagnostic")
        return None
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(FAILURE_SLOT_BYTES + 1)
    if len(raw) > FAILURE_SLOT_BYTES:
        raise ValueError("worker failure diagnostic exceeds its reserved slot")
    value = json.loads(raw)
    if (type(value) is not dict or value.get("schema") != "hiroute-worker-failure-v1" or
            any(type(value.get(key)) is not str for key in ("error_type", "message", "stage"))):
        raise ValueError("invalid worker failure diagnostic")
    return value


class BoundedEvidenceWriter:
    """Single-owner, one-pass writer; any failed write poisons completion.

    Charge = fixed metadata/report headroom + per-path metadata + twice every
    accepted byte. Reservations are never refunded, even after failed writes.
    Successful paths are atomically linked without overwrite. Failed partials
    and the journal remain; reopening an attempt as a writer is forbidden.
    """

    def __init__(self, root: Path | str, cap_bytes: int, *, profile_name: str):
        self.cap_bytes = _integer(cap_bytes, "cap_bytes", WRITER_HEADROOM + 1)
        if type(profile_name) is not str or not profile_name:
            raise ValueError("profile_name must be a nonempty string")
        self.root = Path(os.path.abspath(root))
        self.profile_name = profile_name
        self.charged_bytes = WRITER_HEADROOM
        self.files: list[dict] = []
        self._paths: set[str] = set()
        self._failed = False
        self._closed = False
        self._journal_bytes = 0
        parent = _directory(self.root.parent, create=True)
        try:
            os.mkdir(self.root.name, mode=0o700, dir_fd=parent)
        finally:
            os.close(parent)
        self._fd = self._partial_fd = self._journal = None
        try:
            self._fd = _directory(self.root)
            os.mkdir("__partial", mode=0o700, dir_fd=self._fd)
            self._partial_fd = os.open("__partial", os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=self._fd)
            lock = os.open("__writer.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o400, dir_fd=self._fd)
            os.close(lock)
            self._journal = os.open("__journal.jsonl", os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o400, dir_fd=self._fd)
        except BaseException:
            self.close()
            raise

    def _reserve(self, amount: int) -> None:
        if self.charged_bytes + amount > self.cap_bytes:
            raise ValueError("worker evidence charge exceeded")
        self.charged_bytes += amount

    def _event(self, value: dict) -> None:
        data = _json(value)
        if self._journal_bytes + len(data) > METADATA_BYTES:
            raise ValueError("bounded journal exhausted")
        _write_all(self._journal, data)
        self._journal_bytes += len(data)
        os.fsync(self._journal)

    def write(self, relative_path: str, chunks: Iterable[bytes], *, expected_bytes: int | None = None) -> dict:
        if self._closed or self._failed:
            raise ValueError("writer is finalized or failed")
        partial = f"__partial/{len(self._paths):04d}.part"
        fd = parent_fd = None
        try:
            parts = _relative(relative_path)
            if expected_bytes is not None:
                _integer(expected_bytes, "expected_bytes", 0)
            if relative_path in self._paths or len(self._paths) >= MAX_FILES:
                raise ValueError("duplicate path or file count exceeded")
            self._reserve(ENTRY_CHARGE)
            self._paths.add(relative_path)
            parent_fd = _directory(self.root.joinpath(*parts[:-1]), create=True)
            # Claiming a path never overwrites a pre-existing file or symlink.
            try:
                os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("evidence target already exists")
            partial_name = partial.split("/")[1]
            fd = os.open(partial_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o400, dir_fd=self._partial_fd)
            digest, size = hashlib.sha256(), 0
            self._event({"event": "begin", "path": relative_path, "partial": partial})
            for chunk in chunks:
                if type(chunk) is not bytes:
                    raise ValueError("evidence chunks must be immutable bytes")
                for offset in range(0, len(chunk), CHUNK_BYTES):
                    piece = chunk[offset:offset + CHUNK_BYTES]
                    self._reserve(2 * len(piece))
                    _write_all(fd, piece)
                    digest.update(piece)
                    size += len(piece)
            if expected_bytes is not None and size != expected_bytes:
                raise ValueError("producer ended before the expected byte count")
            os.fsync(fd)
            os.close(fd)
            fd = None
            row = {"path": relative_path, "size_bytes": size, "sha256": digest.hexdigest()}
            os.link(partial_name, parts[-1], src_dir_fd=self._partial_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
            os.unlink(partial_name, dir_fd=self._partial_fd)
            os.fsync(parent_fd)
            self._event({"event": "published", **row})
            self.files.append(row)
            return dict(row)
        except BaseException as exc:
            self._failed = True
            self._event({"event": "failed", "reason": type(exc).__name__})
            raise
        finally:
            if fd is not None:
                os.close(fd)
            if parent_fd is not None:
                os.close(parent_fd)

    def finalize(self) -> dict:
        if self._closed or self._failed:
            raise ValueError("cannot finalize a failed or finalized writer")
        result = {"schema": "hiroute-evidence-v1", "profile_name": self.profile_name,
                  "cap_bytes": self.cap_bytes, "charged_bytes": self.charged_bytes,
                  "charge_kind": "worker-local conservative reservation; not live aggregate disk usage",
                  "files": self.files}
        try:
            _exclusive_json(self.root / "__manifest.json", result)
            os.fsync(self._fd)
            self.close()
            return verify_manifest(self.root, expected_cap_bytes=self.cap_bytes,
                                   expected_profile_name=self.profile_name)
        except BaseException:
            self._failed = True
            self.close()
            raise

    def close(self) -> None:
        if not self._closed:
            for fd in (self._journal, self._partial_fd, self._fd):
                if fd is not None:
                    os.close(fd)
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _inventory(root: Path, checkpoint: Callable[[], None]) -> dict[str, tuple[int, ...]]:
    found = {".": _identity(root.lstat())}
    for base, directories, files in os.walk(root, followlinks=False):
        checkpoint()
        for name in directories + files:
            checkpoint()
            path = Path(base) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("symlink in evidence inventory")
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ValueError("nonregular evidence inventory entry")
            found[path.relative_to(root).as_posix()] = _identity(info)
    return found


@dataclass(frozen=True)
class VerifiedEvidence:
    manifest: dict
    manifest_sha256: str
    manifest_size_bytes: int
    root: Path
    identities: dict[str, tuple[int, ...]]

    def check_unchanged(self, checkpoint: Callable[[], None]) -> None:
        if _inventory(self.root, checkpoint) != self.identities:
            raise ValueError("evidence/output context changed after cold verification")


def _verify_manifest(root: Path | str, *, expected_cap_bytes: int,
                     expected_profile_name: str, deadline_monotonic: float | None = None,
                     resource_check: Callable[[], None] | None = None) -> VerifiedEvidence:
    """Return a commitment to the same bytes parsed and cold-verified below."""
    def checkpoint() -> None:
        if resource_check is not None:
            resource_check()
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise TimeoutError("phase expired during cold manifest verification")

    checkpoint()
    _integer(expected_cap_bytes, "expected_cap_bytes", WRITER_HEADROOM + 1)
    root = Path(os.path.abspath(root))
    fd = _directory(root)
    os.close(fd)
    manifest_path = root / "__manifest.json"
    manifest_fd = os.open(manifest_path, os.O_RDONLY | _NOFOLLOW)
    with os.fdopen(manifest_fd, "rb") as stream:
        manifest_identity = _identity(os.fstat(stream.fileno()))
        raw = stream.read(METADATA_BYTES + 1)
        if _identity(os.fstat(stream.fileno())) != manifest_identity:
            raise ValueError("manifest changed while being read")
    checkpoint()
    if len(raw) > METADATA_BYTES:
        raise ValueError("manifest too large")
    manifest = json.loads(raw)
    if (manifest.get("schema") != "hiroute-evidence-v1" or
            type(manifest.get("cap_bytes")) is not int or manifest["cap_bytes"] != expected_cap_bytes or
            manifest.get("profile_name") != expected_profile_name):
        raise ValueError("manifest profile/cap mismatch")
    rows = manifest.get("files")
    if type(rows) is not list or len(rows) > MAX_FILES:
        raise ValueError("invalid manifest inventory")
    expected = {"__writer.lock", "__journal.jsonl", "__manifest.json"}
    read_identities = {"__manifest.json": manifest_identity}
    total = 0
    for row in rows:
        checkpoint()
        parts = _relative(row["path"])
        if row["path"] in expected:
            raise ValueError("duplicate manifest path")
        expected.add(row["path"])
        _integer(row["size_bytes"], "size_bytes", 0)
        parent = _directory(root.joinpath(*parts[:-1]))
        try:
            file_fd = os.open(parts[-1], os.O_RDONLY | _NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)
        with os.fdopen(file_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("evidence must be singly linked regular files")
            digest, size = hashlib.sha256(), 0
            while data := stream.read(CHUNK_BYTES):
                checkpoint()
                digest.update(data)
                size += len(data)
            if _identity(os.fstat(stream.fileno())) != _identity(info):
                raise ValueError("evidence changed while being hashed")
            read_identities[row["path"]] = _identity(info)
        checkpoint()
        if size != row["size_bytes"] or digest.hexdigest() != row["sha256"]:
            raise ValueError("evidence hash/size mismatch")
        total += size
    identities = _inventory(root, checkpoint)
    actual = {name for name, info in identities.items() if stat.S_ISREG(info[2])}
    for name, identity in read_identities.items():
        if identities.get(name) != identity:
            raise ValueError("evidence/output context changed during verification")
    if any(identities[name][4] > METADATA_BYTES for name in ("__journal.jsonl", "__manifest.json")):
        raise ValueError("metadata bound exceeded")
    if identities["__writer.lock"][4] != 0:
        raise ValueError("writer lock must be empty; metadata bound exceeded")
    if any(not stat.S_ISREG(identities[name][2]) or identities[name][3] != 1
           for name in ("__journal.jsonl", "__manifest.json", "__writer.lock")):
        raise ValueError("metadata must be singly linked regular files")
    charge = WRITER_HEADROOM + ENTRY_CHARGE * len(rows) + 2 * total
    if (actual != expected or type(manifest.get("charged_bytes")) is not int or
            manifest["charged_bytes"] != charge or charge > expected_cap_bytes):
        raise ValueError("incomplete inventory or invalid conservative charge")
    checkpoint()
    return VerifiedEvidence(manifest, hashlib.sha256(raw).hexdigest(), len(raw), root, identities)


def verify_manifest(root: Path | str, *, expected_cap_bytes: int,
                    expected_profile_name: str, deadline_monotonic: float | None = None) -> dict:
    """Cold rehash, inventory and accounting checks against expected values."""
    return _verify_manifest(root, expected_cap_bytes=expected_cap_bytes,
                            expected_profile_name=expected_profile_name,
                            deadline_monotonic=deadline_monotonic).manifest


def _mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("Linux MemAvailable is required")


def _disk_available(path: Path) -> int:
    value = os.statvfs(path)
    return value.f_bavail * value.f_frsize


def _live_checks(profile: RuntimeProfile, attempt: Path, deadline: float,
                 *, pending_metadata_bytes: int = 0) -> None:
    if _mem_available() < profile.host_reserve_bytes:
        raise MemoryError("live host MemAvailable reserve breached")
    if _disk_available(attempt) < profile.disk_floor_bytes + pending_metadata_bytes:
        raise OSError("live free disk floor or reserved report metadata floor breached")
    if time.monotonic() >= deadline:
        raise TimeoutError("absolute phase wall deadline exceeded")


def _read_json_bytes(path: Path, limit: int) -> tuple[dict, bytes]:
    fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        identity = _identity(os.fstat(stream.fileno()))
        raw = stream.read(limit + 1)
        if _identity(os.fstat(stream.fileno())) != identity or _identity(path.lstat()) != identity:
            raise ValueError("control record changed while being read")
    if len(raw) > limit:
        raise ValueError("bounded control record exceeded")
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError("invalid control record")
    return value, raw


def _reject(attempt: Path, reason: str) -> dict:
    value = {"schema": "hiroute-phase-rejection-v1", "status": "unresolved", "reason": reason[:512]}
    if not os.path.lexists(attempt / "rejection.json"):
        _exclusive_json(attempt / "rejection.json", value, DECISION_BYTES)
    return value


def _read_ready(attempt: Path) -> tuple[dict, bytes]:
    if os.path.lexists(attempt / "rejection.json"):
        raise ValueError("phase has a terminal rejection")
    report, report_raw = _read_json_bytes(attempt / "result.json", METADATA_BYTES)
    ready, ready_raw = _read_json_bytes(attempt / "supervisor-decision.json", DECISION_BYTES)
    profile = RuntimeProfile(**report["profile"])
    PlanContext(**report["context"])
    request, request_raw = _read_json_bytes(attempt / "request.json", profile.supervisor_evidence_bytes // 8)
    RuntimeProfile(**request["profile"])
    PlanContext(**request["context"])
    for key in ("profile", "context", "entry_monotonic", "deadline_monotonic", "launcher_rss_bytes_at_entry"):
        if report.get(key) != request.get(key):
            raise ValueError(f"report {key} differs from bound request")
    if profile == BATCH_REPLAY or "worker_cpus" in request or "worker_cpus" in report:
        _request_worker_cpus(profile, request)
        _request_worker_cpus(profile, report)
        for key in ("cpu", "worker_cpus"):
            if _json(report.get(key)) != _json(request.get(key)):
                raise ValueError(f"report {key} differs from bound request")
    for key in ("entry_monotonic", "deadline_monotonic"):
        if any(type(record.get(key)) is not float or not math.isfinite(record[key]) for record in (report, request)):
            raise ValueError(f"invalid exact-type {key}")
    if not report["entry_monotonic"] < report["deadline_monotonic"] <= report["entry_monotonic"] + profile.wall_seconds:
        raise ValueError("bound request exceeds profile wall budget")
    _integer(request.get("launcher_rss_bytes_at_entry"), "request launcher RSS", 0)
    integer_limits = {"sampled_group_rss_peak_bytes": profile.group_rss_bytes,
                      "kernel_max_reaped_ru_maxrss_bytes": profile.child_as_bytes,
                      "supervisor_kernel_peak_rss_bytes": profile.supervisor_as_bytes,
                      "worker_charged_bytes": profile.worker_evidence_bytes,
                      "supervisor_metadata_charge_bytes_before_report": profile.supervisor_evidence_bytes,
                      "launcher_rss_bytes_at_entry": None}
    for key, maximum in integer_limits.items():
        value = _integer(report.get(key), key, 0)
        if maximum is not None and value > maximum:
            raise ValueError(f"reported {key} exceeds profile limit")
    float_limits = {"largest_sample_gap_seconds": profile.max_sample_gap_ms / 1000,
                    "phase_wall_seconds": report["deadline_monotonic"] - report["entry_monotonic"],
                    "reaped_cpu_seconds": None, "supervisor_cpu_seconds": None}
    for key, maximum in float_limits.items():
        value = report.get(key)
        if type(value) is not float or not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
            raise ValueError(f"invalid or over-limit sampled metric {key}")
    if type(report.get("worker_exit_code")) is not int or report["worker_exit_code"] != 0 or report.get("descendants_reaped") is not True:
        raise ValueError("completed phase requires successful worker exit and descendant reaping")
    if (PROFILES.get(profile.name) != profile or report["context"]["profile_name"] != profile.name or
            report.get("schema") != "hiroute-phase-v1" or report.get("status") != "provisional" or
            ready.get("schema") != "hiroute-supervisor-decision-v1" or ready.get("status") != "ready" or
            ready.get("report_sha256") != hashlib.sha256(report_raw).hexdigest() or
            ready.get("report_size_bytes") != len(report_raw) or
            ready.get("manifest_sha256") != report.get("verified_manifest_sha256") or
            ready.get("manifest_size_bytes") != report.get("verified_manifest_size_bytes") or
            report.get("request_sha256") != hashlib.sha256(request_raw).hexdigest()):
        raise ValueError("provisional report/manifest decision binding mismatch")
    return report, ready_raw


def read_phase_result(attempt_dir: Path | str, *, successful_return: dict | None = None,
                      deadline_monotonic: float | None = None,
                      resource_check: Callable[[], None] | None = None) -> dict:
    """Require a separately retained/pinned successful caller return as well as
    the final decision and cold evidence. Attempt files alone cannot certify an
    interrupted launcher: the last decision's publication precedes its final
    checks. Never reconstruct successful_return from those attempt files.
    A historical decision's phase deadline is checked against its recorded
    acceptance time; an optional new deadline bounds this read/replay operation.
    """
    attempt = Path(os.path.abspath(attempt_dir))
    try:
        if (type(successful_return) is not dict or successful_return.get("schema") != "hiroute-phase-v1" or
                successful_return.get("status") != "completed"):
            raise ValueError("separately retained successful caller return is required")
        fd = _directory(attempt)
        os.close(fd)
        report, ready_raw = _read_ready(attempt)
        decision, decision_raw = _read_json_bytes(attempt / "decision.json", DECISION_BYTES)
        accepted = decision.get("accepted_monotonic")
        if (decision.get("schema") != "hiroute-phase-decision-v1" or decision.get("status") != "completed" or
                type(decision.get("supervisor_exit_code")) is not int or decision["supervisor_exit_code"] != 0 or
                decision.get("supervisor_decision_sha256") != hashlib.sha256(ready_raw).hexdigest() or
                type(accepted) is not float or not math.isfinite(accepted) or
                not report["entry_monotonic"] <= accepted < report["deadline_monotonic"]):
            raise ValueError("missing or invalid final phase decision")
        profile = PROFILES[report["profile"]["name"]]
        receipt = successful_return.get("acceptance_receipt")
        returned = receipt.get("returned_monotonic") if type(receipt) is dict else None
        if (type(receipt) is not dict or receipt.get("schema") != "hiroute-caller-return-v1" or
                receipt.get("result_sha256") != json.loads(ready_raw)["report_sha256"] or
                receipt.get("decision_sha256") != hashlib.sha256(decision_raw).hexdigest() or
                receipt.get("manifest_sha256") != report["verified_manifest_sha256"] or
                type(receipt.get("manifest_size_bytes")) is not int or
                receipt["manifest_size_bytes"] != report["verified_manifest_size_bytes"] or
                type(returned) is not float or not math.isfinite(returned) or
                not accepted <= returned < report["deadline_monotonic"] or
                type(successful_return.get("phase_wall_seconds")) is not float or
                successful_return["phase_wall_seconds"] != returned - report["entry_monotonic"]):
            raise ValueError("successful caller return does not bind this final decision")
        if len(_json(successful_return)) > min(METADATA_BYTES, profile.supervisor_evidence_bytes // 16):
            raise ValueError("successful caller return exceeds its reserved metadata slot")
        for key, value in report.items():
            if key not in ("status", "reason", "phase_wall_seconds") and _json(successful_return.get(key)) != _json(value):
                raise ValueError(f"caller return {key} differs from provisional report")
        verified = _verify_manifest(attempt / "evidence", expected_cap_bytes=profile.worker_evidence_bytes,
                                    expected_profile_name=profile.name, deadline_monotonic=deadline_monotonic,
                                    resource_check=resource_check)
        if (verified.manifest_sha256 != report["verified_manifest_sha256"] or
                verified.manifest_size_bytes != report["verified_manifest_size_bytes"] or
                verified.manifest["charged_bytes"] != report["worker_charged_bytes"]):
            raise ValueError("cold-verified manifest differs from completed decision")
        _, current_ready = _read_ready(attempt)
        _, current_decision = _read_json_bytes(attempt / "decision.json", DECISION_BYTES)
        if current_ready != ready_raw or current_decision != decision_raw:
            raise ValueError("completion context changed during verification")
        if resource_check is not None:
            resource_check()
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise TimeoutError("phase expired during final decision reconciliation")
        return dict(successful_return, reason="accepted pinned caller return and cold-verified evidence")
    except Exception as exc:
        return {"schema": "hiroute-phase-v1", "status": "unresolved", "reason": f"{type(exc).__name__}: {str(exc)[:512]}"}


def _processes() -> dict[int, tuple[int, int, int, int]]:
    """pid -> (ppid, pgid, start ticks, RSS bytes); shared pages double count."""
    rows = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            tail = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            rows[int(entry.name)] = (int(tail[1]), int(tail[2]), int(tail[19]),
                                     int(tail[21]) * os.sysconf("SC_PAGE_SIZE"))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rows


def _descendants(rows: dict, supervisor_pid: int, pgid: int) -> set[int]:
    found = {pid for pid, row in rows.items() if row[1] == pgid}
    parents = {supervisor_pid, *found}
    while additions := {pid for pid, row in rows.items() if row[0] in parents} - found:
        found.update(additions)
        parents.update(additions)
    return found


def _prctl(option: int, value: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(option, value, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl failed")


def _subreaper_value() -> int:
    value = ctypes.c_int()
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(37, ctypes.byref(value), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_GET_CHILD_SUBREAPER failed")
    return value.value


def _reap_launcher_groups(groups: set[int], timeout: float = 2.0) -> bool:
    """Bounded fallback when the supervisor died, including orphaned grandchildren."""
    until = time.monotonic() + timeout
    while groups:
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            while True:
                try:
                    pid, _ = os.waitpid(-group, os.WNOHANG)
                except ChildProcessError:
                    break
                if not pid:
                    break
        rows = _processes()
        groups &= {row[1] for row in rows.values()}
        if time.monotonic() >= until:
            return not groups
        if groups:
            time.sleep(0.01)
    return True


def _check_hard_limit(profile: RuntimeProfile) -> None:
    hard = resource.getrlimit(resource.RLIMIT_AS)[1]
    if hard != resource.RLIM_INFINITY and hard < max(profile.child_as_bytes, profile.supervisor_as_bytes):
        raise ValueError("inherited RLIMIT_AS hard limit is smaller than the exact profile")


def _worker_cpu_mask(profile: RuntimeProfile, cpu: int,
                     worker_cpus: tuple[int, ...] | None) -> tuple[int, ...]:
    """Keep serial profiles unchanged; batch reserves five distinct worker CPUs."""
    _integer(cpu, "cpu", 0)
    if profile != BATCH_REPLAY:
        if worker_cpus is not None:
            raise ValueError("worker_cpus is only supported by the fixed batch replay profile")
        return (cpu,)
    if type(worker_cpus) is not tuple or len(worker_cpus) != 5:
        raise ValueError("batch replay worker_cpus must be a tuple of exactly five CPU IDs")
    for worker_cpu in worker_cpus:
        _integer(worker_cpu, "worker CPU", 0)
    if len(set(worker_cpus)) != 5 or cpu in worker_cpus:
        raise ValueError("batch replay requires six distinct CPUs including the supervisor")
    return worker_cpus


def _request_worker_cpus(profile: RuntimeProfile, request: dict) -> tuple[int, ...] | None:
    """Decode the exact request/report mask without consulting current affinity."""
    value = request.get("worker_cpus")
    if value is not None and type(value) is not list:
        raise ValueError("serialized worker_cpus must be a list")
    worker_cpus = tuple(value) if value is not None else None
    _worker_cpu_mask(profile, request.get("cpu"), worker_cpus)
    return worker_cpus


def _preflight(profile: RuntimeProfile, attempt: Path, cpu: int,
               worker_cpus: tuple[int, ...] | None = None) -> None:
    _check_hard_limit(profile)
    mask = _worker_cpu_mask(profile, cpu, worker_cpus)
    if not {cpu, *mask} <= os.sched_getaffinity(0):
        raise ValueError("explicit CPU mask is outside inherited affinity")
    worker_reservation = max(profile.child_as_bytes, profile.group_rss_bytes)
    if _mem_available() < profile.host_reserve_bytes + worker_reservation + profile.supervisor_as_bytes:
        raise ValueError("insufficient host MemAvailable admission reserve")
    if _disk_available(attempt) < profile.disk_floor_bytes + profile.evidence_bytes:
        raise ValueError("insufficient free disk admission reserve")


def _supervise(request: dict, attempt: Path) -> dict:
    profile = PROFILES[request["profile"]["name"]]
    deadline = request["deadline_monotonic"]
    started = request["entry_monotonic"]
    report = {"schema": "hiroute-phase-v1", "status": "unresolved", "reason": "not started",
              "profile": asdict(profile), "context": request["context"], "worker_pid": None,
              "entry_monotonic": started, "deadline_monotonic": deadline,
              "sampled_group_rss_peak_bytes": 0, "largest_sample_gap_seconds": 0.0,
              "reaped_cpu_seconds": 0.0, "kernel_max_reaped_ru_maxrss_bytes": 0,
              "launcher_rss_bytes_at_entry": request["launcher_rss_bytes_at_entry"],
              "rss_scope": "sampled worker process group; shared pages may double count; not exact aggregate peak",
              "kernel_peak_scope": "maximum wait4 ru_maxrss across reaped processes, not summed group peak",
              "evidence_scope": "worker-local conservative charge plus separate supervisor metadata reservation"}
    if profile == BATCH_REPLAY:
        report.update(cpu=request.get("cpu"), worker_cpus=request.get("worker_cpus"))
    worker = None
    lock_fd = snapshot_fd = None
    last_sample = last_snapshot = time.monotonic()
    metadata_used = 2 * (attempt / "request.json").stat().st_size
    report_limit = min(METADATA_BYTES, profile.supervisor_evidence_bytes // 16)
    terminal_reserve = 2 * (2 * report_limit + 3 * DECISION_BYTES)
    metadata_used += 2 * FAILURE_SLOT_BYTES  # Reserve even when the worker cannot report.
    tracked: dict[int, int] = {}
    verified = None
    request_raw = (attempt / "request.json").read_bytes()
    report["request_sha256"] = hashlib.sha256(request_raw).hexdigest()

    def checkpoint() -> None:
        _live_checks(profile, attempt, deadline, pending_metadata_bytes=2 * report_limit + 3 * DECISION_BYTES)
        if metadata_used + terminal_reserve > profile.supervisor_evidence_bytes:
            raise ValueError("supervisor final metadata reservation exhausted")

    def unchanged() -> None:
        checkpoint()
        if (attempt / "request.json").read_bytes() != request_raw:
            raise ValueError("phase request/context changed before final acceptance")
        if verified is not None:
            verified.check_unchanged(checkpoint)

    def reap() -> bool:
        alive = True
        while True:
            try:
                pid, status, usage = os.wait4(-1, os.WNOHANG)
            except ChildProcessError:
                return False
            if not pid:
                return alive
            report["reaped_cpu_seconds"] += usage.ru_utime + usage.ru_stime
            report["kernel_max_reaped_ru_maxrss_bytes"] = max(report["kernel_max_reaped_ru_maxrss_bytes"], usage.ru_maxrss * 1024)
            if worker is not None and pid == worker.pid:
                worker.returncode = os.waitstatus_to_exitcode(status)
                report["worker_exit_code"] = worker.returncode

    def sample() -> tuple[dict, set[int]]:
        nonlocal last_sample, last_snapshot, metadata_used
        rows = _processes()
        descendants = _descendants(rows, os.getpid(), worker.pid)
        tracked.update({pid: rows[pid][2] for pid in descendants})
        group_rss = sum(row[3] for row in rows.values() if row[1] == worker.pid)
        report["sampled_group_rss_peak_bytes"] = max(report["sampled_group_rss_peak_bytes"], group_rss)
        available, disk = _mem_available(), _disk_available(attempt)
        now = time.monotonic()
        gap = now - last_sample
        report["largest_sample_gap_seconds"] = max(report["largest_sample_gap_seconds"], gap)
        last_sample = now
        if now - last_snapshot >= 5 or last_snapshot == started:
            data = _json({"stage": "worker-running", "elapsed_seconds": now - started, "sampled_group_rss_bytes": group_rss,
                          "host_available_bytes": available, "disk_available_bytes": disk})
            if metadata_used + 2 * len(data) + terminal_reserve > profile.supervisor_evidence_bytes:
                raise ValueError("supervisor metadata reservation exhausted")
            _write_all(snapshot_fd, data)
            os.fsync(snapshot_fd)
            metadata_used += 2 * len(data)
            last_snapshot = now
        if now >= deadline:
            raise TimeoutError("absolute phase wall deadline exceeded")
        if gap > profile.max_sample_gap_ms / 1000:
            raise TimeoutError("maximum RSS sampling gap exceeded")
        if group_rss > profile.group_rss_bytes:
            raise MemoryError("sampled process-group RSS limit exceeded")
        if available < profile.host_reserve_bytes:
            raise MemoryError("live host MemAvailable reserve breached")
        if disk < profile.disk_floor_bytes:
            raise OSError("live free disk floor breached")
        if any(rows[pid][1] != worker.pid for pid in descendants):
            raise RuntimeError("descendant escaped the worker process group")
        return rows, descendants

    try:
        report["stage"] = "preflight"
        if time.monotonic() >= deadline:
            raise TimeoutError("phase expired before preflight")
        worker_cpus = _request_worker_cpus(profile, request)
        _preflight(profile, attempt, request["cpu"], worker_cpus)
        # This file is shared by every profile of this guard for the current UID.
        lock_path = Path("/tmp") / f"hiroute-recorded-phase-{os.getuid()}.lock"
        inherited_lock = request.get("admission_lock_fd")
        if inherited_lock is None:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | _NOFOLLOW, 0o600)
        else:
            lock_fd = os.dup(_integer(inherited_lock, "admission lock descriptor", 0))
            actual, expected = os.fstat(lock_fd), lock_path.lstat()
            if not stat.S_ISREG(actual.st_mode) or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                raise ValueError("inherited admission lock identity mismatch")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        hard = resource.getrlimit(resource.RLIMIT_AS)[1]
        resource.setrlimit(resource.RLIMIT_AS, (profile.supervisor_as_bytes, hard))
        os.sched_setaffinity(0, {request["cpu"]})
        _prctl(36, 1)  # PR_SET_CHILD_SUBREAPER: collect orphaned descendants.
        snapshot_fd = os.open(attempt / "samples.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o400)
        if time.monotonic() >= deadline:
            raise TimeoutError("phase expired during preflight")

        def child_limits() -> None:
            _prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
            resource.setrlimit(resource.RLIMIT_AS, (profile.child_as_bytes, profile.child_as_bytes))
            resource.setrlimit(resource.RLIMIT_FSIZE, (profile.worker_evidence_bytes, profile.worker_evidence_bytes))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            os.sched_setaffinity(0, set(worker_cpus) if worker_cpus is not None else {request["cpu"]})

        env = dict(os.environ, HIROUTE_EVIDENCE_ROOT=str(attempt / "evidence"),
                   HIROUTE_EVIDENCE_CAP_BYTES=str(profile.worker_evidence_bytes), HIROUTE_PROFILE=profile.name,
                   HIROUTE_FAILURE_PATH=str(attempt / "worker-failure.json"),
                   OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        worker = subprocess.Popen(request["command"], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  env=env, start_new_session=True, preexec_fn=child_limits)
        report["worker_pid"] = worker.pid
        report["stage"] = "worker-running"
        metadata_used += 2 * _exclusive_json(attempt / "worker.json", {"pid": worker.pid}, 1024)
        last_sample = time.monotonic()
        # A first snapshot is useful even if a phase dies before five seconds.
        last_snapshot = started
        while True:
            _, descendants = sample()
            reap()
            if worker.returncode is not None:
                if worker.returncode != 0:
                    raise RuntimeError(f"worker exited with {worker.returncode}")
                if descendants - {worker.pid}:
                    raise RuntimeError("worker exited with lingering descendants")
                break
            time.sleep(min(profile.poll_ms / 1000, max(0, deadline - time.monotonic())))
        report["stage"] = "cold-verification"
        verified = _verify_manifest(attempt / "evidence", expected_cap_bytes=profile.worker_evidence_bytes,
                                    expected_profile_name=profile.name, deadline_monotonic=deadline,
                                    resource_check=checkpoint)
        report.update(reason="cold verification passed; final acceptance pending",
                      worker_charged_bytes=verified.manifest["charged_bytes"],
                      verified_manifest_sha256=verified.manifest_sha256,
                      verified_manifest_size_bytes=verified.manifest_size_bytes)
    except Exception as exc:
        verified = None
        report["reason"] = f"{type(exc).__name__}: {str(exc)[:512]}"
    finally:
        if worker is not None:
            cleanup_deadline = time.monotonic() + 2
            while True:
                rows = _processes()
                descendants = _descendants(rows, os.getpid(), worker.pid)
                tracked.update({pid: rows[pid][2] for pid in descendants})
                try:
                    os.killpg(worker.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                for pid, birth in tracked.items():
                    if pid in rows and rows[pid][2] == birth:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                if not reap():
                    report["descendants_reaped"] = True
                    break
                if time.monotonic() >= cleanup_deadline:
                    verified = None
                    report.update(status="unresolved", reason="descendant cleanup incomplete", descendants_reaped=False)
                    break
                time.sleep(0.01)
        try:
            failure = _read_worker_failure(attempt)
            if failure is not None:
                verified = None
                report["worker_failure"] = failure
                report.update(status="unresolved", reason="worker reported a failure")
        except Exception as exc:
            verified = None
            report.update(status="unresolved", reason=f"invalid worker failure diagnostic: {type(exc).__name__}")
        report["last_stage"] = report.pop("stage", "unknown")
        report["phase_wall_seconds"] = time.monotonic() - started
        report["supervisor_cpu_seconds"] = sum(resource.getrusage(resource.RUSAGE_SELF)[:2])
        report["supervisor_kernel_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        report["supervisor_metadata_charge_bytes_before_report"] = metadata_used
        if snapshot_fd is not None:
            os.close(snapshot_fd)
        try:
            if verified is None:
                _exclusive_json(attempt / "result.json", report, report_limit)
            else:
                unchanged()
                report.update(status="provisional", reason="awaiting final launcher decision")
                _exclusive_json(attempt / "result.json", report, report_limit, before_publish=unchanged)
                unchanged()
                report_bytes = (attempt / "result.json").read_bytes()
                ready = {"schema": "hiroute-supervisor-decision-v1", "status": "ready",
                         "report_sha256": hashlib.sha256(report_bytes).hexdigest(), "report_size_bytes": len(report_bytes),
                         "manifest_sha256": verified.manifest_sha256, "manifest_size_bytes": verified.manifest_size_bytes}
                _exclusive_json(attempt / "supervisor-decision.json", ready, DECISION_BYTES, before_publish=unchanged)
                unchanged()
        except Exception as exc:
            report.update(status="unresolved", reason=f"final publication rejected: {type(exc).__name__}: {str(exc)[:256]}")
            _reject(attempt, report["reason"])
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
    return report


def _run_phase_locked(command: list[str], *, attempt_dir: Path | str, profile: RuntimeProfile,
                      cpu: int, context: PlanContext, entry_monotonic: float,
                      deadline_monotonic: float, admission_lock_fd: int | None,
                      admission_error: str | None, worker_cpus: tuple[int, ...] | None = None) -> dict:
    """Run only after external root admission; new attempt directory required.

    The caller is a control-only launcher. Its RSS is reported separately and is
    not included in the worker group limit. All binding/preflight/verification
    work must fit the supplied phase deadline. Cleanup may follow expiry.
    """
    if type(profile) is not RuntimeProfile or PROFILES.get(profile.name) != profile:
        raise ValueError("profile must exactly match a named fixed profile")
    if type(context) is not PlanContext or context.profile_name != profile.name:
        raise ValueError("pinned context must match profile")
    _worker_cpu_mask(profile, cpu, worker_cpus)
    if type(command) is not list or not command or any(type(x) is not str or not x or "\0" in x for x in command):
        raise ValueError("command must be an explicit argv list")
    for value in (entry_monotonic, deadline_monotonic):
        if type(value) is not float or not math.isfinite(value):
            raise ValueError("monotonic clocks must be finite floats")
    if entry_monotonic > time.monotonic() or not entry_monotonic < deadline_monotonic <= entry_monotonic + profile.wall_seconds:
        raise ValueError("deadline must be within the fixed profile wall budget")
    attempt = Path(os.path.abspath(attempt_dir))
    parent = _directory(attempt.parent, create=True)
    try:
        os.mkdir(attempt.name, mode=0o700, dir_fd=parent)
    finally:
        os.close(parent)
    request = {"command": command, "profile": asdict(profile), "cpu": cpu,
               "context": asdict(context), "entry_monotonic": entry_monotonic,
               "deadline_monotonic": deadline_monotonic,
               "admission_lock_fd": admission_lock_fd,
               "launcher_rss_bytes_at_entry": _processes()[os.getpid()][3]}
    if worker_cpus is not None:
        request["worker_cpus"] = list(worker_cpus)
    cpu_binding = {"cpu": cpu, "worker_cpus": list(worker_cpus)} if profile == BATCH_REPLAY else {}
    _exclusive_json(attempt / "request.json", request, profile.supervisor_evidence_bytes // 8)
    if admission_error is not None:
        report = {"schema": "hiroute-phase-v1", "status": "unresolved", "worker_pid": None,
                  "reason": admission_error, "phase_wall_seconds": time.monotonic() - entry_monotonic,
                  **cpu_binding}
        _exclusive_json(attempt / "result.json", report, DECISION_BYTES)
        _reject(attempt, admission_error)
        return report
    baseline_children = {pid for pid, row in _processes().items() if row[0] == os.getpid()}
    previous_subreaper = _subreaper_value()
    _prctl(36, 1)
    try:
        supervisor = subprocess.Popen([sys.executable, str(Path(__file__).absolute()), "--supervise", str(attempt)],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      start_new_session=True, pass_fds=(admission_lock_fd,))
    except Exception as exc:
        _prctl(36, previous_subreaper)
        report = {"schema": "hiroute-phase-v1", "status": "unresolved",
                  "reason": f"supervisor launch failed: {type(exc).__name__}: {str(exc)[:256]}",
                  **cpu_binding}
        _exclusive_json(attempt / "result.json", report, DECISION_BYTES)
        _reject(attempt, report["reason"])
        return report
    supervisor_reaped = True
    try:
        supervisor.wait(timeout=max(0, deadline_monotonic - time.monotonic()) + 5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(supervisor.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            supervisor.wait(timeout=2)
        except subprocess.TimeoutExpired:
            supervisor_reaped = False
    rows = _processes()
    groups = {row[1] for pid, row in rows.items()
              if row[0] == os.getpid() and pid not in baseline_children | {supervisor.pid}}
    groups.update(rows[pid][1] for pid in _descendants(rows, supervisor.pid, supervisor.pid))
    worker_path = attempt / "worker.json"
    if worker_path.exists():
        worker_record, _ = _read_json_bytes(worker_path, 1024)
        groups.add(_integer(worker_record["pid"], "worker pid"))
    groups.discard(os.getpgrp())
    descendants_reaped = _reap_launcher_groups(groups)
    if supervisor_reaped and descendants_reaped:
        _prctl(36, previous_subreaper)
    result_path = attempt / "result.json"
    if not result_path.exists():
        if result_path.with_name("result.json.partial").exists():
            result_path = attempt / "launcher-result.json"
        _exclusive_json(result_path, {"schema": "hiroute-phase-v1", "status": "unresolved",
                                     "reason": "supervisor failed without a final report",
                                     "phase_wall_seconds": time.monotonic() - entry_monotonic,
                                     **cpu_binding})
    report, _ = _read_json_bytes(result_path, METADATA_BYTES)
    if (not supervisor_reaped or not descendants_reaped or supervisor.returncode != 0 or
            report.get("status") != "provisional"):
        if report.get("status") == "provisional":
            report.update(status="unresolved", reason="supervisor did not finish successfully")
        if not supervisor_reaped or not descendants_reaped:
            report.update(status="unresolved", reason="launcher cleanup incomplete",
                          supervisor_reaped=supervisor_reaped, descendants_reaped=descendants_reaped)
        _reject(attempt, report["reason"])
        return report

    def checkpoint() -> None:
        _live_checks(profile, attempt, deadline_monotonic,
                     pending_metadata_bytes=min(METADATA_BYTES, profile.supervisor_evidence_bytes // 16) + 2 * DECISION_BYTES)

    try:
        checkpoint()
        report, ready_raw = _read_ready(attempt)
        verified = _verify_manifest(attempt / "evidence", expected_cap_bytes=profile.worker_evidence_bytes,
                                    expected_profile_name=profile.name, deadline_monotonic=deadline_monotonic,
                                    resource_check=checkpoint)
        if (verified.manifest_sha256 != report["verified_manifest_sha256"] or
                verified.manifest_size_bytes != report["verified_manifest_size_bytes"] or
                verified.manifest["charged_bytes"] != report["worker_charged_bytes"]):
            raise ValueError("manifest changed between supervisor and launcher decisions")

        def unchanged() -> None:
            checkpoint()
            verified.check_unchanged(checkpoint)
            _, current_ready = _read_ready(attempt)
            if current_ready != ready_raw:
                raise ValueError("supervisor decision changed before acceptance")
            checkpoint()

        unchanged()
        decision = {"schema": "hiroute-phase-decision-v1", "status": "completed",
                    "supervisor_decision_sha256": hashlib.sha256(ready_raw).hexdigest(),
                    "supervisor_exit_code": supervisor.returncode, "accepted_monotonic": time.monotonic()}
        _exclusive_json(attempt / "decision.json", decision, DECISION_BYTES, before_publish=unchanged)
        unchanged()
        _, decision_raw = _read_json_bytes(attempt / "decision.json", DECISION_BYTES)
        if decision_raw != _json(decision):
            raise ValueError("final decision changed before caller return")
        receipt = {"schema": "hiroute-caller-return-v1", "result_sha256": json.loads(ready_raw)["report_sha256"],
                   "decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
                   "manifest_sha256": verified.manifest_sha256, "manifest_size_bytes": verified.manifest_size_bytes,
                   "returned_monotonic": 0.0}
        result = dict(report, status="completed", reason="accepted final decision and cold-verified evidence",
                      phase_wall_seconds=0.0, acceptance_receipt=receipt)
        if len(_json(result)) + 128 > min(METADATA_BYTES, profile.supervisor_evidence_bytes // 16):
            raise ValueError("successful caller return exceeds reserved metadata headroom")
        unchanged()
        returned = time.monotonic()
        if returned >= deadline_monotonic:
            raise TimeoutError("phase expired before successful caller return")
        receipt["returned_monotonic"] = returned
        result["phase_wall_seconds"] = returned - entry_monotonic
        return result
    except Exception as exc:
        # Publication remains provisional until its post-write checks pass.
        # Removing an unaccepted decision prevents later readers trusting it even
        # if a failing disk cannot accommodate the reserved rejection record.
        try:
            (attempt / "decision.json").unlink()
        except FileNotFoundError:
            pass
        _reject(attempt, f"final acceptance rejected: {type(exc).__name__}: {str(exc)[:256]}")
        return dict(report, status="unresolved", reason=f"final acceptance rejected: {type(exc).__name__}: {str(exc)[:256]}")


def run_phase(command: list[str], *, attempt_dir: Path | str, profile: RuntimeProfile,
              cpu: int, context: PlanContext, entry_monotonic: float,
              deadline_monotonic: float, worker_cpus: tuple[int, ...] | None = None) -> dict:
    """Hold exclusive phase ownership through cleanup and final publication.

    PlanContext is not execution authorization. The external root must admit the
    phase first. Binding work must start at or after entry and fit its deadline.
    Batch replay requires five worker_cpus, ordered coordinator then four fresh
    children, disjoint from the supervisor's cpu. The trusted coordinator pins
    itself after spawning its children in the inherited worker process group.
    """
    lock_path = Path("/tmp") / f"hiroute-recorded-phase-{os.getuid()}.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | _NOFOLLOW, 0o600)
    try:
        error = None
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            error = f"BlockingIOError: another phase owns admission: {str(exc)[:128]}"
        return _run_phase_locked(command, attempt_dir=attempt_dir, profile=profile, cpu=cpu,
                                 context=context, entry_monotonic=entry_monotonic,
                                 deadline_monotonic=deadline_monotonic,
                                 admission_lock_fd=lock_fd if error is None else None,
                                 admission_error=error, worker_cpus=worker_cpus)
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--supervise":
        raise SystemExit("internal supervisor entry point only")
    _attempt = Path(sys.argv[2])
    _supervise(json.loads((_attempt / "request.json").read_text()), _attempt)
