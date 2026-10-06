# Milestone 4R-B1D Formal Specification

**Project:** dy-HiRoute  
**Stage:** Milestone 4R-B1D — Deployable Region Bounds  
**Status:** theory candidate after B1-O correctness and oracle-potential validation  
**Normative predecessors:** `RESEARCH_SPEC_v0.2.md`, `MILESTONE_4R_B0_FORMAL_SPEC.md`, B1 action-domain amendment, accepted B1 H0–H5 results  
**Implementation authorization:** none — this document freezes the deployable-bound theory before a Codex implementation prompt.

---

# 0. Purpose

B1-O established that a static Region hierarchy can preserve the exact one-stop optimum and can have strong **logical** pruning potential when exact trip-conditioned per-Site information is already available.

B1-D asks a different question:

\[
\boxed{
\textbf{Can the same hierarchy prune safely using Region bounds that do not scan/evaluate all Sites online?}
}
\]

The primary correction relative to earlier thinking is:

\[
\boxed{
\textbf{B1-D does not require a cheap RCC in order to prune.}
}
\]

A deployable exact branch-and-bound search needs:

1. coverage of every semantic concrete action by a Region branch;
2. an admissible Region lower bound;
3. a verified concrete incumbent;
4. exact concrete evaluation at leaves.

RCCs are required only if a coarse Region is to be directly concretized without refinement. B1-D v1 does not require that operation.

---

# Part I — Declared B1-D domain

## 1. Search domain

B1-D uses the same amended semantic one-stop domain \(D_{B1}\) validated by H0–H5.

The semantic domain contains:

\[
\mathcal A_{B1}(\ell)
=
\{a_0\}
\cup
\{a_s:\operatorname{Effect}(a_s,\ell)\neq\varnothing\},
\]

where current modeled stop effects are:

\[
\{C,S\}.
\]

- \(C\): the concrete stop actually adds positive charging energy;
- \(S\): the concrete stop actually satisfies the active scheduled-stop requirement.

No neutral role is introduced.

The no-stop action \(a_0\) is handled separately.

The flat/leaf concrete evaluator, routing semantics, objective, charging model, support predicate, and numerical tolerances remain those of accepted 4R-A/B1.

---

## 2. Primary B1-D assumptions

The primary proof domain assumes:

- directed road graph \(G=(V,E)\);
- nonnegative travel-time edge weights;
- nonnegative physical edge lengths;
- selected fastest-time route operator \(\pi_T(u,v)\);
- actual length of the selected fastest-time route \(L_T(u,v)\);
- deterministic distance-proportional energy:
  \[
  E_{\rm drive}=\kappa L;
  \]
- fixed battery capacity \(E_{\max}\);
- execution floor \(E_{\min}\);
- destination reserve \(E_{\rm res}\);
- fixed stop overhead \(h\);
- fixed stop nuisance cost \(\lambda_{\rm stop}\);
- hard scheduled-start window \([a,b]\);
- fixed scheduled duration \(D\);
- charging and scheduled activity are compatible at the same anchor;
- charging curve has a global finite upper power bound
  \[
  P(E)\le P_{\max};
  \]
- primary distance penalty is zero.

The current canonical experiment has \(P_{\max}=100\) kW, but the proofs use only the abstract upper bound.

---

# Part II — Static capability supersets

## 3. Why performed roles are not required at internal Regions

Performed effects are trip-conditioned and may require exact Site evaluation.

B1-D therefore does not attempt to know exact `C/S/CS` performed roles before reaching a leaf.

Instead, internal nodes use **static capability/support supersets**.

A superset may contain false positives.

False positives may increase search work but must not remove any semantic action.

Only an exact semantic concrete action may update the incumbent.

---

## 4. Static bucket definitions

For a Region \(R\), define the following static buckets.

### 4.1 Energy-only charger bucket

\[
R_{\mathrm{Ccap}}
=
\{s\in R:\;s\text{ has accepted charging capability}\}.
\]

Any semantic energy-only one-stop action with performed effect \(C\) must belong to this bucket.

A charger in this bucket may later evaluate to zero added charge; such a Site is an internal false positive and is discarded at exact leaf evaluation.

### 4.2 Scheduled noncharger bucket

\[
R_{\mathrm{S0cap}}
=
\{s\in R:\;Sat_{\rm sched}(s)=1,\;s\text{ has no charging capability}\}.
\]

