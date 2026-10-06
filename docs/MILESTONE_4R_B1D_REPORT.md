# Milestone 4R-B1D — Deployable Region Bounds

Date: 2026-10-02 (Asia/Shanghai). **B1-D deployable gate failed. D1–D5 all pass.**

## A. Scope

This experiment tests deployable one-stop Region lower bounds on the existing
binary topology-first hierarchy. It adds fixed static capability summaries and
eight directed landmarks; it does not redesign the tree or the stop domain.
The B1 action-effect amendment remains unchanged. Zero-stop is separate; only
actual C/S/CS effects make a Site action semantic. No neutral role was added.
The earlier blocker and H0 migration audit remain in the separate
[B1 report](MILESTONE_4R_B1_REPORT.md) and archived blocker evidence.

## B. B1-O statistical closure

The explicitly approved zero-denominator clarification closes the B1-O gate
without rerunning its hierarchy or changing oracle traces. Of **480 cases**,
**387** have a positive semantic denominator and **93** have r=NA, labelled
`no_semantic_site_pruning_opportunity`. All cases remain in correctness and runtime.
The conditional macro median is **91.86%**;
P(r>=50%)=98.97%, P(r>=25%)=100.00%.
The all-case micro reduction is **83.23%**.
The unchanged thresholds classify B1-O as **strong GO**.
`b1_oracle_classification.json/csv` and B1's `zero_denominator_policy.json`
record the population and authority. Pre-closure report and acceptance copies
are retained in this new result namespace. Oracle reductions describe logical
pruning potential, not saved oracle preprocessing computation.

## C. Preservation

The pre-implementation full suite passed **153 tests**. The final full suite
passed **187 tests**, with zero failures, errors or skips.
The frozen accepted baseline commit remains `20b658257fb67655e09229411783935e17084fa4`. Git changes are
untracked milestone files; no accepted tracked source/output was changed.
The full before/after manifests record Git status, accepted source hashes,
933 protected checkpoint files, 4881 B1 evidence files,
archived blocker hashes, and the five authorized closure edits.
Final protected-artifact verification passed with zero unexpected changes.
No dependency installation or new geographic data was used.

The frozen hierarchy hash is
`4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805`:
60,498 attached Sites, 2,047 Regions, 1,024 leaves, branching factor 2,
primary capacity 64, including the accepted co-attached early leaf of size 65.
Existing Region IDs, membership and parking Sites were preserved.

## D. Frozen landmarks

The candidate set is the largest directed SCC (5,819,010 nodes).
The equirectangular projection is centered on all graph-node coordinates
(longitude 14.945060151198, latitude 46.198809852674).
Normalized directions use descending projection score, then ascending OSM/node
identity; repeated extrema advance to the next unique node. This list was saved
before comparative queries and was selected twice identically.

| Direction | Graph node ID | OSM node ID |
|---|---:|---:|
| E | 611316 | 412449453 |
| W | 765317 | 523338682 |
| N | 537267 | 336944294 |
| S | 5181121 | 9433841848 |
| NE | 2880865 | 3035262964 |
| SE | 121844 | 247060591 |
| NW | 1521217 | 1403398173 |
| SW | 2300632 | 2204641569 |

The SCC restricts landmark selection only. Sites and queries outside it remain
eligible; unavailable finite landmark terms safely contribute zero.

## E. Preprocessing

Two independent metrics use exactly the accepted directed edges: travel time
and physical-distance shortest paths. The distance metric d_D is **not** the
actual length L_T of the selected fastest route. The original fastest-route
evaluator is unchanged. Across 30 ODs and both directions, independent checks
verified d_D<=L_T for **3,577,770 attached-Site legs**, with
zero violations (audit tolerance 1e-5 m).

