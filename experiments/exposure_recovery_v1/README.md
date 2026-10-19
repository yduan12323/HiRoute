# Disclosed incomplete historical exposure recovery

This amendment implements the explicit 2026-10-19 permission to exclude recoverable
historical exposure and disclose broader lost-history coverage for new-map
correctness and performance validation. It does not establish strict independent
holdout, recover the old registry, or authorize selecting ODs before protocol freeze.
The existing complete-registry validation default remains unchanged.

## Reproduction

From this repository root:

```
python -m experiments.exposure_recovery_v1.build \
  --repository /path/to/recovered/source-audit \
  --external-inputs /path/to/authenticated/real_inputs \
  --output /private/path/outside/this/repository
```

The checked-in config binds all configured source files to exact SHA-256 digests.
The builder resolves the source commit, inventories all reachable Git blobs with
content hashes, and binds builder bytes, config and inventory in the registry.
The full registry and inventory remain outside the publication tree. Receipt
hashes use canonical JSON (`rules.digest`); the registry and inventory files
are emitted as those exact canonical bytes, with no trailing newline, so their
raw-file SHA-256 equals the receipt digest. Pretty-printing changes file bytes. Retain the generated files together for audit.

Only supported, source-bound records are admitted. All four grid14 partitions
are included, including failed/unreachable and non-retained pairs; recursive
screen traversal includes extrema, representatives and regional endpoints. A
screen's node-file hash is matched to the partitions, whose node and edge file
hashes and exact v5 screen hash are checked. Conflicting coordinates or anchors
fail closed. Occurrences retain source JSON pointers; repeated exposures are
kept as occurrences, not reported as unique observations. Endpoint exclusion
sets deduplicate naturally at admission. The DEV config is retained as a bound source declaration. The original 30 DEV
pairs and their 60 graph-local anchors are separately recovered from the exact
historical od_remapping.parquet, authenticated through the recovered required
input manifest, metadata and per-row graph hashes. Their exact graph-node
coordinates remain unavailable: nearby attached Site geometry is never
substituted. `anchor_only_exposures` enforces their graph-local anchor exclusion.

The entire authenticated historical stop_sites catalog is conservatively
excluded, including unattached Sites geographically. This does not assert that
every Site was actually inspected: it deliberately excludes the superset of
available historical endpoints and labels these records accordingly. Screen versus catalog anchors must agree. Screen coordinates are graph-access
node coordinates (the historical screen script joins sites to nodes), while
catalog coordinates are Site geometry. Both are retained and explicitly labeled,
never silently equated or used to fill unknown DEV node coordinates. Exact known file hashes are
mandatory; merely similar inputs are rejected.

The inventory is a discovery/recovery audit, not a completeness certificate.
Unextracted diagnostic/candidate/archived history, original registry/builder
loss, exact missing M2 bytes, and named China proposals without exact endpoints
are listed as explicit gaps. The old totals 74,754 / 248,348 / 5,961 are not
recovered counts. The inventory's Git-blob count is not comparable to the
original builder's source-count denominator. Unknown history remains unknown.

## Admission interface

`validate_exposures(registry)` continues requiring the original complete schema.
The recovery path must explicitly provide `recovery_admission` to
`select_od_slate(..., graph_file_identity=...)`. Required admission fields:

- schema: `hiroute.m6h.recovered_exposure_registry.v1`
- registry_sha256: canonical `rules.digest(registry)`
- gap_list_sha256: `rules.digest(registry['coverage']['known_missing_artifacts'])`
- purpose: `new_map_correctness_and_performance_validation`
- strict_independent_holdout_claim: `false`

The candidate graph identity contains exactly `nodes_sha256` and
`edges_sha256`, both full file hashes. Historical records carry the same form.
Site labels and access_node values are namespaced by this complete identity.
An access_node is a graph-local row index, never a cross-map OSM node ID.
Matching bare indexes between Europe and Shandong do not exclude endpoints.
Geographic pair-neighborhood exclusion remains cross-graph; recovery also
excludes the neighboring cells of every recovered inspected endpoint across
graph identities. This conservative addition is explicit, not hidden retuning.

The bounded lexicographic selector, six groups, capability pool, budgets and
solver are otherwise unchanged. This package itself never invokes selection,
routing, preprocessing or solving. Tests use synthetic tiny fixtures only.
