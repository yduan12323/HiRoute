# RESEARCH_SPEC v0.2

**Project:** dy-HiRoute  
**Working title:** *Hierarchical Risk-Aware Active Route Recommendation under Partial Information*  
**Application focus:** long-distance EV route and stop planning  
**Status:** Frozen formulation after Milestone 4R design review  
**Date:** 2026-10-02  

> This document is the consolidated successor to the previous `RESEARCH_SPEC.md`. Earlier accepted milestones remain valid unless this document explicitly marks a semantic contract as superseded. Milestone 4B remains a valid diagnostic experiment, but several of its task and region semantics are no longer normative.

---

## 1. Core research question

How should a mobile decision system allocate limited **decision-search** and **information-acquisition** budget when route decisions are hierarchical, the world is only partially observed, uncertainty is represented conservatively rather than by unjustified probabilities, useful opportunities can expire while the system is computing or acquiring information, and EV charging must be coordinated with human stop timing and future route structure?

The guiding principle remains:

> **Know only what is necessary, search only where it matters, and recommend before the opportunity disappears.**

The intended contribution is a joint form of compression:

- **decision-space compression:** avoid expanding route/stop alternatives that cannot materially affect the decision;
- **information-space compression:** avoid acquiring facts that cannot materially affect the decision.

The two should reinforce one another through hierarchical refinement.

---

## 2. Research boundary

HiRoute is an **EV route-planning and stop-planning system**, not a consumer-business recommender.

Restaurants, lodging, toilets, parking, and similar facilities may provide evidence that a stop or region supports a human activity. HiRoute does **not** optimize which restaurant, hotel, cuisine, brand, or merchant should be selected.

> **HiRoute plans vehicle stops, not consumer choices.**

Transportation-critical infrastructure may be modeled at exact vehicle-waypoint resolution, especially chargers, vehicle parking/stopping facilities, motorway service/rest facilities, and access infrastructure that directly affects vehicle feasibility. Non-transport services are represented only through aggregate support evidence.

---

## 3. World and partial observability

Let the road network be

\[
G=(V,E).
\]

The observable trip state at time \(t\) is

\[
x_t=(l_t,t,E_t,d,\eta_t,\ldots),
\]

where \(l_t\) is current location, \(E_t\) is current vehicle energy state, \(d\) is the current destination, and \(\eta_t\) contains the energy-consumption model or relevant operating parameters.

The partially observed world is

\[
w_t=(traffic,\ road\ conditions,\ charger\ state,\ access,\ldots).
\]

Uncertainty is represented by an ambiguity set

\[
\mathcal B_t,
\]

rather than by fabricated probabilities. Probabilistic models may be introduced only where probability estimates are empirically justified.

The default planning horizon terminates at the current destination. Unknown driving after the current destination has no intrinsic value in the present objective unless future legs are explicitly supplied as part of the current problem.

---

## 4. Hard constraints versus utility

Hard constraints are enforced by the planning framework/verifier, not by semantic scoring. They may arise from physical reachability, energy feasibility, road legality/access restrictions, or explicit user hard requirements.

A weak behavioral heuristic or inferred human state must not silently become a hard constraint.

> **Semantic processing interprets evidence; the framework enforces feasibility.**

---

## 5. Utility, generalized cost, Top-K, and minimax regret

The overall research formulation remains utility-based:

\[
U_\theta(p,w).
\]

Milestone 4R uses generalized cost internally,

\[
J_\theta(p,w),
\]

with

\[
U_\theta(p,w)=-J_\theta(p,w).
\]

For known world \(w\),

\[
R_K(S,w)
=
U(p^*,w)-\max_{p\in S}U(p,w).
\]

Under ambiguity,

\[
MR_K(S;\mathcal B)
=
\sup_{w\in\mathcal B}
\left[
U^*(w)-\max_{p\in S}U(p,w)
\right].
\]

The robust Top-K set is

