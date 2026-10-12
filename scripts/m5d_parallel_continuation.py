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
import shutil
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from timecut5.systemd_supervisor import run_m5d_phase

WORKERS_MAX = 5
WORKERS_START = 4
RAMP_AFTER_DURABLE_RECEIPTS = 4
ROW_CPU_RESERVATION_NS = 610 * 10**9
HOST_CPU_GUARD_NS = 60 * 10**9
ROW_WALL_SECONDS = 600
ROW_MEMORY_BYTES = 8 * 1024**3
HOST_MEMORY_RESERVE_BYTES = 8 * 1024**3
MAIN_CPU_CEILING_NS = 117000 * 10**9


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(Path(path).read_bytes())


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
    info = os.lstat(path)
    if (path.is_symlink() or not path.is_file() or info.st_nlink != 1 or
            path.parent.resolve() != row_out.resolve()):
        raise ValueError("Supervisor receipt is not a unique row-local regular file")
    raw = path.read_bytes()
    after = os.lstat(path)
    if ((info.st_dev, info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns,
         info.st_ctime_ns) !=
        (after.st_dev, after.st_ino, after.st_nlink, after.st_size, after.st_mtime_ns,
         after.st_ctime_ns)):
        raise ValueError("Supervisor receipt changed while being checked")
    if json.loads(raw) != asdict(receipt):
        raise ValueError("Durable supervisor receipt differs from the returned receipt")
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    fsync_directory(row_out)
    return sha_bytes(raw)


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
    outside_required_ns = (remaining_rows + 1) * HOST_CPU_GUARD_NS
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
    if (amendment.get("schema") != "hiroute.m5d.parallel_continuation_amendment.v2" or
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
            amendment.get("memory_current_source") != "systemd-cgroup-v2-memory.current"):
        raise ValueError("Parallel continuation amendment or source binding differs")


def validate_handoff(handoff, manifest_sha: str, state_bytes: bytes):
    if (handoff.get("schema") != "hiroute.m5d.parallel_handoff.v1" or
            handoff.get("manifest_sha256") != manifest_sha or
            handoff.get("main_state_sha256") != sha_bytes(state_bytes) or
            handoff.get("old_scheduler_gone") is not True or
            handoff.get("old_main_units_empty") is not True or
            handoff.get("review_approved") is not True or
            type(handoff.get("outside_main_available_cpu_seconds")) not in (int, float) or
            handoff["outside_main_available_cpu_seconds"] < 0 or
            type(handoff.get("main_host_cpu_ns")) is not int or
            handoff["main_host_cpu_ns"] < 0):
        raise ValueError("Reviewed, terminal and source-bound handoff required")


def current_main_processes(source: Path, output: Path) -> bool:
    text = subprocess.check_output(["ps", "-eo", "args="], text=True)
    return any("scripts/m5d_main_batch.py" in line and
               str(source) in line and str(output) in line for line in text.splitlines())


