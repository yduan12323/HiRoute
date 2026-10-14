# M5-D D5.2 preregistered representative ablations

Frozen source: 1a6bd82b4b96df04c6e849525cdb30f39ba79d55.
Frozen manifest: PREREGISTERED_PLAN.json and adjacent SHA256 file. This is a new supplementary experiment, not a rewrite of the original 192-row main run. It does not authorize holdout, production promotion or merge.

## Smallest directly runnable matrix

Eight fixed frozen v2 cases cover waiting, charging-curve breakpoints, primary-unattained, secondary-unattained, repeated stops, infeasibility at a fixed depth, deterministic action ties and directed cyclic travel. Selection uses case semantics, not observed runtime. Each case runs both methods under all four reduction/coalescing combinations: 64 rows. Exact case IDs are in the manifest. The eight cases intentionally include difficult correctness statuses rather than only attained successes.

Reduction is the existing `dominance` argument in both engines. Coalescing is the existing `solve_bounded_coalesced` / `solve_hierarchical_coalesced` entrypoint. These are actual implementations, not mocked feature switches. Coalescing can run with reduction off because it wraps advance and finish separately; it is not implicitly the same axis as reduction. All paired methods use the same depth bound, leaf size 1, no externally improved incumbent, same cold process and same coalescing setting. Optional progress instrumentation is off.

Before timing, compare each row with its frozen independent expected status and full exact key or unattained infimum, and replay every attained witness. Equal valid optima need not have byte-identical charging allocations. Resource interruption remains a recorded row; it must not be relabeled infeasible. The harness caps each worker at 30 wall seconds, 29/30 CPU seconds and 4 GiB address space, with a 180-second batch ceiling. This is small-domain correctness evidence; bounded-domain infeasibility is not unrestricted-trip infeasibility.

A separate performance phase, not started here, repeats the 64 cells three times with fresh processes and a 600-second total ceiling. Alternate method order per repeat, retain every row including those not scheduled after the batch limit, and report the predetermined denominator. Record setup, propagation, witness-check, coalescing counts and peak RSS separately. Charge input loading and independent audit outside online search but report them. If a chosen fixture exhibits no reduction or compression, report a no-effect result; do not substitute a faster or more favorable case. Tiny runtimes are descriptive only, with no claimed cross-OD confidence interval or long-haul speedup.

## Cold/warm: a separate routing experiment

Use the existing four-node table-free fixture with all three predefined query variants: nonbest, charge_required, equality. Keep the synthetic Python router explicitly identified. For each method, instantiate a new provider and bound provider; establish the same validated witness seed and initial witness-cache contents. Cold means no additional query-result warmup beyond that unavoidable equal seed preparation. Warm means run one unmeasured query of the same method, then run again with its selected-leg cache retained. Record and separately charge warmup. Never warm HIER with FLAT's traversal or share providers between methods. Compute counter deltas instead of mutating cumulative counters. Keep source-label LRU off, as the fixture currently does, so this measures selected-leg reuse only.

The minimal matrix is 3 cases × 2 methods × 2 cache states = 12 cells, three repetitions. All cases and warmup policy are fixed now. Existing sparse execution refuses a preused provider at the recovery boundary; therefore warm query execution needs an explicit benchmark harness below that boundary after one validated admission. Do not disable or monkeypatch the guard. This is prepared protocol, not a currently implemented production warm-query feature. Its search/results parity must pass first. No fresh seed-minimum pass may run only for one condition.

## Verified tightening: currently absent as a selectable axis

The table-free Region provider constructs a single certified directed integer ALT summary. It has no optional separately validated tightening flag. In the full-table Region provider, the default already uses exact minimum incoming selected-leg times; optional ALT is required not to exceed those minima. Consequently ALT-on is not a tightening of the default and can be weaker. Labeling these two modes 'base versus tightened' would reverse or falsify the intended experiment.

The honest D5.2 status is missing validated tightening variant, not completed by cache or coalescing measurements. Do not manufacture a new bound merely to fill a table. A future zero-incoming versus certified ALT diagnostic can answer the value of the existing ALT summary, but must be labeled that weaker-baseline comparison and cannot silently stand in for base-summary versus additional tightening. Any additional tightening must first have a precise admissibility statement, independent reference checks including open/unattained cases, and its own frozen implementation/source manifest.

## Minimal table-free coalescing integration

The existing `_Coalescing` mixin compacts inputs/outputs and supplies a reducer; its shipped subclasses only cover `Problem` and full-table `RealProblem`. A separate `_Coalescing, TableFreeRealProblem` experimental adapter plus reducer wiring appears mechanically small, within the intended representation experiment. Both engines must receive the same adapter and `dominance` setting, with identical independently verified upper bound/depth, bound provider and cache policies. Preserve the public recovery boundary and do not remove the fixture-only guard in the published API.

