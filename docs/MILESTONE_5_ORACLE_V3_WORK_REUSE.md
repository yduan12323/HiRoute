# Opt-in independent oracle v3

The v2 source stays byte-for-byte unchanged as the differential reference.
The new module is not enabled by any default checker or formal replay entrypoint.
It adds no numerical tolerance, grid, pruning rule, changed domain or new gate.

For exact_family_equal, v2 constructs a coverage-certificate cell and discards
it before comparing the exact family signatures. V3 omits that unused work.
Both traverse the same complete endpoint/intersection arrangement and compare
the same minimum time and attainment for each full family key on every cell.
V3 retains the arrangement once and returns its length; v2 computes it again.
Valid inputs therefore have the same return value or rejection payload.

Optional MemoizedOracle owns a cache for one caller/run. Complete canonical
bytes of both ordered piece lists and the operation name identify an entry;
keys include every endpoint/flag, affine term, chi, rho, pi and physical state.
There is no digest collision assumption or cross-family partial key. Failed
checks are never cached. Exact-equivalence results are integers. Continuation
certificates use the unchanged v2 computation and are stored as immutable bytes,
then decoded on each hit so callers cannot mutate future results.

The defaults bound retained serialized keys/results to 8 MiB, each entry to
1 MiB and the entry count to 128. Oversized entries bypass the cache. These are
stored-wire bounds, not a claimed exact Python heap quota; the existing process
memory guard remains necessary. Cache state and hit/miss counts are explicit.

Eight tiny tests cover 300 seeded exact-cell differential cases, endpoint and
attainment discontinuities, singleton/disconnected domains, metadata/order
changes, rejection payloads, certificate detachment, eviction and bypass.
No real C01 replay or throughput claim follows from these tests. The next
measurement should use the same immutable capture and diagnostic budget, with
this opt-in version explicitly pinned, before default integration is considered.

Retained-byte accounting is derived from the bounded actual entries rather than
a separately updated counter, so asynchronous interruption between cache writes
cannot leave a stale admission total. An opcode-boundary regression interrupts
after insertion and verifies safe reuse. Diagnostic maximum key/certificate byte
counts describe only calls reached in that bounded observation; they do not bound
unseen jobs or transient Python/JSON memory. Future parallel admission must size
each submitted job and enforce its own explicit resource cap.

If complete-key serialization is unavailable (for example, Python's configured
integer-to-string digit limit on a very large derived rational), validation
bypasses the cache and uses the unchanged scalar computation. This does not
change global interpreter limits or turn a cache failure into mathematical
rejection. Memory/resource failures remain governed by the process profile.
