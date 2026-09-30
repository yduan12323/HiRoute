# Research Specification

## Hierarchical Risk-Aware Active Route Recommendation under Partial Information

**Status:** Research prototype specification  
**Version:** 0.1  
**Primary purpose:** Define the scientific problem, fixed modeling assumptions, interfaces, evaluation protocol, and implementation boundaries for the research codebase.

This document is the authoritative research specification for the project.

Implementation agents, including Codex, **must not silently change the research formulation in order to simplify implementation**. If a specification appears infeasible, inconsistent, or unnecessarily expensive, flag the issue explicitly and propose alternatives before changing the semantics.

---

# 1. Research Question

We study the following problem:

> How should a route recommendation system efficiently search the decision space and selectively acquire information when the environment is partially observed, information acquisition has cost and latency, and decision opportunities may disappear while information is being acquired?

The central hypothesis is:

> A hierarchical route abstraction combined with decision-relevant information acquisition can approach full-information route recommendation quality using substantially fewer candidate plans, tool calls, and decision time.

The system should avoid two forms of unnecessary computation:

1. **Decision-space waste:** evaluating route plans or waypoints that could not plausibly become good recommendations.
2. **Information-space waste:** acquiring information whose possible outcomes cannot materially change the recommendation.

The project therefore studies two coupled compression problems:

\[
\text{Decision-space compression}
\]

and

\[
\text{Information-space compression}.
\]

---

# 2. Scope

The first paper is restricted to **navigation and long-distance route recommendation**.

The framework should be:

- model-agnostic with respect to semantic processors;
- provider-agnostic with respect to routing, POI, traffic, charging, and other information tools;
- geographically general where data permits;
- applicable to multiple route-planning objectives;
- independent of persistent user profiles.

The first paper does **not** claim universality across arbitrary recommendation domains.

The navigation domain is sufficiently rich because it contains:

- route choice;
- intermediate waypoint selection;
- charging;
- food;
- rest;
- accommodation;
- time-dependent information;
- uncertain POI conditions;
- dynamic road conditions;
- information acquisition cost;
- decision deadlines.

---

# 3. Non-Goals

The first version explicitly does **not** attempt to solve the following problems.

## 3.1 No autonomous vehicle control

The system does not perform steering, lane control, or low-level vehicle control.

It produces route-plan recommendations.

---

## 3.2 No persistent user profiling

The system does not infer or maintain long-term user profiles.

User preferences may be provided explicitly for an experiment, but preference learning is outside the initial scope.

---

## 3.3 No full contingency policy

The first version does not learn or output a complete state-contingent policy tree.

Instead, the system performs:

\[
\text{event-triggered receding-horizon replanning}.
\]

When important world state changes occur, the system may rerun the hierarchical planner.

---

## 3.4 No dependence on one LLM

The core planning method must not depend on GPT-, Claude-, Gemini-, Qwen-, or any other model-specific behavior.

Semantic processors are replaceable modules.

---

## 3.5 No requirement to solve semantic extraction

The research assumes that a semantic processor can convert unstructured evidence into usable typed evidence.

Semantic extraction quality may affect downstream performance, but designing the best semantic processor is not a central contribution.

---

## 3.6 No claim that more information is always better

A central hypothesis of the work is precisely the opposite:

> Much available information has negligible decision value.

The system should stop acquiring information when additional information is unlikely to improve route recommendation sufficiently to justify its cost or latency.

---

# 4. Core Scientific Claims to Test

The work should ultimately test three primary hypotheses.

## H1 — Decision-space compression

A large route/POI search space can be compressed into hierarchical Opportunity Regions and representative microplans while preserving near-optimal recommendation quality.

Formally, large compression should be possible while maintaining low abstraction regret:

\[
R_{\mathrm{abs}}
=
U(p^*)-
\max_{\tilde p\in\widetilde{\mathcal P}}U(\tilde p).
\]

