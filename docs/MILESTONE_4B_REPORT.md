# Milestone 4B — topology gateways, exact local microplans and structural Go-1

This is the first measured candidate-compression / abstraction-regret experiment.
It evaluates fixed structured activity tasks on the frozen static road graph.
It does not certify real-world access, preserve arbitrary human utility, or test
partial information, minimax regret, semantic evidence or active acquisition.

## Preservation and acceptance

Initial Git commit `5757944207802566a864509edb7bb4af208f6e31`, dirty state **False**.
All **64** previous acceptance tests passed in **102.55 s** before
implementation. All three previous preservation checkpoints, both road graphs,
six dated source hashes/headers, opportunity snapshot/inventory and every
checksummed 4A result were verified read-only. Final protection check:
**True**, **493** files, zero changes.
`RESEARCH_SPEC.md` SHA256 `d594f4ac78e1bfe8903c98d48bb20c4e9e3f2b15f1e8fed5fedde964be7ead04` is unchanged.
Final suite: **{'tests': 84, 'failures': 0, 'errors': 0, 'skipped': 0}**. Previous outputs/configs/modules were not regenerated.

All 30 original remapped ODs, seven ratios and eight configured tasks were
processed, with all-attached/conservative access and no-dwell/structural-dwell
scenarios. Four practical budgets are primary. Nine 2.00 risk ODs
`[0,1,4,9,10,16,19,22,23]` remain flagged and retained. No practical case carries
that boundary-risk flag. No 4A region parameter was retuned using regret.

## Exact flat oracle and task scope

The flat reference enumerates the complete **explicit local-task formulation**,
not every possible multi-stop tour or every Pareto road path. Single tasks use
one object; compound tasks allow one multi-capability object or two distinct
objects, each contributing at least one required capability and whose union
satisfies the task. Both visit orders are considered, including objects at the
same access node. Maximum two visits. Parking-only is secondary; the seven
primary tasks have equal OD/budget/utility weight rather than candidate-count
weight, preventing the 55.4% parking inventory from dominating conclusions.

Compound pairs must be within 1800 m projected geography, with ordered minimum
road distance <=2500 m and ordered fastest time <=600 s. These rules explicitly
define a nearby local bundle and apply identically to flat and region sets. The
600 s rule was nonbinding in the measured sparse queries: all
**4,967,648** ordered requests had
finite costs within it. The previously verified 4A neighbor list is complete for
these spatial/distance cutoffs; configurations exceeding it are rejected.
Single-object tasks have no local-pair cutoff.

For ordered visits, exact mobility cost is
`d(s,o1) + d(o1,o2) + d(o2,d)` (omit the middle term for one visit). Every complete
plan must pass `C <= B + 1e-8 + 1e-10*B`; individual envelope membership is only
necessary. Triangle inequalities safely exclude pairs with either member outside
the maximum envelope. Capability and complete local-pair screening are exact for
the declared tasks. No heuristic oracle sampling or geographic baseline-route
buffer is used. Independent exhaustive toy oracles detect both zero region loss
and a valid excluded cross-region bundle with finite nonzero loss.

Routes minimize travel time; length is accumulated along those actual routes.
Native routing breaks equal-time ties by shorter length, then stable graph
traversal. Prefix/suffix costs agree with the unchanged envelope distances.
Detour distance is actual fastest-segment plan length minus the corresponding
fastest baseline length; it can legitimately be negative when a slower activity
route is shorter. It is never a sum of independently distance-optimal segments
pretending to be one time-optimal route. Alternate non-fastest road paths are
outside this first oracle; Go-1 conclusions are conditional on this route contract.

The estimate before execution was 68,720,149 max-budget OD/task candidates;
**68,137,723** exact-feasible max-budget plans are saved across 240 partitions.
Smaller budgets are exact total-time filters of these partitions.

### Flat candidates by task and budget

Counts below sum across all 30 ODs; the same plan can recur across budgets and
shared physical objects can serve different fixed tasks. Parking is secondary.