\[
S^*
=
\arg\min_{|S|=K}MR_K(S;\mathcal B),
\]

and

\[
\rho_K(\mathcal B)=MR_K(S^*;\mathcal B).
\]

A future information-acquisition stopping criterion remains

\[
\rho_K(\mathcal B)\le\epsilon.
\]

The deterministic Milestone 4R stage evaluates Top-1 only. Meaningful Top-K evaluation is deferred until world/objective ambiguity is introduced.

---

## 6. Safe Detour Envelope

Let \(c_0(e)\) be base mobility cost and

\[
C^*=d(s,d)
\]

the shortest baseline mobility cost.

For budget \(B\),

\[
V_B=
\{v:d(s,v)+d(v,d)\le B\},
\]

\[
E_B=
\{(u,v):
d(s,u)+c_0(u,v)+d(v,d)\le B
\}.
\]

Every route whose total base mobility cost is at most \(B\) is contained in this envelope.

The envelope is a **safe superset**, not the exact set of budget-feasible paths. A path assembled from individually safe edges must still have its total cost checked.

At \(B=C^*\), the envelope contains the union of all shortest paths, not merely one selected baseline path.

Envelope expansion remains adaptive:

\[
B_0<B_1<\cdots<B_{\max}.
\]

The previously used \(B_{\max}=2C^*\) is an experimental cap, not a universal constant.

The Safe Detour Envelope compresses **vehicle-route geometry only**. It does not imply \(J_\theta(p)\le B\).

---

# Part I — Milestone 4R formulation revision

## 7. Four-layer separation of concerns

### 7.1 Layer 1 — Static World Representation

\[
W^0=(G,O,\mathcal S^0,\mathcal R^0).
\]

Here \(O\) is the raw opportunity inventory, \(\mathcal S^0\) the static Stop Sites, and \(\mathcal R^0\) the static Opportunity Regions.

This layer contains only objective primitives. It must not contain current ETA, current arrival energy, current detour, current generalized cost, or user-specific scores.

### 7.2 Layer 2 — Trip-Conditioned Decision State

For current state \(x_t\) and partial plan \(p_{0:i}\),

\[
\phi_t(S\mid p_{0:i})
\]

may include

\[
arrivalTime,\quad
arrivalEnergy,\quad
detour,\quad
chargingTime,\quad
scheduleCompatibility.
\]

These are dynamic features, not permanent Site attributes.

### 7.3 Layer 3 — Hierarchical Search Views

For the current planning episode, create temporary views

\[
V_t(S),\qquad V_t(R),
\]

which may contain

\[
LB,\quad UB,\quad feasibility,\quad uncertainty,\quad relevant\ queries.
\]

Decision bounds belong to the current view, not the static Site or Region.

### 7.4 Layer 4 — Preference-Conditioned Evaluation

Only here does the planner introduce external decision parameters

\[
\theta
\]

and evaluate

\[
J_\theta(p).
\]

The world abstraction remains user-agnostic.

---

## 8. Frozen Milestone 4R invariants

### I1 — Vehicle-stop-first

The executable planning unit is a **vehicle stop event**, not a raw POI.

### I2 — User-agnostic world abstraction

Roads, Sites, Regions, charger attributes, and support primitives do not depend on a learned user profile.

### I3 — Independent requirements; emergent bundles

There are no primitive tasks such as `charge_meal`, `charge_parking`, or `sleep_charge`. Independent requirements may be satisfied by the same stop; their joint value emerges from stop consolidation.

### I4 — Hard constraints require explicit justification

Hard constraints come only from physical/energy/legal feasibility or explicit user hard requirements.

### I5 — Energy reserve is a floor, not an objective

The planner must preserve required reserve, but extra SOC/energy has no intrinsic reward.

### I6 — Charging amount is globally coupled

Charging amount may change later stop structure and must be optimized jointly with future stops.

### I7 — Consolidation uses concurrent makespan

Compatible activities at one vehicle stop may overlap in time.

