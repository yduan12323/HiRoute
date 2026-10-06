# Milestone 4R-B2-B21 Experimental Protocol

**Project:** dy-HiRoute  
**Stage:** Milestone 5 / legacy namespace 4R-B2  
**Substage:** B2-1 — Exact Small-Domain Multi-Stop Validation  
**Status:** preregistered validation protocol before implementation  
**Primary purpose:** validate continuous-energy multi-stop exactness before any production-scale or long-haul claim  
**Frozen success endpoint:** deterministic exact multi-stop hierarchical planning + deployable evaluation + independent holdout

---

# 0. Stage rule

B2-1 is a **correctness milestone**, not a scalability milestone.

Its job is to determine whether the theory closed in B2-T1–T7 can be implemented without changing the declared decision problem.

B2-1 must validate:

\[
\boxed{
\text{continuous charging}
+
\text{multi-stop transitions}
+
\text{effect semantics}
+
\text{dominance}
+
\text{hierarchical action coverage}
}
\]

against an independent exact reference.

B2-1 does **not** authorize:

- long-haul performance claims;
- China-scale benchmarking;
- production scalability claims;
- SOC discretization;
- new charging heuristics;
- hierarchy retuning;
- new user preferences;
- active information / uncertainty;
- holdout consumption.

If any correctness gate fails, stop before B2-2.

---

# 1. Frozen theory basis

The implementation must conform to the accepted theory artifacts:

1. B2 formal specification;
2. B2 theory audit;
3. B2-T7 charging-frontier specification;
4. B2-T7 theorem audit.

The following theory choices are frozen:

- physical Markov state:
  \[
  y=(v,t,E,r);
  \]
- effect-labelled actions:
  \[
  \alpha\in\{C,S,CS\};
  \]
- semantic charging:
  \[
  q>0;
  \]
- finite piecewise-affine energy frontiers;
- explicit attained / limit-only status;
- lexicographic witness metadata;
- conservative strict-cost dominance;
- exact small-domain reference by finite regime enumeration;
- no SOC grid;
- no arbitrary \(q_{\min}\);
- no neutral/effect-free stop action.

---

# 2. Three independent computational objects

B2-1 compares three implementations.

## 2.1 REF — independent exact reference

REF is the correctness authority for the bounded diagnostic domain.

REF must:

1. enumerate every effect-labelled concrete Site sequence up to the declared diagnostic stop cap:
   \[
   H\le H_{\rm ref};
   \]
2. enumerate the finite charging-curve / schedule / makespan regimes for each sequence;
3. optimize continuous charging quantities within each regime;
4. preserve strict:
   \[
   q>0
   \]
   semantics;
5. distinguish attained optimum from unattained infimum;
6. optimize the accepted plan key lexicographically.

REF must **not** call the frontier propagation implementation.

---

## 2.2 FLAT-F — exact frontier solver

FLAT-F implements the T7 frontier representation without Region pruning.

It must propagate exact frontiers over all concrete next actions in the bounded candidate set.

Its purpose is to validate:

- frontier operators;
- merges;
- attainment flags;
- witness reconstruction;
- continuous charge optimization;
- state dominance.

REF and FLAT-F must be independently implemented enough that agreement is meaningful.

---

## 2.3 HIER-F — exact small-domain hierarchical solver

HIER-F wraps the exact frontier engine in the B2 hierarchical next-action search:

\[
N=(\mathfrak F,R,\alpha).
\]

It must use:

- effect-labelled action nodes;
- exact Region refinement coverage;
- admissible B2 continuation bounds;
- exact concrete frontier operators at leaves;
- the frozen conservative state-dominance rule.

HIER-F must return exactly the same diagnostic-domain answer as REF and FLAT-F.

This is a correctness test only.

No B2-1 claim is made that the hierarchy is already production-efficient.

---

# 3. Reference-domain stop cap

B2-1 is allowed to use a finite diagnostic cap:

\[
\boxed{H_{\rm ref}=4}
\]

for its exact reference domain.

This cap is **not** a production assumption.

It exists only so exhaustive sequence enumeration remains independently checkable.

The bounded-domain optimum is:

\[
J^*_{\le4}.
\]

All B2-1 solver comparisons are against this same declared domain unless a test is explicitly marked as a T7-5 incumbent-depth test.

No result from B2-1 may be described as proving unrestricted multi-stop scalability.

---

# 4. Objective and exact plan key

All solvers must use the same primary objective:

\[
J
=
T_{\rm clock}
+
\lambda_{\rm stop}H.
\]

Hard requirement failure is infeasible.

The accepted lexicographic result key is:

\[
\boxed{
K(p)
=
(
J,
Q_{\rm total},
H,
\pi_{\rm Site/action}
)
}
\]

where:

- \(J\): unrounded primary objective for mathematical comparison;
- \(Q_{\rm total}\): cumulative charged energy;
- \(H\): semantic stop count;
- \(\pi_{\rm Site/action}\): deterministic Site/action sequence.

Implementation may store a display-rounded objective, but exact comparison must use the frozen numerical contract and must not use display rounding as the mathematical optimizer.

---

# 5. Result statuses

Every diagnostic case must return exactly one of:

\[
\boxed{\texttt{attained\_optimum}}
\]

\[
\boxed{\texttt{infimum\_unattained}}
\]

\[
\boxed{\texttt{infeasible}}
\]

within the declared \(H_{\rm ref}\) domain.

For `attained_optimum`, return:

- primary objective;
- total charge;
- stop count;
- full Site/action sequence;
- charge amount at every C/CS stop;
- schedule start/completion times;
- terminal energy.

For `infimum_unattained`, return:

- exact infimal primary value;
- proof/certificate that no executable sequence attains it;
- no fabricated executable key.

For `infeasible`, no finite executable or limit-only feasible completion exists within the declared diagnostic domain.

---

# 6. Charging-model audit before solver work

Before implementing frontier comparisons:

1. inspect the frozen exact charging evaluator;
2. record its segment breakpoints and power values;
3. verify:
   \[
   P(E)>0
   \]
   on every accepted segment;
4. construct cumulative primitive:
   \[
   F(E);
   \]
5. independently test:
   \[
   C(a,b)=F(b)-F(a)
   \]
   across:
   - segment interiors;
   - exact breakpoints;
   - multi-segment intervals;
   - zero-length interval.

If the frozen evaluator is not exactly representable by the T7 finite-segment contract, hard stop and report the discrepancy.

Do not alter the charging model.

---

# 7. Numerical policy must be frozen before comparison

B2-1 must create a numerical-contract artifact before solver comparison.

It must specify:

- float representation;
- equality tolerance;
- breakpoint snapping policy;
- open/closed endpoint comparison;
- line-intersection handling;
- lexicographic comparison tolerance;
- conservative lower-bound rounding;
- witness feasibility recheck.

Required principle:

\[
\boxed{
\text{numerical tolerance may protect correctness, but may not change semantic feasibility.}
}
\]

For critical synthetic cases, compare against higher-precision or analytic values.

---

# 8. Stage A — mandatory hand-constructed theorem cases

Implement all 20 cases frozen by the T7 specification.

They are not optional.

1. one charging segment;
2. exactly one charging breakpoint;
3. multiple charging breakpoints;
4. frontier with increasing and decreasing pieces;
5. disconnected feasible energy domain;
6. merge intersection inside an interval;
7. schedule clipping at deadline \(b\);
8. schedule branch switch at \(a\);
9. CS charge-dominant;
10. CS schedule-dominant;
11. CS active-branch switch;
12. exact zero-charge limit;
13. unattained positive-charge infimum;
14. attained positive-charge interior optimum;
15. primary-time tie with different cumulative charge;
16. primary-time/charge tie with different Site tuple;
17. energy-floor clipping;
18. battery-capacity clipping;
19. two-charge redistribution across two chargers;
20. repeated-Site cycle / stop-depth case.