Before a production measurement: replay the 64-cell small-domain checks through the adapter where representable; run three tiny sparse fixture pairs in every reduction/coalescing setting; verify exact key/status/witness parity; assert route requests/caches are independently scoped; verify proof-family guard behavior. No new coalescing mathematics is proposed: use the existing exact adjacent-cut implementation, including inherited-parent dispatch. Production extension must explicitly bind source hashes and certify the full real graph/domain; it is not enabled by these tiny tests alone.

If the adapter becomes ready, the real pilot is fixed in advance to the already diagnosed OD06 scheduled low-SOC N128 case and the same saved feasible incumbent. Use the existing balanced sorted-site Region policy and report its distinction from the supplied original hierarchy. Freeze the actual query, graph, incumbent, compilation flags, cache capacity and experiment-source hashes before timing. Equal policy for both methods is mandatory. No other OD is substituted after seeing timeout. A bounded pilot can legitimately yield only resource-interruption or no-speedup evidence.

## Deliverables and scope

- PREREGISTERED_PLAN.json / .sha256: immutable scope and case manifest.
- source/: exact pinned coalescing implementation and frozen cases.
- runtime/: isolated local snapshot, individually hashed in manifest.
- run_correctness.py: fresh-worker bounded validation; refuses result overwrite.
- CORRECTNESS_RESULTS.jsonl / CORRECTNESS_SUMMARY.json: actual validation outcomes, if completed.

This closes preparation and can provide small-domain reduction/coalescing correctness evidence. It does not complete all D5.2 performance comparisons, D5.1 main comparisons, D5.3 literature, D5.4 transportation-value experiments, D6 full accounting or D8 final acceptance.

## Observed correctness preparation result

All 64 fixed cells passed on 2026-10-14. The run includes attained optima, primary-unattained and secondary-unattained outcomes, and infeasibility within H_ref. Every attained witness was replayed. Seven of eight case strata had nonzero cumulative adjacent-piece compression; the zero-depth infeasible stratum had zero compression, retained as specified. This is not a runtime performance claim. `CORRECTNESS_SUMMARY.json` records a 6.38-second whole harness wall time only.

The first harness attempt passed 8 cells and failed to serialize Fraction-containing outputs in the other 56 after their assertions. Those raw records are retained under `attempt1_serialization_failure/`. The reporting serializer was changed to render exact rationals as strings, with no changes to the frozen cases, runtime sources, solver settings or manifest. The full fixed 64-row matrix was then rerun. Do not present first-attempt harness failures as solver failures, or silently erase the attempt.

## Timed phase completed after preparation

After the correctness gate passed, TIMING_PLAN.json froze the same 64 cells with three repetitions (192 rows), alternating method order between repetitions. Its SHA256 is 6bfbf8e3eb65afd7bab355ad5a9fd9cab51ede1cba51c2bbf227b552e403c245. The batch cap was tightened from the earlier planned 600 seconds to 180 seconds before execution. All 192 rows passed in 19.26 seconds. This supersedes the earlier preparation-stage statement that timing had not started; the original preregistration is retained unchanged.

Aggregate accounting: solver-call wall 1.003 seconds; solver CPU 0.993 seconds; frozen expected-outcome comparison plus witness replay 0.027 seconds; input/import setup 8.558 seconds; parent-observed row total 19.248 seconds. Peak single-worker RSS was 14,080 KiB. Source hashing and process-launch/serialization overhead are included in parent row totals, not misclassified as solver work. Solver call includes its own Problem construction and routing, so this is not a pure propagation timer. A new REF solve was not performed during these timings; the independent expected answers are the frozen reference fixtures.

TIMING_ANALYSIS.json contains per-case/per-method paired median ratios for reduction and coalescing, using reduction-on/coalescing-off as the fixed one-factor-at-a-time anchor. Descriptive off/on ratios ranged from 0.549 to 1.087 for reduction and from 0.611 to 1.836 for coalescing. Reduction-on was faster in 4/16 case-method pairs and coalescing-on in 13/16. These millisecond-scale, three-repeat measurements are noisy and cannot establish universal speedup, long-haul scaling or OD-population uncertainty. The zero-effect stratum and all less favorable outcomes remain included.

Cold/warm selected-leg caching and verified additional tightening remain unexecuted. Repetition under fresh processes does not satisfy the routing cold/warm axis. The full D5.2 requirement is therefore only partially addressed.

## Cold/warm completed continuation

