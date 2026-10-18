# Prospective q0 versus q10 dyadic ALT DEV gate

This opt-in, separately frozen gate tests whether finer certified travel-time
potentials help the observed OD10 N32 search bottleneck. It changes only the
explicit `time_quantum_exponent`: q0 uses 1 integer unit per second; q10 uses
1024. The selected native road paths still use the original binary64 graph.
There is no physical-model approximation or default solver change.

## Fixed domain and arms

Both arms use destination-target routing, terminal-energy screening, exact
skyline reduction, indexed onward ALT, and the remaining-charge region bound
ON. The shared bound is
`max(existing onward region bound, prefix travel/charge bound, B(k+1))`.
Original None/action-mask/effect coverage and engine-owned strict `>` pruning
remain unchanged. Equality stays live. Original OD10 N32 membership, query,
hierarchy and Hmax26 are checked rather than rewritten. One newly prepared
full-routing seed is double-replayed and supplied identically to both arms.
Context-specific runtime admission identities do not enter portable replay
binding; the stable q/configuration/source policy does. Cross-arm durable
artifacts are rejected; fresh full verification does not reuse search contexts.

The fixed five stages are common preparation, q0 search, fresh full verification,
q10 search, fresh full verification. Each search receives exactly 120 seconds
under the external phase deadline. Preparation/arm wall and CPU limits are
600 seconds; verification is 180 seconds wall/120 seconds CPU; child address
space is 8 GiB. Supervisor CPU is 90 seconds. Numerical stages run sequentially
on one selected CPU with the same bounded cache policy. No automatic N128,
repeat, 600-second search or holdout follows. No positive result is required.

## Quantum and receipt admission

Provider construction accepts only exact integer 0 or10. The gate checks the
actual provider's read-only q and units properties, records its full public
construction certificate and digest, and calls the public live suffix accessor.
No private numeric potential arrays are read.

The q0 certificate retains the byte-compatible integer-second v1 schema with
no new quantum fields. The q10 certificate uses the dyadic-second v2 schema,
exponent10, units1024 and the pinned scaled-nextafter/floor policy. Internal
labels/extrema are integer units; all provider/remaining-charge outputs are
exact Fraction seconds, including onward and singleton bounds.

Admission independently recomputes the suffix binding from certificate digest,
provider sources, destination, Site catalog and the q-specific suffix schema.
It must match the time binding inside the remaining-charge runtime receipt.
The certificate's source hashes, quantum policy and exact integer limit are
checked. The recorded origin suffix bound is recomputed from the certified
origin/destination labels with exact division by Q. Bool/float q substitutions,
unit changes, mixed certificates, stale runtime hashes, mismatched snapshot
policy and wrong origin conversions fail closed.

The reviewed remaining-charge activation checks are reused: exact common seed
H/J, original Hmax, B0/B(seed H)/B(original Hmax), positive stop cost, seed
sanity and diagnostic integer threshold. The threshold is recorded and never
used to shrink Hmax. Status/None semantics and snapshot echoes are validated.
The initial bounded observer includes quantum/certificate evidence and all
activation diagnostics so a successful write survives a later hard timeout.
A SUCCESS result authenticates both admission and final progress hashes plus
final observer health. TIMEOUT is censored, with terminal observer health
unknown even if the last snapshot says returned. All five stage identities,
phase budgets, cleanup receipts and fresh verifier results must pass separately.
Completed exact answers must agree.

## Interpretation

q10 need not strengthen every difference of independently recomputed landmark
labels. It does refine the origin-to-destination forward term when the landmark
is the origin. Measure B0/origin suffix, completed work, source/target routing,
wrapper costs and actual pruning. Stronger priorities can reorder work as well
as prune it; do not call a measured difference pruning-only causality.

The shared 0.5-second bounded heartbeat retains up to32 recent events and256 KiB
per snapshot. Active-operation and layer-checkpoint observations at timeout
are censored. Enqueue-time strict-prune opportunities are not actual engine
prunes. Actual checkpoint counters can lag an active layer. Timings are nested
and inclusive; observer overhead is only partially measured. Activation wall
excludes earlier ALT construction; overall setup is separately measured.
Maximum observed write gap is the gap between persistence attempts, and sampled
provider counters are not an atomic history transaction.

This is an incremental DEV diagnosis. Prior outcomes remain recorded, historical
accounting is not retroactively repaired, and final holdout remains unrun.

## Commands after review and freeze approval

Use the matching installed Python from a reviewed immutable checkout with no
source override; set `PY` to it. Keep outputs outside the source closure.

```sh
OUT=$(mktemp -d ../dyadic-alt-gate-XXXXXX)
CPU=$($PY -c 'import os; print(min(os.sched_getaffinity(0)))')
$PY -m experiments.dyadic_alt_gate_v1.run --freeze \
  --input-directory ../recovery_inputs --output "$OUT/manifest.json"
SHA=$(sha256sum "$OUT/manifest.json" | cut -d' ' -f1)
taskset -c "$CPU" "$PY" -m experiments.dyadic_alt_gate_v1.run --gate \
  --manifest "$OUT/manifest.json" --manifest-sha256 "$SHA" \
  --output "$OUT/gate" --cpu "$CPU"
```

Tiny tests, without recovered road inputs:

```sh
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -m unittest test_dyadic_alt_gate -v
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -OO -m unittest test_dyadic_alt_gate -v
```
