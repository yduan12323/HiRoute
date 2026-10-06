# Milestone 4R-B1E Formal Specification

**Project:** dy-HiRoute  
**Stage:** Milestone 4R-B1E — Deployable Baseline & Certificate Decomposition  
**Status:** diagnostic specification after B1-D v1  
**Normative predecessors:** `RESEARCH_SPEC_v0.2.md`, `MILESTONE_4R_B0_FORMAL_SPEC.md`, B1 action-domain amendment, `MILESTONE_4R_B1D_FORMAL_SPEC.md`, accepted B1/B1-D reports  
**Implementation authorization:** diagnostic only — no hierarchy redesign, no landmark retuning, no B2

---

# 0. Motivation

B1-D v1 established two facts simultaneously:

1. **Correctness passed.**
   The deployable hierarchy preserved all 480 exact B1 semantic optima and tie keys; D1–D5 had zero violations.

2. **The preregistered deployable workload gate failed.**
   Relative to the **semantic oracle denominator**, the median reduction was negative.

At the same time, the same completed run showed that relative to a static-information flat baseline, the hierarchy avoided most candidate checks and passed the separately measured timing gate.

These statements are not contradictory.

They expose an information-state mismatch between two baselines:

\[
\boxed{
\text{semantic-oracle flat}
\neq
\text{deployable flat}.
}
\]

B1-E does **not** retroactively reclassify B1-D v1.

The historical conclusion remains:

\[
\boxed{
\textbf{B1-D v1 deployable gate failed.}
}
\]

B1-E asks what that failure actually means and whether the next research problem is:

- the work metric/baseline;
- landmark approximation;
- static action abstraction;
- Region relaxation physics;
- incumbent acquisition;
- or the hierarchy itself.

---

# 1. B1-E research questions

B1-E answers four questions.

## Q1 — Fair deployable baseline

Given the same online information available to B1-D, how much work does the hierarchy save relative to a nonhierarchical flat algorithm?

## Q2 — Landmark approximation loss

How much lower-bound looseness comes specifically from replacing exact static-bucket metric minima with the 8-landmark ALT approximation?

## Q3 — Residual static-relaxation loss

Even with perfect static metric minima, how much lower-bound slack remains because of:

- static capability supersets;
- componentwise Frankenstein minima;
- optimistic \(P_{\max}\) charging;
- other one-stop relaxation structure?

## Q4 — Leaf false-positive composition

What fraction of reached static candidates are rejected because of:

- envelope;
- energy;
- schedule;
- no performed effect;
- other infeasibility?

B1-E is complete only when these sources are separated rather than conflated into one negative reduction number.

---

# Part I — Freeze all algorithms

## 2. No algorithm changes

B1-E must use the already completed B1-D v1 artifacts.

The following are frozen:

- the 2,047-Region / 1,024-leaf hierarchy;
- Region memberships;
- leaf capacity;
- the 8 landmarks;
- landmark selection rule;
- \(d_T\) and \(d_D\) arrays;
- static `Ccap`, `S0cap`, `SCcap` buckets;
- B1-D exact search implementation;
- cost bounds;
- numerical tolerances;
- incumbent rules;
- B1 semantic domain;
- 480 development cases.

Do not:

- add landmarks;
- replace landmarks;
- change hierarchy geometry;
- change leaf capacity;
- change static buckets;
- add learned filters;
- add a new heuristic;
- change pruning thresholds;
- rerun B1-D with a stronger bound and call it B1-E.

B1-E is a **diagnostic experiment**.

---

# Part II — Three information states

## 3. Oracle semantic flat baseline

Define:

\[
B_{\rm sem}
\]

as the post-hoc semantic flat reference that knows which exact Site actions belong to \(D_{B1}\).

This baseline is valid for:

- B1-O logical-potential analysis;
- correctness/reference comparison.

It is **not** a deployable online work baseline because semantic membership may itself require exact trip-conditioned evaluation.

Do not use it as the sole denominator for deployable work claims.

---

## 4. Deployable flat baseline

Define:

\[
\boxed{
B_{\rm flat}^{D}
}
\]

as a flat algorithm with exactly the same online information available to B1-D before Site evaluation.

For each case:

### `energy_only`

Enumerate every Site in the static:

\[
Ccap
\]

root bucket.

### `energy_and_scheduled`

Enumerate every Site in:

\[
S0cap\cup SCcap.
\]

For every candidate, execute the same concrete evaluation pipeline used at B1-D leaves:

1. exact envelope check;
2. exact concrete Site evaluation if the envelope passes;
3. exact performed-effect classification;
4. semantic-domain acceptance/rejection;
5. incumbent/tie comparison if semantic.

The flat deployable baseline must not use:

- Region lower bounds;
- hierarchy pruning;
- B1-O oracle role tables;
- post-hoc semantic membership;
- precomputed exact per-Site costs.

It may use the same shared OD routing state that the hierarchy uses, provided that shared work is accounted identically.

This is the primary **deployable work comparator**.

---

## 5. Deployable hierarchy

Define:

\[
B_{\rm hier}^{D}
\]

as the already frozen B1-D v1 search.

No B1-E algorithm modification is permitted.

---

# Part III — Work vector

## 6. No single synthetic operation count

A Region lower-bound evaluation, an exact envelope check, and a concrete Site evaluator call have different computational costs.

Therefore B1-E does not collapse them into an arbitrary weighted scalar.

For every case report:

\[
\boxed{
W=
(
N_{\rm region},
N_{\rm bound},
N_{\rm envelope},
N_{\rm exact},
N_{\rm semantic},
T_{\rm bound},
T_{\rm envelope},
T_{\rm exact},
T_{\rm search},
T_{\rm e2e}
).
}
\]

Where:

- \(N_{\rm region}\): Region/bucket nodes created or processed;
- \(N_{\rm bound}\): deployable Region bound evaluations;
- \(N_{\rm envelope}\): exact Site envelope checks;
- \(N_{\rm exact}\): concrete Site evaluator calls;
- \(N_{\rm semantic}\): exact evaluated actions accepted into \(D_{B1}\);
- corresponding \(T\) values are isolated wall-clock components when reliably measurable.

Report \(W\) separately for:

\[
B_{\rm flat}^{D}
\quad\text{and}\quad
B_{\rm hier}^{D}.
\]

Do not invent a weighted “equivalent Site evaluation” score.

---

## 7. Componentwise reductions

Where the flat denominator is positive, report:

\[
R_{\rm envelope}
=
1-
\frac{
N_{\rm envelope,hier}
}{
N_{\rm envelope,flat}
},
\]

\[
R_{\rm exact}
=
1-
\frac{
N_{\rm exact,hier}
}{
N_{\rm exact,flat}
}.
\]

For all-case micro totals:

\[
R_{\rm envelope}^{micro}
=
1-
\frac{
\sum_c N_{\rm envelope,hier}(c)
}{
\sum_c N_{\rm envelope,flat}(c)
},
\]

\[
R_{\rm exact}^{micro}
=
1-
\frac{
\sum_c N_{\rm exact,hier}(c)
}{
\sum_c N_{\rm exact,flat}(c)
}.
\]

These are descriptive diagnostics.

B1-E does not create a post-hoc confirmatory success threshold from these already observed development cases.

---

# Part IV — Perfect-static diagnostic bound

## 8. Purpose

The B1-D deployable bound uses landmark lower bounds:

\[
\underline T^-_{\rm ALT},
\quad
\underline T^+_{\rm ALT},
\quad
\underline D^-_{\rm ALT},
\quad
\underline D^+_{\rm ALT}.
\]

To isolate landmark approximation error, B1-E defines an **offline diagnostic bound** using the exact static-bucket minima.

This bound is not deployable and must never enter the online search.

---

## 9. Exact static-bucket metric minima

For a query and static Region bucket \(A\), define:

\[
T_A^{-,*}
=
\min_{s\in A}d_T(o,s),
\]

\[
T_A^{+,*}
=
\min_{s\in A}d_T(s,z),
\]

\[
D_A^{-,*}
=
\min_{s\in A}d_D(o,s),
\]

\[
D_A^{+,*}
=
\min_{s\in A}d_D(s,z).
\]

These minima may come from different Sites.

They therefore preserve the same Frankenstein relaxation structure as B1-D.

They differ from B1-D only by replacing landmark estimates with exact static-bucket metric minima.

---

## 10. Perfect-static cost bound

Use exactly the same B1-D physics formulas, but substitute:

\[
\underline T^\pm
\leftarrow
T_A^{\pm,*},
\]

