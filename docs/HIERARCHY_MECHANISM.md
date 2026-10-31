# Hierarchy mechanism comparison — bounded development result

2026-10-31, fresh `dot/hierarchy-mechanism-comparison` checkout from main
`423c7b4dc8b161f62bef55d6e7d8679b0c1fd800`. This is a controlled development
comparison, not holdout, external SOTA, real-road or deployment evidence.

## Structural expectation and implementation

For the same prefix, nonempty action set A and comparison threshold U,
`L(A)=min(l(a) for a in A) > U` iff every `l(a)>U`. The excluded action set is
therefore the same as singleton testing. This assumes the identical reachable
members, legal effects, `_next_stop_bound` and threshold. Missing inbound/onward
legs use the existing reachability treatment. Region grouping does not strengthen
this bound. Dynamic searches need not match unless discovery order is controlled.

`flat_bb` evaluates zero stop first, constructs the same legal actions, computes
singleton bounds once per prefix, sorts by `(bound,effect,leaf_priority)`, and
recursively visits retained actions. It never calls `_build_regions`, creates a
Region or delegates to HIER. A terminal-infeasible prefix still expands. All three
methods share time-cut v2, analytic C, generic CS, exact prefix reuse, selected-leg,
full K and numerical/witness semantics. No seed, REF-derived initial bound, routing
prewarm, Core/union/reducer/cache-key change or N/H expansion was introduced.

The comparison threshold is the primary infimum of evaluated **nonempty** terminal
families, including unattained ones. It is not necessarily an executable incumbent.
For `l>infimum`, that family contains an actual member strictly below l; hence
strict pruning is safe. Equality is retained for attainment/secondary ordering.
First attained incumbent and infimal threshold updates are recorded separately.

HIER's existing heap compares bound, depth, effect and Region ID. Ancestor IDs
are smaller than descendant IDs and their bounds cannot exceed a descendant's.
Consequently its emitted leaf priority is `(bound,effect,leaf_ID)`; arithmetic
IDs reproduce this without constructing a tree, including uneven N. Tests check
N=1…8 and C/S/CS ties. Two untimed comparisons, M03/M04, found identical complete
terminal traces and threshold history: first attained at attempt 2, s0-C, one
threshold update (5/6 respectively), 3/17 terminal evaluations. No other explanatory
trace or profiler was run. FLAT remains breadth-first enumeration; comparisons
against it include ordering and reachability strategy, not a pure bound ablation.
Flat-BB carries elapsed route time recursively; current HIER also pays for its
existing prefix-route recomputation. Runtime differences include that cost.

## Fixed suite and execution limits

[Configuration](../configs/diagnostics/hierarchy_mechanism.json) contains all eight
explicit rational inputs. M02/M03 use a length-1+1 short branch (time 1+1) and fixed
detours with each leg time 5+i. M04 has eight equal branches, penalty 2, and equal
second-stop bounds. M05/M06 have three length-2 corridor legs, initial=capacity=2,
two charging layers and alternative stations; M06 adds four fixed long detours.
No single charge can bridge the two remaining length-2 legs, and the second layer
cannot be reached on initial energy: at least two positive charges are necessary.
M08 applies the predetermined permutation `[5,2,7,0,6,1,4,3]` to M03. Its positive
branch times are distinct, giving unique fastest physical road paths. The optimal
stop maps s0→s5; J/Q/H are unchanged. No full-optimum Pi tie occurs here; a changed
Pi string under renaming is not itself a physical or mathematical disagreement.

**Two configuration mistakes limit completion of the requested suite.** M01 kept
P07's graph/curve/N/H but inherited penalty 1 instead of P07's 0 (J=17 rather than
16); it is a variant control, not exact P07 reuse. M07 inherited capacity 10 while
its charge primitive covers only [0,5]. All nine M07 attempts failed independent
replay's input validation (`Charging primitive must cover the full battery domain`).
No M07 math result or timing is accepted. These mistakes were missed in preflight.
Physical parameters were not changed after observing results; only descriptive
labels were corrected. No case was substituted or rerun to improve outcomes.

Before timing, 59 focused unittests passed (final run 2.278 s; earlier development
runs included). Coverage includes zero stop, unreachable/infeasible, required two
charges and depth cap, C/S/CS and completed schedule, equal-primary better Q,
strict bound equality retention, primary/secondary unattainment, duplicate Site
prefixes and immutable witness ancestry, ±3600 time translation, and timeout
publication as unknown. Attained regression witnesses were physically replayed.
A timing-wrapper metrics forwarding defect was caught and fixed during development.
The new test is included in the existing isolated-wheel CI cohort and collection
manifest. No local numerical verification ran concurrently with timing.

