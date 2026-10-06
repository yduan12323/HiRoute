# HiRoute — Formal Model and Exactness Specification

**Purpose:** mathematical specification for collaborator review  
**Scope:** latest deterministic multi-stop research model  
**Notation:** all optimization is exact unless an explicitly declared lower-bound relaxation is used

---

# 1. Directed transport network

Let:

\[
G=(V,E_G)
\]

be a finite directed legal road graph.

Each road edge \(e\) has:

- travel time \(t_e>0\);
- physical length \(\ell_e>0\).

For \(u,v\in V\), let:

\[
P_T(u,v)
\]

be the deterministically selected fastest-time directed path.

Define:

\[
d_T(u,v)
=
\sum_{e\in P_T(u,v)}t_e,
\]

\[
L_T(u,v)
=
\sum_{e\in P_T(u,v)}\ell_e.
\]

Define directed shortest physical distance:

\[
d_D(u,v)
=
\min_{P:u\leadsto v}
\sum_{e\in P}\ell_e.
\]

Then:

\[
d_D(u,v)\le L_T(u,v).
\]

No triangle inequality is assumed for \(L_T\).

---

# 2. Static Stop Sites

Let:

\[
\mathcal S
\]

be the finite attached Stop Site set.

Each Site \(s\in\mathcal S\) has:

- road anchor \(v_s\);
- static capability flags;
- stop overhead \(h_s>0\);
- charging law if charging-capable;
- schedule-support flag if relevant.

A static Region hierarchy is:

\[
\mathcal R.
\]

The root covers all Sites. Children partition parent Site membership. Leaves contain finite Site subsets.

---

# 3. Query

A query is:

\[
q=
(o,z,t_0,E_0,E_{\min},E_{\max},E_{\rm reserve},\mathcal H)
\]

where:

- \(o\): origin;
- \(z\): destination;
- \(t_0\): departure time;
- \(E_0\): initial battery energy;
- \(\mathcal H\): optional hard scheduled requirement.

For the primary multi-stop domain:

\[
\mathcal H\in
\{
\varnothing,
([a,b],D)
\}.
\]

---

# 4. Physical state

Physical state:

\[
\boxed{
x=(v,t,E,r)
}
\]

with:

\[
r\in\{0,1\}.
\]

Initially:

\[
x_0=(o,t_0,E_0,r_0).
\]

If no schedule requirement:

\[
r_0=0.
\]

Otherwise:

\[
r_0=1.
\]

Terminal feasibility requires:

\[
v=z,
\qquad
r=0,
\qquad
E\ge E_{\rm reserve}.
\]

---

# 5. Driving transition

For leg \(v\to u\):

\[
T(v,u)=d_T(v,u),
\]

\[
C_E(v,u)=\kappa L_T(v,u).
\]

Transition:

\[
t'=t+T(v,u),
\]

\[
E'=E-C_E(v,u).
\]

Require:

\[
E'\ge E_{\min}.
\]

---

# 6. Charging primitive

For charging-capable Site \(s\), assume finite positive piecewise charging power:

\[
P_s(E)>0.
\]

Define:

\[
F_s(E)=3600\int_0^E\frac{1}{P_s(u)}\,du.
\]

Exact charge duration from \(E_a\) to \(E_d\) is:

\[
C_s(E_a,E_d)
=
F_s(E_d)-F_s(E_a).
\]

Semantic charging requires:

\[
E_d>E_a.
\]

---

# 7. Semantic stop effects

Effect set:

\[
\mathcal A_{\rm eff}=\{C,S,CS\}.
\]

## 7.1 C

At Site \(s\):

\[
E_d>E_a.
\]

Completion:

\[
t'=t+h_s+C_s(E_a,E_d).
\]

## 7.2 S

Requires:

\[
r=1.
\]

Service start:

\[
y=\max(a,t+h_s).
\]

Require:

\[
y\le b.
\]

