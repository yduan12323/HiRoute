# Milestone 4R-B2-T7 Theorem Audit

**Project:** dy-HiRoute  
**Stage:** Milestone 5 / legacy namespace 4R-B2  
**Substage:** T7 — Exact Continuous Charging Frontier  
**Purpose:** decide whether deterministic exact multi-stop implementation can represent continuous charging with a finite exact state/frontier structure  
**Frozen success endpoint:** deterministic exact multi-stop hierarchical planning + deployable evaluation + independent holdout

---

# 0. Executive verdict

The five T7 subgates were audited from first principles.

| Subgate | Status | Result |
|---|---|---|
| T7-1 charging-model contract | **closed** | the frozen canonical finite-segment positive-power charging law admits a finite piecewise-affine cumulative primitive |
| T7-2 relaxed frontier closure | **closed** | drive, S, relaxed C, relaxed CS, merge, and clipping preserve finite piecewise-affine frontiers |
| T7-3 strict-positive semantics / attainment | **closed without model patch** | exact open-frontier semantics are finitely representable by value + attainment; non-attained infima are never treated as executable plans |
| T7-4 lexicographic witness closure | **closed** | time, cumulative charge, and deterministic witness ties admit a finite lexicographic piecewise representation |
| T7-5 finite depth / termination | **closed for the declared feasible-query domain** | any supplied finite feasible incumbent plus strictly positive per-stop overhead+nuisance gives an exact finite stop bound |

Therefore:

\[
\boxed{\textbf{T7 CLOSED}}
\]

for the primary B2 research domain:

\[
\boxed{
\textbf{feasible deterministic multi-stop queries supplied with a finite executable incumbent}
}
\]

under the frozen canonical charging model.

No SOC grid, positive charge quantum, neutral action, route-energy semantic change, or arbitrary stop cap is required.

A pathological instance may have an executable-plan infimum that is not attained because semantic charging uses \(q>0\). The exact solver must detect and report that condition rather than fabricate an executable optimum. On instances with an attained optimum, it returns the exact executable optimum and accepted tie key.

The next stage may therefore be **B2-1 exact small-domain validation**, not production-scale long-haul search.

---

# 1. Scope and non-goals

This audit does not change:

- the B1-D2 frozen one-stop method;
- the action-effect principle;
- \(q>0\) for C/CS;
- fastest-time routing semantics;
- selected-fastest-route actual length for driving energy;
- the canonical charging curve;
- the one generic hard scheduled-stop requirement;
- exactness as the success criterion.

It does not authorize:

- SOC discretization;
- arbitrary \(q_{\min}\);
- effect-free route-shaping stop actions;
- new routing semantics;
- new geography;
- long-haul stress;
- holdout consumption.

---

# 2. T7-1 — Charging-model contract

The accepted canonical charging law is a finite positive-power piecewise model.

Write its breakpoints as:

\[
0=b_0<b_1<\cdots<b_m=E_{\max}
\]

and on each segment:

\[
P(E)=p_j>0.
\]

For the currently frozen canonical curve the accepted powers are finite positive constants (the existing 100/60/30 kW piecewise curve).

Define cumulative charging time:

\[
\boxed{
F(E)
=
3600\int_0^E \frac{1}{P(u)}\,du.
}
\]

Then:

1. \(F\) is finite on \([0,E_{\max}]\);
2. \(F\) is continuous;
3. \(F\) is strictly increasing;
4. \(F\) is piecewise affine with finitely many segments;
5. exact charging time is:
   \[
   \boxed{
   C(a,b)=F(b)-F(a)
   }
   \]
   for:
   \[
   0\le a\le b\le E_{\max}.
   \]

If a later product model introduces Site-dependent charging curves, T7 must be re-audited only to the extent that those curves cease to have finite positive piecewise-affine cumulative primitives.

For the frozen research model:

\[
\boxed{\textbf{T7-1 CLOSED}}.
\]

---

# 3. Exact frontier object

For a concrete anchor \(v\), remaining-schedule flag \(r\), and completed semantic stop count \(k\), define:

\[
\boxed{
\phi_{v,r,k}(E)
=
\inf
\left\{
t:
\exists\text{ admissible prefix ending at }(v,t,E,r,k)
\right\}.
}
\]

The exact frontier representation is not merely a real-valued function.

It is the tuple:

\[
\boxed{
\mathfrak F
=
(\phi,\mathcal A,Q,\Pi)
}
\]

where:

- \(\phi(E)\): infimal completion time;
- \(\mathcal A(E)\in\{0,1\}\): whether \(\phi(E)\) is attained by an executable prefix;
- \(Q(E)\): minimum cumulative charged energy among attained prefixes realizing \(\phi(E)\);
- \(\Pi(E)\): deterministic lexicographically winning prefix witness among those matching \((\phi,Q)\).

The domain is a finite union of intervals whose endpoints may be open or closed.

Outside the domain:

\[
\phi(E)=+\infty.
\]

This tuple is the exact search representation.

---

# 4. Why attainment must be first-class

The semantic action rule is:

\[
q>0
\]

for C and CS.

Therefore the set of executable charging actions is not topologically closed at \(q=0\).

For an infimum approached only as:

\[
q\downarrow 0,
\]

the frontier value is mathematically meaningful but no executable action realizes it.

Such a point may:

- contribute to an admissible lower bound;
- participate in proving that no better objective exists.

It may not:

- update the incumbent;
- produce a returned plan;
- satisfy a hard equality deadline as an executable witness.

This is not a numerical approximation.

It is the exact semantics of an optimization problem over an open feasible set.

---

# 5. T7-2A — Drive closure

For a fixed leg:

\[
T=d_T(u,v),
\qquad
c=\kappa L_T(u,v),
\]

the arrival frontier is:

\[
(D\phi)(E)
=
\phi(E+c)+T.
\]

This is an affine translation.

Finite interval structure, affine pieces, attainment, charged-energy metadata, and witness identity all transfer directly.

Capacity/floor clipping introduces at most finitely many new endpoints.

Therefore drive closure is finite and exact.

---

# 6. T7-2B — Schedule closure

At an eligible scheduled Site:

\[
y(E)=\max\{a,\phi(E)+h\}.
\]

Feasibility is:

\[
y(E)\le b.
\]

Completion is:

\[
(S\phi)(E)=y(E)+D.
\]

On each affine frontier piece, the equation:

\[
\phi(E)+h=a
\]

has at most one interior crossing unless the piece is exactly flat at that level.

Therefore each input piece is split into only finitely many schedule branches.

Deadline clipping:

\[
\max\{a,\phi(E)+h\}\le b
\]

also cuts each affine piece at finitely many points.

Attainment transfers unchanged because S introduces no new optimization over an open variable.

Hence S preserves finite exact frontier structure.

---

# 7. T7-2C — Relaxed charging closure

Temporarily permit:

\[
q\ge0.
\]

For departure energy \(E_d\):

\[
(C^{\ge0}\phi)(E_d)
=
h+
\min_{E_a\le E_d}
[
\phi(E_a)+F(E_d)-F(E_a)
].
\]

Define:

\[
G(E)=\phi(E)-F(E).
\]

Then:

\[
\boxed{
(C^{\ge0}\phi)(E)
=
h+F(E)+M(E)
}
\]

with:

\[
M(E)=\min_{x\le E}G(x).
\]

Because \(\phi\) and \(F\) are finite piecewise affine, so is \(G\).

On an affine segment:

\[
G(x)=\alpha x+\beta,
\]

the prefix minimum behaves as follows:

- if \(\alpha>0\), the segment cannot improve after its left endpoint;
- if \(\alpha=0\), it contributes a constant candidate;
- if \(\alpha<0\), the running minimum follows the affine segment only after it crosses the previous minimum.

Thus every input affine piece creates only finitely many output switches.

Therefore:

\[
M
\]

is finite piecewise affine, hence:

\[
C^{\ge0}\phi
\]

is finite piecewise affine.

No discretization is used.

---

# 8. T7-2D — Relaxed CS closure

