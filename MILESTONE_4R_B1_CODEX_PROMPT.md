# Codex Prompt — Milestone 4R-B1

You are working in the existing **dy-HiRoute** research repository.

Your task is to implement and evaluate:

\[
\boxed{\textbf{Milestone 4R-B1 — Exact One-Stop Hierarchical Validation}}
\]

This is a **theorem-validation and pruning-potential experiment**, not an open-ended optimization exercise.

Read the following files in this order before changing code:

1. `RESEARCH_SPEC_v0.2.md`
2. `MILESTONE_4R_REPORT.md`
3. `MILESTONE_4R_B0_FORMAL_SPEC.md`
4. `MILESTONE_4R_B1_EXPERIMENT_PROTOCOL.md`

Treat items 3 and 4 as the normative B1 theory and preregistered experiment contract.

Do not silently weaken, reinterpret, or replace their definitions.

---

# 0. Precondition: freeze the accepted 4R-A baseline

Milestone 4R-A has already passed acceptance and is the scientific baseline for B1.

Before implementation:

- inspect Git status and branch history;
- verify the accepted 4R-A artifacts, tests, and source hashes;
- verify that the working tree corresponds to the accepted 4R-A state plus the supplied B0/B1 specification files.

The previously reported 4R-A work was on branch:

`codex/milestone-4r-a`

and had not yet been committed at the time of the acceptance report.

## Hard rule

If the accepted 4R-A baseline is still uncommitted:

- **do not auto-commit user work**;
- **do not start B1 implementation on top of an ambiguous dirty baseline**;
- stop and report that a frozen/committed 4R-A baseline is required first.

Once the accepted baseline is committed/frozen, create a fresh B1 branch following repository conventions, e.g.:

`codex/milestone-4r-b1`

Do not rewrite or regenerate accepted M1–M4R-A outputs.

---

# 1. Scientific objective

B1 answers two separate questions.

## Q1 — correctness

Does hierarchical search preserve the exact optimum of the declared real-data one-stop domain while satisfying every B0 lower-bound and concretization theorem?

Correctness failures are bugs/theory violations.

## Q2 — pruning potential

If correctness holds, can a theorem-guided Region hierarchy materially reduce concrete Stop-Site evaluation relative to exhaustive flat one-stop evaluation?

B1 is still a development-stage one-stop validation. It does **not** establish the final multi-stop Revised Go-1 result.

Do not proceed to B2 multi-stop work in this run.

---

# 2. Non-negotiable theoretical rules

The following rules are mandatory.

1. A Region is a **search abstraction**, never a physical-feasibility boundary.
2. Static Region identity must be independent of OD, SOC, envelope budget, role, preference, and \(\epsilon\).
3. The online search node is a role/state-conditioned View:

   \[
   N=(R,\alpha,\ell).
   \]

4. Role predicates are exact in B1.
5. `charge_meal`, `charge_parking`, etc. must not reappear as primitive task types.
6. Unknown is not absent, but B1 uses the deterministic observed-role domain from 4R-A; do not invent a partial-information role policy here.
7. Selected fastest-path **actual length** is the energy-routing quantity in the accepted B1 domain.
8. Do **not** assume that fastest-path actual length is a metric.
9. Do **not** replace \(\omega_{L^-},\omega_{L^+}\) with independent shortest-distance diameter unless a separate proof is supplied.
10. Lower-bound pruning requires an admissible lower bound.
11. RCCs and lower bounds are different objects.
12. A failed RCC margin test means **refine / certificate inconclusive**, not “Region infeasible”.
13. Any \(\epsilon\)-optimality claim is only within the declared B1 domain and Safe Detour Envelope.
14. Oracle certificates may measure logical pruning potential but may not be counted as saved online computation when they were built from all per-Site values.
15. Do not tune the hierarchy after observing B1 outcomes.

---

# 3. Preservation and audit

Before new source code is written:

- run all accepted pre-existing and 4R-A tests;
- capture the exact test result;
- capture Git status;
- hash/verify protected accepted artifacts exactly as 4R-A did;
- inspect the 4R-A Stop Site schema;
- inspect the flat zero/one-stop evaluator;
- inspect envelope/routing APIs;
- inspect the accepted native fastest-route time + actual-length semantics;
- inspect available graph-partition libraries/dependencies without installing anything;
- inspect repository naming and report conventions.