---

## H2 — Decision-relevant information acquisition

Queries selected according to their potential effect on route decisions should outperform generic uncertainty-driven acquisition.

In particular:

\[
\text{high uncertainty}
\not\Rightarrow
\text{high decision value}.
\]

A highly uncertain fact should not be queried if no possible value of that fact could change the relevant recommendation set.

---

## H3 — Joint refinement synergy

Decision-space compression and information-space compression should reinforce each other.

Opportunity abstraction should reduce the number of potentially relevant information queries.

New information should in turn allow additional regions or candidate plans to be pruned.

The complete method should exhibit a better tradeoff between decision regret and information/compute cost than either component used alone.

---

# 5. World Model

Let the road network be:

\[
G=(V,E).
\]

Let:

- \(s\): origin;
- \(d\): destination;
- \(x_t\): observable ego state;
- \(w_t\): partially observed world state.

The ego state may include:

\[
x_t=
(
l_t,
t,
SOC_t,
d,
\ldots
),
\]

where:

- \(l_t\): current position;
- \(t\): current time;
- \(SOC_t\): battery state of charge where relevant.

The hidden world state may include:

\[
w_t=
(
\text{traffic},
\text{road conditions},
\text{charger availability},
\text{charging queue},
\text{POI availability},
\text{parking conditions},
\text{weather},
\text{activity quality},
\ldots
).
\]

The system does not assume complete access to \(w_t\).

---

# 6. Ambiguity Representation

The project uses **interval / ambiguity-set uncertainty** as the primary uncertainty representation.

Do not require every uncertain variable to have an exact calibrated probability distribution.

Examples:

\[
\text{queue time}
\in
[10,35]\text{ min},
\]

or:

\[
\text{parking convenience}
\in
[\text{medium},\text{high}].
\]

The planner maintains an ambiguity representation:

\[
\mathcal B_t.
\]

Unknown must remain distinct from known-good and known-bad.

Specifically:

\[
\texttt{unknown}
\neq
\texttt{false}
\neq
0.
\]

Evidence should retain provenance wherever possible.

A generic evidence object should be capable of storing:

- attribute;
- value or interval;
- source;
- observation time;
- freshness;
- reliability metadata;
- semantic processor identifier if relevant.

---

# 7. Semantic Processor

The semantic processor is an interchangeable module:

\[
S_\phi:
X_{\mathrm{unstructured}}
\rightarrow
E_{\mathrm{typed}}.
\]

Its purpose is to transform information such as:

- user reviews;
- textual POI descriptions;
- web information;
- natural-language route preferences;

into typed structured evidence.

Example:

Input:

> “The chargers are fast, but there is usually a long queue around dinner time.”

Possible typed output:

```yaml
attribute: charging_queue_risk
value_interval:
  lower: medium
  upper: high
applicable_time:
  start: "17:00"
  end: "20:00"
freshness: 14_days
source_type: user_review
```

The planner must not depend on the internal architecture of the semantic processor.

Initial experiments should include:

1. oracle semantic processor;
2. frontier semantic model;
3. fast/cheap model;
4. smaller or open model if practical.

The semantic processor is treated as a sensor, not as the authoritative planner.

---

# 8. Hard Constraints vs Soft Utility

Hard feasibility constraints must not be delegated to unconstrained semantic-model judgment.

Examples include:

\[
SOC_t \ge SOC_{\min},
\]

road legality,

vehicle restrictions,

reachability,

and other domain-defined safety constraints.

Soft preferences may enter the utility function.

Examples include:

- travel time;
- toll;
- detour;
- comfort;
- food quality;
- parking convenience;
- charging convenience;
- rest quality.

The framework should follow the principle:

> Semantic processors interpret information; the planning framework enforces feasibility.

---

# 9. Route Plan Representation

A route plan is not merely a road polyline.

Represent a route plan conceptually as:

\[
p=
(
\Gamma,
R_{1:H},
M_{1:H}
),
\]

where:

- \(\Gamma\): macro road corridor;
- \(R_i\): Opportunity Region;
- \(M_i\): selected local microplan.

A microplan may include multiple coordinated activities.

Example:

```text
leave expressway
    ↓
fast charger
    +
restaurant within walking distance
    ↓
rest
    ↓
re-enter main corridor
```

Concurrent activities must not always be modeled additively.

For example:

\[
t_{\text{meal}}=45,
\qquad
t_{\text{charge}}=35
\]

may imply effective dwell time closer to:

\[
\max(45,35)
\]

than:

\[
45+35.
\]

---

# 10. Safe Detour Envelope

The system must **not** define candidate opportunities only by buffering a single shortest or fastest route.

This would incorrectly remove potentially valuable alternative corridors.

Let the base mobility cost of an edge be:

\[
c_0(e)\ge0.
\]

Let the shortest base mobility cost be:

\[
C^*=d(s,d).
\]

For a detour budget \(B\), construct the feasible envelope:

\[
V_B
=
\{
v:
d(s,v)+d(v,d)\le B
\}.
\]

Likewise, feasible edges may satisfy:

\[
d(s,u)+c_0(u,v)+d(v,d)\le B.
\]

This yields a bounded-detour subgraph:

\[
G_B=(V_B,E_B).
\]

Any route whose base mobility cost is no greater than \(B\) should not be discarded merely because it does not follow the baseline shortest path.

---

# 11. Adaptive Envelope Expansion

The detour budget must not always be initialized to its maximum value.

Use adaptive expansion:

\[
B_0<B_1<\cdots<B_{\max}.
\]

The maximum envelope may, for initial experiments, use a cap such as:

\[
B_{\max}=2C^*
\]

or another explicit experimentally controlled limit.

The exact value is a hyperparameter and must not be silently hard-coded as a universal constant.

Expansion should stop when additional envelope growth has negligible potential decision value.

Possible stopping conditions include:

\[
\Delta V_j
=
V_{j+1}^*-V_j^*
<
\epsilon_B,
\]

or when optimistic bounds for newly introduced regions cannot challenge the current recommendation set.

The purpose of adaptive expansion is to avoid both:

- prematurely excluding useful detours;
- exploring extreme detours with negligible value.

---

# 12. Opportunity Region

An Opportunity Region is **not simply a geographic cluster or administrative region**.

It is a route-attached decision abstraction.

Conceptually:

> An Opportunity Region is a reachable area where the traveler can leave the current macro journey, access one or more valuable activities at similar routing cost, and subsequently continue toward the destination.

Regions should be derived from:

- road topology;
- route progress;
- gateway structure;
- reachability;
- detour cost;
- opportunity density;
- activity compatibility.

Administrative units such as cities or counties may be useful features but must not define the abstraction.

---

# 13. Gateway Representation

Opportunity Regions should preferably be associated with route-network gateways.

A local detour may be represented as:

\[
m=
(
g_{\mathrm{out}},
A,
g_{\mathrm{in}}
),
\]

where:

- \(g_{\mathrm{out}}\): departure gateway;
- \(A\): activities or local waypoints;
- \(g_{\mathrm{in}}\): re-entry gateway.

Examples of gateways include:

- expressway exits;
- major intersections;
- corridor branch points;
- road-network access points into dense POI areas.

This representation is intended to distinguish decision similarity from Euclidean proximity.

---

# 14. Decision-Space Distance

Opportunity abstraction should not rely purely on Euclidean distance.

A candidate decision-space distance may consider:

\[
D(i,j)
=
w_1|r_i-r_j|
+
w_2|\Delta_i-\Delta_j|
+
w_3d_G(i,j)
+
w_4D_A(i,j),
\]

where:

- \(r_i\): normalized route progress;
- \(\Delta_i\): minimum detour cost;
- \(d_G\): road-network distance or gateway similarity;
- \(D_A\): activity compatibility distance.

The exact clustering or region-construction algorithm remains an implementation/research choice.

Codex may propose alternatives, but must preserve the semantic requirement that region similarity is defined in decision space, not merely geographic space.

---

# 15. User-Agnostic Opportunity Abstraction

Opportunity Region generation and microplan compression must be **user-agnostic**.

The representation should preserve a multi-objective description such as:

\[
z(m)
=
(
\Delta t,
\Delta d,
\Delta toll,
\Delta E,
food,
comfort,
charging,
rest,
risk,
\ldots
).
\]

User/task utility is applied after abstraction.

The world abstraction must not need to be recomputed for each user profile.

---

# 16. Microplan Compression

Within each Opportunity Region, generate feasible microplans.

Then compress them using a decision-preserving representation such as an:

\[
\epsilon\text{-Pareto cover}.
\]

For minimized cost dimensions:

\[
c_j(\tilde m)
\le
c_j(m)+\epsilon_j^c.
\]

For maximized benefit dimensions:

\[
q_j(\tilde m)
\ge
q_j(m)-\epsilon_j^q.
\]

Hard-safety dimensions may require:

\[
\epsilon_j=0.
\]

The intended scientific claim is that substantial candidate-space compression can occur with bounded or empirically small abstraction regret.

---

# 17. Abstraction Loss

For a full plan space \(\mathcal P\) and compressed space \(\widetilde{\mathcal P}\):

\[
R_{\mathrm{abs}}
=
U(p^*)-
\max_{\tilde p\in\widetilde{\mathcal P}}U(\tilde p).
\]

The project must explicitly measure the tradeoff:

\[
\boxed{
\text{Compression Ratio}
\quad\text{vs}\quad
R_{\mathrm{abs}}
}
\]

rather than treating Opportunity Region quality as a qualitative visualization problem.

A theoretical conditional bound may be derived under assumptions such as monotonicity and Lipschitz continuity of utility.

Empirical validation remains mandatory.

---

# 18. Top-K Recommendation

The primary output is a set of recommendations:

\[
S=
\{p_1,\dots,p_K\}.
\]

This reflects the decision-support nature of the system.

Define Top-\(K\) regret under a known world \(w\):

\[
R_K
=
U(p^*,w)
-
\max_{p\in S}U(p,w).
\]

A useful secondary metric is:

\[
P(R_K\le\epsilon),
\]

interpreted as \(\epsilon\)-optimal recommendation coverage.

The system does not need to identify a unique globally optimal plan if multiple alternatives are practically equivalent.

---

# 19. Minimax-Regret Criterion

The primary uncertainty-aware decision criterion is minimax regret.

For an ambiguity set \(\mathcal B\):

\[
MR_K(S;\mathcal B)
=
\sup_{w\in\mathcal B}
\left[
U^*(w)
-
\max_{p\in S}U(p,w)
\right].
\]

The best recommendation set is:

\[
S^*
=
\arg\min_{|S|=K}
MR_K(S;\mathcal B).
\]

Define:

\[
\rho_K(\mathcal B)
=
MR_K(S^*;\mathcal B).
\]

Information acquisition may stop when:

\[
\rho_K(\mathcal B)\le\epsilon.
\]

Expected-value or Bayesian VOI methods may be studied later when reliable probability models exist, but they are not the primary uncertainty framework for v1.

---

# 20. Information Acquisition

An information query is an epistemic action:

\[
q\in\mathcal Q.
\]

Examples include:

- charger availability lookup;
- traffic lookup;
- weather lookup;
- POI details;
- review inspection;
- parking-condition lookup.

Each query may have:

\[
C(q)
\]

for monetary/computational/tool cost and:

\[
\tau(q)
\]

for latency.

A query changes the ambiguity set:

\[
\mathcal B_t
\rightarrow
\mathcal B_{t+\tau(q)}.
\]

The system must not query information merely because it is uncertain.

It should query information because resolving that uncertainty may change a relevant decision.

---

# 21. Decision-Relevant Uncertainty

The project adopts the principle:

\[
\boxed{
\text{uncertainty}
\neq
\text{decision-relevant uncertainty}.
}
\]

If a candidate plan cannot enter the \(\epsilon\)-optimal Top-\(K\) set under any permissible value of an uncertain variable, information about that variable has zero or negligible current decision value.

This principle should be exploited for query pruning.

---

# 22. Plan Bounds

Candidate plans and Opportunity Regions should maintain lower and upper utility bounds where practical:

\[
U(p)\in[L_p,U_p].
\]

If the optimistic upper bound of a candidate cannot challenge the current recommendation threshold:

\[
U_p^{UB}
<
L_K-\epsilon,
\]

then the candidate may be pruned.

Information queries that affect only pruned candidates may also be pruned.

The tightness and computational cost of such bounds is an important algorithmic design problem.

---

# 23. Deadline-Aware Information Acquisition

Information acquisition occurs while the vehicle is moving.

Therefore:

\[
x_{t+\tau(q)}
\neq
x_t.
\]

Some actions may disappear before a query completes.

For example, an upcoming exit may become unreachable.

Therefore query value must account for the future feasible-plan set:

\[
\mathcal P_{t+\tau(q)}.
\]

Latency should preferably be modeled through actual opportunity expiration rather than only through an arbitrary discount coefficient.

The algorithm should compare:

- acting now;
- querying first, then acting with a potentially smaller feasible action set.

---

# 24. Query Selection

Exact sequential value-of-information computation may be intractable.

The intended v1 algorithm should therefore use hierarchical pruning.

A preferred structure is:

### Stage 1 — Plan/Region pruning

Remove candidate regions/plans whose optimistic bounds cannot challenge the current recommendation set.

### Stage 2 — Query pruning

Remove queries that affect no decision-relevant candidate.

### Stage 3 — Cheap impact bound

Estimate the maximum possible utility change caused by each remaining query.

If a query cannot change the decision boundary even under perfect information, do not issue it.

### Stage 4 — Expensive evaluation

Only for a small surviving query set, evaluate approximate robust query value using interval splitting, scenario sampling, or another tractable surrogate.

The exact surrogate is a central algorithmic research choice.

---

# 25. Information-Acquisition Stopping Rule

Information acquisition should stop if either:

\[
\rho_K(\mathcal B)\le\epsilon,
\]

or no remaining query has sufficient estimated decision value after accounting for information cost and latency.

The guiding principle is:

> Stop once the remaining uncertainty is no longer important enough to affect a sufficiently good recommendation.

---

# 26. Replanning

The initial paper uses:

\[
\boxed{\text{event-triggered receding-horizon replanning}}
\]

rather than precomputed contingency trees.

Examples of replanning triggers:

- significant traffic change;
- charger failure;
- material SOC deviation;
- user requirement change;
- arrival at a new planning horizon;
- loss of feasibility of the current recommendation.

The planner may then recompute:

- detour envelope;
- Opportunity Regions;
- candidate microplans;
- relevant uncertainty;
- information queries.

---

# 27. Two-Time-Scale Planning

The framework should support two computational regimes.

## 27.1 Pre-trip / slow planning

Large compute and information budget.

Used for:

- alternative macro corridors;
- envelope expansion;
- Opportunity Region discovery;
- global route-plan skeleton;
- broad information acquisition.

---

## 27.2 En-route / fast replanning

Strict latency budget.

Used for:

- nearby Opportunity Region evaluation;
- concrete waypoint selection;
- limited local information acquisition;
- rapid replanning.

The architectural principle is:

\[
\boxed{
\text{slow global deliberation}
+
\text{fast local adaptation}.
}
\]

