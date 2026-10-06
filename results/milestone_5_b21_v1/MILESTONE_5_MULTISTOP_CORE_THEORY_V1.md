# Milestone 5 — Multi-Stop Core Theory v1.0

**Project:** dy-HiRoute  
**Stage:** Milestone 5 — Deterministic Exact Multi-Stop Hierarchical Planning  
**Status:** normative theory reset after the B21 correctness counterexample  
**Success endpoint:** deterministic exact multi-stop hierarchical planning + deployable evaluation + independent holdout  
**Scope:** deterministic research core only; no product-layer uncertainty, personalization, or active-information planning

---

# 0. Authority and supersession

This document is a **theory reset**, not an amendment chain.

For all future Milestone-5 implementation work, this document supersedes the normative multi-stop claims in:

- `MILESTONE_4R_B2_FORMAL_SPEC.md`
- `MILESTONE_4R_B2_THEORY_AUDIT.md`
- `MILESTONE_4R_B2_T7_CHARGING_FRONTIER_SPEC.md`
- `MILESTONE_4R_B2_T7_THEOREM_AUDIT.md`
- the draft `MILESTONE_4R_B2_B21_THEORY_REVISION_R1.md`

Those documents remain historical development evidence.

They are not implementation authority after v1.0 is accepted.

The frozen one-stop/B1-D2 artifacts remain authoritative for:

- accepted route semantics;
- frozen Region hierarchy;
- B1-D2 landmarks and boundary artifacts;
- Site attachment and static capability/support semantics;
- one-stop predecessor preservation.

The failed B21 counterexample, report, failed regression tests, REF certificates, operator traces, and dominance witness remain immutable historical evidence.

---

# 1. Why a reset was necessary

The failed B21 case demonstrated:

\[
t_A<t_B,
\qquad
E_A=E_B,
\qquad
g_A<g_B,
\]

but after a scheduled waiting operator:

\[
\Psi(t)=\max(a,t+h)+D,
\]

the prefix time advantage vanished:

\[
\Psi(t_A)=\Psi(t_B).
\]

The later prefix then won the accepted plan key because it had lower cumulative charged energy.

Therefore the previous theory had made a structural mistake:

\[
\boxed{
\text{local primary superiority was treated as if it implied final lexicographic superiority.}
}
\]

This document removes that assumption.

The design order is now:

\[
\boxed{
\text{final objective}
\rightarrow
\text{continuation semantics}
\rightarrow
\text{continuation preorder}
\rightarrow
\text{sufficient label algebra}
\rightarrow
\text{canonical reduction}
\rightarrow
\text{hierarchical action pruning}.
}
\]

No compression rule is allowed before its continuation safety is proved.

---

# 2. Frozen primary decision problem

A concrete executable multi-stop plan is:

\[
p=(\Gamma,E_1,\ldots,E_H),
\]

where each semantic stop event is:

\[
E_i=(s_i,\alpha_i,q_i,\text{timing data}),
\]

with:

\[
\alpha_i\in\{C,S,CS\}.
\]

The stop count \(H\) is endogenous.

No Region centroid is executable.

A route-shaping via-Site visit with no modeled stop effect is not a semantic stop action.

Destination arrival is terminal, not a semantic stop.

---

# 3. Frozen route and energy semantics

For every concrete leg \(u\to v\):

\[
T(u,v)=d_T(u,v)
\]

is selected fastest directed travel time.

Its energy-relevant physical length is:

\[
L_T(u,v),
\]

the actual length of the selected fastest-time route.

Do not assume:

\[
L_T
\]

is shortest-distance or obeys a triangle inequality.

Driving-energy consumption is:

\[
c(u,v)=\kappa L_T(u,v).
\]

The directed shortest physical road distance:

\[
d_D(u,v)\le L_T(u,v)
\]

remains available for lower bounds.

---

# 4. Frozen hard constraints

Battery:

\[
E_{\min}\le E\le E_{\max}.
\]

Destination reserve:

\[
E_z\ge E_{\rm res}.
\]

Semantic C or CS action:

\[
q>0.
\]

A scheduled requirement, when present, has:

\[
[a,b],\qquad D,
\]

and may overlap charging at the same stop.

Waiting is allowed.

Hard requirement miss is infeasible.

---

# 5. The one and only final optimization order

The complete accepted plan key is:

\[
\boxed{
K(p)=
\left(
J(p),
Q(p),
H(p),
\Pi(p)
\right)
}
\]

and plans are minimized lexicographically.

Here:

\[
J(p)
=
T_{\rm clock}(p)
+
\lambda_{\rm stop}H(p),
\]

\[
Q(p)
=
\sum_i q_i,
\]

and:

\[
\Pi(p)
=
\big((s_1,\alpha_1),\ldots,(s_H,\alpha_H)\big)
\]

under the frozen deterministic tuple ordering.

No internal theorem may optimize only \(J\) and then silently assume the rest of \(K\) is preserved.

Every compression, dominance, bound, incumbent update, and termination rule must explicitly preserve this lexicographic order.

---

# 6. Physical Markov state versus optimization label

The physical state is:

\[
\boxed{
x=(v,t,E,r)
}
\]

where:

- \(v\): current concrete anchor;
- \(t\): current absolute completion time;
- \(E\): current battery energy;
- \(r\in\{0,1\}\): whether the single hard scheduled requirement remains unsatisfied.

The physical state determines future feasibility.

It does **not** contain enough information by itself to determine which historical prefix is lexicographically preferable.

Therefore optimization metadata is separate.

For a prefix with \(k\) semantic stops, define:

\[
\boxed{
\ell=(x,k,\rho,\pi)
}
\]

where:

- \(k\): completed semantic stop count;
- \(\rho\): cumulative-charge offset defined below;
- \(\pi\): deterministic prefix Site/action tuple.

---

# 7. State sufficiency theorem

## Theorem M5-T1 — physical state sufficiency

Under the frozen primary domain, the legal future action set and every future physical transition depend on the past only through:

\[
(v,t,E,r).
\]

Past Site identities do not affect future feasibility because the primary domain contains no:

- repeat-visit bans;
- history-dependent service rules;
- learned beliefs;
- user-history utility;
- stochastic information state.

Thus:

\[
(v,t,E,r)
\]

is a sufficient physical Markov state.

This theorem says nothing about safe optimization compression between different histories that reach the same physical state.

That is a separate problem.

---

# 8. Energy-conservation coordinate for the secondary key

Let:

- \(E_0\): initial battery energy;
- \(Q\): cumulative charged energy;
- \(C_{\rm drive}\): cumulative driving-energy consumption;
- \(E\): current battery energy.

Energy conservation gives:

\[
E
=
E_0
+
Q
-
C_{\rm drive}.
\]

Define:

\[
\boxed{
\rho
=
Q-E
=
C_{\rm drive}-E_0.
}
\]

Therefore:

\[
\boxed{
Q=E+\rho.
}
\]

At fixed current energy \(E\), comparing total charge \(Q\) is exactly equivalent to comparing \(\rho\).

This is not a patch variable.

It is a conservation-law coordinate.

---

# 9. Transition law for \(\rho\)

## Drive consuming \(c\)

\[
E'=E-c,
\]

\[
Q'=Q,
\]

hence:

\[
\boxed{
\rho'=\rho+c.
}
\]

## Charge by \(q\)

\[
E'=E+q,
\]

\[
Q'=Q+q,
\]

hence:

\[
\boxed{
\rho'=\rho.
}
\]

## Schedule / waiting

Energy and cumulative charge do not change:

\[
\boxed{
\rho'=\rho.
}
\]

Thus \(\rho\) is invariant under charging and waiting, and increases only by deterministic drive consumption.

---

# 10. Exact charging primitive

The canonical research charging law has finitely many positive-power segments.

Let:

\[
0=b_0<b_1<\cdots<b_m=E_{\max}.
\]

