# Full N64 independent-comparator input/proof audit

## Decision

**NO-GO for a real N64 comparator benchmark with the current implementation.**
This is not a proof that an independent N64 formulation is impossible. A finite
exact slot formulation exists, and a shared finite selected-leg lookup avoids
unnecessary per-slot multiplication of its input table. Its full-instance
implementation and practical resource behavior remain unverified. The next
useful work is that input/lookup implementation and construction verification,
not a solver timing batch or another main-algorithm optimization.

No real road query, SMT check, selected-leg table generation, historical solve
rerun, new data, physics change, main experiment or holdout ran in this gate.
The new audit tool imports neither HiRoute nor Z3. It streams the existing road
file only to verify its identity; it does not parse/load a road graph or index.
All48 historical query cells /96 method slots remain in the denominator.

## Frozen inspection and measured structural facts

Base main is `bbbb98ff89ff0ea76afe83898a7beb874e899789`. The inspection producer
is `91fcd7cc8d4d4f1d9a501e30c82653e54ff03adc`; subsequent delivery changes add
the actual report and documentation. Input/config/manifest hashes, the original
domain fingerprints and the complete conditional per-cell counts are in
[comparator_input_audit_results.json](comparator_input_audit_results.json).
The historical results SHA is
`cecab6da2fd47df131106025688cc5b70cbd558c13c6cfa74cbf804ac66a7d2c`.
The old preparation, results, raw witnesses and all previous budget records are
unchanged. Published JSON adds producer identity, raw-audit hash and explicitly
derived min/max summaries; the raw audit remains outside Git.

| Quantity | Observed or conditional count |
| --- | ---: |
| Query cells / historical method slots | 48 /96 |
| Available / unavailable N64 cells | 44 /4 |
| Distinct available domain fingerprints | 22 |
| Site actions per available cell | 64–110 |
| Charging-curve segments | 3 |
| Basic conditional relevant depth | 25–51 |
| After direct-time subtraction | 4–23 |
| After direct-time and pending-activity subtraction | 2–20 |
| Available cells still requiring depth >6 after both subtractions | 21 /44 |
| Directed physical pair records per domain | 4225 |
| Of those, zero diagonal / nontrivial directed pairs | 64 /4161 |

Every available cell has a historical physically verified feasible witness.
Those values are used **only for conditional sizing**, not as optimum oracles.
This audit does not independently replay those upper witnesses or certify the
historical direct-time observations. It therefore makes no new feasibility,
depth-admission or optimality claim for an external solver. A future comparator
must independently replay its actual supplied witness and certify the road-time
input before applying these floors. Missing a witness remains UNKNOWN.

The current [compact solver](../comparison/compact_smt.py) rejects N>2,
curve segments>2 and complete basic depth>6. Its
[tiny road selector](../comparison/tiny_smt.py) additionally requires at most6
road nodes /12 edges and enumerates simple road paths. The frozen real graph
has millions of vertices; that routine must never be used to export its pairs.
The real snapshot has an empty `directed_edges` field because routing lives in
an external provider, so passing that metadata snapshot directly is also not a
valid bridge to the current tiny-road interface.

Historical router metadata reports 2986695 nodes and5900232 directed edges;
the file hash was verified, not those counts independently recomputed. A
complete per-target reverse-tree approach for65 targets has worst-case
383515080 edge-relaxation opportunities, plus queue/path work. This is a
complexity illustration, not measured routing time or a promised upper cost.
Retaining all65 potential arrays would require194135175 scalar entries;
processing one target at a time avoids that residency, not its computation.
Construction, verification, path storage and cold graph/index residency must
all be charged in a later admitted experiment. The4225-row count is not free
routing and is not a memory/runtime measurement.

## Exact selected-leg input contract

One input record is the result of a directed **selected** road leg, never an
edge in a smaller graph to be rerouted. For each ordered pair it must preserve:

* immutable graph identity, literal physical anchors and exact rational time;
* the actual length on that selected path, not shortest-road-distance length;
* reachable versus unreachable, with no invented zero/unreachable substitution;
* the full node-tuple then edge-ID-tuple tie contract after minimum time;
* a verifiable path or selection certificate and its provenance;
* an explicit zero-time/zero-length/empty-edge path for coincident anchors.

