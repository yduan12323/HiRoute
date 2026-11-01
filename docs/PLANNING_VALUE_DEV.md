# Four-query planning-value DEV gate

This stage executes the previously frozen definitions in
[PLANNING_VALUE_BASELINES.md](PLANNING_VALUE_BASELINES.md), whose proposal file
is preserved unchanged. The execution allocation in
`configs/planning_value_dev_gate.json` authorizes only the original four
schedule/N64 queries and eight policy slots, in the original order. There is
no new joint run, tuning grid, larger domain, main experiment or holdout.

## Predeclared resource and measurement contract

The inclusive cap is3000 CPU seconds within the original28800, carrying
12805.649970329. Allocations are2100 for all fresh workers and cumulative
controller CPU;240 for development/focused validation and metadata preflight;
360 for PR and future merged-main dedicated CI (180 each);180 for ordinary
development/control/report/verification;120 for cancelling this PR's unrelated
automatic legacy workflow at startup. The900 nonstage allocation is charged
conservatively; actual inclusive stage CPU is added to it. No unused allocation
permits an extra query. Preprocessing remains652.040677976 /900; no graph/data
acquisition or preparation change occurs.

Every complete two-policy query pair requires1240 CPU seconds plus120 cleanup
headroom before admission. Each fresh numerical worker is limited to300 CPU/
outer wall seconds (180 cold allowance plus120 loaded query seconds), one thread,
8GiB total process and the unchanged8GiB query-extra/host-headroom guards.
The loaded watchdog includes binding, activity ranking, masks, seed, search and
replay. Controller CPU is live, cumulative across safe boundary pauses, and
included in admission and active-worker budget monitoring. Each method has a
durable start, supervisor receipt, incumbent checkpoint and terminal row.
Uncertain starts or failed/terminal controller states cannot silently restart.
Only an explicit between-pair paused state supports ordinary resume, carrying
earlier controller CPU. Every query/slot remains in the denominator if the
budget prevents its pair or an input/outcome fails.

## Adapter proof and focused validation

Only original legal actions are removed. Candidate/effect order is preserved;
an actionless Site is a policy restriction, while its road vertex and every road
edge remain in the shared provider. All physical fields, objective, depth,
charging curves and selected-leg contracts are unchanged. Thus every policy
plan is feasible for the original model; relevant depth and strict-charge/
attainment/full-key semantics use the unchanged Strong solver on that subset.
No independently legal C/S action is synthesized at a CS-only Site.

Activity-first computes exact directed-time features within the loaded budget,
then invokes the already frozen pure time-only ranking function. It does not
filter by energy or accept a joint result, key, plan or seed. The selected Site
never changes after seeing charging feasibility. Both policies use the same
deterministic Strong seed procedure under their own masks.

Every new feasible witness is independently physically replayed under both the
policy and original snapshots. Charging duration is recomputed from the exact
curve; CS overlap is the charging/service interval intersection; distance delta
against the direct fastest leg remains signed. Positive charges and total stops
are reported separately. Historical joint controls are read only by the final
report join after durable terminal baseline receipts, with exact domain/model/
profile identity checks. UNKNOWN controls remain feasible references, not
optima or contemporary runtime controls.

Nine focused tests cover subset/order/physical-field
preservation, CS-only exclusion, energy-independent activity choice, original
replay with strict positive charge, full tiny policy keys, inclusive budget
boundary, persistent failure/unrun receipts, safe resume accounting and duplicate
execution rejection, plus actual worker dispatch/checkpoint/no-activity receipts
using a tiny substituted index. The analytic tiny schedule has original/fixed-site CS key
(16,3,1), versus separated C-then-S key(30,3,2); both replay under the original
model. A signed length delta of-1 is retained. These are correctness fixtures,
not real application results. One initial test-only deepcopy of immutable road
metadata failed; it was corrected and its CPU receipt retained.

## Execution status

Implementation/tests precede source freeze and real execution. No real row is
claimed by this initial version. Final results will retain all four queries/
eight policy slots, attained/unattained/resource/unavailable/budget statuses,
actual feasible values, physical metrics and historical-control limitations.
Small selected DEV contrasts cannot establish a causal or population-wide
benefit. Original taskbook timing/scale, real four-charge, independent real-domain
comparison and frozen holdout acceptance remain unmet.
