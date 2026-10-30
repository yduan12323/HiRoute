# P0 semantics and P1 small-domain profile

2026-10-30. Base: `515a75f63406fd45b7fde412c6673a6ba5e915f0` (fresh clone of
origin/main). This is a finite correctness repair and developer diagnosis,
not a scalability acceptance, real-road benchmark, or holdout run.

## 1. Confirmed P0 problems and repairs

All three observations were reproduced against the base implementations loaded
in memory, without reverting working files:

| Problem | Minimal old behavior | Repaired behavior |
|---|---|---|
| A: equal-time road tie | A1 chose `o,b,z`, time 2, length 2 instead of lexicographically smaller `o,a,z`, length 4 | Dijkstra labels compare `(time, string node tuple, string edge-ID tuple)`; length is accumulated only as an attribute |
| B: mixed time origins | At t0=-3600, after finding `a-C` with K=(6,3,1,a-C), HIER pruned better sibling `b-C`, K=(4,1,1,b-C) | Relative prefix duration + inbound/onward duration + stop penalties, without subtracting t0 |
| C: candidate order treated as route | Fork `o→a→z`, `o→b→z` raised `unreachable selected leg a->b` | Accept both candidate orders and isolated legal candidates; search handles unreachable transfers |

A1 with initial energy 3 is now infeasible within the declared domain in both
production and REF; with energy 5, K=(2,0,0,()), terminal energy 1. This is a
semantic correction, not a speedup. An old test explicitly expecting length as
a tie objective was renamed and corrected. Unique fastest paths still win even
when longer. Tests cover parallel edges, all 24 A1 edge permutations, string
ordering (`10 < 2`), self legs, and unreachable legs.

The positive-edge-time Dijkstra argument is documented beside `selected_leg`:
all shortest-path predecessors settle earlier; equal-time paths to one endpoint
cannot be proper node-tuple prefixes because that would contain a positive-time
cycle. Node-tuple order therefore survives common extension; for equal node
sequences, edge-ID-tuple order survives extension too. No simple-path enumeration
or adjacency caching was added. REF routing and optimization were not changed
and do not import production routing or the optimization kernel.

Missing edge IDs now use REF's existing `input:{index:08d}` interpretation;
these positional defaults intentionally do not promise permutation invariance.
Explicit or resolved default ID collisions are rejected by `ProblemSnapshot`.

The Region bound remains weak by design. It omits nonnegative charge, wait,
service and overhead times; the onward shortest **time** cannot exceed travel
via further stops. It never assumes a triangle inequality for physical length.
Empty reachable-member sets retain existing unreachable handling. Pruning is
still strictly `bound > best_j`; equality is retained. Tests compare bounds with
independent tiny-domain optima, include a nonempty two-stop suffix, equal-primary
better-Q selection, and translate t0/window bounds by 0/+3600/-3600. Attained
witness times translate; J/Q/H/Pi and primary/secondary unattained infima do not.

`ProducedSnapshot.selected_legs` has no computational consumers: repository uses
are producer DAG outputs and tests. Its documented meaning is an O(N) diagnostic
of adjacent pairs in `[origin,*candidate_order,destination]`, **not** a required
itinerary or complete leg table. Each requested pair remains present with
`reachable`; unavailable attributes are null. Unlisted pairs are unqueried,
not unreachable. The full snapshot graph remains authoritative. The synthetic
XML producer shares the same diagnostic helper. No O(N²) table was introduced.
Missing endpoints/attachments, duplicate node/Site/edge identities and other
existing structural/model checks remain input errors. A legal disconnected
problem is accepted and reported infeasible by the bounded solver.

Validation before P1: 62 relevant unittest regressions passed against
non-editable, separately built/installed production and REF wheels. Coverage
includes 76 kWh, strict q>0, open cut/waiting plateau, primary/secondary
unattainment, full-key routing/optimization, physical witness replay, CLI
publication safety and producer contracts. Legacy differential tests used a
separate staged `timecut5` source directory; production/REF imports resolved to
`.venv/lib/python3.11/site-packages`. The new regression is included in the
existing isolated-wheel CI cohort and collection manifest. No historical
certificate, R0–R4 acceptance, raw geographic reconstruction or holdout was run.
A direct local pytest invocation stopped at the repository conftest's unavailable
pandas dependency; the stated local passing result is the explicit unittest
cohort, not that failed invocation. Linux CI runs the normal broader workflow.

## 2. Fixed cases, execution and scope

Configuration: [small_profile.json](../configs/diagnostics/small_profile.json).
All eight slots were written before running them. Explicit graph edges in that
file are authoritative; `graph_or_leg_identity` inherits a descriptive base-fixture
label and is not an external leg provider or an input-identity acceptance check.

