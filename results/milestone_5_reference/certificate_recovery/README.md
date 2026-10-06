# B07 exact certificate recovery

This is a post-discovery oracle certification repair, not a fixture adjustment
or newly independent holdout. The original B07 fixture, expected key, unresolved
run and rejected certificate remain preserved. No LP row, charging strictness,
energy bound, or acceptance tolerance changes.

## Failure

Frozen Stage-B case B07 stopped at regime 60,823, sequence `(u,C),(u,CS),(u,C)`,
segments `(0,1,0,2,0,0)`, early schedule / charge-completion branch. The closed
regime is infeasible, so REF attempted to certify that via an auxiliary Phase-I
LP. HiGHS supplied a near-optimal floating candidate. Rationalizing coordinates
independently reconstructed its slack as `32880329725/999998003`, which is
`1/3034993939105` below the true slack. Four exact constraints were violated by
that amount, and REF correctly reported the whole case unresolved.

The other coordinates and dual multipliers identify an exact common active
face. Its exact solution is:

- q1 = 141516/3035
- q2 = 4408/3035
- q3 = 0 in this closed, relaxed Phase-I auxiliary problem
- auxiliary slack = 99792/3035 > 0

The last value equals the rational dual objective. Three binding inequalities
(rows 16,18,23 in the retained rejected problem) carry multipliers
`(-2,-5,-600)/607`. Their stationarity gives the objective vector for minimizing
slack. The exact primal satisfies all original Phase-I rows, proving its
positive optimum and hence the closed regime's infeasibility. The auxiliary
q3=0 does not relax the model's strict-positive executable charge requirement.

## Repair

The existing fast path still rationalizes the floating candidate and checks
exact primal feasibility, dual signs/stationarity, and strong duality. Only when
that fails, REF now reconstructs both primal and dual coordinates by rational
Gaussian elimination on candidate active rows and exact stationarity equations.
Degenerate free coordinates can be recovered using additional independently
rank-increasing rows ordered by residual. Those choices are candidate hints;
they are never acceptance rules or changes to the LP.

Every recovered candidate passes the same unchanged full exact certificate
verifier. If reconstruction cannot supply a verified certificate, REF still
returns unresolved globally. This conservative procedure is not a complete
exact simplex implementation and may remain unresolved on difficult candidates.

## Evidence

- `b07_rejected_certificate.json`: original failure, copied byte-for-byte
- `b07_frozen_input.json`: unchanged B07 input and expected result
- `b07_minimal_lp.json`: independent three-variable/three-row reduction
- `freeze_manifest.json`: regression inputs and original hashes
- `tests/test_reference5_certificate_recovery.py`: original rejection, exact
  repaired primal/dual equations, original regime, dual-coordinate recovery,
  free-coordinate degeneracy, equality recovery, and failure-closed tests

The one-regime repair does not by itself establish a complete B07 case result.
A full population rerun must use a separately frozen new REF source and retain
the earlier unresolved record. Production source and all fixture expectations
must remain unchanged during that comparison.
