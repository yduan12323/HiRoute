# Milestone 5 — Multi-Stop Core Theory Audit v1.0

**Project:** dy-HiRoute  
**Audited authority:** `MILESTONE_5_MULTISTOP_CORE_THEORY_V1.md`  
**Trigger:** B21 correctness counterexample to earliest-time-only compression and strict-cost dominance  
**Audit mode:** adversarial theorem audit before any B21 protocol rewrite or implementation  
**Decision target:** whether the reset theory is coherent enough to become the sole multi-stop implementation authority

---

# 0. Executive verdict

The reset architecture was attacked at the level of:

- final lexicographic objective;
- state sufficiency;
- conservation-law label coordinates;
- continuation dominance;
- branch compression;
- transition congruence;
- strict-positive charging;
- attainment;
- finite representation;
- finite depth;
- branch-and-bound pruning;
- hierarchy/action coverage.

The audit result is:

| Core contract | Verdict | Notes |
|---|---|---|
| M5-C1 physical state sufficiency | **PASS** | under the frozen deterministic one-schedule domain |
| M5-C2 \(\rho\) conservation law | **PASS** | exact under the frozen drive-only energy-consumption model |
| M5-C3 Pareto dominance \(\Rightarrow\) continuation dominance | **PASS** | same \((v,E,r,k)\) only |
| M5-C4 finite/idempotent canonical reduction | **PASS** | finite PWA branches; semantic rather than syntactic equality |
| M5-C5 Drive/S/C/CS transition congruence | **PASS** | for attained exact branches under the frozen monotone-time operators |
| M5-C6 branchwise C/CS PWA closure + attainment | **PASS** | finite positive piecewise-affine charging primitive verified by predecessor evidence |
| M5-C7 finite-depth theorem | **PASS** | feasible-query domain with verified finite incumbent and positive per-stop cost |
| M5-C8 full-key-safe B&B | **PASS** | primary-only pruning must be strict at equality |
| M5-C9 hierarchy coverage/refinement | **PASS** | hierarchy abstracts action sets only |
| M5-C10 independent REF contract | **PASS** | reference remains structurally independent |

No counterexample was found that invalidates the reset architecture under its declared domain.

Two **normative clarifications** are required before implementation, but neither changes the architecture:

1. transition-congruence equality is **semantic equivalence**, not literal equality of branch segmentation/provenance IDs;
2. attained executable Pareto branches and limit-only lower-bound objects must be maintained as two logically distinct layers.

With those clarifications, the audit accepts the reset theory for B21 protocol redesign.

\[
\boxed{\textbf{CORE THEORY v1 ACCEPTED FOR SMALL-DOMAIN VALIDATION}}
\]

This is **not** a claim that the eventual implementation is correct or scalable. It authorizes only a rewritten B21 correctness protocol.

---

# 1. Audit philosophy

The old theory failed because it tried to prove that a locally earlier/lower-cost prefix could be deleted before proving that deletion was safe under **every legal future continuation**.

The reset reverses the order.

This audit therefore does not ask:

> "Does the new frontier look reasonable?"

It asks:

\[
\boxed{
\textbf{Can any label deleted by the new reduction become lexicographically useful after some legal suffix?}
}
\]

If the answer were yes for any legal suffix, the reset would fail.

---

# 2. Frozen domain used by the audit

The audit assumes exactly the v1 research domain:

- deterministic selected-fastest-time leg routing;
- actual selected-route length for energy;
- constant drive energy rate \(\kappa\);
- no auxiliary/idling/HVAC energy;
- finite battery capacity;
- one generic hard scheduled requirement;
- waiting allowed;
- schedule start window \([a,b]\);
- charge/schedule overlap;
- canonical finite positive piecewise charging law;
- effect classes \(C,S,CS\);
- semantic C/CS requires \(q>0\);
- positive stop overhead;
- positive stop nuisance;
- no time-varying charger availability;
- no stochastic information state;
- no history-dependent rewards or bans.

The conclusions must be re-audited if any of those change.

---

# 3. M5-C1 — Physical state sufficiency

The physical state is:

\[
x=(v,t,E,r).
\]

The future depends on:

- \(v\): determines future concrete route legs;
- \(t\): determines schedule-window feasibility and waiting;
- \(E\): determines drive/charge feasibility;
- \(r\): determines whether S/CS remains required/available.

