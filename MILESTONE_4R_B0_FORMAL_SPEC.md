# Milestone 4R-B0 Formal Specification

**Project:** dy-HiRoute  
**Stage:** Milestone 4R-B0 — Hierarchical Search Model  
**Status:** formal theory candidate after adversarial proof audit  
**Normative predecessor:** `RESEARCH_SPEC_v0.2.md` and accepted `MILESTONE_4R_REPORT.md`  
**Implementation authorization:** **none** — this freezes the mathematical contract for a later B1 experiment; it is not a Codex prompt.

---

## 0. Purpose

Milestone 4R-A fixed the semantics of an EV stop decision. Milestone 4R-B0 defines the mathematical contract for reducing concrete stop-search work **without changing the declared decision problem**.

The central question is

\[
\boxed{
\text{How can a hierarchy avoid evaluating most concrete Stop Sites while preserving a certified optimum, or a declared }\epsilon\text{-optimum?}
}
\]

The hierarchy is not a semantic recommender and is not a physical-feasibility partition.

\[
\boxed{
\textbf{Opportunity Regions compress search, never physical feasibility.}
}
\]

---

# Part I — Declared optimization domain

## 1. Domain discipline

Every correctness statement is relative to an explicitly declared planning domain \(D\).

Let

\[
\mathcal P_D(\ell)
\]

be the feasible plans represented by that domain, and

\[
J_D^*(\ell)=\min_{p\in\mathcal P_D(\ell)}J(p)
\]

its optimum.

No theorem in this document silently upgrades a result within \(D\) into an unrestricted EV-routing optimum.

### 1.1 B1 one-stop validation domain

The intended first validation domain is the accepted 4R-A real-data zero/one-stop domain:

- directed road graph and fastest-time routing semantics inherited from the accepted substrate;
- current origin \(o\) and destination \(z\);
- zero or one concrete Stop Site;
- source-to-Site and Site-to-destination legs use the accepted fastest-time route operator;
- energy consumption uses the **actual path length of those selected fastest-time legs**;
- Sites are drawn from the current Safe Detour Envelope and exact role predicate;
- no Region membership restriction is applied;
- canonical deterministic EV and scheduled-stop semantics from 4R-A;
- no real multi-stop claim.

The B1 exactness target is therefore

\[
\boxed{
\text{exact/exhaustive Site selection within the declared one-stop domain, not unrestricted EV-route optimality.}
}
\]

### 1.2 Safe Detour Envelope boundary

If search is restricted to budget \(B\), any later \(\epsilon\)-optimality certificate is only

\[
\boxed{\epsilon\text{-optimal within the declared envelope/domain}.}
\]

The Safe Detour Envelope guarantees containment of vehicle routes whose **base mobility cost** is at most \(B\); it does not by itself prove that the unrestricted generalized-cost optimum lies in that envelope.

---

## 2. Routing primitives

Let

\[
d_T(u,v)
\]

be the directed shortest-travel-time metric.

Let

\[
\pi_T(u,v)
\]

be the accepted selected fastest-time route, with deterministic tie semantics inherited from the routing substrate.

Define

\[
L_T(u,v)
\]

as the actual road length of \(\pi_T(u,v)\).

Important:

\[
\boxed{
L_T(u,v)\text{ is not assumed to be a shortest-distance metric and is not assumed to satisfy triangle inequality.}
}
\]

This distinction is required because the current 4R-A energy model consumes energy on the actual selected fastest-time legs.

---

## 3. Search state and role

A current partial decision state is

\[
\ell=(o,t_0,E_0,\sigma,\ldots),
\]

where \(o\) is current road state/node, \(t_0\) the trip clock, \(E_0\) current energy, and \(\sigma\) relevant requirement state.

A role

\[
\alpha
\]

describes what the next stop is allowed/required to accomplish in the current branch. Typical deterministic B1 roles are

\[
C,\qquad S,\qquad CS,
\]

for charging-capable, scheduled-stop-capable, and jointly capable stops.

This is **not** a return to primitive `charge_meal` tasks. Requirements remain independent; \(\alpha\) only describes which independent requirements are assigned to the same next stop.

---

# Part II — Static hierarchy and dynamic Region Views

## 4. Static Opportunity Region

