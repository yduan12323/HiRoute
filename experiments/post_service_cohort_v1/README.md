# Prospective matched post-service cohort v1

This isolated, experiment-only gate has passed independent lifecycle and method
review. Its prospective plan remains nonlaunchable; freezing requires a clean,
committed immutable source and all pinned compiler/input/source checks. It leaves
production defaults and historical gates unchanged. There has been no real OSM
or holdout launch for this cohort.

## Fixed cases and comparison

Two previously exposed DEV cases use the original candidate order, source query,
hierarchy and Hmax from `experiments/dev_cohort_v1`:

- OD02_energy_only_soc3_10: N128, Hmax33, FLAT then HIER, CPU0
- OD06_energy_and_scheduled_soc3_10: N128, Hmax39, HIER then FLAT, CPU1

Both methods select analyticC ON and the completed-departure post-service reducer
ON. They use the same q10 time, target, energy, support and historical
remaining-linear bound family. FLAT explicitly installs the reviewed singleton
adapter for that same family. Envelope sweep, convex charge-count runtime and the
optional operator-compaction candidate are OFF. There are no new production
optimizations in this cohort.

The primary purpose is matched exact outcomes and scheduled-service coverage.
Timings are descriptive shared-host observations. CPU affinity and numeric thread
limits do not establish clean caches, independent hardware or memory/I/O
isolation. Earlier 240-second timeouts and the single-method 600-second OD02
completion remain separate evidence; they are never pooled or superseded.

## Fixed resources and retained denominator

Exactly two fresh single-threaded pipeline processes run concurrently. Each is
pinned to its case CPU and supervises one heavy worker at a time. The coordinator
only supervises those two pipeline processes; it never invokes the low-level
heavy-worker supervisor while it has unrelated children.

Each case has five reserved stages: common preparation, first method search,
first method fresh replay, second method search, second method fresh replay.
The combined denominator is ten, including failed and unattempted slots. A
case-local launch, cleanup or artifact-admission failure blocks remaining slots
for that case. The independent other case retains its own pipeline. No stage is
automatically retried. A coordinator-level exception aborts both pipelines,
retains all ten slots and admits no aggregate result. Final observer/admission
errors also retain all original receipts and slots.

- Preparation: 600s wall / 600s CPU
- Exact phase: exactly 600s from the authenticated entry marker until worker exit,
  including final stores, result serialization and post-solver finalization
- Search worker: 900s wall / 900s CPU (setup is outside the exact phase)
- Fresh full-routing replay: 180s wall / 120s CPU
- Per-process virtual-address-space cap: 8GiB; numeric threads: one
- Pipeline supervisor: 90s CPU soft budget with inherited hard cap preserved,
  which must admit a 901s search-worker hard cap; 3000s coordinator wall watchdog
- Maximum heavy workers: two, with no silent reduction to serial execution

A read-only prelaunch `/proc/meminfo` MemAvailable observation must show at least
8448MiB: two 3840MiB estimated job budgets plus 768MiB headroom. The estimate is
informed by an approximately 3.6GiB prior per-job peak RSS. Missing/insufficient
memory observations fail clearly before launch. This check reserves no memory,
can become stale immediately, and provides no aggregate hard-memory/cgroup or
OOM guarantee. Each supervisor records sampled RSS independently.

## Source and evidence admission

The production slice must contain exactly 95 `src/` entries and match the d7a38c02
baseline digest `bcaf573c0d82ebee70cd877616aff9c5367883640794335ff8c081b385c57bea`.
Only the exact generated `src/hiroute.egg-info/` prefix is omitted from that
production comparison. The complete executable closure still binds metadata,
all other source entries and the new adapter/lifecycle bytes.

A frozen manifest binds the concurrency policy, per-case order, method, shared
configuration, budgets, original source/candidates/hierarchy and new schema.
Search phase identities, durable bindings, result envelopes, admissions and
progress snapshots bind the actual method. A successful process receipt alone
is not exact completion. A timeout snapshot remains censored even if its status
says `returned`.

For each completed method, admission requires an authenticated canonical terminal
payload, original Hmax, healthy final observer, matching conserved final
statistics and a fresh full-routing replay of its own durable witness. Completed
pairs compare the canonical status and full lexicographic key for attained
optima, or the proper exact primary/secondary unattained-infimum components.
Witness bytes and charging choices need not match between methods. Timeout arms
can support only independently replayed feasible incumbents. No positive
performance result is required.

## Validation and eventual interface

Tests use Python3.11 in the existing venv, explicit source paths and CPU3. They
cover synthetic lifecycle/failure fixtures and tiny native graphs, normal and
`-OO`, with no installs and no real OSM or holdout launch.

After independent approval of an immutable source only:

```
python -m experiments.post_service_cohort_v1.run --plan
python -m experiments.post_service_cohort_v1.run --freeze --input-directory INPUTS --output MANIFEST.json
python -m experiments.post_service_cohort_v1.run --gate --manifest MANIFEST.json --manifest-sha256 SHA --output NEW_OUTPUT
```

The gate CPUs are frozen to0/1. These commands document an interface and do not
launch a run by themselves. A patched pending-review status still rejects both
freeze and manifest consumption; focused tests retain that regression.
