# M5 semantic quotient foundation: conditional proof and implementation audit

Date: 2026-10-06 UTC. Repository reviewed: HiRoute `381e9d6b2ccc214d8dc1ce348f5ec38cb1fe5b1b`.

## 0. Decision and scope

The attainment-aware lower time cut has a self-contained conditional proof for the frozen deterministic model. The exact object is an **upper closure of executable completion times**, with constructive realization support. It is not an attained-label frontier and is not a claim that every represented time is executable.

Under hypotheses H1–H8 below, the mathematical statements SQ-1 through SQ-8 are proved in Sections 2–10. This is a human-readable deductive proof, not a machine-checked formalization, a verified implementation, or acceptance of a production solver. In particular, an existence proof of a finite representation does not supply a tested, efficient frontier algorithm. Final M5-T acceptance must separately review the hypotheses, equivalence definition, witness contract, and implementation conformance.

The bounded semantic-contract/microprobe stage may proceed now. It may test the exact formulas and the historical witnesses while larger implementation/proof-review gates remain open. Passing point probes does not establish full PWA C/CS propagation, reduction congruence in code, REF independence, or hierarchical exactness. Do not proceed to normal REF/FLAT/HIER acceptance or scalability by relabeling bounded probes as those missing stages.

Important corrections/clarifications:

1. Apply the hard latest-start clipping rule before S/CS output formulas.
2. An open cut can dominate a later closed cut by supplying an actual no-later realization. The infimum itself is never an executable witness.
3. Witness metadata must realize a prefix below a valid supplied time budget, including an open-cut budget.
4. Congruence means mutual continuation substitution preserving optimization results, not equality of all executable-time sets, all plan keys, or branch records.
5. Terminal optimization is sequential: minimize J, verify attainment, then minimize Q on the attained J face. Primary attainment does not imply secondary attainment.
6. A verified incumbent gives a finite relevant-depth bound. Without one, this proof does not certify unrestricted infeasibility.
7. Different exact solvers may return different valid charge allocations with the same full optimum key unless an additional canonical witness order is frozen.

## 1. Hypotheses and authority

### H1. Static physical semantics

The Site set and effect alphabet are finite. Each ordered concrete leg has a deterministically selected route, with fixed time T >= 0 and fixed battery consumption c >= 0. Energy uses the actual length of that selected fastest-time route. No triangle inequality for its length is used here. Unreachable legs are simply unavailable.

### H2. State and histories

The state is (v,t,E,r), with r in {0,1}. Legal future actions depend on history only through this state and static capabilities. There are no repeat bans, history-dependent rewards, time-varying charger availability, hidden schedules, or other omitted physical state. All comparisons below use identical (v,E,r,k). Prefix tuples have the same length k.

### H3. Energy conservation

Only driving subtracts battery energy and only explicit charging adds it. Waiting, stop overhead and service consume no battery. The energy bounds are finite. Semantic C/CS requires Ed > Ea, never Ed >= Ea.

### H4. Charging primitive

Each permitted F is finite, continuous, strictly increasing, and piecewise affine on a finite energy partition. This holds for positive **piecewise-constant** power and for the frozen 100/60/30 kW law. Merely saying that power is positive or piecewise defined is insufficient to imply a PWA primitive; an arbitrary nonconstant power function can yield a non-PWA integral.

### H5. Temporal semantics

Stop overhead h > 0; service duration D >= 0. The schedule is [a,b], with invalid a > b treated as infeasible. S and CS use the stated max formulas and the latest-start condition max(a,t+h) <= b. Drive, C, S and CS are continuous and monotone nondecreasing in incoming time when their energy decisions are fixed. Every temporal feasibility guard is downward-closed in incoming time. Schedule waiting is exactly the waiting encoded by the stated max formulas. The proof does not require a discretionary waiting action, nor does it add one. If the declared physical model separately permits discretionary waiting, include its nonnegative durations explicitly in the linear realization constraints; assume they add no hidden cost or energy use beyond elapsed time. In neither interpretation are arbitrary synthetic budget times asserted to be executable waiting decisions.

### H6. Objective and prefix metadata

K = (J,Q,H,pi) in lexicographic order, J = terminal_time - t0 + lambda H. Prefix metadata rho and pi are exact. The tuple alphabet has a deterministic total order. A fixed discrete prefix fixes all driven legs, hence rho is constant. A branch after reduction may represent a restricted subfamily of that fixed prefix; it must never combine different rho/pi metadata under one lower envelope.

### H7. Finite exact descriptions

Initial sets and branch pieces have finite descriptions with affine equalities and strict/non-strict inequalities. A branch witness retains all inherited membership restrictions of its represented subfamily, including intermediate-energy restrictions introduced by earlier reduction; retaining only the unrestricted original prefix is insufficient. Exact arithmetic supports ordering of the coefficients. Rational data give an implementable rational arithmetic model; the abstract real-coefficient theorem alone does not imply an exact floating-point implementation. Empty fibers are omitted; every retained time fiber is nonempty and bounded below with finite infimum.

