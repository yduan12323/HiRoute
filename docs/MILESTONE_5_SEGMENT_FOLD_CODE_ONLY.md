# Pure block-to-segment fold

`validation/suffix5/segment_fold.py` adds
`merge_block_segments(population_plan, block_reports)`. Its result is the
integer-keyed segment mapping accepted by `occurrence_join.join_projection`.
Inputs and outputs use original logical ordinals and compact half-open tie runs.

This is arithmetic and coverage checking only. Before calling it, the caller
must independently authenticate the population and each complete report,
including every losing and excluded model's certificate and source binding.
The helper does not check certificates, authenticate receipts, admit a physical
witness, authorize a query optimum, or close any acceptance gate. A
`complete_certificates` flag expresses that caller precondition; it is not proof.
The final collector must separately bind its required population and provenance.

The helper checks canonical block IDs, ranges, counts and uniqueness; ordered
gap-free segment spans and stable IDs; exact segment/block intersections; and
the report's verified, unresolved and unsubmitted model accounting. It validates
the summary result and exclusion/tie audit types using the existing streaming
algebra. Every complete whole-block summary must exactly equal its segment
fragment fold, including every audit range and exclusion count. Declared segment
graph-exclusion counts, when present, must match completed segments. Other
population/report metadata does not confer authority and is not interpreted.

Reports may arrive in any order. Fragment order inside each complete report must
be canonical. Missing or genuinely incomplete reports leave affected nonempty
segments unresolved with no partial aggregate. Contradictory completion flags,
pending counts, or aggregates in incomplete reports are rejected as malformed.
Zero-length canonical segments are complete without model proofs. No model ID
range is expanded, and returned summaries do not alias input reports.

Validation uses synthetic results only: differential comparisons with
`aggregate_records`, tiny exhaustive partition/arrival permutations, crossed
boundaries, short final blocks, both nonattainment outcomes, exact rational
ordering, J/Q/H/pi ties and earliest winners, all exclusions, empty segments,
malformed plans/reports/fragments, direct query-join compatibility, and a compact
billion-model span. No optimizer, real input, server job, or numerical acceptance
is part of this increment.

Run from the repository root:

```
python -m unittest tests.test_suffix_segment_fold tests.test_suffix_aggregate_stream tests.test_suffix_occurrence_join -q
```