Define:

\[
\boxed{
F(E)
=
3600\int_0^E\frac{1}{P(u)}\,du.
}
\]

Then \(F\) is:

- continuous;
- strictly increasing;
- finite;
- piecewise affine.

Exact charging time is:

\[
\boxed{
C(a,b)
=
F(b)-F(a),
\qquad
0\le a\le b\le E_{\max}.
}
\]

Site-dependent charging laws are outside v1 unless each Site's exact law independently satisfies the same finite positive piecewise-affine primitive contract.

---

# 11. Discrete prefix family

A discrete prefix family is defined by a concrete effect-labelled stop sequence:

\[
\pi
=
((s_1,\alpha_1),\ldots,(s_k,\alpha_k)).
\]

For a fixed \(\pi\):

- all selected road legs are fixed;
- cumulative drive energy is fixed;
- therefore \(\rho_\pi\) is constant.

At a fixed final energy \(E\):

\[
\boxed{
Q_\pi(E)=E+\rho_\pi.
}
\]

Different allocations of charge among the stops of the same discrete prefix cannot change \(Q_\pi(E)\).

Therefore, for one fixed prefix family, the only continuous optimization required at final energy \(E\) is the earliest achievable completion time.

---

# 12. Branch representation

For one discrete prefix family \(\pi\), define an exact branch:

\[
\boxed{
b=
(I_b,t_b(E),\rho_b,\pi_b,A_b,w_b)
}
\]

where:

- \(I_b\): finite energy interval;
- \(t_b(E)\): finite piecewise-affine infimal completion time;
- \(\rho_b\): constant cumulative-charge offset;
- \(\pi_b\): fixed discrete prefix tuple;
- \(A_b(E)\): attainment indicator;
- \(w_b\): exact witness/predecessor rule where attained.

Open and closed interval endpoints are explicit.

A limit-only point may be retained for lower bounding but cannot update an executable incumbent.

---

# 13. Exact multi-branch frontier

For fixed:

\[
(v,r,k),
\]

the exact frontier is:

\[
\boxed{
\mathcal F_{v,r,k}
=
\{b_1,\ldots,b_n\}
}
\]

after canonical continuation-safe reduction.

It is **not**:

\[
\min_i t_i(E).
\]

Multiple branches may coexist at the same energy.

The frontier is therefore a finite set of one-dimensional PWA branches, not a general two-dimensional continuous surface.

---

# 14. Continuation preorder — the definition of dominance

Local inequalities do not define dominance.

Continuation behavior does.

For two attained prefixes A and B, define:

\[
\boxed{
A\preceq_{\mathcal C}B
}
\]

iff for every legal executable suffix \(\sigma\) from B, A can execute a corresponding suffix with final key:

\[
K(A\oplus\sigma)
\le_{\rm lex}
K(B\oplus\sigma).
\]

Only relations proved to imply:

\[
\preceq_{\mathcal C}
\]

may be used for pruning.

This is the normative definition of safe dominance.

---

# 15. Conservative operational dominance

v1 deliberately uses a conservative sufficient condition.

Compare only attained labels sharing exactly:

\[
\boxed{
(v,E,r,k).
}
\]

Let their metadata be:

\[
A=(t_A,\rho_A,\pi_A),
\]

\[
B=(t_B,\rho_B,\pi_B).
\]

Define:

\[
\boxed{
A\preceq_{\rm safe}B
}
\]

iff:

\[
t_A\le t_B,
\]

\[
\rho_A\le\rho_B,
\]

and if:

\[
\rho_A=\rho_B,
\]

then:

\[
\pi_A\le_{\rm lex}\pi_B.
\]

At least one strict improvement is required unless the labels are exact duplicates.

No cross-energy dominance is part of v1.

No higher-SOC dominance is part of v1.

No strict-\(g\) dominance is part of v1.

---

# 16. Safe-dominance theorem

## Theorem M5-T2

If:

\[
A\preceq_{\rm safe}B
\]

