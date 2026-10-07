# Small exact task-payload preview helper

`validation.suffix5.task_catalog` prepares only an explicitly selected, bounded
list of logical models from a genuine checked family bundle. It is not a real
runner, numerical verifier, or authorization to compile the full population.
Selection must be declared structurally before model outcomes are observed.

Both existing candidate and independently authored convex model builders must
produce exactly the same complete model. Raw model bytes retain original family
ID, complete word, original arrival bands, J/Q constants, H and site/action
sequence. The helper stores feasibility and primary LP tasks only: later
optimal-face tasks depend on exact preceding certificates and remain unknown.

Each task key hashes the entire ordered canonical `{c,A,b,equalities}` payload.
Every repeated digest is checked against the retained complete bytes; a digest
collision fails closed. Rows are not reordered or algebraically normalized to
increase reuse. Shared task payloads never merge original model identities or
authorize reuse of another family's physical witness. The helper does not
produce certificates, call an LP solver, or claim full-population coverage.

Callers must supply finite model count, per-model bytes, total model bytes,
per-task bytes, total task bytes and unique-task count limits. Encoded payloads
are consumed in bounded chunks. Retained-byte accounting uses the immutable
payload dictionary itself; there is no separate mutable byte counter that can
become stale after an interrupted insertion. Calls reject concurrent/reentrant
admission. These limits bound stored wire bytes, not Python object or transient
encoding memory, so a surrounding reviewed process guard is required for a real
preview. A partial or cap-stopped preview establishes no numerical acceptance.

Tiny tests compare both model builders, preserve different coattached Site words
sharing identical LP tasks, and reject ordering/face/key/cap/type changes:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python -B -m unittest -q test_suffix_task_catalog
```

The task-catalog helper alone neither implements nor launches a server preview.
The guarded thin runner below is a separate integration. First obtain
the completed logical-model count, then bind a small deterministic selection,
the actual checked bundle and a separately reviewed/admitted resource plan. Use
the measured payload sizes and construction times before deciding whether a
full disk-backed task catalog is justified.

## Frozen structural selection

`preview_selection.select_preview` implements policy
`first-two-families-per-depth-all-first-actions-lengths-extreme-bands-v1`.
It chooses the first two family groups at each prefix depth in the authenticated
logical-plan order (or all groups if fewer than two exist). For each selected
group, each frozen first action and each remaining word length, it chooses the
lexicographically first syntactically legal word of that exact length. No energy,
time, LP feasibility or objective result is consulted. Repeated stops remain
legal. The first and last original arrival-band assignments are selected, with
identical endpoints deduplicated; a graph-excluded word has one null assignment.

C01 has one selected depth-0 family and two at each other depth, eight first
actions, four remaining horizons and three charging bands. Consequently the
selection is exactly `2*8*(1*4+2*3+2*2+2*1) = 256` distinct models across seven
families, distributed `64,96,64,32` over depths 0–3. This is a construction-cost
sample, not a representative estimate of every mixed-band/word/family reuse
rate or a numerical proof for the population. The complete 695,712 unique
logical models and 7,652,832 original occurrences remain required later.

The small runner below must authenticate the completed replay and logical-count
returns/manifests, pin the capture bytes, recompute this exact metadata selection
before matrices, and obtain a genuine freshly verified CheckedBundle using the
existing bounded family checker. It must never manufacture that type from
index flags. The approved implementation envelope is the existing 20 GiB group
RSS / 16 GiB host reserve with four 1 GiB scalar-check children, 480 seconds total,
and 64 MiB aggregate model/task payloads. Only source review and a separate exact
launch admission can enable a real attempt; no execution is implied here.

## Thin guarded preview runner

`experiments.time_cut_v2.recorded_real.model_preview` uses that fixed policy and
the existing batch replay guard. It authenticates the retained successful
structural replay and logical-count returns, cold manifests and original index,
recomputes the logical plan, and writes the exact selection before decoding the
capture or constructing matrices. Four fresh scalar-check workers start while
the coordinator still has its five-CPU inherited mask; only then is the
coordinator pinned separately. The existing exact endpoint-join family checker
validates all nodes/batches and the provenance-derived physical anchor states.
The returned genuine CheckedBundle must match the completed index and each
selected family's full scalar/context fields.

Only the declared 256 selections reach the existing candidate and independent
model builders. The aggregate streamed model/task files must stay within
64 MiB, including their envelopes. The runner retains exact payload hashes,
measured construction wall/CPU time and stored byte counts. Its numerical and
full-population acceptance flags remain false. It preserves the old ordered
trace proof, rather than claiming to have replayed that grammar again. Inputs,
loaded sources and completed proof bindings are checked again before finalizing.

The command requires every existing structural-census argument, plus the exact
logical-count attempt/return/report/source pins, the preserved capture path,
five allocated worker CPU IDs, a separate supervisor CPU and a fresh attempt
directory. The entry-time absolute deadline is 480 seconds; the existing
20 GiB group/16 GiB host-reserve profile is unchanged. Example additional flags:

```text
python -B -m experiments.time_cut_v2.recorded_real.model_preview \
  [the explicit source, historical-plan and completed replay pin arguments] \
  --logical-attempt COMPLETED_LOGICAL_COUNT \
  --logical-return RETAINED_LOGICAL_RETURN --logical-return-sha RETURN_SHA \
  --logical-report-sha REPORT_SHA --logical-source-sha SOURCE_SHA \
  --capture PRESERVED_CAPTURE --worker-cpus COORDINATOR CPU1 CPU2 CPU3 CPU4 \
  --cpu SUPERVISOR --attempt-dir FRESH_PREVIEW_ATTEMPT
```

This illustrative command is not executable until all placeholders are replaced
with verified inputs and separately admitted CPU/resource assignments. It must
not be used as a default full-population compile or LP command.

Focused preflight includes `test_real_model_preview`,
`test_suffix_preview_selection`, and `test_suffix_task_catalog`. Tiny tests
exercise genuine fresh family checking, selected model/task hashes, wrong
capture/bundle/source/count-return bindings, model-builder disagreement, and
payload-cap failure. Existing guard tests cover process admission and cleanup;
the thin runner does not introduce a new resource controller.
