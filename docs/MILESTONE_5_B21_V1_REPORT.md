# Milestone 5 — B21-v1 Exact Multi-Stop Validation

2026-10-05 (Asia/Shanghai). **B21-v1 blocked.** The first exact C-closure hand object fails the mandatory ALG-4 attained-set congruence under the prescribed branchwise infimum and attained/limit-only reduction semantics. No Stage A/B/C expansion or full solver implementation follows this hard stop.

## A. Scope and authority

The research specification and frozen accepted one-stop/B1-D2 contracts were read before the Core Theory, Core Audit, and B21-v1 protocol, in that order. The three supplied Milestone-5 artifacts are at the repository root rather than the prompt's `docs/` paths. They are byte-identical to all three expected hashes; the resolved paths, hashes and immutable snapshots are archived in the new namespace. No missing theory was reconstructed and no historical B2 rule controls this probe.

| Authority | Verified SHA-256 |
|---|---|
| Core Theory v1 | `dbe44ff83b4d98f2d06b090f7cd44bd40b0a4e21cc8eb439eee991ff2c73ccb2` |
| Core Audit v1 | `02a1c417614852daec17a46be66f8930aa8de626128344122136617d5077b4c7` |
| B21-v1 protocol | `013c039b0c4d71f61fc43002ae05f63d33073293f7e0a709fc2e8b5bbe1e537f` |

Git commit: `20b658257fb67655e09229411783935e17084fa4`. Exact initial/final Git statuses are retained. This is a correctness hard-stop report, not completed B21 acceptance. No long-haul, holdout or deployment work was started.

## B. Preservation baseline

Before diagnostic implementation, **235 accepted predecessor tests passed**, with no failures, errors or skips. Preservation checked **12,939 files** against **66,215 expected hash records**, including B1-D2 acceptance/report/source/output hashes, hierarchy, landmarks, boundaries, protected substrate and historical evidence. The dedicated B21-v0 archive manifest covers **62 files**, including its report, acceptance, failed logs/XML, original 76-kWh fixture, REF certificates, operator traces, dominance witness and the prior missing-authority attempt. All remain byte-identical after this run.

Final configured full-suite run plus the six new diagnostics: **240 passed, 1 failed**, no errors/skips. The sole new failure is `test_alg4_mandatory_charge_congruence`; all 235 accepted predecessor tests still pass. The assertion is ordinary and unwaived. Historical v0 diagnostic tests remain outside configured `tests/` testpaths; their original two failed assertions and failed logs/XML are preserved unchanged. No xfail, expected-failure marker, waiver or weakened comparison was introduced.

## C. Algebraic architecture laws and exact counterexample

The numerical contract and hand object/analytic certificate were frozen before evaluation. All branch mathematics uses exact rational arithmetic and zero semantic tolerance. The planned deterministic seed is 52101 with 50 objects in each required generation category; generation was not executed after the first hard-stop witness. ALG-4 has one evaluated object and one violation. ALG-1/2/3/5/6/7/8/9/10 remain unrun, rather than being presented as passing.

Both inputs are attained labels at index `(v,r=1,k=1)`:

| Input | Energy domain | Completion time | rho | Prefix |
|---|---|---|---:|---|
| A | (0,1] | 1000+60 E_a | 0 | (Site 1,C) |
| B | {1/2} | 1031 | 1 | (Site 2,C) |

At E_a=1/2, A has time 1030 < 1031 and rho 0 < 1. The exact same-energy safe rule therefore allows removal of B. Both prefix labels have physical charging/drive realizations under the unchanged curve, recorded in `physical_realization_certificate.json`. B's singleton is an attained label in the finite hand set; this object does not claim that B is an exhaustive prefix-family domain.

Apply semantic C at Site 3, h=300, and exact output energy E_d=1. The frozen primitive is F(E)=36 E on this interval. For A, strict charging gives 0 < E_a < 1 and

    t'_A = 1000 + 60 E_a + 300 + 36(1-E_a)
         = 1336 + 24 E_a.

Its infimum is 1336, unattained. For B, the executable result is

    t'_B = 1031 + 300 + 36(1-1/2) = 1349.

The required branchwise infimal C summary stores A's 1336 as a limit-only object and B's 1349 as an attained object. With the required separation, limit-only A cannot delete attained B. Thus, at E_d=1:

| Order | Represented attained labels after reduction |
|---|---|
| R(C(R(X))) | empty |
| R(C(X)) | (1349, rho=1, ((2,C),(3,C))) |

The comparator checks exact attained `(t,rho,pi)` sets, not IDs or segmentation. A single exact energy witness suffices to disprove global semantic equivalence; it is not an SOC grid. The two sides have the same lower infimum, which does not make their represented attained label sets equal.

The input safe-dominance theorem itself is not refuted: A can replay B's charge at E_a=1/2 to finish at 1348, or use E_a=1/4 to finish at 1342. Both are attained and beat B. **Those noninfimal attained A outputs are missing from the prescribed per-family infimal-time summary.** For every attained A output with E_a=u>0, choosing u/2 gives another strictly earlier attained output, with the same final energy/rho/tuple. There is no earliest attained A at E_d=1.

Consequently the proof's dominating executable replacement need not belong to any attained minimum branch. Core Theory section 19 requires every deleted attained label to have a retained attained dominator; section 26 keeps the branchwise infimum; the audit sections 5 and 9 require earliest attained Pareto branches and prohibit limit-only deletion. These conditions do not justify the asserted ALG-4 equality for this finite open-domain input. Retaining a finite collection of arbitrary attained A times would not supply the exact earliest attained Pareto frontier: its earliest retained time always misses another smaller legal time.