### 4.3 Scheduled charger-capable bucket

\[
R_{\mathrm{SCcap}}
=
\{s\in R:\;Sat_{\rm sched}(s)=1,\;s\text{ has charging capability}\}.
\]

Here \(Sat_{\rm sched}\) is the accepted static support predicate, e.g. `meal_count >= 1` in the primary B1 domain.

These two scheduled buckets are disjoint.

---

## Proposition 1 — Superset coverage

For the primary B1 scenarios:

### Energy-only

Every semantic one-stop action is contained in \(R_{\mathrm{Ccap}}\).

### Energy-and-scheduled

Every semantic one-stop action is contained in exactly one of:

\[
R_{\mathrm{S0cap}},
\qquad
R_{\mathrm{SCcap}}.
\]

### Proof

In an energy-only case, a semantic Site stop must have nonempty effect set. The only available effect is \(C\), which requires a concrete charging-capable Site.

In an energy-and-scheduled case, the scheduled requirement is hard. Therefore every feasible semantic one-stop action must satisfy the accepted scheduled-support predicate. A Site either has charging capability or it does not, placing it in exactly one of the two scheduled buckets. ∎

### Consequence

Internal-node classification need not know whether a charger will actually add charge.

\[
\boxed{
\text{static superset first, exact performed-effect classification at the leaf.}
}
\]

---

# Part III — Two road metrics

## 5. Travel-time metric

Let

\[
d_T(u,v)
\]

be the directed shortest-travel-time distance.

This is a directed shortest-path metric and satisfies directed triangle inequality whenever the relevant distances are finite.

---

## 6. Physical-distance metric

Let

\[
d_D(u,v)
\]

be the directed shortest physical road-distance using the **same legal directed edge set** but edge length as the objective.

For every reachable pair,

\[
\boxed{
d_D(u,v)\le L_T(u,v).
}
\]

### Proof

The selected fastest-time route \(\pi_T(u,v)\) is one legal directed \(u\to v\) path. \(d_D(u,v)\) is the minimum length over all legal directed \(u\to v\) paths, so it cannot exceed the length of \(\pi_T(u,v)\). ∎

### Important distinction

B1-D does **not** assume \(L_T\) is a metric.

It uses \(d_D\le L_T\) only as a one-sided lower-bound relation.

This is sufficient for energy lower bounds.

---

# Part IV — Deployable point-to-Region landmark bounds

## 7. Landmark summaries

Choose a fixed query-independent landmark set

\[
\Lambda\subseteq V.
\]

For a directed metric \(d\), a Region bucket \(A\subseteq R\), and each landmark \(\lambda\), store:

\[
m_{\lambda A}
=
\min_{s\in A}d(\lambda,s),
\]

\[
M_{\lambda A}
=
\max_{s\in A}d(\lambda,s),
\]

\[
m_{A\lambda}
=
\min_{s\in A}d(s,\lambda),
\]

\[
M_{A\lambda}
=
\max_{s\in A}d(s,\lambda).
\]

These summaries are static with respect to OD, SOC, schedule, envelope, and preference.

Separate summary tables are maintained for \(d_T\), \(d_D\), and each static bucket.

---

## 8. Infinite/unreachable distances

Expressions containing undefined forms such as \(+\infty-(+\infty)\) must never be evaluated.

A landmark-derived term is used only when all operands required by that term are finite.

If no valid landmark term exists, the corresponding lower bound falls back to 0.

This is safe but may be loose.

Reachability-specific strengthening is deferred; it is not required for B1-D v1 correctness.

---

## Theorem 2 — Directed point-to-Region lower bound

For current point \(x\) and Region bucket \(A\),

\[
\boxed{
\underline d(x,A)
=
\max_{\lambda\in\Lambda}
\left\{
0,\;
m_{\lambda A}-d(\lambda,x),\;
d(x,\lambda)-M_{A\lambda}
\right\},
}
\]

using only finite valid terms.

Then:

\[
\underline d(x,A)
\le
\min_{s\in A}d(x,s).
\]

### Proof

Directed triangle inequality gives:

\[
d(\lambda,s)
\le
d(\lambda,x)+d(x,s),
\]

so

\[
d(\lambda,s)-d(\lambda,x)
\le
d(x,s).
\]

Taking the minimum over \(s\in A\),

\[
m_{\lambda A}-d(\lambda,x)
\le
\min_{s\in A}d(x,s).
\]