### H8. Finite local operation; global depth separately justified

Each proof of operator closure concerns finite branch sets and a finite action sequence. Uniform global finiteness additionally requires a fixed diagnostic depth or the incumbent-derived bound of Section 12. No polynomial size or runtime bound is asserted.

### Source record

Latest uploaded authority, read together:

- HIROUTE_FORMAL_SPEC.md, SHA-256 `1eddd50e5fd3f51841fa0c1f607b180aefde3b5e0a229b5c09de00f214e8f827`
- HIROUTE_RESEARCH_MASTER_PLAN.md, SHA-256 `f191e16d6ba1d3cbde059a06522d6a38da867f4ebdd54f531baa1928b01c174b`
- HIROUTE_COLLABORATOR_BRIEF.md, SHA-256 `9e150abc351353e6004be2e335ec28cdc97991df058cab7916b15f49234a2ff2`

Historical material used as failure evidence, not restored as current authority:

- MILESTONE_5_MULTISTOP_CORE_THEORY_V1.md, SHA-256 `dbe44ff83b4d98f2d06b090f7cd44bd40b0a4e21cc8eb439eee991ff2c73ccb2`
- MILESTONE_5_MULTISTOP_CORE_THEORY_AUDIT_V1.md, SHA-256 `02a1c417614852daec17a46be66f8930aa8de626128344122136617d5077b4c7`
- MILESTONE_5_B21_EXACT_VALIDATION_PROTOCOL_V1.md, SHA-256 `013c039b0c4d71f61fc43002ae05f63d33073293f7e0a709fc2e8b5bbe1e537f`
- docs/MILESTONE_5_B21_V1_REPORT.md
- docs/MILESTONE_4R_B2_B21_REPORT.md

## 2. Lower cuts and their exact order — SQ-1

Let T be a nonempty subset of real time, bounded below, with finite tau = inf T and chi = 1 iff tau belongs to T. Define

    U(T) = {u in R : there exists t in T with t <= u}.

**Lemma 2.1.** U(T) = [tau,infinity) if chi = 1, and U(T) = (tau,infinity) if chi = 0.

**Proof.** No t in T is below tau, so u < tau is excluded. For every u > tau, some t in T satisfies t < u: otherwise u would be a lower bound greater than the infimum. Thus u belongs to U(T). At u = tau, membership is equivalent to the existence of t <= tau in T, which is equivalent to tau in T. These exhaust the cases. QED.

A cut describes this upper closure exactly. It does not describe T exactly. For example, T1 = {0} and T2 = {0,1} have the same cut, although their feasible time sets differ.

**Lemma 2.2 (exact time-substitution characterization).** For nonempty families A and B,

    every tB in B has some tA in A with tA <= tB

holds iff

    tauA < tauB, or
    tauA = tauB and (chiA = 1 or chiB = 0).

Equivalently U(B) is a subset of U(A).

**Proof.** If tauA < tauB, every tB >= tauB > tauA has an A realization below it by Lemma 2.1. If the infima tie and chiA = 1, choose tA = tauA. If they tie and both cuts are open, every tB > tauA again has an A realization below it. Conversely, if tauA > tauB, the infimum property supplies tB < tauA, which no A realization can match. If the infima tie, chiA = 0 and chiB = 1, B's executable boundary tauB has no no-later A realization. These are exactly the remaining cases. QED.

**Lemma 2.3 (exact abstract one-step lifting).** Fix any continuous energy/discrete action decision z. Let its incoming-time guard G_z be downward-closed and its completion map f_z be monotone. The upper closure of its executable output is exactly

    {y : there exists u in U(T), G_z(u), and f_z(u) <= y}.

**Proof.** A real executable input t can be used as u, proving one inclusion. For the other, choose an executable t <= u from U(T)'s definition. Downward closure gives G_z(t); monotonicity gives f_z(t) <= f_z(u) <= y. Thus y bounds a genuine executable output. The same proof applies when existentially ranging over energy decisions, because the replacement uses the identical decision z. QED.

Continuity is not needed for this relational lemma. It is needed for evaluating the infimum as f(tau) at an open input cut. For instance f(0)=0, f(t)=1 for t>0 is monotone but not right-continuous, and an open cut at 0 maps to infimum 1 rather than f(0).

Apply Lemma 2.3 repeatedly. Equal lower cuts at fixed energy and identical rho/pi have mutually no-worse executable continuations under every finite legal suffix. This proves SQ-1 in the optimization/continuation sense, not equality of all executable keys. A literal requirement to preserve all executable time sets would be false by the example above.

## 3. Conservation and full-key continuation dominance — SQ-2

Energy conservation at every prefix is

    E = E0 + Q - Cdrive,    rho = Q - E = Cdrive - E0.

