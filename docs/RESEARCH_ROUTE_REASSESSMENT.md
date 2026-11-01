# Research-route reassessment

## Decision and scope

**Retain the exact system and both fair search methods. Keep hierarchy as an
optional batching/frontier mechanism; do not claim that its summaries add
stronger exclusion than the same-information singleton baseline. Do not launch
the main experiment or holdout on the current performance evidence.** The next
highest-value work is an independently specified common-model comparator, then
planning-value baselines, rather than another timed micro-optimization of the
same difficult DEV case.

This is a research decision, not taskbook completion. The original
`HIROUTE_REAL_SCALE_DECISION_AND_PLAN.md` was reread in full: 370 lines, 21,734
bytes, Library ID `libfile_cf7d0c0cc18c81918bb9ec32174ad6cb`. Its section 2 already
allows weaker summaries whose purpose is cheaper exclusion. Lack of a stronger
bound therefore does **not** by itself invalidate the proposed mechanism.
Its population, external-comparison, application and independent-validation
requirements still apply. No criterion is waived or renamed here.

The reassessment starts from merged main
`e2e92efc398f44ef155ff90092df7e3ec83ad02a`. It changes no solver, routing, seed,
physical model, candidate policy or historical scientific row. It reduces
existing evidence and adds tiny correctness/design fixtures. PR34's existing
body was republished with only its confirmed CI/merge status corrected; the
new explicit authorization resolved the previous status-update denial.

## What hierarchy can and cannot contribute

Fix one identical physical family, remaining activity state, next effect, and
valid attained incumbent U. For a Region R and represented Site s, write
`L(a,R) = max(0, min_R d(o,s)-d(o,a), d(a,D)-max_R d(s,D))` separately for
directed shortest time and directed shortest length. Each extremum relaxes the
singleton value, so `L(a,R) <= L(a,s)`. Adding `min_R d(s,D)` preserves this
ordering for the complete-remaining-travel bound. The optional inbound energy
threshold is also no greater for R than for s.

The completion relaxation is pointwise nondecreasing in remaining time and
required energy. R's relaxed energy interval contains the singleton interval,
including their closed endpoint limits. Minimizing over that larger interval
therefore yields `LB_R <= LB_s`. Empty relaxed support is treated as +infinity.
This proof allows negative affine time slopes, open physical endpoints,
pending-service duration and the inbound-energy restriction; it does not turn
an infimum into a feasible plan.

The pending-activity screen has the same ordering. Its service union is shared;
the Region inbound bound and, for C, the onward term
`max(0,min_R d(s,D)-max_service d(v,D))` cannot exceed the singleton terms.
Consequently, at the **same family and incumbent**, rejecting a Region strictly
above U, or strictly after the activity deadline, implies that its corresponding
singletons could also be rejected. Equality remains eligible. Internal queries
read static extrema, not a scan of members; no physical histories are merged.

This is a local relation, **not whole-search dominance**: priority order and
incumbent discovery can differ. It does not prove equal visited histories or
identical work across a run. It does locate the independent contribution:
avoiding many individual tests, organizing priorities and retaining fewer OPEN
entries, with possible refinement and queue overhead.

Tiny regressions show both directions. On 64 homogeneous high-detour Sites,
Strong makes 64 bound queries and Scale one; on a loose two-Site grouping, Strong
makes two and Scale three. Both fixtures produce the identical attained full K
with zero exact transitions and zero selected-leg queries. These are mechanism
examples, not real-scale results. Additional tests check the pointwise ordering
over directed summaries, remaining-service states, negative/positive slopes,
open endpoints and inbound clipping.

## Existing real evidence, including the tradeoff

`tools/reassess_hierarchy_evidence.py` imports no solver or road provider. It
validates the frozen N64 frame, paired domains, implementation identity and
common exact full keys, then reproduces
[hierarchy_reassessment_evidence.json](hierarchy_reassessment_evidence.json).
Scientific input hashes are recorded in that artifact. Regenerate with:

```sh
python tools/reassess_hierarchy_evidence.py
```

All **48 query cells /96 method slots** remain: Strong/Scale attain 36/37 optima,
time out 8/7 times and lack inputs in four cells each. Exact within60s is35/48
versus36/48, or35/44 versus36/44 on the prospective supported population.
Supported medians26.340/25.020s and censored p95>=120s fail the original targets.
All44 supported cells have physically replayed feasible plans. One to three
positive charges are observed, never four.

The following ratios are **Scale/Strong on the 36 common-exact pairs**, not a
selection replacing that full denominator:

