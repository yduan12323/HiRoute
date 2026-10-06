# Milestone 4R-B1E — Deployable Baseline & Certificate Decomposition

Date: 2026-10-02 (Asia/Shanghai). **Post-hoc diagnosis only. E1–E6 have zero violations.**

## A. Scope

B1-E diagnoses frozen B1-D v1 on all 480 development cases. It introduces no
algorithm improvement, weighted work score or new confirmatory success threshold.
The existing hierarchy, eight landmarks, static buckets, epsilon=0 search,
incumbent policy, exact evaluator and numerical tolerances remain unchanged.
Perfect-static calculations are offline counterfactuals and are not deployable.

## B. Frozen evidence

The pre-existing full suite passed **187 tests** before diagnostic computation.
The final full suite passed **207 tests**, with no failures, errors or skips.
Before/after manifests verified **8,404 frozen files**, including
all B1-D primary outputs, code hashes, landmark arrays, Region summaries, accepted
baseline/protection manifests and archived blocker evidence. There were zero
unauthorized changes and no accepted tracked-source/output diff.
The Git commit remains `20b658257fb67655e09229411783935e17084fa4`; exact statuses are archived in the manifests.

Hierarchy hash: `4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805`.
Landmark-manifest hash: `4627d789aaae53ddf5e084bf8ccdcff0b44ec0ca181c5e8c3b99a6c7b5975af1`.
The unchanged tree has 60,498 Sites, 2,047 Regions and 1,024 leaves. The original
eight landmarks and Ccap/S0cap/SCcap membership are preserved. B1-D uses ALT
outward adjustment `1e-6 + 2e-8*(abs(a)+abs(b))`, a further 1e-5 s cost adjustment,
and nextafter toward minus infinity; B1-E imports these functions read-only.

New evidence is under `results/milestone_4r_b1e/`. No historical report, result,
search/config file, accepted evaluator, graph or hierarchy was overwritten.
Native routing compilation uses a separate B1-E cache. No dependency was installed.
The accepted memory guards passed; observed diagnostic peak RSS was
4.479 GiB.

## C. Historical outcomes retained

**B1-O strong GO.** The approved positive-denominator population has 387 cases;
93 zero-semantic cases remain NA. Its median logical reduction remains
91.86%, with micro reduction
83.23%.

**B1-D v1 deployable gate failed.** B1-D v1 was exact and deployable in the sense
of no online Region scans. Its preregistered semantic-denominator workload gate
failed (median -183.95%, micro -146.41%), while correctness and the clean timing
gate passed. **That historical failure is not retroactively reversed.**
The separate [B1 report](MILESTONE_4R_B1_REPORT.md) and
[B1-D report](MILESTONE_4R_B1D_REPORT.md) are unchanged.

## D. Fair deployable baseline

The reconstructed flat method uses the same pre-evaluation information as B1-D:
all 2,749 root Ccap Sites for energy_only; all 45,129 S0cap plus 2,480 SCcap Sites
for energy_and_scheduled. It knows no performed roles or exact Site costs before
evaluation. Shared fastest-route time/actual-length arrays have the same accepted
semantics as the hierarchy.

Both methods call the **identical frozen `exact_leaf` function object**: exact
envelope check; unchanged accepted evaluator for envelope-pass candidates;
performed-effect classification; semantic filtering; accepted plan-key tie rule.
The flat method seeds zero-stop separately and compares it with the exact semantic
Site result. A file-access guard prohibits oracle per-Site reads during the flat
call. All 480 reconstructed flat optima/tie keys and envelope/exact/semantic counts
match the frozen paired flat control. Oracle evidence is read only afterward for
offline diagnostic audits. No semantic filtering is used to construct flat candidates.

## E. Workload-vector comparison

All-case totals retain distinct operations:

| component | flat | hierarchy |
|---|---|---|
| N_region | 0 | 147765 |
| N_bound | 0 | 191849 |
| N_envelope | 12085920 | 706117 |
| N_exact | 1103938 | 249642 |
| N_semantic | 286567 | 173577 |

N_region means popped Region/bucket nodes; N_bound counts created nonempty bound
nodes, including those rejected at creation. No weighted equivalent-Site score
is used. All paid envelope checks count, even cheap rejects. The semantic
denominator is retained for historical B1-D reporting, not substituted for the
deployable flat workload in this descriptive comparison.

Envelope-check reduction: median **96.28%**, all-case
micro **94.16%**. Exact-evaluator-call reduction: median
**81.23%**, all-case micro
**77.39%**. Metric-defined case counts are respectively
480 and 480.
These are effect sizes, not a new pass/fail gate.

