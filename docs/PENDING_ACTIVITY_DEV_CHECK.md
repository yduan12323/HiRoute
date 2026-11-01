# Frozen two-row pending-activity DEV check

Predeclared before either new numerical worker. This follows merged main
7392383c9d805ff62d826a0afe088d16303a9597 and changes only the pending-activity
screen flag in the numerical profile. Scope: WD01, initial18kWh, schedule, N64;
Strong first, then Scale, once each. No control rerun, grid, other OD/domain,
physics/seed/routing change, main experiment or holdout.

## Inputs and controls

`configs/pending_activity_dev_check.json` selects one cell from the unchanged
48-cell N64 matrix. Its candidate-domain SHA256 is
`2a8f28645f781049a73619eb8222dd730261b58318d1f73f295edf08dad4dc64`.
Preparation verifies catalog/binding/graph provenance, model, endpoints,
qualified counts, candidate fingerprint and host memory/disk before execution.
Historical screen-off controls are read from `docs/n64_coverage_stage_results.json`
(numerical source fb6989f34c34f1c2c23cacba0dd96ae79d38f63f). Both controls timed
out and remain UNKNOWN; matching their incumbents cannot establish optimality.

Strong and Scale share the existing source-tree reuse, landmark A*, rank-lazy
seed, inbound-energy bound, eager queue pruning and all physical settings. The
pilot now explicitly forwards `pending_activity_screen` to the shared solver.
Only the two new screen-on rows are freshly executed. Both require independent
physical replay; compare full K/attainment when exact completion occurs.

## Limits and accounting

Hard additional1360 CPU seconds within28800 original, carrying10599.235906329.
Pair admission reserves1240 (310 worker +310 controller per method). Of the
remaining120,110 are conservatively precharged for development/reporting, and10
are initial controller headroom. Actual cumulative controller CPU is counted
live, not replaced by its allowance. Fresh workers retain120s loaded limit,
180s cold allowance,300s guarded worker wall/CPU, one thread and8GiB process/query
guards with the existing host headroom. Preprocessing remains separate,
carrying651.638454976/900 before this data-only preflight.

The existing durable controller now also passes a live inclusive budget guard
into the OS supervisor. It combines development, previous workers, cumulative
controller CPU and active-worker CPU peak; it rejects30 CPU seconds before
either cap for sampling, completed compiler CPU, cleanup and serialization.
Rejection uses the existing resource-stop group cleanup, never a mathematical
completion. Guard exceptions also reap the leader and clean its group before
being recorded terminal. A low remaining reservation stops the next method.
Locking, source/input consistency, write-once starts and uncertain-outcome
recovery remain in force. No automatic replay of an uncertain start is allowed.

## Verification before execution

44 scoped controller/pilot/screen/guard checks passed normal and-OO. This
includes the one-cell denominator, exact sole profile override, cumulative
controller and previous-worker budget input, no duplicate resume, guard resource
cleanup, error cleanup and actual pilot flag forwarding. Earlier direct local
Linux-/proc tests failed on Mac; adapter-assisted legacy OS checks also exposed
Mac-specific signal/address-space limitations. Their assertions remain intact
for Linux CI. The new guard checks use the same established Mac monitor adapter
as the production pilot; no failed check is called a pass. Failure logs and CPU
costs are kept externally (with credential values redacted from tracebacks).

## Interpretation and stopping rule

Report raw outcomes, loaded/cold/CPU costs, full K, seed identity, physical
replay and complete relevant-depth semantics. Record pre-route and post-route
screen decisions separately. These counts are not incremental savings: energy
or incumbent bounds could reject overlapping actions. Compare actual work and
timing descriptively with historical controls, without a causal speedup claim.
Any negative/weak result remains visible. No tuning or additional pair follows;
the next decision is whether the measured common relaxation helps enough to
justify broader research, while the hierarchy novelty/performance gaps remain.