| Slot | Domain/purpose | Expected physical interpretation |
|---|---|---|
| P01 | N=0, H=0 | No-stop fixed overhead |
| P02 | N=1, H=1 | Initial energy 1, two length-1 legs: charge 1 at a |
| P03 | N=2, H=3 | Three length-2 legs, capacity/initial energy 2: at least two positive charges are necessary |
| P04 | N=2, H=2, hard service | a permits S/CS; b permits C; fixed [10,20] service window, D=3; waiting plateau |
| P05–P07 | N=2/4/8, H=3 | Same sparse `o→c1→…→c8→z` graph, same query/curve; only nested candidate prefixes change |
| P08 | real DEV slot | NOT_RUN_INPUT_UNAVAILABLE: fresh checkout/task inputs expose no ready real small snapshot |

P08 caused no map download, clipping, data recovery or historical admission.
Its two method rows are retained with null measurements. No real-road cost or
physical real-road witness claim is made.

Environment: macOS 27.0.1 arm64, Python 3.11.15, NumPy 2.4.6, SciPy 1.17.1,
psutil 7.2.2. Each production/ref/profile row used a fresh process; methods
alternated FLAT-first on odd slots, HIER-first on even slots. No numerical
workers ran concurrently. OMP/OpenBLAS/MKL/Accelerate/NumExpr thread counts were
set to 1. Profiles were `bounded_time_cut_v2`, no reduction/coalescing/seed.

The existing `run_supervised` enforcement and process-group cleanup were reused.
A small macOS-only psutil adapter in the diagnostic entry supplies its existing
RSS/CPU/host-headroom sampling hooks; Linux retains the normal /proc monitors.
Per production and profiler row: 120 s wall/CPU; REF: 60 s. Group RSS ceiling:
4 GiB; host available-memory floor: 2 GiB. Group limits are sampled every 50 ms,
not aggregate kernel hard caps; RLIMIT_CPU remains per process. There was no
resource cutoff or leftover job. Supervisor accounting charged 9.167 CPU seconds
(total including profiles/REF), far below the 7200 s ceiling. The sum of worker
CPU checkpoints is 9.109 s; final serialization/profile-summary work can occur
after those checkpoints. Peak sampled group RSS was 79.77 MiB.

Exactly 14 production normal rows, two P08 non-run rows, three REF rows and two
extra profiler rows were recorded. No numerical retry or case replacement was
needed. A quick P02 control with counters off/on preserved status, full key and
complete replay in both methods. P0 code was not changed after P1 started.

## 3. Results and measurement boundaries

Primary table: [SEMANTICS_AND_PROFILE.jsonl](SEMANTICS_AND_PROFILE.jsonl).
All seven completed FLAT/HIER pairs agree in full K. REF P01–P03 independently
completed with matching status/full K and physical replay; other REF slots are
not run. All attained production witnesses were also checked by REF's independent
physical replay (without full optimization). P03 charges twice and P04 completes
the required service with CS. There is no timeout, unresolved REF or mismatch.

| Case | K=(J,Q,H,Pi) | FLAT solve s | HIER solve s | FLAT / HIER supervised wall s |
|---|---|---:|---:|---:|
| P01 | (1,0,0,()) | 0.000180 | 0.000215 | 0.4374 / 0.2656 |
| P02 | (4,1,1,a-C) | 0.001104 | 0.001084 | 0.2497 / 0.2553 |
| P03 | (9,4,2,a-C;b-C) | 0.010598 | 0.010585 | 0.2745 / 0.2614 |
| P04 | (14,1,1,a-CS) | 0.007985 | 0.008137 | 0.2598 / 0.2600 |
| P05 | (16,6,1,c1-C) | 0.021046 | 0.021281 | 0.2752 / 0.2773 |
| P06 | (16,6,1,c1-C) | 0.092654 | 0.093368 | 0.3501 / 0.3464 |
| P07 | (16,6,1,c1-C) | 0.429272 | 0.427241 | 0.6860 / 0.6844 |
| P08 | NOT_RUN_INPUT_UNAVAILABLE | null | null | null / null |

Times are single observations, not statistical performance estimates. Startup
and imports dominate the smallest cases. `load_and_parse_s` includes worker
imports (including independent physical-check dependencies), configuration load
and snapshot parsing; P07 about 0.192 s. `wall_total_s` includes fresh process
startup, solve, independent witness validation, JSON write and supervision.
Independent validation has its own timer and is outside `solve_total_s`.
`cpu_s` is actual worker `process_time()` at the reporting checkpoint; sampled
aggregate group CPU and worker high-water RSS are separately named.

Normal solve timers are disjoint: routing includes adjacency construction;
transition propagation wraps `execute_exact_plan`; terminal wraps
`terminal_optimize`; hierarchy excludes nested evaluate time and routing;
result/witness wraps incumbent/final `replay_terminal`. `solve_other_s` is the
remaining compilation/result-assembly/search overhead. These categories include
light instrumentation overhead. Detailed profiler cumulative times are nested
and **must not be added** to one another or substituted for normal timings.

P07 normal cost breakdown:

| Category | FLAT s | HIER s |
|---|---:|---:|
| Routing | 0.00259 | 0.00292 |
| Transition propagation | 0.37395 | 0.37059 |
| Terminal optimization | 0.04532 | 0.04524 |
| Hierarchy traversal/bound (exclusive) | 0 | 0.00395 |
| Result/witness replay | 0.00006 | 0.00006 |
| Other solve work | 0.00735 | 0.00449 |

