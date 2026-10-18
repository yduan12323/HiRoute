# Prospective exact projection-support OFF/ON DEV gate

This separately frozen gate tests whether rejecting provably empty C/CS
energy-segment pairs before exact projection reduces the observed search cost.
It changes only `ProjectionSupportPrefilter(enabled=False/True)`. With no context,
production behavior remains the historical path. The explicit OFF context counts
baseline work without adding support arithmetic.

## Fixed comparison

Both arms use q10 certified time ALT, destination-target routing, terminal-energy
screening, exact skyline reduction, indexed onward ALT and the remaining-charge
bound ON. Original OD10 N32 membership, query, hierarchy, original Hmax26 and
bounded source-cache policy are unchanged. One fresh full-routing seed is
independently double-replayed and supplied identically to both arms. The stable
prefilter configuration/source policy enters portable durable binding; live
runtime receipts stay separate. Cross-arm incumbent artifacts are rejected.

The fixed five stages are preparation, OFF search, fresh full verification,
ON search, fresh full verification. Search phases each have externally enforced
120-second budgets. Preparation/arm wall and CPU limits are 600 seconds;
verification has 180 seconds wall/120 seconds CPU. Each child has 8 GiB address
space, with 90 seconds supervisor CPU. Numerical stages are sequential on one
selected CPU. No automatic repeat, N128, 600-second search or holdout follows.
Negative and inconclusive outcomes are retained.

## Exact mechanism and scope

For a source piece and each input charging segment, ON intersects the original
energy domain with that input interval. For each output segment it skips only:

1. An empty input-domain intersection.
2. Input-support infimum at least the output-segment supremum, which contradicts
   the existing strict charging requirement `arrival_energy < departure_energy`.

All other pairs use the original projection rows, row order, extraction and
witness lift. Open boundaries are handled conservatively: uncertain pairs stay
with the original projector. S-only handling is unaffected. This is not a
route-pruning rule; Region coverage, strict bound comparisons, equality retention,
query/Hmax and feasible-witness verification remain unchanged.

A fresh context surrounds only the existing exact solver invocation, after setup
and runtime admission. A distinct disabled nested context surrounds each durable
incumbent callback, ensuring that fresh full verification neither activates ON
nor contaminates the search context's counts. The outer context is restored even
if verification raises. Standalone verification runs outside the context. The
solver's own internal replay belongs to its search-phase work; observed pairs
are not unique route-feasibility decisions.

## Counters and admission

The public frozen snapshot contains exactly five detached scalars: enabled,
considered_pairs, skipped_empty_input, skipped_strict_energy, projection_builds.
The same bounded observer samples them in both arms: 0.5-second persistence
interval, 32 recent events, 256 KiB maximum snapshot. No per-piece trace or
per-pair I/O is added. Counts are separate from provider routing deltas.

Heartbeat samples are not transactional multi-counter reads. A sample or hard
interrupt can occur between consideration and skip/build accounting, so TIMEOUT
requires exact types, nonnegative values and the correct enabled policy, but does
not require count conservation. OFF must always report zero skips. A normal
SUCCESS requires authenticated final statistics matching the final progress
snapshot and `considered = empty_skips + strict_skips + builds`.
`projection_builds` counts invocations, not only feasible projections.

The reviewed q10 certificate, remaining-charge activation and original seed/Hmax
validators are reused. Prefilter policy and enabled state are bound in admission,
snapshot, result and portable domain configuration. SUCCESS additionally requires
matching final progress/admission hashes and healthy observer state. A final fsync
failure remains inconclusive even if an earlier disk snapshot appears healthy.
TIMEOUT is censored and never proves terminal observer health, including a
kill-after-return race. Stage/phase identities, cleanup and independent full
verification must pass separately; completed exact answers must agree.

Interpret projection savings as local construction savings. A 120-second timeout
does not establish exact completion or a universal speedup. Timings remain nested
and inclusive. Observer overhead is only partially measured, provider counters
are individually sampled, and actual engine pruning counters at checkpoints can
lag an active layer. Remaining-charge activation wall excludes earlier ALT
construction; complete setup time includes it. Prior gate results are preserved;
final holdout remains unrun.

## Commands after source review and freeze approval

Use the matching installed Python from a reviewed immutable checkout without a
source override. Set `PY` to it and keep outputs outside the source closure.

```sh
OUT=$(mktemp -d ../projection-support-gate-XXXXXX)
CPU=$($PY -c 'import os; print(min(os.sched_getaffinity(0)))')
$PY -m experiments.projection_support_gate_v1.run --freeze \
  --input-directory ../recovery_inputs --output "$OUT/manifest.json"
SHA=$(sha256sum "$OUT/manifest.json" | cut -d' ' -f1)
taskset -c "$CPU" "$PY" -m experiments.projection_support_gate_v1.run --gate \
  --manifest "$OUT/manifest.json" --manifest-sha256 "$SHA" \
  --output "$OUT/gate" --cpu "$CPU"
```

Tiny integration tests, without recovered road inputs:

```sh
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -m unittest test_projection_support_gate -v
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -OO -m unittest test_projection_support_gate -v
```
