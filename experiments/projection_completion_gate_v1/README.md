# Separately declared projection 240 completion gate

This is a new, prospective 240-second exact-phase experiment. It does not modify
or reinterpret either arm of the recorded 120-second projection-support trial.
A solver-return heartbeat without an authenticated worker result remains a
TIMEOUT, even if the search frontier was empty when sampled.

## What changes

Only the fixed exact-phase allowance changes from 120 to 240 seconds. Both matched
projection OFF/ON arms retain q10 ALT, target routing, terminal-energy screening,
skyline, onward ALT, remaining-charge ON, original OD10 N32 membership/query,
original Hmax26, identical fresh double-replayed seed and the same bounded cache.
Envelope sweep is not enabled. The fixed five stages remain common preparation,
OFF search, fresh full verification, ON search, fresh full verification.

All other resource caps stay unchanged: 600-second preparation/arm wall and CPU,
180-second verification wall/120-second verification CPU, 8 GiB child address
space and 90-second supervisor CPU. Arms run sequentially on the same CPU.
The exact-phase clock starts at the existing post-setup marker and includes
solver return, final durable-incumbent storage/replay and result finalization.
It is not a solver-only timer and is not an extra grace period added after expiry.

The shared supervisor gains one explicit keyword, `exact_phase_seconds=120`.
Only exact integers 120 and 240 are admitted; bools, floats and other values fail.
The 240 choice requires a matching closed manifest with every other limit
unchanged. Existing gate defaults and their 120-only phase validator are retained.
The new module has its own 240-only receipt validator. There is no global mutation
of an old runner, automatic retry, larger domain, further budget increase or
holdout run. Negative and inconclusive results are retained.

## Reuse and binding

The domain inherits the reviewed projection setup, algorithm selection, observer,
context scoping and independent-verifier behavior unchanged. Inner support_off/on
arm names and their configuration are never rewritten. Its existing activation
receipt and progress format retain the explicit projection-support inner schema.

A separate completion schema/policy is layered into the durable domain/source
binding and full result. A bounded outer completion-admission artifact records
that policy, manifest digest, unchanged inner configuration and inner activation
receipt digest. Outer admission is checked before invoking the existing inner
q/runtime/support validators. Fresh full verification reconstructs the same
portable two-layer binding without reusing the live search context. Artifacts
from the 120-second gate, the other arm or another completion policy are rejected.
The new source closure includes both adapters and the explicit supervisor hook.

## Completion criterion

Operational admission means all five declared stages, phase identities, cleanup,
artifact hashes and independent verifications passed. It does not imply the
solver completed. `both_authenticated_complete` is a separate result field and
is true only when BOTH arms have:

1. A SUCCESS supervisor receipt for the declared 240-second phase.
2. A hash-authenticated final result artifact, with the outer/inner policy,
   admission and final progress identities intact and a healthy final observer,
   plus an attained-optimum or unattained-infimum status and its exact payload.
3. A fresh full verifier whose accepted key and result status match that artifact.
4. Matching completed exact answers across arms.

A missing final result, a mismatched replay or an unhealthy final observer fails
admission. A valid TIMEOUT can retain feasible-only operational evidence while
`both_authenticated_complete` stays false. A last snapshot saying returned never
substitutes for the result artifact. No later diagnostic can upgrade an old
TIMEOUT. The command's exit status reports operational admission; always inspect
the separately recorded completion outcome before claiming exact completion.

Inherited projection counter conservation is required only for authenticated
normal completion. Live timeout counters remain censored/nontransactional.
Observer/write clocks are partial overhead measurements; timings are nested and
inclusive. Activation time excludes earlier ALT construction, while overall setup
includes it. All prior scientific and historical accounting limits remain.

## Commands after review and freeze approval

Use the matching installed Python in the reviewed immutable checkout without
source override. Set `PY` to it; keep outputs outside the source closure.

```sh
OUT=$(mktemp -d ../projection-completion240-XXXXXX)
CPU=$($PY -c 'import os; print(min(os.sched_getaffinity(0)))')
$PY -m experiments.projection_completion_gate_v1.run --freeze \
  --input-directory ../recovery_inputs --output "$OUT/manifest.json"
SHA=$(sha256sum "$OUT/manifest.json" | cut -d' ' -f1)
taskset -c "$CPU" "$PY" -m experiments.projection_completion_gate_v1.run --gate \
  --manifest "$OUT/manifest.json" --manifest-sha256 "$SHA" \
  --output "$OUT/gate" --cpu "$CPU"
```

Tiny and mocked integration tests:

```sh
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -m unittest test_projection_completion_gate -v
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -OO -m unittest test_projection_completion_gate -v
```
