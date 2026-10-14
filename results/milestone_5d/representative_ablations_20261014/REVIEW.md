# Independent review of frozen representative ablations

Reviewed 2026-10-14, approximately 04:04–04:06 UTC. Target delivery manifest SHA256: f19e1aebf0fc7b8f00be269194e8b1b7a4c2616b56a2a53d2a852ff4077aec79.

## Verdict

No blocking solver or cache-isolation defect found. Accept these artifacts as small-domain exploratory correctness, representation timing, and selected-leg cache mechanism evidence. They do not complete production D5.2 or general performance acceptance.

## Checks performed

- Verified all hashes in the three experiment manifests and final delivery manifest. All 64 correctness rows, 192 timed rows, and 36 cold/warm rows match their frozen ordered row definitions, with no missing or duplicate cells.
- The eight specified semantic strata and four reduction/coalescing combinations use the actual solver implementations. Reduction and coalescing are distinct switches. Attained witnesses are physically replayed; frozen expected status and complete lexicographic key or unattained infimum are checked. This is not a newly executed independent optimization REF.
- Independently recomputed all 32 per-case/per-method median off/on ratios exactly. They are valid descriptive paired ratios for these fixed fixtures and repetitions. Millisecond timing, fixed within-pair ordering and only three repetitions preclude general speed claims or population uncertainty estimates.
- Examined cold/warm fixture, fresh recovery admission, engines, Region provider and counters. Every row owns its provider/router/process; warm measured execution creates fresh Problem and search state, retaining original admitted upper bound/depth. Region data are built eagerly; only counters change, not learned bounds. Source-label LRU remains off.
- Independently checked all 36 terminal keys, warmup-to-measurement cache transitions, and replay routing deltas. Cold calls are consistently 3/7/1 by fixture and warm calls zero; the mechanism is actual selected-leg reuse, not simply repeated timing.
- Analytic fixture keys agree: nonbest has direct feasible drive J=3,Q=0,H=0; charge_required needs charge 2 and one stop for J=8,Q=2,H=1 with lexicographic site s; equality needs S at s with J=13,Q=0,H=1. Each is independently compatible with the four-node fixture geometry and query constraints.
- Independently reran immutable cold/warm worker row 5 (warm charge_required FLAT) in a fresh subprocess with its existing limits. It passed with key (8,2,1,((s,C),)) and zero measured routing calls. No result file was overwritten.

## Evidence and accounting limits

Manifest creation timestamps and runner order support freezing before these measurements, and runners enforce source hashes. These local records are not external timestamp notarization. Initial correctness runner uses Python assertions and is intended for normal interpreter mode; do not claim its checks remain effective under -O/-OO. Timed and cold/warm verification use explicit exceptions.

The cold/warm protocol required independent review before launch. This reviewer received the batch after execution. The author has recorded that deviation without altering the original protocol. Subsequent review cannot retroactively satisfy a prelaunch gate. Retain the current batch as exploratory. If strict protocol closure is required, execute a separately frozen, identically specified 36-row confirmation after this review, preserving prior results; expected cost is around 24 seconds, not a production rerun.

Setup covers fresh admission and Region/landmark construction; separate seed-snapshot fabrication is outside setup but inside parent row total. Warmup solve and replay costs are separately recorded. Tiny source CPU counters can quantize to zero; these are not zero-work claims. Neither task-wide CPU nor historical 48-CPU-hour reconciliation is established by these records.

Cold/warm uses a synthetic Python router and selected-leg reuse only. It does not establish native source-label-cache performance, cold production startup, production table-free coalescing, additional tightening, general HIER superiority, or main-merge eligibility. Additional verified tightening remains absent, and representation production integration requires its own manifest and parity review.
