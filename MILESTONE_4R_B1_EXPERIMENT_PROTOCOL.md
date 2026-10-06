# Milestone 4R-B1 Experimental Protocol

**Project:** dy-HiRoute  
**Stage:** Milestone 4R-B1 — Exact One-Stop Hierarchical Validation  
**Status:** pre-registered protocol candidate; freeze before B1 implementation/results  
**Normative theory:** `MILESTONE_4R_B0_FORMAL_SPEC.md`  
**Development substrate:** accepted Milestone 4R-A Stop Sites and 30 development ODs  
**Scientific role:** validate the theorem-guided hierarchy and measure its pruning potential; **not** final holdout validation and **not** yet the final multi-stop Revised Go-1 claim.

---

## 1. Purpose

B1 asks two different questions and must keep them separate.

### Q1 — Correctness

Does the hierarchical search preserve the exact optimum of the declared one-stop domain and respect every B0 lower-bound/concretization theorem?

This is a correctness question. Any violation is a failure, not an unfavorable empirical result.

### Q2 — Pruning potential

Assuming correctness, does the hierarchy avoid enough concrete Site evaluation to justify continuing to a multi-stop hierarchical stage?

This is the empirical Go/No-Go question.

B1 must not conflate oracle diagnostic pruning with deployable computational savings.

---

## 2. Declared B1 domain

B1 uses exactly the accepted 4R-A real-data zero/one-stop domain.

For each development case:

- directed graph and routing semantics are unchanged;
- zero-stop is evaluated explicitly;
- one-stop candidates are attached Stop Sites eligible under the selected Safe Detour Envelope;
- source→Site and Site→destination are the accepted fastest-time directed legs;
- energy uses the actual lengths of those selected fastest-time legs;
- no candidate cap;
- no Region feasibility restriction;
- no real multi-stop search;
- canonical 4R-A EV/charging/scheduled-stop configuration unless explicitly listed below;
- the flat exhaustive one-stop evaluator is the reference oracle.

Any optimality statement is therefore:

\[
\boxed{
\text{optimal within this declared B1 domain and envelope.}
}
\]

---

## 3. Development cases

Use the same 30 repeatedly inspected ODs as **development data only**.

Primary cases reproduce the accepted 4R-A grid:

\[
30\ ODs
\times
4\ envelope\ ratios
\times
2\ initial\ SOCs
\times
2\ requirement\ scenarios
=
480\ cases.
\]

Envelope ratios:

\[
1.05,\ 1.10,\ 1.20,\ 1.40.
\]

Initial SOC:

\[
0.30,\ 0.76.
\]

Requirement scenarios:

1. `energy_only`;
2. `energy_and_scheduled`.

Scheduled-stop configuration remains the accepted 4R-A configuration:

- hard scheduled requirement;
- window at 0.40–0.70 of OD baseline travel time;
- duration 2700 s;
- charging-compatible;
- support predicate `meal_count >= 1`;
- fixed stop overhead 300 s;
- \(\lambda_{\rm stop}=600\) s;
- distance penalty \(=0\) for the primary theorem domain.

No parameter is tuned per OD.

---

## 4. Flat reference

For every case, run the accepted exhaustive flat zero/one-stop evaluator over every eligible concrete Site.

Record:

- flat optimum cost \(J_D^*\);
- selected concrete Site or zero-stop;
- role assignment;
- arrival/departure energy;
- charging duration;
- scheduled-start time;
- total clock time;
- stop count;
- exact eligible-Site count.

This flat result is the declared-domain reference for H1–H4.

The flat evaluator must remain independent of Region membership.

---

## 5. Search roles

Role branches are generated from the independent requirement state, not from pre-written compound tasks.

The B1 role vocabulary is:

\[
C,\quad S,\quad CS.
\]

Interpretation:

- \(C\): charging-capable next stop;
- \(S\): scheduled-stop-capable next stop;
- \(CS\): one concrete Site satisfies both independent requirements.

