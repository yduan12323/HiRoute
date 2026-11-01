# Pending-activity screen: audit, proof and bounded validation proposal

This is an opt-in shared feasibility relaxation, not a new search architecture.
No real-data solve, cohort rerun, main experiment or holdout is authorized or
performed by this change. Baseline main is d5b719c39e6b7391c1977084f164b218f16fdb50.

## Core audit and nonredundancy

`schedule_piece` already clips arrival time to `b-h` for S, with equality
conditional on the exact cut's attainment. CS applies the same feasibility
restriction in `stop_partition`; physical replay checks it independently.
`execute_exact_plan` applies these constraints only when S/CS is attempted.
C leaves the pending flag unchanged and does not inspect a future deadline.
The old `completion_bound` includes pending duration D but relaxes windows.
Consequently the candidate adds no new physical constraint, but can reject a
C branch before its valid, potentially expensive physical family is generated.

A hand-built directed example demonstrates logical nonredundancy: h=1,
b=3, o→c time2, c→s time4, o→s time1; c supports C, s supports S.
The C prefix is physically nonempty, but even its zero-charge-time limit
finishes at time3, after the latest permitted service arrival2. Core rejects
the eventual S; this screen can reject the C branch first. This is a tiny
correctness/work-count fixture, not evidence of real-data runtime improvement.

## Necessary-condition proof

All distances here are shortest **time** distances on the existing underlying
directed graph. They are not selected-fastest-leg lengths. Let a be the current
physical anchor, R the eligible next-effect Region, and S the static union of
Sites supporting S or CS. Pending service may use any Site in S: exact search
permits revisits and has no history-dependent service exclusion. Proven
origin/destination-unreachable Sites are removed by the existing preparation.
The union counts a dual-capability Site once and is built once, identically
for Strong and Scale, with its O(N) cost charged to preparation.

For x in R and s in S, directed triangle inequalities give:

```
L(a,R) = max(0, min_R d(o,x)-d(o,a), d(a,z)-max_R d(x,z)) <= d(a,x)
L(a,S) = max(0, min_S d(o,s)-d(o,a), d(a,z)-max_S d(s,z)) <= d(a,s)
L(R,S) = max(0, min_R d(x,z)-max_S d(s,z))               <= d(x,s)
```

For next S/CS, service arrival is at least `L=max(L(a,S),L(a,R))` time after
the current physical state. For next C, it is at least
`L=max(L(a,S),L(a,R)+h+L(R,S))`: that C precedes the still-pending service and
incurs h even in its zero-positive-charge-time limit. All subsequent driving,
waiting, charging and stop overheads are nonnegative. Arbitrarily many future
stops or repeated Sites cannot reduce these bounds. At a leaf, the already
paid exact selected inbound time can replace L(a,R); the other bounds remain
unchanged. No new route, distance map or cache is constructed for this screen.

Every physical member of a family piece has time at least its affine cut
tau(E). Thus any completion through the next effect requires

```
min_over_family_and_energy tau(E) + L <= b-h.
```

Reject only a strict violation for **all** pieces. Endpoint/time infima are
evaluated as limits; equality is retained even if no physical point attains
it. An empty service union cannot complete a pending schedule. Completed-service
pieces bypass the test. No domain, attainment flag, history, witness, objective
key, incumbent or relevant-depth certificate is modified. In particular an
open infimum is never an executable incumbent. This only deletes actions with
no feasible completion, so all primary/secondary attainment and full-key ties
survive. Strict-primary incumbent pruning remains unchanged.

Region queries read static extrema and scan only physical family pieces;
they never traverse children, members, masks, feature maps or candidate lists.
Strong receives the identical service summary and singleton formulas. A Region
may be weaker than its singleton, which is safe and is not claimed as a gain.
The one-sided L(R,S) can be especially weak when service lies earlier in the
destination landmark order; no stronger directed metric is invented.

## Implementation and measurement boundary

`solve_scale(..., pending_activity_screen=True)` enables the screen; its default
is false, and `use_bound=False` disables it. The deterministic seed, road-index
policy, exact kernels and frozen historical numerical profile stay unchanged.
Pre-route Region/action rejections are counted separately from post-route
selected-inbound rejections. These counters show excluded work, not predicted
saved runtime. No source-tree cache expansion, new graph pass, energy change,
history dominance or second architecture is introduced.

Before focused tests, reserve a conservative300 CPU seconds for this development,
tiny-REF and delivery verification, within the original28800 envelope. Prior
carry is10299.235906329; after this precharge it is10599.235906329, leaving
18200.764093671. The completed N64 stage5073.157452/12000 and separate preprocessing
651.638454976/900 remain unchanged. Local test CPU is measured below this
precharge; if it exceeds the reserve, no further test admission is permitted
without reconciling the original cap. No new real-data worker is launched.

## Proposed minimal next measurement (not launched)

Use exactly the existing supported WD01 / initial18kWh / schedule / N64 domain,
with both Strong and Scale, one fresh screen-on row per method. Reuse the two
verified screen-off N64 rows as historical controls; do not rerun a valid row
for a cleaner table. Require identical input fingerprints, physical model,
seed policy, routing, inbound-energy and eager-pruning settings. Preserve both
UNKNOWN controls and do not infer exact optimality from their incumbents.

Both methods receive this same screen; the primary question is whether it
actually excludes transitions before the deadline in a hard schedule cell.
Record pre-route/late rejection counters, exact transitions, family-piece work,
loaded time/status, full K where attained, physical replay and full cold-worker
cost. A single historical comparison cannot isolate runtime noise or prove a
population performance win. Zero/weak exclusion is a valid negative outcome.

Preserve120s loaded query limit,60s target, single numerical worker/thread,
8GiB query-extra guard plus host headroom, durable receipts and cumulative
controller accounting. Proposed reservation is1240 CPU seconds for one pair
plus120 reporting/verification, within the remaining original budget. This is
a proposal only, requiring the next scoped execution decision; no broader
matrix, new domain, parameter tuning, main experiment or holdout follows from it.
