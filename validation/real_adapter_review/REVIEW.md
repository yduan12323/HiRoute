# Independent immutable-leg adapter review

Date: 2026-10-06 UTC.

## Disposition

No unresolved blocking issue was found in the reviewed mock-only adapter and importer snapshot after two fixes were independently rechecked. This is a code/mock review, not acceptance of real-road optimization or of a global/unbounded optimality claim. No actual exported query was optimized. The reviewer did not edit repository-owned files.

Reviewed worktree: `/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut`, branch `codex/m5-real-input-adapter`. Initial loader baseline was `fad06406882d1e373adedb9c0edd538cf5307306`; worktree HEAD advanced to `d02f0f5e9060ca15128dc60a478fdcbafa0c4de5` during review. Exact hashes of the reviewed production sources are in `review_summary.json` and are more precise than the moving worktree HEAD.

## Findings and resolutions

### 1. External incumbent validation disappeared under Python optimization — fixed

The initial `_replay_problem` used Python `assert` for almost every legality check. Under Python `-O`, an initial-only forged witness claimed as terminal passed replay with key `(0, 0, 0, ())`. On the frozen `nonmetric_outgoing_bound_must_be_zero` mock, that false incumbent caused HIER to prune all legal actions and report `infeasible_within_H_ref`; the genuine optimum is `J=6`, `Q=1`, `H=2`.

The owner replaced all these replay assertions with unconditional checks that retain the existing `AssertionError` rejection API, and added a subprocess `-O` regression. Independent rerun of the exact original reproducer under both ordinary and optimized Python now rejects the forgery. Own-search still returns the correct optimum. Relevant artifacts:

- `reproduce_optimized_incumbent.py`
- `incumbent_normal_after_fix.log`
- `incumbent_optimized_after_fix.log`

### 2. Fixed bundle filenames did not enforce symlink containment — fixed

The importer's manifest-declared table/restriction paths already resolved symlinks and checked containment. Its fixed `export_manifest.json` and `query_states_resolved.json` reads initially bypassed that containment helper. The owner routed those reads through the same helper. Independent tests now reject escapes at all four filenames, absolute/empty/traversal paths, and duplicate object keys in state/selection content.

Explicit caller-supplied selection and original-hierarchy paths may remain outside the export directory by design; they are pinned by the reviewed selection hash and original hierarchy hash.

Artifacts: `importer_boundary_checks.py`, `importer_boundary_results.json`.

## Verification results

### Focused repository suites

116 tests and 84 subtests passed in 4.61 seconds:

- `test_time_cut_v2.py`
- `test_time_cut_pwa_v2.py`
- `test_time_cut_bounded_v2.py`
- `test_time_cut_hierarchy_v2.py`
- `test_real_leg_contract.py`
- `test_real_solver_adapter.py`
- `test_real_export_input.py`

See `final_focused_tests.log`. These are the focused physical-search, loader, and importer suites, not a claim that the entire repository test suite was run.

### Independent differential mocks

Sixteen additional adversarial mock tables were frozen before solver execution, using deterministic seed 5072026. They use complete immutable directed constants, sometimes deliberately nonmetric, and are expressly not certified road exports. Dataset SHA-256:

`9d3ac44550cb69a5a821960808ead7aee31a2d286871e6f161500ce6a1d53d61`

All 80 production variants matched the separate REF adapter: FLAT/HIER, dominance on/off, and legal externally supplied incumbents where an attained witness existed. Every independent REF regime was certified: 322 regimes total, at most 144 in any case, within a prechecked limit of 256. The 16 results comprised 8 attained optima, 7 bounded-infeasible cases, and 1 primary-unattained infimum.

Coverage includes co-attached distinct Site identities, Site text equal to the destination anchor while physically attached elsewhere, destination-attached excluded actions, empty original-tree children, binary64 0.1/0.2 rational lifts, nonmetric direct constants, mixed C/S/CS capabilities, two-segment charging curves, schedule state, and exact fractional scalar parameters.

A seventeenth separately frozen hand-arithmetic mock covers secondary nonattainment. Its only feasible scheduled action route requires strictly positive charge but permits that charge to approach zero while waiting for service. Expected `J=14`, secondary infimum `Q=0`, unattained was recorded before runs. All four production variants and independent REF agree.