COLD_WARM_PROTOCOL.json remains byte-identical (SHA256 45a07e6b586c1e9f20ce29228f689d1d40d04c52cfb616faafa2de28cc964c20). COLD_WARM_EXECUTION_PLAN.json froze the actual executable and source closure before any cache measurements, SHA256 f6f80c5b6af879566bcbe8a48e95bc5a7ccb06b95d8430d79011ab1f70c52b73. All 36 scheduled measurements passed in 23.67 seconds under the 180-second cap, with no failed attempts. This supersedes earlier preparation-stage statements that this axis had not executed.

All nine case/repetition groups had four successful rows (FLAT/HIER × cold/warm), equal initial witness-cache contents, certified upper/depth and landmark identity, and equal final full exact keys. Every measured and warmup witness passed full-depth physical replay. Providers, routers and process state were independently created per row. Warm executions retained selected-leg cache only; each engine call created fresh Problem/search state and used the original admitted incumbent and depth. Source-label LRU remained disabled. No public recovery guard was relaxed or called with a preused provider.

Cold measured source runs were 3 (nonbest), 7 (charge_required), and 1 (equality), consistently for both methods and all repeats. Warm measured source runs were zero in every row. This demonstrates the selected-leg reuse mechanism on these synthetic fixtures. Descriptive paired median cold/warm solver-wall ratios were 1.244/1.413 (nonbest FLAT/HIER), 1.104/1.032 (charge_required), and 1.180/1.323 (equality). These are tiny Python-router measurements and do not establish native production latency or global hierarchy advantage.

Measured solver wall totaled 0.491 seconds; measured witness audit 0.006 seconds; separately charged warmup solver 0.263 seconds and warmup audit 0.003 seconds; fresh admission/bound preparation 0.365 seconds. Peak single-worker RSS was 62,008 KiB. Process-launch/import/hash overhead accounts for most batch wall time. Some submillisecond routing CPU counter deltas quantized to zero; retain raw values without implying routing was CPU-free. COLD_WARM_ANALYSIS.json contains exact accounting and per-case ratios. Read-only independent review remains required before treating this artifact as accepted experiment evidence.

## Remaining integration estimate

The table-free coalescing adapter is a small isolated engineering increment, approximately one adapter class and two engine-call wiring sites (likely tens of lines), plus a substantially larger parity/guard test harness. A useful acceptance unit is one focused implementation-and-review iteration with three sparse cases × two methods × reduction/coalescing combinations (24 correctness cells), followed by witness and provenance checks. This is an effort estimate, not a completion-time promise. Actual real-graph measurements require a separate frozen production manifest and matching native/compiler/cache settings, so tiny adapter completion must not be reported as production rollout. Additional tightening is still an absent validated feature and cannot be replaced by this adapter or by cache measurements.

Review-sequence deviation: the protocol listed read-only review before launch. The author inspected the harness before freezing it, but the separate independent reviewer received and examined it only after the 36-row execution had begun/completed. This is recorded as a protocol sequence deviation; subsequent review does not create retroactive independent preapproval. The original protocol is not changed. The data remain exploratory pending that review and any required remedy.

Accounting clarification: `setup_ns` covers the fresh measured-row admission and Region/landmark preparation. Creating the seed snapshot uses a separate provider before that timer; its work is included in the parent-observed row total, not silently included in `setup_ns` or omitted from the total. The source-code validation/import and worker launch also fall outside `setup_ns` and inside the parent-observed total.

## Review-approved confirmation completed

The independent reviewer approved an identical fixed 36-row confirmation, bound by review SHA256 c98d916fcd776fba20120d89a7d0785eadaf005c2b5e384320deaca0565c81d2. Before launch, `confirmation_20261014T040625Z/CONFIRMATION_LEDGER.json` froze a new run ID, unique outputs, unchanged execution plan/protocol/runtime/fixtures, the prior exploratory output hash and the 180-second cap. Ledger SHA256: 1f0c24f1b4bf34c5f215eb694b9f75371730a5a3eeb457844ce19f2e17c3be49.

The confirmation completed 36/36 rows in 24.28 seconds, with all nine paired cache/bound/depth/terminal checks passing. Warm measured source calls remained zero. Measured solver wall was 0.465 seconds, measured replay 0.006 seconds, warmup solver 0.220 seconds, warmup replay 0.003 seconds and admission/bound setup 0.312 seconds. The confirmation is reported separately, not substituted for or pooled selectively with the earlier exploratory batch. Original exploratory outputs were hash-checked unchanged. Confirmation details and hashes are in its `CONFIRMATION_RECEIPT.json` and `COLD_WARM_ANALYSIS.json`.

The review-sequence issue is closed for this separate confirmation. The earlier batch retains its sequence-deviation label. Conclusions remain synthetic selected-leg reuse only; verified additional tightening and production table-free coalescing remain unsupported.
