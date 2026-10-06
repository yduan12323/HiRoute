# Milestone 4R-B1D2 Formal Specification

**Project:** dy-HiRoute  
**Stage:** Milestone 4R-B1D2 — Boundary-Augmented Deployable Metric Bounds  
**Status:** final one-stop algorithmic iteration  
**Normative predecessors:** RESEARCH_SPEC_v0.2, 4R-B0 formal spec, B1 action-domain amendment, B1-D formal spec, B1-E formal spec, accepted B1/B1-D/B1-E reports.

## 0. Non-negotiable progress rule

\[
\boxed{\textbf{B1-D2 is the final algorithmic iteration in the one-stop development phase.}}
\]

After B1-D2, the one-stop method is frozen and the project advances to B2 multi-stop formalization. No B1-D3 may be opened merely for better pruning, better timing, tighter bounds, more landmarks, stronger filters, or better hierarchy geometry. B1 may be reopened only if a **fundamental correctness defect** is found that invalidates a theorem, loses semantic actions, or changes the exact optimum.

This rule prevents indefinite development-set hill climbing.

## 1. Why B1-D2 exists

B1-E showed a mixed certificate bottleneck, with metric approximation as the first intervention to test. Replacing ALT8 time/distance approximations with exact static-bucket metric minima, while freezing hierarchy, buckets, incumbent policy, and resource relaxation, substantially reduced work. The largest paid leaf rejection was exact envelope failure.

B1-D2 therefore changes exactly one primary mechanism:

\[
\boxed{\textbf{the travel-time Region lower bound}}
\]

and freezes everything else.

## 2. Frozen components

B1-D2 must reuse unchanged:

- the accepted 2,047-Region / 1,024-leaf hierarchy;
- Region IDs, memberships, parent/child structure, and leaf capacity;
- all 8 ALT landmarks and all existing landmark arrays;
- the existing shortest-distance \(d_D\) energy bound;
- static `Ccap`, `S0cap`, `SCcap` buckets;
- Safe Detour Envelope;
- charging and schedule models;
- \(P_{\max}\) relaxation;
- incumbent policy;
- exact leaf evaluator;
- B1 semantic action domain;
- deterministic tie rules.

B1-D2 strengthens only:

\[
\underline T^-,
\qquad
\underline T^+.
\]

It does **not** change:

\[
\underline D^-,
\qquad
\underline D^+.
\]

## 3. Directed road-cell boundaries

Let Region \(R\) correspond to static road-node cell:

\[
V_R\subseteq V.
\]

Define directed ingress boundary:

\[
\boxed{
\partial^-R=
\{v\in V_R:\exists (u,v)\in E,\ u\notin V_R\}
}
\]

and directed egress boundary:

\[
\boxed{
\partial^+R=
\{u\in V_R:\exists (u,v)\in E,\ v\notin V_R\}.
}
\]

These use the same accepted directed graph as routing. A node may belong to both boundaries.

## Theorem 1 — Ingress crossing

If \(o\notin V_R\), then for every reachable Site anchor \(s\in V_R\),

\[
\boxed{
d_T(o,s)\ge
\min_{b\in\partial^-R}d_T(o,b).
}
\]

**Proof.** Any directed path from outside \(V_R\) to \(s\in V_R\) has a first in-cell vertex \(b\). Its predecessor lies outside the cell, hence \(b\in\partial^-R\). Reaching \(s\) cannot take less time than reaching that first ingress boundary vertex. Minimizing over ingress vertices preserves a lower bound. ∎

## Theorem 2 — Egress crossing

If \(z\notin V_R\), then for every reachable \(s\in V_R\),

\[
\boxed{
d_T(s,z)\ge
\min_{b\in\partial^+R}d_T(b,z).
}
\]

The proof is symmetric using the last in-cell vertex before leaving \(V_R\). ∎

## 4. Boundary lower bounds

Define:

\[
\delta_R^-(o)=
\begin{cases}
0,&o\in V_R,\\
\min_{b\in\partial^-R}d_T(o,b),&o\notin V_R,
\end{cases}
\]

\[
\delta_R^+(z)=
\begin{cases}
0,&z\in V_R,\\
\min_{b\in\partial^+R}d_T(b,z),&z\notin V_R.
\end{cases}
\]

If the required boundary is empty, or no finite usable boundary term exists, fall back to 0. Do not infer infeasibility from that condition without a separate reachability proof.

## 5. Boundary-augmented time bound

Let the frozen B1-D v1 ALT8 bounds be:

\[
\underline T^-_{\rm ALT},
\qquad
\underline T^+_{\rm ALT}.
\]

Define:

\[
\boxed{
\underline T^-_{\rm BA}
=
\max\{\underline T^-_{\rm ALT},\delta_R^-(o)\}
}
\]

and:

\[
\boxed{
\underline T^+_{\rm BA}
=
\max\{\underline T^+_{\rm ALT},\delta_R^+(z)\}.
}
\]

## Theorem 3 — Admissibility

For every Site \(s\in R\),

\[
\underline T^-_{\rm BA}\le d_T(o,s),
\qquad
\underline T^+_{\rm BA}\le d_T(s,z).
\]

Each term in the max is independently admissible; the max of lower bounds remains a lower bound. ∎

Therefore:

\[
\boxed{
\underline T^\pm_{\rm BA}\ge \underline T^\pm_{\rm ALT}
}
\]

while preserving admissibility.

## 6. Bucket compatibility

For any static bucket \(A\subseteq R\), the same boundary bound remains valid because every Site anchor in \(A\) lies inside \(V_R\). No bucket-specific boundary scan is needed.

## 7. B1-D2 cost bounds

Reuse the B1-D v1 cost formulas unchanged except substitute:

\[
\underline T^-_{\rm ALT}\rightarrow\underline T^-_{\rm BA},
\]

\[
\underline T^+_{\rm ALT}\rightarrow\underline T^+_{\rm BA}.
\]

Distance/energy terms stay frozen:

\[
\underline D^-_{\rm ALT},
\qquad
\underline D^+_{\rm ALT}.
\]

This produces:

\[
L_C^{BA},\qquad L_{S0}^{BA},\qquad L_{SC}^{BA}.
\]

## Theorem 4 — Cost admissibility

Under the same assumptions as B1-D v1:

\[
\boxed{
L^{BA}(N)\le J_{\rm semantic,min}(N).
}
\]

The existing cost formulas are monotone in inbound/outbound time lower bounds, and the substituted BA quantities remain admissible. ∎

## 8. Envelope strengthening

The exact envelope condition is:

\[
d_T(o,s)+d_T(s,z)\le B.
\]

Hence:

\[
\boxed{
\underline T^-_{\rm BA}
+
\underline T^+_{\rm BA}
>B
}
\]

safely proves that no Site in the Region bucket can satisfy the envelope.

This is the primary intended effect of B1-D2.

## 9. Why distance/energy is not changed

B1-D2 deliberately does **not** build a new boundary distance certificate. This keeps one causal variable changed at a time. B1-E already identified travel-time/envelope looseness as the first intervention to test. Energy-bound redesign, stronger state-dependent filters, or new action abstractions are deferred.

## 10. Online computation contract

B1-D2 may use the already available exact query arrays:

\[
d_T(o,\cdot),
\qquad
d_T(\cdot,z).
\]

For each visited Region, online work is:

\[
\min_{b\in\partial^-R}d_T(o,b)
\]

and:

\[
\min_{b\in\partial^+R}d_T(b,z).
\]

No additional SSSP is required.

No Site ID may be scanned to compute the bound.

The new bound complexity is:

\[
\boxed{
O(|\partial^-R|+|\partial^+R|).
}
\]

This complexity must be measured, not assumed cheap.

## 11. Boundary complexity contract

Before comparative search results are inspected, freeze:

- \(|\partial^-R|\);
- \(|\partial^+R|\);
- union boundary size;
- Region node count;
- Region Site count;
- relevant static-bucket counts;
- depth-wise median/p95/max boundary size;
- total boundary references.

Boundary scans are deployable only if their cost is explicitly accounted. No post-hoc threshold is created from current development data.

## 12. Forbidden hidden work

B1-D2 must not precompute or query Site-dependent terms such as:

\[
d_T(o,b)+d_T(b,s)
\]

for all \(s\in R\).

That would reintroduce online Region Site scans.

Only boundary-node lookups are permitted for the new certificate.

## 13. Parent monotonicity

The existing rule may be retained:

\[
L^{BA}(child)
\leftarrow
\max\{L^{BA,raw}(child),L^{BA}(parent)\}.
\]

Store raw and normalized bounds separately.

## Theorem 5 — Exact branch-and-bound

Assume:

1. static bucket coverage remains valid;
2. BA cost bounds are admissible;
3. only exact semantic leaf actions update \(U\);
4. exact leaf evaluation is unchanged;
5. pruning uses \(L^{BA}(N)\ge U-\epsilon\).

Then:

\[
U-J_{B1}^*\le\epsilon.
\]

At \(\epsilon=0\), B1-D2 returns the exact B1 semantic optimum. ∎

## 14. Perfect-static ceiling

Using B1-E's perfect-static bound \(L^{PS}\), audit:

\[
\boxed{
L^{ALT}\le L^{BA}\le L^{PS}\le J_{\rm sem}^*
}
\]

within conservative tolerance wherever the semantic target exists.

This ordering is a core correctness diagnostic.

## 15. Bound headroom recovery

When:

\[
L^{PS}>L^{ALT},
\]

define:

\[
\boxed{
H_{\rm bound}
=
\frac{L^{BA}-L^{ALT}}
{L^{PS}-L^{ALT}}.
}
\]

If the denominator is zero, report `NA`.

This measures how much ALT→perfect-static certificate headroom is recovered by the topology-derived boundary bound.

It is descriptive only.

## 16. Work headroom recovery

For a work component \(N\), with frozen ALT8 work \(N_{\rm ALT}\), perfect-static work \(N_{\rm PS}\), and B1-D2 work \(N_{\rm BA}\), define when \(N_{\rm ALT}>N_{\rm PS}\):

\[
\boxed{
H_{\rm work}
=
\frac{
N_{\rm ALT}-N_{\rm BA}
}{
N_{\rm ALT}-N_{\rm PS}
}.
}
\]

Compute separately for:

- envelope checks;
- exact evaluator calls;
- refinements.

Do not combine into one weighted score.

## 17. Acceptance model

Because B1-D2 was designed after B1-E diagnosis on the same development set, no new confirmatory performance threshold may be invented.

Hard acceptance concerns only:

- theorem validity;
- exactness;
- no hidden Site scans;
- frozen-component preservation;
- complete boundary accounting.

Performance is descriptive.

## 18. Final one-stop freeze

After B1-D2:

\[
\boxed{
\textbf{freeze one-stop and advance to B2.}
}
\]

Poor pruning, incomplete headroom recovery, large residual slack, or a possible stronger design do not justify B1-D3.

## 19. Formal verdict

The boundary augmentation is first-principles admissible because it follows from directed path crossing of static road cells. Its empirical priority is diagnosis-driven, but its correctness does not depend on the development results.

B1-D2 therefore tests one isolated causal hypothesis:

\[
\boxed{
\text{Can topology-derived boundary travel-time bounds recover a material part of the ALT→perfect-static gap without Site scans?}
}
\]

After this single test, the one-stop phase ends.