Also,

\[
d(x,\lambda)
\le
d(x,s)+d(s,\lambda),
\]

hence

\[
d(x,\lambda)-d(s,\lambda)
\le
d(x,s).
\]

Since \(M_{A\lambda}\ge d(s,\lambda)\) for every \(s\),

\[
d(x,\lambda)-M_{A\lambda}
\le
d(x,s)
\]

for every \(s\), and therefore it lower-bounds the set minimum. Taking the maximum of valid lower bounds preserves validity. ∎

---

## Theorem 3 — Directed Region-to-point lower bound

For Region bucket \(A\) and destination \(z\),

\[
\boxed{
\underline d(A,z)
=
\max_{\lambda\in\Lambda}
\left\{
0,\;
d(\lambda,z)-M_{\lambda A},\;
m_{A\lambda}-d(z,\lambda)
\right\},
}
\]

again using only finite valid terms.

Then:

\[
\underline d(A,z)
\le
\min_{s\in A}d(s,z).
\]

### Proof

From:

\[
d(\lambda,z)
\le
d(\lambda,s)+d(s,z),
\]

we obtain:

\[
d(\lambda,z)-d(\lambda,s)
\le
d(s,z).
\]

Using the maximum \(M_{\lambda A}\) makes the left side no larger for any \(s\).

Similarly:

\[
d(s,\lambda)
\le
d(s,z)+d(z,\lambda),
\]

so:

\[
d(s,\lambda)-d(z,\lambda)
\le
d(s,z).
\]

Taking the minimum \(m_{A\lambda}\) preserves a lower bound on the set minimum. ∎

---

## 9. Time and distance Region bounds

Apply Theorems 2–3 under \(d_T\):

\[
\underline T^-(A)
=
\underline d_T(o,A),
\]

\[
\underline T^+(A)
=
\underline d_T(A,z).
\]

Apply them independently under \(d_D\):

\[
\underline D^-(A)
=
\underline d_D(o,A),
\]

\[
\underline D^+(A)
=
\underline d_D(A,z).
\]

For every concrete Site \(s\in A\),

\[
T^-_s\ge\underline T^-,
\qquad
T^+_s\ge\underline T^+,
\]

and

\[
L^-_s
\ge
d_D(o,s)
\ge
\underline D^-,
\]

\[
L^+_s
\ge
d_D(s,z)
\ge
\underline D^+.
\]

---

# Part V — Safe Region-level infeasibility checks

## 10. Envelope infeasibility

The exact Site envelope rule is based on travel time:

\[
T^-_s+T^+_s\le B.
\]

If:

\[
\boxed{
\underline T^-+\underline T^+>B,
}
\]

then every Site in the bucket violates the envelope.

Thus the whole Region bucket is safely discarded.

Failure of this test does not prove any Site is envelope-eligible.

---

## 11. Inbound energy infeasibility

Before the first stop, no charging is available.

If:

\[
\boxed{
E_0-\kappa\underline D^-<E_{\min},
}
\]

then every concrete Site in the bucket is unreachable before violating the execution floor.

The Region bucket is safely infeasible.

---

## 12. Charger outbound infeasibility

For charger-capable buckets, even a full battery cannot rescue a Region if:

\[
\boxed{
E_{\max}-\kappa\underline D^+<E_{\rm res}.
}
\]

Then every concrete Site in the bucket is unable to reach the destination with the required terminal reserve.

---

## 13. Noncharging total-energy infeasibility

For the scheduled noncharger bucket, if:

\[
\boxed{
E_0-\kappa(\underline D^-+\underline D^+)<E_{\rm res},
}
\]

then no concrete noncharging one-stop action in the bucket can satisfy the terminal reserve.

---

## 14. Hard scheduled-window infeasibility

Let:

\[
\underline r
=
t_0+\underline T^-+h,
\]

\[
\underline y
=
\max(a,\underline r).
\]

If:

\[
\boxed{
\underline y>b,
}
\]

then no concrete Site in the scheduled bucket can start the activity within the hard window.

---

# Part VI — Energy and charging lower bounds

## Lemma 4 — Required charging-energy lower bound

For a charger-capable bucket define:

\[
\boxed{
\underline q
=
\left[
E_{\rm res}
+
\kappa(\underline D^-+\underline D^+)
-
E_0
\right]_+.
}
\]

