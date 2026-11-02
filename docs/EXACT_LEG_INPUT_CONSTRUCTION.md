# Exact selected-leg input and grounded construction

## Result and boundary

**The input/discrete-trace component passes this construction gate. A real N64
comparator benchmark is still NO-GO.** Both fixed synthetic N64-width profiles
construct under the admitted guards, retaining64 literal Sites,110 actions and
51 slots. No real road table, full continuous physical model, independent
real-scale optimum or query-time result is produced. The existing compact
optimizer and its tiny guards remain unchanged; no production solver, physics,
candidate domain, road index, cache, seed or old numerical result is changed.

[exact_leg_construction_results.json](exact_leg_construction_results.json)
contains both source rounds, all four construction attempts, bootstrap errors
and conservative accounting. Final measurement source is
`5bf2fdeba8f31807830f8757099367f748c0f7bf`; the first source is
`5297ac4fdc6a6ab62a0d1ca8876c21d2fd0f5f7f`. Later delivery changes add validation guards, ownership/coverage regressions,
reporting and documentation. Historical timings remain tied to their measured
source; no full-width construction was repeated for the later guards.

## Independent input contract

`tools/exact_leg_table.py` imports no production optimizer, router or bound.
It accepts exact integer/rational fields under the current
`positive_time_node_path_edge_path_tie_v1` contract and rejects the legacy
binary64/length-tie declaration. JSON duplicate keys, duplicate/missing/extra
pairs, invalid exact types, malformed paths, contradictory edge identities,
invalid zero legs and directed reachability/time inconsistencies fail closed.
String/object containers cannot be silently iterated as candidate, effect or
path arrays. Inputs are copied into immutable Site, capability and Pair records. Lookup
construction requires a parser-validated object; the validation marker is not
a road certificate. `road_selection_certified` remains false, and a payload
cannot certify itself by setting that flag true.

Literal Site IDs, effect tags and candidate order remain separate from physical
anchors. Several Sites may share an anchor without becoming one action or Pi
entry. Logical origin/destination roles also remain separate when their textual
labels collide with Site IDs. Sources are origin plus Site anchors; targets are
Site anchors plus destination. Every ordered physical pair must be present,
including source/terminal and alias-zero pairs. Explicit unreachable is not
the same as absent. Coincident anchors require a reachable exact0/0 leg with
one path node and no edges. Directed reverse pairs are not inferred.

Selected time satisfies necessary directed triangle/reachability consistency
through exposed Site anchors; checking it costs O(S*T*M) and is included in
validation time. **Selected actual length is not a shortest-distance metric.**
It is never triangulated, minimized, rerouted or replaced. The tiny parity
fixture selects equal-time o-a-z of length20 over o-b-z of length2 because a<b;
the chosen edge-ID tuple selects oa1 over parallel oa2. The length triangle
through b fails and is correctly accepted.

These checks preserve exact input representation and necessary consistency.
They do not prove a real graph's path sums, shortest-time selection, canonical
ties, source provenance or unreachable cut. Real-road certification still
needs an independently validated graph/certificate. No such real table was
generated or certified here, and the component reports no planning optimum.

## Shared grounded arrays and finite-index proof

The table is stored once in finite Z3 T/L/Reach arrays. For source index p and
target index q, key=p*T+q is injective within the explicit integer bounds.
All legal keys are grounded from actual input records, including unreachable
records whose numeric storage is unused behind a false Reach guard. No missing
pair is filled with a default. Outside-array defaults cannot enter a transition:
the compiled active-leg and terminal guards require valid integer indices and
Reach. Bool, real and fractional public indices are rejected rather than coerced.

Action ranks1..A preserve canonical literal `(Site,effect)` order, with0 solely
inactive. Shared rank maps retain physical source and target indices separately,
plus charging/service tags. Source and target index spaces need not agree;
after an active action the next source is its **source-space** anchor index.
Inactive slots preserve the last active anchor, contribute zero drive and form
a suffix. Repeated C visits and C-S-C remain represented; a scheduled S/CS
consumes one pending activity without prohibiting later C visits. Terminal
lookup always starts at the last active source, or origin for an empty prefix.
All active slots still count toward H even for a zero-length alias leg.

