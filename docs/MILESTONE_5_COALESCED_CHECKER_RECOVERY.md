# Reconstructed recorded-coalescing trace checker

This is **newly reconstructed source above PR7**, dated 2026-10-07. It is not
the missing historical checker source, an independent-review acceptance, or a
new certification of the historical B64/C32 populations. The published
`validation/trace5/checker.py`, `validation/family5/checker.py`, `CheckedTrace`,
and `CheckedBundle` remain unchanged.

## Entry points and isolation

The explicit new entry point is:

```python
from validation.trace5.coalesced import verify_coalesced_trace

checked = verify_coalesced_trace(trace, bundle, trusted_case)
```

It returns the existing immutable `CheckedTrace` with the existing
`CheckedBundle`. The snapshot is the exact detached v2 trace, and its digest
covers the v2 header and every occurrence. Existing v1 entry points do not
automatically dispatch v2 evidence. The new checker rejects v1 traces and any
other representation label.

`CoalescedReplay` subclasses the published `_Replay` and is available for
composition with a separately trusted physical/Region adapter. Its own
`run()` retains the synthetic balanced-binary, leaf-size-one Region contract.
Neither a trace-supplied Region nor a representation label establishes trust
in a real adapter.

The checker and all its hand-authored test fixtures import no production
coalescer, recorder, solver, envelope, or projection code. The physical branch
of `invoke` is reconstructed from the published v1 grammar because the two
compact boundaries occur inside a producer call. Drive, stop, exact selection,
action coverage, queue ordering, strict pruning, candidate witnesses,
incumbents, terminal selection, and node-query freezes retain the published
independent checks.

## Exact wire contract

The top-level object has exactly these fields:

```json
{
  "schema": "family5-hier-trace-v2",
  "representation": "exact-adjacent-cut-coalescing-v1",
  "events": []
}
```

Each `coalesce` event retains the ordinary `seq`, `kind`, `payload` envelope.
Its payload has exactly:

```text
coalescing_id: consecutive integer occurrence ID, starting at zero
input_families: exact ordered input IDs, including repeated occurrences
output_families: exact independently reconstructed output IDs
input_guards: exact input domains, in matching original order
batch_range: [current_batch_cursor, current_batch_cursor]
```

For every `advance`, `finish`, and `reduce` call, the checker consumes:

1. `coalesce(input)` at the current batch cursor, including empty/singleton
   inputs when such an operation is called.
2. The independently reconstructed physical operation and its complete batches.
3. `coalesce(output)` at the resulting batch cursor, including empty/singleton
   outputs.
4. The existing `invoke` event, whose input is the original call input and
   output is the compacted result. Its `batch_range` spans the whole call.

This order preserves the published producer's end-of-call `invoke` emission.
`initial` consumes only its ordinary `invoke`; it has no compact occurrence.
Compaction itself consumes no physical batch. The inherited final accounting
rejects extra events, unconsumed batches, and unaccounted proof nodes.

## Independent connected components and lineage

The verifier groups by the complete exact signature
`(state, rho, pi, m, b, chi)` in first-occurrence order. It builds a pairwise
interval graph using rational endpoints and closure flags, independently of
the producer's running-union sweep. Overlapping intervals are connected;
touching intervals are connected precisely when at least one includes the
shared endpoint. Two open intervals remain separated at a missing knot; an
included singleton at that knot bridges them. Positive gaps never merge.

Components follow the first domain in exact sorted interval order. Parent
dispatch inside each component follows original input order, preserving
multiplicity. A singleton must return the same family ID. Every genuine merge
must match a content-addressed `guarded_union` node with those exact ordered
parents and their exact original guards. Its union endpoints, closure flags,
and all affine/family metadata are reconstructed independently. A repeated
identical call may reuse the same content hash; it must still have its own
consecutive coalescing occurrence.

The family checker separately verifies connected coverage, metadata equality,
physical lineage, and guarded witness dispatch. The occurrence checker then
establishes the unique deterministic representation and rejects a physically
valid but reordered dispatch choice. The pairwise component algorithm has
quadratic worst-case cost inside a signature group; no performance claim or
large-population measurement is made here.

## Fresh focused verification

The new `tests/test_recovered_coalesced_trace.py` contains 15 test methods,
with parameterized subcases. It includes complete hand-authored service and
charging traces in both dominance modes. Charging performs genuine merges;
the other fixture checks empty and singleton occurrences.

Adversarial coverage includes missing, reordered, duplicate and foreign
occurrences; stale and boolean coalescing IDs; missing/repeated/reordered
parents; stale union outputs; incorrect guards and guard scalar types; wrong
compact/invocation spans; forged endpoint closure; uncovered open knots and
positive gaps; component-order changes; physically valid wrong dispatch
order; redundant singleton union IDs; orphan valid nodes; and wrong schema
or representation. Positive cases include nested/overlapping intervals,
duplicate support IDs, a singleton bridge, full signature separation,
immutable detached snapshots, and unchanged result classes.

Fresh verification used Python 3.11.16:

```bash
python3.11 -m unittest tests.test_recovered_coalesced_trace \
  validation.trace5.test_checker_units validation.family5.test_checker_units -v
python3.11 -OO -m unittest tests.test_recovered_coalesced_trace -v
```

The combined normal run passed 33 test methods. The reconstructed module also
runs producer-import-denial subprocesses under normal Python, `-O`, and `-OO`
with positive and negative acceptance checks.

A separate direct integration used the reconstructed producer's explicit
`record_lineage=True` option and `InvocationTrace(..., representation=VERSION)`
on the existing tiny `invocation_trace_pilot_v1.json` fixture. Both modes passed
this independent checker: dominance off had 43 events, 10 compacts, 8 nodes,
and 1 merged cluster; dominance on had 46 events, 12 compacts, 12 nodes, and 2
merged clusters. This integration supplements, rather than generates, the
independent hand-authored tests.

No real population, C01, LP, numerical suffix optimization, historical
physical-witness replay, or heavy benchmark ran for this checker recovery.
The checked summary keeps `literal_G8_closed=False` and records
`reconstruction_status='newly_reconstructed_source'`. Real adapter validation,
population parity, research acceptance, and later release decisions remain
separate obligations.