There are 32 full-node float64 memory-mapped arrays, preserving IEEE infinities
and graph node order, with per-array hashes and graph/config input hashes.
Array payload projection: 1,508,479,488 bytes; stored arrays
including headers: **1,508,483,584 bytes**. The projected additional
RSS was 9.405 GiB and passed the accepted 38 GiB RSS /
10 GiB available-memory reserve guards. Observed preprocessing peak RSS was
**4.154 GiB**; query peak was
**5.687 GiB**.
The query driver separately checked a 10 GiB additional-memory projection before
graph loading and retained per-OD memory guards.

Total preprocessing took 152.889 s, including graph loading,
selection, array hashing/repeat checks and summaries. Logged SSSP/storage work
took 126.424 s; Region summaries took 4.036 s.
The summary Parquet is 1,352,226 bytes; query arrays separately
store min/max/count/children. Ccap has 2,749 Sites; scheduled support partitions
into 45,129 S0cap and 2,480 SCcap Sites. These are static supersets, not effects.
The fixed summary shape implies 3,144,192 payload
bytes; the observed summary NPY is 3,144,320 bytes.
`storage_accounting.json` additionally records counts, children and leaf-ID disk
sizes, separate from the compact Parquet summary.

Every Region/bucket/landmark stores forward/reverse min and max. Infinite maxima
are retained, never replaced by finite maxima. Empty buckets create no bound
node. Independent bottom-up reconstruction exactly matched all summaries and
counts; the static audit checked all 6,141 Region/bucket views and every leaf ID.
The four direction/metric arrays for landmark 0 were recomputed exactly;
the remaining arrays use the same deterministic SSSP primitive.

For each finite ALT difference, the implementation subtracts
`1e-6 + 2e-8*(abs(a)+abs(b))` in the metric's units, then applies nextafter
toward minus infinity. The relative allowance exceeds 8*n*float64 epsilon
for this fixed nonnegative graph. Cost bounds subtract a further 1e-5 s and
round downward. Accepted feasibility tolerances remain intact. No inf-inf is
evaluated. Charging lower bounds use the fixed maximum 100 kW, not minimum or
average power. Raw and parent-monotone bounds are both recorded.

## F. D1–D5

| Gate | Violations | Result |
|---|---:|---|
| D1 | 0 | pass |
| D2 | 0 | pass |
| D3 | 0 | pass |
| D4 | 0 | pass |
| D5 | 0 | pass |

D1 checked all 286,567 per-case semantic actions
against the scenario's static bucket. Exact parent/child and leaf membership
verification extends coverage over every root-to-leaf path. Scheduled S0cap and
SCcap partition supported Sites; SCcap may perform S or CS.

D2 independently checked 1,296 real Region bounds before comparison, then all
**191,849 visited Region/bucket bounds** against exhaustive
static Site minima for both metrics and directions. D3 checked all
**52,405 semantic-populated views** against their exact
semantic minimum, including every infeasibility decision. There were
139,444 false-positive-only views, reported separately.
Audits are offline and do not enter online bound construction.

D4 matched the full accepted plan key (rounded objective, charging energy,
stop count, Site identity), not just the optimal value, in all 480 cases.
D5 recorded every bound's eight landmarks, 16 summary rows, zero Site IDs,
zero evaluator calls and zero oracle table reads. There were
146,439 internal views. Leaf ID access is guarded by
phase and node type. An online file-access guard rejects B1 oracle paths.
The deployable modules import no oracle bound code; independent auditing occurs
only after each timed query and clean flat control.

## G. Deployable exact results

All **480 epsilon=0** queries completed with identical B1 semantic optima and
accepted ties. Zero-stop supplied a verified initial incumbent where feasible;
otherwise search started at infinity and descended best-bound-first. Only exact
semantic leaf plans updated it. Zero-stop was ultimately selected in
120 cases. No optional epsilon runs were needed.

## H. Pruning/work results

Primary work counts **every reached leaf candidate check**, including exact
envelope rejects and static false positives; objective calls are separately
reported. This is conservative and cannot inflate savings by hiding work.
Flat semantic actions total **286,567**. B1-D performed
**706,117 candidate checks**, including
249,642 concrete Site evaluator calls and
456,475 outside-envelope checks; only
173,577 evaluated actions were semantic.

