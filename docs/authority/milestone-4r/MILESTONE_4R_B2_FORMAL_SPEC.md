# Milestone 4R-B2 Formal Specification

**Project:** dy-HiRoute  
**Stage:** B2 — Multi-stop Formalization  
**Status:** theory/formal-model stage only; no B2 implementation authorized yet  
**Normative predecessors:** `RESEARCH_SPEC_v0.2.md`, accepted 4R-A/B0/B1/B1-D/B1-E/B1-D2 specifications and reports  
**Frozen one-stop base:** B1-D2 boundary-augmented deployable hierarchy

---

# 0. Stage transition

B1-D2 closed the one-stop development phase.

The one-stop method is now frozen. B2 does not reopen or retune:

- the accepted road hierarchy;
- the 8 ALT landmarks;
- the B1-D2 boundary augmentation;
- static `Ccap/S0cap/SCcap` semantics;
- the one-stop exact evaluator;
- the B1 action-effect principle.

B2 asks a different question:

\[
\boxed{
\textbf{Can HiRoute preserve exact multi-stop decision semantics while controlling the combinatorial growth of continuation choices?}
}
\]

This is the first milestone where stop-sequence combinatorics, not one-stop candidate filtering, is the central problem.

---

# 1. Primary B2 research question

The revised Go-1 question becomes operational in the multi-stop setting:

\[
\boxed{
\textbf{How can a hierarchical abstraction avoid explicitly evaluating most valid multi-stop continuations without changing the stop-planning problem?}
}
\]

The primary object is no longer a single Site action.

It is a continuation over a finite executable stop sequence.

---

# 2. Executable multi-stop plan

A concrete plan is:

\[
p=
(\Gamma,E_1,\ldots,E_H),
\]

where:

\[
E_i=
(S_i,t_i,\tau_i,e_i,\mathcal R_i^{sat})
\]

is the \(i\)-th vehicle stop event.

The stop count \(H\) is a decision variable.

Destination arrival is a terminal event, not a stop event unless explicitly modeled otherwise.

No Opportunity Region centroid is executable.

Only concrete Stop Sites are executable anchors.

---

# 3. Action-effect principle remains binding

Every vehicle stop event in the B2 semantic domain must perform at least one modeled effect:

\[
\boxed{
\operatorname{Effect}(E_i)\neq\varnothing.
}
\]

In the primary B2 domain:

\[
\operatorname{Effect}(E_i)\subseteq\{C,S\}.
\]

Where:

- \(C\): positive charging energy is actually added;
- \(S\): an active scheduled-stop requirement is actually satisfied.

A pure route-shaping via-Site visit is not a stop-planning action.

The no-stop / no-additional-stop continuation remains distinct from an effect-free Site visit.

---

# 4. Primary B2 requirement scope

B2 begins with the smallest multi-stop domain that creates genuine sequence combinatorics:

\[
\boxed{
\text{multiple charging stops}
+
\text{at most one generic hard scheduled-stop requirement}.
}
\]

The scheduled requirement retains:

- hard start window \([a,b]\);
- fixed duration \(D\);
- accepted static support predicate;
- compatible overlap with charging at the same Site.

B2 does not yet add:

- multiple heterogeneous appointments;
- restaurant/hotel choice;
- user profiles;
- stochastic occupancy;
- learned preferences;
- active information acquisition.

Those remain outside the primary B2 formal domain.

---

# 5. Concrete search state

A concrete continuation state after event \(i\) is:

\[
\boxed{
x_i=
(v_i,t_i,E_i,r_i,g_i)
}
\]

where:

- \(v_i\): current concrete road/Stop-Site anchor;
- \(t_i\): current clock time after completing the event;
- \(E_i\): current battery energy after completing the event;
- \(r_i\in\{0,1\}\): whether the hard scheduled requirement remains unsatisfied;
- \(g_i\): accumulated objective contribution excluding future continuation cost.

For the initial state:

\[
x_0=(o,t_0,E_0,r_0,0).
\]

If no scheduled requirement exists:

\[
r_0=0.
\]

If it exists:

\[
r_0=1.
\]

---

# 6. Why this state is sufficient in the primary domain

Under the primary B2 assumptions, future feasibility and future cost depend on the past only through:

- current anchor;
- current time;
- current energy;
- whether the scheduled requirement remains;
- accumulated cost for comparison.

The future does not depend on the identities of previous Stops except through these state variables.

Therefore the primary B2 model is Markov in \(x_i\).

This claim is part of the B2 theorem audit and must be rechecked if later work adds:

- visit-count penalties by Site;
- repeat-visit bans;
- path-history-dependent energy;
- user-history utility;
- time-varying learned beliefs.

---

# 7. Concrete next-stop action

From state \(x_i\), a next-stop action chooses a concrete Site \(s\) and an executable event:

\[
a_i=
(s,q_i,\sigma_i),
\]

where:

- \(q_i\ge0\): charging energy added at the Site;
- \(\sigma_i\in\{0,1\}\): whether the active scheduled requirement is satisfied there.

Semantic action condition:

\[
\boxed{
q_i>0
\quad\text{or}\quad
\sigma_i=1.
}
\]

If \(\sigma_i=1\), then:

- \(r_i=1\);
- the Site satisfies the accepted support predicate;
- the exact schedule window is feasible.

If \(q_i>0\), the Site must have accepted charging capability.

---

# 8. Exact transition

Let the selected fastest-time route from current anchor \(v_i\) to next Site \(s\) have:

\[
T_i=d_T(v_i,s),
\]

and selected actual route length:

\[
L_i=L_T(v_i,s).
\]

Arrival energy:

\[
E_i^{arr}
=
E_i-\kappa L_i.
\]

Hard arrival feasibility:

\[
E_i^{arr}\ge E_{\min}.
\]

Let fixed stop overhead be \(h\).

Pre-activity release time:

\[
r_i^{site}
=
t_i+T_i+h.
\]

If scheduled activity is performed:

\[
y_i=\max(a,r_i^{site}),
\]

with hard feasibility:

\[
y_i\le b.
\]

Scheduled completion:

\[
c_i^S=y_i+D.
\]

If charging energy \(q_i>0\), exact charging time is:

\[
C_i=C(E_i^{arr},E_i^{arr}+q_i;s),
\]

and charging completion is:

\[
c_i^C=r_i^{site}+C_i.
\]

The stop completion time is:

\[
\boxed{
t_{i+1}
=
\max
\left(
r_i^{site},
c_i^C,
c_i^S
\right),
}
\]

with absent components omitted.

This preserves concurrent makespan semantics.

Departure energy:

\[
E_{i+1}=E_i^{arr}+q_i.
\]

Battery capacity:

\[
0\le E_{i+1}\le E_{\max}.
\]

Requirement state:

\[
r_{i+1}
=
r_i-\sigma_i.
\]

---

# 9. Destination transition

From any continuation state \(x_i\), destination is reachable without another stop only if:

\[
E_i-\kappa L_T(v_i,z)
\ge
E_{\rm res}.
\]

Terminal arrival time:

\[
t_z=t_i+d_T(v_i,z).
\]

The scheduled requirement must be complete:

\[
r_i=0.
\]

Only then may the continuation terminate.

---

# 10. Objective decomposition

The accepted one-stop objective generalizes to:

\[
J(p)
=
T_{\rm clock}(p)
+
\lambda_{\rm stop}H
+
P_{\mathcal R}(p)
+
\theta^\top z_{\rm other}(p).
\]

In the primary B2 domain:

- hard requirement violation has cost \(+\infty\);
- no new user-specific utility is introduced;
- \(\theta^\top z_{\rm other}\) is fixed/absent unless already accepted.

Clock time is:

\[
T_{\rm clock}
=
t_z-t_0.
\]

The stop nuisance term is:

\[
\lambda_{\rm stop}H.
\]

No travel-time or stop-time component is counted twice.

A convenient accumulated prefix cost is:

\[
\boxed{
g_i
=
(t_i-t_0)
+
\lambda_{\rm stop} i.
}
\]

The terminal objective is:

\[
J(p)=g_H+d_T(v_H,z)
\]

when all hard constraints are satisfied.

---

# 11. Stop count is not pre-fixed

B2 must not assume a fixed number of stops.

The optimizer chooses:

\[
H\in\{0,1,2,\ldots\}.
\]

However, exact search must be finite.

