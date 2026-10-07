# Exact interval sweep for certificate coverage

This opt-in kernel addresses the measured hot-job structure: 260,569 reference
cells but only 259 input energy endpoints, with sparse active right support.
V2 remains the unchanged mathematical and materialized-certificate reference.
No solver, model, energy grid, pruning condition or certificate cell is changed.

## Correctness argument

1. For a fixed ordered pair p,q, static eligibility is equal physical state and
   rho_p < rho_q, or equal rho and pi_p <= pi_q. Within both energy domains,
   the remaining condition is an affine inequality tau_p(e) < tau_q(e), allowing
   equality exactly when p.chi or not q.chi. Intersecting these conditions gives
   one exact interval, possibly empty or a closed singleton.
2. Interval endpoints are input domain endpoints or affine-line intersections,
   all already present in the unchanged v2 arrangement. Before a singleton,
   closed starts enter and open ends leave; after it, closed ends leave and open
   starts enter. Thus the active edges and supports equal v2 at every singleton
   and every adjacent open cell.
3. Each target maintains the smallest original index among its active covering
   sources. This is exactly the first result of v2's ordered `next(...)` scan.
   Forward/reverse cover vectors and support indices therefore match v2. A
   missing cover is rejected at the same first cell with the same payload.
4. Antichain edges use the same pair intervals. The smallest active unordered
   pair (i,j), i<j, is exactly the first violating `combinations` pair in v2.
   Overlapping directions are reference-counted, preserving boundary ties.

The kernel reuses vectors only while their support and covering indices remain
identical. It still visits and emits **every original arrangement cell**, with
its original endpoint strings and singleton flag. It does not coalesce output
cells or replace certificate contents with a weaker statement.

## Exact streaming

`equivalent` materializes an ordinary detached certificate for tiny differential
checks. `equivalent_compact` hashes the complete canonical JSON certificate in
exact v2 key/array/cell order, including brackets and commas, while retaining only
current vectors and bounded encoded arrays. It returns the same counts and SHA.
The worker protocol already requires only those fields; the baseline worker
built the full body and discarded it. No formerly required check is omitted.

Hash-update chunks are at most 64 KiB, each cached array encoding at most 1 MiB.
Full rows are never accumulated by the compact path. Returned materialized cells
have separate list ownership, even when the sweep internally reuses vectors.

## Computational guards

The opt-in implementation bounds inputs to 20,000 pieces, coverage/antichain
pair construction to 2,000,000 pairs, distinct-line arrangement construction to
500,000 pairs, the completed arrangement to 1,100,000 cells, and registered
intervals to 250,000. The existing worker AS/time guard remains authoritative
for transient Python allocations. These are explicit resource limits, not
mathematical cutoffs: exceeding any limit raises `SweepResourceLimit` and leaves
the job incomplete. No truncated certificate is accepted. Counters record pair
intersections, dominance intervals, event points, vector states and emitted cells.

Six focused tests compare complete certificate bytes/hashes and first-error
payloads against v2 over 700 seeded cases, all endpoint/attainment combinations,
duplicates, full keys, disconnected/singleton domains and large coefficients.
They also verify bounded chunks, resource-limit behavior, detached list ownership
and reuse across irrelevant line crossings. Real performance remains unmeasured.

## Fixed extracted-job pilot

Only the hot-job command exposes `--kernel interval-sweep-v1`, restricted to
index 11835. It reads the existing extraction manifest and authenticates the
original v2 job bytes, then reconstructs a canonical job-v2 changing only the
schema/kernel fields. Both original and candidate SHA values are retained.
Workers pin that kernel in the existing versioned result/ledger contract. The
whole-capture profile does not expose this kernel.

The existing 60-second/1 GiB targeted profile reports native pair/interval/vector
state and emitted-cell counts, arrangement and operation timings. It avoids
per-pair wrapper calls for the sweep; that instrumentation difference is reported
and must not be hidden in a throughput comparison. No new extraction, solver or
whole-capture run is needed. Completion still has acceptance=false; compare the
full certificate count/hash and reviewed mathematical invariants before broader
use. The next remote command is the already reviewed hot-job profile command
with index 11835, `--kernel interval-sweep-v1`, the new reviewed source pins and
a fresh attempt/return path.