The audit explicitly permits transforming both layers and recomputing attainment (section 9, rule 4). That does not identify an attained C minimum for A in this hand object, nor permit using a limit-only C result to delete B. A future revised representation may carry full feasible-family information or a continuation certificate, but that is not silently substituted for the frozen attained-set congruence in this run.

## D. Permanent B21-v0 counterexample regression

Not run after the algebra hard stop. Its required key remains **(44950 s,76 kWh,3,((2,C),(3,C),(4,S)))**. The original fixture and all old failure evidence are unchanged. This report does not claim that the new architecture passes that regression.

## E. Reset adversarial regressions

0/10 completed. The independent analytic hand object is an algebra/closure disproof, not a substitute for any of the preregistered ten cases. No expected result or case was replaced after observation.

## F. Independent REF-v1

The full REF-v1 solver was not implemented. No sequence enumeration or comparative optimization population was run. The hand expectation is derived analytically, independently of reduction, by the exact affine expression above. Neither the existing historical reference nor a frontier routine supplies that derivation. REF-v1 independence/population gates remain NA.

## G. FLAT-P representation and implementation

Only a narrowly scoped literal contract probe was written, entirely under `results/milestone_5_b21_v1/`. It evaluates one finite input reduction, one branchwise C regime and attained-only output reduction. It is not a completed FLAT-P, REF-v1 or HIER-P solver. No accepted source was changed. The probe uses no old earliest-time merge, strict-g rule, cross-energy dominance, SOC grid, charge quantum, neutral action or heuristic cap.

## H. Stage A/B/C population completion

| Population | Completed | Required |
|---|---:|---:|
| Legacy Stage A | 0 | 20 |
| Synthetic Stage B | 0 | 64 |
| Bounded-real Stage C | 0 | 32 |

The remaining algebra population, permanent/reset regressions, solver implementations, candidate selection manifest and later suites were not executed after the failed mandatory architecture gate.

## I. V1-G0 through V1-G12

| Gate | Status | Violations |
|---|---|---:|
| V1-G0 | failed | 1 |
| V1-G1 | passed | 0 |
| V1-G2 | failed | 1 |
| V1-G3 | not_evaluated | NA |
| V1-G4 | not_evaluated | NA |
| V1-G5 | not_evaluated | NA |
| V1-G6 | not_evaluated | NA |
| V1-G7 | not_evaluated | NA |
| V1-G8 | not_evaluated | NA |
| V1-G9 | not_evaluated | NA |
| V1-G10 | not_evaluated | NA |
| V1-G11 | not_evaluated | NA |
| V1-G12 | passed | 0 |

V1-G2's failure scope is the same C-closure hand object. V1-G1 covers the independent charging primitive audit: positive powers 100/60/30 kW, energy breaks 0/30/48/60 kWh, and **55** segment-interior/breakpoint/multisegment/zero-length interval checks. Its rational integral and the unchanged evaluator agree within the frozen binary64 audit policy. No charging law was changed. V1-G12 is the completed before/after preservation audit. Other solver-wide gates are not inferred from these narrow probes. NA means unmeasured, never zero violations.

## J. D-on/D-off dominance audit

The full D-on/D-off solver comparison is unrun. The hand deletion witness uses the identical state and identical energy 1/2, with t_A=1030<t_B=1031 and rho_A=0<rho_B=1; the tuple rule's equal-rho condition is not needed. There are zero cross-energy deletions in this single probe. No full-population zero mismatch is claimed.

## K. Hierarchy coverage, refinement and bounds

HIER-P is unimplemented. Coverage, refinement, bounds and equality-node audits are NA. Frozen hierarchy/landmark/boundary artifacts remain unchanged. No Region-average state or executable Region representative was introduced.

## L. Attained versus limit-only behavior

At E_d=1, A's infimal time 1336 is correctly nonattained and B's 1349 is executable. The contradiction is not caused by turning q>0 into q>=0. For the exact A witness E_a=1/4, charge is 3/4 and completion 1342. A legal S suffix with h=300, [a,b]=[2000,2100], D=100 waits to a and completes at **2100**, attained. Therefore missing noninfimal executable realizations cannot simply be dismissed as irrelevant to all future optimal attained outputs.

This observation does not claim a globally solved case or a new theory. It pinpoints the missing attained replacement in the stated closure/congruence argument. No primary/secondary status comparison from full solvers was run.

## M. Frontier complexity

Only the local probe is measured: two attained input pieces; one safe singleton deletion; left C summary has zero attained objects and one limit-only object at the exact witness energy; right summary has one attained object and one limit-only object. Full per-state/per-case branch/piece/split/intersection accounting is NA. The probe's counts are not substituted for full solver complexity tables.

## N. Runtime

The preservation hash audit and pre/final full test timings are in their logs/summaries. The rational closure hand probe took 0.001136 seconds. REF enumeration/regime optimization, FLAT propagation/reduction, HIER bounds/refinement and leaf materialization are unrun and remain null. Runtime has no acceptance threshold or scalability interpretation.

## O. Limitations

B21-v1 is incomplete. The theorem/operator diagnostic addresses one exact open-domain C regime only. No full solver comparison, CS operator population, permanent regression, generated/real suite, Region audit or incumbent-derived depth validation was completed. The failing assertion remains unwaived. No Core Theory v1.1 or alternative frontier design was implemented.

## P. Decision

**B21-v1 blocked.** Classification: **theory contradiction** in the asserted branchwise C closure / attained-set ALG-4 congruence contract. A safe attained input replacement can have only an unattained infimal summary after C, while an attained dominated-family output remains represented when C precedes reduction. The required zero-violation architecture gate fails.

Stop here. **Do not authorize or begin deployable/long-haul multi-stop work.** The existing B21-v0 failure and its original 76-kWh expected winner remain preserved exactly.
