# Fixed known-DEV FLAT/HIER cohort (prospective, not launchable)

This selection is based on **prior DEV exposure and mechanism coverage**, not
outcome-blind sampling. Freeze these three domains before new cohort outcomes.
They are neither a final holdout nor a representative statistical sample.
The accompanying `dev_cohort_v1_bindings.json` preserves the exact original
query bindings and ordered pool rows. It is a design input, not a run manifest.

| Case | Original candidates | Historical Hmax | Fixed method order | Coverage |
| --- | ---: | ---: | --- | --- |
| OD00_energy_only_soc19_25 | 32 | 28 | FLAT, HIER | High SOC, energy only; reverse direction of previous OD10 control |
| OD02_energy_only_soc3_10 | 128 | 33 | HIER, FLAT | Low SOC, multiple charging stops |
| OD06_energy_and_scheduled_soc3_10 | 128 | 39 | FLAT, HIER | Low SOC, scheduled service, CS+C witness |

## Original input identity and domain

The JSON's `inputs` map records the original SHA256 and byte size for each
restored input. Its `cases[].original_binding` is copied unchanged from
`recovery_inputs/queries.json` by `query_id` and `bindings[str(N)]`, including
the full query, ordered candidate IDs, query/site/anchor/candidate/domain hashes.
`original_pool_prefix` is copied unchanged from the matching OD's first N rows
of `recovery_inputs/pools.json`. Those ordered site IDs were checked for exact
equality; no sorting, reselection, expansion or repair creates this cohort.

Small-input hashes were rechecked while writing the plan. Graph/hierarchy
hashes are copied from the existing restore-verification receipt; the future
launch must independently verify its full input/source closure.

- queries.json: `dc22c22bd56dbd763e41eecbc0da1310259990c25caef469783a49032ccaed7c`
- pools.json: `4b93c90b0f4f77364cd9e58b5a779bccd11fb7b99819646c8096ed4f122fe937`
- original slate: `68917b71ff74cc13a4f35d2b7c7fb7ca577e572295c2d091bb0a0957a3789b95`

Retain original hierarchy identifiers/topology, empty/unary regions and
multi-site leaves while intersecting membership with the frozen candidates.
Original query `H_ref=4` is a placeholder, not the admitted search depth.
Fresh first-feasible proposal generation and double physical replay must
produce the expected historical seed-derived Hmax above. A mismatch is an
admission failure requiring a separately declared future plan, not permission
to shrink or expand this domain. Do not recompute Hmax from later incumbents.
Keep original and newly authenticated runtime-domain hashes separately labeled.

## Seed evidence and unknowns

OD00 and OD06 have independently replayed feasible historical witnesses in
`results/milestone_5d/frozen_dev_coverage_20261015/`. Their public witness
projections are not loadable signed checkpoints. OD02 has matched DEV evidence
in `results/milestone_5d/matched_dev_coverage_20261015/` and an authenticated old
common seed under the OD02 forward execution. No old native admission is reused.
All three need fresh common preparation; historical feasibility does not imply
that the new admission process has succeeded.

Original OD07 N128 previously exhausted its proposal stream without a seed;
candidate feasibility remained unknown. Do not substitute its repaired N149
domain. OD06's older failed N32 preparation is also not repaired retroactively
by selecting its separately established N128 DEV domain here. No new outcomes
may change case membership or remove failures from the denominator.

## Matched bound family and explicit FLAT adapter

Freeze the same target routing, terminal-energy screen, skyline reducer,
q10/onward ALT, projection prefilter and remaining-charge configuration for
both methods. The envelope ON/OFF choice must be explicit and common before
launch; this plan does not inherit a choice from a pending experiment.

`RemainingChargeRegionBound.bound()` strengthens HIER only; its inherited
singleton method does not add the remaining-charge terms. The new explicit
`experiments.remaining_charge_gate_v1.singleton.RemainingChargeSingletonBound`
has constructor `(original, problem, *, runtime=None)` and method
`singleton_bound(problem, pieces, site, effect) -> Fraction | None`.
The runner must pass this method directly to FLAT. No default is changed.

For an original non-None lower bound L and next stop count k+1, return
`max(L, certified_prefix_bound(pieces), certified_whole_route_bound(k+1))`.
Each term bounds the complete primary objective for every continuation of the
trusted same-state frontier through the proposed action; taking their maximum
is admissible. The action adds one stop even when it is S or CS. No prefix
clock authentication for forged caller-created pieces is claimed.

