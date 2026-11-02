# Bounded streaming exact road representation gate

## Actual outcome

**PASS for complete frozen graph representation/identity and tiny supplied-
certificate components only.** Independently validated2986695nodes and5900232
directed edges match the full original raw TSV. No real source tree, selected-
leg table, source certificate, physical upper-witness replay, optimizer or
holdout ran. All65real sources/4225pairs remain
`unrun_source_generation_not_admitted`. Overall taskbook completion remains false.

The run producer is `4b0df95a8574ef55def0edc31cca1effb961e117`, based on verified
main `a0d088815aa9583dc4d52fd7299c6a50bb1b5486`. Post-run fail-closed hardening at
`829973eddb98fb86df1efdc8a334b5777fc22a5c` adds metadata/converter regressions;
it does not repeat or reattribute the full graph passes. The original failed
[JSON-loader preflight](REAL_ROAD_CERTIFICATE_PREFLIGHT.md) remains unchanged.

[Small result/receipt summary](streaming_road_representation_results.json) keeps
all16 formal tiny cells, all14 command outcomes including failures, source/config
identity, input/receipt hashes, all65/4225unrun counts and measured resources.
Bulk graph/index/state/input files remain outside Git.

## Same full frozen input

WD01/E18/schedule/N64 and its64literal Sites/capabilities, original physical
parameters and endpoints are unchanged. Domain SHA256:
`2a8f28645f781049a73619eb8222dd730261b58318d1f73f295edf08dad4dc64`.
Frozen-domain artifact SHA256:
`250ff5d84aed3e6fbf86e371f0cabbf135c4cc89034f9ce27fbc5f0bb411db7a`.
The exact raw graph is530374281bytes with SHA256:
`8076e850b096c5cf74f307ae7ad34c2aebd1f1e53c3c4d092234d40078a4c54d`.

The representation is985202688bytes on disk; actual binary SHA256:
`db363d5b58d3bfe8731f7ff30e3a354c6d6223f276edd407d3c4ee197c60bfc1`.
Its logical graph envelope hashes to
`00f983ee3fdcfb04fa1b6dc008b39ab73e30e384c9c264d2f8691ea7224f1601`.
That envelope binds the raw hash, numerical/selection contracts and whether the
node domain is the complete endpoint union or an explicit isolated-node input.
It is a new format identity, not a replacement claim for the raw input hash.

All66source/target anchor nodes are present. No candidate, road edge, terminal
pair or relevant action depth was reduced. This remains the original N64 DEV
workload, not all qualified provincial Sites, a safe reduction, or holdout.
Matching the frozen graph does not prove real-world road-extraction completeness.

## Independent identity validation

`streaming_road_graph.py` writes an **untrusted** SQLite representation. Literal
node/edge identifiers and rational weights are TEXT with BINARY collation;
numeric-looking identities such as`01`,`1`,`10`,`2` are never cast to numbers.
Edge row ordinals are grounded by the complete authoritative input, not free
indices. The builder does not issue a validated graph or road certificate.

A separate pass creates its own bounded-cache seen-node database and verifies:

- every actual raw edge row matches exactly one representation ordinal and its
  full source/target/edge-ID/time/length tuple; EOF rejects extra or missing rows;
- all edge IDs, independently read in full string order, are strictly unique;
- the independent endpoint union and stored node table agree in both directions,
  with no hidden, omitted, duplicated or numerically collapsed identity;
- explicit node files, when supplied for tiny isolated-node cases, are complete,
  sorted and unique, and contain every actual endpoint;
- the actual raw/node hashes and numerical contracts match metadata; duplicate
  metadata keys fail closed rather than being overwritten;
- SQLite structural checks and before/after representation byte hashes agree.

The full raw pass is necessary to construct a new artifact; the second pass is
necessary to independently validate it. Neither repeats the old unchanged
preflight merely to obtain a cleaner report. The old hash/count metadata is not
used as a substitute for this join. Node count2986695is now independently
observed, rather than promoted from historical router telemetry.

Only successful validation creates a privately owned, immutable public graph
handle. Identical bytes reparsed under another owner cannot borrow its table or
checked result. Public caller-supplied hash/certification flags are not accepted.
Readonly handles and byte-integrity checks protect the validated
representation's use. Consuming an issued certificate or cached finish rechecks
the raw/index/path bytes; owner tokens alone cannot protect mutable files. This establishes input representation, not shortest paths.

## Streaming supplied-certificate backend