MacOS 27.2 arm64, Python 3.11.15, NumPy 2.4.6, SciPy 1.17.1, psutil 7.2.2;
one fresh process per row and one numerical worker, thread environment fixed to 1.
Each case used orders flat/flat_bb/hier, flat_bb/hier/flat, hier/flat/flat_bb across
three repetitions. Repetitions are order controls, not independent problems.
Existing `run_supervised` and its macOS adapter enforced 120 s production / 60 s REF,
4 GiB sampled RSS and 2 GiB host available-memory floor; 50 ms sampling is
observational, not a hard aggregate kernel memory cap. Build/initialization are
inside total solve; startup/load/replay are included in supervised wall.

The first M02 REF worker was launched, then sandbox process-list observation
failed; its temporary output was lost. An authorized process check confirmed no
worker remained. It was **not retried**, and its mathematical outcome stays
`REF_RESULT_UNAVAILABLE`. The full 60 s limit was conservatively charged.
The subsequent supervisor run used process observation permission and a preflight
check before launching workers. Development numerical CPU measured under 10 s;
10 s was charged conservatively. Including that 10 s, the lost REF's 60 s and
remaining observed workers, total charged CPU was 89.188204 s of this task's new
7200 s budget. Peak sampled RSS was 80,625,664 bytes; minimum sampled host available
memory was 3,613,884,416 bytes. No profiler, duplicate matrix or leftover worker.

## Outcomes and work

[One result table](HIERARCHY_MECHANISM.jsonl) retains exactly **72 normal attempts**:
63 complete, nine M07 ERROR/unknown; plus M05 completed REF and M02 unavailable REF
records. The seven completed cases agree in status and full K across all methods
and repetitions; all 63 attained outputs passed independent physical replay.
Only **M05** has a new completed full independent REF optimization, agreeing in K
and two positive charges. M01/M02/M03/M04/M06/M08 have parity/replay only; M07 is
unverified. Existing frozen unattainment cases reuse their original expected
results, not a claim of new REF certification for these mechanism inputs.

Median solve wall milliseconds (three descriptive observations each):

| Case | N/H | K=(J,Q,H,Pi) or outcome | FLAT ms | Flat-BB ms | HIER ms |
|---|---:|---|---:|---:|---:|
| M01 | 8/3 | (17,6,1,c1-C) | 83.984 | 82.637 | 85.836 |
| M02 | 4/2 | (5,1,1,s0-C) | 4.192 | 1.522 | 1.806 |
| M03 | 8/2 | (5,1,1,s0-C) | 8.904 | 3.430 | 2.298 |
| M04 | 8/2 | (6,1,1,s0-C) | 9.100 | 8.694 | 9.401 |
| M05 | 4/3 | (11,4,2,a-C;b-C) | 6.346 | 6.001 | 6.541 |
| M06 | 8/3 | (11,4,2,a-C;b-C) | 17.985 | 7.643 | 8.414 |
| M07 | 2/3 | ERROR / unknown | — | — | — |
| M08 | 8/2 | (5,1,1,s5-C) | 8.980 | 2.159 | 2.404 |

Actual counts, constant over repetitions. Triples are FLAT / Flat-BB / HIER;
pairs are Flat-BB / HIER. Terminal includes evaluated empty/infeasible families.

| Case | attempted plans | completed terminals | C calls | bound-pruned next actions | singleton bound calls | HIER bound member visits / unreachable | HIER coverage scans |
|---|---:|---:|---:|---:|---:|---:|---:|
| M01 | 585 / 165 / 165 | 165 / 165 / 165 | 109 / 109 / 109 | 0/0 | 164/656 | 1148/492 | 4164 |
| M02 | 21 / 3 / 3 | 9 / 3 / 3 | 8 / 2 / 2 | 3/3 | 5/13 | 20/7 | 76 |
| M03 | 73 / 3 / 3 | 17 / 3 / 3 | 16 / 2 / 2 | 7/7 | 9/26 | 44/18 | 164 |
| M04 | 73 / 17 / 17 | 17 / 17 / 17 | 16 / 16 / 16 | 0/0 | 16/64 | 208/144 | 768 |
| M05 | 85 / 25 / 25 | 25 / 25 / 25 | 18 / 18 / 18 | 0/0 | 24/72 | 140/68 | 524 |
| M06 | 585 / 25 / 25 | 49 / 25 / 25 | 42 / 18 / 18 | 4/4 | 28/104 | 296/192 | 1096 |
| M08 | 73 / 3 / 3 | 17 / 3 / 3 | 16 / 2 / 2 | 7/7 | 9/26 | 44/18 | 164 |

