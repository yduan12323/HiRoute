# Certified onward ALT tightening (opt-in)

`TableFreeRegionBoundProvider(..., onward_alt=True)` adds the same directed
onward-time relaxation to FLAT singleton and HIER Region bounds. The default is
False: no new extrema scans, altered default arithmetic, CLI, production policy,
existing result files, or pruning rules. This is a provider-level experimental
switch; a caller must explicitly select it for both arms. No large-graph result
or speedup is claimed.

## Certificate and arithmetic proof

Reuse `certify_integer_landmark` on the same authenticated graph/anchor catalog.
For each finite positive binary64 road time w, set c =
max(0, floor(nextafter(w, -infinity))). Thus c is a nonnegative integer <= w.
The certificate audits original directed edges for forward potential F and
reverse potential T: F(v) <= F(u)+c(u,v) and T(u) <= c(u,v)+T(v), whenever the
relevant antecedent is finite, including finite reachability closure. Finite
labels and audited sums lie below 2^53. No selected-fastest distance/length is
used: those lengths need not obey a triangle inequality.

Importantly, native road-leg time is a left-to-right binary64 sum, not the exact
sum of real edge times. Let C_i be the mathematical integer sum of conservative
weights through edge i and r_i the native floating accumulator starting at zero.
Inductively r_i >= min(C_i, 2^53): if the previous C is below 2^53, the unrounded
addition is at least C_previous+c; if this remains below 2^53, that integer is
exactly representable and monotonic correctly rounded addition cannot fall
below it. If it crosses 2^53, monotonic rounding cannot fall below the exactly
representable 2^53 threshold. Once the accumulator reaches that threshold,
nonnegative additions cannot reduce it. Overflow is no counterexample. Therefore
any certified nonnegative potential difference (<2^53), which is <= C_i by
edge telescoping, is <= the actual native leg total. This does not assume exact
native path accumulation and accommodates discarded sub-ULP increments.

For a physical anchor x and destination D, each finite difference F(D)-F(x)
and T(x)-T(D) lower-bounds a selected leg, whether or not it is a shortest path.
For arbitrary sequences of selected legs through intermediate Sites, finite
reachability closure propagates along the sequence and differences telescope.
Each leg's binary64 total is converted to an exact Fraction before planning;
thus their exact sum still dominates the telescoped difference. Additional
service, charging, waiting, and future stop penalties are nonnegative. Hence
max(0, F(D)-F(x), T(x)-T(D)) is a lower bound for every completion from x,
not only the direct selected leg x->D. Skip each term independently if either
operand is nonfinite; never infer unreachability from absent potentials.

For a complete Region R, use

    O(R) = max(0, F(D) - max(x in R) F(x), min(x in R) T(x) - T(D)).

Every retained term lower-bounds every member's completion, so O(R) <= its
minimum onward time. Extrema cover all members including action-ineligible
members, aliases and destination members. This may weaken but never strengthens
incorrectly. Incoming and outgoing minima can occur at different members; their
sum still lower-bounds each individual member's sum. Service is evaluated first:

    t = infimum(prefix time) + incoming(R) + overhead
    if effect in {S, CS}: t = max(schedule start, t) + schedule duration
    lower primary = t + O(R) - query start + penalty * (stops + 1)

The same formula with singleton extrema is used for FLAT. Strict charging time
is relaxed to zero; schedule service is included once (CS overlap retained).
Empty candidate masks return no bound, empty pieces return no bound; an empty
Region cannot reach the extrema path. Same-anchor differences are zero. Distinct
Site identities at the same physical anchor retain distinct action bits.

## Binding, strategies, and pruning

Opt-in calls verify destination, Site-catalog digest and the complete selected-
leg source binding against the construction-time snapshot. Separate FLAT/HIER
providers with the same bindings are accepted. Existing immutability and
byte-verification preconditions for graph arrays, routers, Sites, and certified
landmarks still apply. This is not a replacement for launcher certificate
admission or provenance checks.

Indexed mode builds complete-Region max-F/min-T extrema during setup; online
queries access no members. Recompute builds no outgoing summaries and performs
two complete member passes per outgoing query, without memoization or action-mask
scans. The optional member-read count includes those two passes (four total for
an active Region bound); a partial failure invalidates the count. Original
incoming methods and default-off behavior are unchanged.

Both solvers retain their strict `lower > upper` pruning comparison. Equal
primary bounds stay live to preserve secondary/lexicographic optima. The tests
inject a proven optimum as an equal candidate bound and verify both engines
expand candidates; HIER explicitly records equality nodes retained.

## Targeted validation

Run from repository root with Python 3.11 and dependencies installed:

    PYTHONPATH=src python -m unittest discover -s tests/m5d_recovery -p test_onward_alt.py
    PYTHONPATH=src python -OO -m unittest discover -s tests/m5d_recovery -p test_onward_alt.py

Tests use unittest checks (not removable assert statements): asymmetric/
nonfinite potentials, alias/same-anchor/empty cases, waiting and C/S/CS service,
wrong bindings, indexed/recompute scan isolation and failure accounting,
all anchor walks with up to two intermediate anchors, fractional times and
nonmetric fastest-path lengths, FLAT/HIER exact optimum equivalence across both
strategies and switches, and equality survival. These are synthetic functional
checks, not a certification of a new production or performance row.