On the 387 positive-denominator cases, the primary conditional median reduction
is **-183.95%**. All-case micro reduction is
**-146.41%**. Negative values, if present, mean more
candidate work than the semantic flat denominator and are retained unchanged.
The 93 zero-semantic cases remain NA; they incurred
2,768 candidate checks, included in the micro numerator.

The separate operational baseline checks all appropriate static candidates:
12,085,920 checks across 480 cases. Against that larger
baseline, median reduction is 96.28%, micro
reduction 94.16%. These values do not replace the
preregistered semantic-denominator metric.

## I. Oracle retention

B1-O median reduction is 91.86%; B1-D median reduction is
-183.95%. Their ratio is
**-2.0025**, compared with the fixed **0.70** retention threshold.
Both medians use the same 387-case population. No excluded effect-free legacy
action was added to the semantic denominator.

## J. Timing

The clean flat control uses the same routing arrays and exact leaf routine,
without H0 observation-table serialization inside the timed section. The
separate avoided-work control times exactly the static candidates omitted by
the completed hierarchy run; routing and construction of that complement are
outside timing. Its candidate counts plus reached-leaf counts equal the full
static flat counts for every case. This isolates replaced Site work without
subtracting incomparable H0 diagnostic runtimes.

| Component | Median seconds | P95 seconds |
|---|---:|---:|
| lookup_seconds | 0.000050 | 0.000070 |
| bound_seconds | 0.041150 | 0.096650 |
| refinement_overhead_seconds | 0.002828 | 0.007548 |
| leaf_seconds | 0.008342 | 0.150566 |
| search_seconds | 0.052522 | 0.248099 |
| shared_routing_seconds | 2.249886 | 2.300095 |
| flat_seconds | 0.101927 | 0.437503 |
| end_to_end_seconds | 2.304883 | 2.501946 |
| flat_end_to_end_seconds | 2.329920 | 2.683004 |
| bound_refinement_seconds | 0.043886 | 0.104263 |
| avoided_site_seconds | 0.087015 | 0.261569 |

Hierarchy summary/index loading took 0.004673 s.
All 480 search sections total 35.864 s; clean flat
sections total 69.068 s. Shared routing was
computed once per OD (67.404 s in total) and
reused for 16 states; the per-query end-to-end columns include its full OD cost
for both methods. They are counterfactual standalone-query comparisons, not a
sum of actual experiment elapsed time. Offline exhaustive distance/cost audits
and serialization are excluded from online timing.

The original median bound+refinement versus avoided-flat-work timing gate
**passed**. Timings are one sequential development pass with
uncontrolled Python/filesystem cache effects; they are not a production latency
guarantee. Counts and correctness do not depend on timing. Preprocessing is
reported separately and has not been amortized into a claimed speedup.

## K. Certificate diagnosis

The signed offline certificate gap G_cert=L_oracle-L_deploy has median
**1115.011 s** and P95 **5942.712 s** over
52,405 semantic-populated visited views. False-positive-only views
have no oracle semantic minimum and their gap is NA, not zero. The oracle
comparison partitions current performed effects offline and takes the minimum
valid oracle role bound for the static bucket. Signed gaps are not clipped;
parent-monotone correction can occasionally make a deployable bound stronger
than the corresponding raw oracle bound.

| Static bucket | Views | Median G_cert (s) | P95 (s) |
|---|---:|---:|---:|
| Ccap | 19,038 | 1264.865 | 6884.698 |
| S0cap | 16,382 | 1324.101 | 5692.604 |
| SCcap | 16,985 | 723.297 | 5142.898 |

| Depth | Views | Median G_cert (s) | P95 (s) |
|---|---:|---:|---:|
| 0 | 519 | 2496.185 | 5922.403 |
| 1 | 794 | 2878.334 | 9442.472 |
| 2 | 1,239 | 3301.310 | 8284.308 |
| 3 | 1,805 | 3289.491 | 8223.130 |
| 4 | 2,259 | 2534.386 | 8078.089 |
| 5 | 2,859 | 2191.610 | 7211.171 |
| 6 | 3,882 | 1658.834 | 6391.065 |
| 7 | 5,487 | 1326.204 | 6034.120 |
| 8 | 7,745 | 1062.266 | 5141.386 |
| 9 | 11,086 | 829.635 | 3847.992 |
| 10 | 14,730 | 712.312 | 3034.202 |