at the same:

\[
(v,E,r,k),
\]

then:

\[
A\preceq_{\mathcal C}B.
\]

### Proof

Take any executable suffix from B.

A begins that suffix at:

- the same anchor;
- the same energy;
- the same requirement state;
- the same completed stop count;
- no later absolute time.

All future time operators are monotone nondecreasing in incoming time:

- drive adds a constant;
- charge duration depends on energies, not absolute clock;
- S applies `max`;
- CS applies maxima of monotone terms.

Therefore the same suffix from A finishes no later.

Because A and B begin the suffix with the same \(E\), and the same suffix applies the same future driving and charging actions:

\[
Q_A^{final}-Q_B^{final}
=
Q_A-Q_B
=
\rho_A-\rho_B
\le0.
\]

If final \(J\) is strictly lower, A wins.

If future waiting collapses the time difference and final \(J\) ties, A has no larger \(Q\).

If \(Q\) also ties, both have the same prefix length \(k\), the same suffix adds the same stop count, and lexicographic prefix order is extension-safe under appending the same suffix.

Hence final key from A is no worse. ∎

---

# 17. Why the failed B21 prefixes are incomparable

At the blocking state:

\[
t_A<t_B
\]

but:

\[
Q_A>Q_B.
\]

At fixed energy:

\[
\rho_A>\rho_B.
\]

Therefore neither prefix safely dominates the other.

Both must survive.

A later schedule plateau may erase:

\[
t_A<t_B
\]

while preserving:

\[
\rho_A>\rho_B.
\]

The later lower-charge prefix then becomes the exact final winner.

This behavior follows from the general order above and requires no fixture-specific rule.

---

# 18. Canonical reduction operator

For any finite branch set \(X\), define:

\[
\boxed{
R(X)
}
\]

as the set obtained by deleting only labels/branch portions that are safely dominated under M5-T2 at the same energy and same discrete state index.

The reduction is pointwise over energy and may split PWA branches at:

- existing breakpoints;
- pairwise time intersections;
- interval boundaries.

Because each pair of affine pieces crosses finitely many times, \(R(X)\) remains a finite branch set.

---

# 19. Canonical reduction laws

The reduction must satisfy:

## Idempotence

\[
\boxed{
R(R(X))=R(X).
}
\]

## Soundness

Every deleted attained label is continuation-dominated by a retained attained label.

## Completeness is not required

v1 does not require \(R\) to remove every mathematically dominated label.

It is intentionally conservative.

Correctness dominates compression aggressiveness.

---

# 20. The central architecture theorem: transition congruence

Previous B2 theory lacked this requirement.

For every legal transition operator \(T\), v1 requires:

\[
\boxed{
R(T(R(X)))=R(T(X)).
}
\]

This means:

> reducing first and then applying a transition yields the same exact reduced continuation set as applying the transition to every original label and reducing afterward.

This is the formal condition that prevents a deleted prefix from becoming useful again later.

---

# 21. Drive congruence

For a fixed leg with time \(T\) and energy \(c\):

\[
E'=E-c,
\]

\[
t'=t+T,
\]

\[
\rho'=\rho+c.
\]

If A safely dominates B before the drive:

\[
t_A\le t_B,
\qquad
\rho_A\le\rho_B,
\]

then afterward:

\[
t_A+T\le t_B+T,
\]

\[
\rho_A+c\le\rho_B+c.
\]

The same action is appended to both histories.

Thus safe dominance is preserved.

Therefore:

\[
\boxed{
R(D(R(X)))=R(D(X)).
}
\]

---

# 22. Schedule congruence

The schedule operator is:

\[
S(t)=\max(a,t+h)+D
\]

subject to the hard window.

It is monotone nondecreasing.

Thus:

\[
t_A\le t_B
\Rightarrow
S(t_A)\le S(t_B).
\]

Also:

\[
\rho'_A=\rho_A,
\qquad
\rho'_B=\rho_B.
\]

