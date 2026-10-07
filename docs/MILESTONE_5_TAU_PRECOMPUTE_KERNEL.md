# Opt-in per-cell exact-time precomputation

The independent v2 oracle remains byte-for-byte unchanged. V4 computes tau(e)
once for each active input occurrence on each exact affine cell, then uses those
same rational values in the original dominance predicate. It preserves original
input indices, duplicate occurrences, forward/reverse first-cover scan order,
endpoint/attainment rules, rho/pi/state comparisons and the full arrangement.
Antichain checks preserve the same pair order and first rejection.

For valid exact Piece inputs, substituting a previously computed value of the
pure expression m*e+b cannot change a predicate. Thus each certificate cell,
first covering index, full certificate JSON bytes/hash and rejection payload
matches v2. There is no cross-cell cache, sorting, approximate arithmetic,
pruning, omitted cell or weakened provenance obligation.

Four focused tests cover 400 seeded complete comparisons/rejections, open and
closed endpoints, attainment, line crossings, disconnected domains, singletons,
full family keys, duplicate/support order and very large rational coefficients.
A call-count test proves tau evaluation is linear in active input occurrences
rather than repeated inside pair scans. These are correctness checks, not a
claim about real runtime improvement. The separate same-capture/hot-job
measurement remains required before reporting a speed gain.

## Versioned worker/profile selection

The default batch API continues to emit job/result-v1 and run the v2 kernel.
Only explicit `kernel='tau-precompute-v1'` emits job/result-v2 with that kernel
identifier inside the hashed job, returned result and final ledger. Each worker
also pins its configured kernel and rejects jobs naming another version. The
original Piece order and rational values are unchanged in either wire version.

The reviewed four-worker profile can select this candidate with
`--batch-kernel tau-precompute-v1`. Its group limits and 180-second post-decode
observation remain unchanged. Pull the reviewed source, recompute its full source
inventory hash, and use a fresh attempt/return path; retain every earlier profile.
No real run is authorized by this document and diagnostic completion still
confers no structural or numerical acceptance.
