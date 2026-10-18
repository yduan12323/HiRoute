# OD10 N32 full/target energy-screen profiling gate

This is a new, opt-in, known-DEV diagnostic. It preserves the earlier skyline gate
and all its evidence. No import, test, default command, or completed predecessor
automatically launches this gate. The final holdout remains unrun.

## Fixed comparison

- Original OD10_energy_only_soc19_25 N32, original restricted hierarchy IDs
- One newly generated, independently double-replayed common seed and its Hmax
- HIER with the original reduce_frontier in both arms
- Full selected-leg routing + terminal-energy screen versus destination-target
  routing + the same terminal-energy screen
- Indexed ALT, onward ALT OFF, coalescing OFF, unchanged two-source/1-GiB cache
- Same bounded progress observer enabled in both arms
- Fixed baseline_full then destination_target_only order, no combined skyline arm
- One120-second exact phase per arm, each followed by a separate fresh full-only
  physical durable-incumbent verification

Generation, landmark, verification, durable verification, and recovery remain
full-mode; only search changes routing mode. The combined target/energy policy
requires the separately reviewed production support in this source commit.
Complete mathematical terminal results must agree if both finish; valid continuous
charge allocations may differ. Censored feasible outcomes need not match.

This isolates a routing-policy change under a fixed observer. It is not a ranking
against old-source results or an enabled/disabled observer performance experiment.
The known N32 choice is for bottleneck diagnosis, not independent confirmation.
A negative or inconclusive result is valid. Do not adjust the window, case, source,
feature mixture, or order after seeing its result.

## Bounded active-operation evidence

ProfileProgress subclasses the existing ExactSearchProgress in this experiment
package only. It keeps the original event/operation hooks, active stack, inclusive
wall/calling-thread CPU timers, heartbeat and atomic fsynced latest snapshot.
Persistence is rate-limited to one write per0.5 seconds, plus initial/final writes.
This avoids the stock observer's per-outer-operation/projection/routing fsync cost.
Skipped persistence never skips the corresponding event or timing update.

Only the latest progress.json plus its temporary replacement is retained. The
journal holds at most32 events; snapshots have the existing256-KiB cap. Counter
fields contain only fixed bounded operation names/scalars and declared-anchor
source counts. No frontier, full witness, trace-per-action, graph scan, or growing
request journal is added. A fixture with2000 fast operations retains all2000
completed timings in two writes, with at most32 recent events.

A separate heartbeat preserves long-running active operations before layer2/3
finishes. Hard termination leaves a running, censored snapshot; it never fabricates
returned status, a completed operation, an exact kill-time stack, or a global gap.
GIL-held native/Python work, scheduling and I/O can delay the heartbeat. Record the
actual sampled timestamp, last active stack and maximum observed write gap.
The field maximum_observed_write_gap_ns measures gaps between persistence attempts,
not independently confirmed completed writes. Provider counters are individually
sampled values, not an atomic routing-history transaction.
Observer I/O and thread errors block diagnostic admission when observed; an old
healthy snapshot does not prove the unseen timeout tail stayed healthy. On normal
SUCCESS, admission also authenticates the final snapshot SHA against the arm
result and checks that result's final observer health. This catches final fsync
failures latched after snapshot bytes were written. TIMEOUT always remains
health-unknown/censored, even if its last snapshot says returned. The ledger keeps
solver outcomes separately from diagnostic admission; diagnostic failure never
rewrites the solver's physical outcome.

The new durable_incumbent_callback operation includes its fresh full verification
contexts. Nested road/energy/replay operations are inclusive, so do not sum timer
categories. Search-provider counters exclude those separate verifier providers;
the callback timing prevents assigning their residual wall to the reducer.
Counter deltas start at exact observer entry after setup. Cache bytes/entries are
end gauges, not cumulative differences. Per-source run deltas reveal whether a
full-source calculation repeated; cache eviction alone does not prove rerouting.
Persistence clocks measure persistence only, not total observer overhead. Equal
instrumentation removes a configuration difference but does not prove zero or
identical realized overhead. No whole-run throughput from a partial snapshot.

## Resources and admission

Exactly five planned stages: preparation, baseline search/replay, target search/
replay. The inherited supervisor owns cleanup and external exact-phase deadlines.
Preparation/search workers:600-second wall and600-second per-process CPU soft
limit. Replay workers:180-second wall and120-second CPU soft limit. Each worker
has8-GiB per-process address-space limit and one-CPU affinity; RSS is sampled,
not an aggregate cgroup limit. Run one road worker at a time with host headroom.
The per-gate reservations remain2160 worker-wall seconds,2040 worker-CPU-soft
seconds and90 parent CPU-soft seconds. Reservations are not measured CPU totals;
CLI/source-validation/finalization outside the inherited parent timer stay separate.

Source/input/native/configuration drift, common-preparation failure, unsuccessful
search other than exact phase timeout, missing/failed replay, unknown cleanup,
completed-answer disagreement, missing/unbound/known-unhealthy observer output,
or exhausted orchestration budget prevents admission. Every original stage stays
in the ledger. A valid time_limit+fresh-replay result is operational evidence only.
No automatic next gate, extension, repeat, reverse order, or holdout is present.

## Commands

Run only from the separate reviewed worktree, after a clean committed source and
an isolated installed-wheel environment match that source. Do not install into
another still-running experiment's shared environment. Use unused output paths.

Graph-free/tiny tests, pinnedCPU2:

    taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src ../hiroute-ci-venv/bin/python -m unittest discover -s tests/m5d_recovery -p test_scalability_profile_gate.py -v
    taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src ../hiroute-ci-venv/bin/python -OO -m unittest discover -s tests/m5d_recovery -p test_scalability_profile_gate.py -v

Read-only plan (use reviewed installed runtime for numerical commands):

    PROFILE_PYTHON -m experiments.scalability_profile_v1.run --plan
    PROFILE_PYTHON -m experiments.scalability_profile_v1.run --freeze --input-directory ../recovery_inputs --output ../extension_runs/profile_od10_n32_v1_manifest.json
    PROFILE_PYTHON -m experiments.scalability_profile_v1.run --gate --manifest ../extension_runs/profile_od10_n32_v1_manifest.json --manifest-sha256 RETURNED_SHA --output ../extension_runs/profile_od10_n32_v1_execution --cpu AVAILABLE_CPU

PROFILE_PYTHON means the actual isolated environment executable selected after
source review. The freeze authenticates the existing nine inputs, compiler,
installed source and the full inherited/new executable closure. The parent decides
launch only after current immutable N32/N128 work is terminal. No command publishes,
merges, changes old results, or runs final holdout.
