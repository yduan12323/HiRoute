# Milestone 5: time-cut foundation v2 implementation report

Date: 2026-10-06. Baseline: `381e9d6b2ccc214d8dc1ce348f5ec38cb1fe5b1b`.
Branch: `codex/m5-time-cut-foundation`.

## Result and decision

The new, versioned constructive-cut foundation is implemented and its bounded checks pass. It retains an open cut's executable approach witness, creates attained outputs on waiting plateaus, protects the lower-charge prefix, and reports primary versus secondary nonattainment separately.

**This is not a full multi-stop solver or B21 acceptance.** The conditional SQ-1–SQ-8 proof review is supplied separately from implementation acceptance. Complete energy-wide PWA C/CS propagation, physical witness validation, independent REF/FLAT/HIER comparison, and the actual original v0 regression remain open.

No code was pushed, no PR was opened, and no deployment was performed.

## Delivered files

- [Versioned semantic contract](MILESTONE_5_TIME_CUT_CONTRACT_V2.md): authority hashes, exact semantics, witness API, scope and remaining gates.
- [Conditional mathematical review](MILESTONE_5_TIME_CUT_THEORY_REVIEW_V2.md): deductive SQ-1–SQ-8 arguments under explicitly stated H1–H8, finite strict-polyhedral closure and witness reconstruction.
- [Independent theory audit](MILESTONE_5_TIME_CUT_THEORY_AUDIT_V2.md), with resolutions integrated in the review.
- [Independent microprobe review](MILESTONE_5_TIME_CUT_MICROPROBE_REVIEW_V2.md): initial 31-test checkpoint review and separate final 37-test verification, with final source/test hashes.
- `docs/time_cut_v2_authority/`: three byte-identical user-supplied latest research documents.
- `src/timecut5/probe.py`: rational point/affine theorem probes. Seed prefixes are explicitly analytic assumptions.
- `tests/test_time_cut_v2.py`: 37 focused tests, plus four cut-order subtests.
- `experiments/time_cut_v2/independent_review_checks.py`: independently authored held-out exact checks, seed 63119.
- `experiments/time_cut_v2/evidence/`: focused-test XML, unchanged historical-v1-failure XML, independent-check output and tracked-file preservation summary.
- `pyproject.toml`: adds only the new `timecut5` package to the explicit package list. Existing `hierarchy4r` packaging omission is not repaired in this patch.

## Verification actually run

The runtime available here is Python **3.12.14**, whereas the repository declares **>=3.11,<3.12**. Focused standard-library probes run successfully, but this does not replace validation on the project's declared 3.11 environment. Additional test dependencies were installed in an isolated environment; the repository's accepted environment files were unchanged.

| Command | Outcome |
|---|---|
| `PYTHONPATH=src python -m unittest discover -s tests -p test_time_cut_v2.py -q` | 37 tests passed |
| `python -m pytest tests/test_time_cut_v2.py -q` | 37 passed, four subtests passed |
| `PYTHONPATH=src python experiments/time_cut_v2/independent_review_checks.py` | All held-out checks passed; scope below |
| `PYTHONPATH=src python -m compileall -q src/timecut5 tests/test_time_cut_v2.py` | Passed |
| `git diff --check` | Passed |
| `python -m pytest results/milestone_5_b21_v1/test_closure_contract.py -q` | **5 passed, 1 failed**, the unchanged mandatory historical ALG-4 assertion |
| Original v0 full-key test invoked directly | Blocked by missing `results/milestone_4r_b2_b21/hand_cases.json`; FileNotFoundError, no correctness result |
| `python -m pytest -q` | Collection blocked by unavailable `pyrosm`, after other missing dependencies were installed |
| Baseline `python -m pytest --continue-on-collection-errors -q` | **189 passed, 31 failed, 5 skipped, 1 collection error** |
| Final patched tree, same continued-collection command | **226 passed, 31 failed, 5 skipped, 1 collection error**, four new subtests passed |
| `python -m pip wheel --no-deps --no-build-isolation .` | Rejected because Python 3.12.14 is outside the project's declared requirement; no wheel claimed |

