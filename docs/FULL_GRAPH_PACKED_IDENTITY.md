# Complete graph packed identity gate

This stage checks representation, not road certificates or EV solutions. The
same known DEV query WD01/E18/schedule/N64 retains all 64 literal Sites, 65
sources, 65 targets and 4,225 directed pairs. The prior real source attempt
remains one UNKNOWN, 64 UNRUN and zero independently certified sources.

Prospective research cap: 900 CPU seconds inside the original 28,800, carrying
17,062.772892741. Allocations: fixed development/controller 240, tiny tests 120,
one full construction 180, one independent raw verification 240, close/tails
120. All failures and controller costs count. No repeated real attempt is
authorized by a resource failure. Ordinary software CI is separately reserved;
old inclusive charges are retained. These limits were recorded before real work.

## Writer and independent proof obligations

The writer creates disk BINARY node/edge rank maps from the prior immutable,
hash-bound full SQLite graph. A disk composite primary key orders all arcs by
(source rank,target rank,literal edge rank). Bounded positional buffers write
CSR sections; rational magnitudes use variable-length arbitrary precision.
The source DB is byte-hashed before/after and read through a read-only immutable
URI. There is no all-graph Python dictionary, shared denominator or source search.

The verifier parses the authoritative raw TSV itself into a NEW relation with
primary key (literal source,target,edge ID) and globally UNIQUE edge ID. Its
node union and both rank maps come only from this raw relation (or explicit
node input, preserving isolated nodes), never writer maps. It compares complete
literal pools in order and then joins its independently ranked raw rows against
the sequential packed arcs. Equal dense ranks imply equal literals because
both complete ordered pools have already been checked bijectively. Every exact
time and actual length is independently decoded and cross-multiplied against
the raw rational. All offset/range/cardinality/order checks are explicit.

Contiguous identity and magnitude arena checks reject gaps, overlaps, missing
or trailing bytes. The arc join plus raw UNIQUE constraint proves an all-edge
bijection; adjacency boundaries identify the source for every arc, including
empty outgoing lists. Zero-weight inputs are unsupported, positive self-loops
and parallel edges are retained. Site aliases are not merged. All required
source/terminal/Site anchors must exist. Raw and packed hashes are rechecked at
the end to reject changed inputs. A schema or producer hash is never the proof.

## Bounded resources and admission

Use single worker/thread, 1 GiB whole-process-tree RSS stop, 3 GiB available RAM
before each real phase and 2 GiB host-memory floor. Start with at least 12 GiB
free disk, retain a 2 GiB floor; new stage workspace cap is 10 GiB and each worker
output file at most 2 GiB. Maps, arc sorting and independent raw tracking each
have explicit 2 GiB SQLite file quotas. SQLite's global hard heap is 128 MiB,
per-connection cache at most 16 MiB, mmap zero and threads one.

Compared with the proposal, the validator uses a raw composite PK and sequential
join instead of reverse-edge arrays: this avoids repeated random packed reads.
Only the checked adjacency offsets are resident (8*(N+1) = 23,893,568 bytes for
this graph; explicit 64 MiB admission ceiling, resource stop rather than cropping).
SQLite temporary storage is MEMORY under the SAME global hard-heap limit;
unexpected TEMP B-TREE plans are rejected before real release, so no unlinked
external sort can escape a disk accounting guard. The bounded on-disk B-trees
are updated incrementally. Per-record and batch envelopes retain exact values
or stop, never round/truncate them.

These structural limits are not a measured RSS or runtime prediction. The
873,173,089-byte packed upper and previous construction/validation timings are
not new measurements. One guarded real construction/verification is released
only after fail-closed tiny tests and fresh host admission pass. Child CPU caps
150/210, phase reservations 180/240, preparation wall limits 300 each; query
limits and physics remain unchanged because no query is executed.

Bulk data, controller/failed attempts and receipts remain outside Git. See
configs/full_graph_packed_identity.json and tools/run_full_graph_packing.py.
Even a complete representation PASS leaves real shortest-path certification,
upper-witness replay, independent physical optimization and holdout uncompleted.

