# OD07: diagnosis, charging coverage, and verified complete-route repair

A separately versioned **149-site domain produced a complete two-stop feasible route**, physically verified in a fresh process. The original N128 heuristic-exhaustion results remain unchanged and feasibility-unknown. No exact search ran in this repair, and no optimality, full-site, all-road-path or generalized speed claim follows.

## 1. Original-domain diagnosis

One separately admitted observational FLAT seed-only diagnostic completed with zero proposals and 59 native source runs. At beam depth 1, all 128 selected sites were evaluated: 99 failed the arrival-energy floor; the remaining 29 offered service only. Each completed service but failed terminal reserve. All 29 were retained with zero beam drops.

At depth 2, 29 repeated-site transitions were rejected. Of 3,683 other transitions, 3,101 failed the arrival floor; the remaining 582 reached service-only opportunities after service had already been completed and were rejected as already served. These are transition counts, covering 29 unique reachable service sites. No next frontier remained. No full/small charge amount was tried, and no scheduling-lateness rejection was recorded.

Thus beam truncation and charge-amount discretization did not cause this observed empty stream. This is an observation about the generator's selected legs, not a proof that the original candidate domain or all road paths are infeasible. Observational callbacks added no native routing calls. Original matched FLAT/HIER failed-to-find rows are retained in the [prior matched report](../matched_dev_coverage_20261015/README.md).

## 2. One-origin selected-path reachability observation

Exactly one native origin-source run classified all 2,749 catalog charging sites at 2,301 unique anchors. No seed enumeration or exact solver ran during this stage; the original solver domain was unchanged.

| Charging-site group | Sites | Road-reachable | Arrival floor passes | Reserve passes |
|---|---:|---:|---:|---:|
| Selected N128 chargers | 64 | 64 | 0 | 0 |
| Omitted, originally eligible | 577 | 571 | 21 | 11 |
| Outside original eligibility | 2,108 | 2,085 | 95 | 48 |

Counts are sites, not anchors. The 21 omitted floor-pass sites span 20 anchors; the 11 reserve-pass sites span 11 anchors. Outside-eligibility positives were observations only and were not added.

Initial energy was 18 kWh, arrival floor 0, reserve 6, and consumption 1/6250 kWh/m. Arrival below reserve can still allow charging, so floor and reserve must not be conflated. The unchanged provider reconstructed predecessor edges and independently accumulated their binary64 time/distance to check native labels before exact rational energy arithmetic. This stage had no separate fresh-router replay. A selected-path negative is not an all-road impossibility result, and first-charge reachability alone did not establish the complete scheduled journey.

## 3. Deterministic domain repair and complete-route verification

The explicitly versioned construction retained every original site and added **all 21 originally eligible floor-pass chargers**, with deterministic ordering. No positive outside original eligibility was admitted; no favorable representative was cherry-picked. The domain grew from 128 to 149 sites, with separately bound query/candidate/domain identities in [domain_construction.json](domain_construction.json).

One new seed attempt produced:

- 4r:node/4683740340, CS, newly added
- 4r:node/10039741536, C, originally selected

Exact charges are 1019831064647119/17179869184000 and 6737864034479/134217728000 kWh. Exact primary upper bound is 4631380169628339331/137438953472000; freshly derived Hmax is 37. The saved provisional route was independently reloaded and physically verified in a separate process, with native resources closed. This establishes complete-route feasibility under the existing selected-fastest-path leg/energy model, only in the augmented domain.

The seed snapshot intentionally stopped at its first feasible proposal; it does not claim completed candidate enumeration. No exact search, retry or broader-case experiment occurred. The underlying reused supervisor's missing_exact_start reason is expected for this seed-only gate; authenticated outcomes were provisional_seed_saved and verified_feasible_seed.

Original sparse-domain SHA-256: c4499fd246783883cb11581c638dea63f642e53eccd2c150a457b2e51c8faf2d.

Augmented sparse-domain SHA-256: 876f3d71a4e6d87dc6d885af36d11a7fa1206f0e26cc8db91e2dc322a23d5b6e.

The original exhausted rows were not rerun by this repair and are not relabeled successful. The intervening observational diagnostic is separately identified above.

## Runtime accounting and clocks

| Reviewed stage | Whole controller wall (s) | Conservative stage CPU (s) | Full allowance (s) | Total / reservation (CPU s) |
|---|---:|---:|---:|---:|
| Original N128 diagnostic | 130.354270661 | 137.790358965 | 120 | 257.790358965 / 790 |
| One-origin reachability | 28.648624396 | 29.956533181 | 120 | 149.956533181 / 790 |
| Augmented seed | 131.535596204 | 140.350058514 | shared below | — |
| Fresh physical verification | 20.738442198 | 21.758194234 | 120 for both augmented stages | 282.108252748 / 940 |

The augmented seed's first provisional snapshot occurred 127.915096755 seconds after worker start, after 52 source calls. This worker-relative latency is different from whole-controller wall and the later fresh verification. The interstage orchestration gap belongs to neither stage wall. Cleanup was verified for all executed stages.

Full runtime allowances remain charged. Historical failure/experiment charges remain separate and unchanged. Development/test/review CPU is separately and partially measured; the 120-second allowances do not cover all historical development costs. Conservative wait4 accounting may double-count descendants; per-process CPU/address-space limits and one-core workers are not aggregate cgroup guarantees. Observed wall includes actual terminal processing and is not a hard deadline promise covering all receipt tails. Host/OS caches and contention were uncontrolled, so these values do not support a speed comparison.

## Evidence, source identity and limits

[Stage results](stage_results.json) retain each stage's original time-local conclusions; reachability's then-untested complete-journey claim is followed by the separately admitted successful repair. [Route evidence](route_evidence.json) includes exact sequence/charges, handoff and fresh-verification projections plus original snapshot and witness identities. [Final reviews](final_reviews.json) approve 136 diagnostic, 135 reachability and 162 augmented-stage artifacts; all inventory hashes were rechecked before publication. [Provenance](provenance.json) binds the original inventories and review records.

The augmented runtime used reviewed optional diagnostic source hooks disabled in this attempt; prior stream-equivalence tests support unchanged numerical order. It is not byte-identical to the earlier matched source, and no runtime speed attribution is made. Process headroom observations were namespace-local; separate parent confirmation covered the stopped target experiment.

These compact projections omit absolute machine paths, process identifiers and raw source maps. Original hashes identify archived originals rather than projected bytes. Full road-edge arrays remain in the archived snapshot; the published evidence supplies their counts and canonical JSON hashes. This is not a standalone executable reproduction bundle or a loadable checkpoint replacement. No graph experiment or fresh replay was rerun to prepare this report. No experimental coordinator or solver source is installed, and prior reports, failures and bounded milestone conclusions remain unchanged.
