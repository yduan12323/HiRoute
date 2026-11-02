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
old inclusive charges are retained. The real phase is initially UNRUN.

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