`streaming_road_certificate.py` consumes bounded JSONL records into disk-backed
path and one-source state tables. No full graph JSON, per-edge Python object
array, all-node label dictionary, all-source label array or priority queue is
retained. Every supplied path edge resolves to a validated literal edge and
matches its endpoints; exact time/actual-length sums, continuity, positive
simple paths, explicit unreachable legs and exact alias-zero legs are checked.
All physical source/target pairs and literal Site/effect/order identities remain.

For a source, complete node records provide distance labels, attaining
predecessors and target masks. Full raw-edge scanning verifies the same proof as
the earlier independent checker: all reachable outgoing edges stay reachable,
all Bellman inequalities hold, every nonroot finite label has a strictly
attaining predecessor, and each mask equals its own target bit OR all tight
successors' supplied masks. Positive times make the tight graph a DAG, so the
mask equations have a unique target-reachability solution. Any shortest
predecessor tree is acceptable; it need not be the canonical selected-path tree.

Canonical verification needs no retained adjacency or per-target full-graph
rerouting. For every supplied path step toward target t, reject **any** tight
raw outgoing edge with a t-reaching suffix and a smaller(next literal node,
full string edge-ID)choice. The supplied edge itself must exist and be tight.
Thus its next node is minimal; recursively the full node tuple is minimal.
Parallel tight edges have equal time and reach the same node/suffix, so the
smallest full edge-ID string gives the final edge-tuple tie. Shared prefixes,
numeric-looking IDs and actual selected length are preserved. Length is not
replaced by shortest distance or triangulated.

Source prefixes are explicitly source-only receipts. Failure poisons the
session; a final resource stop prevents issuance. Whole-table checking requires
all complete sources. The current table reader intentionally requires the full
Cartesian pair domain; it cannot invent missing pairs as unreachable. Real
incremental source admission still needs an explicit source-unit reader/exporter
whose result cannot be mistaken for a complete table (see next step below).

## Exact arithmetic and bounded resources

Input component widths78/84/75/77from the prior preflight are not bounds on path
numerators, denominators or a global LCM. No int64 path arithmetic, binary64,
fixed common denominator or precision clipping is used. SQLite stores exact
weight/label/mask text; even65-bit target masks never pass through SQLite INTEGER
or floating arithmetic. Fraction operations remain arbitrary precision.

Records have an explicit1MiB resource envelope. Exact operand/cross-product
storage is conservatively admitted before arithmetic; exhaustion raises a
resource stop and issues no whole certificate. The normal decimal conversion
limit is temporarily lifted only within the already bounded record/operation
envelope and restored afterward. Tests cover a path denominator exceeding84bits,
values beyond int64 and5000-digit exact input/conversion. These are resource
failure boundaries, not a changed physical/model domain or truncated optimum.

SQLite total heap is hard-limited to128MiB per process, each connection cache
to16MiB, mmap disabled, temporary storage on disk and one SQLite thread. Batches
are bounded by both4096rows and4MiB raw bytes. The supervisor enforces1GiB for
the whole process tree,3GiB start availability,2GiB runtime host headroom, and
free-disk guards. Full admission observes5.170184192GB available memory and
48.3328GB free disk on the same output/temp filesystem; at least12GiB free is
required. Graph/tracking databases have4GiB/2GiB growth limits. No other graph
process/resident index or purchased resource is treated as free.

| Full new-artifact phase | Body CPU s | Wall s | Whole cold/controller/tail charge | Tree peak RSS bytes | Minimum host available bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Construction, untrusted until checked |26.336984|28.639238|29.224331|52772864|4719230976|
| Independent full identity validation |27.427326|27.811059|30.119726|73891840|5153423360|

Post-exit native peaks are52772864/74088448bytes. These are measured complete
representation construction/identity-validation resources. They are not source
tree, source-certificate or EV solver measurements. The old JSON loader's
structural floor and this new measured RSS are different kinds of evidence;
no percentage speedup/memory benchmark is inferred between them.

## Tiny evidence, failures and accounting

The16formal cells match both the earlier independent checker and the new
backend:6accepted,8rejected,2unsupported. The added closed-form star has64Sites,
65sources/targets and4225pairs, including a65-bit mask; its labels are analytic,
not real routing. Other fixture path production remains exhaustive only within
the existing<=6node/12edge/2048prefix tiny guard. Combined4268pair claims and
76source certificates are synthetic component checks, not real routes.

