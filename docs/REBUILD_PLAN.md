# HiRoute R0–R4 Rebuild Plan

This is the active rebuild record, updated at stage checkpoints. It does not replace the user taskbook.

## R0 — inventory and baselines (partial)

- GitHub refs rechecked 2026-10-24: main `c33f621f080eea500dfc9ca32b79e23aa9ae9c6a`; PR #14 head `8809424e60eedf519cab814f2fa71af976ff1d25`. The PR remains draft/unmerged as observed. No PR mutation was made.
- New worktree `/home/dy/HiRoute/rebuild-r0-r4`, branch `dot/rebuild-r0-r4`, starts at that main SHA.
- Old workspace preservation is in `/home/dy/HiRoute/r0_rebuild_20261024_baseline/`: checkout statuses, tracked patch, untracked result-file hashes, and old `source-*` Python inventory. The existing project checkout had no tracked diff and six untracked `results/` directories. Its results file inventory contains 19,320 SHA-256 entries. Old source copies were clean at inspection; no worker matched the HiRoute/M5-E2E process patterns.
- Host read-only check: dyserver, Python 3.13.13, 12 logical CPUs, 57 GiB RAM, 278 GiB available on `/`; old M5-E2E path exists. Python 3.11.15 is also available at /home/dy/.local/bin/python3.11; use this interpreter for the declared package range.
- Repository instruction scan found no `AGENTS.md` or `.agents/skills` files in the scanned project/parent depth.
- Static inventory: 81 Python files under `src/` in seven top-level packages (`envelope`, `graph`, `hierarchy4r`, `microplan`, `opportunity`, `stopplan4r`, `timecut5`). AST scan found no direct `experiments.*`, `docs.*`, or `ci.*` imports in `src/`; this does not establish absence of dynamic/path-based dependencies.
- `pyproject.toml` declares `hiroute==0.1.0`, Python `>=3.11,<3.12`, one required dependency set including the geospatial stack, and an explicit setuptools package list that omits several source packages. Pytest adds `src` to `pythonpath`; clean installation is not established.
- The time-cut v2 contract, PWA design and theory review are present. The contract limits itself to bounded probes and says production acceptance remains closed. The theory is conditional; it does not establish production solver acceptance. R12 records scoped historical M5-V acceptance, not blanket rebuild acceptance.
 - The full taskbook text was read through Library text-read in three line windows and saved at the requested local filename. Size matches exactly (57,815 bytes), UTF-8 LF, trailing newline present; computed SHA-256 is 95f7055d28a898f7735d16c33828e278a5701f1a7b4345a796b1c73bdefb3864, which differs from expected 4bf20801a3ccfc1cf64a66777902757f3727e1fad73dbb2c5f7400651cbd6fdc. Byte-for-byte identity is therefore not claimed. The earlier Library materialization helper failed twice; no repeated download was made.

R0 remains partial: inventory, preliminary component disposition and C01–C24 candidate mapping are recorded, but rebuild-owned expected fixtures for C18 and C20–C24 are incomplete. Taskbook reconstruction matches byte count but has a different SHA-256, retained separately; exact source bytes remain unverified.

## R1–R4

Not started. Planned order remains public contracts and installed entry points; exact kernel; search/routing/reference/supervision; raw-data A/B reproduction and independent review. Mainline performance, Shandong N8 bridge and holdout remain out of scope.

## R0 component disposition (preliminary source review)

