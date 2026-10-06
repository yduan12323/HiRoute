# Milestone 5: constructive lower-time-cut contract v2

Version: 2.0, 2026-10-06. Status: **bounded theorem-probe contract; production gate remains closed**.

This is a new, explicit semantic contract. It does not change the historical B21-v0 or B21-v1 contracts, tests, or failure reports. Passing the new probe is not acceptance of B21, REF, FLAT, or HIER.

## 1. Authority and bounded implementation

The user-supplied latest research documents are preserved byte-for-byte under `docs/time_cut_v2_authority/`:

| Document | SHA-256 |
|---|---|
| `HIROUTE_RESEARCH_MASTER_PLAN.md` | `f191e16d6ba1d3cbde059a06522d6a38da867f4ebdd54f531baa1928b01c174b` |
| `HIROUTE_FORMAL_SPEC.md` | `1eddd50e5fd3f51841fa0c1f607b180aefde3b5e0a229b5c09de00f214e8f827` |
| `HIROUTE_COLLABORATOR_BRIEF.md` | `9e150abc351353e6004be2e335ec28cdc97991df058cab7916b15f49234a2ff2` |

The implementation in `src/timecut5/probe.py` covers:

- Rational fixed-energy cuts and constructive replay/approach witnesses.
- Finite pointwise reduction at identical `(v,E,r,k)`.
- Point Drive, S, C, and fixed-`Ea,Ed` CS.
- Exact C infimum at one chosen output energy from a finite union of affine input pieces of one fixed discrete prefix.
- Sequential terminal J/Q attainment over a finite union of affine terminal seed families.

It does **not** implement general output-energy PWA C/CS propagation, branch splitting/reduction over whole energy intervals, a route enumerator, independent REF, FLAT, HIER, or a production solver. No small test population establishes a universal theorem.

All executable arithmetic uses `fractions.Fraction`; binary64 inputs are rejected. An output energy in a theorem probe is an exact evaluation point, not an SOC discretization. The approach budget is supplied on demand and may be arbitrarily small; it is not a minimum charge quantum.

## 2. Semantics: continuation budgets, not stored attained minima

For a nonempty executable time family T with finite lower bound, define `tau=inf(T)` and `chi=(tau in T)`. Its continuation-budget upper closure is

`U(T) = {u : there exists t in T with t <= u}`.

Thus `U(T)=[tau,infinity)` if chi is true, and `(tau,infinity)` otherwise. This is not a claim that all values in U(T) are executable completion times. No extra free-wait action is added.

The time preorder A <= B means `U(B) subset U(A)`, equivalently:

- `tau_A < tau_B`; or
- `tau_A == tau_B` and `(chi_A or not chi_B)`.

The constructive meaning is: for every real executable B completion, reconstruct an A completion no later than it. Equal-time open A cannot dominate closed B. Earlier open A can dominate a later closed B when the other full-key conditions hold.

At identical `(v,E,r,k)`, require additionally `rho_A <= rho_B`; if rho is equal require `pi_A <=lex pi_B`. The conservation coordinate is `rho=Q-E`. No cross-energy or cross-state comparison is authorized. Earlier time with larger rho does not suffice.

For finite point families the probe's equivalence comparator certifies mutual coverage under this sufficient preorder. It is not a complete decision procedure for every possible semantic continuation equivalence. It does not compare the explicit attained-record sets, arbitrary chosen witnesses, or serialization/segmentation. This is a changed versioned obligation relative to v1 ALG-4, not a reinterpretation of that old assertion.

## 3. Constructive witness interface

Every represented nonempty cut carries executable reconstruction information:

- `minimum()` returns a witness at tau only when chi is true; otherwise it raises `UnattainedError`.
- `approach(epsilon)`, epsilon>0, returns a witness with `tau <= t < tau+epsilon`. For an open cut the inequality at tau is strict. For a closed cut this implementation returns its minimum.
- `realize_le(u)` returns a witness no later than u iff `tau<u`, or `tau==u` and chi is true.

A witness records actual time, energy, rho, discrete prefix/state, and predecessor/action events. Charging replay always satisfies `Ed>Ea`. The infimum 1336 in the v1 example is never returned as an executed time.

After future pointwise energy-domain reduction, a witness must retain every inherited restriction on intermediate energies and predecessor subfamilies. Solving an unrestricted original prefix is insufficient: it could produce a physically valid prefix outside the represented branch and even below that branch's claimed tau. The current predecessor callbacks retain their chosen analytic seed domain.

`AffineFamily` is a deliberately explicit analytic seed assumption: at each E it represents `{tau(E)}` when closed, and `(tau(E),tau(E)+1]` when open. A seed event is labeled `analytic_seed`; it does not certify a road path or reconstruct earlier stops. Subsequent probe actions are replayed from that seed. Production input families must instead carry independently checked physical prefix reconstruction, including the selected fastest route and its actual length.

The arbitrary upper end of the analytic open seed does not alter its lower cut; all approach witnesses truly lie in the declared seed family. This bounded probe does not infer that every physical family has this interval form.

## 4. Exact operators and feasibility

These are local operator probes. The caller supplies an already selected Site and must validate arrival anchor, capability and route identity externally. Changing the output anchor label in a local stop operator is not a substitute for a drive transition in a full physical planner.

Physical destination semantics are carried forward: `MILESTONE_5_MULTISTOP_CORE_THEORY_V1.md`, Section 2, says “Destination arrival is terminal, not a semantic stop”; `MILESTONE_4R_B2_FORMAL_SPEC.md`, Section 2, likewise treats arrival as terminal unless explicitly modeled otherwise. The new cut authority does not explicitly change that rule. The bounded physical adapters therefore forbid semantic actions at the destination and departure from a current terminal anchor, including when origin equals destination. This does not introduce a stronger ban on a selected road leg merely transiting the destination internally.

