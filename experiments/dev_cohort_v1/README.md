# Fixed paired FLAT/HIER known-DEV cohort

The complete selection, exact original candidate/query bindings and resource
rationale are in `docs/DEV_COHORT_PAIRED_PLAN.md` and
`docs/dev_cohort_v1_bindings.json`. This is a previously exposed DEV cohort, not
outcome-blind sampling or a final holdout. No positive result is required.

The fixed cases and search admission orders are:

- OD00_energy_only_soc19_25: original N32, Hmax28, FLAT then HIER
- OD02_energy_only_soc3_10: original N128, Hmax33, HIER then FLAT
- OD06_energy_and_scheduled_soc3_10: original N128, Hmax39, FLAT then HIER

There are always 15 slots: three common preparations followed by six searches
and their six independent verifier slots. Preparation failure blocks that case's
four descendant slots. An unknown owned-process outcome stops further launches;
unattempted slots remain explicitly blocked in the denominator. Other failures
remain recorded. No replacement, automatic retry, reordering or next run occurs.

## Frozen domain and shared features

Both methods share target routing, terminal-energy screening, skyline reduction,
q10/onward ALT, projection-support ON and remaining-charge ON. The envelope
setting is frozen OFF, common to every method/case; runtime cannot override it.
This is an engineering selection informed by the already exposed OD10 DEV
control, not an outcome-blind choice. That exact matched control completed in
116.765 seconds OFF versus 207.223 seconds ON, with the same final work/cells.
Correctness passed, but the negative timing evidence did not justify enablement.
The earlier design input retains its prospective, choice-pending chronology;
the closed run manifest separately records the final OFF selection.

The runner authenticates original input bytes, exact ordered pool prefixes and
query bindings, preserving the original hierarchy topology and identifiers via
the existing validated restriction routine. The original H_ref=4 field is a
placeholder. Fresh deterministic first-feasible generation and two independent
full physical replays must yield the separately required historical Hmax. A
mismatch writes a bounded `blocked.json` diagnostic and fails preparation;
neither Hmax nor candidate membership changes. Such a diagnostic cannot grant
admission. Source-dependent sparse-domain rebinding is separately labeled and
is the only permitted query-field difference.

A single freshly admitted seed is shared by the two methods for a case. Later
incumbents cannot shrink the original Hmax. All cases retain their own original
candidate count, query and common seed, so cross-case timings are not causal
candidate-count comparisons.

## Method-aware experiment adapter

`domain.py` inherits reviewed physical setup, target/search versus full/verifier
contexts, q/runtime activation and source validation. Its inherited inner arm
remains immutable `support_on`; method, common configuration and complete case
binding are separate outer identities. They enter durable domain/source hashes,
activation, progress, final result and fresh verification. Supervisor phase
identity binds the method, case, common artifact, manifest and source closure.

FLAT explicitly calls `_solve_problem` with the newly reviewed
`RemainingChargeSingletonBound.singleton_bound`. HIER explicitly calls
`_solve_hierarchical_problem` with the existing Region wrapper. Both use
max(original ALT lower, certified prefix lower, certified whole-route lower at
next stop count). Original None handling, action coverage, original Hmax and
engine-owned strict greater-than pruning are retained. Equality remains live.
Region aggregation, queue order and incumbent discovery still differ: this is
a matched lower-bound-family comparison, not identical pruning or an isolated
hierarchy-only speedup.

A small local lifecycle replaces every HIER-only seam in the older adapter:
solver dispatch, method-specific checkpoint counters, return-type normalization,
AtomicIncumbentStore's explicit `flat`/`hier` tag and method-bound recovery.
Both attained and unattained terminal payloads use the common canonical result
contract; no full key is invented for an unattained infimum. Fresh full replay
also checks the durable record's explicit method tag and verifies that its bytes
did not change during replay. It verifies feasible witnesses; exact completion
still requires the authenticated solver result.

Projection and envelope contexts cover exact solve only. Fresh incumbent
verification uses separate nested OFF contexts; final storage and independent
verification run outside them. No production/default or earlier frozen runner
is modified, and no global method/configuration monkeypatch is used.

## Evidence and limits

The existing bounded observer is shared: 0.5-second heartbeat, 32 recent events,
256 KiB snapshots. Final normal admission requires a hash-matching snapshot and
healthy in-memory observer result. Timeout snapshots are censored and their final
health is unknown, even if their last sampled status says returned.

FLAT reports detached singleton calls, None outcomes, active/disabled calls and
strengthened calls. These are invocation counts, not actual pruning counts;
FLAT's actual Region prune count is explicitly unavailable. HIER keeps its
separate Region counters. Projection/envelope counts are likewise live,
nontransactional samples until authenticated normal completion. No sums of
nested inclusive timings or fabricated total CPU costs are reported.

Each exact phase is 240 seconds, including finalization; total declared exact
allowance is 1440 seconds. Other caps are unchanged: preparation/arm whole wall
and CPU 600 seconds, verifier wall/CPU 180/120 seconds, child address space 8 GiB,
parent CPU 90 seconds. The serial worst-case stage allowance is 6480 wall seconds
and 6120 worker soft-CPU seconds. This runner fixes ONE heavy worker. The plan's
possible later two-worker scheduling policy is not implemented or enabled here;
any such scheduler requires separate reviewed changes and a new frozen manifest.
Per-process address space is not a hard aggregate RSS guarantee.

Per-case operational admission and paired authenticated completion are separate.
Completed FLAT/HIER payloads must agree, including attainment/infimum semantics;
every successful method must match fresh full replay. Valid timeouts may provide
operational feasible evidence, but cannot count as exact completion. Read
`case_outcomes`, `all_pairs_authenticated_complete` and `completion_outcome`.
The CLI success code reports operational admission alone. All 15 slots and
negative/inconclusive outcomes remain visible.

## Commands after configuration, code and resource review

Use the matching installed Python in the immutable checkout. The explicit
envelope argument must be the reviewed literal `off`. Outputs stay
outside the source closure.

```sh
OUT=$(mktemp -d ../dev-cohort240-XXXXXX)
CPU=$($PY -c 'import os; print(min(os.sched_getaffinity(0)))')
$PY -m experiments.dev_cohort_v1.run --freeze --envelope-sweep off \
  --input-directory ../recovery_inputs --output "$OUT/manifest.json"
SHA=$(sha256sum "$OUT/manifest.json" | cut -d' ' -f1)
taskset -c "$CPU" "$PY" -m experiments.dev_cohort_v1.run --gate \
  --manifest "$OUT/manifest.json" --manifest-sha256 "$SHA" \
  --output "$OUT/gate" --cpu "$CPU"
```

Tiny/mocked tests do not run the original road graph:

```sh
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -m unittest test_dev_cohort_gate -v
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -OO -m unittest test_dev_cohort_gate -v
```