Therefore safe dominance is preserved even if strict time differences collapse to equality.

This is exactly why \(\rho\) must be retained.

Hence:

\[
\boxed{
R(S(R(X)))=R(S(X)).
}
\]

---

# 23. Charge congruence

For one concrete charging Site and fixed output energy \(E_d\), an input label at energy \(E_a\) incurs:

\[
t'
=
t
+
h
+
F(E_d)-F(E_a),
\]

with:

\[
E_a<E_d
\]

for semantic C.

For two safely ordered labels at the same \(E_a\):

\[
t_A\le t_B,
\qquad
\rho_A\le\rho_B,
\]

charging them to the same \(E_d\) yields:

\[
t'_A\le t'_B,
\]

\[
\rho'_A=\rho_A\le\rho_B=\rho'_B.
\]

Therefore a safely dominated input cannot become useful after charging.

The branchwise exact C transform may minimize over all feasible \(E_a<E_d\) because dominated points at each \(E_a\) have safe replacements at that same energy.

Hence:

\[
\boxed{
R(C(R(X)))=R(C(X)).
}
\]

Strict-positive attainment remains explicit.

---

# 24. Combined CS congruence

For a fixed input energy \(E_a\) and output energy \(E_d>E_a\), CS completion is:

\[
\max
\left\{
t+h+F(E_d)-F(E_a),
\max(a,t+h)+D
\right\}.
\]

Both arguments are monotone nondecreasing in \(t\).

Thus a safely dominant input remains no worse after the same CS action.

\[
\rho
\]

remains unchanged by charging/schedule activity.

Therefore:

\[
\boxed{
R(CS(R(X)))=R(CS(X)).
}
\]

---

# 25. Consequence

The set of exact transition operators:

\[
\{D,S,C,CS\}
\]

is compatible with canonical reduction.

Therefore a prefix deleted by \(R\) cannot later become the accepted winner after any finite legal suffix.

This is the core correctness property that the previous theory failed to establish.

---

# 26. Branchwise charging closure

For a fixed branch with constant \(\rho\):

\[
b=(I,t(E),\rho,\pi,A,w),
\]

the exact C output time is:

\[
t_C(E_d)
=
h+
\inf_{E_a<E_d}
\left[
t(E_a)+F(E_d)-F(E_a)
\right].
\]

Since both:

\[
t
\]

and:

\[
F
\]

are finite PWA, the strict-prefix infimum has a finite PWA value representation.

Attainment is stored separately.

The output branch keeps:

\[
\boxed{
\rho_C=\rho.
}
\]

Its discrete tuple becomes:

\[
\pi_C=\pi\Vert(s,C).
\]

---

# 27. Branchwise CS closure

For one branch:

\[
t_{CS}(E_d)
=
\inf_{E_a<E_d}
\max
\left\{
t(E_a)+h+F(E_d)-F(E_a),
\max(a,t(E_a)+h)+D
\right\}
\]

subject to schedule feasibility.

The finite PWA charging/schedule regime decomposition gives a finite PWA value function.

Attainment is explicit.

The output keeps:

\[
\rho_{CS}=\rho.
\]

Tuple:

\[
\pi_{CS}
=
\pi\Vert(s,CS).
\]

---

# 28. Strict-positive semantics and unattained infima

Executable C/CS requires:

\[
q>0.
\]

Therefore some infima may be approached only as:

\[
q\downarrow0
\]

without being attained.

v1 represents:

- infimal value;
- attainment status;
- executable witness if attained.

A limit-only object may provide a lower bound.

It may not:

- update the incumbent;
- be returned as an executable plan;
- delete an attained branch solely through its unattained key.

A pathological query whose global infimum is unattained is reported as:

\[
\boxed{
\texttt{infimum\_unattained}.
}
\]

This is exact behavior, not an implementation failure.

---

# 29. Finite representation theorem

## Theorem M5-T3

Assume:

- finite concrete Site set;
- finite action-effect classes;
- finite charging-curve segments;
- finite stop depth \(H_{\max}\).

