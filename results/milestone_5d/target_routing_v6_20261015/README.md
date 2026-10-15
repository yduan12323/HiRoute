# V6 target routing: verified feasible improvement and finite matched prefix

## Outcome
All four admitted comparison stages completed with verified cleanup. Both searches reached their original 120-second exact limit. Both saved witnesses were independently replayed in fresh full-only mode, preserving original Hmax 39. Full retained its initial feasible witness; target committed a strictly better feasible witness, replayed from record `5dc31d6d35b725c05e98e0d810275e496475f348c464a9085a7c2972ac31df3a`.

The primary objective decreased from **35125.440141758** to **32066.730295358**, an **8.70796162%** improvement for this one fixed-order, known-DEV pair. Exact best keys and secondary components are in WORK_AND_WITNESSES.json. This is a feasible-result observation, not an optimum or general superiority claim. Both workers had unfinished durable-hook spans at cutoff; only committed, independently replayed records count as final witnesses.

## Authenticated completed common prefix
The unchanged production comparator reproduces **763 identical completed requests**, with equal phase/role/consumer/source/target semantics and equal reachability, hexadecimal labels, edge counts and ordered edge-chain hashes. No divergence was observed through request 762. Mode and target dispatch differ intentionally.

Of these, **430 requests belong to exact search**: 371 intermediate-anchor and 59 terminal-destination requests. Both arms made 29 native calls within that same exact prefix: full used 29 full calls; target used 2 full and 27 destination-target calls. Remaining requests were generation 312, initial verification 3, initial search 3 and durable verification 15; those native roles used full mode in both arms.

### Completed exact-prefix timing
Durations below exclude the unmatched next request and all later unrecorded work. They remain useful finite observations even though the formal complete-log gate is not met.

| Measured scope | Full wall s | Target wall s | Full thread CPU s | Target thread CPU s |
|---|---:|---:|---:|---:|
| Inclusive selected-leg call body | 64.397926 | 54.142036 | 57.589569 | 52.448696 |
| Router wrappers, nested within body | 60.748120 | 52.534352 | 54.389345 | 50.888377 |
| Guarded ctypes calls, nested within wrappers | 60.742256 | 52.526277 | 54.383619 | 50.881353 |

Do not add rows: they overlap. The guarded-ctypes scope includes its boundary/instrumentation and is not a pure C-only timer. Process CPU includes heartbeat threads; thread CPU is the synchronous calling thread. Full raw wall/thread/process values, cache outcomes and each wrapper category are in COMPLETED_PREFIX.json.

### Setup and non-exact roles, separately
| Completed request group | Count | Full inclusive wall s | Target inclusive wall s |
|---|---:|---:|---:|
| Generation | 312 | 56.578646 | 54.869052 |
| Initial verification | 3 | 5.187587 | 5.395323 |
| Initial search seed | 3 | 5.300156 | 5.224246 |
| Durable verification | 15 | 5.804446 | 5.392802 |

These groups include full-mode native calls in both arms. They do not measure all setup: graph loading, artifact/authentication, landmark work and gaps outside selected-leg calls are excluded. The retained, unpublished diagnostic-spans artifact separately aggregates completed worker-lifetime spans by pre-exact/exact phase, role and span, including landmark calls; unfinished spans are excluded. Its later evaluated work differs between arms and must not be treated as a matched comparison.

## Recording coverage and formal limitation
Both ordered logs end with the same unmatched begin for request 763 (`road:1391171` to `road:618480`, exact search, intermediate anchor). There is no partial JSON tail, but neither ordered terminal status exists. The begin occurs at exact elapsed **69.324489 s full / 58.506749 s target**. Later progress snapshots reach **119.946476 / 120.017477 s**: another **50.621987 / 61.510728 s** of work beyond the recording frontier. Therefore the unmatched begin is not evidence that the workers remained in that request until timeout.

The completed prefix reconstructs **1,999,361 hashed edges**, leaving only **639** of the configured 2,000,000 edge budget. NativeContexts enforces unique provider roles, supporting the per-role/source/target reconstruction. Exhausting the next chain's hash allowance is a strong source-consistent explanation for the shared recording cutoff, but the next chain length and in-memory capped/error flags were not persisted, so the cause remains unproved. Event/byte totals themselves are far below their caps.

The frozen comparator correctly keeps `diagnostics_complete=false` and `matched_speed_claim_allowed=false`. No criterion is loosened retrospectively. **Formal whole comparison: inconclusive. Completed-prefix observations: valid and reported above.** No statement about equality or divergence beyond the captured prefix is possible.

## Evaluated work and accounting
Last progress snapshots report full/target: attempted **563/573**, feasible **141/150**, generated advance pieces **951/1053**, selected pairs **298/307**; both were at depth 1 with four expanded prefix groups. Search provider totals were full **50 full / 0 target runs**, versus target **5 full / 54 target runs**. These are sampled counters, not exact timeout stacks or equal-work certificates.

Stage charges, CPU observations, cadence receipts and cleanup results are in STAGE_SUMMARY.json. New conservative charge: **594.230939430 CPU seconds**. Prior **1240.651958771** is retained, for **1834.882898201 total**. Original numeric values and raw sums are preserved; display is rounded to nine decimal places. Conservative wait4 charging is not claimed to be uniquely measured aggregate CPU.

This is one fixed full-then-target known-DEV pair; order, shared OS cache and runtime variability remain confounders. No general routing speedup, production activation or further numerical run is authorized. Frozen candidate/source bytes, run evidence and historical failures were verified unchanged; see PROVENANCE_AND_REVIEW.json for original hashes and preservation checks.

## Shared inputs and publication scope
Both arms used the same authenticated candidate native binary/build, Python wrapper, physical query/domain binding, initial seed key and original Hmax 39. Only the intended routing dispatch differed. Both fresh replays used full-only mode. The shared identities and exact review are in [PROVENANCE_AND_REVIEW.json](PROVENANCE_AND_REVIEW.json). This report-only publication does not install the target-routing experiment or activate it by default. Earlier failed attempts remain unchanged and charged.

The resource sampling cadence is nominal, not a strict upper bound on observation gaps: actual maximum gaps and original CPU values remain in STAGE_SUMMARY.json. Completed progress is sampled and unfinished work cannot be reconstructed from its final sample. There is no full-domain, optimum or general speedup claim.

### Published evidence
- [Result, cutoff coverage and unchanged comparator](RESULT_AND_COVERAGE.json)
- [Completed-prefix measurements](COMPLETED_PREFIX.json)
- [Exact witness keys and sampled work](WORK_AND_WITNESSES.json)
- [Stage accounting, cleanup and observed sampling gaps](STAGE_SUMMARY.json)
- [Original identities, preservation and independent review](PROVENANCE_AND_REVIEW.json)

These compact evidence projections support auditing the stated result. They do not form a standalone graph/replay bundle; the original event streams and graph data are retained separately. No numerical experiment was rerun to prepare this publication.