Each case must provide a hand-derived or independently enumerated expected outcome.

No case may be deleted because it is inconvenient to implement.

---

# 9. Additional semantic cases

Add at least these multi-stop cases:

- zero-stop terminal plan;
- C;
- S;
- CS;
- C→C;
- C→S;
- S→C;
- C→CS;
- CS→C;
- C→C→C;
- schedule feasible only after one charge;
- schedule feasible only before a later charge;
- reserve-tight destination;
- no feasible plan within \(H_{\rm ref}\);
- a feasible effect-free via-Site that must **not** enter the action set;
- charger-support Site where C, S, and CS are all distinct valid decisions.

These may overlap with the 20 theorem cases, but coverage must be explicit in a case matrix.

---

# 10. Stage B — deterministic generated synthetic suite

After the hand cases pass, run a deterministic generated suite.

No randomness is required.

Use a fixed Cartesian design over:

- topology templates:
  - line;
  - fork;
  - diamond;
  - directed asymmetric loop;
- initial SOC:
  - low;
  - medium;
- schedule:
  - absent;
  - present;
- charger/support arrangement:
  - chargers only;
  - mixed charger/support;
- energy tightness:
  - slack;
  - tight.

This gives:

\[
4\times2\times2\times2\times2
=
\boxed{64\text{ generated cases}}.
\]

Every generated case uses:

- finite candidate set of at most 6 Sites;
- \(H_{\rm ref}=4\);
- the frozen canonical charging curve;
- deterministic Site IDs and tie ordering.

If a generated case is infeasible or has an unattained infimum, retain it.

Do not replace it with a "more interesting" case.

---

# 11. Stage C — bounded real-data integration suite

Real-data cases are integration tests, not performance benchmarks.

Use the existing accepted development geography only.

Freeze the selected OD population **before solver comparison**:

\[
\boxed{\text{the first 8 ODs in the repository's canonical deterministic OD order}}
\]

with two initial SOC states:

\[
0.30,\qquad0.76.
\]

For each OD use:

- `energy_only`;
- `energy_and_scheduled`.

Total integration states:

\[
8\times2\times2
=
\boxed{32}.
\]

---

# 12. Real-data candidate restriction

The real-data reference must remain small.

For each of the 32 integration states:

1. start from the frozen static Site/action eligibility rules;
2. construct the static candidate pool without consulting objective outcomes;
3. order candidates deterministically by:
   1. increasing accepted baseline-route progress proxy if already available;
   2. then stable Site ID;
4. select at most:
   \[
   \boxed{8\text{ concrete Sites}}
   \]
   while preserving every static effect class represented in the pool where possible.

If no accepted deterministic route-progress field exists in the frozen repository, use stable Site ID only and record that fallback before comparisons.

Do not select candidates because REF says they are useful.

The bounded real domain remains:

\[
H_{\rm ref}=4.
\]

This suite checks repository integration only.

It must not be used for scalability claims.

---

# 13. Reference solver independence

REF must not reuse:

- frontier min-plus code;
- frontier merge code;
- HIER Region-bound code;
- FLAT-F breakpoint propagation code.

Allowed shared primitives are limited to immutable physical semantics such as:

- accepted route leg time/length;
- charging-curve constants;
- fixed schedule parameters.

REF must implement continuous optimization through explicit finite regime enumeration.

Within one fixed effect-labelled Site sequence:

1. enumerate charge-segment membership;
2. enumerate schedule `max` branches;
3. enumerate CS makespan active branches;
4. derive the resulting linear constraints/objective;
5. solve or analytically enumerate the finite linear extreme-point candidates;
6. recheck the winning continuous solution in the original nonlinear/piecewise semantics.

No new external dependency may be installed silently.

If a required exact/reference optimization capability is unavailable, hard stop and report the smallest needed dependency or analytic implementation.

---

# 14. Frontier representation contract

FLAT-F and HIER-F must represent each frontier with explicit pieces containing at minimum:

- energy interval;
- open/closed left endpoint;
- open/closed right endpoint;
- affine primary-time coefficients;
- attainment status;
- affine or constant cumulative-charge tie value where applicable;
- predecessor piece ID;
- predecessor energy rule;
- action effect label;
- Site ID;
- schedule branch;
- deterministic witness metadata.

No sampled SOC table is permitted internally as the authoritative state.

Sampling may be used only as a secondary visualization/audit.

---

# 15. Operator-level validation

Before complete multi-stop search, validate each operator independently.

For every hand case and enough generated pieces, compare REF-derived exact transformations against frontier transformations for:

- Drive;
- S;
- C;
- CS;
- merge;
- floor/capacity clipping.

Audit:

1. value function;
2. breakpoint locations;
3. interval openness;
4. attainment status;
5. secondary charged-energy value;
6. reconstructable witness.

---

# 16. Dominance validation

Run FLAT-F in two modes:

### D-off

No same-anchor state dominance except exact duplicate representation merging.

### D-on

Use the frozen conservative rule:

\[
t_A\le t_B,\qquad
E_A\ge E_B,\qquad
g_A<g_B.
\]

Require identical final case result between D-off and D-on.

For every dominance deletion, save a witness containing:

- dominating state/frontier point;
- dominated state/frontier point;
- strict primary-cost relation;
- energy/time relation.

On hand cases, explicitly validate the continuation-emulation theorem.

No equal-\(g\) dominance may be introduced in B2-1.

---

# 17. T7-5 stop-depth validation

B2-1's normal comparison uses \(H_{\rm ref}=4\).

Separately validate the incumbent-derived exact bound.

For selected hand/generated cases with verified finite incumbent \(U\), compute:

\[
\eta=h_{\min}+\lambda_{\rm stop},
\]

\[
H_{\max}
=
\left\lfloor\frac{U}{\eta}\right\rfloor.
\]

Construct the reference test domain with a cap strictly larger than the derived bound when computationally possible.

Verify that no plan beyond \(H_{\max}\) can improve or primary-tie the incumbent.

This test validates the production-depth theorem without replacing the normal \(H_{\rm ref}=4\) reference contract.

---

# 18. Hierarchical action coverage

For HIER-F, every concrete semantic next action in the bounded domain must belong to exactly one effect-labelled branch:

\[
C,\quad S,\quad CS.
\]

For each concrete frontier state/action, audit:

- root action-node coverage;
- Region ancestry;
- leaf membership;
- materialization exactly once.

Required:

\[
\boxed{
\text{lost actions}=0
}
\]

\[
\boxed{
\text{duplicate actions}=0.
}
\]

Overlapping static Site capability sets are permitted; duplicated concrete actions are not.

---

# 19. Region refinement coverage

For every refined node:

\[
N=(\mathfrak F,R,\alpha),
\]

verify that child Regions partition the parent concrete Site/action set under fixed \(\alpha\).

Audit:

\[
\mathcal A_\alpha(R)
=
\dot\bigcup_j
\mathcal A_\alpha(R_j).
\]

No Region centroid or abstract Site becomes executable.

---

# 20. Continuation-bound admissibility

For every HIER-F Region/action node in the small domain, compare its lower bound against the exact REF continuation minimum over the node's represented concrete actions.

Require:

\[
\boxed{
L(N)\le J^*_{\rm REF}(N)
}
\]

for every nonempty exact node.

If the represented exact set is empty, record it separately; do not fabricate a target.

This audit validates the B2-T4 lower-bound contract.

---

# 21. Attained/unattained exactness

For all three solvers, compare not only objective values but status.

Required exact agreement:

\[
\boxed{
status_{\rm REF}
=
status_{\rm FLAT-F}
=
status_{\rm HIER-F}.
}
\]

For `attained_optimum`, compare complete result key and continuous witness.

For `infimum_unattained`, compare infimal value and absence of executable witness.

An attained solution with the same value is **not** equivalent to an unattained infimum unless REF proves the value is actually attained.

---

# 22. Exactness gates

B2-1 hard gates are:

## B21-G1 — charging primitive

Frozen evaluator equals cumulative-primitive representation on the audit suite.

Required violations: `0`

## B21-G2 — operator exactness

Drive/S/C/CS/merge/clipping agree with independent exact cases.

Required violations: `0`

## B21-G3 — attainment semantics

Attained vs limit-only classification agrees with REF.

Required violations: `0`

## B21-G4 — lexicographic witness

Primary objective, charge tie, stop count, and Site/action tuple agree.

Required mismatches: `0`

## B21-G5 — full FLAT-F exactness

Across every Stage A/B/C case:

\[
K_{\rm FLAT-F}=K_{\rm REF}
\]

or exact matching non-attained/infeasible status.

Required mismatches: `0`

## B21-G6 — dominance safety

D-on and D-off produce identical exact case results.

Required mismatches: `0`

## B21-G7 — hierarchical coverage

Lost or duplicate concrete semantic actions:

`0`

## B21-G8 — Region-bound admissibility

Violations:

`0`

## B21-G9 — HIER-F exactness

HIER-F exactly matches REF on every case.

Required mismatches: `0`

## B21-G10 — no discretization / no semantic patch

No authoritative SOC grid, \(q_{\min}\), neutral action, or hidden finite charging-action enumeration.

Required violations: `0`

## B21-G11 — frozen predecessor preservation

B1-D2 and earlier accepted artifacts unchanged.

Required unauthorized changes: `0`

All G1–G11 must pass.

---

# 23. Hard-stop rule

Stop immediately before performance interpretation if any G1–G11 gate fails.

Do not:

- tune frontier breakpoints to make a failed case pass;
- add an SOC grid;
- relax \(q>0\);
- drop pathological cases;
- change tie semantics;
- change candidate selection;
- alter the Region hierarchy.

A correctness failure triggers diagnosis, not benchmark expansion.

---

# 24. Frontier-complexity accounting

B2-1 must measure representation growth but attach no success threshold.

Per operation/state record:

- input piece count;
- output piece count;
- number of new breakpoints;
- number of open endpoints;
- number of limit-only pieces/points;
- merge candidates;
- merge survivors;
- witness-switch breakpoints.

Per complete case report:

- peak frontier pieces at one discrete state;
- total frontier pieces created;
- total pieces retained after merge/dominance;
- maximum \(k\) reached;
- number of concrete effect-labelled actions;
- number of Region nodes for HIER-F.

These are descriptive only.

---

# 25. Runtime accounting

Runtime is secondary.

Measure separately:

- REF sequence enumeration;
- REF continuous regime optimization;
- FLAT-F frontier propagation;
- frontier merge/dominance;
- HIER-F Region-bound/refinement;
- exact leaf/frontier materialization;
- total case time.

Do not compare B2-1 runtime to B1-D2 production runtime as if they solve the same domain.

Do not make a scalability claim from B2-1.

---

# 26. No performance gate

B2-1 has **no pruning or speedup threshold**.

A case where HIER-F performs more work than FLAT-F is not a B2-1 failure if exactness gates pass.

B2-1 answers:

\[
\boxed{
\text{Can the exact multi-stop semantics be implemented correctly?}
}
\]

Performance belongs to the later deployable B2 stage.

---

# 27. Required tests

The project test suite must add dedicated tests for at least:

- charging primitive identity;
- all 20 theorem cases;
- open/closed interval handling;
- strict \(q>0\);
- unattained infimum;
- tie metadata propagation;
- frontier merge;
- dominance on/off equivalence;
- Region action coverage;
- Region-bound admissibility;
- exact reference independence guard;
- no SOC-grid guard;
- witness reconstruction;
- H-ref cap isolation;
- incumbent-derived H-max theorem;
- preservation of frozen one-stop artifacts.

Run the full existing test suite before and after B2-1 implementation.

---

# 28. Required artifacts

Write all new evidence under:

`results/milestone_4r_b2_b21/`

or the repository's equivalent Milestone-5 namespace if formally renamed before implementation.

At minimum produce:

## Protocol/preservation
- protocol snapshot/hash;
- `preservation_before.json`;
- `preservation_after.json`;
- full test logs/XML.

## Charging audit
- charging segments;
- cumulative primitive audit;
- numerical contract.

## Cases
- `hand_cases.json/csv`;
- `generated_cases.json/csv`;
- `real_micro_cases.json/csv`;
- case-construction manifest.

## Reference
- REF sequence enumeration summary;
- REF regime enumeration;
- REF exact results;
- reference-independence manifest.

## Frontier
- frontier piece traces for all hand cases;
- per-case FLAT-F result;
- operator audits;
- attainment audits;
- tie/witness audits.

## Dominance
- dominance on/off comparison;
- dominance deletion witnesses.

## Hierarchy
- action-coverage audit;
- Region-refinement audit;
- bound-admissibility audit;
- per-case HIER-F result.

## Complexity/timing
- frontier complexity table;
- piece-count strata;
- runtime table.

## Final
- `docs/MILESTONE_4R_B2_B21_REPORT.md`;
- `results/milestone_4r_b2_b21/acceptance.json`.

Do not overwrite B1-D2 artifacts.

---

# 29. Final report structure

The B2-1 report must contain:

## A. Scope

State clearly that this is small-domain exact validation, not a scalability benchmark.

## B. Frozen theory and preservation

T1–T7 authority, hashes, pre-tests.

## C. Independent reference

Explain REF and its independence.

## D. Charging/frontier implementation

Representation, open endpoints, attainment, witnesses.

## E. Case suites

Stage A/B/C counts and deterministic construction.

## F. G1–G11

Report every correctness gate independently.

## G. Attainment/pathology results

Especially zero-charge-limit and unattained-infimum cases.

## H. Dominance

On/off exactness and deletion counts.

## I. Hierarchy coverage and bounds

Exact action coverage and Region-bound admissibility.

## J. Frontier complexity

Piece growth, merges, peak sizes.

## K. Runtime

Descriptive only.

## L. Limitations

Small domain, \(H_{\rm ref}=4\), bounded candidate sets, no long-haul claim, no holdout.

## M. Decision

If G1–G11 all pass:

\[
\boxed{
\text{B2-1 correctness validated; authorize the next deployable multi-stop design stage.}
}
\]

If any gate fails:

\[
\boxed{
\text{B2-1 blocked; do not proceed to long-haul/deployable scaling.}
}
\]

---

# 30. Acceptance JSON

The acceptance artifact must include:

- milestone/version;
- protocol hash;
- frozen predecessor hashes;
- test counts;
- Stage A/B/C case counts;
- G1–G11 status/violation counts;
- REF/FLAT-F/HIER-F mismatch counts;
- attained/unattained/infeasible case counts;
- dominance on/off mismatch count;
- lost/duplicate action counts;
- bound-admissibility violation count;
- no-discretization status;
- peak frontier piece count;
- total frontier pieces;
- maximum diagnostic stop depth;
- final authorization decision.

No performance GO/NO-GO field is permitted.

---

# 31. Completion rule

B2-1 completes only after:

1. the numerical contract is frozen;
2. REF is independently implemented;
3. all Stage A hand cases pass;
4. all Stage B generated cases pass;
5. all Stage C bounded real integration cases pass;
6. G1–G11 are evaluated;
7. full tests pass;
8. preservation is reverified;
9. report and acceptance artifacts are written.

Then stop.

Do **not** automatically start long-haul B2-2 in the same run.

The next artifact after a successful B2-1 is a separately frozen deployable multi-stop design/protocol.