A drive consuming c changes (E,Q,rho) to (E-c,Q,rho+c). A charge q changes it to (E+q,Q+q,rho). S/wait changes neither E nor Q nor rho. Induction over actions proves the identity. For a fixed discrete prefix, Cdrive and therefore rho are constant, so Q(E)=E+rho for every charge allocation in that prefix family.

**Theorem 3.1.** At identical (v,E,r,k), suppose

    cA <=time cB,
    rhoA <= rhoB,
    rhoA = rhoB implies piA <=lex piB.

Then every executable realization of B with every finite legal suffix has an executable counterpart from A, using the same suffix Site/effect choices and charging energy decisions, with no-worse final K.

**Proof.** Choose B's actual starting time tB and its suffix. Lemma 2.2 supplies a real A prefix realization tA <= tB. Induct through the suffix: energies and r remain identical, temporal guards stay feasible because they are downward-closed, and completion time remains no later because each map is monotone. The number of future stops is identical. Thus final J_A <= J_B. Future charge increments are identical, and the initial Q difference at fixed E is rhoA-rhoB, so final Q_A <= Q_B. If J ties and Q ties, then rhoA=rhoB. Equal k and the same suffix imply equal H. Equal-length prefixes preserve their lexicographic order when appending the same tuple suffix: either a first differing prefix position remains the first difference, or the prefixes are identical. Therefore the final pi is also no worse. QED.

This is sufficient, not necessary, dominance. It authorizes no cross-energy, cross-k, or scalar-earliest-time deletion. Strictly earlier time alone is insufficient because waiting can erase the time advantage.

## 4. Exact clipping and fixed-parameter transforms — SQ-3 and SQ-4

### 4.1 Latest-start clipping

For S or CS, service feasibility is

    a <= b and t <= L,    L = b-h.

For a nonempty cut c=(tau,chi), the clipped actual family T intersect (-infinity,L] is nonempty iff

    tau < L, or tau = L and chi = 1.

**Proof.** If tau<L, the infimum property gives t<L. If tau=L and chi=1, t=tau is feasible. If tau>L no t can be feasible; if tau=L and chi=0 all t>L. QED.

Whenever the clipped family is nonempty, it has the same lower cut. For tau<L, arbitrarily close realizations remain below L; boundary membership is unchanged. For equality the clipped family contains the original attained boundary. Thus clipping must precede every S/CS formula, and an open cut at the deadline is empty rather than a limit-feasible state.

### 4.2 Drive — SQ-3

For fixed drive (T,c), restrict E to feasible battery outputs and put E'=E-c. Then

    tauD(E') = tau(E'+c)+T,
    chiD(E') = chi(E'+c),
    rhoD = rho+c.

Translation is a bijection between actual input and output times, proving both formulas and attainment exactly. Affine substitution and interval clipping preserve finite PWA pieces and endpoint flags. The stop count and tuple do not change during the drive itself.

### 4.3 S — SQ-4

After successful clipping and r=1/support checks, let theta=a-h. Then

    tauS = max(a,tau+h)+D,
    chiS = 1 if tau<theta, otherwise chi,
    rhoS = rho, r'=0, k'=k+1, pi'=pi||(s,S).

**Proof of value.** If chi=1, evaluate the actual boundary. If chi=0, take actual times converging down to tau within the clipped family; continuity gives output values converging to max(a,tau+h)+D, while monotonicity makes that a lower bound.

**Proof of attainment.** An attained input boundary is sufficient. If the input is open and tau<theta, the infimum property gives an actual t<=theta (indeed t<theta), and all such t finish at a+D, the output infimum. If tau>=theta, every actual t>tau lies on the strictly increasing side or strictly beyond its boundary, so output is strictly larger than the infimum. QED.

The piece split at tau(E)=theta and the deadline split at tau(E)=L are finite affine splits, including isolated endpoints.

## 5. C and CS value/attainment formulas — SQ-5 and SQ-6

Let I be the exact energy domain of one fixed-prefix branch, with actual time family at every included energy. Output energies also obey battery bounds.

### 5.1 C

For fixed Ed define A(Ed)={Ea in I: Ea<Ed}. If this set is empty, output is empty. Otherwise

    m(Ed) = inf over Ea in A(Ed) of [tau(Ea)-F(Ea)],
    tauC(Ed) = h+F(Ed)+m(Ed).

The output is attained iff there exists an actual admissible Ea<Ed such that

    tau(Ea)-F(Ea) = m(Ed) and chi(Ea)=1.

**Proof.** At each Ea the completion map is the strictly increasing translation t+h+F(Ed)-F(Ea), so its output cut is the translated input cut. The union over Ea has infimum equal to the infimum of those fiber infima: every actual value is bounded below by the latter, and for any positive epsilon choose Ea within epsilon/2 of the parameter infimum and an actual time within epsilon/2 of its time infimum. This approaches the stated value. Equality at an actual output forces both inequalities to be equalities, hence a minimizing actual Ea and an attained input cut; conversely these conditions provide the exact witness. QED.

