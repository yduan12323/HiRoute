# Selected physical replay boundary

`replay_selected_witnesses(admitted, registry, requested, emit, *, deadline, before)`
accepts an actual `AdmittedSuffixPopulation` with its genuine checked family,
and a `CheckedRegistry` whose `block_reports()` are available after cold
reconciliation. A scheduling-only registry fails. The registry population must
match the admission. The function never certifies a complete query or G8.

`requested` maps each integer logical ordinal to `{descriptor, result}`. Every
descriptor is regenerated from `population.descriptors(ordinal, ordinal + 1)`;
the full logical identity and its digest must match. Only attained, primary
unattained and secondary unattained mathematical results request physical
witnesses. A selected segment can lose its encompassing block; the selected
full model record is replayed regardless of the block winner.

Each selected source entry receives one additional archive pass after existing
receipt reconciliation. Registry entries with no requested models are skipped, relying
on the already reconciled loser dependencies. Consumed source context, exact
compressed bytes, source row positions and canonical row-plus-newline hashes
are retained. Ordinary completed windows, the fixed seed continuation, and
admitted `suffix_window_recovery` entries are supported. Seed references resolve only through the entry's independently
retained dependency pin to one full old model row; the entire old archive is
consumed and authenticated. Recursive and unknown recovery grammars fail.

For generic recovery, the reader consumes the current entry's independently
pinned canonical `recovery-plan.json` dependency. Its exact predecessor paths,
archive modes and chronological contexts must match the current proof header's
committed history. Every ancestor is read once in chronological order, including
ancestors without a requested leaf, and its entire compressed bytes are hashed.
A retained reference names a full `model_certificate` in the original failed
window or an intermediate recovery. It never resolves through another retained
reference. The selected row index, canonical row hash, context, descriptor,
verification result and direct leaf provenance must all agree. Current full
certificates take the same fresh physical verification path.

Each predecessor retains its explicitly admitted `finalized` or
`interrupted-prefix` policy. Interrupted reads use the exact pinned path,
including `.part`, and must reproduce the admitted gzip EOF/partial-row state.
Finalized history requires its footer, whose `complete` flag may be true or
false: a failed runtime may have completed its proof stream. That flag cannot
grant successful-runtime authority. The existing recovery receipt admission
remains responsible for the actual successful current runtime return, reviewed
source, complete losing-proof dependencies and registry registration authority.
The adapter neither re-admits failures nor changes receipt or numerical rules.

The unchanged `calibration.verify_model` independently checks exact certificates
and physical attained or nonattained approaches. Its actual mathematical result
must equal the request. Its fixed epsilon approach contract is preserved;
mathematical query-bound comparisons do not imply that a particular lifted
approach point violates the same bound.

`emit` receives one detached receipt at a time, marked `provisional: true`, with
ordinal, descriptor, result, model/record hashes, complete selected source-row
ancestry and the actual fresh calibration receipt. The helper retains no full
certificate collection. Streamed rows become eligible for the caller's
transaction only after a successful return. Any callback failure, cancellation,
late corruption, missing row, dependency conflict or deadline failure leaves no
completed return. The final detached return contains compact per-ordinal hashes
and fully consumed archive pins/summaries, with all full-query/G8 flags false.
`physical_request_rows_sha256` commits to the canonical persistence array sorted
by integer model ordinal, matching the query planner; final assembly must bind
that exact request commitment before promoting streamed receipts.

Resource limits are hard, with no upward override:

- At most 8,192 distinct requested ordinals.
- At most 16 MiB for the canonical persistence-array representation of requests:
  `[{model_ordinal, descriptor, result}, ...]`, including brackets and commas.
- Existing `ArchiveReader` limits: 512 MiB compressed, 512 MiB raw, 8 MiB per row,
  64 KiB I/O/decompression chunks, regular files without symlink traversal.
- At most 32 recovery predecessors and a 1 MiB canonical recovery plan. Each
  recovery entry's entire historical archive set has cumulative 512 MiB
  compressed and raw limits; each read is limited to its remaining raw budget.
- Explicit finite absolute monotonic deadline and `before` checkpoints around
  I/O, checking, callback delivery and completion.
- At most 30 seconds for each descriptor validation and each selected exact
  certificate/physical replay through the existing non-nesting verification
  timer. Run on the main thread without another active timer.

Exceeding a resource limit aborts this attempt. It never becomes a mathematical
exclusion. The complete C01 planning bound of 3,232 family/action segments fits
the request-count limit. External orchestration must still enforce cumulative
disk/RSS and publication budgets; this helper does not claim those controls.
No LP optimizer, server, real evidence archive or publication is involved in
its focused tests. Test receipt admission is explicitly protocol-only, while
the tiny checked families, exact certificates and physical checks are genuine.
