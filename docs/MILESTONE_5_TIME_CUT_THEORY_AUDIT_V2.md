# Independent audit of HiRoute cut lemmas

Scope: frozen finite-site, deterministic nonnegative-leg model, continuous increasing finite piecewise-affine charging primitive, strict positive charging, monotone max-based schedule rules. This is an elementary proof audit, not an implementation review.

## Verdict

The proposed upper-closure/projection route is sound with the qualifications below. No counterexample was found to the corrected SQ-1–SQ-8 claims in the frozen model. The two most important separations are (i) arbitrary-family cut sufficiency versus semilinear-prefix witness construction, and (ii) mutual continuation optimization equivalence versus equality of executable time sets or syntax.

## 1. Cut identity and order

For nonempty T bounded below, let tau=inf T and chi indicate tau in T. Set U(T)={u: there exists t in T with t<=u}. Every u>tau has some t in T with t<u, by the definition of infimum. No u<tau belongs. Hence U(T)=[tau,infinity) if chi=1, and (tau,infinity) otherwise.

The semantic comparison forall b in B, exists a in A with a<=b is exactly B subset U(A), equivalently U(B) subset U(A). The asserted four-case cut order follows. This requires neither interval structure nor closedness of T.

An empty family needs a separate absent-domain marker or explicitly specified infinity cut. Do not apply the nonempty lemma to it.

## 2. Upper-closure transform lemma

Fix all non-time action parameters z. Let G_z be a downward-closed set of input times and f_z be nondecreasing. Then

U({f_z(t): t in T intersect G_z})
=
U({f_z(u): u in U(T) intersect G_z}).

One containment uses T subset U(T). For the other, an abstract u has an actual t<=u. Downward closure gives t in G_z, and monotonicity gives f_z(t)<=f_z(u). Union over z preserves the identity. This also covers correlated energy parameters by holding the input energy fixed while selecting t.

Continuity is not required for this identity. Right continuity is required if one separately asserts inf f(T)=f(tau) for an open input boundary. Counterexample without it: T=(0,infinity), f(t)=0 for t<=0 and 1 for t>0. The upper-closure identity is true, but f(tau)=0 is not the output infimum 1.

Downward-closed guards are essential: T={0}, guard t>=1, identity transform. Exact output is empty while applying the guard to U(T) is nonempty.

This identity concerns upper closures. It does not identify exact executable-time sets: T={0} and U(T)=[0,infinity) already differ under identity.

## 3. Exact schedule feasibility and CS plateau

For the hard window, a<=b makes the guard exactly t<=B where B=b-h. A nonempty input family survives iff

tau<B, or tau=B and chi=1.

Both S and the admissible Ea domain in CS must enforce this before their displayed infimum formulas. An open cut with tau=B is infeasible, despite its numerical boundary satisfying the weak inequality.

For fixed Ea<Ed let delta=F(Ed)-F(Ea)>0, M=max(delta,D), A=a+D. Then

psi_CS(t)=max(A,t+h+M).

Define beta=A-h-M. Since M>=D, beta<=a-h<=B. Conditional on feasibility, the output boundary is max(A,tau+h+M), and its attainment bit is 1 if tau<beta, otherwise chi. For an open cut with tau<beta, choose an actual t<=beta; it is feasible and lies on the plateau. At tau=beta with chi=0 every actual t is above the plateau. S is the special max(A,t+h+D) rule with beta=a-h.

CS minimization over Ea still needs existence of an admissible energy and actual prefix witness achieving the overall boundary. A fixed-Ea plateau test alone does not settle this existential energy minimization.

## 4. Finite strict polyhedra and projection

Use finite unions of sets given by affine equalities, weak inequalities, and strict inequalities over real variables. Choose charging affine segments and max regimes as finitely many disjuncts. Strict Ea<Ed stays strict. The complete executable prefix relation is therefore such a union, by induction over a finite action sequence. Add the budget variable u and t<=u, then project other variables to obtain U in (E,u).

Fourier–Motzkin is exact here. Pair a lower bound L<=y or L<y with an upper bound y<=R or y<R. The projected inequality is L<=R when both are weak and L<R when either is strict. Zero-variable inequalities and inconsistent strict equalities must be retained. With only one side bounded, there is no cross-bound condition. Equalities can be represented as two weak inequalities.

This is mathematical exactness over exact real coefficients. An executable exact algorithm additionally needs an effective coefficient representation/comparison model, for example rational or appropriate algebraic data; arbitrary unnamed real constants do not by themselves supply computable comparisons.