Let the concrete Stop Site set be \(\mathcal S\).

A static Opportunity Region is a subset

\[
R\subseteq\mathcal S.
\]

The Region has no permanent ETA, SOC, generalized cost, or decision bound.

A hierarchy

\[
\mathcal T
\]

is a rooted refinement tree over such subsets.

For an internal node \(R\) with children \(R_1,\ldots,R_k\),

\[
R=\bigcup_{i=1}^kR_i.
\]

For the primary B1 design, children should form a disjoint partition:

\[
R_i\cap R_j=\varnothing\quad(i\neq j).
\]

Leaves refine to concrete Sites or a small exact-enumeration bucket.

The hierarchy must be independent of OD pair, current SOC, scheduled window, user preference \(\theta\), and envelope budget.

---

## 5. Role-conditioned Region View

The dynamic search object is

\[
\boxed{N=(R,\alpha,\ell).}
\]

For the current role and trip state, define the exact deterministic role subset

\[
R_\alpha=\{s\in R:\;s\text{ satisfies the concrete role predicate }\alpha\}.
\]

In future partial-information work, **unknown must not be filtered as absent**; B1 uses the deterministic observed-role domain.

A current envelope/admissibility filter may further restrict the Region View, but it must not change the static Region identity.

If \(R_\alpha=\varnothing\), that role branch contains no concrete action and may be discarded.

---

## 6. Exact predicates, approximate metrics

B0 freezes the rule

\[
\boxed{\textbf{Exact predicates, approximate metrics.}}
\]

Discrete/categorical feasibility predicates such as charging capability and scheduled-support satisfaction are filtered exactly in deterministic B1.

Continuous quantities such as travel time, selected-route length, energy requirement, charging duration, and schedule timing may be relaxed only with explicit sound bounds.

---

# Part III — Three distinct certificates

## 7. Admissible lower-bound certificate

For search node \(N=(R,\alpha,\ell)\), let \(\mathcal P_D(N)\) be the concrete plans in the declared domain whose next stop lies in the represented branch.

A lower bound \(L(N)\) is admissible if

\[
\boxed{L(N)\le\min_{p\in\mathcal P_D(N)}J(p).}
\]

Its purpose is **pruning correctness**.

---

## 8. Region Concretization Certificate (RCC)

An RCC describes how far an abstract super-site realization may lie from a concrete Site realization in physically meaningful quantities.

It is a vector, not a user-weighted scalar:

\[
\Gamma_t(N)=(\gamma_1,\ldots,\gamma_m).
\]

Its purpose is:

- safe abstract-to-concrete transfer under sufficient hard-constraint margins;
- deciding whether a coarse Region must be refined;
- diagnosing Region aggregation looseness.

An RCC is not required for pruning when the admissible lower bound already proves the branch decision-irrelevant.

---

## 9. Global optimality certificate

Let \(U\) be the cost of a concrete feasible incumbent and `OPEN` the current frontier.

The global search certificate is

\[
\boxed{U-\min_{N\in OPEN}L(N).}
\]

The lower-bound certificate, RCC, and global optimality certificate are distinct objects and must not be conflated.

---

# Part IV — Trip-conditioned one-stop oracle quantities

## 10. Per-Site dynamic quantities

For each \(s\in R_\alpha\), define

\[
T^-_s=d_T(o,s),\qquad T^+_s=d_T(s,z),
\]

and, using the accepted selected fastest-time legs,

\[
L^-_s=L_T(o,s),\qquad L^+_s=L_T(s,z).
\]

Define component minima

\[
\widehat T^-=\min_sT^-_s,\qquad \widehat T^+=\min_sT^+_s,
\]

\[
\widehat L^-=\min_sL^-_s,\qquad \widehat L^+=\min_sL^+_s.
\]

Define component oscillations

\[
\omega_{T^-}=\max_sT^-_s-\min_sT^-_s,
\]

\[
\omega_{T^+}=\max_sT^+_s-\min_sT^+_s,
\]

\[
\omega_{L^-}=\max_sL^-_s-\min_sL^-_s,
\]

\[
\omega_{L^+}=\max_sL^+_s-\min_sL^+_s.
\]

These quantities are **trip-conditioned and user-agnostic**.

---

## 11. Oracle RCC