Do not install packages or download new geographic data unless explicitly authorized by the user.

Record this audit in a B1 preservation/provenance artifact.

---

# 4. Declared B1 cases

Use exactly the preregistered 480 development cases:

\[
30\ ODs
\times
4\ envelope\ ratios
\times
2\ initial\ SOCs
\times
2\ scenarios.
\]

Envelope ratios:

- 1.05
- 1.10
- 1.20
- 1.40

Initial SOC:

- 0.30
- 0.76

Scenarios:

- `energy_only`
- `energy_and_scheduled`

Retain the accepted 4R-A primary configuration:

- battery: 60 kWh
- consumption: 0.16 kWh/km
- terminal reserve: 10%
- robust margin: 0 in the deterministic B1 primary run
- canonical piecewise charging curve from 4R-A
- support radius: accepted primary 500 m
- scheduled support predicate: `meal_count >= 1`
- scheduled window: 0.40–0.70 of OD baseline time
- scheduled duration: 2700 s
- scheduled requirement: hard
- scheduled activity compatible with charging
- stop overhead: 300 s
- `lambda_stop = 600 s`
- distance penalty: 0

Do not tune any parameter per OD.

---

# 5. Flat exhaustive reference

For every case, run or reuse the accepted exhaustive 4R-A zero/one-stop evaluator over **all** eligible concrete Sites.

This is the reference oracle for the declared domain.

For each case save at minimum:

- exact eligible Site IDs;
- zero-stop feasibility/cost;
- every concrete one-stop feasibility/cost;
- role(s) satisfied;
- selected fastest-leg times;
- selected fastest-leg actual lengths;
- arrival energy;
- required departure energy;
- charging duration;
- scheduled start;
- stop completion time;
- generalized cost;
- flat optimum;
- deterministic tie result.

The flat result must not use Region membership.

Do not change the flat oracle merely to make the hierarchy easier to match.

---

# 6. B1 role generation

Generate role-conditioned branches from independent requirements.

Allowed role vocabulary:

- `C`
- `S`
- `CS`

Interpretation:

- `C`: one concrete Site is charging-capable;
- `S`: one concrete Site satisfies the scheduled-support predicate;
- `CS`: the **same concrete Site** satisfies both.

A Site may appear only in roles it truly satisfies.

Zero-stop is a separate concrete action outside the Region tree.

The union of zero-stop plus all role-conditioned concrete Site actions must equal the flat declared feasible action set.

Add explicit tests for this equality.

---

# 7. Pre-register the static hierarchy before comparative results

B1 must use one deterministic topology-first hierarchy for the primary run.

## 7.1 Allowed implementation choice

Use the following frozen choice order:

1. If the existing environment/repository already contains a deterministic reproducible graph-partition primitive suitable for recursive road-cell partitioning, use it.
2. Otherwise implement deterministic recursive graph bisection using only static road topology and accepted access-node data.

The choice must be based only on:

- availability;
- determinism;
- reproducibility;
- memory/runtime feasibility;
- compatibility with the static hierarchy contract.

It must **not** be based on pruning results.

Do not test several partition algorithms and select the one with the best B1 performance.

## 7.2 Primary structural parameters

For the primary hierarchy, freeze:

- branching factor: 2
- target leaf capacity: 64 Stop Sites
- deterministic tie-breaking: stable road-node/Site identity order

If a node cannot be cleanly split while preserving deterministic topology partition semantics, it may become an early leaf; record the reason.

## 7.3 Predeclared sensitivity

Only after the primary hierarchy is fully built and frozen, optional structural sensitivity may use:

- leaf capacity 32
- leaf capacity 128

Use the **same partition mechanism**.

Report all sensitivity results.

Do not replace the primary 64-Site hierarchy after seeing sensitivity outcomes.

## 7.4 Freeze artifact

Before running any 480-case hierarchical comparative experiment, write an immutable preregistration artifact containing:

- partition mechanism;
- implementation version/hash;
- hierarchy construction inputs;
- branch factor;
- leaf capacity;
- deterministic seed if any;
- all tie rules;
- hierarchy hash;
- Region count by depth;
- leaf-size distribution;
- parent/child/Site coverage checks.

