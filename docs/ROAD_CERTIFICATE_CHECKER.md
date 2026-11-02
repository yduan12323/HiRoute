# Independent exact road certificate checker

## Result and scope

The frozen15-row tiny gate matches every decision: **5 accepted,8 rejected,
2 unsupported**. Sixteen local regression methods pass normally and under-OO.
No real table, real shortest-path tree, EV optimization or holdout was generated.
Original taskbook completion remains false. This checker closes the supplied-
certificate verification implementation gap; real input compatibility and
resource behavior remain unverified.

Gate source is `bc1f9714dafb4c175298f23b6eb30afbfad768d6`, from verified main
`ad53b4622524e2d87d4a9d8257157f41a0e50fb2`. Later receipt/report changes do not
rerun or reattribute that gate. [road_certificate_results.json](road_certificate_results.json)
keeps all15 rows, source/config identity, saved input hashes and all command
receipts. Every formal decision consumes the saved graph/table/source-certificate
bytes, rather than the generator's in-memory answers.

## What is checked

`tools/exact_road_certificate.py` uses only the standard library and the existing
exact table parser. It calls no production router, optimizer, Z3 or fixture
producer. It does not derive distances using Dijkstra or enumerate paths.

The graph explicitly declares every node and edge, exact rational time/length,
direction and a unique literal string edge ID. All weights must be positive,
matching the current road input contract. Missing endpoints, duplicate IDs,
floats/bools, nonfinite values and duplicate JSON keys fail closed. Source byte
hashes are derived internally; there is no caller digest override. The table
must bind to `sha256:<actual graph byte hash>`. Input schema flags are never
certificates.

The result is conditional on this **exact supplied explicit graph**. It does
not establish that an extractor included every real-world road, that graph
bytes match a frozen real working dataset, or that candidate attachments are
correct. Those are separate real input/provenance obligations. A reduced graph
has a different identity and is a different problem, not a safe reduction.

### Exact shortest times and unreachable cuts

One source certificate is checked at a time. It supplies d(v) for every graph
node, with explicit null for unreachable nodes; an attaining predecessor edge
for each nonroot reachable node; and target-reach masks on reachable nodes.
Let R be the nodes with finite labels. The checker verifies:

- source is in R with d(source)=0, and finite labels are nonnegative;
- each v in R except source has a real predecessor u->v in R with
  d(v)=d(u)+time(u,v) and d(u)<d(v);
- every graph edge leaving R also ends in R;
- every edge u->v within R satisfies d(v)<=d(u)+time(u,v).

Strictly decreasing predecessor labels and finiteness exclude predecessor
cycles. Only source has no predecessor, so each reachable node has an attaining
source path. The Bellman inequalities make d(v) a lower bound on every source
path; the predecessor path attains it, proving a global shortest time. Closure
of R proves all excluded nodes unreachable. This is stronger than checking that
one supplied path merely exists or agrees with a tree.

The full graph is examined, including nodes/edges outside the table's anchor
set. A negative fixture supplies a valid3-second direct path with an attaining
predecessor, but an unexposed route takes2seconds. Its table has no intermediate
Sites, so table-only triangle checks cannot detect the error. The graph-wide
lower inequality rejects it.

### Full canonical path ties and actual length

An edge is tight when d(v)=d(u)+time(u,v). Positive time makes tight edges
strictly increase d, so the tight graph is a DAG even when the original graph
has positive cycles. For each reachable node the supplied target bitset must
be exactly its own target bit OR all tight successors' bitsets. Acyclicity makes
these local equations have a unique solution: a bit is set exactly when that
target can be reached by a tight suffix. A certificate cannot invent or hide a
competing suffix.

A shortest source-target path consists of tight edges. Among target-reaching
tight successors, the smallest next **node string** is required. Recursing
chooses the full lexicographically smallest node tuple. For parallel tight
edges with that same next node, the smallest complete **edge-ID string** is
required. Such parallel edges have identical time and reach the same state,
so this does not alter future node choices; local string choices give the
smallest full edge-ID tuple after the full node tuple. This handles shared
multi-edge prefixes as well as the first step. IDs are never cast to integers.

