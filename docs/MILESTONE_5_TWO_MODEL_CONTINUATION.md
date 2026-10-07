# Fixed two-model continuation

`experiments.time_cut_v2.recorded_real.block_resume` prepares a guarded
continuation of the failed four-block pilot. This change is code and tiny
hand-certificate tests only. It does not execute the real archive, run a native
LP, publish private inputs, or claim a new completed attempt.

The runner admits the original completed structural/query replay and logical
population using their existing separately retained returns. It rebuilds a
genuine family bundle, independently freezes the same 1,024 descriptors in
blocks **0, 1352, 2535, 2687**, then authenticates the consumed old selection,
summary, and compressed archive against fixed source constants. The old pilot
was failed; there is intentionally no old-pilot successful-return argument.

The archive pin is SHA-256
`e7371f1ec32492ff05a05907b52261d9d10ab20112be9222f5aad1d3eb8360cc`,
756,356 bytes. The pinned summary must report 1,022 checked certificates and
failed completion. The existing cold reader checks every retained certificate,
unresolved-model identity, complete block witness, and full archive grammar.
It must recover precisely the two unresolved ordinals **687940 and 687941**,
with no missing or additional unresolved identities.

Only those two descriptors reach the existing independent model builders and
four-credit persistent LP transport. Their models must match the fixed old
model hashes. There are at most two candidate jobs, 24 candidate passes, and
ten logical stages. The normal 30 seconds/model, twelve passes/model, 1 GiB
candidate AS, and 768 MiB candidate VmHWM limits remain. The existing
`BATCH_REPLAY` controller supplies the 20 GiB sampled group RSS cap, 16 GiB host
reserve, and separate 512 MiB supervisor. The phase has a 900-second absolute
deadline and a 512 MiB conservatively charged evidence subquota.

## Evidence and authority

The new `continued-model-proofs.jsonl.gz` uses the distinct
`hiroute-suffix-block-resume-archive-v1` schema. It is not an old-format archive
and is not accepted by the existing old-archive cold reader.

- Each retained certificate is checked again through a new `BlockCertificates`
  instance. Its disposition references the old compressed archive hash/size,
  original row index, original row hash including LF, and old source context.
  No fake candidate frames or new-source attribution are created for old rows.
- New successful candidates retain full model, stage tasks, certificates,
  result, checked receipt, and actual new-source candidate identity. Failed
  candidates remain unresolved; absent outputs are explicit unsubmitted rows.
- All four reports aggregate their complete original descriptors. Physical
  winning witnesses are rebuilt only after the two-job transport completes
  without late errors and reaps its processes. Missing, duplicate, foreign,
  invalid, or timed-out evidence cannot produce proof completion.
- `historical_attempt_status` remains `failed` and
  `historical_runtime_revalidated` remains false. New `proof_complete` and
  `complete` flags concern only the combined four-block proof. A new completed
  runtime still requires its own genuine successful `run_phase` return.
- `query_optimum_certified`, `full_population_complete`, and
  `literal_G8_closed` remain false in all cases.

The evidence set is `run-binding.json`, `batch-ledger.json`,
`family-summary.json`, `block-plan.json`, `pilot-selection.json`,
`cold-replay.json`, `continued-model-proofs.jsonl.gz`, and
`block-resume-summary.json`. Old inputs remain immutable dependencies; this
output alone does not contain their complete original certificates.

## Interface and tests

The CLI takes the existing `block_pilot` source/admission/resource arguments,
plus required `--old-archive`, `--old-summary`, and `--old-selection` paths.
Historical SHA-256 pins and byte size are fixed in reviewed source, not supplied
as runtime overrides. Use a fresh attempt directory and retain the separately
observed launcher output when an actual run is later authorized.

Focused optimizer-free validation:

```sh
PYTHONPATH=src:. python -B -m unittest \
  tests.test_suffix_archive_reader tests.test_suffix_block_replay \
  tests.test_suffix_block_archive tests.test_suffix_block_certificates \
  tests.test_suffix_block_resume -q
```

Continuation tests use five tiny original descriptors across the same four
block IDs, with two designated pending ordinals. They authenticate actual
temporary old-format gzip/selection/summary bytes, exercise source and
population reconciliation, verify exact retained/new provenance and physical
winners, and cover gaps, duplicates, source changes, failed candidates, late
transport errors, and late exact/physical verifier exits. Subprocess APIs are
blocked in those tests; model selection checks both builders with numerical
libraries unavailable.