### I8 — Stop count is a separate soft dimension

\(N_{\rm stop}\) counts distinct vehicle stop events, not requirements or POIs.

### I9 — Non-transport services remain aggregate

Restaurants, lodging, toilets, and similar services are support evidence, not ranked route targets.

### I10 — Opportunity Regions are search abstractions, never feasibility boundaries

Region membership cannot delete an otherwise feasible underlying plan.

### I11 — Unknown is not absent

At minimum distinguish

\[
known\ present,\quad unknown,\quad known\ absent.
\]

For chargers, existence and current usability are separate states.

### I12 — Information acquisition follows decision pruning

The order is

\[
feasibility
\rightarrow
decision\ bounds
\rightarrow
candidate\ pruning
\rightarrow
query\ pruning
\rightarrow
active\ acquisition
\rightarrow
commitment.
\]

---

## 9. Requirement model

A requirement is

\[
r=
(type,priority,source,status,W,L_{\min}).
\]

where

\[
priority\in\{hard,soft,optional\},
\]

\[
source\in\{state\text{-}derived,explicit,inferred\},
\]

\[
status\in\{proposed,confirmed,rejected\}.
\]

\(W\) is an optional time window and \(L_{\min}\) the minimum commitment resolution.

### 9.1 Energy requirement

Energy requirement is state-derived. If the remaining route cannot be completed while maintaining required reserve, charging is a hard requirement.

### 9.2 Generic scheduled-stop requirement

Milestone 4R uses one generic scheduled-stop requirement

\[
r_{\rm sched}
\]

representing a desired stop in a time window with aggregate local support. The primary experiment interpretation is a meal stop. No restaurant is selected.

### 9.3 User-declared stop requirement

A user may explicitly request a stop, e.g. rest. Latent fatigue is not inferred from weak proxies such as continuous driving time in the 4R core.

### 9.4 Requirement inference policy

Conceptually,

\[
InferencePolicy(r)
\in
\{
state\text{-}derived,\ suggestible,\ explicit\text{-}only
\}.
\]

However, 4R experiments do not evaluate intent inference; scheduled-stop windows are supplied exogenously.

---

## 10. Static Stop Site

A static Stop Site is

\[
S^0=
(a,\phi_{\rm transport},\phi_{\rm support},\phi_{\rm context}),
\]

where \(a\) is a real vehicle anchor.

A vehicle anchor is a location at which the vehicle can actually stop, such as a charging station, parking facility, motorway service/rest area, or another legitimate vehicle-stopping facility.

Only vehicle anchors participate directly in vehicle routing.

### 10.1 Transportation primitives

Examples:

\[
chargerPresence,\quad
chargerClass,\quad
parkingCapability,\quad
accessMetadata.
\]

These are facts, not utility values.

### 10.2 Aggregate support primitives

The world stores evidence; requirements define sufficiency.

For meal support,

\[
\phi_{\rm meal}(S)
=
(
N_{\rm meal},
d_{\rm meal}^{min},
coverage_{\rm meal},
\ldots
).
\]

A simple experiment may define

\[
Sat(r_{\rm meal},S)
=
\mathbf 1[N_{\rm meal}(S)\ge1].
\]

Changing the satisfaction threshold must not require rebuilding the static world.

### 10.3 Local accessibility

A non-transport opportunity \(o\) supports Site \(S\) when

\[
o\in A_c(S)
\iff
d_{\rm local}(a,o)\le\rho_c.
\]

The theoretical quantity is human local-access distance. If implementation uses geographic distance as a proxy, it must be explicitly labeled an approximation and must never be reinterpreted as a second vehicle visit.

### 10.4 Stop context

A Site may store objective context such as motorway service area, town parking, urban cluster, or roadside stop. Preference over those contexts belongs to \(\theta\), not the Site.

---

## 11. Opportunity Region

A static Region is

\[
R^0=
(\mathcal S_R,\Phi_R^0,G_R),
\]

