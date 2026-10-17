# V8 reversed-order finite comparison

## Result

The admitted target-search / target-replay / full-search / full-replay sequence completed with verified cleanup. Both searches reached their unchanged 120-second exact limit, and both saved witnesses passed fresh full-only independent replay with original Hmax 39 and zero target calls in replay.

Target again committed the improved feasible key observed in V6: primary **32066.730295358**, versus full's retained initial **35125.440141758**, an **8.70796162%** lower primary objective for this pair. The secondary components were 74.106016640 and 119.070179040 respectively. Exact rational keys and replay records are in WORK_AND_WITNESSES.json. Target record: `956ac4300d2a65557d10f0b488cc38621e18e3f732782ef8f9967934c00406c5`; full record: `4108efd4b11eb7cedb016e57e5f30459135e7fc6ec914974725a834d3fdb0fc9`.

**Authenticated completed-prefix observations are valid; the unchanged formal whole-comparison gate is inconclusive.** There is no optimum or general superiority claim.

## Equal completed requests and timing

The existing production comparator reproduces **902 identical completed requests, numbered 0–901**, with equal phase, role, consumer, source and target semantics, plus equal reachability, hexadecimal labels, edge counts and ordered edge-chain hashes. There is no observed divergence in this common prefix. Full has 902 completed requests in total; target has 1024. Target's additional 122 completions are outside the matched timing comparison. Full's pending request 902 has the same semantics as target's completed request 902, but full has no completion to compare.

Of the common prefix, **569 requests are exact-search calls**: 480 intermediate-anchor and 89 terminal-destination requests. Each arm made 39 native calls within this exact prefix: full made 39 full calls; target made 2 full and 37 destination-target calls.

| Completed exact-prefix scope | Full wall s | Target wall s | Full thread CPU s | Target thread CPU s |
|---|---:|---:|---:|---:|
| Inclusive selected-leg body | 109.242245 | 86.440960 | 104.619141 | 83.224194 |
| Nested router wrappers | 102.317605 | 84.012103 | 97.991609 | 80.871854 |
| Nested guarded ctypes calls | 102.307447 | 84.001855 | 97.981440 | 80.862505 |

These rows overlap and must not be added. Guarded ctypes includes its boundary and instrumentation, rather than pure C-only time. Process CPU, which also includes heartbeat-thread work, is preserved separately in COMPLETED_PREFIX.json. Unfinished requests and spans are excluded.

Non-exact matched roles are separate:

| Role | Requests | Full inclusive wall s | Target inclusive wall s |
|---|---:|---:|---:|
| Generation | 312 | 63.315801 | 66.247089 |
| Initial verification | 3 | 7.810249 | 5.828589 |
| Initial search seed | 3 | 6.207112 | 5.590466 |
| Durable verification | 15 | 6.134151 | 5.931624 |

These roles use full-mode native calls in both arms. They exclude graph loading, authentication, landmark setup and gaps outside selected-leg calls. The retained, unpublished diagnostic-spans artifact separately groups completed worker-lifetime spans by phase, role and span, including landmark calls. Later work differs between arms, so those whole-worker totals are not an equal-work comparison. Each worker ends with unfinished search cache/wrapper/ctypes spans; their partial durations are not included.

## Coverage, cap and censoring

Neither ordered log has a terminal status or commit; neither has a partial JSON tail or failure event. The authenticated classifier reports `authenticated_timeout_prefix`, not `clean_declared_cap`.

Full's pending request 902, `road:2936413` to `road:5289152`, begins at exact elapsed **118.456956 s**. Target's pending request 1024, `road:726784` to `road:5289152`, begins at **119.559077 s**. The last progress samples are **119.958404 / 119.986975 s** respectively. Progress is heartbeat-sampled, so those later samples alone do not prove completion of the pending operation. This recording reaches near the timeout boundary, unlike the early V6 frontier.