The checker verifies every supplied edge exists with the given endpoints,
that its exact time sum equals the proven label, and that its exact **actual
length** sum matches the table. Length is not minimized or triangulated. In the
base fixture, canonical o-a-z has time2 and length20; equal-time o-b-z has
length2, and a direct route has length1. The longer canonical path is accepted.
Parallel edge `"10"` precedes `"2"`, and node `"10"` precedes `"2"` as full
strings. An edge-first rule would incorrectly prefer `"00"` toward node b over
`"10"` toward node a. Deep-prefix examples exercise both tuple comparisons
beyond their first entry.

A deliberately noncanonical shortest predecessor tree is accepted when the
separately supplied table paths are canonical. A forged bitset paired with an
otherwise valid equal-time wrong-node path is rejected by the local bitset
proof. Neither tree identity nor a path's validity is used as a canonicality
shortcut.

### Coverage, ownership and unsupported inputs

Sources are exactly origin plus distinct physical Site anchors; targets are
all distinct Site anchors plus destination. Every ordered pair is checked,
including directed unreachable, every terminal leg, empty-prefix origin-to-
destination, and coincident-anchor zero paths. Alias-zero is exactly0time,
0length, one node and no edges. Literal Site/action/Pi identities are retained
in the full table hash; physical aliases do not merge those identities.

`CertificateSession` accepts sources in the complete declared order. A prefix
is explicitly source-only; `finish()` cannot issue a whole-table result until
all sources and targets are covered. Failed source checks poison the session.
Graph/table references and prefix receipts are read-only public properties.
The immutable checked result binds parser-created graph and table owner tokens,
not just caller-provided hashes or self-declared flags. Reparsed identical bytes
need a new check; they cannot reuse a checked object belonging to other inputs.
A final resource callback can stop issuance of a whole certificate.

Zero-time edges are unsupported, including acyclic zero edges and zero-cost
cycles. They are not deleted, contracted or treated as harmless ties. The
positive-time predecessor/DAG proof does not apply to zero-cost cycles, where
walk/simple-path and lexicographic semantics need another explicit contract.
Negative times and nonpositive lengths are also outside the current positive
road input contract. Positive cycles are supported; they are not tight cycles.
Unsupported input is distinct from a false certificate or EV infeasibility.

## Bounded evidence

| Frozen tiny class | Expected and observed |
| --- | --- |
| Full directed table, terminal and aliases | accepted |
| Noncanonical attaining predecessor tree | accepted |
| Empty prefix with coincident origin/destination | accepted |
| Full string node tuple | accepted |
| Deep node/edge shared-prefix ties | accepted |
| Valid slower path with false lower labels | rejected |
| Wrong equal-time full node tuple | rejected |
| Wrong parallel string edge-ID tuple | rejected |
| Wrong selected actual length | rejected |
| False unreachable cut | rejected |
| Forged suffix masks hiding a competing canonical path | rejected |
| Missing physical source | rejected |
| Missing terminal pair | rejected |
| Zero time on an acyclic edge | unsupported |
| Zero-time cycle | unsupported |

These5 accepted-case checks cover43 pair claims and11 complete source
certificates, including repeated synthetic inputs with different predecessor
proofs; they are not43 distinct real routes. All15 decisions and all input
bytes are retained. No missing/unrun cell is removed from the denominator.
The fixture producer is independent exhaustive tiny simple-prefix enumeration,
limited to6nodes/12edges/2048prefixes per source. It computes all-pairs tiny
reference distances and uses a distance-equality characterization for masks;
the checker independently verifies local inequalities, cuts and DAG equations.
That producer must never be applied to the real graph.

Normal and-OO regressions additionally cover malformed graph/certificate data,
digest/owner spoofing, immutable session state, partial coverage, rational
arithmetic, on-disk tampering and a resource stop before whole-table issuance.
The checker passes in an isolated import that blocks routers, optimizers, Z3
and the fixture producer. Both checker and generator share the exact input
parser and Fraction arithmetic; this is not a claim of independent graph
extraction or real-world data completeness.

## Cost and reproduction

This admission is <=600 research CPU seconds starting15646.570668741/28800.
The full220 development/controller/report precharge is retained. Nine metered
commands, including all unit runs and the single formal gate, charge9.800848
with child/controller/tail allowance rounded upward per command. Stage total
is **229.800848/600**, cumulative **15876.371516741/28800**, remaining
**12923.628483259**. Preprocessing stays652.040677976/900. All old charges and
results remain. Ordinary software CI is separately prospectively reserved:
9000 capacity-CPU full M5 and120 dedicated stdlib CI per invocation; neither
allowance is measured whole-job CPU or a research refund.