Artifacts:

- `adversarial_mock_cases.json`, `adversarial_mock_freeze.json`
- `differential_checks.py`
- `differential_production_results.json`, `differential_production.log`
- `differential_with_ref_results.json`, `differential_with_ref.log`
- `secondary_attainment_check.py`
- `secondary_attainment_mock.json`, `secondary_attainment_freeze.json`, `secondary_attainment_results.json`

The initial differential harness compared optional REF summary fields too literally; its status-specific normalization was corrected before the reported successful run. It does not compare a particular optimal continuous charge split when multiple allocations have the same canonical lexicographic result.

### Additional adversarial checks

`adversarial_checks.py` rejected 23 malformed scalar/provenance/tree inputs. It also reconstructed and replayed four deeper witnesses after deliberately restricting the first charge's energy domain to `[3,4]`, then taking a second same-anchor charge and a distinct co-attached schedule action. The first charging departure remained inside the imposed interval, both charges remained strictly positive, semantic Site identities remained distinct, and final state used the destination road anchor.

`importer_boundary_checks.py` rejected 10 malformed path/duplicate-object variants. These checks use tiny fabricated bundles only, with graph construction guarded against accidental invocation.

## Code inspection conclusions

- Real routing is consumed as accepted direct constants. `RealProblem` does not invoke the synthetic graph constructor or perform any graph/metric closure. Energy is the exact query rate times each accepted actual length.
- Road-anchor state identity is separate from semantic Site/capability/event/pi identity. Co-attached action movement remains an explicit zero identity drive.
- `_retag_anchor` delegates through the original constrained `piece.at()` and `Cut.approach()` callbacks rather than rebuilding an unconstrained analytic family. This preserves inherited witness/domain restrictions.
- Terminality compares physical road anchors; a Site named like the destination is not incorrectly excluded when attached elsewhere.
- Real HIER preserves supplied original Region IDs and empty branches. Root and child action partitions are checked; real mode does not call the tiny synthetic repartitioner.
- The real Region bound combines a valid current-time infimum, exact immediate incoming time, obligatory overhead/service, and nonnegative stop penalty. Onward travel is zero. It does not use a possibly nonmetric direct destination time or energy to prune continuation. Pruning remains strict-primary, so equality stays live.
- The synthetic Dijkstra selection logic and its `(time, node path, edge-ID path)` tie behavior remain unchanged. Existing valid-input synthetic behavior passed the focused regressions.
- Witness replay now enforces canonical drive/stop alternation, Site/anchor compatibility, capabilities, schedule completion, strictly positive charging, energy/time equations, terminal reserve, H_ref, and the full final witness identity even under Python `-O`.
- The filesystem importer pins the artifact chain, reconstructs the restriction from actual original-tree bytes, compares the serialized restriction to that reconstruction, and validates scalar/SOC/baseline/schedule arithmetic without propagation or optimization.

## Remaining boundaries, not newly found blockers

- Public dataclass constructors themselves are not an authenticity boundary. Low-level solver callers must use validated factories; the filesystem importer supplies a stronger boundary using caller-pinned hashes and original tree bytes.
- Hash agreement identifies the reviewed inputs. It does not independently prove the router algorithm, selection method, physical-source validity, or raw graph provenance. The importer intentionally does not reread all raw graph files.
- The production and REF implementations were compared on mocks only. Real resource preflight, gate completion, and authorized acceptance runs remain separate work.
- Serialized cut traces still omit some inherited predecessor masks. This review does not upgrade a superset lower-bound certificate into an exact node-constrained REF certificate.

## Reproduction

Use `/workspace/shared/navigation_audit/venv-python311/bin/python`.

1. Run `adversarial_checks.py` to reproduce the extra input/domain checks and deterministic mock freeze.
2. Run `differential_checks.py --ref` for the bounded mock differential pass. The independent adapter is read from `/workspace/shared/navigation_audit/ref5_work`.
3. Run `secondary_attainment_check.py` and `importer_boundary_checks.py`.
4. Run `reproduce_optimized_incumbent.py` normally and with `-O`; both should reject the forged incumbent after the fix.
5. Run the focused pytest command listed in the test log/context above from the production worktree.