---

# 28. Simulator

The first scientific benchmark should use a controlled simulator containing a hidden ground-truth world:

\[
w^*.
\]

The oracle has access to all hidden information.

The tested agent only receives partial observations and must issue queries to reduce ambiguity.

This allows computation of:

\[
U(p^*,w^*),
\]

and therefore true decision regret.

The simulator should support controlled variation in:

- traffic;
- charging availability;
- queue times;
- POI quality;
- opening status;
- parking convenience;
- information freshness;
- tool latency;
- information cost;
- missing information.

---

# 29. Evaluation Metrics

The primary evaluation should not rely on a single composite score.

Report at least:

## Decision quality

\[
R_K
\]

and/or:

\[
MR_K.
\]

Also:

\[
P(R_K\le\epsilon).
\]

---

## Decision-space efficiency

- candidate compression ratio;
- number of Opportunity Regions;
- number of retained microplans;
- planning runtime.

---

## Information efficiency

- number of tool calls;
- information cost;
- bytes/items processed if useful;
- semantic-processing cost;
- decision latency.

---

## Reliability

- hard-constraint violation rate;
- infeasible-plan rate;
- missed-opportunity rate;
- expired-opportunity rate.

---

## Overall tradeoff

The principal experimental visualization should include:

\[
\boxed{
\text{Decision Regret}
\quad\text{vs}\quad
\text{Information / Compute Cost}.
}
\]

The proposed system should ideally shift the Pareto frontier outward.

---

# 30. Go / No-Go Tests

Before building a full system, validate the following three hypotheses.

## Go-1 — Opportunity abstraction

Show that large candidate compression is possible with low abstraction regret.

If removing 90% of candidate plans immediately causes large regret across realistic instances, the current abstraction hypothesis is weak and should be reconsidered.

---

## Go-2 — Decision-relevant acquisition

Compare against:

- random query;
- cheapest-query-first;
- widest-interval-first;
- uncertainty-first.

The proposed query-selection mechanism should produce lower regret for comparable information cost.

If generic uncertainty-first acquisition performs equivalently, the decision-relevance contribution is weak.

---

## Go-3 — Joint synergy

Compare:

1. Flat candidates + exhaustive information;
2. Flat candidates + active information;
3. Opportunity abstraction + exhaustive information;
4. Opportunity abstraction + active information.

The fourth configuration should show a meaningful efficiency advantage.

If the two components do not reinforce one another, the proposed unified story must be reconsidered.

---

# 31. Required Baselines

At minimum, implement or approximate the following baselines where feasible.

1. Shortest/fastest conventional route.
2. Fixed baseline-route POI corridor.
3. Fixed large detour envelope.
4. Full-candidate full-information oracle.
5. Full-candidate exhaustive information acquisition.
6. Opportunity abstraction + exhaustive information.
7. Flat candidates + active acquisition.
8. Uncertainty-first acquisition.
9. Cheapest/random acquisition.
10. Frontier-model/ReAct-style agent using the same tools, if later semantic/tool experiments are conducted.
11. Full proposed method.

The proposed method must not be compared only against weak or artificial baselines.

---

# 32. Required Ablations

Important ablations include:

### Adaptive envelope → fixed envelope

Measures whether adaptive search materially improves efficiency without losing useful detours.

### Opportunity Regions → flat POI planning

Measures the value of hierarchical abstraction.

### ε-Pareto compression → random or geometric representatives

Measures whether decision-preserving compression matters.

### Decision-relevant acquisition → uncertainty-first acquisition

Measures whether uncertainty must be evaluated through decision impact.

### Deadline-aware → deadline-unaware acquisition

Tests the central real-world phenomenon where information may arrive after an opportunity has disappeared.

### Oracle semantic processor → real semantic processors

Measures downstream sensitivity to semantic-processing quality.

---

# 33. External Validity

