# Milestone 4R-B2 Theory Audit

**Project:** dy-HiRoute  
**Stage:** Milestone 5 / B2 — Multi-stop Hierarchical Planning  
**Purpose:** close the pre-implementation theory gates for the frozen success endpoint: deterministic exact multi-stop hierarchical planning + deployable evaluation + independent holdout.

## 0. Executive result

The six originally declared B2 theory gates were audited.

| Gate | Status | Result |
|---|---|---|
| B2-T1 | closed with normalization | physical Markov state is sufficient; accumulated objective is a label value |
| B2-T2 | closed | effect-labelled actions give an exact disjoint decomposition |
| B2-T3 | closed conservatively | strict-cost same-anchor dominance is safe |
| B2-T4 | closed | a deployable admissible multi-stop continuation lower bound exists |
| B2-T5 | closed conditionally | OPEN coverage/exactness follows if charger leaves are solved exactly |
| B2-T6 | closed as a contract | an independent exact small-domain reference can optimize continuous charging |

The audit exposes one prerequisite omitted from T1–T6:

\[
\boxed{\textbf{B2-T7: finite exact representation of continuous charging actions}}
\]

A charger action contains:

\[
q\in(0,E_{\max}-E^{arr}],
\]

so a naive exact search has uncountably many successor states. A finite SOC grid would violate the declared word **exact**.

Therefore:

\[
\boxed{\textbf{B2 production implementation is not yet authorized.}}
\]

The next and only theory target is to prove finite piecewise-linear charging-frontier closure.

---

# 1. Frozen assumptions

This audit keeps the declared primary B2 domain unchanged:

- deterministic, time-invariant routing;
- fastest-time legs and their selected actual lengths;
- constant driving energy rate \(\kappa\);
- finite battery capacity and reserve/floor;
- canonical finite-segment charging curve;
- multiple charging stops;
- at most one hard scheduled-stop requirement;
- waiting allowed;
- charge/schedule overlap allowed;
- positive stop nuisance and fixed positive stop overhead;
- no stochastic occupancy, user profile, active information, or history-dependent utility.

The one-stop hierarchy and B1-D2 method remain frozen.

---

# 2. B2-T1 — State sufficiency

The draft state:

\[
(v,t,E,r,g)
\]

should be normalized.

Define the **physical Markov state**:

\[
\boxed{y=(v,t,E,r)}
\]

and a search label:

\[
\boxed{\ell=(y,g,\tau_{\rm tie})}.
\]

Here:

- \(v\): current concrete anchor;
- \(t\): current absolute completion time;
- \(E\): battery energy;
- \(r\in\{0,1\}\): scheduled requirement still unsatisfied;
- \(g\): accumulated primary objective;
- \(\tau_{\rm tie}\): prefix information needed only for deterministic tie reconstruction.

With \(k\) completed semantic stops:

\[
g=(t-t_0)+\lambda_{\rm stop}k.
\]

## Theorem T1

Under the frozen primary domain, future feasibility and future transition costs depend on history only through:

\[
(v,t,E,r).
\]

**Reason.** Future route evaluation depends on current anchor and next Site; energy feasibility depends on current \(E\); schedule feasibility depends on current \(t\) and \(r\); no accepted objective or hard constraint depends on earlier Site identities. Past elapsed time and nuisance affect only accumulated objective \(g\).

Thus:

\[
\boxed{\textbf{B2-T1 CLOSED}}
\]

with the correction that \(g\) is label cost, not physical state.

This does **not** imply a finite state space because \(E\) is continuous.

---

# 3. B2-T2 — Disjoint action representation

Use effect-labelled concrete actions:

\[
\boxed{a=(s,\alpha,q)},\qquad \alpha\in\{C,S,CS\}.
\]

Define:

### Charge only

\[
\mathcal A_C=
\{(s,C,q):s\text{ charger},\ q>0\}.
\]

Requirement state remains unchanged.

### Schedule only

\[
\mathcal A_S=
\{(s,S,0):r=1,\ s\text{ supports schedule},\ \text{schedule feasible}\}.
\]

### Charge + schedule

\[
\mathcal A_{CS}=
\{(s,CS,q):r=1,\ s\text{ charger+support},\ q>0,\ \text{schedule feasible}\}.
\]