No frozen future constraint depends on:

- previously visited Site identity;
- previous number of visits to a Site;
- prior charging locations;
- prior route geometry;
- prior observations;
- user history.

Therefore two histories reaching identical:

\[
(v,t,E,r)
\]

have identical physical future action spaces.

The optimization key may still distinguish their historical metadata, which is why physical-state sufficiency does **not** justify merging those histories.

### Adversarial check

Could a previous Site identity affect the terminal tuple tie?

Yes, but that is optimization metadata \(\pi\), not physical feasibility.

Could previous cumulative drive affect future battery feasibility?

No; current \(E\) is sufficient physically.

Could previous cumulative charge affect future physical feasibility?

No; it matters only for secondary objective \(Q\).

### Verdict

\[
\boxed{\textbf{M5-C1 PASS}}
\]

---

# 4. M5-C2 — Conservation-law coordinate

The reset defines:

\[
\rho=Q-E.
\]

From:

\[
E=E_0+Q-C_{\rm drive}
\]

we obtain:

\[
\rho=C_{\rm drive}-E_0.
\]

Thus:

\[
Q=E+\rho.
\]

The transition laws are exact:

## Drive consuming \(c\)

\[
E'=E-c,\qquad Q'=Q,
\]

so:

\[
\rho'=\rho+c.
\]

## Charge by \(q\)

\[
E'=E+q,\qquad Q'=Q+q,
\]

so:

\[
\rho'=\rho.
\]

## Wait / S / CS activity

No energy is consumed under the frozen model outside driving and explicit charging, hence:

\[
\rho'=\rho.
\]

### Adversarial check

This identity would fail if the model later charged battery energy for:

- waiting;
- HVAC;
- stop overhead;
- charging losses modeled as battery-side energy loss;
- auxiliary loads.

Those are outside v1.

### Verdict

\[
\boxed{\textbf{M5-C2 PASS}}
\]

---

# 5. Critical lemma — one discrete prefix needs only earliest time

This lemma is central because it prevents the corrected representation from becoming a two-dimensional continuous surface.

Fix one discrete effect-labelled prefix:

\[
\pi=((s_1,\alpha_1),\ldots,(s_k,\alpha_k)).
\]

Its route legs are fixed by deterministic route semantics.

Therefore cumulative drive consumption is fixed:

\[
C_{\rm drive}(\pi)=\text{constant}.
\]

Hence:

\[
\rho_\pi=C_{\rm drive}(\pi)-E_0
\]

is constant.

At any fixed current energy \(E\):

\[
Q_\pi(E)=E+\rho_\pi.
\]

Take two attained realizations of the same \(\pi\) and same \(E\), with:

\[
t_A<t_B.
\]

They have identical:

- current anchor;
- energy;
- requirement state;
- stop count;
- \(\rho\);
- prefix tuple.

Thus A safely dominates B by the reset theorem.

Therefore only the earliest attained time is needed **within one fixed discrete prefix family** at each \(E\).

This is not the failed global earliest-time merge.

It is a within-family compression where all secondary/tertiary metadata is identical.

### Verdict

\[
\boxed{\textbf{LEMMA PASS}}
\]

---

# 6. M5-C3 — Same-state Pareto dominance

The operational rule compares only attained labels at identical:

\[
(v,E,r,k).
\]

A dominates B when:

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

## 6.1 Feasibility preservation

Because the two labels share:

- anchor;
- energy;
- requirement state;

A can execute every concrete suffix available to B.

Earlier time cannot destroy feasibility because all future temporal operators are monotone and waiting is allowed.

For the hard schedule window:

\[
y=\max(a,t+h).
\]

If B satisfies:

\[
y_B\le b,
\]

then:

\[
t_A\le t_B
\Rightarrow
y_A\le y_B\le b.
\]

So an earlier A cannot lose schedule feasibility.

## 6.2 Primary objective

For the same suffix, future stop count is equal.

Every future time operator is monotone nondecreasing in incoming time.

Thus:

\[
J_A^{final}\le J_B^{final}.
\]

Strict prefix time is **not** assumed to remain strict.

That is precisely the old theorem's error.

## 6.3 Secondary objective

The two labels begin the suffix with the same \(E\).

The same suffix applies the same future drives and charges.

Therefore the difference in final cumulative charge remains:

\[
Q_A^{final}-Q_B^{final}
=
Q_A-Q_B
=
\rho_A-\rho_B
\le0.
\]

## 6.4 Tertiary stop count

They share the same \(k\), and execute the same suffix.

Thus final \(H\) ties.

## 6.5 Tuple order

If primary and charge also tie, equal \(k\) ensures the two prefixes have the same tuple length.

Appending the same suffix preserves lexicographic prefix order.

Hence:

\[
\pi_A\le_{\rm lex}\pi_B
\Rightarrow
\pi_A\Vert\sigma
\le_{\rm lex}
\pi_B\Vert\sigma.
\]

### Adversarial cases

- **Waiting fully erases \(t_A<t_B\):** \(\rho\) still protects the secondary key.
- **Waiting partially erases the gap:** A remains no later.
- **No waiting:** earlier A remains strictly earlier.
- **Equal time, lower \(\rho\):** A wins Q.
- **Equal time/equal \(\rho\), better tuple:** A wins \(\Pi\).

### Verdict

\[
\boxed{\textbf{M5-C3 PASS}}
\]

---

# 7. Why cross-energy dominance is correctly excluded

Suppose:

\[
E_A>E_B.
\]

Even if A is earlier, future suffixes need not be comparable by replaying the exact same charge policy because:

- charge duration is SOC-dependent;
- the exact secondary key \(Q\) changes differently;
- future charge allocation may exploit the lower/higher starting energy differently.

A stronger theorem may exist.

v1 does not need it.

By refusing to use cross-energy dominance, the reset removes an entire class of unproved assumptions.

### Verdict

This conservatism is theoretically sound.

---

# 8. M5-C4 — Finite canonical reduction

At fixed:

\[
(v,r,k),
\]

there are finitely many branch families under finite depth.

Each branch has:

- a finite union of energy intervals;
- finite PWA \(t(E)\);
- constant \(\rho\);
- fixed discrete \(\pi\).

For two branch pieces A and B, the dominance relation can change only when:

\[
t_A(E)=t_B(E),
\]

because \(\rho\) and \(\pi\) are constant over the branch piece.

Two affine functions intersect:

- zero times;
- once;
- or coincide over the entire interval.

After refining by existing breakpoints and pairwise intersections, dominance is constant on each open cell.

Therefore pointwise Pareto reduction creates finitely many pieces.

## Idempotence

The safe dominance relation is transitive.

Once all dominated labels are removed:

\[
R(R(X))=R(X)
\]

semantically.

### Normative clarification 1

The equality above is **semantic equality**, not literal equality of:

- piece IDs;
- interval segmentation choices;
- provenance record ordering.

Define:

\[
X\equiv Y
\]

iff they represent exactly the same attained nondominated labels for every energy and the same executable tie winner set.

The implementation law is therefore:

\[
\boxed{
R(R(X))\equiv R(X).
}
\]

Canonical normalization may later make representations byte-deterministic, but correctness depends on semantic equivalence.

### Verdict

\[
\boxed{\textbf{M5-C4 PASS}}
\]

with the semantic-equivalence clarification.

---

# 9. Normative separation: executable frontier vs lower-bound envelope

The reset contains attained and limit-only objects.

The audit makes their roles explicit.

Define:

\[
\boxed{
\mathcal F^{A}
}
\]

as the attained executable Pareto frontier.

Define:

\[
\boxed{
\mathcal F^{L}
}
\]

as optional limit-only / infimal lower-bound objects.

Rules:

1. \(\mathcal F^{A}\) determines executable incumbents and full-key exactness.
2. A member of \(\mathcal F^{L}\) may support a lower bound.
3. \(\mathcal F^{L}\) may never delete an attained branch from \(\mathcal F^{A}\).
4. Transition operators may transform both layers, but attainment must be recomputed exactly.
5. If an output value is attainable through any transformed attained predecessor, it is attained regardless of an equal limit-only witness.

This avoids treating nonattained infima as if they were executable labels.

This clarification does not change the model; it makes the representation contract explicit.

---

# 10. M5-C5 — Transition congruence

The exact law should be read as:

\[
\boxed{
R(T(R(X)))\equiv R(T(X))
}
\]

for the attained executable frontier.

## 10.1 Drive

For the same drive:

\[
t'=t+T,
\qquad
\rho'=\rho+c.
\]