| Component | Current source / use | Math responsibility | Preliminary disposition | Exit condition |
|---|---|---|---|---|
| Cut / bounded operators | `src/timecut5/probe.py`, `bounded.py` | Exact arithmetic, attainment, bounded FLAT | `RELOCATE_WITH_TESTS` | C01–C24 conformance and installed import |
| PWA / projection | `src/timecut5/pwa.py`, related probe modules | Exact operator behavior; PWA file describes itself as prototype | `ADAPT_INTERFACE` | Explicit supported domain and conformance coverage |
| Reducer / coalescing | `src/timecut5/coalesce.py`, `layer_envelope.py`, `coalesced_solver.py` | Search equivalence and deletion | `RELOCATE_WITH_TESTS` | Preserve same-state scope, strict cuts and witness lift |
| Terminal optimization | `src/timecut5/terminal_energy.py`, `terminal_energy_native.cpp` | Sequential J/Q attainment and native operator | `ADAPT_INTERFACE` | Native and Python parity in frozen cases |
| Witness / provenance | `src/timecut5/provenance.py`, `live_replay.py`, validators | Feasible-plan construction and proof scope | `RELOCATE_WITH_TESTS` | Serialized witness independent replay |
| FLAT / HIER | `src/timecut5/bounded.py`, `hierarchy.py` | Search and declared depth/domain | `ADAPT_INTERFACE` | Same snapshot/key; no hidden legacy imports |
| Region bounds | `src/timecut5/hierarchy.py` | Pruning correctness | `RELOCATE_WITH_TESTS` | Strict-bound and equality-retention conformance |
| Seed / incumbent | `src/timecut5/sparse_seed.py`, incumbent modules | Feasible incumbents and depth claims | `ADAPT_INTERFACE` | Seed absence never means infeasibility; verify source domain |
| Selected-leg provider | `src/timecut5/real_legs.py`, `road_provider.py`, `real_adapter.py` | Chosen route time/length/tie and energy | `ADAPT_INTERFACE` | Fixed route identity with independent route replay |
| Native routing | `src/microplan/routing.cpp`, Python graph/routing modules | Real leg selection | `RELOCATE_WITH_TESTS` | Static packaging and deterministic route ties |
| Data preparation | `src/graph`, `scripts/build_graph.py`, `build_stop_sites_4r.py` | Raw-to-graph/site identity, not optimizer semantics | `ADAPT_INTERFACE` | Raw source DAG regenerates every downstream artifact |
| Independent REF | `validation/reference5/` | Independent parser, LP optimizer, replay | `RELOCATE_WITH_TESTS` | Separate hiroute-ref distribution; remove production imports |
| Supervisor / run ledger | `src/timecut5/systemd_supervisor.py`, `resumable.py`, streaming modules | Execution/resource state, not mathematical status | `REIMPLEMENT_GLUE` | One supervisor; atomic outputs and explicit terminal states |
| Reports / CI / scripts | `scripts/`, `ci/`, `docs/` | Orchestration and historical evidence | `LEGACY_ONLY` except selected data APIs | New CLI works without these runtime paths |
| PR #14 E2E / bridge | PR #14; exact SHA in R0 record | E2E adapter and historical evidence | `LEGACY_ONLY` this round | Keep PR open/draft and preserve original N8 status |

These are initial dispositions from static inspection. They are not proof of correctness or final migration decisions.

## C01–C24 source coverage map

Candidate historical tests and fixtures were located by source inspection. This table records candidate protection only; no test was run here and none is promoted to a new baseline until its inputs, expected result and provenance are frozen in the rebuild.

