# Four-query planning-value DEV gate

This stage executes the previously frozen definitions in
[PLANNING_VALUE_BASELINES.md](PLANNING_VALUE_BASELINES.md), whose proposal file
is preserved unchanged. The execution allocation in
`configs/planning_value_dev_gate.json` authorizes only the original four
schedule/N64 queries and eight policy slots, in the original order. There is
no new joint run, tuning grid, larger domain, main experiment or holdout.

## Predeclared resource and measurement contract

The inclusive cap is3000 CPU seconds within the original28800, carrying
12805.649970329. Allocations are2100 for all fresh workers and cumulative
controller CPU;240 for development/focused validation and metadata preflight;
360 for PR and future merged-main dedicated CI (180 each);180 for ordinary
development/control/report/verification;120 for cancelling this PR's unrelated
automatic legacy workflow at startup. The900 nonstage allocation is charged
conservatively; actual inclusive stage CPU is added to it. No unused allocation
permits an extra query. Preprocessing remains652.040677976 /900; no graph/data
acquisition or preparation change occurs.

Every complete two-policy query pair requires1240 CPU seconds plus120 cleanup
headroom before admission. Each fresh numerical worker is limited to300 CPU/
outer wall seconds (180 cold allowance plus120 loaded query seconds), one thread,
8GiB total process and the unchanged8GiB query-extra/host-headroom guards.
The loaded watchdog includes binding, activity ranking, masks, seed, search and
replay. Controller CPU is live, cumulative across safe boundary pauses, and
included in admission and active-worker budget monitoring. Each method has a
durable start, supervisor receipt, incumbent checkpoint and terminal row.
Uncertain starts or failed/terminal controller states cannot silently restart.
Only an explicit between-pair paused state supports ordinary resume, carrying
earlier controller CPU. Every query/slot remains in the denominator if the
budget prevents its pair or an input/outcome fails.

## Adapter proof and focused validation

Only original legal actions are removed. Candidate/effect order is preserved;
an actionless Site is a policy restriction, while its road vertex and every road
edge remain in the shared provider. All physical fields, objective, depth,
charging curves and selected-leg contracts are unchanged. Thus every policy
plan is feasible for the original model; relevant depth and strict-charge/
attainment/full-key semantics use the unchanged Strong solver on that subset.
No independently legal C/S action is synthesized at a CS-only Site.

Activity-first computes exact directed-time features within the loaded budget,
then invokes the already frozen pure time-only ranking function. It does not
filter by energy or accept a joint result, key, plan or seed. The selected Site
never changes after seeing charging feasibility. Both policies use the same
deterministic Strong seed procedure under their own masks.

Every new feasible witness is independently physically replayed under both the
policy and original snapshots. Charging duration is recomputed from the exact
curve; CS overlap is the charging/service interval intersection; distance delta
against the direct fastest leg remains signed. Positive charges and total stops
are reported separately. Historical joint controls are read only by the final
report join after durable terminal baseline receipts, with exact domain/model/
profile identity checks. UNKNOWN controls remain feasible references, not
optima or contemporary runtime controls.

Eleven adapter/controller tests pass normally and under `-OO`, covering subset/order/physical-field
preservation, CS-only exclusion, energy-independent activity choice, original
replay with strict positive charge, full tiny policy keys, inclusive budget
boundary, persistent failure/unrun receipts, safe resume accounting and duplicate
execution rejection, plus actual worker dispatch/checkpoint/no-activity receipts
using a tiny substituted index, compiler-only failure accounting and changed-dependency rejection. Five additional report tests pass in both modes, covering the joint-control read barrier, UNKNOWN references, absent actual values and full-key counterexamples. Eight existing pilot-control tests and four pure policy-definition tests remain in the dedicated CI in both modes. The analytic tiny schedule has original/fixed-site CS key
(16,3,1), versus separated C-then-S key(30,3,2); both replay under the original
model. A signed length delta of-1 is retained. These are correctness fixtures,
not real application results. One initial test-only deepcopy of immutable road
metadata failed; it was corrected and its CPU receipt retained.

## Observed real results