Destination remains a separate terminal action.

These are disjoint **actions** even when the Site sets overlap:

\[
\mathcal A_{\rm semantic}
=
\mathcal A_C
\dot\cup
\mathcal A_S
\dot\cup
\mathcal A_{CS}.
\]

For hierarchy nodes use:

\[
N=(\ell,R,\alpha).
\]

Static supersets may overlap in Site membership because \(\alpha\) distinguishes the action.

No neutral action is added.

Therefore:

\[
\boxed{\textbf{B2-T2 CLOSED}}.
\]

---

# 4. B2-T3 — Conservative same-anchor dominance

For two labels sharing the same concrete anchor and requirement state:

\[
\ell_A=((v,t_A,E_A,r),g_A,\tau_A),
\]

\[
\ell_B=((v,t_B,E_B,r),g_B,\tau_B),
\]

use the conservative primary rule:

\[
\boxed{
t_A\le t_B,\qquad
E_A\ge E_B,\qquad
g_A<g_B.
}
\]

The strict inequality in \(g\) is deliberate. Equal-primary-cost labels are not removed unless an additional tie-safe duplicate theorem applies.

## Emulation argument

Take any semantic continuation feasible from \(B\).

State \(A\) may wait until \(t_B\), then follow the same effect-labelled Site sequence.

For an \(S\) action, earlier time can wait and higher energy cannot hurt.

For a \(C\) or \(CS\) action, if the \(B\) stop charges from:

\[
e_B^{arr}\to e_B^{dep},
\]

and \(A\) arrives with:

\[
e_A^{arr}\ge e_B^{arr},
\]

then if \(e_A^{arr}<e_B^{dep}\), \(A\) can charge only to \(e_B^{dep}\), using no more time because its charge interval is a subset.

If:

\[
e_A^{arr}\ge e_B^{dep},
\]

choose a sufficiently small positive charge so the stop remains semantic; charging-time continuity guarantees it can fit within the positive charge time used by \(B\). If \(A\) is already at \(E_{\max}\), a positive C-effect is impossible; under positive energy consumption on positive-length legs this can only occur in a zero-consumption/co-located edge case, where an unnecessary C-only event is removed, or a CS event becomes an S event.

Inductively, \(A\) can maintain no later time and no less energy than \(B\).

Since:

\[
g_A<g_B,
\]

the resulting complete plan has strictly smaller primary objective, so deterministic tie ordering is irrelevant.

Therefore:

\[
\boxed{\textbf{B2-T3 CLOSED}}
\]

with this conservative rule.

We intentionally give up equal-cost dominance for now.

---

# 5. B2-T4 — Admissible continuation lower bound

The B1-D2 one-stop bound cannot be copied unchanged.

Two differences matter:

1. a next stop need not make destination directly reachable;
2. current anchor changes after every stop.

Also, B1-D2 inbound boundary tightening used an exact origin-to-all-nodes array. Running an SSSP from every multi-stop state would not be deployable.

## 5.1 Deployable metric composition

For arbitrary current anchor \(v\), use set-valued ALT:

\[
\underline T^-(v,R)
=
\underline T_{\rm ALT}(v,R).
\]

This requires only fixed landmark arrays and Region summaries.

For the fixed trip destination \(z\), use:

\[
\underline T^+(R,z)
=
\max\{
\underline T_{\rm ALT}(R,z),
\delta_R^+(z)
\},
\]

where \(\delta_R^+(z)\) uses the one query-global reverse destination routing array and the frozen egress boundary.

Thus no per-state all-node SSSP is introduced.

## 5.2 Baseline Region/effect bounds

Let:

\[
T_R^-=\underline T_{\rm ALT}(v,R),
\qquad
T_R^+=\underline T^+(R,z).
\]

For charge only:

\[
\boxed{
L_C^0
=
g+T_R^-+h+\lambda_{\rm stop}+T_R^+
+\mathbf 1[r=1](h+\lambda_{\rm stop}+D).
}
\]

Positive charging time has infimum zero. If the schedule remains after this C action, at least one later semantic schedule stop is unavoidable; travel detour and waiting are optimistically ignored.

For schedule only, earliest possible completion is:

\[
\underline c_S
=
\max\{a,t+T_R^-+h\}+D,
\]