| ID | Candidate source evidence | R0 state |
|---|---|---|
| C01 zero-stop / reserve | `tests/test_reference5.py`, `tests/test_time_cut_bounded_v2.py` | Candidate located; exact fixture mapping pending |
| C02 single C / strict positive charge | `tests/test_reference5.py::test_strict_feasibility_has_no_charge_quantum`, `tests/test_time_cut_v2.py::TestCharge` | Candidate located |
| C03 single S / window | `tests/test_time_cut_v2.py::TestDriveAndSchedule` | Candidate located |
| C04 CS / parallel makespan | `tests/test_time_cut_v2.py::TestCombinedPoint`, bounded physical tests | Candidate located |
| C05 multiple positive charges | `tests/test_reference5.py::test_original_76_fixture_exhaustively`; original 76 kWh witness | Candidate located; original fixture identity present |
| C06 infeasible time window | `tests/test_time_cut_v2.py::TestDriveAndSchedule` | Candidate located |
| C07 floor / capacity / reserve | REF invalid-input and bounded boundary cases | Candidate located; exact boundary tuple pending |
| C08 waiting plateau and Q | `tests/test_time_cut_v2.py::TestDriveAndSchedule` | Candidate located |
| C09 original 76 kWh | `tests/fixtures/milestone_4r_b2_b21/hand_cases.json`, hash assertion in REF and bounded tests | Fixture and historical hash assertions located |
| C10 full tuple tie | REF deterministic Site tuple tie and time-cut terminal tests | Candidate located |
| C11 open cut is not attained | `tests/test_time_cut_v2.py::TestCutSemantics` | Candidate located |
| C12 waiting turns open cut attained | Schedule plateau test in `TestDriveAndSchedule` | Candidate located |
| C13 hard deadline equality | `test_latest_start_boundary_is_exact` | Candidate located |
| C14 CS active-branch switch | `tests/test_time_cut_v2.py::TestCombinedPoint` | Candidate located |
| C15 primary infimum unattained | REF and terminal tests | Candidate located |
| C16 primary attained / secondary unattained | REF `test_open_lower_secondary_face_blocks_larger_attained_charge`; terminal tests | Candidate located |
| C17 equal primary bound cannot prune | `tests/test_time_cut_hierarchy_v2.py::test_equal_primary_cannot_prune_a_lower_charge_candidate` | Candidate located |
| C18 inherited family / witness lifting | `tests/test_time_cut_optimized_replay.py::TestOptimizedReplay`; `tests/test_reference5.py::test_witness_replay_rejects_invalid_actions_and_energy` | Historical candidate mapped; new public witness case required |
| C19 directed roads / unreachable / tie | REF selected-leg, tie, zero-stop fixtures | Candidate located |
| C20 diagnostic vs seed-derived depth | `tests/m5d_recovery/test_feasible_incumbent.py::test_invalid_depth_assumptions_fail_closed`; sparse execution binding tests | Historical candidate mapped; separate modes required |
| C21 no seed is not infeasibility | `tests/r0/test_remaining_contract_fixtures.py::test_c21_no_seed_is_unknown_not_infeasible` | Result-schema fixture only; actual no-seed solver-path behavior remains pending R3 |
| C22 identity / corruption / unsupported input | `tests/r0/test_remaining_contract_fixtures.py`; `tests/r0/test_cli_supported_matrix.py` | Schema and installed CLI input mutations; exact REF support-matrix parity remains pending |
| C23 timeout preserves incumbent without optimum claim | `tests/r0/test_remaining_contract_fixtures.py::test_c23_timeout_preserves_feasible_incumbent_without_optimum_key` | Result-schema/serialization fixture only; actual supervisor timeout and incumbent replay remain pending R3 |
| C24 observation level preserves mathematical result | `tests/r0/test_remaining_contract_fixtures.py::test_c24_observation_profiles_do_not_change_solver_result` | Executable legacy pilot comparison across off/metrics/trace with full key and witness; new exact-kernel integration remains pending |

R0 source mapping is complete at the candidate-reference level. C18, C20–C24 still require rebuild-owned fixture/expected records before their later conformance gates; historical fixture availability does not itself satisfy an installed conformance gate.

## R1 — public contracts and installed entrypoint (partial)

