# Generic original-window recovery core

`experiments.time_cut_v2.recorded_real.window_recovery_core` cold-checks one
independently admitted original window and joins only its exact missing proof
complement. It does not admit source policies, historical selections, runtime
returns or registry membership, and never interprets a failed run as a successful
run. Those checks belong to the guarded controller and receipt adapter.

## API and authority

- `ArchiveInput(reader, source_context)` pairs an existing single-use
  `ArchiveReader` with its independently admitted source context. The reader
  authenticates an exact compressed hash and size. Explicit `allow_incomplete`
  permits an independently pinned interrupted prefix, not a repaired gzip file.
- `open_recovery(ctx, blocks, history, *, deadline, before)` requires a genuine
  `CheckedBundle`, independently admitted original full descriptors, and a
  chronological nonempty history. It exhausts and authenticates every archive
  before returning a live `RecoverySession`. The initial archive uses unchanged
  `block_replay.replay_blocks(..., replay_profile='window32/8192')` semantics.
- `session.summary()` returns detached exact complement, original population
  hash, certificate provenance, and full consumed ancestor pins. It is an audit
  summary, not an input that can construct another session.
- `session.candidate_jobs(current_source_context)` filters original descriptors
  before the existing candidate and independent model builders. It is single-use.
  It constructs no new candidate inputs for retained ordinals.
- `session.records(current_source_context, outcomes)` independently rechecks
  every retained full certificate into a fresh `BlockCertificates` accumulator,
  then exact-checks actual new outcomes. It is single-use and source-bound to any
  preceding candidate iterator. Unresolved outcomes remain unresolved; invalid
  purported certificates abort without a successful footer.
- With an empty complement, call `records(context)` with no transport object.
  Completion is explicitly `recovery_mode='exact-only'`, `transport=null`, and
  `new_verified_models=0`. A fake empty transport is rejected.
- `publish_proofs(session, context, quota_writer, outcomes=None)` writes
  `recovery-model-proofs.jsonl.gz` using the unchanged bounded canonical JSONL,
  checkpoint sync-flush and gzip encoding.

Current and historical source contexts may be equal. Contexts are detached exact
JSON dictionaries, limited to the existing 16 KiB job context cap. The controller
must admit their values independently; archive content never authorizes a new
source. Prefer hashes of previous context/history in current contexts to avoid
recursively expanding contexts.

## New archive grammar

The distinct schemas are `hiroute-suffix-window-recovery-archive-v1` and
`hiroute-suffix-window-recovery-footer-v1`; fixed seed archives are unchanged.
The header binds full original descriptor digest, block ranges, exact candidate
ordinals/count, retained count, current source context, recovery mode, and every
ancestor in order. `previous_archive` is the immediate predecessor's byte pin.
Each history entry has `archive={sha256,size_bytes}`, original `source_context`,
`gzip_eof`, and `trailing_partial_row_bytes` from its authenticated reader.

Every retained disposition has exactly `kind`, `descriptor`, `verification`, and
`provenance`. Provenance contains the original full proof archive hash/size,
zero-based `archive_row_index`, `archive_row_sha256`, and original source context.
The row hash covers canonical JSON plus its terminating newline. A reference
always points directly to a full `model_certificate` row; references to references
are never emitted or accepted. Its result remains in `verification.result`, and
the full model/stages/result remain in the authenticated original leaf row.

Retained references precede new `model_certificate` or `unresolved_model` rows.
Complete blocks have immediate unchanged `block_certificate_checkpoint` records.
Missing outcomes have explicit `unsubmitted_model` records, followed by one
`block_report` per original block and the footer. Every accepted physical winner
is reconstructed from the genuine checked context with `calibration.verify_model`.
No inherited witness flag can certify completion. Invalid source, model, result,
descriptor, reference, duplicate ordinal, repeated pin, or lineage gap fails
closed. Only complete records in a permitted interrupted prefix contribute;
independently checked ancestral leaves survive interruption while writing the
next archive's references. A prefix never acquires a fabricated footer or gzip
success state.

The footer counts retained, new verified, total verified and candidate models
separately. Candidate completion requires actual clean/reaped transport and exact
candidate coverage. Transport input byte accounting must cover all received
jobs, stay within the cap, and equal received bytes whenever all submitted jobs
are accounted for. Unaccounted failed transport can retain its submitted byte
total without manufacturing missing outcomes. Query optimum, full population,
literal G8 and historical runtime authority remain false.

## Bounds and tests

The core accepts at most 32 blocks / 8,192 original models and an absolute caller
deadline no more than 900 seconds ahead. Exact checks have at most 30 seconds
within that shared deadline. Cumulative compressed and uncompressed history is
limited to 512 MiB. Before each archive is consumed, `ArchiveReader.limit_raw_bytes`
tightens its streaming raw limit to the remaining shared budget, including any
trailing partial row. The optional reader constructor `max_raw_bytes` cap can be
smaller; tightening never expands it. Default reader behavior and the existing
per-row limit remain unchanged.
New candidate input bytes are capped at 128 MiB. Writer raw archive/evidence caps
remain 512 MiB. The controller must run the existing four-worker transport with
1 GiB address space per child, 30 seconds / 12 passes per new model, and no cache.
The core does not launch workers or relax those runtime controls.

Tiny tests use genuine hand certificates, original ordinal gaps and fake
transport. Run without native optimization or real artifacts:

```sh
PYTHONPATH=src python -B -m unittest tests.test_suffix_window_recovery_core
```
