# Bounded diagnosis of inherited M5 drift-fixture failure

Failed source: main0f486300d931558d072ce05a6fcc4c42d4b70027 (merged PR37).
Run41332956301, job124926707427, step9 `ci/run_m5_recovery_code.py`.
Normal mode:484 passed. Optimized mode:483 passed,1 failed,285 subtests.
The failure is `tests/m5d_recovery/test_m6h_held_manifest.py:91`,
`ContractTests.test_drift_stops_whole_queue`: expected INTEGRITY_FAILED,
observed MOCK_FINISHED_WITH_RETAINED_OUTCOMES. It predates PR38's adapters.
The original failed assertion and CI status remain in the evidence.

## What source inspection proves

`contract.admit` rejects source/runtime/input/method drift with an explicit
ValueError; it does not use an assert. `mock_worker.result` explicitly changes
the runtime identity for the drift scenario. Relevant runner, worker, contract,
supervisor and test sources did not change between passing main36 and main37.
Thus no evidence shows `-OO` removed an identity check or PR38 caused a regression.

Each search has an unchanged0.2s phase,1s actor CPU,5s startup-inclusive wall,
256MiB address-space ceiling and CPU3 affinity. A non-SUCCESS supervisor receipt
is retained by runner lines94–100 without calling admit; siblings continue.
A drift slot stopped before delivery can therefore legitimately end the queue
as MOCK_FINISHED_WITH_RETAINED_OUTCOMES. A non-success preparation can also block
the intended drift slot. The original test discarded its temporary receipt tree,
so the old failing logs cannot identify which path occurred. Resource/timing
preemption is a supported candidate, not a confirmed cause of that old failure.

## Targeted fixture correction and one retry design

The queue-admission test now supplies a deterministic SUCCESS receipt containing
the actual malformed mock result. Its original INTEGRITY_FAILED and blocked-tail
assertions are unchanged. Limits are not raised or disabled. A new deterministic
regression supplies phase_timeout before drift delivery and verifies resource
retention/sibling continuation. Existing real-supervisor success, startup and
timeout/cleanup tests remain unchanged. Direct full-identity rejection is also
checked in normal and optimized Python. This corrects the fixture's conflation
of guaranteed delivery and integrity admission; it does not diagnose the old
resource outcome by assumption or alter production solver/runner semantics.

Only one original-process retry is admitted. It loads the exact original test
bytes from0f486300, runs only that original `-OO -B` unittest on Linux, and uses
the unchanged dependencies and all original assertions/limits. The capture
wrapper copies TemporaryDirectory contents only after the mock queue has
finished, before cleanup/original assertion; it adds no work inside a timed
worker phase. All receipts survive either pass or failure. A failed retry remains
failed; no successful retry is sought after it. Passing this isolated retry
would not make the original full M5 green or prove the original failure's cause.

The branch temporarily uses the existing registered workflow's manual branch-ref
entry to run this diagnostic-only job, clearly named as such. Main's full M5
definition is unchanged. Before final delivery the branch workflow is restored;
there is no broad-suite rerun or new automatic main diagnostic invocation.
The artifact records source identities, original test bytes/hash, Python mode,
affinity, raw stage receipts and bounded CPU accounting. No real query, policy
row, data acquisition or holdout is run. PR38's six rows and two unrun slots stay
unchanged.

## Separate diagnostic cap and accounting reconciliation

This diagnostic has its own **240CPU-second inclusive cap**, inside the original
28800 ceiling:180 for one bounded Linux CI invocation,20 local/logical/control/
reporting,40 for final-PR unrelated M5 startup cancellation if needed. No future
main diagnostic run or second original retry is admitted. Local mocked checks
have an8s cumulative child allowance, leaving12s in the20s control allowance.
The entire240 is conservatively precharged; no actual CI cost is invented.

PR38's frozen row ledger is unchanged:762.630577412 worker/controller/setup CPU
plus900 conservative nonstage reservations = **1662.630577412 /3000**.
The900 already includes PR38 dedicated CI180 and future merged-main dedicated
CI180. That future180 must **not** be added again, subtracted from headroom twice,
or described as covering full legacy M5. Cap remainder is1337.369422588;
another pair needs1240+120=1360, exceeding it by22.630577412. The last pair's
budget-unrun status therefore remains correct. No extra row is funded by
relabeling an unused CI allowance.

