# HiRoute — Collaborator Brief

**One-line objective**

\[
\boxed{
\textbf{Exact hierarchical EV stop planning with continuous charging and schedule-aware stops.}
}
\]

---

## 1. Problem

HiRoute asks:

\[
\boxed{
\text{Where should an EV stop, when should it stop, and how long should it stay?}
}
\]

It is not a restaurant/hotel recommender. It plans vehicle stops.

The deterministic research core jointly chooses:

- road legs;
- stop Sites;
- stop effect:
  \[
  C,S,CS;
  \]
- charging quantity;
- schedule timing.

---

## 2. Exact objective

Plans are compared by:

\[
\boxed{
K(p)=
(J,Q,H,\Pi)
}
\]

lexicographically, with:

\[
J=T_{\rm clock}+\lambda_{\rm stop}H.
\]

Thus the exact solver must preserve not only primary time but also:

- total charged energy;
- number of stops;
- deterministic Site/action tuple.

---

## 3. Route/energy semantics

Every concrete leg uses the selected fastest directed route.

Travel time:

\[
d_T(u,v).
\]

Energy uses the actual length of that same fastest-time route:

\[
L_T(u,v).
\]

Driving energy:

\[
\kappa L_T(u,v).
\]

The shortest physical road metric:

\[
d_D
\]

is used only for admissible lower bounds.

---

## 4. Multi-stop physical state

\[
\boxed{
x=(v,t,E,r)
}
\]

with:

- anchor;
- absolute time;
- battery energy;
- remaining hard schedule flag.

A single generic hard schedule requirement is the current primary domain.

---

## 5. Continuous charging

Charging is not discretized.

For finite positive charging power:

\[
F(E)=3600\int_0^E1/P(u)\,du,
\]

and:

\[
C(a,b)=F(b)-F(a).
\]

Semantic charging requires:

\[
b>a.
\]

This strict inequality is mathematically important because feasible sets can be open.

---

## 6. Current exact semantic proposal

For a fixed discrete stop prefix \(\pi\) and current energy \(E\), define all executable completion times:

\[
\mathcal T_\pi(E).
\]

The exact abstraction should not assume an earliest executable time exists.

Define:

\[
\tau_\pi(E)=\inf\mathcal T_\pi(E),
\]

and:

\[
\chi_\pi(E)=
\mathbf 1[
\tau_\pi(E)\in\mathcal T_\pi(E)
].
\]

The pair:

\[
\boxed{
(\tau,\chi)
}
\]

is an attainment-aware lower time cut.

---

## 7. Secondary charge coordinate

Energy conservation gives:

\[
E=E_0+Q-C_{\rm drive}.
\]

Define:

\[
\boxed{
\rho=Q-E=C_{\rm drive}-E_0.
}
\]

For a fixed discrete prefix, \(\rho\) is constant.

At fixed energy:

\[
\boxed{
Q=E+\rho.
}
\]

So the candidate exact branch representation is:

\[
\boxed{
(I,\tau(E),\chi(E),\rho,\pi).
}
\]

Only \(E\) is a continuous frontier coordinate.

---

## 8. Continuation-safe dominance

At the same:

\[
(v,E,r,k),
\]

time cut A can substitute for B iff:

\[
\tau_A<\tau_B
\]

or:

\[
\tau_A=\tau_B
\land
(\chi_A=1\lor\chi_B=0).
\]

Full branch dominance additionally requires:

\[
\rho_A\le\rho_B,
\]

and if \(\rho_A=\rho_B\):

\[
\pi_A\le_{\rm lex}\pi_B.
\]

No cross-energy dominance is assumed.

---

## 9. Exact operator target

The representation must be closed under:

### Drive

\[
\tau'(E')=\tau(E'+c)+T.
\]

### Scheduled stop

\[
\tau_S=\max(a,\tau+h)+D.
\]

A waiting plateau can make an open input cut become attained.

### Charge

\[
\tau_C(E_d)
=
h+F(E_d)
+
\inf_{E_a<E_d}
[\tau(E_a)-F(E_a)].
\]

### Combined charge + schedule

\[
\tau_{CS}(E_d)
=
\inf_{E_a<E_d}
\max\{
\tau(E_a)+h+F(E_d)-F(E_a),
\max(a,\tau(E_a)+h)+D
\}.
\]

In every case the endpoint-attainment flag must also be propagated exactly.

---

## 10. Central theorem question

The immediate research question is:

\[
\boxed{
\textbf{
Is }(\tau,\chi,\rho,\pi)\textbf{ a sufficient exact continuation quotient, and does it admit a finite PWA representation?
}
}
\]

The production multi-stop solver is intentionally blocked until this is proved.

---

## 11. Hierarchy

The static hierarchy contains 60,498 attached Stop Sites organized into 2,047 Regions and 1,024 leaves.

The hierarchy may abstract only the **next-action set**.

It may not approximate the current semantic frontier.

Search node:

\[
N=(\mathcal Q,R,\alpha),
\qquad
\alpha\in\{C,S,CS\}.
\]

---

## 12. Lower bounds

For arbitrary current multi-stop anchor:

- inbound Region metric:
  directed ALT;
- Region-to-fixed-destination metric:
  ALT plus frozen egress-boundary lower bound.

The baseline multi-stop lower bound intentionally ignores future charging/schedule cost unless forced by the current effect.

Correctness precedes tightness.

---

## 13. Pruning

With incumbent primary value \(U_J\):

\[
\boxed{
L_J>U_J
}
\]

is safe.

\[
L_J=U_J
\]

is not enough because the node may contain a plan with equal primary time but lower charge or a better tie key.

---

## 14. Finite depth

For:

\[
\eta=h_{\min}+\lambda_{\rm stop}>0,
\]

and verified finite incumbent \(U_J\):

\[
\boxed{
H_{\max}
=
\left\lfloor U_J/\eta\right\rfloor.
}
\]

Thus the exact production theorem covers feasible queries with a verified incumbent.

---

## 15. Research program

### Stage 1 — semantic quotient theorem

Prove:

- cut sufficiency;
- exact attainment propagation;
- finite PWA closure;
- transition congruence.

### Stage 2 — exact small-domain validation

Implement:

- independent REF;
- flat exact quotient solver;
- hierarchical exact solver.

Require zero correctness mismatch.

### Stage 3 — deployable long-haul development

Measure:

- branch growth;
- Region pruning;
- exact evaluations;
- runtime;
- memory.

### Stage 4 — independent holdout

Freeze all algorithms and thresholds before holdout.

---

## 16. Intended final claim

If all stages succeed, the paper claim is:

\[
\boxed{
\textbf{
continuous-charge, deterministic, exact multi-stop EV stop planning can be made deployable by hierarchical action abstraction without changing the decision problem.
}
}
\]

Active information, stochastic uncertainty, and personalized preference learning are separate future layers.