## 5. Projection to finite PWA tau and finite chi

Here upward-closed means vertical/time-upward at each fixed E, not product-order upward closure in energy and time. Let D be the nonempty-fiber energy domain. Assume each E in D has a finite real lower boundary.

Write projected U as a finite union P_i of strict/weak polyhedra in (E,u). For each P_i, project onto E to get a finite interval or singleton domain D_i (possibly empty). A nonempty P_i fiber must have at least one finite lower u bound: otherwise that fiber is unbounded below, contradicting the assumed finite lower boundary of U.

Normalize its u-lower inequalities as u>=ell_ij(E) or u>ell_ij(E). On D_i its infimum is

l_i(E)=max_j ell_ij(E).

The domain D_i already incorporates upper u bounds and their feasibility/strictness; they cannot simply be dropped before computing D_i. Thus tau(E)=min_{i:E in D_i} l_i(E).

Partition the real E-line at all domain endpoints and affine crossings needed by these maxima and minima. Include each endpoint as its own singleton cell when required. The resulting finite cells have affine tau. To determine chi, substitute u=tau(E) into all inequalities of each active P_i and take the OR over i. Each substituted inequality is affine in E, so adding finitely many roots gives a finite partition on which chi is constant.

'Piecewise affine' here permits jumps and independent singleton values. Semilinearity does not imply continuity of tau. For example U={E<0,u>0} union {E>=0,u>=1} has tau 0 to the left and 1 at/right of zero.

## 6. Constructive witnesses

A finite PWA executable witness exists for the finite union of complete prefix systems with parameters (E,u). Project by elimination, retain the elimination records, choose the first feasible disjunct on a finite semilinear partition, and back-substitute in reverse order.

For the eliminated variable y let L be the largest lower affine bound and R the smallest upper affine bound, evaluated at the already selected variables. Choose:

- (L+R)/2 when L<R;
- L when L=R (projection guarantees all binding endpoint requirements are weak);
- L+1 when only lower bounds exist;
- R-1 when only upper bounds exist;
- 0 when neither exists.

Max/min selection, feasibility disjunct selection, and the equality cases induce finitely many affine cells. Composition with earlier finite PWA choices remains finite PWA. The selected complete prefix variables satisfy the original system and hence return an actual execution with t<=u. Substitution of a piecewise-affine terminal/plateau budget yields corresponding finite PWA witnesses on its feasible domain.

Crucial limitation: semilinear U alone does not imply such a selector for arbitrary underlying T. Let T be the positive rational times, so U=(0,infinity). A finite PWA selection t(u) in T with 0<t(u)<=u cannot exist: on every open interval an affine function valued only in the rationals must be constant, and a finite partition has a constant cell arbitrarily near zero, contradicting t(u)<=u. Thus retain the full semilinear executable-prefix relation; the arbitrary-T sufficiency theorem does not prove witness regularity.

## 7. Branch preorder and canonical reduction

The branch relation is transitive. If rho_A=rho_C in a chain rho_A<=rho_B<=rho_C, then all three rho are equal and prefix lex ordering composes. Lower-cut ordering is transitive by upper-set inclusion.

For continuation safety, choose A's actual no-later realization at the exact same (v,E,r,k), then use B's same discrete suffix and same charge energy choices. Monotonicity and downward guards preserve feasibility and no-later arrival. Same k and suffix give equal total H. Conservation gives final Q_A-Q_B=rho_A-rho_B. When primary and Q tie, equal-length prefix lex order is preserved on appending the same suffix. This requires the stated Markov model: no unstated history-dependent constraints such as prohibiting previously visited sites. It also requires a fixed total order for the discrete prefix alphabet.

A finite preorder quotient followed by retaining one representative of each minimal equivalence class ensures every removed label is dominated by a retained one. Quotient first, or use a deterministic duplicate rule; naive 'remove every dominated item' can delete all mutually equivalent copies. Energy-wise changes of comparison have a finite partition because cuts are finite PWA, chi is finite piecewise constant, and rho/pi are fixed per branch. Preserve rho/pi and witness provenance on every retained fragment.

For congruence, continuation equivalence must quantify over the same continuation/action context. Mere equality of one currently optimal terminal key is not a congruence for forced next-action operators. The concrete replacement construction above is stronger and supplies the needed same-suffix simulation. Union and one-step composition preserve it, yielding R(T(R(X))) equivalent to R(T(X)) in this continuation-optimization sense. It does not establish equality of exact time sets or branch syntax.

## 8. Terminal and depth qualifications