The baseline was run in a separate clean detached worktree at the same original commit. Machine-readable per-test comparison found **zero changed outcomes among baseline tests**. The 37 additional passing tests account for the increase from 189 to 226. This is not a green full suite.

All 31 aggregate failures are missing files/tools: 29 missing frozen data/result/evidence files, plus `/usr/bin/time` and the expected `osmium` binary. The collection error is missing `pyrosm`. A binary-only install attempt could not resolve its `cykhash` dependency in this environment. No test was waived, rewritten, xfailed, skipped by this patch, or hidden through a collection-rule change.

The frozen prior report's 235-pass acceptance was not reproduced because its data/tooling is absent from the public clone. The present 189-pass baseline is a different available-environment result and must not be substituted for that historical acceptance.

## Held-out validation scope

The preserved independent check script evaluates:

- 4,000 randomized finite affine input unions for fixed-output C; 3,021 have nonempty outputs.
- 8,000 S/CS actions on sparse executable time families `{tau+2^-n}`, including 5,240 feasible actions.
- Six terminal optimal-face/tie cases.
- 252 constructive dominated-witness replays.

The C oracle enumerates exact interval-closure endpoints, charging kinks, and analytical-cell interior points, tracking endpoint feasibility independently. Every nonempty C and feasible S/CS result is replayed with approach budgets 1000 and `10^-60`. These are held-out point/affine checks, not a general independent physical REF solver, finite-PWA extraction test or theorem proof.

## Historical regression meaning

### v1

At Ed=1, A has `(tau,chi)=(1336,false)` and B has `(1349,true)`. A reconstructs actual 1342 and 1348 completions and arbitrary closer legal approaches. A's new continuation cut covers B. The old explicit attained-record sets still differ, so its mandatory ALG-4 equality **still fails unchanged**.

After S(h=300,a=2000,b=2100,D=100), the new implementation reconstructs an actual A predecessor and returns attained 2100. It never executes 1336.

### v0

The analytic prefix reconstruction retains both earlier/higher-rho A and later/lower-rho B. After waiting, it obtains the published `(44950,76,3,((2,C),(3,C),(4,S)))` winner rather than `(44950,83,3,...)`.

This is expressly **not the original end-to-end regression**. Its synthetic latest-start choice is b=a=40000 and is not claimed to be the absent original fixture's b.

The clone is non-shallow. All eight reachable commits and available local/remote-tracking refs were searched. No original `hand_cases.json` or complete construction dictionary is committed; checked-in scripts only consume it. The root `*.json` ignore rule matches the missing fixture. The smallest original input needed to rerun the bounded reference solve is that file; `case_construction_manifest.json` is additionally needed to verify its frozen identity. Rerunning unchanged historical evidence tests also requires their original saved result/certificate JSONs.

## Preservation

Of the 370 existing tracked baseline files, 369 remain byte-identical. The only changed existing file is `pyproject.toml`, adding `timecut5`. All historical v0/v1 source, tests, reports, XML and theory snapshots are unchanged. The original audit checkout is untouched; implementation and baseline testing used separate worktrees.

This preservation statement covers committed files actually available here. It does not assert preservation of historical ignored artifacts missing from the clone.

## Next gates

1. Review and freeze the conditional proof hypotheses, continuation comparator, exact witness contract, and terminal status contract as M5-T authority.
2. Specify and implement finite **energy-wide** PWA C/CS partitions, isolated endpoints, overlap normalization and whole-domain reduction. Retain inherited intermediate-energy/subfamily restrictions in all witnesses.
3. Build independent physical-prefix replay and a bounded REF that does not invoke quotient reduction; then FLAT with reduction off/on; then HIER.
4. Restore the original v0 fixture/certificates and verify the exact 76-kWh regression, status, full key, and independently replayed witnesses. Different valid charge allocations are allowed when the key agrees.
5. Keep deployable scaling, long-haul evaluation and holdout blocked until the prerequisite theory/implementation/reference gates pass.

General PWA specification is the next unblocked research step. Missing original evidence blocks its historical acceptance test, not the bounded work already delivered.
