# Exact endpoint join for the interval-sweep checker

The optional `interval-join-v1` kernel (independent_oracle_v6) removes a measured
false resource bottleneck. The previous kernel rejected a 2,481,444-pair Cartesian
product before construction, although only 389,836 domain intersections were
nonempty. This was an incomplete computation, not a mathematical rejection.
The v2 and v5 reference kernels and v5's 250,000-interval limit remain unchanged.

## Exact join and certificate preservation

For each energy endpoint, process open ends, closed starts, closed ends, then
open starts. Maintain separate active index sets for each physical state and
input side. At a start, pair with opposite-side active occurrences. For an
antichain, pair with earlier active occurrences in the same list. Each pair is
emitted exactly once, at its later start. Intervals touching at a point pair if
and only if both contain that point. Closed singleton domains participate only
at their point; empty domains never enter. Duplicate occurrences retain their
original distinct indices.

Any omitted pair has different states or an empty domain intersection, so it
cannot contribute a dominance interval. The exact affine/attainment predicate
and interval-sweep states, minimum-index heaps and cell serialization remain the
reviewed v5 implementations. All original arrangement cells are emitted. The
certificate bytes and first mathematical failure therefore match v2/v5 whenever
both computations complete. Only resource-failure admission differs.

Sorting requires linear endpoint storage and O(n log n) endpoint comparisons;
active support is linear in input pieces. Candidate work counts only emitted
nonempty same-state overlaps and stops after 2,000,000. No complete Cartesian
pair collection or decoded capture registry is held in a scalar worker.

## Explicit measured limits

The new kernel retains at most 450,000 intervals, separately for coverage and
antichain. The old kernel retains its original 250,000. Other bounds remain:
20,000 pieces, 500,000 line pairs, 1,100,000 arrangement cells, 1 MiB per support array,
64 KiB hashing chunks, 8 MiB job and 32 KiB response, and 1 GiB hard worker AS. The
interval count does not bound arbitrary rational-object heap size; the hard AS
and runtime limits remain authoritative. Exceeding any guard is incomplete.

For the pinned 11840 job, measured counts give the conservative coverage bound:
3,180 supports + 389,836 nonempty left/right overlaps + 4,122 equal-full-key pair
count = 397,138 registrations. Unequal full keys permit at most one dominance
direction; equal keys permit one extra. The measured right list has 1,374 distinct
pieces and 1,560 overlapping unordered domains, with zero overlapping equal-full-
key pairs, so at most 1,560 antichain registrations. These are count bounds for
that fixed payload, not a guarantee for unseen jobs.

## Fixed pilot and later full replay

`recorded_real.join_profile` accepts only the already dispatched 11840 payload,
including its fixed byte SHA/size, batch hash, capture context, old kernel and
canonical encoding. It changes only the serialized kernel field and retains
both source and candidate job hashes. It uses the existing 60-second kernel
budget, 90-second absolute profile and 1 GiB worker cap. Its report always has
acceptance=false and structural_verified=false. No extraction or solver runs.

```sh
python -B -m experiments.time_cut_v2.recorded_real.join_profile \
  --job "$PINNED_11840_JOB" --source-commit "$REVIEWED_COMMIT" \
  --source-sha "$REVIEWED_SOURCE_SHA" --cpu 0 --attempt-dir "$FRESH_ATTEMPT"
```

The complete parallel runner retains its sweep default. A separately admitted
run may select `--batch-kernel interval-join-v1`; that identity binds its runtime
context, run binding, all jobs/results/ledger and final summary. The same complete
node/physical/trace/callback/query obligations apply. A failed worker now retains
its exact pending job identity and reported response hash/error in the partial
ledger. A successful ledger gains no failure field. The failure report is
observational and cannot establish a mathematical conclusion.

Focused tests cover exact endpoint combinations, singleton/empty/duplicate
supports, 400 seeded full certificates and first-error comparisons, caps, complete
serial-versus-parallel mock paths, kernel identities and fixed-payload negatives.
The real 11840 pilot must complete before any full replay retry is admitted.
