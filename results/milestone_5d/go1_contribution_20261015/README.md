# Go1 matched fixed-DEV result

All six fixed method rows now have freshly physically verified best routes. Four searches ran in the original stopped phase; the two OD10 searches ran in the separately admitted continuation using the saved original preparation. The original failure and its 150 debit remain unchanged.

| Case | FLAT primary improvement | HIER primary improvement |
|---|---:|---:|
| OD02 | 12.981069% | 12.228967% |
| OD07 | 19.223071% | 0.000000% |
| OD10 | 0.000000% | 0.000000% |

All six exact searches reached their 120-second window cutoff; no optimality or global-gap claim follows. HIER did not improve bounded route quality over FLAT in these observations. Both OD10 methods retained their original one-charge route. OD07 original 128 heuristic exhaustion remains unknown; its common feasible route and both searches use the explicitly repaired 149 domain.

Continuation stage charge: 401.390869420 CPU seconds. Full 240 orchestration allowance yields 641.390869420; retained original 1537.444518831 yields combined 2178.835388251. Actual completed continuation orchestration debits totaled 25. The allowance is not measured development CPU.

Within each pair, common seed/domain/backend/model/Hmax are matched. HIER uses the authenticated original topology with indexed summaries and zero recorded online internal-member reads. Setup work and mask-word work are counted. Progress values are censored snapshots; local queue bounds are not global lower bounds. Sequential order and uncontrolled OS cache limit timing comparisons. See RESULT.json for exact keys, witness sequences, source pins, sampled counters and clock definitions.

## Evidence and interpretation

Within each case, FLAT and HIER share the same freshly verified initial seed, domain, selected-fastest-path full-source backend, model and original Hmax. [COMMON_SEEDS.json](COMMON_SEEDS.json) binds their exact initial keys, query/domain/native/source identities and fixed policy. Target routing is not used in this comparison. HIER uses the authenticated original topology restricted to each candidate domain, with indexed summaries. Zero recorded online internal-member reads does not mean zero setup or mask work; those counts remain in the sampled metrics.

[RESULT.json](RESULT.json) preserves all six exact keys, witness sequences, improvement fractions, clocks and censored work samples. All six best routes were freshly physically replayed; all six searches were cut off. The results provide no verified global lower bound or optimality gap. HIER has no bounded-route-quality advantage over FLAT in these three fixed DEV cases; neither this observation nor the sequential timings establishes general algorithmic superiority.

OD07 original 128-site heuristic exhaustion remains feasibility-unknown. Its separately repaired 149-site domain is shared by both Go1 methods, rather than credited only to one arm. See the [original repair report](../od07_coverage_repair_20261015/README.md).

The [original stopped result](ORIGINAL_STOPPED_RESULT.json) is retained separately. OD10 seed-verification preflight exhausted the original orchestration allowance before a verification worker launched; both searches were blocked in that attempt and the failed 150 debit remained charged. The later separately admitted continuation reused the saved preparation, freshly verified the common seed, ran both searches and replayed both best witnesses. It does not overwrite the original failed rows.

Accounting retains the full original 1537.444518831 CPU-second charge plus 401.390869420 continuation stage charge and the full 240 orchestration allowance, totaling 2178.835388251. The 25 completed orchestration debits are not added again to the full allowance. Conservative charge is not measured unique aggregate CPU or all development CPU. Supervisor wall excludes outer-controller work; observed exact duration includes polling/cleanup overshoot and is not a precise kill-stack sample or end-user latency. Local queue bounds exclude other prefixes/pending layers and are not global bounds.

[PROVENANCE_AND_REVIEW.json](PROVENANCE_AND_REVIEW.json) records the final independent review and original hashes. All 456 original evidence entries were rehashed during preparation. This compact report omits raw machine paths and graph/event archives; it is not a standalone replay bundle. No numerical experiment was rerun and no experimental source or default was installed by publication.