Simulation provides the primary controlled evaluation.

However, the final study should include at least one external-validity layer.

Possible options:

## Human pairwise route-plan preference

Participants compare realistic route plans.

Purpose:

> Validate whether the chosen utility representation approximately agrees with human judgments.

This does not require modeling long-term user profiles.

---

## Historical replay

Replay the algorithm on historical travel/traffic scenarios where available.

Purpose:

> Test whether the system behaves sensibly under realistic world states and real network structures.

Historical replay does not provide perfect counterfactual ground truth and should not be treated as a full utility oracle.

---

## Real-world case study

Run selected real trips or route-planning scenarios with live or frozen real APIs.

Purpose:

> Demonstrate ecological validity and implementation feasibility.

This may be limited in the first paper.

---

# 34. Initial Data Strategy

The first prototype should avoid dependency on proprietary APIs.

Preferred starting data:

- OpenStreetMap road network;
- OpenChargeMap or OSM charging stations;
- OSM POIs;
- EV-IPA-1000 where useful;
- simulated dynamic world attributes.

Commercial/live APIs may be integrated later.

All external datasets must be versioned or snapshot-frozen for reproducibility.

---

# 35. Recommended Engineering Stack

Initial implementation may use:

- Python 3.11 or 3.12;
- Pyrosm;
- igraph and/or NetworKit;
- GeoPandas;
- Shapely;
- PyProj;
- NumPy;
- SciPy;
- Pandas or Polars;
- PyArrow/Parquet;
- DuckDB;
- Pydantic;
- PyYAML;
- Matplotlib;
- pytest.

NetworkX may be used for debugging or toy tests, but should not become the default large-road-network backend unless performance measurements justify it.

---

# 36. Core Software Modules

The codebase should keep the following conceptual modules separate:

```text
graph/
envelope/
opportunity/
microplan/
uncertainty/
acquisition/
planner/
simulator/
semantic/
evaluation/
```

In particular:

\[
\boxed{
semantic/
\neq
planner/
}
\]

The planner must consume typed evidence and should not know whether it came from GPT, Claude, a classifier, an API, or an oracle simulator.

---

# 37. Required Typed Interfaces

The implementation should create explicit typed representations for at least:

- `EgoState`
- `RoadGraph`
- `Opportunity`
- `OpportunityRegion`
- `Gateway`
- `MicroPlan`
- `AmbiguityInterval`
- `Evidence`
- `InformationQuery`
- `RoutePlan`
- `RecommendationSet`
- `WorldState`
- `SimulatorState`

Exact fields may evolve, but semantic meaning must remain explicit.

Avoid passing untyped dictionaries through the entire system.

---

# 38. Reproducibility Requirements

Every experiment must record:

- Git commit;
- experiment configuration;
- random seed;
- dataset versions;
- OSM snapshot date;
- charging-data snapshot date;
- semantic-model identifier where relevant;
- tool configuration;
- ambiguity/noise parameters.

Raw source data should be immutable.

Processed data should preferably be reproducible from scripts and configuration.

Experiment logic must not exist only in notebooks.

---

# 39. Implementation Order

The project should be implemented in the following order.

## Milestone 1 — Road graph

- Parse frozen OSM data.
- Build routable graph.
- Generate realistic OD pairs.
- Verify shortest-path computation.

---

## Milestone 2 — Safe Detour Envelope

Implement:

\[
d_s(v),d_d(v)
\]

and:

\[
V_B=
\{v:d_s(v)+d_d(v)\le B\}.
\]

Verify mathematically and with tests that feasible bounded-detour paths are retained.

---

## Milestone 3 — Adaptive Envelope

Implement envelope expansion up to an explicit maximum budget.

Do not yet add LLMs or reviews.

---

## Milestone 4 — Opportunity Regions

Extract POIs/opportunities.

Develop route-attached Opportunity Region generation.

Visualize and inspect regions, but do not use qualitative inspection as the primary evaluation.