so:

\[
\boxed{
L_S^0
=
g+(\underline c_S-t)+\lambda_{\rm stop}+T_R^+.
}
\]

For CS, charging may have arbitrarily small positive duration and can overlap schedule, hence:

\[
\boxed{
L_{CS}^0=L_S^0.
}
\]

These bounds may be weak but are admissible because all downstream charging beyond the next event may be optimistically ignored.

## 5.3 Safe next-action infeasibility

Using directed shortest-distance ALT:

\[
\underline D_{\rm ALT}(v,R)
\le
\min_{s\in R}d_D(v,s),
\]

if:

\[
E-\kappa\underline D_{\rm ALT}(v,R)<E_{\min},
\]

then no Site in that Region can be the **next** stop.

This does not imply whole-trip infeasibility.

Therefore:

\[
\boxed{\textbf{B2-T4 CLOSED}}.
\]

A stronger continuation heuristic can be added later only through a separately proved relaxation.

---

# 6. B2-T5 — OPEN coverage and exactness

B2 has two search-object types:

1. concrete labels \(\ell\);
2. abstract next-action nodes \(N=(\ell,R,\alpha)\).

For every undominated concrete label, root Region/effect nodes must cover all semantic next actions.

Region refinement must satisfy, for fixed \((\ell,\alpha)\):

\[
R=R_1\dot\cup R_2
\Rightarrow
\mathcal A_\alpha(\ell,R)
=
\mathcal A_\alpha(\ell,R_1)
\dot\cup
\mathcal A_\alpha(\ell,R_2).
\]

Only a complete destination-reaching concrete plan may update incumbent \(U\).

## Coverage invariant

Every feasible complete continuation extending a generated undominated prefix is always represented by exactly one of:

- an unpruned abstract action node;
- an exact concrete successor label;
- a completed incumbent;
- a safely dominated prefix.

## Theorem T5

If:

1. root action nodes cover every semantic next action;
2. Region refinement preserves action-set coverage;
3. every Region/action lower bound is admissible;
4. concrete leaf action sets are solved exactly;
5. successor transitions are exact;
6. dominance satisfies T3;
7. only complete plans update \(U\);

then:

\[
\min_{n\in OPEN}L(n)\ge U-\epsilon
\]

implies:

\[
U-J^*\le\epsilon.
\]

At \(\epsilon=0\), search is exact.

Thus:

\[
\boxed{\textbf{B2-T5 CLOSED CONDITIONALLY}}.
\]

The only unresolved premise is exact solution of the continuous \(C/CS\) leaf action set. That becomes T7.

---

# 7. B2-T6 — Exact small-domain reference

The reference must not discretize energy and then claim exactness for the continuous problem.

Declare a small reference domain with:

- finite Site set;
- small synthetic/real graph;
- diagnostic stop cap \(H_{\rm ref}\);
- the same continuous energy domain;
- the same charging curve;
- the same schedule/overlap semantics.

Enumerate every effect-labelled Site sequence up to \(H_{\rm ref}\).

For each fixed sequence, optimize continuous charging exactly.

Because the canonical charging curve has finitely many power/SOC segments:

- drive energy transitions are affine;
- battery constraints are linear;
- schedule windows are piecewise linear;
- charging time is piecewise linear once arrival/departure charging segments are fixed;
- CS completion is piecewise linear once the active `max` branch is fixed.

Therefore the reference can enumerate the finite segment/max regimes. Inside each regime, solve the resulting linear optimization problem, reject inconsistent regimes, and retain the best feasible result.

Use lexicographic reference optimization:

1. primary objective;
2. total charged energy;
3. stop count;
4. Site tuple.

Required synthetic cases include:

- zero stop;
- one charge;
- two charges;
- S only;
- C→S;
- S→C;
- CS;
- charging-curve breakpoint;
- schedule-overlap free charging;
- reserve-tight;
- infeasible multi-stop.

Therefore:

\[
\boxed{\textbf{B2-T6 CLOSED AS A REFERENCE CONTRACT}}.
\]

---

# 8. Newly exposed blocker — B2-T7

At a concrete charger leaf:

\[
q\in(0,E_{\max}-E^{arr}]
\]

is continuous.

A production search cannot create one successor label per \(q\).

