# Real suffix occurrences and count-only admission

`validation.real5_v2.suffix_context.RealSuffixQueries` accepts the genuine
immutable `CheckedTrace` returned by the independent real checker and the
separately pinned `TrustedRealCase`. It indexes original occurrences once,
preserves family order and inherited ancestry, and hashes only a requested
query using the unchanged canonical query bytes. It never calls the whole
population's `export_queries()` to select one occurrence. Passing a fabricated
`CheckedTrace` is outside this trusted-object API; a thin index cannot create
one.

The existing candidate and independently authored convex model builders already
consume this physical context. They receive the accepted directed time/actual
length primitives, distinct Site identities and zero identity legs. No graph
routing, metric assumption or new LP equation is introduced. Model enumeration
requires an explicit finite model-slot cap and fails unresolved before starting
if its exact census exceeds that cap.

`experiments.time_cut_v2.recorded_real.suffix_census` is a separate no-LP phase.
It cold-verifies the completed structural replay's manifest and retained
successful launcher return, checks original/current source-plan and capture
bindings, then consumes that replay's exact thin query index. This is a census
of authenticated metadata, not a reconstruction of a checked trace. The full
recorded capture need not be decoded again for this count.

For each original family occurrence, every nonempty mandatory-first-action
word up to the unchanged remaining stop bound is retained. Repeated stops and
distinct coattached Sites are counted separately. One graph-unreachable word
contributes one exclusion slot. A reachable word contributes the product of
the original arrival-band counts for its C/CS actions; an S action contributes
one. The memoized finite recurrence sums those quantities without constructing
words, LP matrices, optimizer calls or energy-feasibility pruning. Original
empty-action occurrences keep their separate count and commitment. The output
contains every nonempty query identity, thin-row hash, family multiplicity,
ancestry commitment and exact count, as well as global totals and the largest
occurrence.

The initial count-only command uses the existing reviewed replay guard with a
180-second absolute deadline, then narrows its single worker's AS soft limit
to 2 GiB. Existing host-memory and disk floors remain in force. Input index,
query-count and output limits are respectively 128 MiB, 200,000 and 64 MiB.
Limits are resource failures, never mathematical infeasibility. The census
source inventory additionally includes `validation/suffix5`; historical
structural source manifests stay unchanged.

Before any server run, bind the reviewed source commit/inventory, exact
historical capture plan, completed replay plan, attempt directory, independently
retained successful return, result, decision, manifest and query-index hashes.
Use a fresh output attempt and an explicitly allocated CPU. Example interface:

```text
python -B -m experiments.time_cut_v2.recorded_real.suffix_census \
  --source-commit COMMIT --source-sha CENSUS_SOURCE_SHA \
  --historical-plan ORIGINAL_PLAN --historical-plan-sha ORIGINAL_PLAN_SHA \
  --replay-plan COMPLETED_REPLAY_PLAN --replay-plan-sha REPLAY_PLAN_SHA \
  --replay-attempt COMPLETED_ATTEMPT \
  --replay-return RETAINED_RETURN --replay-return-sha RETURN_SHA \
  --replay-result-sha RESULT_SHA --replay-decision-sha DECISION_SHA \
  --replay-manifest-sha MANIFEST_SHA --query-index-sha INDEX_SHA \
  --cpu ALLOCATED_CPU --attempt-dir FRESH_COUNT_ATTEMPT
```

Focused tests:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python -B -m unittest -q test_real_suffix_context test_real_suffix_census
```

Cloud tests use the available Python 3.12; the project's Python 3.11 server
preflight is required before an admitted real census. This change supplies no
numerical execution authority or G8 acceptance. The exact count must first
inform a separately declared numerical resource/evidence budget. Later suffix
certificates must bind actual checked prefix families and independently replay
their inherited witnesses; index metadata and historical REF agreement cannot
replace those obligations.

## Optional exact logical-model reuse count

Add `--logical-model-plan` to the same guarded census command to count distinct
logical identities `(source bundle, original family ID, complete suffix word,
arrival bands)`. This preserves the original flat census and adds a compressed
binding map. It does not build matrices or measure LP-task reuse.

For one original family, identical words start with the same first action.
Different first actions define disjoint languages. Therefore, taking the union
of that family's original mandatory first-action pairs and applying the same
finite recurrence counts distinct complete word/band identities exactly.
Different family IDs remain separate even if all scalar cut fields coincide.
Repeated appearances of one family must have byte-identical state/rho/pi/depth
context. Exact string/pair equality is used; no new digest-based equivalence is
introduced. Graph-excluded words retain null band assignments and one slot.

Every original query position and family position is retained in the ordered
binding map, together with original first-action order, ancestry commitment and
thin-row hash. Expanding those finite languages restores every original model
occurrence; the summed occurrence count must equal the original census. The
global group ordering is only a storage choice, never a replacement for the
original query/word/band certificate ordering.

Memory and output size grow with original query/family/action references, not
with the expanded model count. C01's completed first census had 12,172 query
rows, 13,736 family occurrences and 7,652,832 expanded model slots; its measured
worker peak RSS was 319,815,680 bytes. The optional count keeps the same 2 GiB AS,
180-second deadline and 64 MiB output limit. That prior measurement is a planning
reference, not a claimed bound on the new run. The new run reports its own guard
measurements and remains count-only.

Later candidate certificate reuse may use only complete ordered LP task bytes
`{c,A,b,equalities}`, with equality checked after any digest lookup. Optimal-face
tasks cannot be predeclared identical until their preceding exact result exists.
J/Q constants, H, site/action order and original-family witness lifting remain
per binding. A logical-model count is not a count of unique LP tasks and grants
no permission to launch millions of optimizations.
