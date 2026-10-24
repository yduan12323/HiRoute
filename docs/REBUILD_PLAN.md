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
| C21 no seed is not infeasibility | `tests/m5d_recovery/test_feasible_incumbent.py::test_missing_incumbent_and_malformed_witness_rejected`; `test_sparse_feasible_execution.py::test_unknown_pair_stays_unknown_and_manifest_labels_alternative_tree` | Historical candidate mapped; explicit no-seed conformance fixture required |
| C22 identity / corruption / unsupported input | `tests/test_reference5.py::test_invalid_input_is_not_infeasibility`; frozen fixture hash tests | Historical parser coverage mapped; snapshot identity and unsupported-model cases remain new |
| C23 timeout preserves incumbent without optimum claim | `tests/m5d_recovery/test_supervisor.py::test_wall_timeout_is_owned_and_bounded`; `test_durable_incumbent.py::test_abrupt_interrupt_both_methods_durable_and_independent`; `test_open_primary_infimum_is_only_feasible_approximation` | Historical candidates mapped; result-state fixture required |
| C24 observation level preserves mathematical result | `tests/test_invocation_trace_v1.py::test_positive_modes_and_same_answer`; `tests/test_ordered_trace_profile.py` | Historical candidate mapped; observation levels need rebuild-owned profile fixture |

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