---

## Milestone 5 — Microplans and ε-Pareto compression

Construct local activity bundles and representative microplans.

Measure:

\[
\text{compression ratio}
\]

against:

\[
R_{\mathrm{abs}}.
\]

This completes Go-1.

---

## Milestone 6 — Controlled uncertainty simulator

Create hidden world states and interval observations.

At this point use an oracle semantic processor.

---

## Milestone 7 — Minimax-regret recommendation

Implement Top-\(K\) robust recommendation under ambiguity sets.

---

## Milestone 8 — Query baselines

Implement:

- random;
- cheapest;
- uncertainty-first;
- widest-interval-first.

---

## Milestone 9 — Decision-relevant acquisition

Implement plan/query pruning and approximate minimax-regret information acquisition.

This completes Go-2.

---

## Milestone 10 — Joint refinement

Combine Opportunity Region refinement and information acquisition.

Evaluate Go-3.

---

## Milestone 11 — Semantic processors

Only after Go-1/2/3 succeed, integrate actual semantic models.

---

## Milestone 12 — External validity

Add human comparison, replay, or selected real-world case studies.

---

# 40. Forbidden Silent Simplifications

Implementation agents must **not** silently make any of the following changes.

Do not:

- restrict all POIs to a fixed buffer around the shortest route;
- replace adaptive detour search with only top-3 standard navigation routes;
- treat Opportunity Regions as simple geographic K-means clusters without justification;
- remove information latency from the model;
- treat unknown information as negative information;
- convert all uncertainty into arbitrary point estimates;
- let the LLM directly override hard feasibility constraints;
- replace Top-\(K\) recommendation with only one deterministic route unless running an explicit ablation;
- remove microplan activity bundling;
- make the semantic processor inseparable from the planner;
- introduce persistent user profiling into the first study;
- require live commercial APIs for core benchmark execution;
- evaluate only visually or through anecdotal case studies;
- claim full optimality after restricting the decision space without measuring abstraction regret;
- modify the mathematical formulation purely because another version is easier to code.

If one of these simplifications appears necessary, document the issue and request a research-level decision.

---

# 41. Allowed Implementation Flexibility

Codex and other implementation agents may independently choose or propose:

- spatial indexing techniques;
- graph-storage representation;
- shortest-path implementation;
- clustering algorithm;
- gateway detection method;
- approximate Pareto algorithms;
- caching strategies;
- parallelization;
- data serialization;
- query-score surrogate;
- minimax-regret approximation;
- sampling scheme;
- visualization implementation.

However, these choices must preserve the research semantics in this document.

---

# 42. Initial Success Criterion

The first meaningful prototype is successful if it demonstrates all three:

### 1.

A very large reduction in route/POI candidate space with low empirical abstraction regret.

### 2.

Decision-relevant information acquisition achieves lower regret than generic uncertainty-first acquisition at comparable query budgets.

### 3.

Joint Opportunity Region + active acquisition produces a superior regret-cost tradeoff relative to either component alone.

Until these effects are observed, do not spend substantial resources on:

- fine-tuning semantic models;
- large-scale human studies;
- proprietary APIs;
- elaborate UI;
- production deployment.

---

# 43. Research Philosophy

This project is based on the following principle:

> A useful decision system does not need to understand every possible route, nor does it need to know every fact about the world.

Instead, it should determine:

1. which parts of the decision space remain potentially valuable;
2. which unknown facts can still change the decision;
3. whether the value of obtaining those facts exceeds their cost and latency;
4. when enough is known to make a sufficiently good recommendation.

The intended system therefore performs:

\[
\boxed{
\text{decision-space refinement}
\leftrightarrow
\text{information-space refinement}
}
\]

until further refinement has negligible decision value.

A concise description of the research objective is:

> **Know only what is necessary, search only where it matters, and recommend before the opportunity disappears.**