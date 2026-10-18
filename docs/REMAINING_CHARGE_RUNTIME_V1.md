# Conditional remaining-charge runtime admission v1

This is an explicit, experimental API. The API itself does not run a solver,
prune a prefix or depth layer, accept an incumbent upper bound, or change Hmax.
A separately opt-in integration is defined in
[the development gate](../experiments/remaining_charge_gate_v1/README.md). Existing immediate-finish screening,
Region/onward bounds, routing defaults and verifier roles retain their APIs.

## Admission and output

Call `admit_remaining_charge_runtime(problem, energy_screen=screen,
travel_provider=bound_provider)` on an exact live `TableFreeRealProblem` with
its own activated screen. The optional travel provider must be the exact
`TableFreeRegionBoundProvider` sharing that selected-leg provider; omission
explicitly selects a zero travel relaxation.

Admission binds the actual case and live physical fields: origin/destination,
initial energy, start time, floor/capacity/reserve, consumption rate, overhead,
stop penalty, schedule state, Hmax, actual Site/effect/anchor catalog, the exact
shared charging curve and its global minimum integral slope. It also binds
the graph, provider, router mode and artifact, energy artifact, complete
guarded arithmetic history, source hashes, native owners and cache policy.
The runtime pins the live curve and leg-adapter owners. Replacing even an
equal curve requires fresh admission.

`evaluate_group(pieces)` returns `RemainingChargeBoundResultV1` with `status`,
`primary_lower_bound` and `binding_sha256`. `whole_route_lower_bound(H)` returns
the conditional fixed-H complete-route bound, for H within the original Hmax.
`binding` is a detached receipt. It cannot restore or authorize another runtime.

All pieces must have the same complete physical State, including remaining
schedule and stop count. Energy domains must stay within the actual physical
domain. Runtime and certificate bindings are rechecked on every evaluation.
These checks perform no road routing or graph-sized scan. Validation cost is
O(anchors + Sites + curve segments + pieces), apart from exact-number costs.

## The trusted-frontier limitation

The caller must pass trusted live solver-produced frontiers from this same
problem. `CutPiece` does not itself carry authenticated query/clock lineage.
The runtime validates syntax, state, physical model, native history and road
potentials. It does **not** certify arbitrary caller-created affine clocks or
their callbacks, prove a frontier was reachable, or create a feasible witness.
This limitation is explicit in the runtime receipt.

## Separately versioned potential accessors

`screen.certified_suffix_energy_v1(problem, anchor)` derives its result from
the pinned, edge-audited integer certificate, with the common conservative
binary64 beta factor and actual consumption rate. It never reads the private
immediate-finish lower-bound map. Signed per-leg potential differences
telescope across selected legs even when each native length accumulation
restarts; beta is not exponentiated by stop count. The existing artifact's
immediate-finish use remains unchanged; this v1 runtime supplies the separate
multi-leg interpretation and binding.

`bound_provider.certified_suffix_time_v1(problem, anchor)` checks the original
integer-landmark certificate, matching routing source, retained labels and
same guarded provider. Its directed ALT differences bound total future travel;
missing/nonfinite terms contribute zero and are not unreachability claims.
Both accessors return a typed `SuffixPotentialV1` and accept full or
destination-target search history under the existing exact guards. Target
labels are never admitted to the complete-source cache by these APIs.

## Disabled results and future integration requirements

With no shared charging curve, the runtime returns
`inactive_no_charging_curve` and None. An explicitly configured unsupported-zero
arithmetic policy returns `disabled_unsupported` and None, permanently for that
context. Integrity drift, unknown anchors and mixed states raise; they are not
converted to zero. None means retain the existing lower bound unchanged.

The prefix bound includes elapsed prefix clock, relaxed future charge and
travel, and past stop penalties. The complete-route bound adds H separate
stop overheads and penalties. Neither adds scheduled service or waiting,
because CS can overlap those with charging. Future integration must combine
complete objective bounds by max, not addition, and prune only on strict >
against an independently verified incumbent. It must retain equal-J secondary
competitors, the original Hmax/domain and independently replayed seed. The experimental gate performs that separately reviewed integration;
no real-road performance claim follows from the API or its finite tests.
The mathematical contract is stated in [the bound proof](REMAINING_CHARGE_BOUND_PROOF_V1.md).
