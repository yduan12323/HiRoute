# Milestone 5 — B21 Exact Multi-Stop Validation Protocol v1.0

**Project:** dy-HiRoute  
**Stage:** Milestone 5 — deterministic exact multi-stop hierarchical planning  
**Substage:** B21-v1 — exact small-domain validation after core-theory reset  
**Status:** preregistered correctness protocol; no implementation authorized outside this protocol  
**Normative authority:** `MILESTONE_5_MULTISTOP_CORE_THEORY_V1.md` + `MILESTONE_5_MULTISTOP_CORE_THEORY_AUDIT_V1.md`  
**Historical predecessor:** failed B21-v0 attempt and its preserved correctness counterexample evidence

---

# 0. Purpose

B21-v1 validates whether Multi-Stop Core Theory v1 can be implemented exactly.

It does **not** validate scalability.

It does **not** reopen the old B21-v0 theory.

It does **not** continue from the previously failed Stage-A case.

B21-v1 restarts the exact small-domain validation from zero under the new authority.

The principal correctness object is now:

\[
\boxed{
\mathcal F^A_{v,r,k}
=
\text{finite attained Pareto PWA branches over }(t,\rho,\pi)
}
\]

with optional separate:

\[
\boxed{
\mathcal F^L_{v,r,k}
=
\text{limit-only lower-bound objects}.
}
\]

The old global earliest-time envelope is prohibited.

---

# 1. Authority and supersession

For B21-v1, read in this order:

1. `RESEARCH_SPEC_v0.2.md`
2. frozen one-stop / B1-D2 accepted artifacts
3. `MILESTONE_5_MULTISTOP_CORE_THEORY_V1.md`
4. `MILESTONE_5_MULTISTOP_CORE_THEORY_AUDIT_V1.md`
5. this protocol
6. future B21-v1 Codex prompt

Historical B2/B21 documents remain archived for provenance but are not normative:

- old B2 Formal Spec
- old B2 Theory Audit
- old T7 Charging Frontier Spec
- old T7 Theorem Audit
- draft B21 Theory Revision R1
- old B21 experimental protocol
- old B21 Codex prompt

The failed B21-v0 report, acceptance record, failed tests, REF certificates, operator traces, and dominance witness must remain unchanged.

---

# 2. No silent compatibility rule

If any implementation requirement conflicts with Core Theory v1 or its audit:

\[
\boxed{\text{hard stop}}
\]

Do not silently preserve old code behavior for compatibility.

In particular, the following are forbidden:

- global earliest-time-only merge;
- old strict-\(g\) dominance;
- cross-energy dominance;
- primary-only equality pruning;
- limit-only deletion of attained branches;
- SOC discretization;
- arbitrary \(q_{\min}\);
- neutral/effect-free stop actions.

---

# 3. Diagnostic domain

B21-v1 remains a small-domain exact validation.

The independent reference domain uses:

\[
\boxed{H_{\rm ref}=4}
\]

for normal REF/FLAT-F/HIER-F comparisons.

This is diagnostic only.

It is not the production stop bound.

The production finite-depth theorem remains separately validated from a verified incumbent.

---

# 4. Three solver objects

B21-v1 compares three implementations.

## REF-v1

Independent exact reference.

It must enumerate:

- discrete effect-labelled Site/action sequences;
- charging-curve regimes;
- schedule branches;
- CS max branches;

and solve the exact continuous subproblems.

REF-v1 must not call frontier reduction or hierarchy code.

## FLAT-P

Exact nonhierarchical Pareto-frontier solver.

It implements:

\[
\mathcal F^A,\mathcal F^L
\]

with no Region pruning.

Its purpose is to validate:

- branch representation;
- PWA transforms;
- continuation-safe reduction;
- lexicographic exactness.

## HIER-P

Exact hierarchical solver.

It uses:

\[
N=(\mathcal F^A,R,\alpha)
\]

with:

\[
\alpha\in\{C,S,CS\}.
\]

Hierarchy abstracts next-action sets only.

Current value frontier remains exact.

---

# 5. Exact final result key

All attained executable plans are compared by:

\[
\boxed{
K(p)=
(J,Q,H,\Pi)
}
\]

lexicographically.

Where:

\[
J=T_{\rm clock}+\lambda_{\rm stop}H.
\]

No implementation may use primary objective equality as acceptance-equivalent if \(Q,H,\Pi\) differ.

---

# 6. Exact result statuses

