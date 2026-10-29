# Milestone 4R-B2-T7 Charging Frontier Specification

**Project:** dy-HiRoute  
**Stage:** Milestone 5 / legacy namespace 4R-B2  
**Substage:** T7 — Exact Continuous Charging Frontier  
**Status:** theory specification only; production B2 implementation is **not authorized** by this document  
**Frozen success endpoint:** deterministic exact multi-stop hierarchical planning + deployable evaluation + independent holdout

## 0. Purpose

The B2 theory audit closed T1–T6 except for one implementation-critical premise:

\[
q\in(0,E_{\max}-E^{arr}]
\]

is continuous at a charger leaf. An exact multi-stop search cannot enumerate one successor per \(q\), while an SOC grid would change the problem from exact to approximate.

T7 asks:

\[
\boxed{\textbf{Can exact continuous charging choices be represented by a finite frontier closed under all B2 transitions?}}
\]

This document freezes the mathematical object, proof obligations, semantic edge cases, and stop rules for answering that question. It does not authorize B2 production implementation, discretization, charge-to-X heuristics, hierarchy tuning, new geography, or long-haul experiments.

## 1. First principle

Battery energy remains continuous:

\[
E\in[E_{\min},E_{\max}].
\]

Exactness does not require enumerating every energy value as a separate node. It requires a finite representation \(\mathcal F\) such that:

1. every executable continuous-energy continuation is represented;
2. every executable represented point corresponds to a real continuation;
3. optimal value and deterministic tie key can be recovered;
4. the representation remains finite after every finite expansion.

The target object is a finite piecewise-affine frontier.

## 2. Charging-model prerequisite

Before proving T7, audit the exact charging law inherited from the frozen evaluator.

Assume a finite partition:

\[
0=b_0<b_1<\cdots<b_m=E_{\max}
\]

with strictly positive power on every segment:

\[
P_s(E)=p_{s,j}>0.
\]

The current canonical model is expected to satisfy this contract. If the accepted evaluator is Site-dependent, record it rather than silently homogenizing it.

Define:

\[
\boxed{
F_s(E)=3600\int_0^E\frac{1}{P_s(u)}\,du
}
\]

so \(F_s\) is continuous, strictly increasing, finite piecewise affine, and

\[
\boxed{
C_s(a,b)=F_s(b)-F_s(a)
}
\]

for \(0\le a\le b\le E_{\max}\).

## 3. Frontier state

For concrete anchor \(v\), schedule flag \(r\), and completed semantic stop count \(k\), define:

\[
\boxed{
\phi_{v,r,k}(E)
=
\inf\{t:\text{an admissible prefix ends at }(v,t,E,r,k)\}.
}
\]

The domain may be disconnected. Represent it as finitely many energy intervals with piecewise-affine time and \(+\infty\) outside the domain.

Open/closed endpoint status is part of the representation because semantic charging requires:

\[
q>0.
\]

## 4. Executable versus limiting points

Do not silently replace \(q>0\) with \(q\ge0\).

Every frontier boundary must carry attainment information:

- **attained**: an executable prefix realizes the value;
- **limit only**: the value is an infimum but no executable prefix attains it.

A limit-only point may support a lower bound. It may not update an incumbent, be returned as a plan, or satisfy a hard deadline by equality unless an executable point attains it.

## 5. Tie metadata

The accepted plan key is lexicographic. For every attained frontier point retain:

\[
\boxed{
\mu(E)=(Q(E),k,\pi(E))
}
\]

where:

- \(Q(E)\): minimum cumulative charged energy among histories attaining the same primary frontier value;
- \(k\): stop count;
- \(\pi(E)\): deterministic prefix Site/action signature.

When equal-time winners change, preserve the induced finite breakpoints.

## 6. Drive closure

For a fixed leg with:

\[
T=d_T(u,v),\qquad c=\kappa L_T(u,v),
\]

the transformed frontier is:

\[
\boxed{
(D\phi)(E)=\phi(E+c)+T.
}
\]

This is an affine shift plus domain clipping, so finite piecewise-affine structure, endpoint status, and witness metadata are preserved.

## 7. Schedule closure

For fixed overhead \(h\), start window \([a,b]\), and duration \(D\):

\[
y(E)=\max\{a,\phi(E)+h\},
\]

with feasibility:

\[
y(E)\le b.
\]

Completion:

\[
\boxed{
(S\phi)(E)=y(E)+D.
}
\]

The max with a constant and deadline clipping preserve finite piecewise-affine structure.

## 8. Closed-relaxation charging operator

First permit \(q\ge0\):

\[
\boxed{
(C_s^{\ge0}\phi)(E_d)
=
h+\min_{E_a\le E_d}
[\phi(E_a)+F_s(E_d)-F_s(E_a)].
}
\]

Define:

\[
G_s(E)=\phi(E)-F_s(E).
\]

Then:

\[
(C_s^{\ge0}\phi)(E_d)
=
h+F_s(E_d)+M_s(E_d),
\]

where:

\[
M_s(E)=\min_{x\le E}G_s(x).
\]