- Added standard-library-only hiroute contracts, explicit snapshot/config parsing and hiroute validate/solve console entrypoints. Static wheel package list contains only hiroute; hiroute-ref is not yet implemented. Wheel contains 9 files (26,619 uncompressed bytes), no experiments, validation, docs or ci package.
- Built hiroute-0.2.0-py3-none-any.whl and installed non-editably into /tmp/hiroute-r1-core-venv with Python 3.11.15. Import resolved under site-packages; with PYTHONPATH unset, hiroute --version returned hiroute 0.2.0.
- Three contract unit tests passed (Ran 3 tests, OK); this is not C01–C24 conformance.
- Installed C01 zero-stop snapshot completed through the explicitly selected separate-process legacy bounded adapter: attained_optimum, key [1,0,0,[]], witness replay succeeded. Semantic problem ID 5584ae7ad54ddd30033d78ecd8e015bf0df5bde0e2435a2e0f51ab5451fb7985. This tests installed interface and migration adapter, not new-core solving or independent certification.
- First adapter attempt failed because it assumed nonexistent Event.kind/start/end fields. Fixed to actual legacy fields; failure retained in /tmp/hiroute-r1-wheel/smoke-attempt1-failed.log and smoke-retry.log.
- The original untimed REF install is reserved at 10,680 CPU-s using the full 890-second rebuild-round window multiplied by the 12-logical-CPU ceiling. This is a gross reservation, not measured CPU or a trusted command-specific bound; see runs/rebuild_budget.json. A separate supervised REF wheel install/dependency call measured 10.19 CPU-s (user+system), 279 seconds wall, peak RSS 109,296 KB; its start/end and command are in runs/supervised/ref-wheel-install-and-deps/. Temporary venv creation is separately supervised.
- Future formal invocations use tools_rebuild_run.sh: nonblocking single-worker lock, explicit argv, UTC start/end, GNU time resource output, wall timeout and native thread count 1. Historical R1 actions are recorded retrospectively with their known limits.

R1 remains partial. Core CLI still requires the explicitly named legacy adapter. The independent REF package is now separately buildable/installable and its installed module and script entry points show the snapshot CLI; this is packaging/entry-point evidence only. Exact kernel migration, broader conformance, clean validation and removal of production imports from validation.reference5 remain. The separate package boundary is mandatory; no production dependency on independent REF will be carried forward.

## R2–R4

Not started. Next: exact kernel, FLAT/HIER, routing, independent REF and supervision, then raw-data A/B reproduction. Mainline performance, Shandong N8 bridge and holdout remain out of scope.

## 2026-10-24 supervised checkpoint (authoritative update)

This checkpoint supersedes stale stage summaries above. It records work on branch `dot/rebuild-r0-r4`; no PR was created or changed.

### R0 status and C01–C24 disposition

- Candidate-to-spec mapping is complete in the table above, but candidate references are not all rebuild-owned conformance fixtures. Executable migration-owned checks are currently C18 and C20–C24; their mathematical roles are kept distinct: C18 is inherited-family restriction plus witness lifting; C20 diagnostic versus seed-derived depth; C21 missing seed does not imply infeasibility; C22 malformed identity/corruption/unsupported input; C23 timeout preserves a feasible incumbent without claiming optimality; C24 observer profiles do not change mathematical output.
- C09 is the original 76 kWh fixture at `tests/fixtures/milestone_4r_b2_b21/hand_cases.json`, SHA-256 `5e8f4b92bdbefdf5f35104b9430bbc2d0541517e0df41b4ecdb9ca67f85a5744`. The bounded unittest `test_original_76_regression_full_bounded_d_on_off` passed under `runs/supervised/r0-c09-bounded-unittest-v1/` (2.04 measured CPU-s, exit 0). A separate pytest invocation remains as a failed environment attempt because pytest is not installed; that does not invalidate the passing unittest.
- C01–C08, C10–C17, and C19 remain mapped to historical candidates; not every one has an executable rebuild-owned expected fixture. Thus the C01–C24 suite is not complete and R0 remains partial.
- The exact-byte taskbook copy under the local workspace still has a SHA mismatch and is not represented as the source original. Work in this repository follows the available taskbook content as a working specification; byte identity remains unresolved.

### R1 status

- Wheel build/install and installed entry-point evidence remain as recorded above. The independent REF package was separately installed and solved a small C01-derived two-node snapshot (`r1-ref-small-real-case-v2`, 1.75 measured CPU-s, exit 0). This proves only the migration entry point on a synthetic small case, not production correctness or independent optimality coverage.
- The production CLI still uses the explicitly named legacy adapter. Independent REF remains a separate package and must not become a production mathematical optimization dependency.
- Remaining R1: broader contract parity, installed C01–C24 conformance, production import-boundary proof, and removal of the legacy CLI adapter.

### R2 exact-kernel slices completed

