# Milestone 4R-B1D2 Experimental Protocol

**Project:** dy-HiRoute  
**Stage:** Milestone 4R-B1D2 — Boundary-Augmented Deployable Metric Bounds  
**Type:** final one-stop development experiment  
**Population:** existing 480 development cases  
**Primary comparator:** frozen B1-D v1 ALT8  
**Diagnostic ceiling:** frozen B1-E perfect-static replay

## 0. Progress rule

\[
\boxed{\textbf{B1-D2 is the last one-stop algorithmic experiment.}}
\]

After completion, freeze one-stop and proceed to B2. There is no automatic B1-D3.

## 1. Experimental question

Does adding the proven directed road-cell boundary time lower bound to ALT8 reduce deployable search work while preserving exactness and without online Site scans?

Only:

\[
\underline T^-,
\qquad
\underline T^+
\]

change.

Everything else remains frozen.

## 2. Primary design

Use exactly:

\[
\underline T^-_{\rm BA}
=
\max(\underline T^-_{\rm ALT},\delta^-_R),
\]

\[
\underline T^+_{\rm BA}
=
\max(\underline T^+_{\rm ALT},\delta^+_R).
\]

No alternative boundary formula, extra landmark, or secondary design may be selected after comparative performance is seen.

## 3. Frozen non-changes

Do not change:

- hierarchy;
- Region membership;
- leaf capacity;
- landmarks or landmark count;
- \(d_D\) bounds;
- static buckets;
- charging relaxation;
- schedule model;
- envelope definition;
- incumbent policy;
- exact leaf evaluator;
- tie semantics;
- 480 development cases.

Do not add witness heuristics, learned filters, state-dependent action filters, or new pruning mechanisms.

## 4. Static boundary extraction

Before comparative B1-D2 search:

1. compute \(\partial^-R\) and \(\partial^+R\) for every Region;
2. save deterministic boundary membership;
3. save a manifest with hierarchy hash, graph hash, extraction-code hash, and per-Region boundary hashes;
4. freeze boundary artifacts.

No query outcome may influence boundary construction.

## 5. Boundary complexity audit

Before inspecting comparative results, report by depth:

- ingress boundary size median/p95/max;
- egress boundary size median/p95/max;
- union boundary size median/p95/max;
- total boundary references;
- Region road-node counts;
- Region Site counts;
- relevant static-bucket sizes.

Also report boundary-size ratios against Region node/Site/bucket size.

No performance threshold is attached.

## 6. Query-time implementation

Use existing exact arrays:

\[
d_T(o,\cdot),
\qquad
d_T(\cdot,z).
\]

For each visited Region:

- if \(o\in V_R\), set \(\delta^-_R=0\);
- otherwise scan only \(\partial^-R\);
- if \(z\in V_R\), set \(\delta^+_R=0\);
- otherwise scan only \(\partial^+R\).

If the relevant boundary is empty or no finite term exists, return 0.

Instrument boundary-node reads.

No Site IDs may be read for bound construction.

## 7. Numerical safety

Freeze an outward/downward float64 safety adjustment before comparative results.

Audit equality cases and ensure:

\[
\underline T^{BA}
\]

never exceeds the mathematical lower bound due to rounding.

## 8. Offline boundary audit

For every visited Region/bucket, compare against exact static-bucket Site minima:

\[
\delta_R^-\le T_A^{-,*},
\qquad
\delta_R^+\le T_A^{+,*}.
\]

Also verify:

\[
\underline T^-_{\rm ALT}
\le
\underline T^-_{\rm BA}
\le
T_A^{-,*},
\]

\[
\underline T^+_{\rm ALT}
\le
\underline T^+_{\rm BA}
\le
T_A^{+,*}.
\]

Required violations:

`0`

## 9. Cost-bound audit

For semantic-populated nodes verify:

\[
L^{ALT}
\le
L^{BA}
\le
L^{PS}
\le
J_{\rm sem}^*.
\]

Required violations:

`0`

False-positive-only nodes still participate in ALT≤BA≤PS checks where defined.

## 10. Exact search

Run B1-D2 at:

\[
\epsilon=0
\]

for all 480 cases.

Require:

- exact objective match;
- exact accepted tie-key match;
- no lost semantic action.

Required mismatches:

`0`

No positive-\(\epsilon\) run is needed.

## 11. No-hidden-scan instrumentation

For every internal Region bound computation record:

- ingress boundary reads;
- egress boundary reads;
- Site IDs read;
- exact evaluator calls;
- oracle-table reads.

Required:

- Site IDs read: 0;
- evaluator calls: 0;
- oracle reads: 0.