def active_main_units() -> list[str]:
    lines = subprocess.check_output(["systemctl", "--user", "list-units",
        "--type=service", "--state=running", "--no-legend", "--plain"], text=True)
    return [line for line in lines.splitlines() if "m5d_main_row.py" in line]


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
        if current_main_processes(source, output) or active_main_units():
            raise ValueError("Old scheduler or main row unit is still active")
        handoff_bytes = Path(handoff_path).read_bytes()
        handoff_sha = sha_bytes(handoff_bytes)
        handoff = json.loads(handoff_bytes)
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_bytes())
            if (ledger.get("schema") != "hiroute.m5d.parallel_continuation_state.v2" or
                    ledger.get("manifest_sha256") != manifest_sha or
                    ledger.get("amendment_sha256") != amendment_sha or
                    ledger.get("handoff_sha256") != handoff_sha or
                    type(ledger.get("start_index")) is not int or
                    start_index < ledger["start_index"]):
                raise ValueError("Continuation resume bindings differ")
            if ledger.get("inflight"):
                raise ValueError("Interrupted in-flight rows need receipt review; refusing rerun")
            if ledger.get("stopped"):
                if state.get("stopped") is not True:
                    raise ValueError("Stopped continuation ledger lacks a stopped main state")
                return ledger
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
            expected_charge = ledger["charged_cpu_ns_at_start"] + sum(
                row["charged_cpu_ns"] for row in completed.values())
            if expected_charge != ledger["charged_cpu_ns"]:
                raise ValueError("Continuation cumulative CPU charge differs from its receipts")
            row_index = {row["row_id"]: index for index, row in enumerate(rows)}
            if any(row_id not in row_index or row_index[row_id] < ledger["start_index"]
                   for row_id in completed):
                raise ValueError("Continuation ledger names a row outside its fixed suffix")
            for row_id, status in state["rows"].items():
                if row_index[row_id] >= ledger["start_index"]:
                    record = completed.get(row_id)
                    if (record is None or
                            status.get("status") != record.get("row_result", {}).get("status")):
                        raise ValueError("Main state differs from a durable parallel completion")
            if state["charged_cpu_ns"] > ledger["charged_cpu_ns"]:
                raise ValueError("Main state CPU charge exceeds the continuation ledger")
            if state.get("stopped") and not ledger.get("stopped"):
                raise ValueError("Main denominator stopped without a terminal continuation ledger")
            advance_state_prefix(rows, state, ledger, manifest_sha, state_path)
        else:
            validate_handoff(handoff, manifest_sha, state_bytes)
            ledger = {"schema": "hiroute.m5d.parallel_continuation_state.v2",
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

        baseline_host_cpu = host_cpu_ns()
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
                    result["status"] = "verification_failed_resource_contract"
                if _is_supervisor_or_verification_failure(result):
                    failure = result["status"]

            result["batch_and_waited_child_cpu_ns"] = ledger["host_cpu_ns"]
            record = {"status": result["status"], "row_result": result,
                "charged_cpu_ns": charged,
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
                        ledger["completed"][pair_id]["status"] = \
                            "verification_failed_method_disagreement"
                        ledger["completed"][pair_id]["row_result"]["status"] = \
                            "verification_failed_method_disagreement"
                    if pair_id in state["rows"]:
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
                    pause_admission("fewer_than_four_effective_cpus", {
                        "effective_cpu_count": effective_cpu_count(),
                        "required_initial_workers": WORKERS_START})
                    if active:
                        wait(active, timeout=1, return_when=FIRST_COMPLETED)
                    else:
                        time.sleep(2)
                    continue

                slots = target_workers - len(active)
                blocked = False
                while slots > 0 and cursor < len(pending) and failure is None:
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
                    if regime == "ramped_5" and not ledger["ramp_events"]:
                        first_four, receipts_ok = durable_ramp_receipts(
                            ledger["launch_order"], ledger["completed"])
                        if (not receipts_ok or not ramp_receipts_ready(
                                ledger["launch_order"], ledger["completed"], failure)):
                            failure = "verification_failed_ramp_receipt_gate"
                            break
                        ledger["ramp_events"].append({
                            "regime": "initial_4_to_ramped_5",
                            "monotonic_ns": time.monotonic_ns(),
                            "first_four_rows": first_four,
                            "first_four_receipt_sha256": [
                                ledger["completed"][key]["receipt_sha256"] for key in first_four],
                            "fifth_admitted_row_id": row_id,
                            "memory_admission": memory_sample,
                            "budget_admission": cpu_sample})
                    close_admission_pause(row_id)
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
                    command = (sys.executable, str(source / "scripts/m5d_main_row.py"),
                        str(source), str(graph_dir), str(pool_path), str(queries_path),
                        str(manifest_path), manifest_sha, row_id, str(row_out))
                    future = executor.submit(run_m5d_phase, command,
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
