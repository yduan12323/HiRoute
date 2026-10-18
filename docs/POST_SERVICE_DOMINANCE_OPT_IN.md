# Post-service total cut order, default OFF

`timecut5.post_service_dominance` adds an explicitly selected reducer factory.
No existing solver entry point, PWA operator, historical reducer, certificate
checker, experiment, or stop bound is changed by importing the module.

```python
from timecut5.post_service_dominance import make_post_service_reducer

reducer = make_post_service_reducer(
    problem,
    enabled=False,  # Must explicitly opt in.
    completed_departure_layers=True,
    runtime=None,  # For enabled TableFreeRealProblem, pass bound.runtime.
)
result = _solve_problem(problem, dominance=True, reducer=reducer)
# Or pass the same reducer to _solve_hierarchical_problem for this live problem.
statistics = reducer.snapshot()
```

Version: `post-service-total-cut-order-v1`.

## Conditional model and trusted hook contract

Enabling requires the exact built-in `Problem`, `RealProblem`, or
`TableFreeRealProblem`. Unreviewed subclasses, coalescing adapters, instance
transition overrides, changed physical query fields, changed owners, and changed
declared Hmax are rejected. Immutable `RealProblem` leg mappings are supported;
its optional on-demand cache adapter is not admitted in this first version.

For native table-free use, supply the exact existing same-live-problem
`RemainingChargeRuntimeV1`. This reuses its bounded physical query, Site catalog,
provider, immutable graph/router ownership, arithmetic-history, and artifact
guards. It does not compute a road leg or scan graph arrays during reduction.
An unsupported live native status falls back to historical skyline before
deletion. No new native certificate is created.

`completed_departure_layers=True` explicitly promises that every input comes
from this same live problem's completed departure frontier. The supported call
sites are the existing complete-next-layer, full-State-grouped `reducer=` hooks
in `bounded._solve_problem` and `hierarchy._solve_hierarchical_problem`, after
every chosen Site action and `_retag_anchor` have completed. Do not use the
strong path for raw stop Site states, pre-stop arrivals, internal projection
unions, mid-layer partial reductions, arbitrary external frontiers, or another
problem's pieces.

This ownership/phase requirement is a **trusted caller boundary**. `CutPiece`
does not authenticate the original problem, physical phase, or predecessor
history. The module rejects detectable mistakes using exact types, one complete
State, physical energy limits, k/Hmax, Site/effect prefixes, service history, and
the last Site's actual road anchor. These checks cannot authenticate a forged
cut or distinguish all same-label/same-anchor phases. Explicit immutable
graph/router ownership and source binding remain the caller's existing duties.
The guards protect the supported API; they are not a hostile-Python sandbox.

The admitted physical model has static selected-leg travel time/consumption,
static common charging primitive and overhead, no history-dependent eligibility
or prior-charge budget, and no post-service opening times, queues, reservations,
new service windows, time-dependent roads/charging, or battery clock decay.
Repeated Sites and identity self legs remain legal. Search-process deadlines
are operational interruptions, not physical time-window semantics.

## Rule and proof

At one exact energy and identical complete state `(road_anchor, 0, k)`, choose
the first minimum of `(tau, not chi, rho, pi, original_index)`. Secondary rho/pi
are used only when primary `(tau, not chi)` ties.

For any actual removed prefix at time tB:

- If `tauA < tauB`, choose an inherited A realization below tauB, using its
  minimum or a sufficiently small positive approach budget. Then tA < tB.
- If tau ties and A is attained while B is open, A's minimum is strictly earlier
  than every actual B realization. An open tau is never executed.
- If both primary cut components tie, choose A no later than tB and require
  `(rhoA, piA) <= (rhoB, piB)`.

After `remaining_schedule == 0`, built-in continuations contain only static D
and C actions. Hold the suffix Site choices and all continuous energy decisions
fixed. D adds its leg time; C adds `h + F(Ed) - F(Ea)`. Feasibility and the
remaining stop budget are identical, and the same time increment is added to
both prefixes. A strict time advantage survives to final J regardless of Q/pi.
For a primary tie, energy conservation gives the final Q difference
`rhoA-rhoB`; equal k preserves H and equal-length prefix order under a common
suffix. Convexity of F is unnecessary; the existing valid continuous
positive-slope primitive suffices.

