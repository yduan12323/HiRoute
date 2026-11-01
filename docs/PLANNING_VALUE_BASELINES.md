# Frozen planning-value baseline contracts, v1

These are **definitions, not results**. No policy solve or real graph query ran
in the compact-comparator design gate. The policies evaluate user-facing trip
choices within the same original modeled candidate domain; they are not new
claims about hierarchy, published-method superiority or full-province optimality.

## Common physical and information contract

Both policies use the unchanged battery, consumption, reserve, charging curve,
activity window/duration, overhead, stop penalty and exact selected-leg contract
of the frozen joint snapshot. Every returned plan must be feasible under that
original joint model. Masks may only remove legal actions, never invent C/S
capabilities, turn a CS-only Site into an S Site, allow zero-charge C/CS, merge
histories or reroute selected legs through unrecorded waypoints.

The original N64 domain fingerprint remains the common workload definition.
Actionless Sites may be absent from an effective solver adapter, but original
candidate counts and mask-derived active/action counts must both be reported.
An adapter preserves original candidate order when filtering actionless Sites;
it must not derive a nondeterministic search order from the mask's set iteration.
That is a policy restriction, not unavailable source data or a safe reduction
of the joint domain. Service-only POIs never become energy candidates. The road
graph remains unchanged even when a Site has no permitted policy action.

Both policy planners use current Strong Flat-BB with the same exact routing,
kernels, information access and deterministic seed **procedure**, under their
own action masks. Constructing masks, ranking, directed-time features, feasible
seeds and replay all costs time. Each seed must be feasible under that policy;
missing a seed is not infeasibility and no hidden H cap is allowed. Joint-control
keys, plans and seed records are prohibited as ranking/search/upper-bound inputs.
The reporting join reads them only after durable baseline terminal receipts.

Cold initialization, loaded time, total/query-extra memory and all controller/
worker CPU are recorded under the existing resource guards. Each method/query
has120s loaded time, one numerical worker/thread and the same host headroom and
8GiB query-extra policy. This is an application-policy comparison: different
feasible sets and historical controls do not establish a causal algorithm
runtime speedup.

## Policy A: separated_no_overlap

Retain only the original C and S actions; remove CS. All legal activity Sites
remain available for policy search. C-then-S at the same Site is allowed only
when both actions were independently legal, and it incurs two physical stop
overheads/penalties. Charging and activity are sequential; overlap is zero.

This is a **no-overlap policy comparator**. Its activity/charging Site choice
still uses joint search within that restriction, so it does not represent every
possible fully decoupled planner. Relative to the original problem it is a
restricted-policy heuristic, even if its policy optimum is proved. Differences
include stop count, overhead, detour and timing; they are not a pure causal
estimate of charging/activity overlap alone.

If removing CS leaves no legal service action, report `policy_no_eligible_activity`
or a justified policy-infeasibility proof. Do not relabel it source-data absence,
invent S at a CS-only Site or change the window to repair it.

## Policy B: activity_first_fixed_site

First choose one activity Site without energy/charge planning. For each original
S/CS Site, require explicit exact directed shortest-time features
`T(o,s),T(s,D)`. A missing feature record is an input error; explicit None means
proved directed unreachability. Reject a Site only when reachability is disproved
or `t0+T(o,s)>b-h`, a safe necessary deadline test. Do not reject it merely because
the initial battery cannot reach it without intermediate charging.

Rank the remaining Sites by

`max(a+D,t0+T(o,s)+h+D)+T(s,D)+lambda`, then canonical Site ID.

This is an **energy-relaxed ranking score**, not an executable one-stop plan,
incumbent or optimality value. The helper's interface accepts no energy,
charging-curve or solver-result argument. The ranking is invariant to a common
time translation. Select the first Site only: no fallback to the next candidate
after seeing charging outcomes, no oracle from the joint route.

Then plan charging with C actions wherever originally legal and S/CS only at
that fixed activity Site. Retain CS there if originally legal, including its
strict positive-charge requirement. Do not synthesize C at other CS-only Sites.
Activity-first describes the decision order, not the first physical stop:
legal charging stops may occur before and after the fixed activity.
This policy preserves the possibility of overlap but fixes the activity choice
before charging planning. Failure to find a feasible plan stays in the report;
there is no hidden repair/reselection loop.