Once the comparative run starts, do not rebuild the primary hierarchy.

---

# 8. Static hierarchy invariants

The primary hierarchy must satisfy:

- root covers all attached B1 Stop Sites;
- children are disjoint;
- union(children) = parent;
- every Site belongs to exactly one leaf;
- Site IDs are never dropped because of Region geometry;
- Region IDs and memberships are invariant across all 480 cases;
- role filtering happens in the dynamic Region View, not in the static tree;
- envelope filtering happens in the dynamic Region View, not by rebuilding the tree.

Implement exact artifact-level tests for these invariants.

---

# 9. B1-O — Oracle-certificate hierarchy

B1-O is mandatory.

Its purpose is to validate theory and measure **logical pruning potential** without confounding the result with a weak cheap certificate.

For each current Region View

\[
N=(R,\alpha,\ell),
\]

derive the current concrete role/envelope subset and, from exact per-Site reference quantities, compute:

\[
\widehat T^-,
\widehat T^+,
\widehat L^-,
\widehat L^+,
\]

\[
\omega_{T^-},
\omega_{T^+},
\omega_{L^-},
\omega_{L^+}.
\]

Construct the B0 oracle RCC:

\[
\Gamma_t^{oracle}(N)
=
(
\omega_{T^-},
\omega_{T^+},
\omega_{L^-},
\omega_{L^+}
).
\]

Implement the B0 one-stop relaxed lower bound and margin checks exactly as specified.

## Critical accounting rule

The exact per-Site quantities used to build oracle Region summaries have already been computed.

Therefore:

- do not count them as concrete evaluations avoided;
- do not report B1-O wall-clock speedup as a hierarchy computational saving;
- do not claim routing-call savings from B1-O;
- report only logical expansion/pruning potential.

B1-O is a theorem-guided potential study.

---

# 10. B0 theorem implementation requirements

Implement independent tests for the following.

## 10.1 Directed road-time diameter theorem

Where finite Region directed diameter is computed/available, verify:

\[
\omega_{T^-}\le\Delta_T,
\qquad
\omega_{T^+}\le\Delta_T,
\]

and

\[
0\le H^*-\widehat H\le\Delta_T.
\]

If directed pair distances are not finite, the static certificate is \(+\infty\); do not fabricate a finite value.

This theorem is diagnostic in B1-O unless a deployable diameter representation is later used.

## 10.2 Energy perturbation

Verify for every tested Region View:

\[
\widehat E^{arr}-E^{arr}_s
\le
\kappa\omega_{L^-},
\]

\[
E^{req}_s-\widehat E^{req}
\le
\kappa\omega_{L^+},
\]

and required charge perturbation:

\[
q_s-\widehat q
\le
\kappa(\omega_{L^-}+\omega_{L^+}).
\]

## 10.3 Charging perturbation

Using the accepted canonical curve and

\[
P_{\min}=30\text{ kW},
\]

verify the conservative bound:

\[
C_s-\widehat C
\le
3600
\frac{
\kappa(\omega_{L^-}+\omega_{L^+})
}{
P_{\min}
}.
\]

Do not assume Site-specific charging heterogeneity in the primary B1 model.

## 10.4 Schedule perturbation

Verify the hard-window margin transfer based on:

\[
m_{\rm deadline}
=
b-\widehat y,
\]

and

\[
m_{\rm deadline}\ge\omega_{T^-}.
\]

A failed margin test is inconclusive and must trigger refinement, not infeasibility.

## 10.5 One-stop aggregation-gap corollary

For every Region View whose B0 margin conditions certify concretization, verify:

\[
0
\le
J_R^*-\widehat J_R
\le
\omega_{T^-}
+
\omega_{T^+}
+
\gamma_C.
\]

Record all margins, observed gaps, and bound slack.

Expected theorem violations:

\[
0.
\]

---

# 11. Oracle hierarchical search

Use best-bound-first search.

Maintain:

- `OPEN`
- admissible Region lower bound \(L(N)\)
- concrete feasible incumbent \(U\)

Zero-stop should seed/update \(U\) when feasible.

For every Region View:

1. exact role/envelope filter;
2. if empty, discard;
3. compute oracle lower bound/RCC;
4. if

   \[
   L(N)\ge U-\epsilon,
   \]

   prune;
5. otherwise, if leaf, enumerate its concrete Sites exactly;
6. otherwise refine to children.

When a concrete Site is evaluated, use the same evaluator/tie semantics as the flat reference.

Do not introduce a different objective implementation inside the hierarchy.

---

# 12. Numerical safety

Implement conservative numerical comparisons.

Do not prune using an unadjusted floating-point lower bound at the boundary.

Use explicit documented safety tolerance/outward adjustment, e.g.:

\[
L_{\rm safe}=L_{\rm num}-\tau_{\rm num}.
\]

Concrete incumbents must be verified feasible under the accepted numerical tolerances.

Record the exact tolerances in config and report.

---

# 13. Correctness hard gates H1–H5

Run the following before any empirical GO/NO-GO conclusion.

## H1 — lower-bound validity

For every evaluated Region View:

\[
L(N)\le J_R^*
\]

within conservative tolerance.

Required:

`0 violations`

## H2 — exact preservation

For all 480 primary cases with:

\[
\epsilon=0,
\]

hierarchical optimum equals flat optimum under accepted deterministic tie semantics.

Required:

`0 optimum mismatches`

## H3 — RCC validity

Every certified Region View must preserve all B0 hard constraints and satisfy the aggregation-gap bound.

Required:

`0 certificate violations`

## H4 — refinement preservation

For every Region:

- union(children) = parent Site IDs
- children disjoint
- no role-filtered action is lost during refinement

Required:

`0 lost/duplicated actions`

## H5 — static/dynamic separation

Hierarchy hash/membership must be identical across all:

- ODs
- envelope ratios
- SOCs
- scenarios
- epsilon values

Required:

`0 hierarchy mutations`

### Hard stop

If any H1–H5 condition fails:

- stop the comparative scientific interpretation;
- diagnose/fix the correctness problem;
- rerun the same preregistered protocol;
- do **not** tune the hierarchy or thresholds to hide the failure.

---

# 14. Primary epsilon and sensitivity

Primary run:

\[
\epsilon=0.
\]

Only after exact preservation succeeds, run secondary:

- 30 s
- 60 s
- 120 s

These are certified work-vs-gap sensitivities.

Do not substitute an approximate run for the exact primary result.

---

# 15. B1-O accounting and metrics

For each case record:

### Flat work

- eligible concrete Site count
- flat concrete Site evaluations

### Hierarchy logical work

- Region Views created
- Region Views popped
- Region lower bounds computed
- nodes pruned
- internal nodes refined
- leaves reached
- concrete Sites logically requiring leaf evaluation
- concrete Sites logically avoided by pruning

Define:

\[
r_c
=
1-
\frac{N_{\rm site,hier}(c)}
{N_{\rm site,flat}(c)}.
\]

In B1-O this is explicitly:

\[
\boxed{\text{logical Site-evaluation reduction potential}}
\]

not measured online compute saving.

Also record:

\[
G_k
=
U_k-\min_{N\in OPEN_k}L(N)
\]

against cumulative logical decision work.

---

# 16. B1-O preregistered GO/NO-GO classification

Do not change these thresholds after comparative results are observed.

## Strong GO

Require both:

\[
\operatorname{median}(r_c)\ge 70\%
\]

and

\[
P(r_c\ge50\%)\ge75\%.
\]

## NO-GO

If either:

\[
\operatorname{median}(r_c)<50\%
\]

or

\[
P(r_c\ge25\%)<75\%.
\]

## Gray zone

All other outcomes.

In a gray zone or NO-GO:

- do not immediately try another clustering algorithm;
- compute/inspect the preregistered gap diagnostics;
- identify whether weakness is model relaxation, Region aggregation, or certificate looseness;
- stop and report the structural diagnosis.

---

# 17. Gap diagnostics

Where defined, compute and report:

\[
G_{\rm model},
\qquad
G_{\rm agg},
\qquad
G_{\rm cert}.
\]

For the primary one-stop oracle experiment, emphasize \(G_{\rm agg}\).

Stratify by:

- envelope ratio;
- initial SOC;
- scenario;
- role (`C`, `S`, `CS`);
- OD;
- hierarchy depth.

Do not hide poor role-specific behavior inside overall medians.

If pruning is weak, no hierarchy redesign is allowed until this decomposition has been analyzed.

---

# 18. B1-D — Deployable-certificate stage

B1-D is **conditional**.

Proceed only if:

1. H1–H5 pass;
2. B1-O is complete;
3. a conservative deployable certificate/lower bound can be implemented without online enumeration of all concrete Sites in each Region.

If condition 3 is not met, do not improvise an empirical average or unsafe proxy.

Instead record:

`B1-D unresolved: no proven non-enumerative deployable certificate implemented`

and stop after B1-O.

This is an acceptable scientific outcome.

---

# 19. Allowed B1-D ingredients

A deployable bound may use only quantities that can be obtained without current-query enumeration/evaluation of the entire concrete Region, for example:

- static road-cell metadata;
- proven directed road-time diameter upper bounds;
- precomputed landmark summaries;
- Region boundary/gateway summaries;
- static role counts/bitsets;
- lazy summaries inherited from already-refined children;
- conservative route-length oscillation upper bounds **only if separately proved**.

Do not use:

- current exact per-Site objective values hidden inside a “summary”;
- empirical average route lengths as lower-bound certificates;
- shortest-distance diameter as a substitute for fastest-route actual-length oscillation without proof;
- a full Region scan and then count that scan as free.

---

# 20. B1-D accounting

For deployable B1-D, separately measure:

- static preprocessing cost;
- memory of hierarchy/summaries;
- per-query Region-bound work;
- actual concrete Site evaluations;
- actual extra routing/bound calls;
- concrete Site evaluations avoided;
- end-to-end wall time;
- hierarchy-only wall time;
- peak RSS.

Shared forward/reverse all-node routing work required by both flat and hierarchical methods is reported as shared work and is not credited as hierarchy savings.

---

# 21. B1-D preregistered gate

Let:

\[
r_c^{oracle}
\]

and

\[
r_c^{deploy}
\]

be exact-\(\epsilon=0\) logical/concrete Site-evaluation reductions.

Require:

\[
\operatorname{median}(r^{deploy})\ge50\%.
\]

Also require:

\[
\frac{
\operatorname{median}(r^{deploy})
}{
\operatorname{median}(r^{oracle})
}
\ge0.70.
\]

If reliable timing decomposition is available, also require median hierarchy bound/refinement time to be no greater than the median flat concrete-evaluation time actually replaced.

If timing attribution is not reliable, report count-based results and mark computational break-even unresolved rather than inventing a speedup claim.

---

# 22. What B1 must not do

Do **not**:

- add a hard same-Region feasibility rule;
- alter the flat oracle;
- downsample parking Sites to improve results;
- remove difficult ODs;
- tune hierarchy parameters after observing comparative outcomes;
- test many partitioners and report only the best;
- add consumer-business ranking;
- add learned user profiles;
- add Bayesian charger availability;
- implement full Go-2;
- implement real multi-stop B2;
- claim oracle-summary pruning as actual saved computation;
- claim unrestricted global optimality;
- claim final Revised Go-1 establishment from B1 alone.

---

# 23. Required tests

Add tests at least for:

1. static hierarchy root coverage;
2. disjoint child partition;
3. leaf uniqueness;
4. deterministic byte-/hash-reproducible hierarchy construction where serialization permits;
5. hierarchy independence from OD/SOC/envelope/role/preference;
6. exact role filtering;
7. zero-stop action preservation;
8. flat/hierarchy action-set equivalence;
9. B0 road-time theorem checks;
10. energy perturbation bounds;
11. charging perturbation bounds;
12. schedule margin transfer;
13. aggregation-gap bound;
14. safe pruning with \(\epsilon=0\);
15. safe pruning with positive \(\epsilon\);
16. earlier pruning remains valid after incumbent improves;
17. no false infeasibility on RCC margin failure;
18. all H1–H5 acceptance checks;
19. protected-artifact hash preservation.

Synthetic small fixtures should independently verify theorem edge cases before running the full development cases.

Include cases with:

- unreachable directed pairs;
- empty role-conditioned Region;
- exact decision-boundary equality;
- battery arrival margin exactly at the certificate;
- battery-capacity margin exactly at the certificate;
- schedule deadline exactly at the certificate;
- charging interval crossing piecewise curve breakpoints.

---

# 24. Required outputs

Use repository conventions and a new B1 result namespace.

Produce at minimum:

- B1 hierarchy artifact;
- hierarchy construction/preregistration manifest;
- Region membership/parent-child artifact;
- flat reference table or verified reference linkage;
- B1-O Region-view diagnostics;
- B1-O search traces;
- H1 violation table;
- H2 mismatch table;
- H3 RCC violation table;
- H4 coverage table;
- H5 hierarchy-stability table;
- per-case logical work metrics;
- role/envelope/OD stratified metrics;
- certified-gap trajectories;
- gap-decomposition outputs;
- optional B1-D deployable summaries/results if authorized by the conditions above;
- timing and memory logs;
- protected-file verification;
- `MILESTONE_4R_B1_REPORT.md`;
- `acceptance.json`.

All empty violation tables should still be emitted explicitly.

---

# 25. Report structure

`MILESTONE_4R_B1_REPORT.md` must clearly separate:

## A. Scope and declared domain

State exactly what is and is not optimized.

## B. Baseline preservation

Tests, hashes, Git state, inputs.

## C. Frozen hierarchy

Construction mechanism and preregistered parameters.

## D. Correctness H1–H5

Report each gate independently.

## E. B1-O oracle potential

Explicitly label all pruning as logical potential, not computational savings.

## F. GO/NO-GO classification

Apply the frozen thresholds mechanically.

## G. Gap diagnosis

Report \(G_{\rm model},G_{\rm agg},G_{\rm cert}\) where available.

## H. B1-D deployable stage

Only if a proven non-enumerative certificate exists.

## I. Runtime/memory

Separate shared routing, oracle diagnostic work, and deployable hierarchy work.

## J. Limitations

Include at minimum:

- 30 ODs are development data;
- one-stop declared domain only;
- fixed-envelope optimality only;
- no real multi-stop claim;
- no final holdout;
- no full active information acquisition;
- no user-learning/business-ranking claims.

## K. Final gate statement

Use one of:

- `B1 correctness failed — no empirical Go/No-Go interpretation`
- `B1-O strong GO`
- `B1-O gray zone`
- `B1-O NO-GO`
- plus, if applicable:
  - `B1-D deployable gate passed`
  - `B1-D deployable gate failed`
  - `B1-D unresolved`

Do not write `Revised Go-1 established`.

---

# 26. Hard-stop / escalation rules

Stop and report rather than silently improvising if:

- 4R-A accepted baseline is not cleanly frozen/committed;
- any protected accepted artifact changes unexpectedly;
- any pre-existing/4R-A test fails;
- hierarchy construction requires changing the declared action set;
- a graph partition dependency would need to be installed;
- the chosen partition mechanism is nondeterministic and cannot be made reproducible;
- H1–H5 fails and the failure cannot be clearly identified;
- a deployable route-length certificate would require assuming an unproved metric property;
- memory projections exceed the existing server guard;
- B1-D would require a current-query full Region scan that is then falsely counted as saved computation.

When escalating, describe:

1. the exact blocker;
2. which B0/B1 contract it conflicts with;
3. the smallest scientifically defensible next change.

Do not solve a theoretical blocker with an unregistered engineering shortcut.

---

# 27. Final acceptance condition for this Codex run

This run is complete when:

1. the accepted 4R-A baseline remains unchanged;
2. the primary hierarchy is frozen before comparative results;
3. all new theorem/unit tests pass;
4. H1–H5 are evaluated over the full primary B1 development set;
5. B1-O is completed and classified using the preregistered thresholds;
6. gap diagnostics are produced;
7. B1-D is either:
   - correctly completed with proven non-enumerative certificates, or
   - explicitly marked unresolved and not fabricated;
8. the B1 report and acceptance artifacts are written;
9. all protected hashes are reverified;
10. no B2/Go-2 work is started.

Then stop.

Do not continue automatically into a new hierarchy design, multi-stop planner, holdout experiment, or active-information stage.
