# Milestone 4R-B2-B21 — Exact Small-Domain Multi-Stop Validation

Date: 2026-10-05 (Asia/Shanghai). **Blocked before implementation.**

## A. Scope

Requested scope is exact small-domain validation with diagnostic H_ref=4, three independent objects REF / FLAT-F / HIER-F, and no long-haul B2-2 work. No solver or comparative experiment was run.

## B. Frozen theory/preservation

The required authority read cannot be completed: `MILESTONE_4R_B2_FORMAL_SPEC.md` and `MILESTONE_4R_B2_THEORY_AUDIT.md` are absent. A filesystem search under `/home/dy/HiRoute` found neither. The ordered authority read could not proceed past the missing B2 formal specification. After the user suggested a B21-like name, the three available B2 document headers and the protocol's frozen-theory list were inspected to resolve aliases. Protocol Section 1 (lines 52–59) explicitly requires the B2 formal specification and B2 theory audit separately from the T7 documents; no alias or replacement was declared. Later documents were not substituted for missing authorities. The protocol was archived byte-for-byte without treating that snapshot as completion of the ordered semantic read. Available headers identify “Milestone 5 / legacy namespace 4R-B2”; the requested legacy output namespace and B21 semantic identity are retained.

Git commit: `20b658257fb67655e09229411783935e17084fa4`. The working tree already contained untracked accepted one-stop source, specifications and evidence. Their initial status is preserved; untracked status alone was not classified as an unauthorized change. Accepted tracked diff is empty. Preservation rechecked 12,870 files and 53,288 expected hash records from 19 manifests. Predecessor hash violations: 0; changed files after tests: 0. Graph basenames in the boundary manifest were resolved using the frozen boundary builder's declared graph directory; the audit correction is recorded separately and changed no predecessor file.

Full pre-tests: **235 tests, 0 failures, 0 errors, 0 skips**, exit code 0. Full log/XML and before/after preservation records are archived under `results/milestone_4r_b2_b21/`. No final implementation suite was run because implementation never started. These pre-tests validate the existing repository, not B21.

Protocol SHA-256: `a50e2072615449c84b072b2a9e5975b37582d42e05bcf7387bf0c8d8eb5e6423`.

Predecessor hashes:

- `docs/MILESTONE_4R_B1D2_REPORT.md`: `f805471e3603951867d17ed40482c12509d2e197385b3158465f3915fd530f55`
- `results/milestone_4r_b1d2/acceptance.json`: `c31e0262ceb7af156121d3d22fd18b53939797e64f5729ce5f09bafe723573dd`
- `results/milestone_4r_b1/hierarchy.json`: `4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805`
- `results/milestone_4r_b1d/landmark_manifest.json`: `4627d789aaae53ddf5e084bf8ccdcff0b44ec0ca181c5e8c3b99a6c7b5975af1`
- `results/milestone_4r_b1d2/boundary_manifest.json`: `4c5be4f7f8c7f72db707297832f26177f3344f35c9810210b3304581296b26af`

## C. Charging-model audit

Not run. The frozen charging evaluator was not changed; G1 remains unevaluated.

## D. Independent REF

Not implemented. No sequence or continuous-regime enumeration, attainment certificate, or executable witness is claimed.

## E. Frontier implementation

Not implemented. Numerical contract was not frozen. No authoritative SOC grid, charging-quantity patch, or frontier output was introduced.

## F. Case suites

Stage A: 0/20 executed. Stage B: 0/64 executed. Stage C: 0/32 executed. No hand expectations, generated cases, real candidate selections, or coverage matrix were invented. Missing authority must be resolved before those constructions and solver comparison.

## G. G1–G11

| Gate | Status | Violations |
|---|---|---|
| G1 | not_evaluated | NA |
| G2 | not_evaluated | NA |
| G3 | not_evaluated | NA |
| G4 | not_evaluated | NA |
| G5 | not_evaluated | NA |
| G6 | not_evaluated | NA |
| G7 | not_evaluated | NA |
| G8 | not_evaluated | NA |
| G9 | not_evaluated | NA |
| G10 | not_evaluated | NA |
| G11 | passed | 0 |

NA means unmeasured, never zero violations or acceptance. G11 concerns predecessor preservation only and does not validate B21 correctness.

## H. Attainment/pathology

Not evaluated. Attained/unattained/infeasible counts are all zero executed results, not a population finding.

## I. Dominance

D-on/D-off comparisons and deletion witnesses were not produced.

## J. Hierarchical coverage/bounds

Coverage, refinement and REF continuation-bound checks were not run. Lost/duplicate actions and bound violations remain unmeasured.

## K. Frontier complexity

No frontiers were created. Complexity metrics remain NA.

## L. Runtime

Only preservation/pre-test durations were measured. No solver runtime comparison or performance interpretation is supported.

## M. Limitations

The milestone is incomplete. Missing frozen authorities block implementation. Intended validation is limited to H_ref=4 and bounded candidate populations, with no holdout or long-haul claim. The preservation and pre-test evidence establishes only the unchanged predecessor baseline. All new evidence is in the requested B21 namespace and this report.

## N. Decision

**B2-1 blocked; do not proceed to deployable/long-haul scaling.**

Restore/provide the two frozen authority documents, then resume the required ordered read before freezing numerics or implementing REF, FLAT-F and HIER-F. Do not replace the missing documents with newly inferred specifications. B2-2 was not started.
