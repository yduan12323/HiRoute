# Prospective exact envelope-selector OFF/ON gate

This is a separately frozen developmental OD10 N32 comparison, with 240 seconds
per exact phase. The single factor is the opt-in `EnvelopeSweep` selector.
Both arms share projection-support ON, q10 dyadic ALT, target routing,
terminal-energy screening, skyline reduction, onward ALT and remaining-charge ON.
Original candidate membership, query, Hmax26 and the freshly double-replayed
common seed are unchanged. No outcome is required to be positive.

## Reuse and explicit identities

`EnvelopeDomain` inherits the reviewed projection-support domain. Its inner
`arm` is always `support_on`, and its inner configuration is never temporarily
rewritten. Context construction, original ALT/runtime admission, seed validation,
remaining-charge bound, native-cache policy and durable full replay are inherited.
The small exact-solve wrapper retains the same solver arguments, checkpoint and
incumbent callback, adding only the envelope context and scalar observation.

`envelope_off` and `envelope_on` are separate outer identities. Their schema,
configuration and policy enter the portable durable domain and source hashes,
manifest, supervisor phase identity, bounded activation artifact, progress and
final worker result. The outer activation binds the unchanged inner activation
artifact by digest. Admission checks the outer identity before calling the
existing projection/q/runtime validators with the immutable inner identity.
Cross-arm, stale-inner and earlier-experiment artifacts fail. Fresh independent
full verification reconstructs both binding layers without live search context.

The existing completion240 phase validator, supervisor hook, stage caps and
reserve accounting are reused unchanged. Existing runners are not patched or
monkeypatched. The short experiment-specific orchestration explicitly names the
new outer arms and worker module; it never invokes an old gate's global arm list.

## What the selector changes

The unchanged original arrangement is built in both arms. OFF uses the historical
parent selector. ON selects the same original parent on each cell using exact
pair-relation interval events and a zero-better-parent heap. Cell order, parent
identity, ties, lift/witness lineage, action coverage and engine pruning are
unchanged. Any active provenance recorder uses the historical selector and is
counted as a fallback. No default enablement is introduced.

Both contexts start only around the exact solver, after setup and admission.
A durable-incumbent callback uses distinct nested OFF contexts for envelope sweep
and projection support while fresh full replay runs. These contexts restore on
exceptions. Final durable storage and independent verifier stages occur outside
the solver contexts. Setup, seed generation and verification are not optimized
by the new selector.

## Bounded measurements and interpretation

The same 0.5-second heartbeat, 32-event journal and 256 KiB snapshot cap apply to
both arms. The public detached envelope statistics have exactly 15 scalar fields:
enabled, calls, completed_calls, input_pieces, arrangement_cells, selected_cells,
pair_tests, relation_intervals, event_updates, heap_pushes, heap_pops,
baseline_parent_visits, recorded_fallback_calls, max_input_pieces and
max_arrangement_cells. There is no per-piece log or per-pair I/O.

Both arms increment selection-start counters at the same point after shared
arrangement construction. Completed calls/selections are counted on successful
return. OFF parent visits count completed support rescans; ON work counters are
incremental. A live heartbeat is a nontransactional multi-counter sample, and a
TIMEOUT snapshot is censored. Only authenticated healthy normal completion
requires completed_calls == calls and consistent final projection pair counts.
A sampled `returned` status does not prove terminal health after a timeout.

An authenticated final result binds the final snapshot digest and its in-memory
observer health. A late fsync/heartbeat error cannot be hidden by an earlier
healthy disk image. Observer write gaps are gaps between persistence attempts;
provider counters are individually sampled. Nested operation timings must not be
summed. Activation time excludes earlier ALT construction; setup includes it.
No claim of pruning-only or asymptotic end-to-end speedup follows from these
counters. Repeated-order or broader-domain validation would be a separate plan.

## Fixed phases and success criteria

There are five sequential stages on one CPU: common preparation, envelope OFF,
fresh full replay, envelope ON, fresh full replay. The two exact phases are each
240 seconds, with a total declared exact allowance of 480 seconds. Preparation
and arm whole-process wall/CPU caps remain 600 seconds; verifier wall/CPU caps are
180/120 seconds; child address space is 8 GiB; supervisor CPU is 90 seconds.
The phase clock includes final durable storage and worker finalization, rather
than granting extra grace after a solver return.

Operational admission requires all declared stages, source/policy identities,
cleanup, receipt statuses, hashes and fresh verifications. Exact completion is
separate: both SUCCESS arm receipts must authenticate a terminal attained-optimum
or unattained-infimum payload, agree with fresh replay, have healthy final
observers, and agree on the exact completed answer. A valid TIMEOUT remains
feasible-only evidence. Read `both_authenticated_complete` and
`completion_outcome`; the CLI exit status alone reports operational admission.

Original 120-second and projection240 outcomes remain intact. This gate does not
pool historical timings, launch another budget/domain/order, or run a holdout.

## Commands after independent review and source freeze

Use the matching installed Python in the immutable reviewed checkout without a
source override. Keep outputs outside the source closure.

```sh
OUT=$(mktemp -d ../envelope-sweep240-XXXXXX)
CPU=$($PY -c 'import os; print(min(os.sched_getaffinity(0)))')
$PY -m experiments.envelope_sweep_gate_v1.run --freeze \
  --input-directory ../recovery_inputs --output "$OUT/manifest.json"
SHA=$(sha256sum "$OUT/manifest.json" | cut -d' ' -f1)
taskset -c "$CPU" "$PY" -m experiments.envelope_sweep_gate_v1.run --gate \
  --manifest "$OUT/manifest.json" --manifest-sha256 "$SHA" \
  --output "$OUT/gate" --cpu "$CPU"
```

Tiny/mocked tests, never the original graph:

```sh
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -m unittest test_envelope_sweep_gate -v
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -OO -m unittest test_envelope_sweep_gate -v
```