For arrival energy \(E_a\) and departure energy \(E_d\ge E_a\), define:

\[
x(E_a)=\phi(E_a)+h.
\]

Charging completion:

\[
c_C
=
x(E_a)+F(E_d)-F(E_a).
\]

Scheduled completion:

\[
c_S
=
\max\{a,x(E_a)\}+D.
\]

Relaxed CS completion:

\[
(CS^{\ge0}\phi)(E_d)
=
\min_{E_a\le E_d}
\max\{c_C,c_S\}
\]

subject to:

\[
\max\{a,x(E_a)\}\le b.
\]

Partition the feasible set by the finite combinations of:

- one affine segment of \(\phi(E_a)\);
- one affine segment of \(F(E_a)\);
- one affine segment of \(F(E_d)\);
- schedule branch \(x(E_a)\le a\) or \(x(E_a)\ge a\);
- active makespan branch.

Inside one such regime all expressions are affine in:

\[
(E_a,E_d,z)
\]

with linear inequalities:

\[
z\ge c_C,
\qquad
z\ge c_S,
\qquad
E_a\le E_d.
\]

For fixed parameter \(E_d\), minimizing \(z\) is a finite-dimensional linear program.

A one-parameter linear program with finitely many bases has a value function that is piecewise affine over finitely many parameter intervals.

There are finitely many regimes and finitely many bases.

The lower envelope of all valid regime value functions is therefore finite piecewise affine.

Hence relaxed CS closure is finite.

---

# 9. T7-2E — Merge closure

For finitely many predecessor frontiers:

\[
\phi(E)=\min_i\phi_i(E).
\]

On any pair of affine pieces, equality occurs:

- nowhere;
- everywhere;
- or at one intersection.

Therefore the primary lower envelope of finitely many finite piecewise-affine functions has finitely many breakpoints.

Tie metadata is treated separately in T7-4.

Thus merge closure is finite.

---

# 10. T7-2 verdict

Drive, S, relaxed C, relaxed CS, merge, and clipping all preserve a finite piecewise-affine representation.

Therefore:

\[
\boxed{\textbf{T7-2 CLOSED}}.
\]

The relaxed result alone does not yet prove exact \(q>0\) semantics.

---

# 11. T7-3 — Strict-positive charging

The exact semantic C operator is:

\[
(C^{>0}\phi)(E_d)
=
h+
\inf_{E_a<E_d}
[
\phi(E_a)+F(E_d)-F(E_a)
].
\]

Define again:

\[
G(E)=\phi(E)-F(E).
\]

Then:

\[
(C^{>0}\phi)(E)
=
h+F(E)+
\inf_{x<E}G(x).
\]

The exact value is therefore a **strict prefix infimum**.

The key observation is:

> for a finite piecewise-affine \(G\), the strict prefix infimum has the same finite piecewise-affine value representation as the closed prefix minimum, but its attainment status may differ at finitely describable sets.

---

# 12. Strict-prefix attainment classification

For a fixed departure energy \(E\), define:

\[
m_<(E)=\inf_{x<E}G(x).
\]

The value is attained iff there exists:

\[
x^*<E
\]

such that:

\[
G(x^*)=m_<(E)
\]

and the predecessor frontier value at \(x^*\) is itself attained.

For finite PWA \(G\), a failure of attainment can occur only when the active infimum is approached at an open right boundary or at:

\[
x\uparrow E
\]

without an earlier minimizing point.

On each affine regime, whether such an earlier minimizer exists is constant except at finitely many:

- input breakpoints;
- running-minimum switch points;
- equality intersections.

Therefore the attainment function:

\[
\mathcal A_C(E)
\]

is piecewise constant over a finite interval partition.

The exact C frontier is thus finitely representable as:

\[
(\phi_C,\mathcal A_C).
\]

No \(q_{\min}\) is required.

---

# 13. Strict-positive CS

The exact CS operator replaces:

\[
E_a\le E_d
\]

with:

\[
E_a<E_d.
\]

The closure of the feasible polyhedron gives the same infimal value as the relaxed parametric LP.