Define the primary one-stop oracle certificate

\[
\boxed{
\Gamma_t^{oracle}(N)
=
(\omega_{T^-},\omega_{T^+},\omega_{L^-},\omega_{L^+}).
}
\]

This matches current routing/energy semantics exactly and does not assume that \(L_T\) is a metric.

A deployable certificate \(\Gamma^{deploy}\) must satisfy

\[
\boxed{\Gamma_t^{oracle}\preceq\Gamma^{deploy}}
\]

for every state in its claimed coverage. If a safe static bound for a component is unavailable, use \(+\infty\), not an empirical average.

---

# Part V — B1 model assumptions

## 12. Energy model

For B1,

\[
E_{drive}=\kappa L,
\]

with deterministic \(\kappa>0\).

Let \(E_{min}\) be the execution floor, \(E_{max}\) battery capacity, and \(E_{res}\) destination reserve including any declared robust margin.

For Site \(s\),

\[
E^{arr}_s=E_0-\kappa L^-_s,
\]

\[
E^{req}_s=E_{res}+\kappa L^+_s.
\]

Define optimistic abstract quantities

\[
\widehat E^{arr}=E_0-\kappa\widehat L^-,
\]

\[
\widehat E^{req}=E_{res}+\kappa\widehat L^+.
\]

---

## 13. Charging model

For the primary B1 proof:

- charging-capable Sites use the same declared charging curve;
- Site-specific real charging-performance heterogeneity is not introduced unless supported by data;
- charging power satisfies

\[
P(E)\ge P_{min}>0.
\]

Define

\[
C(a,b)=
\begin{cases}
0,&b\le a,\\[3pt]
\displaystyle\int_a^b\frac{1}{P(E)}\,dE,&b>a.
\end{cases}
\]

When charging is available,

\[
C_s=C(E^{arr}_s,E^{req}_s),
\]

\[
\widehat C=C(\widehat E^{arr},\widehat E^{req}).
\]

Because the abstract arrival energy is optimistic-high and required departure energy optimistic-low,

\[
\widehat C\le C_s.
\]

If the role does not allow charging, charging time is zero and a separate no-charge feasibility margin is required.

---

## 14. Scheduled-stop model

For the primary B1 hard-schedule proof:

- activity duration is fixed \(D\);
- stop overhead is fixed \(h\);
- activity is compatible with charging;
- waiting is allowed;
- activity must start in \([a,b]\).

For Site \(s\),

\[
r_s=t_0+T^-_s+h,
\]

\[
y_s=\max(a,r_s).
\]

Hard feasibility requires

\[
y_s\le b.
\]

The abstract optimistic start is

\[
\widehat y=\max(a,t_0+\widehat T^-+h).
\]

---

# Part VI — Formal results

## Theorem 1 — Directed road-time diameter bound

Let \(A_R\) be the road anchors of \(R_\alpha\).

Define

\[
\Delta_T(R_\alpha)
=
\max_{u,v\in A_R}\max\{d_T(u,v),d_T(v,u)\}.
\]

Assume the relevant directed pair distances are finite.

Then

\[
\omega_{T^-}\le\Delta_T(R_\alpha),
\qquad
\omega_{T^+}\le\Delta_T(R_\alpha).
\]

Further, let

\[
H^*=\min_{s\in R_\alpha}(T^-_s+T^+_s),
\]

and

\[
\widehat H=\widehat T^-+\widehat T^+.
\]

Then

\[
\boxed{0\le H^*-\widehat H\le\Delta_T(R_\alpha).}
\]

### Proof

For any anchors \(u,v\),

\[
d_T(o,u)\le d_T(o,v)+d_T(v,u),
\]

and symmetrically with \(u,v\) reversed. Hence

\[
|d_T(o,u)-d_T(o,v)|
\le
\max\{d_T(u,v),d_T(v,u)\}
\le\Delta_T.
\]

Thus \(\omega_{T^-}\le\Delta_T\); the outbound statement is analogous.

Let

\[
s^-=\arg\min_sT^-_s,
\qquad
s^+=\arg\min_sT^+_s.
\]

Then

\[
H^*\le T^-_{s^-}+T^+_{s^-}.
\]

By triangle inequality,

