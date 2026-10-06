# Milestone 4R-B1D2 — Pre-implementation blocker

Date: 2026-10-02 (Asia/Shanghai). **Stopped before implementation: protected-file mismatch and pre-existing test failures.**

## A. Scope and stage rule

> B1-D2 is the final one-stop algorithmic iteration. After B1-D2, the one-stop method is frozen and the next research milestone is B2 multi-stop formalization. B1 may be reopened only for a fundamental correctness defect, not for additional performance tuning.

The stage rule is retained. This run did not reach B1-D2 completion or one-stop
freeze: the mandatory preservation precondition failed before boundary extraction.
No B1-D3 or alternative algorithm is proposed.

## B. Frozen evidence

The existing full suite contains exactly 207 tests, but its actual result is
**205 passed, 2 failed, 0 errors, 0 skips** (136.37 s), not 207 passing tests.
Both failures detect the same protected-file mismatch:

- `tests/test_hierarchy4r_artifacts.py::test_archived_blocker_and_accepted_hashes_unchanged`
- `tests/test_hierarchy4r_diagnosis.py::test_frozen_modules_and_all_protected_evidence_unchanged`

The audit checked **11,332 frozen files**. Exactly one differs:
`.gitignore`, which was already modified when this run started.

Expected SHA-256: `68bfbdb7f03c9fdaf30bb55bb4e1d10e15055ee87214125e5ded8aaeb93d8b26`.
Observed SHA-256: `30815e72d7068c9d62f59092375ecae3ea2cd0bbee28a6f82e056e3c2d6bb386`.

The existing diff adds seven patterns: `*.parquet`, `*.json`, `*.csv`, `*.npy`,
`*.npz`, `*.log`, `*.xml`. This file is protected by the B1 checkpoint and B1-E
preservation manifest. Its current contents were not reverted or changed.
The exact diff is archived as `preexisting_tracked_diff.patch`.

All other frozen files match, including accepted algorithms and outputs,
B1/B1-D/B1-E reports, landmark arrays, Region summaries and perfect-static artifacts.
The older accepted protection audit also passes (840 artifacts, 56 sources).
The mismatch is therefore a **provenance/preservation blocker**, not evidence of
a mathematical or routing correctness defect.

Git commit: `20b658257fb67655e09229411783935e17084fa4`. Full status and input hashes are in
`preservation_before.json`; final verification confirms no frozen file changed
further during this run.

Hierarchy hash: `4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805`.
Landmark-manifest hash: `4627d789aaae53ddf5e084bf8ccdcff0b44ec0ca181c5e8c3b99a6c7b5975af1`.

## C. Boundary construction

Not started. No boundary artifact, boundary-complexity result, numerical rule,
new SSSP, or comparative performance result was created.

## D. F1–F7

| Gate | Status | Violations |
|---|---|---:|
| F1 | not_evaluated | NA |
| F2 | not_evaluated | NA |
| F3 | not_evaluated | NA |
| F4 | not_evaluated | NA |
| F5 | not_evaluated | NA |
| F6 | not_evaluated | NA |
| F7 | failed: pre-existing protected-file mismatch | 1 |

The user prompt sections 2 and 34 require a hard stop on protected-file changes
or pre-existing test failures. No gate was waived, no protection manifest was
rewritten, and no frozen algorithm was repaired. F7's mismatch concerns repository
metadata; all frozen algorithm components still match their hashes.

## E. Exactness

B1-D2 cases evaluated: **0/480**. No optimum/tie claim is made for B1-D2.
The prior B1-D and B1-E correctness results remain unchanged.

## F. ALT8 vs BA vs perfect-static

Not evaluated. No new work comparison or performance interpretation is made.

## G. Bound headroom recovery

Not evaluated; no fabricated values.

## H. Work headroom recovery

Not evaluated; no fabricated values.

## I. Envelope-pruning migration

Not evaluated.

## J. Boundary cost and timing

Not evaluated. Only preservation checks and the pre-existing full test suite ran.
Post-implementation tests are not applicable because no implementation was added.

## K. Residual gap

Not evaluated. Historical B1-E findings remain frozen.

## L. Historical context

The retained historical outcomes are **B1-O strong GO**, **B1-D v1 deployable gate
failed**, and B1-E's mixed-bottleneck diagnosis recommending stronger deployable
metric bounds. No B1-D2 descriptive result exists yet. None of these historical
artifacts was overwritten.

## M. One-stop freeze

**Not completed in this run.** F1–F7 have not all passed. This stop is caused by
pre-implementation provenance/test failure, not poor performance and not a reason
to open B1-D3. The final-one-stop iteration commitment remains binding.

The smallest recovery is to retain the archived diff and restore `.gitignore`
to its existing frozen content, then rerun protection checks and the full suite.
Alternatively, an explicit authorization of a protection-contract amendment is
needed before accepting the changed metadata. This run does neither silently.

## N. Transition

**Next milestone after successful B1-D2 closure: B2 multi-stop formalization.**
No B2 formalization or implementation, China benchmark, Go-2 or holdout work began.
The required one-stop freeze statement applies after B1-D2 correctness closure;
it is not asserted as an achieved result here.