Both order coordinates receive identical additions.

Safe dominance is preserved.

PASS.

## 10.2 S

\[
t'=\max(a,t+h)+D.
\]

This is monotone nondecreasing.

\[
\rho'=\rho.
\]

Thus a safely dominated label cannot become nondominated after S.

The known B21 counterexample is handled because the later/lower-\(\rho\) label is **not** dominated before S and therefore survives.

PASS.

## 10.3 C

At identical input energy \(E_a\), safely ordered labels charged to the same \(E_d>E_a\) receive the same charging-time increment:

\[
F(E_d)-F(E_a),
\]

and keep their \(\rho\).

So safe dominance is preserved pointwise.

When the C operator optimizes over possible \(E_a\), removing a dominated label at a particular \(E_a\) is safe because a dominating attained replacement exists at that same \(E_a\).

PASS.

## 10.4 CS

For fixed \(E_a,E_d\), completion is:

\[
\max\{
t+h+F(E_d)-F(E_a),
\max(a,t+h)+D
\}.
\]

This is monotone in \(t\), and \(\rho\) remains unchanged.

The same pointwise replacement argument as C applies.

PASS.

### Adversarial check: strict \(q>0\)

The replacement label exists at the same \(E_a\), and the same chosen \(E_d>E_a\) therefore remains strictly positive charge.

No \(q=0\) relaxation is introduced by the congruence proof.

### Verdict

\[
\boxed{\textbf{M5-C5 PASS}}
\]

---

# 11. M5-C6 — Branchwise finite PWA closure

The predecessor B21 evidence independently verified the frozen charging primitive against the evaluator, including charging breakpoints and multisegment intervals.

The mathematical audit considers one branch:

\[
t(E)
\]

finite PWA.

## 11.1 C

\[
t_C(E_d)
=
h+F(E_d)
+
\inf_{E_a<E_d}
[t(E_a)-F(E_a)].
\]

Since:

\[
t-F
\]

is finite PWA, its strict prefix infimum has a finite PWA value representation.

Attainment changes only at finitely many:

- branch endpoints;
- PWA breakpoints;
- running-infimum switches.

Thus C remains finite PWA plus a finite attainment partition.

## 11.2 CS

Partition by:

- input branch piece;
- charging segment of \(E_a\);
- charging segment of \(E_d\);
- schedule `max` branch;
- final makespan active branch.

Within a fixed regime, the epigraph problem is linear in:

\[
(E_a,E_d,z).
\]

The one-parameter optimal value in \(E_d\) is finite piecewise affine across finitely many LP bases.

The strict inequality:

\[
E_a<E_d
\]

may make an optimum unattained, but does not create infinitely many value regimes.

Attainment is represented separately.

## 11.3 Secondary key inside one prefix family

At fixed \(E_d\):

\[
Q(E_d)=E_d+\rho.
\]

Therefore minimizing branchwise time over \(E_a\) cannot discard a distinct lower-Q realization of the **same discrete prefix** at that output energy.

There is no hidden secondary tradeoff inside the family.

This closes the exact failure mode that invalidated the old global earliest-time frontier.

### Verdict

\[
\boxed{\textbf{M5-C6 PASS}}
\]

---

# 12. M5-C7 — Finite depth

Let:

\[
\eta=h_{\min}+\lambda_{\rm stop}.
\]

The declared domain has:

\[
h_{\min}>0,
\qquad
\lambda_{\rm stop}>0.
\]

Every semantic stop contributes at least \(h_{\min}\) to elapsed clock and \(\lambda_{\rm stop}\) to objective.

Hence:

\[
J(p)\ge H\eta.
\]

Given a verified executable incumbent:

\[
U_J<\infty,
\]

any plan that can beat or primary-tie it must satisfy:

\[
H\eta\le U_J.
\]

Therefore:

\[
H\le
\left\lfloor
U_J/\eta
\right\rfloor.
\]

### Adversarial check

Could charge/schedule overlap erase the stop overhead?

No. Overlap occurs after the stop release; the fixed overhead is already part of elapsed clock.

Could zero-length/co-located repeated stops avoid the bound?

No. Each semantic stop still pays positive \(h+\lambda\).

Could a negative reward offset stop cost?

No such term exists in the v1 objective.

### Verdict

\[
\boxed{\textbf{M5-C7 PASS}}
\]

