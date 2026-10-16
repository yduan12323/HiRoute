# Stopped same-ALT mechanism comparison

## Result

The fixed batch stopped on stage25 of30. There are24 valid stages, one failed stage, and five unattempted stages. Four of six planned five-stage blocks completed. The second OD07 block is incomplete because its recomputed-arm fresh replay failed; the second OD02 block never started. All attempted searches ended at the exact timeout.

All four completed pairs returned identical full result keys within each pair. OD02 improved12.228967174% versus its verified common seed; OD07 improved19.883338903%; both OD10 orderings retained the original key (0%). These are feasible results, not exact optimality or a global gap certificate. The incomplete order-balanced design does not establish a general indexed-summary advantage.

Both arms use actual HIER, identical ALT values/traversal semantics, no_redundant_extrema and disabled member-read instrumentation. Common eager action tuples and masks remain. Recomputed summaries are not claimed to be a globally optimized scan baseline.

## Descriptive mechanism observations

| Block | Case | Arm | Setup CPU s | Setup wall s | Sampled region calls |
|---|---|---|---:|---:|---:|
|b01|od02|indexed|7.843619|10.092834|252|
|b01|od02|recomputed|6.035242|7.717859|214|
|b02|od07|recomputed|5.615498|7.209190|2302|
|b02|od07|indexed|6.231367|7.892016|1020|
|b03|od10|indexed|5.601205|7.296197|858|
|b03|od10|recomputed|5.788649|7.519581|1116|
|b04|od10|recomputed|5.555376|7.130676|966|
|b04|od10|indexed|5.530698|7.117886|1235|

Setup is charged in both arms. Region counts are sampled/censored, not final totals or normalized throughput; tail health is unknown. Setup/online member-read values and legacy paid-scan values are null because counting is disabled. This table is descriptive and does not support a speedup claim.

## Stop and costs

Failure: b05.od07.recomputed.replay reached the supervisor CPU soft budget. Worker was killed, cleanup verified, classifier recorded Controller CPU ceiling exceeded and accounting_complete=false. The failed stage retains180CPU seconds. No retry occurred.

Controller absolute process CPU was12.585177603s at supervision entry and40.717430874s at end; running-supervision delta28.132384291s. Source/prior-chain authentication has no separate timing, so entry cannot be attributed entirely to prefix growth. Valid b03 indexed replay also had26.920s supervision CPU, while most other replays had0.5–2.2s. Aggregate phase clocks are inclusive and non-additive; no cache/parser cause is established.

Retained current stage charges3316.602485659000012 + full1440 orchestration =4756.602485659000012CPU seconds. Parent launch authorization separately retained12 planned driver seconds, yielding conservative4768.602485659000012. Actual driver0.31888928s is descriptive within those12, not added again. The wrapper implementation also reserves12 inside its1440 successor gate; that overlap is disclosed but is not retrospectively netted/refunded against the parent-authorized separate allowance. The prior preflight-failed attempt retains1620 separately. Earlier development/fixture and historical experiment costs remain separate and unchanged.

The earlier REPORT.md is a preserved prelaunch document, not current status. FINAL_STOPPED_RESULT.json and FINAL_STOPPED_SHA256.json preserve the stopped records. STOPPED_DIAGNOSTICS.json contains all25 parent clock aggregates, worker milestone traces and stage artifact sizes. A separate bounded graph-free timing diagnostic is not part of this scientific comparison.

## Separate graph-free diagnostic

The separately reserved 30-CPU-second diagnostic completed with return code zero and verified cleanup. Its supervisor wall was approximately 35.096272361 seconds and supervision CPU 0.340207507 seconds; it did not reproduce the stopped replay anomaly and established no cause. Sample and sleep process-CPU scopes were 0.121732589 and 0.018734264 seconds. These are nested descriptive observations, not an additive decomposition. Parent CPU 0.404645494 plus conservative waited-child CPU about 0.098754 gives about 0.503399494 seconds; worker self CPU must not be added again. Per-process enforcement does not establish a hard aggregate bound, including for helpers. The diagnostic reservation remains separate from both the current comparison and prior failure.

## Published evidence

- [Stopped outcomes and fixed denominator](FINAL_STOPPED_RESULT.json)
- [Final accounting addendum with separate driver allowance](FINAL_REPORT_ADDENDUM.json)
- [Separate non-reproducing diagnostic summary](SEPARATE_DIAGNOSTIC_SUMMARY.json)
- [Original identities and independent final/basis reviews](PROVENANCE_AND_REVIEW.json)

The 30-stage plan retains 24 valid stages, one failed fresh replay and five unattempted stages. Four complete pairs have equal quality; ten attempted searches timed out, but the failed fresh replay prevents treating the second OD07 block as complete. Neither the incomplete comparison nor the diagnostic supports an indexing performance win or a causal explanation for the stop.

The inventories and STOPPED_DIAGNOSTICS.json named above are retained original evidence, not additional public files. Raw infrastructure logs are excluded from this compact publication. Current retained 4768.602485659000012 plus prior failed-launch 1620 gives 6388.602485659000012 CPU seconds; diagnostic30 and older development/history remain separate. The prior [balanced-order DEV report](../balanced_order_20261016/README.md) and all earlier failures remain unchanged. No production code or defaults are changed.