Keep Site identity/action capability/Pi order separate from physical anchors.
Several Sites can share an anchor without becoming one action or history.
The frozen domains happen to have64 distinct Site anchors and distinct
endpoints. Their sources are origin plus64 Sites, and targets are64 Sites plus
destination:65*65=4225 records. The64 diagonal pairs need no road search.
Aliases can reduce physical pair count without reducing the Site action domain.
The terminal leg from the last active stop, and the origin-to-destination leg
for an empty prefix, are mandatory. Reverse legs are independent directed data.

The existing [old real REF adapter](../reference/src/hiroute_ref/real_input.py)
is **not compatible**: its `binary64_totals_as_exact_rationals_v1` preserves
rounded binary64 totals, and its tie policy is
`min_time_then_actual_length_then_first_discovery`. The current contract is
`positive_time_node_path_edge_path_tie_v1` over exact input sums. For example,
equal-time o-a-z (length20) and o-b-z (length2), a<b, select o-a-z under the
current node-tuple rule, but o-b-z under a length tie break. A hash or a wrapper
renaming the old table cannot repair either semantic difference. That legacy
adapter and its historical evidence remain unchanged.

An independent exact reverse-Dijkstra producer is possible without simple-path
enumeration. Positive time makes its shortest-time DAG strictly decreasing.
A certificate can retain target potential p(t)=0, Bellman inequalities
`p(u)<=w(u,v)+p(v)`, and a source path whose exact time equals p(source).
These establish a shortest time. Among equality arcs, choose the smallest next
node, then the smallest parallel edge ID; strict decrease and recursion give
the canonical full node/edge tuples. Sum length only on that path. Unreachable
claims additionally need a validated reverse-reachable cut, not merely an
absent record. This describes a proof/implementation contract; this gate did
not produce such certificates. Every legally queryable pair must be covered.

## Complete relevant depth, including equalities and repeated visits

Let U be the **independently replayed attained** primary cost of a feasible
plan, h>0 the physical overhead and lambda>=0 the stop penalty. With H stops,
every stop consumes at least h elapsed time. For S/CS, the completion equation
also consumes at least its mandatory duration D once, even when charging
overlaps it. Driving/waiting/charging are nonnegative. Concatenating selected
road legs is a valid directed OD walk, so its drive time is at least the exact
shortest direct road time tau_OD. Hence

`J >= tau_OD + H*(h+lambda) + pending*D`.

Consequently all actual plans with J<=U satisfy

`H <= floor((U-tau_OD-pending*D)/(h+lambda))`.

Dropping tau or D gives the weaker floors in the table. None uses a HiRoute
relaxation as an oracle: this is a direct inequality from the independently
specified physical and road contracts. The audit's use of historical values
is explicitly conditional on later certification. The subtraction is of road
**time**, not selected-path length or an unproved distance triangle inequality.
The formula does not cap H by N,6 or the returned witness's stop count. Repeated
C visits, including before/after activity and at the same physical anchor, are
allowed. S/CS consumes the single pending activity once; it does not prohibit
later C visits. Equality at the integer floor is retained. An attained U is
not interchangeable with an open infimum. There is no finite U-based admission
certificate when no feasible witness is available.

If the true primary infimum is below U, every sufficiently close feasible
plan has J<=U and is retained by this depth. If it equals U, the supplied
feasible U proves primary attainment, and all primary/joint faces at U remain.
This justifies full relevant-depth completeness, including unattained limits
below U. It never licenses silently replacing an excessive floor by6.

## Formulation completeness and avoidable input expansion

The existing finite selectors can represent all legal histories through H:
an action (inactive0 or a canonical Site/effect), charging segments and the
active max expression. Inactive slots form a suffix; they preserve physical
state. Add the actual terminal leg and reserve test after the last active slot.
Increasing the finite curve segment set is mathematically compatible with the
same continuous equations, provided coverage/continuity and positive slopes
are validated. The current3-segment real curve meets that physical contract;
the prototype still rejects it, and no optimizer guard was lifted here.

For each fixed selector vector, both continuous copies remain affine rational
polyhedra. Keep branch-wide strict-support y before optimizing the closure of
x. Actual q>0 is mandatory for attainment tests. At primary value j, support
for secondary minimization must itself have J(y)=j; otherwise an empty primary
fiber can invent Q=0. Test actual joint attainment, then minimize H and literal
Pi only on the attained joint face. Initial waiting, service window equality,
CS max pieces, curve-boundary equality and strict/open endpoints must survive.
These are the [existing proof obligations](COMPACT_COMPARATOR_GATE.md), not
new real-scale verification. Do not globally close the disjunction or use an
open infimum as an incumbent.

