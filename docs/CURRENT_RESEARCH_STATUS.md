## Representative synthetic ablations: 2026-10-14

Separately reviewed tiny-domain evidence now records 64 correctness cells and
192 descriptive reduction/coalescing timing rows, plus 36 exploratory routing
cold/warm rows and a distinct 36-row post-review confirmation. All final cells
passed their specified exact-outcome checks. The initial serialization-failed
harness attempt and exploratory review-order deviation remain preserved and
explicit. This uses frozen reference answers, not newly solved REF cases.

See [the evidence and source-reconstruction index](../results/milestone_5d/representative_ablations_20261014/README.md).
These results demonstrate synthetic correctness and selected-leg cache reuse;
they do not establish production long-haul performance. Additional verified
tightening, production table-free coalescing, the fixed 24-row production
supplement, full D6 accounting and final D8 closure remain open. Original
192-row main outcomes remain 148 timeouts, 44 seed failures and zero exact
completions. M5-D remains incomplete.

# Current research status

## Current checkpoint: 2026-10-14

M5-V remains accepted within its historical scope. M5-D is **not complete**.
The frozen 192-row main evaluation has finished recording outcomes: 148 timeouts,
44 initial-solution failures, zero exact completions and no completed FLAT/HIER
pair. The paired speedup is NA. Detailed evidence, reproducible commands, CPU
accounting limits and remaining D5/D6/D8 work are in the stable
[M5-D report](MILESTONE_5D_REPORT.md).

Recovery work established a real two-stop feasible OD06 N128 witness and entered
both exact solvers, but the bounded runs still timed out. Candidate-domain failure
must not be described as global infeasibility. Code and installed-wheel CI are
current through `1a6bd82b4b96df04c6e849525cdb30f39ba79d55`; this is a code-quality
checkpoint, not large-scale performance acceptance. Completed-layer replay already
exists. Mid-layer durable improved-incumbent export and a global OPEN certificate
are distinct remaining capabilities.

The preselected 24-row supplement and additional ablations remain unrun; the
original CPU ledger still has unresolved host/transition components. Later
exploratory work is accounted separately. M6-H is untouched. The project may
legitimately conclude with no demonstrated benefit, after remaining deliverables
are resolved. Do not treat the historical statements below as current running
status or current input availability.

## Historical 2026-10-11 observations (preserved verbatim)

# Current research status

As of 2026-10-11, Milestone 5-V r12 final acceptance is scoped to the accepted A/B H4 and C32 results and source-bound C01 HIER; it is not an unrestricted real-data deployment claim. Milestone 5-D D0/design checkpoint `a2f12f2595ff1789ca70822c19089b40938dbdf5` was merged as PR #11, merge commit `fae2b71b342cb95fb7f578cfe031252d7e31700a`. Further work uses `dot/m5d-continuation` from that exact main commit. The protocol is in [MILESTONE_5D_DESIGN_AND_PROTOCOL.md](MILESTONE_5D_DESIGN_AND_PROTOCOL.md). D1–D3 implementation is in progress; no formal M5-D comparison or final holdout has run.

The isolated Linux D0 code-only suite passed 394 tests and 752 subtests in 62.2 s. The full bootstrap suite also passed all six normal/`-OO` groups (50, 37, and 50 tests in each mode). The macOS code-only and bootstrap attempts are retained as platform diagnostics: the accepted RSS interpretation assumes Linux units and bootstrap uses Linux CPU affinity. A first Linux bootstrap invocation hit an overly short 120 s **aggregate** watchdog, not a test failure. Logs remain in the isolated server checkout `/home/dy/HiRoute/m5d_d0_1af12a9/results/milestone_5d/d0_20261011/`. Local source hashes are recorded at `results/milestone_5d/d0_20261011/source_manifest.json`.

The previous server production checkout `/home/dy/HiRoute/project` was observed at `1af12a96ca7de909f5971e49f118322117bf07ec` before M5-D work, after an external 2026-10-11 fast-forward. This task did not update or clean that checkout. Its older 3ad6 source inventory must not be presented as a current fingerprint.

The retained real selection covers eight ODs and eight selected Sites per OD/mode, below the 12-OD and 32/128-candidate main design. A read-only check of all 32 retained states finds zero with a road-distance-based two-charge lower bound; this alone does not prove that no multi-charge instance exists. A second, independent replay preflight found an executable direct or one-stop witness for **all 32 of these frozen states** on their immutable eight-Site tables. Thus none of those exact states requires two stops. The full 30-row remapped OD set has a maximum recorded shortest distance of 289.43 km. Its full attached-Site/progress screen contains at least 32 charging Sites for every OD and at least 128 for 29 of 30 ODs.

A separate same-map geographic-extrema screen froze 31 attached road anchors before routing. Of 930 directed pairs, 478 are reachable; 78 pairs from 15 origin anchors have integer-micrometer road-distance lower bounds over 450001 m. An independent all-edge potential check passed for those 15 origins, with a one-metre margin above the frozen low-SOC one-charge allowance. These anchors cluster geographically, and their 32/128 Site eligibility and schedule support have not been checked. They establish plausible same-map multi-charge inputs, **not** a frozen independent 12-OD sample or accepted M5-D experiment. No larger map or new dataset is presently required; formal numerical work remains gated on a justified OD/input design, exact source bindings, and bounded implementation review.

A final fixed 14×14 same-map geographic grid yielded 158 attached anchors; four bounded route-screen partitions found 140 directed pairs above 450001 m among 24,806 pairs. The source-bound aggregate is `results/milestone_5d/continuation_20261011/grid14_aggregate.json`. Grid refinement has stopped. The main design requires at least 12 qualifying **queries** among 12 ODs × 2 SOC × 2 activity states (48 queries); it does not require 12 distinct long ODs or unique endpoints. Each proposed query still needs its own multi-charge, 32/128 eligible Site, and schedule support check before selection. Formal comparison and final holdout remain untouched.