| Quantity | Median paired ratio | Scale less / equal / more |
| --- | ---: | ---: |
| Summary plus singleton bound queries | 0.5803 | 36 /0 /0 |
| Heap pushes | 4.3955 | 0 /0 /36 |
| Peak OPEN entries | 0.8316 | 25 /1 /10 |
| Query-extra peak RSS | 1.00024 | 13 /1 /22 |
| Loaded wall time | 0.9656 | 33 /0 /3 |

All36 pairs also have equal aggregate transitions, terminal attempts, leaf
routes, transition input/output pieces and maximum depth. This supports a
measured bound-query reduction rather than extra exclusion of exact transition
work on this subset. Equal totals do not establish identical histories,
incumbent trajectories or primitive costs. OPEN entries are not bytes; the RSS
result does not demonstrate a consistent memory benefit. There is one
observation per cell, always Strong first, with possible host/cache/order
effects. The wall ratios establish neither a causal batching speedup nor a
population performance claim.

On the seven common timeouts, Scale also has fewer bound queries and OPEN
entries, but these are different censored work prefixes. Median transition
timer/loaded time is60.4% Strong and65.2% Scale, versus6.89% and6.77% on the
common exact subset. Selected-leg shares there are42.2%/45.1%. Timers are nested,
not additive exclusive shares; transition timing does not split C/S/CS.
Hard schedule continuation work and typical completed-query road costs are
different concerns. The failed pending-activity pair does not identify a safe
next fast kernel or justify another broad optimization campaign.

Existing evidence must not be erased or understated. The earlier shared-bound
SD02 energy N16 ablation finished at47.67s with completion terms and timed out
at60s without them: useful evidence for the **shared bound**, not hierarchy.
Historical D02 solved all64 qualified C anchors of its declared corridor, with
two positive charges; it is a complete corridor snapshot, not full-province
optimality. Later D04 energy N128 finished exactly at76.573/64.075s, missing60s.
The N64 cohort and the last two screen-on UNKNOWN rows remain unchanged.

The exact subset's seed-quality diagnostic is also reproducible:35/36 Strong
and36/37 Scale exact rows record a seed;26/27 improve its primary cost. Median
relative seed J gap is2.024%/2.069%, maximum37.514%. WD12/E18/schedule lacks a
recorded seed for each method. This is conditional anytime-seed quality. The
seed already uses joint CS logic, so this **does not fulfill** the separate
planning/activity-overlap value comparison.

## Targeted primary-source audit

This is a focused comparator/claim audit, not exhaustive novelty clearance.

* Baum et al.'s [CHArge full paper](https://arxiv.org/pdf/1910.09812) treats
  minimum trip time with charging stops, variable/partial charging and
  continuous charging-function labels, combining generalized A* with road
  preprocessing. Continuous charging and a hierarchy are not sufficient new
  claims by themselves. Its road-path decisions must be mapped to HiRoute's
  selected-leg contract; full K and activity/CS equivalence are not established
  here. This audit found no verified drop-in author implementation; it does not
  establish that none exists. No CHArge runtime comparison has been performed.
* Froger et al.'s [author manuscript](https://re.public.polimi.it/retrieve/e0c31c0f-fe02-4599-e053-1705fe0aef77/11311-1087446_Jabali.pdf)
  develops E-VRP-NL formulations and fixed-route charging methods. Its problem
  definition assumes triangle inequalities for travel time **and energy**.
  Energy on our selected fastest paths need not be a shortest-length metric;
  importing such pruning without proof would change correctness. Fleet/customer
  constraints and HiRoute's full-key/activity/open-attainment semantics also
  differ. The paper is a modeling reference, not a directly comparable baseline.