where \(\mathcal S_R\) contains Stop Sites, \(\Phi_R^0\) static aggregate primitives, and \(G_R\) gateway/road-interface structure.

A Region does not permanently store current ETA, arrival energy, detour, generalized cost, or decision bounds.

For a current trip,

\[
V_t(R)
=
(
\Phi_t(R),
\underline J_t(R),
\overline J_t(R),
\mathcal F_t(R),
\mathcal Q_t(R)
).
\]

Region structure may later be a partition, overlapping cover, tree, or DAG. v0.2 does not freeze that representation.

The non-negotiable contract is:

\[
\boxed{
\text{Region boundaries do not change the underlying feasible plan set.}
}
\]

Regions may bound, rank, prune, and refine search. Region membership itself is not a physical constraint.

---

## 12. Abstract and executable plans

A hierarchical search procedure may maintain an abstract plan \(\bar p\) in which future choices are represented by Regions.

An executable plan must resolve vehicle actions to concrete Stop Sites:

\[
p=(\Gamma,E_1,\ldots,E_H),
\]

where

\[
E_i=
(S_i,t_i,\tau_i,e_i,\mathcal R_i^{sat}).
\]

A Region centroid must never be treated as a fake executable waypoint.

---

## 13. Energy dynamics

Using energy state \(E\),

\[
E_{i+1}
=
E_i-E_{\rm drive}(\Gamma_i)+e_i.
\]

The plan must satisfy

\[
0\le E_i\le E_{\max},
\]

and throughout execution

\[
E(t)\ge E_{\min}.
\]

At the destination,

\[
E_d
\ge
E_{\rm reserve}+M_{\rm robust}.
\]

---

## 14. Charging model

Charging duration is

\[
T_{\rm charge}
=
C^{-1}(E_{\rm arr},E_{\rm dep};S),
\]

with an interface that permits nonlinear charging curves.

A fixed rule such as “always charge to 80%” or “always charge to 100%” is not normative. Departure energy is a decision variable.

Extra charging is valuable only through downstream consequences such as avoiding a later stop, reducing detour, reducing later charging time, or preserving feasibility. Extra terminal energy has no intrinsic utility.

---

## 15. Stop event, compatibility, and consolidation

A distinct vehicle stop event is defined by the vehicle stopping at one anchor before later departing for another anchor. Multiple activities at the same anchor still count as one stop.

Define

\[
Compat(a,b,S)\in\{0,1\}.
\]

Only compatible activities may overlap.

The general stop-duration model is

\[
\tau_i
=
T_{\rm overhead}(S_i)
+
Makespan(\mathcal A_i,S_i).
\]

For the canonical charging plus locally accessible scheduled-activity case,

\[
\tau_i
=
T_{\rm overhead}(S_i)
+
\max(T_{\rm charge},T_{\rm sched}).
\]

The incremental charging dwell relative to the scheduled activity is

\[
\Delta T_{\rm charge|sched}
=
\max(0,T_{\rm charge}-T_{\rm sched}).
\]

---

## 16. Plan features and generalized cost

Before scalarization retain

\[
Z(p)
=
(
T_{\rm clock},
N_{\rm stop},
P_{\rm sched},
D,
Toll,
Context,
\ldots
).
\]

The deterministic generalized cost is

\[
J_\theta(p)
=
T_{\rm clock}(p)
+
\lambda_{\rm stop}N_{\rm stop}(p)
+
P_{\mathcal R}(p)
+
\theta^\top z_{\rm other}(p),
\]

with

\[
T_{\rm clock}
=
T_{\rm drive}+\sum_i\tau_i.
\]

### 16.1 No double counting

\(\lambda_{\rm stop}\) represents non-clock-time nuisance/comfort cost only. Actual driving, detour, parking/entry/exit time, charging, and dwell already belong to \(T_{\rm clock}\).

### 16.2 Requirement penalties

For hard requirement \(r\),