Each trace has fresh selectors; separate traces do not accidentally share them.
Its parser-created ownership token prevents mixing a trace with another table,
even if two independently parsed payloads have identical bytes. Public
`from_dict` computes its own canonical digest and accepts no digest override;
`from_bytes` derives raw provenance from those bytes. Digests remain provenance,
not the authority for trace ownership. The
compiler applies each guard automatically. The lower-level `at` expression API
returns its guard together with time/length; consuming the terms without that
guard is not the compiled-trace contract. The fixed-sequence resolver performs
only substitution/simplification and explicitly reports neither physical
feasibility nor optimality.

There is no H<=N, H<=6 or H<=51 optimizer restriction. The API accepts any
nonnegative integer slot count subject to external resources.51 is the declared
construction test size from the preceding conditional-depth audit. Actual
solver integration must still derive its complete depth from an independently
replayed attained U and validated road inputs, preserve equality/open endpoints,
and retain branch-wide strict support and primary/joint-face attainment. This
component does not build the charging/energy/time families, the three charging
pieces or the full J/Q/H/Pi optimization. Literal Pi identities and history
bindings are preserved for that later integration; no optimum is asserted.

## Verification and observed construction

Fifteen local tests pass normally and under-OO. They cover current exact types,
legacy declarations, complete pair coverage, alias zero, endpoint/Site label
collision, directed unreachable, node/edge ties and actual length, immutable
input ownership, typed finite indices, repeated visits, empty prefix, pending
activity and inactive terminal behavior. A focused selected test adds explicit
out-of-domain action-rank and inactive-gap assignments in both modes. It does
not rerun a construction profile. Solver/SolverFor/Optimize are forbidden in
the tests; the isolated module import also blocks production optimizers.

The new tiny four-node/five-edge fixture is checked against the existing
independent exhaustive tiny-road selector. It is not an old optimization
cohort or a full-real-graph REF. Eight completed local suite invocations perform
eight such tiny road selections across initial/final/corrected source verification; none
calls a planning or SMT optimizer. Full-width probes record zero Solver,
SolverFor and Optimize constructor calls. Real road queries and real comparison
solves remain zero.

The initial two profiles completed at5297ac4. A subsequent API review added
strict index typing and parser-owned instances. The same two profiles were
predeclared for final-source verification without changing shape or values.
Both input hashes and AST counts remain the same; all four raw attempts are
preserved. They are separate source-version observations, not repetitions for
an average, a speed claim or a favorable selection.

Review correction source `8fc1374d7bb1759de445035f5fb34a1561396bb1` rejects
container coercion, caller-supplied digest provenance and cross-table traces.
Admission and reporting now require exactly the two frozen profile identities,
order and shapes; all four historical slots must complete before component
PASS. Empty, missing, duplicate, reordered or shrunken profiles, missing
historical receipts and mismatched worker shapes fail closed. These are input
and reporting repairs, not new construction observations.

A separate data-only sensitivity receipt reproduces old acceptance of all five
malformed containers and of a supplied digest, and the old empty-cohort PASS.
The corrected interfaces reject each. Both stored final synthetic inputs were
reparsed: hashes, every exact pair/path field and literal Site/action records
are unchanged. This check imports no Z3 and creates no lookup or trace. The
15-test suites additionally reject mixing different-cost tables with the same
literal actions, and identical-input tables with different owners. No profile,
real input, routing call or full-width construction was repeated for this fix.

| Final synthetic profile | Literal Sites/actions/slots | Pair records | Expression DAG nodes | Body CPU /wall s | Full-process-group peak RSS bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| Unique physical anchors | 64 /110 /51 | 4225 | 26943 | 1.167718 /1.279247 | 95092736 |
| Alias-heavy physical anchors | 64 /110 /51 | 1089 | 8191 | 0.359668 /0.398859 | 63619072 |