Retained families are subsets of original families, and every removed actual
plan has a no-worse retained completion. Therefore the J infimum agrees. If J is
attained, the simulated counterpart must also attain J, and the same argument
on that face preserves Q infimum/attainment. It then preserves H/pi on attained
J/Q faces. Primary-unattained results never acquire a fabricated Q/key;
secondary-unattained results never become a worse attained Q plan. No uniform
time gap, energy sampling quantum, or attained control optimizer is assumed.

The condition r=0 alone is insufficient in an extended model. For example,
waiting for a future service/opening time can erase A's primary advantage and
make B's better rho necessary. Different energy, stop count, history-dependent
action eligibility, or a raw Site/road-anchor collision also invalidate the
continuation argument.

## Exact arrangement, callbacks, and narrow parent runs

The strong path retains the historical exact arrangement of input endpoints and
affine intersections, including every singleton and open cell. It validates
every active `p.at(sample)` callback before selection, including dominated
ones. The sample represents a whole proven affine-order cell; it is not an SOC
grid. Primary ties and chi changes at isolated points remain exact.

Adjacent selected cells are joined only when they select the **identical
original parent object** and their exact interval union is connected. An
omitted open-open knot, a gap, or a cell assigned to another parent interrupts
the run. The joined interval remains a restriction of that original parent's
domain and uses its unchanged callback. This removes inactive-crossing
fragmentation without a general coalesced-family dispatch or a new certificate
meaning. Different original objects never join, even if scalar metadata agrees.

All inherited intermediate-energy, strict-charge, and predecessor-subfamily
constraints stay in the original callback chain. No unrestricted prefix
re-solve, zero-charge limit execution, domain enlargement, or altered chi is
permitted. Source family objects may remain referenced by descendant lifts
after their display/frontier occurrence is removed.

## Historical fallbacks and certificates

- Disabled (the default): `reduce_frontier_skyline`.
- A pre-service r=1 group: `reduce_frontier_skyline`.
- An active `Recorder`, or any input with `_family` present:
  `reduce_frontier_skyline`, before any strong deletion or parent-run joining.
- Unsupported native admission status: `reduce_frontier_skyline`.

Known recorded families outside their original recording context retain the
historical rejection; they are never stripped to enter the strong path.
Ordinary family5/real5_v2 `reduction` certificates keep their product-order
meaning. This mode claims conditional terminal-result preservation, not legacy
product-antichain equality or equality of all raw executable time/key sets.

Original action coverage, Hmax, terminal reserve, strict `Ea < Ed`, independent
incumbent replay, and primary pruning at **strict greater-than only** remain
unchanged. Do not lower Hmax or prune primary equality because of this feature.

## Statistics and testing

`PostServiceDominanceStatistics` is a detached frozen dataclass containing
`enabled`; completed successful calls/input/output piece counts; strong,
disabled, pre-service, recorded, and unsupported call counts; arrangement cells,
selected cells, candidate visits, strict-primary/tied-primary discarded visits,
and same-parent run joins. These are repeated cell/piece visits, not unique
routes or a speedup estimate. Failed calls commit no partial counts.

For completed snapshots:

- calls = strong calls + the four fallback call counts;
- candidate visits = selected cells + strict-primary discards + tied-primary
  discards (strong path only);
- selected cells minus parent-run joins is the strong-path output-piece count;
  overall output pieces also includes fallback outputs;
- input/output piece count need not decrease because an exact arrangement can
  split an original piece;
- an enabled admitted unrecorded empty input is one strong call with zero
  piece/cell/visit counts.

`tests/test_post_service_dominance.py` covers exact point orders, bad secondary
ties, crossings/singletons, parent-run holes/interruptions, tiny epsilon lifts,
all-callback validation, invalid model/phase/state/ownership, historical
recording certificates, all 18 frozen synthetic result statuses, five immutable
real-input mocks with anchor aliases, both FLAT/HIER hooks, and tiny native
full/target routing with same-live-runtime admission and fresh full-only
verification. A separate independent standard-library rational oracle
exhausts continuous two-C suffixes on tiny frontiers; it imports no production
projection/reduction/envelope code.

Run focused tests in normal and optimized Python. Source/policy/config freezes,
fresh independent replay and truthful interruption reporting remain obligations
of any separately authorized real experiment. These tests imply no real-road
runtime improvement or completion of a previously timed-out search.