\[
P_r(p)
=
\begin{cases}
0,&Sat(r,p)=1,\\
+\infty,&Sat(r,p)=0.
\end{cases}
\]

For soft requirement \(r\),

\[
P_r(p)
=
P_r^{miss}\mathbf 1[\neg Sat(r,p)]
+
P_r^{time}(p).
\]

A planner must not be able to avoid a scheduled-stop penalty simply by omitting the activity.

### 16.3 Preference boundary

v1 does not learn user profiles. Parameters such as \(\lambda_{\rm stop}\), schedule penalty, or context preferences are exogenous experimental parameters. Future product personalization is outside the research contribution.

---

## 17. Dynamic coupling

Arrival time and energy are plan-conditioned:

\[
arrivalTime(S\mid p_{0:i}),
\]

\[
arrivalEnergy(S\mid p_{0:i}).
\]

They cannot be permanently attached to a Site.

The stop-selection and charging decisions are dynamically coupled:

\[
S_i
\rightarrow
E_i
\rightarrow
S_{i+1}.
\]

The specification permits stateful search, dynamic programming, label-setting, or related resource-constrained methods, but does not freeze a specific algorithm.

---

# Part II — Risk-aware decision refinement

## 18. Uncertainty representation

For a candidate plan or a Site/Region decision view,

\[
J(p)\in[\underline J_p,\overline J_p].
\]

Unknown infrastructure states remain explicit. For chargers, distinguish station existence from current operational/usability state.

An unknown candidate may remain **conditionally viable**.

---

## 19. Decision-equivalent pruning

Let the best guaranteed incumbent have cost

\[
J_{\rm inc}^{UB}.
\]

For

\[
\epsilon_{\rm dec}\ge0,
\]

if

\[
\underline J_p
\ge
J_{\rm inc}^{UB}-\epsilon_{\rm dec},
\]

then even the optimistic realization of \(p\) cannot improve the incumbent by more than \(\epsilon_{\rm dec}\), and \(p\) may be pruned.

Terminology:

- \(\epsilon_{\rm dec}=0\): strict safe pruning;
- \(\epsilon_{\rm dec}>0\): \(\epsilon_{\rm dec}\)-decision pruning.

---

## 20. Query model

A query is

\[
q=
(target,observations,C(q),\tau(q),Rel(q)).
\]

A query may return multiple typed observations and may target a Region, Site, or transportation infrastructure.

A query is pruned if it affects only already-pruned candidates, no outcome can materially change commitment, reliability is insufficient, or latency destroys the relevant fallback.

Thus

\[
uncertainty\not\Rightarrow information\ acquisition.
\]

---

## 21. Fallback-aware latency

While a query executes,

\[
x_t\rightarrow x_{t+\tau(q)}.
\]

A fallback \(f\) remains valid only if

\[
f\in\mathcal F(x_{t+\tau(q)}).
\]

“Commitment deadline” is an intuitive term; the formal rule is state-dependent fallback feasibility.

---

## 22. Availability temporal assumption for 4R

Real charger availability is time-varying:

\[
A_S(t).
\]

Milestone 4R does not solve future occupancy forecasting.

Synthetic 4R uncertainty tests therefore assume that a queried availability state remains sufficiently stable over the short decision horizon being tested. This assumption must be reported and later relaxed.

---

## 23. Risk-aware does not mean always conservative

If an unknown candidate is nominally better and a safe fallback remains executable, it may be rational to preserve the candidate, query its decision-critical state, and fall back only if the result is unfavorable.

The intended behavior is

\[
preserve\ optionality
\rightarrow
query
\rightarrow
commit/fallback,
\]

not

\[
uncertainty\Rightarrow immediate\ rejection.
\]

---

# Part III — Experimental program after the revision

## 24. Milestone 4R executable core

The first 4R implementation is deliberately narrow:

\[
EV\ charging
+
one\ generic\ scheduled\ stop\ window
+
aggregate\ local\ support.
\]

