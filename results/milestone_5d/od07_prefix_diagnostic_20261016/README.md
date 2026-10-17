# OD07 paired prefix/source-role diagnostic

## Result and scope

The fixed HIER→FLAT pair completed with the same historical physical seed freshly authenticated under the new observation/verifier source identity,149-site domain and original Hmax37. Both120-second exact searches ended by authenticated timeout; separate fresh full-source replay verified both saved routes. HIER retained the seed. FLAT improved primary cost by19.136847597855215% (exact ratio22157504118476593874/115784504240708483275). This diagnostic does not replace the earlier uninstrumented OD07 result (FLAT19.2231%,HIER0), nor establish a general HIER or FLAT superiority claim.

The trace establishes a concrete difference in work selection: both methods' depth1 layer contains the same87 semantic prefix IDs, each with matching piece count, but their order differs. HIER first expands charger4r:node/8099989597; FLAT first expands4r:node/10088989871. FLAT's first prefix is tenth (zero-based9) in HIER; HIER's first is53rd (zero-based52) in FLAT. Both expand only that first depth1 prefix before cutoff. Semantic prefix IDs encode anchor,remaining schedule,depth,rho,pi; they do not hash full PWA functions, so matching IDs/counts alone is not mathematical equality of every cut.

HIER completes299depth0 and108depth1 actions. FLAT completes299depth0 and14depth1 actions. FLAT's first depth1 prefix yields a six-piece terminal family for10088989871(C)→11013727536(CS), six search witness replays and one completed independent durable verification. HIER yields no terminal family or witness replay. The productive prefix is present but unexpanded in HIER's recorded order. This supports an anytime-order mechanism; it does not prove a counterfactual reordered HIER would reproduce FLAT's timing or route.

## Routing attribution

All intervals are completed inclusive scopes with calling-thread CPU. Nested scopes overlap and must not be added. These are source-label scopes including cache/copy/observer work, not isolated native-kernel timers.

| Completed scope | HIER calls | HIER wall/thread seconds | FLAT calls | FLAT wall/thread seconds |
|---|---:|---:|---:|---:|
| Incoming source labels |211|5.307590356 /5.282469202|149|3.624828767 /3.612615208|
| Terminal source labels |56|105.945857965 /104.912430180|49|93.695797205 /92.156204338|
| Advance |407|10.837053147 /10.707264746|313|5.505624535 /5.481229291|
| Finish |285|106.538981092 /105.498776390|186|94.199064952 /92.652917844|
| Independent durable verification |0|—|1|17.212178900 /17.095324888|
| Labels inside that independent verifier |0|—|3|5.302946061 /5.275493007|

HIER incoming labels contain3misses and208hits; all56terminal labels are misses. FLAT incoming contains2misses/147hits, all49terminal labels are misses, plus3independent-verifier misses. HIER's only repeated incoming miss source is5788209; no repeated terminal miss appears in the recorded completed stream. This gives no evidence that simply enlarging the source cache would eliminate the dominant first-source terminal computations.

FLAT discovers the first successful witness at exact100.833s; its independent durable hook runs from100.835s for17.212s. Subsequent search witness callbacks occur around118.050–118.063s. This paid hook cost is included in its search budget. It is not instrumentation CPU or evidence that persistence fsync itself dominates; the scope includes independent routing and binding work.

## Why HIER finish returns zero

The authenticated operation-parent join resolves all285 completed HIER finishes:
-72still have remaining_schedule=1 and return before any road call.
-213have schedule satisfied, each makes exactly one completed reachable terminal road-leg call, and every finish returns zero pieces.

For the latter, the actual finish implementation immediately calls drive_pwa with the selected leg's consumption and destination reserve. drive_pwa only intersects shifted energy intervals with the reserve floor; it performs no terminal time-window or objective-bound test. Thus these213empty terminal completions are energy/reserve infeasible, including the possibility of an open upper endpoint exactly at the threshold. All56completed expensive terminal source searches are among them (48depth1,8depth2). This is retrospective cause classification, not proof that105.946seconds could have been safely saved before knowing the route.