- `src/hiroute/exact/scalar.py`: exact rational parsing/text; floats and booleans rejected.
- `src/hiroute/exact/interval.py`: rational nonempty intervals, endpoint closure, intersection, affine infimum and constructive approach.
- `src/hiroute/exact/cut.py`: attainment-aware lower cuts, context/family-bound approach witnesses and time-budget realization.
- `src/hiroute/exact/linear.py`: strict rational rows, normalization, Fourier–Motzkin projection and checked back-substitution lift.
- Supervised passing tests: `r2-exact-cut-v1` (5), `r2-strict-projection-v2` (10), `r2-interval-v1` (4). The earlier syntax-error attempt `r2-strict-projection-v1` is retained in the ledger.
- These slices do not constitute a complete exact kernel. Remaining R2 dependencies, in order: PWA pieces and endpoint semantics; Drive/S/C/CS operators; inherited-family union; safe reduction and dominance; terminal lexicographic J/Q optimization; complete constructive witness/provenance bridge; differential and integration parity. No full production solve or optimality claim is made.

### Supervision and cost

All new formal numerical validation and build/test attempts use `tools_rebuild_run.sh`; measured CPU seconds and failed attempts are in `runs/rebuild_budget.json`. The old install reservation remains a gross reserved allowance derived from the entire prior round window times the 12-CPU ceiling. It is neither measured usage nor a trustworthy command-specific bound. Current new runs do not rely on that reservation as evidence of exact historical cost.


### 2026-10-24 follow-up: R2 PWA, installed dispatch, and review fixes

- src/hiroute/exact/pwa.py adds an exact affine cut piece with open/closed domain endpoints, infimum attainment, and closure-energy witness; tests/r2/test_pwa_piece.py compares three endpoint cases against historical PWA behavior. r2-pwa-piece-v1 passed (0.06 measured CPU-s).
- Projection now retains its declared dimension before tautological zero-row normalization. Regressions cover projecting an all-true 2D row and lifting retained coordinates after all rows normalize away. r2-projection-dimension-regression-v1 passed 7 tests (0.01 measured CPU-s); the prior 5-test comparison did not include these new cases.
- Review found explicit packages=[hiroute] omitted hiroute.exact; static packages now include both. A non-editable wheel was built (hiroute-0.2.0-py3-none-any.whl, SHA-256 ecd8e31b46e9d9a163264e476e29e63fe7d17a2742f0979810d2555c09af42c6) and installed into /tmp/hiroute-r2-wheel-venv-v1; with PYTHONPATH unset and cwd /tmp, imports resolved from site-packages for the public package and all exact modules. One failed import probe used the mistaken module name cuts; the package module is cut, and the corrected supervised import check passed.
- CLI dispatch now accepts only the explicit R1 adapter matrix: bounded time-cut model, exact rational inputs, positive-time selected-leg contract, diagnostic-cap depth, FLAT with no reduction/coalescing/bound/seed profile, bounded_time_cut_v2 charging, and full lexicographic J/Q/H/Pi tie policy. It requires the supplied canonical semantic ID and rejects unsupported contracts/profiles before adapter invocation. The CLI converts adapter output through SolveResult.
- SolveResult now rejects non-completed mathematical claims, malformed/incomplete four-coordinate keys, keys on unattained outcomes, infimum fields on unrelated statuses, and witness_verified without a witness. ProblemSnapshot defensively freezes schedule, Site capability, and edge mappings so caller mutation cannot alter identity-bearing data.
- C24 pilot input charges and stops at Site c; the measured complete key is [5,1,1,[["c","C"]]], not the stale [5,0,0,[]]. The fixture now checks the complete key and replayed-witness signal across off, metrics, and detailed trace. r0-c24-observer-fullkey-v1 passed.
- r0-contracts-result-invariants-v2 passed 10 schema/immutability checks. The first attempt is retained with two test-harness defects (candidate order omitted in the mutation fixture; incorrect expected error phrase).
- A six-case installed-wheel CLI mutation suite has been added. Its first run had 5 passes and exposed that the legacy adapter supplies a primary_infimum field even for an attained optimum; CLI normalization now keeps only status-defined infima. Rebuild and rerun the installed-wheel suite before claiming C22 dispatch evidence complete.
- C21 and C23 remain schema/serialization evidence only; actual no-seed solve behavior and an actual supervisor timeout with feasible incumbent still need R3 path tests. C18 is an old-PWA behavior test, not evidence that the new exact PWA is integrated.


