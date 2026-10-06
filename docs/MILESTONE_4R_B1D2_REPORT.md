# Milestone 4R-B1D2 — Boundary-Augmented Deployable Metric Bounds

Date: 2026-10-03 (Asia/Shanghai). All 480 exact cases completed; F1–F7 have zero violations.

## A. Scope and stage rule

**B1-D2 is the final one-stop algorithmic iteration. After B1-D2, the one-stop method is frozen and the next research milestone is B2 multi-stop formalization. B1 may be reopened only for a fundamental correctness defect, not for additional performance tuning.**

This final development experiment isolates directed Region boundary **travel-time**
information added to frozen ALT8. Performance is descriptive on the same development
cases used by B1-E. There is no new GO/NO-GO threshold, weighted workload score,
positive-epsilon comparison, or performance-based reopening of one-stop research.

## B. Frozen evidence

The current pre-implementation full suite passed **207 tests**, no failures, errors
or skips. The final suite passed **235 tests**, also without failures,
errors or skips. An intermediate run had 234 passes and one failure in a newly
added synthetic fixture whose Site ID and OSM ID disagreed. The fixture was
corrected without changing algorithm code; its failed log/XML and explanation
remain archived as `final_tests_invalid_new_fixture.*` and
`test_fixture_correction.json`. Before/after verification covers **11,332 frozen
files**, 9 archived prior-attempt files and all accepted
protection manifests. No accepted tracked source/output differs; no protected hash
changed. Git remains `20b658257fb67655e09229411783935e17084fa4`. Exact status is retained in both preservation files.

The prior 2026-10-02 attempt stopped on a pre-existing protected `.gitignore` change
and two preservation-test failures. That blocker report, acceptance, logs and diff
are retained unchanged under `blocked_attempt_2026_10_02/`. The protected file was
restored before this resumed run; this history is not erased or counted as a current
algorithm defect. No frozen algorithm was repaired during B1-D2.

Hierarchy SHA-256: `4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805`.
Landmark-manifest SHA-256: `4627d789aaae53ddf5e084bf8ccdcff0b44ec0ca181c5e8c3b99a6c7b5975af1`.
Boundary-manifest SHA-256: `4c5be4f7f8c7f72db707297832f26177f3344f35c9810210b3304581296b26af`.

The accepted 2,047 Regions, 1,024 leaves, 60,498 attached Sites, eight landmarks,
Region memberships, static Ccap/S0cap/SCcap buckets, energy distance bounds,
charging/schedule/evaluator semantics and incumbent/tie policy remain unchanged.
All new evidence is confined to the B1-D2 result directory and this report;
new implementation consists only of boundary extraction/lookup/augmentation and
experiment diagnostics. No dependencies were installed. Peak experiment RSS was
6.951 GiB; existing guards passed.

## C. Boundary construction

For every frozen road-node cell V_R, ingress contains in-cell endpoints of directed
edges entering from outside; egress contains in-cell endpoints of directed edges
leaving to outside. Boundaries use the accepted **11,561,067 directed edges** and
**5,892,498 road nodes**, never geometry, Site positions or undirected adjacency.
The original OSM-rank cell file is mapped back to accepted node IDs. All Site
attachment cells independently match the frozen leaf membership artifact.

Extraction repeated with reversed edge iteration yields identical sorted arrays;
repeated Parquet serialization has identical SHA-256. Every stored endpoint has a
cross-cell edge witness, and every directed crossing contributes its endpoint.
The manifest contains graph, hierarchy, extraction-code and per-Region hashes.
Boundary membership/index files, complexity and safety were frozen before search.

| quantity | median | p95 | max | total |
|---|---|---|---|---|
| ingress | 94.0 | 499.7999999999993 | 3454.0 | 339039.0 |
| egress | 94.0 | 502.0 | 3451.0 | 339038.0 |
| union | 102.0 | 527.6999999999998 | 3603.0 | 360358.0 |