Completion:

\[
t'=y+D.
\]

Then:

\[
r'=0.
\]

## 7.3 CS

Requires charging capability and:

\[
r=1.
\]

With:

\[
E_d>E_a,
\]

charging completion:

\[
c_{\rm ch}=t+h_s+C_s(E_a,E_d).
\]

Schedule completion:

\[
c_{\rm sch}=\max(a,t+h_s)+D.
\]

Require schedule start no later than \(b\).

Completion:

\[
t'=\max(c_{\rm ch},c_{\rm sch}).
\]

Then:

\[
r'=0.
\]

---

# 8. Plan and objective

A complete plan:

\[
p=(\pi,\mathbf E)
\]

contains a discrete effect-labelled Site sequence:

\[
\pi=((s_1,\alpha_1),\ldots,(s_H,\alpha_H))
\]

and continuous charge decisions.

Primary objective:

\[
J(p)
=
(t_z-t_0)
+
\lambda_{\rm stop}H.
\]

Total charged energy:

\[
Q(p)=\sum_i q_i.
\]

Complete key:

\[
\boxed{
K(p)=
(J(p),Q(p),H,\pi)
}
\]

with lexicographic minimization.

---

# 9. Prefix family

Fix a discrete prefix:

\[
\pi_k=((s_1,\alpha_1),\ldots,(s_k,\alpha_k)).
\]

At exact anchor \(v\), requirement state \(r\), and battery energy \(E\), define executable completion-time family:

\[
\boxed{
\mathcal T_{\pi_k}^{v,r}(E)
=
\{
t:
\exists\text{ executable continuous realization of }\pi_k
\text{ ending at }(v,t,E,r)
\}.
}
\]

This set may be nonclosed.

---

# 10. Conservation coordinate

For every executable prefix:

\[
E=E_0+Q-C_{\rm drive}.
\]

Define:

\[
\boxed{
\rho=Q-E=C_{\rm drive}-E_0.
}
\]

For fixed discrete prefix:

\[
\rho_{\pi_k}
\]

is constant.

Therefore:

\[
Q(E)=E+\rho_{\pi_k}.
\]

---

# 11. Lower time cut

For nonempty \(\mathcal T(E)\), define:

\[
\tau(E)=\inf\mathcal T(E),
\]

\[
\chi(E)
=
\mathbf 1[\tau(E)\in\mathcal T(E)].
\]

Define:

\[
\boxed{
c(E)=(\tau(E),\chi(E)).
}
\]

The intended semantic branch is:

\[
\boxed{
b=
(I,\tau(E),\chi(E),\rho,\pi,w).
}
\]

---

# 12. Exact cut order

For:

\[
c_A=(\tau_A,\chi_A),
\qquad
c_B=(\tau_B,\chi_B),
\]

define:

\[
c_A\preceq_t c_B
\]

iff:

\[
\tau_A<\tau_B
\]

or:

\[
\tau_A=\tau_B
\land
(\chi_A=1\lor\chi_B=0).
\]

Equivalent semantic statement:

\[
\boxed{
c_A\preceq_t c_B
\iff
\forall t_B\in\mathcal T_B,\;
\exists t_A\in\mathcal T_A:
t_A\le t_B.
}
\]

This equivalence is a primary theorem obligation.

---

# 13. Full branch preorder

At identical:

\[
(v,E,r,k),
\]

define:

\[
b_A\preceq b_B
\]

if:

\[
c_A\preceq_t c_B,
\]

\[
\rho_A\le\rho_B,
\]

and:

\[
\rho_A=\rho_B
\Rightarrow
\pi_A\le_{\rm lex}\pi_B.
\]

The intended theorem is:

\[
\boxed{
b_A\preceq b_B
\Rightarrow
\text{every executable suffix of B has a lexicographically no-worse executable counterpart from A}.
}
\]

No cross-energy comparison is part of the core theorem.

---