\[
\underline D^\pm
\leftarrow
D_A^{\pm,*}.
\]

This yields raw perfect-static bounds:

\[
L^{PS,raw}_C,
\qquad
L^{PS,raw}_{S0},
\qquad
L^{PS,raw}_{SC}.
\]

Use the same:

- envelope logic;
- energy logic;
- schedule logic;
- \(P_{\max}\);
- overhead;
- nuisance cost;
- numerical safety convention.

No other strengthening is allowed.

---

## 11. Monotone normalization

B1-D may enforce parent monotonicity.

To compare like with like, recursively define:

\[
L^{ALT}(N)
=
\max
\{
L^{ALT,raw}(N),
L^{ALT}(parent(N))
\},
\]

and:

\[
L^{PS}(N)
=
\max
\{
L^{PS,raw}(N),
L^{PS}(parent(N))
\}.
\]

At the root, each equals its raw value.

Because exact static minima dominate admissible landmark lower bounds componentwise and the cost formulas are monotone:

\[
\boxed{
L^{PS}(N)\ge L^{ALT}(N)
}
\]

up to the declared conservative numerical tolerance.

Required audit violations:

\[
0.
\]

---

# Part V — Clean certificate decomposition

## 12. Landmark gap

Define:

\[
\boxed{
G_{\rm landmark}(N)
=
L^{PS}(N)-L^{ALT}(N).
}
\]

Expected:

\[
G_{\rm landmark}\ge0
\]

within numerical tolerance.

This isolates the loss due to the 8-landmark approximation and its finite/infinite term availability.

---

## 13. Residual static-relaxation gap

For a Region bucket containing at least one B1 semantic concrete action, let:

\[
J_{\rm sem}^*(N)
=
\min_{a\in N\cap D_{B1}}J(a).
\]

Define:

\[
\boxed{
G_{\rm residual}(N)
=
J_{\rm sem}^*(N)-L^{PS}(N).
}
\]

Because \(L^{PS}\) remains an admissible lower bound:

\[
G_{\rm residual}\ge0.
\]

This residual includes all looseness that remains even if static travel-time and shortest-distance minima are known exactly.

It may include:

- static bucket false positives;
- different Sites supplying different component minima;
- use of \(d_D\) rather than selected-fastest-route actual length;
- optimistic \(P_{\max}\);
- other one-stop relaxation effects.

B1-E does not yet force an artificial further decomposition unless it is mathematically exact.

---

## 14. Total deployable slack identity

For every semantic-populated audited node:

\[
\boxed{
J_{\rm sem}^*(N)-L^{ALT}(N)
=
G_{\rm residual}(N)
+
G_{\rm landmark}(N).
}
\]

Audit this identity numerically.

This is the primary B1-E certificate decomposition.

---

## 15. Relation to old \(G_{\rm cert}\)

The previous B1-D report defined a signed comparison:

\[
G_{\rm cert}^{old}
=
L_{\rm oracle}-L_{\rm deploy}.
\]

Retain that historical quantity unchanged.

Do not overwrite or reinterpret it.

B1-E's new decomposition is preferred for diagnosis because it uses one common semantic target:

\[
J_{\rm sem}^*.
\]

This avoids ambiguity from comparing bounds built over different role/bucket abstractions.

---

# Part VI — Diagnostic counterfactual pruning

## 16. Perfect-static search replay

Run an **offline counterfactual replay** of the same frozen hierarchy using:

\[
L^{PS}
\]

instead of the 8-landmark deployable bound.

All other rules remain identical:

- same hierarchy;
- same static buckets;
- same leaf evaluation;
- same zero-stop incumbent;
- same best-bound ordering rule, with deterministic tie handling;
- same semantic incumbent restrictions;
- same \(\epsilon=0\).

This replay is explicitly oracle/diagnostic because computing exact static minima scans bucket Sites.

Do not count its runtime as deployable.

Its purpose is to answer:

\[
\boxed{
\text{How much work would remain if landmark approximation were perfect?}
}
\]

---

## 17. Three search levels

Compare:

1. **B1-O semantic oracle hierarchy**
   — previous logical-potential result.

2. **B1-E perfect-static hierarchy**
   — exact static metric minima, same static buckets and physics relaxation.

3. **B1-D ALT8 deployable hierarchy**
   — actual deployable v1.

Report, for the same metric-defined case population where applicable:

- leaf candidate checks;
- exact evaluator calls;
- Region refinements;
- depth reached;
- pruning reasons.

Do not call level 2 deployable.

---

# Part VII — Leaf false-positive decomposition

## 18. Population

A leaf static candidate is a false positive if B1-D pays candidate-check work for it but it does not become a semantic B1 Site action.

Every paid reached-leaf candidate must be assigned to exactly one terminal category.

---

## 19. Ordered mutually exclusive categories

Use the following precedence.

### FP1 — envelope reject

The exact Site violates the current Safe Detour Envelope.

### FP2 — inbound-energy infeasible

The exact Site cannot be reached without violating the execution floor before charging.

### FP3 — outbound/total-energy infeasible

The Site passes inbound reachability but exact energy feasibility fails later:

- charger branch cannot satisfy terminal reserve/capacity; or
- noncharger total-energy requirement fails.

### FP4 — schedule infeasible

Energy and envelope conditions pass sufficiently to reach the schedule test, but the hard scheduled requirement cannot be satisfied.

### FP5 — other concrete infeasible

The exact evaluator rejects for another declared reason.

### FP6 — feasible but effect-free

The concrete plan is feasible in the broader via-Site sense but:

\[
\operatorname{Effect}(a_s,\ell)=\varnothing.
\]

It is therefore outside \(D_{B1}\).

### TP — semantic action

The concrete Site action belongs to \(D_{B1}\).

Every paid leaf candidate must appear in exactly one category.

The sum must equal total reached-leaf candidate checks.

---

## 20. False-positive reports

Report counts and fractions by:

- static bucket;
- scenario;
- SOC;
- envelope ratio;
- OD;
- hierarchy depth / leaf depth where meaningful.

In particular report:

\[
FP_{\rm envelope},
\quad
FP_{\rm energy},
\quad
FP_{\rm schedule},
\quad
FP_{\rm no-effect}.
\]

Where:

\[
FP_{\rm energy}=FP2+FP3.
\]

Do not merge these categories in the primary diagnostic table.

---

# Part VIII — Incumbent acquisition diagnosis

## 21. Why incumbent timing matters

A valid lower bound cannot prune until a useful finite incumbent exists.

For each case record:

- whether zero-stop initializes \(U\);
- number of Region pops before first finite Site incumbent;
- number of leaf candidates checked before first finite Site incumbent;
- first incumbent cost;
- final incumbent cost;
- time to first incumbent;
- fraction of total refinement performed before first incumbent.

This is diagnostic only.

Do not add representative witnesses or heuristic UB seeding in B1-E.

---

# Part IX — Decision interpretation

## 22. No post-hoc pass/fail reclassification

B1-E must preserve both historical results:

\[
\boxed{
\text{B1-O strong GO}
}
\]

and:

\[
\boxed{
\text{B1-D v1 deployable gate failed}.
}
\]

B1-E does not replace either statement with a new confirmatory classification.

Its output is a structural diagnosis.

---

## 23. Diagnostic interpretation matrix

Use the evidence as follows.

### Case A — large \(G_{\rm landmark}\), small \(G_{\rm residual}\)

Primary bottleneck:

\[
\boxed{\text{deployable metric approximation}}
\]

Candidate next research direction:

- stronger road-cell/boundary summaries;
- improved landmark architecture;
- other proven metric lower bounds.

Do not redesign static action semantics first.

### Case B — small \(G_{\rm landmark}\), large \(G_{\rm residual}\)

Primary bottleneck:

\[
\boxed{\text{static relaxation / action abstraction}}
\]

Candidate next research direction:

- stronger state-dependent proven filters;
- tighter charging/resource relaxation;
- reduction of static false positives.

Do not merely add landmarks.

### Case C — both large

Both certificate approximation and abstraction are limiting.

A staged B1-D2 design is required.

### Case D — both modest, but online work remains high

Investigate:

- incumbent acquisition;
- tree geometry;
- cost distribution across Region refinement.

Only here should hierarchy redesign become a serious hypothesis.

---

# Part X — Evidence discipline

## 24. Development data only

All 480 cases remain development data.

B1-E is explicitly post-hoc diagnostic analysis of B1-D v1.

Therefore:

- do not invent a new numerical success threshold from these results;
- do not claim confirmatory validation;
- do not call a favorable deployable-flat comparison a retroactive B1-D pass;
- do not use B1-E to establish final Revised Go-1.

