# Milestone 4R-B2-B21 — Exact Small-Domain Multi-Stop Validation

2026-10-05 (Asia/Shanghai). **Correctness hard stop: frozen tie/frontier and dominance contracts fail on an attained C→C→S hand case.**

## A. Scope

Small-domain exact validation only; H_ref=4 is a diagnostic cap. This run found a contract counterexample during the first executed Stage A tie case (#15). It does not complete B21, authorize deployable scaling, or make a long-haul claim. Full REF, FLAT-F and HIER-F implementations were not completed after the hard stop. The independent finite-regime reference and exact frontier operator probe are narrower diagnostic objects, explicitly identified below.

## B. Frozen theory/preservation

The previously missing B2 formal specification and theory audit are now present. The required B2 authority read was completed in order after reviewing the research specification and accepted one-stop/B1-D2 artifacts. Authority: B21 protocol, T7 theorem audit, T7 frontier specification, B2 theory audit, B2 formal specification, frozen predecessors. Earlier nonstrict dominance and closed-charge drafts are superseded by the later strict contracts. The conflict below persists in the highest-priority protocol's exact K=(J,Q,H,Site/action tuple) requirement; no authority permits changing that key to accept the counterexample.

Git commit `20b658257fb67655e09229411783935e17084fa4`. Initial untracked accepted one-stop sources/evidence were retained; accepted tracked diff is empty. Before/after checks verified **12,872 files** and **53,288 expected hash records**; all protected source/result manifests, hierarchy, boundary, and B1-D2 report/result hashes match. **14 prior-attempt files** were independently preserved. The earlier missing-authority attempt and report are archived in `blocked_attempt_missing_authority_2026_10_05/`, with their hashes recorded. All new code/evidence is confined to the requested B21 result directory and this report. Available headers identify Milestone 5 / legacy 4R-B2; the requested legacy namespace retains that provenance.

Pre-tests: **235 passed**, no failures/errors/skips. Final full suite, including the new diagnostic tests: **244 passed, 2 failed**, no errors/skips. The two ordinary, unwaived failures are the frozen frontier complete-key assertion and frozen strict-cost dominance complete-key assertion. All 235 accepted predecessor tests still pass. Failed log/XML remain available; final suite failure is not presented as acceptance.

Protocol SHA-256: `a50e2072615449c84b072b2a9e5975b37582d42e05bcf7387bf0c8d8eb5e6423`. Authority hashes, numerical-contract hash, all Git statuses and predecessor hashes are recorded in the JSON manifests/acceptance.

## C. Charging-model audit

Frozen capacity: 60 kWh. Charging powers/breakpoints:

| Energy interval (kWh) | Power (kW) | F(E), seconds |
|---|---:|---|
| [0,30] | 100 | 36E |
| [30,48] | 60 | 60E−720 |
| [48,60] | 30 | 120E−3600 |

P(E)>0 on every segment. An independent segment-integral primitive matches the unchanged evaluator on **55 interval pairs**, including interiors, exact breakpoints, multisegment and zero-length intervals; violations=0. Binary64 is used only for candidate discovery and the separate primitive audit (1e−10 s tolerance), never to relax physical feasibility. Diagnostic arithmetic is rational, with zero semantic/tie tolerance, no snapping, exact open inequalities, and exact affine intersection ordering.

## D. Independent REF

`validation/reference_probe.py` enumerates **263 static effect-labelled sequences**, including repeats and the empty sequence, through H_ref=4 over the four-Site fixture. It derives **11,070 charging-segment/schedule-branch LP regimes**. Physical route selection uses the fastest directed path and that path's actual length. No frontier/Region-bound module is imported. The blocking fixture has C and S actions; CS and the general full-suite REF are not claimed implemented.

HiGHS discovers candidates using existing SciPy. Every LP accepted as optimal is checked with exact rational primal feasibility, dual feasibility and strong duality. A positive exact Phase-I optimum certifies infeasible closed regimes. Strict charge is tested by a positive feasible common slack on the original regime or optimal face, not an arbitrary required charge quantum. Open secondary faces remain nonattained within their regimes and cannot supply executable keys; the global winning key is attained in another certified regime. The winning witness is rechecked in the original charging integrals, max schedule equations and energy constraints.

The reference result is J=**44950 s**, Q=**76 kWh**, H=**3**, tuple `(Site 2,C)→(Site 3,C)→(Site 4,S)`, terminal energy **6 kWh**, scheduled start/completion **40000/42700 s**. Its LP witness charges **41, 35 kWh**. Another valid witness is (28,48) kWh; witness multiplicity does not change the result key. An independent analytic certificate gives the same primary and secondary lower bounds.

## E. Frontier implementation

The exact rational operator probe implements the frozen earliest-time PWA representation, strict-positive charging for this fixture, exact primary/secondary merge, drive, S, and clipping. Pieces include state index, intervals/open endpoints, affine time/charge, attainment, predecessor/optimizer rules and Site/effect witness metadata. It is not a completed FLAT-F/HIER-F solver.

At Site 3 with r=1 and k=2, the exact earliest prefix frontiers on E∈(0,60] are:

| Prefix | Earliest t(E) | Cumulative Q(E) |
|---|---|---|
| Site 1 C → Site 3 C | 20100+F(E) | E+35 |
| Site 2 C → Site 3 C | 20328+F(E) | E+28 |

The first frontier is 228 s earlier everywhere. The frozen earliest-time merge therefore deletes the second prefix's metadata. After a 9000 s, 40 kWh drive to Site 4, 300 s overhead, and S with a=40000, both histories wait to the same start. The final primary difference becomes zero. The deleted prefix charges 7 kWh less.

Computationally, `S(merge(A,B))` and `merge(S(A),S(B))` agree on primary time but disagree on charge/witness. At terminal reserve 6, the frozen earlier-prefix propagation returns **(44950,83,3,Site-1 tuple)** while the independent exact result is **(44950,76,3,Site-2 tuple)**. T7 Sections 3 and 16–20 retain Q only among primary-earliest prefixes; that information cannot recover a later prefix whose primary gap collapses under `max(a,t+h)`.

This is a representation/tie-theorem defect, not numerical rounding, charge discretization, or a route/charging-model discrepancy. Retaining later alternatives in the diagnostic is used only to expose the counterexample, not silently substituted for the frozen solver.

## F. Case suites

Stage A: **1/20 executed**, frozen theme #15 (time tie with different cumulative charge). It also covers C→C→S and a reserve-tight destination. Four concrete Sites, H_ref=4, frozen charging law, fixed directed route/length semantics. The case and analytic expected result were frozen before regime optimization. Candidate selection was not changed after outcomes.

Stage B: **0/64**. Stage C: **0/32**. They were not constructed or run after the hard stop. The remaining 19 Stage A cases, CS/attainment pathologies, real-data candidate manifest, hierarchical coverage/bounds and T7-5 depth validation remain uncompleted. There is no claim that those requirements passed or were optional.

## G. G1–G11

| Gate | Status | Violations/mismatches | Evidence scope |
|---|---|---:|---|
| G1 | passed | 0 | Frozen curve/primitive, 55 pairs |
| G2 | **failed** | **1** | Exact merge/drive/S composition loses Q/witness |
| G3 | not evaluated fully | NA | Both results attained in the blocking case only |
| G4 | **failed** | **1** | Same J/H, charge 83 vs 76, wrong Site tuple |
| G5 | not evaluated | NA | No completed REF/FLAT-F suite comparison |
| G6 | **failed** | **1** | T3 point-label continuation counterexample; full FLAT-F modes unrun |
| G7 | not evaluated | NA | HIER-F unrun; lost/duplicate actions unmeasured |
| G8 | not evaluated | NA | No HIER Region/effect nodes audited |
| G9 | not evaluated | NA | HIER-F unrun |
| G10 | passed for introduced code | 0 | No SOC grid, q_min, neutral action or finite charging-action discretization |
| G11 | passed | 0 | Predecessors and earlier blocked attempt preserved |

NA is unmeasured, not zero violations. Failed gates remain failed; passing primitive/preservation checks and 244 passing tests do not authorize B21 acceptance.

## H. Attainment/pathology

The blocking global optimum is attained and all its C quantities are strictly positive. The failure does not require a zero-charge limit. The reference independently distinguishes empty strict regimes and unattained primary/secondary faces during enumeration. The required global unattained-infimum and zero-charge-limit hand cases were not executed after the hard stop.

## I. Dominance

Take the two earliest executable prefix witnesses at Site 3 with E=48, r=1, k=2:

| Quantity | A: Site 1 prefix | B: Site 2 prefix |
|---|---:|---:|
| t | 22260 | 22488 |
| E | 48 | 48 |
| g=t+2λ | 23460 | 23688 |
| Q | 83 | 76 |
| Schedule wait after arrival/overhead | 8440 | 8212 |
| Final J | 44950 | 44950 |

All three frozen dominance relations hold: t_A<t_B, E_A=E_B, g_A<g_B. Deleting B loses the globally better charge key. The 228 s prefix advantage is consumed by 228 s additional scheduled waiting. The B2-T3 emulation argument's claimed strict final advantage does not follow from a strict g advantage when waiting collapses clock differences.

The exact point-label D-off continuation chooses B; the rule-authorized D-on deletion chooses A. The deletion witness records every required relation and both completed keys. This is a theorem test, not a claimed completed FLAT-F D-on/off population run. No stronger dominance, equal-g deletion, or rule amendment was implemented.

## J. Hierarchical coverage/bounds

HIER-F was not begun after the operator/tie failure. No lost-action, duplicate-action, refinement or admissibility zero is fabricated. The frozen hierarchy and boundary artifacts remain unchanged. Region centroids and average charge quantities were not used.

## K. Frontier complexity

Stored operator trace piece counts: `{'branch_A': 3, 'branch_B': 3, 'earliest_merge': 6, 'after_schedule': 5, 'terminal': 3, 'alternative_schedule_merge': 5}`. Peak stored trace group: **6**, total stored pieces across these trace groups: **25**. Open endpoints and exact breakpoints are recorded per group. These are partial diagnostic traces, not complete per-case solver counts or a complexity acceptance threshold. Full total pieces created/retained and HIER node counts remain NA.

## L. Runtime

`runtime_table.csv` retains reference enumeration, continuous-regime optimization and operator-probe times for reproducibility only. No performance comparison or interpretation follows the failed gates. Complete FLAT-F/HIER-F component timing is unmeasured. No B1-D2 runtime comparison or long-haul scalability statement is made.

## M. Limitations

B21 is incomplete and blocked by a counterexample inside its permitted small domain. The reference/probe validates one hand case only, with diagnostic H_ref=4 and four candidates. No generated/real integration population, CS operator, full solver, hierarchy audit, production depth theorem test, long-haul stage or holdout was completed. Normal full REF/FLAT-F/HIER-F mismatch fields remain null rather than being populated with narrower diagnostic counts.

Frozen predecessor files and theory documents were not altered. The two failing regressions are ordinary assertions, with no xfail/waiver or weakened tie comparison. The first reference implementation assertion was corrected to preserve nonattained secondary faces per regime; no case, physical parameter or expected result changed.

## N. Decision

**B2-1 blocked; do not proceed to deployable/long-haul scaling.**

The exact failed contracts are **T7-4 lexicographic closure of earliest-time-only frontiers** and **B2-T3 strict-cost dominance as tie-safe deletion**. A separately accepted theory revision must resolve the loss of later lower-charge histories under scheduled waiting before implementation can resume. The current run does not choose or authorize a replacement representation/rule. B2-2 was not started.

Reproduce the diagnostic with `python results/milestone_4r_b2_b21/validation/run_contract_probe.py` in a fresh evidence directory (it refuses to overwrite existing evidence). Recheck the full suite with `python -m pytest -vv tests results/milestone_4r_b2_b21/validation`; the two contract assertions remain failing under the frozen theory. Exact reference results, regime certificates, traces, dominance witness, source/authority hashes, failed logs/XML and prior blocked-attempt evidence remain archived.