Then the exact reduced frontier is finite after every expansion.

### Reason

For any fixed discrete prefix family:

- \(\rho\) is constant;
- time is finite PWA over energy;
- attainment partition is finite.

At depth \(k\), only finitely many discrete effect-labelled Site sequences exist.

Each sequence generates finitely many branch pieces.

Pairwise safe-dominance relations change only at finitely many PWA intersections and endpoints.

Therefore reduction produces finitely many surviving pieces.

No SOC discretization is required.

---

# 30. Finite depth contract

The exact production domain requires a verified finite executable incumbent:

\[
U_J<+\infty.
\]

Let:

\[
h_{\min}>0
\]

be minimum stop overhead and:

\[
\lambda_{\rm stop}>0.
\]

Define:

\[
\eta=h_{\min}+\lambda_{\rm stop}>0.
\]

Every semantic stop contributes at least:

\[
\eta
\]

to primary objective.

Thus any plan that can primary-tie or improve incumbent satisfies:

\[
H\eta\le U_J.
\]

Therefore:

\[
\boxed{
H
\le
H_{\max}
=
\left\lfloor
\frac{U_J}{\eta}
\right\rfloor.
}
\]

This is an instance-derived exact depth bound, not an arbitrary stop cap.

The primary deployable research domain is therefore feasible queries supplied with a verified finite incumbent.

Arbitrary unlimited-stop infeasibility detection is not claimed by v1.

---

# 31. Terminal evaluation

A terminal state is executable only if:

\[
r=0
\]

and destination reserve holds.

For every attained terminal branch point, construct:

\[
K=
(J,Q,H,\Pi).
\]

The incumbent is the lexicographically smallest attained terminal key found so far.

A limit-only terminal infimum does not become an incumbent.

---

# 32. Hierarchy principle

The hierarchy may abstract **next-action sets**.

It may not abstract the current value state.

The exact current frontier:

\[
\mathcal F_{v,r,k}
\]

remains concrete.

An abstract next-action node is:

\[
\boxed{
N=
(\mathcal F_{v,r,k},R,\alpha)
}
\]

where:

- \(R\): frozen static Region;
- \(\alpha\in\{C,S,CS\}\): effect class.

The Region is only a compact representation of candidate concrete next actions.

---

# 33. Region-never-value-state principle

The one-stop principle:

\[
\text{Region is never a feasibility boundary}
\]

is strengthened for multi-stop:

\[
\boxed{
\textbf{Region is never a physical state, value state, or executable action.}
}
\]

No:

- Region centroid;
- Region-average SOC;
- Region-average charge;
- Region-average time;
- Region-compressed frontier

may replace the exact current frontier.

The hierarchy may only prune or refine sets of next concrete actions.

---

# 34. Action coverage

For each exact current frontier and effect class:

\[
\mathcal A_\alpha(\mathcal F,R)
\]

is the concrete action set represented by Region \(R\).

If:

\[
R=R_1\dot\cup R_2,
\]

then exact refinement must satisfy:

\[
\boxed{
\mathcal A_\alpha(\mathcal F,R)
=
\mathcal A_\alpha(\mathcal F,R_1)
\dot\cup
\mathcal A_\alpha(\mathcal F,R_2).
}
\]

No action may disappear or duplicate.

---

# 35. Region lower-bound contract

A Region/action node may carry a primary lower bound:

\[
\boxed{
L_J(N)
\le
\inf
\left\{
J(p):
p\text{ is a complete continuation represented by }N
\right\}.
}
\]

The exact formula may use frozen B1-D2 metric ingredients and multi-stop relaxations.

The core theory requires only admissibility.

It does not require a secondary charge lower bound.

---

# 36. Full-key-safe pruning

Suppose current incumbent is:

\[
K_U=
(U_J,U_Q,U_H,U_\Pi).
\]

With only a primary lower bound \(L_J\):

\[
\boxed{
L_J(N)>U_J
\Rightarrow
\text{safe prune}.
}
\]