Three obvious shortcuts are unacceptable:

### SOC grid

Finite, but not exact.

### Charge-to-X heuristic

Can miss the optimum under nonlinear charging, future charger placement, schedule overlap, and reserve constraints.

### Infinite successor enumeration

Not implementable.

Therefore exact multi-stop planning needs a compact exact representation of the continuum.

---

# 9. Recommended T7 representation

Use a functional energy frontier.

For concrete anchor \(v\), requirement state \(r\), and discrete completed-stop count \(k\), define:

\[
\boxed{
\phi_{v,r,k}(E)
=
\text{earliest achievable completion time at }v
\text{ with departure energy }E.
}
\]

Because \(k\) is retained:

\[
g=(\phi(E)-t_0)+\lambda_{\rm stop}k
\]

is recoverable.

The frontier represents infinitely many point states compactly.

---

# 10. T7 theorem obligations

T7 closes only if finite piecewise-linear frontiers are proved closed under all B2 operators.

## Drive

For fixed travel time \(T\) and consumption \(c\):

\[
E^{arr}=E^{dep}-c,
\qquad
t^{arr}=t^{dep}+T.
\]

Affine shift.

## Schedule

\[
t'=\max\{a,t+h\}+D.
\]

Piecewise-linear transform.

## Charge

For arrival frontier \(\phi\):

\[
\boxed{
\phi_C(E_d)
=
\min_{E_a\le E_d}
\left[
\phi(E_a)+h+C(E_a,E_d)
\right].
}
\]

Must prove the min-plus transform of a finite piecewise-linear frontier under the frozen piecewise charging curve remains finitely piecewise linear.

## CS

\[
\phi_{CS}(E_d)
=
\min_{E_a\le E_d}
\max\{
\phi(E_a)+h+C(E_a,E_d),
\max(a,\phi(E_a)+h)+D
\}.
\]

Must prove finite piecewise-linear closure.

## Merge

Multiple predecessor frontiers reaching the same \((v,r,k)\) are reduced to their exact lower envelope.

## Domain clipping

Retain exactly:

\[
E_{\min}\le E\le E_{\max}.
\]

## Witness/tie recovery

Every retained frontier segment must preserve enough predecessor information to reconstruct the exact plan and deterministic tie key.

---

# 11. T7 acceptance conditions

The theorem must establish:

1. finite representation after every finite expansion;
2. closure under drive, C, S, CS, and merge;
3. no SOC discretization;
4. exact breakpoint propagation subject only to declared conservative floating-point policy;
5. exact predecessor/action reconstruction;
6. compatibility with lexicographic tie semantics.

Until then, production B2 code must not be written.

---

# 12. Revised B2 gate

The theory gate is now:

| Gate | Required state |
|---|---|
| T1 | closed |
| T2 | closed |
| T3 | closed |
| T4 | closed |
| T5 | closed conditional on exact charger-leaf operator |
| T6 | reference contract closed |
| **T7** | **must close before production implementation** |

Current state:

\[
\boxed{
\textbf{B2 theory is concentrated on one remaining fundamental representation problem.}
}
\]

This is preferable to starting implementation with a hidden continuum.

---

# 13. Immediate next action

Do not write a B2 Codex implementation prompt.

Create next:

\[
\boxed{
\texttt{MILESTONE\_4R\_B2\_T7\_CHARGING\_FRONTIER\_SPEC.md}
}
\]

Its sole task is to prove or falsify finite exact piecewise-linear frontier closure for the frozen canonical charging model.

If T7 closes:

\[
\text{B2-1 exact small-domain implementation}
\rightarrow
\text{correctness validation}
\rightarrow
\text{deployable multi-stop stress}.
\]

If T7 fundamentally fails, choose explicitly between:

- narrowing the exact charging model; or
- accepting an approximate discretized multi-stop formulation.

The latter would require changing the frozen success definition because it would no longer be exact.

---

# 14. Audit conclusion

The audit does not support abandoning B2.

It also does not support coding yet.

The remaining theoretical uncertainty is sharply isolated:

\[
\boxed{
\textbf{Can the continuous charging decision be represented by a finite exact frontier closed under HiRoute's multi-stop transitions?}
}
\]

That is the next and only theory target before B2 implementation.