Then for every concrete Site \(s\) in the bucket whose plan charges:

\[
q_s\ge\underline q.
\]

### Proof

For every concrete Site:

\[
L^-_s+L^+_s
\ge
\underline D^-+\underline D^+.
\]

The minimum charge required to finish with reserve is:

\[
q_s
=
\left[
E_{\rm res}
+
\kappa(L^-_s+L^+_s)
-
E_0
\right]_+.
\]

The positive-part function is monotone. ∎

---

## Lemma 5 — Charging-time lower bound

Assume:

\[
P(E)\le P_{\max}
\]

throughout the modeled charging domain.

Then charging \(\underline q\) kWh requires at least:

\[
\boxed{
\underline C
=
3600\frac{\underline q}{P_{\max}}
}
\]

seconds.

For every concrete charging plan:

\[
C_s\ge\underline C.
\]

### Proof

Instantaneous charging rate never exceeds \(P_{\max}\). Delivering \(q\) kWh therefore requires at least \(q/P_{\max}\) hours. Since \(q_s\ge\underline q\), the stated lower bound follows. ∎

---

# Part VII — Deployable one-stop Region cost bounds

## 15. Energy-only charger branch

For bucket \(A=R_{\mathrm{Ccap}}\), define:

\[
\boxed{
L_C(A)
=
\underline T^-
+
h
+
\underline C
+
\underline T^+
+
\lambda_{\rm stop}.
}
\]

## Theorem 6 — Admissibility of \(L_C\)

For every semantic concrete energy-only charging action \(s\in A\),

\[
L_C(A)\le J_s.
\]

This follows by componentwise lower bounds on inbound time, charging time, outbound time, with exact fixed overhead and nuisance cost. ∎

---

## 16. Scheduled noncharger branch

For \(A=R_{\mathrm{S0cap}}\), define:

\[
\underline y
=
\max(a,t_0+\underline T^-+h).
\]

When \(\underline y\le b\), define:

\[
\boxed{
L_{S0}(A)
=
(\underline y+D-t_0)
+
\underline T^+
+
\lambda_{\rm stop}.
}
\]

## Theorem 7 — Admissibility of \(L_{S0}\)

For every feasible concrete scheduled noncharging action \(s\in A\),

\[
L_{S0}(A)\le J_s.
\]

Concrete scheduled start is \(y_s=\max(a,t_0+T^-_s+h)\). Since \(T^-_s\ge\underline T^-\) and `max` is monotone, \(y_s\ge\underline y\). Outbound time is likewise no smaller than \(\underline T^+\). ∎

---

## 17. Scheduled charger-capable branch

For \(A=R_{\mathrm{SCcap}}\), define:

\[
\underline r
=
t_0+\underline T^-+h.
\]

Define the relaxed stop-completion lower bound:

\[
\boxed{
\underline c
=
\max\{
\underline r+\underline C,\;
\max(a,\underline r)+D
\}.
}
\]

Equivalently:

\[
\underline c
=
\max\{
\underline r+\underline C,\;
a+D,\;
\underline r+D
\}.
\]

Then define:

\[
\boxed{
L_{SC}(A)
=
(\underline c-t_0)
+
\underline T^+
+
\lambda_{\rm stop}.
}
\]

## Theorem 8 — Admissibility of \(L_{SC}\)

For every feasible semantic scheduled action at a charger-capable Site \(s\in A\), whether its performed effect is \(S\) or \(CS\),

\[
L_{SC}(A)\le J_s.
\]

Concrete stop completion is:

\[
c_s
=
\max\{
r_s+C_s,\;
\max(a,r_s)+D
\},
\]

with \(r_s=t_0+T^-_s+h\).

Every concrete term is no smaller than the corresponding relaxed term, so monotonicity of `max` proves the claim. ∎

---

# Part VIII — Branch-and-bound without RCC

## 18. Search node

A deployable search node is:

\[
N=(R,\beta,\ell),
\]

where \(\beta\) is a static superset bucket, not a performed role.

For the primary scenarios:

\[
\beta\in
\{
\mathrm{Ccap},
\mathrm{S0cap},
\mathrm{SCcap}
\}.
\]

---

## 19. Internal-node processing

For a nonempty Region bucket:

1. compute Region lower bounds from precomputed summaries;
2. apply safe Region-level infeasibility checks;
3. compute the appropriate admissible cost bound;
4. if:
   \[
   L(N)\ge U-\epsilon,
   \]
   prune;
