# Compact comparator: proof/design gate

## Decision and observed scope

**The strict-support lift is mathematically valid and practicable on the declared
tiny tests with the existing Z3 backend.** It uses slot/action/segment/max
selectors rather than enumerating complete plans or linear branches. Thirteen
frozen cases match their independent analytic answers and both unrestricted
Strong/Scale results:11 attained optima,1 primary-unattained and1 secondary-
unattained result. The public API requires an independently replayable attained
upper-bound witness. Missing a witness is UNKNOWN, not infeasibility.

This does not establish a practical N64 comparator, an external state-of-the-art
advantage, or original taskbook completion. Production HiRoute, its physical
parameters, data, routing, seed procedure and historical results are unchanged.
The new module is opt-in under `comparison/compact_smt.py`; it is not registered
as a production solver. Baseline policies are definitions only; see
[PLANNING_VALUE_BASELINES.md](PLANNING_VALUE_BASELINES.md).

The verified merged base is
`151f0e147fc0dda707985e38672760cfadec8fe6` (PR36). Its existing full M5 CI
`41328071918` is followed without restart or cancellation. Comparison source
at this merge is the already reviewed PR36 source; no new main run is requested
to repeat that evidence. The new bounded comparator CI also runs automatically
on a subsequent main push touching its files, with that invocation reserved
inside this gate's budget. CI results are recorded separately from solver data.

## Relevant-depth domain and input contract

Only the known exact-rational snapshot/model/selected-leg versions are accepted.
The snapshot must declare `unrestricted`: a diagnostic H cap is rejected rather
than interpreted as an unrestricted optimum. Scalar types, identities, physical
bounds, capabilities and charging-curve coverage/continuity are checked.
The supplied feasible plan is concretely replayed with the independent Fraction
ledger before its cost is used. No claimed numeric upper bound is trusted.

Let its actual attained primary value be U. Every physical stop adds at least
h time and lambda penalty; driving, waiting, charging and service duration are
nonnegative. Thus every plan with `J<=U` satisfies

`H<=floor(U/(h+lambda)) = H_U`.

This argument uses the actual witness, not a reference optimum or a HiRoute
relaxation. The model includes every legal history through H_U and cuts at
`J<=U`. That cut preserves a global optimum or global infimum below U; if the
infimum equals U, the supplied attained U already establishes primary
attainment. Joint optimal J/Q faces at U remain included. No seed does not
provide a finite depth bound, so the API returns `unknown_no_attained_bound`.

The prototype currently supports at most2 literal Site anchors,6 road nodes,
12 edges,2 charging segments and H_U<=6. It returns unsupported when a guard is
exceeded; it never replaces H_U by6 and calls that result optimal. Aliases and
Sites coinciding with origin/destination are explicitly outside this prototype.
The old enumerative comparator retains its H<=2 guard unchanged.

Road selection uses the previous independent tiny-road implementation: positive
time guarantees that a shortest-time path is simple; full node and then edge-ID
tuples determine ties, with length measured on that selected path. No selected-
leg table is rerouted as an ordinary graph. Exhaustive road-path selection is
deliberately limited to <=6 road nodes, not applied to the real graph.

## Compact encoding

There are H_U slots with shared finite selectors d:

* an action rank (inactive0 or a canonical `(Site,effect)` rank);
* incoming/outgoing charging-segment indices;
* the maximizing output-time expression.

Inactive slots form a suffix and preserve energy, time and anchor. Service S/CS
requires a pending activity and consumes it once; repeated charging Sites are
allowed. The action selectors determine consecutive anchors and exact directed
selected-leg costs. Unreachable pairs are forbidden. They also determine H and
the canonical Pi order. Segment and max selectors are shared between both
continuous state copies; sharing only the plan would not establish the required
convex-fiber proof.

Each copy has its own initial wait, energy/time state and charge quantities.
It independently enforces floors/capacity/reserve, selected-leg consumption,
piecewise charging-time differences and the exact C/S/CS maxima and window
conditions. Multiplication is only by rational constants; conditional terms
use finite selectors, not products of two variables. The formulation is mixed
linear integer/real arithmetic, not nonlinear optimization.

For a **fixed** selector assignment d, the weak-charge constraints define a
closed affine polyhedron P_d with `q_i>=0`. The valid U envelope bounds times and
initial wait; energies are bounded by capacity. Hence P_d is compact. The only
open constraints are the strict positive charges. This statement concerns one
fiber, not the closure of an arbitrary disjunction.

