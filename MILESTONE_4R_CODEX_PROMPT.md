# Codex Prompt — Milestone 4R-A

You are working in the existing **dy-HiRoute** research repository.

Your task is to implement the first stage-gated pass of **Milestone 4R: State-Aware EV Stop Planning Semantics**.

Read `RESEARCH_SPEC_v0.2.md` first and treat it as the normative formulation. Then inspect the repository, accepted milestone reports, schemas, tests, and existing utilities before writing code.

## Primary objective

Replace the old Milestone 4B compound-task semantics with a clean **vehicle-stop-first** substrate and a deterministic flat stop-planning baseline.

The research object is EV route/stop planning and time utilization. It is **not** restaurant/hotel/business recommendation.

Do not rebuild the final hierarchical Opportunity Region algorithm or the full active-information Go-2 algorithm in this pass.

---

## Non-negotiable semantic rules

1. **Vehicle-stop-first:** executable actions are vehicle stop events, not arbitrary POIs.
2. **No primitive compound tasks:** do not use `charge_meal`, `charge_parking`, `sleep_charge`, etc. as fundamental task units.
3. **Independent requirements:** charging and the generic scheduled stop are separate; one Site may satisfy both.
4. **No consumer-business ranking:** meal/lodging/toilet objects are aggregate local support only.
5. **Static/dynamic separation:** static Sites must not contain current detour, ETA, arrival energy, generalized cost, or user score.
6. **Energy reserve is a constraint, not a reward:** extra terminal SOC/energy has no intrinsic utility.
7. **Charging amount is globally coupled:** extra charging now may be useful only if it improves downstream route/stop structure.
8. **Stop consolidation:** compatible charging + local scheduled activity at one anchor may overlap in time.
9. **Stop count means distinct vehicle stop events.**
10. **Unknown is not absent.**
11. **Region membership is never a physical-feasibility constraint.**
12. **Do candidate pruning before information-query logic.**

If existing code conflicts with these rules, preserve the old code/results for reproducibility and implement the new semantics in a separate 4R namespace rather than silently changing old milestone outputs.

---

## Step 0 — Audit and preservation

Before modifying anything:

- inspect repository structure;
- inspect environment files;
- inspect M1/M2/M3A/M4A/M4B reports;
- inspect the M4A opportunity inventory schema and capability fields;
- inspect graph and routing APIs;
- inspect existing tests and naming conventions;
- inspect whether Git is available and record `git status`;
- create a hash/metadata manifest for protected accepted artifacts.

Do not download new geographic data.

Do not alter frozen source PBFs, graph artifacts, OD artifacts, M1–M4B reports/results, or prior accepted outputs.

If the repository has an established milestone directory convention, follow it. Otherwise create an isolated Milestone 4R namespace.

Document the exact files you treat as protected.

---

## Step 1 — Build static Stop Sites

Construct a stable `StopSite` representation from the existing opportunity inventory.

### Anchor rule for this first pass

A raw opportunity may serve as a vehicle anchor only if the existing inventory identifies it as transportation-capable through one or more of:

- `charge`
- `parking`
- `rest`
- `services`

Do not make `meal`, `sleep`, `groceries`, `pharmacy`, or `toilets` objects vehicle anchors solely because those POIs exist.

If an object has both a transport capability and a support capability, it may be an anchor because of the transport capability.

Do not invent additional OSM semantic rules without documenting them.

### Stable ID

A Site ID must be independent of:

- OD;
- envelope budget;
- SOC;
- time window;
- preference parameters.

For this pass, prefer one Site per raw transportation anchor. Do not aggressively spatially merge anchors.

### Static schema

Store only static primitives, e.g.:

- stable Site ID;
- source OSM identity/type;
- coordinates;
- attached vehicle-road node;
- transport capabilities;
- charger/parking/access metadata already supported by the source inventory;
- static context/tag evidence;
- aggregate local-support primitives.

Add a schema-level regression test ensuring dynamic fields such as `detour`, `arrival_time`, `arrival_soc`, `generalized_cost`, or OD progress are not serialized into the static Site artifact.