5. otherwise refine to children, or exact-evaluate concrete Sites if the node is a leaf.

B1-D v1 does not directly concretize an internal Region.

Therefore a dynamic RCC is not required for search correctness.

---

## 20. Exact leaf semantics

At a leaf:

- perform exact envelope check;
- perform the unchanged accepted concrete Site evaluation;
- determine actual performed effects;
- discard static-superset false positives;
- only a concrete semantic action in \(D_{B1}\) may update the incumbent.

A charger-capable energy-only Site that evaluates to zero added charge must not update \(U\).

---

## Theorem 9 — Exactness with static supersets

Assume:

1. every B1 semantic Site action is contained in at least one root static bucket;
2. child refinement preserves the static bucket's Site-ID coverage;
3. every internal cost bound is admissible for every semantic action represented by that node;
4. only exact B1 semantic actions update the incumbent;
5. leaves exact-evaluate all unpruned candidate Sites;
6. pruning uses:
   \[
   L(N)\ge U-\epsilon.
   \]

Then termination certifies:

\[
\boxed{
U-J_{B1}^*\le\epsilon.
}
\]

At \(\epsilon=0\), the search returns the exact B1 semantic-domain optimum. ∎

---

# Part IX — Bound ladder and monotonicity

## 21. Optional cheap \(L_0\)

B1-D may use an even cheaper first-stage lower bound only if its admissibility is separately proven.

No heuristic geometric estimate may be used for pruning without proof.

## 22. Landmark \(L_1\)

The primary deployable bound family is:

\[
\boxed{
L_1=
\text{set-valued landmark time bound}
+
\text{set-valued landmark distance/energy bound}
+
\text{optimistic charging/schedule physics}.
}
\]

A node not pruned by \(L_1\) is refined.

Exact per-Site evaluation occurs only at leaves.

## 23. Bound monotonicity

For numerical robustness one may enforce:

\[
\boxed{
L_{\rm child}
\leftarrow
\max\{
L_{\rm child}^{raw},
L_{\rm parent}
\}.
}
\]

Because the parent lower bound also lower-bounds every child semantic action, this preserves admissibility.

---

# Part X — Query complexity and accounting

## 24. No online Region scan

A B1-D internal bound is deployable only if it is evaluated from Region metadata, precomputed bucket summaries, landmark summaries, and current query/state parameters.

It must not enumerate every Site in the Region at query time.

A full Region scan followed by a summary is oracle work, not deployable work.

## 25. Preprocessing is not free

Report separately:

- landmark selection/build time;
- time- and distance-metric shortest-path preprocessing;
- Region×bucket summary construction;
- storage size;
- peak memory;
- query-time bound operations.

## 26. Shared routing work

Any routing arrays/computations required equally by flat and hierarchical methods receive zero hierarchy savings credit.

Additional landmark/query work required only by B1-D is hierarchy cost.

---

# Part XI — Zero-semantic denominator clarification

## 27. Case-level reduction metric

For:

\[
N_{\rm semantic,flat}>0,
\]

define:

\[
r_c
=
1-
\frac{N_{\rm semantic,hier}}
{N_{\rm semantic,flat}}.
\]

If:

\[
N_{\rm semantic,flat}=0,
\]

then:

\[
\boxed{
r_c=\mathrm{NA}.
}
\]

Such a case has no Site-evaluation pruning opportunity.

## 28. Classification population

Define:

\[
\mathcal C_+
=
\{
c:N_{\rm semantic,flat}(c)>0
\}.
\]

Macro case-level GO/NO-GO statistics are computed on \(\mathcal C_+\).

All cases remain in correctness, domain, runtime, and zero-stop reporting.

## 29. All-case micro workload reduction

Also report:

\[
\boxed{
R_{\rm micro}
=
1-
\frac{
\sum_c N_{\rm semantic,hier}(c)
}{
\sum_c N_{\rm semantic,flat}(c)
}.
}
\]

Zero-semantic cases contribute zero to both sums.

---

# Part XII — B1-D validation hypotheses

## D1 — Static-superset coverage

Every B1 semantic concrete Site action must be contained in the correct static bucket path from root to leaf.

Required violations:

\[
0.
\]

## D2 — Landmark lower-bound validity

For every audited Region bucket and query:

\[
\underline T^-
\le
\min_s T^-_s,
\]