### Drive

For nonnegative drive time T and energy c, map energy to `E-c`, rho to `rho+c`, tau to `tau+T`, and keep chi. Check the energy floor. Q is unchanged. Zero time/energy is allowed for an already selected self leg; this does not alter the positive-edge assumption of the route model.

### Schedule S

Assume h>0, D>=0, `r=1`. Check a<=b. First restrict actual input times to `t<=L=b-h`.

A nonempty input cut survives iff `tau<L` or (`tau==L` and chi). In particular `tau=L, chi=false` is infeasible, not a limit-feasible action.

On surviving input:

- `tau_S=max(a,tau+h)+D`
- `chi_S=chi or (tau<a-h)`

Equality at `tau=a-h` does not create attainment. A strict waiting plateau can create it. Its witness must select a real predecessor inside both the plateau and latest-start allowance, not execute tau when open.

### Charge C

At fixed output Ed, optimize only admissible input energy `Ea<Ed` inside the declared input and charging-curve domains:

`tau_C=h+F(Ed)+inf_Ea[tau(Ea)-F(Ea)]`.

Each input affine piece is intersected with every exact charging segment and the strict energy constraint. The objective is affine on each resulting interval. Its infimum is determined analytically by the slope and endpoint openness. A constant objective attains at any executable interior point even when both interval endpoints are open.

The output boundary is attained iff at least one globally minimizing regime has both an included minimizing Ea and a closed input time cut there. Tied open regimes must not hide a closed minimizer in another regime.

Otherwise construct a legal energy approaching the relevant boundary and a legal input time, splitting the requested error budget between energy-objective and input-time gaps. Every witness retains strictly positive charge. A closure point Ea=Ed is never used as a charged witness.

### Combined CS at fixed Ea,Ed

Let `d=F(Ed)-F(Ea)>0`, `M=max(d,D)`, `K=a+D`, `offset=h+M`. After the same latest-start feasibility check:

- `tau_CS=max(K,tau+offset)`
- `chi_CS=chi or (tau<K-offset)`

The witness replays concurrent charging and schedule completion. Charging may finish after b; b restricts schedule start, not stop completion. This fixed-energy result is not the theorem for minimizing over Ea. Full CS closure and its constructive optimizer remain a separate gate.

## 5. Terminal result contract

Optimize lexicographically through **attained optimal faces**:

1. Find the global primary infimum J.
2. If J is not achieved by any legal terminal plan, return `infimum_unattained`, component J. Do not report the best later attained plan or fabricate a secondary optimum.
3. On the actually attained J-optimal face, minimize Q.
4. If Q is not attained, return `infimum_unattained`, component Q, with the attained primary value and Q infimum. No full executable key or witness is returned.
5. Only when both are attained choose the minimum H, then pi, and return a valid executable witness with the complete key.

The probe demonstrates the secondary issue with a legal C(q>0)-then-S waiting construction: J=14 for all q in (0,1], but Q=q has no minimum. A primary-only status flag is insufficient.

Future REF/FLAT/HIER agreement requires the same status, attained optimum key, and independently replayable valid witnesses. It does **not** require identical continuous charging allocations: the historical v0 allocations (41,35) and (28,48) both total 76 kWh. Any extra canonical witness tie-break must be explicitly specified before it is required.

## 6. Permanent historical regressions

### v1 C closure counterexample

Use A: E in (0,1], `t=1000+60E`, rho=0; B: E=1/2, t=1031, rho=1. Both have closed input times. At Ed=1 and h=300:

- A cut: (1336, open); actual times `1336+24Ea`, Ea in (0,1).
- B cut: (1349, closed).
- A witnesses Ea=1/4 and 1/2 execute at 1342 and 1348 respectively.
- A's constructive continuation cut covers B; the explicit stored attained-record sets still differ under old v1 semantics.
- A followed by S(h=300,a=2000,b=2100,D=100) has attained minimum 2100, reconstructed through an actual noninfimal A witness.

The historical v1 ordinary failing assertion remains unchanged and should still fail when invoked under its original contract. The new passing test checks a separately named v2 continuation contract.

### v0 later/lower-charge prefix

Published prefix equations at Site 3 are `t_A(E)=20100+F(E), rho_A=35` and `t_B(E)=20328+F(E), rho_B=28`. Neither dominates the other before waiting. At E=48 and the published suffix, both end at J=44950, but Q is 83 versus 76; the 76-kWh winner must remain.

The new test is labeled an **analytic prefix reconstruction**. It chooses a tight synthetic latest start b=a=40000, which both continuations meet; it does not guess the original missing b. The clone lacks the original `hand_cases.json`, reference certificates and related ignored JSON artifacts. This test is not a rerun of the original graph fixture, full sequence enumeration, or global REF proof.

## 7. Gates before broader implementation

- Independently close SQ-1..SQ-8 with stated temporal/domain assumptions, exact open-face handling, finite PWA closure and constructive witnesses. A point probe is not this proof.
- Implement and test full C/CS output-energy partitions, isolated endpoint pieces, overlap normalization and energy-wide reduction.
- Supply physical prefix replay independently of the quotient and build an independent bounded reference oracle.
- Restore the original v0 fixture/certificates and run its actual regression without changing expectations.
- Preregister generated C/S/CS, terminal nonattainment, and reduction-before/after populations; compare REF/FLAT/HIER statuses and full attained keys.
- Only after zero mismatches proceed to hierarchy, deployable long-haul evaluation and a separately frozen holdout.

Packaging omissions, historical result-test discovery and ignored evidence files are separate reproducibility issues. This patch does not mask those issues by changing old collection rules or failure assertions.
