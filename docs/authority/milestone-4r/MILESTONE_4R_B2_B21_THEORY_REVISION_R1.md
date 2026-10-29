# Milestone 4R-B2-B21 Theory Revision R1
## Waiting-Plateau Tie Preservation and Pareto Frontier Semantics

**Project:** dy-HiRoute  
**Stage:** Milestone 5 / legacy namespace 4R-B2  
**Trigger:** confirmed B21 Stage-A counterexample  
**Status:** proposed normative theory revision; B21 implementation remains blocked until this revision is accepted and the B21 protocol is amended accordingly  
**Frozen predecessor evidence:** the failed B21 attempt and its counterexample evidence must remain archived unchanged

---

# 0. Revision trigger

B21 produced a correctness counterexample in an attained `C→C→S` case.

At the same concrete state before the scheduled stop:

- prefix A is 228 s earlier;
- prefix A has charged 83 kWh cumulatively;
- prefix B is 228 s later;
- prefix B has charged 76 kWh cumulatively.

The scheduled transform contains a waiting plateau:

\[
t'=\max\{a,t+h\}+D.
\]

Both prefixes therefore reach the same scheduled completion time.

The earlier prefix's primary advantage disappears, and the later prefix wins the accepted plan key through lower cumulative charge:

\[
(44950,76,3,\pi_B)
<
_{\rm lex}
(44950,83,3,\pi_A).
\]

The frozen earliest-time-only frontier deleted B before the scheduled transform.

The frozen strict-cost dominance rule also deleted B.

Therefore the previous claims:

- T7-4 lexicographic closure of an earliest-time-only frontier;
- B2-T3 strict-cost dominance as a full-key-safe deletion rule;

are false.

This revision does not weaken the counterexample or reinterpret it as an implementation bug.

---

# 1. Root cause theorem

The scheduled-time operator:

\[
\Psi(t)=\max\{a,t+h\}+D
\]

is monotone nondecreasing:

\[
t_A\le t_B
\Rightarrow
\Psi(t_A)\le\Psi(t_B),
\]

but it is not strictly increasing.

Whenever:

\[
t_A+h\le a
\quad\text{and}\quad
t_B+h\le a,
\]

we have:

\[
\Psi(t_A)=\Psi(t_B)=a+D.
\]

Therefore:

\[
t_A<t_B
\]

does **not** imply a strict advantage in final primary objective.

The correct implication is only:

\[
\boxed{
\text{earlier prefix time}
\Rightarrow
\text{no worse future primary time under the same suffix}.
}
\]

If that weak inequality collapses to equality, the accepted secondary/tertiary tie key must still be available.

This is the precise defect in the frozen T3/T7-4 reasoning.

---

# 2. Energy-conservation identity for the secondary key

Let:

- \(E_0\) be initial trip energy;
- \(Q\) be cumulative charged energy;
- \(C_{\rm drive}\) be cumulative driving energy consumed;
- \(E\) be current battery energy.

Energy conservation gives:

\[
E=E_0+Q-C_{\rm drive}.
\]

Hence:

\[
\boxed{Q=E+\rho}
\]

where:

\[
\boxed{\rho=C_{\rm drive}-E_0}.
\]

For a fixed current energy \(E\), comparing cumulative charged energy \(Q\) is exactly equivalent to comparing \(\rho\).

Transitions are simple:

