# M5-D evaluation and acceptance report

Outcome: **M5D_LIMITED_BY_DATA_OR_SCALE**. Prepared against repository 7dbd82. Original and supplemental evaluations are terminal; the separately supervised real checkpoint trial is terminal. This is a bounded research-report closure, not an assertion that every original implementation/performance requirement passed.

## Findings already supported

The original preregistered main matrix recorded all 192 rows: 148 time_limit, 44 incumbent_search_failed, zero exact completions, and zero completed exact FLAT/HIER pairs among 96 bindings. The paired end-to-end speed ratio and confidence interval are NA. Equal timeout caps are not equal performance. All failed rows remain in the denominator.

Later recovery established an independently replayed OD06 N128 two-stop feasible witness and entered both exact engines; the bounded production runs still timed out. Reachable S-only sites in the N32 candidate set indicate coverage limits, not broken chargers or global infeasibility. The incumbent is not an optimum. Routing dominated completed operations in sampled prefixes; this is not a universal whole-query bottleneck claim.

The separate synthetic ablations comprise 64 correctness cells, 192 descriptive reduction/coalescing timing rows, 36 exploratory cold/warm rows and 36 separately identified reviewed confirmation rows. They support fixture-level outcome/witness agreement and cache reuse only. Frozen reference answers are not newly recomputed REF solves. Retain the serialization failure and review-order deviation. Additional tightening and production coalescing have not been demonstrated.

## Terminal supplement: all 24 rows accounted

Fixed denominator: 24, separate from the original 192. The strict terminal reporter records 23 time limits and one infrastructure-unknown interruption. All 23 completed process-group receipts verify cleanup; the interrupted row's prior-namespace cleanup is unknown and is not inferred. Every recorded final phase is seed_started. There are zero recorded exact-search starts, zero exact results and zero completed sequential-baseline results. The interrupted row is retained without replacement.

The 12 full-universe rows have 11 timeouts and one infrastructure-unknown outcome; the four same-ALT member-scan, four repeat and four sequential-construction rows all timed out. Thus none of these runs measures completed full-domain exact search, member-scan benefit or real transportation gain. No feasible sequential result was emitted, so the conditional saved-witness reconstruction is unnecessary for this batch. Joint-versus-sequential clock, overlap, stop-count, charge, detour and window comparisons are unavailable, not zero. Seed/proposal failure does not prove physical infeasibility.

The public terminal projection and independently recomputed receipt audit are indexed at results/milestone_5d/fixed24_continuation_20261014/. Source/host/runtime amendments prevent an unqualified pooled speedup claim against the original main batch. The mathematical and performance comparisons remain unavailable when the relevant solver never started.

## Completed real checkpoint integration trial

The portable durable-incumbent and completed-layer envelope are source-bound and covered by normal/optimized code tests. In the separate OD06/N128 real trial, both fresh verifiers reconstructed their method's depth 1 envelope byte for byte and independently replayed the original two-stop feasible witness. FLAT recovery took 112.6934 s wall; HIER recovery 114.7523s. Both exact searches had first hit their 120 s exact-search limits; neither completed exact optimization or improved the initial witness. All four supervised stages verified cleanup.

The conservative stage total is 515.558138019 CPU seconds plus 120 seconds preparation allowance, 635.558138019 total, versus 1160 reserved. The 120-second allowance is trial preparation allocation, not the full engineering/development cost. These are separately accounted integration diagnostics, outside the 192/24 denominators. The two method-specific checkpoint hashes and sanitized receipt provenance are in results/milestone_5d/combined_checkpoint_20261014/. Recovery replays from the original seed under identical source/domain/policy; work after the saved complete layer is recomputed. This is not arbitrary mid-layer continuation. The primary-only envelope is not an attained or lexicographic optimality certificate or a global gap. These results establish this query's depth 1 integration, not all depths, queries or production deployments. The source hierarchy file is verified, while HIER runs an explicitly bound sorted-ID binary Region policy (sorted_site_ids_binary_split_leaf1_v1); equivalence to the original frozen hierarchy topology is not claimed. Fresh recovery checks the same generated Region tree, membership/action coverage and bound summaries.

## Cost and protocol limits

Original main row cgroup CPU: 99,559.649486 s (27.655458 h). Continuation host/controller CPU: 4,265.765481 s. Known combined subtotal: 103,825.414967 s (28.840393 h), excluding the recorded conservative pre-main 10.536667 h and unresolved serial-host/transition/tail terms. The original 48-hour compliance gate remains unresolved, not passed. Later user-authorized work is separate and does not erase old charges. Cumulative host snapshots must not be summed.

