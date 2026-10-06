# HiRoute — Latest Research Master Plan

**Working title:** Hierarchical Exact Active Route Recommendation for Electric-Vehicle Stop Planning  
**Project:** dy-HiRoute  
**Research endpoint:** deterministic exact multi-stop hierarchical planning + deployable evaluation + independent holdout  
**Scope:** user-agnostic academic core; uncertainty, active information, personalization, and product behavior are future layers  
**Status of the mathematical core:** one-stop substrate is frozen; the multi-stop exact solver is gated on proving the attainment-aware semantic quotient described below

---

## 1. Research question

HiRoute studies a route-planning problem that is deliberately narrower than a general POI recommender and broader than classical shortest-path routing.

The primary decision is:

\[
\boxed{
\text{Where should the vehicle stop, when should it stop, and how long should it stay?}
}
\]

The system plans **vehicle stops** rather than consumer choices. A stop is justified only by a modeled routing effect, such as charging or satisfying a hard scheduled requirement.

The research objective is to obtain an exact deterministic multi-stop planner that:

1. preserves the physical route/energy/schedule decision problem;
2. avoids explicit evaluation of most valid next-stop decisions through a static hierarchy and admissible lower bounds;
3. handles continuous charging without SOC discretization;
4. preserves the complete lexicographic solution key, not only primary travel time;
5. exposes correctness through an independent exact reference solver;
6. is evaluated first on development instances and later on an independent holdout.

---

## 2. Scientific contribution

The intended contribution has four layers.

### 2.1 Stop-planning formulation

A route recommendation is not only a road path. It jointly determines:

\[
\text{route}
+
\text{stop sequence}
+
\text{stop effect}
+
\text{charging quantity}
+
\text{schedule timing}.
\]

### 2.2 Exact continuous multi-stop semantics

Charging energy remains continuous. The exact solver must not use:

- an SOC grid;
- arbitrary minimum charging quanta;
- a fixed target SOC such as 80% or 100%;
- a finite hand-picked charging-action set.

### 2.3 Hierarchical action search

Static geographic Regions organize **candidate next actions**. Regions are never:

- executable stops;
- physical states;
- value states;
- feasibility boundaries.

The hierarchy may prune/refine action sets only.

### 2.4 Decision-preserving compression

All state compression must be justified by continuation semantics:

\[
\boxed{
\text{a discarded prefix must remain useless under every legal future continuation}.
}
\]

This is the central theoretical standard for the multi-stop planner.

---

## 3. Scope and non-goals

### Included in the deterministic core

- directed road graph;
- fastest-time routing;
- actual length of the selected fastest-time route for energy;
- finite battery capacity;
- continuous charging;
- multiple charging stops;
- at most one generic hard scheduled-stop requirement in the primary multi-stop domain;
- C, S, and CS stop effects;
- waiting;
- charging/schedule concurrency at the same stop;
- exact lexicographic optimization;
- static Region hierarchy;
- admissible hierarchical pruning;
- independent exact reference validation.

### Excluded from the core

- learned user profiles;
- personalized utility learning;
- stochastic charger occupancy;
- uncertain road conditions;
- active information acquisition;
- POMDP/policy-tree planning;
- dynamic pricing;
- battery degradation utility;
- history-dependent POI utility;
- arbitrary multiple heterogeneous scheduled requirements.

These may be layered on later without changing the core scientific endpoint.

---

## 4. Static world

The static world is:

\[
\boxed{
W^0=(G,O,\mathcal S^0,\mathcal R^0)
}
\]

where:

- \(G=(V,E)\): directed legal road graph;
- \(O\): raw located opportunities;
- \(\mathcal S^0\): attached Stop Sites;
- \(\mathcal R^0\): frozen static Region hierarchy.

The static abstraction is user-agnostic.

### 4.1 Current frozen research substrate

The accepted development substrate contains:

- 60,498 attached Stop Sites;
- 2,047 Regions;
- 1,024 leaves;
- hierarchy depth 0–10;
- leaf target approximately 64 Sites;
- frozen directed landmarks;
- frozen Region boundary information;
- frozen one-stop correctness/performance evidence.

The static hierarchy is topology-first and does not depend on user preferences.

---

## 5. Route semantics

For any concrete ordered pair \(u,v\), let:

\[
d_T(u,v)
\]

be the travel time of the selected fastest directed legal route.

Let:

\[
L_T(u,v)
\]

be the **actual physical length of that selected fastest-time route**.

The energy model uses \(L_T\), not an independently shortest-distance path.

Do not assume:

\[
L_T(u,v)
\]

obeys a triangle inequality.

For admissible metric lower bounds, define directed shortest physical road distance:

\[
d_D(u,v),
\]

on the same legal edge set, satisfying:

\[
\boxed{
d_D(u,v)\le L_T(u,v).
}
\]

---

## 6. Stop semantics

A semantic stop action has the form:

\[
a=(s,\alpha,q),
\]

where:

- \(s\in\mathcal S^0\): concrete Stop Site;
- \(\alpha\in\{C,S,CS\}\): performed effect;
- \(q\): charged energy where relevant.

### C

Positive charging is actually performed:

\[
q>0.
\]

### S

The stop actually satisfies the hard scheduled requirement.

### CS

Both effects are performed at the same stop.

A route-shaping visit with no modeled effect is not a semantic stop.

A zero-stop trip is represented separately.

---

## 7. Physical state

The deterministic physical Markov state is:

\[
\boxed{
x=(v,t,E,r)
}
\]

where:

- \(v\): current concrete anchor;
- \(t\): absolute completion time at the anchor;
- \(E\): current battery energy;
- \(r\in\{0,1\}\): whether the generic hard scheduled requirement remains unsatisfied.

The frozen primary domain contains no history-dependent physical constraint, so future physical feasibility depends on the past only through \(x\).

Optimization metadata is deliberately kept separate from physical state.

---

## 8. Energy dynamics

For a concrete drive leg \(u\to v\):

\[
c(u,v)=\kappa L_T(u,v),
\]

and:

\[
E' = E-c(u,v).
\]

Battery constraints are:

\[
E_{\min}\le E\le E_{\max}.
\]

Destination arrival must satisfy:

\[
E_z\ge E_{\rm reserve}.
\]

The reserve is a hard floor, not a reward.

---

## 9. Charging model

The implementation baseline uses the frozen finite positive piecewise charging law.

On the accepted 60 kWh model:

\[
P(E)=
\begin{cases}
100\text{ kW}, & 0\le E\le30,\\
60\text{ kW}, & 30<E\le48,\\
30\text{ kW}, & 48<E\le60.
\end{cases}
\]

Define the cumulative primitive:

\[
\boxed{
F(E)=3600\int_0^E\frac{1}{P(u)}\,du.
}
\]

For the current baseline:

\[
F(E)=
\begin{cases}
36E, & 0\le E\le30,\\
60E-720, & 30<E\le48,\\
120E-3600, & 48<E\le60.
\end{cases}
\]

Exact charging time is:

\[
\boxed{
C(a,b)=F(b)-F(a).
}
\]

The multi-stop theory requires only that the exact charging primitive be finite, positive-power, and piecewise affine.

---

## 10. Scheduled-stop model

The primary multi-stop domain contains at most one hard scheduled requirement:

\[
[a,b],\qquad D,
\]

where:

- service may not start before \(a\);
- service must start no later than \(b\);
- required duration is \(D\).

If a stop is reached at time \(t\) and incurs stop overhead \(h_s\), scheduled service completes at:

\[
\boxed{
S_s(t)=\max(a,t+h_s)+D
}
\]

when the hard window is feasible.

Waiting is allowed.

For CS, charging and scheduled activity may overlap. The completion time is a makespan of charging and schedule completion.

---

## 11. Plan

An executable plan is:

\[
p=(\Gamma,E_1,\ldots,E_H),
\]

where:

- \(\Gamma\): concatenated selected-fastest route legs;
- \(E_i\): semantic stop event;
- \(H\): endogenous number of semantic stops.

No fixed stop count is assumed.

---

## 12. Exact objective

The complete accepted solution key is:

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

and is minimized lexicographically.

Primary objective:

\[
\boxed{
J(p)=T_{\rm clock}(p)+\lambda_{\rm stop}H(p).
}
\]

Secondary key:

\[
Q(p)=\sum_i q_i.
\]

Tertiary key:

\[
H(p).
\]

Final deterministic tie key:

\[
\Pi(p)=((s_1,\alpha_1),\ldots,(s_H,\alpha_H)).
\]

A hard requirement miss is infeasible.

The exact algorithm is incorrect if it returns the right \(J\) but a worse \(Q\), \(H\), or \(\Pi\).