| Task | 1.00 | 1.05 | 1.10 | 1.20 | 1.40 | 1.60 | 2.00 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| charge | 30 | 2,232 | 3,472 | 5,434 | 9,072 | 14,963 | 30,392 |
| charge_meal | 131 | 237,888 | 525,773 | 793,410 | 1,041,009 | 1,588,848 | 3,133,204 |
| charge_parking | 348 | 571,212 | 1,233,683 | 1,841,181 | 2,352,392 | 3,385,658 | 5,901,442 |
| meal | 253 | 18,680 | 30,401 | 50,908 | 83,981 | 138,991 | 258,309 |
| meal_parking | 1,970 | 4,806,175 | 10,859,222 | 17,220,309 | 22,698,446 | 35,924,851 | 57,491,307 |
| parking | 717 | 64,358 | 105,661 | 170,961 | 270,063 | 412,438 | 707,831 |
| sleep | 60 | 3,569 | 6,107 | 10,781 | 20,818 | 35,062 | 71,580 |
| sleep_charge | 32 | 44,338 | 100,849 | 152,105 | 200,202 | 285,252 | 543,658 |


Median practical-range exact-feasibility rate relative to the capability,
spatial/distance and individually eligible candidate upper count:
**99.90%**. Detailed rates by
OD/task/budget are in microplan_feasibility.parquet. Unavailable flat task groups
are not called abstraction failures: primary all-attached/no-dwell practical
range has **0 / 840** absent flat groups.

## Topology gateways and directed semantics

For every frozen decision-aware region, take the union of weak road-distance
balls of radius **2500 m** around all member access nodes, preserving original
directed edges in that view. Weak distance defines neighborhood inclusion only;
reachability and interfaces use directed edges. The radius contains every
<=2500 m member-link path used in 4A, so all such connecting paths are included.
The original graph is shared; sparse local views are transient and no full graph
is copied per region or saved again.

For an outside-to-inside crossing edge `(u,v)`, ingress exists only when
`d_s(u)+t(u,v)+min_member[d_local(v,member)+d_d(member)] <= B+tolerance`.
Egress uses the reverse counterpart with local paths from a member. Multi-source
internal Dijkstra preserves the original member prefix/suffix costs. Thus a
retained crossing supports an actual bounded-cost directed walk through a member,
not just a geographically nearby interface. Deduplication combines only identical
inside boundary-node identities; distinct exits remain. These are bounded-local
interfaces, not certified motorway interchange identifiers or arbitrary anchors.

All alternative feasible interfaces are stored. Canonical member ingress/egress
bindings trace the deterministic fastest origin prefix/destination suffix until
leaving the local view. `-1` means the terminal lies within the view, not a made-up
gateway. Pair plans retain first-member ingress and last-member egress; their
middle route can leave/re-enter the view. Gateway alternatives do **not** restrict
candidate generation in this clean initial test, so gateway omission contributes
no candidate loss. Optimizing ingress/egress alternatives is deferred.

**5,116,326** region-budget gateway records across **251,403**
region-budget views. Practical medians per view: **4**
member access nodes; **1483** local nodes;
**2904** local directed edges;
**16** gateways;
**196** possible ingress/egress pairs.
Unreachable-member total inside all views: **0**.
The interface-pair product is a diagnostic upper count, not proof every pair
supports a feasible microplan. gateway_microplan_usage.parquet records actual
exact plan counts sharing canonical pairs (median **3**).
Routing computations avoided by gateway reuse: **0**, explicitly measured as
unimplemented; no computational saving is claimed from gateway counts.

On unchanged complete member sets between consecutive budgets, median interface
Jaccard is **0.7636** and median identical-interface
fraction **0.5367**. This conditional
stability does not track gateways across changing/split/merged regions. Directed
motorway-exit, one-way ingress/egress, river-separated and multiple-exit toy tests
pass. Persistent matching across changing regions remains future work.

## Typed objectives, access and concurrency

