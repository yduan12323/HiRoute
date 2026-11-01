# Independent exact comparator: bounded availability and semantic gate

## Result and scope

**GO for exact-solver availability and tiny common-model semantics. Not ready
for a real-domain external benchmark.** The independent rational linear model
matches all12 frozen analytic cases and both Strong/Scale on those same finite
domains. There are8 attained optima,1 primary-unattained result,1 secondary-
unattained result and2 infeasible results. All8 external optimal witnesses and
all16 attained Core witnesses pass the separate concrete Fraction replay.
The normal and `-OO` runs agree. These are tiny correctness fixtures, not real
queries or evidence for a runtime advantage.

This gate starts at merged main
`60866a55e52dae35ba56f9f4fcfceee7c4ff80b2` (PR35). The production solver,
routing, seed, physical parameters, candidate data and historical results are
unchanged. Main35's existing full CI is monitored separately; no duplicate main
run is requested. New code is under `comparison/`, outside the installed
HiRoute package. There is no new Ours architecture or real-data solve.

## Solver availability and provenance

Initial inspection found no SCIP, SoPlex or Z3 installation. SciPy was available,
but its floating LP interface was not used as an exact comparator. The selected
dependency is **z3-solver4.13.4.0**, backend4.13.4, installed into an isolated
temporary environment from its [official PyPI release](https://pypi.org/project/z3-solver/4.13.4.0/).
Its project metadata links the Z3Prover repository and declares MIT licensing;
the [upstream license](https://github.com/Z3Prover/z3/blob/master/LICENSE.txt)
permits use and redistribution subject to its notice. This pinned older release
is not presented as the latest version. Its wheels have no PyPI provenance
attestation; hash pinning checks download integrity, not a reproducible-build
or upstream-signature guarantee.

The official [arithmetic guide](https://microsoft.github.io/z3guide/docs/theories/Arithmetic/)
distinguishes mathematical Reals from floating-point sorts. The model uses
quantifier-free **linear real arithmetic** with rational coefficients, not
floating-point, nonlinear or transcendental constraints. The official
[optimization guide](https://microsoft.github.io/z3guide/docs/optimization/arithmeticaloptimization/)
also distinguishes strict-bound infinitesimals from attained values. Here we
optimize closed linear branches and test strict faces separately; no printed
sample is mistaken for an attained infimum.

Only official binary wheels were installed, without source compilation,
accounts, credentials or paid licenses. The checked wheel hashes are:

| Platform | SHA256 |
| --- | --- |
| macOS13+ arm64 | `39ba75b867d6afadabc4812b999c9d96656da07d152510452e71ae9374e98926` |
| manylinux2014 x86_64 | `2fb8a857adf1064f89581c424fd729ee3e8bad95f4ebf0fb4c1210f65b831f37` |

`comparison/requirements.txt` pins both platform wheels. Registry metadata and
the installation receipt are retained externally. The36.9MB local wheel took
169.475s wall time but3.479 conservatively charged CPU seconds; elapsed download
time is not CPU. Preflight found about43GiB free disk and several GiB reclaimable
memory. No map or charging-data preparation occurred.

## Independent model and exactness argument

`comparison/tiny_smt.py` imports only the standard library and Z3. It neither
imports HiRoute/REF nor calls their relaxations, witnesses, road provider or
optimization results. A focused test blocks every `hiroute*` import while
independently solving the analytic cases. `comparison/run_gate.py` finishes and
persists **all independent results before importing Core** for parity checks.
Only the input snapshot is passed into the independent solver; expected analytic
answers and later Core results are never optimization inputs.

The supported domain is explicit: at most2 Sites,6 road nodes,12 directed edges,
2 charging segments and2 stops; at most128 selected road paths per pair and128
linear branches per case. Larger inputs are rejected, not approximately solved.
Repeated Sites are permitted and service occurs once. The finite depth belongs
to the declared common test domain, not a hidden restriction on production
Scale. No large-domain scalability is inferred from these limits.

Road inputs have positive time and length. An independent exhaustive simple-
path enumerator is complete for shortest-time paths on these tiny graphs:
removing a cycle strictly reduces time. It chooses minimum time, then the full
node tuple, then the full edge-ID tuple, and sums **that selected path's length**.
The test with node and parallel-edge ties deliberately selects length12 rather
than the shortest-length alternative2. Reverse unreachability is retained. The
resulting leg table is used only for the specified consecutive physical stops;
it is not rerouted as an ordinary graph with unrecorded waypoints.

For each legal plan, independent constraints specify initial waiting `w>=0`,
arrival energy/time, floor/capacity, destination reserve and the exact effects:

* C: `t_out=t_arr+h+Phi(E_out)-Phi(E_in)`, with `E_out>E_in`.
* S: `t_arr<=b-h`, unchanged energy,
  `t_out=max(a+D,t_arr+h+D)`.
* CS: `t_arr<=b-h`, strict positive charge,
  `t_out=max(a+D,t_arr+h+D,t_arr+h+Phi(E_out)-Phi(E_in))`.

The charging curve is continuous piecewise affine. Every incoming/outgoing
segment pair and every maximizing time expression is enumerated. Chosen maxima
have both equality to the selected expression and dominance over every other
expression. Thus each branch is a closed linear polyhedron P after relaxing
only charge positivity to `q>=0`. Boundary overlaps between branches are benign
for minimum/attainment selection; they are not claimed to form a disjoint
partition. Empty physical termination is considered when service is complete;
an infeasible terminal does not remove longer plans.

For a finite set of active charges, `P and all(q_i>0)` is nonempty exactly when
the common-epsilon formulation can attain a positive epsilon. Native strict
LRA satisfiability therefore implements the reviewed branch-wide feasibility
gate without inventing a minimum charge. **This test precedes closure
optimization.** If it fails, the branch is discarded completely. If it succeeds,
convex combination with one strict point proves `closure(P_strict)=P`.

The minimum closed J is then a valid primary infimum. Finite linear optima on
these polyhedra are rational and attained in the closure; time is bounded below,
and `J=t_final-t0+lambda*H` is bounded below. The implementation requires exact
rational matching lower/upper objective bounds, a feasible equality face and
an UNSAT exact query for any strictly better point. Unknown, infinite or
nonrational results stop the gate; no tolerance substitutes for equality.

Across branches, select minimum J. Test strict feasibility on that J face
before allowing it to contribute to Q optimization. If none attain J, return
`primary_unattained`, without a complete key. For primary-attaining branches,
the same convex argument on the J face validates the closed minimum of
`Q=sum(q_i)`. Test strict feasibility on the joint J/Q face. If no branch attains
Q, return `secondary_unattained`; otherwise choose minimum H and Pi among jointly
attained faces. This handles both kinds of unattainment and preserves all four
coordinates, rather than using a closed zero-charge incumbent.

The Python Fraction replayer independently executes the physical equations from
snapshot, plan, concrete charges and initial wait, checking capability, strict
charge, energy, activity and final reserve, and recomputing the full key. It
does not evaluate SMT expressions or call the production replayer.

## Analytic cases and observed parity

The12-case input and analytic answers were fixed before the first solve in
`comparison/cases.json`; they were not changed to fit solver outputs. The
cohort performs41 linear branches and133 exact SMT/optimization checks. All24
Strong/Scale comparisons agree with the independent result:

| Frozen case | Independent analytic result | Strong /Scale parity |
| --- | --- | --- |
| Empty prefix | attained J1,Q0,H0 | match /match |
| One required charge | attained J16,Q3,H1 | match /match |
| Open primary endpoint | primary infimum13, unattained | match /match |
| Activity-overlap charging endpoint | J17 attained, Q infimum0 unattained | match /match |
| Equal primary S/CS alternatives | attained J17,Q0,H1, S | match /match |
| Reversed candidate order | attained J14,Q0,H1, lexicographic Site a | match /match |
| Temporal-energy equality | attained J29,Q3,H2 | match /match |
| Deadline earlier by1/100 | infeasible | match /match |
| Time shifts +100 and -100 (two cells) | same attained J29,Q3,H2 | match /match |
| Piecewise charging | attained J18,Q3,H1 | match /match |
| Full battery, CS-only, zero consumption | strictly infeasible despite feasible closure | match /match |

The primary-open fixture uses the canonical fast direct leg with excessive
energy; treating selected legs as a freely reroutable graph would incorrectly
allow a zero-stop indirect route. Its positive charge can tend to zero but
cannot equal zero. In the secondary-open fixture, activity duration hides small
positive charging time, so J is attained while Q approaches zero. Adding a legal
S action correctly restores joint attainment on that same J/Q face.

These examples also admit independent completeness arguments. With h1 and
lambda10, the exhibited feasible J values give safe depth floors0,1 or2.
For the primary-open fixture, charge1/2 gives feasible J27/2 and depth floor1.
The temporal case requires total charge3 and arrives at service no earlier than
6; deadline b7 is equality, whereas b699/100 permits arrival only through599/100.
Splitting charge at the sole charger only adds overhead, and the directed graph
does not permit returning there after service. The full-battery case has no
legal first positive-charge action at all. These tiny analytic arguments do not
prove completeness of arbitrary capped domains.

Seven focused unit tests pass normally and under `-OO`. Besides the12 analytic
subcases, they test node/edge ties, directionality, replay rejection, resource/
input limits, integer-versus-rational numeral conversion, and the strict-empty
closure trap. A later focused H-tie fixture, specified before its first solve,
uses an activity-waiting plateau: CS and C-then-S have identical J102/Q3; the
model correctly chooses the one-stop CS plan. This does not alter the frozen
12-cell cohort. All checks use active unittest assertions in optimized Python.

The initial run retained10 adapter errors: Z3 returned integral numerals for
closed objective bounds, which the first adapter accepted only as RatNum.
Both infeasible cases were already correct. The adapter now accepts exact IntNum
as Fraction too; a focused regression covers both numeral types. This was an
interface bug, not a mathematical counterexample or changed expected result.
Failed receipts and SMT query files remain outside Git. A compact result summary
is [independent_comparator_gate_results.json](independent_comparator_gate_results.json).

## Budget, verification and reproduction

The whole gate conservatively charges its complete **600CPU-second allocation**,
not600 plus setup, failures, reporting or CI. Original carry becomes
**11905.649970329 /28800**, leaving16894.350029671. Preprocessing remains
**652.040677976 /900**. No real-data row, map work, source acquisition beyond the
official software wheel, main experiment or holdout ran.

Reservations within600 are:180 local dependency/tests,180 dedicated CI,
120 development/controller/report/verification,120 for promptly cancelling the
automatically triggered unchanged legacy M5 workflow at PR startup. Local
commands have cumulative child-CPU receipts and per-process CPU limits; their
observed charged total before delivery was below10 seconds, including the
failed run and installation. The full600 is retained conservatively rather than
reclaimed for an extra experiment.

The dedicated isolated CI executes only these new model/parity/replay checks
in normal and optimized Python. Its Python controller has a20CPU-second hard
limit and child processes15 each, with cumulative admission and receipts.
The environment/setup and short utility subprocess allowances are conservative
reservations, not separate kernel hardlimits. Binary-only installation prevents
unbounded source builds. Started/final records are retained; an unexpected
failure stops subsequent commands. No resource-limited result counts as optimal.

Because production source is unchanged, main35's full installed-wheel CI supplies
the production regression evidence. This PR's automatic broad legacy M5 run is
cancelled promptly to preserve the600 gate cap; it is **not called successful**.
The bounded comparator CI and the existing main CI have separate recorded IDs
and terminal statuses. No workflow/source hashes or fixed file-count locks are
introduced to inhibit normal development.

Reproduce the model in a fresh Python3.11 environment:

```sh
python -m pip install --require-hashes --only-binary=:all: --no-deps \
  --index-url https://pypi.org/simple -r comparison/requirements.txt
python -m unittest discover -s comparison -p test_gate.py
PYTHONPATH=src python comparison/run_gate.py --output /tmp/tiny-comparator-run
```

Use the budget wrapper for bounded execution; CI uses
`comparison/ci_budget.py`. Raw results and exact SMT queries are written outside
the repository. The supplied summary is evidence from one tiny gate, not a
performance table or an independent formal proof certificate.

## Remaining independence and completion gaps

Z3 is an external exact-arithmetic backend, but optimization and the strictly-
better UNSAT check use the same solver implementation. No separately verified
Farkas/VIPR or proof-checker certificate is produced. The Fraction replay proves
feasibility of concrete returned plans, not optimality. Saved SMT inputs enable
audit/reproduction; they do not remove trust in Z3. Road selection is independently
implemented relative to HiRoute, while the model and its replayer share that
tiny-road selector; analytic tie fixtures and Core parity are additional checks,
not a second formally verified routing engine.

Finite plan/segment/max enumeration is deliberately unsuitable for N64 with a
large relevant depth. No real common-domain external comparison is ready, and
increasing these guards blindly would be unjustified. A further comparator
encoding/design gate must preserve the strict-branch/face proof before any
bounded real comparison. This is external-comparison engineering, not permission
to change the validated Ours architecture.

Availability and tiny semantic parity can now be marked complete. Real external
comparison, separated/sequential planning value, larger/full domains, true four-
charge evidence, original performance targets and frozen independent holdout
remain unfinished. The next useful work is to specify a scalable independent
encoding under a new bounded design, or progress the already proposed planning-
value baseline definitions. No additional experiment is launched by this report.