The executable pure definitions are `comparison/planning_policies.py`.
Focused tests cover capability subsets, exact ties, time shifts, deadline
equality, missing versus unreachable features and overlap interval arithmetic.
Those toy definition checks are not application-value measurements.

## Value, feasibility and failure reporting

Any policy-feasible plan belongs to the joint feasible set. Therefore an
**attained joint optimum's full key** must be <= every verified policy key on
an identical input domain. A contrary verified result is a correctness/input
counterexample: stop affected comparisons and investigate rather than claim
that a restricted policy beats a proved joint optimum.

For an UNKNOWN joint control, its recorded feasible route is only a feasible
reference. A policy can legitimately improve that observed route. Report
`delta_J_vs_observed_joint_plan`, not an optimality gap. Do not promote the
joint incumbent to optimality because two solvers found the same key. Open
infima are bounds, never actual trip values. Compare actual replayed J,Q,H,Pi,
elapsed time, total charge/time, drive time/distance, service and overlap.
Count positive charging actions separately from total stops H.

CS overlap is the interval intersection between charging
`[arrival+h,arrival+h+delta]` and service
`[max(a,arrival+h),max(a,arrival+h)+D]`. It is **not always min(delta,D)**:
charging may finish while waiting for a later activity start. Distance delta
against the canonical direct fastest leg is signed; that leg's length need not
be the shortest-distance metric, so a negative length delta is possible.

Preserve these distinct outcomes for every recipe:

* attained optimum **within the policy**, with a replayed key;
* primary/secondary-unattained policy objective, with any feasible incumbent
  separately labeled and replayed;
* proved policy infeasibility (not joint infeasibility);
* resource UNKNOWN with or without a verified feasible plan;
* no eligible policy activity, source-input unavailable, budget-unrun or
  verification error.

No resource termination counts as optimal. No infimum is substituted for a
missing feasible value, and failed/unrun cells do not disappear from denominators.
Infeasibility requires an actual completion/structural proof, not a missing seed
or exhaustion of an arbitrary diagnostic cap.

## Frozen DEV proposal and admission

`configs/planning_value_baselines_dev.json` freezes both policies and four
existing schedule/N64 query cells: WD01 and WD07, each at18/48kWh initial energy.
It keeps original candidate-domain fingerprints and input/source-report hashes.
There are **eight unexecuted policy slots**, all `not_started_definition_only`.
The configuration explicitly has `execution_authorized:false` for this gate.

Ordering is SOC ascending then OD ID, alternating policy order by query ordinal.
These are selected DEV contrasts, not a prospective population sample or holdout.
No query is replaced because it is difficult. Historical Scale joint controls
are fixed for the value join; Strong records remain consistency evidence, not
an outcome-selected best-of-method reference. WD01 controls are UNKNOWN and
must remain labeled that way; historical timings are not contemporary runtime
controls. Before measurement, verify physical/domain/profile compatibility
without a fresh joint solve.

The proposed separate stage has an inclusive1800CPU-second cap inside the
remaining original budget. Existing conservative admission reserves1240 before
a fresh two-policy query pair plus120 reporting/controller allowance. Actual
cold/worker/controller CPU is charged live. This cap does **not guarantee all
eight rows will be admitted**; stop before a pair if it cannot fit, retain the
unrun suffix and keep the full4-query/8-slot denominator. No temporary cap,
wall-limit or physics extension is permitted to finish the table.

Preflight must confirm data/version availability and host/disk/memory headroom;
no acquisition or new graph preparation is authorized by this proposal. Methods
share the exact same source snapshot, caches/resources and physical kernels.
Only the declared policy changes allowed actions/site choice. Every new feasible
witness is physically replayed before value comparison. A staged result table
must distinguish mathematical status, actual feasible value, completeness,
cost and missing data. Definitions alone do not satisfy taskbook section8.2.
