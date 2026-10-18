"""Read-only zero/one-stop witness preflight on retained immutable tables.

This proves existence when independent replay succeeds. Failure to find a
witness is not a proof that two stops are necessary: proposal coverage is
deliberately limited and the export may contain only a small Site sample.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import time

import timecut5.deployable as deployable
from timecut5.deployable import constructive_seed_candidates
from timecut5.real_legs import ImmutableLegTable
from validation.reference5.model import InvalidInput
from validation.reference5.real_input import IndependentLegTable
from validation.reference5.real_solver import query_from_resolved_state, replay_real_witness


def checked_json(path: Path, digest: str):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Input hash mismatch: {path.name}")
    return data, json.loads(data)


def run(export_dir: Path, states_path: Path, states_sha256: str) -> dict:
    started = time.monotonic()
    _, states = checked_json(states_path, states_sha256)
    if not isinstance(states, list) or not states:
        raise ValueError("Resolved states must be a nonempty list")
    rows = []
    cache = {}
    for state in states:
        reference = state["immutable_direct_leg_table"]
        relative = Path(reference["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Leg table path escapes export directory")
        digest = reference["sha256"]
        if digest not in cache:
            data, _ = checked_json(export_dir / relative, digest)
            cache[digest] = (ImmutableLegTable.from_bytes(data, digest),
                             IndependentLegTable.from_bytes(data, digest))
        table, independent = cache[digest]
        query = query_from_resolved_state(state, independent)
        bound_query = dict(query, leg_payload_sha256=table.payload_sha256,
                           selection_certificate_sha256=table.selection_certificate_sha256,
                           hierarchy_sha256=table.hierarchy_sha256)
        proposals = constructive_seed_candidates(bound_query, table)
        verified = []
        for sequence, charges in proposals:
            try:
                result = replay_real_witness(query, independent, sequence, charges)
            except (InvalidInput, ValueError, AssertionError):
                continue
            verified.append({"J": str(result["J"]), "H": result["H"],
                             "site_action_tuple": result["site_action_tuple"],
                             "charges": [str(x) for x in result["charges"]]})
        rows.append({"state_id": state["state_id"], "pool_id": state["pool_id"],
                     "table_sha256": digest, "proposal_count": len(proposals),
                     "verified_count": len(verified),
                     "example_verified": min(verified, key=lambda x: (Fraction(x["J"]), x["H"]))
                     if verified else None})
    return {"schema": "hiroute.m5d.one_stop_preflight.v1",
            "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "candidate_source_sha256": hashlib.sha256(Path(deployable.__file__).read_bytes()).hexdigest(),
            "resolved_states_sha256": states_sha256,
            "one_stop_or_direct_verified_state_count": sum(r["verified_count"] > 0 for r in rows),
            "state_count": len(rows), "table_count": len(cache),
            "elapsed_seconds": time.monotonic() - started,
            "no_optimizer_calls": True,
            "negative_result_is_not_two_stop_proof": True, "states": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--states-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    args.output.write_text(json.dumps(run(args.export_dir, args.states, args.states_sha256),
                                      indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