Boundary reads are allowed and counted.

## 12. Hard gates F1–F7

### F1 — Boundary extraction correctness

Every stored ingress/egress node satisfies the formal directed graph predicate.

Required violations: `0`

### F2 — Boundary lower-bound validity

Offline static-minimum audit.

Required violations: `0`

### F3 — ALT≤BA≤PS ordering

Required violations: `0`

### F4 — BA cost-bound admissibility

Required violations: `0`

### F5 — Exact optimum/tie preservation

480 cases.

Required mismatches: `0`

### F6 — No hidden Site scans

Required violations: `0`

### F7 — Frozen one-stop components unchanged

Hierarchy, landmarks, static buckets, energy bound, evaluator, incumbent policy.

Required unauthorized changes: `0`

Only F1–F7 are hard acceptance gates.

## 13. Three-level work comparison

Compare:

1. frozen ALT8 B1-D v1;
2. B1-D2 boundary-augmented;
3. frozen B1-E perfect-static ceiling.

Report separately:

- Regions created;
- Regions popped;
- refinements;
- leaves reached;
- envelope checks;
- exact evaluator calls;
- semantic evaluations.

No weighted aggregate score.

## 14. Boundary work accounting

Report:

- total ingress boundary reads;
- total egress boundary reads;
- total boundary reads;
- median/p95 reads per visited Region;
- boundary lookup/min time;
- fraction of Region-bound time spent on boundary scans.

Compare boundary reads descriptively with:

- envelope checks avoided;
- exact evaluations avoided.

Do not equate one boundary read with one Site evaluation.

## 15. Bound headroom recovery

For nodes with nonzero ALT→PS gap:

\[
H_{\rm bound}
=
\frac{L^{BA}-L^{ALT}}
{L^{PS}-L^{ALT}}.
\]

Report median, p25, p75, p95, and strata by:

- depth;
- bucket;
- scenario;
- OD.

No threshold.

## 16. Work headroom recovery

Compute separately:

\[
H_{\rm work}
=
\frac{N_{\rm ALT}-N_{\rm BA}}
{N_{\rm ALT}-N_{\rm PS}}
\]

for:

- envelope checks;
- exact evaluator calls;
- refinements;

only where denominator is positive.

No threshold.

## 17. Envelope-focus analysis

Report:

- Region envelope prunes under ALT8 vs BA;
- leaf envelope rejects under ALT8 vs BA;
- number/fraction of former ALT8 leaf envelope rejects avoided;
- depth at which pruning moves upward.

This is the primary mechanism-specific analysis.

## 18. Residual gap

Report:

\[
J_{\rm sem}^*-L^{ALT},
\qquad
J_{\rm sem}^*-L^{BA},
\qquad
J_{\rm sem}^*-L^{PS}.
\]

Residual looseness is documented but not repaired in B1-D2.

## 19. Timing

Measure separately:

- boundary extraction preprocessing;
- boundary artifact loading;
- boundary lookup/min time;
- Region bound/refinement time;
- leaf evaluation time;
- search time;
- shared routing time;
- end-to-end time.

Use the same timing policy for ALT8 and BA.

Perfect-static runtime is diagnostic only and must not be used as deployable timing.

No new timing pass/fail threshold.

## 20. Performance interpretation

Because B1-D2 is post-diagnosis on the same development set, performance is descriptive only.

Do **not** create a new GO/NO-GO threshold.

Even if gains are small, B1-D2 completes if F1–F7 pass.

## 21. Required artifacts

Produce at minimum:

- boundary membership artifact;
- boundary complexity table;
- boundary manifest/hash;
- numerical-safety config;
- F1–F7 audit tables;
- per-case B1-D2 work table;
- per-node ALT/BA/PS bound table;
- headroom-recovery tables;
- envelope-pruning migration table;
- boundary-work accounting;
- timing table;
- preservation manifests;
- `docs/MILESTONE_4R_B1D2_REPORT.md`;
- `results/milestone_4r_b1d2/acceptance.json`.

## 22. Final report structure

The report must include:

1. scope and final-one-stop rule;
2. preservation;
3. boundary construction and complexity;
4. F1–F7;
5. 480-case exactness;
6. ALT8 vs BA vs perfect-static;
7. \(H_{\rm bound}\) and \(H_{\rm work}\);
8. envelope-pruning migration;
9. timing and boundary cost;
10. residual gap;
11. one-stop freeze statement;
12. transition to B2.

## 23. Completion rule

After artifacts and report are complete:

\[
\boxed{\textbf{freeze one-stop and move to B2.}}
\]

Do not start B2 implementation in the same run.
