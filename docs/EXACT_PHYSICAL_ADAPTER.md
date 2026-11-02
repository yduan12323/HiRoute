# Independent physical model on exact leg inputs

## Observed result and boundary

The frozen eight-class tiny gate passes: six attained optima, one primary
unattained infimum and one secondary unattained infimum agree with the analytic
contracts. This establishes a working independent continuous-model integration
on these synthetic supplied tables. It does not establish real N64 practicality,
real road selection, a general Core parity theorem or original taskbook success.
No production optimizer, physical parameter, old result or original compact
prototype guard is changed. No real road table, real-scale solve or holdout ran.

Numerical gate source is `cc85f5827723c04170cb765248c3e03324b365ef` on verified
main `c0600d4d12061bceedfed6ec22b3f53d3df9e8c7`. Later changes add fail-closed
receipt joining, regression coverage and reporting; the eight cells are not
rerun. [exact_physical_results.json](exact_physical_results.json) preserves the
full denominator, source/input identities, command failures and check hashes.

## Physical and input contract

`tools/exact_physical_adapter.py` implements the current positive-overhead,
nonnegative-consumption time-cut physical rules on a parser-owned
`ExactLegTable`. The new versioned parameter schema accepts exact integer or
rational strings, a positive capacity/overhead, floor<=initial<=capacity,
floor<=reserve<=capacity, nonnegative penalty/consumption, one pending activity
and a contiguous continuous charging-time curve with positive slopes. Every
provided charging piece is represented; there is no two-piece prototype cap.
All charging fixtures here use three pieces. Parameters are copied to immutable
Fraction tuples. This entry point is a declared-table model, not a general
real-snapshot ingestion or road certificate pipeline.

T/L/Reach and action/source/target mappings come from the shared grounded lookup.
There is no new shortest-path search over the leg table. Selected actual lengths
are used directly for consumption. Literal Site/effect/Pi identities, alias-zero
legs and repeated visits remain separate actions and stops. Every active visit
has the overhead and penalty, including a visit that moves zero distance.
Inactive slots form a suffix and copy energy/time. Terminal drive always follows
the last active physical anchor, or origin for the empty prefix. Pending activity
prevents an empty completion; terminal energy failure does not remove prefixes
that can charge before completing.

For selected leg (dt,ds), arrival is t+dt and incoming energy is E-rate*ds.
Active arrivals/departures obey floor/capacity. S preserves energy. C/CS require
strictly positive q=Eout-Ein, with charge duration Phi(Eout)-Phi(Ein). The exact
finish equations are:

- C: arrival+h+charge_duration.
- S: max(a+D, arrival+h+D), with arrival<=b-h.
- CS: max(a+D, arrival+h+D, arrival+h+charge_duration), with arrival<=b-h.

Thus charging/service overlap uses a maximum. Equality at the latest start is
legal. Initial waiting is nonnegative; the terminal reserve is checked after
the selected terminal leg. J is terminal time minus departure plus lambda*H;
Q is total positive charge. Full K=(J,Q,H,Pi) is optimized in that order.

The standalone Fraction replay uses these concrete equations and the literal
selected pairs, with no SMT expressions or production optimization. Invalid
upper witnesses fail validation. Missing seeds return UNKNOWN rather than
infeasibility. Every returned attained witness is replayed and its full key
compared exactly, without floating tolerances.

## Complete relevant depth and strict-support proof

Let U be J of the independently replayed feasible supplied witness. Drive,
waiting, service and charge durations are nonnegative. Each active stop adds
at least h to elapsed time and lambda to J, so every relevant actual plan with
J<=U satisfies H*(h+lambda)<=U. Therefore floor(U/(h+lambda)) is a complete
finite relevant depth. The equality boundary is retained. Prefixes may revisit
Sites; neither H<=N nor H<=6 nor H<=51 is imposed. A construction-only regression
uses seven slots with two Sites, and a loose feasible bound derives H>6. Those
construction probes are not diagnostic-cap optimum claims. Any resource stop
is UNKNOWN, not a truncated optimum or infeasibility proof.