Numerical source is `e63f803af86b6e1168763578aaae4387e1a9b430`, from merged
main `0f486300d931558d072ce05a6fcc4c42d4b70027`. The later delivery adds
reporting and stronger dependency/recovery checks; it does not relabel the six
measurements as produced by that later source. Original proposal, physical
parameters, candidate fingerprints, implementation profile and policy order
remain unchanged. Four query cells mean **two existing OD pairs crossed with
two initial energies**, not four new OD pairs. Every optimum statement is within
the declared N64 workload, further restricted by the policy mask for new rows.
It is not an optimum over the full qualified candidate pool or province.

All8 slots remain in [planning_value_dev_results.json](planning_value_dev_results.json).
Six loaded policy solves ran once:1 attained policy optimum and5 time limits;
4 have independently replayed feasible plans. WD07/E48's two slots were not
admitted. No timeout is called infeasible or optimal. A missing feasible witness
is not evidence that the fixed activity Site is physically infeasible.

A = separated_no_overlap; B = activity_first_fixed_site. J and times are seconds,
rounded here only; the JSON keeps exact rational values and full keys. C+ counts
strictly positive charges separately from H, the total stops.

| Cell | Policy | Terminal outcome | Loaded s | Actual feasible J | H / C+ | CS overlap s | ΔJ vs joint reference s |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| WD01/E18 | A | timeout, feasible only |120.100|50651.507|4 /3|0|+3946.445 (UNKNOWN reference) |
| WD01/E18 | B | timeout, no feasible witness |120.041|—|—|—|— |
| WD07/E18 | B | attained policy optimum |5.967|28939.861|2 /2|2700|0 (attained joint optimum) |
| WD07/E18 | A | timeout, feasible only |120.042|32950.438|3 /2|0|+4010.576 (attained joint optimum) |
| WD01/E48 | A | timeout, feasible only |120.095|38868.758|3 /2|0|0 (UNKNOWN reference) |
| WD01/E48 | B | timeout, no feasible witness |120.062|—|—|—|— |
| WD07/E48 | B | budget_unrun |—|—|—|—|— |
| WD07/E48 | A | budget_unrun |—|—|—|—|— |

The deadline stops loaded work at120s; the recorded total includes subsequent
final output/cleanup. Each terminal supervisor receipt has exit0; controller
PID88145 and all six worker PIDs were verified absent after stage termination.
The maximum sampled process-group RSS was2450079744 bytes, maximum query-extra
RSS1152024576 bytes, and minimum available host memory5118132224 bytes.
No memory/headroom limit or hidden graph residency is omitted from these costs.

The historical Scale controls were read only after terminal policy receipts.
Their graph/catalog/bindings hashes, original candidate domains, model/profile
and exact direct leg metrics match. Four historical witness checkpoints were
physically replayed again from their exact stored plans, without a joint solve
or road search. New witnesses were verified under both policy and original
snapshots within loaded time. Full keys are checked against every attained
joint reference; no counterexample was found.

| Observed policy plan | Δelapsed s | Δdrive s | Δdistance km | Δcharge-duration s | Δoverlap s | ΔH |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| WD01/E18 A, vs UNKNOWN joint plan |3346.445|1068.597|26.544|50.093|0|1 |
| WD07/E18 B, vs attained joint optimum |0|0|0|0|0|0 |
| WD07/E18 A, vs attained joint optimum |3410.576|319.895|8.990|90.681|-2700|1 |
| WD01/E48 A, vs UNKNOWN joint plan |0|0|0|0|0|0 |

WD07/E18 B matches the joint **full key and plan**, so fixing an activity Site
need not lose value in this selected case. Its2700s overlap is observed, while
the separated plan has none. The separated feasible plan's4010.576s J gap is an
observed feasible-plan gap to the attained joint optimum; its policy optimum
remains unknown. Routing, charging duration, extra stop and overlap all change,
so this is not a causal estimate of overlap alone. WD01/E18's joint witness
contains CS but has **zero actual interval overlap**; substituting min(charge,
service duration) would give a false application claim. Its positive ΔJ compares
two observed feasible plans because the joint control is UNKNOWN. WD01/E48 A
matches that UNKNOWN joint plan exactly. The equal-value cases and failures remain in the report. No observed route has four positive charges: H4 in
the first row means three charges plus one S stop.

