# Bounded rational reconstruction after a failed one-row neighborhood

The existing direct, greedy active-row and one-row exchange paths are retained.
Only the exact `Exact basis-exchange neighborhood did not certify the candidate`
failure enters the new fallback. A dimension limit, trial limit, timeout or other
failure does not enable another search. The native LP settings, model rows,
strict-face protocol and independent certificate checker are unchanged.

The fallback visits at most 512 bases and retains at most 4096 distinct row-ID
tuples. Dimensions remain at most32 variables,256 inequalities and32 equalities.
Each queued basis contains only original inequality row IDs; all original
equalities remain mandatory. Traversal is deterministic breadth-first order:
violated rows in original order, then leaving positions in sorted basis order.
Singular/inconsistent bases are discarded. Every unsuccessful cap or exhausted
neighborhood remains unresolved. The enclosing per-model30-second process and
resource guard remains authoritative; this helper makes no native call.

For each exact basis point, an optional coordinate lift can repair several
epigraph rows together. A coordinate is eligible only when its objective
coefficient and every equality coefficient are exactly zero. Coordinates are
discovered in an acyclic order: every row with a positive coefficient in a new
coordinate must have a negative coefficient in a previously discovered one.
Reverse-order processing raises each coordinate by the exact minimum sufficient
to satisfy all rows in which it is negative. A raise cannot change objective or
equalities. Any inequality it worsens has a later repair direction. Cycles and
objective/equality-constrained coordinates are excluded. Rows outside this
repair structure can remain violated; they guide further basis exchanges.

The lift is candidate construction, not acceptance. Full primal feasibility,
equality feasibility, nonpositive inequality duals, stationarity and exact
strong duality are rechecked by the unchanged vendor verifier. The independently
authored suffix checker rechecks the published certificate. Certificates retain
the existing wire schema; active-row annotations include only rows actually
tight after the lift. Model constants, later optimum-face RHS values and
physical witness obligations are unchanged.

Hand fixtures demonstrate two distinct limitations of the old neighborhood:
successive energy-face changes and simultaneous free-clock epigraph repairs.
Tests also cover fake-native single-pass use, row permutations, redundant
equalities, prohibited objective/equality movement, cycles, invalid duals,
infeasible systems, interrupted execution and both finite count caps.

The frozen window.051 diagnostic keeps its historical vendor source pin. It
must be run on its original reviewed diagnostic commit; this change does not
silently repoint that diagnostic or alter its retained observations. The three
recorded native hints can be reconstructed and their resulting rational
certificates checked without another native LP call. Such a first-task check
does not complete a model's remaining stages or register its failed window.

Focused command: `PYTHONPATH=src:tests:. python -m unittest
test_suffix_basis_walk test_suffix_basis_exchange -q`; repeat under `-O` and
`-OO`. Fixtures call no native optimizer.
