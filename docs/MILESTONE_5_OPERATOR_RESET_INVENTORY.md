# M5-V operator and reset inventory — 2026-10-11

This is a mapping of existing evidence to the original B21-v1 §21/§23 population request under the versioned v2 continuation-cut semantics. The v1 `alg_case_manifest.json` froze intended seed `52101` but the generator did not run after the first ALG-4 hard stop. There is no historical 250-object population to recover. The refuted v1 attained-set ALG-4 equality is excluded; v2 continuation equivalence is defined in `MILESTONE_5_TIME_CUT_CONTRACT_V2.md` §2 and proved conditionally in `MILESTONE_5_TIME_CUT_THEORY_REVIEW_V2.md` §§3, 9–10.

## Existing current-source checks

At current candidate source `d51367c` (unchanged in `src/timecut5` and `validation/reference5` through `33a50a8`), the unmodified independent oracle scripts were rerun with outputs in `m5_v_current_candidate/`. `validate_production.py --repo . --symbolic-random 150 --point-random 180 --output .../current_v2_validation_results.json` exited 0. Its [result](m5_v_current_candidate/current_v2_validation_results.json), SHA-256 `a7db12993ae5bd9a052c61d1e3baadbdeda6d08b0c82e39cc29fa06112372a1b`, records 172 full-energy symbolic C/CS cases: 75 randomized C + 75 randomized CS + 22 named adversaries, with 7,991 open cells, 8,163 singleton boundaries and 46,548 witness checks. The 180 point-only fuzz cases remain separate. `frontier_checks.py --repo . --output .../current_v2_frontier_results.json` exited 0. Its [result](m5_v_current_candidate/current_v2_frontier_results.json), SHA-256 `fce0f4fe6b98053c5e9923e4a044f55e7b1aad786514b093005fdb6e87d63b0b`, records nine directed frontiers, 216 whole-domain checks, 1,854 operator witnesses and three restricted two-charge witnesses. The script independently implements `cells_for`, `dominates`, `minimal_classes`, `independent_reduce`, Drive and S; its C/CS expected cuts come from independent `oracle.py`. It compares against production outputs but does not reuse the production preorder or arrangement. This is the independent bridge missing from the instrumented A/B reduction observation.

Script SHA-256: `validate_production.py` `ccd6720ecd4b0e8d1024d265838a196e89fc193c692ca998b94dd2119e56f6d0`; `frontier_checks.py` `f98e1b9dfdbc0fe77a9b332faf40e8a2ea221b2d20d47cf4d2dbe878b86077fa`; `oracle.py` `8abc48f6b83e15b7da7cc0087a97cd68e2c7f202c370386f9059cc9c9557aff4`; current `pwa.py` `b769fc3609d4d2040b00de6ad813384c7c00ea9c2e4c1249a4749bea4eea6c8b`; `probe.py` `79226bd7dcf9ff9ceb326e2caf6cee1c471312a6e178ac024a77c27f2ea02b6d`.

| Original §21 category | Existing matching evidence | Remaining exact population/law gap |
| --- | --- | --- |
| 50 Drive objects | Independent whole-domain Drive transform and reduction/congruence on nine directed frontiers; point tests | No frozen deterministic 50-object Drive population with case IDs and independent expected outcomes |
| 50 S objects | Independent whole-domain S transform and congruence on nine directed frontiers; schedule adversaries and point tests | No frozen deterministic 50-object S population |
| 50 C objects | 75 randomized full-energy C objects plus named adversaries; independent symbolic oracle and witnesses | Count and full-domain C law coverage exceed 50; document v2 semantic mapping and exact case IDs before treating these as the §21 replacement population |
| 50 CS objects | 75 randomized full-energy CS objects plus named adversaries; independent symbolic oracle and witnesses | Count and full-domain CS law coverage exceed 50; same identity/semantic mapping step |
| 50 three-way merge objects | Independent envelope/reduction, order reversal, equivalence-class, idempotence and congruence checks on nine frontiers | No frozen deterministic 50-object three-way merge population |

The 250 seeded checks in `tests/test_time_cut_coalescing.py` use seed `762013` and test adjacent-cut union. They do not supply the §21 250 objects. The C/CS script uses seed `20261006`. Counts alone do not prove every algebra law; evaluate the v2 law mapping for each category before closing it.

## Ten original §23 reset themes

| Theme | Closest retained v2 check | Residual mapping |
| --- | --- | --- |
| 1. Full waiting plateau, earlier/high rho vs later/low rho | `frontier_checks.py::rho_tradeoff_survives_then_plateau`; `test_constructive_dominance_budget` | Bind original expected full key if this exact §23 fixture is required |
| 2. Partial waiting-gap collapse | `test_schedule_creates_attainment_on_strict_plateau`, `test_schedule_after_plateau_preserves_attainment` | No frozen theme-specific independent expected-result receipt identified |
| 3. No waiting plateau | `test_schedule_after_plateau_preserves_attainment`; frontier S transform | No frozen theme-specific independent expected-result receipt identified |
| 4. Equal time, unequal rho | `frontier_checks.py::strict_rho_overrides_pi`; `test_rho_and_tuple_are_required` | Map exact original parameter choice |
| 5. Equal time/rho, different tuple | `frontier_checks.py::equal_rho_pi_still_matters`; `test_rho_and_tuple_are_required` | Map exact original tuple fixture |
| 6. Old cross-energy pair must survive | `test_no_cross_energy_or_state_deletion` | Map exact old high-SOC fixture |
| 7. Same prefix, different charge allocation, same final E | `test_v1_infimum_and_real_noninfimal_witnesses`; restricted two-charge replay | Explicit same-prefix allocation fixture and expected key not independently pinned |
| 8. Limit-only better infimum vs attained worse plan | `test_open_cut_cannot_execute_limit`, `test_attained_primary_tie_survives_open_primary_competitor` | Map exact original end-to-end status/key |
| 9. Multiple PWA branch intersections with different rho | `frontier_checks.py::affine_crossing_and_chi_tie`; whole-domain arrangements | Explicit multiple-crossing, different-rho fixture not identified |
| 10. Region bound equals incumbent J with better secondary key | `test_equal_primary_cannot_prune_a_lower_charge_candidate`; current A/B strict pruning traces | Map exact original §23 fixture/source if separately mandated |

The ten names are themes in the protocol, not a frozen generated file. Existing named tests demonstrate mechanisms; this table does not silently mark ten independently derived original expected results as passed. The smallest new work is to freeze and check only unmapped Drive/S/three-way objects and reset fixtures after reviewing the law/fixture mapping. No existing C/CS or C32 population is scheduled for repetition.