Each method's CSV/Parquet includes the full requested W vector. T_envelope and
T_exact are **NA** because frozen measurements did not separate those components.
Historical paired T_search and T_e2e are retained with provenance; bound, lookup,
refinement and combined leaf times are separately available for the hierarchy.
No new deployable timing was inferred from diagnostic runtime. Historical search
time reduction has case median 28.63% and
aggregate ratio reduction 48.07%; historical
end-to-end ratio reduction is 2.89%, reflecting shared
routing dominance. **Timing diagnosis is limited**: envelope/exact splits and
time-to-incumbent are unavailable, and original cache/timing limitations remain.
No H0 serialization runtime or perfect-static runtime is used as a deployable comparator.

## F. Perfect-static construction

For each of 30 ODs, independent full-node SSSPs produce d_T from origin/to
destination and d_D from origin/to destination on the accepted directed edges.
For every static Region/bucket, exhaustive offline scans produce the four exact
minima, finite counts and unreachable counts. d_D remains shortest-distance
length, not the actual length of the selected fastest-time route.

The saved audit population covers **all 191,849 frozen ALT8 visited
nodes** across all cases. Every recomputed minimum matches its frozen B1-D audit
value within 1e-5 metric units. The minima Parquet pairs exact and ALT8 values,
bucket sizes and reachability counts.

Perfect-static bounds call the same B1-D `cost_bound`: same Pmax=100 kW,
charging relaxation, overhead, nuisance, envelope, energy and schedule tests,
and numerical safety. Each node independently normalizes against its own
perfect-static parent. `L_PS_raw` and `L_ALT_raw` are safety-adjusted values before
parent normalization. Component minima can come from different Sites; this
relaxation remains intentionally unchanged.

The counterfactual index is passed to the **unchanged frozen `deploy_search`**,
retaining root buckets, heap tie order, zero-stop policy, exact leaves and epsilon=0.
The index's exhaustive metric inputs make it nondeployable. Its runtime is
excluded from all deployable-performance claims.

## G. E1–E6

| gate | status | violations |
|---|---|---|
| E1 | passed | 0 |
| E2 | passed | 0 |
| E3 | passed | 0 |
| E4 | passed | 0 |
| E5 | passed | 0 |
| E6 | passed | 0 |

E1 verifies common code identity and all 480 reconstructed flat results/counts.
E2 checks perfect-static admissibility and infeasibility decisions against the
exact semantic minimum for every semantic-populated ALT8 view and every visited
perfect-static replay node. All 480 replay optima and complete tie keys also match.
E3 checks L_ALT<=L_PS on every frozen visited node with independent parent
normalization. E4 checks the decomposition identity on all semantic-populated
views. E2/E3/E4 use the explicit **2e-6 s** audit tolerance, retained from B1-D's
cost audit; the maximum identity residual is 1.82e-12 s.
E5 checks the exact per-case FP/TP partition and aggregate candidate reconciliation.
E6 verifies frozen algorithms, inputs, outputs and protected evidence after tests.
No frozen implementation defect was found or repaired.

## H. Certificate decomposition

For each of **52,405 semantic-populated nodes**:

G_landmark = L_PS - L_ALT;
G_residual = J_sem* - L_PS;
J_sem* - L_ALT = G_landmark + G_residual.

G_landmark median/P95: **718.421 / 3103.493 s**.
G_residual median/P95: **228.548 / 4855.931 s**.
Landmark loss accounts for 51.85% of summed total slack
and exceeds residual loss in 71.60% of these nodes.
These are descriptive node-weighted summaries, not independent statistical samples.
Medians of components are not added to construct a median total.

There are 139,444 false-positive-only static views.
Their semantic minimum and residual gap are NA; no target is fabricated.
Raw signed components are stored without clipping. The previous signed
G_cert_old=L_oracle-L_deploy is copied exactly (median
1115.011 s) and checked against frozen artifacts.
The new common-target identity is preferred for interpretation and does not
replace or rewrite the historical quantity.

Bucket strata:

| value | nodes | median_G_landmark | p95_G_landmark | median_G_residual | p95_G_residual | sum_landmark_fraction |
|---|---|---|---|---|---|---|
| Ccap | 19038 | 863.873 | 3693.939 | 385.501 | 5701.162 | 51.09% |
| S0cap | 16382 | 838.687 | 3077.197 | 222.953 | 4159.754 | 55.45% |
| SCcap | 16985 | 566.529 | 2304.725 | 71.687 | 4471.539 | 48.68% |

Depth strata:

| value | nodes | median_G_landmark | p95_G_landmark | median_G_residual | p95_G_residual | sum_landmark_fraction |
|---|---|---|---|---|---|---|
| 0 | 519 | 150.773 | 677.174 | 4204.839 | 9807.464 | 4.34% |
| 1 | 794 | 486.249 | 2808.708 | 4244.670 | 9634.391 | 13.32% |
| 2 | 1239 | 713.740 | 3884.681 | 3536.858 | 8468.683 | 25.08% |
| 3 | 1805 | 1371.095 | 4275.936 | 2483.397 | 7522.385 | 35.35% |
| 4 | 2259 | 1127.068 | 4317.195 | 2001.515 | 6495.218 | 39.60% |
| 5 | 2859 | 936.728 | 4108.114 | 1411.591 | 5865.256 | 43.50% |
| 6 | 3882 | 913.785 | 3583.943 | 782.025 | 4748.671 | 47.25% |
| 7 | 5487 | 838.188 | 3249.587 | 447.244 | 4203.365 | 52.90% |
| 8 | 7745 | 773.853 | 2982.409 | 242.809 | 3305.989 | 60.21% |
| 9 | 11086 | 662.807 | 2564.090 | 129.055 | 1854.462 | 70.04% |
| 10 | 14730 | 615.591 | 2465.612 | 72.578 | 1101.775 | 77.05% |

Envelope, SOC, scenario and OD strata are also provided in
`certificate_decomposition_strata.csv`.

## I. Three-level search comparison

| method | regions_created | regions_popped | refinements | leaves | candidate_checks | exact_evaluator_calls | semantic_evaluations |
|---|---|---|---|---|---|---|---|
| ALT8 | 191849 | 147765 | 98525 | 31779 | 706117 | 249642.0 | 173577 |
| B1O | 19398 | 19398 | 11216 | 1821 | 48069 | 48069.0 | 48069 |
| perfect_static | 78891 | 58134 | 39591 | 6238 | 166000 | 76092.0 | 54770 |

B1-O counts are **logical oracle work**: its semantic membership and oracle
summary scans were already paid offline and are not actual computational savings.
The B1-O exact-call column denotes logical leaf evaluator work only. Perfect-static
counts are paid operations in an **offline counterfactual**, not deployable work.
ALT8 counts are the actual frozen deployable work. Created nodes count nonempty
views consistently; B1-O empty creation attempts are separately retained per case.

| method | median_max_depth | median_case_depth | prune_cost | prune_envelope | prune_energy | prune_schedule |
|---|---|---|---|---|---|---|
| ALT8 | 10.0 | 8.0 | 17461 | 30364 | 8767 | 4953 |
| B1O | 10.0 | 7.0 | 6361 | 0 | 0 | 0 |
| perfect_static | 10.0 | 7.0 | 12305 | 14590 | 3752 | 2415 |

Depth columns summarize per-case deepest created bound and median created-bound
depth. The per-case three-level table retains all 480 cases, including zero-semantic
cases; no cherry-picked ODs are used. Prune counts retain envelope, energy,
schedule and cost reasons separately.

Counterfactual changes from ALT8 to exact static minima:

| component | ALT_total | PS_total | PS_vs_ALT_reduction |
|---|---|---|---|
| N_envelope | 706117 | 166000 | 76.49% |
| N_exact | 249642 | 76092 | 69.52% |
| N_semantic | 173577 | 54770 | 68.45% |

These isolate the effect of metric approximation while keeping the same static
action superset and resource relaxation. They are not a proposed deployed algorithm.

## J. Leaf false-positive decomposition

Exactly **706,117** paid ALT8 leaf checks were assigned once each, in the required
order FP1 envelope, FP2 inbound energy, FP3 later energy, FP4 schedule, FP5 other,
FP6 feasible but effect-free, TP semantic. Inbound and later energy checks use
the accepted evaluator; schedule feasibility uses its accepted start candidates.
Archived per-Site feasibility/effects serve only as offline terminal truth.
Any undeclared concrete rejection would have stopped diagnosis.

| category | count | fraction |
|---|---|---|
| envelope | 456475 | 64.65% |
| energy | 42921 | 6.08% |
| schedule | 31892 | 4.52% |
| other | 0 | 0.00% |
| no_effect | 1252 | 0.18% |
| semantic | 173577 | 24.58% |

Terminal counts: FP1=456,475,
FP2=4,330, FP3=38,591,
FP4=31,892, FP5=0,
FP6=1,252, TP=173,577.
Their sum exactly equals frozen candidate checks in every case; all non-FP1
checks reconcile to exact evaluator calls, and TP reconciles to semantic evaluations.
Energy has precedence over schedule when both fail. Bucket, scenario, SOC,
envelope, OD and leaf-depth counts/fractions are in `false_positive_strata.csv`.

## K. Incumbent acquisition

Zero-stop initialized a finite incumbent in **120 cases**;
**360** started without one. A Site incumbent was acquired
in 360 cases; 120 had no Site update.
Missing Site updates remain NA and are not treated as delayed infinite incumbents
when zero-stop already supplied finite U.

