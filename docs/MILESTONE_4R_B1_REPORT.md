# Milestone 4R-B1 — Exact one-stop hierarchical validation

Date: 2026-10-02 (Asia/Shanghai). **H0–H5 pass. B1-O strong GO. B1-D unresolved.**

## A. Scope and declared domain

Exhaustive selection of zero or one concrete vehicle stop under accepted directed
fastest-time legs and their selected-path actual lengths, within each fixed Safe
Detour Envelope. Primary configuration is unchanged: 60 kWh, 0.16 kWh/km, 6 kWh
reserve, zero robust margin, canonical 100/60/30 kW curve, 500 m support radius,
meal_count >= 1, hard compatible 2700 s activity at 0.40–0.70 baseline time,
300 s overhead, 600 s stop nuisance, no distance penalty. No arbitrary road-path
optimization, neutral role, new geographic data, dependency install or B2 work.

## Action-domain amendment and H0 migration audit

The first attempt stopped because C/S/CS capability roles did not cover the
broader accepted via-Site domain. That evidence remains unchanged in
`docs/MILESTONE_4R_B1_BLOCKER_REPORT.md`, `blocker_acceptance.json`,
`role_coverage_counterexample.json` and `reproduce_role_audit.py`.

The user approved the separate `MILESTONE_4R_B1_ACTION_DOMAIN_AMENDMENT.md`.
D_4RA retains all accepted feasible via-Site plans. D_B1 contains feasible
zero-stop separately and only Site actions with a nonempty **performed** effect:
C iff charged energy > 1e-8 kWh; S iff the active scheduled activity is actually
satisfied. Each Site plan receives one of C/S/CS, never a static capability label.
No neutral role was added. Road-path choice is not silently recast as a stop task.

H0: **480 expected, 480 evaluated, 0 cost mismatches,
0 identity-only changes**. Excluded feasible
effect-free legacy actions: **442,368**.
No optimal value or selected action changed. Recomputed legacy optima match the
accepted 4R-A table in both cost and identity for every case.

`flat_actions` observes the original `assemble_plan` calls during unchanged
`best_one_stop`, returns original objects, retains the first minimum by accepted
plan_key per Site, and records zero-stop separately. It changes no evaluator
source, feasibility, objective, optimizer, ties or routing. All eligible Site IDs,
feasible/infeasible status, times, actual lengths, energies, charging, schedule,
completion and costs are saved in `flat_reference/case_*.parquet`; case JSON
contains trip, baseline, zero-stop feasibility, both optimum plans and metadata.
Full H0 tables and excluded actions are under `h0_*`.

## B. Baseline preservation and tests

Baseline commit `20b658257fb67655e09229411783935e17084fa4`; branch
`codex/milestone-4r-b1`. No user work committed. The resume pre-existing suite
passed **116 tests**. Final suite: **153 passed**, zero failures,
errors or skips. The 840-file historical manifest, 56 older accepted source
hashes, all 4R-A sources/inputs/results covered by the **933-file**
checkpoint, and archived blocker hashes are unchanged. New manifests record
source hashes and input/output linkage. Old reports/results were not regenerated.

Synthetic tests cover effect/tie boundaries, coverage, exact and positive-epsilon
pruning, improved-incumbent persistence, failed margins causing refinement,
unreachable directed pairs, piecewise charging breakpoints, exact arrival/capacity/
deadline certificate margins, and disconnected/co-attached topology cells.
Initial new equality fixtures exposed decimal endpoint roundoff; fixtures were
changed to exactly representable synthetic endpoints before the comparative run.
No empirical theorem failure or post-result hierarchy tuning occurred.

## C. Frozen static hierarchy

Binary deterministic recursive BFS bisection of the road graph's weak undirected
topology, weighted only by accepted access-node Site counts. Seeds/neighbors use
stable OSM node order; earliest BFS prefix minimizing Site-count imbalance wins;
co-attached Sites never split. Directed routing semantics remain unchanged.
This is the allowed fallback after dependency feasibility inspection; the reason
for rejecting large Python KL sweeps and non-balanced community algorithms is
recorded in `hierarchy_build/partition_choice.json`. No partition alternatives
were selected by pruning outcomes.