Optimize J first. If its finite infimum is unattained, report that fact and do not assign fictitious later components of a full minimum key. If J is attained, restrict to its actual attained face and optimize Q there. Q can itself have an unattained infimum. Only if both are attained proceed to H and then pi. Integer H and finite site/effect alphabet give attained later tie-breakers in the bounded setting. A finite real lexicographic infimum tuple need not exist when the first coordinate is unattained; e.g. keys {(epsilon,0):epsilon>0} have no greatest finite tuple lower bound.

Mutual no-worse continuation simulation preserves nonemptiness, these sequential infima/attainment stages, and any attained minimum key. Earlier-time surrogate points on an attained global J face cannot be spurious: an actual strictly earlier realization would contradict global J minimality.

The depth proof needs eta=h_min+lambda>0, not only h_min>0, nonnegative leg/charge durations, and a verified executable finite incumbent. Then J>=H eta, and all plans that can tie or improve its J have H<=floor(U_J/eta). This bounds a global improving sequence too. Without an incumbent, this argument proves neither finite search depth nor global infeasibility.

## 9. Document-specific second-pass review (2026-10-06 03:23 UTC)

Reviewed the actual draft `M5_SEMANTIC_QUOTIENT_FOUNDATION_REVIEW_20261006.md`, especially Sections 6–10 and its final mathematical/acceptance status. This review postdates the general lemma audit above.

### Findings and verified corrections

1. **Inherited-subfamily witness restrictions were initially omitted from Section 8's construction.** H6 permits a retained branch to represent a restricted subfamily of a fixed prefix. Solving the unrestricted original prefix can return an execution outside that subfamily and strictly below its reported boundary, invalidating both the boundary-reconstruction assertion and literal subfamily preservation. Concrete counterexample: two C stops, no drive, E0=0, final E=1, unit overheads, F1(E)=E and F2(E)=2E; t=4-q1 for 0<q1<1. Restricting the represented branch to q1<=1/2 gives attained tau=7/2. An unrestricted solve at budget 7/2 can return q1=3/4,t=13/4, outside the branch. **Verified fixed:** H7 and Section 8 now require all inherited intermediate-energy membership restrictions and predecessor-subfamily disjunctions, and the draft includes this counterexample.

2. **Finite PWA selection needed an explicit regime-selection rule.** Arbitrary deterministic choice need not itself have finite affine cells. **Verified fixed:** Section 8 now selects the first feasible regime in a fixed finite ordering.

3. **The nonattainment examples initially excluded repeated charging stops in their prose without authority.** H2 permits repeats, so 'only legal plan' and 'every feasible plan has H=2' were false. The infimum conclusions did not depend on that exclusion. **Verified fixed:** The primary example allows n>=1 C stops with J=2+2n+q; the secondary example proves terminal time>=12 and H>=2, exhibits H=2/J=14, and excludes extra C stops only from primary optimality by their larger H.

4. **H5's broad 'Waiting is allowed' needs model-consistent wording.** If it introduces discretionary waiting, the exact executable relation in Section 8 must include nonnegative wait variables and inherited constraints on them. For the frozen max-formula model, the clean wording is that schedule waiting is encoded by the max formulas and no discretionary-wait action is required. This is a model-consistency clarification rather than a counterexample to the stated monotone-cut argument.

### Final mathematical and acceptance assessment

Sections 6–7 give a correct elementary strict-projection and finite cut-extraction proof. In particular, upward-closing each projected conjunction before extracting its maximal lower bound correctly accounts for original upper-time bounds through the energy-feasibility domain. Sections 9–10 correctly use finite same-energy preorder reduction and concrete same-suffix replacement; they do not falsely equate executable-time sets or syntactic branches.

After the inherited-subfamily fix, no further substantive mathematical gap was found in SQ-1–SQ-8 for the frozen finite-semilinear model. The document's conditional claim that these statements are deductively proved is supported by the argument. Its explicit separation from machine-checked formalization, M5-T acceptance, production implementation, REF independence, and hierarchical acceptance is necessary and appropriately retained. The proof supports the bounded semantic-contract/microprobe gate, not an unqualified solver-acceptance claim.

**Final resolution verification (03:24 UTC):** Item 4 is also resolved. I read the revised H5 and Section 8: they now distinguish max-encoded schedule waiting from a separately permitted discretionary-wait action and explicitly add nonnegative wait variables/time equations only in the latter declared model. All document-specific findings above have now been corrected and verified. No unresolved substantive mathematical gap or acceptance overclaim remains from this review, within the stated hypotheses and scope.
