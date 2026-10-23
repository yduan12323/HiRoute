# Original Shandong bridge adapter

The `ci.m5e2e_original_bridge` entry point is fail-closed. Missing or mismatched evidence produces an immutable `NOT_RUN_DEPENDENCY` report and creates no claim.

## Admission evidence

The caller supplies exact SHA256 bindings for the canonical recovery configuration, original M6 manifest, original common/seed bytes, and a canonical `hiroute.m5e2e.master_accounting.v1` file. Each external charge/reservation points to a canonical `hiroute.m5e2e.accounting_evidence.v1` JSON record whose ID and amounts must exactly match. The accounting document binds the fixed `master_root`, its exact `phase_ledger.jsonl`, external charge and reservation evidence files, the original 28,800 CPU-second / 43,200 wall-second caps, and computed remaining totals. Unknown costs, unsettled invocations, unverified cleanup, hash drift, or insufficient reserve block launch. The minimum remaining balance is 720 CPU and wall seconds: one 120-second REF plus the original 300-second FLAT and HIER allowances.

Under the existing `budget/exclusive.lock`, the adapter rechecks the accounting snapshot and ledger hash, then creates one atomic claim at `.m5e2e_bridge_claims/original-shandong-n8-ref.claim.json`. The claim is bound to N8, eight candidates, SOC 0.30, seed-derived depth 10, source/config/input digests, and the fixed master root. Changing run roots cannot reset it. Any ambiguous outcome after the claim consumes the one REF attempt.

## Preserved gate and limits

Admission uses the existing validated `recovery_runtime.activate()`; the supervised wrapper uses it again, and unchanged M6 `physical._manifest()` and `reference.run_reference()` recheck `require_root_freeze()`. No environment-only bypass, pin change, or expired full-round recovery runner is used.

This adapter has not been executed. Focused tests are added but unrun because the current master accounting does not reconcile all costs and cannot certify the remaining original budget. No claim or numerical worker was created.

The adapter dispatches only the original REF. Existing M6 physical methods use `EXACT_PHASE_SECONDS=1200` and 1200-second arm limits in `physical_domain.py` / `physical.py`; taskbook follow-ups are capped at 300 seconds. M5 microdomain `solve.py` consumes different frozen inputs and is not a valid substitute for original N8. Therefore successful REF is necessary but insufficient to run FLAT/HIER; a taskbook-compatible method adapter remains an explicit implementation gap. No math or root gate was weakened to conceal that mismatch.

Invocation: `python -m ci.m5e2e_original_bridge --report /outside/report.json ...`. All bindings are required for launch; missing CLI inputs still write a `NOT_RUN_DEPENDENCY` report.