Encoding size is O(H_U) state variables/selectors and
O(H_U*(N+1)*number_of_actions) leg-selection terms, plus charging/max constraints.
There is no explicit complete-plan/branch list. This is a representation-size
statement, **not polynomial solve time**; Z3 may still explore many assignments.
N-squared leg preparation, real graph residency and routing costs are not made
free by the compact encoding.

## Strict-support proof and objective faces

Let `Strict_d(y)` mean `y in P_d` and every active charging quantity in y is
strictly positive. Construct two copies sharing **all** d:

`F(x,y,d) = x in P_d AND Strict_d(y)`.

Projection onto `(x,d)` is exactly the union of P_d for fibers with a nonempty
strict physical set. If no strict y exists, that fiber contributes no x at all.
If a strict y exists, for any x in P_d and `0<epsilon<=1`,
`(1-epsilon)x+epsilon*y` belongs to the same fiber and has every active charge
positive. Consequently `closure(Strict_d)=P_d`. The finite union of these
supported closed compact fibers therefore gives the correct primary infimum.
The candidate x may be a limit, but it is never reported as an incumbent merely
because it optimizes F.

1. Minimize J(x) over F. Require a finite exact rational bound, matching lower/
   upper bounds, a feasible equality face and an UNSAT exact query for a strictly
   better point. Call the result j.
2. Test the **actual strict formula** at `J(x)=j`. If unsatisfiable, report
   `primary_unattained`; do not report later coordinates.
3. For secondary minimization use
   `F AND J(x)=j AND J(y)=j`. The additional support-face equality is essential:
   only a fiber whose strict primary face is nonempty may contribute its closed
   J-face to Q. Convex combination within that affine J-face gives the same
   closure proof. Minimize Q(x), obtaining q.
4. Test the actual strict formula at both `J(x)=j,Q(x)=q`. If unsatisfiable,
   report `secondary_unattained`, without a complete key.
5. Otherwise minimize integer H and each successive canonical action rank on
   the **actual jointly attained face**. These finite coordinate sets attain
   their minima. Replay the resulting physical plan and require exact full-key
   equality before returning `(J,Q,H,Pi)`.