---

# Part II — Exact Multi-Stop Semantic Core

## 13. Why the multi-stop state requires a semantic quotient

With strict:

\[
q>0,
\]

the set of executable completion times for one discrete prefix may have an infimum but no minimum.

Therefore the exact multi-stop abstraction must not assume that every prefix family has an earliest attained representative.

The primitive object is the **attainable completion-time set**.

---

## 14. Discrete prefix family

Let:

\[
\pi=
((s_1,\alpha_1),\ldots,(s_k,\alpha_k))
\]

be a fixed concrete effect-labelled stop prefix.

For a fixed anchor \(v\), remaining requirement state \(r\), and energy \(E\), define:

\[
\boxed{
\mathcal T_\pi(E)
=
\{t:
\text{there exists an executable realization of }\pi
\text{ ending at }(v,t,E,r)
\}.
}
\]

If the set is empty, the prefix is infeasible at energy \(E\).

---

## 15. Conservation-law secondary coordinate

Let:

- \(E_0\): initial energy;
- \(Q\): cumulative charged energy;
- \(C_{\rm drive}\): cumulative drive-energy consumption.

Then:

\[
E=E_0+Q-C_{\rm drive}.
\]

Define:

\[
\boxed{
\rho=Q-E=C_{\rm drive}-E_0.
}
\]

Therefore:

\[
\boxed{
Q=E+\rho.
}
\]

For a fixed discrete prefix \(\pi\), all route legs are fixed, hence:

\[
\boxed{
\rho_\pi=\text{constant}.
}
\]

Thus at fixed final energy, all charging allocations realizing the same discrete prefix have the same total charged energy.

---

## 16. Time cut

For every nonempty \(\mathcal T_\pi(E)\), define:

\[
\boxed{
\tau_\pi(E)=\inf\mathcal T_\pi(E)
}
\]

and endpoint attainment:

\[
\boxed{
\chi_\pi(E)
=
\mathbf 1[
\tau_\pi(E)\in\mathcal T_\pi(E)
].
}
\]

The pair:

\[
\boxed{
c_\pi(E)=(\tau_\pi(E),\chi_\pi(E))
}
\]

is the lower time cut of the executable family.

Interpretation:

- \(\chi=1\): the lower boundary is executable;
- \(\chi=0\): the lower boundary is not executable, but executable realizations exist arbitrarily close above it.

The cut is semantic state, not merely a lower bound.

---

## 17. Time-substitutability order

For two nonempty executable families A and B at the same physical index and energy, define:

\[
c_A\preceq_t c_B
\]

iff every attained time of B can be matched by an attained time of A that is no later.

For lower cuts this is equivalent to:

\[
\boxed{
c_A\preceq_t c_B
\iff
\left[
\tau_A<\tau_B
\right]
\lor
\left[
\tau_A=\tau_B
\land
(\chi_A=1\lor\chi_B=0)
\right].
}
\]

The only equal-infimum case in which A fails to time-dominate B is:

\[
\chi_A=0,\qquad \chi_B=1.
\]

---

## 18. Full continuation-safe branch order

At the same:

\[
(v,E,r,k),
\]

let:

\[
b_A=(c_A,\rho_A,\pi_A),
\qquad
b_B=(c_B,\rho_B,\pi_B).
\]

A is continuation-safe no worse than B if:

\[
c_A\preceq_t c_B,
\]

\[
\rho_A\le\rho_B,
\]

and, when:

\[
\rho_A=\rho_B,
\]

also:

\[
\pi_A\le_{\rm lex}\pi_B.
\]

This order is designed so that for every executable suffix of B, A can choose an executable representative no later than B, execute the same suffix, and finish with a lexicographically no-worse complete key.

No cross-energy dominance is assumed in the core.

---

## 19. Candidate exact quotient

For fixed:

\[
(v,r,k),
\]

the current candidate exact semantic frontier is:

\[
\boxed{
\mathcal Q_{v,r,k}
=
\operatorname{ND}
\left\{
(\tau_\pi(E),\chi_\pi(E),\rho_\pi,\pi)
\right\}_{\pi,E}
}
\]

under the continuation-safe order above.

A branch is represented over an energy interval by:

\[
\boxed{
b=
(I,\tau(E),\chi(E),\rho,\pi,w)
}
\]

where:

- \(I\): energy domain with exact open/closed endpoints;
- \(\tau(E)\): infimal completion-time function;
- \(\chi(E)\): endpoint-attainment function;
- \(\rho\): constant;
- \(\pi\): fixed discrete prefix;
- \(w\): realization/approach certificate.

The intended finite representation is:

- \(\tau(E)\): finite PWA;
- \(\chi(E)\): finite piecewise-constant;
- \(\rho,\pi\): branch constants.

This is the current foundational theorem target.

---

## 20. Central semantic-quotient theorem to prove

The multi-stop theory is considered closed only if the following is proved:

\[
\boxed{
(\tau,\chi,\rho,\pi)
\text{ is an exact continuation quotient for the frozen deterministic domain.}
}
\]

More precisely, if two executable prefix families have the same quotient branch at a state/energy, then no legal suffix can distinguish them with respect to:

\[
(J,Q,H,\Pi).
\]

Equivalently, all future operators must factor through this quotient.

This theorem is the immediate research gate before implementation.

---

# Part III — Exact Operator Semantics

## 21. Generic monotone time transform

Many transitions act on incoming time through:

\[
y=\psi(t;z),
\]

where \(\psi\) is continuous, monotone nondecreasing, and piecewise affine in \(t\), and \(z\) denotes other exact transition parameters.

For an input time cut:

\[
(\tau,\chi),
\]

the fixed-\(z\) output infimum is:

\[
\boxed{
\tau'=\psi(\tau;z).
}
\]

If \(\chi=1\), the boundary is attained.

If \(\chi=0\), the boundary is attained after the transform iff the transform is constant on a right neighborhood of \(\tau\) that intersects the feasible time family.

For parameterized transitions, global output attainment additionally requires an admissible parameter value realizing the global infimum.

---

## 22. Drive

For leg \(v\to s\) with:

\[
T=d_T(v,s),
\qquad
c=\kappa L_T(v,s),
\]

the output energy is:

\[
E'=E-c.
\]

Time cut:

\[
\tau'(E')=\tau(E'+c)+T.
\]

Attainment:

\[
\chi'(E')=\chi(E'+c).
\]

Secondary coordinate:

\[
\boxed{
\rho'=\rho+c.
}
\]

---

## 23. Scheduled stop S

For Site \(s\):

\[
\psi_S(t)=\max(a,t+h_s)+D.
\]

Output infimum:

\[
\boxed{
\tau_S(E)=\max(a,\tau(E)+h_s)+D.
}
\]

Let:

\[
\theta=a-h_s.
\]

Endpoint attainment:

\[
\chi_S(E)=
\begin{cases}
1, & \tau(E)<\theta,\\
\chi(E), & \tau(E)\ge\theta.
\end{cases}
\]

subject to the hard latest-start window.

The requirement state changes:

\[
r:1\to0.
\]

\[
\rho_S=\rho.
\]

---

## 24. Charging stop C

For output energy \(E_d\), semantic charging requires:

\[
E_a<E_d.
\]

For one prefix branch:

\[
\boxed{
\tau_C(E_d)
=
h_s
+
F(E_d)
+
\inf_{E_a<E_d}
[
\tau(E_a)-F(E_a)
].
}
\]

The output secondary coordinate remains:

\[
\boxed{
\rho_C=\rho.
}
\]

The output attainment flag is one iff there exists an admissible minimizing \(E_a<E_d\) and an executable realization whose transformed completion time equals \(\tau_C(E_d)\).

If the infimum is approached only through an open input cut, an excluded strict boundary, or an unattained minimizing regime, then:

\[
\chi_C(E_d)=0.
\]

The open cut remains semantic state.

---

## 25. Combined stop CS

For fixed \(E_a<E_d\):

\[
c_{\rm ch}(t,E_a,E_d)
=
t+h_s+F(E_d)-F(E_a),
\]

\[
c_{\rm sch}(t)
=
\max(a,t+h_s)+D,
\]

\[
\boxed{
\psi_{CS}(t,E_a,E_d)
=
\max\{
c_{\rm ch},
c_{\rm sch}
\}.
}
\]

Then:

\[
\boxed{
\tau_{CS}(E_d)
=
\inf_{E_a<E_d}
\psi_{CS}(\tau(E_a),E_a,E_d).
}
\]

Attainment must be evaluated exactly from:

- input cut attainment;
- strict \(E_a<E_d\);
- active PWA regime;
- whether a time plateau maps an open input cut to the output boundary.

The output requirement flag is:

\[
r:1\to0,
\]

and:

\[
\rho_{CS}=\rho.
\]

---

## 26. Canonical quotient reduction

Let:

\[
\mathscr R(X)
\]

remove only branch portions continuation-dominated under the cut/\(\rho\)/tuple order.

For every exact transition:

\[
T\in\{D,S,C,CS\},
\]

the quotient must satisfy:

\[
\boxed{
\mathscr R(T(\mathscr R(X)))
\equiv
\mathscr R(T(X)),
}
\]

where equivalence is semantic equality of continuation-relevant executable families, not byte-identical branch segmentation.

No implementation is authorized until this congruence is proved for the time-cut quotient.

---

## 27. Finite representation target

Under:

- finite Site/action branching;
- finite stop depth;
- finite PWA charging law;
- one hard scheduled requirement;
- monotone PWA time operators;

the quotient frontier is conjectured to remain representable by finitely many branches with:

\[
\tau(E)
\]

piecewise affine and:

\[
\chi(E)
\]

piecewise constant over a finite partition.

This finite-closure theorem is the decisive condition for an exact continuous implementation without SOC discretization.

---

# Part IV — Hierarchical Exact Search

## 28. Hierarchy role

The hierarchy abstracts only the next-action set.

A search node is conceptually:

\[
\boxed{
N=(\mathcal Q_{v,r,k},R,\alpha)
}
\]

where:

- \(\mathcal Q_{v,r,k}\): exact current semantic frontier;
- \(R\): frozen static Region;
- \(\alpha\in\{C,S,CS\}\): performed effect.

A Region is never a physical location, approximate current state, executable stop, or charging surrogate.

---

## 29. Action coverage

For current frontier \(\mathcal Q\), Region \(R\), and effect \(\alpha\), define:

\[
\mathcal A_\alpha(\mathcal Q,R)
\]

as the concrete Site/effect actions represented by the node.

If \(R\) has children \(R_1,\ldots,R_m\), exact refinement requires:

\[
\boxed{
\mathcal A_\alpha(\mathcal Q,R)
=
\dot\bigcup_j
\mathcal A_\alpha(\mathcal Q,R_j).
}
\]

Required invariants:

\[
\text{lost actions}=0,
\]

\[
\text{duplicate actions}=0.
\]

---

## 30. Metric lower bounds

The multi-stop current anchor changes after every stop.

### Current anchor to Region

Use directed ALT point-to-Region lower bound:

\[
\underline T^-(v,R).
\]

### Region to fixed destination

Use:

\[
\underline T^+(R,z)
=
\max\{
\underline T_{\rm ALT}(R,z),
\underline T_{\rm boundary}(R,z)
\}.
\]

Distance analogues use \(d_D\) where physical-distance lower bounds are needed.

---

## 31. Baseline admissible Region bound

The first exact multi-stop hierarchy should prefer a weak proof-clean bound over an aggressive unproved one.

For C:

\[
L_C(N)
=
\inf_{b,E}
[
\tau_b(E)
+
\underline T^-(v,R)
+
h_{\min,R}
+
\underline T^+(R,z)
]
-t_0
+
\lambda_{\rm stop}(k+1).
\]

For S, let:

\[
\underline a
=
\tau_b(E)
+
\underline T^-(v,R)
+
h_{\min,R}.
\]

Then:

\[
L_S(N)
=
\inf_{b,E}
[
\max(a,\underline a)
+
D
+
\underline T^+(R,z)
]
-t_0
+
\lambda_{\rm stop}(k+1).
\]

CS may use the same schedule-based lower bound as S because semantic positive charging has zero infimal duration.

These are relaxations and remain valid even if the relaxed direct leg is physically infeasible.

---

## 32. Full-key-safe pruning

Suppose incumbent:

\[
K_U=(U_J,U_Q,U_H,U_\Pi).
\]

With only a primary lower bound:

\[
\boxed{
L_J>U_J
}
\]

is sufficient to prune.

But:

\[
\boxed{
L_J=U_J
}
\]

is not sufficient.

An equal-primary continuation may improve \(Q\), \(H\), or \(\Pi\).

Equality pruning requires a separately proved lexicographic lower-bound certificate.

---

## 33. Finite-depth exactness

Let:

\[
h_{\min}>0,
\qquad
\lambda_{\rm stop}>0,
\]

and:

\[
\eta=h_{\min}+\lambda_{\rm stop}.
\]

Given a verified finite executable incumbent:

\[
U_J<\infty,
\]

any plan that can primary-tie or improve it satisfies:

\[
H\eta\le U_J.
\]

Therefore:

\[
\boxed{
H_{\max}
=
\left\lfloor
\frac{U_J}{\eta}
\right\rfloor.
}
\]

This is an instance-derived exact bound.

---

## 34. Search invariant

Every feasible complete plan not already certified lexicographically no better than the incumbent must remain represented by at least one of:

1. an exact quotient branch;
2. an unpruned Region/action node;
3. an exact materialized successor quotient;
4. a continuation-dominance certificate.

Nothing else may make a plan disappear.

---

## 35. Exact termination

With only primary Region lower bounds, exact search terminates when all remaining OPEN nodes satisfy:

\[
\boxed{
L_J>U_J,
}
\]

or have been exhausted/materialized.

If the infimal executable key is not attained, return:

\[
\boxed{
\texttt{infimum\_unattained}.
}
\]

---

# Part V — Validation Architecture

## 36. Independent reference solver

Small-domain correctness is judged by an independent reference solver.

REF must:

- enumerate concrete effect-labelled Site sequences;
- enumerate charging-curve regimes;
- enumerate schedule/max regimes;
- solve exact continuous subproblems;
- distinguish attained and unattained optima;
- return the full key:
  \[
  (J,Q,H,\Pi).
  \]

REF must not use quotient reduction or hierarchy bounds.

---

## 37. Validation order

### Phase T — semantic quotient foundation

Prove or refute:

1. time-cut sufficiency;
2. cut-order characterization;
3. continuation-safe full-key dominance;
4. exact Drive closure;
5. exact S closure;
6. exact C closure with open parameter domains;
7. exact CS closure with plateau-generated attainment;
8. finite PWA/\(\chi\) representation;
9. quotient congruence;
10. finite-depth compatibility.

No production solver work begins before Phase T closes.

### Phase V — algebraic implementation validation

After theorem closure, validate:

\[
\mathscr R(\mathscr R(X))\equiv\mathscr R(X),
\]

and:

\[
\mathscr R(T(\mathscr R(X)))
\equiv
\mathscr R(T(X))
\]

for:

\[
T\in\{D,S,C,CS\}.
\]

Also validate merge laws, full-key preservation, boundary semantics, and equal-primary pruning safety.

### Phase A — exact hand cases

Include adversarial cases for:

- waiting plateaus;
- open charging domains;
- unattained infima;
- plateau-created attainment;
- secondary-key ties;
- tuple ties;
- multiple PWA intersections;
- repeated stops;
- CS branch switches.

### Phase B — deterministic synthetic cases

Use small directed graphs and bounded Site sets with exact REF comparison.

### Phase C — bounded real-data integration

Use the accepted development graph and deterministic small candidate sets.

### Phase D — deployable long-haul development

Only after correctness is frozen.

### Phase H — independent holdout

Only after algorithm and thresholds are frozen.

---

## 38. Hard correctness gates

The multi-stop solver is accepted only if all hold with zero violations:

1. semantic quotient theorem closed;
2. exact charging primitive matches evaluator;
3. operator closure exact;
4. quotient congruence exact;
5. full key matches REF;
6. dominance on/off yields the same result;
7. lost actions = 0;
8. duplicate actions = 0;
9. Region bounds admissible;
10. equal-primary nodes never primary-pruned;
11. no SOC grid or hidden charge discretization;
12. frozen predecessor artifacts unchanged.

No performance threshold may compensate for a correctness failure.

---

## 39. Performance metrics

After correctness is frozen, report:

### Quotient complexity

- branches per discrete state;
- PWA pieces per branch;
- open/closed boundary count;
- branch intersections;
- dominance deletions;
- peak frontier size.

### Hierarchy work

- Regions created;
- Regions refined;
- candidate checks;
- exact Site/action materializations;
- leaf evaluations;
- pruning by bound class.

### Runtime

- routing;
- quotient propagation;
- operator closure;
- Region bound calculation;
- refinement;
- exact materialization;
- total runtime.

### Memory

- active branches;
- OPEN size;
- witness storage.

---

