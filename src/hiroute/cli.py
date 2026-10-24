"""Installed command line entry points for explicit problem snapshots."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

from . import __version__
from .contracts import (ProblemSnapshot, SolverConfig, SolveResult, Witness, canonical_json, content_id)


def _read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid UTF-8 JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Top-level JSON value must be an object")
    return value


def _atomic_new_file(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp_name, path)
        os.unlink(temp_name)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def validate_command(args: argparse.Namespace) -> int:
    snapshot = ProblemSnapshot.from_dict(_read_object(Path(args.problem)))
    print(json.dumps({"valid": True, "semantic_problem_id": snapshot.semantic_problem_id,
                      "schema": "hiroute.problem_snapshot.v1"}, sort_keys=True))
    return 0


def validate_migration_support(snapshot: ProblemSnapshot, config: SolverConfig) -> None:
    """Reject contracts the migration adapter has not implemented; never reinterpret them."""
    supported_snapshot = {
        "model_contract_id": "hiroute.time_cut_v2.bounded",
        "numerical_contract_id": "exact_rational_inputs_v1",
        "selected_leg_contract": "positive_time_node_path_edge_path_tie_v1",
        "depth_mode": "diagnostic_cap",
    }
    for field, expected in supported_snapshot.items():
        actual = getattr(snapshot, field)
        if actual != expected:
            raise NotImplementedError(f"unsupported_model: {field}={actual!r}; supported value is {expected!r}")
    supported_config = {
        "method": "flat",
        "reduction_profile": "none",
        "charging_operator_profile": "bounded_time_cut_v2",
        "coalescing_profile": "none",
        "bound_profile": "none",
        "seed_policy": "none",
        "deterministic_tie_policy": "full_lexicographic_J_Q_H_Pi",
    }
    for field, expected in supported_config.items():
        actual = getattr(config, field)
        if actual != expected:
            raise NotImplementedError(f"unsupported solver profile: {field}={actual!r}; supported value is {expected!r}")


def solve_command(args: argparse.Namespace) -> int:
    snapshot_obj = _read_object(Path(args.problem))
    if not snapshot_obj.get("semantic_problem_id"):
        raise ValueError("solve input must include semantic_problem_id; run hiroute validate and use its canonical snapshot")
    snapshot = ProblemSnapshot.from_dict(snapshot_obj)
    config = SolverConfig.from_dict(_read_object(Path(args.config)))
    validate_migration_support(snapshot, config)
    if args.backend != "legacy_migration_adapter":
        raise ValueError("R1 requires explicit backend=legacy_migration_adapter")
    if not args.adapter_script or not args.adapter_python or not args.adapter_source_root:
        raise ValueError("The migration adapter requires explicit script, interpreter and legacy source root")
    child_env = os.environ.copy()
    child_env.pop("PYTHONPATH", None)
    child_env["HIROUTE_LEGACY_SOURCE_ROOT"] = args.adapter_source_root
    completed = subprocess.run(
        [args.adapter_python, args.adapter_script],
        input=canonical_json(snapshot.to_dict()), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, env=child_env,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Migration adapter exited {completed.returncode}: "
                           f"{completed.stderr.decode('utf-8', 'replace')[-2000:]}")
    try:
        evidence = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Migration adapter did not return one JSON object") from exc
    result = evidence["result"]
    status = result.get("status")
    mathematical = {
        "attained_optimum": "attained_optimum",
        "primary_unattained": "primary_unattained",
        "secondary_unattained": "secondary_unattained",
        "infeasible_within_H_ref": "infeasible_within_declared_domain",
    }.get(status, "unknown")
    execution = "completed" if mathematical != "unknown" else "error"
    raw_witness = evidence.get("witness")
    witness = None
    if raw_witness is not None:
        witness = Witness(tuple(tuple(x) for x in raw_witness["actions"]),
                          tuple(raw_witness["charges_kwh"]),
                          tuple(raw_witness["route_legs"]),
                          tuple(raw_witness["events"]))
    result_record = SolveResult(
        execution_status=execution,
        mathematical_status=mathematical,
        verification_status="witness_verified" if evidence.get("witness_replayed") else "not_run",
        semantic_problem_id=snapshot.semantic_problem_id,
        representation_id=content_id({"method": config.method, "config": config.to_dict()}),
        build_id=__version__, run_id=str(uuid.uuid4()),
        key=None if result.get("key") is None else tuple(result["key"]),
        witness=witness,
        primary_infimum=result.get("primary_infimum") if mathematical == "primary_unattained" else None,
        secondary_infimum=result.get("secondary_infimum") if mathematical == "secondary_unattained" else None,
        backend="legacy_migration_adapter",
        backend_evidence=evidence,
    ).to_dict()
    out = Path(args.output)
    _atomic_new_file(out, canonical_json(result_record))
    print(json.dumps({"output": str(out), "run_id": result_record["run_id"],
                      "semantic_problem_id": snapshot.semantic_problem_id,
                      "execution_status": execution, "mathematical_status": mathematical,
                      "verification_status": result_record["verification_status"],
                      "backend": result_record["backend"]}, sort_keys=True))
    return 0 if execution == "completed" else 4


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hiroute", description="HiRoute explicit snapshot interface")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate one versioned ProblemSnapshot")
    validate.add_argument("--problem", required=True)
    validate.set_defaults(run=validate_command)
    solve = sub.add_parser("solve", help="run a declared solver backend on a snapshot")
    solve.add_argument("--problem", required=True)
    solve.add_argument("--config", required=True)
    solve.add_argument("--backend", required=True,
                       choices=["legacy_migration_adapter"])
    solve.add_argument("--adapter-script")
    solve.add_argument("--adapter-python")
    solve.add_argument("--adapter-source-root")
    solve.add_argument("--output", required=True)
    solve.set_defaults(run=solve_command)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return args.run(args)
    except NotImplementedError as exc:
        print(f"hiroute: {exc}", file=sys.stderr)
        return 3
    except (ValueError, TypeError) as exc:
        print(f"hiroute: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        print(f"hiroute: {exc}", file=sys.stderr)
        return 4