Attainment is determined by whether at least one optimal basis admits a feasible point with strict:

\[
E_a<E_d
\]

and an attained predecessor witness.

For each finite active-basis regime, this strict-feasibility property is described by finitely many linear inequalities in \(E_d\).

Therefore the parameter domain partitions into finitely many intervals where:

- the infimum is attained;
- or the value is limit-only.

Thus exact CS also has a finite:

\[
(\phi_{CS},\mathcal A_{CS})
\]

representation.

---

# 14. Non-attained global optimum

The current model can, in principle, produce:

\[
\inf J
\]

with no executable plan attaining it.

This is possible because:

- effect-free zero-charge Site stops are excluded;
- positive charge can approach zero;
- selected-fastest-route actual lengths are not assumed to satisfy a distance triangle inequality.

This is a property of the frozen mathematical domain, not a frontier defect.

The exact solver must therefore distinguish:

### Attained optimum

Return:

- exact objective;
- executable charging quantities;
- complete plan key.

### Unattained infimum

Return:

\[
\boxed{\texttt{status = infimum\_unattained}}
\]

together with:

- exact infimum value;
- proof that no attained frontier/witness realizes it.

It must not fabricate an executable optimizer.

This preserves exactness without changing the action model.

For the research success endpoint, evaluation cases intended to test executable planning should be required to have attained optima; the reference solver must audit this rather than assume it.

---

# 15. T7-3 verdict

Exact \(q>0\) semantics can be represented by:

\[
\boxed{
\text{finite PWA value}
+
\text{finite attainment partition}
}
\]

without introducing a charge quantum or neutral action.

Therefore:

\[
\boxed{\textbf{T7-3 CLOSED}}.
\]

---

# 16. T7-4 — Lexicographic witness closure

Primary frontier time is not enough.

For every attained energy \(E\), define secondary cumulative charge:

\[
Q(E)
=
\min
\{
Q_{\rm prefix}:
\text{prefix attains }\phi(E)
\}.
\]

If multiple prefixes tie on \((\phi,Q)\), use the accepted deterministic witness order.

Stop count \(k\) is already an explicit frontier index.

---

# 17. Charge transform for secondary energy

Suppose a charging transition chooses optimizer:

\[
E_a^*(E_d).
\]

Then:

\[
Q'(E_d)
=
Q(E_a^*)
+
(E_d-E_a^*).
\]

Within any fixed active parametric-LP basis/regime:

\[
E_a^*(E_d)
\]

is affine in \(E_d\).

The predecessor secondary function \(Q\) is piecewise affine by induction.

Therefore:

\[
Q'
\]

is affine within a finite refinement of the primary regime partition.