\[
T^+_{s^-}
\le
d_T(s^-,s^+)+d_T(s^+,z)
\le
\Delta_T+\widehat T^+.
\]

Since \(T^-_{s^-}=\widehat T^-\),

\[
H^*\le\widehat H+\Delta_T.
\]

The lower inequality follows because the relaxed super-site independently minimizes the two terms. ∎

### Limitation

There is **no corresponding theorem for \(L_T\)** without additional assumptions. The actual length of a selected fastest-time path is not assumed to satisfy triangle inequality.

---

## Lemma 2 — Energy and charging perturbation bounds

For any \(s\in R_\alpha\),

\[
0\le\widehat E^{arr}-E^{arr}_s\le\kappa\omega_{L^-},
\]

\[
0\le E^{req}_s-\widehat E^{req}\le\kappa\omega_{L^+}.
\]

Let

\[
q_s=[E^{req}_s-E^{arr}_s]_+,
\qquad
\widehat q=[\widehat E^{req}-\widehat E^{arr}]_+.
\]

Then

\[
\boxed{q_s-\widehat q\le\kappa(\omega_{L^-}+\omega_{L^+}).}
\]

If \(P(E)\ge P_{min}>0\),

\[
\boxed{
C_s-\widehat C
\le
\gamma_C
:=
3600\frac{\kappa(\omega_{L^-}+\omega_{L^+})}{P_{min}}
}
\]

when energy is in kWh, power in kW, and time in seconds.

### Proof sketch

The endpoint-energy inequalities follow directly from the min/max definitions. The positive-part function is 1-Lipschitz. Charging time is an integral of \(1/P(E)\), and \(1/P(E)\le1/P_{min}\); changing the lower and upper endpoints by \(\delta_a,\delta_b\) changes charging duration by at most \((\delta_a+\delta_b)/P_{min}\). ∎

---

## Theorem 3 — Margin-aware one-stop concretization

Consider a nonempty deterministic role-conditioned Region \(R_\alpha\).

Define:

\[
m_{arr}=\widehat E^{arr}-E_{min},
\]

\[
m_{cap}=E_{max}-\widehat E^{req},
\]

and, for a scheduled role,

\[
m_{deadline}=b-\widehat y.
\]

If the role does not permit charging, also define

\[
m_{nocharge}=\widehat E^{arr}-\widehat E^{req}.
\]

If

\[
m_{arr}\ge\kappa\omega_{L^-},
\]

\[
m_{cap}\ge\kappa\omega_{L^+},
\]

and, when scheduled activity is active,

\[
m_{deadline}\ge\omega_{T^-},
\]

then every concrete Site in \(R_\alpha\) preserves:

- arrival energy floor;
- sufficient battery capacity for required departure energy;
- hard scheduled-start deadline.

If charging is not permitted by the role, also require

\[
m_{nocharge}\ge\kappa(\omega_{L^-}+\omega_{L^+}).
\]

Then every concrete Site remains no-charge energy-feasible.

### Proof

For any \(s\),

\[
E^{arr}_s
\ge
\widehat E^{arr}-\kappa\omega_{L^-}
\ge E_{min}.
\]

Similarly,

\[
E^{req}_s
\le
\widehat E^{req}+\kappa\omega_{L^+}
\le E_{max}.
\]

The map \(x\mapsto\max(a,x)\) is 1-Lipschitz. Hence

\[
y_s\le\widehat y+\omega_{T^-}\le b.
\]

For a no-charge role,

\[
E^{arr}_s-E^{req}_s
\ge
m_{nocharge}-\kappa(\omega_{L^-}+\omega_{L^+})
\ge0.
\]

Thus no charging is required. ∎

### Interpretation

This theorem does **not** say that a static Region always has finite scalar abstraction regret.

It says that physical-unit RCCs transfer hard feasibility **when current state margins absorb the certificate**.

If a margin test fails, the correct conclusion is

\[
\boxed{\text{certificate inconclusive — refine the Region}.}
\]

It is not a proof of infeasibility.

---

## Corollary 4 — One-stop aggregation-gap bound

Under Theorem 3 assumptions, use one-stop generalized cost with actual clock time, fixed one-stop nuisance penalty \(\lambda_{stop}\), fixed overhead \(h\), compatible hard scheduled activity of duration \(D\) when active, and no additional distance/context penalty in the primary B1 theorem domain.