Body timers include fixture generation/validation, cold Z3 import, arrays,
trace, DAG traversal and literal projection; Python/bootstrap/source checks
outside that timer are charged by the supervisor. Full guarded command charges
are2.441656 and1.520765 CPU seconds, including process/controller/tail allowance.
RSS uses the maximum of child/native and process-group samples, including short
source-metadata subprocesses. These are component metrics on synthetic data,
and cold import means a fresh process/context; OS page caches were not flushed.
They are not solver time, a real N64 model benchmark, or evidence that query targets pass.
They are not compared numerically with the preceding nested-loop projections:
construction requests and unique DAG nodes are different quantities.

The single worker/thread is supervised with30CPU/55wall seconds per command,
1GiB RSS,3GiB starting host availability and an unchanged2GiB runtime host
guard. Final minimum host availability was4828594176 bytes. No guard or profile
was relaxed. All19 recorded child processes are confirmed terminal.

Two setup errors remain charged: default sandbox process monitoring raised
PermissionError, then the road-only Python environment lacked Z3. The first
child was checked absent before an approved own-process monitoring escalation;
the second returned an explicit import error. Switching to the already installed
pinned comparator environment required no new installation. These yielded no
completed semantic suite, and their logs/receipts remain outside Git. They were
not discarded or relabeled as infeasibility.

## Accounting and reproduction

The additional admission is400CPU seconds inside the original600 stage and
28800 total. It carries132.202735 stage and15139.701737741 global, keeping the
earlier120 precharge and every old receipt. New fixed development/report/control
precharge140 is retained. Nineteen commands, including both setup failures,
initial/final checks, focused symbolic validation and review correction, charge26.274330 with
controller/tail allowance. Thus new charge is **166.274330 /400**, combined
stage **298.477065 /600**, global **15305.976067741 /28800**, remaining
**13494.023932259**. No budget is reset or refunded. Preprocessing remains
652.040677976 /900. Ordinary software CI is separately prospectively reserved:
9000 capacity-CPU for full M5 and180 for the clean component CI, per admitted
invocation. Those allowances are not measured whole-job CPU.

Raw synthetic inputs, both preflights, all worker/controller logs and receipts,
controller versions and terminal PID verification remain in
`comparator-leg-construction-artifacts-v1` outside Git. Git contains generators,
config, source/test provenance and one joined result file, not synthetic tables
disguised as real datasets. Reproduction uses a fresh output path and the pinned
`comparison/requirements.txt`; run the external resource supervisor around the
following commands with the declared limits:

```sh
python -m unittest discover -s tests -p test_exact_leg_table.py
python -OO -m unittest discover -s tests -p test_exact_leg_table.py
python tools/probe_exact_leg_table.py preflight --output /new/run/preflight.json
python tools/probe_exact_leg_table.py run --probe unique64 \
  --preflight /new/run/preflight.json --output /new/run/unique64
python tools/probe_exact_leg_table.py run --probe aliases64 \
  --preflight /new/run/preflight.json --output /new/run/aliases64
```

The source/config check is only consistency within one declared run. New source
versions may have new preflights and receipts; it is not a source-file/hash lock.
Existing outputs are inspected rather than overwritten or blindly restarted.

## Next bounded research step

The table/trace representation is now usable for a later independent physical
adapter. The next useful step is to connect it to the existing strict-support
continuous formulation and independently replay supplied upper witnesses on
certified tiny fixtures, preserving full relevant depth,3 curve pieces, strict
positive charges, CS overlap, repeated visits and attained/unattained full-key
semantics. Real selected-leg generation/certification and any real comparator
measurement need their own frozen admission with all costs included. None is
authorized or launched just because this component constructed successfully.

Original performance/hierarchy claims, larger/full real domains, real four-
positive-charge evidence, independent real-scale comparison, design freeze and
new-OD holdout remain unmet. The original taskbook is not complete. Existing
DEV groups and synthetic construction fixtures are not holdout evidence.
