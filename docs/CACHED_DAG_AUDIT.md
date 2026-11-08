# Exact assertion-DAG audit cache and producer finalization

The audit cache retains at most one assertion-only export, its original ordered
roots, context, node-to-name map and expected payload identity. Root references
keep the entire Z3 DAG alive, preventing node-ID reuse. A hit requires identical
ordered AST roots in the same context; each arithmetic objective must already
be a node in that retained DAG. New objective expressions use the uncached
exporter. Changed roots/order/context invalidate the entry. No solver result,
model or SAT status is cached: every live check still runs.

A hit verifies the original complete audit, streams its assertion payload into
a new standalone file, verifies that copied payload against the expected hash,
then appends exact minimize references and a new digest footer. Existing symbol
bindings suffice precisely because objective roots must already be present.
No hidden include file or parsed transport is introduced. Each final file has
its own full hash, expected payload hash, objective count and cache-hit receipt.
Interrupted/corrupt copies fail closed and clear the cache. Resource/deadline
callbacks cover verification, copying and publication. Per-entry defaults bound
retained nodes to500000 and source/output bytes to64MiB; larger entries fall back
to the bounded original exporter. External RSS/CPU/disk guards remain required.
No full-size performance saving is established by this development-only stage.

Successful consumer finalization derives producer_source from the already
validated producer chain. An optional duplicate admission source must agree;
absence is permitted. Tests exercise successful run closure without that field,
rejection of mismatches and UNKNOWN on failed final verification. Historical
outside-source runners and sealed artifacts are not edited or retried. A future
separately admitted runner must call this reviewed finalization helper rather
than copying the old defective result construction.