Typed MicroPlan, Gateway, RegionGateways, Task, OpportunityArrays, LocalPairs and
PlanBatch live under src/microplan. Bulk arrays preserve stable opportunity-index
references into opportunity_index.parquet, which retains original type/id,
coordinates, capabilities and frozen attachment identity. On-demand materializing
creates the full typed MicroPlan with visit order, capabilities, costs, gateway
identities, structural access label and feasibility fingerprint. Original tags and
provenance remain in the unchanged frozen inventory. Full paths are stored only
as reconstructed figure diagnostics.

The minimized objective vector is `(detour time s, detour length m, visit count,
dwell s, access penalty)`. Capabilities and mobility budgets are hard feasibility
conditions. Access penalty is an explicit structural ordinal 0/1, not observed
quality. Low risk requires a Point geometry and snap <=50 m; polygons and other
geometries, or longer accepted snaps, are uncertain. **29,040 / 102,415** attached
objects qualify. This conservative rule intentionally favors explicit point
locations; it is not entrance certification or proof other objects are inaccessible.
No legal off-road time/distance or unobserved barriers are invented.

Same-object multiple activities are concurrent-compatible. Distinct objects are
labelled **potential_concurrency** only if both directed minimum road distances
are <=100 m; this is a road/walking proxy, not a verified walk or opening-hour
compatibility. Other pairs are sequential. Fixed scenario durations are charge
1800 s, meal 2700 s, sleep 28800 s, parking 0 s. Structural concurrent dwell takes
the maximum duration; sequential dwell sums them. Constants are experimental
scenarios, not empirical population estimates. The primary experiment excludes
dwell terms; the sensitivity includes them. Mobility budgets never include dwell.

## Candidate reductions and stage loss

Geographic and decision-aware restrictions require both objects to share their
respective frozen 4A region; single stops remain in both. Exact Pareto is computed
**within each region and task**, preserving exact objective ties. The five-dimensional
native skyline agrees with independent Python dominance checks. A plan is removed
only if another is no worse in all dimensions and strictly better in one.

Deterministic epsilon covers also run separately per region. Every removed Pareto
point has a componentwise witness `z(rep) <= z(point)+epsilon` in fixed normalized
units. Representative order is lexicographic objective cost, stop dimensions and
stable opportunity order, never an evaluation theta. Exact zero covers may merge
objective-equal ties; exact Pareto itself preserves them. Random controls retain
the identical count **per region**, sampled from the region candidates with a
stable seeded design. This is a stronger geographic control than a globally
matched random subset.

Configured normalized epsilon vectors and physical allowances:

| Cover | Normalized vector (time, length, visits, dwell, access) | Physical allowance |
| --- | --- | --- |
| exact | [0,0,0,0,0] | exact objective equivalence |
| tight | [.02,.02,0,0,0] | 12 s, 200 m |
| medium | [.10,.10,0,.05,0] | 60 s, 1000 m, 1440 s scenario dwell |
| loose | [.25,.25,.50,.10,0] | 150 s, 2500 m, one visit, 2880 s scenario dwell |

All retained plans still satisfy their exact task and mobility budget; these
allowances never relax hard feasibility or invent activity evidence.

Median final reductions below are computed per OD/task/budget and then summarized,
not inferred from the ratio of count medians. Flat column is median candidate count;
other columns are reductions from the flat set. Zero-candidate cases retain null
fractions. 4A opportunity→region reduction remains the unchanged representation
result and is not confused with microplan reduction.

| Ratio | flat | geographic | decision | exact_pareto | epsilon_exact | epsilon_tight | epsilon_medium | epsilon_loose |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.05 | 698 | 0.0% | 34.7% | 91.2% | 94.3% | 94.8% | 94.9% | 95.2% |
| 1.10 | 2,084 | 0.0% | 56.3% | 97.2% | 98.2% | 98.3% | 98.4% | 98.4% |
| 1.20 | 5,066 | 0.0% | 61.8% | 97.4% | 98.3% | 98.6% | 98.7% | 98.8% |
| 1.40 | 6,600 | 0.0% | 62.4% | 97.0% | 98.1% | 98.4% | 98.5% | 98.6% |