Each case returns exactly one of:

\[
\boxed{\texttt{attained\_optimum}}
\]

\[
\boxed{\texttt{infimum\_unattained}}
\]

\[
\boxed{\texttt{infeasible}}.
\]

For `attained_optimum`, return:

- \(J\);
- \(Q\);
- \(H\);
- complete Site/action tuple;
- charging amounts;
- schedule timing;
- terminal energy.

For `infimum_unattained`, return:

- exact infimal primary value;
- secondary/tie lower-bound information if defined;
- explicit non-attainment certificate;
- no fabricated executable key.

---

# 7. Exact branch representation

Every attained branch must contain:

\[
b=
(I,t(E),\rho,\pi,A,w)
\]

with:

- finite energy interval \(I\);
- exact open/closed endpoints;
- finite PWA time \(t(E)\);
- constant \(\rho\);
- discrete prefix tuple \(\pi\);
- attainment state;
- predecessor/witness reconstruction rule.

At fixed energy:

\[
Q(E)=E+\rho.
\]

A branch is tied to one discrete prefix family.

Do not merge different \(\rho\)-branches merely because one is earlier.

---

# 8. Attained and limit-only layers

Maintain two logical layers.

## Executable layer

\[
\mathcal F^A
\]

contains attained Pareto branches.

Only this layer may:

- update incumbents;
- supply executable returned plans;
- dominate/delete other attained branches.

## Lower-bound layer

\[
\mathcal F^L
\]

contains limit-only objects.

This layer may:

- support lower bounds;
- certify unattained infima.

It may not delete an attained executable branch.

If an output value is attained through any valid attained predecessor, that executable attainment must be retained even if an equal limit-only value exists.

---

# 9. Safe reduction rule

Compare attained labels only at identical:

\[
(v,E,r,k).
\]

A safely dominates B only if:

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

At least one strict improvement is required unless exact duplicate.

No cross-energy dominance is allowed in B21-v1.

---

# 10. Algebraic validation comes before case validation

Before any normal Stage-A theorem case, B21-v1 must pass the architecture algebra suite.

No Stage A/B/C progression is permitted until ALG-1 through ALG-10 all pass.

---

# 11. ALG-1 — reduction idempotence

For every generated finite frontier object:

\[
\boxed{
R(R(X))\equiv R(X).
}
\]

Equivalence is semantic.

It does not require identical:

- branch IDs;
- segmentation;
- provenance ordering.

Required mismatch count:

\[
0.
\]

---

# 12. ALG-2 — Drive congruence

\[
\boxed{
R(D(R(X)))\equiv R(D(X)).
}
\]

Test across:

- one-piece branches;
- multiple PWA pieces;
- multiple \(\rho\)-branches;
- endpoint clipping.

Required violations:

\[
0.
\]

---

# 13. ALG-3 — S congruence

\[
\boxed{
R(S(R(X)))\equiv R(S(X)).
}
\]

Mandatory stress patterns:

- full waiting plateau;
- partial plateau;
- no plateau;
- deadline clipping;
- equal-time secondary tie.

Required violations:

\[
0.
\]

---

# 14. ALG-4 — C congruence

\[
\boxed{
R(C(R(X)))\equiv R(C(X)).
}
\]

Must preserve:

- strict \(q>0\);
- attained vs limit-only;
- exact \(\rho\);
- exact witness.

Required violations:

\[
0.
\]

---

# 15. ALG-5 — CS congruence

\[
\boxed{
R(CS(R(X)))\equiv R(CS(X)).
}
\]

Stress:

- charge-dominant completion;
- schedule-dominant completion;
- branch switching;
- strict-positive boundary;
- limit-only cases.

Required violations:

\[
0.
\]

---

# 16. ALG-6 — merge commutativity

\[
\boxed{
R(X\cup Y)\equiv R(Y\cup X).
}
\]

Required violations:

\[
0.
\]

---

# 17. ALG-7 — merge associativity

\[
\boxed{
R(R(X\cup Y)\cup Z)
\equiv
R(X\cup R(Y\cup Z)).
}
\]

Required violations:

\[
0.
\]

---

# 18. ALG-8 — reduction on/off complete-key equivalence

For exact finite domains, compare:

- reduction disabled;
- safe reduction enabled.

Require identical:

- result status;
- \(J\);
- \(Q\);
- \(H\);
- \(\Pi\).

Mismatch count:

\[
0.
\]

---