But:

\[
\boxed{
L_J(N)=U_J
}
\]

is **not** sufficient for pruning.

The node may contain an equal-primary plan with:

\[
Q<U_Q
\]

or a better later tie component.

Equality pruning is allowed only if a separately proved lexicographic lower-bound certificate establishes:

\[
K_{LB}(N)
\ge_{\rm lex}
K_U.
\]

v1 does not require such a certificate.

---

# 37. OPEN exactness invariant

Every feasible complete plan not already proven lexicographically no better than the incumbent must remain represented by one of:

1. an exact current frontier branch;
2. an unpruned Region/action node;
3. an exact materialized successor frontier;
4. a continuation-safe dominance witness.

No other disappearance is permitted.

---

# 38. Exact termination

With only primary Region lower bounds, exact search may terminate when all remaining OPEN nodes satisfy:

\[
\boxed{
L_J(N)>U_J.
}
\]

Equivalently, after all equal-primary possibilities have been materialized, exhausted, or lexicographically certified.

A primary-equality node cannot be ignored.

At termination, incumbent is the exact lexicographic optimum among attained executable plans.

If the global best value is limit-only and strictly better than every attained incumbent, return:

\[
\texttt{infimum\_unattained}.
\]

---

# 39. Independent reference solver

Small-domain validation uses a REF solver that is independent from frontier reduction.

REF must:

- enumerate discrete effect-labelled Site sequences;
- enumerate finite charging/schedule/max regimes;
- solve the resulting continuous subproblems;
- distinguish attained and unattained optima;
- return the full key:
  \[
  (J,Q,H,\Pi).
  \]

REF must not call:

- branch Pareto reduction;
- frontier merge;
- hierarchical Region bounds.

Agreement with REF is the correctness authority for B21.

---

# 40. Algebraic validation laws

Before example-based validation, implementation must test the architecture laws.

## A1 — reduction idempotence

\[
R(R(X))=R(X).
\]

## A2 — Drive congruence

\[
R(D(R(X)))=R(D(X)).
\]

## A3 — S congruence

\[
R(S(R(X)))=R(S(X)).
\]

## A4 — C congruence

\[
R(C(R(X)))=R(C(X)).
\]

## A5 — CS congruence

\[
R(CS(R(X)))=R(CS(X)).
\]

## A6 — merge commutativity

\[
R(X\cup Y)=R(Y\cup X).
\]

## A7 — merge associativity

\[
R(R(X\cup Y)\cup Z)
=
R(X\cup R(Y\cup Z)).
\]

## A8 — complete-key preservation

Running with reduction enabled and disabled on the same finite exact domain must return the same full key/status.

## A9 — limit-only nondeletion

An unattained branch cannot delete an attained branch solely by an unattained key.

## A10 — primary-equality prune safety

A node with:

\[
L_J=U_J
\]

must remain live unless a full-key lower-bound certificate exists.

These laws are mandatory before large case suites.

---

# 41. Mandatory regression from failed B21

The blocking case becomes permanent.

Required exact result:

\[
J=44950\ {\rm s},
\]

\[
Q=76\ {\rm kWh},
\]

\[
H=3,
\]

\[
\Pi=
(Site\ 2,C)
\rightarrow
(Site\ 3,C)
\rightarrow
(Site\ 4,S).
\]

The alternative 83 kWh prefix may be present but must not win.

A solver returning only the correct \(J\) fails.

---

# 42. Additional adversarial regressions

Before generated suites, include:

1. earlier/higher-Q vs later/lower-Q before a full waiting plateau;
2. partial waiting-gap collapse;
3. no waiting plateau;
4. equal time / unequal Q;
5. equal time / equal Q / different tuple;
6. cross-energy pair that old high-SOC dominance would incorrectly compare;
7. primary Region bound exactly equal to incumbent with a better-Q plan inside;
8. unattained q→0 lower limit versus attained alternative;
9. multiple PWA time intersections between two \(\rho\)-branches;
10. same discrete prefix with different charge allocations but same final \(E\), verifying identical \(Q\).