for the declared feasible-query domain with a verified incumbent.

---

# 13. M5-C8 — Full-key-safe branch-and-bound

The incumbent is:

\[
K_U=(U_J,U_Q,U_H,U_\Pi).
\]

Suppose a Region/action node has only a primary admissible lower bound:

\[
L_J.
\]

## Strict inequality

If:

\[
L_J>U_J,
\]

every represented complete plan has worse primary objective.

Safe prune.

## Equality

If:

\[
L_J=U_J,
\]

the node may contain:

\[
Q<U_Q
\]

or equal Q with better later tie components.

Therefore equality is not enough.

The safe primary-only rule is:

\[
\boxed{
L_J>U_J.
}
\]

A future lexicographic certificate could permit equality pruning, but v1 does not rely on one.

## Termination

With finite hierarchy, finite depth, finite exact branch representation, and exact leaf processing, equality nodes can be exhausted/materialized.

Termination is valid once no unprocessed represented plan can primary-tie or beat the incumbent.

### Adversarial regression

A node with:

\[
L_J=U_J
\]

and an internal plan with:

\[
Q<U_Q
\]

must remain live.

This is now a mandatory architecture test.

### Verdict

\[
\boxed{\textbf{M5-C8 PASS}}
\]

---

# 14. M5-C9 — Hierarchy coverage/refinement

The hierarchy is permitted to represent only next-action sets.

Current value state remains the exact frontier.

For:

\[
N=(\mathcal F,R,\alpha),
\]

the represented action set is the concrete set of Site/effect actions with Site in \(R\) and effect label \(\alpha\).

If:

\[
R=R_1\dot\cup R_2,
\]

the Site partition gives:

\[
\mathcal A_\alpha(\mathcal F,R)
=
\mathcal A_\alpha(\mathcal F,R_1)
\dot\cup
\mathcal A_\alpha(\mathcal F,R_2).
\]

Because \(\alpha\) is explicit:

- C;
- S;
- CS

are distinct actions even when they occur at the same concrete Site.

No Region representative is executable.

No Region-level averaged frontier replaces \(\mathcal F\).

### Adversarial check

Could the same Site/action be duplicated across two child Regions?

Not if the frozen road/Site hierarchy is a true partition.

This remains an implementation gate and must be audited.

Could the same Site appear under C and CS?

Yes, but those are distinct semantic actions, not duplicates.

### Verdict

\[
\boxed{\textbf{M5-C9 PASS}}
\]

as an exact representation contract.

---

# 15. M5-C10 — Independent reference contract

The reference solver does not rely on:

- Pareto branch reduction;
- frontier merge;
- Region bounds;
- hierarchical pruning.

It enumerates:

- discrete effect-labelled Site sequences;
- charging-curve regimes;
- schedule/max regimes;

and solves the resulting continuous subproblems.

Thus it attacks exactly the abstraction layer whose correctness B21 needs to establish.

The earlier blocker report already demonstrated the value of this independence: REF detected a full-key error that the frontier representation itself could not reveal.

### Verdict

\[
\boxed{\textbf{M5-C10 PASS}}
\]

---

# 16. Attempted counterexamples against the reset

The audit explicitly attacked the following patterns.

## CE-1 — full waiting plateau

Earlier/high-Q vs later/low-Q.

Result: incomparable under \((t,\rho)\), so both survive.

No failure.

## CE-2 — partial waiting-gap collapse

Earlier remains earlier or ties; lower-\(\rho\) information remains available.

No failure.

## CE-3 — no waiting plateau

Earlier/lower-or-equal-\(\rho\) safe dominance behaves conventionally.

No failure.

## CE-4 — earlier but higher energy

v1 refuses cross-energy dominance.

No unsafe deletion.

## CE-5 — earlier but higher \(\rho\)

v1 treats prefixes as incomparable.

No unsafe deletion.

## CE-6 — equal time and equal \(\rho\), different tuple

Lexicographic prefix tie decides only when same \(k\); extension by same suffix preserves order.

No failure.

## CE-7 — strict-positive charge boundary

The same-energy dominance replacement preserves:

\[
E_d>E_a.
\]

Limit-only objects are separated from executable reduction.

No failure.

## CE-8 — schedule upper deadline

Earlier label cannot be made infeasible if the later one is feasible, because waiting is optional and earliest feasible start is monotone.

