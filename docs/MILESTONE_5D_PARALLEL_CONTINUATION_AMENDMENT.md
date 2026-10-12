# M5-D parallel continuation amendment

**Status: UNVALIDATED DRAFT for independent review. This document does not
authorize a live continuation launch.**

This amendment changes only orchestration after a reviewed serial-to-parallel
handoff. The frozen 192-row manifest, row order and identities, query and pool
bytes, numerical row runner, and each row's 600-second, 8-GiB, one-CPU limit
remain bound to their existing hashes. The original serial scheduler and
production checkout are not rewritten by this controller.

## Handoff and worker regimes

The coordinator starts only after the old scheduler has exited and all of its
row units are empty. It verifies the manifest, state, source and input hashes,
and requires a separately reviewed handoff bound to the exact durable main
state. One empty precreated boundary-row directory can be adopted. Every new
row gets an exclusive claim and is launched through the existing systemd
supervisor under the unchanged per-row limits.

The initial regime targets four workers. The ramp gate is fixed in the
amendment: the first four rows launched by this controller must each have a
durable, rehashed supervisor receipt, with no supervisor or verification
failure recorded. The gate ignores solver status, seed result, and runtime.
After the receipt gate passes, admissions used to fill four active slots are
labeled `ramp_armed`. The coordinator enters `ramped_5` only when an admission
with four active row cgroups also passes the five-worker worst-case memory and
budget checks. That fifth-slot admission records the ramp event and its four
receipt hashes as a separate regime.

## Admission limits

All resource admission and claims run under one exclusive coordinator lock.
For each candidate row, the controller samples `MemAvailable` in bytes from
`/proc/meminfo` and `memory.current` from each active row's systemd cgroup v2
directory. It verifies each sampled cgroup's `memory.max` is exactly 8 GiB. A
missing cgroup before unit creation reserves that active row's full 8-GiB cap;
an invalid sample pauses admissions.

For a candidate row, the memory test is:

```text
MemAvailable >= 8 GiB host reserve
                 + 8 GiB for the candidate row
                 + sum(max(0, 8 GiB - memory.current)) for active row cgroups
```

This accounts for current unrelated host load through `MemAvailable`, keeps an
8-GiB host reserve, and preserves enough headroom for every active row to grow
to its full cgroup cap. If headroom falls below that bound, the coordinator
records a pause sample and waits for an active row to finish or memory to free
before admitting another row. Python RSS is not used for admission.

Before every claim, the coordinator also checks the existing 117,000-second
main cgroup ceiling, 610-second reservation per unfinished row, 60-second
outside-main guard per row, and reviewed remaining outside-main budget. A
failed budget check stops further admissions and preserves all fixed row
identities in the denominator.

## Durable state and failure handling

Each successful admission records the row id and index, worker regime, active
cgroup identities and `memory.current` bytes, `MemAvailable`, memory headroom,
effective CPU count, the per-admission CPU budget calculation, and the
admission decision. The sample and exclusive row claim are atomically saved
before the supervised worker starts. The fifth-slot admission also records the
separate 4-to-5 ramp event.

Completions may arrive out of order. The private continuation ledger records
each durable receipt and charge; the shared main state advances only across a
contiguous manifest prefix. Resume replays already recorded completions into
that prefix. Any unresolved in-flight claim is fail-closed and requires manual
receipt review; it is never automatically rerun. A supervisor or verification
failure stops new admissions while already claimed rows are collected and
charged.

The code-only gate exercises resource arithmetic, cgroup sampling, receipt
durability, outcome-independent ramp eligibility, out-of-order prefix
reconciliation, and a mocked four-to-five transition. The mocked test launches
no numerical row. Live handoff, host measurements, and the transition remain
subject to independent review before any parallel launch.