# 19. ALG-9 — limit-only safety

Construct cases where:

- limit-only branch has smaller/equal infimal primary value;
- attained branch is executable.

Verify:

\[
\boxed{
\mathcal F^L
\text{ never deletes executable winner from }
\mathcal F^A.
}
\]

Required violations:

\[
0.
\]

---

# 20. ALG-10 — primary-equality pruning safety

Construct Region/action nodes with:

\[
L_J=U_J
\]

and a contained plan satisfying:

\[
Q<U_Q.
\]

Verify that the node remains live without a lexicographic lower-bound certificate.

Required violations:

\[
0.
\]

---

# 21. Algebra-suite population

The algebra suite must include:

- hand-constructed exact objects;
- deterministic generated finite PWA branch sets.

At minimum generate:

- 50 Drive objects;
- 50 S objects;
- 50 C objects;
- 50 CS objects;
- 50 three-way merge objects.

All generation is deterministic from a frozen seed/configuration manifest.

This is not a statistical test.

Any single mismatch is a correctness failure.

---

# 22. Permanent blocking regression

The B21-v0 counterexample becomes the first mandatory semantic regression after ALG-1..10.

Required exact result:

\[
\boxed{
J=44950\ {\rm s}
}
\]

\[
\boxed{
Q=76\ {\rm kWh}
}
\]

\[
\boxed{
H=3
}
\]

\[
\boxed{
\Pi=
(Site\ 2,C)
\rightarrow
(Site\ 3,C)
\rightarrow
(Site\ 4,S)
}
\]

The 83-kWh alternative must not win.

Primary-objective-only agreement is a failure.

---

# 23. New adversarial regression set

Before the legacy Stage-A suite, add these 10 reset-specific cases:

1. full waiting plateau: earlier/high-\(\rho\) vs later/low-\(\rho\);
2. partial waiting-gap collapse;
3. no waiting plateau;
4. equal time / unequal \(\rho\);
5. equal time / equal \(\rho\) / different tuple;
6. old high-SOC cross-energy pair that must not be pruned;
7. same discrete prefix, different charge allocation, same final E;
8. limit-only better infimum vs attained worse plan;
9. multiple intersections between PWA branches with different \(\rho\);
10. Region lower bound equal to incumbent primary with better secondary key inside.

Every case must have an independently derived expected result.

---

# 24. Legacy Stage A suite

After algebra and reset regressions pass, run the 20 previously frozen theorem themes, updated only where the old expected behavior explicitly relied on invalid earliest-time compression or old dominance.

Any changed expectation must be documented with:

- old expectation;
- reason invalid under v1;
- new authority citation;
- new exact expected result.

Do not silently rewrite tests.

The original B21-v0 blocking fixture must remain unchanged.

---

# 25. Stage B — deterministic generated suite

Retain the original 64-case Cartesian design:

Topology:

- line;
- fork;
- diamond;
- directed asymmetric loop.

Initial SOC:

- low;
- medium.

Schedule:

- absent;
- present.

Capability arrangement:

- chargers only;
- mixed charger/support.

Energy tightness:

- slack;
- tight.

Total:

\[
4\times2\times2\times2\times2
=
64.
\]

At most 6 Sites per generated case.

Use:

\[
H_{\rm ref}=4.
\]

Do not replace infeasible or unattained cases.

---

# 26. Stage C — bounded real-data integration

Retain the original integration population:

- first 8 ODs in canonical deterministic repository order;
- SOC 0.30 and 0.76;
- `energy_only`;
- `energy_and_scheduled`.

Total:

\[
32.
\]

Use at most 8 concrete Sites per state under a deterministic static candidate-selection rule frozen before solving.

No REF-outcome-guided selection.

No scalability claim.

---

# 27. REF-v1 independence

REF-v1 may share only immutable physical primitives:

- accepted leg travel time;
- accepted selected-route actual length;
- charging curve constants;
- fixed schedule parameters.

REF-v1 must not import or call:

- Pareto reduction;
- branch merge;
- FLAT-P frontier transforms;
- HIER-P Region bounds.

REF-v1 solves exact continuous subproblems through independent finite regime enumeration.

---

# 28. Operator-level exactness

Before full solver comparisons, test branchwise operators against REF-derived or analytic exact expectations:

- Drive;
- S;
- C;
- CS;
- merge;
- clipping.

Audit:

- PWA value;
- breakpoints;
- open/closed endpoints;
- \(\rho\);
- attainment;
- witness reconstruction.

