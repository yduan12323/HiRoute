"""Close the final one-stop iteration after correctness, tests and preservation."""
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
from _common import ROOT,sha256
from _stopplan4r_common import write_json,verify_protected

STAGE='B1-D2 is the final one-stop algorithmic iteration. After B1-D2, the one-stop method is frozen and the next research milestone is B2 multi-stop formalization. B1 may be reopened only for a fundamental correctness defect, not for additional performance tuning.'


def table(df,columns):
    return '\n'.join(['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']+[
        '| '+' | '.join('NA' if pd.isna(row[k]) else str(row[k]) for k in columns)+' |' for _,row in df.iterrows()])


def tests(path):
    suites=list(ET.parse(path).getroot().iter('testsuite'))
    return {k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}


def main():
    out=ROOT/'results/milestone_4r_b1d2';d=ROOT/'results/milestone_4r_b1d'
    read=lambda p:json.loads((out/p).read_text())
    before=read('preservation_before.json');changes=[]
    for p,h in {**before['files'],**before['archive_sha256']}.items():
        if not (ROOT/p).is_file() or sha256(ROOT/p)!=h:changes.append(p)
    protection=verify_protected();tracked=subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert not changes and protection['passed'] and not tracked.strip() and commit==before['git_commit'],'F7 preservation failure'
    boundary=read('boundary_manifest.json');protocol=read('experiment_protocol.json')
    for p,h in {**boundary['extraction_code_sha256'],**protocol['source_sha256']}.items():assert sha256(ROOT/p)==h,p
    for p,h in boundary['artifact_sha256'].items():assert sha256(out/p)==h,p
    assert sha256(out/'boundary_manifest.json')==protocol['boundary_manifest_sha256']
    assert sha256(ROOT/'scripts/analyze_hierarchy_4r_boundary.py')==read('lookup_profile_protocol.json')['source_sha256']
    hierarchy=sha256(ROOT/'results/milestone_4r_b1/hierarchy.json')
    landmark=sha256(d/'landmark_manifest.json')
    after=dict(files_verified=len(before['files']),archive_files_verified=len(before['archive_sha256']),unauthorized_changes=changes,
        accepted_protection=protection,tracked_changes=tracked,git_commit=commit,git_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
        hierarchy_sha256=hierarchy,landmark_manifest_sha256=landmark,boundary_manifest_sha256=sha256(out/'boundary_manifest.json'))
    write_json(out/'preservation_after.json',after);write_json(out/'f7_frozen_component_audit.json',dict(status='passed',violations=0,**after))
    pre=tests(out/'preexisting_tests.xml');post=tests(out/'final_tests.xml')
    assert pre['tests']==207 and not any(pre[k] or post[k] for k in ['failures','errors','skipped'])
    gates={'F1':dict(status='passed',violations=boundary['F1_violations'],audited_regions=2047)}
    for gate,name in [('F2','f2_boundary_lb_audit.csv'),('F3','f3_alt_ba_ps_ordering.csv'),('F4','f4_ba_cost_admissibility.csv'),('F6','f6_no_hidden_scan.csv')]:
        a=pd.read_csv(out/name);assert len(a)==480
        gates[gate]=dict(status='passed',violations=int(a.violations.sum()),audited_nodes=int(a.audited_nodes.sum()))
    f5=pd.read_csv(out/'f5_exact_preservation.csv');assert len(f5)==480 and f5.full_key_equal.all() and f5.static_action_coverage_preserved.all()
    gates['F5']=dict(status='passed',violations=int(f5.F5_mismatches.sum()),exact_cases=480)
    gates['F7']=dict(status='passed',violations=0,files_verified=after['files_verified'])
    gates={k:gates[k] for k in sorted(gates)};assert all(g['violations']==0 for g in gates.values())
    s=read('descriptive_summary.json');w=s['work_totals'];b=s['boundary'];h=s['H_bound'];tm=s['timing'];env=s['envelope']
    work=pd.read_csv(out/'three_level_work_totals.csv');complexity=pd.read_csv(out/'boundary_complexity_by_depth.csv')
    c=complexity[(complexity.depth.astype(str)=='all')&complexity.quantity.isin(['ingress','egress','union'])]
    hs=pd.read_csv(out/'bound_headroom_strata.csv');rs=pd.read_csv(out/'ba_residual_gap_strata.csv')
    hwork=pd.DataFrame([dict(component=k,median=v['median'],p95=v['p95'],defined_cases=v['defined'],micro=v['micro']) for k,v in s['H_work'].items()])
    time_table=pd.DataFrame([dict(component=k,ALT8=tm['ALT8'][k]['total'],BA=tm['BA'][k]['total']) for k in ['lookup_seconds','bound_seconds','boundary_seconds','leaf_seconds','refinement_overhead_seconds','search_seconds','shared_routing_seconds','end_to_end_seconds','ALT_metric_lookup_replay_seconds']])
    reductions={k:1-w['BA'][k]/w['ALT8'][k] for k in ['candidate_checks','exact_evaluator_calls','refinements']}
    report=f'''# Milestone 4R-B1D2 — Boundary-Augmented Deployable Metric Bounds

Date: 2026-10-03 (Asia/Shanghai). All 480 exact cases completed; F1–F7 have zero violations.

## A. Scope and stage rule

**{STAGE}**

This final development experiment isolates directed Region boundary **travel-time**
information added to frozen ALT8. Performance is descriptive on the same development
cases used by B1-E. There is no new GO/NO-GO threshold, weighted workload score,
positive-epsilon comparison, or performance-based reopening of one-stop research.

## B. Frozen evidence

The current pre-implementation full suite passed **207 tests**, no failures, errors
or skips. The final suite passed **{post['tests']} tests**, also without failures,
errors or skips. An intermediate run had 234 passes and one failure in a newly
added synthetic fixture whose Site ID and OSM ID disagreed. The fixture was
corrected without changing algorithm code; its failed log/XML and explanation
remain archived as `final_tests_invalid_new_fixture.*` and
`test_fixture_correction.json`. Before/after verification covers **{after['files_verified']:,} frozen
files**, {after['archive_files_verified']} archived prior-attempt files and all accepted
protection manifests. No accepted tracked source/output differs; no protected hash
changed. Git remains `{commit}`. Exact status is retained in both preservation files.

The prior 2026-10-02 attempt stopped on a pre-existing protected `.gitignore` change
and two preservation-test failures. That blocker report, acceptance, logs and diff
are retained unchanged under `blocked_attempt_2026_10_02/`. The protected file was
restored before this resumed run; this history is not erased or counted as a current
algorithm defect. No frozen algorithm was repaired during B1-D2.

Hierarchy SHA-256: `{hierarchy}`.
Landmark-manifest SHA-256: `{landmark}`.
Boundary-manifest SHA-256: `{after['boundary_manifest_sha256']}`.

The accepted 2,047 Regions, 1,024 leaves, 60,498 attached Sites, eight landmarks,
Region memberships, static Ccap/S0cap/SCcap buckets, energy distance bounds,
charging/schedule/evaluator semantics and incumbent/tie policy remain unchanged.
All new evidence is confined to the B1-D2 result directory and this report;
new implementation consists only of boundary extraction/lookup/augmentation and
experiment diagnostics. No dependencies were installed. Peak experiment RSS was
{read('experiment_completion.json')['peak_rss_mib']/1024:.3f} GiB; existing guards passed.

## C. Boundary construction

For every frozen road-node cell V_R, ingress contains in-cell endpoints of directed
edges entering from outside; egress contains in-cell endpoints of directed edges
leaving to outside. Boundaries use the accepted **11,561,067 directed edges** and
**5,892,498 road nodes**, never geometry, Site positions or undirected adjacency.
The original OSM-rank cell file is mapped back to accepted node IDs. All Site
attachment cells independently match the frozen leaf membership artifact.

Extraction repeated with reversed edge iteration yields identical sorted arrays;
repeated Parquet serialization has identical SHA-256. Every stored endpoint has a
cross-cell edge witness, and every directed crossing contributes its endpoint.
The manifest contains graph, hierarchy, extraction-code and per-Region hashes.
Boundary membership/index files, complexity and safety were frozen before search.

{table(c,['quantity','median','p95','max','total'])}

Sizes are boundary references across Regions, not distinct graph-wide nodes.
The depth table also retains median/P95/max/totals and ratios against road-node,
Site and each static-bucket count; zero denominators remain NA. A node may be in
both boundaries. Storage is **{b['artifact_storage_bytes']:,} bytes** for the primary
membership/index artifacts (excluding the duplicate reconstruction witness).
Extraction took **{b['preprocessing_seconds']:.3f} s**, peak RSS
**{b['preprocessing_peak_rss_mib']:.1f} MiB**. No compactness threshold was introduced.

## D. F1–F7

{table(pd.DataFrame([dict(gate=k,**v) for k,v in gates.items()]),['gate','status','violations'])}

F1 covers all Regions and directed cross-cell edges. F2 covers **{s['audited_BA_nodes']:,}**
created nonempty BA Region/buckets, including immediate infeasibility rejects:
boundary delta and max(ALT,delta) never exceed exact static time minima within
1e-5 s. Offline minima are recomputed independently, inaccessible to online search.
F3 checks independently parent-normalized L_ALT <= L_BA <= L_PS within **2e-6 s**.
F4 checks L_BA <= J_sem* and safe infeasibility for **{s['semantic_populated_nodes']:,}**
semantic-populated nodes. The other **{s['false_positive_only_nodes']:,}** nodes have
no semantic target; J_sem and residual fields remain NA.

F5 checks objective and complete accepted plan key in every case. F6 records zero
Site-ID reads, evaluator calls, oracle reads and additional SSSPs in every bound;
actual ingress/egress reads are recorded separately. A file-open guard rejects
oracle evidence access during deployable searches. F7 verifies all frozen inputs,
algorithms, manifests and historical outputs, plus the frozen new boundary artifact.
Explicit empty violation tables are emitted. Per-node numerical evidence is in
`alt_ba_ps_bound_audit.parquet`; per-case gate summaries are separate CSVs.

Boundary reduction uses float64 and the fixed rule
`max(0, nextafter(min - (1e-6 + 2e-8*abs(min)), -inf))`.
Origin/destination inside a cell, empty boundary, or all-unreachable values return
conservative zero. Existing exact current-query arrays supply min-reductions;
there is no boundary routing. The shared two time/actual-length SSSPs per OD are
unchanged; separate offline distance SSSPs support audits only.

The max-combined time bounds feed the unchanged B1-D `cost_bound`, retaining the
same distance inputs, charging relaxation, Pmax=100 kW, overhead, nuisance,
schedule/envelope logic, 1e-5 s downward cost safety and parent maximum. Raw ALT,
raw boundary, combined time, raw cost and parent-normalized costs are saved.
Boundary reductions are cached per Region per case across static buckets; actual
cache-hit reads are zero. This cache contains no Site quantities.

## E. Exactness

All **480/480 epsilon=0** BA optima match the B1 semantic flat reference in accepted
objective and full `(rounded cost, charged energy, stop count, Site-ID tuple)` key.
Zero-stop remains separate; no neutral role is added. Frozen static root/leaf
candidate memberships reconcile exactly without duplication, so semantic action
coverage is preserved. Every pruned semantic-populated node has an admissible
bound and no false infeasibility. All 480 paired ALT8 controls also reproduce their
frozen optimum keys and workload counts exactly.

The search uses the original `deploy_search` and `exact_leaf` functions unchanged:
same heap order, zero-stop seed, envelope check, exact Site evaluator, performed
effects, semantic filtering and tie rule. Only time-bound inputs are augmented.

## F. ALT8 vs BA vs perfect-static

{table(work,['method','regions_created','regions_popped','refinements','leaves','candidate_checks','exact_evaluator_calls','semantic_evaluations'])}

The primary ALT8 counts are frozen B1-D v1; perfect-static counts are frozen B1-E
nondeployable counterfactuals; BA counts are this run. Candidate checks are exact
Site envelope checks, including cheap rejects. BA reduces envelope checks by
**{reductions['candidate_checks']:.2%}**, exact evaluator calls by
**{reductions['exact_evaluator_calls']:.2%}**, and refinements by
**{reductions['refinements']:.2%}** against ALT8 in aggregate. Operations remain
separate and no weighted score is used. Perfect-static runtime is excluded.

## G. Bound headroom recovery

For semantic-populated BA-visited nodes with L_PS>L_ALT,
H_bound=(L_BA-L_ALT)/(L_PS-L_ALT). Defined nodes: **{h['defined']:,}**.
Median **{h['median']:.2%}**, P25 **{h['p25']:.2%}**, P75 **{h['p75']:.2%}**,
P95 **{h['p95']:.2%}**. Raw values are retained without clipping; zero denominators
remain NA. PS tightens both time and distance metrics, while BA tightens time only,
so the remaining headroom also includes the deliberately frozen distance certificate.

{table(hs[hs.dimension.eq('bucket')],['value','defined','median','p25','p75','p95'])}

`bound_headroom_strata.csv` includes depth, bucket, scenario, OD, SOC and envelope
strata. These dependent, visit-conditioned node summaries are descriptive.

## H. Work headroom recovery

H_work=(N_ALT-N_BA)/(N_ALT-N_PS), only where N_ALT>N_PS.
Micro values use the corresponding aggregate totals; no combined scalar is formed.

{table(hwork,['component','defined_cases','median','p95','micro'])}

Per-case raw values and NA denominators are in `work_headroom_recovery.csv`.

## I. Envelope-pruning migration

ALT8 Region envelope prunes: **{env['ALT_region_envelope_prunes']:,}**;
BA: **{env['BA_region_envelope_prunes']:,}**.
ALT8 paid leaf envelope rejects: **{env['ALT_leaf_envelope_rejects']:,}**;
BA: **{env['BA_leaf_envelope_rejects']:,}**.
Exactly **{env['former_ALT_FP1_avoided']:,} ({env['fraction_avoided']:.2%})** former ALT8
FP1 Site checks are avoided. **{env['former_ALT_FP1_retained']:,}** remain paid and
**{env['new_BA_FP1']:,}** BA rejects were not paid by ALT8; both changes are retained
rather than assuming nested search populations.

The smaller number of Region-envelope rejections does not imply a weaker bound:
BA creates fewer descendant views. Prune counts alone do not measure the number
of candidate checks avoided. Every avoided check has a witness identifying its old leaf and BA terminal ancestor,
prune reason and depth. Median upward movement is **{s['upward_depth']['median']:.1f}**
levels, P95 **{s['upward_depth']['p95']:.1f}**. The depth/reason distribution and
OD/SOC/envelope strata accompany the per-case reconciliation. A cost or schedule
prune can also avoid an old envelope reject: only witnesses explicitly labeled
`infeasible_envelope` are direct Region-envelope rejection. Bound tightening changes
search order and U arrival as a consequence; the incumbent policy is unchanged.
No improvement is attributed to a new energy certificate or action filter.

## J. Boundary cost and timing

Ingress reads: **{b['ingress_reads']:,}**; egress reads: **{b['egress_reads']:,}**;
total: **{b['total_reads']:,}**. Actual reads per visited Region (across its buckets
within one case) have median **{b['reads_per_visited_region']['median']:.1f}**,
P95 **{b['reads_per_visited_region']['p95']:.1f}**, maximum
**{b['reads_per_visited_region']['maximum']:.0f}**.
Boundary lookup/min-reduction time totals **{b['boundary_lookup_seconds']:.3f} s**,
**{b['fraction_bound_time']:.2%}** of BA Region-bound time.
Reads per avoided envelope check: **{b['reads_per_envelope_avoided']:.2f}**;
reads per avoided exact evaluation: **{b['reads_per_exact_avoided']:.2f}**.
These ratios do not imply equivalent computational cost.

Timing totals (seconds):

{table(time_table,['component','ALT8','BA'])}

ALT8 and BA use one paired pass with the same shared routing arrays, alternate
execution order by case, and no explicit cache flush or warm-up. Neither diagnostic
serialization nor offline exact-minimum scans are timed as search. The aggregate
BA/ALT search-time ratio is **{tm['search_ratio_BA_over_ALT']['aggregate']:.3f}**;
median per-case ratio is **{tm['search_ratio_BA_over_ALT']['median']:.3f}**.
Boundary load took **{tm['preprocessing']['boundary_load_seconds']:.6f} s**.
`lookup_seconds` is the frozen endpoint-landmark lookup timer. The separate
`ALT_metric_lookup_replay_seconds` measures four frozen ALT metric calculations per
visited node in an isolated alternating replay; it is not subtracted from paired
bound time and is not added to search/e2e. The BA wrapper also pays the existing
ALT cost-formula call before the augmented call; that overhead is retained.

End-to-end adds full shared OD routing to each case, identically for both methods;
unique-OD routing totals **{tm['unique_OD_shared_routing_seconds']:.3f} s** and is
reported separately to avoid confusing amortized experiment time with query cost.
Leaf time includes envelope and accepted evaluator work together. Timing is one
measurement pass with OS/cache variability, not a confirmatory timing gate.

## K. Residual gap

On the common BA-visited semantic population:

{table(rs[rs.dimension.eq('all')],['metric','defined','median','p95'])}

G_ALT=J_sem*-L_ALT, G_BA=J_sem*-L_BA, G_PS=J_sem*-L_PS.
All raw rows and depth/bucket strata are retained. Remaining gaps reflect the
unchanged relaxation, static action superset and metric approximations; this run
does not assign an unsupported finer decomposition or repair them. Node-population
changes mean these medians need not equal the earlier B1-E visited-node medians.

## L. Historical context

**B1-O strong GO. B1-D v1 deployable gate failed.** Both historical outcomes remain
unchanged; B1-D correctness and clean timing had passed. B1-E identified dominant
metric-certificate loss and the large paid envelope-rejection class, motivating
this isolated boundary-time test. B1-D2 reports the effect sizes above without
retroactively relabeling B1-D or adding a post-hoc success threshold. Topology-derived
boundary information tightens the deployable time certificate; its measured search
benefit and scan cost are reported componentwise, without claiming architectural
optimality. Residual looseness is documented future work, not another iteration.

Development data only; zero/one-stop only; no independent holdout, China benchmark,
multi-stop implementation or active-information experiment was run.

## M. One-stop freeze

**One-stop method frozen after B1-D2.** No fundamental correctness defect was found.
F1–F7 passed, all exact cases and evidence are complete, and protected artifacts
were reverified. Poor performance or unused headroom cannot open B1-D3. The frozen
boundary manifest, experiment protocol, source hashes and acceptance preserve this
final one-stop variant for subsequent formal work.

## N. Transition

**Next milestone: B2 multi-stop formalization.** B2 implementation was not started.

**One-stop development frozen. Proceed next to B2 multi-stop formalization.**

Reproduction entry points: `build_hierarchy_4r_boundary.py`,
`run_hierarchy_4r_boundary.py`, `analyze_hierarchy_4r_boundary.py`, and
`finalize_hierarchy_4r_boundary.py`. Build/run refuse to overwrite frozen started
artifacts. All new tests and raw gate/work/timing evidence are retained.
'''
    report_path=ROOT/'docs/MILESTONE_4R_B1D2_REPORT.md';report_path.write_text(report)
    sources=[ROOT/'src/hierarchy4r/boundary.py',*sorted((ROOT/'scripts').glob('*hierarchy_4r_boundary.py')),*sorted((ROOT/'tests').glob('test_hierarchy4r_boundary*.py'))]
    acceptance=dict(milestone='4R-B1D2',version='1.0',status='completed',final_one_stop_iteration=True,stage_rule=STAGE,
        git_commit=commit,git_status=after['git_status'],pre_tests=pre,post_tests=post,protected_artifact_status='verified_unchanged',
        hierarchy_sha256=hierarchy,landmark_manifest_sha256=landmark,boundary_manifest_sha256=after['boundary_manifest_sha256'],Region_count=2047,
        boundary_node_totals={k:boundary[k] for k in ['ingress_references','egress_references','union_references']},gates=gates,
        exact_preservation_cases=480,ALT_BA_PS_work_totals=w,boundary_read_totals={k:b[k] for k in ['ingress_reads','egress_reads','total_reads']},
        H_bound=h,H_work=s['H_work'],timing_summary=tm,one_stop_freeze_status='frozen',fundamental_correctness_defect=False,
        next_milestone='B2 multi-stop formalization',B2_implementation='not_started',no_new_performance_gate=True,
        historical_outcomes=['B1-O strong GO','B1-D v1 deployable gate failed'],protected_artifact_verification=after,
        report_sha256=sha256(report_path),source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in sources},
        artifact_sha256={str(p.relative_to(ROOT)):sha256(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ['acceptance.json','finalization.log'] and '__pycache__' not in str(p)})
    write_json(out/'acceptance.json',acceptance)
    print('F1–F7 passed; 480 exact cases; '+str(post));print('One-stop development frozen. Proceed next to B2 multi-stop formalization.')

if __name__=='__main__':main()