All **60,498 attached Sites** remain in the static tree, including Sites whose
actions are excluded in particular queries. There are **2,047 Regions**, **1,024
leaves**, depth 0–10, leaf capacity 64, observed leaf sizes **54–65**.
One early leaf contains 65 co-attached Sites at the same road anchor; it is
explicitly recorded as unsplittable without splitting one road node. This is the
predeclared early-leaf exception, not dropped Sites or a retuned capacity.
Coverage, child disjointness and leaf uniqueness pass. Two construction runs
produce byte-identical road-cell and Region files. Primary hash:
`4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805`.
The immutable preregistration was written after H0 and before comparisons.
Optional capacity 32/128 sensitivities were not run; the primary tree was not rebuilt.

## D. Correctness H0–H5

| Gate | Primary evidence | Violations |
| --- | --- | ---: |
| H0 | 480 legacy-to-semantic comparisons | 0 |
| H1 | 19,398 oracle Region View bounds vs concrete costs | 0 |
| H2 | 480 epsilon=0 optima, full accepted tie keys and identities | 0 |
| H3 | 15,915 certified Views, all concrete gap checks | 0 |
| H4 | Static exact partitions and all internal role-count partitions per case | 0 |
| H5 | Same hierarchy hash across all 1,920 primary/sensitivity searches | 0 |

Energy, charge and schedule perturbations: zero violations. Independent real
directed-time checks: **213 Views**, 45
anchors, zero violations. The initial first-leaf diagnostic had no represented
development actions; it is retained, and a supplementary diagnostic used the
first leaf with two C actions in H0 case 0. This changed no hierarchy or experiment
cases. Uncomputed/unreachable diameter certificates are not treated as finite.
No distance-metric theorem is assumed for selected-fastest-route actual lengths.

Numerical contract: effects/energy tolerance 1e-8 kWh, scheduled feasibility
1e-8 s, accepted cost key round(cost,7), safe bound L_num - 1e-6 s, theorem audit
2e-6 s / 1e-8 kWh. Margin tests add no slack: borderline negative slack is
inconclusive. Equality ties survive the outward lower-bound adjustment. Leaf
actions use the original accepted evaluator and tie rule.

## E. B1-O oracle potential

These are **logical Site-evaluation reduction potential** measurements. H0 already
paid to determine feasibility, performed roles, times, lengths and concrete costs
for every Site. Reading those results to filter and summarize Regions is also
oracle work. None is counted as actual saved online computation or routing.

Total semantic Site actions across primary cases: **286,567**;
logical leaf evaluations: **48,069**.
Legacy eligible counts and excluded effect-free counts are recorded separately.
Best-bound-first traces retain bounds, pops, refinements, leaves, concrete work
and U - min(OPEN). A separate certified-gap column includes the saved pruned-node
lower floor, avoiding a false zero certificate after positive-epsilon termination.

| Role | Nonempty cases | Empty cases | Conditional median reduction |
| --- | ---: | ---: | ---: |
| C | 147 | 333 | 93.33% |
| CS | 146 | 334 | 95.92% |
| S | 132 | 348 | 81.21% |

This table conditions on nonempty role branches. Empty branches are never counted
as 100% pruning. Envelope, SOC, scenario, OD and role tables are in
`stratified_work.csv`; case-level data are in `logical_work.csv` and `role_work.csv`.

## F. Preregistered classification

The approved B1-D clarification closes this contract: 480 total cases,
387 metric-defined cases, 93 zero-semantic cases recorded as NA and
`no_semantic_site_pruning_opportunity`. All 480 remain in correctness/runtime
reporting. On the 387 defined cases, median reduction is 91.860465%,
P(r>=50%) is 98.966408%, and P(r>=25%) is 100.000000%. The all-case micro
workload reduction is 83.225912%.
The unchanged thresholds give **B1-O strong GO**. No hierarchy was rerun
or retuned. Closure tables are in `results/milestone_4r_b1d/b1_oracle_classification.*`.
The earlier unresolved state is preserved in the B1-D preservation archive.

