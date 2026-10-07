# Recorded coalescing producer recovery

This is a reconstructed opt-in producer bridge above the published PR7 code.
It is new source requiring its own review; unavailable historical review hashes
and completed population runs do not certify it.

Existing untraced defaults remain unchanged. To record HIER coalescing, enter
`Recorder()` and `InvocationTrace(recorder, representation=VERSION)`, then pass
`record_lineage=True` to the synthetic or immutable-leg HIER coalesced solver.
A matching active Recorder and explicit v2 trace are required.

A merged piece obtains a fresh `guarded_union` node containing every original
parent ID and exact energy guard in callback dispatch order. The output never
inherits the first parent's identity. Recorded callbacks recheck IDs, guards,
wire types and dispatch order before realizing a witness. Singletons retain
identity; gaps, different cuts and different physical/objective contexts retain
the existing coalescing behavior.

Trace schema `family5-hier-trace-v2` adds the fixed representation identifier.
Every advance, finish or reduction records input compact, physical batches,
output compact, then the existing invoke event. Empty and singleton compact
occurrences are retained. A compact payload contains `coalescing_id`, ordered
`input_families`, `output_families`, `input_guards`, and an empty `batch_range`
at the exact current batch cursor. Initial invocation has no compact calls.

The independently authored reconstructed v2 checker is a separate component.
Producer hashes and callback assertions alone do not certify physical trace
completeness, mathematical family validity or literal G8.

Focused Python 3.11 verification uses:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python -B -m unittest -q \
  tests.test_recorded_coalescing_recovery tests.test_time_cut_coalescing \
  tests.test_coalesced_solver tests.test_trace_coalescing_integration
```
