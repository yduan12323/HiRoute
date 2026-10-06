# Independent bounded REF / FLAT / HIER audit

Audit date: 2026-10-06. Review scope is bounded solver correctness only. Neither implementation worktree was edited by this reviewer. Source hashes are in `final_revision_summary.json`.

## Findings, corrected and independently rechecked

1. **Illegal selected destination stop.** FLAT admitted an S action at z and marked the witness replayed while REF rejected it. Minimal example: H=1, o→z time1/energy1, initial2, capacity5, h1, schedule[0,100] duration1, sites z:S. Old FLAT returned (3,0,1,zS). The preserved physical rule says destination arrival is terminal, not a semantic stop (MILESTONE_5_MULTISTOP_CORE_THEORY_V1.md section 2). The v2 contract now explicitly carries it forward. Selected anchors at z are terminal; internal road-path transit through z remains allowed. Latest REF, FLAT and HIER return bounded infeasible.
2. **Replay omitted H_ref.** An H1 witness was still accepted after changing only the case bound to H0. Latest replay rejects the witness.
3. **Consecutive-drive witness could poison HIER's incumbent.** With o→z(time1,energy5), o→x(1,1), x→z(1,1), initial2, h1 and x:C, the true bounded answer is primary-unattained with infimum3. A forged H0 witness D(o,x),D(x,z) bypassed the fixed fastest o→z leg and replay accepted J2. Supplying it as HIER's incumbent pruned the only legitimate branch and returned infeasible. Latest replay enforces one selected leg before each semantic stop and a final selected terminal leg, rejecting the forged incumbent. Independent REF additionally verifies any supplied precomputed leg map by reselection.

Executable minimal regression reproductions: `reproduce_fixed_defects.py`. Permanent implementation-owner regressions were inspected and the three examples were rerun successfully after fixes.

## Independent added validation

- `seeded_cases_v1.json`: 100 deterministic random positive-domain H_ref=2 cases, generated and frozen before any solve, SHA-256 b7fe45805c605c1ce17bc5777c3aab7e12349536b7e89f46df9276d173761e78.
- Final source-hashed run: all **400 comparisons** match independent REF, covering FLAT D-off/on and HIER D-off/on. Source hashes were unchanged over the entire run.
- REF statuses: 36 attained, 62 infeasible within H_ref, 2 secondary-unattained. Every reference regime was certified; no unresolved case was suppressed.
- HIER D-on exercised 66 strict-pruned regions and retained 32 equal-primary nodes. Coverage checks reported no missing or duplicate actions.
- `targeted_attainment_cases_v1.json`: six hand-constructed post-discovery regression cases, each with analytic expected status/key, derivation and explicit legal incumbent sequence. These are labeled regression evidence, not preregistered held-out acceptance cases.
- Those six yield **12 FLAT and 24 HIER comparisons**, all matching analytic expectations and independently certified REF. HIER checks both dominance settings and both own-search/external valid incumbents.
- Targeted obligations: a lower primary-open infimum cannot be masked by an attained incumbent; a primary-open regime at equal J cannot donate a hypothetical smaller Q; an open smaller Q on the attained J face blocks a larger attained Q; equal-primary alternatives with better Q survive; equal J/Q alternatives with fewer stops survive; equal J/Q/H alternatives with a smaller tuple survive.
- Independent final production test invocation: **77 passed, 40 subtests passed**, covering test_time_cut_v2.py, test_time_cut_pwa_v2.py, test_time_cut_bounded_v2.py and test_time_cut_hierarchy_v2.py. This is the module snapshot before any later owner-added regression tests.

## Source inspection conclusions

The independent REF imports no production propagation, projection, reduction or hierarchy routines. Its exact certificate checks cover rational primal feasibility, dual signs/stationarity, strong duality and certified positive Phase-I infeasibility including equalities. An uncertified regime invalidates the whole case. Strict common slack is only an auxiliary feasibility test, not a charging quantum. Sequential strict J and J/Q face checks and global selection correctly exclude primary-open regimes from secondary optimization.

The production strict Fourier–Motzkin projection and back-substitution preserve strict endpoints and constrained predecessor domains. Terminal selection keeps primary and secondary attainment separate and applies the full (J,Q,H,site/action tuple) key only to attained plans. No hidden energy grid, equality pruning, or conversion of a lower bound into an executable plan was found.

HIER uses independently partitioned next-action sets, conservative directed-time bounds and only strict primary pruning. Its incumbent is a replayed executable witness, including when drawn constructively from an open branch. An incumbent does not substitute for the final global terminal-union classification. The new replay checks close the identified externally supplied incumbent gap.

## Remaining scope limits

No outstanding solver defect was found in the reviewed bounded domain after the three corrections. This is not a universal proof, a full-network integration claim, an unrestricted infeasibility result, a production stop-bound derivation or a performance claim. The random population is small-graph H_ref=2 and the six targeted cases are H_ref≤2. HIER scans members of a tiny deterministic static tree and does not establish real-hierarchy deployment correctness. The oracle may conservatively return unresolved on numerically ill-conditioned rational inputs; it must never silently skip those regimes.

## Reproduction

Runtime: /workspace/shared/navigation_audit/venv-python311/bin/python

Set PYTHONDONTWRITEBYTECODE=1 and PYTHONPATH to /workspace/shared/navigation_audit/ref5_work:/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut/src. Run `reproduce_fixed_defects.py` and `run_targeted.py`. `run_audit.py` documents the complete 100-case run; its original result file uses exclusive-create to avoid overwriting evidence. Full fresh-run results are in `final_revision_results.jsonl` and source hashes/counts are in `final_revision_summary.json`.