All requested depth, bucket, envelope, SOC, scenario and OD strata are in
`certificate_gap_strata.csv`. `landmark_slack_strata.csv` separately compares
the time and shortest-distance ALT bounds with exact static-bucket minima.
Distance is only a one-sided energy lower bound: this experiment does not
substitute shortest-distance geometry for fastest-route actual-length
oscillations or claim a new route-length certificate.

Median exact-static-minimum minus ALT-bound slack is substantial in both
independent metrics:

| Bucket | Inbound time (s) | Outbound time (s) | Inbound distance (km) | Outbound distance (km) |
|---|---:|---:|---:|---:|
| Ccap | 735.62 | 637.42 | 6.68 | 4.42 |
| S0cap | 1005.01 | 767.20 | 12.34 | 8.24 |
| SCcap | 647.84 | 635.84 | 5.68 | 4.11 |

| Region decision | Count | Fraction of all created bounds |
|---|---:|---:|
| cost | 17,461 | 9.10% |
| infeasible_envelope | 30,364 | 15.83% |
| infeasible_inbound_energy | 3,266 | 1.70% |
| infeasible_noncharger_energy | 5,501 | 2.87% |
| infeasible_schedule | 4,953 | 2.58% |
| leaf | 31,779 | 16.56% |
| refined | 98,525 | 51.36% |

The three energy infeasibility reasons (inbound, charger outbound and noncharger
total energy) together prune **4.57%** of created bounds. False positives
at reached leaves total 532,540, a rate of
**75.42%**. These are paid checks, including envelope
rejects, infeasible plans and effect-free plans. Static supersets and landmark
slack are therefore distinct sources of lost oracle pruning potential. No
landmark, bucket, hierarchy or threshold was tuned in response to these results.

## L. Gate statement

**B1-D deployable gate failed.**

The workload gate requires both median reduction >=50% and oracle retention
>=0.70. Observed values are -183.95% and
-2.0025; workload gate passed=False.
The separately measured timing gate passed. Correctness remains
fully passed regardless of the empirical result. B1-O strong GO identifies
oracle potential; it does not by itself establish deployable computational gains.

## M. Limitations

These results cover the 480 development cases only, the zero/one-stop semantic
domain, fixed preregistered Safe Detour Envelopes and canonical charging curve.
They make no real multi-stop claim, use no holdout, no active-information Go-2,
and no elevation/temperature energy model. The eight fixed landmarks and the
existing hierarchy were not tuned. Conditional macro reductions concern only
the 387 cases with semantic Site-pruning opportunity. Optional epsilon runs,
B2, China benchmark construction and holdout evaluation were not performed.

## Reproduction and artifacts

New results are exclusively under `results/milestone_4r_b1d`, with preserved
B1 closure copies, manifests, mmap arrays, summaries, per-case audit/search
Parquets, D1–D5 tables, work/timing tables, gap strata, test logs and acceptance.
Scripts are `preprocess_hierarchy_4r_deploy.py`, `audit_deploy_landmarks.py`,
`run_hierarchy_4r_deploy.py`, `audit_hierarchy_4r_deploy_static.py`,
`time_hierarchy_4r_deploy_avoided.py`, `analyze_hierarchy_4r_deploy.py` and
`finalize_hierarchy_4r_deploy.py`. Preprocessing and primary query scripts refuse
to overwrite completed frozen runs. Online implementation is confined to
`src/hierarchy4r/deploy.py` and `deploy_search.py`; accepted evaluator sources
remain untouched. Run the full project suite with the accepted real-data and
milestone-result flags; `final_tests.xml` records the exact final outcome.