The scheduled-stop interpretation is primarily meal-like, but no consumer-business choice is made.

The 4R core does not attempt restaurant/hotel ranking, fatigue inference, personalization learning, full time-varying charger occupancy prediction, final Top-K ambiguity reasoning, or the final Go-2 active-acquisition algorithm.

---

## 25. 4R implementation responsibilities

The code stage must:

1. replace the old compound-task interpretation with independent requirements;
2. construct stable Stop Site representations from transportation-capable anchors and aggregate local support;
3. implement deterministic state-aware stop planning with energy feasibility, charging amount, scheduled windows, dwell overlap, stop-count cost, and future-stop coupling;
4. expose a minimal uncertainty/query interface and synthetic regression tests without claiming the final Go-2 algorithm.

The 4R stage first establishes a flat Stop-Site semantic baseline. Hierarchical Region evaluation follows only after that baseline is trustworthy.

---

## 26. Updated Go/No-Go program

### Go-1 — Hierarchical decision compression

> Can hierarchical abstraction substantially reduce the decision work that must be expanded/evaluated while preserving near-optimal executable stop plans?

Measure at least Sites expanded, Regions expanded, routing evaluations, stop plans materialized, and later information queries. Final candidate-table size alone is not a sufficient compression metric.

### Go-2 — Active information acquisition

Compare active decision-boundary acquisition against baselines such as random, cheapest-query-first, widest-interval/uncertainty-first, and exhaustive acquisition.

Queries attached only to candidates that are already decision-irrelevant should be eliminated before acquisition.

### Go-3 — Joint synergy

Use the conceptual 2×2 comparison

\[
flat/hierarchical
\times
exhaustive/active\ information.
\]

The purpose is to test whether decision-space and information-space compression reinforce one another.

---

## 27. Development and holdout policy

The existing 30 OD pairs have been repeatedly inspected during design and are now a **development set**.

They may be used for debugging, semantic diagnostics, algorithm development, and sensitivity analysis.

After the algorithm and experimental protocol are frozen, final evaluation must use a new holdout OD set. Approximately 100 ODs is a planning target, not yet a frozen constant.

---

# Part IV — Supersession ledger for Milestone 4B

## 28. Status of Milestone 4B

Milestone 4B remains a valid diagnostic/negative-result experiment. It showed that large representation compression can coexist with substantial decision loss when a Region boundary is incorrectly given physical-feasibility semantics. It also showed that, under the tested known positive-linear objective family, later Pareto/\(\epsilon\)-cover stages contributed far less scalar loss than the hard Region restriction.

The following semantics are explicitly superseded.

| 4B semantic/assumption | v0.2 status | Replacement |
|---|---|---|
| Raw opportunity object can directly act as a route activity waypoint | **Superseded** | Vehicle Stop Site is the route action; non-transport POIs are local support evidence |
| `charge_meal`, `charge_parking`, `sleep_charge`, etc. are primitive tasks | **Superseded** | Independent requirements; joint satisfaction emerges through stop consolidation |
| Two-object compound task implies the vehicle visits both objects | **Superseded** | Local activity may be completed from one vehicle anchor without a second vehicle waypoint |
| `charge + parking` is a default two-object compound decision | **Superseded** | Charging is itself a vehicle stop; parking is normally support/infrastructure unless explicitly modeled otherwise |
| Both objects must lie in the same frozen Region for the bundle to exist | **Superseded** | Region membership never defines underlying physical feasibility |
| Region membership may be used as a hard pair-feasibility restriction | **Superseded** | Regions only bound/rank/prune/refine search |
| Region anchors/gateways can stand in as executable waypoints | **Not permitted** | Executable plans resolve to real Stop Sites |
| Fixed positive-linear cost Pareto losslessness validates future partial-information pruning | **Superseded as a validation claim** | Future pruning under unknown state/quality requires robust bounds/dominance |
| Known-\(\theta\) Top-1/3/5 equality validates meaningful Top-K | **Superseded as a validation claim** | Meaningful Top-K is deferred to world/objective ambiguity |
| Candidate-count reduction alone is the principal Go-1 metric | **Superseded** | Measure expansion, routing, plan materialization, and later queries |