* The [CTU author publication page](https://fel.cvut.cz/cs/fakulta/lide/420-michal-jakob/publikace)
  records Cuchy, Stolba and Jakob's 2019 *Integrated Route, Charging and Activity
  Planning for Whole Day Mobility with Electric Vehicles*
  (DOI10.1007/978-3-030-05453-3_13), and Cuchy, Vokrinek and Jakob's 2024
  *Multi-Objective Electric Vehicle Route and Charging Planning with Contraction
  Hierarchies* (DOI10.1609/icaps.v34i1.31467). Their author abstracts already
  describe joint activity planning and multiobjective road hierarchy methods.
  Only abstract-level evidence was obtained for these works; no full model or
  attainment equivalence is asserted. Road contraction and next-action Region
  refinement are different mechanisms. Their reported gains cannot transfer
  to this system.

A defensible future claim must explain the distinctive representation,
correctness contract and measured cost tradeoff relative to these methods.
The current evidence supports an exact modeled planning system and a conditional
batching mechanism, not a demonstrated external state-of-the-art advantage.

## Independent comparator contract: proof gate before a benchmark

Taskbook section8.1 permits an independently auditable optimization model.
That is the recommended first gate if a faithful external implementation cannot
be obtained. It must not call Core/REF internally under a new method name.
Start with tiny common energy-only cases and independently generated constraints;
expand only after semantic parity. This is a specification, **not an implemented
or validated external baseline**.

1. Use directed canonical selected-leg time/length as fixed stop-to-stop inputs,
   charging all input preparation costs. Do not route that table as an ordinary
   graph that inserts unrecorded intermediate stops. Bound active prefix slots
   only by the safe depth derived from an actual attained UJ/(hmin+lambda).
   Permit empty termination, repeated Sites and only legal effects; service
   occurs once. A small diagnostic depth does not certify the unrestricted task.
2. Independently model arrival energy, positive C/CS charge, capacity, selected
   leg consumption and final reserve. Use incoming/outgoing charging-segment
   selectors for Phi(Eout)-Phi(Ein), not a constant average power. For future
   schedule support, encode exact C/S/CS output-time maxima with branch selectors
   and dominance constraints, not unexplained lower-bound time slack. Include
   the allowed nonnegative initial wait. Derive finite time/energy Big-M bounds
   from attained U and capacity; unsupported branches must be reported.
3. Optimize the actual lexicographic `(J,Q,H,Pi)`, with exact Site/effect order.
   Use rational coefficients/row scaling and checked solver evidence; a small
   floating MIP gap is not an exact certificate. Replay an independently
   obtained witness and report attained, unattained, infeasible and resource
   UNKNOWN separately.
4. Handle strict `q>0` explicitly. Closing it to `q>=0` is insufficient even
   with a test on the optimum face. A full-battery CS-only branch with zero
   driving energy has no positive-charge point anywhere, yet its closure can
   admit a cheap zero-charge service. The new tiny fixture demonstrates this
   comparator trap; it is **not a defect in the current exact Core**.

For a fixed discrete branch (including charging segments and max pieces), its
closed relaxation P is convex. First maximize a common epsilon with each active
charge `q_i>=epsilon`, `0<=epsilon<=capacity`, **before fixing an objective
face**. If no positive epsilon exists, discard the entire branch as strictly
infeasible. Otherwise convex combination with a strictly feasible point proves
that the closure of its strict set is P. Its closed minimum J is a valid
infimum. Test positive epsilon again on the global minimum-J face to establish
primary attainment. Only primary-attaining branches contribute to secondary-Q
optimization; repeat the test on the J/Q face before selecting H/Pi among
jointly attained optima. A fixed artificial minimum charge is not an equivalent
model. Tiny exhaustive branches are acceptable for this audit, with no promise
of scalable enumeration or use of the full real road graph as REF.

[SCIP10's official exact-mode documentation](https://www.scipopt.org/doc-10.0.0/html/EXACT.php)
describes rational/safe arithmetic, required exact LP dependencies and optional
proof logging; certificates may need completion before checking. Read-only local
inspection found no scip/soplex executable or PySCIPOpt installation. No package
was installed and no external solver ran. Exact-mode build/verification and the
strict-branch protocol are concrete prerequisites, not assumed capabilities.

## Original acceptance checklist, reconciled

| Taskbook requirement | Present evidence and status | Remaining work |
| --- | --- | --- |
| Exact physical incremental families, terminal separation, full K/attainment, safe relevant depth, UNKNOWN | Implemented, focused normal/optimized tests, finite REF parity and physical replay; old diagnostics preserved | Preserve contract in any extension; tests are evidence, not a formal proof of all code |
| Exact directed selected legs/ties, shared seed/kernel/resources, no member scans | Implemented shared provider and static extrema; costs/residency reported | Independently audit external input mapping; no free all-pairs routing |
| Real pilot, two/three positive charges | Completed on declared Shandong domains | Four-positive-charge evidence absent; no proof of impossibility and no artificial physics changes |
| N64/128/256 and complete qualified domains | All48 N64 cells executed/reused/unavailable; limited N128 exact and historical full-corridor N64 result | Wider N128/N256 and representative full domains unvalidated |
| >=95% exact <=60s; median <=10s | **Failed**, including supported population | Neither more Sites nor narrower reporting fixes this failure |
| Query-extra <=8GiB and host guards | Observed N64 maxima1.036/1.062GiB; graph/index/total/cold costs recorded | No larger-domain memory guarantee |
| Bound/batching/order attribution | Shared-bound ablation; present query/OPEN/heap tradeoff; routing/queue diagnostics | No pure causal timing isolation or broad hierarchy superiority |
| External exact/common-model comparison | Primary-source/semantic audit and proposed model contract | Independent implementation, exact verification, declared common DEV comparison |
| Planning/application value | Seed quality can be reported now | Separate/sequential heuristics, feasibility/time/stops/Q/detour/overlap comparison |
| Algorithm/design/statistics freeze and >=8 new OD groups | Not frozen; all12 existing OD groups are DEV | No holdout started; none may be relabeled independent |

Coverage is an additional explicit limit. The supplemented catalog has172
distinct qualified C road anchors, not227 usable charging anchors. Frozen60km
availability is20/24 energy and24/24 schedule cells at N64,0/24 and24/24 at
N128,0/24 and22/24 at N256. This policy-specific N128 energy gap does not
contradict the wider-corridor D04 N128 result. Energy N256 lacks enough anchors
even in the current provincial catalog. Service-only POIs, duplicate station
records or corridor widening to fill N cannot solve that input requirement.

## Bounded revised completion path, not new experiment authorization

This turn conservatively precharges300CPU seconds for analysis/tiny tests,
reproduction, required CI and delivery (superseding its initial120s reservation).
Carry is **11305.649970329 /28800**, leaving **17494.350029671**.
Preprocessing stays **652.040677976 /900**. No fresh real
solver row, data acquisition, source upload, main experiment or holdout ran.
The relevant36-test normal and `-OO` runs each passed, with measured child CPU
1.392196/1.825932s; final bound reruns after adding the artifact gate consumed
1.431738/1.871716s. Reducer integrity tests separately validate the denominator
and reject duplicate, substituted-domain and inconsistent full-key evidence.
Two initial local verification invocations hit the repository's explicit test
classification guard. Their failure receipts are preserved externally. The
committed-data reducer tests are now registered as research-artifact tests and
run separately with unittest; the data-free cohort selection was not relaxed.

The following is a concrete staged resource proposal. It reserves future
validation rather than spending the remaining budget on tuning. It is not a
claim that all acceptance criteria can be achieved within these envelopes.

| Gate, in order | Proposed inclusive CPU envelope | Frozen scope / stop condition |
| --- | ---: | --- |
| Independent common-model prototype | 600 | Exact-mode availability and tiny strict/attainment/full-key tests first; stop if unavailable, unsound or too costly; no Core-hidden comparator |
| External common-domain DEV check | 1500 | Only after prototype parity: existing WD07/E48/energy and WD01/E18/energy N64 domains, one external row each; reuse historical Strong/Scale controls, no fresh baseline timings; preserve UNKNOWN/unsupported |
| Planning-value DEV check | 1800 | WD01 and WD07, both initial energies, schedule N64: two deterministic separated/sequential heuristics, eight rows; freeze selection/search and physical replay before outcomes; include failures and costs |
| Larger/full-domain DEV gate | at most2094.350029671 | At most one existing N128 schedule pair and one current full-qualified corridor energy pair, identical methods/domains and no outcome-driven replacement; select by declared candidate count/query-ID rule before execution; budget-unrun retained |
| Protected future holdout reserve | 11500 | After algorithm/design/statistics freeze only: >=8 genuinely new OD groups x2SOC x2scenario, both methods; not selected or launched now |

Every gate includes development, cold workers, numerical work, cumulative
controller and reporting charges. Keep one numerical worker/thread,120s method
limits, memory/headroom checks and durable starts/finals. The repaired live
all-inclusive admission mechanism must reserve a conservative pair and reporting
allowance before starting; an uncertain start is inspected, not replayed.
Unused allocations do not authorize extra rows. A reservation is not a separate
hardlimit on controller CPU; continued inclusive monitoring remains necessary.
Future holdout also needs this protection and an explicit completion decision.

The full144-query N64/128/256 product needs34560 query-slot seconds at120s per
method even before cold costs, supplemental domains and external work. It
cannot be promised within the remaining budget. Four-charge discovery, missing
energy256 inputs, demonstrated performance improvement and a genuinely
independent holdout cannot be manufactured by finishing documentation. If the
prototype cannot support a defensible common model, or bounded DEV still fails,
the concrete decision is whether to revise the research objective/budget/data
scope or conclude a negative result. Such a change requires an explicit research
decision; routine permission for individual functions is unnecessary.

Correctness evidence, reproducibility and limitations can be delivered now.
The original real-scale success claim remains **NO-GO**, while the optional
batching mechanism and exact planning system are worth preserving. No further
algorithm architecture or blind timed tuning is proposed by this reassessment.