\[
\underline T^+
\le
\min_s T^+_s,
\]

\[
\underline D^-
\le
\min_s d_D(o,s),
\]

\[
\underline D^+
\le
\min_s d_D(s,z).
\]

Required violations:

\[
0.
\]

## D3 — Cost-bound validity

For every audited nonempty Region bucket with at least one semantic action:

\[
L_C,\ L_{S0},\ \text{or }L_{SC}
\le
J_{\rm semantic,min}.
\]

Required violations:

\[
0.
\]

False-positive-only static buckets are recorded separately rather than assigned a fabricated semantic minimum.

## D4 — Exact deployable preservation

At:

\[
\epsilon=0,
\]

B1-D must return:

\[
\boxed{
J_{\rm B1D}^*=J_{B1}^*
}
\]

for every development case.

Required mismatches:

\[
0.
\]

## D5 — No hidden full scans

Required:

- zero online full Region scans used to compute deployable bounds;
- zero oracle per-Site objective arrays read by deployable search;
- exact Site evaluation only at reached leaves.

A violation invalidates computational-savings claims.

---

# Part XIII — Existing deployable gate

## 30. Gate remains unchanged

The previously frozen B1-D empirical gate remains:

\[
\operatorname{median}_{c\in\mathcal C_+}
(r_c^{deploy})
\ge
50\%.
\]

And:

\[
\frac{
\operatorname{median}(r^{deploy})
}{
\operatorname{median}(r^{oracle})
}
\ge
0.70.
\]

Timing break-even is applied only if replaced flat work can be isolated reliably.

The zero-denominator clarification changes only the metric domain, not the numerical thresholds.

---

# Part XIV — What failure means

## 31. If D1–D5 fail

This is a correctness/implementation failure.

Do not interpret pruning rates.

## 32. If correctness passes but pruning is weak

Compute:

\[
G_{\rm cert}
=
L_{\rm oracle}-L_{\rm deploy}.
\]

Diagnose whether weakness comes from:

- landmark time bounds;
- shortest-distance energy bounds;
- optimistic \(P_{\max}\) charging bound;
- static superset false positives;
- late incumbent acquisition.

Do not immediately replace the hierarchy.

## 33. If oracle pruning is strong but deployable pruning is weak

The primary diagnosis is:

\[
\boxed{
\text{deployable certificate too loose or too expensive}.
}
\]

This is distinct from Region aggregation failure.

---

# Part XV — Known non-guarantees

B1-D v1 does not establish:

- real multi-stop scalability;
- final Revised Go-1;
- unrestricted route optimality outside the declared envelope/domain;
- dynamic charger occupancy;
- heterogeneous real station charging curves;
- elevation/speed/temperature energy physics;
- a deployable RCC;
- optimal landmark selection;
- optimal Region partitioning;
- final holdout validity.

---

# Part XVI — Formal audit verdict

The following claims survive the B1-D proof audit under the stated assumptions:

\[
\boxed{
\textbf{1. Static capability/support supersets safely replace exact performed-role knowledge at internal nodes.}
}
\]

\[
\boxed{
\textbf{2. Directed set-valued landmark summaries give admissible point-to-Region and Region-to-point lower bounds.}
}
\]

\[
\boxed{
\textbf{3. A shortest-distance metric can safely lower-bound the actual length of the selected fastest-time route without assuming that selected-route length is itself a metric.}
}
\]

\[
\boxed{
\textbf{4. These distance bounds yield safe energy, reachability, and minimum-charge lower bounds.}
}
\]

\[
\boxed{
\textbf{5. Global }P_{\max}\textbf{ yields a safe optimistic charging-time lower bound.}
}
\]

\[
\boxed{
\textbf{6. The }C,\ S0,\ SC\textbf{ Region cost bounds are admissible in the current one-stop domain.}
}
\]

\[
\boxed{
\textbf{7. Exact hierarchical search does not require an RCC if coarse Regions are never directly concretized and exact evaluation is deferred to leaves.}
}
\]

\[
\boxed{
\textbf{8. Static-superset false positives cannot harm correctness provided they never update the incumbent unless exact evaluation proves they are semantic actions.}
}
\]

No principle-level blocker was found in this B1-D v1 construction.

The next stage, if authorized, is a **B1-D implementation prompt** that freezes landmark selection/preprocessing, storage format, instrumentation, and the existing empirical gate before comparative results are observed.
