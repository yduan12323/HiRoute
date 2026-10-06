# Immutable-leg physical solver adapter, reviewed mock scope

Scope: tested adapters on mocks; real physical input export and read-only import are complete. Real C32 optimization/acceptance remains gated. This extends the loader-only contract without changing the delivered `579c6db` checkpoint or synthetic route-selection policy.

## APIs

`solve_bounded_real(query, table, restriction=None, dominance=True)` and `solve_hierarchical_real(query, table, restriction, dominance=True, incumbent=None)` consume a hash-validated `ImmutableLegTable` and an independently validated original-tree restriction. `evaluate_real_sequence` and `replay_real_witness` expose constrained sequence and event verification.

Query scalars use the original bounded schema, but origin/destination are physical `road:<dense node ID>` anchors, no graph edges are permitted, and Site effects are taken from the table. If a query repeats origin/destination/Site or provenance fields, they must agree. The numeric model freezes initial SOC, capacity, reserve, overhead, penalty, charging coefficients and consumption rate as exact decimal rationals; leg time/actual-length values are exact lifts of stored binary64 constants. This does not assert bitwise equality with legacy floating evaluator sums.

## Shared production search, separate routing inputs

Factor only the production query/search/event mechanics. Synthetic `Problem` retains its exact graph Dijkstra and `(time,node path,edge-ID path)` tie rule. Real `RealProblem` performs no route search: its immutable direct legs carry accepted time and actual length, and energy is the declared exact rate times that length. REF has a separate parser and adapter and imports no production optimization helpers.

Physical `State.anchor` is always a road anchor in real mode. Semantic events and pi retain Site IDs. After a stop, wrap the cut/witness state to the Site's road anchor while preserving its original constrained predecessor callback, energy, time, rho, pi and semantic event. This allows safe same-anchor comparison without merging different action identities. Co-attached movement is an explicit zero identity drive followed by a real semantic stop.

Destination terminality uses road-anchor equality, including co-attached Sites and an origin already at destination. A selected concrete leg may internally transit destination; table replay does not invent a stronger path rule. Canonical witnesses alternate selected drive/semantic stop pairs, with one terminal leg; no consecutive-drive route shaping or over-H_ref witness is accepted.

## Real hierarchy and bounds

Real HIER constructs its action-view nodes from the supplied original restriction, retaining Region IDs, parents, children and empty branches. Root coverage must equal the exact table Site universe; child partitions must be disjoint/exhaustive. It never calls the tiny-fixture repartitioner in real mode.

The production bound interface separates immediate inbound primitives from onward bounds. Synthetic mode retains its metric directed-destination relaxation. Real mode returns **zero onward travel** and never substitutes a direct destination leg or its energy for continuation reasoning. Exact immediate inbound minima, common overhead, forced service and lambda*(k+1) remain safe. Strict-primary pruning only; equality remains live.

## Review/test obligations

- All existing synthetic module tests must remain unchanged and pass.
- Mocks distinguish Site IDs from anchors, preserve co-attached actions/zero legs, exercise terminal aliases, reject inconsistent query/provenance/tree inputs, preserve inherited witness constraints, and reject forged drive grammar/bound violations.
- A non-metric mock must expose why direct outgoing time is unsafe; real HIER must match direct immutable-leg FLAT and independently implemented REF with zero onward bounds.
- Real outputs identify table/selection/tree fingerprints and scope witness replay to immutable physical primitives and semantic events, not road-edge path reconstruction.
- Candidate selection, numerical direction policy, source hashes, resource estimates and independent adapter review precede any real optimization. Query/regime volume must be estimated; no uncontrolled parallel launch.

Current serialized cut traces omit some inherited predecessor masks. Superset lower-bound certificates are not exact node-constrained REF certificates; that separate gap remains explicit.

## Hash-frozen filesystem boundary

`timecut5.real_export_input.load_exported_case(export_directory, state_id,
expected_manifest_sha256, selection_path=..., expected_selection_sha256=...,
original_hierarchy_path=...)` reads without optimization. It checks the caller's
reviewed manifest and selection hashes, resolves all bundle paths under the
export directory, rejects duplicate JSON keys, verifies state/table bindings,
compares each selected Site's physical anchor and allowed actions, and derives
the restriction again from the actual original hierarchy bytes. Every exported
restriction row must equal that reconstruction. It then verifies binary64
baseline records, exact SOC and schedule arithmetic, and translates the frozen
scalar/charging schema. Raw source hashes remain explicitly declared provenance
at this layer; the exporter and independent source audit verify raw files.

## Optimized Python safety correction

Review found that the historical bounded witness verifier relied on Python
`assert`, which is disabled by `-O`/`-OO`. A forged external incumbent could then
alter pruning. All physical replay checks now raise unconditionally, and a
subprocess regression covers normal, optimized and doubly optimized Python.
This correction also applies to the original bounded API; its standalone
backport is `ef2f356`, directly above checkpoint `579c6db`.