Native strict satisfiability is equivalent to existence of a positive common
epsilon for the finitely many active charges. No artificial minimum charge,
floating tolerance or global closure is introduced. The exact
[Z3 optimization documentation](https://microsoft.github.io/z3guide/docs/optimization/arithmeticaloptimization/)
distinguishes infinitesimal bounds from attained values; a printed optimizer
model alone is not treated as a certificate. Resource unknowns and nonrational/
nonfinite/tightness failures stop this gate, rather than becoming optimal results.

## Adversarial and observed evidence

`comparison/compact_cases.json` was frozen before its first solve. Every
independent result is persisted before importing Core for the26 Strong/Scale
comparisons. The13 cases perform196 external checks per mode. They cover the
previous feasible analytic cases, both unattainment kinds, time shifts,
piecewise charging, Pi ties and three additional designs:

| Fixture | Forbidden shortcut's answer | Correct compact result |
| --- | --- | --- |
| Full-battery CS disjunct plus a feasible S alternative | Global closure invents J14 from an empty strict CS fiber | Attained J20,Q0,H1 at the S Site |
| Two CS Sites, one unable to attain the best J | Supporting the branch only away from the J face invents Q0 | Attained J13,Q1,H1 at the other Site |
| Valid but loose one-stop seed J36 | A hidden H2 cap would omit part of the declared relevant domain | H_U=3,12 selectors, optimum J16/Q3/H1; no plan enumeration |

The first two wrong answers are tested explicitly against the intentionally
unsafe formulas. They are counterexamples to those shortcuts, not defects in
the implemented strict-support model. The H3 test blocks the old plan and branch
enumeration functions while the compact solver succeeds.

A separate focused regression, specified before its first solve, actually
requires three stops: C-S-C attains J42,Q4,H3 and a two-slot strict model is
infeasible. Initial energy1 reaches charger c empty; capacity3 permits the
c-service-c round trip of length2, but cannot also cover the final length2 leg
without returning to charge. Skipping the first charge cannot reach service;
skipping the second leaves insufficient energy after service. Both unrestricted
Core methods agree with the independently solved/replayed H3 key. This adds two
focused comparisons without changing the frozen13-case cohort or any real row.

At numerical source `23204b5a8731e9adcacfb60956d3f1855c349f10`, twenty focused
tests pass in normal and `-OO` Python, including the old gate,
compact proof cases and policy-definition tests. An additional waiting-plateau
fixture has complete H_U=2: one-stop CS and two-stop C-then-S both attain
J12/5,Q1, and H selects CS. Tests reject invalid upper witnesses, unsupported
contract versions, floating/noncanonical inputs and diagnostic caps. A valid
seed with excessive waiting derives H_U>6 and returns unsupported without an
optimal key. Missing a seed remains UNKNOWN. There were no failed semantic
cases in this gate. All raw runs, including any future failures, retain their
denominator and error/unrun states.

The subsequent audit-only correction persists all26 Core slots before the
first parity call, then atomically checkpoints before and after each call.
Caught exceptions (including interrupts and SystemExit(0)) finalize a failed
gate with explicit error and remaining-unrun cells. Abrupt process termination
leaves the current slot running/uncertain, prior completed receipts and future
unrun cells, with passed=false and finalized=false. Checkpoint I/O failures
propagate; pre-existing output receipts require a fresh directory. Five mocked
regressions pass normally and under `-OO`: mid-phase exception, abrupt child
exit, mismatch/interrupt, all-slot completion and atomic replace failure.
These local correction checks import neither Core nor a numerical solver.

The original13-case results,196 SMT inputs per mode and original CI artifact
remain evidence for source23204b5a; they are not relabeled as produced by the
delivery correction. The solver, frozen cases and published numerical summary
are unchanged. Standard bounded CI on the corrected head checks integration in
fresh artifact directories, separately from those historical records.

Observed local CPU is a resource receipt, not a runtime benchmark. No real
graph/N64 or baseline policy solve ran. A compact encoding does not establish
that external real-domain selected-leg preparation or optimization fits120s.

## Accounting, CI and reproducibility

The entire **900CPU-second gate** is conservatively charged, including setup,
tiny validation, control, reporting and verification. Carry becomes
**12805.649970329 /28800**, leaving15994.350029671. Preprocessing remains
**652.040677976 /900**. The initial allocation was240 local CPU,360 for PR/main
CI,180 development/control/report/verification and120 automatic PR legacy
startup cancellation. For the audit correction,92 unused local seconds move
to CI: reservations are now148 local,452 shared dedicated CI,180 control/report
and120 startup cancellation, still900 total. Original PR CI conservatively
charged91.791824; corrected-head PR CI reserves180 and future merged-main CI
retains180 (451.791824 <=452). Local correction verification adds only the five
mocked tests in each Python mode. Both allocation versions and original raw
receipts are retained externally. No unused reservation authorizes extra
measurements.

The pre-existing merged-main legacy M5 workflow was already admitted by the
parent's merge before this gate. It is tracked as inherited infrastructure,
with verification/control included here; its uninstrumented legacy execution is
identified separately, not described as a new comparator solve or assigned a
fictitious zero CPU measurement. It is neither restarted nor cancelled. The
new source does not change the production package. The new comparator's PR
and future main invocations are explicitly budgeted and guarded; status IDs,
startup cancellations and receipts are preserved separately and never relabeled
as passing checks.

Local commands have cumulative CPU receipts and hard process limits. The
dedicated CI keeps per-command admission/limits, a hard controller limit,
single-threaded solver calls, partial started records and retained artifacts.
Environment/setup allowances are conservative reservations, not separate kernel
hardlimits. The official solver dependency is unchanged from PR36. No new
installation, license, credential, data acquisition or server upload was needed.

```sh
python -m unittest discover -s comparison -p 'test_*.py'
PYTHONPATH=src python comparison/run_compact_gate.py --output /tmp/compact-gate
```

Use the bounded wrapper/CI controller for admission and accounting. Raw exact
queries and results are outside Git and retained as CI artifacts. The compact
summary is [compact_comparator_gate_results.json](compact_comparator_gate_results.json).
Z3 optimization and better-point checks still trust the same external backend;
no separately checked formal proof certificate is claimed. The road selector
is independent of HiRoute but shared with the concrete prototype replayer.

## Next bounded measurement decision

The proposed next measurement is the frozen **four-query/eight-policy-row
planning-value DEV stage**, with a hard1800 inclusive CPU cap, unchanged120s
method limit and all budget-unrun/failure cells retained. It reuses historical
joint values only after baseline receipts, never as a seed/oracle. It is defined,
not launched, in `configs/planning_value_baselines_dev.json`.

A real external comparator still needs a scalable selected-leg input contract,
charged routing/table preparation and larger-domain validation. Raising tiny
road/size guards would not supply that evidence. After protecting the previously
proposed11500 holdout reserve and1800 planning-value proposal, only2694.350029671
CPU seconds remain for other pre-holdout work; the earlier larger/external
proposal cannot all be promised unchanged. No main experiment or holdout is
started or authorized by this report. Original timing goals, larger/full-domain
evidence, true four-charge cases, application results and independent validation
remain unmet.
