"""Linux user-cgroup supervisor for bounded M5-D subprocesses.

Requires a working systemd user manager. A transient unit enforces wall time
and total cgroup memory, including descendants. Exact CPU and peak-memory
fields are read before the unit is stopped; missing fields fail closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
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
    command.extend(["-p", "MemorySwapMax", "-p", "KillMode", "-p", "RuntimeMaxUSec"])
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def run_supervised(argv: tuple[str, ...], *, cwd: Path, output_dir: Path,
                   wall_seconds: int, memory_bytes: int) -> ResourceReceipt:
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
               "--property=StandardError=append:" + str(stderr), "--", *argv]
    started = time.monotonic_ns()
    launched = False
    try:
        subprocess.run(command, check=True, text=True, capture_output=True)
        launched = True
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
                fields.get("RuntimeMaxUSec") != str(wall_seconds) + "s" or
                not re.fullmatch(r"[0-9]+", fields.get("ExecMainStatus", ""))):
            raise RuntimeError("Cgroup CPU, peak memory or enforced limit receipt missing")
        receipt_path = output_dir / (unit + ".receipt.json")
        receipt = ResourceReceipt(unit, fields["Result"], int(fields["ExecMainStatus"]),
                               int(fields["CPUUsageNSec"]), int(fields["MemoryPeak"]),
                               memory_bytes, time.monotonic_ns() - started,
                               str(stdout), str(stderr), str(receipt_path))
        with receipt_path.open("x") as stream:
            json.dump(asdict(receipt), stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        return receipt
    finally:
        if launched:
            subprocess.run(["systemctl", "--user", "stop", unit],
                           text=True, capture_output=True)
