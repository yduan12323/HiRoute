# Original-query collection planning

`plan_query_collection(admitted, registry, on_query=..., before=...)` accepts
exact `AdmittedSuffixPopulation` and `CheckedRegistry` instances. The original
population must have an exact `OrderedModelPopulation`. The registry must
provide cold-reconciled report bodies through `block_reports()`; scheduling
metadata or authority flags cannot replace them. The planner compares the
population commitments, canonical block catalogue, full report coverage and
compact report hashes before folding any query. Missing, duplicate, foreign,
unsubmitted or unresolved block coverage fails before streaming query rows.

`merge_block_segments` retains every logical segment summary. `join_projection`
then restores every original query, family and action binding in index order,
including repeated segments and all tie ranges. Its unchanged `_bound_audit`
runs once per query during planning. Violated and missing bounds remain audit
findings; they do not discard the mathematical aggregate. All totals come from
the supplied population, with no fixed C01 population constants.

For each nonempty result, the representative is the first winning regime for
attainment, first secondary-tied regime for secondary nonattainment, or first
primary-tied regime for primary nonattainment. The exact original projection
maps that regime to one logical ordinal. Its descriptor comes from
`admitted.population.descriptors(ordinal, ordinal + 1)`. Distinct query binding
IDs commit to the query sequence/index position, original projection hash,
result hash, query regime, logical ordinal and descriptor hash. A block's own
winner is not a substitute for this original-query representative.

`physical_requests()` exposes the integer-ordinal map expected by selected
witness collection: `{ordinal: {descriptor, result}}`. For persistence use
`physical_request_rows()`, an ordered JSON array with explicit integer
`model_ordinal` fields. Its exact canonical array bytes, hash and request count
are in the summary. At most 8,192 distinct physical requests and 16 MiB of these
canonical request-array bytes are admitted, checked incrementally. This limit
does not cap the number of original query bindings or bound audits. Empty
restricted queries need no physical request. Nonempty all-excluded languages
remain distinct from zero-length legal languages.

The returned immutable planning object owns compact segment summaries, query
bindings and unique requests. `iter_queries()` re-emits detached provisional
rows and checks their original bindings. No expanded model-occurrence ledger
or matrices are retained. Tie-range space can still grow with the number of
distinct runs. `before` supplies caller resource/cancellation checks around
source, block, query, descriptor and callback boundaries. It does not preempt
the existing pure fold/join or a descriptor generator internally: hard process
deadlines, including any per-descriptor timeout, remain the enclosing runtime's
responsibility. A callback/checkpoint exception propagates without returning a
completed plan, even after the final row has streamed.

## Empty occurrences and final assembly

`recover_empty_partition(original_trace, before=...)` is a separate explicit
method. It calls the cleared empty-occurrence bridge itself with the admitted
trace SHA, complete ordered nonempty query IDs, empty count and empty hash. It
never accepts a previously returned false-authority dictionary as a source.
The bridge hashes the trace once and checks the complete identity partition;
callers should not duplicate that hash just to invoke this method. The result
remains pending final collection. The separately reviewed bridge supports the
original v1 and exact recorded v2 schema/representation shapes; changing either
or re-pinning a normalized trace is not supported.

This module provides no physical or final-query acceptance. Before assembling
a final result, the runtime must freshly obtain the genuine checked family and
authenticate the following original sources using the existing admission path:

- Immutable original capture and its trace SHA, original query-index pin and
  query-freeze hash, structural/parallel replay summaries, logical plan/report,
  actual successful caller returns, decisions and complete evidence manifests
- Exact source bundle/case/physical-input commitments and the reviewed source
  allowlist; never a reconstructed successful return or synthetic trust object
- Actual registry registration return, registered metadata bytes, full
  catalogue/population commitments and the freshly reconciled successful
  receipt dependency chain, including all losing and excluded certificates
- The planner's query-row stream/hash, separate original query binding IDs,
  unique request-array hash and freshly recovered empty count/hash/identity
  partition; the complete mixed original event order must be retained
- Selected full archived records matching each exact descriptor and expected
  mathematical result, followed by existing `calibration.verify_model` with
  the genuine fresh bundle and retained per-query binding to each actual check

Only a successful enclosing final-collection return can seal streamed output.
A nonattainment certificate may establish a negative infimum-based bound gap;
its fixed-epsilon physical approach point is a bound-violating trajectory only
if that point's independently evaluated value actually violates the bound.
This planner makes neither trajectory claim nor G8 closure claim.

Tests use genuine tiny checked families and clearly marked protocol-fake receipt
metadata to exercise these boundaries. They do not authenticate any real
execution, run an LP/server, or alter receipt, window or runtime admission.
