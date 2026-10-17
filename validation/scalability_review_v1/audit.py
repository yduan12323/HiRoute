#!/usr/bin/env python3
"""Independent graph-free equivalence audit; no solver/road timing claim.

Run from the repository root:
  python validation/scalability_review_v1/audit.py --output validation/scalability_review_v1/audit_results.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction as R
import hashlib
from itertools import product
import json
from pathlib import Path
from random import Random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from timecut5.probe import AffineFamily, Cut, Interval, State, reduce_cuts
from timecut5.pwa import CutPiece, _same_state_energy_skyline, reduce_frontier, reduce_frontier_skyline
from timecut5 import provenance as prov

POINT_SEED = 20261017
PWA_SEED = 8172026


def equal(actual, expected, context):
    # Deliberately works under optimized Python, independently of assert.
    if actual != expected:
        raise AssertionError(context)


def point_audit():
    state = State("v", 1, 1)
    items = [Cut(R(tau), chi, R(2), R(rho), ((pi, "C"),), state,
                 lambda epsilon: None)
             for tau, chi, rho, pi in product(range(3), (False, True), range(3), ("a", "b", "c"))]
    count = 0
    for indices in product(range(len(items)), repeat=3):
        cuts = tuple(items[i] for i in indices)
        equal(tuple(map(id, _same_state_energy_skyline(cuts))),
              tuple(map(id, reduce_cuts(cuts))), ("ordered_triple", indices))
        count += 1
    rng = Random(POINT_SEED)
    for case in range(2000):
        cuts = tuple(rng.choice(items) for _ in range(rng.randrange(70)))
        equal(tuple(map(id, _same_state_energy_skyline(cuts))),
              tuple(map(id, reduce_cuts(cuts))), ("random_point_list", case))
    return dict(point_universe=54, exhaustive_ordered_triples=count,
                random_long_lists=2000, random_list_length_range=[0, 69],
                seed=POINT_SEED, stable_identity_equivalence=True)


def pwa_audit():
    rng = Random(PWA_SEED)
    checks = 0
    for case in range(250):
        descriptors = []
        for _ in range(rng.randrange(1, 14)):
            lo, hi = sorted((R(rng.randrange(-4, 5), rng.randrange(1, 5)),
                             R(rng.randrange(-4, 5), rng.randrange(1, 5))))
            lc, rc = ((True, True) if lo == hi else
                      (bool(rng.randrange(2)), bool(rng.randrange(2))))
            descriptors.append((Interval(lo, hi, lc, rc),
                                R(rng.randrange(-3, 4), rng.randrange(1, 4)),
                                R(rng.randrange(-3, 4), rng.randrange(1, 4)),
                                bool(rng.randrange(2)), R(rng.randrange(-2, 3)),
                                ((rng.choice("abc"), "C"),)))
        repeat = rng.randrange(len(descriptors))
        outputs = []
        for reducer in (reduce_frontier, reduce_frontier_skyline):
            with prov.Recorder() as recorder:
                pieces = [prov.bind(CutPiece.from_affine(AffineFamily(*d, State("v", 1, 1))),
                                    "analytic", seed_index=i)
                          for i, d in enumerate(descriptors)]
                pieces.insert(repeat, pieces[repeat])
                result = reducer(pieces)
                requests = []
                for piece in result:
                    energy = (piece.domain.lo + piece.domain.hi) / 2
                    for epsilon in (R(1), R(1, 10**50)):
                        requests.append(prov.witness_dict(piece.at(energy).approach(epsilon)))
                outputs.append((recorder.export(result), recorder.export_witness_requests(), requests))
        equal(outputs[0], outputs[1], ("PWA provenance and witness mismatch", case))
        checks += len(outputs[0][2])
    return dict(random_pwa_families=250, seed=PWA_SEED,
                witness_requests_per_arm=checks, epsilons=["1", "1/" + str(10**50)],
                repeated_parent_object_per_family=True,
                exact_recorded_dag_batch_roots_and_witness_equality=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    result = dict(schema="hiroute-independent-scalability-audit-v1",
                  status="PASS", graph_free=True, real_query_runs=0,
                  timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  python=sys.version, optimized_python=bool(sys.flags.optimize),
                  git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  command="python validation/scalability_review_v1/audit.py --output validation/scalability_review_v1/audit_results.json",
                  invocation=[sys.executable, *sys.argv],
                  source_sha256={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                                 for path in ("src/timecut5/pwa.py", "src/timecut5/probe.py",
                                              "src/timecut5/provenance.py", "validation/scalability_review_v1/audit.py")})
    result["point_audit"] = point_audit()
    result["pwa_audit"] = pwa_audit()
    result["audit_wall_seconds_descriptive_only"] = time.perf_counter() - started
    result["limitations"] = ["Finite equivalence audit against unchanged baseline, not a theorem proof.",
                              "No real-road query, optimum, scalability acceptance or performance claim.",
                              "Synthetic provenance roots test exact export equivalence, not independent physical replay."]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
