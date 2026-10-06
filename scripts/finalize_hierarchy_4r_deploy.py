"""Write B1-D report/acceptance only after correctness, tests and preservation."""
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
from _common import ROOT,sha256
from _stopplan4r_common import write_json,verify_protected


def main():
    out=ROOT/'results/milestone_4r_b1d';old=ROOT/'results/milestone_4r_b1'
    read=lambda name:json.loads((out/name).read_text())
    a=read('analysis.json');g=read('correctness_gates.json');lm=read('landmark_manifest.json')
    pre=read('preprocessing.json');projection=read('memory_projection.json');oracle=read('b1_oracle_classification.json')
    before=read('preservation_before.json');changes=[]
    for key in ['files','source_sha256']:
        changes.extend(p for p,h in before[key].items() if not (ROOT/p).exists() or sha256(ROOT/p)!=h)
    checkpoint=json.loads((old/'preservation_checkpoint.json').read_text())['files']
    changes.extend(p for p,r in checkpoint.items() if sha256(ROOT/p)!=r['sha256'])
    archive=json.loads((old/'resume_preservation_before.json').read_text())['archived_hashes']
    changes.extend(p for p,h in archive.items() if sha256(ROOT/p)!=h)
    protection=verify_protected()
    frozen=read('query_preregistration.json')
    changes.extend(p for p,h in frozen['source_sha256'].items() if sha256(ROOT/p)!=h)
    assert sha256(old/'hierarchy.json')==lm['hierarchy_sha256']==frozen['hierarchy_sha256']
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert commit==before['git_commit']=='20b658257fb67655e09229411783935e17084fa4'
    assert not changes and protection['passed']
    # Verify that the earlier closure changed only the explicitly approved files.
    original=read('preservation_before_closure.json')
    closure_changes=[p for p,h in original['files'].items() if sha256(ROOT/p)!=h]
    assert set(closure_changes)==set(before['approved_statistical_changes'])
    protection.update(B1_files_verified=len(before['files']),B1_sources_verified=len(before['source_sha256']),
        checkpoint_files_verified=len(checkpoint),archived_hashes=archive,changes=changes,
        approved_closure_changes=closure_changes,hierarchy_sha256=lm['hierarchy_sha256'],git_commit=commit,
        git_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True))
    write_json(out/'preservation_after.json',protection)
    suites=list(ET.parse(out/'final_tests.xml').getroot().iter('testsuite'))
    tests={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    assert not any(tests[k] for k in ['failures','errors','skipped'])
    assert g['passed'] and g['cases']==480 and a['correctness_passed']
    work=pd.read_csv(out/'work.csv');timing=pd.read_csv(out/'timing_summary.csv').set_index('component')
    reasons=pd.read_csv(out/'prune_reasons.csv');gap=pd.read_csv(out/'certificate_gap_strata.csv')
    landmarks='\n'.join(f'| {d} | {n} | {o} |' for d,n,o in zip(['E','W','N','S','NE','SE','NW','SW'],lm['landmarks'],lm['osm_ids']))
    gate_rows='\n'.join(f'| {k} | {v} | pass |' for k,v in g['violations'].items())
    reason_rows='\n'.join(f'| {r.decision} | {r.count:,} | {r.fraction:.2%} |' for r in reasons.itertuples())
    gap_rows='\n'.join(f'| {r.value} | {r.views:,} | {r.median_G_cert:.3f} | {r.p95_G_cert:.3f} |' for r in gap[gap.dimension.eq('bucket')].itertuples())
    depth_rows='\n'.join(f'| {r.value} | {r.views:,} | {r.median_G_cert:.3f} | {r.p95_G_cert:.3f} |' for r in gap[gap.dimension.eq('depth')].itertuples())
    slack=pd.read_csv(out/'landmark_slack_strata.csv')
    sl=slack[slack.dimension.eq('bucket')].pivot(index='value',columns='metric',values='median_slack')
    slack_rows='\n'.join(f'| {bucket} | {row.tm:.2f} | {row.tp:.2f} | {row.dm/1000:.2f} | {row.dp/1000:.2f} |' for bucket,row in sl.iterrows())
    energy_fraction=float(reasons.loc[reasons.decision.str.contains('energy'),'fraction'].sum())
    timing_rows='\n'.join(f'| {component} | {row.median_seconds:.6f} | {row.p95_seconds:.6f} |' for component,row in timing.iterrows())
    one_sided=pd.read_csv(out/'distance_vs_fastest_length.csv')
    assert one_sided.violations.sum()==0
    runtime=pd.read_csv(out/'landmark_runtime.csv')
    routing=pd.read_csv(out/'shared_routing.csv')
    storage=dict(summary_payload_bytes=2047*3*2*8*4*8,
        summary_npy_bytes=(out/'summaries.npy').stat().st_size,
        counts_npy_bytes=(out/'counts.npy').stat().st_size,
        children_npy_bytes=(out/'children.npy').stat().st_size,
        summary_parquet_bytes=(out/'region_landmark_summaries.parquet').stat().st_size,
        leaf_membership_bytes=sum(p.stat().st_size for p in (out/'leaf_buckets').glob('*.json')),
        query_additional_memory_guard_gib=10,
        provenance='Summary payload derived from the frozen 2047x3x2x8x4 float64 shape; observed disk sizes. Query memory projection is the guard in the frozen query source.')
    write_json(out/'storage_accounting.json',storage)
    timing_statement=('passed' if a['timing_gate_passed'] else 'failed') if a['timing_gate_passed'] is not None else 'unresolved'
    report=f'''# Milestone 4R-B1D — Deployable Region Bounds

Date: 2026-10-02 (Asia/Shanghai). **{a['classification']}. D1–D5 all pass.**

## A. Scope

This experiment tests deployable one-stop Region lower bounds on the existing
binary topology-first hierarchy. It adds fixed static capability summaries and
eight directed landmarks; it does not redesign the tree or the stop domain.
The B1 action-effect amendment remains unchanged. Zero-stop is separate; only
actual C/S/CS effects make a Site action semantic. No neutral role was added.
The earlier blocker and H0 migration audit remain in the separate
[B1 report](MILESTONE_4R_B1_REPORT.md) and archived blocker evidence.

## B. B1-O statistical closure

The explicitly approved zero-denominator clarification closes the B1-O gate
without rerunning its hierarchy or changing oracle traces. Of **480 cases**,
**387** have a positive semantic denominator and **93** have r=NA, labelled
`no_semantic_site_pruning_opportunity`. All cases remain in correctness and runtime.
The conditional macro median is **{oracle['macro_conditional_median_reduction']:.2%}**;
P(r>=50%)={oracle['p_reduction_ge_50']:.2%}, P(r>=25%)={oracle['p_reduction_ge_25']:.2%}.
The all-case micro reduction is **{oracle['micro_workload_reduction']:.2%}**.
The unchanged thresholds classify B1-O as **{oracle['classification']}**.
`b1_oracle_classification.json/csv` and B1's `zero_denominator_policy.json`
record the population and authority. Pre-closure report and acceptance copies
are retained in this new result namespace. Oracle reductions describe logical
pruning potential, not saved oracle preprocessing computation.

## C. Preservation

The pre-implementation full suite passed **153 tests**. The final full suite
passed **{tests['tests']} tests**, with zero failures, errors or skips.
The frozen accepted baseline commit remains `{commit}`. Git changes are
untracked milestone files; no accepted tracked source/output was changed.
The full before/after manifests record Git status, accepted source hashes,
{len(checkpoint)} protected checkpoint files, {len(before['files'])} B1 evidence files,
archived blocker hashes, and the five authorized closure edits.
Final protected-artifact verification passed with zero unexpected changes.
No dependency installation or new geographic data was used.

The frozen hierarchy hash is
`{lm['hierarchy_sha256']}`:
60,498 attached Sites, 2,047 Regions, 1,024 leaves, branching factor 2,
primary capacity 64, including the accepted co-attached early leaf of size 65.
Existing Region IDs, membership and parking Sites were preserved.

## D. Frozen landmarks

The candidate set is the largest directed SCC ({lm['largest_scc_nodes']:,} nodes).
The equirectangular projection is centered on all graph-node coordinates
(longitude {lm['centroid_lon']:.12f}, latitude {lm['centroid_lat']:.12f}).
Normalized directions use descending projection score, then ascending OSM/node
identity; repeated extrema advance to the next unique node. This list was saved
before comparative queries and was selected twice identically.

| Direction | Graph node ID | OSM node ID |
|---|---:|---:|
{landmarks}

The SCC restricts landmark selection only. Sites and queries outside it remain
eligible; unavailable finite landmark terms safely contribute zero.

## E. Preprocessing

Two independent metrics use exactly the accepted directed edges: travel time
and physical-distance shortest paths. The distance metric d_D is **not** the
actual length L_T of the selected fastest route. The original fastest-route
evaluator is unchanged. Across 30 ODs and both directions, independent checks
verified d_D<=L_T for **{int(one_sided.checked.sum()):,} attached-Site legs**, with
zero violations (audit tolerance 1e-5 m).

There are 32 full-node float64 memory-mapped arrays, preserving IEEE infinities
and graph node order, with per-array hashes and graph/config input hashes.
Array payload projection: {projection['array_bytes']:,} bytes; stored arrays
including headers: **{pre['array_disk_bytes']:,} bytes**. The projected additional
RSS was {projection['projection_gib']:.3f} GiB and passed the accepted 38 GiB RSS /
10 GiB available-memory reserve guards. Observed preprocessing peak RSS was
**{pre['peak_rss_mib']/1024:.3f} GiB**; query peak was
**{a['query_peak_rss_mib']/1024:.3f} GiB**.
The query driver separately checked a 10 GiB additional-memory projection before
graph loading and retained per-OD memory guards.

Total preprocessing took {pre['runtime_seconds']:.3f} s, including graph loading,
selection, array hashing/repeat checks and summaries. Logged SSSP/storage work
took {runtime.seconds.sum():.3f} s; Region summaries took {pre['summary_seconds']:.3f} s.
The summary Parquet is {pre['summary_disk_bytes']:,} bytes; query arrays separately
store min/max/count/children. Ccap has 2,749 Sites; scheduled support partitions
into 45,129 S0cap and 2,480 SCcap Sites. These are static supersets, not effects.
The fixed summary shape implies {storage['summary_payload_bytes']:,} payload
bytes; the observed summary NPY is {storage['summary_npy_bytes']:,} bytes.
`storage_accounting.json` additionally records counts, children and leaf-ID disk
sizes, separate from the compact Parquet summary.

Every Region/bucket/landmark stores forward/reverse min and max. Infinite maxima
are retained, never replaced by finite maxima. Empty buckets create no bound
node. Independent bottom-up reconstruction exactly matched all summaries and
counts; the static audit checked all 6,141 Region/bucket views and every leaf ID.
The four direction/metric arrays for landmark 0 were recomputed exactly;
the remaining arrays use the same deterministic SSSP primitive.

For each finite ALT difference, the implementation subtracts
`1e-6 + 2e-8*(abs(a)+abs(b))` in the metric's units, then applies nextafter
toward minus infinity. The relative allowance exceeds 8*n*float64 epsilon
for this fixed nonnegative graph. Cost bounds subtract a further 1e-5 s and
round downward. Accepted feasibility tolerances remain intact. No inf-inf is
evaluated. Charging lower bounds use the fixed maximum 100 kW, not minimum or
average power. Raw and parent-monotone bounds are both recorded.

## F. D1–D5

| Gate | Violations | Result |
|---|---:|---|
{gate_rows}

D1 checked all {g['coverage_semantic_actions']:,} per-case semantic actions
against the scenario's static bucket. Exact parent/child and leaf membership
verification extends coverage over every root-to-leaf path. Scheduled S0cap and
SCcap partition supported Sites; SCcap may perform S or CS.

D2 independently checked 1,296 real Region bounds before comparison, then all
**{g['visited_region_buckets']:,} visited Region/bucket bounds** against exhaustive
static Site minima for both metrics and directions. D3 checked all
**{g['semantic_populated_buckets']:,} semantic-populated views** against their exact
semantic minimum, including every infeasibility decision. There were
{g['false_positive_only_buckets']:,} false-positive-only views, reported separately.
Audits are offline and do not enter online bound construction.

D4 matched the full accepted plan key (rounded objective, charging energy,
stop count, Site identity), not just the optimal value, in all 480 cases.
D5 recorded every bound's eight landmarks, 16 summary rows, zero Site IDs,
zero evaluator calls and zero oracle table reads. There were
{g['internal_region_buckets']:,} internal views. Leaf ID access is guarded by
phase and node type. An online file-access guard rejects B1 oracle paths.
The deployable modules import no oracle bound code; independent auditing occurs
only after each timed query and clean flat control.

## G. Deployable exact results

All **480 epsilon=0** queries completed with identical B1 semantic optima and
accepted ties. Zero-stop supplied a verified initial incumbent where feasible;
otherwise search started at infinity and descended best-bound-first. Only exact
semantic leaf plans updated it. Zero-stop was ultimately selected in
{a['exact_zero_stop_selected']} cases. No optional epsilon runs were needed.

## H. Pruning/work results

Primary work counts **every reached leaf candidate check**, including exact
envelope rejects and static false positives; objective calls are separately
reported. This is conservative and cannot inflate savings by hiding work.
Flat semantic actions total **{a['flat_semantic_total']:,}**. B1-D performed
**{a['deploy_exact_total']:,} candidate checks**, including
{a['deploy_objective_calls']:,} concrete Site evaluator calls and
{a['outside_envelope_checks']:,} outside-envelope checks; only
{a['deploy_semantic_total']:,} evaluated actions were semantic.

On the 387 positive-denominator cases, the primary conditional median reduction
is **{a['macro_conditional_median_reduction']:.2%}**. All-case micro reduction is
**{a['micro_workload_reduction']:.2%}**. Negative values, if present, mean more
candidate work than the semantic flat denominator and are retained unchanged.
The 93 zero-semantic cases remain NA; they incurred
{a['zero_semantic_leaf_work']:,} candidate checks, included in the micro numerator.

The separate operational baseline checks all appropriate static candidates:
{a['flat_static_candidate_total']:,} checks across 480 cases. Against that larger
baseline, median reduction is {a['operational_median_reduction']:.2%}, micro
reduction {a['operational_micro_reduction']:.2%}. These values do not replace the
preregistered semantic-denominator metric.

## I. Oracle retention

B1-O median reduction is {a['oracle_median']:.2%}; B1-D median reduction is
{a['macro_conditional_median_reduction']:.2%}. Their ratio is
**{a['oracle_retention']:.4f}**, compared with the fixed **0.70** retention threshold.
Both medians use the same 387-case population. No excluded effect-free legacy
action was added to the semantic denominator.

## J. Timing

The clean flat control uses the same routing arrays and exact leaf routine,
without H0 observation-table serialization inside the timed section. The
separate avoided-work control times exactly the static candidates omitted by
the completed hierarchy run; routing and construction of that complement are
outside timing. Its candidate counts plus reached-leaf counts equal the full
static flat counts for every case. This isolates replaced Site work without
subtracting incomparable H0 diagnostic runtimes.

| Component | Median seconds | P95 seconds |
|---|---:|---:|
{timing_rows}

Hierarchy summary/index loading took {read('query_completion.json')['summary_load_seconds']:.6f} s.
All 480 search sections total {a['all_case_query_seconds']:.3f} s; clean flat
sections total {a['all_case_clean_flat_seconds']:.3f} s. Shared routing was
computed once per OD ({routing.shared_routing_seconds.sum():.3f} s in total) and
reused for 16 states; the per-query end-to-end columns include its full OD cost
for both methods. They are counterfactual standalone-query comparisons, not a
sum of actual experiment elapsed time. Offline exhaustive distance/cost audits
and serialization are excluded from online timing.

The original median bound+refinement versus avoided-flat-work timing gate
**{timing_statement}**. Timings are one sequential development pass with
uncontrolled Python/filesystem cache effects; they are not a production latency
guarantee. Counts and correctness do not depend on timing. Preprocessing is
reported separately and has not been amortized into a claimed speedup.

## K. Certificate diagnosis

The signed offline certificate gap G_cert=L_oracle-L_deploy has median
**{a['G_cert_median']:.3f} s** and P95 **{a['G_cert_p95']:.3f} s** over
{a['gap_views']:,} semantic-populated visited views. False-positive-only views
have no oracle semantic minimum and their gap is NA, not zero. The oracle
comparison partitions current performed effects offline and takes the minimum
valid oracle role bound for the static bucket. Signed gaps are not clipped;
parent-monotone correction can occasionally make a deployable bound stronger
than the corresponding raw oracle bound.

| Static bucket | Views | Median G_cert (s) | P95 (s) |
|---|---:|---:|---:|
{gap_rows}

| Depth | Views | Median G_cert (s) | P95 (s) |
|---|---:|---:|---:|
{depth_rows}

All requested depth, bucket, envelope, SOC, scenario and OD strata are in
`certificate_gap_strata.csv`. `landmark_slack_strata.csv` separately compares
the time and shortest-distance ALT bounds with exact static-bucket minima.
Distance is only a one-sided energy lower bound: this experiment does not
substitute shortest-distance geometry for fastest-route actual-length
oscillations or claim a new route-length certificate.

Median exact-static-minimum minus ALT-bound slack is substantial in both
independent metrics:

| Bucket | Inbound time (s) | Outbound time (s) | Inbound distance (km) | Outbound distance (km) |
|---|---:|---:|---:|---:|
{slack_rows}

| Region decision | Count | Fraction of all created bounds |
|---|---:|---:|
{reason_rows}

The three energy infeasibility reasons (inbound, charger outbound and noncharger
total energy) together prune **{energy_fraction:.2%}** of created bounds. False positives
at reached leaves total {a['false_positive_total']:,}, a rate of
**{a['leaf_false_positive_rate']:.2%}**. These are paid checks, including envelope
rejects, infeasible plans and effect-free plans. Static supersets and landmark
slack are therefore distinct sources of lost oracle pruning potential. No
landmark, bucket, hierarchy or threshold was tuned in response to these results.

## L. Gate statement

**{a['classification']}.**

The workload gate requires both median reduction >=50% and oracle retention
>=0.70. Observed values are {a['macro_conditional_median_reduction']:.2%} and
{a['oracle_retention']:.4f}; workload gate passed={a['workload_gate_passed']}.
The separately measured timing gate {timing_statement}. Correctness remains
fully passed regardless of the empirical result. B1-O strong GO identifies
oracle potential; it does not by itself establish deployable computational gains.

## M. Limitations

These results cover the 480 development cases only, the zero/one-stop semantic
domain, fixed preregistered Safe Detour Envelopes and canonical charging curve.
They make no real multi-stop claim, use no holdout, no active-information Go-2,
and no elevation/temperature energy model. The eight fixed landmarks and the
existing hierarchy were not tuned. Conditional macro reductions concern only
the 387 cases with semantic Site-pruning opportunity. Optional epsilon runs,
B2, China benchmark construction and holdout evaluation were not performed.

## Reproduction and artifacts

New results are exclusively under `results/milestone_4r_b1d`, with preserved
B1 closure copies, manifests, mmap arrays, summaries, per-case audit/search
Parquets, D1–D5 tables, work/timing tables, gap strata, test logs and acceptance.
Scripts are `preprocess_hierarchy_4r_deploy.py`, `audit_deploy_landmarks.py`,
`run_hierarchy_4r_deploy.py`, `audit_hierarchy_4r_deploy_static.py`,
`time_hierarchy_4r_deploy_avoided.py`, `analyze_hierarchy_4r_deploy.py` and
`finalize_hierarchy_4r_deploy.py`. Preprocessing and primary query scripts refuse
to overwrite completed frozen runs. Online implementation is confined to
`src/hierarchy4r/deploy.py` and `deploy_search.py`; accepted evaluator sources
remain untouched. Run the full project suite with the accepted real-data and
milestone-result flags; `final_tests.xml` records the exact final outcome.
'''
    report_path=ROOT/'docs/MILESTONE_4R_B1D_REPORT.md';report_path.write_text(report)
    sources=[ROOT/'src/hierarchy4r/deploy.py',ROOT/'src/hierarchy4r/deploy_search.py']
    sources+=list((ROOT/'scripts').glob('*deploy*.py'))
    sources+=[ROOT/'scripts/close_b1_oracle_statistics.py']
    sources+=list((ROOT/'tests').glob('test_hierarchy4r_deploy*.py'))
    acceptance=dict(milestone='4R-B1D',status='completed',correctness_passed=True,
        deployable_gate_passed=a['workload_gate_passed'] and a['timing_gate_passed'] is not False,
        classification=a['classification'],B1_O=oracle,B1_D=a,D1_D5=g,
        frozen_hierarchy_sha256=lm['hierarchy_sha256'],landmark_manifest_sha256=sha256(out/'landmark_manifest.json'),
        protected_artifact_verification=protection,tests=tests,
        report_sha256=sha256(report_path),source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in sorted(set(sources))},
        artifact_sha256={str(p.relative_to(ROOT)):sha256(p) for p in sorted(out.rglob('*'))
            if p.is_file() and p.name not in ['acceptance.json','finalization.log'] and '__pycache__' not in str(p)},
        optional_epsilon='not run',B2='not run',holdout='not run',Go2='not run')
    write_json(out/'acceptance.json',acceptance)
    print(a['classification']);print(tests);print('Protected artifacts unchanged')


if __name__=='__main__':main()