# 14. Quotient frontier

For fixed:

\[
(v,r,k),
\]

the exact semantic quotient frontier is intended to be:

\[
\boxed{
\mathcal Q_{v,r,k}
=
\operatorname{ND}_{\preceq}
\{
b_\pi
\}.
}
\]

At energy \(E\), multiple branches may coexist.

The quotient is not a scalar earliest-time function.

---

# 15. Drive operator on cuts

Let drive time and energy be:

\[
T,c.
\]

Then:

\[
E'=E-c,
\]

\[
\tau_D(E')=\tau(E'+c)+T,
\]

\[
\chi_D(E')=\chi(E'+c),
\]

\[
\rho_D=\rho+c.
\]

---

# 16. S operator on cuts

Let:

\[
\psi_S(t)=\max(a,t+h)+D.
\]

Then:

\[
\tau_S(E)=\psi_S(\tau(E)).
\]

Define:

\[
\theta=a-h.
\]

Attainment:

\[
\boxed{
\chi_S(E)=
\begin{cases}
1, & \tau(E)<\theta,\\
\chi(E), & \tau(E)\ge\theta.
\end{cases}
}
\]

subject to hard-window feasibility.

This formula captures plateau-created attainment.

---

# 17. C operator on cuts

For output energy \(E_d\):

\[
\boxed{
\tau_C(E_d)
=
h+F(E_d)
+
\inf_{E_a<E_d}
[
\tau(E_a)-F(E_a)
].
}
\]

Let:

\[
m(E_d)
=
\inf_{E_a<E_d}
[
\tau(E_a)-F(E_a)
].
\]

Then:

\[
\chi_C(E_d)=1
\]

iff the value \(m(E_d)\) is realized by at least one admissible \(E_a<E_d\) together with an executable input realization that attains \(\tau(E_a)\).

Otherwise:

\[
\chi_C(E_d)=0.
\]

\[
\rho_C=\rho.
\]

---

# 18. CS operator on cuts

For:

\[
E_a<E_d,
\]

define:

\[
\psi_{CS}(t,E_a,E_d)
=
\max
\left\{
t+h+F(E_d)-F(E_a),
\max(a,t+h)+D
\right\}.
\]

Then:

\[
\boxed{
\tau_{CS}(E_d)
=
\inf_{E_a<E_d}
\psi_{CS}(\tau(E_a),E_a,E_d).
}
\]

Attainment requires exact witness existence.

For an input open cut, an output boundary can still become attained if:

\[
t\mapsto
\psi_{CS}(t,E_a,E_d)
\]

is constant on a right neighborhood of the input infimum.

This must be handled as an exact regime condition.

\[
\rho_{CS}=\rho.
\]

---

# 19. Semantic quotient theorem set

The following must be proved before production implementation.

## SQ-1 — lower-cut sufficiency in time

For the frozen monotone temporal domain, continuation-relevant information from a time family is exhausted by:

\[
(\tau,\chi).
\]

## SQ-2 — full branch continuation safety

The preorder in Section 13 implies full-key continuation dominance.

## SQ-3 — Drive closure

Drive maps finite quotient branches to finite quotient branches exactly.

## SQ-4 — S closure

S maps cuts exactly and may convert an open input cut into a closed output cut on a plateau.

## SQ-5 — C closure

Strict-positive charging maps finite PWA cut branches to finite PWA cut branches with exact endpoint attainment.

## SQ-6 — CS closure

Combined charging/schedule makespan has the same finite exact property.

## SQ-7 — finite quotient representation

After any finite action sequence, the quotient is representable by finitely many pieces with:

\[
\tau(E)\text{ PWA},
\]

\[
\chi(E)\text{ piecewise constant}.
\]

## SQ-8 — quotient congruence

For canonical reduction \(\mathscr R\):

\[
\boxed{
\mathscr R(T(\mathscr R(X)))
\equiv
\mathscr R(T(X))
}
\]