No failure.

## CE-9 — CS overlap

Completion is a max of monotone time terms. Safe order is preserved.

No failure.

## CE-10 — equal-primary Region lower bound

v1 prohibits primary-only equality pruning.

No failure.

## CE-11 — repeated Site cycles

Correctness does not rely on a no-repeat theorem.

Finite incumbent-derived depth handles global finiteness.

No failure.

## CE-12 — different charge allocations on same prefix

At fixed output energy, cumulative Q is fixed by conservation.

Only earliest time is needed within that discrete prefix.

No failure.

No counterexample found inside the frozen domain.

---

# 17. What would invalidate v1

The following future changes require a new core-theory audit because they break proof assumptions:

- auxiliary battery drain during waiting/stops;
- Site-dependent charging laws not covered by the finite-PWA primitive contract;
- charger opening hours or time-dependent charging power;
- multiple heterogeneous scheduled requirements whose remaining state is not summarized by \(r\);
- history-dependent Site bans;
- negative stop rewards;
- battery degradation utility depending on charge history;
- stochastic availability/information;
- user-specific history-dependent utility.

These are product/future-research extensions, not hidden assumptions to be added to B21.

---

# 18. Required implementation semantics after audit

The rewritten B21 protocol must implement the following exact object:

\[
\boxed{
\mathcal F^A_{v,r,k}
=
\text{finite attained Pareto PWA branches over }(t,\rho,\pi)
}
\]

plus, separately if needed:

\[
\boxed{
\mathcal F^L_{v,r,k}
=
\text{limit-only lower-bound objects}.
}
\]

It must not restore a single earliest-time envelope across different discrete prefix families.

It must not use:

- old strict-\(g\) dominance;
- high-SOC dominance;
- primary equality pruning;
- limit-only deletion of attained branches.

---

# 19. Algebraic gates for rewritten B21

Before the previous 20 theorem cases, the new protocol must require:

## ALG-1

\[
R(R(X))\equiv R(X).
\]

## ALG-2

\[
R(D(R(X)))\equiv R(D(X)).
\]

## ALG-3

\[
R(S(R(X)))\equiv R(S(X)).
\]

## ALG-4

\[
R(C(R(X)))\equiv R(C(X)).
\]

## ALG-5

\[
R(CS(R(X)))\equiv R(CS(X)).
\]

## ALG-6

Merge commutativity under semantic equivalence.

## ALG-7

Merge associativity under semantic equivalence.

## ALG-8

Reduction-on vs reduction-off returns identical complete key/status.

## ALG-9

Limit-only objects never erase an attained executable winner.

## ALG-10

Primary-equality Region nodes remain live without a lexicographic certificate.

All must have zero violations before case-suite expansion.

---

# 20. Decision on the failed B21 attempt

The failed attempt remains scientifically valuable evidence.

It should be classified permanently as:

\[
\boxed{
\textbf{B21-v0 blocked by a fundamental compression/dominance counterexample}.
}
\]

It is not overwritten or retroactively made passing.

The two failed regressions remain historical evidence that the old authority was false.

---

# 21. Audit decision

The reset theory is materially different from an engineering patch.

Its correctness argument is now built around:

\[
\boxed{
\text{continuation preorder}
+
\text{conservation-law secondary coordinate}
+
\text{Pareto branches}
+
\text{transition congruence}.
}
\]

The audit found no internal contradiction or counterexample under the frozen research domain.

Therefore:

\[
\boxed{
\textbf{MILESTONE 5 CORE THEORY v1 PASSES THE ADVERSARIAL THEORY AUDIT}.
}
\]

Authorization granted:

\[
\boxed{
\textbf{rewrite the B21 protocol and Codex prompt against Core Theory v1}.
}
\]

Authorization not granted:

- B2-2 / long-haul;
- scalability claims;
- holdout;
- new dominance optimizations;
- product-layer uncertainty.

---

# 22. Immediate next artifact

The next document should be a **clean B21-v1 protocol**, not an amendment to the old protocol:

\[
\boxed{
\texttt{MILESTONE\_5\_B21\_EXACT\_VALIDATION\_PROTOCOL\_V1.md}
}
\]

It should treat the old B21 protocol as historical.

The new protocol must begin with ALG-1 through ALG-10 and the permanent 76-kWh waiting-plateau regression before the rest of Stage A.