### Theorem T7-A

If \(\phi\) and \(F_s\) are finite piecewise affine, then \(M_s\) and therefore \(C_s^{\ge0}\phi\) are finite piecewise affine.

Constructively, on each affine segment of \(G_s\), the running minimum is either the previous constant minimum or the current affine segment while it decreases; only finitely many switches occur.

## 9. Exact semantic C operator

The actual C action requires strict positive charge:

\[
\boxed{
(C_s^{>0}\phi)(E_d)
=
h+\inf_{E_a<E_d}
[\phi(E_a)+F_s(E_d)-F_s(E_a)].
}
\]

Two cases exist:

1. the infimum is attained at some \(E_a<E_d\): executable;
2. the infimum occurs only as \(E_a\uparrow E_d\): limit-only.

The closed \(q\ge0\) transform is therefore an admissible relaxation, not automatically the exact semantic operator.

## 10. T7-B — semantic-attainment obligation

The theorem audit must close this in one of two principled ways.

### B1 — exact open-frontier representation

Prove that strict-positive C/CS frontiers, including endpoint openness and attainment, remain finitely representable and propagate safely through later operators.

### B2 — model-derived positive lower charge

Derive a strictly positive lower charge from already accepted semantics, not from an arbitrary engineering quantum.

An ad hoc SOC or energy granularity is not allowed under the frozen exact endpoint.

Until B1 or B2 is proved:

\[
\boxed{\textbf{T7 remains open.}}
\]

## 11. Why zero-charge non-closure matters

Selected-fastest-route actual lengths are not assumed to satisfy a distance triangle inequality.

Therefore it is possible in principle that:

- direct no-stop travel is energy-infeasible;
- a via-Site route is energy-feasible with zero charge;
- the via-Site event is effect-free and excluded;
- arbitrarily small positive charge makes it a semantic C action.

Then the semantic feasible set may approach a zero-charge limit without attaining it.

T7 must not hide this possibility.

## 12. Relaxed CS operator

Let:

\[
x(E_a)=\phi(E_a)+h.
\]

For \(E_a\le E_d\):

\[
c_C=x(E_a)+F_s(E_d)-F_s(E_a),
\]

\[
c_S=\max\{a,x(E_a)\}+D.
\]

Define:

\[
\boxed{
(CS_s^{\ge0}\phi)(E_d)
=
\min_{E_a\le E_d}\max\{c_C,c_S\}
}
\]

subject to:

\[
\max\{a,x(E_a)\}\le b.
\]

### Theorem T7-C

Partition by the finite regimes induced by:

- a segment of \(\phi\);
- a segment of \(F_s(E_a)\);
- a segment of \(F_s(E_d)\);
- schedule branch;
- active makespan branch.

Within a regime, all constraints and epigraph inequalities are linear in \((E_a,E_d,z)\). For fixed \(E_d\), minimizing \(z\) is a one-dimensional parametric LP. Its value is finite piecewise affine. A finite lower envelope over all regimes is finite piecewise affine.

Thus relaxed CS has finite piecewise-affine closure.

Exact CS still inherits T7-B's strict-positive attainment issue.

## 13. Merge closure

For finitely many predecessor frontiers:

\[
\boxed{
(M\{\phi_i\})(E)=\min_i\phi_i(E).
}
\]

The lower envelope of finitely many finite piecewise-affine functions is finite piecewise affine. Breakpoints arise only at existing segment boundaries and pairwise intersections.

Equal primary values are resolved by frozen lexicographic metadata. Endpoint openness is preserved exactly.

## 14. Capacity and floor

All operators clip exactly to:

\[
E_{\min}\le E\le E_{\max}.
\]

Clipping a finite union of intervals preserves finiteness.

## 15. Witness reconstruction

Every retained affine piece must preserve enough provenance to reconstruct:

- predecessor frontier piece;
- predecessor energy optimizer;
- selected Site;
- effect class;
- charging amount;
- schedule branch;
- stop count;
- cumulative charged energy;
- deterministic Site/action tuple.

A frontier value without an executable witness cannot update the incumbent.

## 16. Stop-count indexing

The initial exact representation remains:

\[
\phi_{v,r,k}(E).
\]

Do not merge across \(k\) unless a separate theorem proves it safe, because:

\[
g=(t-t_0)+\lambda_{\rm stop}k.
\]

## 17. Global termination is separate from local closure

Finite frontier closure after each finite expansion does not itself prove termination of an unlimited-stop search.

Production B2 therefore also needs one of:

1. a proved finite stop bound;
2. a cycle-elimination theorem;
3. an exact incumbent-derived depth bound plus a guaranteed finite-incumbent construction for every declared feasible query.

No hidden arbitrary stop cap is allowed.

## 18. Candidate cycle-elimination theorem

Under a Site-independent canonical charging law and waiting allowed, a promising theorem is:

> An optimal plan never visits the same concrete Stop Site twice with the same remaining-schedule flag \(r\).

Reasoning target:

- if the second visit has no more energy, the earlier state dominates;
- if it has more energy, replace the intervening same-\(r\) cycle by charging the net increase at the first visit;
- with the same charging law, charging around the cycle cannot be faster than direct charging for the net increase;
- removing the cycle also removes nonnegative drive time, overhead, and nuisance.

If proved:

\[
\boxed{
H\le2|\mathcal S|.
}
\]

If exact charger curves are Site-dependent, this theorem may fail and another termination argument is required.

## 19. T7-D — termination obligation

Before production implementation, prove one of:

- **D1:** cycle elimination and finite no-repeat depth;
- **D2:** exact finite depth from incumbent and positive per-stop cost;
- **D3:** another exact finite-domain theorem.

A diagnostic reference stop cap is not a production proof.

## 20. Complexity contract

T7 requires finite exact representation, not polynomial complexity.

For every operator later report:

- input piece count;
- output piece count;
- new breakpoints;
- intersections;
- merge compression.

The theorem must give a finite worst-case bound in terms of input piece count, charging-segment count, and predecessor count.

Exponential growth is an acceptable theorem outcome. It becomes a later performance issue, not a correctness excuse for discretization.

## 21. Numerical contract

The theorem is over real arithmetic.

A later implementation protocol must separately freeze:

- conservative breakpoint rounding;
- equality tolerance;
- open/closed endpoint logic;
- charger-breakpoint ordering;
- deterministic intersection ordering;
- high-precision/symbolic synthetic audits.

Numerical tolerance may protect admissibility; it may not alter feasibility.

## 22. Independent reference relation

The B2-T6 reference and T7 frontier implementation must be independently checkable.

For small fixed Site/effect sequences:

- the reference enumerates charging/max regimes and solves exact continuous optimization;
- the frontier method propagates piecewise-affine frontiers.

They must agree on:

- primary optimum;
- charged-energy tie value;
- stop count;
- Site tuple;
- charging amounts;
- schedule timing.

Do not implement both by calling the same core optimizer and call that independent validation.

## 23. Required synthetic theorem cases

At minimum cover:

1. one charging segment;
2. one breakpoint;
3. multiple breakpoints;
4. frontier with increasing/decreasing pieces;
5. disconnected energy domain;
6. merge intersection;
7. schedule clipping at \(b\);
8. schedule branch crossing at \(a\);
9. CS charge-dominant;
10. CS schedule-dominant;
11. CS branch switch;
12. zero-charge limit;
13. unattained positive-charge infimum;
14. attained positive-charge interior optimum;
15. time tie with different charged energy;
16. time/charge tie with different Site tuple;
17. floor clipping;
18. capacity clipping;
19. two-charge redistribution;
20. repeated-Site cycle.

## 24. T7 subgates

T7 closes only when all subgates close.

### T7-1 — charging-model contract

Finite positive segment representation verified against frozen evaluator.

### T7-2 — relaxed finite closure

Drive, S, \(C^{\ge0}\), \(CS^{\ge0}\), merge, and clipping proved finite piecewise affine.

### T7-3 — semantic positivity / attainment

Exact \(q>0\) semantics represented without treating unattained limits as executable.

### T7-4 — lexicographic witness closure

Charged-energy and deterministic plan-key ties remain exactly recoverable.

### T7-5 — finite depth / termination

The unlimited-stop optimum has a finite exact search representation.

All T7-1 through T7-5 must close before production B2 implementation.

## 25. What this specification already establishes

Subject to the finite-segment charging contract, this document establishes:

1. finite drive closure;
2. finite schedule closure;
3. a constructive prefix-minimum formula for relaxed charging;
4. finite parametric-LP closure for relaxed CS;
5. finite merge closure.

The unresolved exactness work is concentrated in:

\[
\boxed{
\text{strict-positive attainment}
+
\text{tie/witness closure}
+
\text{global finite-depth proof}.
}
\]

## 26. No model patching

If T7-3 fails because the semantic feasible set is genuinely non-closed, do not silently repair it by:

- adding arbitrary \(q_{\min}\);
- allowing effect-free charger waypoints;
- discretizing SOC;
- changing route-energy semantics.

Instead, produce the non-closure result and present the smallest principled model amendment as a separate decision.

## 27. Immediate next artifact

The next artifact is:

\[
\boxed{
\texttt{MILESTONE\_4R\_B2\_T7\_THEOREM\_AUDIT.md}
}
\]

It must resolve T7-1 through T7-5.

It should start with the strict zero-charge attainment issue, because that determines whether the proposed frontier represents the exact semantic action set or only its closure.

Do not write a B2 Codex implementation prompt before that audit closes.

## 28. Final verdict

The piecewise-linear frontier direction remains mathematically promising.

But finite closure of the relaxed set \(q\ge0\) is easier than exact representation of the actual semantic domain \(q>0\).

The central distinction is therefore:

\[
\boxed{
\text{finite lower-envelope representation}
}
\]

versus

\[
\boxed{
\text{finite exact executable-action representation}.
}
\]

T7 is closed only when the second statement is proved.
