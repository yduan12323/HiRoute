"""Reviewed, resume-safe parallel continuation for the frozen M5-D rows.

This controller is an orchestration amendment. It invokes the frozen row
runner unchanged and never changes row identities or per-row resource limits.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import sys
import time
import types
import uuid

WORKERS_MAX = 5
WORKERS_START = 4
RAMP_AFTER_DURABLE_RECEIPTS = 4
ROW_CPU_RESERVATION_NS = 610 * 10**9
HOST_CPU_GUARD_NS = 60 * 10**9
ROW_WALL_SECONDS = 600
ROW_MEMORY_BYTES = 8 * 1024**3
HOST_MEMORY_RESERVE_BYTES = 8 * 1024**3
MAIN_CPU_CEILING_NS = 117000 * 10**9
FINALIZE_CPU_GUARD_NS = 60 * 10**9
PARALLEL_STATE_SCHEMA = "hiroute.m5d.parallel_continuation_state.v3"
AMENDMENT_SCHEMA = "hiroute.m5d.parallel_continuation_amendment.v3"
OLD_MAIN_PID = 2286454
OLD_MAIN_SOURCE = Path("/home/dy/HiRoute/m5d_main_9e52c05")
OLD_MAIN_OUTPUT = Path("/home/dy/HiRoute/m5d_main_a99f534_20261011")
OLD_MAIN_OBSERVED_UNIT = "hiroute-m5d-e90e6586228344ae87393389e149c470.service"
TRUSTED_PYTHON = Path("/home/dy/miniconda3/envs/hiroute/bin/python3.11")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(Path(path).read_bytes())


def stable_row_file(path: Path, row_out: Path) -> tuple[bytes, str]:
    path, row_out = Path(path), Path(row_out)
    row_info = os.lstat(row_out)
    if stat.S_ISLNK(row_info.st_mode) or not stat.S_ISDIR(row_info.st_mode):
        raise ValueError("Row output is not a real directory")
    info = os.lstat(path)
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or
            info.st_nlink != 1 or path.parent.resolve(strict=True) != row_out.resolve(strict=True)):
        raise ValueError("Row evidence is not a unique row-local regular file")
    raw = path.read_bytes()
    after = os.lstat(path)
    if ((info.st_dev, info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns,
         info.st_ctime_ns) !=
        (after.st_dev, after.st_ino, after.st_nlink, after.st_size, after.st_mtime_ns,
         after.st_ctime_ns)):
        raise ValueError("Row evidence changed while being checked")
    return raw, sha_bytes(raw)


def canon(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def host_cpu_ns() -> int:
    """This controller plus waited systemd-run/systemctl children."""
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return round(1e9 * (own.ru_utime + own.ru_stime +
                        children.ru_utime + children.ru_stime))


def save_atomic(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".next")
    with temporary.open("x") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_receipt_sha(receipt, row_out: Path) -> str:
    path = Path(receipt.receipt_path)
    raw, digest = stable_row_file(path, row_out)
    if json.loads(raw) != asdict(receipt):
        raise ValueError("Durable supervisor receipt differs from the returned receipt")
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    fsync_directory(row_out)
    return digest


def durable_claim_sha(row_out: Path, claim: dict) -> str:
    path = Path(row_out) / "parallel_claim.json"
    raw, digest = stable_row_file(path, row_out)
    if raw != json.dumps(claim, sort_keys=True).encode() + b"\n" or json.loads(raw) != claim:
        raise ValueError("Durable row claim differs from the admitted row")
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    fsync_directory(row_out)
    return digest


def validate_supervisor_binding(source: Path, source_hashes: dict):
    relative = "src/timecut5/systemd_supervisor.py"
    expected = source_hashes.get(relative)
    target = (Path(source) / relative).resolve(strict=True)
    raw = target.read_bytes()
    if (not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None or
            sha_bytes(raw) != expected):
        raise ValueError("M5-D supervisor differs from the frozen source hash")
    module = types.ModuleType("_hiroute_verified_m5d_supervisor_" + uuid.uuid4().hex)
    module.__file__ = str(target)
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(target), "exec"), module.__dict__)
    except Exception:
        sys.modules.pop(module.__name__, None)
        raise
    if sha_file(target) != expected:
        raise ValueError("M5-D supervisor changed while being loaded")
    runner = getattr(module, "run_m5d_phase", None)
    if (not callable(runner) or
            Path(runner.__code__.co_filename).resolve(strict=True) != target):
        raise ValueError("Verified M5-D supervisor entry point is missing")
    return runner


def validate_python_runtime(handoff: dict) -> str:
    expected = handoff.get("python_runtime")
    if type(expected) is not dict or set(expected) != {
            "executable_path", "executable_sha256", "implementation", "version", "cache_tag"}:
        raise ValueError("Handoff lacks the complete verified Python runtime fingerprint")
    executable = Path(sys.executable).resolve(strict=True)
    if (str(executable) != str(TRUSTED_PYTHON.resolve()) or
            expected.get("executable_path") != str(executable) or
            expected.get("executable_sha256") != sha_file(executable) or
            expected.get("implementation") != sys.implementation.name or
            expected.get("version") != sys.version.split()[0] or
            expected.get("cache_tag") != getattr(sys.implementation, "cache_tag", None)):
        raise ValueError("Running Python differs from the previously verified runtime fingerprint")
    return str(executable)


def advance_state_prefix(rows, state, ledger, manifest_sha: str, state_path: Path) -> None:
    """Commit only a contiguous manifest prefix; ledger receipts can finish out of order."""
    index = assert_prefix(rows, state)
    while index < len(rows):
        row_id = rows[index]["row_id"]
        completed = ledger["completed"].get(row_id)
        if completed is None:
            break
        state["rows"][row_id] = dict(completed["row_result"])
        index += 1
    state["charged_cpu_ns"] = ledger["charged_cpu_ns"]
    state["phase_sha256"] = manifest_sha
    save_atomic(state_path, state)


def fixed_rows(manifest):
    rows = manifest.get("rows")
    if (not isinstance(rows, list) or len(rows) != 192 or
            any(type(row) is not dict or type(row.get("row_id")) is not str or
                row["row_id"] in (".", "..") or
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", row["row_id"]) is None
                for row in rows) or
            len({row["row_id"] for row in rows}) != 192):
        raise ValueError("The frozen 192-row denominator is required")
    return rows


def assert_prefix(rows, main_state):
    ids = [row["row_id"] for row in rows]
    completed = set(main_state.get("rows", {}))
    if len(completed) > len(ids) or completed != set(ids[:len(completed)]):
        raise ValueError("Main state is not the unique frozen manifest prefix")
    return len(completed)


def effective_cpu_count() -> int:
    if hasattr(os, "sched_getaffinity"):
        return max(1, len(os.sched_getaffinity(0)))
    return max(1, os.cpu_count() or 1)


def mem_available_bytes(meminfo_path: Path = Path("/proc/meminfo")) -> int:
    for line in Path(meminfo_path).read_text().splitlines():
        key, sep, value = line.partition(":")
        if sep and key == "MemAvailable":
            fields = value.split()
            if len(fields) != 2 or fields[1] != "kB" or not fields[0].isdigit():
                break
            return int(fields[0]) * 1024
    raise RuntimeError("MemAvailable could not be read in bytes")


def memory_admission(mem_available: int, active_memory_current: list[int]) -> dict:
    if (type(mem_available) is not int or mem_available < 0 or
            type(active_memory_current) is not list or
            any(type(value) is not int or value < 0 for value in active_memory_current)):
        raise ValueError("Invalid cgroup memory admission sample")
    remaining = [max(0, ROW_MEMORY_BYTES - value) for value in active_memory_current]
    required = HOST_MEMORY_RESERVE_BYTES + ROW_MEMORY_BYTES + sum(remaining)
    return {"mem_available_bytes": mem_available,
        "host_memory_reserve_bytes": HOST_MEMORY_RESERVE_BYTES,
        "new_row_memory_bytes": ROW_MEMORY_BYTES,
        "active_memory_current_bytes": list(active_memory_current),
        "active_remaining_to_cap_bytes": remaining,
        "required_mem_available_bytes": required,
        "admitted": mem_available >= required}


def cgroup_memory_sample(unit: str, cgroup_root: Path = Path("/sys/fs/cgroup")) -> dict:
    result = subprocess.run(["systemctl", "--user", "show", unit, "--no-pager",
        "-p", "ActiveState", "-p", "ControlGroup", "-p", "MemoryMax"],
        check=True, text=True, capture_output=True, timeout=5)
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    control_group = fields.get("ControlGroup", "")
    if (fields.get("ActiveState") != "active" or
            fields.get("MemoryMax") != str(ROW_MEMORY_BYTES) or
            not control_group.startswith("/user.slice/") or ".." in Path(control_group).parts):
        raise RuntimeError("Active row cgroup memory limit or identity could not be verified")
    root = Path(cgroup_root).resolve(strict=True)
    group = (root / control_group.lstrip("/")).resolve(strict=True)
    if root not in group.parents:
        raise RuntimeError("Row cgroup escaped the cgroup root")
    memory_current_path = group / "memory.current"
    memory_max_path = group / "memory.max"
    current_raw = memory_current_path.read_text().strip()
    maximum_raw = memory_max_path.read_text().strip()
    if not current_raw.isdigit() or maximum_raw != str(ROW_MEMORY_BYTES):
        raise RuntimeError("Row cgroup v2 memory.current or memory.max is invalid")
    return {"unit": unit, "control_group": control_group,
        "memory_current_bytes": int(current_raw), "memory_max_bytes": int(maximum_raw),
        "memory_current_path": str(memory_current_path)}


def active_memory_samples(active: dict) -> tuple[list[dict], bool]:
    samples = []
    valid = True
    for future, (row, row_out, _token) in active.items():
        if future.done():
            # A completed Future remains active until its receipt and cleanup
            # are reconciled. Reserve the whole cap and surface exceptions so
            # a completion cannot silently free admission headroom.
            try:
                error = future.exception()
            except Exception as caught:
                error = caught
            samples.append({"row_id": row["row_id"], "unit": None,
                "memory_current_bytes": 0, "memory_max_bytes": ROW_MEMORY_BYTES,
                "memory_current_path": None, "source": "unreconciled-future-full-cap-reserve"})
            if error is not None:
                valid = False
            continue
        candidates = sorted(row_out.glob("hiroute-m5d-*.stdout"))
        if len(candidates) > 1:
            raise RuntimeError("More than one supervisor unit is bound to an active row")
        if not candidates:
            # Before systemd creates the unit, reserve the active row's whole
            # memory cap; this is more conservative than an unknown RSS value.
            samples.append({"row_id": row["row_id"], "unit": None,
                "memory_current_bytes": 0, "memory_max_bytes": ROW_MEMORY_BYTES,
                "memory_current_path": None, "source": "pre-cgroup-full-cap-reserve"})
            continue
        unit = candidates[0].name.removesuffix(".stdout")
        try:
            sample = cgroup_memory_sample(unit)
        except Exception as error:
            samples.append({"row_id": row["row_id"], "unit": unit,
                "sample_error": str(error), "source": "systemd-cgroup-v2-memory.current"})
            valid = False
            continue
        sample.update(row_id=row["row_id"], source="systemd-cgroup-v2-memory.current")
        samples.append(sample)
    return samples, valid


def reconcile_completed_futures(active: dict, reconcile) -> bool:
    """Collect every finished worker before another row admission."""
    finished = [future for future in active if future.done()]
    for future in finished:
        reconcile(future)
    return bool(finished)


def budget_admission(charged_cpu_ns: int, remaining_rows: int,
                     outside_available_seconds: int | float,
                     host_cpu_ns_used: int) -> dict:
    if (type(charged_cpu_ns) is not int or charged_cpu_ns < 0 or
            type(remaining_rows) is not int or remaining_rows < 0 or
            type(outside_available_seconds) not in (int, float) or
            outside_available_seconds < 0 or
            type(host_cpu_ns_used) is not int or host_cpu_ns_used < 0):
        raise ValueError("Invalid parallel continuation budget sample")
    outside_available_ns = int(Decimal(str(outside_available_seconds)) * 10**9)
    cgroup_required_ns = charged_cpu_ns + remaining_rows * ROW_CPU_RESERVATION_NS
    outside_required_ns = (remaining_rows * HOST_CPU_GUARD_NS + FINALIZE_CPU_GUARD_NS)
    outside_left_ns = max(0, outside_available_ns - host_cpu_ns_used)
    return {"charged_cpu_ns": charged_cpu_ns, "remaining_row_count": remaining_rows,
        "row_cpu_reservation_ns": ROW_CPU_RESERVATION_NS,
        "cgroup_required_ns": cgroup_required_ns,
        "cgroup_ceiling_ns": MAIN_CPU_CEILING_NS,
        "outside_available_ns": outside_available_ns,
        "outside_used_ns": host_cpu_ns_used,
        "outside_left_ns": outside_left_ns,
        "outside_required_ns": outside_required_ns,
        "admitted": (cgroup_required_ns <= MAIN_CPU_CEILING_NS and
                     outside_left_ns >= outside_required_ns)}


def paused_cpu_budget_failure(cpu_count: int, charged_cpu_ns: int, remaining_rows: int,
                              outside_available_seconds: int | float,
                              host_cpu_ns_used: int) -> tuple[str | None, dict]:
    sample = budget_admission(charged_cpu_ns, remaining_rows,
                              outside_available_seconds, host_cpu_ns_used)
    if cpu_count < WORKERS_START and not sample["admitted"]:
        return "budget_exhausted", sample
    return None, sample


def _is_supervisor_or_verification_failure(completed: dict) -> bool:
    status = completed.get("status", "")
    return (not isinstance(status, str) or
            status.startswith("supervisor_failed") or
            status.startswith("verification_failed"))


def ramp_receipts_ready(launch_order: list[str], completed: dict,
                        failure: str | None = None) -> bool:
    if failure is not None or len(launch_order) < RAMP_AFTER_DURABLE_RECEIPTS:
        return False
    first_four = launch_order[:RAMP_AFTER_DURABLE_RECEIPTS]
    return (all(row_id in completed and completed[row_id].get("receipt_durable") is True and
                not _is_supervisor_or_verification_failure(completed[row_id])
                for row_id in first_four) and
            not any(_is_supervisor_or_verification_failure(row)
                    for row in completed.values()))


def worker_target(cpu_count: int, launch_order: list[str], completed: dict,
                  failure: str | None = None) -> int:
    if type(cpu_count) is not int or cpu_count < WORKERS_START:
        return 0
    if (cpu_count >= WORKERS_MAX and
            ramp_receipts_ready(launch_order, completed, failure)):
        return WORKERS_MAX
    return WORKERS_START


def durable_ramp_receipts(launch_order: list[str], completed: dict) -> tuple[list[str], bool]:
    first_four = launch_order[:RAMP_AFTER_DURABLE_RECEIPTS]
    if len(first_four) != RAMP_AFTER_DURABLE_RECEIPTS:
        return first_four, False
    for row_id in first_four:
        record = completed.get(row_id, {})
        path = record.get("receipt_path")
        expected = record.get("receipt_sha256")
        if (record.get("receipt_durable") is not True or not isinstance(path, str) or
                not isinstance(expected, str)):
            return first_four, False
        try:
            actual = Path(path)
            info = os.lstat(actual)
            if (actual.is_symlink() or not actual.is_file() or info.st_nlink != 1 or
                    sha_file(actual) != expected):
                return first_four, False
            if json.loads(actual.read_bytes()).get("receipt_path") != path:
                return first_four, False
        except OSError:
            return first_four, False
    return first_four, True


def validate_amendment(amendment, manifest_sha: str, controller_sha: str):
    if (amendment.get("schema") != AMENDMENT_SCHEMA or
            amendment.get("manifest_sha256") != manifest_sha or
            amendment.get("controller_sha256") != controller_sha or
            amendment.get("max_workers") != WORKERS_MAX or
            amendment.get("initial_workers") != WORKERS_START or
            amendment.get("ramp_after_durable_receipts") != RAMP_AFTER_DURABLE_RECEIPTS or
            amendment.get("ramp_ignores_row_outcomes") is not True or
            amendment.get("ramp_requires_clean_receipts") is not True or
            amendment.get("ramp_requires_five_worker_memory_admission") is not True or
            amendment.get("ramp_requires_budget_admission") is not True or
            amendment.get("cpu_quota_percent_per_row") != 100 or
            amendment.get("wall_seconds_per_row") != ROW_WALL_SECONDS or
            amendment.get("memory_bytes_per_row") != ROW_MEMORY_BYTES or
            amendment.get("host_memory_reserve_bytes") != HOST_MEMORY_RESERVE_BYTES or
            amendment.get("host_cpu_guard_seconds_per_row") != 60 or
            amendment.get("finalize_cpu_guard_seconds") != 60 or
            amendment.get("old_scheduler_pid") != OLD_MAIN_PID or
            amendment.get("old_scheduler_source") != str(OLD_MAIN_SOURCE) or
            amendment.get("old_scheduler_output") != str(OLD_MAIN_OUTPUT) or
            amendment.get("trusted_python_path") != str(TRUSTED_PYTHON) or
            amendment.get("memory_current_source") != "systemd-cgroup-v2-memory.current"):
        raise ValueError("Parallel continuation amendment or source binding differs")


def validate_handoff(handoff, manifest_sha: str):
    identity = handoff.get("old_scheduler_identity")
    identity_fields = {"pid", "start_ticks", "source_root", "output_root", "cmdline_sha256"}
    owned = handoff.get("old_owned_units")
    runtime = handoff.get("python_runtime")
    if (handoff.get("schema") != "hiroute.m5d.parallel_handoff.v2" or
            handoff.get("manifest_sha256") != manifest_sha or
            handoff.get("old_scheduler_gone") is not True or
            handoff.get("old_main_units_empty") is not True or
            handoff.get("review_approved") is not True or
            type(handoff.get("outside_main_available_cpu_seconds")) not in (int, float) or
            handoff["outside_main_available_cpu_seconds"] < 0 or
            type(handoff.get("main_host_cpu_ns")) is not int or
            handoff["main_host_cpu_ns"] < 0 or
            type(identity) is not dict or set(identity) != identity_fields or
            identity.get("pid") != OLD_MAIN_PID or
            type(identity.get("start_ticks")) is not int or identity["start_ticks"] <= 0 or
            identity.get("source_root") != str(OLD_MAIN_SOURCE) or
            identity.get("output_root") != str(OLD_MAIN_OUTPUT) or
            not isinstance(identity.get("cmdline_sha256"), str) or
            re.fullmatch(r"[0-9a-f]{64}", identity["cmdline_sha256"]) is None or
            handoff.get("old_scheduler_identity_sha256") != sha_bytes(canon(identity)) or
            type(owned) is not list or not owned or
            type(runtime) is not dict or
            runtime.get("executable_path") != str(TRUSTED_PYTHON)):
        raise ValueError("Reviewed handoff lacks the exact old-process and Python runtime bindings")
    names = []
    for item in owned:
        if (type(item) is not dict or set(item) != {"unit", "control_group"} or
                not isinstance(item.get("unit"), str) or
                re.fullmatch(r"hiroute-m5d-[0-9a-f]{32}\.service", item["unit"]) is None or
                not isinstance(item.get("control_group"), str)):
            raise ValueError("Handoff old-unit inventory is malformed")
        names.append(item["unit"])
    if (len(names) != len(set(names)) or OLD_MAIN_OBSERVED_UNIT not in names):
        raise ValueError("Handoff does not bind the observed old row-unit inventory")
    return identity, owned


def proc_start_ticks(pid: int, proc_root: Path = Path("/proc")) -> int | None:
    try:
        raw = (Path(proc_root) / str(pid) / "stat").read_text()
    except FileNotFoundError:
        return None
    close = raw.rfind(")")
    fields = raw[close + 2:].split() if close >= 0 else []
    if len(fields) <= 19 or not fields[19].isdigit():
        raise RuntimeError("Process start identity could not be read")
    return int(fields[19])


def current_main_processes(identity: dict) -> bool:
    pid = identity["pid"]
    if proc_start_ticks(pid) == identity["start_ticks"]:
        return True
    text = subprocess.check_output(["ps", "-eo", "args="], text=True)
    return any("scripts/m5d_main_batch.py" in line and
               str(OLD_MAIN_SOURCE) in line and str(OLD_MAIN_OUTPUT) in line
               for line in text.splitlines())


def _cgroup_populated(control_group: str, cgroup_root: Path = Path("/sys/fs/cgroup")) -> bool:
    if control_group == "":
        return False
    if (not control_group.startswith("/user.slice/") or
            ".." in Path(control_group).parts):
        raise RuntimeError("Invalid old row cgroup identity")
    root = Path(cgroup_root).resolve(strict=True)
    group = (root / control_group.lstrip("/")).resolve()
    if root not in group.parents:
        raise RuntimeError("Old row cgroup escaped the cgroup root")
    events = group / "cgroup.events"
    if not events.exists():
        return False
    fields = dict(line.split() for line in events.read_text().splitlines())
    if fields.get("populated") not in ("0", "1"):
        raise RuntimeError("Old row cgroup population could not be verified")
    return fields["populated"] == "1"


def active_main_units() -> list[str]:
    lines = subprocess.check_output(["systemctl", "--user", "list-units",
        "--all", "--type=service", "--no-legend", "--plain"], text=True)
    units = []
    for line in lines.splitlines():
        fields = line.split()
        if not fields or re.fullmatch(r"hiroute-m5d-[0-9a-f]{32}\.service", fields[0]) is None:
            continue
        result = subprocess.check_output(["systemctl", "--user", "show", fields[0],
            "--no-pager", "-p", "ActiveState", "-p", "ControlGroup", "-p", "ExecStart"],
            text=True)
        properties = dict(item.split("=", 1) for item in result.splitlines() if "=" in item)
        if "m5d_main_row.py" not in properties.get("ExecStart", ""):
            continue
        active = properties.get("ActiveState") in ("active", "activating", "deactivating", "reloading")
        populated = _cgroup_populated(properties.get("ControlGroup", ""))
        if active or populated:
            units.append(fields[0])
    return units


def old_owned_units_empty(owned_units: list[dict]) -> bool:
    for item in owned_units:
        result = subprocess.run(["systemctl", "--user", "show", item["unit"],
            "--no-pager", "-p", "LoadState", "-p", "ActiveState", "-p",
            "ControlGroup", "-p", "ExecStart"], check=True, text=True,
            capture_output=True, timeout=5)
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        active = fields.get("ActiveState") in ("active", "activating", "deactivating", "reloading")
        control_group = fields.get("ControlGroup", "") or item["control_group"]
        exec_start = fields.get("ExecStart", "")
        if active or _cgroup_populated(control_group):
            return False
        if fields.get("LoadState") not in ("loaded", "not-found"):
            return False
        if fields.get("LoadState") != "not-found" and (
                "m5d_main_row.py" not in exec_start or
                str(OLD_MAIN_SOURCE) not in exec_start):
            return False
    return True


def validate_completed_evidence(rows, state: dict, ledger: dict, output: Path,
                                manifest_sha: str, amendment_sha: str) -> None:
    completed = ledger.get("completed")
    launch_order = ledger.get("launch_order")
    admissions = ledger.get("admissions")
    start_index = ledger.get("start_index")
    if (ledger.get("schema") != PARALLEL_STATE_SCHEMA or
            type(start_index) is not int or not 0 <= start_index <= len(rows) or
            type(completed) is not dict or type(launch_order) is not list or
            type(admissions) is not list or len(admissions) != len(launch_order) or
            len(launch_order) != len(set(launch_order)) or set(completed) != set(launch_order)):
        raise ValueError("Continuation admission and completion inventory is incomplete")
    row_index = {row["row_id"]: index for index, row in enumerate(rows)}
    if any(type(row_id) is not str or row_id not in row_index or
           row_index[row_id] < start_index for row_id in launch_order):
        raise ValueError("Continuation ledger names a row outside its fixed suffix")
    if [row_index[row_id] for row_id in launch_order] != sorted(
            row_index[row_id] for row_id in launch_order):
        raise ValueError("Continuation admission order differs from the frozen manifest")

    for row_id, admission in zip(launch_order, admissions):
        record = completed[row_id]
        if (type(admission) is not dict or admission.get("row_id") != row_id or
                admission.get("manifest_index") != row_index[row_id] or
                record.get("manifest_index") != row_index[row_id] or
                record.get("admission_sha256") != sha_bytes(canon(admission)) or
                type(record.get("row_result")) is not dict or
                record.get("status") != record["row_result"].get("status") or
                record["row_result"].get("denominator_included") is not True or
                type(record.get("receipt_durable")) is not bool or
                type(record.get("charged_cpu_ns")) is not int or record["charged_cpu_ns"] < 0):
            raise ValueError(f"Continuation completion fields differ for {row_id}")

        token = record.get("claim_token")
        claim_sha = record.get("claim_sha256")
        if (not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{32}", token) is None or
                not isinstance(claim_sha, str) or re.fullmatch(r"[0-9a-f]{64}", claim_sha) is None):
            raise ValueError(f"Continuation row claim is not pinned for {row_id}")
        claim = {"schema": "hiroute.m5d.parallel_row_claim.v2",
            "row_id": row_id, "manifest_sha256": manifest_sha,
            "amendment_sha256": amendment_sha, "claim": token,
            "manifest_index": row_index[row_id],
            "admission_sha256": record["admission_sha256"],
            "regime": admission.get("regime")}
        row_out = Path(output) / row_id
        if durable_claim_sha(row_out, claim) != claim_sha:
            raise ValueError(f"Durable row claim hash differs for {row_id}")

        if not record["receipt_durable"]:
            if (not _is_supervisor_or_verification_failure(record) or
                    record.get("receipt_path") is not None or
                    record.get("receipt_sha256") is not None or not ledger.get("stopped")):
                raise ValueError(f"Unreceipted completion is not a terminal failure for {row_id}")
            continue

        receipt_path = record.get("receipt_path")
        receipt_sha = record.get("receipt_sha256")
        if (not isinstance(receipt_path, str) or not Path(receipt_path).is_absolute() or
                not isinstance(receipt_sha, str) or
                re.fullmatch(r"[0-9a-f]{64}", receipt_sha) is None or
                record["row_result"].get("receipt_path") != receipt_path):
            raise ValueError(f"Durable supervisor receipt is not pinned for {row_id}")
        raw, digest = stable_row_file(Path(receipt_path), row_out)
        if digest != receipt_sha:
            raise ValueError(f"Durable supervisor receipt hash differs for {row_id}")
        receipt = json.loads(raw)
        required_receipt_fields = {"unit", "control_group", "result", "exit_status",
            "cpu_usage_ns", "memory_peak_bytes", "memory_limit_bytes", "wall_elapsed_ns",
            "stdout_path", "stderr_path", "receipt_path", "cpu_quota_percent",
            "thread_environment"}
        if (type(receipt) is not dict or set(receipt) != required_receipt_fields or
                receipt.get("receipt_path") != receipt_path or
                Path(receipt_path).name != receipt.get("unit", "") + ".receipt.json" or
                re.fullmatch(r"hiroute-m5d-[0-9a-f]{32}\.service", receipt.get("unit", "")) is None or
                record["row_result"].get("cgroup_cpu_usage_ns") != receipt.get("cpu_usage_ns") or
                record["row_result"].get("cgroup_memory_peak_bytes") != receipt.get("memory_peak_bytes") or
                record["row_result"].get("cgroup_memory_limit_bytes") != receipt.get("memory_limit_bytes") or
                record["row_result"].get("wall_elapsed_ns") != receipt.get("wall_elapsed_ns")):
            raise ValueError(f"Supervisor receipt contents differ from completion for {row_id}")
        cpu = receipt.get("cpu_usage_ns")
        expected_charge = cpu if type(cpu) is int and cpu >= 0 else ROW_CPU_RESERVATION_NS
        if record.get("charged_cpu_ns") != expected_charge:
            raise ValueError(f"Supervisor CPU charge differs from receipt for {row_id}")
        if receipt.get("result") == "success" and receipt.get("exit_status") == 0:
            status_path = row_out / "status.json"
            if status_path.exists():
                status_bytes, _ = stable_row_file(status_path, row_out)
                status = json.loads(status_bytes)
                expected_status = record["row_result"].get("source_row_status",
                    record["row_result"].get("pre_pair_status"))
                if (type(status) is not dict or any(
                        (expected_status if key == "status" and
                         expected_status is not None else record["row_result"].get(key)) != value
                        for key, value in status.items())):
                    raise ValueError(f"Row status bytes differ from completion for {row_id}")
            elif record["row_result"].get("status") != "verification_failed_missing_status":
                raise ValueError(f"Missing row status is not recorded as failure for {row_id}")
    if (type(ledger.get("charged_cpu_ns_at_start")) is not int or
            type(ledger.get("charged_cpu_ns")) is not int or
            ledger["charged_cpu_ns_at_start"] < 0 or
            ledger["charged_cpu_ns"] != ledger["charged_cpu_ns_at_start"] + sum(
                record["charged_cpu_ns"] for record in completed.values()) or
            type(state.get("charged_cpu_ns")) is not int or
            state["charged_cpu_ns"] > ledger["charged_cpu_ns"]):
        raise ValueError("Continuation cumulative CPU charge differs from durable completions")
    for row_id, result in state.get("rows", {}).items():
        if row_index[row_id] < start_index:
            continue
        record = completed.get(row_id)
        if record is not None:
            if result != record["row_result"]:
                raise ValueError(f"Main state differs from durable completion for {row_id}")
        elif (not ledger.get("stopped") or type(result) is not dict or
                result.get("status") not in ("budget_exhausted_unrun", "verification_blocked_unrun") or
                result.get("denominator_included") is not True):
            raise ValueError(f"Main state contains an unbound suffix row {row_id}")
    if ledger.get("stopped") is True and state.get("stopped") is not True:
        raise ValueError("Stopped continuation ledger lacks a stopped main state")
    if ledger.get("stopped") is not True and state.get("stopped") is True:
        raise ValueError("Main state stopped without a terminal continuation ledger")


def phase_name(row_out: Path):
    path = row_out / "phase.jsonl"
    lines = path.read_bytes().splitlines() if path.exists() else []
    return json.loads(lines[-1])["phase"] if lines else None


def completed_status(receipt, row_out: Path):
    if receipt.result == "success" and receipt.exit_status == 0:
        path = row_out / "status.json"
        return (json.loads(path.read_bytes()) if path.exists() else
                {"status": "verification_failed_missing_status"})
    if receipt.result == "timeout":
        return {"status": "time_limit"}
    if receipt.result in ("oom-kill", "memory-limit"):
        return {"status": "memory_limit"}
    return {"status": "verification_failed_process_exit",
            "unit_result": receipt.result, "exit_status": receipt.exit_status}


def verify_pair_consistency(rows, states):
    """Fail closed if two completed exact method outputs disagree."""
    for row in rows:
        if row["method"] != "hier":
            continue
        flat_id = row["row_id"].removesuffix("_hier") + "_flat"
        flat = states.get(flat_id, {})
        hier = states.get(row["row_id"], {})
        if "exact_outcome" not in flat or "exact_outcome" not in hier:
            continue
        if (flat["exact_outcome"] != hier["exact_outcome"] or
                flat.get("seed_j") != hier.get("seed_j") or
                flat.get("certified_depth") != hier.get("certified_depth") or
                flat.get("prewarm_sha256") != hier.get("prewarm_sha256")):
            return flat_id, row["row_id"]
    return None


def run(source: Path, graph_dir: Path, pool_path: Path, queries_path: Path,
        full_path: Path, manifest_path: Path, amendment_path: Path,
        handoff_path: Path, output: Path):
    process_cpu_baseline = host_cpu_ns()
    source, output = Path(source).resolve(strict=True), Path(output).resolve(strict=True)
    manifest_bytes = Path(manifest_path).read_bytes()
    manifest_sha = sha_bytes(manifest_bytes)
    manifest = json.loads(manifest_bytes)
    rows = fixed_rows(manifest)
    if (manifest.get("schema") != "hiroute.m5d.frozen_main_phase.v1" or
            manifest.get("wall_seconds") != ROW_WALL_SECONDS or
            manifest.get("memory_bytes") != ROW_MEMORY_BYTES or
            manifest.get("main_cpu_seconds_ceiling") != 117000):
        raise ValueError("Frozen numerical phase limits differ")
    amendment_bytes = Path(amendment_path).read_bytes()
    amendment_sha = sha_bytes(amendment_bytes)
    amendment = json.loads(amendment_bytes)
    controller_sha = sha_file(Path(__file__).resolve())
    validate_amendment(amendment, manifest_sha, controller_sha)
    supervisor_runner = validate_supervisor_binding(source, manifest.get("source_sha256", {}))
    for name, expected in manifest["source_sha256"].items():
        if sha_file(source / name) != expected:
            raise ValueError(f"Frozen numerical source differs: {name}")
    for name, path in (("queries", queries_path), ("pools", pool_path),
                       ("full_universes", full_path)):
        if sha_file(Path(path)) != manifest["input_sha256"][name]:
            raise ValueError(f"Frozen input differs: {name}")

    state_path = output / "state.json"
    state_bytes = state_path.read_bytes()
    state = json.loads(state_bytes)
    if state.get("schema") != "hiroute.m5d.main_batch_state.v1" or \
            state.get("phase_sha256") != manifest_sha:
        raise ValueError("Main batch state differs from frozen manifest")
    start_index = assert_prefix(rows, state)
    if type(state.get("charged_cpu_ns")) is not int or state["charged_cpu_ns"] < 0:
        raise ValueError("Main CPU charge must be a nonnegative integer")
    if any(_is_supervisor_or_verification_failure(row)
           for row in state["rows"].values()):
        raise ValueError("Existing main state contains a supervisor or verification failure")
    ledger_path = output / "parallel_continuation_state.json"
    lock_path = output / "parallel_continuation.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handoff_bytes = Path(handoff_path).read_bytes()
        handoff_sha = sha_bytes(handoff_bytes)
        handoff = json.loads(handoff_bytes)
        old_identity, old_owned_units = validate_handoff(handoff, manifest_sha)
        runtime_executable = validate_python_runtime(handoff)
        if (current_main_processes(old_identity) or active_main_units() or
                not old_owned_units_empty(old_owned_units)):
            raise ValueError("Old dispatcher or one of its row cgroups is still active")
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_bytes())
            if (ledger.get("schema") != PARALLEL_STATE_SCHEMA or
                    ledger.get("manifest_sha256") != manifest_sha or
                    ledger.get("amendment_sha256") != amendment_sha or
                    ledger.get("handoff_sha256") != handoff_sha or
                    type(ledger.get("start_index")) is not int or
                    start_index < ledger["start_index"]):
                raise ValueError("Continuation resume bindings differ")
            if ledger.get("inflight"):
                raise ValueError("Interrupted in-flight rows need receipt review; refusing rerun")
            completed = ledger.get("completed")
            if (type(completed) is not dict or type(ledger.get("launch_order")) is not list or
                    type(ledger.get("admissions")) is not list or
                    type(ledger.get("ramp_events")) is not list or
                    type(ledger.get("charged_cpu_ns")) is not int):
                raise ValueError("Continuation ledger schema is incomplete")
            if (type(ledger.get("charged_cpu_ns_at_start")) is not int or
                    state["charged_cpu_ns"] < ledger["charged_cpu_ns_at_start"]):
                raise ValueError("Continuation starting CPU charge is invalid")
            if any(type(row.get("charged_cpu_ns")) is not int or row["charged_cpu_ns"] < 0
                   for row in completed.values()):
                raise ValueError("Continuation completion CPU charge is invalid")
            validate_completed_evidence(rows, state, ledger, output, manifest_sha, amendment_sha)
            if ledger.get("stopped"):
                return ledger
            advance_state_prefix(rows, state, ledger, manifest_sha, state_path)
        else:
            if handoff.get("main_state_sha256") != sha_bytes(state_bytes):
                raise ValueError("Handoff does not bind the exact terminal main state")
            ledger = {"schema": PARALLEL_STATE_SCHEMA,
                "manifest_sha256": manifest_sha,
                "amendment_sha256": amendment_sha,
                "handoff_sha256": handoff_sha,
                "start_index": start_index,
                "host_cpu_ns": 0,
                "charged_cpu_ns_at_start": state["charged_cpu_ns"],
                "charged_cpu_ns": state["charged_cpu_ns"],
                "completed": {}, "inflight": {}, "launch_order": [],
                "admissions": [], "ramp_events": [], "admission_pause_events": [],
                "admission_pause_open": None, "boundary_row_id": None,
                "stopped": False, "stop_reason": None}
        if state.get("stopped"):
            raise ValueError("Main denominator already marked terminal")
        if ledger["stopped"]:
            return ledger
        if state["stopped"]:
            raise ValueError("Main denominator already marked terminal")

        original_start_index = ledger["start_index"]
        pending = [row for index, row in enumerate(rows)
                   if index >= original_start_index and
                   row["row_id"] not in state["rows"] and
                   row["row_id"] not in ledger["completed"]]
        if not pending:
            if len(state["rows"]) != len(rows):
                raise ValueError("No uncompleted rows remain but the fixed denominator is incomplete")
            state["charged_cpu_ns"] = ledger["charged_cpu_ns"]
            state["stopped"] = True
            save_atomic(state_path, state)
            ledger["stopped"] = True
            ledger["stop_reason"] = "all_fixed_rows_completed"
            save_atomic(ledger_path, ledger)
            return ledger

        # The only permitted pre-existing output is the empty serial-boundary
        # directory, and it must be the first row in the handoff suffix.
        existing = []
        for row in pending:
            row_out = output / row["row_id"]
            if not row_out.exists():
                continue
            if row_out.is_symlink() or not row_out.is_dir() or any(row_out.iterdir()):
                raise ValueError(f"Unexpected nonempty row output: {row['row_id']}")
            existing.append(row["row_id"])
        if existing:
            if existing != [pending[0]["row_id"]] or (ledger["boundary_row_id"] not in
                    (None, pending[0]["row_id"])):
                raise ValueError("Only the empty first handoff-boundary row may be adopted")
            ledger["boundary_row_id"] = pending[0]["row_id"]
        elif ledger["boundary_row_id"] is not None and \
                ledger["boundary_row_id"] in {row["row_id"] for row in pending}:
            raise ValueError("Recorded boundary row directory disappeared")
        save_atomic(ledger_path, ledger)

        baseline_host_cpu = process_cpu_baseline
        prior_host_cpu = ledger["host_cpu_ns"]

        def update_host():
            ledger["host_cpu_ns"] = prior_host_cpu + max(0, host_cpu_ns() - baseline_host_cpu)

        active = {}
        cursor = 0
        pool_size = WORKERS_MAX
        row_index = {row["row_id"]: index for index, row in enumerate(rows)}
        failure = None

        def current_remaining_rows():
            return len(pending) - cursor + len(active)

        def close_admission_pause(row_id: str):
            opened = ledger.get("admission_pause_open")
            if opened is not None:
                opened["ended_monotonic_ns"] = time.monotonic_ns()
                opened["next_admitted_row_id"] = row_id
                ledger["admission_pause_open"] = None
                save_atomic(ledger_path, ledger)

        def pause_admission(reason: str, sample: dict):
            opened = ledger.get("admission_pause_open")
            if opened is None or opened.get("reason") != reason:
                if opened is not None:
                    opened["ended_monotonic_ns"] = time.monotonic_ns()
                event = {"reason": reason, "started_monotonic_ns": time.monotonic_ns(),
                         "resource_sample": sample}
                ledger["admission_pause_events"].append(event)
                ledger["admission_pause_open"] = event
                save_atomic(ledger_path, ledger)

        def record_completion(future):
            nonlocal failure
            row, row_out, token = active.pop(future)
            row_id = row["row_id"]
            inflight = ledger["inflight"].get(row_id)
            if inflight is None or inflight.get("claim") != token:
                raise ValueError("Completion does not match its durable row claim")
            claim = {"schema": "hiroute.m5d.parallel_row_claim.v2",
                "row_id": row_id, "manifest_sha256": manifest_sha,
                "amendment_sha256": amendment_sha, "claim": token,
                "manifest_index": row_index[row_id],
                "admission_sha256": inflight["admission_sha256"],
                "regime": inflight["regime"]}
            claim_sha = None
            claim_error = None
            try:
                claim_sha = durable_claim_sha(row_out, claim)
            except Exception as error:
                claim_error = str(error)
            receipt = None
            receipt_sha = None
            receipt_is_durable = False
            try:
                receipt = future.result()
                receipt_sha = durable_receipt_sha(receipt, row_out)
                receipt_is_durable = True
            except Exception as error:
                receipt_cpu = getattr(receipt, "cpu_usage_ns", None) if receipt is not None else None
                charged = (max(ROW_CPU_RESERVATION_NS, receipt_cpu)
                           if type(receipt_cpu) is int and receipt_cpu >= 0
                           else ROW_CPU_RESERVATION_NS)
                result = {"status": ("verification_failed_receipt_durability" if receipt is not None
                                     else "supervisor_failed_cpu_unknown"),
                    "error": str(error), "denominator_included": True,
                    "reached_phase": phase_name(row_out),
                    "conservative_cpu_charge_ns": charged}
                failure = result["status"]
            else:
                valid_cpu = type(receipt.cpu_usage_ns) is int and receipt.cpu_usage_ns >= 0
                charged = receipt.cpu_usage_ns if valid_cpu else ROW_CPU_RESERVATION_NS
                result = completed_status(receipt, row_out)
                result.update(denominator_included=True,
                    reached_phase=phase_name(row_out),
                    receipt_path=receipt.receipt_path,
                    cgroup_cpu_usage_ns=receipt.cpu_usage_ns,
                    cgroup_memory_peak_bytes=receipt.memory_peak_bytes,
                    cgroup_memory_limit_bytes=receipt.memory_limit_bytes,
                    wall_elapsed_ns=receipt.wall_elapsed_ns)
                expected_threads = {name: "1" for name in
                    ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS")}
                if (not valid_cpu or receipt.cpu_quota_percent != 100 or
                        receipt.cpu_usage_ns > ROW_CPU_RESERVATION_NS or
                        receipt.memory_limit_bytes != ROW_MEMORY_BYTES or
                        receipt.memory_peak_bytes > ROW_MEMORY_BYTES or
                        receipt.wall_elapsed_ns > (ROW_WALL_SECONDS + 10) * 10**9 or
                        receipt.thread_environment != expected_threads):
                    result.setdefault("source_row_status", result.get("status"))
                    result["status"] = "verification_failed_resource_contract"
                if _is_supervisor_or_verification_failure(result):
                    failure = result["status"]

            if claim_error is not None:
                result.setdefault("source_row_status", result.get("status"))
                result["status"] = "verification_failed_claim_durability"
                result["claim_error"] = claim_error
                failure = result["status"]

            result["batch_and_waited_child_cpu_ns"] = ledger["host_cpu_ns"]
            record = {"status": result["status"], "row_result": result,
                "charged_cpu_ns": charged,
                "claim_token": token, "claim_sha256": claim_sha,
                "receipt_durable": receipt_is_durable,
                "receipt_path": receipt.receipt_path if receipt_is_durable else None,
                "receipt_sha256": receipt_sha if receipt_is_durable else None,
                "manifest_index": row_index[row_id],
                "admission_sha256": inflight["admission_sha256"]}
            ledger["charged_cpu_ns"] += charged
            ledger["completed"][row_id] = record
            ledger["inflight"].pop(row_id)
            update_host()
            result["batch_and_waited_child_cpu_ns"] = ledger["host_cpu_ns"]

            views = dict(state["rows"])
            views.update({key: value["row_result"]
                          for key, value in ledger["completed"].items()})
            pair = verify_pair_consistency(rows, views)
            if pair:
                for pair_id in pair:
                    if pair_id in ledger["completed"]:
                        pair_result = ledger["completed"][pair_id]["row_result"]
                        pair_result.setdefault("source_row_status", pair_result.get("status"))
                        pair_result["pre_pair_status"] = pair_result.get("status")
                        ledger["completed"][pair_id]["status"] = \
                            "verification_failed_method_disagreement"
                        pair_result["status"] = "verification_failed_method_disagreement"
                    if pair_id in state["rows"]:
                        state["rows"][pair_id].setdefault("source_row_status",
                            state["rows"][pair_id].get("status"))
                        state["rows"][pair_id]["pre_pair_status"] = \
                            state["rows"][pair_id].get("status")
                        state["rows"][pair_id]["status"] = \
                            "verification_failed_method_disagreement"
                failure = "verification_failed_method_disagreement"
            save_atomic(ledger_path, ledger)
            advance_state_prefix(rows, state, ledger, manifest_sha, state_path)

        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            while (cursor < len(pending) and failure is None) or active:
                update_host()
                finished = [future for future in active if future.done()]
                if finished:
                    for future in finished:
                        record_completion(future)
                    continue
                if failure is not None:
                    if active:
                        wait(active, timeout=1, return_when=FIRST_COMPLETED)
                    continue

                target_workers = worker_target(effective_cpu_count(), ledger["launch_order"],
                    ledger["completed"], failure)
                if target_workers == 0:
                    update_host()
                    failure, cpu_sample = paused_cpu_budget_failure(
                        effective_cpu_count(), ledger["charged_cpu_ns"],
                        current_remaining_rows(), handoff["outside_main_available_cpu_seconds"],
                        ledger["host_cpu_ns"])
                    if failure is not None:
                        continue
                    pause_admission("fewer_than_four_effective_cpus", {
                        "effective_cpu_count": effective_cpu_count(),
                        "required_initial_workers": WORKERS_START,
                        "budget": cpu_sample})
                    if active:
                        wait(active, timeout=1, return_when=FIRST_COMPLETED)
                    else:
                        time.sleep(2)
                    continue

                slots = target_workers - len(active)
                blocked = False
                while slots > 0 and cursor < len(pending) and failure is None:
                    if reconcile_completed_futures(active, record_completion):
                        break
                    update_host()
                    remaining_rows = current_remaining_rows()
                    cpu_sample = budget_admission(ledger["charged_cpu_ns"],
                        remaining_rows, handoff["outside_main_available_cpu_seconds"],
                        ledger["host_cpu_ns"])
                    if not cpu_sample["admitted"]:
                        failure = "budget_exhausted"
                        break

                    row = pending[cursor]
                    row_id = row["row_id"]
                    row_out = output / row_id
                    cgroup_rows, cgroup_samples_valid = active_memory_samples(active)
                    memory_values = [item["memory_current_bytes"] for item in cgroup_rows
                                     if "memory_current_bytes" in item]
                    memory_sample = memory_admission(mem_available_bytes(), memory_values)
                    memory_sample["active_cgroups"] = cgroup_rows
                    memory_sample["cgroup_samples_valid"] = cgroup_samples_valid
                    memory_sample["effective_cpu_count"] = effective_cpu_count()
                    memory_sample["active_worker_count"] = len(cgroup_rows)
                    if (not cgroup_samples_valid or not memory_sample["admitted"]):
                        pause_admission("cgroup_memory_sample_unavailable" if not cgroup_samples_valid
                                        else "memory_headroom_below_worst_case", {
                            "row_id": row_id, "memory": memory_sample,
                            "budget": cpu_sample, "target_workers": target_workers})
                        blocked = True
                        break

                    # Refresh the host CPU accounting after cgroup inspection,
                    # immediately before the claim is made durable.
                    update_host()
                    remaining_rows = current_remaining_rows()
                    cpu_sample = budget_admission(ledger["charged_cpu_ns"],
                        remaining_rows, handoff["outside_main_available_cpu_seconds"],
                        ledger["host_cpu_ns"])
                    if not cpu_sample["admitted"]:
                        failure = "budget_exhausted"
                        break

                    target_workers = worker_target(effective_cpu_count(),
                        ledger["launch_order"], ledger["completed"], failure)
                    if ledger["ramp_events"]:
                        regime = "ramped_5"
                    elif target_workers == WORKERS_MAX:
                        regime = ("ramped_5" if len(cgroup_rows) >= WORKERS_START
                                  else "ramp_armed")
                    else:
                        regime = "initial_4"
                    admission = {"row_id": row_id, "regime": regime,
                        "monotonic_ns": time.monotonic_ns(),
                        "manifest_index": row_index[row_id],
                        "active_worker_count_before": len(cgroup_rows),
                        "target_workers": target_workers,
                        "memory": memory_sample, "budget": cpu_sample}
                    token = uuid.uuid4().hex
                    admission_sha = sha_bytes(canon(admission))
                    ramp_event = None
                    if regime == "ramped_5" and not ledger["ramp_events"]:
                        first_four, receipts_ok = durable_ramp_receipts(
                            ledger["launch_order"], ledger["completed"])
                        if (not receipts_ok or not ramp_receipts_ready(
                                ledger["launch_order"], ledger["completed"], failure)):
                            failure = "verification_failed_ramp_receipt_gate"
                            break
                        ramp_event = {
                            "regime": "initial_4_to_ramped_5",
                            "monotonic_ns": time.monotonic_ns(),
                            "first_four_rows": first_four,
                            "first_four_receipt_sha256": [
                                ledger["completed"][key]["receipt_sha256"] for key in first_four],
                            "fifth_admitted_row_id": row_id,
                            "memory_admission": memory_sample,
                            "budget_admission": cpu_sample}
                    if reconcile_completed_futures(active, record_completion):
                        break
                    close_admission_pause(row_id)
                    if ramp_event is not None:
                        ledger["ramp_events"].append(ramp_event)
                    ledger["admissions"].append(admission)
                    ledger["launch_order"].append(row_id)
                    ledger["inflight"][row_id] = {"claim": token,
                        "cpu_reservation_ns": ROW_CPU_RESERVATION_NS,
                        "host_guard_ns": HOST_CPU_GUARD_NS,
                        "admission_sha256": admission_sha,
                        "regime": regime}
                    update_host()
                    save_atomic(ledger_path, ledger)
                    if row_out.exists():
                        # Only the one empty handoff boundary directory can be adopted.
                        if row_id != ledger["boundary_row_id"] or any(row_out.iterdir()):
                            failure = "unexpected_existing_row_directory"
                            break
                    else:
                        row_out.mkdir()
                        fsync_directory(output)
                    claim = {"schema": "hiroute.m5d.parallel_row_claim.v2",
                        "row_id": row_id, "manifest_sha256": manifest_sha,
                        "amendment_sha256": amendment_sha, "claim": token,
                        "manifest_index": row_index[row_id],
                        "admission_sha256": admission_sha, "regime": regime}
                    with (row_out / "parallel_claim.json").open("x") as stream:
                        json.dump(claim, stream, sort_keys=True)
                        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
                    fsync_directory(row_out)
                    command = (runtime_executable, str(source / "scripts/m5d_main_row.py"),
                        str(source), str(graph_dir), str(pool_path), str(queries_path),
                        str(manifest_path), manifest_sha, row_id, str(row_out))
                    future = executor.submit(supervisor_runner, command,
                        cwd=source, output_dir=row_out,
                        wall_seconds=ROW_WALL_SECONDS, memory_bytes=ROW_MEMORY_BYTES,
                        phase="main", frozen_main_phase=(manifest_bytes, manifest_sha),
                        remaining_cpu_seconds=610, pythonpath=source / "src")
                    active[future] = (row, row_out, token)
                    cursor += 1
                    slots -= 1
                if blocked:
                    if active:
                        wait(active, timeout=1, return_when=FIRST_COMPLETED)
                    else:
                        time.sleep(2)
                    continue
                if active:
                    wait(active, timeout=1, return_when=FIRST_COMPLETED)
                elif cursor < len(pending):
                    time.sleep(2)

        if failure:
            # Fixed identities remain visible; no rows are silently dropped.
            for row in rows[original_start_index:]:
                if row["row_id"] not in state["rows"]:
                    completed = ledger["completed"].get(row["row_id"])
                    if completed is not None:
                        state["rows"][row["row_id"]] = dict(completed["row_result"])
                    else:
                        state["rows"][row["row_id"]] = {
                            "status": "budget_exhausted_unrun" if failure == "budget_exhausted"
                                     else "verification_blocked_unrun",
                            "denominator_included": True}
            state["stopped"] = True
            ledger["stopped"] = True
            ledger["stop_reason"] = failure
            state["charged_cpu_ns"] = ledger["charged_cpu_ns"]
            save_atomic(state_path, state)
        else:
            advance_state_prefix(rows, state, ledger, manifest_sha, state_path)
        if not failure and len(state["rows"]) == len(rows):
            state["stopped"] = True
            ledger["stopped"] = True
            ledger["stop_reason"] = "all_fixed_rows_completed"
        elif not failure and cursor == len(pending) and not active and \
                len(state["rows"]) != len(rows):
            failure = "verification_failed_contiguous_completion_gap"
            for row in rows[original_start_index:]:
                if row["row_id"] not in state["rows"]:
                    completed = ledger["completed"].get(row["row_id"])
                    state["rows"][row["row_id"]] = (dict(completed["row_result"])
                        if completed is not None else
                        {"status": "verification_blocked_unrun", "denominator_included": True})
            state["stopped"] = True
            ledger["stopped"] = True
            ledger["stop_reason"] = failure
            state["charged_cpu_ns"] = ledger["charged_cpu_ns"]
        update_host()
        save_atomic(state_path, state)
        save_atomic(ledger_path, ledger)
        return ledger


if __name__ == "__main__":
    if len(sys.argv) != 10:
        raise SystemExit("usage: source graph pools queries full manifest amendment handoff output")
    run(*(Path(arg) for arg in sys.argv[1:]))