## Observed result

Producer `124b3014fa33c3c010cc4496e043b92ef85edd2d` was clean for both real
phases. Exactly one construction and one independent raw verification completed;
no earlier real source, graph scan or timed solver row was repeated.

| Phase | Worker CPU s | Wall s | Inclusive charged CPU s | Native peak RSS bytes | Sampled new-stage disk peak bytes |
|---|---:|---:|---:|---:|---:|
| Complete construction | 53.063139 | 56.606159 | 57.278456 | 56,475,648 | 1,348,218,458 |
| Independent raw verification | 74.564378 | 75.465311 | 79.810970 | 101,580,800 | 2,929,397,414 |

The 669,640,897-byte packed artifact has SHA256
`2c64f108db4dc97d916e82cc23567ff82e0c7514372c1a3562c965c9c0ffa603`.
All 2,986,695 nodes, 5,900,232 edges, exact time/actual-length values and 66
original anchors passed the independent raw join. Writer maps use 420,155,392
bytes, sorted arcs 258,371,584, independent raw tracking 1,581,170,688. Real query
plans used PK/covering-index scans and three PK seeks per joined row, with no
temporary sorting. Host available RAM stayed at least 5,268,373,504 bytes and
free disk at least 43,256,840,192 bytes during the real phases. Native and sampled
RSS are distinct; verifier sampled peak was 101,449,728 bytes. Caches were not
flushed, so these are preparation measurements, not a cold benchmark.

The raw TSV hash remains
`8076e850b096c5cf74f307ae7ad34c2aebd1f1e53c3c4d092234d40078a4c54d`;
graph identity remains
`00f983ee3fdcfb04fa1b6dc008b39ab73e30e384c9c264d2f8691ea7224f1601`.
Construction hashes its immutable old representation before/after. Verification
performs one authoritative raw parse plus one necessary final streamed mutation
hash, and packed hashes at admission/finish. No gratuitous full raw audit was
added. The observed 84-bit maximum is a component measurement, never a bound on
path sums, denominators or a license for fixed-width arithmetic.

Thirteen new contracts and sixteen prior packed contracts pass normal/-OO.
The initial supervisor sysctl restriction safely killed/waited its tiny child;
the initial SQLite URI attachment implementation error was fixed before real
release. Both failures and all costs remain. Twelve guarded commands / 24
recorded PID identities are terminal. An additional conservative two CPU seconds
for receipt/report bookkeeping is retained without rerunning any large input.

Final new charge **390.316884 / 900 CPU seconds**: 240 fixed, 10.200394 tiny,
57.278456 construction, 79.810970 independent verification, 3.027064 close.
Original total **17,453.089776741 / 28,800**, remaining **11,346.910223259**.
Preprocessing stays 652.040677976 / 900. Prior 325.696447 representation-stage
charge, old source timeout and all prior ledgers remain in the carried total;
reuse is not free and those charges are not added twice. Software CI is recorded
separately as authorized. Exact receipts are in the small committed
`full_graph_packed_identity_results.json`; bulk artifacts remain outside Git.

Decision: **PASS_COMPLETE_REPRESENTATION_IDENTITY_ONLY**. No shortest-path source
or EV solution has been certified. Real status remains 1 UNKNOWN / 64 UNRUN / 0
certified; the complete 65-source / 4,225-pair denominator is unchanged. This
closes the real representation/identity bridge, not independent real-scale
optimization, larger candidate coverage, performance targets or holdout.

The smallest proposed next gate is a separately admitted <=600 CPU seconds:
120 development, 60 tiny driver/quota tests, 150 one packed-source generation,
150 conditional independent check, 120 report/tails. Retain the existing
120-second component limits, source `3797700636` and all 65 targets. Add live
aggregate certificate/path/SQLite storage admission and durable completion
receipts before release. Necessary full-graph checker revalidation and all
serialization/hash costs count. Even success is one source only, with old
attempt/history preserved; no 64-source expansion or EV optimization is released.
No expected runtime, certification or budget fit is inferred from packing alone.
