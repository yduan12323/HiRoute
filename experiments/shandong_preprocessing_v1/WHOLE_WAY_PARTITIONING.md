# Bounded whole-way parser recovery

This is an implementation-only memory repair for the disclosed validation run.
It does not authorize a real run or alter the existing source, registry, deadline,
resource envelope, access/road policy, or experiment acceptance conditions.

## Frozen production settings

The graph phase uses the exact previously filtered `highways.pbf`. The literal
filter chain, original raw tags and complete ordered references are unchanged.
Production parameters are source-frozen: at most **50,000 references and 10,000
whole ways per parser child**, pinned **Pyrosm 0.13.1**, `out_of_core`, one worker.
These are not geographical regions. A way is never divided, even at repeated
nodes, loops, or chunk boundaries. A single way larger than the reference bound
fails explicitly; it is never truncated. Every node and way ID in the source
must be positive, unique, and strictly increasing. Unordered/history inputs and
relations fail closed. The native `osmium getid -r` operation retains each entire
selected way and its reference closure, and `check-refs` runs before parsing.

Each child exits before the next starts. Thus the installed OOC parser's internal
all-node concatenation is bounded by this chunk's reference count, rather than
the complete province. Node and reference payloads are on the stage's owned disk
scratch, not a tmpfs. SQLite uses a 16 MiB page cache and file-based temporaries;
Arrow readers and writers use 16,384-row batches. The final sorted used-node ID
array is O(global used nodes); no global tag or geometry dataframe is built.
Final original `IgraphRoadGraph` validation loads only routing columns, after all
parser children exit. Existing whole-process-tree RSS, address-space, CPU, wall,
thread, and cleanup guards remain authoritative; the chunk bounds are not a
claim that arbitrarily large individual tag strings have constant byte size.

## Exactness argument

1. Pyrosm network segmentation consumes one original way and its coordinates.
   Installed `frames.pyx` invokes `calculate_geom_array_length`; installed
   `distance.py` computes each segment's haversine distance and rounds to 3
   decimals. No global projection or geometry rewrite is introduced here.
2. The unchanged policy, speeds, directions, geometry reversal, travel times and
   original-way shelter proof are evaluated by `normalize_network` itself.
   The new default-false `allow_empty` only permits a locally empty result after
   existing unknown-class/policy checks. Global empty output remains an error.
3. Each complete way occurs in precisely one contiguous increasing-ID chunk.
   Canonical per-chunk stable sorting by way/source/target/direction, followed by
   chunk concatenation, is the identical global stable order, including ties
   within repeated segments of a way. Dense edge IDs are assigned only after
   that concatenation. Shared node IDs are unioned and globally sorted; dense
   node IDs and endpoint indices are assigned from that single global order.
4. Shared parser-node coordinates must agree exactly. Duplicate parser IDs
   within a chunk fail. Source duplicate node IDs fail before partitioning.
   All returned parser nodes, including those unused by retained edges, enter
   the unique global node union, so `unused_parser_nodes` is not a sum of local
   counts. Other audits count disjoint ways/segments/directions and are additive;
   nodes and directed edges are calculated globally.
5. Policy dataframe type evidence is collected before access or invalid-length
   rows are discarded. This matters when an excluded policy record introduces
   missing values or when a zero-length-only way is the sole non-null value for
   an attribute. Global Parquet column types reproduce canonical pandas
   inference, rather than inferring types solely from surviving chunk rows.

Parquet row-group layout differs from a single global dataframe write. The
contract is exact ordered table values, types, WKB bytes, costs and audit, not
byte identity to the old parquet file. Repeats with the same frozen chunk settings
remain deterministic. No roads, components or policy exclusions are added.

## Worker boundary

The production caller is still the gated supervised `phases.graph`. The child
CLI requires an inherited anonymous pipe bound to parent PID, exact PBF and
routing paths and SHA-256 content identities before reading parser input. A
standalone CLI invocation without that capability fails. This is a cooperative
internal-worker boundary, not an assertion of isolation from hostile code with
full Python execution rights. The Python coordinator is also callable by the
explicitly authorized small synthetic qualification tests.

## Qualification

`tests/test_partition_normalization.py` checks empty-chunk policy error behavior,
exclusion/invalid-length audit retention and child capability rejection.
`tests/test_way_partition_semantics.py` is an opt-in pinned-parser synthetic
integration gate. Run with `HIROUTE_PYROSM_QUALIFICATION=1`, `OSMIUM_BINARY` and the
pinned runtime/library paths. It checks exact ordered pandas tables (including
dtypes), WKB, costs and complete audit against single-parser canonical results,
as well as bad IDs, oversized whole ways, missing references, globally empty
results and unknown classes in an otherwise excluded chunk. Full real-graph
execution still requires the separate root-reviewed source/protocol freeze.
