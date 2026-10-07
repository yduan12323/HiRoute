# Bounded replay diagnosis

This opt-in command profiles the existing immutable capture. It does not run a
solver, alter any checker equation/order, or grant structural/numerical acceptance.
The prior timed-out attempt stays unresolved and its files remain untouched.

The diagnostic uses the unchanged replay-v1 runtime: one explicit CPU, 16 GiB
worker AS/group RSS, 16 GiB host reserve, and 20 GiB disk floor. Its absolute
phase deadline is shortened to 300 seconds. Only the first 180 seconds of the
post-decode checker run are observed, leaving time for input checks, decode,
report publication and cleanup. The report is bounded to 1 MiB (twice-payload
charged by the existing writer). No new concurrent scheduler or lock bypass is
introduced. CPU and all paths must be confirmed by the remote executor.

Temporary, restored wrappers record inclusive call times/counts for family
validation, physical phase checks, trace setup/walk, ancestry hashing, query
freezing and exact affine comparisons. A 1 Hz signal samples at most 182 Python
stacks, each at most 24 frames. Selected scalar/collection-length progress is
observational. Inclusive times overlap and must not be added. This is not a
full cProfile run; sampling/counter overhead is not zero. All normal checker
entrypoints remain unchanged when this diagnostic is not used.

A source snapshot binds the newly committed diagnostic file. Every historical
checker file named by the original capture plan must remain byte-identical; the
only additional inventoried source is diagnose.py. Input-manifest links and the
full existing capture byte hash are rechecked. The old plan/recorded source
identity remains distinct from this new diagnostic identity.

After pulling the reviewed commit, produce the current source inventory digest
read-only (and record git rev-parse HEAD):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B -c \
 'from experiments.time_cut_v2.recorded_real.plan import ROOT,source_inventory,digest; print(digest(source_inventory(ROOT)))'
```

After the exact diagnostic source hash and invocation are admitted, use the
already verified original plan/capture paths; the following names are placeholders,
not claims about where the remote attempt was stored:

```sh
set -o noclobber
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B -m experiments.time_cut_v2.recorded_real.diagnose \
 --plan ORIGINAL_PLAN_PATH --plan-sha ORIGINAL_PLAN_SHA256 \
 --capture EXISTING_CAPTURE_PATH \
 --capture-sha 66bdff79410db1e27aa7e1226e0698ef07bd7b5d307d00f61fbd07edaaede2ff \
 --source-commit REVIEWED_REMOTE_COMMIT --source-sha REVIEWED_SOURCE_INVENTORY_SHA256 \
 --cpu APPROVED_CPU --attempt-dir NEW_DIAGNOSTIC_ATTEMPT \
 > NEW_DIAGNOSTIC_CALLER_RETURN.json
```

The worker retains diagnostic.json after the timed sample ends. A completed
runtime means that this diagnostic report was collected, not that replay passed:
the report always states acceptance=false and structural_verified=false.
If the runtime cannot finish publication, its existing rejection/failure records
remain authoritative and no diagnostic completion is claimed. No automatic retry.

The current full replay performs all callbacks after the trace checker returns.
Because the previous real attempt never emitted after-trace, its bottleneck
precedes supplemental callback checking. Profiling will distinguish exact family
operator validation from trace traversal, ancestry commitments and copy/hash work
before choosing any optimization or parallel unit.
