"""Installed command line entry points for explicit problem snapshots."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

from . import __version__
from .exact.search import solve_snapshot as solve_native_snapshot
from .exact.scalar import rational_text
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


def validate_native_support(snapshot: ProblemSnapshot, config: SolverConfig) -> None:
    """Fail closed on model fields and profiles outside the exact core search."""
    supported_snapshot = {
        "model_contract_id": "hiroute.time_cut_v2.bounded",
        "numerical_contract_id": "exact_rational_inputs_v1",
        "selected_leg_contract": "positive_time_node_path_edge_path_tie_v1",
    }
    for field, expected in supported_snapshot.items():
        actual = getattr(snapshot, field)
        if actual != expected:
            raise NotImplementedError(f"unsupported_model: {field}={actual!r}; supported value is {expected!r}")
    if snapshot.depth_mode not in {"diagnostic_cap", "seed_derived"}:
        raise NotImplementedError(f"unsupported_model: depth_mode={snapshot.depth_mode!r}")
    supported_config = {
        "reduction_profile": "none",
        "charging_operator_profile": "bounded_time_cut_v2",
        "coalescing_profile": "none",
        "bound_profile": "none",
        "deterministic_tie_policy": "full_lexicographic_J_Q_H_Pi",
    }
    for field, expected in supported_config.items():
        actual = getattr(config, field)
        if actual != expected:
            raise NotImplementedError(f"unsupported solver profile: {field}={actual!r}; supported value is {expected!r}")
    expected_seed_policy = "verified_seed_certificate" if snapshot.depth_mode == "seed_derived" else "none"
    if config.seed_policy != expected_seed_policy:
        raise NotImplementedError(f"unsupported_model: seed policy for {snapshot.depth_mode} is {config.seed_policy!r}")


def _native_result(snapshot: ProblemSnapshot, config: SolverConfig, solved: dict, observer: str = "off") -> dict:
    status = solved["status"]
    if status == "time_limit":
        incumbent = solved.get("incumbent")
        witness = None
        incumbent_record = None
        verification = "not_run"
        if incumbent is not None:
            replay = incumbent["replay"]
            trace = replay["trace"]
            charges = [str(oe - ie) for effect, _site, ie, _it, oe, _ot in trace
                       if effect in {"C", "CS"}]
            witness = Witness(
                actions=tuple(tuple(x) for x in incumbent["key"][3]),
                charges_kwh=tuple(charges),
                route_legs=tuple(_leg_dict(x) for x in incumbent["legs"]),
                events=tuple({"effect": effect, "site": site,
                              "input_energy_kwh": str(ie), "input_time_s": str(it),
                              "output_energy_kwh": str(oe), "output_time_s": str(ot)}
                             for effect, site, ie, it, oe, ot in trace),
            )
            incumbent_record = {
                "key": [rational_text(incumbent["key"][0], "incumbent.J"),
                        rational_text(incumbent["key"][1], "incumbent.Q"),
                        incumbent["key"][2], incumbent["key"][3]],
                "plan": incumbent["plan"], "replay_key": incumbent["replay"]["key"],
                "label": "feasible_incumbent_not_optimality_claim",
            }
            verification = "witness_verified"
        return SolveResult(
            execution_status="time_limit", mathematical_status="unknown",
            verification_status=verification, semantic_problem_id=snapshot.semantic_problem_id,
            representation_id=content_id({"method": config.method, "config": config.to_dict(),
                                          "backend": "exact_core_search",
                                          "observer": observer}),
            build_id=__version__, run_id=str(uuid.uuid4()), witness=witness,
            backend="exact_core_search",
            backend_evidence={"enumerated_route_domains": solved["domains"],
                             "incumbent": incumbent_record,
                             "elapsed_s": solved["elapsed_s"],
                             "depth_contract": solved.get("depth_certificate") or {
                                 "mode": snapshot.depth_mode, "limit": snapshot.depth_limit,
                                 "certificate_reference": snapshot.depth_certificate_reference},
                             "observer": solved.get("observer"),
                             "hierarchy_metrics": solved.get("hierarchy_metrics")},
        ).to_dict()
    mathematical = {
        "attained_optimum": "attained_optimum",
        "primary_unattained": "primary_unattained",
        "secondary_unattained": "secondary_unattained",
        "infeasible": "infeasible_within_declared_domain",
    }[status]
    witness = None
    key = None
    verification = "not_run"
    primary_infimum = secondary_infimum = None
    if status == "attained_optimum":
        replay = solved["replay"]
        trace = replay["trace"]
        charges = [str(oe - ie) for effect, _site, ie, _it, oe, _ot in trace
                   if effect in {"C", "CS"}]
        witness = Witness(
            actions=tuple(tuple(x) for x in solved["key"][3]),
            charges_kwh=tuple(charges),
            route_legs=tuple(_leg_dict(x) for x in solved["legs"]),
            events=tuple({"effect": effect, "site": site,
                          "input_energy_kwh": str(ie), "input_time_s": str(it),
                          "output_energy_kwh": str(oe), "output_time_s": str(ot)}
                         for effect, site, ie, it, oe, ot in trace),
        )
        key = (rational_text(solved["key"][0], "key.J"),
               rational_text(solved["key"][1], "key.Q"),
               solved["key"][2], solved["key"][3])
        verification = "witness_verified"
    elif status == "primary_unattained":
        primary_infimum = rational_text(solved["primary_infimum"], "primary_infimum")
    elif status == "secondary_unattained":
        primary_infimum = rational_text(solved["primary_infimum"], "primary_infimum")
        secondary_infimum = rational_text(solved["secondary_infimum"], "secondary_infimum")
    return SolveResult(
        execution_status="completed", mathematical_status=mathematical,
        verification_status=verification, semantic_problem_id=snapshot.semantic_problem_id,
        representation_id=content_id({"method": config.method, "config": config.to_dict(),
                                      "backend": "exact_core_search",
                                      "observer": observer}),
        build_id=__version__, run_id=str(uuid.uuid4()), key=key, witness=witness,
        primary_infimum=primary_infimum, secondary_infimum=secondary_infimum,
        backend="exact_core_search",
        backend_evidence={"search_method": config.method,
                          "enumeration_backend": solved.get("enumeration_backend", "exact_enumeration_backend"),
                          "hierarchical_search": solved.get("hierarchical_search", "not_requested"),
                          "enumerated_route_domains": solved["domains"],
                          "depth_contract": solved.get("depth_certificate") or {
                              "mode": snapshot.depth_mode, "limit": snapshot.depth_limit,
                              "certificate_reference": snapshot.depth_certificate_reference},
                          "selected_leg_identity": solved.get("selected_leg_identity", snapshot.graph_or_leg_identity),
                          "routing_cache_entries": solved.get("routing_cache_entries", 0),
                          "witness_replay": "exact_transition_chain",
                          "observer": solved.get("observer")},
    ).to_dict()


def _leg_dict(leg):
    from .exact.search import _leg_dict as serialize_leg
    return serialize_leg(leg)


def solve_command(args: argparse.Namespace) -> int:
    snapshot_obj = _read_object(Path(args.problem))
    snapshot = ProblemSnapshot.from_dict(snapshot_obj)
    config = SolverConfig.from_dict(_read_object(Path(args.config)))
    validate_native_support(snapshot, config)
    certificate = _read_object(Path(args.depth_certificate)) if args.depth_certificate else None
    if snapshot.depth_mode == "seed_derived" and certificate is None:
        raise ValueError("seed_derived requires --depth-certificate")
    if snapshot.depth_mode == "diagnostic_cap" and certificate is not None:
        raise ValueError("--depth-certificate is only valid for seed_derived depth")
    solved = solve_native_snapshot(snapshot, config, time_limit_s=args.time_limit_s,
                                   observer=args.observer, depth_certificate=certificate)
    result_record = _native_result(snapshot, config, solved, args.observer)
    out = Path(args.output)
    _atomic_new_file(out, canonical_json(result_record))
    print(json.dumps({"output": str(out), "run_id": result_record["run_id"],
                      "semantic_problem_id": snapshot.semantic_problem_id,
                      "execution_status": result_record["execution_status"],
                      "mathematical_status": result_record["mathematical_status"],
                      "verification_status": result_record["verification_status"],
                      "backend": result_record["backend"]}, sort_keys=True))
    return 0


def run_command(args: argparse.Namespace) -> int:
    from .runtime import run_supervised

    command = list(args.argv)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise ValueError("run requires a command after --")
    try:
        result = run_supervised(
            command,
            timeout_s=args.wall_limit_s,
            cpu_limit_s=args.cpu_limit_s,
            memory_limit_bytes=args.memory_limit_bytes,
            process_address_space_limit_bytes=args.process_address_space_limit_bytes,
            host_min_available_bytes=args.host_headroom_bytes,
            memory_poll_s=args.poll_s,
            receipt_path=args.receipt,
            cwd=args.cwd,
        )
    except RuntimeError as exc:
        try:
            record = _read_object(Path(args.receipt))
        except ValueError:
            raise
        if record.get("status") in {"host_headroom_blocked", "host_monitor_error"}:
            print(f"hiroute: {exc}", file=sys.stderr)
            return 127
        raise
    if result.stdout:
        sys.stdout.write(result.stdout.decode("utf-8", errors="replace"))
    if result.stderr:
        sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
    if result.host_headroom_limited:
        return 127
    if result.timed_out:
        return 124
    if result.memory_limited:
        return 125
    if result.cpu_limited:
        return 126
    if result.returncode is None:
        return 125
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hiroute", description="HiRoute explicit snapshot interface")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate one versioned ProblemSnapshot")
    validate.add_argument("--problem", required=True)
    validate.set_defaults(run=validate_command)
    solve = sub.add_parser("solve", help="run the built-in exact solver on a snapshot")
    solve.add_argument("--problem", required=True)
    solve.add_argument("--config", required=True)
    solve.add_argument("--output", required=True)
    solve.add_argument("--time-limit-s", type=float,
                       help="optional exact-search wall deadline; timeout output keeps a feasible incumbent separately")
    solve.add_argument("--observer", choices=["off", "metrics", "detailed_trace"], default="off")
    solve.add_argument("--depth-certificate", help="independently constructed, replayable D2 seed certificate JSON")
    solve.set_defaults(run=solve_command)
    run = sub.add_parser("run", help="run any command under OS resource and host-headroom supervision")
    run.add_argument("--wall-limit-s", type=float, required=True)
    run.add_argument("--cpu-limit-s", type=float, required=True)
    run.add_argument("--memory-limit-bytes", type=int, required=True,
                     help="sampled process-group RSS ceiling; not a kernel hard cap")
    run.add_argument("--host-headroom-bytes", type=int, required=True,
                     help="minimum host MemAvailable checked before launch and while running")
    run.add_argument("--process-address-space-limit-bytes", type=int,
                     help="optional per-process RLIMIT_AS ceiling")
    run.add_argument("--poll-s", type=float, default=0.1)
    run.add_argument("--receipt", required=True, help="atomic supervision receipt path")
    run.add_argument("--cwd")
    run.add_argument("argv", nargs=argparse.REMAINDER)
    run.set_defaults(run=run_command)
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
    except (OSError, RuntimeError, KeyError) as exc:
        print(f"hiroute: {exc}", file=sys.stderr)
        return 4