Sizes are boundary references across Regions, not distinct graph-wide nodes.
The depth table also retains median/P95/max/totals and ratios against road-node,
Site and each static-bucket count; zero denominators remain NA. A node may be in
both boundaries. Storage is **29,708,212 bytes** for the primary
membership/index artifacts (excluding the duplicate reconstruction witness).
Extraction took **9.779 s**, peak RSS
**1033.7 MiB**. No compactness threshold was introduced.

## D. F1–F7

| gate | status | violations |
|---|---|---|
| F1 | passed | 0 |
| F2 | passed | 0 |
| F3 | passed | 0 |
| F4 | passed | 0 |
| F5 | passed | 0 |
| F6 | passed | 0 |
| F7 | passed | 0 |

F1 covers all Regions and directed cross-cell edges. F2 covers **121,526**
created nonempty BA Region/buckets, including immediate infeasibility rejects:
boundary delta and max(ALT,delta) never exceed exact static time minima within
1e-5 s. Offline minima are recomputed independently, inaccessible to online search.
F3 checks independently parent-normalized L_ALT <= L_BA <= L_PS within **2e-6 s**.
F4 checks L_BA <= J_sem* and safe infeasibility for **42,873**
semantic-populated nodes. The other **78,653** nodes have
no semantic target; J_sem and residual fields remain NA.

F5 checks objective and complete accepted plan key in every case. F6 records zero
Site-ID reads, evaluator calls, oracle reads and additional SSSPs in every bound;
actual ingress/egress reads are recorded separately. A file-open guard rejects
oracle evidence access during deployable searches. F7 verifies all frozen inputs,
algorithms, manifests and historical outputs, plus the frozen new boundary artifact.
Explicit empty violation tables are emitted. Per-node numerical evidence is in
`alt_ba_ps_bound_audit.parquet`; per-case gate summaries are separate CSVs.

Boundary reduction uses float64 and the fixed rule
`max(0, nextafter(min - (1e-6 + 2e-8*abs(min)), -inf))`.
Origin/destination inside a cell, empty boundary, or all-unreachable values return
conservative zero. Existing exact current-query arrays supply min-reductions;
there is no boundary routing. The shared two time/actual-length SSSPs per OD are
unchanged; separate offline distance SSSPs support audits only.

The max-combined time bounds feed the unchanged B1-D `cost_bound`, retaining the
same distance inputs, charging relaxation, Pmax=100 kW, overhead, nuisance,
schedule/envelope logic, 1e-5 s downward cost safety and parent maximum. Raw ALT,
raw boundary, combined time, raw cost and parent-normalized costs are saved.
Boundary reductions are cached per Region per case across static buckets; actual
cache-hit reads are zero. This cache contains no Site quantities.

## E. Exactness

All **480/480 epsilon=0** BA optima match the B1 semantic flat reference in accepted
objective and full `(rounded cost, charged energy, stop count, Site-ID tuple)` key.
Zero-stop remains separate; no neutral role is added. Frozen static root/leaf
candidate memberships reconcile exactly without duplication, so semantic action
coverage is preserved. Every pruned semantic-populated node has an admissible
bound and no false infeasibility. All 480 paired ALT8 controls also reproduce their
frozen optimum keys and workload counts exactly.

The search uses the original `deploy_search` and `exact_leaf` functions unchanged:
same heap order, zero-stop seed, envelope check, exact Site evaluator, performed
effects, semantic filtering and tie rule. Only time-bound inputs are augmented.

## F. ALT8 vs BA vs perfect-static

| method | regions_created | regions_popped | refinements | leaves | candidate_checks | exact_evaluator_calls | semantic_evaluations |
|---|---|---|---|---|---|---|---|
| ALT8 | 191849 | 147765 | 98525 | 31779 | 706117 | 249642 | 173577 |
| BA | 121526 | 93544 | 62588 | 16185 | 331172 | 129031 | 93777 |
| perfect_static | 78891 | 58134 | 39591 | 6238 | 166000 | 76092 | 54770 |

