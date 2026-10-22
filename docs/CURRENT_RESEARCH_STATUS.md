## 2026-10-22 M5-E2E delivery

New installed interfaces and synthetic validation are documented in [MILESTONE_5_E2E_REPORT.md](MILESTONE_5_E2E_REPORT.md) and [M5_E2E_REPRODUCING.md](M5_E2E_REPRODUCING.md). Real A/B and original bridge remain unexecuted because the host fails memory safety admission. No historical conclusion below is changed.

# Current research status

## Current delivery checkpoint — 2026-10-17 23:17 UTC

**M5D_LIMITED_BY_DATA_OR_SCALE; local evidence consolidated, public delivery pending.** The [stable report](MILESTONE_5D_REPORT.md#current-coverage-and-delivery-checkpoint) separates completed taskbook evidence, empirical limitations and remaining delivery work. This checkpoint supersedes progress statements in dated entries below, without changing their historical evidence.

- [Tranche A (historical artifact)](REPRODUCING.md#historical-results), frozen numerical source `7d23f28af3ecfdb9d3be56ddbc45e79c7dc64850`: all eight original high-SOC scheduled OD01/03/04/05 N32/N128 domains completed. All 16 method rows authenticate attained optima with their own fresh physical replays; all eight pairs agree canonically; all 40 operational slots are SUCCESS. Returned charge counts do not prove minimum necessary charges. Fixed-order shared-host wall ratios are descriptive, not a generalized hierarchy-benefit estimate.
- [Tranche B (historical artifact)](REPRODUCING.md#historical-results) is **terminal**, frozen source `d5dad19a0d5954aeac0d9f6c653d72a4e65fca51`, batch SHA256 `5694068e93dbddf675fe6ce150d8a1016fa4f11be82df09dcc4efb2406f34eba`. Its fixed seven domains, 14 method rows and 35 slots retain their own denominator. All 35 slots are accounted: 20 SUCCESS, 3 FAILED_NO_SEED and 12 BLOCKED_NO_COMMON_SEED; eight methods authenticate exact completion in four canonically agreeing pairs. OD08/09 high-SOC completed at N32/N128. OD06/07 low-SOC N32 and OD07 low-SOC N128 exhausted the seed heuristic, with feasibility unknown. Terminal accounting and independent review are linked in the stable report.
- The [prior linked OD06 N128 pair (historical artifact)](REPRODUCING.md#historical-results) is qualified separately for shared-grid coverage by a 57-check identity audit. HIER is exact; FLAT timed out and has a feasible-only fresh replay. There is no completed paired-speed ratio. Its five slots and costs are not part of B's 35 new slots. The fixed whole grid has 16 domains / 32 method rows / 80 slots: 25 exact methods, one prior FLAT timeout and six blocked methods; 12/16 domains have both methods exact. Slot totals are 64 SUCCESS, 3 FAILED_NO_SEED, 12 BLOCKED_NO_COMMON_SEED and one prior TIMEOUT. These are disjoint coverage totals, not pooled timing or generalization statistics.
- Original main 192 rows and supplement 24 rows remain unchanged and unpooled. Historical CPU/phase/cleanup gaps remain explicit. Existing bounded ablations, literature comparability and OD07 sequential comparison remain valid within their stated scopes; a positive result, another rerun or a new exact sequential baseline is not a taskbook closure requirement.
- All 96 non-generated production source entries remain at digest `c1a8ebc5a046b9ae402bb9337548d9b84037b9876853e99efa8b975263649547` for these frozen coverage runs. Optional optimization candidates remain unintegrated. Reused regression evidence is source-scoped, not fresh final-head CI. Public push, final review PR and main merge are not verified here. M6-H is unapproved and unrun; no unseen holdout input is opened.

## Fixed scheduled method comparison — 2026-10-17 20:45 UTC

The [original OD06 N128/Hmax39 pair (historical artifact)](REPRODUCING.md#historical-results)
finished at unpublished source 43e83b5. All five declared slots authenticate
operationally with verified cleanup: four SUCCESS and one FLAT exact-phase
TIMEOUT. HIER attained the finite-domain optimum with its own fresh full replay
and healthy final observer; FLAT retained a freshly replayed feasible route.
Both recovered the same complete key, but FLAT did not authenticate exact
completion. Paired exact equivalence and a completed-speed ratio are unavailable.

HIER decorated search took 1021.696292741 seconds and its worker 1056.421447377
seconds. FLAT exhausted its 1200-second exact phase; its worker took
1227.864440322 seconds including setup. Whole invocation wall was
2389.513650993 seconds. Each standalone wall cost includes the full shared
preparation: 1315.370681 seconds FLAT and 1142.767449 seconds HIER. Those are
not standalone CPU costs. Invocation CPU and per-process maxRSS remain separately
scoped; fixed order and shared-host effects limit general performance inference.

Terminal audit passed 103 checks and the final report review 3200. Historical
failures and the old interrupted lifecycle/accounting gap remain unchanged.
This matched result satisfies the next coverage tranche's prerequisite without
requiring both methods to finish or a positive speed ratio.

The reviewed next tranche preselects high-SOC scheduled OD01/03/04/05 at original
N32 then N128: eight domains, sixteen method rows and forty serial operational
slots. It keeps all 96 production files unchanged. Typed seed exhaustion retains
failed preparation and four blocked descendants, with feasibility unknown.
Integrity/resource/cleanup failures stop new starts. The whole eight-query
selection is frozen prospectively, but Tranche B remains nonexecutable here.
No Tranche A outcome, final holdout, publication or main merge is claimed.


## Scheduled original N128 optimum authenticated — 2026-10-17 19:49 UTC

The [treatment-only completion diagnostic (historical artifact)](REPRODUCING.md#historical-results)
completed all three stages at unpublishedf89e4f3. HIER attained the exact optimum
on original OD06 N128/Hmax39, followed by its own fresh full-routing replay and
verified cleanup. The full two-stop key matches the prior feasible incumbent;
optimality within this frozen finite domain is the new evidence.

The decorated solver took1056.176836444 seconds and the full search worker
1094.169638186 seconds. Fresh replay took17.514666534 seconds; whole invocation
1188.490496422 seconds. Final actual region prunes6671 differ from last sampled
checkpoint6465. Final reducer totals are1145 calls,121250 cumulative inputs and
13647 cumulative outputs; these are not a remaining-frontier size. Per-process
maxRSS4129068KiB is not simultaneous aggregate memory. Nested timers are not summed.

Terminal audit passed163 checks and the four-file report review3394. The old
600-second timeouts and interrupted verification/accounting gap remain recorded;
separate earlier replay recovery did not retroactively complete that invocation.
No matched scheduled-method speedup follows from this treatment-only run.

Next is a separately frozen original OD06 FLAT/HIER pair, exact1200 each,
pending/post-service ON in both and all96 production files unchanged. It runs
five stages serially to preserve memory headroom. Optional convex-count and lazy
native allocation candidates remain separate. See [next sequence](NEXT_VALIDATION_SEQUENCE.md).
No final holdout, public publication or main merge is claimed.


## Scheduled pending-window outcome and next diagnostic — 2026-10-17 19:20 UTC

The fixed original OD06 N128/Hmax39 HIER pending OFF/ON exact600 comparison at
unpublished02493a4 retained both timeouts. In the last saved samples, identical
13,333 cumulative input pieces produced12,359 outputs OFF and1,743 ON. ON had
4,948 late-primary discarded cell visits and5,672 connected same-parent joins.
These are censored completed-call counters, not final frontiers or exact-query
completion. The new rule activated in depth two; no general speedup is proved.

The first invocation failed both preparations due to a missing Parquet engine;
all six slots are preserved. The repaired invocation has two authenticated
preparations and two authenticated exact600 timeouts, but the execution
connection was lost during final verification. Its two verification slots,
coordinator cleanup and complete invocation accounting remain unresolved.
The stale RUNNING ledger is not a live-job or completion claim.

Two separately supervised fresh full-routing replays then passed, independently
reviewed in153 checks, authenticating the same saved feasible incumbent. They
do not retroactively complete the interrupted invocation or prove optimality.
The [report (historical artifact)](REPRODUCING.md#historical-results)
keeps failed, interrupted and recovery records separate.

Next is a separately declared treatment-only exact1200 completion diagnostic:
original OD06 N128/Hmax39, HIER, pending and post-service ON, all96 production
source entries unchanged, three serial preparation/search/replay slots onCPU0.
Search-worker caps are1500 wall/CPU seconds. This is a completion feasibility
check, not a matched speed comparison. The new engine-import/Parquet roundtrip
preflight prevents the observed missing-dependency error before source freeze.
Optional lazy routing allocation, convex-count runtime and operator compaction
remain excluded. No new1200 outcome, holdout, publication or main merge is claimed.


## Conditional pending-window diagnostic — prospective 2026-10-17 18:47 UTC

The default-OFF [pending-window reducer](PENDING_WINDOW_DOMINANCE_OPT_IN.md)
adds a conditional strict-primary dominance rule for pending scheduled service.
Every affine tau=a-h threshold root is preserved as an exact arrangement knot;
original witness callbacks and historical fallback remain. Independent proof
and implementation review passed, followed by installed-wheel regression with
583 tests and 9,273 subtests in each normal and -OO mode.

The [isolated OFF/ON gate](../experiments/pending_window_gate_v1/README.md)
uses only original exposed scheduled OD06 N128/Hmax39, HIER in both arms,
existing post-service reduction ON and the same certified bound family. Two
independent pipelines run on CPUs0/1, with six retained slots, exact600 phases,
worker900 caps and fresh full-routing replay. The95 prior production source
entries remain pinned; only the reviewed new pending-window module is added.
Convex-count runtime, operator compaction and deadline-screen candidates remain
excluded. New counters and delegated post-service counters are distinct.

This source freeze claims no real-road result or general speedup. Old scheduled
timeouts remain intact. No holdout, GitHub publication or main merge is claimed.


## Matched cohort outcome — 2026-10-17 18:40 UTC

The [fixed two-case N128 cohort (historical artifact)](REPRODUCING.md#historical-results)
finished at unpublished source 1a83b644 with all ten slots retained: eight
SUCCESS and two exact600 TIMEOUT. All four independent full-routing replays
and all stage/coordinator cleanups passed. Completion is two of four searches
and one of two matched cases, not full cohort scientific completion.

On original OD02 N128/Hmax33 both FLAT and HIER attained the same full optimum.
Search times were 535.359557730 and 527.901237496 seconds respectively. The small
single shared-host paired difference is descriptive; it does not establish
stable or general HIER superiority. Attempt counts differ (4499 and 4539).
On scheduled OD06 N128/Hmax39 both methods timed out with the same improved
feasible key. Neither has an authenticated exact answer or final observer
health. Scheduled reducer samples mix strong and pre-service fallback work;
they are not pure strong-reduction compression ratios.

Two case pipelines ran concurrently on CPUs 0 and 1. Invocation wall was
1389.326161772 seconds; overlapping stage sums and per-process memory metrics
are separately scoped in the report. Terminal review passed 185 checks and
final report review passed 307. Historical failures remain unchanged.

Next local development targets the remaining scheduled-state cost. A new
conditional pending-window dominance rule is under implementation review,
with exact threshold knots and historical fallback. No new real result,
final holdout, public publication or main merge is claimed here.

## Matched N128 cohort — prospective 2026-10-17 18:00 UTC

The [fixed two-case cohort](../experiments/post_service_cohort_v1/README.md)
compares FLAT/HIER on original exposed OD02 N128/Hmax33 and scheduled OD06
N128/Hmax39, holding the d7a38c02 production algorithm and selected controls
fixed. Both methods receive the same certified bound family. Ten preparation,
search and full-replay slots are declared, with 600-second exact phases and
900-second search-worker caps.

Two independent case pipelines use CPUs 0 and 1; arms within each case remain
serial. A read-only 8,448 MiB MemAvailable check gates the fixed two-worker plan,
without claiming aggregate hard memory control or an isolated host. No result
is claimed at this source freeze. See [local note](LOCAL_POST_SERVICE_COHORT_EXECUTION_NOTE.md).
Optional newer candidates remain excluded, and old experiment records remain
unchanged. No final holdout or main merge has occurred in this continuation.

## Original N128 optimum authenticated — 2026-10-17 17:53 UTC

The [separate 600-second completion diagnostic (historical artifact)](REPRODUCING.md#historical-results)
completed all three stages at unpublished source 0d454b9d. HIER returned an
attained optimum on original OD02 N128/Hmax33, with the same previously known
improved full key, followed by successful independent full-routing replay.
Search took 506.847817020 seconds; total arm time was 542.443302960 seconds.
This establishes optimality within the original declared finite domain only.

Final actual region prunes were 440. The strong reducer processed 59,490
cumulative input pieces into 1,928 outputs over 164 calls; its inclusive cost
was 139.522938306 seconds. Authenticated final progress and counter scopes are
in the report. Terminal review passed 74 checks; report review passed 119.
The older 240-second timeouts remain unchanged. One treatment-only completion
does not establish a matched same-budget speedup or general HIER superiority.

Next is a fixed matched FLAT/HIER study on the exposed OD02 and scheduled OD06
N128 domains. It preserves the same production source and selected controls,
with the same certified bound family supplied to both methods. The optional
convex-count runtime and operator compaction are separate candidates and are
excluded. No final holdout, public publication or main merge is claimed here.

## Post-service 240-second outcome — 2026-10-17 17:25 UTC

The [post-service OFF/ON pair (historical artifact)](REPRODUCING.md#historical-results)
finished at unpublished source d7a38c02. Both exact240 searches timed out;
all five declared slots remain, with three SUCCESS, two TIMEOUT, successful
fresh full-routing replay and cleanup. Both retain the already-known improved
feasible OD02 key. Neither authenticated an exact answer.

First-layer reducer input counts were 804 in both arms. ON returned 392 pieces
versus 542 OFF, with 44 strong calls and 122 connected same-parent joins. The
last completed-layer frontiers contained 380 versus 530 pieces. Both searches
stopped during depth two, before its reduction. Cumulative expansion starts
are not completed-group counts or evidence that a layer was nearly finished.
This is mechanism activation evidence, not whole-query speedup. The terminal
audit passed 115 checks, and the final report review passed 170 checks.

The next separately declared treatment-only diagnostic permits 600 seconds for
exact search including finalization, retaining the original N128/Hmax33 and
all selected algorithm settings. It will preserve the old 240-second failures
and cannot establish a matched same-budget performance comparison. Production
src bytes remain exactly d7a38c02; the optional convex-count runtime is excluded.
No holdout, public publication or main merge is claimed here.

## Post-service reduction diagnostic — prospective 2026-10-17

The separately selected [post-service reducer](POST_SERVICE_DOMINANCE_OPT_IN.md)
uses the final lexicographic objective only after all scheduled service is
complete, at an identical trusted physical departure state. Static common
continuations preserve strict time advantages; pending-service states and
historical recording retain the skyline product order. Parent-run compaction
joins only connected cells from the identical original parent object.

The [new fixed gate](../experiments/post_service_gate_v1/README.md) holds analytic
C ON and compares reducer OFF/ON on the same exposed OD02 N128/Hmax33 domain,
with 240-second exact phases and fresh full-routing replay. No new result is
claimed at source freeze. The pure [convex charge/count helper](CHARGE_COUNT_BOUND_PROOF.md)
is separately retained but is not integrated into this experiment or live bounds.

Installed-wheel core regression passed 567 tests and 9,268 subtests per mode;
the final gate's 13 focused tests also passed normal and optimized execution,
including a tiny native OFF/ON test and fresh physical replay. Earlier missing
fixture/staging failures are preserved with their corrected successful runs.
Finite tests and conditional proof do not establish large-instance speedup.
See [local execution note](LOCAL_POST_SERVICE_EXECUTION_NOTE.md). Public upload
is still separate; no final holdout or main merge has occurred.

## Analytic C diagnostic outcome — 2026-10-17 16:50 UTC

The [original OD02 N128 analytic C comparison (historical artifact)](REPRODUCING.md#historical-results)
finished at unpublished source 46b088e5 with all five slots retained:
three SUCCESS and two exact-phase TIMEOUT. Both 240-second searches retained
the same already-known improved feasible key, and both fresh full-routing
replays and owned-process cleanup passed. Completion remains 0/2 searches.
The terminal audit passed 109 checks and the report review passed 152 checks.

The ON sampled prefix exercised 49,399 analytic C builds with zero generic C
builds, versus 35,026 generic builds OFF. It also recorded more extension
attempts (2,188 versus 1,600), but these are different censored work prefixes;
no completed-query speedup or new optimum follows. Both remained at depth two.

Further local development is examining objective-aware state reduction after
scheduled service is complete, and an optional convex charge/count bound.
Neither candidate is enabled or accepted by this report checkpoint. The known
N128 scalability issue remains open. No final holdout or main merge occurred;
public publication remains separately pending. Historical records are unchanged.

## Known-DEV cohort outcome — 2026-10-17 16:22 UTC

The [fixed matched-bound-family cohort (historical artifact)](REPRODUCING.md#historical-results)
finished at unpublished source 6112893b with all fifteen slots retained:
eleven SUCCESS and four exact-phase TIMEOUT. OD00 N32/Hmax28 completed both
FLAT and HIER with the same authenticated optimum and fresh full replay.
OD02 N128/Hmax33 and scheduled OD06 N128/Hmax39 retained matching improved
feasible keys in both methods, but neither pair completed exact search.
Completion is 2/6 searches and 1/3 paired cases; operational admission is not
full scientific completion. All six fresh replays and fifteen cleanups passed.
The final audit passed 280 checks; installed recovery CI passed 305 tests plus
179 subtests in each mode, with its pending-at-freeze chronology preserved.

OD00 search times were 65.112651112 seconds FLAT and 59.862219504 seconds HIER.
This single fixed-order complete pair and four censored N128 searches do not
establish general HIER superiority. The N128 feasible improvements are not
new historical-best claims. Original candidate domains and Hmax remain intact.

The next [analytic C gate](../experiments/analytic_charge_gate_v1/README.md)
compares only the optional direct C construction on original OD02 N128/Hmax33,
with HIER and all other controls fixed, envelope OFF, and 240-second phases.
It is prospective at source freeze. Exact ordered-piece, attainment, constrained
witness and provenance comparisons plus installed regressions passed; no real
speedup follows from those finite checks. Generic and analytic construction work
have distinct counters. See [local provenance](LOCAL_ANALYTIC_CHARGE_EXECUTION_NOTE.md).
No holdout or main merge has occurred; public upload remains separately pending.

## Prospective paired DEV cohort — 2026-10-17 15:41 UTC

The [envelope OFF/ON comparison (historical artifact)](REPRODUCING.md#historical-results)
completed all five stages at unpublished source 3063d1a. Both arms authenticated
the same attained optimum and fresh physical replay within original OD10 N32,
Hmax26. The terminal audit passed 170 checks. The optional sweep was slower in
this single paired DEV observation: search 116.764524519 seconds OFF versus
207.223273812 seconds ON, despite identical final cells and selected witnesses.
Operation categories differ and are not unit-cost equivalents. The candidate
and negative evidence are retained; the upcoming cohort fixes envelope OFF.

The [paired three-case plan](DEV_COHORT_PAIRED_PLAN.md) covers previously exposed
OD00 N32, OD02 N128 and scheduled OD06 N128. It preserves all fifteen declared
preparation/search/replay slots. This is mechanism-focused DEV coverage, not a
holdout or a statistical sample. Fresh seed admission must match the declared
historical Hmax values 28/33/39; mismatch blocks rather than revises a domain.

The new explicit FLAT singleton adapter supplies the same certified prefix and
whole-route lower-bound family used by HIER. The [cohort runner](../experiments/dev_cohort_v1/README.md)
binds actual method dispatch, durable identity, terminal normalization and fresh
replay. Region aggregation and queue order still differ by design. This cohort
is prospective at source freeze; no new cross-method result is claimed here.
See [local provenance](LOCAL_DEV_COHORT_EXECUTION_NOTE.md). Public upload remains
pending separately, with no final holdout or main merge during this continuation.

## Authenticated DEV completion — 2026-10-17 15:26 UTC

The [240-second projection comparison (historical artifact)](REPRODUCING.md#historical-results)
completed all five stages at unpublished source eef3936. Both OFF and ON returned
authenticated attained optima with the same full lexicographic key and original
seed witness, then passed fresh full-routing replay. Scope is original OD10 N32,
Hmax26 and the frozen physical/candidate model. The terminal audit passed 160
checks. This is a completed known-DEV example, not whole-project acceptance.

Both arms considered 61,317 local projection pairs. OFF built all 61,317; ON built
18,146 after 43,171 proven empty local skips. Observed exact solver times were
160.994256223 and 118.336647041 seconds; total arm times including setup/final
storage were 187.013648348 and 146.270471996 seconds. Native setup and external
fresh verification are separately reported. This single fixed-order, shared-host
pair is descriptive evidence, not a general population speed claim. Historical
120-second timeouts remain unchanged. The later full recovery CI passed 276 tests
plus 163 subtests in each mode; its initial collection timeout remains recorded.

The next [envelope sweep gate](../experiments/envelope_sweep_gate_v1/README.md)
fixes projection support ON and all other controls, comparing only exact envelope
selection OFF/ON with 240-second phases. It is prospective at this source freeze;
implementation proof, independent ordered-cell/witness comparisons and installed
wheel regressions passed. See [local execution provenance](LOCAL_ENVELOPE_EXECUTION_NOTE.md).
No final holdout or main merge has occurred; public upload remains separate.

## Local completion diagnostic — 2026-10-17 15:04 UTC

The [120-second projection-support comparison (historical artifact)](REPRODUCING.md#historical-results)
finished at unpublished source 696fd9d with two TIMEOUT receipts and unchanged
freshly replayed feasible seeds. Its ON snapshot records a normal solver-body
return at 119.106197470 seconds and an empty depth-four frontier, but no arm
result was authenticated. The exact unobserved post-return tail is unknown.
These observations do not establish an accepted exact answer. The independent
terminal audit passed 123 checks without changing that classification.

ON skipped 43,171 of its own 61,317 local projection builds (70.4%); these are
local energy-support skips, not route prunes or a whole-query speedup. Different
workloads prevent interpreting OFF/ON raw counts as equal-work timing.

The separately declared [240-second completion gate](../experiments/projection_completion_gate_v1/README.md)
is prospective at this source freeze. It grants both unchanged arms the same
240-second phase including postsolver finalization, while retaining all other
stage/CPU/memory limits, original N32/Hmax26 and seed. It excludes the separately
developed envelope-sweep candidate. Historical 120-second records remain intact.
See [local provenance](LOCAL_COMPLETION_EXECUTION_NOTE.md). No final holdout or
main merge is claimed; publication is still pending separately.

## Local continuation — 2026-10-17 14:47 UTC

The [q0/q10 DEV comparison (historical artifact)](REPRODUCING.md#historical-results)
finished at unpublished source 8951481. Both 120-second exact searches timed out;
both fresh full replays retained the same feasible seed, with Hmax26 unchanged.
The terminal audit passed 117 checks. Finer time quantization strengthened B(0)
by exactly 243517/64 seconds (3804.953125), changing the diagnostic threshold
from nine to four. Sampled explored work differed; no whole-query speedup,
optimality or incumbent improvement was established.

The next [projection-support gate](../experiments/projection_support_gate_v1/README.md)
holds q10 and all previously shared search features fixed. It compares the
optional C/CS energy-support prefilter OFF/ON under the same original domain,
seed and two 120-second exact windows. The mathematical filter skips only empty
local projection systems; surviving rows/order/lifting remain unchanged.
Implementation and independent rational feasibility checks passed. This gate
is prospective at the source freeze. See [local execution provenance](LOCAL_PROJECTION_SUPPORT_EXECUTION_NOTE.md).
The external publication remains pending; final holdout and main merge have
not occurred during this continuation.

## Local continuation — 2026-10-17 14:35 UTC

The [remaining-charge OFF/ON trial (historical artifact)](REPRODUCING.md#historical-results)
finished at unpublished source de6ba8d: two 120-second exact-phase timeouts,
unchanged independently replayed seeds, and no exact completion or improvement.
The terminal audit passed 92 checks. ON strengthened 1,041 of 1,196 active
bound calls and observed seven enqueue-time strict-pruning opportunities;
these are not final actual-prune counts. Original Hmax remains 26, while the
reported threshold of nine is only a diagnostic consequence of the bound.

The next [dyadic ALT gate](../experiments/dyadic_alt_gate_v1/README.md) holds
all shared routing, energy, skyline, onward and remaining-charge features fixed
and changes only conservative time-bound quantization from seconds to 1/1024
seconds. It is prospective at this source freeze. Production proof/code and
installed-wheel regressions passed; these do not establish a real-road gain.
Defaults remain q0; actual route costs and candidate domains are unchanged.
See [local execution provenance](LOCAL_DYADIC_ALT_EXECUTION_NOTE.md). The separate
public upload remains pending and no final holdout or main merge is claimed.

## Local continuation — 2026-10-17 14:12 UTC

The [local routing/profile comparison (historical artifact)](REPRODUCING.md#historical-results)
finished with two exact-phase timeouts and two independently replayed unchanged
seed routes. Execution source 2eda725 was explicitly unpublished; it is distinct
from the still-pending public increment. The sampled target arm recorded fewer
full-source runs and reached an unfinished reducer, while the full arm remained
in advance. Neither completed exact search or demonstrated whole-query speedup.

Development now tests the separately reviewed remaining-charge/time lower bound
against a shared stronger baseline (target routing, energy screening, skyline and
onward ALT all enabled in both arms). The original candidate domain/Hmax remains;
only strict incumbent-safe pruning is delegated to the existing engine. The
[next gate](../experiments/remaining_charge_gate_v1/README.md) is prospective at
this source freeze. Local execution/pending-publication provenance is explicit
in [the execution note](LOCAL_REMAINING_CHARGE_EXECUTION_NOTE.md).


## Active continuation — 2026-10-17 12:58 UTC

### 13:30 UTC measured continuation and next routing diagnostic

The [original N32/N128 OD10 skyline comparison (historical artifact)](REPRODUCING.md#historical-results)
is terminal at execution source `36106b5`: ten retained stages, four exact-phase
timeouts, four successful fresh physical replays, and no exact completion or
feasible-key improvement. Independent artifact audits passed 78/84 checks.
Same-domain witness equality is not optimality. The last completed checkpoints
cover only 17–41 seconds of each 120-second search: routing dominates those
observed prefixes, while most remaining search time is unprofiled. No whole-query
speed claim follows from the synthetic skyline improvement.

Development continues. The next opt-in gate compares full versus destination-
target routing with the terminal-energy screen enabled in both, using the original
reducer and an equally enabled, rate-limited operation heartbeat. Fresh generation
and verification remain full-only. Combined target/energy correctness and history
binding passed independent review plus installed-wheel tests: core 464 tests/775
subtests, recovery 247/163, target 17 and energy 24, each normal and optimized mode.
Those tests do not establish real-road benefit. The next numerical gate still
requires its own published-source freeze; it has not run at this update.


The owner explicitly requested continued development after the bounded handoff.
Work has resumed on real-road 32/128-candidate scalability in the assistant's
cloud environment. The previous LIMITED report remains a historical scientific
outcome; it is not a reason to stop this newly requested development.

Three parallel workstreams are active: exact frontier-reduction complexity,
road-routing reuse and a separately versioned developmental validation protocol.
No new improvement, exact completion or speedup has yet been established.
The first objective is to complete representative known-DEV exact queries under
explicit budgets, with independently replayed witnesses and unchanged domain
semantics. Old failures and accounting gaps remain recorded. Final holdout
execution and a main merge have not occurred.


M5-D outcome: **M5D_LIMITED_BY_DATA_OR_SCALE**. This closes the bounded evaluation report with explicit limitations; it does not declare unrestricted implementation or deployment acceptance. M5-V remains accepted within its historical scope.

The original 192-row M5-D matrix is terminal: 148 timeouts, 44 failed initial-solution searches and no exact completion. Current portable recovery code has passed exact-head CI at 7dbd82. Neither fact establishes large-scale performance acceptance.

The fixed24 supplement is terminal: 23 pre-search timeouts and one infrastructure-unknown interruption; no sequential comparison completed. Fresh FLAT and HIER recovery each reconstructed its depth 1 completed-layer envelope and independently replayed the same original feasible witness. Both exact searches timed out; no new optimum or performance gain was established. Historical accounting and undemonstrated comparison capabilities remain explicit limitations. See [the single M5-D report](MILESTONE_5D_REPORT.md). The experiment-level outcome and any remaining implementation gates must be reported separately. M6-H and automatic main merge remain outside this handoff.


## 2026-10-15 cold-query development increment

The seed generator now skips provably unnecessary outbound routing, with eight portable regression tests including 2,304 finite stream-equivalence cases. The [cold development evidence (historical artifact)](REPRODUCING.md#historical-results) records a single known DEV control: the same first verified witness at roughly 253 to 75 seconds and 128 to 29 first-proposal source searches. Sequential ordering and OS caches are uncontrolled; this does not establish broad speedup, exact completion or hierarchy equivalence.

Cold-query and durable-incumbent coordinators remain experimental and are not installed APIs in this increment. Durability has tiny local validation only and was not active in either measured DEV pair. Later scalar improvements have no saved replayable route. Existing bounded milestone conclusions remain unchanged.

## 2026-10-15 frozen DEV durable-route coverage

A later, separately admitted [finite DEV continuation (historical artifact)](REPRODUCING.md#historical-results) saved and independently recovered an improved OD06 N128 route (9.604105% lower primary objective, strict full-lex improvement, original Hmax 39) and the original OD00 N32 route (Hmax 28). Both exact searches reached their 120-second caps; neither certifies optimality. The prior OD06 N32 controller_error remains unchanged: completed zero-proposal heuristic exhaustion was independently supported, while candidate-domain feasibility remains unknown. N128 success belongs only to its separately bound larger domain.

This later experimental runtime had durable recording active, unlike the earlier cold-query pair above. It does not retroactively make that pair's scalar improvements replayable. The new stages plus their full preparation allowance charged 616.911965031 CPU seconds; retaining the failed phase's 790 gives 1406.911965031 against the combined 2550 maximum. These are conservative charges, not unique measured CPU. No HIER run, holdout, optimum, or generalized performance claim is added. Experimental coordinators remain uninstalled; the bounded M5-D conclusion is unchanged.

## 2026-10-15 matched original-topology DEV coverage

The [matched six-search report (historical artifact)](REPRODUCING.md#historical-results) records FLAT/HIER pairs on three existing frozen DEV selections. OD02 N128 recovered the same improved two-charge route in both methods (12.981068813% lower primary objective, strict full-lex improvement, Hmax 33). OD10 N32 independently recovered the same original one-charge route (Hmax 26). OD07 N128 produced no seed in either method: both complete zero-proposal streams remain feasibility-unknown, no exact search ran, and both replays were explicitly skipped. Four actual fresh replays succeeded; all four dispatched exact searches timed out.

The original 2,047-node topology was retained with memberships intersected with each selected candidate domain, not the full-site problem. No optimum or generalized HIER superiority is claimed. Twelve stage records retain all six searches, four replays and two skips. Conservative charges including the full preparation allowance total 1397.109392533 of 5040 CPU seconds. Earlier reports, failures and accounting remain unchanged; experimental coordinators remain uninstalled.

## 2026-10-15 OD07 charging-coverage repair

The [OD07 diagnosis-to-repair report (historical artifact)](REPRODUCING.md#historical-results) separates three reviewed stages. The original N128 diagnostic reached only service-only sites, with no beam drops or charge-amount choices. A one-origin selected-path observation then found zero initially floor-reachable chargers among the selected 64, while 21 omitted but originally eligible chargers passed the arrival floor (11 also passed reserve).

A separately versioned domain retained all 128 sites and added all 21 eligible floor-pass chargers, producing 149 sites. One new seed and a separate fresh physical verification established the complete route CS 4683740340 → C 10039741536, exact primary upper bound 4631380169628339331/137438953472000 and Hmax 37. This success belongs to the new domain; original N128 heuristic exhaustion remains unknown and all prior failed rows remain unchanged. No exact search, optimum, full-site/all-road guarantee or speedup is claimed. Conservative runtime charges including each stage's full allowance were 257.790358965/790, 149.956533181/790 and 282.108252748/940 CPU seconds; development CPU is separately partial. Experimental runtime code remains uninstalled.

## 2026-10-15 V6 target-routing DEV result

The [V6 target-routing report (historical artifact)](REPRODUCING.md#historical-results) records one fixed full-then-target OD06 N128 FLAT pair. Both exact searches timed out at 120 seconds. Full retained its initial witness; target saved a freshly full-mode-replayed feasible witness with 8.70796162% lower primary objective than the shared initial seed. Both used the same authenticated native build/binary, physical inputs and Hmax 39.

An authenticated common prefix contains 763 completed requests, including 430 exact-search requests, with no observed semantic/label/edge-chain divergence. Prefix timings are descriptive only. Ordered logs stopped before later observed work and lack terminal completion; the formal whole comparison remains inconclusive and its speed-claim gate remains false. No general speedup, optimality or default activation follows. All previous failed attempts and charges remain retained: 594.230939430 new plus 1240.651958771 prior = 1834.882898201 conservative CPU seconds. Actual sampling gaps and overlapping timing scopes are explicit.

## 2026-10-15 V8 reversed-order target-routing DEV result

The [V8 report (historical artifact)](REPRODUCING.md#historical-results) reverses V6's order: target search/replay, then full search/replay. Both exact searches reached 120 seconds; both committed witnesses passed fresh full-only replay with Hmax 39. Target retained the same improved feasible key as V6 (primary 32066.730295358, 8.70796162% below the shared initial key); full retained its initial 35125.440141758.

The authenticated common prefix contains 902 completed requests, 569 in exact search. Exact-prefix inclusive wall times were 109.242245 s full and 86.440960 s target; the additional 122 target completions are excluded. These finite measurements do not establish general speed superiority. The unchanged formal whole-comparison gate remains inconclusive: forced timeout prevents normal worker close, and absent status proves neither a clean cap nor unseen observer health. Two fixed orders on one query with different observation budgets cannot isolate order effects.

Prior V6 and failed V7 evidence/charges remain unchanged. Conservative charge is 653.688007234 new plus 1954.882898201 prior = 2608.570905435 CPU seconds. Timing overlap, sampled-progress limits, actual sampling gaps and unresolved historical supervisor-accounting caveats remain explicit. No source installation or default activation is included.

## 2026-10-15 Go1 matched contribution result

The [six-row Go1 result (historical artifact)](REPRODUCING.md#historical-results) now has freshly physically verified best routes for FLAT/HIER on OD02, OD07 and OD10, with a common seed/domain per pair, full routing backend and authenticated original indexed HIER topology. All six exact searches reached their 120-second cutoff. Primary improvements over common seeds were FLAT 12.9811%/19.2231%/0% and HIER 12.2290%/0%/0%; HIER showed no bounded-route-quality advantage here. No optimality/global-gap or general performance claim follows.

OD07 original 128-site heuristic exhaustion stays unknown; both methods share its separately repaired 149-site domain. The original OD10 budget/preflight failure and blocked rows remain preserved, with later results separately attributed to the admitted continuation. Combined conservative charge is 2178.835388251 CPU seconds. Sampled counters, setup/mask work, sequential order and uncontrolled OS-cache limitations remain explicit. This is report-only.

## 2026-10-16 OD07 prefix/source-role diagnostic

The [paired OD07 diagnostic (historical artifact)](REPRODUCING.md#historical-results) found the same 87 depth-1 semantic prefixes and piece counts in different orders. FLAT's productive first prefix was tenth in HIER; HIER's first was 53rd in FLAT. Both spent the remaining window on their first depth-1 prefix. HIER retained the common seed; FLAT's separately freshly verified route improved primary cost by 19.1368476%. Both searches timed out; this does not replace the earlier six-row Go1 result.

All 213 recorded HIER schedule-complete reachable finishes returned empty energy/reserve intervals; 72 schedule-incomplete finishes exited before routing. Completed terminal-source work dominated the measured scopes, not bound arithmetic. These are retrospective recorded-operation findings, not certified screening savings or causal proof that reordering improves HIER. Parent-finalized censored traces do not prove whole-stream completeness or unseen observer health.

Numerical conservative charge is 855.301360969 CPU seconds including the full 240 allowance. Separately bounded finalizer/reporting costs, incomplete wrapper/analysis accounting and the initial failed timing wrapper are retained; no numerical retry occurred. No source/default activation accompanies this report.

## 2026-10-16 Canonical-prefix ablation: no verified improvement

The [OD07 canonical-order ablation (historical artifact)](REPRODUCING.md#historical-results) recorded the same 87 semantic depth-1 prefixes in a common order. Both HIER and FLAT retained the shared seed at the 120-second exact cutoff; both saved routes passed fresh replay with Hmax 37. Earlier insertion-order outcomes remain unchanged.

FLAT recorded the productive child finish starting at 119.985938 seconds without a completion. For each method, 1,905 normalized root records matched the earlier insertion run; slower canonical root routing scopes are descriptive and unattributed, not evidence of a causal sorting penalty. No ordering benefit, irrelevance, optimum or global gap is established.

Numerical conservative charge is 840.097081772 CPU seconds including the full 240 allowance. Reporting/finalizer accounting remains separate; the unexplained initial tiny CPU-ceiling failure is preserved. Censored traces, sequential order and uncontrolled runtime/cache conditions limit interpretation. No source/default activation accompanies this negative report.

## 2026-10-16 Certified terminal-energy screen: bounded quality benefit

The [OD07 HIER OFF/ON report (historical artifact)](REPRODUCING.md#historical-results) records a fresh-replayed ON route 8099989597(C) to 11013731180(CS), 19.8833389% lower primary cost than the common seed; OFF retained the seed. Both reached the 120-second exact cutoff with the same repaired 149-domain, original indexed HIER, insertion order, full routing and Hmax 37. No optimum/global-gap or general HIER superiority follows.

ON activation cost 2.523206723 seconds includes construction and nested full-edge validations over the 11,561,067-edge graph; immutable copy cost 0.894038509 seconds. Censored attempted advances rose 400 to 931 and new source runs fell 54 to 14; inclusive recorded routing wall fell 110.068436747 to 49.618292753 seconds. Whole-worker cold wall nevertheless increased 213.682333384 to 218.595244889 seconds, so no whole-latency speedup is claimed.

Numerical conservative charge is 850.442808382 CPU seconds including the full 240 allowance. Sampled RSS, nested timers, unknown observation-tail health, historical fixture failures and post-run transport trouble remain explicit; reporting/development costs are separate. No source/default activation is included.

## 2026-10-16 Fixed-route transportation timing

The [OD07 fixed-route timing comparison (historical artifact)](REPRODUCING.md#historical-results) keeps the same selected legs, two stops, charge amounts and repaired 149-domain. Both fresh physical replays passed. Concurrent charging/activity took 32497.725809 seconds; local charge-before-activity at the CS stop took 34257.673619 seconds. The difference is approximately 1759.947809 seconds of overlap, about 29.33 minutes. Both charged 109.56297984 kWh and drove 550.723819 km. The signed distance difference from the separately inspected selected-fastest-road reference was +4.744465 km; this is not a shortest-distance or direct EV-feasibility claim.

This is one known-DEV fixed route with screening OFF in both rows, not an optimized sequential-planner, globally charge-first, population-effect or optimality comparison. Conservative actual-stage CPU plus the full orchestration allowance is 165.142137359000003 / 1460 seconds. Computational replay wall times are separate from travel times. Prior rejected prototypes, the retained native-ownership fixture failure and the unavailable auto-cleaned earliest fixture receipt remain explicit. No source/default activation accompanies this report.

## 2026-10-16 Shared energy-screen comparison stopped on infrastructure

The [stopped six-row comparison (historical artifact)](REPRODUCING.md#historical-results) retains every failure and blocked row. OD02 is the only completed matched pair: fresh primary improvements are approximately 12.981068813% FLAT and 12.228967174% HIER. OD07 HIER freshly verifies 19.883338903%; OD07 FLAT hit the absolute supervisory CPU guard after only 44.765371271 observed exact seconds and has no fresh replay. Both OD10 rows were unlaunched. The three completed searches reached their 120-second exact timeouts; the failed row is not an equivalent solver outcome or zero improvement.

Both methods use the same energy screen, full routing, insertion order and per-case common seed/domain. The failed stage retains its full 670 CPU-second debit, and all fifteen scheduled slots remain visible. Conservative charge including the full 720 allowance is 2359.793342497999985 / 6360 CPU seconds. The guard crossing is verified; component-level supervisory cost attribution remains unresolved. Sampled counters, nested timers, RSS and unknown observation-tail health cannot establish causal savings or a global gap. Original OD07 N128 exhaustion remains unknown and its repaired149 domain remains explicit. No source/default change or numerical retry accompanies this report.

## 2026-10-16 Separately admitted shared-energy continuation completed

The [ten-stage continuation (historical artifact)](REPRODUCING.md#historical-results) completed four 120-second exact-window searches and four fresh physical best-route replays. On repaired149 OD07, HIER improved approximately 19.883338903% and FLAT 19.223071020% from their common seed (Hmax37). On original32 high-SOC OD10, both retained the original one-charge full key (Hmax26). Each pair shares seed/domain/query and certified-energy/full-routing/insertion policies. These bounded findings do not establish optimality or general HIER superiority.

The prior stopped batch remains intact; its OD02 pair uses a separate controller revision, and its failed OD07 FLAT row and blocked OD10 rows remain recorded. New conservative charge including the full480 allowance is 1676.212772402 CPU seconds; retained prior charge2359.793342498 yields4036.006114900 displayed (exact4036.006114899999980). All failed670/prior720 allowances remain included. Fixed order, OS/cache effects, sampled RSS and unknown timeout tails limit interpretation. Nested short-scope process/thread clocks disagree and cannot support additive attribution; observed lower controller cost does not prove a causal caching fix. No source/default change accompanies this report.

## 2026-10-16 Balanced-order DEV sensitivity completed

The [opposite-order sensitivity report (historical artifact)](REPRODUCING.md#historical-results) retains all30 stages:12 exact-window timeouts and18 fresh verification/replays (six common seeds and twelve saved best routes). Each method reproduced its exact full key across both fixed orders on each of three existing DEV cases. OD02 favors FLAT (approximately12.981068813% versus12.228967174% HIER); OD07 favors HIER (19.883338903% versus19.223071020% FLAT); OD10 retains the original full key for both. The supplement preserves exact paired differences and observed two-repeat ranges. This is descriptive finite order sensitivity, without general superiority, statistical population, optimality or global-gap claims.

Full routing, terminal-energy ON, insertion order and one shared controller revision were fixed. New conservative charge is5232.686186478000080 CPU seconds including the entire1440 allowance, within12720. Prior4036.006114899999980 and separate development2792.320406432 remain distinct; no prior failure is erased or measured cost double-counted. Sampled/censored telemetry and distinct clock scopes cannot establish causal speedup. The disclosed last-block outer environment typo did not alter the unchanged supervisor-enforced numerical thread caps. No source/default change accompanies publication.

## 2026-10-16 Same-ALT hierarchy mechanism comparison stopped

The [stopped mechanism report (historical artifact)](REPRODUCING.md#historical-results) retains24 successful stages, one failed stage25 fresh replay and five unattempted slots. Four complete indexed/recomputed HIER pairs returned identical full keys: OD02 approximately12.228967174% improvement, OD07 19.883338903%, and both OD10 orderings0%. All ten attempted searches timed out. The second OD07 pair is incomplete and second OD02 block unattempted; no indexing performance advantage or optimality follows. Setup is charged in both arms; member-read instrumentation is disabled and sampled region calls are censored.

The replay stopped at absolute parent CPU40.717430874 seconds above its40-second soft limit, distinct from28.132384291 seconds of supervision. Cleanup passed and full180 failure charge remains. Current retained cost4768.602485659000012 includes conservative separate driver12; prior failed launch1620 and separate graph-free diagnostic30 remain distinct. The diagnostic did not reproduce the anomaly or establish its cause. Infrastructure logs are retained privately; this report publishes compact evidence and installs no production source/default changes.


## 2026-10-17 Fixed three-DEV recovery mechanism comparison completed

The [fixed recovery report (historical artifact)](REPRODUCING.md#historical-results) records all 27 predeclared stages: 3 common preparations, 12 searches and 12 fresh independent best-route verifications. There were 15 SUCCESS and 12 externally enforced 120-second search-phase TIMEOUT outcomes, with no FAILED, BLOCKED, UNKNOWN or pending stages. All six indexed/recompute pairs had identical complete lexicographic keys; each of the three DEV cases also reproduced its key after reversing arm order. OD02 and OD07 improved their common seeds; OD10 retained its seed.

Execution source remains d2474ec6795c7be67509a727517b3ad04b19b93e. Summed worker-stage wall was 2083.902947925 seconds; batch-parent process CPU was 67.521368542 seconds. These are separate scopes, not a measured total CPU cost. The integration gate, historical UNKNOWN and prior interrupted batches remain separate and unchanged, without pooled timing. This bounded report proves neither optimality nor an indexing performance benefit, and does not pass Go1 or M5-D performance acceptance. No source, default, task specification or main-branch change accompanies publication.

## 2026-10-17 Opt-in onward ALT and table-free coalescing integration

Source `e00edaf6dcecbc9f71ae174862761ea13de6ea89` adds default-OFF certified onward ALT and table-free exact adjacent-cut coalescing, with ordinary/optimized small-graph full-key and independent replay tests. The [OD02 three-arm report (historical artifact)](REPRODUCING.md#historical-results) records one original N128 DEV case, a shared seed/Hmax33 and three externally enforced 120-second search timeouts. Baseline and coalescing returned identical freshly verified full keys; onward returned a worse feasible primary value in this fixed forward-order window. No general ranking or speedup follows.

The original seven-stage ledger remains FAILED_VERIFICATION: the coalescing verifier was interrupted by the supervisor's temporary-directory sampling race. A separately recorded eighth stage used a reviewed no-follow descriptor-relative scanner with the unchanged original numerical worker and bindings; fresh physical replay succeeded. The original failure and all costs remain visible. All search telemetry is partial, with unequal snapshot positions, and cannot establish full-run throughput or pruning savings.

These additions close bounded implementation/integration evidence gaps only. They do not establish full D2/D5 acceptance, optimality, Go1/M5-D performance success, a final holdout result or whole-project completion. Independent real sequential-feasible construction remains a separate residual comparison, distinct from the earlier fixed-route timing replay.

## 2026-10-17 Independent OD07 sequential-feasible comparison completed

The [single known-DEV gate (historical artifact)](REPRODUCING.md#historical-results) completed three SUCCESS stages: independent first-feasible construction, fresh sequential replay and fresh replay of the predeclared original OD07 indexed joint plan. The repaired 149-Site domain and Hmax37 stayed fixed. Sequential physical elapsed was 34257.673619 seconds versus joint 25591.211474 seconds; sequential-minus-joint was +8666.462144 seconds and +29.629877 km. Charged energy Q was 109.562980 versus 71.448109 kWh, with different terminal battery energy; the Q difference is not an energy-saving claim.

The generator retains concurrent-clock candidate ordering/pruning and stops after the first sequentially feasible proposal (`generation_complete=false`); this is feasible construction, not sequential optimization or a lower bound. The stored joint plan previously received a 120-second search window. Different routes, charge amounts, overlap and search effort prevent a causal-overlap or fair solver-performance claim. Both plans were freshly physically verified under source `66c2f459a52d9d28c85d87967a26034d3d074dec`; neither is proved optimal. Whole worker-stage wall summed to 126.883382013 seconds; controller process CPU was 5.466541180 seconds, with no measured aggregate worker CPU. The earlier four sequential failures and fixed-route 29.33-minute report remain unchanged. This closes a bounded feasible-comparison gap, not full D5/Go1/M5-D acceptance or whole-project completion.