Finiteness must come from proved dominance / positive-cost / declared search-domain arguments, not from an arbitrary unreported stop cap.

A finite stop cap may be used only in a separately declared **exact diagnostic subdomain** for small-instance validation.

---

# 12. Safe Detour Envelope in B2

The existing Safe Detour Envelope remains a spatial search superset.

A Site or edge lying inside the envelope does **not** imply that an arbitrary multi-stop sequence through it satisfies a total detour budget.

Therefore:

\[
\boxed{
\text{single-Site envelope membership does not compose into multi-stop route feasibility.}
}
\]

B2 must distinguish:

1. static spatial candidate restriction;
2. exact cumulative route/time/energy feasibility.

No theorem may infer sequence feasibility merely from each Site's individual envelope eligibility.

---

# 13. Multi-stop search graph

The exact multi-stop decision problem induces an implicit directed state graph:

\[
\mathcal G_X=(\mathcal X,\mathcal A_X).
\]

Vertices are concrete continuation states.

Edges are semantic next-stop actions or the terminal destination action.

A complete plan is a path:

\[
x_0\to x_1\to\cdots\to x_H\to z.
\]

The central computational problem is that:

\[
|\mathcal X|
\]

can grow combinatorially with candidate stops, energy choices, and requirement state.

B2 hierarchy must reduce continuation search, not redefine \(\mathcal G_X\).

---

# 14. Exact continuation value

Define:

\[
V^*(x)
\]

as the minimum future objective increment required to complete the trip from state \(x\).

Then:

\[
J^*=V^*(x_0).
\]

For a nonterminal state:

\[
V^*(x)
=
\min_{a\in\mathcal A(x)}
\left[
c(x,a)+V^*(f(x,a))
\right].
\]

This Bellman equation is a mathematical definition of the optimum, not an instruction to implement a dense dynamic program.

---

# 15. Dominance must be explicit

B2 must not merge states merely because they share a Site.

Consider two states at the same concrete anchor with the same requirement status:

\[
x^A=(v,t_A,E_A,r,g_A),
\]

\[
x^B=(v,t_B,E_B,r,g_B).
\]

A sufficient dominance condition in the primary domain is:

\[
\boxed{
t_A\le t_B,
\qquad
E_A\ge E_B,
\qquad
g_A\le g_B.
}
\]

Then \(A\) weakly dominates \(B\) if every continuation feasible from \(B\) is feasible from \(A\) with no larger final objective.

This theorem must be proved before using it for pruning.

No scalarized SOC/time score may replace componentwise dominance.

---

# 16. Dominance theorem candidate

## Theorem 1 — Same-anchor continuation dominance

Under the primary B2 assumptions:

- nonnegative travel/stop durations;
- waiting is always allowed;
- extra battery energy has no penalty;
- charging can be skipped;
- future service availability depends only on absolute time and current requirement state;
- objective is nondecreasing in elapsed clock time and stop count;

if two states share \((v,r)\) and satisfy:

\[
t_A\le t_B,
\qquad
E_A\ge E_B,
\qquad
g_A\le g_B,
\]

then state \(B\) may be discarded.

### Proof sketch

Take any feasible continuation from \(B\). State \(A\) can follow the same future Site sequence.

Earlier time cannot make a hard time window infeasible because \(A\) can wait.

Higher energy cannot remove feasibility because excess energy need not be consumed or penalized.

Every future action available to \(B\) remains available to \(A\).

The same continuation therefore produces no larger final objective from \(A\), given \(g_A\le g_B\).

A full formal proof is required before implementation.

---

# 17. Important dominance limitation

The theorem fails or requires revision if future models add:

- battery-mass penalties;
- SOC-dependent degradation utility;
- history-dependent Site bans;
- stochastic beliefs conditioned on prior observations;
- negative rewards for visiting certain Sites.

B2 primary does not include these.

---

# 18. Abstract next-stop search node

The hierarchy does not abstract the current vehicle state into a Region centroid.

For a concrete continuation state \(x\), define an abstract next-stop node:

\[
\boxed{
N=(x,R,\beta)
}
\]

where:

- \(x\) remains concrete;
- \(R\) is a frozen static road Region;
- \(\beta\) is a static action-superset bucket.

