# One failed original window

`suffix_window_recovery` is a separate entrypoint. It leaves the original
`suffix_window` argument parser, optional-null input digest, seed continuation,
and prior failed attempt unchanged. It runs once; it never launches the next
window or retries itself.

The CLI has exactly the existing suffix-window arguments plus required
`--recovery-plan PATH --recovery-plan-sha SHA256`. That SHA must be supplied
independently, after reviewing the exact failed-attempt dependencies. No real
attempt, source inventory, return, archive, or candidate ordinal is built into
the generic source.

## Pinned plan

The plan is canonical JSON plus one final newline, at most 1 MiB. Its exact keys
are `schema` (`hiroute-suffix-window-recovery-plan-v1`),
`historical_attempt_status` (`failed`), `original_selection`, `base_registry`, and
`predecessors`. Artifact pins have exactly `path` (absolute), `sha256`, and
`size_bytes`. Every file read is bounded and consumes the exact pinned bytes.

`predecessors` is oldest first, at most 32 entries and 512 MiB of compressed
archive bytes in total. The first is the original `suffix_window` attempt; every
later entry is a `suffix_window_recovery` attempt on the same original window.
Either archive mode can pin its exact retained common-writer path
`evidence/__partial/NNNN.part`; no file is renamed or repaired. A fully written
gzip can remain there if publication was interrupted. The archive mode binds
gzip completion, independently of whether its filename was published.
An entry has exactly these keys:

- `module`: full reviewed module name
- `source_commit`: full 40-character commit
- `source_sha256`: reviewed source inventory digest
- `attempt`: distinct absolute failed attempt directory
- `archive_mode`: `finalized` or `interrupted-prefix`
- `source_context`: independently linked original archive context
- `artifacts`: the pins described below

Every `artifacts` object contains all these keys. `request`, `run_binding`,
`selection`, `base_registry`, `source_policy`, and `archive` must have pins.
`summary`, `manifest`, `result`, `decision`, and `actual_return` may be explicit
JSON nulls when unavailable. `recovery_plan` and `cold_replay` are null for the
original attempt and mandatory pins for recovery ancestors. A recovery
ancestor's plan must equal the current plan with the predecessor list truncated
before that ancestor. The same reviewed source may recur.

The plan does not accept retry ordinals. Admission independently checks the base
registry, original physical/query/logical proof dependencies, source policies,
worker command and invocation origin, copied registry, original selection,
manifest links, and summary links. The original selection must be precisely the
first outstanding window of that base registry. Old result/decision/return
metadata is linked evidence only. A successful historical runtime return is
rejected, and no failed attempt is passed to `read_phase_result`.

Summary counts and authority-looking flags do not grant mathematical authority.
After a fresh genuine family admission, the recovery core consumes the pinned
archives, checks their explicit finalization policies, rechecks certificates,
and freezes the exact missing complement. Only that complement reaches model
construction. All original selected blocks receive rebuilt physical winners.
An empty complement creates no candidate stream and uses the core's explicit
exact-only transport.

## Guard and outputs

The original BATCH_REPLAY guard owns one 900-second total deadline, including
plan admission, family checking, cold replay, new candidates, and registration.
It retains the 20 GiB group ceiling, 16 GiB host reserve, 512 MiB evidence/raw
bounds, four 1 GiB candidate workers, 30 seconds and 12 passes per candidate,
128 MiB cumulative new candidate input, at most 32 original blocks / 8192
models, and disabled numerical cache.

The ten evidence files are `run-binding.json`, `batch-ledger.json`,
`family-summary.json`, `block-plan.json`, `base-registry.json`,
`window-selection.json`, `recovery-plan.json`, `cold-replay.json`,
`recovery-model-proofs.jsonl.gz`, and `recovery-summary.json`. The binding and
summary use the `hiroute-suffix-window-recovery` schema prefix. The context adds
plan/cold receipt hashes, a digest of the complete ordered cold history, the
immediate predecessor archive pin, and a digest of its source context. It does
not recursively embed ancestry inside each source context.

The new actual runtime return is preserved outside the raw attempt whenever the
remaining guard budget permits, even if the attempt failed. A late failure
always exposes the actual returned value and never invents persistence. A
successful new runtime is admitted through
`window_recovery_receipts.admit_completed_recovery`; only that typed receipt can
extend the registry. Missing or rejecting receipt admission leaves raw evidence
and the actual return available, with no scheduling authority. Registry and
external return publication remain exclusive and do not overwrite old files.

## Focused verification

Run from the checkout:

```
PYTHONPATH=src:. python -m unittest tests.test_suffix_recovery_plan tests.test_suffix_window_recovery_runner -q
```

These tests use tiny admitted family fixtures, hand metadata and fake transport.
They do not launch a real LP, consume a real archive, or publish a registry from
a numerical run. Exact certificate replay and completed-receipt integration
have their own focused tests in the recovery core and receipt adapter.
