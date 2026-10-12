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
state. The handoff binds PID 2286454, its `/proc` start ticks and command-line
hash, the original source and output roots, and the complete set of old row
unit IDs with their cgroup paths. The controller independently scans process
arguments, checks the exact PID/start identity, inspects systemd `ExecStart`
properties for generic `hiroute-m5d-<uuid>.service` names, and checks every
owned cgroup. A handoff is rejected if any identity or cgroup detail is absent.
The handoff also pins the trusted `/home/dy/miniconda3/envs/hiroute/bin/python3.11`
binary by SHA-256, implementation, version and cache tag; that exact runtime
launches each row. One empty precreated boundary-row directory can be adopted.
Every new row gets an exclusive claim and is launched through the existing
systemd supervisor under the unchanged per-row limits. The controller and
loaded supervisor must come from the same frozen source tree, whose supervisor
file is also bound by the manifest source hash.

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
identities in the denominator. The controller captures its outside-main CPU
baseline before source and evidence validation, and reserves another 60 seconds
for final state/ledger writes. A pause for fewer than four effective CPUs still
rechecks the aggregate budget and stops if that budget is exhausted.

## Durable state and failure handling

Each successful admission records the row id and index, worker regime, active
cgroup identities and `memory.current` bytes, `MemAvailable`, memory headroom,
effective CPU count, the per-admission CPU budget calculation, and the
admission decision. The sample and exclusive row claim are atomically saved
before the supervised worker starts. The fifth-slot admission also records the
separate 4-to-5 ramp event.

Completions may arrive out of order. The private continuation ledger records
each durable receipt, row claim, and charge; the shared main state advances
only across a contiguous manifest prefix. Before a resumed ledger advances
state or admits a row, the controller rechecks every completed row's admission
record, claim bytes/hash, receipt bytes/hash, receipt-to-state fields, and
aggregate charge. Any unresolved in-flight claim is fail-closed and requires
manual receipt review; it is never automatically rerun. A finished Future is
reconciled before the next claim, remains reserved at its full 8-GiB cap until
then, and blocks admission when it completed with an error. A supervisor or
verification failure stops new admissions while already claimed rows are
collected and charged.

The code-only gate exercises resource arithmetic, cgroup sampling, receipt and
claim durability, outcome-independent ramp eligibility, out-of-order prefix
reconciliation, runtime/source bindings, old-process and systemd-unit checks,
the completed-Future admission race, and a mocked four-to-five transition. The
mocked test launches no numerical row. The retained snapshot does not contain
the old PID's start ticks or the Python binary hash; those exact values and the
complete unit inventory still need to be captured and independently reviewed.
This remains an unvalidated draft and does not authorize a live continuation.
