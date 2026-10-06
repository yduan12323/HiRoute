"""Close the correctness hard stop, retaining failed regressions and evidence."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(name):
    return json.loads((OUT / name).read_text())


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def counts(path):
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    return {key: sum(int(s.attrib.get(key, 0)) for s in suites)
            for key in ["tests", "failures", "errors", "skipped"]}


def main():
    if (OUT / "acceptance.json").exists():
        raise FileExistsError("Do not overwrite a finalized decision")
    before = read("preservation_before.json")
    hashes = read("frozen_input_hash_manifest.json")
    changed = [name for name, value in hashes.items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != value]
    prior = read("prior_attempt_hash_manifest.json")
    prior_changed = [name for name, value in prior.items()
                     if not (ROOT / name).is_file() or digest(ROOT / name) != value]
    probe_freeze = read("probe_freeze_manifest.json")
    probe_changed = [name for name, value in probe_freeze.items() if digest(OUT / name) != value]
    tracked = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=ROOT, text=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True)
    pre = counts(OUT / "preexisting_tests.xml")
    final = counts(OUT / "final_tests.xml")
    failed = [test.attrib["name"] for test in ET.parse(OUT / "final_tests.xml").getroot().iter("testcase")
              if test.find("failure") is not None or test.find("error") is not None]
    assert set(failed) == {"test_frozen_frontier_preserves_complete_key_after_schedule_waiting",
                           "test_frozen_strict_cost_dominance_preserves_complete_key"}, failed
    assert final["failures"] == 2 and final["errors"] == 0 and final["skipped"] == 0
    assert not changed and not prior_changed and not probe_changed and not tracked.strip()
    assert commit == before["git_commit"] and before["preservation_passed"]
    assert pre["tests"] == 235 and not any(pre[k] for k in ["failures", "errors", "skipped"])
    after = dict(preservation_passed=True, git_commit=commit, git_status=status, tracked_diff=tracked,
        files_verified=len(hashes), expected_hash_records_verified=before["expected_hash_records_verified"],
        changed_files=changed, predecessor_hash_violations=[], prior_attempt_files_verified=len(prior),
        prior_attempt_changes=prior_changed, probe_frozen_files_verified=len(probe_freeze),
        probe_frozen_changes=probe_changed, full_pretests=pre, full_final_tests=final,
        failed_new_contract_regressions=failed, accepted_predecessor_tests_failed=0,
        full_B21_solvers_implemented=False, B2_2_started=False)
    write("preservation_after.json", after)
    write("final_test_summary.json", dict(**read("final_test_execution.json"), **final,
        passed=final["tests"] - final["failures"] - final["errors"] - final["skipped"],
        failed_new_contract_regressions=failed, accepted_predecessor_tests_failed=0,
        xfailed_or_waived_tests=0))
    gates = {f"G{i}": dict(status="not_evaluated", violations=None,
        reason="Hard stop after the first Stage A tie/dominance counterexample") for i in range(1, 12)}
    gates.update(G1=dict(status="passed", violations=0, audited_pairs=55),
        G2=dict(status="failed", violations=1, scope="merge/drive/S composition in Stage A case 15",
                failure="Earliest-time frontier merge loses the secondary winner after scheduled waiting"),
        G4=dict(status="failed", violations=1, scope="Stage A case 15 complete result key",
                failure="Equal primary objective but charge 83 versus 76 kWh and wrong Site tuple"),
        G6=dict(status="failed", violations=1, scope="T3 point-label continuation theorem test",
                full_FLAT_F_D_on_off_comparison_run=False,
                failure="Strict g advantage disappears in mandatory scheduled waiting; deletion loses Q tie"),
        G10=dict(status="passed", violations=0, scope="all code introduced in this blocked run",
                 full_solver_validation_completed=False),
        G11=dict(status="passed", violations=0, files_verified=len(hashes), prior_attempt_files_verified=len(prior)))
    gates["G3"]["blocking_case_observation"] = dict(status_equal=True, both="attained_optimum")
    write("correctness_gates.json", gates)
    ref = read("ref_exact_case_results.json")[0]
    probe = read("frontier_traces_hand_cases.json")
    seq = read("ref_sequence_enumeration_summary.json")
    regimes = read("ref_regime_enumeration_evidence.json")
    prefix = probe["dominance_witness"]
    stored_piece_counts = {name: len(pieces) for name, pieces in probe["pieces"].items()}
    write("piece_count_summary.json", dict(scope="stored traces in blocking operator probe, not complete solver accounting",
        counts=stored_piece_counts, peak_stored_group=max(stored_piece_counts.values()),
        total_stored_pieces=sum(stored_piece_counts.values()), full_case_total_pieces_created=None))
    predecessor_names = ["docs/MILESTONE_4R_B1D2_REPORT.md", "results/milestone_4r_b1d2/acceptance.json",
        "results/milestone_4r_b1/hierarchy.json", "results/milestone_4r_b1d/landmark_manifest.json",
        "results/milestone_4r_b1d2/boundary_manifest.json"]
    predecessor = {name: hashes[name] for name in predecessor_names}
    decision = "B2-1 blocked; do not proceed to deployable/long-haul scaling."
    acceptance = dict(milestone="4R-B2-B21", version="contract-hard-stop-v1", date="2026-10-05",
        timezone="Asia/Shanghai", status="blocked_correctness_failure", completion_rule_satisfied=False,
        semantic_identity="Exact Small-Domain Multi-Stop Validation",
        naming_provenance="Milestone 5 / legacy namespace 4R-B2; requested legacy artifact paths retained",
        protocol_hash=digest(OUT / "protocol_snapshot.md"), predecessor_hashes=predecessor,
        authority_hashes=read("authority_read_manifest.json")["sha256"],
        numerical_contract_hash=digest(OUT / "numerical_contract.json"),
        numerical_contract_scope="exact rational diagnostic probe, not a completed production solver contract",
        test_counts=dict(pre=pre, final=final), final_tests_passed=False,
        stage_case_counts=dict(A=1, B=0, C=0), expected_stage_case_counts=dict(A=20, B=64, C=32),
        executed_stage_A_case=read("contract_probe_decision.json")["case_id"],
        gates=gates, REF_FLAT_F_mismatch_count=None, REF_HIER_F_mismatch_count=None,
        D_on_D_off_mismatch_count=None,
        frontier_operator_probe_mismatch_count=1, point_label_dominance_probe_mismatch_count=1,
        attained_unattained_infeasible_counts=dict(attained_optimum=1, infimum_unattained=0, infeasible=0),
        result_count_scope="one independently optimized hand case",
        lost_action_count=None, duplicate_action_count=None, bound_admissibility_violations=None,
        no_discretization_status="verified_for_all_new_diagnostic_code_no_semantic_patch",
        peak_frontier_piece_count=None, total_frontier_pieces=None,
        probe_peak_stored_piece_group=max(stored_piece_counts.values()),
        probe_total_stored_pieces=sum(stored_piece_counts.values()), maximum_diagnostic_stop_depth=4,
        depth_scope="REF sequence enumeration at the diagnostic cap; winning plan has 3 stops",
        full_REF_implemented=False, full_FLAT_F_implemented=False, HIER_F_implemented=False,
        independent_regime_reference_probe_implemented=True, REF_sequences_enumerated=seq["sequences_enumerated"],
        REF_regimes_enumerated=regimes["regime_count"], B2_2_started=False,
        final_authorization_decision=decision)
    report = f"""# Milestone 4R-B2-B21 — Exact Small-Domain Multi-Stop Validation