The primary ALT8 counts are frozen B1-D v1; perfect-static counts are frozen B1-E
nondeployable counterfactuals; BA counts are this run. Candidate checks are exact
Site envelope checks, including cheap rejects. BA reduces envelope checks by
**53.10%**, exact evaluator calls by
**48.31%**, and refinements by
**36.48%** against ALT8 in aggregate. Operations remain
separate and no weighted score is used. Perfect-static runtime is excluded.

## G. Bound headroom recovery

For semantic-populated BA-visited nodes with L_PS>L_ALT,
H_bound=(L_BA-L_ALT)/(L_PS-L_ALT). Defined nodes: **42,859**.
Median **43.20%**, P25 **5.20%**, P75 **72.82%**,
P95 **95.99%**. Raw values are retained without clipping; zero denominators
remain NA. PS tightens both time and distance metrics, while BA tightens time only,
so the remaining headroom also includes the deliberately frozen distance certificate.

| value | defined | median | p25 | p75 | p95 |
|---|---|---|---|---|---|
| Ccap | 16690 | 0.3693699857377756 | 0.0717125857659496 | 0.6188633264083591 | 0.8453669829216592 |
| S0cap | 12049 | 0.7535815152023659 | 0.4418469478644914 | 0.9208371807741056 | 0.9902863135227064 |
| SCcap | 14120 | 0.240901807720655 | 0.0 | 0.5592589733772898 | 0.8478865644951961 |

`bound_headroom_strata.csv` includes depth, bucket, scenario, OD, SOC and envelope
strata. These dependent, visit-conditioned node summaries are descriptive.

## H. Work headroom recovery

H_work=(N_ALT-N_BA)/(N_ALT-N_PS), only where N_ALT>N_PS.
Micro values use the corresponding aggregate totals; no combined scalar is formed.

| component | defined_cases | median | p95 | micro |
|---|---|---|---|---|
| candidate_checks | 460 | 0.6415595923792645 | 1.0 | 0.6941921842859973 |
| exact_evaluator_calls | 449 | 0.5342465753424658 | 1.0 | 0.6949639873235379 |
| refinements | 480 | 0.6243558029272316 | 0.8214175977653629 | 0.6097838259748193 |

Per-case raw values and NA denominators are in `work_headroom_recovery.csv`.

## I. Envelope-pruning migration

ALT8 Region envelope prunes: **30,364**;
BA: **19,418**.
ALT8 paid leaf envelope rejects: **456,475**;
BA: **202,141**.
Exactly **254,334 (55.72%)** former ALT8
FP1 Site checks are avoided. **202,141** remain paid and
**0** BA rejects were not paid by ALT8; both changes are retained
rather than assuming nested search populations.

The smaller number of Region-envelope rejections does not imply a weaker bound:
BA creates fewer descendant views. Prune counts alone do not measure the number
of candidate checks avoided. Every avoided check has a witness identifying its old leaf and BA terminal ancestor,
prune reason and depth. Median upward movement is **3.0**
levels, P95 **8.0**. The depth/reason distribution and
OD/SOC/envelope strata accompany the per-case reconciliation. A cost or schedule
prune can also avoid an old envelope reject: only witnesses explicitly labeled
`infeasible_envelope` are direct Region-envelope rejection. Bound tightening changes
search order and U arrival as a consequence; the incumbent policy is unchanged.
No improvement is attributed to a new energy certificate or action filter.

## J. Boundary cost and timing

Ingress reads: **36,925,357**; egress reads: **37,322,427**;
total: **74,247,784**. Actual reads per visited Region (across its buckets
within one case) have median **360.0**,
P95 **2993.0**, maximum
**6905**.
Boundary lookup/min-reduction time totals **2.957 s**,
**15.79%** of BA Region-bound time.
Reads per avoided envelope check: **198.02**;
reads per avoided exact evaluation: **615.60**.
These ratios do not imply equivalent computational cost.

Timing totals (seconds):