If multiple primary-optimal bases exist, minimize \(Q'\) over the primary-optimal face.

This is a second parametric linear optimization over a finite polyhedral family and again yields a finite piecewise-affine value function.

---

# 18. Discrete witness tie

After primary time and cumulative charge tie, candidate predecessor/Site tuples come from a finite set on every finite expansion.

Pairwise winner changes can occur only at the finite primary/secondary breakpoints already created.

Therefore the lexicographically winning discrete witness is piecewise constant over a finite partition.

Every attained frontier piece can store:

- predecessor piece ID;
- affine predecessor-energy rule;
- Site ID;
- effect label;
- schedule branch;
- stop count;
- charged-energy expression.

This suffices to reconstruct the exact executable plan.

---

# 19. Limit-only points and ties

Limit-only points have no executable tie key.

They retain only:

- infimal primary value;
- lower-bound provenance;
- non-attainment status.

They cannot defeat an attained incumbent merely through an unavailable secondary tie.

If:

\[
\inf J < U,
\]

a limit-only OPEN object prevents an exact attained-optimum certificate until the solver establishes whether the global problem itself has an unattained infimum.

If:

\[
\inf J = U,
\]

the attained incumbent remains a valid executable optimum in primary objective; secondary tie comparison applies only among attained plans.

---

# 20. T7-4 verdict

Lexicographic exactness is representable by a finite refinement of the PWA frontier partition.

Therefore:

\[
\boxed{\textbf{T7-4 CLOSED}}.
\]

---

# 21. T7-5 — Finite depth / termination

Local frontier closure does not by itself bound the number of semantic stops.

The cleanest exact finite-depth theorem does **not** require a no-repeat-site theorem.

It uses the already accepted positive per-stop cost.

Let:

\[
h_{\min}>0
\]

be the minimum fixed stop overhead in the declared B2 domain and:

\[
\lambda_{\rm stop}>0.
\]

Define:

\[
\boxed{
\eta=h_{\min}+\lambda_{\rm stop}>0.
}
\]

Every semantic stop adds at least:

\[
\eta
\]

to the primary objective because all travel, waiting, charging, and scheduled durations are nonnegative.

Therefore every plan with \(H\) semantic stops satisfies:

\[
\boxed{
J(p)\ge H\eta.
}
\]

---

# 22. Incumbent-derived exact stop bound

Suppose the search is supplied with a finite executable incumbent of unrounded primary objective:

\[
U<+\infty.
\]

Any plan capable of strictly improving the incumbent must satisfy:

\[
H\eta<U.
\]

Any plan capable of tying the incumbent primary objective must satisfy:

\[
H\eta\le U.
\]

Therefore it is sufficient to search:

\[
\boxed{
H\le H_{\max}
=
\left\lfloor
\frac{U}{\eta}
\right\rfloor
}
\]

with one conservative extra level permitted in implementation if desired for floating-point safety.

This is **not** an arbitrary stop cap.

It is an exact consequence of:

- a concrete executable incumbent;
- positive fixed stop overhead;
- positive stop nuisance.

---

# 23. Why a feasible incumbent is an explicit domain contract

Without a finite incumbent, the above theorem does not give a finite depth.

The primary B2 production/evaluation domain is therefore declared as:

\[
\boxed{
\mathcal D_{\rm B2}
=
\{\text{queries supplied with at least one verified finite executable plan}\}.
}
\]

This is appropriate for the frozen research endpoint because B2 evaluates optimization and hierarchical pruning on feasible EV trips.

The incumbent may come from:

- an independent baseline planner;
- the exact small-domain reference in B2-1;
- a separately verified constructive feasible route in B2-2.

The hierarchical method may improve it but must never rely on an unverified heuristic objective as an incumbent.

Detecting infeasibility for arbitrary unlimited-stop queries is not claimed by this theorem and is not part of the primary B2 benchmark contract.

This limitation must be stated in the final paper.

---

# 24. Finite global representation

Once:

\[
H\le H_{\max},
\]

the discrete indices are finite:

- finite concrete anchor set;
- \(r\in\{0,1\}\);
- \(k\in\{0,\ldots,H_{\max}\}\);
- finite effect classes.

At every finite expansion:

- each frontier contains finitely many pieces by T7-2/T7-3;
- merging finitely many predecessor frontiers remains finite;
- only finitely many \(k\)-layers exist.

Therefore the entire exact multi-stop search representation is finite.

No cycle-elimination theorem is required for T7 closure.

A no-repeat theorem may later improve performance, but it is not a correctness prerequisite.

---

# 25. T7-5 verdict

For the declared feasible-query domain with a verified finite incumbent:

\[
\boxed{\textbf{T7-5 CLOSED}}.
\]

The derived bound is exact and instance-specific.

No hidden fixed \(H\) is introduced.

---

# 26. Complexity theorem

Let:

- \(n\): input frontier piece count;
- \(m\): charging primitive segment count;
- \(p\): number of predecessor frontiers merged.

Then every T7 operator creates a finite number of regimes.

A conservative structural bound is polynomial in the finite regime enumeration for a **single operator application**, while repeated multi-stop expansion may cause exponential growth in frontier pieces across depth.

T7 makes no polynomial-time claim.

The theorem required for correctness is only:

\[
\boxed{
\text{finite input}
\Rightarrow
\text{finite exact output}.
}
\]

Piece explosion is a B2-1/B2-2 empirical scalability question.

---

# 27. Frontier form of the B2 exactness theorem

The earlier B2-T5 theorem used point labels.

T7 permits an exact finite set-valued replacement.

For a frontier object:

\[
\mathfrak F_{v,r,k},
\]

the frontier represents all nondominated continuous-energy labels at that discrete state.

An abstract next-action node becomes:

\[
\boxed{
N=(\mathfrak F_{v,r,k},R,\alpha).
}
\]

Its Region lower bound is:

\[
L(N)
\le
\inf_{E\in\operatorname{dom}\mathfrak F}
\left[
g(E)
+
\text{relaxed next-action/continuation cost}
\right].
\]

Because \(g(E)\) and all frontier pieces are finite piecewise affine, this infimum over a Region-bound expression is itself finitely computable by segment endpoint/intersection analysis.

Thus T5 OPEN coverage extends from point labels to exact frontier labels without changing the represented concrete plan set.

No new theory gate is required.

---

# 28. Search termination and unattained lower limits

For an attained global optimum, normal branch-and-bound termination is:

\[
\min_{OPEN}L\ge U
\]

at \(\epsilon=0\), with the accepted tie audit over attained candidates.

If OPEN contains a limit-only object with:

\[
L<U,
\]

the search cannot certify \(U\) yet.

If all remaining improving representations are limit-only and their exact global infimum is below every attained plan, the correct result is:

\[
\boxed{\texttt{infimum\_unattained}}.
\]

This behavior is necessary for mathematical exactness under the frozen open action domain.

---

# 29. Independent reference requirement

T7 closure is theoretical.

B2-1 must still validate it against an independent exact reference.

The reference solver must:

- enumerate small effect-labelled Site sequences;
- enumerate charging-curve/max regimes;
- solve the resulting continuous linear subproblems;
- distinguish attained optima from unattained infima.

The frontier implementation must not share its charging-frontier transform code with the reference optimizer.

Required agreement:

- attained/unattained status;
- primary value;
- total charged energy;
- stop count;
- Site tuple;
- charging quantities;
- schedule times.

---

# 30. Required B2-1 pathological tests

B2-1 must include explicit cases where:

1. a zero-charge C limit exists but is not attained;
2. the global infimum is unattained;
3. an attained alternative has slightly higher primary cost;
4. a later operation merges an unattained lower-limit frontier with an attained frontier;
5. CS has a strict-positive limit inside schedule overlap;
6. exact tie metadata changes winner on an interior breakpoint;
7. incumbent-derived \(H_{\max}\) is active;
8. a repeated-site route exists but is cut only by the exact depth bound, not an unproved no-repeat rule.

These cases are mandatory because they exercise the precise issues T7 resolves.

---

# 31. Audit conclusion

All five T7 subgates are now theoretically closed for the declared feasible-query B2 domain.

The result is:

\[
\boxed{
\textbf{continuous charging does not require SOC discretization for exact multi-stop search.}
}
\]

The exact representation is:

\[
\boxed{
\text{finite piecewise-affine energy frontier}
+
\text{attainment flags}
+
\text{lexicographic witness metadata}
}
\]

with finite depth derived from a verified feasible incumbent and positive per-stop cost.

The one nonstandard but mathematically necessary behavior is that the solver may report:

\[
\boxed{\texttt{infimum\_unattained}}
\]

for pathological instances in the frozen open \(q>0\) action domain.

No model patch is required to preserve exactness.

---

# 32. Authorization status after this audit

The theory blocker is closed.

However, the next step is **not** long-haul production search.

The correct next milestone is:

\[
\boxed{
\textbf{B2-1 — Exact Small-Domain Multi-Stop Validation}
}
\]

Before coding, freeze a B2-1 experimental protocol that specifies:

- the independent reference solver;
- frontier implementation contract;
- small synthetic and bounded real cases;
- exact tie/attainment comparisons;
- frontier-piece accounting;
- no production scalability claim;
- hard stop on any correctness mismatch.

Only after B2-1 passes should a deployable multi-stop hierarchy be scaled toward B2-2 long-haul stress.