---

# 43. What v1 deliberately does not optimize

v1 correctness does not rely on:

- cross-energy dominance;
- cross-\(k\) dominance;
- advanced lexicographic Region lower bounds;
- Site-repeat elimination;
- frontier approximation;
- SOC discretization;
- user-specific utility;
- stochastic occupancy;
- active information.

These may be future performance/product extensions.

They cannot be introduced into B21 without a separate theorem.

---

# 44. Why this is not an engineering patch

The corrected architecture does not say:

> "retain one extra variable because one test failed."

It says:

1. define the final lexicographic objective first;
2. define continuation dominance semantically;
3. derive a conservation-law resource coordinate;
4. retain exactly the Pareto information required by the continuation preorder;
5. prove reduction/transition congruence;
6. allow hierarchy to abstract actions only;
7. align branch-and-bound termination with the full final order.

The failed waiting example is one witness that motivates this structure.

The structure itself is defined independently of that example.

---

# 45. Main theorems required before implementation authority

This document asserts the architecture and provides proof sketches.

Before B21 resumes, the following theorem checklist must be independently audited.

## M5-C1

Physical state sufficiency.

## M5-C2

Energy-conservation identity and \(\rho\) transition law.

## M5-C3

Same-state Pareto dominance implies continuation dominance.

## M5-C4

Canonical reduction is finite and idempotent.

## M5-C5

Drive/S/C/CS transition congruence.

## M5-C6

Branchwise C/CS finite PWA closure with strict-positive attainment.

## M5-C7

Finite-depth theorem from verified incumbent.

## M5-C8

Full-key-safe Region pruning and OPEN termination.

## M5-C9

Hierarchy action coverage/refinement exactness.

## M5-C10

Independent REF contract.

No implementation prompt should be rewritten until C1–C10 are accepted.

---

# 46. B21 restart rule

The failed B21 attempt is not resumed in place.

After this core theory passes an independent theorem audit:

1. create a new B21 protocol version;
2. create a new Codex prompt;
3. preserve the old failed attempt unchanged;
4. rerun preservation and baseline tests;
5. restart Stage A from case 1;
6. run algebraic laws A1–A10 before the original hand cases;
7. only then proceed to generated and bounded-real suites.

Do not continue from the previously failed case number.

---

# 47. Progress discipline

This reset is intended to prevent amendment proliferation.

After v1.0:

- correctness defects may revise the core theory;
- performance disappointments may not revise the core semantics;
- no "R2/R3" patch chain is allowed for local performance tuning;
- any new state compression must come with a continuation-congruence theorem;
- any new pruning rule must be full-key safe.

If v1.0 fails again on a fundamental theorem, stop and reassess the exact multi-stop success endpoint rather than stacking local patches.

---

# 48. Current authorization state

At the moment this document is created:

\[
\boxed{
\textbf{B21 remains blocked.}
}
\]

No B2-2 / long-haul work is authorized.

The next artifact must be:

\[
\boxed{
\texttt{MILESTONE\_5\_MULTISTOP\_CORE\_THEORY\_AUDIT\_V1.md}
}
\]

It must attack M5-C1 through M5-C10 adversarially.

Only if that audit passes should the B21 protocol and implementation prompt be rewritten.

---

# 49. Final statement

The multi-stop research question is not:

\[
\text{"which prefix is currently earliest?"}
\]

It is:

\[
\boxed{
\textbf{"which prefix information is sufficient to preserve the final lexicographic optimum under every legal future continuation?"}
}
\]

For the frozen deterministic research domain, v1 answers:

\[
\boxed{
\textbf{exact multi-stop state is represented by finite PWA energy branches carrying }(t,\rho,\pi)\textbf{ Pareto information, with continuation-safe reduction.}
}
\]

The hierarchy may reduce next-action search.

It may not reduce away information required by the continuation preorder.
