# Milestone 4R Implementation Plan

**Project:** dy-HiRoute  
**Normative input:** `RESEARCH_SPEC_v0.2.md`  
**Purpose:** implement the new stop-planning semantics without prematurely rebuilding the full hierarchical/active-information system.

---

## 1. Execution strategy

Milestone 4R should be implemented as a **stage-gated semantic revision**, not as one large end-to-end rewrite.

The first implementation pass should establish:

1. a correct static Stop Site substrate;
2. a deterministic trip-conditioned evaluator;
3. a flat stop-planning baseline;
4. exact behavioral regression tests on synthetic cases;
5. a limited real-data diagnostic on the existing development ODs.

Do **not** rebuild the final Opportunity Region hierarchy or full Go-2 active-information algorithm until this baseline passes.

---

## 2. Protected assets

Treat all accepted M1–M4B source artifacts and reports as read-only unless a new file is explicitly required.

At the start:

- inspect the repository layout;
- record `git status` if Git is available;
- create a manifest/hash snapshot of protected data/report artifacts;
- do not alter frozen PBFs, graph artifacts, OD files, M1/M2/M3A outputs, M4A outputs, or M4B outputs;
- place new work under the repository's existing convention for a new milestone; if no convention exists, use a clearly isolated `milestone_4r/` namespace.

At the end, verify protected artifacts are byte-identical.

No new external data download is required for the first 4R pass.

---

## 3. Stage R0 — Repository and schema audit

Before coding the new semantics:

- inspect the existing graph-loading API;
- inspect the M4A opportunity inventory schema;
- inspect how capabilities (`charge`, `parking`, `rest`, `services`, `meal`, `sleep`, `toilets`, etc.) are represented;
- inspect existing access-node attachment fields;
- inspect M4B routing/cache utilities that can be reused without inheriting old compound-task semantics.

Produce a short schema note documenting the exact fields used.

Do not infer undocumented fields from filenames or assumptions.

---

## 4. Stage R1 — Static Stop Site builder

### 4.1 Conservative anchor rule

For the first 4R implementation, build Sites only from raw opportunities that are already transportation-capable under the existing inventory.

Primary anchor-capability set:

- `charge`;
- `parking`;
- `rest`;
- `services`.

A raw `meal`, `sleep`, `groceries`, `pharmacy`, or `toilets` object must **not** become a vehicle anchor merely because it is a POI.

If a raw object has both a transport-anchor capability and a non-transport capability, it may be an anchor because of the transport capability.

Do not introduce new OSM semantic assumptions unless they are explicitly documented in the report.

### 4.2 Stable identity

Site identity must be independent of:

- OD pair;
- detour budget;
- current SOC;
- scheduled-stop window;
- preference parameters.

For the first pass, prefer one stable Site per raw transportation anchor. Do not aggressively merge neighboring anchors.

If duplicate-looking anchors exist, report them; do not invent a semantic facility-dedup rule in 4R-A.

### 4.3 Static-only schema

A saved `StopSite` must contain static primitives only, e.g.:

- stable `site_id`;
- source OSM identity;
- coordinates;
- attached road/access node;
- transport capabilities;
- charger/parking/access fields already supported by existing data;
- objective context/tag evidence if available;
- aggregate local-support primitives.

It must not store:

- current detour;
- current ETA;
- arrival SOC/energy;
- current generalized cost;
- OD-specific progress;
- user preference score.

Add tests that reject or flag accidental dynamic fields in the static schema.

---

## 5. Stage R2 — Aggregate local-support builder

The theoretical contract is local human accessibility. The first implementation may use a clearly labeled geographic-distance proxy.

### Primary diagnostic radii

Use configuration rather than a hard-coded constant.

Recommended primary/sensitivity values:

\[
\rho_{\rm local}\in\{250,500,750\}\text{ m},
\]

with 500 m as the primary diagnostic setting.

For each Site, compute at minimum:

- meal-object count within radius;
- nearest meal-object distance;
- toilet-object count and nearest distance;
- lodging-object count and nearest distance for future compatibility.

Do not rank individual businesses.

For the primary scheduled-stop satisfaction rule, use

\[
N_{\rm meal}\ge1
\]

and keep the threshold configurable.

### Efficiency requirement

Do not perform an \(O(|S||O|)\) all-pairs scan.

Use an appropriate spatial index such as a KD-tree, BallTree, or geospatial index and report build/query time and memory.

---

## 6. Stage R3 — Trip-conditioned evaluator

Implement a separate layer that takes:

- current trip state;
- partial plan;
- a static Site;
- EV configuration;
- requirement configuration;

and returns dynamic features such as:

- source-to-Site or previous-stop-to-Site travel time/distance;
- Site-to-destination travel time/distance when needed;
- arrival time;
- arrival energy;
- detour;
- required charging energy;
- charging duration;
- scheduled-window penalty;
- requirement satisfaction.

No trip-conditioned value may be written back into the static Site dataset.

---

## 7. Canonical EV configuration

Use a parameterized EV model. Do not couple the code to a single vehicle.

For regression/default diagnostics, use a simple canonical configuration:

- battery capacity: 60 kWh;
- deterministic consumption: 0.16 kWh/km;
- terminal reserve: 10% battery;
- robust margin: 0 in deterministic primary tests;
- charging curve: configurable piecewise function.

The charging API must support nonlinear curves. A default synthetic curve may be specified in configuration, but the report must label it as an experimental canonical EV model rather than measured real-vehicle performance.

Do not use “charge to 80%” as a rule.

---

## 8. Stage R4 — Flat deterministic planner

Implement the planner before any new Region hierarchy.

Required semantics:

- energy feasibility is hard;
- scheduled-stop requirement is independent of charging;
- one stop can satisfy both;
- stop duration uses compatible makespan;
- distinct vehicle stops incur `lambda_stop`;
- charging amount is a decision variable;
- extra energy has value only through downstream route consequences.

### 8.1 Planner interfaces

Prefer a general state/label representation that can support multi-stop extension, containing at least:

- current vehicle anchor/state;
- elapsed clock time;
- current energy;
- requirements satisfied;
- number of vehicle stops;
- accumulated generalized cost.

The implementation may use label-setting, DP, or another stateful search method.

### 8.2 Exactness claims

Do not call a large real-data planner “exact” unless all candidate-generation and transition restrictions have a proof that they preserve the stated feasible set.

For the first 4R pass:

- synthetic small-graph tests may be exhaustive/exact;
- one-stop real-data evaluation may be exhaustive over all eligible Sites;
- any multi-stop real-data diagnostic that uses candidate caps, sparse transitions, or heuristics must be labeled diagnostic/approximate.

Do not repeat the 4B mistake of letting an implementation shortcut silently redefine feasibility.

---

## 9. Stage R5 — Synthetic behavioral regression suite

Build small deterministic graph fixtures where the correct result can be checked exhaustively.

At minimum cover:

- enough energy + scheduled stop → no forced charge;
- mandatory charging;
- one charger stop simultaneously satisfying the scheduled activity;
- local meal object never becomes a second vehicle waypoint;
- same anchor with charge/meal/toilet counts as one stop;
- no fatigue inference;
- later meal-aligned charger may beat earlier charger while reserve remains feasible;
- 76% sufficient for destination → no wait for 80%;
- extra 15 min charging now avoids a 25 min later stop;
- stop-count penalty changes a near-tie;
- optimistic bound cannot materially beat incumbent → prune before query;
- materially better unknown candidate remains conditionally viable;
- fallback after unfavorable query;
- query latency destroys fallback → do not wait;
- Region IDs alone never change the flat feasible set.

These are semantic acceptance tests, not illustrative demos.

---

## 10. Stage R6 — Minimal uncertainty/query interface

Do not implement full Go-2 yet.

Implement only the types/functions required to express:

- `present / unknown / absent`;
- charger existence vs usability;
- cost interval `[LB, UB]`;
- `epsilon_dec` pruning;
- query latency;
- fallback feasibility after latency.

A synthetic query may reveal a binary charger usability state.

Do not add Bayesian probabilities to the planner merely because a synthetic world generator uses random masks.

If unavailability is later sampled, keep world-generation probability separate from the planner's ambiguity representation.

---

## 11. Stage R7 — Real-data development diagnostic

Use the existing 30 ODs only as a development set.

The first real-data report should focus on semantic-substrate diagnostics, not paper-level Go-1 claims.

Report at minimum:

- raw opportunity count used;
- number of transportation anchors / Stop Sites;
- Site counts by anchor capability;
- aggregate-support coverage at 250/500/750 m;
- fraction of Sites with meal support;
- fraction of chargers with meal support;
- Site counts inside practical Safe Detour Envelopes;
- one-stop exact diagnostic results where tractable;
- runtime and peak memory;
- any ODs/scenarios for which a required semantic test cannot be instantiated from the real data.

Do not tune choices against known bad ODs and then present the same 30 ODs as final validation.

---

## 12. Region work is gated

Do not implement a new hierarchical Region planner until:

- static Sites are stable;
- support aggregation passes tests;
- trip-conditioned fields are cleanly separated;
- synthetic planner acceptance tests pass;
- the flat baseline has a credible real-data diagnostic.

After that gate, rebuild Regions over Stop Sites and test bounds/refinement without hard feasibility restriction.

The old M4A/M4B Region partition may be used for diagnostics only; it is not automatically the new normative Region structure.

---

## 13. Deliverables

The first 4R implementation pass should produce, using repository naming conventions where available:

- source code for static Site construction;
- source code for support aggregation;
- trip-conditioned evaluator;
- deterministic planner;
- minimal uncertainty/query data types;
- unit/regression tests;
- a reproducible config file;
- a serialized Stop Site artifact;
- diagnostic CSV/Parquet outputs;
- `MILESTONE_4R_REPORT.md`.

The report must include:

- exact commands;
- environment/package versions;
- input artifact hashes/identifiers;
- configuration values;
- protected-file verification;
- test count/results;
- runtime and memory;
- limitations;
- clear exact-versus-approximate statements.

---

## 14. Acceptance gate

Milestone 4R-A passes only if all of the following hold:

1. all pre-existing tests still pass;
2. all new 4R semantic regression tests pass;
3. no protected M1–M4B artifact changed;
4. Site IDs are independent of OD/budget/preferences;
5. static Site files contain no trip-conditioned fields;
6. non-transport POIs are not emitted as independent vehicle waypoints in the scheduled-stop core;
7. same-anchor charge + scheduled activity counts as one stop and uses overlap semantics;
8. global charging tests demonstrate that extra current charging can remove a later stop;
9. extra terminal SOC is not rewarded by itself;
10. support aggregation is reproducible and avoids quadratic all-pairs scanning;
11. every approximation is explicitly labeled;
12. the report does not claim revised Go-1 success yet.

If any semantic acceptance test fails, fix the model before proceeding to Region hierarchy work.

---

## 15. Recommended Codex execution mode

Use a high-reasoning coding configuration. The task requires repository archaeology, schema preservation, algorithm design, regression tests, and a scientific report; correctness matters more than speed.

Run in a fresh branch if Git is available.

The companion `MILESTONE_4R_CODEX_PROMPT.md` is intentionally scoped to this first stage-gated implementation pass.
