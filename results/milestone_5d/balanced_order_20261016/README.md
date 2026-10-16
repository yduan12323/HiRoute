# Balanced DEV sensitivity results

All 30 fixed stages completed: 12 searches and 18 fresh verification/replays. All searches reached exact_timeout_feasible, all six seeds verified, and all twelve final independent replays verified_best. No production retries, substitutions, global stop, accounting failures, or cleanup failures occurred.

Opposite-order blocks reproduced each method's exact full best key, not merely rounded primary scores:

| Existing DEV instance | FLAT improvement from common seed | HIER improvement from common seed | Order/repeat result |
|---|---:|---:|---|
| OD02, 128 candidates, Hmax33 | 12.981068813% | 12.228967174% | Same full keys in both orders |
| OD07, repaired149, Hmax37 | 19.223071020% | 19.883338903% | Same full keys in both orders |
| OD10, original32, Hmax26 | 0% | 0% | Original full key retained in both orders |

FLAT is better on this OD02, HIER on this OD07, and neither improves this OD10. This is descriptive order/repeat sensitivity on three existing DEV instances, not sufficient evidence of statistical general superiority. Exact searches were censored at the unchanged120-second window; no exact optimum, global gap or near-optimality is established. Internal per-stage denominator flags are preserved as emitted; the descriptive comparison denominator is the fixed six blocks/twelve search outcomes, with all 18 verification stages separately retained.

## Resource accounting

Production stage charges:3792.686186478000080 CPU seconds. Recorded orchestration debits:691, within1440. Retaining the entire1440 allowance gives5232.686186478000080, below12720 admission ceiling. This figure is conservative protocol accounting, not an independent wall-clock measurement or aggregate cgroup CPU meter.

Historical charge4036.006114899999980 remains separate. Development includes the two failed full1200 outer reservations plus the successful third-attempt392.320406432 charges/debits/reserve, combined2792.320406432; earlier measured costs are already covered, not added again. All prior failure evidence is preserved.

The exact admitted digest is8cc678d446ccaa4146e4d81b0da395a9e17bda6daa7a37f3119c906809f9b367. The original admission90-file inventory still verifies after completion. Every stage uses CPU0 and one contained numerical worker. The final block shell invocation duplicated ARROW_NUM_THREADS and omitted the otherwise present outer NUMEXPR_NUM_THREADS variable; the unchanged supervisor explicitly sets NUMEXPR_NUM_THREADS=1 and all other worker thread caps, so numerical-worker treatment stayed fixed. No running stage was altered.

RESULT.json contains exact rational keys and percentages, per-stage charges, and opposite-order equality checks. EXECUTION_SHA256.json pins execution artifacts, ledgers, workers, admission inventory and completed block reviews. Full independent prefix authentication is recorded in the six block audit files.

## Fixed schedule and reproducibility

The frozen order was b01 OD02 FLAT/HIER; b02 OD07 HIER/FLAT; b03 OD10 FLAT/HIER; b04 OD10 HIER/FLAT; b05 OD07 FLAT/HIER; b06 OD02 HIER/FLAT. Each block began with a new verification of its unchanged common seed, then each search had its own new independent replay. The18 verification/replay stages comprise six seed verifications plus twelve final replays.

Both methods used terminal energy ON, insertion hierarchy layer order, full-source routing and the same revised cached controller with telemetry. Genuine original saved inputs were reused with no regeneration, replacement, holdout or user Mac/server work. The admitted plan pins every active source/runtime/input/history identity. Preparation evidence remains in go1_order_balanced_linear_work, including original97-pin preparation and supplemental607-pin chain gate, with both failed fixture attempts retained. The one-line admission-only source delta is separately frozen; the admission inventory is206db6bba25b9a7ea480e2f9d315de9a4e694ebf4cd2179235d071d073129144. Local Python3.12 supplemental execution does not substitute for the separately required Python3.11CI checks.

Diagnostic telemetry is a bounded snapshot: timeout counters can be censored and are not final totals. Exact-phase elapsed clocks, process CPU, supervisor/preflight/finalization CPU and end-to-end elapsed time have different scopes and must not be conflated into causal speedup or throughput claims. These trials establish repeated feasible full keys within the fixed windows, not performance generality. External polling or transcript timestamps are not precise solver runtime measurements. Original supervisor/guard/receipt accounting remains authoritative, and all diagnostic source/status/snapshot artifacts are pinned for reproduction.

## Published evidence

- [All thirty stage outcomes, exact keys and accounting](RESULT.json)
- [Exact paired differences, opposite-order keys and observed repeat ranges](EXACT_ENDPOINT_SUPPLEMENT.json)
- [Original evidence identities and independent final review](PROVENANCE_AND_REVIEW.json)

All 673 execution pins and both supplemental pins were rehashed for this publication. Full internal infrastructure logs are retained in the original inventory rather than redistributed. Machine paths/process IDs are omitted; the compact projection is not a standalone graph/replay bundle. Earlier [stopped shared-energy results](../shared_energy_stopped_20261016/README.md) and [separately admitted continuation](../shared_energy_continuation_20261016/README.md), including their failures and accounting, remain unchanged. No source/default activation accompanies this report.
