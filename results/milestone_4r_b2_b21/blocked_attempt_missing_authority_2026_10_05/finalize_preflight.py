"""Record an authority blocker without inventing solver validation evidence."""
import json
from pathlib import Path
from preflight import ROOT, OUT, digest, git, write


def main():
    if (OUT / "acceptance.json").exists():
        raise FileExistsError("Blocked-run decision already exists")
    read = lambda name: json.loads((OUT / name).read_text())
    before = read("preservation_before.json")
    after = read("preservation_after.json")
    hashes = read("frozen_input_hash_manifest.json")
    # Retain the initial diagnostic. The first audit resolved the boundary
    # manifest's graph basenames against ROOT. The frozen builder declares
    # data/processed/graphs/slovenia_extended as their base directory.
    initial = before["hash_violations"]
    if initial:
        resolution = []
        for record in initial:
            assert record["manifest"] == "results/milestone_4r_b1d2/boundary_manifest.json"
            assert record["path"] in {"nodes.parquet", "edges.parquet", "metadata.json"}
            name = "data/processed/graphs/slovenia_extended/" + record["path"]
            actual = digest(ROOT / name)
            assert actual == record["expected_sha256"]
            assert hashes[name] == actual
            resolution.append(record | dict(resolved_path=name, resolved_sha256=actual))
            assert hashes.pop(record["path"]) is None
        write("manifest_path_resolution_audit.json", dict(
            initial_diagnostic=initial, resolved_records=resolution,
            evidence="scripts/build_hierarchy_4r_boundary.py declares base = ROOT/data/processed/graphs/slovenia_extended",
            physical_file_changes=0, note="Corrected audit path resolution; no predecessor was changed"))
        before["hash_violations"] = []
        before["files_verified"] = len(hashes)
        before["preservation_passed"] = not before["tracked_diff"].strip()
        write("frozen_input_hash_manifest.json", hashes)
        before["frozen_input_hash_manifest_sha256"] = digest(OUT / "frozen_input_hash_manifest.json")
        before["manifest_path_resolution_audit"] = "manifest_path_resolution_audit.json"
        write("preservation_before.json", before)
    changed = [name for name, value in hashes.items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != value]
    after.update(files_verified=len(hashes), changed_files=changed,
        predecessor_hash_violations=before["hash_violations"],
        git_commit=git("rev-parse", "HEAD").strip(), git_status=git("status", "--short"),
        tracked_diff=git("diff", "HEAD", "--name-only"))
    after["preservation_passed"] = (before["preservation_passed"] and not changed
        and not after["tracked_diff"].strip() and after["git_commit"] == before["git_commit"])
    write("preservation_after.json", after)
    test = read("pretest_summary.json")
    missing = before["missing_authority_documents"]
    assert missing, "This finalizer is only for a missing-authority hard stop"
    gates = {f"G{i}": dict(status="not_evaluated", violations=None,
             reason="Implementation blocked before complete frozen authority read") for i in range(1, 11)}
    gates["G11"] = dict(status="passed" if after["preservation_passed"] else "failed",
                         violations=len(changed) + len(before["hash_violations"])
                         + int(bool(after["tracked_diff"].strip()))
                         + int(after["git_commit"] != before["git_commit"]))
    predecessor_names = ["docs/MILESTONE_4R_B1D2_REPORT.md",
        "results/milestone_4r_b1d2/acceptance.json", "results/milestone_4r_b1/hierarchy.json",
        "results/milestone_4r_b1d/landmark_manifest.json", "results/milestone_4r_b1d2/boundary_manifest.json"]
    predecessor = {name: hashes[name] for name in predecessor_names}
    decision = "B2-1 blocked; do not proceed to deployable/long-haul scaling."
    acceptance = dict(milestone="4R-B2-B21", version="preflight-blocked-v1",
        status="blocked_before_implementation", semantic_identity="Exact Small-Domain Multi-Stop Validation",
        naming_provenance="Available theory/protocol headers: Milestone 5 / legacy namespace 4R-B2; requested artifact namespace retained",
        date="2026-10-05", timezone="Asia/Shanghai", H_ref=4,
        protocol_hash=read("protocol_snapshot_hash.json")["sha256"],
        predecessor_hashes=predecessor, test_counts=dict(pre=test, final=None),
        stage_case_counts=dict(A=0, B=0, C=0), preregistered_stage_case_counts=dict(A=20, B=64, C=32),
        gates=gates, REF_FLAT_F_mismatch_count=None, REF_HIER_F_mismatch_count=None,
        D_on_D_off_mismatch_count=None, result_status_counts=dict(attained=0, unattained=0, infeasible=0),
        lost_action_count=None, duplicate_action_count=None, bound_admissibility_violations=None,
        no_discretization_status="not_evaluated_no_solver_implemented",
        peak_frontier_piece_count=None, total_frontier_pieces=None,
        maximum_diagnostic_stop_depth=None, missing_authority_documents=missing,
        preservation_passed=after["preservation_passed"],
        numerical_contract_frozen=False, REF_implemented=False, FLAT_F_implemented=False,
        HIER_F_implemented=False, B2_2_started=False, final_authorization_decision=decision)
    report_path = ROOT / "docs/MILESTONE_4R_B2_B21_REPORT.md"
    assert not report_path.exists(), "Do not overwrite existing B21 report"
    rows = "\n".join(f"| {key} | {value['status']} | {value['violations'] if value['violations'] is not None else 'NA'} |"
                      for key, value in gates.items())
    report = f"""# Milestone 4R-B2-B21 — Exact Small-Domain Multi-Stop Validation

Date: 2026-10-05 (Asia/Shanghai). **Blocked before implementation.**

## A. Scope

Requested scope is exact small-domain validation with diagnostic H_ref=4, three independent objects REF / FLAT-F / HIER-F, and no long-haul B2-2 work. No solver or comparative experiment was run.

## B. Frozen theory/preservation

The required authority read cannot be completed: `MILESTONE_4R_B2_FORMAL_SPEC.md` and `MILESTONE_4R_B2_THEORY_AUDIT.md` are absent. A filesystem search under `/home/dy/HiRoute` found neither. The ordered authority read could not proceed past the missing B2 formal specification. After the user suggested a B21-like name, the three available B2 document headers and the protocol's frozen-theory list were inspected to resolve aliases. Protocol Section 1 (lines 52–59) explicitly requires the B2 formal specification and B2 theory audit separately from the T7 documents; no alias or replacement was declared. Later documents were not substituted for missing authorities. The protocol was archived byte-for-byte without treating that snapshot as completion of the ordered semantic read. Available headers identify “Milestone 5 / legacy namespace 4R-B2”; the requested legacy output namespace and B21 semantic identity are retained.

Git commit: `{before['git_commit']}`. The working tree already contained untracked accepted one-stop source, specifications and evidence. Their initial status is preserved; untracked status alone was not classified as an unauthorized change. Accepted tracked diff is empty. Preservation rechecked {len(hashes):,} files and {before['expected_hash_records_verified']:,} expected hash records from {len(before['manifests'])} manifests. Predecessor hash violations: {len(before['hash_violations'])}; changed files after tests: {len(changed)}. Graph basenames in the boundary manifest were resolved using the frozen boundary builder's declared graph directory; the audit correction is recorded separately and changed no predecessor file.

Full pre-tests: **{test['tests']} tests, {test['failures']} failures, {test['errors']} errors, {test['skipped']} skips**, exit code {test['exit_code']}. Full log/XML and before/after preservation records are archived under `results/milestone_4r_b2_b21/`. No final implementation suite was run because implementation never started. These pre-tests validate the existing repository, not B21.

Protocol SHA-256: `{acceptance['protocol_hash']}`.

Predecessor hashes:

""" + "\n".join(f"- `{name}`: `{value}`" for name, value in predecessor.items()) + f"""

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
{rows}

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

**{decision}**

Restore/provide the two frozen authority documents, then resume the required ordered read before freezing numerics or implementing REF, FLAT-F and HIER-F. Do not replace the missing documents with newly inferred specifications. B2-2 was not started.
"""
    report_path.write_text(report)
    acceptance["report_sha256"] = digest(report_path)
    write("acceptance.json", acceptance)
    print(json.dumps(dict(status=acceptance["status"], pretests=test,
        preservation_passed=after["preservation_passed"], files_verified=len(hashes))))


if __name__ == "__main__":
    main()
