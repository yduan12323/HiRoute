"""Frozen Pilot seed-replay equivalence; exits before either exact solver."""
from __future__ import annotations

from fractions import Fraction
import hashlib
import inspect
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scripts import m5d_pilot_exact_row as runner
from timecut5.deployable import constructive_seed_candidates
from validation.reference5 import real_input, real_solver


class FinishedComparison(Exception):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(root: Path, graph: Path, out: Path, certificate: Path,
        od_id: str, size: int, activity: str):
    if (od_id != "OD02" or size not in (8, 16, 32) or
            activity not in ("energy_only", "energy_and_scheduled")):
        raise ValueError("Only frozen OD02 Pilot replay rows are admitted")
    original = runner.construct_verified_seed

    def compare(domain, hashes):
        query, table = domain.open()
        proposals = constructive_seed_candidates(query, table)
        independent = real_input.IndependentLegTable.from_bytes(
            domain.table_bytes, domain.table_sha256)
        prepared = real_solver.prepare_real_case(query, independent)
        rows, accepted = [], []
        for index, (sequence, charges) in enumerate(proposals):
            outcomes = []
            for replay in (
                    lambda: real_solver.replay_real_witness_bytes(
                        query, domain.table_bytes, domain.table_sha256, sequence, charges),
                    lambda: real_solver._replay_real(prepared, sequence, charges)):
                try:
                    value = replay()
                except (ValueError, AssertionError) as error:
                    outcomes.append(("rejected", type(error).__name__, str(error)))
                else:
                    outcomes.append(("accepted", value))
            if outcomes[0] != outcomes[1]:
                raise ValueError(f"Prepared replay differs at proposal {index}")
            if outcomes[0][0] == "accepted":
                value = outcomes[0][1]
                accepted.append((value["J"], value["Q_total"], len(sequence),
                                 sequence, charges))
            rows.append({"index": index, "sequence": sequence,
                "charges": [str(value) for value in charges],
                "status": outcomes[0][0],
                "result_sha256": _sha(repr(outcomes[0]).encode())})
        current = original(domain, hashes)
        if accepted:
            j, _, _, sequence, charges = min(accepted)
            if (not hasattr(current, "max_depth") or
                    (current.seed.primary_j, current.sequence, current.charges) !=
                    (j, sequence, charges)):
                raise ValueError("Fresh-byte final seed differs from old replay selection")
            final = real_solver.replay_real_witness_bytes(
                query, domain.table_bytes, domain.table_sha256, sequence, charges)
            if final["lex_key"] != (j, sum(charges, Fraction(0)),
                                     len(sequence), sequence):
                raise ValueError("Fresh-byte final seed failed exact key comparison")
        elif getattr(current, "status", None) is None or current.status.value != "incumbent_search_failed":
            raise ValueError("Failed-seed row changed mathematical status")
        result = {"schema": "hiroute.m5d.seed_revalidation.v1",
            "row_id": f"{od_id}_{activity}_soc3_10_n{size}",
            "source_sha256": {
                "deployable": _sha(Path(inspect.getsourcefile(original)).read_bytes()),
                "real_solver": hashes["real_solver"],
                "real_input": hashes["real_input"]},
            "query_sha256": _sha(domain.query_bytes),
            "table_sha256": domain.table_sha256,
            "candidate_sha256": _sha(domain.candidate_bytes),
            "proposals": rows,
            "proposal_count": len(rows),
            "all_proposals_equal": True,
            "seed_status": "verified" if accepted else "incumbent_search_failed",
            "seed_J": str(current.seed.primary_j) if accepted else None,
            "seed_sequence": current.sequence if accepted else None,
            "seed_charges": [str(value) for value in current.charges] if accepted else None,
            "certified_depth": current.max_depth if accepted else None}
        target = out / "seed_revalidation.json"
        with target.open("x") as stream:
            json.dump(result, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        raise FinishedComparison

    runner.construct_verified_seed = compare
    try:
        runner.run(root, graph, out, certificate, od_id, size, activity, "flat")
    except FinishedComparison:
        return
    raise ValueError("Frozen Pilot replay hook was not reached")


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:5]), sys.argv[5],
        int(sys.argv[6]), sys.argv[7])
