# Experimental exact charge/count lower bound

This is a conditional mathematical helper, not a live search integration or a
runtime certificate. It does not route, authenticate suffix potentials, load
native artifacts, realize witnesses, prune frontiers, or change the declared
Hmax. It makes no completeness, optimality, acceptance or speedup claim.

Implementation: `src/timecut5/charge_count_bound.py`.
Synthetic unit tests: `tests/test_charge_count_bound.py`.

## Explicit curve admission

Call `admit_shared_convex_curve(curve, minimum_energy=..., capacity=...)`
before calling `charge_count_primary_lower_bound`. Physical quantities must be
exact `Fraction` objects. Counts must be exact nonnegative integers, not bools.
The existing `ChargingCurve` model supplies continuous positive-slope rational
PWA rows. The new admission explicitly verifies exact rows, continuity,
coverage of the usable interval [Emin,C], and nondecreasing slopes on that
interval. Existing `ChargingCurve` validation alone does not require convexity.

The returned frozen `SharedConvexCurveAdmissionV1` stores an immutable row
snapshot. It verifies mathematical properties only. The caller must establish
that the snapshot is the shared charging primitive actually used by **every**
future charge of the same live physical query. It does not authenticate that
relationship, query lineage, object ownership, source code or arithmetic
history. A changed live curve must not continue using an old snapshot without
reestablishing that external relationship.

Admission is `active` when the checks pass. A missing curve or a continuous
positive-slope but nonconvex usable curve gives `unsupported`, with a reason
and no active rows. This does not establish infeasibility. Malformed types or
invalid physical rows raise errors. Emin=C is allowed and has zero usable
charging capacity. Convexity outside the usable interval is unnecessary.

## Required external contracts

For a trusted frontier piece with energy e, affine lower clock tau(e), current
stop count k and pending-schedule flag r, independently establish:

1. Every represented executable prefix has clock at least tau(e), and belongs
   to this same physical query and same discrete state.
2. `remaining_energy_lower` is a certified lower bound on **total** future
   selected-leg energy consumption to the destination, including every
   multi-leg/native-label reset and rounding requirement. Conservation gives
   future charge Q >= reserve + suffix_energy_lower - e. No unsupported free
   energy is introduced. This helper cannot validate a road potential.
3. `remaining_time_lower` bounds total future selected-leg driving time.
   Driving and charging are disjoint in elapsed time.
4. Every charge from a to a+x has Emin <= a <= a+x <= C and duration
   F(a+x)-F(a), using the admitted shared primitive.
5. Every future semantic stop pays `stop_overhead` separately before
   charge/service and adds `stop_penalty` to the primary objective. Overhead
   is positive and penalty nonnegative. Charge may overlap scheduled service
   or waiting; the bound adds no service or waiting duration.
6. `original_hmax` is the unchanged declared maximum total semantic-stop
   count. A nonzero `minimum_future_stops` must be a separately justified
   condition on the continuation being bounded. For example, a bound
   conditional on taking a next stop can use one. It is not a heuristic
   threshold or permission to change Hmax.

The syntax checks and model classes do not prove any of these external
contracts. A future runtime would still need its existing same-live-query,
source/native/FP/cache-history, certified-potential and trusted-frontier guards.
This helper does not replace or modify them.

## Relaxation and proof

Write W=C-Emin, A=reserve+suffix_energy_lower,
q(e)=max(0,A-e), and delta=overhead+penalty. Enumerate **every** integer future
stop count h in

    max(r, minimum_future_stops) <= h <= original_hmax-k.

Actual S-only stops are also treated as charge-capable, with zero charge
allowed. This is a relaxation. h denotes the total number of paid future
semantic stops, not a maximum number of available charging slots.

For h>0 and q<=hW, define

    Lh(q) = h * [F(Emin+q/h)-F(Emin)] + h*delta.

Exclude h when q>hW. For h=0 define L0(0)=0 and exclude positive q.

Consider any actual completion with h future paid stops. Give its stops charge
amounts xi>=0, including xi=0 for noncharging stops. Their total is Q>=q, and
each xi<=W, so Q<=hW. Convexity makes fixed-width increments nondecreasing
with arrival energy. Therefore

    F(ai+xi)-F(ai) >= F(Emin+xi)-F(Emin).

Jensen's inequality and monotonicity of F then give

    sum actual charge durations
      >= sum [F(Emin+xi)-F(Emin)]
      >= h * [F(Emin+Q/h)-F(Emin)]
      >= h * [F(Emin+q/h)-F(Emin)].