B chooses way/1425020410 for both WD01 energies, without an energy filter or
fallback, and node/13784956865 for WD07/E18. Original candidate count is64.
Effective policy candidate counts are64 for A and30/40 for the attempted B
ODs; action/feature counts are retained in JSON. Removed Sites/actions are
explicit policy restrictions, not missing source data or full-domain reductions.

## Setup failures and inclusive accounting

Two setup failures are retained, not converted to successful measurements.
The first controller (PID87990) failed process inventory permission before any
worker. Its only start marker, raw status and results were archived after
confirming the controller absent and no supervisor/worker receipt existed.
The authorized monitor-capable execution resumed with3 conservative CPU seconds
carried. A subsequent worker (PID88033) exited during native compilation because
the curated environment omitted the existing Boost header path. Its terminal
exit1/stderr, row, start and controller failure remain in the predecessor run.
It never loaded the road graph or entered a query. Existing Boost1.83 headers
were reused without download; compile and process-inventory preflights then
passed before source freeze `e63f803`. The new run carries **7.312833412 CPU
seconds** for both earlier failures. No loaded solve was repeated. The delivered
preflight now rechecks the recorded compiler/header environment and monitor
permission before any start; recovery refuses loaded queries, ambiguous or live
workers. All predecessor evidence remains outside Git with the real inputs.

Raw terminal stage CPU is760.267423412:672.630577412 worker/setup/tail charges
(including predecessor controller charges) plus87.636845 current controller CPU.
Rounding the closed controller up and adding2s gives **762.630577412 /2100**.
Adding the900 nonstage conservative precharge gives **1662.630577412 /3000**
for this gate, and **14468.280547741 /28800** original cumulative CPU.
Preprocessing stays **652.040677976 /900**. All development, failed checks,
metadata/native-compile preflights, post-hoc physical replay/reporting and CI
are inside the declared nonstage reservations; no additional real query is
funded by their unused allowance. The future merged-main policy CI still has
180 seconds reserved within this total.

At the last pair boundary, raw charged stage CPU760.267423412 plus1240 pair
reservation and120 cleanup would be2120.267423412 >2100. Thus the final pair
was not admitted despite lower eventual/expected costs being conceivable. The
frozen conservative admission rule is retained; no retrospective budget change
or cheap replacement query finishes the denominator.

Merged PR37 dedicated CI41332956318 passed (86.497123 conservatively charged
against its existing180 reservation). Its separate full M5 run41332956301 failed
under `-OO` at `test_drift_stops_whole_queue`: expected INTEGRITY_FAILED, observed
MOCK_FINISHED_WITH_RETAINED_OUTCOMES. Read-only inspection finds explicit identity
rejection in the admission code; the logs do not establish why that mock stage
escaped the expected outcome. The cause remains unresolved. No assertion was
weakened, no full-CI rerun was launched, and this failure is not called a pass.
This gate's dedicated policy CI is bounded separately; final status is on its PR.

## Completion limits and next bounded decision

This is a partial selected-DEV application measurement:3 query cells attempted,
1 cell's two policy slots budget-unrun, all4/8 retained. It supplies concrete
trip metrics and mixed observations, not general benefit, a pure overlap effect,
hierarchy advantage, external real-domain optimality certification or completed
planning-value cohort evidence. No new joint baseline ran. The underlying joint
system's original timing targets remain unmet; larger/full domains, a real
four-charge case, external real-scale comparisons and a frozen new-OD holdout
are still absent. The original taskbook is not complete.

Original remaining CPU is **14331.719452259**. Protecting the previously proposed
11500 holdout reserve leaves2831.719452259 for other pre-holdout work. The highest
value immediate follow-up is bounded diagnosis of the inherited M5 mock failure,
then a separately admitted **only-unrun WD07/E48 policy pair**, retaining the six
existing measurements and all setup evidence; do not repeat the cohort. Such a
pair needs at least1360 conservative CPU headroom plus any additional delivery
work and an explicit compatible provenance/accounting bridge. This document
does not launch that pair, new domains, main experiments or holdout. It cannot
promise all remaining research acceptance items fit the original budget.
