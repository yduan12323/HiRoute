# Exact energy-wide PWA operator design v2

Design freeze: 2026-10-06. Parent checkpoint: `49b5d182bdc58a7b2869e66f23c1b05c16a2a071`.

This design extends the [bounded foundation](MILESTONE_5_TIME_CUT_FOUNDATION_REPORT_V2.md) under the conditional H1–H8 in the [proof review](MILESTONE_5_TIME_CUT_THEORY_REVIEW_V2.md). It does not authorize production acceptance, replace the missing original v0 fixture, or implement an independent physical REF.

## 1. Public representation and API

`CutPiece` contains:

- exact bounded `Interval`, with explicit open/closed endpoints and supported singleton cells;
- affine `tau(E)=slope*E+intercept`;
- constant boolean chi, constant rational rho, discrete pi and State;
- a persistent predecessor-witness callback, with `at(E)->Cut` using the existing constructive interface.

`CutPiece.from_affine(AffineFamily)` preserves an explicitly assumed analytic seed. A frontier is a finite tuple of pieces. A piece never changes the meaning of its predecessor merely by being restricted to a smaller energy domain.

Planned signatures in `src/timecut5/pwa.py`:

```python
charge_pwa(pieces, curve, overhead, site) -> tuple[CutPiece, ...]
combined_pwa(pieces, curve, site, a, b, duration, overhead) -> tuple[CutPiece, ...]
schedule_pwa(pieces, site, a, b, duration, overhead) -> tuple[CutPiece, ...]
drive_pwa(pieces, anchor, duration, consumption, floor=0) -> tuple[CutPiece, ...]
lower_envelope(pieces) -> tuple[CutPiece, ...]
reduce_frontier(pieces) -> tuple[CutPiece, ...]
```

C/CS/S and `lower_envelope` act on pieces of one `(State,rho,pi)` family. Multi-prefix propagation applies them familywise. `reduce_frontier` compares branches only at one identical `(v,r,k)` state and exact E. Drive preserves each family's pi and translates energy/rho. No cross-state or cross-energy dominance is introduced.

There is no implicit time or charging cap. Physical energy limits come from supplied input domains, charging primitive capacity and drive floors. Stop overhead is positive; service duration and drive costs are nonnegative. Capability and concrete route validation remain the caller's responsibility.

## 2. Exact budget epigraphs

The variables are `(x,t,y,u)=(Ea,input time budget,Ed,output time budget)`.

For one input piece, include x in its exact energy domain and:

`t >= slope*x + intercept`, strict iff chi is false.

This is the **budget upper closure** of the input family, not a declaration that every t is physically executable. Every feasible t must later be lifted by the inherited predecessor's `realize_le(t)`.

For C, intersect x/y with their selected exact charging segments and add:

- `x<y`;
- `u>=t+h+F_out(y)-F_in(x)`.

For CS, also require a<=b and add:

- `t<=b-h`;
- `u>=a+D`;
- `u>=t+h+D`.

These three output inequalities exactly encode the max makespan budget. No max-equality branch enumeration is needed. Only charging energy regimes are split.

For S use the schedule constraints, input epigraph, and x=y, without the strict charging inequality or charging term.

The projection is exact because actual temporal transitions are monotone and guards are downward closed: any feasible input budget can be replaced by a real predecessor no later than that budget, preserving all guards and obtaining output no later than u. Conversely every physical output supplies a feasible budget assignment.

## 3. Strict Fourier–Motzkin elimination

Use an immutable rational row `(coefficients,rhs,strict)` meaning `coefficients·variables <= rhs`, or `< rhs` when strict. Eliminate t, then x. Retain every pre-elimination row system for witness back-substitution.

At an eliminated variable:

- classify coefficients as negative, zero or positive using exact arithmetic;
- preserve all zero-coefficient rows;
- combine every lower row (negative coefficient) with every upper row (positive coefficient) using positive multipliers that cancel the variable;
- the combined row is strict iff either parent is strict;
- if one sign is absent, generate no pairs, while retaining the original rows in the reconstruction record;
- normalize by positive factors only;
- remove true constant rows; a false constant row (`0<=b` with b<0, or `0<b` with b<=0) makes this conjunction empty.