Stage reductions: practical median flat→region
**50.6%**;
region→exact Pareto
**89.1%**;
Pareto→medium cover **47.5%**.
These conditional stage medians are not multiplicatively combined.

Paired scalar stage losses against the same flat reference:

| Loss | Median finite | p95 finite | Worst finite |
| --- | --- | --- | --- |
| region_loss | 0 | 0.049882 | 0.94046 |
| pareto_loss | 0 | 0 | 5.5511e-17 |
| tight_cover_loss | 0 | 5.5511e-17 | 0.0072363 |
| medium_cover_loss | 0 | 3.4417e-15 | 0.036791 |
| loose_cover_loss | 0 | 0.0006509 | 0.14011 |


The exact stage decomposition is computed directly for each scalar observation:
region loss = region best − flat best; cover loss = cover best − Pareto best;
total is their sum (exact Pareto loss is zero). Empty candidate sets preserve
infinite regret; differences of two empty-set costs are undefined and stay null.

## Evaluation family and regret distributions

Sixteen fixed positive linear vectors: four named archetypes (time-sensitive,
balanced, distance-sensitive, stop-minimizing) plus twelve seeded Dirichlet(1)
simplex draws. They exist only for evaluation; no learned or persistent profiles,
region tuning, cover tuning or quality assumptions enter construction.
All vectors are recorded. Fixed unit scales are `[600 s, 10000 m, 2 visits,
28800 s, 1 access ordinal]`, shared by every method/candidate set. No candidate
min/max normalization occurs. Without dwell, its coordinate is zero and other
weights are not method-specifically renormalized.

Absolute regret is selected normalized linear cost minus flat best cost.
Normalized regret divides by `abs(flat best)+0.01`; the 0.01 stabilizer is explicit.
Absolute loss is primary because near-zero flat costs can inflate relative loss.
For intuition only, a 0.01 loss would equal 6/θ_time seconds if entirely due to
time; it is not a universal number of minutes because tradeoff vectors differ.

| Method | Valid θ cases | Median finite | p90 finite | p95 finite | Worst finite | Infinite cases |
| --- | --- | --- | --- | --- | --- | --- |
| decision | 13440 | 0 | 0.018655 | 0.049882 | 0.94046 | 0 |
| epsilon_exact | 13440 | 0 | 0.018655 | 0.049882 | 0.94046 | 0 |
| epsilon_loose | 13440 | 0 | 0.02226 | 0.05 | 0.94046 | 0 |
| epsilon_medium | 13440 | 0 | 0.020953 | 0.049882 | 0.94046 | 0 |
| epsilon_tight | 13440 | 0 | 0.018655 | 0.049882 | 0.94046 | 0 |
| exact_pareto | 13440 | 0 | 0.018655 | 0.049882 | 0.94046 | 0 |
| flat | 13440 | 0 | 0 | 0 | 0 | 0 |
| geographic | 13440 | 0 | 0 | 0 | 0.2616 | 0 |
| random_exact | 13440 | 0.014467 | 0.098516 | 0.13388 | 0.99249 | 0 |
| random_loose | 13440 | 0.015743 | 0.10538 | 0.14409 | 0.99046 | 0 |
| random_medium | 13440 | 0.01642 | 0.108 | 0.14604 | 1.0064 | 0 |
| random_tight | 13440 | 0.016664 | 0.10496 | 0.14211 | 0.95046 | 0 |


Finite distribution columns explicitly condition on available method plans.
Infinite losses remain in coverage and worst-case records, and absent flat tasks
are separately counted. Across all seven budgets and all access/dwell scenarios,
there are **454** absent-flat groups and **20**
nonempty-flat / empty-decision groups; the latter have infinite loss and remain
explicit in the complete tables. No claims are based solely on the median or one tolerance.
The complete raw table includes every OD, budget, task, access/dwell scenario,
method and theta. The central figures are compression_vs_regret and
retained_vs_topk_coverage, with source CSVs and task-stratified diagnostics.