# Part VI — Experimental Substrate and Evaluation Plan

## 40. Development geography

The accepted development substrate is centered on Slovenia and nearby cross-border routing.

Reusable assets include:

- 30 development ODs;
- large directed road graphs;
- attached charging/support Sites;
- frozen Region hierarchy;
- landmark distances;
- Region boundary metadata.

These are development data, not final independent holdout evidence.

---

## 41. Static Site capabilities

The Stop Site substrate may contain overlapping capabilities such as:

- charging;
- meal support;
- accommodation;
- groceries;
- pharmacy;
- rest;
- road services;
- toilets;
- parking.

The multi-stop core uses only capabilities required by current action semantics.

Capabilities remain static and user-agnostic.

---

## 42. User-agnostic principle

The research core does not learn a user profile.

Any exogenous preference parameter is treated as input to a later decision layer, not learned inside the hierarchy.

The exact deterministic core answers:

\[
\boxed{
\text{what stop decisions are feasible and optimal under the declared objective/requirements?}
}
\]

---

# Part VII — Research Milestones

## 43. M5-T — Semantic Quotient Foundation

Deliverable:

`M5_SEMANTIC_QUOTIENT_FOUNDATION.md`

Required theorem closure:

- exact cut semantics;
- continuation order;
- operator closure;
- finite representation;
- quotient congruence.

Decision:

- PASS: authorize exact implementation protocol;
- FAIL: reassess the exact multi-stop representation before coding.

---

## 44. M5-V — Exact Small-Domain Validation

Implement:

- independent REF;
- flat exact quotient solver;
- hierarchical exact quotient solver.

Correctness only.

No scalability gate.

---

## 45. M5-D — Deployable Multi-Stop Development

After M5-V passes:

- freeze deployable lower-bound design;
- run long-haul multi-charge development workloads;
- quantify hierarchy work reduction;
- characterize quotient branch growth;
- optimize only with proved-safe transformations.

No holdout use.

---

## 46. M6-H — Independent Holdout

After all algorithms, thresholds, and metrics are frozen:

- run untouched holdout ODs/geography;
- report exactness;
- runtime;
- hierarchy work;
- failure/NA cases;
- reproducibility.

No post-hoc algorithm modification after holdout inspection.

---

## 47. Publication closure

The final paper should support these claims only if empirically established:

1. exact deterministic multi-stop EV stop planning with continuous charging;
2. a finite exact semantic quotient for open charging domains;
3. continuation-safe hierarchical action pruning;
4. exact full-key agreement with an independent reference on bounded cases;
5. deployable work reduction on long-haul development cases;
6. independent holdout confirmation.

Uncertainty/active-information results are a separate future layer.

---

# Part VIII — Threats, Boundaries, and Future Extensions

## 48. Assumptions that require re-audit if changed

The semantic quotient must be re-audited if the model adds:

- auxiliary battery drain while waiting;
- time-dependent charging power;
- charger opening hours;
- stochastic availability;
- multiple heterogeneous scheduled requirements;
- history-dependent Site bans;
- negative stop rewards;
- battery-degradation utility;
- learned preferences.

These changes may invalidate:

\[
\rho=Q-E
\]

or the time-cut sufficiency theorem.

---

## 49. Future active-information layer

After the deterministic endpoint is complete, partial information may be represented by ambiguity set:

\[
\mathcal B_t.
\]

For candidate solution set \(S\):

\[
MR_K(S;\mathcal B)
=
\sup_{w\in\mathcal B}
[
U^*(w)-\max_{p\in S}U(p,w)
].
\]

Information acquisition is triggered only when regret remains decision-relevant.

The intended architecture is event-triggered receding horizon, not a full POMDP in the first product layer.

This is outside the current research success endpoint.

---

## 50. Final research contract

The project succeeds at the current endpoint when it demonstrates:

\[
\boxed{
\textbf{
deterministic exact multi-stop hierarchical stop planning
+
continuous charging
+
deployable evaluation
+
independent holdout
}
}
\]

under a mathematically closed semantic quotient.

The immediate scientific question is:

\[
\boxed{
\textbf{
Can the attainable-time family of a discrete multi-stop prefix be quotiented exactly by a finite
}(\tau,\chi,\rho,\pi)\textbf{ representation that is closed under Drive, S, C, and CS?
}
}
\]

Only after that question is answered positively should production multi-stop implementation resume.