Any future redesigned B1-D2 algorithm must be versioned as a new design.

Its evaluation threshold must be frozen before its comparative results are observed.

---

# Part XI — Required outputs

## 25. Baseline outputs

Produce:

- deployable-flat per-case work table;
- deployable-hierarchy per-case work table;
- componentwise workload comparison;
- clean timing comparison if reproducible;
- all-case micro totals.

## 26. Certificate outputs

Produce:

- exact static-bucket minima table for audited/visited nodes;
- \(L^{ALT}\);
- \(L^{PS}\);
- \(J_{\rm sem}^*\);
- \(G_{\rm landmark}\);
- \(G_{\rm residual}\);
- identity audit for:
  \[
  J_{\rm sem}^*-L^{ALT}
  =
  G_{\rm landmark}+G_{\rm residual}.
  \]

## 27. Counterfactual search outputs

Produce:

- perfect-static search traces;
- B1-O / perfect-static / ALT8 work comparison;
- depth and bucket stratification.

## 28. False-positive outputs

Produce:

- mutually exclusive leaf-candidate classification;
- aggregate and stratified false-positive tables;
- exact reconciliation with total paid candidate checks.

## 29. Incumbent outputs

Produce:

- per-case incumbent-acquisition diagnostics;
- aggregate stratification.

---

# Part XII — Correctness/audit gates

## E1 — Fair baseline equivalence

The deployable-flat and deployable-hierarchy leaf routines must use the same:

- exact envelope logic;
- exact Site evaluator;
- semantic-effect rule;
- tie rule;
- shared routing state.

Required discrepancies:

\[
0.
\]

## E2 — Perfect-static bound admissibility

For every audited semantic-populated Region bucket:

\[
L^{PS}(N)\le J_{\rm sem}^*(N).
\]

Required violations:

\[
0.
\]

## E3 — Landmark decomposition order

For every audited node:

\[
L^{ALT}(N)\le L^{PS}(N)
\]

within conservative tolerance.

Required violations:

\[
0.
\]

## E4 — Decomposition identity

For every semantic-populated audited node:

\[
J_{\rm sem}^*-L^{ALT}
=
G_{\rm landmark}+G_{\rm residual}
\]

within declared numerical tolerance.

Required violations:

\[
0.
\]

## E5 — False-positive reconciliation

Every reached-leaf candidate belongs to exactly one FP/TP category and counts reconcile exactly.

Required discrepancies:

\[
0.
\]

## E6 — No algorithm mutation

Hashes/configs for hierarchy, landmarks, deployable bound code/config, and primary B1-D result inputs must match the frozen v1 run except for explicitly new diagnostic code/artifacts.

Required unauthorized changes:

\[
0.
\]

---

# Part XIII — Stop rule

B1-E ends after diagnosis.

Do not:

- add landmarks;
- add boundary summaries;
- alter static buckets;
- change hierarchy;
- run B2;
- build a China benchmark;
- run holdout cases;
- claim final deployability.

The final report must recommend the **next hypothesis to test**, but must not implement it.

---

# Part XIV — Final report language

The report must retain these statements exactly in substance:

1. B1-O showed strong oracle pruning potential.
2. B1-D v1 was exact and deployable in the sense of no online Region scans.
3. B1-D v1 failed its preregistered semantic-denominator workload gate.
4. That historical failure is not retroactively reversed.
5. B1-E evaluates whether that gate failure reflects:
   - an unfair deployable comparator,
   - landmark looseness,
   - residual static relaxation,
   - leaf false positives,
   - incumbent delay,
   - or hierarchy structure.

The final B1-E output is a diagnosis, not a new GO/NO-GO verdict.

---

# Part XV — Expected next-stage decision

After B1-E, choose exactly one of the following based on the evidence:

\[
\boxed{
\text{B1-D2 stronger deployable bounds}
}
\]

or

\[
\boxed{
\text{B1-D2 stronger state-dependent action filters}
}
\]

or

\[
\boxed{
\text{hierarchy redesign study}
}
\]

or, only if the current hierarchy is already descriptively adequate against the fair deployable baseline and remaining looseness is not structurally important,

\[
\boxed{
\text{freeze one-stop method and advance to B2 under a new preregistered multi-stop protocol}.
}
\]

No choice is made in advance by this specification.