Completed chains reconstruct **2,409,885 / 2,515,753 hashed edges** under the explicit 8,000,000-edge cap. Full/target logs contain 1,806/2,050 events and 1,034,042/1,196,596 bytes, below their event and byte caps. There is no authenticated cap declaration; do not infer a clean cap or unseen observer health from missing status. The unmatched requests are censored in the record, not proof of the precise worker stack at SIGKILL.

The frozen whole-comparison criterion requires worker-published `matching_complete` status. An observer that is still open when the intentional SIGKILL arrives cannot execute its normal close; an otherwise valid timeout prefix therefore fails that criterion. Repeating the same timed design would not fix the structural mismatch. FORMAL_GATE_ASSESSMENT.md proposes a future controller-finalized record binding final captured bytes and termination authority, with separate incomplete/capped/corrupt categories and a predeclared finite-prefix estimand. It neither changes V8 acceptance nor implements or authorizes another run.

## Work, order and accounting

Last full/target progress samples report attempted **480/564**, feasible **128/142**, generated advance pieces **862/963**, selected pairs **274/298**, and expanded prefix groups **2/4** at depth 1. Search provider totals are **42 full / 0 target runs** versus **5 full / 45 target runs**. These are sampled counters and unequal evaluated work, not exact timeout stacks or equal-work certificates.

The sequence reverses V6's full-first order and reproduces the same feasible best key for each arm. This is still **one known-DEV query in two fixed orders**. V8 also changes the observation edge budget from 2M to 8M and incorporates intervening packaging/instrumentation corrections. Shared OS cache, order and runtime variability remain confounders; this pair cannot isolate an order effect or establish broad routing performance.

| Stage | Conservative CPU charge s |
|---|---:|
| Preparation | 4.672346138 |
| Target search | 277.869042103 |
| Target fresh replay | 38.507970790 |
| Full search | 296.146502128 |
| Full fresh replay | 36.492146075 |
| New total | **653.688007234** |

Prior **1954.882898201** remains retained, including the failed V7 preparation's full 120-second charge, for **2608.570905435** cumulative conservative CPU seconds. Raw numeric values and their decimal sum are preserved in STAGE_SUMMARY.json; displayed totals are rounded to nine places. Wait4 accounting is not claimed to measure unique aggregate CPU.

Search controller parent charges were **9.994603103 / 13.323311128 s** for target/full; actual supervisor limits remained 50/60, with no supervisor CPU signal or soft/hard overrun recorded. The older V3 hard-limit discrepancy and historical poll-cost variation remain unresolved. Frozen candidate/source bytes, all 127 terminal run files, admission identities and historical charge evidence are identified by the original hashes and preservation checks in PROVENANCE_AND_REVIEW.json. No further numerical run or source publication is authorized by this result.

## Published evidence and provenance

The prior [V6 result](../target_routing_v6_20261015/README.md) remains unchanged. Failed V7 preparation and its full 120-second charge are retained in the historical total; no earlier failure is reclassified as a successful row.

- [Result, coverage and frozen comparator](RESULT_AND_COVERAGE.json)
- [Completed common-prefix measurements](COMPLETED_PREFIX.json)
- [Exact witnesses and sampled work](WORK_AND_WITNESSES.json)
- [Stage charges, cleanup and actual sampling gaps](STAGE_SUMMARY.json)
- [Order-reversal context](ORDER_REVERSAL_CONTEXT.json)
- [Formal gate assessment and prospective design discussion](FORMAL_GATE_ASSESSMENT.md)
- [Original hashes, shared build identities, preservation and independent review](PROVENANCE_AND_REVIEW.json)

Both arms used the same authenticated candidate binary/build, wrapper, physical query/domain binding and initial key. The build identity was checked across all five roles in both searches. Published JSON retains original finite measurement values. This compact report bundle omits raw machine paths, event streams and graph inputs; it is not a standalone replay bundle. Target-routing sources remain uninstalled and defaults unchanged. Preparation of this publication reran no numerical experiment.