| component | ALT8 | BA |
|---|---|---|
| lookup_seconds | 0.02482388378120885 | 0.04160207393578565 |
| bound_seconds | 22.489978137658888 | 18.73230759729629 |
| boundary_seconds | 0.0 | 2.9570876355282727 |
| leaf_seconds | 12.087322854902574 | 6.289720108499731 |
| refinement_overhead_seconds | 1.5795302640180802 | 1.0253424586262323 |
| search_seconds | 36.181655140360796 | 26.08897223835809 |
| shared_routing_seconds | 1102.224474683404 | 1102.224474683404 |
| end_to_end_seconds | 1138.4061298237648 | 1128.313446921762 |
| ALT_metric_lookup_replay_seconds | 18.671481356257573 | 11.76986914081499 |

ALT8 and BA use one paired pass with the same shared routing arrays, alternate
execution order by case, and no explicit cache flush or warm-up. Neither diagnostic
serialization nor offline exact-minimum scans are timed as search. The aggregate
BA/ALT search-time ratio is **0.721**;
median per-case ratio is **0.780**.
Boundary load took **0.000587 s**.
`lookup_seconds` is the frozen endpoint-landmark lookup timer. The separate
`ALT_metric_lookup_replay_seconds` measures four frozen ALT metric calculations per
visited node in an isolated alternating replay; it is not subtracted from paired
bound time and is not added to search/e2e. The BA wrapper also pays the existing
ALT cost-formula call before the augmented call; that overhead is retained.

End-to-end adds full shared OD routing to each case, identically for both methods;
unique-OD routing totals **68.889 s** and is
reported separately to avoid confusing amortized experiment time with query cost.
Leaf time includes envelope and accepted evaluator work together. Timing is one
measurement pass with OS/cache variability, not a confirmatory timing gate.

## K. Residual gap

On the common BA-visited semantic population:

| metric | defined | median | p95 |
|---|---|---|---|
| G_ALT | 42873 | 1403.968265827174 | 6924.635957088212 |
| G_BA | 42873 | 894.7996466556524 | 5992.173524120573 |
| G_PS | 42873 | 344.29872307792 | 5260.823927597407 |

G_ALT=J_sem*-L_ALT, G_BA=J_sem*-L_BA, G_PS=J_sem*-L_PS.
All raw rows and depth/bucket strata are retained. Remaining gaps reflect the
unchanged relaxation, static action superset and metric approximations; this run
does not assign an unsupported finer decomposition or repair them. Node-population
changes mean these medians need not equal the earlier B1-E visited-node medians.

## L. Historical context

**B1-O strong GO. B1-D v1 deployable gate failed.** Both historical outcomes remain
unchanged; B1-D correctness and clean timing had passed. B1-E identified dominant
metric-certificate loss and the large paid envelope-rejection class, motivating
this isolated boundary-time test. B1-D2 reports the effect sizes above without
retroactively relabeling B1-D or adding a post-hoc success threshold. Topology-derived
boundary information tightens the deployable time certificate; its measured search
benefit and scan cost are reported componentwise, without claiming architectural
optimality. Residual looseness is documented future work, not another iteration.

Development data only; zero/one-stop only; no independent holdout, China benchmark,
multi-stop implementation or active-information experiment was run.

## M. One-stop freeze

**One-stop method frozen after B1-D2.** No fundamental correctness defect was found.
F1–F7 passed, all exact cases and evidence are complete, and protected artifacts
were reverified. Poor performance or unused headroom cannot open B1-D3. The frozen
boundary manifest, experiment protocol, source hashes and acceptance preserve this
final one-stop variant for subsequent formal work.

## N. Transition

**Next milestone: B2 multi-stop formalization.** B2 implementation was not started.

**One-stop development frozen. Proceed next to B2 multi-stop formalization.**

Reproduction entry points: `build_hierarchy_4r_boundary.py`,
`run_hierarchy_4r_boundary.py`, `analyze_hierarchy_4r_boundary.py`, and
`finalize_hierarchy_4r_boundary.py`. Build/run refuse to overwrite frozen started
artifacts. All new tests and raw gate/work/timing evidence are retained.
