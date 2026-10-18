# M5-D evaluation and acceptance report

## Current coverage and delivery checkpoint

Updated 2026-10-17 23:17 UTC against consolidation base `d5dad19a0d5954aeac0d9f6c653d72a4e65fca51`. **M5D_LIMITED_BY_DATA_OR_SCALE remains the empirical disposition.** This does not mean every D1–D8 field is satisfied or that final delivery is complete. The dated reconciliation below remains useful for clause-level evidence; this section supersedes its older global progress and publication statements.

### Disjoint populations and current evidence

| Population | Fixed denominator | Authenticated outcome / interpretation |
|---|---:|---|
| Original main | 192 method rows / 96 bindings | 148 time limits, 44 seed failures, zero exact completions; paired speed and OD-grouped uncertainty NA, completed-pair subset 0/96 |
| Original supplement | 24 rows | 23 pre-search timeouts and one infrastructure-unknown interruption; retain all failures and unknown cleanup |
| [Tranche A (historical artifact)](REPRODUCING.md#historical-results) | 8 domains / 16 methods / 40 operational slots | All 40 SUCCESS; 16 authenticated attained optima with own fresh physical replays; 8 canonical paired agreements |
| [Tranche B (historical artifact)](REPRODUCING.md#historical-results) | 7 domains / 14 methods / 35 operational slots | 20 SUCCESS, 3 FAILED_NO_SEED, 12 BLOCKED_NO_COMMON_SEED; 8 exact methods / 4 canonical pairs; no timeout |
| [Separately linked prior OD06 N128 (historical artifact)](REPRODUCING.md#historical-results) | 1 domain / 2 methods / 5 operational slots | HIER exact, FLAT exact-phase timeout and feasible-only replay; no completed pair or speed ratio; separate 57-check grid-identity qualification |

Deployment boundary: heuristic seed exhaustion and failure inside a truncated candidate set must be presented as feasibility unknown in that declared domain, never as globally unreachable, infeasible or unsalvageable. The separate repaired OD07 N149 transportation comparison does not repair original N128 outcomes and cannot justify silently substituting candidates. Retain failed preparation and all four blocked descendants when no common seed is authenticated.

The completed accounting of the fixed A+B+linked grid covers 16 domains / 32 methods / 80 slots: 25 exact methods, one prior FLAT timeout and six blocked methods; 12/16 domains have both methods exact. Its 80 operational slots comprise 64 SUCCESS, 3 FAILED_NO_SEED, 12 BLOCKED_NO_COMMON_SEED and one prior TIMEOUT. Success slots include preparations and replays, not just solver completions. It is not a replacement main denominator, a full candidate-universe check, a holdout or a population sample. Do not pool timings across its source/runtime/accounting scopes. The original main remains zero-completion even though later known-DEV queries now have exact endpoints.

A's [summary (historical artifact)](REPRODUCING.md#historical-results) preserves every slot, key, seed-derived Hmax, explored depth, own replay, cost scope and returned charging-action count. Its numerical source is `7d23f28af3ecfdb9d3be56ddbc45e79c7dc64850`; batch SHA256 is `0fcbfd92003c0636db5ec98d95b30de1344bb024d89abee2b74470cf7b3f7a1d`. Whole invocation wall is 5738.427634 s and waited-children CPU is 5726.834826 s. Standalone method wall includes the full shared preparation plus that method's worker and replay; shared preparation physically ran once. Those standalone costs must not be added as physical pair cost. Nested timers are not additive unique CPU. Per-process maxRSS and sampled process-tree RSS are not aggregate simultaneous peak guarantees. Independent runtime audit passed 356 checks; separate report-review evidence remains separate from embedded originals.

The A report's positive charging-action counts are not independent proofs of minimum required charges. Fixed-order shared-host per-domain ratios do not establish causal or generalized HIER advantage; no population confidence interval is inferred from repeated OD timings. The old 48-hour accounting gaps are not repaired by the newer bounded reservation/accounting records.

B ended at 2026-10-17 23:17:21 UTC with return code 0. Whole invocation wall was 2598.046950 s; waited-children CPU was 2592.613878 s, scoped to its own external invocation and reaped descendants. Its conservative CPU reservation was 31,680 s, not measured CPU. Four exact pairs are OD08/09 high-SOC N32/N128. Three heuristic seed failures are OD06/07 low-SOC N32 and OD07 low-SOC N128, each retaining four blocked descendants. Feasibility is unknown; no failed domain is silently replaced by a repaired candidate set. No B timeout, unknown receipt or retry is reported. See the B summary for complete cost and source scopes.

### D8 delivery checklist and stopping point

- Delivered evidence includes the new interfaces/tests, declared finite model domain, original failure-inclusive matrices, bounded reduction/coalescing/tightening/cache evidence, bottleneck findings, the three-family [literature matrix](../paper/related_work.md#compact-comparability-matrix), OD07's six-quantity feasible transportation comparison, [claims](../paper/claims_evidence.md) and [paper outline](../paper/outline.md). Existing compact closure manifests stay source-bound to their original snapshot; later evidence bundles retain their own manifests and receipts.
- The admitted B continuation is terminal: its [four-file report (historical artifact)](REPRODUCING.md#historical-results) retains all failed and blocked slots, cleanup, runtime/source identity, scoped accounting and reversible originals. Independent [terminal audit (historical artifact)](REPRODUCING.md#historical-results) passed 246 checks, [report review (historical artifact)](REPRODUCING.md#historical-results) passed 3,112 and [packaging verification (historical artifact)](REPRODUCING.md#historical-results) passed 4,370. These artifacts are separate from the unchanged four-file report. The [57-check linked-cell identity audit (historical artifact)](REPRODUCING.md#historical-results) is retained separately and is not a new numerical run. Final local consistency checking does not verify public delivery.
- Historical unmet accounting evidence remains unmet: unavailable exclusive phase splits, unique lifetime CPU and the prior-namespace cleanup gap. Keep null/unknown fields and explicit limitations. D7.3 allows LIMITED; it does not waive or manufacture these fields.
- Existing installed production regression receipts passed 583 tests plus 9,273 subtests in each normal and `-OO` mode for their pinned source. The 96-entry production digest remains unchanged; experiment wrappers have their own focused reviews/tests. This is reused scoped evidence, not newly run full CI for a documentation commit.
- Final public push and draft-review-PR delivery must be verified against the actual delivered commit; the last reported public state remains the earlier `36106` prefix and is not evidence of this local consolidation. The previous PR link and historical CI are not that verification. Main merge is not claimed. Full taskbook delivery must not be declared complete while these required delivery fields remain unsupported.
- M6-H and paper closure are later exits. Preserve a source/input/candidate/statistical freeze proposal, isolate untouched OD/geographic groups, and wait for approval before reading or running final holdout. No positive-benefit requirement or additional optimization is added to M5-D closure.

### Reproducing the preserved evidence without a numerical rerun

From this repository root, the following checks the archived A bundle and all reversible UTF-8 originals, without graph reads, native loading, environment changes or solver execution:

```bash
python - <<'PY_CHECK'
from pathlib import Path
import hashlib, json
p = Path('results/milestone_5d/dev_coverage_tranche_a_20261017')  # Use tranche_b below for B
i = json.loads((p / 'evidence_index.json').read_text())
b = p / i['bundle']
assert hashlib.sha256(b.read_bytes()).hexdigest() == i['bundle_sha256']
files = json.loads(b.read_text())['files']
for name, record in i['files'].items():
    data = files[name].encode('utf-8')
    assert len(data) == record['size'], name
    assert hashlib.sha256(data).hexdigest() == record['sha256'], name
s = json.loads((p / 'summary.json').read_text())
assert s['authenticated_exact_method_rows'] == 16
assert s['canonically_agreeing_completed_domains'] == 8
assert s['slot_status_counts'] == {'SUCCESS': 40}
print('A archived evidence integrity and headline counts verified')
PY_CHECK
```

For B, the same integrity loop applies with directory `dev_coverage_tranche_b_20261017`, exact-method count 8, canonical-pair count 4 and slot counts `{'SUCCESS': 20, 'FAILED_NO_SEED': 3, 'BLOCKED_NO_COMMON_SEED': 12}`.

Numerical reproduction requires the exact source, pinned installed/runtime/native identities and all nine checksum-bound raw inputs retained by each run's manifests, plus a newly reviewed resource reservation and fresh external output directory. The wrapper interfaces and freeze/run command templates are in [the tranche protocol](DEV_COVERAGE_TRANCHE_PLAN.md). Reusing existing output paths is prohibited; these instructions are not a request to rerun A or restart the active B invocation. No fresh numerical or CI run was performed for this consolidation.

## Current taskbook reconciliation — 2026-10-17

**Disposition: M5D_LIMITED_BY_DATA_OR_SCALE.** This is one of the four final outcomes explicitly allowed by original D7.3, not a claim that every requirement passed. The original [user-supplied M5-D taskbook](time_cut_v2_authority/MILESTONE_5D_DOT_TASKBOOK.md) defines this scope; its byte provenance is [recorded here](time_cut_v2_authority/MILESTONE_5D_DOT_TASKBOOK_PROVENANCE.md). This section supersedes stale *current-status* statements below; the earlier report remains intact as a dated evidence snapshot. Historical acceptance JSON, failure rows, denominators and source identities are unchanged.

### What is newly delivered, and what it does not establish

- Source `66c2f459a52d9d28c85d87967a26034d3d074dec` contains opt-in onward ALT tightening, table-free exact adjacent-cut coalescing, streamed sequential construction and the verification-supervisor race fix. The [OD02 three-arm integration (historical artifact)](REPRODUCING.md#historical-results) ran on original numerical source `e00edaf6dcecbc9f71ae174862761ea13de6ea89`: baseline, onward-only and coalescing-only all timed out at the 120-second search-phase cap and ultimately received fresh independent feasible-witness verification. The original coalescing verification infrastructure failure remains a failed stage; its separate successful verifier recovery does not rewrite that outcome. The observed coalescing counters are repeated piece visits in partial checkpoint snapshots, not unique compression or full-run speedup.
- The [OD07 independent first-sequential-feasible comparison (historical artifact)](REPRODUCING.md#historical-results) completed construction plus fresh physical replay of both sequential and preselected joint plans on the declared 149-Site/Hmax37 known-DEV domain. Physical elapsed was 34257.673619 versus 25591.211474 seconds; Q was 109.562980 versus 71.448109 kWh; both used two stops and met the activity window; overlap was 0 versus 2155.615330 seconds; selected-path distance was 550.723819 versus 521.093942 km. The baseline stops at first sequential feasibility, and its generator retains concurrent-clock proposal pruning; it is not sequential optimization. The stored joint comparator had a previous 120-second search allowance. Different routes, charge amounts, terminal energies and search effort preclude a causal-overlap or fair solver-speed claim. The six requested physical quantities are reported; the earlier four sequential timeouts remain in their original population.
- The [fixed three-DEV recovery batch (historical artifact)](REPRODUCING.md#historical-results) retains all 27 stages, including 12 search timeouts and 12 fresh witness verifications. All six indexed/recompute pairs had equal full feasible keys. These later known-DEV experiments neither replace the frozen main rows nor demonstrate large-domain optimality or computational benefit.
- The [coalescing-aware completed-layer envelope](COALESCED_LAYER_ENVELOPE.md) connection passed independent focused review and fresh-process small-graph tests: normal and `-OO` each passed 30 tests plus 89 subtests across the new envelope, existing envelope and table-free coalescing suites. FLAT/HIER × coalescing OFF/ON reconstruct completed layers using fresh providers. Envelope schema is now v2 (including default OFF records); old v1 records are rejected, not silently migrated. Solver semantics are unchanged. Recovery is charged replay, not warm resumption or mid-layer restoration. A saved physically feasible incumbent need not equal the final solver's secondary-coordinate optimum; equal primary bounds are not full-key optimality. Existing real OD06 depth-1 recovery remains evidence for its pinned original source/configuration, not a real-road test of this new patch. No further real recovery experiment is added as a taskbook requirement. Delivery-head publication and CI are verified through the associated commit and [review PR checks](https://github.com/yduan12323/HiRoute/pull/12); code CI is separate from scientific acceptance.

### D1–D8 delivery and limits against the original clauses

| Clause | Delivered / executed evidence | Remaining limit or genuinely pending work |
|---|---|---|
| D1.1–D1.3 | Declared selected-leg/candidate/depth domains, attained-face J/Q semantics and distinct terminal/resource statuses; `tests/test_m5d_deployable_contract.py`, `tests/test_time_cut_bounded_v2.py`, and the fixed outcome rows. | Bounded tests and feasible witnesses do not establish an optimum on larger domains. Timeout is never infeasibility; candidate-domain exactness is never full-graph exactness. |
| D2.1–D2.3 | Independent verified common seeds, positive-overhead depth certificates, strict `L_J > U_J` pruning, durable incumbent and source/domain-bound completed-layer reconstruction. [Real OD06/N128 depth-1 evidence (historical artifact)](REPRODUCING.md#historical-results) independently reconstructed both methods' envelopes and replayed their witnesses. | Recovery is charged replay from the original seed at a complete-layer boundary; it retains conservative OPEN lower-bound and unprocessed-domain evidence, not a global gap or optimality certificate. Coalescing-envelope compatibility passed the scoped fresh-process small-graph tests above; no real-road acceptance for the new patch is inferred. Warm or mid-layer recovery is not an additional original requirement. |
| D3.1–D3.4 | On-demand selected-fastest-leg routing/caching, path-witness consistency, directed ALT Region summaries and separate online/offline work; `tests/test_m5d_road_provider.py`, `tests/m5d_recovery/test_onward_alt.py` and real integration receipts. Onward tightening is implemented and tested, replacing the old “unimplemented” status. | Large-domain efficiency is not established. Offline setup, masks, seed routing and evidence work must remain charged in their actual scopes; no zero-total-scan or free-preprocessing claim follows from zero internal bound-member scans. |
| D4.1–D4.3 | Frozen 48-query design at two candidate sizes/two methods yields 192 main rows. Pilot, conditional multi-charge bounds, candidate restrictions and post-start supplemental registration are retained. Twelve full-universe supplemental attempts were executed. | Main: 148 timeouts, 44 seed failures, zero exact completions. Full-universe supplement: 11 timeouts plus one infrastructure-unknown interruption, all before exact-search start. Conditional minimum-charge bounds do not prove feasible optimal routes or completed full-domain coverage. Repaired later DEV domains are distinct from the original fixed matrix. |
| D5.1 | Same-seed FLAT/HIER comparison and diagnostic same-ALT member-scan attempts, preserving all outcomes. | Original main has zero completed exact pairs among 96 bindings; all four supplemental member-scan attempts stopped before search. Hierarchy benefit and paired end-to-end speed ratios remain unavailable. |
| D5.2 | [Representative synthetic evidence (historical artifact)](REPRODUCING.md#historical-results) covers reduction ON/OFF, adjacent-cut coalescing ON/OFF and cold/warm queries. Today's frozen OD02 baseline/onward-only/coalescing-only arms add verified tightening and real table-free coalescing integration. | Four requested contrast categories have bounded evidence, with original failures, review-order deviations and censoring disclosed. No original clause requires every contrast on the full matrix, a reverse-order extension or positive performance. Main comparisons use matched representation settings; the one-factor OD02 treatments do not isolate hierarchy benefit. |
| D5.3 | The [related-work comparability matrix](../paper/related_work.md#compact-comparability-matrix) covers CHArge, nonlinear-charging EVRP exact recursion and charging-time completion-bound labeling, including model/charging/windows/objective/overlap/attainment/common-input boundaries. | No verified external common-input runtime comparison; unavailable code and domain mismatch are disclosed. D5.3 permits this bounded review and does not require weeks of reimplementation or a SOTA win. |
| D5.4 | Independently constructed first-sequential-feasible plan, both fresh physical replays and all six requested transportation quantities for the single OD07 pair, with explicit heuristic status and unequal effort. | Not a sequential optimum, causal benefit estimate, population effect or matched solver-performance experiment. No additional exact sequential solver is required by D5.4. |
| D6.1 | Existing scoped independent REF, selected-leg/event replay, bound/partition, reduction/coalescing, seed/depth, unattained J/Q and interruption tests; [historical test mapping (historical artifact)](REPRODUCING.md#historical-results). New feature tests are source-specific. | Frozen synthetic reference answers are not fresh REF solves. Existing acceptance covers its finite scope, not all later code automatically; the envelope patch has its own focused review/test result above, while delivery-head CI must be checked for the associated commit. |
| D6.2–D6.3 | Failure-inclusive population reporting, separate measured/reserved/conservative/unknown charges, partial phase/counter receipts and distinct offline verification. Zero main paired completions means paired end-to-end ratio and OD-grouped uncertainty are **NA**, subset share 0/96. | **Partial, not passed:** historical phase splits and unique aggregate CPU cannot be reconstructed from wall time/controller CPU; missing fields remain null. No fabricated total-cost identity or interval. Later feasible-key pairs are not substituted into the main speed denominator. |
| D7.1–D7.3 | Supervised terminal attempts and preserved cleanup receipts; original 48h ledger and later separately authorized work kept distinct. D7.3 permits this scale-limited outcome with no demonstrated benefit. | Original 48h host/transition/tail accounting unresolved; one old-namespace cleanup unknown. Per-process address-space limits are not aggregate RSS enforcement. These prevent an unqualified resource-compliance pass. D7.2 is not permission for continuing optimizations until results look favorable. |
| D8 | Stable report/protocol/current-status/positioning entrances; original taskbook copy; code/tests, failure-inclusive results, reproduction commands, bottleneck analysis and paper outline/matrix. All seven named files exist in the [compact closure bundle (historical artifact)](REPRODUCING.md#historical-results), indexed below. | Current code/evidence integration and focused independent review have the scoped evidence above; publication and delivery-head CI require the associated commit/PR receipts and are not inferred from this document. Historical acceptance stays historical. Final holdout is unrun and requires confirmation after a freeze. |

The OD02 result README's earlier “full live OPEN/frontier” residual-work wording describes its diagnostic boundary, not an additional original D2.3 requirement. Its suggested reverse-order extension is also not an original D5.2 closure condition. The historical compact acceptance/disposition JSON retains its original “not implemented” and “transport unavailable” scope and is not a current global feature inventory.

### D8 evidence index and stopping point

The compact closure bundle contains all seven taskbook-named artifacts: [source_manifest.json (historical artifact)](REPRODUCING.md#historical-results), [environment_manifest.json (historical artifact)](REPRODUCING.md#historical-results), [dataset_manifest.json (historical artifact)](REPRODUCING.md#historical-results), [workload_manifest.json (historical artifact)](REPRODUCING.md#historical-results), [benchmark_results.jsonl (historical artifact)](REPRODUCING.md#historical-results), [verification_results.jsonl (historical artifact)](REPRODUCING.md#historical-results), and [acceptance.json (historical artifact)](REPRODUCING.md#historical-results). These retain the 2026-10-14 source/evidence scope: 216 normalized rows with separate 192/24 populations and 25 bookkeeping/receipt/interruption checks, not 25 solver passes. They are not silently updated to certify the new source or later experiments. Today's separately source-bound results are linked above; their manifests and raw evidence are preserved in their bundles. [Paper outline](../paper/outline.md), [claims/evidence](../paper/claims_evidence.md) and [related work](../paper/related_work.md) remain the paper entrances, not performance acceptance certificates.

D6's unresolved historical accounting gaps do **not** disappear under LIMITED, but they do not prevent an honest D7.3 scale-limited report/review handoff. The decision is to retain these as explicit unmet accounting/compliance evidence, rather than invent charges, drop rows or silently waive an obligation. No additional numerical tuning, counterbalancing, larger-domain rerun or exact sequential baseline is added as a closure condition here. The code connection and focused review are complete within the stated small-graph scope. Delivery-head CI and review/publication remain separate from claiming every research objective was attained.

M6-H remains a suggestion only, using the existing [design/protocol](MILESTONE_5D_DESIGN_AND_PROTOCOL.md#experimental-protocol-and-limits) and the handoff below: freeze algorithm/source and native toolchain, graph/leg contracts, candidate/preprocessing rules, thresholds, resource policy and OD-grouped statistical methods; isolate untouched OD/geographic groups; bind the frozen inputs and protocol with hashes before any execution. Small-domain exact checks and larger-domain completeness/witness/performance checks must be reported separately. No holdout selection or execution is performed here. After code/evidence review and delivery, **stop and await the user's decision about future research and confirmation for holdout**; resource-limited evidence alone does not select a new research direction.

## Historical report snapshot — 2026-10-14

The text below is preserved verbatim. In particular its “tightening unimplemented,” “production coalescing undemonstrated” and “real transport unavailable” statements describe that snapshot, not the 2026-10-17 reconciliation above.


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
