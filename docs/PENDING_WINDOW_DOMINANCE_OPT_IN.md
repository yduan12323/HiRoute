# Pending-window late-primary dominance, opt-in v1

Status: default OFF; conditional static-model optimization. No existing solver,
post-service module, product-order reducer, certificate or acceptance obligation
is changed by adding this module. The separate proof study and synthetic/tiny
native tests do not establish real-road speedup or search completion.

## Explicit API and counter separation

Use only the existing complete-next-layer full-State reducer hooks:

```python
from timecut5.pending_window_dominance import make_pending_window_reducer

reducer = make_pending_window_reducer(
    problem,
    enabled=False,                 # new pending-window feature, default OFF
    post_service_enabled=False,     # existing r=0 feature, default OFF
    completed_departure_layers=True,
    runtime=remaining_charge_runtime,  # required for enabled table-free use
)
```

`VERSION` is `pending-window-late-primary-order-v1`. Both switches must be exact
booleans. Both default OFF preserves the historical skyline. Selecting either
feature requires the original trusted completed-departure/live-problem contract;
a `CutPiece` cannot authenticate its own lineage or whether overhead was already
paid. The new wrapper reuses the admitted existing post-service reducer's
unchanged model/state/owner/native runtime guard. No bare metadata claim or
unadmitted custom model is supported.

`enabled=True` applies the new rule only at r=1. r=0 delegates to the old reducer
selected by `post_service_enabled`. An empty call delegates as well. Recorder
or inherited recorded-family inputs always delegate to historical reduction;
metadata is never stripped. Unsupported native status delegates instead of
being used as a pruning certificate. Model/owner/integrity changes retain the
old fail-closed behavior.

`reducer.snapshot()` returns immutable `PendingWindowDominanceStatistics` with
separate new-feature counts. `reducer.post_service_snapshot()` returns the
unchanged existing `PostServiceDominanceStatistics` for actual delegated calls
only. Thus pending strong calls do **not** inflate or reinterpret old
post-service call/strong/fallback counters.

The new fields are:

- flags: `enabled`, `post_service_enabled`
- all calls: `calls`, `input_pieces`, `output_pieces`
- paths: `strong_calls`, `disabled_fallback_calls`,
  `recorded_fallback_calls`, `phase_fallback_calls`, `unsupported_fallback_calls`
- pending strong work: `arrangement_cells`, `selected_cells`, `candidate_visits`,
  `product_discarded`, `late_primary_discarded`, `kept_candidate_visits`,
  `threshold_roots`, `added_threshold_knots`, `parent_run_coalesces`

Successful-call identities:

- calls = strong_calls + the four fallback call counts
- candidate_visits = product_discarded + late_primary_discarded + kept_candidate_visits
- old post-service calls = new calls - new strong_calls

`threshold_roots` counts distinct in-domain-closure affine tau=a-h roots per
strong call; `added_threshold_knots` counts those absent from the historical
arrangement. Constant affine pieces generate no roots. Counters are repeated
cell/candidate visits, not unique routes or performance claims. Selected cells
can have multiple survivors. Failures do not commit new call counts.

## Rule and conditional proof

At identical exact energy and full physical `State(anchor,1,k)`, define
`theta=a-h` and primary `(tau,not chi)`. First compute the old product skyline.
Delete a skyline member B only if its primary is strictly worse than the global
minimum primary and either tauB>theta, or tauB==theta and chiB=False. A stable
minimum-primary/best-secondary member always survives. Earlier cuts and
attained threshold equality retain the historical product-order tradeoff.

For every actual B realization tB, the late predicate gives tB>a-h. Strict
primary order supplies an actual A witness tA<tB through its original minimum
or approach callback, even when A itself is open or is earlier than theta.
Copy B's full suffix Site/effect choices and continuous energy controls.
Before the unique remaining service, static drives and C actions add the same
nonnegative x. B's service release tB+x+h is strictly above a. Service starts
are max(a,tA+x+h) and tB+x+h, so A starts strictly earlier and preserves B's
latest-start feasibility. S adds duration D. CS finishes at
max(service_start+D, t+x+h+F(Ed)-F(Ea)); both coordinates are strictly better
for A. The output gap is at least min(tB-tA,tB+x+h-a)>0. All later operations
add equal constants. H is identical, so final J is strictly improved regardless
of rho/pi. No common positive gap over all approaches is required.

Selected subfamilies remain original subsets. Executable no-worse coverage
therefore preserves J infimum/attainment, then Q infimum/attainment on the
attained J face, and then H/pi. A deleted strictly worse-J branch cannot supply
a missing attained primary optimum. Old product coverage handles all remaining
secondary ties. This is a stronger conditional simulation, not the old
product-order continuation certificate.

The model has one remaining service, global positive h, nonnegative duration,
static nonnegative selected legs, and a common static increasing charging
integral. Repeated Sites, self legs and anchor aliases are legal; Site identities,
capabilities and pi entries stay distinct and each action pays the existing h.
A second waiting window, dynamic queues/routing, history-dependent eligibility,
wrong energy/k/anchor, or an unfinished already-paid stop phase is outside the
proof and admission contract.

## Energy arrangement and witnesses

Every affine tau=a-h root in a piece's domain closure is added to the original
endpoint/pairwise-intersection arrangement. Exact singleton and open endpoint
semantics are preserved. Sampling only the old cells is unsafe: a late midpoint
can conceal early cuts whose advantage is erased by waiting and whose lower Q
must survive. The physical regression has E in (0,4], A tau=E+4/rho=1,
B tau=E+5/rho=0, h=1,a=7,D=1; B must remain through E=1, including its attained
singleton. Omitting the root yields wrong attained Q=3/2 instead of 1/2.

Every active point callback is validated before selecting, including discarded
ones. Output restrictions retain the identical original callback. Joining is
allowed only for consecutive output runs of the identical original parent and
a connected exact interval union. An omitted singleton, gap, or intervening
other-parent run prevents joining; no different-parent metadata merge occurs.

## Verification scope

The focused test module exercises exact point selection, threshold singleton
and crossing domains, physical S/CS/latest-start variants, original callback
restrictions/tiny approach budgets, all four terminal statuses on 18 frozen
synthetic cases, five immutable alias mocks, both FLAT/HIER engines, historical
Recorder certificates, same-live-model/state/history guards, and tiny native
full/destination-target wiring with fresh full physical replay. Native graphs
are finite synthetic arrays; no real OSM/holdout launch or installation is part
of these tests. Preserve original Hmax, seed, candidate/action universe, strict
objective comparisons and replay policy in any separately authorized gate.