The constant rho is preserved; append (s,C). Parameter endpoints excluded by the energy domain or Ea<Ed may define the value as a limit, but they cannot be witnesses.

### 5.2 Exact CS simplification

For d=F(Ed)-F(Ea)>0, put M=max(d,D). Then

    max(t+h+d, max(a,t+h)+D)
      = max(t+h+d, a+D, t+h+D)
      = max(a+D, t+h+M).

The schedule guard remains a<=b and t<=b-h. Completion being below or above a+D does not replace this guard.

For fixed admissible Ea,Ed let

    thetaCS(Ea,Ed) = a+D-h-M.

After successful latest-start clipping,

    g(Ea,Ed) = max(a+D, tau(Ea)+h+M),
    fixed-parameter output attained iff chi(Ea)=1 or tau(Ea)<thetaCS.

**Proof.** This is the same plateau/strictly increasing argument as S, with plateau endpoint thetaCS. Since M>=D, thetaCS<=a-h<=b-h, so tau<thetaCS automatically leaves latest-start slack. At tau=thetaCS an open input is not attained. QED.

For a branch, the parameter domain must first be restricted to

    A_CS(Ed) = {Ea in I : Ea<Ed and
      [tau(Ea)<b-h or (tau(Ea)=b-h and chi(Ea)=1)]},

with a<=b, r=1, charging and support capability checks. Then

    tauCS(Ed) = inf over Ea in A_CS(Ed) of g(Ea,Ed).

It is attained iff some actual Ea in A_CS(Ed) satisfies

    g(Ea,Ed)=tauCS(Ed)
    and [chi(Ea)=1 or tau(Ea)<thetaCS(Ea,Ed)].

**Proof.** The infimum-of-union argument is identical to C. Any actual output equal to the global infimum must lie in a parameter fiber whose own infimum equals the global infimum and is attained; otherwise its output is strictly above the global infimum. The fixed-parameter characterization gives the exact condition. Conversely such a fiber supplies a genuine attaining witness. QED.

Thus there are two separate possible failures of attainment: the input time boundary is unavailable without a plateau, or the parameter infimum is achieved only at an excluded/limiting Ea. Neither may be repaired with a numerical epsilon or charge quantum.

Finite representability for these formulas is proved next; it does not rest on an assertion that an open LP must have an optimal vertex.

## 6. Finite strict-polyhedral projection lemma

Call a generalized linear polyhedron a finite conjunction of affine equalities and inequalities, each inequality independently strict or non-strict. Empty, open, closed, lower-dimensional, and unbounded cases are permitted. A finite union of such sets will be called a finite linear set in this document.

**Lemma 6.1.** Finite linear sets are closed under affine substitutions, finite unions/intersections, and coordinate projections. Rational coefficients remain rational.

**Proof.** Substitution and intersections follow by writing the constraints; distribute finite unions when necessary. For projection, eliminate one real variable x from a conjunction. Replace equality by two weak inequalities or substitute it. Normalize the remaining inequalities with nonzero x coefficients into finite lower bounds x>=L_i(y) or x>L_i(y), and upper bounds x<=U_j(y) or x<U_j(y); retain constraints independent of x.

If there are both lower and upper bounds, existence of x is equivalent to all pairwise inequalities L_i(y)<=U_j(y), made strict whenever either original bound is strict. Necessity is immediate. For sufficiency, let L be the maximum finite lower bound and U the minimum finite upper bound. If L<U choose a midpoint. If L=U, the pairwise conditions force every bound active at L or U to be weak, so x=L satisfies all bounds. The case L>U is excluded. If only lower bounds exist choose their maximum plus 1; if only upper bounds exist choose their minimum minus 1; if neither exists choose 0. Thus the projected conjunction again has finitely many affine strict/non-strict inequalities. Eliminate the finitely many variables one at a time and distribute the finitely many original union members. QED.

This proof preserves strictness; replacing a strict feasible set by its closure is not an equivalent projection method.

## 7. Finite cut extraction and operator closure — SQ-5, SQ-6 and SQ-7

### 7.1 Input upper-closure representation

Refine each branch into finitely many energy cells on which tau(E) is affine and chi is constant. A cell may be an interval with independently open/closed endpoints or a singleton. Its exact upper closure is

    E in cell, u>=tau(E) if chi=1,
    E in cell, u>tau(E) if chi=0.

This is a finite linear set.

### 7.2 Relational operator descriptions

Drive uses E'=E-c and y>=u+T plus battery bounds. S uses the guard a<=b, u<=b-h and y>=a+D, y>=u+h+D. C uses Ea<Ed and

    y >= u+h+F(Ed)-F(Ea).

CS uses a<=b, u<=b-h, Ea<Ed and

    y>=a+D,
    y>=u+h+F(Ed)-F(Ea),
    y>=u+h+D.