### 2026-10-24 follow-up: result invariants, REF admission, and installed-wheel checkpoint

This is the newest authoritative checkpoint; it supersedes the earlier follow-up's instruction to rerun the wheel and installed CLI suite.

- `SolveResult` now checks execution/math/verification compatibility, restricts complete `(J,Q,H,Pi)` keys to attained results, validates exact rational J/Q, nonnegative integer H and supported Pi actions, and rejects mismatched witness actions or infima on unrelated statuses. Failed verification may only accompany mathematical status `unknown`. `ProblemSnapshot` defensively copies/freezes schedule, candidate order, Site capabilities, charging curves and directed edges; exported dictionaries are detached copies. These are schema/immutability guarantees, not solver-path evidence.
- Supervised source batches passed: R0 suite 21 tests, 6 skipped (`r0-r2-batch-regression-v6`); R2 exact slices 18 tests (`r2-exact-slice-regression-v4`). The updated contract suite also passed against an installed, non-editable wheel with PYTHONPATH unset: 7 tests (`r1-wheel-contract-unit-v5`). The six installed CLI mutation cases passed (`r1-installed-cli-mutation-v6`). A preceding invocation with an incorrect test-file path is retained as a failed attempt; it ran no tests.
- Production wheel v5 SHA-256: `0a00e252e4d81c05516d4f1b69e2f43ad660e9dcf351cfe87524c2921c38761c`; it was force-installed non-editably in `/tmp/hiroute-r2-wheel-venv-v4`. Earlier wheel package omission is corrected; `hiroute.exact` is included.
- Independent REF's own admission matrix rejects mutations of model, numeric, selected-leg and depth contracts; its separately installed wheel passed two admission tests (`r1-ref-installed-admission-v2`). The initial small-case attempt was rejected because its fixture omitted `selected_leg_contract`; after adding the declared contract and recomputing semantic identity, the independent installed CLI returned `attained_optimum` on the two-node synthetic case (`r1-ref-small-real-case-v4`, semantic ID `4800d9377cf97ddba14da1b44d569960617cf75bd761de644bea097336a1fc18`). This is REF entry-point evidence on a synthetic C01-derived example, not production input coverage or broad independent-optimality coverage.
- C22 now has installed production input-mutation tests and independent REF support-matrix admission tests. C18 remains legacy PWA inherited-family/witness-lifting behavior only; it does not demonstrate new exact-kernel integration. C20 is schema/admission coverage. C21 no-seed behavior and C23 actual timeout/incumbent replay remain pending real execution-path tests. C24 is the legacy pilot's observer invariance check with the full corrected key and witness; exact-core integration remains pending. The suite has skipped cases and R0 remains partial.
- R2 has exact scalar/interval/cut/projection and a PWA affine-cut piece, including endpoint semantics and projection-dimension regressions. It is not yet an end-to-end PWA solve. Next dependency slices remain Drive/S/C/CS operators, family union/restriction in the new kernel, safe reduction/dominance, terminal lexicographic optimization, and complete witness/provenance; each needs local old/new comparison before advancing.
- Budget ledger at this checkpoint: `36.52 measured CPU-s`, `0 estimated CPU-s`, `10,680 reserved CPU-s`, plus one explicitly unmeasured temporary-venv creation entry. The 10,680 CPU-s is a gross reservation from the entire earlier 890-second round window multiplied by the 12-core ceiling; it is not command-specific or measured. Supervised attempts, including failed attempts, are retained in `runs/rebuild_budget.json`.
- Working branch remains `dot/rebuild-r0-r4`, evaluated source commit before this checkpoint: `d05f6e149b8bf4c58ad9f6f81cfd01c715944262`. No PR #14 changes were made. Supervised run artifacts remain outside the source commit.