A Site may appear only in role branches it concretely satisfies.

Categorical role predicates are exact.

Zero-stop is evaluated outside the Region hierarchy as its own concrete action.

Role generation must preserve exactly the same feasible one-stop plan set as the flat reference.

---

## 6. Static hierarchy contract

B1 uses **one pre-registered deterministic hierarchy construction**. It must not be chosen after inspecting B1 comparative outcomes.

The hierarchy is topology-first:

1. Sites are attached to their accepted vehicle-road access nodes.
2. The vehicle graph is recursively partitioned into nested road cells.
3. A Region is the set of Stop Sites whose access nodes lie in a cell.
4. Region identity is independent of OD, SOC, envelope ratio, role, and preferences.
5. Children form a disjoint partition of the parent Site IDs.
6. Leaves contain a small exact-enumeration bucket; leaf size is fixed globally before comparative results are inspected.
7. Region membership never removes a concrete Site from the declared feasible set.

### 6.1 Construction choice rule

Before B1 result generation, repository/dependency audit may determine the **implementation mechanism** for deterministic balanced road-cell partitioning.

Allowed choice order:

1. reuse an already available deterministic graph-partition primitive if present and reproducible;
2. otherwise implement a deterministic recursive graph bisection using only static road topology/access-node data.

The choice may depend on availability/reproducibility, not on pruning outcomes.

No alternative partitioners may be tried and selected based on which gives better B1 results.

### 6.2 Fixed structural parameters

Structural parameters such as leaf capacity and branching factor must be declared in the B1 config before comparative results are run.

If a sensitivity analysis is desired, use a pre-declared small grid and report every value; do not select a best-performing value as the primary result post hoc.

---

## 7. Oracle-certificate hierarchy: B1-O

B1-O is a **theory/potential experiment**, not a runtime speedup claim.

For each Region View \(N=(R,\alpha,\ell)\), B1-O may use exact trip-conditioned per-Site quantities from the flat reference to compute:

\[
\omega_{T^-},
\quad
\omega_{T^+},
\quad
\omega_{L^-},
\quad
\omega_{L^+}.
\]

These form the oracle RCC:

\[
\Gamma_t^{oracle}(N).
\]

It may also compute the B0 one-stop relaxed lower bound \(\widehat J_R\).

### Critical accounting rule

Because B1-O obtains Region summaries from exact per-Site quantities, those underlying per-Site computations **must not be counted as computational work saved**.

B1-O may report only:

\[
\boxed{
\text{logical pruning / expansion potential under oracle certificates.}
}
\]

It must not claim wall-clock or routing-work savings from those oracle summaries.

This prevents circular accounting.

---

## 8. Deployable-certificate hierarchy: B1-D

B1-D is the first stage allowed to make an actual computational-work claim.

It may use only summaries that can be obtained without enumerating/evaluating every concrete Site in the Region for the current query.

Examples include:

- precomputed static road-cell summaries;
- admissible landmark summaries;
- lazy child summaries;
- conservative static/lazy upper bounds on oracle RCC components.

Every deployable bound must have a documented proof or direct exhaustive verification that it is conservative over the B1 development domain.

For any claimed deployable RCC:

\[
\Gamma^{oracle}
\preceq
\Gamma^{deploy}.
\]

For any deployable lower bound:

\[
L^{deploy}(N)\le J_R^*.
\]

If a safe deployable route-length oscillation bound is unavailable, that component is \(+\infty\); the implementation must refine rather than substitute an empirical average.

---

## 9. Hierarchical search policy

Use best-bound-first search over Region Views.

Maintain:

- `OPEN`: current Region frontier;
- \(L(N)\): admissible lower bound;
- \(U\): best verified concrete incumbent.

A node is pruned when

\[
L(N)\ge U-\epsilon.
\]

Otherwise:

- if a safe concrete witness/upper bound is available, update \(U\);
- if the node is a leaf, enumerate its concrete Sites exactly;
- otherwise refine to children.

Refinement must preserve exact Site-ID coverage.

Numerical comparisons use conservative B0 tolerances/outward safety.

---

## 10. Tolerance schedule

The primary correctness run uses

\[
\boxed{\epsilon=0}.
\]

Sensitivity runs use a pre-registered equivalent-time grid:

\[
\epsilon\in\{30,60,120\}\text{ s}.
\]

The \(\epsilon>0\) runs are secondary work-vs-certified-gap diagnostics.

They do not replace the exact \(\epsilon=0\) preservation result.

---

# Part I — Correctness gates

## 11. H1 — Lower-bound validity

For every evaluated Region View:

\[
L(N)\le J_R^*
\]

within documented conservative numerical tolerance.

Required result:

\[
\boxed{0\ violations.}
\]

Any violation is a hard failure.

---

## 12. H2 — Exact hierarchical preservation

For every one of the 480 primary cases at

\[
\epsilon=0,
\]

hierarchical search must return the same declared-domain optimum cost as flat exhaustive evaluation.

Required result:

\[
\boxed{0\ optimum\ mismatches.}
\]

If multiple concrete plans tie within the accepted deterministic tolerance, Site identity may differ only if their objective values are tie-equivalent under the declared flat tie semantics.

---

## 13. H3 — RCC/concretization validity

Whenever a Region View passes the B0 margin-aware concretization conditions:

- observed concrete hard feasibility must hold;
- the observed concrete cost increase over the relaxed Region solution must not exceed the derived B0 aggregation-gap bound.

Required result:

\[
\boxed{0\ certificate\ violations.}
\]

---

## 14. H4 — Refinement preservation

For every internal Region:

\[
IDs(R)
=
\biguplus_c IDs(c).
\]

Required result:

- zero lost Site IDs;
- zero duplicated IDs under the primary disjoint hierarchy;
- zero role-specific coverage loss after exact role filtering.

Any violation is a hard failure.

---

## 15. H5 — Static/dynamic separation

The Region tree and static Region IDs must be identical across:

- all 30 ODs;
- all envelope ratios;
- both SOC values;
- both requirement scenarios;
- all \(\epsilon\) values.

Only Region Views may vary.

Required result:

\[
\boxed{0\ static\ hierarchy\ mutations.}
\]

---

# Part II — Primary empirical measurements

## 16. Concrete Site evaluation ratio

For case \(c\),

\[
q_c
=
\frac{
N_{\rm site,\,hier}(c)
}{
N_{\rm site,\,flat}(c)
}.
\]

Site-evaluation reduction is

\[
r_c=1-q_c.
\]

A concrete Site counts as evaluated when the hierarchy performs the same trip-conditioned objective/feasibility evaluation that the flat reference would perform for that Site.

Merely reading a static Site ID or role bit does not count as a concrete evaluation.

---

## 17. Region work

Report separately:

- Region nodes popped from `OPEN`;
- Region lower-bound evaluations;
- Region refinements;
- leaves reached;
- Sites enumerated at leaves;
- Region nodes pruned without leaf expansion.

Do not combine these into an arbitrary weighted score.

---

## 18. Routing work

Report separately:

- all-node routing arrays/labels required by both methods;
- additional routing calls used only by the hierarchy;
- concrete Site routing/evaluation calls avoided;
- static preprocessing cost;
- per-query bound cost.

If the same forward/reverse all-node routing arrays are required before both flat and hierarchical one-stop evaluation, that shared work is reported but cannot be credited as hierarchy savings.

---

## 19. Time and memory

Report:

- hierarchy preprocessing wall time and peak RSS;
- per-case bound/search wall time;
- flat per-case planning wall time;
- end-to-end per-case time including shared routing;
- peak memory.

Wall-clock speedup is secondary in B1 because the one-stop experiment is a validation domain and shared all-node routing may dominate total time.