P07 FLAT/HIER respectively attempted 585/165 plans; both performed 165 returning
plan propagations (including early empty-family returns), 300 stop-transition
calls and 1185 per-piece drive calls. Both processed 110 distinct discrete
prefixes, including empty and actually attempted next-stop prefixes. They visited
1485 operator-prefix occurrences, with 333 unique `(prefix,effect,anchor)` keys;
1152 occurrences repeat a key. This is an actual call-derived count, but includes
per-piece drive multiplicity as well as reprocessing across plans: it is **not**
a direct time-saving estimate for caching. Piece/operator visits (1924) separately
include input-family multiplicity. Peak observed post-union propagated family size was 7;
this is distinct from cumulative processed pieces and does not measure transient
projection intermediates.

P07 routing: 1613/2981 selected-leg calls, 81 misses and 73 adjacency builds each
(self-leg misses do not build adjacency). HIER visited 363 Regions, performed
656 reachable member-bound evaluations, retained 0 equal-primary Regions and
pruned 0 Regions. Total member scans including unreachable pairs are not
instrumented and are null, not inferred from reachable-bound counts. Flat-only
nonapplicable hierarchy fields are null. Cutoff rows, if any, would null their
partial counters rather than present them as final counts.

The two cProfile runs selected P07 because it was the slowest completed common
synthetic case. FLAT/HIER solve times became 1.7720/1.7764 s (about 4.1× normal),
so they explain hotspots only. FLAT cumulative/self seconds: `stop_partition`
1.331/0.00538 (300 calls), `linear.build` 1.107/0.00406 (739), `normalize`
0.918/0.06609 (3695), `eliminate` 0.863/0.01464 (1478). HIER has nearly identical
operator costs. Fraction arithmetic is nested in these functions; no cumulative
percentage sum is used. Local binary profiles are ignored under `results/` and
not committed.

## 4. Cost attribution and confidence

The measured production solve bottleneck on this sparse synthetic ladder is
exact transition propagation (86.7–87.1% of P07 normal solve), concentrated in
C-stop projection/normalization. Road queries are below 0.7% of solve; Region
management is below 1% and makes no objective-bound prunes here. Small peak
families (7 pieces) do not support a piece-explosion conclusion on this workload.
End-to-end time on the smallest cases mainly measures imports/startup.

**Primary P2 choice: incremental prefix search / prefix reuse.** Current
`search.evaluate` reconstructs each plan from `initial_piece`, then calls
`pipeline.execute_exact_plan`. The observed 300 C-family calls cover only 109
distinct attempted nonempty C prefixes (110 prefixes including empty); repeated
plans therefore re-enter the expensive measured operator. Reusing exact prefix
families is a concrete way to avoid those calls. Counts support this mechanism,
but do not establish an achievable speedup or attribute every repeated drive
piece to redundant whole-prefix work.

**One secondary bottleneck:** the single C operator's rational projection in
`pwa_partition.stop_partition` / `linear.build`, `normalize`, `eliminate`. Its
nested profiler cost warrants focused study if prefix reuse leaves it dominant.
No routing index, tighter bound, seed change or reducer was implemented.

## 5. Next-step boundary and reproduction

After user review, P2 should develop only prefix reuse, preserving immutable
exact families, open boundaries, strict positive charge, remaining-service state,
full K and lifted physical witnesses. Verify against the same fixed cases and
independent tiny REF, include unattained cases and repeated-site prefixes, then
compare normal counted calls/time with the present baseline under the same
budgets. Avoid claiming a priori time reduction from the 1152 repeated keys.
The C/projection alternative is secondary, not another simultaneous project.

Reproduction (fresh Python 3.11 venv, dependency versions above; pytest is only
needed for the normal existing CI workflow):

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install setuptools==79.0.1 wheel==0.48.0 numpy==2.4.6 scipy==1.17.1 psutil==7.2.2
.venv/bin/python -m pip install --no-build-isolation --no-deps . ./reference
.venv/bin/python -m unittest discover -s tests -p test_semantic_fixes.py
.venv/bin/python tools/profile_small_cases.py --output /tmp/hiroute-profile.jsonl
# Local details only, after the driver produces the two selected profiles:
.venv/bin/python -m pstats results/small-profile-local/P07-flat.pstats
```

The diagnostic entry requires installed core/REF dependencies; on macOS also
install psutil. The output path must be new. The existing Linux isolated-wheel
CI entry remains `python ci/run_m5_code_only.py`; it includes the new tests.

Still unmeasured: real-road routing costs, larger N/H, dense/cyclic road behavior
at scale, universal speedup, unbounded/global-domain optimality, real-world
transferability and holdout performance. All mathematical optimum claims here
are within each explicit candidate/depth domain. Deliver this draft PR and
stop; P2 and holdout require the next user-reviewed task.