`search_metrics` records explicit action construction, coverage membership passes,
all Region bound scans (including unreachable), internal-member subsets, actual
Region builds/visits/refinements/prunes, skipped reachability/bound actions and
equality-retained nodes. Depth counts are prefixes stopped at the cap; no unvisited
subtree was enumerated to invent an avoided-plan count. HIER's 15/7 built nodes
come from its actual full N=8/4 tree, including initialization. Flat-BB builds zero.
Coverage scans include root filtering, partition membership checks, child filtering
and coverage checks. Set membership/hash internals and sorting are timed, not
represented as additional synthetic member visits. Depth-cap prefixes are not
expanded merely for statistics. FLAT discovers unreachable plans at compilation;
its zero `unreachable_actions` does not mean none of its attempted plans failed.

Prefix cache hits/misses, propagated PWA piece output counts, C/CS calls and actual
selected-leg calls/misses are in every complete row. No CS claim is made from the
main table because M07 failed; CS/schedule correctness is covered by regressions.
HIER and Flat-BB have identical completed terminal, prefix cache and C counts in
all seven completed cases. M01's 164 cache misses and 109 C calls are unchanged;
M03/M08 reduce FLAT's 16 C calls and 16 prefix misses to 2/2, M06's 42/48 to 18/24.
M01/M04/M05 have no objective-bound prunes: fewer attempted plans there mostly
reflect reachability filtering, not avoided exact transitions.

Exclusive timing categories are routing, transition propagation, terminal,
bound/traversal (historically named `hierarchy_bound_and_traversal_s` for both BB
methods), result/witness and residual solve work. They exclude nested evaluation
and routing from traversal. `C_operator_s` is nested within transitions and must
not be added. Per-row CPU, full supervised wall and memory sampling are separate.
All accepted rows have nonnegative residuals. Individual category medians need not
sum to the median total. For M01, Flat-BB/HIER management medians are 1.201/4.190 ms;
HIER has 2981 selected-leg calls versus 1325, but both have 81 misses. For M06 the
management medians are 0.240/0.783 ms, calls 289/693, misses 49/49.

## Interpretation and one next step

Ordinary B&B search strategy removes obvious long-detour work in the constructed
positive controls M02/M03/M06/M08; it does not establish a broad real-data claim.
HIER removes **no additional exact terminal, prefix or C work** versus Flat-BB,
and finds its first attained incumbent at the same position in every completed
case. Its Region counts are not stronger exclusion evidence: it performs repeated
member-bound, coverage, routing-cache-hit and tree/queue work. M04 retains eight
equal singleton nodes in Flat-BB versus 32 equal Region nodes in HIER, with no
objective pruning. Their different node counts measure different objects.

Most cases take only 1–18 ms to solve and roughly 0.25–0.47 s including startup.
M03 Flat-BB's three observations are 5.631/2.162/3.430 ms, versus HIER's
2.298/2.298/2.413 ms; that isolated median advantage is not supported by fewer
exact computations or earlier threshold discovery. M08 gives 2.159 vs 2.404 ms
with identical work to M03. Renaming changes no work count here; these small
runtime differences cannot establish a causal benefit from ID grouping.
M01's 82.637 vs 85.836 ms likewise supports descriptive implementation cost only.
No statistically reliable general speedup, stronger Region bound or hierarchy
advantage has been demonstrated. Seven-case parity does not complete the requested
eight-case correctness claim, and the exact P07 control is still absent.

**Sole next priority:** repair input preflight and complete the originally intended
M01/M07 controls in a separately authorized bounded follow-up, keeping this Core,
N/H and bound unchanged. This round stops at its 72-attempt ceiling; no tree/bound
optimization, domain expansion, CS/union work, Shandong batch or holdout is proposed
before those missing controls are addressed. The current draft PR is reviewable
but is not a claim that every taskbook requirement passed. Do not auto-merge.