Seventeen final regression methods pass normally and under-OO. Dedicated clean
stdlib CI runs these plus the existing24certificate/preflight tests per mode.
Negative tests cover missing/extra/swapped/duplicate identities, duplicate
metadata without a trusted schema flag, literal string collisions, parallel
edges, aliases, malformed conversion, exact arithmetic growth, owner mixing,
incomplete terminal/source coverage and final resource failure.

Three failed development/verification commands remain charged and preserved:
SQLite's case-insensitive`t`/`T`column collision; a synthetic origin name that
did not match the older diagnostic helper's`o`; and overbroad test discovery
with unavailable unrelated dependencies plus a missing explicit target-order
field in an empty-graph fixture. Corrected focused tests pass. No assertion or
resource limit was weakened, and no mathematical counterexample was found.

Post-run hardening rejects ambiguous metadata and stops the tiny converter
from dropping invalid suffixes/extra labels or rewriting malformed target order
and identities. A small metadata query confirms the actual full artifact has
six distinct metadata keys; its binary hash is unchanged. No full raw pass or
construction was repeated for this correction. The extra integrity hash/query
gets a conservative2CPU-second verification fee in addition to the retained
fixed precharge. It is not claimed as a measured whole-process CPU value.
One such manual bookkeeping hash read the985202688-byte index as a single byte
buffer outside the recorded supervisor; that operation's RSS peak was not
measured. It completed, with no confirmed headroom overrun, but the two full-
phase peak receipts must not be presented as an overall peak covering it. All
repository hashing uses1MiB chunks. This limitation is retained in the summary.

A late disk-backend ownership regression also verifies that modifying raw,
index or selected-path bytes after certificate issuance invalidates both
`is_for` and cached `finish`. Fix commit
`47c724d994943c7cfd6e0e85fb6f39d672a07cf6` adds these consumption-time integrity
checks;17final tests pass in both modes. No real certificate was issued before
or after the fix, and the valid full representation passes were not repeated.

Prospective900CPU allocation:240development/controller,180tiny validation,
360conditional representation and120verification/tails. Conservative actual
charges are240+9.136399+59.344057+10.647252=**319.127708/900**. All14command
receipts, including3failures, remain. Cumulative research is
**16335.727910741/28800**, remaining**12464.272089259**. Preprocessing remains
652.040677976/900. Old charges are not refunded. Ordinary software CI is
separately prospectively reserved(9000capacity-CPU full M5;120dedicated stdlib
per invocation), without claiming historical whole-job CPU is measured.

Child limits are160CPU/300wall seconds per full phase, with180CPU reserved
including a separate10soft/15hard CPU-limited controller and tail. Controller
limits are applied after spawning the child to avoid an inherited lower hard
limit. Persistent phase totals, locking, durable started/progress/terminal records
and fresh output paths prevent duplicate uncertain starts. All recorded worker
and controller PIDs are terminal. Environment: Python3.11.15,SQLite3.53.1.

## Reproduction and next genuine verification gate

`configs/streaming_road_representation.json` freezes query/input/coverage and
resource policy. `run_streaming_representation_gate.py --mode tiny|build|validate`
requires fresh outputs, committed within-run producer identity, and the declared
external budget/process supervisor. The full raw/index validation, original
frozen domain, old negative preflight, all generated tiny inputs and raw command
receipts remain in `streaming-road-certificate-artifacts-v1` outside Git.

The next concrete step is an **untrusted exact source/path exporter plus an
explicit source-unit input/checker**, preserving the full65/4225denominator.
That reader must label absent sources as unrun, never unreachable, and must be
unable to issue whole-table certification. First test that contract on tiny
adversarial/incomplete cases. Then, only under a new bounded admission, generate
one prospectively selected original OD-origin source with all65targets and all
graph-node labels/pred/masks, and independently check it against the same full
graph. Count all native/index residency, cold load, generation, serialization,
checking and tail costs. One checked source is not the completed N64 table.

A proposed next<=900CPU gate can reserve240development/control,180tiny tests,
300for one real generation/check pair(150each with120CPU/120wall child limits),
and180verification/tails. This is a proposal, not an admitted or executed source
run. The first origin is3797700636, already frozen before observing this source's
cost. Preserve all64other sources as unrun. If it times out or fails, keep the
outcome and do not infer EV infeasibility or a complete optimum.

Complete65-source selected paths and their cost remain absent. Independently
replaying an attained physical upper witness and deriving complete relevant H,
legitimate integration with the independent physical-model lookup, real-scale
comparison, wider/full domains, real four-charge evidence, original hierarchy/
timing targets and holdout remain open. Representation success does not close
those original taskbook gaps.
