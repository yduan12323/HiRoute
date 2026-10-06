"""Record the unwaived algebra hard stop, with no changes to any predecessor."""
import json
import subprocess
from fractions import Fraction as R
from pathlib import Path
from preflight import ROOT, OUT, counts, digest, write


def read(name):
    return json.loads((OUT / name).read_text())


def main():
    final = counts(OUT / 'final_tests.xml')
    import xml.etree.ElementTree as ET
    failed = [t.attrib['name'] for t in ET.parse(OUT / 'final_tests.xml').getroot().iter('testcase')
              if t.find('failure') is not None or t.find('error') is not None]
    assert failed == ['test_alg4_mandatory_charge_congruence'], failed
    assert final['tests'] == read('pretest_summary.json')['tests'] + 6
    assert final['failures'] == 1 and final['errors'] == final['skipped'] == 0
    hashes = read('frozen_input_hash_manifest.json')
    changed = [n for n, h in hashes.items()
               if not (ROOT / n).is_file() or digest(ROOT / n) != h]
    historical = read('historical_b21_v0_hash_manifest.json')
    historical_changed = [n for n, h in historical.items()
                          if not (ROOT / n).is_file() or digest(ROOT / n) != h]
    freeze = read('contract_freeze_manifest.json')
    freeze_changed = [n for n, h in freeze.items() if digest(OUT / n) != h]
    tracked = subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=ROOT, text=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)
    assert not changed and not historical_changed and not freeze_changed and not tracked.strip()
    assert commit == read('git_before.json')['git_commit']
    after = dict(git_commit=commit, git_status=status, tracked_diff=tracked,
        files_verified=len(hashes), changed_files=changed,
        historical_files_verified=len(historical), historical_changed_files=historical_changed,
        contract_freeze_changes=freeze_changed, preservation_passed=True,
        unauthorized_changes=0, accepted_predecessor_tests_failed=0,
        pre_tests=read('pretest_summary.json'), final_tests=final,
        failed_new_contract_tests=failed, historical_failed_tests_modified_or_waived=False,
        full_REF_v1_implemented=False, full_FLAT_P_implemented=False,
        HIER_P_implemented=False, B2_2_started=False)
    write('preservation_after.json', after)
    write('final_test_summary.json', dict(**final, exit_code=1,
        failed_tests=failed, accepted_predecessor_tests_failed=0,
        test_scope='Entire configured tests/ population plus six new exact diagnostic tests',
        archived_v0_failed_tests='Unmodified outside configured testpaths; original failed logs/XML preserved'))
    # This supplies physical realizations of the already frozen input labels;
    # it does not change the hand object, optimizer, or expected result.
    write('physical_realization_certificate.json', dict(
        scope='Explanatory realizations of the original frozen input branches, not a new case',
        initial_energy='30', capacity='60', overhead='300',
        A=dict(prefix=[[1, 'C']], origin_to_site1=dict(time='350', consumption='0'),
               site1_to_current=dict(time='350', consumption='30'),
               first_charge='u, 0 < u <= 1', first_charge_time='60 u',
               current_energy='u', current_time='1000 + 60 u', rho='0'),
        B=dict(prefix=[[2, 'C']], origin_to_site2=dict(time='338', consumption='29'),
               site2_to_current=dict(time='339', consumption='2'),
               first_arrival='1', first_departure='5/2', first_charge='3/2',
               first_charge_time='54', current_energy='1/2', current_time='1031', rho='1'),
        common_next_C=dict(output_energy='1', overhead='300'),
        exact_recheck=dict(A_u_quarter_next_C_time='1342', B_next_C_time='1349'),
        endpoints_and_all_charges_strictly_positive=True,
        charging_law='Unchanged canonical 60-kWh charging evaluator',
        assertion='A is an attained open-energy PWA prefix; B is a valid attained singleton prefix realization'))

    gates = {f'V1-G{i}': dict(status='not_evaluated', violations=None,
        reason='Hard stop at first branch-closure / ALG-4 hand object') for i in range(13)}
    gates['V1-G0'] = dict(status='failed', violations=1, scope='ALG-4 hand object; other algebra laws unrun')
    gates['V1-G1'] = dict(status='passed', violations=0, audited_pairs=55)
    gates['V1-G2'] = dict(status='failed', violations=1,
        scope='Branchwise infimal C closure is not closed under the mandated attained reduction algebra')
    gates['V1-G12'] = dict(status='passed', violations=0,
        frozen_files_verified=len(hashes), historical_files_verified=len(historical))
    write('correctness_gates.json', gates)
    authorities = {a['resolved_path']: a['actual_sha256'] for a in read('authority_manifest.json')['authorities']}
    acceptance = dict(milestone='5-B21', version='v1', date='2026-10-05', timezone='Asia/Shanghai',
        status='blocked_theory_contradiction', completion_rule_satisfied=False,
        authority_hashes=authorities,
        protocol_hash=authorities['MILESTONE_5_B21_EXACT_VALIDATION_PROTOCOL_V1.md'],
        numerical_contract_hash=digest(OUT / 'numerical_contract.json'),
        git_commit=commit, git_status_before=read('git_before.json')['git_status'], git_status_after=status,
        pre_test_counts=read('pretest_summary.json'), final_test_counts=final,
        accepted_predecessor_tests_failed=0, ALG_audits=read('algebra_audit.json'),
        permanent_regression_exact_key=None,
        permanent_regression_expected_key=dict(J=44950, Q=76, H=3, Pi=[[2,'C'],[3,'C'],[4,'S']]),
        permanent_regression_status='not_run_after_algebra_hard_stop',
        reset_regression_counts=dict(completed=0, required=10),
        Stage_counts=dict(A=0, B=0, C=0), required_Stage_counts=dict(A=20, B=64, C=32),
        gates=gates, REF_v1_FLAT_P_mismatch_count=None, REF_v1_HIER_P_mismatch_count=None,
        D_on_D_off_mismatch_count=None, ALG4_hand_object_mismatch_count=1,
        lost_action_count=None, duplicate_action_count=None, Region_bound_violations=None,
        equal_primary_prune_violations=None,
        case_status_counts=dict(attained_optimum=None, infimum_unattained=None, infeasible=None),
        case_status_scope='Full solvers and populations not executed',
        peak_attained_branch_count=None, peak_total_PWA_pieces=None,
        total_frontier_pieces=None, maximum_diagnostic_depth=None,
        intended_reference_depth=4, preservation_status='verified_unchanged',
        unauthorized_preservation_changes=0, historical_files_archived=len(historical),
        solver_implementation_status=dict(REF_v1='not_implemented', FLAT_P='not_implemented', HIER_P='not_implemented'),
        failed_contract='ALG-4 / M5-C5 as asserted with branchwise infimal C closure M5-C6 and the attained/limit-only reduction contract',
        failure_classification='theory contradiction',
        final_authorization_decision='B21-v1 blocked. Do not begin deployable/long-haul work.',
        B2_2_started=False)

    table = '\n'.join(f"| {name} | {g['status']} | {g['violations'] if g['violations'] is not None else 'NA'} |"
                      for name, g in gates.items())
    report = f'''# Milestone 5 — B21-v1 Exact Multi-Stop Validation

2026-10-05 (Asia/Shanghai). **B21-v1 blocked.** The first exact C-closure hand object fails the mandatory ALG-4 attained-set congruence under the prescribed branchwise infimum and attained/limit-only reduction semantics. No Stage A/B/C expansion or full solver implementation follows this hard stop.

## A. Scope and authority

The research specification and frozen accepted one-stop/B1-D2 contracts were read before the Core Theory, Core Audit, and B21-v1 protocol, in that order. The three supplied Milestone-5 artifacts are at the repository root rather than the prompt's `docs/` paths. They are byte-identical to all three expected hashes; the resolved paths, hashes and immutable snapshots are archived in the new namespace. No missing theory was reconstructed and no historical B2 rule controls this probe.

| Authority | Verified SHA-256 |
|---|---|
| Core Theory v1 | `{authorities['MILESTONE_5_MULTISTOP_CORE_THEORY_V1.md']}` |
| Core Audit v1 | `{authorities['MILESTONE_5_MULTISTOP_CORE_THEORY_AUDIT_V1.md']}` |
| B21-v1 protocol | `{authorities['MILESTONE_5_B21_EXACT_VALIDATION_PROTOCOL_V1.md']}` |

Git commit: `{commit}`. Exact initial/final Git statuses are retained. This is a correctness hard-stop report, not completed B21 acceptance. No long-haul, holdout or deployment work was started.

## B. Preservation baseline

Before diagnostic implementation, **{read('pretest_summary.json')['passed']} accepted predecessor tests passed**, with no failures, errors or skips. Preservation checked **{len(hashes):,} files** against **{read('preservation_before.json')['expected_hash_records_verified']:,} expected hash records**, including B1-D2 acceptance/report/source/output hashes, hierarchy, landmarks, boundaries, protected substrate and historical evidence. The dedicated B21-v0 archive manifest covers **{len(historical)} files**, including its report, acceptance, failed logs/XML, original 76-kWh fixture, REF certificates, operator traces, dominance witness and the prior missing-authority attempt. All remain byte-identical after this run.

Final configured full-suite run plus the six new diagnostics: **{final['passed']} passed, {final['failures']} failed**, no errors/skips. The sole new failure is `test_alg4_mandatory_charge_congruence`; all {read('pretest_summary.json')['passed']} accepted predecessor tests still pass. The assertion is ordinary and unwaived. Historical v0 diagnostic tests remain outside configured `tests/` testpaths; their original two failed assertions and failed logs/XML are preserved unchanged. No xfail, expected-failure marker, waiver or weakened comparison was introduced.

## C. Algebraic architecture laws and exact counterexample

The numerical contract and hand object/analytic certificate were frozen before evaluation. All branch mathematics uses exact rational arithmetic and zero semantic tolerance. The planned deterministic seed is 52101 with 50 objects in each required generation category; generation was not executed after the first hard-stop witness. ALG-4 has one evaluated object and one violation. ALG-1/2/3/5/6/7/8/9/10 remain unrun, rather than being presented as passing.

Both inputs are attained labels at index `(v,r=1,k=1)`:

| Input | Energy domain | Completion time | rho | Prefix |
|---|---|---|---:|---|
| A | (0,1] | 1000+60 E_a | 0 | (Site 1,C) |
| B | {{1/2}} | 1031 | 1 | (Site 2,C) |

At E_a=1/2, A has time 1030 < 1031 and rho 0 < 1. The exact same-energy safe rule therefore allows removal of B. Both prefix labels have physical charging/drive realizations under the unchanged curve, recorded in `physical_realization_certificate.json`. B's singleton is an attained label in the finite hand set; this object does not claim that B is an exhaustive prefix-family domain.

Apply semantic C at Site 3, h=300, and exact output energy E_d=1. The frozen primitive is F(E)=36 E on this interval. For A, strict charging gives 0 < E_a < 1 and

    t'_A = 1000 + 60 E_a + 300 + 36(1-E_a)
         = 1336 + 24 E_a.

Its infimum is 1336, unattained. For B, the executable result is

    t'_B = 1031 + 300 + 36(1-1/2) = 1349.

The required branchwise infimal C summary stores A's 1336 as a limit-only object and B's 1349 as an attained object. With the required separation, limit-only A cannot delete attained B. Thus, at E_d=1:

| Order | Represented attained labels after reduction |
|---|---|
| R(C(R(X))) | empty |
| R(C(X)) | (1349, rho=1, ((2,C),(3,C))) |

The comparator checks exact attained `(t,rho,pi)` sets, not IDs or segmentation. A single exact energy witness suffices to disprove global semantic equivalence; it is not an SOC grid. The two sides have the same lower infimum, which does not make their represented attained label sets equal.

The input safe-dominance theorem itself is not refuted: A can replay B's charge at E_a=1/2 to finish at 1348, or use E_a=1/4 to finish at 1342. Both are attained and beat B. **Those noninfimal attained A outputs are missing from the prescribed per-family infimal-time summary.** For every attained A output with E_a=u>0, choosing u/2 gives another strictly earlier attained output, with the same final energy/rho/tuple. There is no earliest attained A at E_d=1.

Consequently the proof's dominating executable replacement need not belong to any attained minimum branch. Core Theory section 19 requires every deleted attained label to have a retained attained dominator; section 26 keeps the branchwise infimum; the audit sections 5 and 9 require earliest attained Pareto branches and prohibit limit-only deletion. These conditions do not justify the asserted ALG-4 equality for this finite open-domain input. Retaining a finite collection of arbitrary attained A times would not supply the exact earliest attained Pareto frontier: its earliest retained time always misses another smaller legal time.

The audit explicitly permits transforming both layers and recomputing attainment (section 9, rule 4). That does not identify an attained C minimum for A in this hand object, nor permit using a limit-only C result to delete B. A future revised representation may carry full feasible-family information or a continuation certificate, but that is not silently substituted for the frozen attained-set congruence in this run.

## D. Permanent B21-v0 counterexample regression

Not run after the algebra hard stop. Its required key remains **(44950 s,76 kWh,3,((2,C),(3,C),(4,S)))**. The original fixture and all old failure evidence are unchanged. This report does not claim that the new architecture passes that regression.

## E. Reset adversarial regressions

0/10 completed. The independent analytic hand object is an algebra/closure disproof, not a substitute for any of the preregistered ten cases. No expected result or case was replaced after observation.

## F. Independent REF-v1

The full REF-v1 solver was not implemented. No sequence enumeration or comparative optimization population was run. The hand expectation is derived analytically, independently of reduction, by the exact affine expression above. Neither the existing historical reference nor a frontier routine supplies that derivation. REF-v1 independence/population gates remain NA.

## G. FLAT-P representation and implementation

Only a narrowly scoped literal contract probe was written, entirely under `results/milestone_5_b21_v1/`. It evaluates one finite input reduction, one branchwise C regime and attained-only output reduction. It is not a completed FLAT-P, REF-v1 or HIER-P solver. No accepted source was changed. The probe uses no old earliest-time merge, strict-g rule, cross-energy dominance, SOC grid, charge quantum, neutral action or heuristic cap.

## H. Stage A/B/C population completion

| Population | Completed | Required |
|---|---:|---:|
| Legacy Stage A | 0 | 20 |
| Synthetic Stage B | 0 | 64 |
| Bounded-real Stage C | 0 | 32 |

The remaining algebra population, permanent/reset regressions, solver implementations, candidate selection manifest and later suites were not executed after the failed mandatory architecture gate.

## I. V1-G0 through V1-G12

| Gate | Status | Violations |
|---|---|---:|
{table}

V1-G2's failure scope is the same C-closure hand object. V1-G1 covers the independent charging primitive audit: positive powers 100/60/30 kW, energy breaks 0/30/48/60 kWh, and **55** segment-interior/breakpoint/multisegment/zero-length interval checks. Its rational integral and the unchanged evaluator agree within the frozen binary64 audit policy. No charging law was changed. V1-G12 is the completed before/after preservation audit. Other solver-wide gates are not inferred from these narrow probes. NA means unmeasured, never zero violations.

## J. D-on/D-off dominance audit

The full D-on/D-off solver comparison is unrun. The hand deletion witness uses the identical state and identical energy 1/2, with t_A=1030<t_B=1031 and rho_A=0<rho_B=1; the tuple rule's equal-rho condition is not needed. There are zero cross-energy deletions in this single probe. No full-population zero mismatch is claimed.

## K. Hierarchy coverage, refinement and bounds

HIER-P is unimplemented. Coverage, refinement, bounds and equality-node audits are NA. Frozen hierarchy/landmark/boundary artifacts remain unchanged. No Region-average state or executable Region representative was introduced.

## L. Attained versus limit-only behavior

At E_d=1, A's infimal time 1336 is correctly nonattained and B's 1349 is executable. The contradiction is not caused by turning q>0 into q>=0. For the exact A witness E_a=1/4, charge is 3/4 and completion 1342. A legal S suffix with h=300, [a,b]=[2000,2100], D=100 waits to a and completes at **2100**, attained. Therefore missing noninfimal executable realizations cannot simply be dismissed as irrelevant to all future optimal attained outputs.

This observation does not claim a globally solved case or a new theory. It pinpoints the missing attained replacement in the stated closure/congruence argument. No primary/secondary status comparison from full solvers was run.

## M. Frontier complexity

Only the local probe is measured: two attained input pieces; one safe singleton deletion; left C summary has zero attained objects and one limit-only object at the exact witness energy; right summary has one attained object and one limit-only object. Full per-state/per-case branch/piece/split/intersection accounting is NA. The probe's counts are not substituted for full solver complexity tables.

## N. Runtime

The preservation hash audit and pre/final full test timings are in their logs/summaries. The rational closure hand probe took {read('runtime_table.json')['closure_probe_seconds']:.6f} seconds. REF enumeration/regime optimization, FLAT propagation/reduction, HIER bounds/refinement and leaf materialization are unrun and remain null. Runtime has no acceptance threshold or scalability interpretation.

## O. Limitations

B21-v1 is incomplete. The theorem/operator diagnostic addresses one exact open-domain C regime only. No full solver comparison, CS operator population, permanent regression, generated/real suite, Region audit or incumbent-derived depth validation was completed. The failing assertion remains unwaived. No Core Theory v1.1 or alternative frontier design was implemented.

## P. Decision

**B21-v1 blocked.** Classification: **theory contradiction** in the asserted branchwise C closure / attained-set ALG-4 congruence contract. A safe attained input replacement can have only an unattained infimal summary after C, while an attained dominated-family output remains represented when C precedes reduction. The required zero-violation architecture gate fails.

Stop here. **Do not authorize or begin deployable/long-haul multi-stop work.** The existing B21-v0 failure and its original 76-kWh expected winner remain preserved exactly.
'''
    report_path = ROOT / 'docs/MILESTONE_5_B21_V1_REPORT.md'
    with report_path.open('x') as stream:
        stream.write(report)
    acceptance['report_sha256'] = digest(report_path)
    acceptance['evidence_sha256'] = {str(p.relative_to(OUT)): digest(p)
        for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
        and p.name != 'acceptance.json'}
    write('acceptance.json', acceptance)
    print(json.dumps(dict(decision=acceptance['final_authorization_decision'],
        final_tests=final, preservation_passed=True, historical_files_unchanged=len(historical))))


if __name__ == '__main__':
    main()