for:

\[
T\in\{D,S,C,CS\}.
\]

## SQ-9 — finite depth

A verified finite incumbent and positive per-stop primary cost imply an exact finite stop bound.

## SQ-10 — hierarchical exactness

Action-set abstraction plus admissible bounds preserves the exact complete key.

---

# 20. Hierarchical node

An abstract next-action node is:

\[
N=(\mathcal Q,R,\alpha).
\]

The hierarchy never approximates:

\[
\mathcal Q.
\]

It only represents a finite subset of concrete next actions.

---

# 21. Action partition invariant

For Region children \(R_j\):

\[
\boxed{
\mathcal A_\alpha(\mathcal Q,R)
=
\dot\bigcup_j
\mathcal A_\alpha(\mathcal Q,R_j).
}
\]

This must hold exactly.

---

# 22. Baseline metric bounds

Current anchor to Region:

\[
\underline T^-(v,R)
=
\underline T_{\rm ALT}(v,R).
\]

Region to fixed destination:

\[
\underline T^+(R,z)
=
\max
\{
\underline T_{\rm ALT}(R,z),
\underline T_{\rm boundary}(R,z)
\}.
\]

All terms must be admissible on the accepted directed road graph.

---

# 23. Baseline primary Region bound

For C:

\[
L_C
=
\inf_{b,E}
[
\tau_b(E)
+
\underline T^-(v,R)
+
h_{\min,R}
+
\underline T^+(R,z)
]
-t_0
+
\lambda_{\rm stop}(k+1).
\]

For S:

\[
L_S
=
\inf_{b,E}
[
\max(
a,
\tau_b(E)
+\underline T^-(v,R)
+h_{\min,R}
)
+
D
+
\underline T^+(R,z)
]
-t_0
+
\lambda_{\rm stop}(k+1).
\]

For CS, the same expression is a valid relaxation because semantic positive charge duration has infimum zero.

---

# 24. Pruning

With incumbent:

\[
K_U=(U_J,U_Q,U_H,U_\Pi),
\]

primary-only pruning is safe only when:

\[
\boxed{
L_J>U_J.
}
\]

Equality remains live unless a complete lexicographic lower bound is separately proved.

---

# 25. Finite stop bound

Let:

\[
\eta=h_{\min}+\lambda_{\rm stop}>0.
\]

Then any plan that primary-ties or improves a verified incumbent \(U_J\) satisfies:

\[
H\eta\le U_J.
\]

Thus:

\[
\boxed{
H_{\max}
=
\left\lfloor
U_J/\eta
\right\rfloor.
}
\]

---

# 26. Terminal exactness

Terminal executable branches satisfy:

\[
r=0,
\qquad
E\ge E_{\rm reserve}.
\]

The exact terminal plan set is ordered by:

\[
(J,Q,H,\Pi).
\]

If the infimum is not attained, return:

\[
\texttt{infimum\_unattained}.
\]

---

# 27. Reference-solver contract

The correctness oracle must be independent.

For bounded cases it enumerates:

- discrete Site/effect sequences;
- charging PWA regimes;
- schedule/max regimes;
- continuous extreme-point/LP regimes.

It must not invoke quotient reduction or Region pruning.

---

# 28. Exactness acceptance

A multi-stop implementation is accepted only if:

\[
\boxed{
K_{\rm production}=K_{\rm REF}
}
\]

for every bounded reference case, including status and attainment.

Required correctness violations:

\[
0.
\]

No runtime gain can compensate for a mismatch.

---

# 29. Current mathematical gate

The exact multi-stop algorithm should not be implemented beyond theorem probes until SQ-1 through SQ-8 are formally closed.

The key proposition is:

\[
\boxed{
\text{the lower time cut }(\tau,\chi)
\text{ is a sufficient and finitely closed continuation quotient under strict-positive C/CS semantics.}
}
\]

This is the current theory frontier.