In each case include the input upper-closure constraints, energy limits and capability/r checks, and existentially project input variables. Split Ea and Ed by the finitely many charging segments, so each F occurrence is affine. Lemma 2.3 proves that the resulting relation is exactly the upper closure of genuine executable outputs. Lemma 6.1 proves it is a finite linear set. No assertion that abstract u itself is executable is needed.

### 7.3 Extraction theorem

**Theorem 7.1.** If U is a finite linear subset of (E,y), each nonempty fiber U_E is an upward ray with a finite lower endpoint, then its energy domain is a finite union of intervals and points. Its lower endpoint tau(E) is finite PWA on a finite partition, and its endpoint-membership indicator chi(E) is constant on each cell of a finite refinement.

**Proof.** Write U as a finite union of conjunctions P_j(E,y). Replace each P_j by its upward closure V_j={ (E,z): exists y<=z with (E,y) in P_j }. Since U is already upward-closed, the union of these V_j is exactly U.

For a fixed j, normalize P_j's y inequalities into lower bounds y>=L_i(E) or y>L_i(E), upper bounds y<=B_l(E) or y<B_l(E), and E-only constraints. Eliminating y while adding y<=z gives:

- E-only feasibility constraints, including each L_i<=B_l, strict if either paired bound is strict;
- z>=L_i(E), with the same strictness as that lower bound.

Thus its exact nonempty energy domain D_j is an intersection of finitely many affine inequalities in one variable, hence an interval, singleton, all of R, or empty. If a nonempty V_j had no lower bound it would contain arbitrarily negative z at each of its energies, contradicting the finite lower endpoint of U. Therefore every nonempty constituent has a finite set of lower affine bounds.

On D_j the constituent lower endpoint is max_i L_i(E). It belongs to V_j iff every lower bound attaining this maximum is weak. Pairwise affine intersections and domain endpoints form a finite partition. On each open cell, the active maximal affine expressions and their strictness are fixed; singleton boundary cells are evaluated separately. Hence each V_j has finite PWA lower endpoint and piecewise-constant endpoint flag.

The union U has lower endpoint min_j tau_j(E) among constituents whose D_j contains E. Refine again by finitely many affine intersections and domain endpoints. Its flag is 1 exactly when a constituent at that minimum has flag 1. This produces a finite PWA endpoint and a finite constant-flag partition, including all isolated endpoint behavior. QED.

This permits discontinuities between cells; it does not assume global continuity of tau as a function of energy. It also distinguishes an excluded energy from an included energy carrying an open time cut.

### 7.4 Finite-sequence induction — SQ-7

The initial state at energy E0 has attained time t0, a singleton finite linear description. Sections 7.1–7.3 prove each D/S/C/CS step preserves finite cut representation. At any fixed finite depth, the finite Site/effect alphabet yields finitely many discrete prefixes. Their unions remain finite, and rho/pi remain constant on each branch by Section 3. Induction proves finite representation after every finite sequence and over every bounded-depth prefix set. This establishes SQ-5/6 finite closure and SQ-7 under H1–H8.

The construction can grow rapidly. It proves neither a practical bound on pieces nor that a particular interval implementation includes every switch or strict boundary.

## 8. Constructive executable witnesses

A sufficient branch witness interface is:

    realize_le(E,u): return an executable fixed-prefix realization
                     with final energy E and completion time t<=u.

Its exact precondition is

    u>tau(E), or u=tau(E) and chi(E)=1.

An equivalent open-cut interface returns a genuine realization with tau<=t<tau+epsilon for every epsilon>0. A finite collection of sampled approach times is not sufficient.

**Theorem 8.1 (existence of exact constructive lifting).** Under H1–H8, such a realization can be obtained by exact feasibility and back-substitution in finitely many strict linear regimes of the original prefix. For rational input data and rational query E,u, a rational realization exists and can be returned.

**Proof.** Fix a finite prefix. Introduce each intermediate energy, time and charge as a variable. If discretionary waiting is separately permitted by the physical model, also introduce its nonnegative duration variables and exact time-update equations; otherwise use only the waiting already expressed by the schedule max formulas. Split every F graph and every max graph into its finitely many affine regimes. A max equality y=max(f1,f2) is the union of y=f1,f1>=f2 and y=f2,f2>=f1; ties cause harmless overlap. Add exact drive equations, energy bounds, strict charge inequalities, service guards and the final conditions E_final=E and t_final<=u. Retain all inherited branch membership constraints, including restrictions on intermediate energies introduced by earlier reductions and predecessor-subfamily choices. These restrictions are part of the represented executable subfamily, not disposable implementation metadata. They remain finite linear constraints or finite disjunctions by Sections 7 and 9. This is a finite union of generalized linear polyhedra, exactly describing the requested concrete realizations in the represented subfamily. Reconstructing from the unrestricted original prefix alone could produce an executable plan outside that subfamily and below its claimed infimum, so that shortcut is not justified.

