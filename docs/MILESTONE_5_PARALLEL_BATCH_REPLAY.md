# Optional four-process selection-batch verification

The serial family checker remains the default independent reference. Its node
hashes, DAG cycles, full rational descriptors, physical parameters, operator
origins and every batch's exact parent/output IDs are checked in the coordinator.
The optional seam moves only complete union/reduction scalar obligations to fresh
worker interpreters. Drive/stop checks and the physical-anchor gate remain intact.
Ordered trace, queue/incumbent and witness replay are unchanged.

Each expected job is identified by its original batch index and digest. Its exact
ordered Piece arrays retain domains/endpoint flags, affine terms, attainment,
rho, pi and state. A canonical rational-hex encoding avoids decimal conversion
limits without rounding. Workers run the unchanged v2 continuation-equivalence
and antichain calculations; union uses the reviewed v3 exact comparison. Every
result binds its complete job bytes, case context and original batch identity.

Workers still build/check the full continuation certificate. They return its
unchanged hash and cell count. The original serial checker discarded that body
and retained the cell count, so this transport omits no previously required
check or stored proof. The full immutable capture remains necessary for replay.
This job ledger is not a numerical suffix certificate or a new acceptance gate.

Only four jobs can be in flight; there is no unbounded queue. Each serialized
job must fit 8 MiB before dispatch, at most 20,000 pieces; each compact response
must fit 32 KiB. Oversized/failed/timed-out work is incomplete, never accepted.
All expected IDs must be submitted exactly once in original order and all result
IDs must join exactly once. EOF/exit handshakes reject trailing responses. No
CheckedBundle is created until every expected job finishes and joins correctly.

The runner must spawn workers before decoding the large capture so no worker
inherits its live registry during startup. Each fresh worker has a 1 GiB AS cap
before importing validation modules and remains in the coordinator's process
group. The separately reviewed runtime retains the UID-wide lock for the group,
20 GiB sampled group RSS, a 16 GiB coordinator AS cap, a 16 GiB live host reserve
and six explicit CPUs (supervisor, coordinator, four workers). This is one bounded
parallel phase, not twelve full-graph copies or multiple uncoordinated phases.

Tiny tests compare complete bundle contents and summaries against serial checks,
including malformed results, missing/duplicate jobs, byte caps, timeout/death
cleanup and fresh-process execution. A subsequent real profile is a separate
admission and cannot turn partial job progress into completed replay acceptance.

## Bounded same-capture profile

The thin `parallel_profile` entrypoint uses the same 180-second post-decode
observation and a 300-second absolute phase deadline. Workers are created before
capture decode while the coordinator still has the exact five-CPU group mask;
the coordinator then narrows to its declared CPU. The worker input check rejects
any mismatch between its command's mask and the guard-assigned affinity.

Its source closure explicitly distinguishes the original captured checker from
the reviewed candidate: only family.py and runtime.py change; new inventoried
sources are the oracle v3, batch jobs and two diagnostic entrypoints. Historical
source blobs, current committed source bytes, original physical input chain and
complete capture hash are all checked. The full result remains diagnostic-only:
acceptance=false, structural_verified=false, with zero solver/suffix calls.

The report retains per-second submitted/completed/in-flight counts and PIDs,
plus the exact expected/submitted/result batch ledger. Timeout or interruption
preserves partial status and kills/reaps all children. There is no resumed
solver, implicit retry or skipped unfinished batch.

After review and explicit remote admission, run from the repository with the
existing verified source-plan/capture and a fresh attempt. CPU numbers below are
parameters to be confirmed against the server's available set, not assumed:

```sh
set -o noclobber
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B \
 -m experiments.time_cut_v2.recorded_real.parallel_profile \
 --plan ORIGINAL_PLAN_PATH --plan-sha ORIGINAL_PLAN_SHA256 \
 --capture EXISTING_CAPTURE_PATH \
 --capture-sha 66bdff79410db1e27aa7e1226e0698ef07bd7b5d307d00f61fbd07edaaede2ff \
 --source-commit REVIEWED_REMOTE_COMMIT --source-sha REVIEWED_SOURCE_INVENTORY_SHA256 \
 --cpu SUPERVISOR_CPU --worker-cpus COORDINATOR_CPU WORKER1 WORKER2 WORKER3 WORKER4 \
 --attempt-dir NEW_PARALLEL_DIAGNOSTIC_ATTEMPT > NEW_CALLER_RETURN.json
```

Use the previously verified ORIGINAL_PLAN_PATH and its inventoried SHA,
supplied by the remote executor. Missing
or stale source/plan pins are a blocker, not permission to reconstruct a plan
from successful outcomes. The current source inventory digest can be read using
the command in recorded_real/DIAGNOSTIC.md after the reviewed commit is pulled.