For a charging-enabled role, use \(\widehat C\) defined above.

If scheduled activity is active, define abstract stop-completion time

\[
\widehat c
=
\max\left\{
 t_0+\widehat T^-+h+\widehat C,
 a+D,
 t_0+\widehat T^-+h+D
\right\}.
\]

Without scheduled activity,

\[
\widehat c=t_0+\widehat T^-+h+\widehat C.
\]

Define

\[
\widehat J_R
=
(\widehat c-t_0)+\widehat T^++\lambda_{stop}.
\]

Then:

1. \(\widehat J_R\) is an admissible Region lower bound in the declared one-stop domain;
2. for any concrete Site \(s\in R_\alpha\),

\[
\boxed{
J_s-\widehat J_R
\le
\omega_{T^-}+\omega_{T^+}+\gamma_C.
}
\]

For a no-charge role satisfying the no-charge margin, set \(\gamma_C=0\).

Therefore

\[
\boxed{
0\le J_R^*-\widehat J_R
\le
\omega_{T^-}+\omega_{T^+}+\gamma_C,
}
\]

where

\[
J_R^*=\min_{s\in R_\alpha}J_s.
\]

### Proof sketch

For every concrete Site,

\[
T^-_s\ge\widehat T^-,
\qquad
T^+_s\ge\widehat T^+,
\qquad
C_s\ge\widehat C.
\]

Hence each abstract stop-completion term is no larger than its concrete counterpart, proving admissibility.

The charging-completion term can shift by at most \(\omega_{T^-}+\gamma_C\), the absolute scheduled term \(a+D\) does not shift, and the arrival-plus-activity term shifts by at most \(\omega_{T^-}\). Since `max` is 1-Lipschitz under the sup norm, stop completion shifts by at most \(\omega_{T^-}+\gamma_C\). The outbound leg adds at most \(\omega_{T^+}\). ∎

### Extension boundary

Distance penalties, heterogeneous overhead, soft schedule penalties, incompatible activities, and heterogeneous charger curves require explicit additional terms. They are not silently covered here.

---

## Theorem 5 — Hierarchical \(\epsilon\)-optimality

Let `OPEN` be a frontier of hierarchical nodes.

Assume:

### Coverage

Every remaining feasible plan in the declared domain belongs to at least one frontier node.

### Admissibility

For every \(N\in OPEN\),

\[
L(N)\le\min_{p\in\mathcal P_D(N)}J(p).
\]

### Concrete incumbent

\[
U=J(p_U)
\]

for a verified feasible concrete plan \(p_U\).

### Refinement preservation

When parent \(N\) is expanded,

\[
\mathcal P_D(N)=\bigcup_{c\in child(N)}\mathcal P_D(c).
\]

### Fixed tolerance

\[
\epsilon\ge0
\]

is fixed for the search.

Then a node may be pruned whenever

\[
\boxed{L(N)\ge U-\epsilon.}
\]

If search terminates with `OPEN` empty or

\[
\boxed{\min_{N\in OPEN}L(N)\ge U-\epsilon,}
\]

then

\[
\boxed{U-J_D^*\le\epsilon.}
\]

For \(\epsilon=0\), the incumbent is optimal within the declared domain.

### Proof

Any plan in a pruned node satisfies

\[
J(p)\ge L(N)\ge U-\epsilon.
\]

Thus no pruned plan can improve the incumbent by more than \(\epsilon\). Coverage ensures every unexamined feasible plan is either represented by `OPEN` or has been safely pruned. At termination,

\[
J_D^*\ge U-\epsilon.
\]

Since \(U\) is feasible, \(U\ge J_D^*\). Therefore

\[
0\le U-J_D^*\le\epsilon.
\]

∎

### Persistence of earlier pruning

If a node was pruned using \(U_{old}\) and a later incumbent improves to \(U_{new}\le U_{old}\), then

\[
U_{new}-\epsilon\le U_{old}-\epsilon,
\]

so the earlier pruning inequality remains valid.

---

# Part VII — Numerical correctness

## 15. Conservative floating-point bounds

A theoretical lower bound must not become unsafe because of rounding.

If a numerical routine returns \(L_{num}\), the implementation must use a conservative lower value such as

