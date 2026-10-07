# Exact query finalization over a shared immutable DAG

Ordered traversal can finish before the complete verifier returns. The legacy
finalizer then hashes every expanded query, including its whole ancestry map.
A repeated shared closure is serialized again at every query occurrence. The
new optional finalizer preserves that exact flat canonical JSON hash while
avoiding repeated JSON encoding of shared node records.

## Ownership, bytes and limits

`QueryDagEncoder` first freezes/copies the complete query list into an owned,
immutable DAG. Every cached object remains alive through that owned root.
Externally backed mapping proxies are copied. Caller mutations and aliases cannot
change cached bytes. The old `query_digest` remains the differential reference.

Top-level field order, key escaping, numeric/string tokens, delimiters, query
order and duplicate occurrences are unchanged. Every expanded byte still reaches
the same SHA-256 in the same order. This does not replace the hash with a Merkle
root or omit ancestry. The encoder caches canonical node bytes, shared ancestry
ID lists and the trusted case. Nonobject fields and oversized/budget-limited
subtrees fall back to the unchanged canonical encoder. Exact rational strings
remain strings, including values larger than ordinary integer conversion limits.

Stored canonical bytes are capped at 512 MiB, each entry at 4 MiB, and retained
key-order tuples at 32 MiB. A prospective entry uses a bounded buffer and never
causes an oversized full subtree to be materialized. Admission rechecks the
remaining budget after yielding; it reserves before insertion. An interruption
can conservatively waste a reservation but cannot insert uncharged bytes.
Snapshots distinguish actual stored bytes from reserved bytes. These caps cover
byte payloads/key tuples, not every Python index object or transient allocation;
the existing coordinator AS/RSS guard remains authoritative.

The helper reports logical expanded bytes, encoded bytes/chunks, cached bytes
emitted, hit/miss counts, cache occupancy and distinct ancestry maps. Even perfect
encoding reuse cannot avoid hashing the logical expanded byte stream. Those
measurements determine whether the existing flat protocol is still practical.

## Unchanged checker and opt-in finalizer

`shared_replay_cached` uses the existing RealCoalescedReplay for family, physical
and ordered checks. Its CheckedTrace class, query contents, summary protocol and
query hash match the old verifier, apart from observational elapsed time. It
freezes the query DAG once before hashing, then returns that same owned snapshot.
The original shared_replay implementation remains available as the reference.

The complete parallel runner defaults to the original finalizer. An explicit
`--shared-query-digest` enables the cache and binds that choice into the resource
context and run binding. The parallel summary adds cache metrics; the underlying
structural/query/receipt protocols are unchanged.

For the first measurement, use `--query-finalization-profile` with the reviewed
source plan and existing original capture/return pins. It enables the cache,
revalidates family checks and executes unchanged traversal. Only after traversal
returns does its fixed 180-second timer start. It counts trace hashing, immutable
query freezing, query hashing, summary creation and final container freezing.
The entire attempt remains capped at 480 seconds under the unchanged group
resource limits. It stops before callback receipts and query-index publication.
The report always says acceptance=false, structural_verified=false and
literal_G8_closed=false, even if the observed finalizer returns successfully.

```sh
--batch-kernel interval-join-v1 --query-finalization-profile
```

Use a fresh attempt and a source-renewed plan. No solver or capture rerun is
needed. A full replay retry is a later, separately admitted step after this
measurement. Tiny tests cover exact bytes, mutation/alias isolation, fallback,
interleaved consumption, complete mock-query equivalence and timer restoration.
Cloud checks currently use Python 3.12; the declared Python 3.11 server preflight
remains required before the real diagnostic.

## Full cached run progress and exact remaining bytes

A full `--shared-query-digest` run now measures canonical lengths once over the
owned DAG before hashing. Container lengths are memoized by owned identity;
scalars use the same JSON spelling, including Unicode escapes and signed zero.
It produces exact total and per-query prefix lengths without expanding repeated
ancestry. Remaining bytes are computed from those totals and the emitted prefix,
not from an average query size. These counts are observations, not a new proof
condition or a runtime-completion guarantee.

The existing 1,800-second full-run limit and all memory/disk limits remain. Full
cached runs publish immutable progress snapshots at phase boundaries and at most
once per 60 seconds during query hashing and callback/query-index output. There
are at most 48 records, each at most 16 KiB, plus an exact progress index. Together with the existing 13 output files,
this stays below the unchanged 64-file runtime inventory limit. The
existing evidence writer accounts and cold-verifies them, including snapshots
written while a larger receipt file is streamed. The complete output inventory
checks the contiguous record sequence and typed index. Progress cannot close a
mathematical gate; missing callbacks or a timeout still leave replay incomplete.

The full command uses `--batch-kernel interval-join-v1 --shared-query-digest` and
omits both diagnostic-profile flags. No additional 180-second diagnostic is
required by this instrumentation. A renewed source plan and separate run
admission are still required.