Required violations:

\[
0.
\]

---

# 29. Full solver comparisons

For every case in:

- reset regressions;
- legacy Stage A;
- Stage B;
- Stage C;

require exact agreement:

\[
\boxed{
REF-v1
=
FLAT-P
=
HIER-P
}
\]

on:

- status;
- \(J\);
- \(Q\);
- \(H\);
- \(\Pi\);
- charging quantities;
- schedule timing;
- terminal energy.

---

# 30. Dominance validation

Run FLAT-P in two modes.

## D-off

No safe dominance except exact duplicate representation normalization.

## D-on

Use only same-state Pareto-safe dominance.

Require identical exact result/status on every case.

For every deletion record:

- state index;
- energy;
- \(t\) relation;
- \(\rho\) relation;
- tuple relation;
- retained branch;
- deleted branch.

No cross-energy deletion may occur.

---

# 31. Hierarchy action coverage

For HIER-P, every concrete semantic next action must belong to exactly one effect-labelled branch.

Required:

\[
\text{lost actions}=0
\]

\[
\text{duplicate actions}=0.
\]

Same Site may appear under different effect labels because those are distinct actions.

---

# 32. Region refinement coverage

For fixed:

\[
(\mathcal F,R,\alpha),
\]

children must partition the represented action set:

\[
\mathcal A_\alpha(\mathcal F,R)
=
\dot\bigcup_j
\mathcal A_\alpha(\mathcal F,R_j).
\]

Required violations:

\[
0.
\]

---

# 33. Region bound admissibility

For every nonempty HIER-P Region/action node:

\[
L_J(N)
\le
J^*_{\rm REF}(N).
\]

Required violations:

\[
0.
\]

Nodes with empty exact represented sets are reported separately.

---

# 34. Primary-equality handling in HIER-P

HIER-P may prune from primary bound only if:

\[
\boxed{
L_J>U_J.
}
\]

If:

\[
L_J=U_J,
\]

the node remains live unless an independently proved lexicographic lower-bound certificate exists.

B21-v1 introduces no such certificate.

Therefore all equality nodes remain live.

---

# 35. Incumbent-derived finite-depth validation

Normal diagnostic comparisons use:

\[
H_{\rm ref}=4.
\]

Separately validate the production theorem.

For verified incumbent \(U_J\):

\[
\eta=h_{\min}+\lambda_{\rm stop},
\]

\[
H_{\max}
=
\left\lfloor U_J/\eta\right\rfloor.
\]

Where computationally feasible, compare against a larger reference cap and verify no plan beyond \(H_{\max}\) can primary-tie or improve.

Required violations:

\[
0.
\]

---

# 36. Hard gates

B21-v1 hard gates are:

## V1-G0 — algebraic architecture

ALG-1 through ALG-10 all pass.

## V1-G1 — charging primitive

Frozen charging evaluator matches exact primitive.

## V1-G2 — branch/operator exactness

Drive/S/C/CS/merge/clipping exact.

## V1-G3 — attained/limit-only semantics

Status and layer handling exact.

## V1-G4 — full lexicographic key

Exact \((J,Q,H,\Pi)\).

## V1-G5 — FLAT-P exactness

Matches REF-v1 on every case.

## V1-G6 — safe dominance

D-on equals D-off on every case.

## V1-G7 — action coverage

Lost/duplicate actions = 0.

## V1-G8 — Region bound admissibility

Violations = 0.

## V1-G9 — HIER-P exactness

Matches REF-v1 on every case.

## V1-G10 — full-key-safe pruning

No equality-prune violation.

## V1-G11 — no semantic approximation

No SOC grid, arbitrary \(q_{\min}\), neutral action, hidden charging discretization, or prohibited dominance.

## V1-G12 — predecessor preservation

Frozen B1-D2 and historical B21-v0 evidence unchanged.

All gates must pass.

---

# 37. Hard-stop rule

If any hard gate fails:

\[
\boxed{\text{stop B21-v1 immediately}}
\]

before Stage expansion or performance interpretation.

Do not repair by:

- weakening full-key checks;
- restoring old earliest-time merge;
- adding heuristic branch caps;
- discretizing energy;
- relaxing \(q>0\);
- dropping adversarial cases;
- changing Site selection;
- adding unproved dominance.

The failure must be classified as:

- theory contradiction;
- implementation defect;
- numerical defect;
- authority/provenance defect.