The cut's budget precondition implies nonemptiness by Lemma 2.1. Eliminate variables as in Lemma 6.1, retain the eliminated bounds, select the first feasible regime in a fixed finite ordering, then back-substitute. When two-sided extrema differ, a midpoint satisfies even strict active bounds. When they coincide, feasibility ensures active bounds are weak and that common value works. In the one-sided cases use maximum+1 or minimum-1; with no bounds use 0. These are actual values, not limiting points. Rational coefficients and query parameters yield rational values at each operation. All original constraints, including q>0, hold. QED.

The same back-substitution construction is piecewise affine in free parameters after finite splitting by the affine comparisons it uses. This establishes existence of finite witness rules, not an obligation to eagerly materialize all of them. An implementation may keep exact predecessor constraints and solve the certified query lazily.

For an attained S/CS output generated from an open input, obtain a valid incoming time budget on the plateau, realize it with this interface, then replay the action. More generally an output-boundary feasibility certificate gives an input budget and energy decision. Lifting can only produce an actual output no later than the certified boundary. Because that boundary is the true output infimum, the actual output must equal it. Therefore an executable optimum can be reconstructed without ever treating the input infimum as executable.

The witness data structure is part of implementation correctness. Storing only witnesses where chi=1 does not meet this theorem's interface. As a concrete restriction check, take two fixed C stops with zero drive, E0=0, final E=1, unit overheads, F1(E)=E and F2(E)=2E. For intermediate charge q1 in (0,1), total time is 4-q1. A represented subfamily restricted to q1<=1/2 has attained infimum 7/2. Solving only the unrestricted prefix at budget 7/2 may return q1=3/4 and time 13/4, outside that branch. The inherited restriction must be retained for exact branch-witness semantics.

## 9. Finite reduction and canonical representatives

At each energy, use the same-state cut/rho/pi preorder of Section 3. It is reflexive and transitive. For time, this follows from inclusion of upper closures; for rho it follows from <=; if the first and last rho in a chain tie, every rho in the chain ties and lexicographic prefix transitivity applies.

On a finite set, first quotient mutually dominating objects; retain a deterministic representative of every minimal equivalence class. Every removed object then has a retained dominating representative, by following a finite descending chain of classes. Do not delete every representative of a duplicate class in a simultaneous pairwise-delete pass.

Over energy, refine all branch endpoints, chi boundaries, and pairwise affine time intersections. On each open cell, support and every dominance predicate are constant; process singleton boundaries separately. The finite pointwise reduction therefore has finitely many pieces and covers every removed piece by retained replacements. Repeating complete reduction changes no semantic representative class. Thus R is idempotent up to the chosen semantic equivalence.

A deliberately partial safe reduction remains sound but may not be idempotent until a specified fixed point; do not claim canonical idempotence for an unspecified deletion pass.

## 10. Quotient congruence — SQ-8

For sets X,Y at the same discrete state, define X <=cont Y to mean: every genuine realization in Y, and every finite legal complete suffix from it, has a counterpart from X using the same future discrete/energy decisions and yielding a no-worse complete key. The counterpart prefix may depend on Y's realization and the suffix. Define X equivalent_cont Y iff both directions hold.

This is an optimization equivalence, not equality of all executable plan keys. Its use must be frozen in the new comparator/protocol; it cannot silently replace the old attained-label-set comparator inside preserved v1 evidence.

**Theorem 10.1.** Exact cut representation and canonical safe reduction satisfy

    R(T(R(X))) equivalent_cont R(T(X))

for T in {D,S,C,CS}, including their strict energy domains and schedule guards.

**Proof.** Section 9 and Theorem 3.1 supply a retained replacement for every realization removed by R. Retained realizations are themselves original realizations, so R(X) equivalent_cont X.

More strongly, consider one actual transition output from X. It came from an actual input at some energy Ea and time tB and a specific action/charge decision. The retained same-energy replacement has a real time tA<=tB with no-worse rho/pi. The same action is feasible from A, including strict Ed>Ea and the latest-start guard. Its actual output is no later, has identical output energy/r/k, and satisfies the same metadata order. Therefore every output from T(X) has an actual no-worse replacement from T(R(X)). The reverse inclusion/substitution follows because retained families are subfamilies of X. Section 2 and Sections 5–8 ensure exact transforms and cuts retain the existence of these actual replacements, including noninfimal outputs of an open-cut family.

Finally applying R to either output set preserves continuation equivalence by the same argument. Transitivity proves the stated law. The proof applies separately to each actual Ea; it does not require one output branch to dominate a removed family's entire parameterized image. QED.

The same argument proves merge commutativity and associativity modulo equivalent_cont, since union preserves pointwise replacement and R preserves equivalence. No equality of witness allocations or piece IDs follows.

