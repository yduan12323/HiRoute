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