\[
L_{safe}=L_{num}-\tau_{num},
\]

or another outward-rounding/validated-error construction with documented tolerance.

Any concrete incumbent used as \(U\) must be verified feasible under the same declared numerical tolerances.

---

# Part VIII — Static versus oracle certificates

## 16. Directed road-time static certificate

Theorem 1 permits a static road-time certificate based on a proven directed road-time diameter or a conservative upper bound thereof.

A Region may also store landmark/road-interface summaries that provide cheaper admissible online bounds.

---

## 17. Route-length certificate is not yet static by theorem

For the accepted routing semantics, \(L_T(u,v)\) is the length of the selected fastest-time route.

B0 does **not** assume triangle inequality for \(L_T\).

Therefore no static \(\Delta_D\) based on an independent shortest-distance metric may be substituted for \(\omega_{L^-},\omega_{L^+}\) without a separate proof.

Primary B1 energy-concretization correctness must use the trip-conditioned oracle length oscillations.

A later deployable bound may replace them only if it proves

\[
\omega_{L^-}\le\overline\omega_{L^-}^{deploy},
\qquad
\omega_{L^+}\le\overline\omega_{L^+}^{deploy}.
\]

---

## 18. Oracle versus deployable hierarchy experiment

### 18.1 Oracle-certificate hierarchy

Use the fixed Region tree but compute exact trip-conditioned Region oscillations from the same concrete Site quantities used by the flat reference.

Purpose:

\[
\boxed{
\text{test whether the hierarchy/Region abstraction itself has pruning potential without certificate approximation confounding the result.}
}
\]

### 18.2 Deployable-certificate hierarchy

Use only precomputed, static, lazy, or otherwise cheap summaries whose conservativeness is independently verified.

Purpose:

\[
\boxed{
\text{measure the additional loss of bound tightness required for an actually cheap hierarchy.}
}
\]

The deployable stage must not precede the oracle stage.

---

# Part IX — Gap decomposition

## 19. Three sources of looseness

Let \(L_{deploy}\) be a cheap deployable lower bound and \(L_{oracle}\) a stronger oracle Region lower bound.

Let \(b^*(s)\) denote the best per-Site lower-bound model used for continuation.

Conceptually,

\[
F^*-L_{deploy}
=
G_{model}+G_{agg}+G_{cert},
\]

where

\[
G_{model}=F^*-\min_sb^*(s),
\]

\[
G_{agg}=\min_sb^*(s)-L_{oracle},
\]

\[
G_{cert}=L_{oracle}-L_{deploy}.
\]

Interpretation:

- large \(G_{model}\): continuation/resource relaxation is weak;
- large \(G_{agg}\): Region groups incompatible concrete actions too coarsely;
- large \(G_{cert}\): cheap/static certificate is much weaker than the oracle certificate.

A low pruning rate must be diagnosed through this decomposition before modifying Region construction.

---

# Part X — Hierarchy construction contract

## 20. What B0 freezes

B0 freezes

\[
\boxed{
\text{static nested action subsets}
+
\text{role-conditioned dynamic Views}
+
\text{admissible lower bounds}
+
\text{RCC-driven refinement}.
}
\]

A topology-first road-cell hierarchy remains the preferred construction family because road-time geometry has a theorem-level relation to aggregation looseness, road topology gives stable query-independent Region identity, and road cells can support reusable boundary/landmark summaries.

B0 does **not** claim a unique optimal partition algorithm.

---

## 21. What B0 does not freeze

B0 does not choose:

- METIS vs nested dissection vs another graph partitioner;
- binary vs multiway branching;
- cell-size thresholds;
- a weighted scalar clustering score;
- a workload distribution;
- a final deployable route-length certificate;
- real multi-stop hierarchy design.

No algorithm may be selected solely because it performs best after inspecting B1 outcomes.

---

## 22. Distribution-free construction principle

Without a workload distribution over states/roles, there is no unique universally optimal scalar hierarchy.

Offline construction should therefore retain a vector of structural/certificate quantities rather than invent a single weighted score.

Candidate splits may be compared by Pareto dominance over quantities such as:

- certified road-time diameter/bound;
- certified route-length oscillation bound, if available;
- interface/boundary complexity;
- role-conditioned action counts;
- future proven charging-profile spread.

