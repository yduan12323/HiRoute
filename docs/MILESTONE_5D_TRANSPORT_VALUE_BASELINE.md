# M5-D transport baseline and seed selection diagnostic

`sequential_no_overlap_baseline` is the D5.4 feasible construction baseline.
It completes charging before starting scheduled service at a combined `CS`
stop. Its fixed proposals are independently replayed on selected native road
edges with exact energy, time-window and reserve checks. It returns the best
feasible proposal in that stream, or reports that none was found. This is a
bounded construction comparison; it does not certify a sequential optimum.
The directed regression checks that a one-second charge and a two-second
service take three seconds sequentially, versus two seconds when overlapping.

The earlier `first_feasible_proposal_baseline` is a seed-selection diagnostic:

It returns the first independently
replayed feasible witness in the already fixed deterministic seed-proposal order.
It binds the full graph and candidate universe, replays the selected native
edges and exact battery/clock constraints, and reports `(J, Q, H, Pi)`. It does
not claim optimality or that no other feasible route exists. Proposal generation,
routing, and replay time are charged. The accepted minimum-seed witness uses
the same proposal stream, so `J(first feasible) - J(minimum seed) >= 0` measures
the value of selection **within that stream only**. A subsequent attained exact
FLAT/HIER result, if verified, would supply the full-domain comparison. A
timeout supplies no such comparison.

The local directed three-anchor regression verifies a one-stop feasible
construction and independent edge/physical replay in normal Python and `-OO`.
It also checks that its key is no better than the selected minimum. The fixed
real OD02 N8 probe at source `ee361ee` completed under 120 s and 4 GiB:
the first feasible proposal was ordinal 0 of 93 and equalled the best seed,
`J = 20740584436525316127/687194767360000` seconds, with two charging
stops. The measured within-stream improvement was exactly zero. This does
not establish zero benefit over other feasible constructions or full-domain
FLAT/HIER search. Its byte-bound receipt is preserved in
`/Users/dy/Documents/Codex/2026-10-09/task/m5d_sparse_value_n8_20261011.tar.gz`
(SHA-256 `b59a26f0ce72af9bb01b404c8144fe3f658e2a37580dd78fc4ea0d56226795a1`).
Larger-domain and fleet-level value are not inferred from it.

Related primary literature shows why partial recharging, time windows and
nonlinear charging should be modeled explicitly, but none of these methods is
claimed to have been reproduced here:

- Desaulniers et al., [*Exact Algorithms for Electric Vehicle-Routing Problems
  with Time Windows*](https://www.gerad.ca/fr/papers/G-2014-110), examine
  multiple and partial recharges in time-window routing variants.
- Liang, Dabia and Luo, [*The Electric Vehicle Routing Problem with Nonlinear
  Charging Functions*](https://arxiv.org/abs/2108.01273), give exact and
  heuristic algorithms for a fleet problem with nonlinear charging.

These papers motivate comparator dimensions and possible later benchmarks.
Their fleet/customer formulations differ from this single-vehicle,
capability-typed Site and scheduled-activity domain. The first-feasible
construction is an internal transparent feasible baseline, not an
implementation of either published algorithm.
