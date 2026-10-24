# Research State at Rebuild Start

## Status labels

- `verified_in_this_rebuild`: checked directly in the new worktree.
- `historically_reported`: recorded by historical documentation, not rerun here.
- `evidence_available_not_rerun`: evidence is present but has not been rechecked in this rebuild.
- `evidence_unavailable`: required artifact is unavailable to this execution context.
- `unresolved`: requires further source or evidence review.

## Accepted theory

- `historically_reported`: `docs/MILESTONE_5_TIME_CUT_THEORY_REVIEW_V2.md` gives a conditional proof under H1–H8 and explicitly says it is neither machine checked nor production solver acceptance.
- `historically_reported`: `docs/MILESTONE_5_TIME_CUT_CONTRACT_V2.md` is a bounded theorem-probe contract; it excludes general production FLAT/HIER/REF acceptance.
- `historically_reported`: `docs/MILESTONE_5_V_R12_FINAL_ACCEPTANCE.md` records scoped M5-V acceptance, not the missing original combined manifest or blanket production certification.

## Implementation and experiment claims

- `verified_in_this_rebuild`: GitHub main and PR #14 refs match the task-provided SHAs at R0 inspection.
- `verified_in_this_rebuild`: branch `dot/rebuild-r0-r4` was created from the actual main SHA in a distinct worktree.
- `unresolved`: accepted proof obligations and historical results have not yet been mapped to every active implementation path.
- `evidence_available_not_rerun`: historical reports, tests and validation code are present; no tests were run in this checkpoint.
- `unresolved`: scalable completeness and performance are not inferred from historical test volume.

## Data and independent validation

- `unresolved`: raw-data availability and provenance were not tested; no real-data regeneration was run.
- verified_in_this_rebuild: static imports show four src/timecut5 modules importing validation.reference5; this violates the intended production/REF package boundary and requires migration.
- unresolved: REF optimizer independence and real-case completion were not revalidated.
- `unresolved`: historical evidence gaps and cost accounting remain unchanged.
- verified_in_this_rebuild: taskbook saved as HIROUTE_R0_R4_REBUILD_TASKBOOK.md, 57,815 bytes, trailing LF. Computed SHA-256 95f7055d28a898f7735d16c33828e278a5701f1a7b4345a796b1c73bdefb3864 differs from expected 4bf20801a3ccfc1cf64a66777902757f3727e1fad73dbb2c5f7400651cbd6fdc; exact byte identity remains unresolved.

## Historical preservation

- `verified_in_this_rebuild`: PR #14 is still at its observed head ref; no PR mutation occurred.
- `verified_in_this_rebuild`: prior checkout status and untracked hashes are in `/home/dy/HiRoute/r0_rebuild_20261024_baseline/`.
- `verified_in_this_rebuild`: original Shandong N8 bridge remains unconfirmed and was not run.