### Task differences and parking support

| Task | Median final reduction | Median finite regret | p95 finite | Worst finite | Infinite θ cases | Absent oracle θ cases |
| --- | --- | --- | --- | --- | --- | --- |
| charge | 48.6% | 0 | 0 | 2.7756e-17 | 0 | 0 |
| meal | 74.4% | 0 | 1.0547e-15 | 0.02193 | 0 | 0 |
| sleep | 50.3% | 0 | 0 | 0.0054959 | 0 | 0 |
| charge_meal | 99.6% | 0.001296 | 0.041267 | 0.2719 | 0 | 0 |
| charge_parking | 99.8% | 0.0057773 | 0.11415 | 0.94046 | 0 | 0 |
| sleep_charge | 98.7% | 0.0058537 | 0.080115 | 0.53479 | 0 | 0 |
| meal_parking | 99.9% | 0 | 0.057509 | 0.34208 | 0 | 0 |
| parking | secondary | 0 | 0 | 0.023758 | 0 | 0 |


This table prevents parking-only counts from concealing sparse charging/sleep
bundle failures. Parking-only remains separately measured at all budgets.
Supporting parking pairs can dominate stored candidate volume (meal+parking),
but primary summaries weight each of seven task scenarios equally. Taxonomy
objects are not certified distinct businesses, and one physical facility can
have multiple OSM identities.

### Top-K and decision tolerances

| Method | K | τ=0 | τ=0.01 | τ=0.05 | τ=0.1 |
| --- | --- | --- | --- | --- | --- |
| geographic | 1 | 98.93% | 99.12% | 99.47% | 99.83% |
| geographic | 3 | 98.93% | 99.12% | 99.47% | 99.83% |
| geographic | 5 | 98.93% | 99.12% | 99.47% | 99.83% |
| decision | 1 | 69.57% | 84.43% | 95.33% | 98.04% |
| decision | 3 | 69.57% | 84.43% | 95.33% | 98.04% |
| decision | 5 | 69.57% | 84.43% | 95.33% | 98.04% |
| exact_pareto | 1 | 69.57% | 84.43% | 95.33% | 98.04% |
| exact_pareto | 3 | 69.57% | 84.43% | 95.33% | 98.04% |
| exact_pareto | 5 | 69.57% | 84.43% | 95.33% | 98.04% |
| epsilon_tight | 1 | 69.30% | 84.41% | 95.33% | 98.04% |
| epsilon_tight | 3 | 69.30% | 84.41% | 95.33% | 98.04% |
| epsilon_tight | 5 | 69.30% | 84.41% | 95.33% | 98.04% |
| epsilon_medium | 1 | 68.86% | 83.59% | 95.31% | 98.00% |
| epsilon_medium | 3 | 68.86% | 83.59% | 95.31% | 98.00% |
| epsilon_medium | 5 | 68.86% | 83.59% | 95.31% | 98.00% |
| epsilon_loose | 1 | 68.38% | 83.10% | 95.01% | 97.98% |
| epsilon_loose | 3 | 68.38% | 83.10% | 95.01% | 97.98% |
| epsilon_loose | 5 | 68.38% | 83.10% | 95.01% | 97.98% |
| random_medium | 1 | 30.80% | 43.36% | 73.22% | 88.65% |
| random_medium | 3 | 30.80% | 43.36% | 73.22% | 88.65% |
| random_medium | 5 | 30.80% | 43.36% | 73.22% | 88.65% |


Best-in-TopK regret is mathematically the same for K=1,3,5 here: candidates are
ranked with the same known theta used to evaluate the set, so Top1 is included in
every nonempty TopK. Returned set size is `min(K, available count)`. Identity can
change while regret remains zero, but this protocol cannot demonstrate a new
TopK quality gain. Diversity/robust set selection across unknown objectives would
require another experiment, not fabricated improvement in these curves.