With N Sites, A legal actions, K curve pieces and H complete slots, current
`Encoding.__init__` builds H*(N+1)*A movement-pair predicates and at most twice
that many numeric movement ITE requests, plus4*K*H curve ITE requests across
the two state copies. These are syntactic construction components, **not**
unique AST-node counts or measured solve/memory cost. Unreachable cells can
reduce the numeric ITE count. Actual full-frame ranges are:

| Conditional depth used | Movement predicates | Numeric movement ITE upper count |
| --- | ---: | ---: |
| Basic | 104000–258570 | 208000–517140 |
| Subtract direct time | 16640–117260 | 33280–234520 |
| Subtract direct time and pending duration | 11180–101400 | 22360–202800 |

A shared finite lookup can instead declare exact T(p,q), L(p,q), Reach(p,q)
values for every legal physical pair once, with explicit finite index domains.
Each active slot and the terminal then use that pair directly: O(P+H) lookup
data/applications, P=4225 here. Site/effect selectors and aliases remain separate.
Inactive slots use zero movement; unreachable active/terminal pairs are forbidden.
Grounding every legal pair prevents a free uninterpreted value from inventing
a leg. Fixing selectors fixes each lookup to an input rational, so the same
fiber-wise strict-support proof continues to apply. Arrays or finite grounded
functions are implementation choices; neither may reroute the pair table.
This avoids H*A duplication of table data. It does **not** prove Z3 search is
fast, smaller in resident memory, or complete within120 seconds. No AST build
or solver benchmark of this proposed lookup was performed here.

## Verification, resources and reproduction

Eight focused tests pass normally and under-OO: equality/empty prefix, no-U,
exact inputs, repeated visits without an N cap, alias/direction/terminal pair
coverage,196 tiny time-history inequalities including CS overlap, unavailable
denominator, duplicate cells and changed inputs. An import blocker verifies
the auditor calls neither internal nor external solvers. The dedicated CI
wrapper is also locally exercised. No existing tiny or real solver cohort is
rerun to manufacture a parity result.

The prospective research cap is600 inside28800, starting15007.499002741.
Eight metered commands including inspection, hashing, tests and reporting cost
8.873910 conservatively (child/controller samples plus per-command tails).
The full120 development/control/documentation precharge is retained. Thus
this gate charges **128.873910 /600**, cumulative **15136.372912741 /28800**,
remaining **13663.627087259**. The command ledger and raw logs remain in
`comparator-input-audit-artifacts-v1` outside Git. Future ordinary software CI
is separately prospectively reserved:9000 capacity-CPU for full M5 and120 for
the pure audit CI. These are not whole-job measured CPU. Prior CI charges are
not refunded. Preprocessing remains652.040677976 /900. No resource cap expands.

```sh
python tools/audit_comparator_input.py \
  --preparation /path/to/original/n64-dev-stage-artifacts-v3/preparation.json \
  --results docs/n64_coverage_stage_results.json --output /new/path/audit.json
python -m unittest discover -s tests -p test_comparator_input_audit.py
python -OO -m unittest discover -s tests -p test_comparator_input_audit.py
```

The preparation references the preserved external input/config/manifest files;
the auditor verifies their hashes and refuses output overwrite. Per-cell raw
counts reproduce directly. Published min/max spans are reductions of those
counts, not new runs or performance observations. The JSON names every
uncertified quantity rather than presenting a conditional floor as a certificate.

## Next bounded action and original acceptance boundary

The concrete next step is an exact selected-leg input/alias validator plus a
shared finite lookup implementation, with tiny directed tie, unreachable,
repeated C-S-C, equality, open primary/joint-face and full-K regressions. Verify
complete N64-width/H<=51 construction under a declared resource guard before
any real optimizer run. The current600 gate has471.126090 unspent; that is
headroom, not a new solver-row authorization or a budget reset. Any continuation
must carry its existing ledger and source identities and reserve before work.
Real complete-table generation/certification and a fair real comparison need
a separate frozen admission with construction, witness/replay and search cost
included. No<=1500 comparison has been launched or charged as a result here.

Original performance, hierarchy advantage, larger/full qualified domains,
four-positive-charge evidence, independent real-scale comparison, final design
freeze and a new-OD holdout remain incomplete. The existing12 DEV OD groups
cannot become holdout. This gate supplies an honest route to the missing
comparator input, not original taskbook completion or a research success claim.