Fix all finite selectors d: action, incoming/outgoing charging piece, and the
chosen maximum expression at each stop. All road terms are then constants and
both continuous copies obey a closed rational affine polyhedron P_d, including
J<=U. Strict inequalities are exactly the positive-charge conditions. If one
strict point y exists in P_d, convex mixing of y with any closed point x in P_d
approaches x while satisfying every positive-charge inequality. Hence the
closure is P_d **only for fibers with nonempty strict support**.

The primary optimization uses shared d, a closure/objective copy x and a strict
support copy y. This excludes a wholly strict-empty fiber without incorrectly
closing the entire disjunction. Primary attainment is then checked with actual
strict x and J=j. For secondary optimization, **both** x and strict y are on
J=j; a fiber whose primary value is merely approached cannot contribute a
spurious Q value on that face. Joint J/Q attainment is tested next. Only the
actual attained joint face is used for H and then the canonical literal Pi.
The selector sets are finite and derived depth is complete, so this is a finite
union of the relevant affine fibers, not plan/simple-path enumeration.

Z3 Optimize bounds must be equal exact rationals, followed by an UNSAT check for
a strictly better point and a SAT check of the closed face. Unknown, nonfinite,
nonrational or contradictory solver results cannot become certified values.
Every SMT call has a <=2s timeout within the <=8s cell deadline. The final
attained replay also checks the deadline. These are resource limits, not depth
or domain reductions. A process guard can leave a started call without a terminal
receipt; reporting keeps that cell incomplete and retains remaining unrun cells.

Focused regressions preserve two unsafe counterexamples: globally closing the
disjunction invents J=14 instead of the supported J=20; letting the secondary
support witness leave the primary face invents Q=0 instead of the attained Q=1.
A waiting plateau also verifies H before Pi when C-S and CS share J/Q. Fifteen
local regressions pass normally and under-OO; extra mocked reporting/accounting
checks pass in both modes. No assertion or existing time limit was weakened.

## Frozen evidence and what parity means

| Synthetic class | Complete H from U | Observed semantic result | Gate SMT checks |
| --- | ---: | --- | ---: |
| Empty prefix/terminal | 0 | attained K=(2,0,0,empty) | 13 |
| Alias positive charge, three pieces | 3 | attained K=(18,6,1,alpha:C) | 16 |
| Repeated literal C-S-C | 4 | attained K=(44,4,3,c:C/s:S/c:C) | 22 |
| CS overlap | 2 | attained K=(16,3,1,p:CS) | 16 |
| Directed dead terminal | 1 | attained K=(8,0,1,a:S) | 16 |
| Temporal/energy equality | 2 | attained K=(29,3,2,c:C/s:S) | 19 |
| Primary open endpoint | 1 | infimum J=10, not attained | 5 |
| Secondary open endpoint | 1 | attained J=14, infimum Q=0 not attained | 9 |

All eight cells are retained, each executed once after successful worker startup.
All116 gate SMT inputs and incremental check receipts are preserved outside Git;
the read-only join verifies their hashes and full eight-cell coverage. Six
returned optima pass the new concrete replay. Seven upper witnesses and five
returned witnesses also agree with the pre-existing independent concrete replay
on nonalias inputs. The alias case has analytic/key checks and the new concrete
replay; the old prototype does not represent its aliases, so it is not called
there. The old optimization cohorts and Core optimizers are not invoked as an
oracle. Focused tests make additional tiny SMT calls; their per-call count was
not instrumented, but complete subprocess CPU is charged.116 is the gate count,
not a claimed total including those regression processes or ordinary software CI.

These are analytic tiny semantics and independent-formulation evidence relative
to HiRoute, not two wholly unrelated implementations: the formulations share Z3,
and the separate old replay and fixture generator share the guarded tiny road
selector. Synthetic graphs have <=6 nodes/12 edges and use exhaustive positive-
time simple-path selection with node/edge tuple ties. This bounded tiny method
is not used on real graphs. External tiny certificates record this explicit
scope; the model still reports road_selection_certified=false. Structural table
validation alone never certifies graph path sums, shortest-time selection, ties
or unreachable cuts.