If two splits trade one component for another, they are theoretically incomparable absent an externally justified workload/objective.

---

# Part XI — B1 falsifiable hypotheses and acceptance logic

## 23. Correctness hypotheses

These are not scientific wins; failure indicates a proof/implementation defect.

### H1 — Lower-bound validity

For every tested Region View,

\[
\boxed{L(N)\le J_R^*}
\]

within documented numerical tolerance.

Expected violations: **0**.

### H2 — Exact hierarchical preservation

With \(\epsilon=0\), hierarchical search returns the same declared-domain optimum as exhaustive flat Site enumeration for every B1 case.

Expected mismatches: **0**.

### H3 — RCC validity

Whenever margin-aware concretization certifies a Region View, observed concrete realization respects all certified hard constraints and does not exceed the derived one-stop aggregation-gap bound.

Expected violations: **0**.

### H4 — Refinement preservation

For every expanded Region,

\[
\mathcal P_D(R)=\bigcup_c\mathcal P_D(c)
\]

over concrete action IDs.

Expected lost/duplicated actions: **0** for the primary disjoint hierarchy.

---

## 24. Empirical Revised Go-1 question

Only after H1–H4 pass may B1 ask:

> Does a theorem-guided hierarchy materially reduce concrete decision work relative to exhaustive flat Site evaluation?

Required measurements:

- concrete Site evaluations;
- Region nodes evaluated;
- Region nodes pruned;
- routing-summary/bound computations;
- concrete routing calls avoided;
- wall time and peak memory;
- bound tightness;
- certified optimality-gap trajectory.

The principal curve should be

\[
\boxed{
\text{decision work}
\quad\text{vs}\quad
U-\min_{OPEN}L.
}
\]

A quantitative Go/No-Go threshold for “material reduction” must be frozen **before** examining B1 comparative outcomes. B0 intentionally does not invent such a threshold without separate practical/statistical justification.

---

## 25. Diagnostic hypotheses

B1 should additionally test, but not assume:

- deeper refinement tends to reduce oracle aggregation gap;
- Region road-time diameter correlates with travel-component aggregation gap;
- oracle-certificate hierarchy exhibits nontrivial pruning potential;
- deployable certificates, when later introduced, preserve much of the oracle pruning benefit.

These are empirical questions, not theorems.

---

# Part XII — Known non-guarantees

## 26. B0 does not guarantee

This specification does not prove:

- unrestricted global EV-route optimality;
- that the generalized-cost optimum lies inside a fixed Safe Detour Envelope;
- that selected-fastest-route length \(L_T\) is a metric;
- that any specific graph partition has good pruning performance;
- real multi-stop scalability;
- future charger-availability forecasting;
- partial-information role filtering;
- full Go-2 active information acquisition;
- a unique optimal hierarchy under all workloads;
- that a coarse Region has finite state-independent scalar regret under hard constraints.

---

# Part XIII — Freeze statement

Milestone 4R-B0 freezes the following theoretical contract:

\[
\boxed{\textbf{1. A Region is a refinable subset of concrete vehicle-stop actions, not a feasibility boundary.}}
\]

\[
\boxed{\textbf{2. Search nodes are state- and role-conditioned Views }(R,\alpha,\ell)\textbf{.}}
\]

\[
\boxed{\textbf{3. Pruning requires an admissible lower bound.}}
\]

\[
\boxed{\textbf{4. Abstract-to-concrete feasibility requires physical-unit RCCs and sufficient online hard-constraint margins.}}
\]

\[
\boxed{\textbf{5. In the current one-stop domain, energy certificates must use actual selected-fastest-leg length semantics; shortest-distance geometry cannot be substituted without proof.}}
\]

\[
\boxed{\textbf{6. Global search stops only with an explicit }\epsilon\textbf{-optimality certificate within the declared domain.}}
\]

\[
\boxed{\textbf{7. Low pruning is diagnosed by separating model relaxation, Region aggregation, and cheap-certificate looseness before changing hierarchy construction.}}
\]

The next authorized stage, if separately approved, is **Milestone 4R-B1: exact one-stop hierarchical validation**. B1 must test correctness hypotheses before making any Revised Go-1 empirical claim.
