"""Linux user-cgroup supervisor for bounded M5-D subprocesses.

Requires a working systemd user manager. A transient unit enforces wall time
and total cgroup memory, including descendants. Exact CPU and peak-memory
fields are read before the unit is stopped; missing fields fail closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


@dataclass(frozen=True)
class ResourceReceipt:
    unit: str
    control_group: str
    result: str
    exit_status: int
    cpu_usage_ns: int
    memory_peak_bytes: int
    memory_limit_bytes: int
    wall_elapsed_ns: int
    stdout_path: str
    stderr_path: str
    receipt_path: str


def _properties(unit: str) -> dict[str, str]:
    command = ["systemctl", "--user", "show", unit, "--no-pager",
               "-p", "ActiveState", "-p", "SubState", "-p", "Result",
               "-p", "ExecMainStatus", "-p", "CPUUsageNSec",
               "-p", "MemoryPeak", "-p", "MemoryMax"]
    command.extend(["-p", "MemorySwapMax", "-p", "KillMode", "-p", "RuntimeMaxUSec",
                    "-p", "ControlGroup"])
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def _duration_us(value: str) -> int | None:
    units = {"us": 1, "ms": 1000, "s": 1_000_000,
             "min": 60_000_000, "h": 3_600_000_000}
    parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(us|ms|min|h|s)", value)
    if not parts or " ".join(number + unit for number, unit in parts) != value:
        return None
    total = sum(Decimal(number) * units[unit] for number, unit in parts)
    return int(total) if total == int(total) else None


def _group_empty(control_group: str) -> bool:
    # systemd clears ControlGroup after the last task exits even while a
    # RemainAfterExit service keeps its accounting properties available.
    if control_group == "":
        return True
    if not control_group.startswith("/user.slice/") or ".." in Path(control_group).parts:
        raise RuntimeError("Invalid or missing user cgroup identity")
    events = Path("/sys/fs/cgroup") / control_group.lstrip("/") / "cgroup.events"
    if not events.exists():
        return True
    values = dict(line.split() for line in events.read_text().splitlines())
    if values.get("populated") not in ("0", "1"):
        raise RuntimeError("Cgroup population could not be verified")
    return values["populated"] == "0"


def run_supervised(argv: tuple[str, ...], *, cwd: Path, output_dir: Path,
                   wall_seconds: int, memory_bytes: int,
                   pythonpath: Path | None = None) -> ResourceReceipt:
    if (not argv or any(type(value) is not str or not value or "\0" in value for value in argv)
            or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file()
            or type(wall_seconds) is not int or wall_seconds < 1
            or type(memory_bytes) is not int or memory_bytes < 1):
        raise ValueError("Absolute executable and positive finite limits required")
    cwd = Path(cwd).resolve(strict=True)
    output_dir = Path(output_dir).resolve(strict=True)
    if not cwd.is_dir() or not output_dir.is_dir():
        raise ValueError("Existing work and receipt directories required")
    unit = "hiroute-m5d-" + uuid.uuid4().hex + ".service"
    stdout = output_dir / (unit + ".stdout")
    stderr = output_dir / (unit + ".stderr")
    # Exclusive files keep a receipt from replacing earlier experiment output.
    for path in (stdout, stderr):
        with path.open("x"):
            pass
    command = ["systemd-run", "--user", "--unit=" + unit,
               "--remain-after-exit", "--working-directory=" + str(cwd),
               "--property=MemoryAccounting=yes",
               "--property=MemoryMax=" + str(memory_bytes),
               "--property=MemorySwapMax=0",
               "--property=RuntimeMaxSec=" + str(wall_seconds) + "s",
               "--property=KillMode=control-group",
               "--property=TimeoutStopSec=1s",
               "--property=StandardOutput=append:" + str(stdout),
               "--property=StandardError=append:" + str(stderr)]
    if pythonpath is not None:
        path = Path(pythonpath).resolve(strict=True)
        if not path.is_dir():
            raise ValueError("Existing Python source directory required")
        command.append("--setenv=PYTHONPATH=" + str(path))
    command.extend(("--", *argv))
    started = time.monotonic_ns()
    launched = False
    receipt = None
    failure = None
    control_group = None
    try:
        launched = True
        subprocess.run(command, check=True, text=True, capture_output=True)
        deadline = started + (wall_seconds + 10) * 1_000_000_000
        while True:
            fields = _properties(unit)
            if fields.get("SubState") in ("exited", "failed", "dead"):
                break
            if time.monotonic_ns() > deadline:
                raise RuntimeError("Systemd unit did not finish after the wall-time guard")
            time.sleep(0.05)
        if (not re.fullmatch(r"[0-9]+", fields.get("CPUUsageNSec", "")) or
                not re.fullmatch(r"[0-9]+", fields.get("MemoryPeak", "")) or
                fields.get("MemoryMax") != str(memory_bytes) or
                fields.get("MemorySwapMax") != "0" or
                fields.get("KillMode") != "control-group" or
                _duration_us(fields.get("RuntimeMaxUSec", "")) != wall_seconds * 1_000_000 or
                not re.fullmatch(r"[0-9]+", fields.get("ExecMainStatus", ""))):
            raise RuntimeError("Cgroup CPU, peak memory or enforced limit receipt missing")
        control_group = fields.get("ControlGroup", "")
        if not _group_empty(control_group):
            raise RuntimeError("Unit exited while descendants remain in its cgroup")
        receipt_path = output_dir / (unit + ".receipt.json")
        receipt = ResourceReceipt(unit, control_group, fields["Result"], int(fields["ExecMainStatus"]),
                               int(fields["CPUUsageNSec"]), int(fields["MemoryPeak"]),
                               memory_bytes, time.monotonic_ns() - started,
                               str(stdout), str(stderr), str(receipt_path))
    except Exception as error:
        failure = error
    finally:
        if launched:
            stopped = subprocess.run(["systemctl", "--user", "stop", unit],
                                     text=True, capture_output=True)
            if stopped.returncode != 0:
                failure = RuntimeError("Transient unit cleanup failed: " + stopped.stderr.strip())
            elif control_group is not None:
                try:
                    if not _group_empty(control_group):
                        failure = RuntimeError("Cgroup remains populated after cleanup")
                except Exception as error:
                    failure = error
    if failure is not None:
        failure_path = output_dir / (unit + ".failure.json")
        with failure_path.open("x") as stream:
            json.dump({"unit": unit, "error": str(failure), "control_group": control_group,
                       "stdout_path": str(stdout), "stderr_path": str(stderr)}, stream,
                      sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        raise failure
    if receipt is None:
        raise RuntimeError("Missing supervisor receipt")
    with Path(receipt.receipt_path).open("x") as stream:
        json.dump(asdict(receipt), stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return receipt


def run_m5d_phase(argv: tuple[str, ...], *, cwd: Path, output_dir: Path,
                  wall_seconds: int, memory_bytes: int, phase: str,
                  pythonpath: Path | None = None,
                  frozen_main_phase: tuple[bytes, str] | None = None,
                  remaining_cpu_seconds: int | None = None) -> ResourceReceipt:
    """Apply the M5-D phase ceiling before creating any supervised unit."""
    if phase in ("pilot", "functionality"):
        if (type(wall_seconds) is not int or wall_seconds < 1 or wall_seconds > 120 or
                type(memory_bytes) is not int or memory_bytes < 1 or
                memory_bytes > 4 * 1024**3 or frozen_main_phase is not None):
            raise ValueError("Pilot/functionality limit is at most 120s and 4GiB")
    elif phase == "main":
        import hashlib
        import json
        if (type(frozen_main_phase) is not tuple or len(frozen_main_phase) != 2 or
                type(frozen_main_phase[0]) is not bytes or
                hashlib.sha256(frozen_main_phase[0]).hexdigest() != frozen_main_phase[1]):
            raise ValueError("Main run requires an exact frozen phase manifest")
        try:
            manifest = json.loads(frozen_main_phase[0])
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid frozen main phase") from error
        if (type(manifest) is not dict or manifest.get("schema") != "hiroute.m5d.frozen_main_phase.v1" or
                manifest.get("wall_seconds") != wall_seconds or
                manifest.get("memory_bytes") != memory_bytes or
                type(wall_seconds) is not int or not 1 <= wall_seconds <= 600 or
                type(memory_bytes) is not int or not 1 <= memory_bytes <= 8 * 1024**3 or
                type(remaining_cpu_seconds) is not int or remaining_cpu_seconds < wall_seconds):
            raise ValueError("Main limit or remaining budget differs from frozen phase")
    else:
        raise ValueError("Unknown M5-D resource phase")
    return run_supervised(argv, cwd=cwd, output_dir=output_dir,
                          wall_seconds=wall_seconds, memory_bytes=memory_bytes,
                          pythonpath=pythonpath)