---

## 20. Certified-gap trajectory

During search, record:

\[
G_k
=
U_k-\min_{N\in OPEN_k}L(N).
\]

Plot/record decision work against \(G_k\).

Primary scientific visualization:

\[
\boxed{
\text{concrete decision work}
\quad\text{vs}\quad
\text{certified optimality gap}.
}
\]

---

# Part III — Pre-registered Go/No-Go gates

## 21. Why the threshold is based on branching reduction

B1 is not the final multi-stop result. Its purpose is to determine whether hierarchical pruning is strong enough to justify B2.

If the one-step retained fraction is \(q\), then under a purely illustrative independent-branching approximation a two-step search has candidate-product scale \(q^2\).

This approximation is **not a theorem** and must not be reported as a predicted B2 speedup. It is used only to define a pre-registered notion of “material” one-step pruning.

A retained fraction

\[
q=0.30
\]

corresponds to a 70% reduction and an illustrative two-level factor

\[
1/q^2\approx 11.1.
\]

A retained fraction

\[
q=0.50
\]

corresponds to only a fourfold illustrative two-level reduction.

This motivates the following gates.

---

## 22. B1-O oracle-potential gate

After H1–H5 pass, classify the exact \(\epsilon=0\) oracle hierarchy using all 480 development cases.

### GO — strong pruning potential

Require both:

\[
\boxed{
\operatorname{median}(r_c)\ge 70\%
}
\]

and

\[
\boxed{
P(r_c\ge 50\%)\ge 75\%.
}
\]

Interpretation: the hierarchy removes most concrete evaluations in the typical case and at least half in a large majority of development cases.

### NO-GO — weak pruning potential

If either:

\[
\operatorname{median}(r_c)<50\%
\]

or

\[
P(r_c\ge25\%)<75\%,
\]

classify the current hierarchy/relaxation as insufficient to justify proceeding directly to B2.

### GRAY ZONE

All other outcomes are inconclusive.

In the gray zone, do **not** tune clustering thresholds against the same 480 cases. First diagnose:

\[
G_{\rm model},\quad
G_{\rm agg},\quad
G_{\rm cert}
\]

and return to the relevant theory/component if a structural weakness is identified.

---

## 23. B1-D deployable-work gate

B1-D is evaluated only after B1-O correctness passes and a conservative deployable certificate exists.

Let

\[
r^{oracle}_c
\]

and

\[
r^{deploy}_c
\]

be exact-\(\epsilon=0\) Site-evaluation reductions.

Require:

\[
\boxed{
\operatorname{median}(r^{deploy}_c)\ge 50\%
}
\]

and deployable pruning retention

\[
\boxed{
\frac{
\operatorname{median}(r^{deploy}_c)
}{
\operatorname{median}(r^{oracle}_c)
}
\ge 0.70.
}
\]

Additionally, hierarchy-only bound/refinement time must not exceed the flat concrete-evaluation time it replaces in the median case:

\[
\boxed{
\operatorname{median}(T_{\rm bound+refine})
\le
\operatorname{median}(T_{\rm flat\ site\ evaluation\ avoided}).
}
\]

If instrumentation cannot isolate the replaced flat work reliably, do not claim this timing gate; report counts and classify computational break-even as unresolved.

### Interpretation

Passing B1-D supports moving to B2 multi-stop hierarchy work.

Failing B1-D after a strong B1-O result means the theoretical hierarchy has pruning potential but the current cheap certificate machinery is not yet computationally adequate. Diagnose certificate/preprocessing design before changing the Region semantics.

---

## 24. What does not count as success

B1 is not considered successful merely because:

- Region candidate counts are smaller;
- a coarse Region table is compact;
- wall time improves due to unrelated caching;
- \(\epsilon>0\) gives high pruning while \(\epsilon=0\) fails preservation;
- oracle summaries prune heavily after computing all per-Site values;
- a tuned hierarchy wins only on selected ODs;
- a hard Region restriction silently deletes plans.

