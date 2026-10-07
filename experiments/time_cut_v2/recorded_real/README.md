# Remote recorded-real structural calibration

This is preparation for one fixed C01 HIER-D1 calibration. It is not permission
to run an experiment. Source review and approval of the generated plan hash
precede execution through the authorized remote task. No full C01 run has been
performed by these wrapper tests.

The runtime provides two separate, serial phase profiles:

| Profile | Worker AS / sampled group RSS | Phase wall limit | Charged evidence |
|---|---:|---:|---:|
| capture-v1 | 8 GiB | 1,200 s | 4 GiB |
| replay-v1 | 16 GiB | 1,800 s | 8 GiB |

Each uses one declared CPU, a 16 GiB live host-memory floor and a 20 GiB free-disk
floor. Admission additionally reserves the full phase RSS/evidence allowance.
The small launcher and dedicated supervisor are reported separately; the
supervisor has a 512 MiB AS limit. Process-group RSS is sampled, not an exact
instantaneous kernel quota. The fixed quota includes 16 MiB for supervisor
metadata. Worker output uses the remainder with conservative twice-payload
charging; paths, file count, metadata and final manifest sizes are bounded.

The supervisor enforces phase entry/deadline, worker AS/affinity, host/disk floors
and one concurrent phase per user. It terminates and reaps the launched process
group after failure, retaining partial evidence. A bounded failure slot remains
available if the cooperative evidence writer has been poisoned. Completed files
and attempts are never overwritten. This is a cooperative validation runner,
not a security sandbox for hostile arbitrary programs.

Completed acceptance requires the separately retained successful `run_phase`
return. Its `acceptance_receipt` binds the final result, decision and manifest
after the launcher's completion checks. A caller must observe the successful
launcher return, retain and pin its exact output, then pass the parsed object as
`read_phase_result(..., successful_return=...)`. Attempt files alone cannot prove
that an interrupted launcher finished its checks; a missing return stays
unresolved. Never reconstruct that receipt from attempt files.

The capture population remains C01, H_ref=4, eight original Sites, all 2,047
original Regions, dominance enabled and exact adjacent coalescing. There is no
reference incumbent seed, route recomputation, SOC grid or suffix LP. Existing
immutable selected-leg inputs make the native routing cache unnecessary here.

Capture and replay are admitted separately. The replay must pin both the prior
resource report and exact evidence manifest and cold-rehash every artifact.
All family, batch, Region, action, compact and supplied callback records are
retained. Required candidate/terminal witnesses are independently checked by
the trace grammar. Supplemental callbacks mean all observed supplied requests;
no additional complete population of internal debug calls is asserted.

The runtime-only checkpoint does not include the separate domain implementation.
When that later checkpoint is included, its query index references the complete
immutable capture registry and retains
each exact occurrence, its roots and ancestry commitment. `domain.expand_query`
reconstructs every original query field. The index does not confer numerical
suffix acceptance. Full source/input hashes and fresh structural counts are
reported; literal G8 remains open.

If the historical C01 reference file is unavailable, plan preparation records
that fact and capture/replay remain explicitly structural-only with reference
comparison pending. A missing file is never replaced by an invented path or
reported as a successful comparison. An available reference is compared only
after unseeded search/replay; its old raw certificates are not revalidated here.

Only tiny mock/runtime tests are authorized locally. Fixed real profiles have
not been launched. See the code entry points for the forthcoming exact plan and
phase commands after source/input review; do not substitute ad-hoc larger limits.

## Prepare the exact remote plan

After the reviewed source is on the server's shared development branch, use its
existing Python 3.11 environment from the repository root. This command validates
only the current input-consumption chain and emits a new plan without searching:

```sh
mkdir -p results/milestone_5_recorded_remote
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B -m experiments.time_cut_v2.recorded_real.plan \
  --export-dir results/milestone_5_real_export \
  --manifest-sha f846eb37219a34dea74aa9a79e7673b8cdae03ae281de189cb9b602a98ac380d \
  --selection results/milestone_5_real_export/selection_manifest.json \
  --selection-sha 0e39ad906c01e05b4a4b764b3270360e309c24d1ae67d7a2e3533b6dca8af06a \
  --tree results/milestone_4r_b1/hierarchy.json \
  --output results/milestone_5_recorded_remote/plan.C01.json
```

These paths and three hashes were independently inventoried on the server. The
plan independently binds the resolved C01 state to its exact query and preserves
all eight Sites and 2,047 Regions. The missing selection-generation catalog files
are not needed by this consumer; their historical validation is not rerun or
claimed. Omit `--reference` while the supported transfer of the historical
reference report is unavailable. If it later becomes available, a new plan or a
separately reviewed post-run comparison is required; completed artifacts are not
rewritten.

Only after the plan hash, current source hashes, CPU and resource profile have
been reviewed and execution authorized, run capture with fresh attempt and return
paths. Retain stdout with shell no-clobber enabled and independently observe exit
status zero before trusting it as a successful caller return:

```sh
set -o noclobber
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B -m experiments.time_cut_v2.recorded_real.run \
  --phase capture --plan results/milestone_5_recorded_remote/plan.C01.json \
  --plan-sha APPROVED_PLAN_SHA256 --cpu APPROVED_CPU \
  --attempt-dir results/milestone_5_recorded_remote/C01.capture.001 \
  > results/milestone_5_recorded_remote/C01.capture.001.return.json
```

A completed process guard does not mean structural replay passed. Inspect and pin
`result.json`, final `decision.json`, `evidence/__manifest.json`, and the separately
retained successful return, then admit the separate replay phase:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B -m experiments.time_cut_v2.recorded_real.run \
  --phase replay --plan results/milestone_5_recorded_remote/plan.C01.json \
  --plan-sha APPROVED_PLAN_SHA256 --cpu APPROVED_CPU \
  --attempt-dir results/milestone_5_recorded_remote/C01.replay.001 \
  --capture-attempt results/milestone_5_recorded_remote/C01.capture.001 \
  --capture-result-sha VERIFIED_CAPTURE_RESULT_SHA256 \
  --capture-decision-sha VERIFIED_CAPTURE_DECISION_SHA256 \
  --capture-manifest-sha VERIFIED_CAPTURE_MANIFEST_SHA256 \
  --capture-return results/milestone_5_recorded_remote/C01.capture.001.return.json \
  --capture-return-sha VERIFIED_SUCCESSFUL_RETURN_SHA256 \
  > results/milestone_5_recorded_remote/C01.replay.001.return.json
```

There is no implicit resume, quota increase or automatic next phase. Timeouts,
resource failures and partial files remain unresolved. The independently checked
structural result explicitly records pending or completed historical-result
comparison and always leaves suffix optimization/literal G8 unclosed. Reuse one
`QueryExpander` for indexed occurrence lookups; each expansion is checked against
the exact verified query identity and shared ancestry commitment.

A provisional `result.json` alone never accepts completion. The runtime reader
requires the final launcher decision, supervisor decision, exact report/manifest
bindings and absence of a rejecting terminal record. Replay pins the final
decision and observed successful caller return independently before consuming the
capture. An interrupted launch cannot be accepted by rebuilding those files.