The original taskbook section10 says the first segment's new numerical solves
and finite REF have a suggested8CPU-hour budget, with map work separate. It
does not itself define a global ledger for every historical CI invocation.
Later gate instructions explicitly include their own verification/CI costs.
The recorded600/900 comparator allocations and PR38's900 nonstage allocation
do **not** show coverage for full main37 M5 run41332956301. Calling it inherited
infrastructure did not establish that coverage. The earlier14468.280547741 is a
conservative research/gate ledger, not a certified globally all-inclusive CI total.

That public repository's job used the standard ubuntu-24.04 runner, starting
17:43:55Z and ending18:04:25Z:1230s wall. GitHub documents4 CPUs for this public
standard runner ([official hardware reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)).
The reported-window capacity product is4*1230=4920CPU seconds; allowing2s
timestamp granularity gives4928. This is a capacity bound, **not a CPU
measurement**. A separate5000s exposure reserve is now disclosed for this run;
no previous reservation is silently reused or double-counted. With this known
exposure and the diagnostic240, the provisional conservative total is
**19708.280547741 /28800**, leaving9091.719452259. It is still not a certification
of every earlier inherited legacy CI's scope/cost. The prior proposed11500
holdout reserve can no longer be guaranteed under this conservative treatment.
Global research-versus-engineering CI scope and prior unmetered exposures need
an explicit project accounting decision before promising further scale/holdout
capacity. No such decision or budget expansion is assumed here.

## Observed diagnostic result

The single admitted diagnostic run is41336411503, job124937079608, source
ff07b4f1086c9caaf00cda6b69496081e3bae6df. The two deterministic Linux phases each
pass all3 checks, normally and under `-OO`, without importing numerical packages.
The original old test was then run exactly once under `-OO`, with its unmodified
bytes (SHA25613d68260b6e02ca13767b1890a776eabd2837794eb34a590c570f3fa5f385faf).

The retained original-process queue shows preparation SUCCESS, then drift search
supervisor SUCCESS/exit0, explicit identity-drift rejection INTEGRITY_FAILED,
and all24 later slots BLOCKED_INTEGRITY_FAILED; both launched workers have
cleanup_verified=true. Thus both original assertion conditions are satisfied
in the captured queue. The old failure was **not reproduced** by this one
isolated attempt. Preceding full-suite load/state was not recreated, and the
original failed-slot receipts were deleted, so this does not confirm timing as
the cause of the old run or certify its whole CI.

The diagnostic CI itself remains **failure**. Its collector recursively read
an auxiliary supervisor ledger.json without a stages key and raised KeyError
*after* the original test had completed and its entire raw directory was retained.
The in-memory unittest result had not yet been serialized; no new synthetic
unittest pass record is invented. Existing raw receipts were recovered offline,
without executing the test or workers again. The artifact13095202832 and failed
CI state are preserved. A focused parser fix now reads only the queue's known
root/run/ledger.json and saves the unittest result before collection. Three
parser-only regressions pass locally in both modes, including an auxiliary-ledger
fixture and missing-main-ledger rejection. No second CI/process retry ran.

The proposed resolution is the deterministic admission fixture correction:
keep the original queue-stop assertions, separately verify correct pre-delivery
resource handling, retain existing real-supervisor tests and preserve original
failure evidence. No actual production identity-rejection regression was found.
This addresses the test's unsupported guarantee of delivery within a resource
budget; it does not claim all scheduling-sensitive process tests can never fail.
Full M5 has not been rerun or declared green. The default full workflow definition
is restored unchanged in the delivery branch; the diagnostic-only workflow at
ff07b4f is a historical one-off invocation, not a replacement for main CI.

CI conservatively charged **63.990695 /180CPU seconds**, including60 setup/
controller allowance. The whole diagnostic's **240** remains precharged, including
all failed collection, local checks, report/control and any final-PR startup
cancellation. The unmetered full-main exposure reserve5000 is separate and is
not measured CPU. The policy ledger and its already included future merge-CI180
are unchanged. See [m5_drift_diagnostic_results.json](m5_drift_diagnostic_results.json)
for the distinct statuses, source identities and reconciliation.

No new real policy row, repeated policy solve, data acquisition, main experiment
or holdout ran. PR38 remains held for parent review and project budget-scope
reconciliation; this report does not assume additional experiment capacity.
