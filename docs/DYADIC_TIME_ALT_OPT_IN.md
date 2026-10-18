# Optional dyadic time ALT

The default remains `time_quantum_exponent=0`, with the existing arithmetic and
byte-compatible `hiroute.m5d.integer_second_landmark.v1` evidence. The only new
supported choice is the exact integer `10`, selected explicitly on
`certify_integer_landmark` or `TableFreeRegionBoundProvider`. Booleans, floats
and other exponents are rejected. There is no automatic precision selection,
fallback downgrade, solver default change, or real-road performance claim.

For q=10, Q=1024 units/second. The certificate uses
`hiroute.m5d.dyadic_second_landmark.v2` and explicitly binds the exponent,
units-per-second and scaled quantization policy. It computes integer weights
`max(0, floor(nextafter(ldexp(original_time, 10), -infinity)))`.
Finite power-of-two scaling is exact. Original native routing still consumes
the unchanged original binary64 graph; selected paths and energy consumption
do not use these conservative weights.

## Exactness and failure behavior

Both directed all-edge audits and the strict finite-label-plus-max-edge
`< 2**53` condition remain in integer units. Invalid/nonpositive/nonfinite
original times, scaling overflow, out-of-domain integer weights, failed
labels/audits or identity drift raise. Quantized zero weights are valid, and
each unavailable ALT term is skipped independently. Neither missing terms
nor a zero bound implies unreachability.

For a certified forward potential p and edge u→v,
`p(v) <= p(u) + w(u,v)` and `w(u,v)/Q <= original_time(u,v)`.
Every relevant signed label difference divided by Q is exactly representable
in binary64 under the retained integer domain. Induction on the selected
path and round-to-nearest monotonicity keep native elapsed time above that
representable potential-difference endpoint. Negative differences are already
below nonnegative elapsed time. The reverse potential has the analogous
argument. Finite forward labels propagate from the start; finite reverse
labels propagate backward from the destination. Signed bounds telescope
across native legs whose accumulators restart at zero. This proof does not
assume an arbitrarily long path's integer sum stays below 2**53.

Existing owned-graph, native source/mode, FP/history and cache safeguards stay
in force. Full and destination-target routing share this potential contract;
no target labels enter the complete-source cache.

## Units at every consumer

Retained landmark labels and Region extrema are integers in the certificate's
declared units. Provider outputs are always exact seconds. A common checked
conversion returns `Fraction(integer_units, Q)` for indexed/recomputed Region
incoming, outgoing/onward, singleton, and certified suffix bounds. The legacy
`SameALTMemberScan` subclass uses that conversion too. The construction quantum
is pinned and its public properties are read-only; changing its live policy
cannot reinterpret numeric outputs. No float division or final floor-to-whole-
seconds conversion is used.

`certified_suffix_time_v1` keeps its v1 return API of exact seconds while
explicitly validating either the old integer v1 or new dyadic v2 evidence.
For q=10 its binding schema is `hiroute.suffix_time_potential.v2`; the pinned
construction certificate binds Q, so runtime admission cannot silently mix
units. Existing sparse-feasible launch construction remains default q=0.
External consumers of raw labels must read their certificate units rather
than treating raw integers as seconds.

Schedule arithmetic, action masks/coverage, original None behavior, Hmax and
strict `>` comparisons are unchanged. Refinement does not guarantee that
every difference of two independently recomputed landmark distances grows.
Only the forward origin-to-destination term is monotone when the landmark is
the origin. A future q=0 versus q=10 experiment must hold every other policy
fixed and measure actual B0, bounds, pruning and completed work.

Focused tests cover old payload bytes, quantum/ULP boundaries, tiny positive
times, overflow and exact-domain rejection, both edge audits, zero cycles,
missing terms, all consumer conversions, policy drift, full/target parity and
native rounding across repeated leg resets. They do not replace a controlled
real-data acceptance gate.