Mutual continuation substitution preserves sequential optimization outcomes: each side's every key has a no-worse counterpart on the other. Primary infima are therefore equal. If one side attains the primary infimum, the other must match at that same primary value, establishing equality of primary-attainment status. Restrict this argument to that face to get equal Q infima and Q attainment. After Q is attained, continue to H and pi. This supplies the precise terminal consequence of SQ-8.

## 11. Terminal sequential lexicographic semantics

Let P be the actual feasible complete-plan set in the certified search domain. Never create a fictitious full key by concatenating unrelated coordinate infima.

1. If P is empty, return `infeasible` for that declared domain.
2. Set Jstar=inf{J(p):p in P}. Let P1={p in P:J(p)=Jstar}.
3. If P1 is empty, return `infimum_unattained`, `first_unattained=J`, exact Jstar and a nonattainment/approach certificate. Later optimized coordinates are undefined, not independently minimized over P.
4. Set Qstar=inf{Q(p):p in P1}. Let P2={p in P1:Q(p)=Qstar}.
5. If P2 is empty, return `infimum_unattained`, `first_unattained=Q`, attained primary Jstar, exact Qstar on the primary-optimal face, and a certificate. Do not supply an executable complete optimum key.
6. Otherwise choose Hstar=min{H(p):p in P2}; the nonnegative integer order guarantees existence. At fixed Hstar, the finite Site/effect alphabet gives finitely many tuples, so pi has a minimum. Return `attained_optimum` with the complete K and a fully replayed executable witness.

For terminal cuts, after the terminal drive and reserve clipping, compute Jstar from tau_b(E)-t0+lambda*k across exact domains. Its attained face is exactly the union of energies satisfying

    tau_b(E)-t0+lambda*k=Jstar and chi_b(E)=1.

Indeed an actual time strictly above tau cannot attain the global primary infimum: its own lower cut would give a strictly lower global infimum. On this face Q=E+rho_b. This proves that the cut representation supports the sequential procedure without keeping slower terminal realizations.

### 11.1 Legal global primary-nonattainment example

Graph edges: o->z has (time=1,energy=100); o->s and s->z each have (time=1,energy=1). The sole Site s supports C. E0=Emax=10, Emin=reserve=0, h=1, lambda=1, F(E)=E seconds, no schedule. The selected fastest direct leg o->z is battery-infeasible. Every feasible plan uses at least one C at s. With exactly one C and q in (0,1], it reaches z at time 3+q, so J=4+q. Repeated C stops at s are allowed, but with n>=1 such stops and total positive charge q, J=2+2n+q; extra stops cannot improve the stated infimum. The global primary infimum 4 is not attained. q=0 would be an illegal neutral stop.

### 11.2 Legal global secondary-nonattainment example

Graph edges: o->g has (time=1,energy=100); o->s, s->g, and g->z each have (time=1,energy=1). Only s supports C; only g supports S. E0=Emax=10, Emin=reserve=0, h_s=h_g=1, lambda=1, F(E)=E seconds. Schedule [10,10], D=1; t0=0.

Direct selected-fastest o->g and o->z legs are battery-infeasible. Every feasible plan must enact at least one C at s and S at g; repeated C stops at s remain legal. Every feasible terminal time is at least 12 and H>=2, hence J>=14. The plans with exactly one C at s, q in (0,1], then S at g arrive at g at 3+q, release at 4+q<=5, wait to service start 10, complete service at 11 and reach z at 12. They attain H=2 and J=14. Extra C stops have H>2 and cannot be primary-optimal. On the actual J=14 optimal face, Q=q has infimum 0 unattained. Primary optimum is attained; there is no lexicographic optimum. The correct result is `infimum_unattained`, first_unattained Q, primary 14, secondary infimum 0. The equality face must not be replaced by its closed q>=0 relaxation.

These graphs are consistent with selected-fastest-route semantics. Their detour consumes less energy than the direct fastest route; the model expressly does not assume a triangle inequality for selected-route energy.

## 12. Finite-depth and pruning caveats

Assume hmin>0, lambda>=0, eta=hmin+lambda>0 and a verified finite executable incumbent with primary UJ. Every stop increases clock by at least its overhead: C adds h+d; S adds max(a,t+h)+D-t>=h; CS is at least t+h+d. Drives have nonnegative time. Therefore

    J(p) >= H(p)*eta.

Any plan primary-tying or improving the incumbent must satisfy

    H <= floor(UJ/eta).

This is exact and does not depend on a no-repeats theorem. It also covers improving sequences approaching an unattained primary/secondary optimum, because every relevant member with J<=UJ lies inside the bound. A tighter incumbent may shrink the bound; equality depths must be retained.

The result does not prove that the algorithm can find an incumbent on every query, or certify infeasibility over arbitrarily many stops when it cannot. `infeasible` under H_ref=4 means bounded-domain infeasible unless another completeness argument applies. A diagnostic cap is not a production theorem.