Only theory contradictions may reopen Core Theory v1.

---

# 38. Frontier-complexity accounting

B21-v1 records complexity descriptively.

Per discrete state:

- number of attained branches;
- number of limit-only objects;
- total PWA pieces;
- Pareto reductions attempted;
- Pareto deletions;
- time intersections;
- branch splits.

Per case:

- peak attained branches at one state;
- peak total pieces;
- total pieces created;
- total retained;
- maximum k;
- number of concrete actions;
- HIER-P Region nodes.

No performance threshold.

---

# 39. Runtime accounting

Measure separately:

- REF-v1 enumeration;
- REF-v1 regime optimization;
- FLAT-P branch propagation;
- Pareto reduction;
- HIER-P Region bound/refinement;
- exact leaf materialization;
- total case runtime.

Runtime is descriptive only.

No scalability claim.

---

# 40. Preservation protocol

Before implementation:

- run full existing tests;
- verify accepted predecessor manifests;
- verify B1-D2 hashes;
- verify old B21-v0 report/acceptance/evidence hashes;
- archive Git commit/status;
- archive authority hashes.

After B21-v1:

- rerun full tests;
- rerun preservation audit;
- verify historical B21-v0 evidence unchanged.

Any unexpected protected-file change is a hard stop.

---

# 41. Required output namespace

Use a new namespace.

Recommended:

`results/milestone_5_b21_v1/`

and:

`docs/MILESTONE_5_B21_V1_REPORT.md`

Do not reuse:

`results/milestone_4r_b2_b21/`

for new evidence.

Historical failed evidence remains in its original namespace.

---

# 42. Required artifacts

At minimum produce:

## Authority/preservation

- authority manifest;
- pre/post preservation JSON;
- test logs/XML;
- Core Theory v1 hash;
- Core Theory Audit v1 hash;
- protocol hash.

## Algebra

- ALG-1..ALG-10 case manifest;
- per-law audit tables;
- semantic-equivalence comparator audit.

## Regressions

- permanent 76-kWh blocking regression;
- 10 reset adversarial cases;
- expected-result certificates.

## REF-v1

- sequence enumeration summaries;
- regime enumeration evidence;
- exact outputs;
- independence manifest.

## FLAT-P

- branch traces;
- PWA operator audits;
- attained/limit-only traces;
- reduction traces;
- D-on/D-off comparisons.

## HIER-P

- action coverage;
- Region refinement;
- bound admissibility;
- equality-node audit;
- exact outputs.

## Complexity/runtime

- frontier complexity table;
- runtime table.

## Final

- `docs/MILESTONE_5_B21_V1_REPORT.md`
- `results/milestone_5_b21_v1/acceptance.json`

---

# 43. Final report structure

The final report must include:

A. scope and authority  
B. preservation baseline  
C. algebraic architecture laws  
D. permanent B21-v0 regression  
E. new adversarial regressions  
F. independent REF-v1  
G. FLAT-P implementation  
H. Stage A/B/C populations  
I. V1-G0 through V1-G12  
J. dominance on/off  
K. hierarchy coverage/refinement/bounds  
L. attained vs limit-only behavior  
M. frontier complexity  
N. runtime  
O. limitations  
P. decision

---

# 44. Acceptance rule

B21-v1 is accepted only if:

\[
\boxed{
V1\text{-}G0\ldots V1\text{-}G12
\text{ all pass with zero correctness violations}
}
\]

and all solver populations are complete.

There is no performance GO/NO-GO threshold.

---

# 45. Completion decision

If all hard gates pass:

\[
\boxed{
\textbf{B21-v1 exact multi-stop correctness validated.}
}
\]

Then and only then authorize a separately designed deployable/scalability stage.

If any hard gate fails:

\[
\boxed{
\textbf{B21-v1 blocked.}
}
\]

Do not begin long-haul work.

---

# 46. Stage completion rule

After writing the B21-v1 report and acceptance artifact:

\[
\boxed{\text{stop}}
\]

Do not automatically start long-haul or holdout work in the same run.

The next milestone after successful B21-v1 is a separately frozen deployable multi-stop design stage.

---

# 47. Immediate next artifact

After this protocol is accepted, create:

\[
\boxed{
\texttt{MILESTONE\_5\_B21\_V1\_CODEX\_PROMPT.md}
}
\]

The Codex prompt must implement this protocol literally.

It must not reference the old B21 protocol as active authority.
