# Fixed matched N128 cohort, prospective at source freeze

This unpublished local source extends the authenticated OD02 completion report
checkpoint 3bf81c3. It adds only a method-aware experiment and tests; the 95
production src entries remain exactly the reviewed d7a38c02 algorithm. Generated
metadata under src/hiroute.egg-info/ is excluded only from that algorithm pin,
while every present entry remains in the full executable closure. The separate
convex-count runtime and operator envelope-compaction candidates are excluded.

The exposed original domains are OD02 energy-only N128/Hmax33 and OD06 scheduled
service N128/Hmax39. Fixed method orders are FLAT then HIER for OD02, HIER then
FLAT for OD06. Both methods use the same selected analytic C/post-service rules
and certified bound family; FLAT has its explicit singleton adapter. Queue
ordering and region aggregation remain method-specific.

Each case has preparation, two serial search/replay pairs, five slots. Two
independent dedicated case-pipeline processes run on CPUs 0 and 1, so at most
two heavy workers execute concurrently. All ten slots, failed launches, cleanup
failures and timeouts remain represented. Each exact phase is 600 seconds,
including finalization; search-worker CPU and wall caps are 900 seconds.
Preparation and verification keep their existing separate limits.

The read-only prelaunch MemAvailable requirement is 8,448 MiB: two measured
planning allocations of 3,840 MiB plus 768 MiB reserve. This is an admission
observation, not a memory reservation or aggregate hard limit. The existing
8 GiB address-space cap is per process. Shared OS/cache and other host activity
remain uncontrolled; descriptive paired timings do not establish population
superiority or isolated/cold-cache performance.

The experiment is a known-DEV correctness and scheduled-coverage comparison,
not holdout. It does not replace older 240-second failures or the separate
single-arm 600-second completion. Publication remains separately pending.
No new real cohort result or main merge is claimed by this source freeze.
