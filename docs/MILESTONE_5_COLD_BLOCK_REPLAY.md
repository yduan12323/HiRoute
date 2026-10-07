# Cold block-certificate replay

This code-only milestone adds a restart reader for the existing
`hiroute-suffix-block-proof-archive-v1` JSONL/gzip format. It does not run an LP,
start a server job, certify an entire query, or close literal G8. The current
helper accepts at most four independently declared blocks and 1,024 models.

## Caller obligations

Supply a fresh genuine `CheckedBundle` from independent family verification,
the exact independently admitted block descriptors, and their admitted source
context. Do not obtain the authoritative declarations or source context from
the archive header. Existing population admission and selection remain
separate prerequisites; this helper does not manufacture a `CheckedTrace` or
replace those checks.

Pin the exact compressed snapshot's SHA-256 and byte size through its trusted
evidence manifest. For an interrupted prefix, pin the actual retained prefix,
not the expected hash of a completed file. A footer's own claims are never an
authentication source.

```python
from experiments.time_cut_v2.recorded_real.archive_reader import ArchiveReader
from experiments.time_cut_v2.recorded_real.block_replay import replay_blocks

reader = ArchiveReader(
    archive_path,
    compressed_sha256=authenticated_sha256,
    compressed_bytes=authenticated_size,
    allow_incomplete=False,
)
receipt = replay_blocks(
    reader, fresh_checked_bundle, admitted_blocks, admitted_source_context,
    deadline=absolute_monotonic_deadline,
    before=resource_guard,
)
summary = receipt.summary()
for certificate in receipt.certificates(block_id=2687):
    # Full original descriptor, ordinal, record and checked receipt survive.
    # Recheck against a fresh admitted context before a later certificate join.
    ordinal = certificate['descriptor']['ordinal']
```

`ArchiveReader` is single-use. Its rows are provisional; `summary` is `None`
until full exhaustion authenticates the consumed compressed bytes. Reads and
decompression output are bounded to 64 KiB per operation, compressed and raw
totals to 512 MiB each, and each newline-terminated row to 8 MiB. The reader
rejects symlinks in the path, nonregular files, duplicate keys, nonfinite or
noncanonical JSON, corrupt gzip, trailing bytes and concatenated gzip members.
There is no compression-ratio cap.

Explicit `allow_incomplete=True` permits an unfinished gzip prefix and an
unfinished last JSON row. That row is counted in raw bytes/hash and reported
as `trailing_partial_row_bytes`, but is not yielded. Any malformed complete
row still fails the entire replay. A completed gzip must contain canonical
newline-terminated rows and the full archive grammar. No row bytes may follow
the terminal footer, even in incomplete mode.

## What the receipt means

Every accepted record passes the existing exact regime checker again. Exact
original ordinals, descriptors, source/job identities, checked-record hashes,
block coverage, aggregates and immediate completion checkpoints are bound.
Winning physical witnesses are rebuilt and checked independently, and any
retained physical receipt must agree except for diagnostic timings. Empty
aggregates cannot claim physical witnesses.

No receipt or reusable block is returned before the full pinned snapshot has
been consumed. An error in a later row, the compressed pin, exact checking or
physical replay invalidates the call. Resource guards cover bounded I/O and
decoding; exact and physical checks use the existing deadline mechanism,
including its late-exit check.

Only complete, checkpointed, freshly checked blocks appear in
`reusable_block_ids`. `coverage` separately records unresolved and unsubmitted
ordinals. `certificate_refs` lists each valid model's original ordinal/block,
zero-based archive row index (header is row zero), SHA-256 of that exact
canonical JSON row **including its final LF**, and current exact-check receipt.
These references are bound to the consumed compressed snapshot in `archive`;
they contain no copied full records. `certificates()` also preserves detached
full individual certificates outside the summary, including good rows from
incomplete blocks, allowing a later exact restart to retain 254 good models
while filling two unresolved slots. It does not perform that later join or
promote incomplete coverage into a block certificate.

Historical footer claims remain diagnostic. An interrupted gzip trailer may
leave a decodable footer; such a receipt has
`historical_archive_finalized=False`. Historical runtime is never revalidated,
and `query_optimum_certified`, `full_population_complete` and
`literal_G8_closed` remain false.

## Validation and limits

Run the focused, optimizer-free suite with:

```sh
PYTHONPATH=src python -m unittest \
  tests.test_suffix_archive_reader tests.test_suffix_block_replay \
  tests.test_suffix_block_archive tests.test_suffix_block_certificates -q
```

All 45 tests pass, including original-writer roundtrip, sync-flushed checkpoint
recovery, source/model/certificate/physical tampering, gap and duplicate
rejection, expired/late deadlines, and an exact 254-of-256 salvage-and-recheck
exercise using repeated tiny hand certificates. These tests do not constitute
a cold replay of the real pilot. Its archive is not present in this checkout;
no real archive result or full-population completion is claimed here.
