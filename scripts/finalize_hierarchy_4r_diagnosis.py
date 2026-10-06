"""Finalize diagnostic-only B1-E after audits, full tests and preservation."""
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
from _common import ROOT,sha256
from _stopplan4r_common import write_json,verify_protected


def table(frame,columns):
    lines=['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']
    for _,row in frame.iterrows():
        values=[]
        for c in columns:
            value=row[c]
            values.append('NA' if pd.isna(value) else str(value))
        lines.append('| '+' | '.join(values)+' |')
    return '\n'.join(lines)


def main():
    out=ROOT/'results/milestone_4r_b1e';d=ROOT/'results/milestone_4r_b1d'
    read=lambda name:json.loads((out/name).read_text())
    before=read('preservation_before.json');changes=[]
    for p,h in before['files'].items():
        if not (ROOT/p).is_file() or sha256(ROOT/p)!=h:changes.append(p)
    protection=verify_protected()
    tracked=subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert not changes and protection['passed'] and not tracked.strip() and commit==before['git_commit']
    for p,h in read('diagnostic_protocol.json')['source_sha256'].items():assert sha256(ROOT/p)==h
    after=dict(files_verified=len(before['files']),unauthorized_changes=changes,accepted_protection=protection,
        tracked_changes=tracked,git_commit=commit,git_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
        hierarchy_sha256=before['hierarchy_sha256'],landmark_manifest_sha256=before['landmark_manifest_sha256'])
    write_json(out/'preservation_after.json',after)
    suites=list(ET.parse(out/'final_tests.xml').getroot().iter('testsuite'))
    tests={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    assert not any(tests[k] for k in ['failures','errors','skipped'])
    audit=pd.read_csv(out/'E1_E5_audit.csv');assert len(audit)==480
    gates={k:dict(status='passed',violations=int(audit[k].sum())) for k in ['E1','E2','E3','E4','E5']}
    gates['E6']=dict(status='passed',violations=len(changes))
    assert all(g['violations']==0 for g in gates.values())
    s=read('diagnostic_summary.json');w=s['workload'];inc=s['incumbent'];rec=read('structural_recommendation.json')
    levels=pd.read_csv(out/'three_level_summary.csv');fp=pd.read_csv(out/'false_positive_summary.csv')
    fp['fraction']=fp.fraction.map(lambda v:f'{v:.2%}')
    gaps=pd.read_csv(out/'certificate_decomposition_strata.csv')
    gaps_display=gaps.copy()
    for name in ['median_G_landmark','p95_G_landmark','median_G_residual','p95_G_residual']:
        gaps_display[name]=gaps_display[name].map(lambda x:f'{x:.3f}')
    gaps_display['sum_landmark_fraction']=gaps_display.sum_landmark_fraction.map(lambda x:f'{x:.2%}')
    gcols=['value','nodes','median_G_landmark','p95_G_landmark','median_G_residual','p95_G_residual','sum_landmark_fraction']
    work_rows=[]
    for name in ['N_region','N_bound','N_envelope','N_exact','N_semantic']:
        work_rows.append(dict(component=name,flat=w['flat_totals'][name],hierarchy=w['hier_totals'][name]))
    work_table=table(pd.DataFrame(work_rows),['component','flat','hierarchy'])
    levelcols=['method','regions_created','regions_popped','refinements','leaves','candidate_checks','exact_evaluator_calls','semantic_evaluations']
    counter=pd.read_csv(out/'perfect_static_counterfactual_effect.csv')
    counter['PS_vs_ALT_reduction']=counter.PS_vs_ALT_reduction.map(lambda x:f'{x:.2%}')
    depth_table=table(levels,['method','median_max_depth','median_case_depth','prune_cost','prune_envelope','prune_energy','prune_schedule'])
    gate_table=table(pd.DataFrame([dict(gate=k,**v) for k,v in gates.items()]),['gate','status','violations'])
    oracle=json.loads((d/'b1_oracle_classification.json').read_text())
    report=f'''# Milestone 4R-B1E — Deployable Baseline & Certificate Decomposition

Date: 2026-10-02 (Asia/Shanghai). **Post-hoc diagnosis only. E1–E6 have zero violations.**

## A. Scope

B1-E diagnoses frozen B1-D v1 on all 480 development cases. It introduces no
algorithm improvement, weighted work score or new confirmatory success threshold.
The existing hierarchy, eight landmarks, static buckets, epsilon=0 search,
incumbent policy, exact evaluator and numerical tolerances remain unchanged.
Perfect-static calculations are offline counterfactuals and are not deployable.

## B. Frozen evidence

The pre-existing full suite passed **187 tests** before diagnostic computation.
The final full suite passed **{tests['tests']} tests**, with no failures, errors or skips.
Before/after manifests verified **{after['files_verified']:,} frozen files**, including
all B1-D primary outputs, code hashes, landmark arrays, Region summaries, accepted
baseline/protection manifests and archived blocker evidence. There were zero
unauthorized changes and no accepted tracked-source/output diff.
The Git commit remains `{commit}`; exact statuses are archived in the manifests.

Hierarchy hash: `{before['hierarchy_sha256']}`.
Landmark-manifest hash: `{before['landmark_manifest_sha256']}`.
The unchanged tree has 60,498 Sites, 2,047 Regions and 1,024 leaves. The original
eight landmarks and Ccap/S0cap/SCcap membership are preserved. B1-D uses ALT
outward adjustment `1e-6 + 2e-8*(abs(a)+abs(b))`, a further 1e-5 s cost adjustment,
and nextafter toward minus infinity; B1-E imports these functions read-only.

New evidence is under `results/milestone_4r_b1e/`. No historical report, result,
search/config file, accepted evaluator, graph or hierarchy was overwritten.
Native routing compilation uses a separate B1-E cache. No dependency was installed.
The accepted memory guards passed; observed diagnostic peak RSS was
{read('diagnostic_completion.json')['peak_rss_mib']/1024:.3f} GiB.

## C. Historical outcomes retained

**B1-O strong GO.** The approved positive-denominator population has 387 cases;
93 zero-semantic cases remain NA. Its median logical reduction remains
{oracle['macro_conditional_median_reduction']:.2%}, with micro reduction
{oracle['micro_workload_reduction']:.2%}.

**B1-D v1 deployable gate failed.** B1-D v1 was exact and deployable in the sense
of no online Region scans. Its preregistered semantic-denominator workload gate
failed (median -183.95%, micro -146.41%), while correctness and the clean timing
gate passed. **That historical failure is not retroactively reversed.**
The separate [B1 report](MILESTONE_4R_B1_REPORT.md) and
[B1-D report](MILESTONE_4R_B1D_REPORT.md) are unchanged.

## D. Fair deployable baseline

The reconstructed flat method uses the same pre-evaluation information as B1-D:
all 2,749 root Ccap Sites for energy_only; all 45,129 S0cap plus 2,480 SCcap Sites
for energy_and_scheduled. It knows no performed roles or exact Site costs before
evaluation. Shared fastest-route time/actual-length arrays have the same accepted
semantics as the hierarchy.

Both methods call the **identical frozen `exact_leaf` function object**: exact
envelope check; unchanged accepted evaluator for envelope-pass candidates;
performed-effect classification; semantic filtering; accepted plan-key tie rule.
The flat method seeds zero-stop separately and compares it with the exact semantic
Site result. A file-access guard prohibits oracle per-Site reads during the flat
call. All 480 reconstructed flat optima/tie keys and envelope/exact/semantic counts
match the frozen paired flat control. Oracle evidence is read only afterward for
offline diagnostic audits. No semantic filtering is used to construct flat candidates.

## E. Workload-vector comparison

All-case totals retain distinct operations:

{work_table}

N_region means popped Region/bucket nodes; N_bound counts created nonempty bound
nodes, including those rejected at creation. No weighted equivalent-Site score
is used. All paid envelope checks count, even cheap rejects. The semantic
denominator is retained for historical B1-D reporting, not substituted for the
deployable flat workload in this descriptive comparison.

Envelope-check reduction: median **{w['macro']['R_envelope']['median']:.2%}**, all-case
micro **{w['micro']['R_envelope']:.2%}**. Exact-evaluator-call reduction: median
**{w['macro']['R_exact']['median']:.2%}**, all-case micro
**{w['micro']['R_exact']:.2%}**. Metric-defined case counts are respectively
{w['macro']['R_envelope']['defined_cases']} and {w['macro']['R_exact']['defined_cases']}.
These are effect sizes, not a new pass/fail gate.

Each method's CSV/Parquet includes the full requested W vector. T_envelope and
T_exact are **NA** because frozen measurements did not separate those components.
Historical paired T_search and T_e2e are retained with provenance; bound, lookup,
refinement and combined leaf times are separately available for the hierarchy.
No new deployable timing was inferred from diagnostic runtime. Historical search
time reduction has case median {w['macro']['R_search_historical']['median']:.2%} and
aggregate ratio reduction {w['micro']['R_search_historical']:.2%}; historical
end-to-end ratio reduction is {w['micro']['R_e2e_historical']:.2%}, reflecting shared
routing dominance. **Timing diagnosis is limited**: envelope/exact splits and
time-to-incumbent are unavailable, and original cache/timing limitations remain.
No H0 serialization runtime or perfect-static runtime is used as a deployable comparator.

## F. Perfect-static construction

For each of 30 ODs, independent full-node SSSPs produce d_T from origin/to
destination and d_D from origin/to destination on the accepted directed edges.
For every static Region/bucket, exhaustive offline scans produce the four exact
minima, finite counts and unreachable counts. d_D remains shortest-distance
length, not the actual length of the selected fastest-time route.

The saved audit population covers **all {s['audited_ALT_nodes']:,} frozen ALT8 visited
nodes** across all cases. Every recomputed minimum matches its frozen B1-D audit
value within 1e-5 metric units. The minima Parquet pairs exact and ALT8 values,
bucket sizes and reachability counts.

Perfect-static bounds call the same B1-D `cost_bound`: same Pmax=100 kW,
charging relaxation, overhead, nuisance, envelope, energy and schedule tests,
and numerical safety. Each node independently normalizes against its own
perfect-static parent. `L_PS_raw` and `L_ALT_raw` are safety-adjusted values before
parent normalization. Component minima can come from different Sites; this
relaxation remains intentionally unchanged.

The counterfactual index is passed to the **unchanged frozen `deploy_search`**,
retaining root buckets, heap tie order, zero-stop policy, exact leaves and epsilon=0.
The index's exhaustive metric inputs make it nondeployable. Its runtime is
excluded from all deployable-performance claims.

## G. E1–E6

{gate_table}

E1 verifies common code identity and all 480 reconstructed flat results/counts.
E2 checks perfect-static admissibility and infeasibility decisions against the
exact semantic minimum for every semantic-populated ALT8 view and every visited
perfect-static replay node. All 480 replay optima and complete tie keys also match.
E3 checks L_ALT<=L_PS on every frozen visited node with independent parent
normalization. E4 checks the decomposition identity on all semantic-populated
views. E2/E3/E4 use the explicit **2e-6 s** audit tolerance, retained from B1-D's
cost audit; the maximum identity residual is {s['maximum_identity_error']:.3g} s.
E5 checks the exact per-case FP/TP partition and aggregate candidate reconciliation.
E6 verifies frozen algorithms, inputs, outputs and protected evidence after tests.
No frozen implementation defect was found or repaired.

## H. Certificate decomposition

For each of **{s['semantic_populated_nodes']:,} semantic-populated nodes**:

G_landmark = L_PS - L_ALT;
G_residual = J_sem* - L_PS;
J_sem* - L_ALT = G_landmark + G_residual.

G_landmark median/P95: **{s['median_G_landmark']:.3f} / {s['p95_G_landmark']:.3f} s**.
G_residual median/P95: **{s['median_G_residual']:.3f} / {s['p95_G_residual']:.3f} s**.
Landmark loss accounts for {s['summed_landmark_share']:.2%} of summed total slack
and exceeds residual loss in {s['landmark_larger_node_fraction']:.2%} of these nodes.
These are descriptive node-weighted summaries, not independent statistical samples.
Medians of components are not added to construct a median total.

There are {s['false_positive_only_nodes']:,} false-positive-only static views.
Their semantic minimum and residual gap are NA; no target is fabricated.
Raw signed components are stored without clipping. The previous signed
G_cert_old=L_oracle-L_deploy is copied exactly (median
{s['historical_old_gap_median']:.3f} s) and checked against frozen artifacts.
The new common-target identity is preferred for interpretation and does not
replace or rewrite the historical quantity.

Bucket strata:

{table(gaps_display[gaps_display.dimension.eq('bucket')],gcols)}

Depth strata:

{table(gaps_display[gaps_display.dimension.eq('depth')],gcols)}

Envelope, SOC, scenario and OD strata are also provided in
`certificate_decomposition_strata.csv`.

## I. Three-level search comparison

{table(levels,levelcols)}

B1-O counts are **logical oracle work**: its semantic membership and oracle
summary scans were already paid offline and are not actual computational savings.
The B1-O exact-call column denotes logical leaf evaluator work only. Perfect-static
counts are paid operations in an **offline counterfactual**, not deployable work.
ALT8 counts are the actual frozen deployable work. Created nodes count nonempty
views consistently; B1-O empty creation attempts are separately retained per case.

{depth_table}

Depth columns summarize per-case deepest created bound and median created-bound
depth. The per-case three-level table retains all 480 cases, including zero-semantic
cases; no cherry-picked ODs are used. Prune counts retain envelope, energy,
schedule and cost reasons separately.

Counterfactual changes from ALT8 to exact static minima:

{table(counter,['component','ALT_total','PS_total','PS_vs_ALT_reduction'])}

These isolate the effect of metric approximation while keeping the same static
action superset and resource relaxation. They are not a proposed deployed algorithm.

## J. Leaf false-positive decomposition

Exactly **706,117** paid ALT8 leaf checks were assigned once each, in the required
order FP1 envelope, FP2 inbound energy, FP3 later energy, FP4 schedule, FP5 other,
FP6 feasible but effect-free, TP semantic. Inbound and later energy checks use
the accepted evaluator; schedule feasibility uses its accepted start candidates.
Archived per-Site feasibility/effects serve only as offline terminal truth.
Any undeclared concrete rejection would have stopped diagnosis.

{table(fp,['category','count','fraction'])}

Terminal counts: FP1={s['FP_terminal_counts']['FP1']:,},
FP2={s['FP_terminal_counts']['FP2']:,}, FP3={s['FP_terminal_counts']['FP3']:,},
FP4={s['FP_terminal_counts']['FP4']:,}, FP5={s['FP_terminal_counts']['FP5']:,},
FP6={s['FP_terminal_counts']['FP6']:,}, TP={s['FP_terminal_counts']['TP']:,}.
Their sum exactly equals frozen candidate checks in every case; all non-FP1
checks reconcile to exact evaluator calls, and TP reconciles to semantic evaluations.
Energy has precedence over schedule when both fail. Bucket, scenario, SOC,
envelope, OD and leaf-depth counts/fractions are in `false_positive_strata.csv`.

## K. Incumbent acquisition

Zero-stop initialized a finite incumbent in **{inc['zero_initialized']} cases**;
**{inc['no_initial_U_cases']}** started without one. A Site incumbent was acquired
in {inc['first_site_acquired']} cases; {inc['no_site_update']} had no Site update.
Missing Site updates remain NA and are not treated as delayed infinite incumbents
when zero-stop already supplied finite U.

The frozen heap order is reconstructed from saved bound decisions and verified
against every trace's cumulative candidate count. Counts are **through the first
successful leaf batch**, including its pop and all batch candidates, consistent
with the frozen batch update policy. Median/P95 pops to first Site incumbent:
**{inc['median_pops_to_first_site']:.1f} / {inc['p95_pops_to_first_site']:.1f}**.
Median candidate/exact checks to first Site incumbent:
{inc['median_candidate_checks_to_first_site']:.1f} / {inc['median_exact_calls_to_first_site']:.1f}.
Median/P95 fraction of refinements completed by then:
**{inc['median_refinement_fraction']:.2%} / {inc['p95_refinement_fraction']:.2%}**.
Among cases lacking zero-stop U, that fraction is
{inc['no_initial_U_median_refinement_fraction']:.2%} / {inc['no_initial_U_p95_refinement_fraction']:.2%};
{inc['no_initial_U_sum_refinements_before']:,} of their
{inc['no_initial_U_sum_total_refinements']:,} total refinements preceded/accompanied
the first Site update. These quantify delay without changing acquisition strategy.

Per-case initial/first/final costs, pops, refinements, candidate/exact calls and
fractions are saved in `incumbent_acquisition.csv`. Time-to-first-incumbent is
NA because frozen traces did not record it reliably. No time is inferred from
operation counts. The structural interpretation below distinguishes incumbent
delay from the counterfactual effect of tighter bounds.

## L. Structural diagnosis

{rec['diagnosis']}

{rec['incumbent_interpretation']}

The fair deployable comparator explains why the historical negative semantic
reduction can coexist with avoided online work. It does not erase certificate
looseness or reverse the original workload gate. Residual slack remains a mixture
of static false positives, independently minimized components, shortest-distance
versus fastest-route actual length, and optimistic charging power. B1-E does not
invent an unsupported finer attribution among those residual terms.

## M. Next hypothesis

Exactly one primary next hypothesis: **{rec['primary_next_hypothesis']}**.

{rec['rationale']}

This recommendation is post-hoc and requires a separate preregistered next-stage
design. No remedy, extra landmark, new filter, hierarchy redesign or new threshold
was implemented in B1-E. Secondary observations do not constitute additional
primary recommendations. The experiment stops here.

## N. Limitations

Development data only; post-hoc diagnosis; the frozen zero/one-stop semantic domain;
fixed envelopes and canonical charging curve; no holdout, no real multi-stop
claim, no China benchmark, no active-information Go-2, no elevation/temperature
energy model. The perfect-static replay requires offline exhaustive scans and is
not deployable. Node-weighted gap summaries are dependent and conditional on
visited populations. Counts are fully reconciled; timing decomposition remains
limited as stated. B1-E produces a structural diagnosis, not a new GO/NO-GO verdict.

Reproduction: `run_hierarchy_4r_diagnosis.py` (refuses to overwrite a started run),
`analyze_hierarchy_4r_diagnosis.py`, and `finalize_hierarchy_4r_diagnosis.py`.
New diagnostic helpers are confined to `src/hierarchy4r/diagnosis.py`.
`diagnostic_protocol.json` freezes formulas, tolerances, scope and timing limits;
per-case Parquets retain minima, decompositions, PS bounds/traces/leaves and the
full paid-candidate classification. `acceptance.json` records audit status,
historical outcomes, recommendation, tests and preservation hashes.
'''
    report_path=ROOT/'docs/MILESTONE_4R_B1E_REPORT.md';report_path.write_text(report)
    source=[ROOT/'src/hierarchy4r/diagnosis.py',*list((ROOT/'scripts').glob('*hierarchy_4r_diagnosis.py')),
        *list((ROOT/'tests').glob('test_hierarchy4r_diagnosis*.py'))]
    acceptance=dict(milestone='4R-B1E',status='completed_diagnostic_only',audit_gates=gates,
        no_confirmatory_classification=True,historical_outcomes=before['historical_outcomes'],
        summary=s,recommendation=rec,tests=tests,protected_artifact_verification=after,
        source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in source},
        report_sha256=sha256(report_path),
        artifact_sha256={str(p.relative_to(ROOT)):sha256(p) for p in sorted(out.rglob('*'))
            if p.is_file() and p.name not in ['acceptance.json','finalization.log'] and '__pycache__' not in str(p)},
        B1_D2='not run',B2='not run',China_benchmark='not run',holdout='not run',Go2='not run')
    write_json(out/'acceptance.json',acceptance)
    print('B1-E diagnosis complete; E1–E6 zero violations');print(tests);print(rec['primary_next_hypothesis'])


if __name__=='__main__':main()
