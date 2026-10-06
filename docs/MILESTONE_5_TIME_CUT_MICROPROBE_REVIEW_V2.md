# Independent bounded time-cut microprobe review

Date: 2026-10-06 UTC.

Reviewed implementation: `src/timecut5/probe.py` in the `codex/m5-time-cut-foundation` worktree. SHA-256 at review: `79226bd7dcf9ff9ceb326e2caf6cee1c471312a6e178ac024a77c27f2ea02b6d`.

Reviewed tests at final integration: `tests/test_time_cut_v2.py`, SHA-256 `a0eca0a36389bd7020ac4976a6660c9df7df97b710c835a68804ab4975e15a40` (37-test version).

## Result

No semantic defect was found within the explicitly bounded implementation scope. The initial independent rerun of `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -p 'test_time_cut_v2.py' -v` passed 31 tests. Six additional regressions were then added. A separate final read-only reviewer reran the 37-test version successfully and checked the final report. The test hash above identifies that final version, not the earlier 31-test checkpoint. This is the new focused microprobe suite, not the full repository suite or preserved historical failed suites.

Static review checked:

- `charge_at`: exact interval intersections, strict input-energy constraint, affine endpoint infimum, constant-objective interior attainment, OR over tied attaining regimes, and splitting of the approach error budget between energy choice and incoming time;
- `_scheduled`: exact open/closed latest-start feasibility, CS max simplification, plateau-created attainment, and constructive predecessor budget kept inside both the latest-start and plateau boundaries;
- `terminal`: primary infimum before attainment, secondary optimization on the attained primary face only, absent fake full keys for either nonattainment stage, and H/pi selection only after J and Q attain;
- `Cut`: actual predecessor metadata checks, exact positive approach budgets, and prohibition on executing an open boundary;
- finite point reduction: same energy/state restriction, rho and tuple requirements, and retention of a representative of equal-preorder objects.

## Scope clarifications sent to implementer

1. `continuation_equivalent` checks mutual coverage under the sufficient same-state preorder. It is not a complete decision procedure for every form of semantic continuation equivalence.
2. Point stop operators assume Site arrival/capability validation externally; this probe does not inspect road routing or static Site capabilities.
3. `AffineFamily` describes explicitly assumed analytic seed families. Its seed event is not a physical replay of a prior route. Subsequent actions are replayed exactly from that declared seed.
4. Future full-frontier witness reconstruction must retain inherited branch membership constraints and intermediate-energy restrictions. Solving an unrestricted original prefix can return a witness outside a retained subfamily. The present domain-bound seed/predecessor callbacks do not make that shortcut.

## What this review does not establish

No general output-energy PWA C/CS propagation, global energy-wide reduction, physical REF enumerator, FLAT/HIER comparison, original missing v0 fixture reconstruction, production finite-depth search, hierarchical coverage or bound admissibility is certified here. The mathematical proof artifact and its independent audit are separate deliverables. Historical v0/v1 failures remain valid under their preserved old contracts.