The 4B result itself is retained as the empirical motivation for:

> **Abstraction boundaries may compress search, but must not define physical feasibility.**

---

# Part V — Milestone status and next sequence

## 29. Accepted substrate

The following remain accepted and are not reopened by 4R:

- **M1:** frozen Slovenia graph/data substrate;
- **M2:** Safe Detour Envelope implementation and correctness checks;
- **M3A:** cross-border 75 km graph substrate and remapped OD set;
- **M4A:** raw opportunity inventory and diagnostic route-attached region experiment;
- **M4B:** gateway/microplan/Pareto experiment as a diagnostic result.

M4A/M4B Region semantics are not automatically carried forward as normative 4R Region semantics.

---

## 30. Immediate next sequence

1. Implement **Milestone 4R semantic substrate and flat deterministic baseline**.
2. Validate all 4R behavioral regression scenarios.
3. Only after the flat baseline is credible, rebuild/test Opportunity Regions over Stop Sites under the new non-feasibility-boundary contract.
4. Re-run revised Go-1.
5. Introduce the full active-information Go-2 stage.
6. Freeze algorithm/protocol, then evaluate on a new holdout OD set.
7. Run Go-3 joint-synergy evaluation.

---

## 31. Canonical behavioral acceptance scenarios

| Scenario | Required behavior |
|---|---|
| Enough energy + scheduled stop | Do not force charging |
| Insufficient energy | Energy-infeasible plan is rejected |
| Charger with local scheduled-stop support | One stop may satisfy charging and scheduled activity |
| Local meal POIs around an anchor | Do not create restaurant vehicle waypoints |
| Charge/meal/toilet at one anchor | Count as one vehicle stop |
| No explicit fatigue input | Do not insert a fatigue/rest stop |
| Earlier charger A vs meal-aligned charger B | B may be chosen if reserve remains feasible |
| 76% already sufficient for destination | Do not wait merely to reach 80% |
| Extra 15 min charging now removes a 25 min later stop | Permit extra charging and remove later stop |
| Similar clock time but one fewer stop | Stop-count penalty may change the choice |
| Incumbent A good; B best case improves less than \(\epsilon_{\rm dec}\) | Prune B before querying |
| B materially better but availability unknown | Keep B conditionally viable |
| B query unfavorable while A remains reachable | Fall back to A |
| Query latency would make A unreachable | Do not continue waiting for the query |
| Two feasible Sites are in different Regions | Region boundary must not delete the plan |
| Support threshold changes | Do not rebuild static world representation |
| \(\theta\) changes | Do not rebuild Sites/Regions |

---

## 32. Deferred questions

v0.2 intentionally does not freeze:

- Region topology: partition vs overlap vs tree vs DAG;
- final Region clustering algorithm;
- final Stop Site deduplication algorithm;
- pedestrian network vs conservative geographic local-access proxy;
- final aggregate-support thresholds;
- empirical population distribution of \(\lambda_{\rm stop}\);
- user-intent inference;
- user-profile learning;
- final query-selection heuristic;
- future charger occupancy forecasting;
- final Top-K construction under ambiguity;
- final holdout size and stratification.

---

## 33. Freeze statement

> **HiRoute plans vehicle stops, not consumer choices.**  
> **Static world facts are separated from trip-conditioned decision state.**  
> **Energy determines what must remain feasible.**  
> **Scheduled stops determine when stopping can be useful.**  
> **Stop consolidation determines how dwell time can be reused.**  
> **Information is acquired only when it can materially change commitment.**  
> **Opportunity Regions compress search, never physical feasibility.**

This formulation supersedes the conflicting Milestone 4B semantics identified in Section 28. All other previously accepted substrate remains in force.
