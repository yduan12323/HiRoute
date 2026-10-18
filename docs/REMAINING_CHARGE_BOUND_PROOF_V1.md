# Remaining charge and travel lower bounds v1

## Scope and assumptions

The selected-leg model has nonnegative consumption, no regeneration, a terminal
reserve R, and separate driving/charging periods. Every stop pays overhead h>0;
the objective is elapsed time plus lambda*H, with lambda>=0. Scheduled service
and waiting may overlap charging, but driving and stop overhead cannot.
Every legal charging primitive has slope at least alpha>0 seconds/kWh over its
entire legal domain. The current model uses one shared piecewise-affine primitive;
alpha is its minimum slope, not an assumed power rating or the next site's rate.

L_E(v) and L_T(v) must be certified lower bounds on total remaining selected-leg
energy and driving time from v to the destination. These include native binary64
arithmetic, separately accumulated legs and source/history integrity. Raw floating
shortest-distance subtraction is not a substitute for those certificates.

## Prefix inequality

For current energy e, energy conservation and terminal reserve imply future
charge q >= max(0,R+L_E(v)-e). Summing charging integrals gives charging duration
at least alpha*q. Driving cannot overlap it. Thus a represented prefix whose
clock is at least tau(e) has final primary objective at least

    tau(e) + L_T(v) + alpha*max(0,R+L_E(v)-e) - start + lambda*k,

where k is its existing stop count. Relaxed future stop costs are omitted.
Taking the infimum over all pieces and their energy intervals is valid for every
suffix of that same physical state. On each affine piece, the only candidates
are the two closure endpoints and the hinge R+L_E(v), when it is in the closure.
Open endpoints give an infimum, never an executable or attained witness.

Combine this complete objective bound with an existing complete bound using
max, not addition. In particular, adding service duration to charging duration
is unsafe: with overhead 2, charge duration 5 and service duration 10, CS can
finish at time 12, not 17. A separately justified schedule bound can be combined
by max. Pruning remains strictly above a verified incumbent primary value;
equality must preserve possible secondary-charge, stop-count and prefix ties.

## Whole-route and depth inequality

At origin energy e0, define

    B0 = L_T(origin) + alpha*max(0,R+L_E(origin)-e0).
    B(H) = B0 + H*(h+lambda).

This lower-bounds every complete route with H stops, including CS schedules.
A queued next-stop branch from a k-stop prefix has at least k+1 total stops, so
B(k+1) is an additional valid lower bound for that branch. The positive per-stop
cost makes this monotone. A diagnostic floor((U-B0)/(h+lambda)) can describe a
strict-pruning threshold, but does not rewrite the declared Hmax or candidate
domain. If it excludes the independently replayed seed's own H, admission fails.

## Certified potentials across separately rounded legs

For the energy certificate, the audited integer potential p satisfies every edge
inequality and p(destination)=0. The conservative common rounding factor beta
bounds each selected leg's rounded distance below by beta times its signed
potential difference, divided by the dyadic quantum. Nonnegative cycles can be
removed for the simple-path rounding argument. Summing leg inequalities cancels
intermediate potentials. Beta is applied once to the resulting difference, not
raised to the number of stops; separately rounded legs are never treated as one
floating accumulation. The exact nonnegative consumption rate converts distance
to energy.

The directed time certificate similarly bounds each leg by a signed integer
potential difference. Integer-label and maximum-edge limits below 2^53 support
the original rounded-path bridge; finite terms telescope, and max with zero is
admissible. Missing/nonfinite terms provide no positive bound and do not prove
unreachability. Certificate caps, all-edge audits, graph/native ownership and
rounding-history checks remain mandatory.

## Code and evidence boundaries

`remaining_charge_bound.py` implements conditional rational inequalities only.
`remaining_charge_runtime.py` admits the actual query, curve and source-bound
potentials through separately versioned accessors. Its input frontiers must be
trusted outputs of the same admitted solver problem; it does not authenticate
arbitrary caller-forged affine clocks. Disabled/unsupported results mean retain
the prior bound. Integrity drift raises rather than silently disabling a check.

The opt-in development wrapper takes max of the original region bound, prefix
bound and B(k+1), preserves original None/masks and delegates strict pruning to
the existing engine. This can also change queue ordering; timing observations
must not be attributed solely to pruning. Finite tests and this theorem do not
establish real-road completion, whole-query speedup or navigation readiness.