For a positive linear evaluation and a valid componentwise epsilon cover, the
**additional loss above the region optimum**, not total flat regret, is bounded
by `theta dot epsilon`. Every Pareto witness is checked and all sixteen scalar
bounds are checked for every evaluated group. Maximum recorded bound excess is
**1.11e-16**, within 1e-10 numerical tolerance.
This conditional bound neither controls region-induced loss nor arbitrary
nonlinear/human utility. Independent toy tests verify the same statement.

## Access and dwell sensitivity

| Access | Dwell | Median final reduction | Median finite regret | p95 finite | Infinite θ cases | Absent flat groups |
| --- | --- | --- | --- | --- | --- | --- |
| all_attached | structural_concurrency | 98.1% | 0 | 0.048201 | 0 | 0 |
| all_attached | without_dwell | 98.2% | 0 | 0.049882 | 0 | 0 |
| conservative | structural_concurrency | 95.7% | 0 | 0.058073 | 32 | 1 |
| conservative | without_dwell | 95.7% | 0 | 0.059759 | 32 | 1 |


Conservative access may make tasks unavailable even when all-attached has plans;
these are recorded as absent flat oracles, not lower abstraction regret. Polygon
exclusion changes the activity mix substantially, especially parking. Scenario
dwell changes tradeoffs without claiming observed queue, reliability or comfort.
The frozen 4A inventory/attachments remain untouched.

## Expansion instability and mandatory failures

| instance_id | ratio | ARI | median_regret | p95_regret | identity_changed | old_oracle_newly_excluded | old_selection_newly_excluded |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 7 | 1.05 | 0.97777 | 0.0 | 0.08267 | 0.82143 | 0.0 | 0.0 |
| 7 | 1.1 | 0.62915 | 0.0 | 0.04507 | 0.39286 | 0.0 | 0.11607 |
| 14 | 1.05 | 0.4331 | 0.0 | 0.00987 | 0.83036 | 0.0 | 0.0 |
| 14 | 1.1 | 0.75379 | 0.0 | 0.00987 | 0.0 | 0.0 | 0.0 |
| 16 | 1.05 | 0.44444 | 0.0 | 0.06258 | 1.0 | 0.0 | 0.0 |
| 16 | 1.1 | 0.94927 | 0.0 | 0.06258 | 0.0 | 0.0 | 0.0 |
| 29 | 1.05 | 0.59734 | 0.0 | 0.01607 | 0.86607 | 0.3125 | 0.3125 |
| 29 | 1.1 | 0.62297 | 0.0 | 0.0196 | 0.16964 | 0.05357 | 0.16964 |


ODs 14,16,29,7 are explicitly retained. decision_expansion.parquet joins every
consecutive-budget decision with 4A common-member ARI and compares flat-optimum
and selected-plan identities. It also tests whether an old oracle or old selected
bundle is newly excluded by the expanded-budget partition even though its mobility
feasibility is preserved. `both_flat_oracles_available` distinguishes absent prior
tasks from real decision comparisons. Identity change alone is not loss; region growth
can leave decisions optimal even when region IDs split/merge. These associations
do not establish causal effects independently of newly eligible opportunities.
All other worst ODs remain available in the raw table.

Every positive geographic/decision region-loss observation is recorded in
failure_analysis.parquet, **24,413** records. A removed flat compound
bundle crossing the frozen partition is structurally verified and labelled
`cross-region bundle required`; unverified causes stay `other`. Region
fragmentation/range constraints can explain such crossings, but finer causal
attribution is not inferred without a counterfactual rebuild. Gateway omission
is excluded because gateways never prune. Access attachment error, legal access,
budget-boundary alternatives outside the crop, and missing taxonomy evidence
cannot be certified from these data and remain unresolved rather than invented.
The local-cutoff rules define both spaces equally and hence introduce no measured
region-relative loss; this does not test larger bundles beyond those rules.

