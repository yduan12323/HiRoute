# OD07 sequential feasible-construction transport gate

This is a new, independent, default-closed experiment. It is not sequential exact
search, not a finite-stream minimum, and not a claim that either compared plan is
optimal. Only two freshly feasible plans are compared. No real graph experiment
has been run while implementing or testing this package.

The sole DEV case is OD07_energy_and_scheduled_soc3_10. Restore its original
query, original Site IDs and original frozen tree IDs. Repair the original 128
with all 21 floor-reachable eligible charging Sites, without truncation, giving 149.
Hmax 37 is the explicitly declared domain for this experiment, not derived from
a sequential optimum. The original query is retained separately and all changes
(H_ref and current native sparse-domain binding) are disclosed. Inputs use the
nine known recovery identities, normally materialized at ../recovery_inputs.

Construction uses first_sequential_feasible and the existing deterministic lazy
candidate stream, whose generator still uses concurrent CS timing. Each proposal
is independently physically replayed with sequential no-overlap semantics;
stop at the first feasible proposal, generation_complete=false. This is a
feasible construction, not a sequentially optimized candidate generator.
Construction does not use the comparator route or charges for generation or
selection. It only hashes comparator bundle bytes for authentication. No joint
seed is constructed first. The callback synchronously persists the exact route,
charges, lexicographic key, edge witnesses, provenance and repaired domain before
requesting any later candidate. Stream exhaustion is UNKNOWN, not infeasibility.

## Fixed budgets and accounting

Exactly one construction worker: wall 240s, soft CPU 240s (hard 241s), AS 8GiB.
Then one fresh sequential replay: wall 120s, soft CPU 120s (hard 121s), AS 8GiB.
Then one fresh joint replay: wall 120s, soft CPU 120s (hard 121s), AS 8GiB.
All use the existing subreaper/process-tree supervisor, one permitted core and numerical
threads 1. CPU hard margins are signal-cleanup margins, not extra admitted budget.
The controller has its own cumulative 120 CPU seconds including preflight and
hashing; it preserves an inherited hard cap admitting the 241s worker and reserves
10s of its budget for finalization. All input/source hashes, native compilation,
repair, loading, candidate generation, persistence and replay are charged within
these containing budgets. These limits are not search-only times. Maximum worker
reservation is 480s execution wall, plus up to 3s cleanup per stage. CPU limits
are per process, including inherited compiler limits, not aggregate process-tree
CPU ceilings. Supervisor receipts include whole-stage wall including cleanup and supervisor-parent
process CPU; aggregate worker-process-tree CPU is not measured. The
construction_local_* fields are partial diagnostics only. Fresh providers/processes do not imply
cold OS caches. No retry, expansion, increased time, changed order or holdout.

The ledger always includes all three stages, including failed, blocked and
UNKNOWN stages. Any failure/timeout/UNKNOWN stops the sequence. A timed-out worker
may leave a durable construction artifact; it is retained but not accepted as a
completed construction, and does not authorize a retry or subsequent comparison.

## Comparator and provenance

Before launch the manifest fixes the published recovery_full_batch_20261017
bundle hash and execution/arm-03/artifacts/arm/incumbent.json hash. results.json
identifies this as the first OD07 indexed arm. Its route and charges are only
parsed by the final verification worker, after successful sequential replay.
That worker reroutes all legs with the new authenticated native implementation
and physically replays the proposal under the current repaired 149/Hmax 37 domain.
The historical binding is reported separately; its old certificate, objective
and source closure are never treated as current feasibility evidence.

Replay output exposes exact J, elapsed seconds (without stop penalty), Q kWh,
H, distance meters along the travel-time-selected road paths (not a shortest-distance
claim or driving time), service start/completion and window margin b-service_start,
and overlap seconds, all taken from replay_sparse_seed(include_events=True).
Service times are absolute query-clock times. An effect is not asserted to occur
in either plan until replay returns it. No improvement/causality claim follows
from comparing independently chosen feasible plans.

## Admission and invocation

python -m experiments.sequential_transport_gate_v1.run --plan

The checked-in manifest has launchable=false. Actual execution requires a new
external SHA256-pinned manifest, publication-verified complete source/runtime
closure (including this package), compiler binary/version/flags, exact input
identities and absolute paths. All protocol fields and the preselected comparator
remain frozen. Source must be published and clean before the manifest is closed.
The base source-closure implementation is reused with this package added once.
NativeDomain, repair_od07 and the existing supervisor are reused without copies.

python -m experiments.sequential_transport_gate_v1.run --gate --manifest /absolute/closed.json --manifest-sha256 SHA256 --output /absolute/new-output --cpu CORE

Do not launch this command merely to validate the implementation. Focused tests:
python -m pytest tests/m5d_recovery/test_sequential_transport_gate.py tests/m5d_recovery/test_first_sequential_feasible.py
python -OO -m pytest tests/m5d_recovery/test_sequential_transport_gate.py tests/m5d_recovery/test_first_sequential_feasible.py