---

# Part IV — Gap diagnostics

## 25. Required decomposition

Where computable, report:

\[
G_{\rm model},
\quad
G_{\rm agg},
\quad
G_{\rm cert}.
\]

For the B1 exact one-stop oracle domain, the preferred design minimizes confounding so that \(G_{\rm agg}\) can be examined directly.

If pruning is weak:

- large \(G_{\rm agg}\) → Region construction/groups are too heterogeneous;
- large \(G_{\rm cert}\) → deployable summary is too loose;
- large \(G_{\rm model}\) → the residual planning relaxation is too weak.

No hierarchy redesign is allowed before this diagnosis.

---

## 26. Role/envelope stratification

Report primary metrics separately by:

- envelope ratio;
- initial SOC;
- requirement scenario;
- role \(C/S/CS\);
- OD.

Do not hide a poor role behind aggregate averages.

Especially inspect whether scheduled-stop-heavy branches and charging branches exhibit materially different pruning behavior.

---

# Part V — Anti-overfitting and decision rules

## 27. Development-set discipline

The 30 ODs are development data.

B1 may be used to:

- falsify the theory;
- validate correctness;
- diagnose hierarchy behavior;
- decide whether B2 is worth pursuing.

B1 may **not** be used as final paper holdout evidence.

After B2 algorithm/protocol freeze, final evaluation uses a new holdout set.

---

## 28. No post-result threshold tuning

The GO/NO-GO/GRAY thresholds in Sections 22–23 are frozen before B1 comparative results.

After results are observed:

- thresholds are not changed;
- failed ODs are not removed;
- hierarchy parameters are not retuned and rerun as if pre-registered;
- any new design is a new experimental version with an explicit reason derived from structural diagnosis.

---

## 29. Versioning rule

If H1–H5 fail, fix the correctness defect and rerun B1 under the same empirical thresholds.

If empirical pruning is weak, do not call the correction a “bug fix” unless it truly is one.

A new hierarchy/bound design after observing B1 outcomes must receive a new version identifier and be reported as a development iteration.

---

# Part VI — Required B1 outputs

## 30. Required artifacts

B1 should eventually produce:

- hierarchy metadata and deterministic construction manifest;
- Region parent/child/Site membership artifact;
- flat reference results;
- oracle Region-bound/RCC diagnostics;
- hierarchical search traces;
- per-case work metrics;
- correctness violation tables;
- gap-decomposition outputs;
- timing/memory logs;
- `MILESTONE_4R_B1_REPORT.md`;
- acceptance JSON recording all frozen gates and outcomes.

No B1 report may state “Revised Go-1 established” unless the report explicitly distinguishes oracle-potential evidence from deployable computational evidence.

---

# Part VII — Freeze statement

The B1 protocol freezes the following before implementation results are seen:

\[
\boxed{
\textbf{Correctness first: H1–H5 require zero violations.}
}
\]

\[
\boxed{
\textbf{Oracle summaries measure pruning potential, not actual saved computation.}
}
\]

\[
\boxed{
\textbf{Deployable savings require certificates that do not enumerate the whole Region online.}
}
\]

\[
\boxed{
\textbf{Primary B1 correctness uses }\epsilon=0\textbf{; }\epsilon>0\textbf{ is secondary.}
}
\]

\[
\boxed{
\textbf{Strong oracle GO: median Site-evaluation reduction }\ge70\%\textbf{ and at least 75\% of cases reduce }\ge50\%.
}
\]

\[
\boxed{
\textbf{Weak oracle NO-GO: median reduction }<50\%\textbf{ or fewer than 75\% of cases reduce at least 25\%.}
}
\]

\[
\boxed{
\textbf{B1 is still a development-stage one-stop validation; final Revised Go-1 requires later multi-stop and holdout evidence.}
}
\]