---

## Step 2 — Aggregate local support

The theory uses human local accessibility. In this first pass use an explicitly labeled **geographic-distance proxy** unless the repository already contains a trustworthy pedestrian/local-access graph.

Make the radius configurable.

Run:

- 250 m
- 500 m primary
- 750 m

For each Site compute at minimum:

- `meal_count`
- nearest meal distance
- `toilet_count`
- nearest toilet distance
- `lodging_count`
- nearest lodging distance

Do not rank or recommend individual businesses.

The default scheduled-stop support predicate for the core experiment is:

`meal_count >= 1`

Keep this threshold configurable.

Do not perform quadratic Site×POI scans. Use a spatial index and report runtime/memory.

Preserve raw evidence; do not introduce an unvalidated semantic facility-dedup algorithm in this pass.

---

## Step 3 — Trip-conditioned evaluator

Implement a separate trip evaluation layer that takes a static Site plus the current/partial plan and computes dynamic quantities.

At minimum support:

- road travel distance/time through existing graph utilities;
- arrival time;
- arrival energy;
- detour;
- energy feasibility;
- required charging energy;
- charging duration;
- scheduled-stop satisfaction/time penalty;
- stop-duration overlap.

Never write these values back into the static Site artifact.

---

## Step 4 — Canonical EV model

The code must be parameterized.

For deterministic regression/default diagnostics, use:

- battery capacity: 60 kWh
- energy consumption: 0.16 kWh/km
- terminal reserve: 10% of capacity
- robust energy margin: 0 for deterministic primary tests

Implement charging through an interface that supports a nonlinear piecewise charging curve.

A synthetic default curve is acceptable, but put it in config and label it an experimental canonical EV model, not measured vehicle-specific performance.

Do **not** implement a fixed "charge to 80%" policy.

---

## Step 5 — Flat deterministic stop planner

Implement semantics correctly before optimizing for scale.

The generalized cost must separate:

- actual clock time;
- distinct vehicle stop-count penalty;
- scheduled-stop miss/time penalty;
- any additional configured non-time dimensions.

At minimum:

`J = T_clock + lambda_stop * N_stop + P_requirements`

Actual stop/detour/charging times are already inside `T_clock`. Do not double-count them in `lambda_stop`.

### Energy semantics

- preserve energy feasibility throughout;
- satisfy terminal reserve;
- departure energy is a decision variable;
- extra terminal energy has no intrinsic benefit;
- extra charging may be chosen if it reduces later stop/time/detour consequences.

### Stop semantics

If charging and the generic scheduled activity are compatible at one Site:

`stop_duration = overhead + max(charge_duration, scheduled_activity_duration)`

not their sum.

Same anchor + charge + meal support + toilet support is one vehicle stop event.

### Search architecture

Use a stateful/label representation suitable for dynamic coupling. A label should represent at least:

- current anchor/state;
- elapsed time;
- current energy;
- scheduled requirement status;
- number of vehicle stops;
- accumulated generalized cost.

DP, label-setting, or another resource-constrained search method is acceptable.

Do not call a real-data planner “exact” if candidate caps or sparse transition heuristics silently remove feasible plans.

It is acceptable for:

- synthetic small cases to be exhaustive/exact;
- real-data one-stop cases to be exhaustive over all eligible Sites;
- multi-stop real-data diagnostics to be explicitly approximate if required for tractability.

---

## Step 6 — Semantic regression tests

Create small synthetic graph/world fixtures where the correct answer is known by exhaustive enumeration.

Implement at least these tests:

1. Enough energy + scheduled stop does not force charging.
2. Insufficient energy rejects non-charging infeasible plans.
3. One charger Site with local meal support can satisfy charging + scheduled stop in one vehicle stop.
4. A local restaurant object never becomes a second vehicle waypoint merely to satisfy the scheduled activity.
5. Charge + meal + toilet at one anchor counts as `N_stop = 1`.
6. No fatigue/rest stop is inserted without an explicit rest requirement.
7. A later charger aligned with the scheduled window may beat an earlier charger if reserve remains feasible.
8. If 55% departure energy is enough for destination and the vehicle already has 76%, the planner does not wait merely to reach 80%.
9. If 15 extra charging minutes now remove a later stop costing 25 minutes, the planner may choose the extra charging and skip the later stop.
10. A configurable `lambda_stop` can make a one-stop plan beat a similar-clock-time two-stop plan.
11. If candidate B's optimistic best cost cannot beat incumbent A by more than `epsilon_dec`, B is pruned before query logic.
12. A materially better candidate with unknown charger usability remains conditionally viable.
13. An unfavorable query can trigger fallback to A if A remains reachable after latency.
14. The planner must not continue waiting for a query if the intended fallback becomes infeasible after latency.
15. Region labels/IDs alone do not remove an otherwise feasible flat plan.

These are acceptance tests. Fail the milestone if the semantics fail.

---

## Step 7 — Minimal uncertainty/query interface

Implement only the minimum types/pure functions needed for the regression tests:

- `present / unknown / absent`
- charger existence vs charger usability
- plan/Site cost interval `[LB, UB]`
- `epsilon_dec` pruning
- query cost/latency/reliability fields
- fallback feasibility after query latency

Do not implement the final Go-2 acquisition policy.

Do not make the planner Bayesian merely because a synthetic test generator might use randomness.

---

## Step 8 — Real-data development diagnostic

Use the existing 30 OD pairs only as a development set.

Do not claim final validation.

Report:

- raw opportunity count used;
- number of transportation anchors / Stop Sites;
- Site counts by anchor capability;
- support-coverage statistics at 250/500/750 m;
- fraction of all Sites with meal support;
- fraction of charger Sites with meal support;
- Site counts inside practical Safe Detour Envelopes;
- tractable one-stop exact diagnostics;
- any limited multi-stop diagnostic, clearly labeled exact or approximate;
- runtime and peak memory.

If a semantic scenario cannot be instantiated on a given OD, report that rather than forcing it.

Do not tune the method to specific known bad ODs and then treat the same OD set as holdout evidence.

---

## Step 9 — Report and preservation check

Produce `MILESTONE_4R_REPORT.md`.

The report must include:

- scope;
- exact source/input artifacts;
- environment/package versions;
- exact commands;
- all configuration values;
- static Site schema;
- support aggregation method;
- EV/charging model;
- planner state/action definition;
- exact versus approximate claims;
- all test results;
- real-data diagnostics;
- runtime and peak memory;
- protected-artifact hash verification;
- limitations;
- explicit statement that revised Go-1 has **not** yet been established.

At the end:

- run all pre-existing tests;
- run all new 4R tests;
- verify protected artifacts did not change;
- show `git diff --stat` / relevant diff if Git exists.

---

## Hard-stop / escalation rules

Stop and report rather than silently improvising if:

- the existing opportunity schema cannot support the stated transport-anchor rule;
- charger/parking/access semantics are ambiguous enough to require a new OSM interpretation;
- a protected artifact appears corrupt or incompatible;
- tractable real-data multi-stop search would require an unproven feasibility restriction;
- memory use is projected to exceed the server limit;
- an existing accepted test fails.

In those cases, explain the blocker and propose the smallest scientifically defensible change.

---

## Acceptance gate

Do not declare Milestone 4R-A complete unless:

- all pre-existing tests pass;
- all semantic regression tests pass;
- protected artifacts are unchanged;
- static Site IDs are stable across OD/budget/preferences;
- static Site files contain no trip-conditioned fields;
- non-transport POIs are not emitted as vehicle waypoints in the core scheduled-stop logic;
- same-anchor activities overlap correctly;
- global charging tests demonstrate future-stop coupling;
- extra terminal energy is not directly rewarded;
- support aggregation is reproducible and spatially indexed;
- every approximation is explicitly labeled;
- the report avoids claiming revised Go-1 success.

Once these conditions are met, stop. Do **not** continue into a new Region hierarchy or full active-information experiment in the same run.