The fixed supplement conservatively accounts 14,939.557706423 seconds: 13,789.557706423 known row charges, 670 seconds reserved for the interrupted row and 480 seconds preparation allowances. The separately reported 563.790783017 controller seconds are already included in the known row-charge construction and must not be added again. Unique measured total CPU is unavailable. Its original and recovery planning reservations overlap and are not measured use. Report measured, conservatively charged, reserved and unknown values separately. Its cloud guard is per-process address space; it is not aggregate RSS or cgroup enforcement. Keep all setup, source hashing, routing, seed, exact search, persistence, witness verification and reconstruction costs in their actual scopes. Missing phase fields stay null.

## D1–D8 disposition

The machine-readable requirement_dispositions.json in the compact closure bundle separates implemented interfaces, bounded test evidence, censored evaluation, missing capabilities and unresolved accounting. It also maps the D6 correctness obligations to existing test/evidence entries. This index is not a new acceptance waiver.

## Acceptance decision and residual gaps

Final outcome: M5D_LIMITED_BY_DATA_OR_SCALE. The fixed main and supplemental evaluation attempts support a scale-limited conclusion, with no demonstrated HIER benefit. Full implementation acceptance is not declared: additional tightening is unimplemented, production table-free coalescing is undemonstrated, real transport comparison is unavailable, the original 48-hour host/tail accounting is unresolved and one infrastructure interruption has unknown cleanup. These are explicit residual requirements/limitations, not passed gates. No new correctness contradiction is asserted by these censored outcomes. Do not infer fullgraph optimality, SOTA superiority, unrestricted feasibility, deployment readiness, or real-world navigation safety.

## Compact evidence entrances

- Original matrix and reproduction: results/milestone_5d/terminal_state_audit_20261014/.
- Synthetic ablations: results/milestone_5d/representative_ablations_20261014/README.md.
- Consolidated acceptance/manifests: results/milestone_5d/final_closure_20261014/.
- Fixed supplement: results/milestone_5d/fixed24_continuation_20261014/public_report.json and public_receipt_audit.json.
- Real checkpoint trial: results/milestone_5d/combined_checkpoint_20261014/summary.json.
- Current code CI: https://github.com/yduan12323/HiRoute/actions/runs/38512690819 at 7dbd82; the delivery commit's hosted CI will be verified in its external publication receipt, without rewriting this report to embed its own commit ID. Code CI is not scientific acceptance.
- Claim limits and comparability: ../paper/claims_evidence.md and ../paper/related_work.md.

## Reproduction and source provenance

From the repository root, reproduce the original terminal audit:

```sh
python scripts/summarize_m5d_terminal_state.py --manifest results/milestone_5d/terminal_state_audit_20261014/inputs/frozen_main_phase_v3_20261011.json --state results/milestone_5d/terminal_state_audit_20261014/inputs/main_state.public.json --parallel-state results/milestone_5d/terminal_state_audit_20261014/inputs/parallel_state.public.json --output /tmp/hiroute-terminal-audit-new
python scripts/plot_m5d_status_counts.py --rows results/milestone_5d/terminal_state_audit_20261014/benchmark_results.jsonl --output /tmp/hiroute-status-figure-new
```

Destinations must be new. Public projections allow reproducible summary counts; retained private-source hashes record provenance but do not independently authenticate or reconstruct unavailable original raw bytes. Main numerical source 14f2b844, frozen manifest a575039c, isolated manifest checkout a99f534, later runtime and CI heads have distinct roles. Record every actual source/input/toolchain digest in the manifest index rather than using the latest repository commit as every experiment's source. Supplement public reproduction instructions are supplied with its fixed24 evidence index. To regenerate the common typed outcome/evidence entrypoints:

```sh
python scripts/consolidate_m5d_closure_outcomes.py --main-rows results/milestone_5d/terminal_state_audit_20261014/benchmark_results.jsonl --supplement-report results/milestone_5d/fixed24_continuation_20261014/public_report.json --supplement-audit results/milestone_5d/fixed24_continuation_20261014/public_receipt_audit.json --output /tmp/hiroute-closure-outcomes-new
```

The 216 normalized benchmark rows retain explicit populations of 192 and 24; they are not pooled into one performance estimate. The 25 verification rows are one main bookkeeping check plus 24 receipt/interruption evidence entries, not 25 solver-witness passes. No private raw scheduler snapshots belong in the public bundle.

## Handoff

This report is delivered for review with the residual requirements listed above. M6-H remains unrun: freeze algorithm/source/native compiler, candidate and preprocessing policies, untouched OD/geographic holdout groups, resource limits and statistical methods before proposing any later execution. The task ends at the report/code/review handoff. No automatic main merge or final holdout.