Worst medium-cover observations in the primary practical range:

| instance_id | ratio | task | theta_id | absolute_regret | normalized_regret | oracle_first_index | oracle_second_index | selected_first_index | selected_second_index |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 21 | 1.1 | charge_parking | distance_sensitive | 0.940458 | 1.083362 | 24477 | 29705 | 13794 | 34857 |
| 13 | 1.05 | charge_parking | distance_sensitive | 0.675863 | 1.261261 | 81024 | 26766 | 46312 | 33707 |
| 21 | 1.1 | charge_parking | simplex_06 | 0.56156 | 1.466844 | 24477 | 29705 | 31319 | 73912 |
| 22 | 1.2 | charge_parking | distance_sensitive | 0.555335 | 0.639719 | 24477 | 29704 | 16061 | 52952 |
| 22 | 1.4 | charge_parking | distance_sensitive | 0.555335 | 0.639719 | 24477 | 29704 | 16061 | 52952 |
| 22 | 1.1 | charge_parking | distance_sensitive | 0.555335 | 0.639719 | 24477 | 29704 | 16061 | 52952 |
| 21 | 1.1 | charge_parking | simplex_07 | 0.553115 | 0.992206 | 24477 | 29705 | 13794 | 34857 |
| 13 | 1.4 | sleep_charge | distance_sensitive | 0.534792 | 1.354617 | 16070 | 886 | 9770 | 33707 |


Opportunity indices in these examples resolve to exact OSM type/id in the saved
catalogue. Figures show a zero-loss high-compression case, a worst medium-cover
case and an early-expansion case, with recorded flat/cover choices and interfaces.
Full failures, absent tasks and risky 2.00 cases remain in machine-readable tables.

## Computational cost and reproducibility

| Stage | Measurements | Median s | p95 s |
| --- | --- | --- | --- |
| envelope_precomputation | 30 | 6.9428 | 7.1794 |
| epsilon_cover_and_random | 6720 | 0.015553 | 0.26681 |
| exact_fastest_path_lengths | 30 | 2.2043 | 2.2848 |
| flat_generation_and_exact_feasibility | 240 | 0.0041638 | 0.40665 |
| gateway_extraction | 210 | 0.44507 | 3.996 |
| graph_load | 1 | 10.036 | 10.036 |
| native_index_build | 1 | 1.8848 | 1.8848 |
| od_total | 30 | 36.386 | 78.225 |
| opportunity_parse | 1 | 0.49174 | 0.49174 |
| pareto_pruning | 6720 | 0.00023777 | 0.028097 |
| region_restriction_index | 210 | 0.018266 | 0.056067 |
| scalar_regret_evaluation | 6720 | 0.0030879 | 0.0042075 |
| exact_budget_feasibility_filter | 1680 | 0.00021239 | 0.0038561 |
| region_candidate_filter | 1680 | 4.1451e-05 | 0.0033606 |
| local_subgraph_build | 210 | 0.14524 | 1.3583 |
| directed_gateway_interfaces | 210 | 0.23451 | 1.9858 |


Sparse exact time/length preparation: **125.15 s**,
**4,967,648** ordered queries from
**69,153** distinct source
access nodes. Minimum-distance neighbor evidence is reused from verified 4A data.
No global all-pairs POI matrix is computed. Prefix/suffix distances and lengths
are computed once per OD and reused at every budget; gateway views are bounded.
ODs remain sequential. Separate native local-build/interface times are also saved
per region and aggregated in gateway_stage_performance.parquet. Stored-plan
budget and region filters receive separate measurements; flat assembly timing
includes its vectorized exact-feasibility check and is labelled accordingly.

Sequential scientific experiment, excluding initial graph loading/local-cost
preparation and later verification/figures: **1270.56 s**.
Peak process high-water RSS: **7342.3 MiB**
(**7.17 GiB**). Workstation timings use warm caches;
RSS is not whole-server simultaneous memory or an interactive latency promise.
Large meal+parking arrays, per-region views and repeated output serialization
are the dominant practical costs; no full path storage or repeated graph copies.