Exact duplicate rows can be combined by retaining stricter constraints. No heuristic cap or dropped inequality is allowed. Any complexity reduction needs a separate exact redundancy proof.

After projection, only y/u coefficients remain. Since input rows have no positive u coefficient and elimination uses positive combinations, every surviving u coefficient must be nonpositive. A positive u coefficient is an invariant failure, not a row to ignore.

## 4. Extract exact PWA cuts

Each projected conjunction consists of:

- energy-only inequalities, defining one possibly empty bounded interval with exact endpoint flags;
- lower-budget inequalities `u>=l_i(y)` or `u>l_i(y)`.

Its lower boundary is `tau(y)=max_i l_i(y)`. At a feasible y, chi is true iff every active maximum row is weak. A strict inactive row does not make the optimum open.

Partition y at all domain endpoints and pairwise affine intersections. Every included endpoint is a singleton cell; every nonempty interval between consecutive knots is an open cell. A rational interior point selects an analytic arrangement cell's fixed ordering; it is not an SOC grid or an approximation.

Within one discrete prefix, union all charging/input regimes by selecting minimum tau at each exact cell and OR-ing chi across **all** tied minimum regimes. Select an attained witness source when that OR is true. Source regimes may have different open endpoints even when tau agrees.

No initial coalescing is required. Future coalescing must preserve piecewise predecessor dispatch and singleton chi differences.

## 5. Constructive witnesses

For a closed output cut at y, set u=tau(y). For an open cut approached with epsilon>0, set `u=tau(y)+epsilon/2`, so a <=u witness satisfies the strict approach contract.

Reverse elimination, first selecting x then t. For each fiber:

- compute exact maximum lower bound and minimum upper bound;
- if lower<upper, choose their rational midpoint;
- if equal, select the endpoint only when all active lower and upper bounds are weak;
- with one finite bound, choose it when allowed, or a rational point strictly beyond it;
- with neither bound choose zero.

The chosen point must satisfy every original row, including strict rows. Then call the selected inherited piece's `at(x).realize_le(t)`, and replay the actual C/S/CS equation from that witness. Never return t as an executed time merely because projection selected it.

Closed outputs must replay exactly to tau. Open outputs must replay strictly above tau and at most the selected budget. Every C/CS witness must satisfy x<y, physical energy limits and all schedule guards.

The callback/DAG retains all intermediate-energy and predecessor-subfamily restrictions from reductions. Removed frontier entries remain reachable if a surviving witness depends on them; an unrestricted re-solve of the original prefix is not an acceptable substitute.

## 6. Whole-domain reduction

Take the exact arrangement of all candidate domains and tau intersections. On each cell, retain the antichain under the existing same-state time-cut/rho/pi preorder. Equal-value endpoints and changes in chi are evaluated as singleton cells. Earlier but higher-rho branches remain incomparable until a later operation truly removes the time advantage.

Canonical output ordering is deterministic; semantic equivalence is mutual coverage under the sufficient preorder, not identical segmentation or chosen continuous witnesses. The old v1 equality assertion remains unchanged.

## 7. Independent acceptance for this bounded extension

An independently authored oracle must not call the production projection, PWA envelope or reduction implementation. It should enumerate exact rational physical/budget regimes and certify each symbolic output cell and endpoint, with strict feasibility separated from closed relaxation.

Required tests include:

- strict FM pairing, one-sided fibers, contradictory zero rows, endpoint ties and rational back-substitution;
- analytic full-energy v1 A/B C outputs, open charge limits, charging kinks, tied attaining regimes;
- CS plateau interiors/boundaries, energy-dependent charging bottlenecks, latest-start equality and empty open faces;
- domain restriction and inherited witness replay after Drive/S/C/CS compositions;
- exact union and reduction on open intervals and isolated endpoints, rho/pi ties and reduction-before/after continuation coverage;
- arbitrarily small approach budgets and positive charging without a fixed quantum;
- terminal primary/secondary face compatibility and the separately labeled v0 analytic prefix reconstruction.

Finite sampled points alone cannot certify a symbolic cell. Report exact cell coverage separately from generated witness probes. Independent physical REF, original v0 regression and full solver acceptance remain later gates even if every bounded PWA operator test passes.
