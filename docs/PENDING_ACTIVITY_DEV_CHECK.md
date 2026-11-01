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
Group CPU/RSS checks remain sampled monitors, not an aggregate kernel limit;
the budget policy combines conservative admission, live checks and cleanup
reserves. Actual terminal costs below are observed and conservatively closed.

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

## Observed result (two fresh rows, no repetitions)

Both new rows hit the120s loaded limit and remain **UNKNOWN**, with the same
physically verified full feasible K as both historical controls. Each feasible
plan has three positive charges; the necessary-charge lower bound remains two.
Neither new row completes within60s. No optimality is inferred from matching
incumbents, and the completed N64 cohort's denominator/results remain unchanged.

| Method | Screen | Provenance | Status | Loaded s | First physical feasible s | Query-extra GiB |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Strong | off | historical control | UNKNOWN/time_limit | 120.111 | 4.648 | 0.713 |
| Strong | on | fresh | UNKNOWN/time_limit | 120.077 | 4.452 | 0.840 |
| Scale | off | historical control | UNKNOWN/time_limit | 120.081 | 4.452 | 0.950 |
| Scale | on | fresh | UNKNOWN/time_limit | 120.079 | 4.490 | 0.920 |

These loaded observations are censored at the same limit; differences in their
overrun/serialization tails are not time-to-optimum improvements. Historical
timing comparisons are descriptive, without repetitions or control over all
host/cache variation. Input fingerprints and profile equality were verified;
the only profile addition is `pending_activity_screen=true`. One of64 input
anchors is again safely directed-unreachable, exactly as in the controls.

Scale recorded8534 pre-route Region rejections representing50824 next-action
instances, plus144 post-route rejections. Counts can overlap previous energy
and incumbent exclusions and cannot be called50824 saved transitions. Its
observed completed-transition counts were6689 off versus6680 on; leaf routes
6710 versus6846; transition input pieces93311 versus94265; transition output
pieces104256 versus107675. These are different censored prefixes, not a common
completed-work population. Peak OPEN42022 versus34077 does not establish an
asymptotic memory reduction or full-search runtime saving. Exact transition
timers were82.174s off versus83.764s on; aggregate C/S/CS work is not separated.
The screen did not resolve this hard query or establish a runtime benefit.

Strong's new row lacks solver metrics, timers, seed diagnostic and returned
depth contract. Missing values are **unavailable, not zero**. Its independently
saved feasible checkpoint and final routing metrics survived:9551 selected-leg
queries /8.383s, versus9249 /9.481s in the historical row. Scale recorded10630
/8.556s versus10338 /9.752s. No transition-exclusion claim is inferred from
these route counts. The observed feasible full K equals the historical seed
key; Strong's absent seed field is not reconstructed as a recorded seed.

### Diagnostic limitation and post-run correction

The pilot assigns solver counters only after `solve_scale` returns. An enclosing
resource exception before that assignment can therefore leave counters absent
while a verified incumbent checkpoint is retained. A tiny provider reproduces
this vulnerability by raising ResourceLimit during final metrics collection,
after the exact search's guarded block. The actual interruption point in the
real Strong run was not logged, so this is not a claimed exact stack diagnosis.

After both real rows were terminal, an optional caller-owned live counter sink
was added, and the pilot retains that sink as explicitly **partial** diagnostics
when final result construction is interrupted. It supplies neither a result,
depth certificate nor incumbent. A focused regression verifies preservation
and no fabricated completion; new counters are never backfilled into these
already-recorded rows. No real-data rerun follows this instrumentation fix.
The final46 focused checks pass normal and-OO, including the late-exception
reproduction and partial-merge semantics. This supersedes the44-check pre-run
verification only for the added diagnostic code; the numerical rows retain
their original source identity.

### Final accounting and decision

Both workers and controller PID81000 / initial invocation are terminal: two
unique starts, two finals, two finished supervisor receipts, no duplicate or
uncertain outcome, no active numerical PID. Neither OS worker guard nor live
budget guard tripped. Raw terminal inclusive charge403.802568s is preserved.
Conservative closed costs are110 development/report precharge +259.414064
fresh-worker charges (including1s margin each) +37 controller CPU seconds
(`ceil(34.388504)+2`), totaling **406.414064 /1360**. Original cumulative charge
is **11005.649970329 /28800**, remaining17794.350029671. Preprocessing is
separately **652.040677976 /900**. Graph/index cold loads are included in worker
charges; unused allowance is not permission for another pair.

The numerical source is9cbfe42aa0394c10103269c4b78027923c3c18c6; later source
changes only preserve diagnostics for future calls. Raw new rows and historical
controls are in [pending_activity_dev_check_results.json](pending_activity_dev_check_results.json).
The historical cohort, its original worker receipts and both new rows remain
unaltered. The stage's external raw root is `pending-activity-dev-artifacts-v1`.

**Recommendation:** stop the sequence of bounded performance tweaks here and
make a research go/no-go decision on the hierarchy hypothesis before more
timed work. The36 common exact N64 pairs had identical transition counts; this
new common relaxation still leaves both methods UNKNOWN on the chosen hard
cell, and Strong attribution is incomplete. Keep the safe screen opt-in and
Strong as the fair baseline. The evidence does not justify main experiments,
holdout or a hierarchy-success claim. Any continuation needs a concrete source
of additional exact exclusion with proof and measurable work attribution, or an
explicitly narrowed research claim; no further architecture, tuning or run is
implemented by this report. Original performance, larger-domain, four-charge,
external-comparison/trip-value and independent-holdout gaps remain open.