One worker/thread and30CPU/55wall seconds,1GiB process RSS,3GiB start/2GiB
runtime host availability guards were retained. Formal gate body CPU is0.029324
and wall0.051929s, including tiny generation, saved-byte verification and I/O
after imports. Whole cold process cost is charged by the supervisor. These
numbers are not real graph verification, table generation or EV solve timings.

The frozen config is `configs/road_certificate_gate.json`. Raw graph/table,
all per-source certificate bytes, input hashes, started/terminal records,
controller source and logs remain in `road-certificate-artifacts-v1` outside
Git. Fresh output paths and the external declared resource supervisor are
required; uncertain started work must be inspected rather than repeated.
The report joins saved receipts without constructing or rechecking certificates.
Source identity is within-run provenance, not a source code/hash/file-count lock.

```sh
python -m unittest discover -s tests -p test_exact_road_certificate.py
python -OO -m unittest discover -s tests -p test_exact_road_certificate.py
python tools/run_road_certificate_gate.py --output /fresh/gate
python tools/report_road_certificate_gate.py --root /fresh --output /fresh/results.json
```

The report also requires its supervisor budget/command journal with the named
verification receipts; arbitrary manual outputs cannot become a certified gate.
The dedicated CI uses a clean stdlib-only venv and does not install an optimizer.

## Smallest proposed real admission, not run

Use **one already frozen WD01/E18/schedule/N64 DEV instance**, preserving its
full candidate/alias/capability/domain fingerprints, all physical parameters and
the complete U-derived action depth. This is a workload domain, not a safe
reduction of all qualified provincial Sites. The audited domains have64 distinct
Site anchors and distinct endpoints:65physical sources x65targets=4225pairs,
including64zero pairs. All rows, unreachable pairs and terminal legs remain.
Do not shrink N, choose easier replacement Sites, reuse a legacy binary64/
length-tie table, truncate H or run an EV optimizer to make this table pass.

Proposed prospective maximum: **3600 research CPU seconds** inside the remaining
original cap, with three explicit components:

- <=240CPU preflight: resolve the existing frozen graph, exact decoder/ID order,
  full V/E and weight bit widths, attachments, cold resident/peak memory and
  source/table serialization contract. Verify identities and budget admission
  before releasing source-tree generation. This includes necessary compact/
  streaming input-bridge verification; the current JSON object loader is not
  established to fit the real graph.
- <=3120CPU total for all65 source units, reserving48CPU per unit for exact
  certificate/table **generation plus independent checking and path output**.
  Process one source certificate at a time; source generation is new charged
  routing work, not something this verifier or tiny gate already performed.
- <=240CPU controller/report/replay/cleanup reserve. Save every started/source
  receipt and admit each next source only with the full reserve available.

These are hard prospective caps, not estimates or promises that65 sources fit.
Historical metadata reports2986695nodes/5900232directed edges; this stage did
not recompute those counts. Sixty-five edge scans alone represent383515080edge
visits before exact arithmetic, generation, queues and paths. Static adjacency
sorting costs sum(deg*log(deg)) once. Per source, checking is O(V+E*W+L), where
W=target-bitset word width and L is supplied path-step claims; batched canonical
checks scan each relevant adjacency once. Exact rational bit costs and decoding
are additional. Streaming avoids retaining all65 label maps, not computation.

The current graph/table JSON parser materializes objects, so tiny success does
not prove an acceptable real peak. Preflight must establish a bounded compact
or streaming exact input path under original8GiB extra residency and actual host
headroom>=2GiB, without claiming existing graph/index residency free. If that
cannot be supported, stop before route generation and report the actual blocker.
No scope/budget increase or denied server source upload is implied.

If any source is unsupported, incorrect, resource-stopped or budget-unrun, keep
all4225pairs/source statuses visible and the whole table uncertified; do not
claim a prefix closes the real-table gap. A successful full admission would
close one actual taskbook gap: one compatible real N64 selected-leg table with
independently checked canonical paths and reachability. It would **not** be a
real EV comparator result. Independently replay the supplied physical witness
on the certified table and keep complete depth; real optimizer measurement
needs a later bounded admission. Holdout, broader/full domains, four-positive-
charge evidence, original timing/hierarchy goals and overall completion remain
unmet.