Preserve original None before added runtime evaluation. Both runtime receipts
must match admission; active values must be exact Fractions. Explicit known
unsupported/inactive status disables only the extra max and returns L;
integrity errors raise. Missing finite ALT terms never imply unreachability.
Hmax and the engine's strict `lower > upper` test stay unchanged, retaining
primary equality for secondary/attainment/provenance decisions.

`POLICY_SCHEMA` is `hiroute.remaining_charge_singleton.v1`.
`statistics_snapshot()` returns detached scalar fields: schema,
runtime_enabled, calls, original_none, active_calls, disabled_calls,
strengthened_calls. Calls count entry, so errors or censored invocations need
not have a completed category. These are bound-call counts, not engine prunes;
there are no per-call callbacks or retained traces.

Region aggregation, queue order and incumbent discovery still differ. Report
a matched lower-bound-family FLAT/HIER comparison, not identical pruning or
an isolated speedup attributable to hierarchy alone.

## Stages, entry reuse and resource policy

Declare 15 slots: 3 common preparations + 6 searches + 6 independent replays.
Keep blocked, failed, timed-out and skipped slots, including descendants of a
failed preparation. No automatic retry, replacement or next-size escalation.
Each search has a 240-second exact phase including post-solver finalization.
Preparation/setup and fresh independent replay have separate charged budgets.
Existing reusable outer caps are 600 seconds per preparation/search stage,
180 seconds per verifier wall time, and 120 verifier CPU seconds; these are
per-process/stage limits, not an aggregate CPU accounting guarantee.

Reuse the authenticated supervisor, compact result envelope, source closure,
common-seed admission and fresh-full-verifier lifecycle from the completed
projection gate and mechanism runner. Their old case allowlist, OD07 repair,
HIER-only dispatch, `.bounded` result assumption and durable `method='hier'`
cannot be silently reused. A new method-aware runner must dispatch explicitly,
normalize the actual result type, and bind the correct durable method/case.
The singleton adapter does not own those runner changes.

Resource scheduling is independent of objective, speedup and solver outcomes:

1. Start with one heavy worker. Run the first N128 FLAT/HIER pair serially and
   retain both complete process-tree memory traces and cleanup receipts.
2. Serial remains the default. An explicitly enabled memory-only scheduler may
   admit at most two independent searches after both first-N128 traces are
   available, complete, and not memory-censored. Let P be the largest observed
   process-tree RSS peak across those searches and earlier stages; reserve
   1.25 P per concurrent worker and at least 2 GiB for the OS/controller.
   Require `2 * 1.25 P + 2 GiB <= measured physical memory` and current available
   memory sufficient for the additional worker plus the 2 GiB reserve.
   Never infer a bound for N128 from N32 measurements alone.
3. This measured envelope is a scheduling estimate, not a hard memory bound.
   Keep monitoring total owned process-tree RSS and host availability. Missing
   telemetry, memory pressure or incomplete cleanup disables further concurrent
   starts; any resource termination remains a recorded failed slot. Never
   terminate unrelated processes. If a guaranteed aggregate cap is required,
   remain serial until an explicit aggregate enforcement mechanism is reviewed.
4. Fixed per-case method order is queue admission order. Preserve actual
   overlap/CPU affinity and disclose shared-host contention; concurrent times
   are not isolated paired speedups. Never alter domains or drop failures to
   make memory or timing results look better.

The host has approximately 9.7 GiB and 9 CPUs. The completed N32 gate sampled
about 3.10 GiB peak process-tree RSS. Its 8 GiB per-process address-space limit
is not an aggregate memory limit or cgroup guarantee.

## Minimal acceptance and reporting

- Bind source, original inputs, runtime policy, actual common seed and Hmax.
- Require authenticated final output plus fresh physical replay for exact
  completion; solver return or a feasible-only checkpoint is insufficient.
- Compare full exact terminal keys and attainment/infimum semantics whenever
  both methods complete; never infer optimality from successful replay alone.
- Verify all owned cleanup, admission and verifier stages. Keep all 15 slots.
- Report completion/failure counts over the fixed cohort, matched completed
  timings separately, setup/replay costs separately and censored snapshots as
  partial. Do not sum nested inclusive timings.
- No positive speedup is required. No holdout/generalization claim is licensed.

Tiny adapter tests cover active exact max, equality, None/inapplicable/empty
actions, disabled fallback, owner/receipt/native drift, q0/q10 units, missing
ALT terms, and exact FLAT/HIER key/terminal parity. No real graph is executed
by the adapter test suite or by writing this plan.
