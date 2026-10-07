# Deterministic suffix windows

`validation.suffix5.window_plan` selects bounded work from the immutable
256-model block catalogue. It runs no model builder, optimizer, server job,
certificate checker, or numerical cache. It neither admits a population nor
authenticates completion: those remain the caller's independent obligations.

```python
from validation.capture5.containers import detach_json
from validation.suffix5.window_plan import next_window, check_window_plan, coverage_plan

plan = admitted.population.plan()
pin = admitted.population.plan_sha256
selected = next_window(plan, authenticated_complete_block_ids,
                       population_plan_sha256=pin)
serializable = detach_json(selected)
# Recompute the exact selection when consuming a persisted copy:
check_window_plan(serializable, plan, authenticated_complete_block_ids,
                  population_plan_sha256=pin)
```

The population pin must come from independent admission, not an untrusted
plan's self-declared hash. Completed IDs must be fully certified blocks from
that same population. Noncontiguous completed IDs are valid; gaps, duplicates,
foreign IDs, changed spans and count mismatches in the catalogue are rejected.
The structural planner cannot detect a falsely authenticated completion claim.

Every next window takes the first 32 outstanding blocks, or all remaining blocks
when fewer remain. A partial block is outstanding and its entire original span
is selected. Execution must cold-check retained partial certificates and fill
the remaining models separately. It cannot infer full block or segment
completion from partial results, winners, or this plan's metadata.

Returned mappings and nested sequences are detached and immutable. The window
ID binds the admitted population, catalogue, selected IDs/spans, expected model
count and fixed budget. Source version, attempt identity, receipt grouping,
and completed-ID input order do not enter the ID. Completion of unrelated later
blocks also leaves the current window ID unchanged. With no outstanding blocks,
the result is `terminal_empty`, with `window_id=None` and `launch_required=False`;
it does not authorize another run or assert numerical/G8 closure.

Each operation records 900 seconds, a conservatively charged 512 MiB evidence
subquota, a 512 MiB uncompressed proof archive cap, at most 32 blocks and 8,192
models, and numerical caching disabled. These are declarations for an executor
to enforce, not a new runtime memory profile or resource-limit implementation.

For the 695,712-model catalogue and independently completed seed blocks
`0, 1352, 2535, 2687`, `coverage_plan` derives:

- 2,718 total blocks, with final block 2,717 spanning `[695552, 695712)` (160 models)
- 1,024 completed and 694,688 remaining models in 2,714 outstanding blocks
- First window: blocks 1 through 32, exactly 8,192 models
- 85 windows if every selected block completes: 84 full windows of 8,192 models,
  then blocks 2,692 through 2,717 containing 6,560 models
- `1024 + 84 * 8192 + 6560 = 695712`

These are complete-coverage planning counts, not a forecast of attempts: a
resource-bounded interruption can require another attempt on outstanding work.

Query-join metadata preserves each intersecting segment's original ID, family,
action, depth, full logical bounds, and exact selected intersections. It does
not change original query occurrence order or make an intersected segment
complete. The existing `join_projection` still requires independently
authenticated full segment certificates and aggregates, including losing and
excluded models. Tests cover compatibility with a fresh tiny admitted
population and its original query projections using synthetic results only.

Run the focused and adjacent structural suites without LP or remote execution:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B -m unittest \
  tests.test_suffix_window_plan tests.test_suffix_block_plan \
  tests.test_indexed_suffix_population tests.test_suffix_occurrence_join
```