2026-10-05 (Asia/Shanghai). **Correctness hard stop: frozen tie/frontier and dominance contracts fail on an attained C→C→S hand case.**

## A. Scope

Small-domain exact validation only; H_ref=4 is a diagnostic cap. This run found a contract counterexample during the first executed Stage A tie case (#15). It does not complete B21, authorize deployable scaling, or make a long-haul claim. Full REF, FLAT-F and HIER-F implementations were not completed after the hard stop. The independent finite-regime reference and exact frontier operator probe are narrower diagnostic objects, explicitly identified below.

## B. Frozen theory/preservation

The previously missing B2 formal specification and theory audit are now present. The required B2 authority read was completed in order after reviewing the research specification and accepted one-stop/B1-D2 artifacts. Authority: B21 protocol, T7 theorem audit, T7 frontier specification, B2 theory audit, B2 formal specification, frozen predecessors. Earlier nonstrict dominance and closed-charge drafts are superseded by the later strict contracts. The conflict below persists in the highest-priority protocol's exact K=(J,Q,H,Site/action tuple) requirement; no authority permits changing that key to accept the counterexample.

Git commit `{commit}`. Initial untracked accepted one-stop sources/evidence were retained; accepted tracked diff is empty. Before/after checks verified **{len(hashes):,} files** and **{before['expected_hash_records_verified']:,} expected hash records**; all protected source/result manifests, hierarchy, boundary, and B1-D2 report/result hashes match. **{len(prior)} prior-attempt files** were independently preserved. The earlier missing-authority attempt and report are archived in `blocked_attempt_missing_authority_2026_10_05/`, with their hashes recorded. All new code/evidence is confined to the requested B21 result directory and this report. Available headers identify Milestone 5 / legacy 4R-B2; the requested legacy namespace retains that provenance.

Pre-tests: **{pre['tests']} passed**, no failures/errors/skips. Final full suite, including the new diagnostic tests: **{final['tests'] - final['failures']} passed, {final['failures']} failed**, no errors/skips. The two ordinary, unwaived failures are the frozen frontier complete-key assertion and frozen strict-cost dominance complete-key assertion. All 235 accepted predecessor tests still pass. Failed log/XML remain available; final suite failure is not presented as acceptance.

Protocol SHA-256: `{acceptance['protocol_hash']}`. Authority hashes, numerical-contract hash, all Git statuses and predecessor hashes are recorded in the JSON manifests/acceptance.

## C. Charging-model audit

Frozen capacity: 60 kWh. Charging powers/breakpoints:

| Energy interval (kWh) | Power (kW) | F(E), seconds |
|---|---:|---|
| [0,30] | 100 | 36E |
| [30,48] | 60 | 60E−720 |
| [48,60] | 30 | 120E−3600 |

P(E)>0 on every segment. An independent segment-integral primitive matches the unchanged evaluator on **55 interval pairs**, including interiors, exact breakpoints, multisegment and zero-length intervals; violations=0. Binary64 is used only for candidate discovery and the separate primitive audit (1e−10 s tolerance), never to relax physical feasibility. Diagnostic arithmetic is rational, with zero semantic/tie tolerance, no snapping, exact open inequalities, and exact affine intersection ordering.

## D. Independent REF

`validation/reference_probe.py` enumerates **{seq['sequences_enumerated']} static effect-labelled sequences**, including repeats and the empty sequence, through H_ref=4 over the four-Site fixture. It derives **{regimes['regime_count']:,} charging-segment/schedule-branch LP regimes**. Physical route selection uses the fastest directed path and that path's actual length. No frontier/Region-bound module is imported. The blocking fixture has C and S actions; CS and the general full-suite REF are not claimed implemented.

HiGHS discovers candidates using existing SciPy. Every LP accepted as optimal is checked with exact rational primal feasibility, dual feasibility and strong duality. A positive exact Phase-I optimum certifies infeasible closed regimes. Strict charge is tested by a positive feasible common slack on the original regime or optimal face, not an arbitrary required charge quantum. Open secondary faces remain nonattained within their regimes and cannot supply executable keys; the global winning key is attained in another certified regime. The winning witness is rechecked in the original charging integrals, max schedule equations and energy constraints.

The reference result is J=**44950 s**, Q=**76 kWh**, H=**3**, tuple `(Site 2,C)→(Site 3,C)→(Site 4,S)`, terminal energy **6 kWh**, scheduled start/completion **40000/42700 s**. Its LP witness charges **{', '.join(ref['charges'])} kWh**. Another valid witness is (28,48) kWh; witness multiplicity does not change the result key. An independent analytic certificate gives the same primary and secondary lower bounds.

## E. Frontier implementation

The exact rational operator probe implements the frozen earliest-time PWA representation, strict-positive charging for this fixture, exact primary/secondary merge, drive, S, and clipping. Pieces include state index, intervals/open endpoints, affine time/charge, attainment, predecessor/optimizer rules and Site/effect witness metadata. It is not a completed FLAT-F/HIER-F solver.

At Site 3 with r=1 and k=2, the exact earliest prefix frontiers on E∈(0,60] are:

| Prefix | Earliest t(E) | Cumulative Q(E) |
|---|---|---|
| Site 1 C → Site 3 C | 20100+F(E) | E+35 |
| Site 2 C → Site 3 C | 20328+F(E) | E+28 |

The first frontier is 228 s earlier everywhere. The frozen earliest-time merge therefore deletes the second prefix's metadata. After a 9000 s, 40 kWh drive to Site 4, 300 s overhead, and S with a=40000, both histories wait to the same start. The final primary difference becomes zero. The deleted prefix charges 7 kWh less.

Computationally, `S(merge(A,B))` and `merge(S(A),S(B))` agree on primary time but disagree on charge/witness. At terminal reserve 6, the frozen earlier-prefix propagation returns **(44950,83,3,Site-1 tuple)** while the independent exact result is **(44950,76,3,Site-2 tuple)**. T7 Sections 3 and 16–20 retain Q only among primary-earliest prefixes; that information cannot recover a later prefix whose primary gap collapses under `max(a,t+h)`.

This is a representation/tie-theorem defect, not numerical rounding, charge discretization, or a route/charging-model discrepancy. Retaining later alternatives in the diagnostic is used only to expose the counterexample, not silently substituted for the frozen solver.

## F. Case suites

Stage A: **1/20 executed**, frozen theme #15 (time tie with different cumulative charge). It also covers C→C→S and a reserve-tight destination. Four concrete Sites, H_ref=4, frozen charging law, fixed directed route/length semantics. The case and analytic expected result were frozen before regime optimization. Candidate selection was not changed after outcomes.

Stage B: **0/64**. Stage C: **0/32**. They were not constructed or run after the hard stop. The remaining 19 Stage A cases, CS/attainment pathologies, real-data candidate manifest, hierarchical coverage/bounds and T7-5 depth validation remain uncompleted. There is no claim that those requirements passed or were optional.

## G. G1–G11

| Gate | Status | Violations/mismatches | Evidence scope |
|---|---|---:|---|
| G1 | passed | 0 | Frozen curve/primitive, 55 pairs |
| G2 | **failed** | **1** | Exact merge/drive/S composition loses Q/witness |
| G3 | not evaluated fully | NA | Both results attained in the blocking case only |
| G4 | **failed** | **1** | Same J/H, charge 83 vs 76, wrong Site tuple |
| G5 | not evaluated | NA | No completed REF/FLAT-F suite comparison |
| G6 | **failed** | **1** | T3 point-label continuation counterexample; full FLAT-F modes unrun |
| G7 | not evaluated | NA | HIER-F unrun; lost/duplicate actions unmeasured |
| G8 | not evaluated | NA | No HIER Region/effect nodes audited |
| G9 | not evaluated | NA | HIER-F unrun |
| G10 | passed for introduced code | 0 | No SOC grid, q_min, neutral action or finite charging-action discretization |
| G11 | passed | 0 | Predecessors and earlier blocked attempt preserved |

NA is unmeasured, not zero violations. Failed gates remain failed; passing primitive/preservation checks and 244 passing tests do not authorize B21 acceptance.

## H. Attainment/pathology

The blocking global optimum is attained and all its C quantities are strictly positive. The failure does not require a zero-charge limit. The reference independently distinguishes empty strict regimes and unattained primary/secondary faces during enumeration. The required global unattained-infimum and zero-charge-limit hand cases were not executed after the hard stop.

## I. Dominance

Take the two earliest executable prefix witnesses at Site 3 with E=48, r=1, k=2:

| Quantity | A: Site 1 prefix | B: Site 2 prefix |
|---|---:|---:|
| t | {prefix['time_A']} | {prefix['time_B']} |
| E | 48 | 48 |
| g=t+2λ | {prefix['g_A']} | {prefix['g_B']} |
| Q | 83 | 76 |
| Schedule wait after arrival/overhead | 8440 | 8212 |
| Final J | 44950 | 44950 |

All three frozen dominance relations hold: t_A<t_B, E_A=E_B, g_A<g_B. Deleting B loses the globally better charge key. The 228 s prefix advantage is consumed by 228 s additional scheduled waiting. The B2-T3 emulation argument's claimed strict final advantage does not follow from a strict g advantage when waiting collapses clock differences.

The exact point-label D-off continuation chooses B; the rule-authorized D-on deletion chooses A. The deletion witness records every required relation and both completed keys. This is a theorem test, not a claimed completed FLAT-F D-on/off population run. No stronger dominance, equal-g deletion, or rule amendment was implemented.

## J. Hierarchical coverage/bounds

HIER-F was not begun after the operator/tie failure. No lost-action, duplicate-action, refinement or admissibility zero is fabricated. The frozen hierarchy and boundary artifacts remain unchanged. Region centroids and average charge quantities were not used.

## K. Frontier complexity

Stored operator trace piece counts: `{stored_piece_counts}`. Peak stored trace group: **{max(stored_piece_counts.values())}**, total stored pieces across these trace groups: **{sum(stored_piece_counts.values())}**. Open endpoints and exact breakpoints are recorded per group. These are partial diagnostic traces, not complete per-case solver counts or a complexity acceptance threshold. Full total pieces created/retained and HIER node counts remain NA.

## L. Runtime

`runtime_table.csv` retains reference enumeration, continuous-regime optimization and operator-probe times for reproducibility only. No performance comparison or interpretation follows the failed gates. Complete FLAT-F/HIER-F component timing is unmeasured. No B1-D2 runtime comparison or long-haul scalability statement is made.

## M. Limitations

B21 is incomplete and blocked by a counterexample inside its permitted small domain. The reference/probe validates one hand case only, with diagnostic H_ref=4 and four candidates. No generated/real integration population, CS operator, full solver, hierarchy audit, production depth theorem test, long-haul stage or holdout was completed. Normal full REF/FLAT-F/HIER-F mismatch fields remain null rather than being populated with narrower diagnostic counts.

Frozen predecessor files and theory documents were not altered. The two failing regressions are ordinary assertions, with no xfail/waiver or weakened tie comparison. The first reference implementation assertion was corrected to preserve nonattained secondary faces per regime; no case, physical parameter or expected result changed.

## N. Decision

**{decision}**

The exact failed contracts are **T7-4 lexicographic closure of earliest-time-only frontiers** and **B2-T3 strict-cost dominance as tie-safe deletion**. A separately accepted theory revision must resolve the loss of later lower-charge histories under scheduled waiting before implementation can resume. The current run does not choose or authorize a replacement representation/rule. B2-2 was not started.

Reproduce the diagnostic with `python results/milestone_4r_b2_b21/validation/run_contract_probe.py` in a fresh evidence directory (it refuses to overwrite existing evidence). Recheck the full suite with `python -m pytest -vv tests results/milestone_4r_b2_b21/validation`; the two contract assertions remain failing under the frozen theory. Exact reference results, regime certificates, traces, dominance witness, source/authority hashes, failed logs/XML and prior blocked-attempt evidence remain archived.
"""
    # The count in the narrative follows the measured XML, never an assumed
    # number of new tests.
    report = report.replace("244 passing tests", f"{final['tests'] - final['failures']} passing tests")
    report_path = ROOT / "docs/MILESTONE_4R_B2_B21_REPORT.md"
    assert not report_path.exists()
    report_path.write_text(report)
    acceptance["report_sha256"] = digest(report_path)
    evidence_names = ["preservation_before.json", "preservation_after.json", "frozen_input_hash_manifest.json",
        "prior_attempt_hash_manifest.json", "probe_freeze_manifest.json", "numerical_contract.json",
        "charging_segments.json", "cumulative_primitive_audit.json", "hand_cases.json",
        "case_construction_manifest.json", "ref_sequence_enumeration_summary.json",
        "ref_regime_enumeration_evidence.json", "ref_exact_case_results.json",
        "reference_independence_manifest.json", "frontier_traces_hand_cases.json", "operator_audits.json",
        "tie_witness_audits.json", "dominance_deletion_witnesses.json", "dominance_on_off_comparison.json",
        "correctness_gates.json", "final_tests.log", "final_tests.xml", "final_test_summary.json"]
    acceptance["evidence_sha256"] = {name: digest(OUT / name) for name in evidence_names}
    write("acceptance.json", acceptance)
    print(json.dumps(dict(status=acceptance["status"], pretests=pre, final_tests=final,
        failed_gates=[key for key, value in gates.items() if value["status"] == "failed"],
        preservation_passed=True, decision=decision)))


if __name__ == "__main__":
    main()