- Drive consuming \(c\): \(\rho'=\rho+c\)
- Charge: \(\rho'=\rho\)
- Schedule/waiting: \(\rho'=\rho\)

Thus the secondary charge key is exactly represented by a path-dependent but charging-allocation-independent offset \(\rho\).

---

# 3. Revised frontier object

The old frontier:

\[
\phi_{v,r,k}(E)=\text{earliest time at energy }E
\]

is insufficient before all future waiting plateaus have been eliminated.

Replace it with an exact Pareto branch set:

\[
\boxed{
\mathcal P_{v,r,k}(E)
=
\operatorname{ND}
\left\{
(t,\rho,\pi):
\text{attained prefix at }(v,E,r,k)
\right\}.
}
\]

Where:

- \(t\): prefix completion time;
- \(\rho=Q-E\): cumulative-charge offset;
- \(\pi\): deterministic prefix Site/action tuple;
- `ND`: nondominated set under the revised safe order below.

Limit-only lower-bound branches are retained separately and may not delete attained branches.

The complete exact search state remains:

\[
(v,E,r,k)
\]

plus a finite set of Pareto branches.

---

# 4. Why one branch per discrete prefix sequence is sufficient

Fix one concrete effect-labelled Site sequence.

For a fixed final energy \(E\), its cumulative driving consumption is fixed because routing semantics are deterministic.

Therefore:

\[
Q(E)=E+C_{\rm drive}-E_0=E+\rho.
\]

So for that discrete sequence, \(\rho\) is constant.

Different charging allocations along the same Site/action sequence cannot create a \(t\)-versus-\(Q\) tradeoff at fixed final energy because \(Q\) is already fixed by energy conservation.

Therefore, within one discrete prefix sequence, it remains safe to optimize only the earliest achievable time as a function of \(E\).

The missing information arises **between different discrete prefixes**, not between charging allocations of the same prefix.

This is why the corrected exact representation remains one-dimensional in continuous energy rather than becoming a general two-dimensional continuous surface.

---

# 5. Revised branch representation

Each attained branch \(b\) stores:

\[
\boxed{
b=
(I_b,t_b(E),\rho_b,\pi_b,w_b)
}
\]

where:

- \(I_b\): finite energy interval, with exact open/closed endpoints;
- \(t_b(E)\): finite piecewise-affine earliest time for this discrete prefix family;
- \(\rho_b\): constant cumulative-charge offset;
- \(\pi_b\): deterministic prefix Site/action tuple;
- \(w_b\): exact predecessor/witness rule.

At energy \(E\in I_b\):

\[
Q_b(E)=E+\rho_b.
\]

Limit-only branches additionally carry non-attainment status and never participate as executable winners.

---

# 6. Revised safe dominance theorem

Only compare attained branches at the same:

\[
(v,E,r,k).
\]

B21 R1 deliberately removes cross-energy dominance from the correctness core.

Let:

\[
A=(t_A,\rho_A,\pi_A),
\qquad
B=(t_B,\rho_B,\pi_B).
\]

Define:

\[
\boxed{A\preceq_{\rm safe}B}
\]

iff:

\[
t_A\le t_B,
\]

\[
\rho_A\le\rho_B,
\]

and, whenever:

\[
\rho_A=\rho_B,
\]

also:

\[
\pi_A\le_{\rm lex}\pi_B.
\]

At least one strict improvement is required for a nonduplicate deletion.

Equivalent charge form at fixed \(E\):

\[
t_A\le t_B,
\qquad
Q_A\le Q_B,
\]

with lexicographically no-worse prefix when \(Q_A=Q_B\).

---

# 7. Revised dominance theorem proof

## Theorem R1-D

If:

- A and B are attained prefixes;
- they share the same \((v,E,r,k)\);
- \(A\preceq_{\rm safe}B\);

then B may be deleted without changing the accepted complete plan key.

### Proof

Take any executable suffix feasible from B.

Because A has the same anchor, energy, schedule state, and stop count, A can execute the same suffix.

All future time operators in the frozen B2 domain are monotone nondecreasing in incoming absolute time:

- drive adds a constant;
- charge adds duration independent of absolute clock;
- S applies a monotone `max`;
- CS applies maxima of monotone expressions.

Therefore:

\[
T_A^{final}\le T_B^{final}.
\]

The same suffix adds the same future charging energy because A and B start the suffix with the same \(E\) and execute the same charging decisions. Hence:

\[
Q_A^{final}-Q_B^{final}
=
Q_A-Q_B
=
\rho_A-\rho_B
\le0.
\]

If final time is strictly smaller, A wins on primary objective.

If final time ties, A has no larger cumulative charge. If charge is strictly smaller, A wins on the secondary key. If charge also ties, final stop counts are equal and lexicographic prefix order is extension-safe under appending the same suffix.

Therefore A is no worse under the complete accepted key, so B may be deleted. ∎

---

# 8. Consequence for old B2-T3

The previous rule:

\[
t_A\le t_B,\qquad E_A\ge E_B,\qquad g_A<g_B
\]

is revoked as a tie-safe deletion theorem.

The counterexample proves that strict \(g\) advantage does not imply strict final-primary improvement when waiting can absorb the time gap.

B21 R1 uses only the new same-energy Pareto-safe rule.

No stronger cross-energy dominance is authorized during B21.

---

# 9. Revised merge operator

The old merge:

\[
\phi(E)=\min_i t_i(E)
\]

is revoked as the authoritative exact merge when future waiting plateaus may remain.

The exact merge keeps every attained branch that is not pointwise safely dominated.

For two branches A and B at energy \(E\), A deletes B only where:

\[
t_A(E)\le t_B(E)
\]

and:

\[
\rho_A\le\rho_B
\]

and the lex condition holds when \(\rho_A=\rho_B\).

Because \(t_A,t_B\) are finite piecewise affine, \(\rho_A,\rho_B\) are constants, and \(\pi_A,\pi_B\) are discrete branch metadata, dominance can change only at finitely many existing breakpoints and affine time intersections.

Therefore Pareto merge remains finitely representable.

---

# 10. Exact treatment of blocking counterexample

At Site 3, \(E=48\):

\[
A:(t,Q)=(22260,83),
\]

\[
B:(t,Q)=(22488,76).
\]

Neither dominates the other because:

\[
t_A<t_B
\]

but:

\[
Q_A>Q_B.
\]

Therefore both survive the revised merge.

After the schedule plateau, both yield:

\[
J=44950.
\]

Then B wins because:

\[
76<83.
\]

The revised representation returns:

\[
\boxed{
(44950,76,3,\pi_B).
}
\]

No fixture-specific special case is required.

---

# 11. Closure under Drive

For branch:

\[
(I,t(E),\rho,\pi),
\]

a drive leg of time \(T\) and energy \(c\) gives:

\[
E'=E-c,
\]

\[
t'(E')=t(E'+c)+T,
\]

\[
\boxed{\rho'=\rho+c}.
\]

The branch remains finite piecewise affine.

---

# 12. Closure under S

For a branch:

\[
t'(E)=\max\{a,t(E)+h\}+D,
\]

subject to the hard window, and:

\[
\rho'=\rho.
\]

This transform may collapse time differences between different branches.

That is now safe because branches are transformed individually before Pareto merge.

---

# 13. Closure under C

For one predecessor branch with constant \(\rho\), exact charging to departure energy \(E_d\) satisfies:

\[
Q'(E_d)=E_d+\rho.
\]

Thus all feasible predecessor arrival energies leading to the same \(E_d\) have the same cumulative secondary charge within that branch.

It is therefore safe within that branch to minimize time over:

\[
E_a<E_d.
\]

The strict-prefix piecewise-affine charging transform remains valid branchwise.

The output retains:

\[
\boxed{\rho'=\rho}.
\]

Different predecessor branches are then Pareto-merged rather than earliest-time-merged.

---

# 14. Closure under CS

The same argument applies to CS.

Within one predecessor branch and fixed \(E_d\):

\[
Q'(E_d)=E_d+\rho.
\]

Therefore the CS operator may minimize completion time over feasible \(E_a<E_d\) inside that branch while preserving \(\rho\).

Different predecessor branches are transformed separately and then Pareto-merged.

Strict-positive attainment handling remains required.

---

# 15. Limit-only branches

The prior T7 distinction remains:

- attained branches can produce executable plans;
- limit-only branches are lower-bound objects only.

A limit-only branch may not delete an attained branch merely because its infimal \((t,\rho)\) is better.

Executable Pareto merge is performed among attained branches.

Limit-only lower-bound envelopes are maintained separately for branch-and-bound certification.

---

# 16. Revised T7-4 theorem

Replace old T7-4 with:

\[
\boxed{
\textbf{T7-4R — finite lexicographic Pareto-branch closure}
}
\]

Under finite stop depth and finite Site/action branching:

1. every discrete prefix family produces finite PWA time pieces;
2. its cumulative-charge offset \(\rho\) is constant;
3. Drive/C/S/CS transform each branch into finitely many PWA branches;
4. pairwise safe-dominance relations change only at finitely many energy breakpoints/intersections;
5. exact Pareto merge therefore remains finite;
6. executable witness metadata remains attached to every surviving branch.

Hence the exact accepted key remains finitely representable without an SOC grid.

Old T7-4 is:

\[
\boxed{\textbf{REVOKED}}.
\]

T7-4R is accepted for B21 validation, not yet experimentally validated.

---

# 17. Revised branch-and-bound tie rule

A primary-only prune rule:

\[
L_J\ge U_J
\]

is unsafe for complete-key exactness.

If:

\[
L_J=U_J,
\]

the node may contain a plan with equal primary objective but lower cumulative charge or a better Site/action tuple.

Therefore B21 R1 freezes:

\[
\boxed{
L_J>U_J
\Rightarrow
\text{safe primary prune}.
}
\]

At equality, keep the node unless a separately proved secondary/tie lower bound certifies its complete key cannot beat the incumbent.

B21 R1 does not require such a secondary Region bound.

---

# 18. Revised OPEN termination

With only a primary lower bound, exact full-key termination is safe when:

\[
\boxed{
\min_{n\in OPEN}L_J(n)>U_J.
}
\]

If:

\[
\min L_J=U_J,
\]

equal-primary continuations remain live unless a full-key certificate resolves them.

This is required even though HIER-F had not yet run in the blocking attempt.

---

# 19. What remains valid

The counterexample does not invalidate:

- T1 physical state sufficiency;
- effect-labelled C/S/CS actions;
- strict \(q>0\);
- branchwise continuous PWA charging transforms;
- attained vs limit-only semantics;
- independent exact REF design;
- finite-depth reasoning from a verified incumbent;
- the frozen hierarchy;
- B1-D2.

The repair is localized to:

\[
\boxed{
\text{frontier merge}
+
\text{state dominance}
+
\text{equal-primary pruning/termination}.
}
\]

---

# 20. Revised B21 correctness obligations

Before B21 may pass Stage A:

## R1-G2 — operator/Pareto exactness

Branchwise Drive/C/S/CS plus Pareto merge must match REF.

## R1-G4 — complete-key exactness

Exact agreement on:

\[
(J,Q,H,\pi).
\]

## R1-G6 — revised dominance safety

Compare dominance disabled vs revised Pareto-safe dominance enabled.

Required mismatches:

\[
0.
\]

The obsolete strict-\(g\) rule is prohibited.

## R1-G8/R1-G9 — tie-safe hierarchy

Primary Region pruning must be strict at equality unless a complete-key lower bound exists.

HIER-F must match REF on full key.

---

# 21. Mandatory regression

The blocking counterexample becomes permanent.

Required exact result:

\[
J=44950\ {\rm s},
\]

\[
Q=76\ {\rm kWh},
\]

\[
H=3,
\]

\[
\pi=
(Site\ 2,C)
\rightarrow
(Site\ 3,C)
\rightarrow
(Site\ 4,S).
\]

Returning 83 kWh at the same primary objective fails the revised contract.

Do not weaken the regression to primary-objective equality only.

---

# 22. Additional mandatory regressions

Before Stage B add explicit cases for:

1. earlier/higher-Q vs later/lower-Q before a full schedule plateau;
2. partial waiting-gap collapse;
3. no plateau, where earlier time remains strictly better;
4. equal time / unequal Q;
5. equal time / equal Q / different tuple;
6. Region lower bound exactly equal to incumbent primary while containing a better secondary key.

These directly stress the revised theorem.

---

# 23. Provenance

The current blocked B21 run must remain permanently archived as:

\[
\boxed{
\textbf{B21 attempt — correctness counterexample under frozen T3/T7-4}.
}
\]

Do not overwrite its:

- report;
- acceptance record;
- failed logs/XML;
- counterexample fixture;
- REF certificates;
- operator traces;
- dominance witness.

This revision must receive its own hash.

After acceptance, amend the B21 protocol and Codex prompt explicitly.

Do not silently resume under the old protocol.

---

# 24. Resume gate

B21 implementation may resume only after:

1. this theory revision is accepted;
2. B2/T7 authority chain explicitly supersedes old T3/T7-4;
3. B21 protocol is revised;
4. B21 Codex prompt is revised;
5. blocking counterexample is a mandatory regression;
6. pre-tests and preservation pass again.

Then restart Stage A from the beginning.

Do not continue from Stage A case 16.

---

# 25. Research interpretation

This is a genuine correctness discovery, but it does not falsify the multi-stop research direction.

It falsifies the compression claim:

\[
\boxed{
\text{earliest time alone is sufficient frontier information before future waiting plateaus}.
}
\]

The corrected exact claim is:

\[
\boxed{
\text{retain the Pareto tradeoff between prefix time and cumulative charge/tie metadata}.
}
\]

The continuous state remains finitely representable because:

- final energy remains the only continuous frontier coordinate;
- cumulative charge at fixed energy is encoded by branch constant \(\rho\);
- each discrete prefix family contributes finite PWA time pieces;
- finite-depth search has finitely many discrete prefix families.

The cost of the repair is potentially more frontier branches, not a retreat from exact to approximate planning.

---

# 26. Decision

Current B21 status remains:

\[
\boxed{\textbf{BLOCKED}}.
\]

The proposed repair is:

\[
\boxed{
\textbf{replace earliest-time-only frontier compression by exact Pareto branch compression over }(t,\rho,\pi)
}
\]

and:

\[
\boxed{
\textbf{replace strict-cost dominance by same-state Pareto-safe full-key dominance}.
}
\]

The hierarchy also uses strict primary pruning at equality unless a full-key certificate exists.

No B2-2 work is authorized.