Strong GO remains median >=70% and P(r>=50%)>=75%; NO-GO remains median <50%
or P(r>=25%)<75%; otherwise gray zone. No difficult case was removed from H0–H5.

## G. Gap diagnosis and epsilon sensitivity

G_model=0 in this exact feasible one-stop diagnostic: the per-Site model b*(s)
is the accepted concrete objective itself, with no residual continuation
relaxation. G_agg is the concrete Region minimum minus component-minimum relaxed
cost. G_cert is unavailable because no deployable bound was implemented.
Across visited primary Views, median G_agg=216.289 s,
p95=2439.627 s. These are View-weighted diagnostics,
not independent case-level observations. Coarse component minima can come from
different Sites; refinement reduces this source of aggregation looseness.

| Role | Views | Median G_agg (s) | p95 G_agg (s) | Certified fraction |
| --- | ---: | ---: | ---: | ---: |
| C | 8104 | 290.684 | 4123.753 | 100.00% |
| CS | 3850 | 145.066 | 1522.403 | 83.38% |
| S | 7444 | 215.225 | 1795.061 | 61.81% |

`gap_decomposition.csv` and `role_depth_gaps.csv` retain depth, role, OD,
envelope, SOC and scenario diagnostics. No redesign was attempted.

| Epsilon (s) | Cases | Nonempty cases | Conditional median reduction | Maximum observed cost gap (s) |
| --- | ---: | ---: | ---: | ---: |
| 0 | 480 | 387 | 91.86% | 0.000000 |
| 30 | 480 | 387 | 92.86% | 29.782342 |
| 60 | 480 | 387 | 93.19% | 54.503268 |
| 120 | 480 | 387 | 94.29% | 105.524490 |

All positive-epsilon searches ran only after exact primary correctness passed.
They are secondary work-versus-certified-gap diagnostics, not substitutes for
exact preservation. Full gap trajectories are `oracle_epsilon_*/trace_*.parquet`.

## H. B1-D deployable stage

**B1-D unresolved: no proven non-enumerative deployable certificate implemented.**
Exact performed-effect classification and oracle length oscillations currently
use prepaid per-Site query results. No cheap route-length bound or role filter
was invented, and no full scan was presented as saved work. Computational
break-even remains unresolved.

## I. Runtime and memory

H0 wall time: 157.84 s, peak 4277.1 MiB;
includes shared routing and exhaustive diagnostic work. Per-OD shared routing is
separate in `h0_runtime.csv`. Hierarchy construction plus reproducibility rerun:
12.53 s, recorded Python-process peak
1149.2 MiB (native child RSS is not included in this figure).
Oracle runs total 845.56 s, peak
849.3 MiB. These are validation costs, not speedups.
Per-case oracle timings include summaries, audits and concrete leaf evaluations;
the H0 flat timing includes observation/serialization and is not an isolated
replaced-work denominator. Shared routing is reused from verified H0 artifacts
and credited with zero hierarchy savings. Native preprocessing RSS attribution
is limited to the process logs; no deployable timing gate is claimed.

## J. Limitations

30 development ODs, one-stop declared domain, fixed-envelope optimality only;
no real multi-stop result, final holdout, active information acquisition, user
learning or business ranking. Support remains the accepted geographic proxy;
chargers use the deterministic canonical curve. Feasible performed roles are
oracle query results. Zero-semantic cases have NA reduction; macro statistics condition on nonempty cases, while all cases remain in correctness and micro-workload reporting.

## K. Final gate statement

**B1-O strong GO. B1-D unresolved.**
All H0–H5 correctness gates pass. B2, Go-2 and holdout work were not started.

Reproduction entry points (fresh B1 outputs; scripts refuse to overwrite freezes):
`run_hierarchy_4r_h0.py`, `build_hierarchy_4r.py`,
`run_hierarchy_4r_oracle.py`, `check_hierarchy_4r_diameter.py --populated`,
`analyze_hierarchy_4r.py`, `finalize_hierarchy_4r.py` under `scripts/`, using
`/home/dy/miniconda3/envs/hiroute/bin/python`. The supplied amendment must be read
alongside the original B0/B1 documents. Archived blocker evidence is permanent.