Exact costs, normalized vectors, deterministic ordering, compiler/source hashes,
Git state, frozen dataset/graph/region fingerprints and full configuration are
recorded. Cold local routing and independent real route checks are documented in
routing_reproducibility.json. Independent reconstruction from stored partitions
checks counts and every theta in 45 representative contexts (including early and
large ODs) in subset_reproducibility.json. These are stated verification scopes,
not a claim that every scenario was independently rerun end-to-end.

Outputs: opportunity_index, local_costs, candidate_estimates, all flat-plan
partitions, candidate_counts, gateways, region_gateway_stats, gateway_bindings,
gateway_microplan_usage/stability, pareto_stats, epsilon_cover_stats, all fixed
utility weights, abstraction_regret, TopK/coverage, paired stage_regret,
failure_analysis, task summaries, decision_expansion, exact-feasibility tables,
performance, benchmark/provenance, preservation/tests, figures and source data.
Region/Pareto/cover plan sets are a reproducible **sufficient representation**:
filter saved flat plans with frozen membership and the documented deterministic
kernels. `rebuild_microplan_subset.py` reconstructs any subset without routing.
This avoids duplicating full microplan tables at every budget/scenario; sample
independent subset verification is explicit. No road graph is duplicated.
README gives exact commands and verifies previous data rather than rebuilding it.

## Go-1 interpretation and next-stage boundary

The measured curve, task strata, tails and failure cases are the decision evidence.
Medium-cover primary median finite loss **0**, p95
**0.049882**, worst finite **0.94046**, with
**0** unavailable-method theta cases; matched random
p95 **0.14604**. Exact Pareto is lossless under the tested positive
linear family; epsilon loss is conditionally bounded, while region restriction
has no such universal guarantee. The curve must be read per task: strong
compression of dense meal/parking bundles cannot establish equal success for
sparse charging/sleep tasks. Geographic regions may preserve a cross-region
bundle that the more coherent 4A decision partition excludes.

This is conditional structural evidence for candidate compression on fixed
single/local-pair tasks, not complete Go-1 validation over arbitrary route plans,
activity schedules or human preferences. There is a clear **compression knee after region restriction**: exact per-region
Pareto reaches 96.6% median total reduction without adding scalar loss, and an
exact/tight cover reaches roughly 97.9–98.1% by removing ties/small differences.
Medium/loose covers reach roughly 98.2–98.3% with little aggregate p95 change.
This knee does **not** erase the region-induced loss already present at 50.6%
median region reduction. Medium is an illustrative curve point, not a regret-tuned
winner. Single charge/sleep tasks compress only around 49–50%, while dense compound
tasks exceed 99%; there is no uniform 90% compression claim.

**Go-1 verdict: qualified empirical support, not a uniform success.** At tolerance
0.05, medium-cover coverage is 95.31% overall, but charge+parking and sleep+charge
reach only 86.98% and 89.22%. Geographic restriction has 99.47% coverage at that
same tolerance with essentially zero median candidate reduction; matched random
achieves 73.22% with identical per-region retained counts. Worst charge+parking
loss is 0.94046 (OD 21, ratio 1.10, distance-sensitive vector). Region membership,
not epsilon, causes that failure. These observations support deterministic
compression within regions, but expose a weak boundary for cross-region bundles.
I would address these structural failures **before** adding partial-information
or active-acquisition layers. The current evidence is insufficient to claim that
the default decision partition uniformly preserves near-optimal activity decisions.
 Before partial-information/active
acquisition: address systematic cross-region compound tasks, certify or model
access, define gateway reuse without omitting alternatives, improve persistent
region/gateway matching, and design meaningful robust/diverse TopK sets. Sparse
task coverage, static legal-model omissions, object/facility deduplication and the
nine risky maximum-budget ODs remain limitations. No uncertainty simulator or
acquisition work proceeds in this milestone.