The eight body CPU values are <=1.283s on these tiny inputs, and the maximum
observed process-group RSS is66600960 bytes, with host availability at least
4675354624 bytes. Body timers start after imports; the supervisor charges the cold process and
bootstrap as well. These are no real-scale runtime, performance-target or
hierarchy advantage claims. A single worker/thread,30CPU/55wall seconds per process,
1GiB process RSS,3GiB start and2GiB runtime host guards were retained.

## Failures, accounting and reproduction

The first development suite retained six Pi container mismatches: old replay
was given lists while the new replay canonicalizes action tuples. Normalizing
the caller's literal action pairs repaired the comparison without changing
physical equations or expected keys. A separate initial controller attempt
failed in preexec before the first gate worker executed: the outer hard CPU
limit10 prevented setting worker CPU30. Its record has no numerical PID or cell
directory. The outer controller now uses soft10/hard34; the worker CPU30 and
all memory/time limits remain unchanged. The unstarted failure remains charged
1.001547 seconds, and the corrected startup has a distinct label. Source and
inputs for all actual gate workers remain cc85f58. No uncertain worker was
replayed. All19 recorded commands are terminal (one preexec failure has no
executed numerical worker); raw old receipts and controller versions remain.

Admission was <=900 research CPU seconds, carrying15308.219957741/28800.
The full300 development/report/controller precharge remains. Metered command,
controller and tail charges are conservatively rounded upward per command,
without reducing an earlier rounded charge:31.808096. Total stage charge is
**331.808096/900**, cumulative **15640.028053741/28800**, remaining
**13159.971946259**. Previous charges are retained. Preprocessing stays
652.040677976/900. Ordinary software CI has separate prospective reservations;
its allowances are not measured whole-job CPU or research refunds.

Raw input tables, all eight source/config/physical fingerprints, literal upper
witnesses,116 SMT artifacts, every started/terminal receipt, controller logs and
failed startup are in `exact-physical-adapter-artifacts-v1` outside Git. Fresh
reproduction paths and an external supervisor with the declared CPU/RSS/host
limits are required. The source/config check is within-run provenance; a new
source may create a new admission, without any source hash/file-count lock.

```sh
python -m unittest discover -s tests -p test_exact_physical_adapter.py
python -OO -m unittest discover -s tests -p test_exact_physical_adapter.py
python tools/run_exact_physical_gate.py prepare --output /fresh/admission.json
python tools/run_exact_physical_gate.py run --case empty_prefix_terminal \
  --preflight /fresh/admission.json --output /fresh/cases/empty_prefix_terminal
# Repeat once for each remaining frozen case_id, sequentially under supervision.
python tools/report_exact_physical_gate.py --root /fresh --output /fresh/results.json
```

The receipt join additionally expects the supervisor's fixed gate budget and
command records (including the final regression labels); it is not a mechanism
for declaring arbitrary manual runs certified. Normal/OO tests need the pinned
`comparison/requirements.txt`; no new solver/license/account is required.

## Next finite step toward real verification

Real comparison remains NO-GO until a reproducible real input path exists.
Next, design and validate an independent exact road-table certificate checker
on bounded tiny adversarial graphs, then cost the existing frozen real N64
input conversion. The checker must verify directed shortest-time lower labels,
attaining paths, canonical node/edge ties, actual lengths and unreachable cuts,
including every source/terminal/alias-zero pair. It must not enumerate all
simple paths on the real graph or reroute the selected leg table as an ordinary
graph. An external graph/input identity must be bound to that evidence.

Real table generation/certification needs a separate prospective cost/admission
inside the remaining original budget, with cold loads and host memory included.
Only after both the real input and complete physical ingestion/replay are
verified should a bounded real comparator measurement be admitted. A tiny pass
or N64-width construction pass is not that measurement. Original failed timing
and hierarchy evidence, larger/full-domain gaps, real four-positive-charge cases,
full real-scale independent comparisons and a design freeze/new-OD holdout remain
unmet. No existing DEV group is relabeled as holdout.