With an admissible primary node bound LJ and executable incumbent UJ, LJ>UJ is safe to prune. LJ=UJ remains live: a plan there may improve Q, H or pi, or prove secondary nonattainment on the primary-optimal face. A synthetic unattained infimum is not an executable incumbent. Full hierarchical exactness additionally requires action coverage/refinement, admissible route bounds and exhaustive finite scheduling of live nodes; SQ-1–8 alone do not prove those implementation properties.

## 13. Historical counterexamples remain permanent

### B21-v1 open-C object

Input A has Ea in (0,1], t=1000+60Ea, rho=0. Input B is attained at Ea=1/2, t=1031, rho=1. With h=300, F(E)=36E, Ed=1:

    tA'=1336+24Ea, 0<Ea<1;
    cA'=(1336,open), rhoA'=0;
    tB'=1349, cB'=(1349,closed), rhoB'=1.

The new cut order permits A' to dominate B'. A concrete witness is Ea=1/4, giving tA'=1342<=1349. It does not use 1336 as an executable time. Applying S with h=300, [a,b]=[2000,2100], D=100 yields attained completion 2100: tauA'=1336<1700, so the plateau creates attainment. The old attained/limit-only frontier cannot express this replacement, which is why its recorded failure remains valid.

### B21-v0 waiting/charge object

At the shared pre-schedule energy, A is earlier by 228 seconds but has rho=35; B is later with rho=28. A does not dominate B because rhoA>rhoB. Both must survive until the schedule plateau removes the time difference. The expected winner remains

    (44950 seconds, 76 kWh, 3, ((2,C),(3,C),(4,S))).

The 83-kWh alternative remains wrong. The historical reference reports different charge allocations (41,35) and (28,48) kWh realizing the same 76-kWh key. Validation should compare status and K exactly and independently replay witnesses, not require identical allocations absent a separately frozen canonical-witness convention.

## 14. SQ status and remaining gates

| Obligation | Mathematical status here | Exact scope / remaining implementation gap |
|---|---|---|
| SQ-1 | Proved under H1–H7, Sections 2–3 | Continuation optimization equivalence, not equality of all executable times; budget-witness interface required |
| SQ-2 | Proved under H1–H6, Section 3 | Same (v,E,r,k) only; no cross-energy/k theorem |
| SQ-3 | Proved under H1–H8, Section 4 | Exact drive translation, clipping and witness replay still require code tests |
| SQ-4 | Proved under H1–H8, Section 4 | Latest-start equality and open plateau endpoints must be tested |
| SQ-5 | Proved finite closure under H1–H8, Sections 5–8 | General output-energy frontier extraction/strict-parameter handling not established by a fixed-Ed probe |
| SQ-6 | Proved finite closure under H1–H8, Sections 5–8 | Full Ea/Ed regime propagation and global witness minimizer testing remain distinct from point CS probes |
| SQ-7 | Proved under H1–H8, Sections 6–9 | Existential finite size only; no efficiency or polynomial-growth claim |
| SQ-8 | Proved under H1–H8, Sections 9–10 | Mutual continuation substitution only; actual canonical reduction/comparator conformance requires independent validation |

The unqualified claims “arbitrary monotone PWA maps admit evaluation f(tau)”, “a cut preserves all feasible time sets”, “every positive charging law gives finite PWA closure”, and “bounded failure without incumbent proves global infeasibility” are not proved and are false or unsupported without the stated restrictions.

### Gate A: bounded semantic contract and microprobes

May proceed before full implementation acceptance. Require exact rational tests of:

- every cut order endpoint combination, including open-earlier vs closed-later;
- latest-start tau<L, tau=L closed, tau=L open, and tau>L;
- S/CS plateau interior, boundary, charging-dominant and schedule-dominant regimes;
- strict Ea<Ed and minimizing Ea excluded at an endpoint;
- actual budget witnesses and original constraint replay;
- old v1 1336-open/1349-closed witness and S completion 2100;
- old v0 preserving the lower-rho candidate, with the full 76-kWh regression kept for the independently validated solver stage;
- primary and secondary nonattainment result contracts;
- immutable preservation of historical evidence.

### Gate B: M5-T proof acceptance and exact implementation specification

Review and freeze this proof's hypotheses and equivalence, verify the source authority and numerical contract, independently audit witness reconstruction, and specify the finite PWA/frontier representation and canonical reduction in enough detail to test. Any discovered counterexample is a theory hard stop, not a reason to reinterpret an earlier failed test.

### Gate C: independent REF, then FLAT, then HIER

Only after Gate B. REF must enumerate physical discrete/regime constraints independently and use strict-feasibility checks on optimal faces. FLAT must be compared with reduction off/on. HIER additionally needs exact action partition, admissible bounds and equal-primary handling. Preserve zero-tolerance full-key/status comparisons. Solver validity is not inferred from this proof document or from the microprobe's pass count.

No push, PR, deployment, long-haul or holdout result is authorized or claimed by this review.