Every future stop's elapsed time is at least overhead+charge_duration, even
when charge overlaps service. Its stop penalty is a separate primary cost.
Adding h*delta is therefore sound. For h=0, conservation requires q=0.
The actual count is in the enumerated domain, so minimizing over counts and
represented energies can only lower this complete primary objective:

    min over piece,e,h [tau_piece(e)+Lh(q(e))]
      + suffix_time_lower - start_time + k*stop_penalty.

Past elapsed time already contains past charging, overhead, service and
waiting. The formula adds past penalties once and future overhead/penalties
once. It does not change the secondary conservation coordinate, prefix,
attainment flag or reconstruction callback.

## Exact interval infimum

For each piece and h, first intersect its **actual flagged interval** with
e>=A-hW. For h=0 this is e>=A. Skip an empty intersection, including a singleton
whose endpoint is excluded. Only after this emptiness check take its closure
for infimum evaluation.

On that closure evaluate both interval endpoints, the hinge e=A if present,
and every transformed charging breakpoint

    e = A-h*(x-Emin)

that lies in the closure, where x is a breakpoint of F within [Emin,C]. Between
these candidates the expression is affine, so the smallest candidate value is
the exact infimum for the piece/count. Minimize these values over all pieces
and all allowed counts. Stored F-breakpoint increments avoid a segment scan
per breakpoint. The arithmetic operation count is
O(pieces * allowed_counts * curve_segments), with no energy grid or routing.

An excluded energy endpoint can supply an unattained infimum. An open clock
face has the same lower clock value. Neither is turned into an executable
witness or an attained optimum. The result contains no witness or attainment
field and never calls a frontier reconstruction callback.

## Result states and safe composition

`ChargeCountBoundResultV1` always records the supplied `original_hmax`:

- `active`: `primary_lower_bound` is an exact Fraction infimum.
- `unsupported`: no convex model was admitted; the lower value is None.
- `infeasible`: the admitted conditional relaxation has no legal future count
  or no nonempty energy/count domain; the lower value is None. This is
  conditional on the caller's external contracts, including a justified
  minimum future count. It is not the same as unsupported.

Combine this complete bound with other complete primary bounds by **max**,
not addition. In particular, never add a separate complete schedule bound to
the charge bound: CS can overlap those durations. This module performs no
comparison with an incumbent. Any later pruning must use strict `>` against
an independently verified feasible primary upper bound and retain equality
for secondary/prefix competitors. No Hmax or prefix domain is rewritten.

## Counterexamples and limitations

- Nonconvex F can overestimate: slope 10 on [0,1] followed continuously by
  slope 1 on [1,2] gives a one-unit charge from energy 1 duration 1, but the
  Emin=0 increment is 10. Such a usable curve is unsupported.
- The count cost is not monotone. For the shared 36/60/120-slope curve with
  breakpoints 0,30,48,60, delta=900 and q=60, h=1,2,3 cost 4500,3960,4860
  seconds. Selecting either count endpoint can overestimate a valid
  intermediate-count completion.
- Charging all available slots' overhead can overestimate a continuation that
  uses fewer paid stops. Only minimization over a count domain containing the
  actual count is justified.
- A faster heterogeneous charging site invalidates an unverified shared F.
- A 10-second charge overlapping a 10-second service with one-second overhead
  takes 11 seconds. Adding both durations would incorrectly claim 21 seconds.

Resetting every future charge to Emin and allowing every stop to charge are
deliberately optimistic. Prior scoped DEV arithmetic found only modest
additional convexity gain beyond capacity-implied stop cost at the OD02
origin. This helper remains experimental pending any separately declared
profiling; no real graph, holdout evaluation or runtime improvement is claimed.

## Pure test scope

Run from the repository root with an existing Python and no installation:

    PYTHONPATH=src taskset -c 2 python -m unittest discover -s tests -p test_charge_count_bound.py -v
    PYTHONPATH=src taskset -c 2 python -OO -m unittest discover -s tests -p test_charge_count_bound.py -v

The tests use unittest checks that remain active under optimization. Coverage
includes nonconvex admission, exact input validation, open and empty flagged
domains, capacity equality, h=0, pending service, justified count conditions,
past costs, nonzero and degenerate usable intervals, callback non-use, charge
allocations, and 5,400 systematic fixed-count plus 300 randomized rational
cases against an independently constructed epigraph-LP vertex oracle.
Existing global-linear lower bounds
are also checked for domination on those feasible randomized cases. These are
code-only synthetic checks, not live certificate authentication or a project
acceptance result.