The frozen heap order is reconstructed from saved bound decisions and verified
against every trace's cumulative candidate count. Counts are **through the first
successful leaf batch**, including its pop and all batch candidates, consistent
with the frozen batch update policy. Median/P95 pops to first Site incumbent:
**101.5 / 266.2**.
Median candidate/exact checks to first Site incumbent:
234.0 / 13.0.
Median/P95 fraction of refinements completed by then:
**47.99% / 90.77%**.
Among cases lacking zero-stop U, that fraction is
47.99% / 90.77%;
37,775 of their
86,953 total refinements preceded/accompanied
the first Site update. These quantify delay without changing acquisition strategy.

Per-case initial/first/final costs, pops, refinements, candidate/exact calls and
fractions are saved in `incumbent_acquisition.csv`. Time-to-first-incumbent is
NA because frozen traces did not record it reliably. No time is inferred from
operation counts. The structural interpretation below distinguishes incumbent
delay from the counterfactual effect of tighter bounds.

## L. Structural diagnosis

The evidence supports a mixed certificate bottleneck with metric approximation as the first intervention to test. Median landmark loss is 718.42 s versus 228.55 s residual loss, and landmark loss is larger at 71.60% of semantic-populated visited nodes. However, summed landmark share is only 51.85%, residual P95 is 4,855.93 s, and root-depth residual median is 4,204.84 s versus 150.77 s landmark loss. Thus residual abstraction is not uniformly small: it dominates coarse levels, while landmark loss dominates deeper levels (77.05% of summed slack at depth 10). The counterfactual supplies stronger operational evidence than a median comparison alone: replacing only ALT8 metrics reduces paid envelope checks from 706,117 to 166,000 (76.49%) and exact calls from 249,642 to 76,092 (69.52%). The largest paid rejection category is envelope failure: 456,475 checks, or 64.65% of all checks. Energy and schedule rejection account for 6.08% and 4.52%; feasible effect-free plans account for only 0.18%. This does not support neutral roles or treating effect-free visits as the main bottleneck.

Incumbent delay is material: in the 360 cases without a zero-stop seed, 37,775 of 86,953 refinements (43.44%) occurred through the first successful Site batch; the case median fraction is 47.99%. These observations do not identify delay as an independent causal defect. Perfect-static replay keeps the same acquisition policy yet reduces total refinements from 98,525 to 39,591 (59.82%), showing that stronger metric information alone changes substantial work. Since certificate losses are not modest, the interpretation matrix does not support hierarchy redesign as the primary next hypothesis.

The fair deployable comparator explains why the historical negative semantic
reduction can coexist with avoided online work. It does not erase certificate
looseness or reverse the original workload gate. Residual slack remains a mixture
of static false positives, independently minimized components, shortest-distance
versus fastest-route actual length, and optimistic charging power. B1-E does not
invent an unsupported finer attribution among those residual terms.

## M. Next hypothesis

Exactly one primary next hypothesis: **B1-D2 stronger deployable metric bounds**.

Test a separately preregistered, proven deployable metric-bound design first, potentially using road-cell/interface summaries in later theory work. Keep the present static action model and hierarchy fixed for that first comparison so the causal contribution remains identifiable. Residual action/resource relaxation is a secondary unresolved issue, especially at coarse depths, but is not a second primary recommendation in this milestone. The fair flat comparison is favorable (94.16% fewer envelope checks and 77.39% fewer exact calls in aggregate), yet the large perfect-static counterfactual effect shows that remaining looseness still materially affects online work; freezing one-stop and advancing to B2 is therefore premature. No proposed remedy is implemented here.

This recommendation is post-hoc and requires a separate preregistered next-stage
design. No remedy, extra landmark, new filter, hierarchy redesign or new threshold
was implemented in B1-E. Secondary observations do not constitute additional
primary recommendations. The experiment stops here.

## N. Limitations

Development data only; post-hoc diagnosis; the frozen zero/one-stop semantic domain;
fixed envelopes and canonical charging curve; no holdout, no real multi-stop
claim, no China benchmark, no active-information Go-2, no elevation/temperature
energy model. The perfect-static replay requires offline exhaustive scans and is
not deployable. Node-weighted gap summaries are dependent and conditional on
visited populations. Counts are fully reconciled; timing decomposition remains
limited as stated. B1-E produces a structural diagnosis, not a new GO/NO-GO verdict.

Reproduction: `run_hierarchy_4r_diagnosis.py` (refuses to overwrite a started run),
`analyze_hierarchy_4r_diagnosis.py`, and `finalize_hierarchy_4r_diagnosis.py`.
New diagnostic helpers are confined to `src/hierarchy4r/diagnosis.py`.
`diagnostic_protocol.json` freezes formulas, tolerances, scope and timing limits;
per-case Parquets retain minima, decompositions, PS bounds/traces/leaves and the
full paid-candidate classification. `acceptance.json` records audit status,
historical outcomes, recommendation, tests and preservation hashes.