Thus abstraction applies to the **next action set**, not to current vehicle state.

This prevents accumulated approximation error from replacing the actual current state with an abstract Region representative.

---

# 19. Multi-stop action decomposition is a theory blocker

With the scheduled requirement still active, the next stop may be:

- charge only;
- schedule only;
- charge + schedule.

Naively searching `Ccap`, `S0cap`, and `SCcap` as independent semantic branches can duplicate concrete Site actions.

Therefore B2 must define a **disjoint action representation** or an exact deduplication theorem before implementation.

A candidate representation is intended effect set:

\[
\alpha\in\{C,S,CS\},
\]

combined with static capability supersets internally and exact performed effects at concrete leaves.

Coverage and nonduplication must be proved.

---

# 20. Hierarchical continuation lower bound

For concrete state \(x\) and abstract next-action node \(N=(x,R,\beta)\), define:

\[
\boxed{
L(N)
\le
\min_{a\in\mathcal A_{\rm semantic}(x,R,\beta)}
\left[
c(x,a)+V^*(f(x,a))
\right].
}
\]

This is the central B2 admissibility contract.

A valid B2 Region bound must lower-bound:

1. immediate cost of reaching/executing some next stop in \(R\);
2. the optimal remaining continuation after that stop.

One-stop Region bounds alone are not sufficient because they may ignore downstream mandatory charging.

---

# 21. Relaxed continuation principle

The B2 lower bound may solve a relaxation:

\[
\widehat{\mathcal X}\supseteq\mathcal X_{\rm concrete}
\]

with relaxed transition/resource constraints, provided:

\[
\widehat J\le J
\]

for every corresponding concrete continuation.

Then:

\[
\inf_{\hat p\in\widehat{\mathcal X}}\widehat J(\hat p)
\]

is admissible.

This is the same first-principles rule used in B0/B1, now applied to entire continuations.

---

# 22. Minimal continuation lower bound

Before designing a strong B2 bound, a universally safe baseline is:

\[
\boxed{
L_0(N)
=
\underline c_{\rm immediate}(N)
+
\underline T_{\rm dest}(R)
}
\]

where:

- \(\underline c_{\rm immediate}(N)\) is an admissible lower bound on reaching/executing a next stop in \(R\);
- \(\underline T_{\rm dest}(R)\) is an admissible lower bound from \(R\) to destination;
- future mandatory charging/schedule work after the next stop is optimistically ignored.

This can be weak but remains admissible.

B2 should strengthen it only through explicit relaxations.

---

# 23. Energy-continuation relaxation

A stronger continuation bound may account for minimum future charging energy.

Let a relaxed continuation require at least:

\[
q_{\rm fut}^{LB}(x')
\]

additional energy after next state \(x'\).

Using global maximum charging power:

\[
P_{\max},
\]

a safe future charging-time lower bound is:

\[
\boxed{
C_{\rm fut}^{LB}
=
3600\frac{q_{\rm fut}^{LB}}{P_{\max}}.
}
\]

B2 must avoid double counting compatible charging and scheduled activity.

If component bounds may overlap in time, combine them through a proved `max` relation rather than arbitrary summation.

---

# 24. Scheduled-requirement continuation relaxation

If the scheduled requirement remains unsatisfied after the next action, a continuation lower bound must preserve the possibility that it is satisfied later.

It must not declare a continuation infeasible merely because the current Region cannot satisfy the schedule if a later Region may do so.

This is a major difference from one-stop B1.

---

# 25. Multi-stop infeasibility is state-dependent

A Region may be infeasible as the next stop from one state and feasible from another due to:

- current SOC;
- current time;
- whether the schedule remains;
- current anchor.

Therefore B2 must not store query-independent Region feasibility labels.

Only static capabilities/support remain query-independent.

---

# 26. Region refinement remains action-set refinement

For fixed concrete state \(x\), refinement must preserve the concrete next-action set.

If:

\[
R=R_1\dot\cup R_2,
\]

then the declared action representation must satisfy the corresponding coverage identity, modulo an explicitly proved deduplication rule.

Refinement must never change which concrete actions are legal.

---

# 27. Two distinct pruning mechanisms

A B2 exact search frontier contains two conceptually different objects:

1. concrete continuation states \(x\);
2. abstract next-action Region nodes \(N=(x,R,\beta)\).

Do not conflate:

- **state dominance**, which removes an inferior concrete continuation state;
- **Region pruning**, which removes a set of next actions from one concrete state.

They require different proofs.

---

# 28. Global incumbent

A global incumbent:

\[
U
\]

must correspond to a fully executable concrete multi-stop plan that reaches the destination and satisfies all hard requirements.

Partial plans cannot update \(U\).

Abstract Regions cannot update \(U\).

---

# 29. Global optimality condition

Let OPEN cover every unpruned continuation possibility.

If every OPEN object \(n\) has admissible lower bound \(L(n)\), then termination at:

\[
\boxed{
\min_{n\in OPEN}L(n)\ge U-\epsilon
}
\]

certifies:

\[
U-J^*\le\epsilon.
\]

At \(\epsilon=0\), exactness follows.

B2 must explicitly prove OPEN coverage under its combined concrete-state / abstract-action representation.

---

# 30. Exact small-domain reference is mandatory

Before any large multi-stop experiment, B2 requires an exact reference solver on a deliberately bounded diagnostic domain.

The reference may use:

- small synthetic graphs;
- small candidate sets;
- a declared stop cap only for the diagnostic reference;
- exhaustive enumeration or dynamic programming.

Its purpose is to validate:

- transition semantics;
- charging decisions;
- schedule overlap;
- action-effect semantics;
- dominance;
- Region coverage;
- hierarchical exactness.

It is not the production algorithm.

---

# 31. B2 roadmap

## B2-0 — Formal theory

Resolve:

- state sufficiency;
- disjoint next-action representation;
- same-anchor dominance;
- continuation lower-bound contract;
- OPEN coverage theorem;
- exact small-domain reference contract.

No real large search yet.

## B2-1 — Exact small multi-stop validation

Use synthetic and tightly bounded real diagnostic instances.

Require zero correctness violations.

No scalability claim yet.

## B2-2 — Deployable long-haul stress

Only after B2-1 passes:

- introduce ODs that genuinely require multiple charging stops;
- measure continuation branching and hierarchy pruning;
- consider expanded geography such as China only after a data-quality audit;
- retain a control geography if useful.

No holdout is consumed before the B2 algorithm/protocol is frozen.

---

# 32. Out of scope for B2 formalization

Do not immediately add:

- stochastic charger occupancy;
- Bayesian/POMDP planning;
- user personalization;
- restaurant/hotel recommendation;
- full road-path optimization beyond accepted routing semantics;
- elevation/temperature energy model;
- multiple heterogeneous appointments;
- learned ranking.

Deterministic multi-stop correctness comes first.

---

# 33. Formal blockers before implementation

B2 implementation is **not authorized** until the following are closed:

\[
\boxed{\textbf{B2-T1: state sufficiency proof}}
\]

\[
\boxed{\textbf{B2-T2: disjoint multi-stop action representation}}
\]

\[
\boxed{\textbf{B2-T3: same-anchor dominance proof}}
\]

\[
\boxed{\textbf{B2-T4: admissible continuation lower-bound definition}}
\]

\[
\boxed{\textbf{B2-T5: OPEN coverage / exactness theorem}}
\]

\[
\boxed{\textbf{B2-T6: exact small-domain reference contract}}
\]

If any cannot be proved cleanly, revise theory before coding.

---

# 34. B2 progress discipline

B2 must not repeat indefinite one-stop tuning.

Use this sequence:

1. solve B2-T1–T6;
2. freeze a B2-1 protocol;
3. implement one exact small-domain algorithm;
4. validate correctness;
5. freeze a deployable B2 design;
6. only then run long-haul stress.

No algorithm shopping after seeing long-haul results.

No geography switching as a substitute for unresolved theory.

---

# 35. Immediate next deliverable

The next artifact should be:

\[
\boxed{
\texttt{MILESTONE\_4R\_B2\_THEORY\_AUDIT.md}
}
\]

It must attack B2-T1 through B2-T6 one by one and either:

- prove each contract; or
- identify the exact unresolved blocker.

Only after that audit passes should a B2-1 experimental protocol or Codex implementation prompt be written.