FLAT has46schedule-incomplete finishes,139schedule-satisfied empty finishes and one six-piece terminal result. All completed terminal road legs in both arms are reachable. PWA upper endpoints/closure and exact leg energy margins were deliberately not logged; numerical margins cannot be reconstructed from this scalar trace.

## Trace integrity and censoring

Finalized HIER stream:3256complete records,1,708,987bytes. FLAT:2468records,1,273,363bytes. Both classify as parent_finalized_exact_timeout_censoring, no declared cap and no partial tail. Finalizers bind controller terminals and raw final trace hashes only after verified process cleanup. There are three unmatched starts in each stream (finish→road_leg→road_labels): HIER begins119.9427s,FLAT118.1706s. These are recorded unmatched starts, not proof of the kill-time stack. No worker terminal status is required to authenticate the completed censored prefix; whole_trace_complete remains false.

The fixed observation budgets are40,000events,16MiB and2seconds of charged scalar/hash/serialization/write CPU. That bucket excludes constant dispatch/clock/stack and post-cap checks; all process work remains inside unchanged worker limits. No on/off production overhead trial was performed. The trace cap's first implementation defect, correction and tiny parity results are preserved. No paths or label arrays were logged and no additional routing calls were introduced.

## Accounting

Stage conservative CPU charges: fresh seed verification33.206270174; HIER search215.884683459; HIER replay47.791996669; FLAT search269.505925225; FLAT replay48.912485442. Sum615.301360969. Adding the full240runtime-orchestration allowance yields855.301360969 of the2030admitted maximum; measured orchestration debits are71/240. These reserve/accounting quantities are not unique end-to-end CPU measurements.

Separate finalizer child CPU:0.130374HIER+0.111350FLAT. Wrapper and later analysis CPU are not completely measured, so do not present these as complete reporting cost. The initial HIER /usr/bin/time command failed before launching Python because that executable was unavailable; its log is retained, then the standard subprocess accounting ran the finalizer once. No numerical retry occurred. Development/review costs remain separate.

## Two separate next options, neither executed here

1. Certified terminal-energy lower bound. Current universally certified lower bound is0; cached exact selected legs/labels may provide exact energy but cannot save the56source-cache misses. Current ALT certifies integer time, not distance/energy. A proposed reverse-to-destination shortest physical-distance/energy potential must bound every path under the original edge-energy model, use conservative rounding and per-edge certificates, and must not replace the forward selected path. For certified L≤actual terminal consumption, reject only immediate finish when every piece has upper endpoint below reserve+L, or equal with an open endpoint. Keep the prefix for future charging/stops. Setup/RSS/certificate cost and amortization need separate proof/tiny validation and resource review before any real graph experiment.
2. Common canonical layer-prefix ordering ablation. Predeclare an outcome-independent semantic key for both methods, leaving within-prefix piece order and HIER's region/action traversal unchanged. This isolates inherited insertion-order effects from within-prefix hierarchy pruning. Do not prioritize the observed winning site or choose the key to manufacture an advantage. It is a new ordering policy, not a retroactive fairness repair. Prove exhaustive full-key equivalence on tiny adversarial cases, retain all actions/support and strict>pruning/equality rules, and explicitly test changed callback/checkpoint/recovery/API ordering. Exact optimum preservation does not imply identical callback histories or timed results.

Neither option justifies premature bound-arithmetic tuning, heuristic energy exclusion, scope reduction or a guaranteed improvement. Preserve all original cases and prior failures in subsequent reporting.

## Published evidence

- [Completed scopes, ordered semantic prefixes and censoring](COMPLETED_OBSERVATIONS.json)
- [Fresh replay keys and witness sequences](FRESH_REPLAYS.json)
- [Accounting, independent review and original hashes](ACCOUNTING_AND_REVIEW.json)

The [six-row Go1 result](../go1_contribution_20261015/README.md) remains unchanged; this separately instrumented diagnostic does not replace it. The retrospective finish classification and observed ordering do not certify advance energy screening savings or reordered HIER improvement. Parent finalization authenticates captured bytes after cleanup, not uninterrupted unseen observer health or whole-trace completeness.

This report-only projection excludes private raw paths, graph inputs and large action/source-request arrays. All 98 original execution pins and four result-package files were rehashed during preparation. No additional numerical run, default change or experimental source installation was performed.
