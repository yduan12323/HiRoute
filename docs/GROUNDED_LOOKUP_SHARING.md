# Grounded lookup definitional sharing

This change is a representation-only conservative extension of the independent
physical model. It is not a new road selector, reduced domain or changed query.
For each of the seven immutable array expressions A, introduce a fresh array a
of the identical sort and the equality a = A. Substitute a for A in the model
trace. Any old model extends to a new model by interpreting a as A; conversely,
substitution of the defining equalities recovers every original constraint and
objective. Whole-array equality retains default values outside the valid index
range as well as all explicit entries. Guarded source/target ranges, separate
AS/AT maps, literal actions, aliases, inactive suffixes and reachability remain.
Fresh names prevent two independently constructed encodings from coupling.

All seven definitions live in trace.constraints and therefore m.G. Every
feasibility, optimization, strict-better, optimal-face, attainment, stop-count
and action-rank query includes m.G. The two continuous state copies, strict
support, full lexicographic objective and complete derived depth are unchanged.
Encoding.ground_trace and the original GroundedLookup retain the expanded
expressions for solver-free grounding. Concrete physical replay is unchanged.

Phase records separate parameter/upper/depth validation, lookup/physical
construction, continuous-state construction, assertion insertion, serialization,
audit hashing/writing, solver check and returned-plan replay. Process CPU in
these records is diagnostic, not a replacement for controller/tree accounting.
The supplied table has already been loaded by the caller: on-disk load/validation
requires a caller-level phase receipt before any future real admission. Every
solver timeout is refreshed after serialization and audit I/O. The external
120-second end-to-end guard is still required. A killed phase remains started;
missing completion is never converted into a solver result.

Regression coverage compares all eight existing analytic fixtures against the
inline encoding, expands each shared trace back to its exact original, checks
all seven equalities in every queried constraint set, verifies independent name
freshness and solver-free grounding, and tests serialization deadline expiry.
Existing strict-support and primary-face traps remain in the suite.

No new real query, table generation, holdout or performance claim accompanies
this development change. The previous 120-second UNKNOWN remains unchanged.
Before a real attempt, independently review this change and explicitly admit a
consumer that verifies the existing immutable table and historical producer
provenance while recording the new consumer source separately. Do not alter
old receipts to satisfy the old runner's same-source checks. Existing-input
loading must be included in the same 120-second deadline.

## Separate consumer admission (not executed)

`run_grounded_lookup_consumer.py` pins the historical producer's budget,
admission, configuration, freeze/generation/validation receipts, physics and
manifest. The original controller receipt links and clean producer source are
verified, without comparing that source to the new consumer. Preparation binds
the clean independently reviewed consumer commit and Python/Z3 environment.
It creates a new output directory and snapshots the current cumulative stage
ledger. Under the old ledger lock, it closes the predecessor as delegated before
publishing the identical cumulative budget continuation. Partial preparations
and existing output directories cannot be reused automatically.

Execution requires a current standard budget-controller optimization child with
120 CPU seconds, 120 wall seconds, 180 CPU seconds reserved, matching process
identity, unchanged inherited charges, and single-worker environment. The
exclusive started marker persists on every failure. All old failed attempts and
the previous UNKNOWN remain recorded. No producer file is edited.

Caller phase receipts cover admission, full split loading/validation, raw graph
and upper/sample replay, the independent query and final verification. All 64
Sites, 78 actions, 65x65 pairs, frozen physics/witness and complete H20 are
verified. The query receives only the wall time remaining after loading and
validation; concrete output replay and final input/source checks must fit the
same external 120-second guard. Expiration or failed verification stays UNKNOWN.
Original input costs are retained. This is not a fresh timing baseline or road
shortest-path certificate.

`run_source_bound_tests.py` records clean commit, runtime identities, command,
exit status and output-log digest under the external accounting controller.
The consumer negative tests cover producer bytes/receipt links, physics, domain,
depth, changed source/environment, budget exhaustion, duplicate attempts and
deadline expiry. This development delivery does not prepare or start the real
consumer. Independent review of the exact clean commit is required first.
