"""Final B1 technical report and acceptance, preserving all old evidence."""
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
from _common import ROOT,sha256
from _stopplan4r_common import write_json,verify_protected


def main():
    out=ROOT/'results/milestone_4r_b1'
    h0=json.loads((out/'h0_summary.json').read_text())
    summary=json.loads((out/'oracle_analysis.json').read_text())
    hierarchy=json.loads((out/'hierarchy_preregistration.json').read_text())
    archive=json.loads((out/'resume_preservation_before.json').read_text())['archived_hashes']
    protection=verify_protected()
    checkpoint=json.loads((out/'preservation_checkpoint.json').read_text())['files']
    changes=[p for p,r in checkpoint.items() if not (ROOT/p).exists() or sha256(ROOT/p)!=r['sha256']]
    archival_changes=[p for p,h in archive.items() if sha256(ROOT/p)!=h]
    protection.update(checkpoint_files_verified=len(checkpoint),checkpoint_changes=changes,archival_changes=archival_changes)
    assert protection['passed'] and not changes and not archival_changes
    for manifest_name in ['h0_summary.json','hierarchy_preregistration.json','oracle_preregistration.json']:
        manifest=json.loads((out/manifest_name).read_text())
        for field in ['implementation_sha256','source_sha256']:
            for p,h in manifest.get(field,{}).items():assert sha256(ROOT/p)==h,p
    tests=list(ET.parse(out/'final_tests.xml').getroot().iter('testsuite'))
    counts={k:sum(int(t.attrib.get(k,0)) for t in tests) for k in ['tests','failures','errors','skipped']}
    assert not any(counts[k] for k in ['failures','errors','skipped'])
    m=pd.read_csv(out/'logical_work.csv');primary=m[m.epsilon.eq(0)]
    assert len(m)==1920 and len(primary)==480
    h2=pd.read_csv(out/'H2_all_comparisons.csv');h4=pd.read_csv(out/'H4_coverage.csv');h5=pd.read_csv(out/'H5_stability.csv')
    assert h2.passed.all() and not h4[['lost','duplicates']].any().any() and not h5.mutated.any()
    assert summary['H1_violations']==summary['H3_violations']==summary['perturbation_violations']==0
    for name in ['H1_violations','H2_mismatches','H3_violations','perturbation_violations']:
        assert pd.read_csv(out/f'{name}.csv').empty
    runtime=pd.read_csv(out/'oracle_runtime.csv')
    sensitivity=pd.read_csv(out/'epsilon_sensitivity.csv')
    gaps=pd.read_csv(out/'gap_decomposition.csv')
    leaf_sizes=[int(k) for k in hierarchy['leaf_size_distribution']]
    diameter=json.loads((out/'diameter_populated/directed_time_diagnostic.json').read_text())
    assert diameter['violations']==0
    classified=summary['classification'] in ['strong GO','gray zone','NO-GO']
    final_gate=f"B1-O {summary['classification']}" if classified else 'B1-O classification unresolved — zero semantic denominator policy required'
    role_stats=pd.read_csv(out/'stratified_work.csv');role_stats=role_stats[role_stats.dimension.eq('role')]
    role_lines='\n'.join(f"| {r.value} | {r.defined_cases} | {r.zero_semantic_cases} | {r.defined_case_median_reduction:.2%} |" for r in role_stats.itertuples())
    epsilon_lines='\n'.join(f"| {r.epsilon} | {r.cases} | {r.defined_cases} | {r.conditional_median_reduction:.2%} | {r.max_observed_gap:.6f} |" for r in sensitivity.itertuples())
    gap_lines='\n'.join(f"| {r.value} | {r.views} | {r.median_G_agg:.3f} | {r.p95_G_agg:.3f} | {r.certified_fraction:.2%} |" for r in gaps[gaps.dimension.eq('role')].itertuples())
    classification_text=(f"The explicitly authorized convention produces median r={summary['median_reduction']:.2%}, "
        f"P(r>=50%)={summary['fraction_at_least_50_percent']:.2%}, P(r>=25%)={summary['fraction_at_least_25_percent']:.2%}. "
        f"Mechanical classification: **{final_gate}**. See zero_denominator_policy.json for scope and authorization.") if classified else (
        "The amended denominator is zero in **93/480 cases** (only zero-stop remains). "
        "The specified formula is 0/0 in these cases. A clarification was requested before comparative "
        "results: either explicitly count them as r=0 within all 480 cases, or declare r undefined "
        "and explicitly change the classification population to the 387 nonempty cases. No response "
        "has been applied. Thresholds are unchanged; **no primary GO/NO-GO classification is asserted**. "
        "The conditional statistics below describe nonempty cases only and are not the preregistered "
        "480-case gate. This is an unresolved statistical-contract issue, not a correctness failure.")
    text=f'''# Milestone 4R-B1 — Exact one-stop hierarchical validation

Date: 2026-10-02 (Asia/Shanghai). **H0–H5 pass. {final_gate}. B1-D unresolved.**

## A. Scope and declared domain

Exhaustive selection of zero or one concrete vehicle stop under accepted directed
fastest-time legs and their selected-path actual lengths, within each fixed Safe
Detour Envelope. Primary configuration is unchanged: 60 kWh, 0.16 kWh/km, 6 kWh
reserve, zero robust margin, canonical 100/60/30 kW curve, 500 m support radius,
meal_count >= 1, hard compatible 2700 s activity at 0.40–0.70 baseline time,
300 s overhead, 600 s stop nuisance, no distance penalty. No arbitrary road-path
optimization, neutral role, new geographic data, dependency install or B2 work.

## Action-domain amendment and H0 migration audit

The first attempt stopped because C/S/CS capability roles did not cover the
broader accepted via-Site domain. That evidence remains unchanged in
`docs/MILESTONE_4R_B1_BLOCKER_REPORT.md`, `blocker_acceptance.json`,
`role_coverage_counterexample.json` and `reproduce_role_audit.py`.

The user approved the separate `MILESTONE_4R_B1_ACTION_DOMAIN_AMENDMENT.md`.
D_4RA retains all accepted feasible via-Site plans. D_B1 contains feasible
zero-stop separately and only Site actions with a nonempty **performed** effect:
C iff charged energy > 1e-8 kWh; S iff the active scheduled activity is actually
satisfied. Each Site plan receives one of C/S/CS, never a static capability label.
No neutral role was added. Road-path choice is not silently recast as a stop task.

H0: **480 expected, 480 evaluated, {h0['cost_mismatches']} cost mismatches,
{h0['identity_only_changes']} identity-only changes**. Excluded feasible
effect-free legacy actions: **{h0['total_feasible_effect_free_actions']:,}**.
No optimal value or selected action changed. Recomputed legacy optima match the
accepted 4R-A table in both cost and identity for every case.

`flat_actions` observes the original `assemble_plan` calls during unchanged
`best_one_stop`, returns original objects, retains the first minimum by accepted
plan_key per Site, and records zero-stop separately. It changes no evaluator
source, feasibility, objective, optimizer, ties or routing. All eligible Site IDs,
feasible/infeasible status, times, actual lengths, energies, charging, schedule,
completion and costs are saved in `flat_reference/case_*.parquet`; case JSON
contains trip, baseline, zero-stop feasibility, both optimum plans and metadata.
Full H0 tables and excluded actions are under `h0_*`.

## B. Baseline preservation and tests

Baseline commit `20b658257fb67655e09229411783935e17084fa4`; branch
`codex/milestone-4r-b1`. No user work committed. The resume pre-existing suite
passed **116 tests**. Final suite: **{counts['tests']} passed**, zero failures,
errors or skips. The 840-file historical manifest, 56 older accepted source
hashes, all 4R-A sources/inputs/results covered by the **{len(checkpoint)}-file**
checkpoint, and archived blocker hashes are unchanged. New manifests record
source hashes and input/output linkage. Old reports/results were not regenerated.

Synthetic tests cover effect/tie boundaries, coverage, exact and positive-epsilon
pruning, improved-incumbent persistence, failed margins causing refinement,
unreachable directed pairs, piecewise charging breakpoints, exact arrival/capacity/
deadline certificate margins, and disconnected/co-attached topology cells.
Initial new equality fixtures exposed decimal endpoint roundoff; fixtures were
changed to exactly representable synthetic endpoints before the comparative run.
No empirical theorem failure or post-result hierarchy tuning occurred.

## C. Frozen static hierarchy

Binary deterministic recursive BFS bisection of the road graph's weak undirected
topology, weighted only by accepted access-node Site counts. Seeds/neighbors use
stable OSM node order; earliest BFS prefix minimizing Site-count imbalance wins;
co-attached Sites never split. Directed routing semantics remain unchanged.
This is the allowed fallback after dependency feasibility inspection; the reason
for rejecting large Python KL sweeps and non-balanced community algorithms is
recorded in `hierarchy_build/partition_choice.json`. No partition alternatives
were selected by pruning outcomes.

All **60,498 attached Sites** remain in the static tree, including Sites whose
actions are excluded in particular queries. There are **2,047 Regions**, **1,024
leaves**, depth 0–10, leaf capacity 64, observed leaf sizes **{min(leaf_sizes)}–{max(leaf_sizes)}**.
One early leaf contains 65 co-attached Sites at the same road anchor; it is
explicitly recorded as unsplittable without splitting one road node. This is the
predeclared early-leaf exception, not dropped Sites or a retuned capacity.
Coverage, child disjointness and leaf uniqueness pass. Two construction runs
produce byte-identical road-cell and Region files. Primary hash:
`{hierarchy['hierarchy_sha256']}`.
The immutable preregistration was written after H0 and before comparisons.
Optional capacity 32/128 sensitivities were not run; the primary tree was not rebuilt.

## D. Correctness H0–H5

| Gate | Primary evidence | Violations |
| --- | --- | ---: |
| H0 | 480 legacy-to-semantic comparisons | 0 |
| H1 | {summary['primary_views']:,} oracle Region View bounds vs concrete costs | 0 |
| H2 | 480 epsilon=0 optima, full accepted tie keys and identities | 0 |
| H3 | {summary['certified_views']:,} certified Views, all concrete gap checks | 0 |
| H4 | Static exact partitions and all internal role-count partitions per case | 0 |
| H5 | Same hierarchy hash across all 1,920 primary/sensitivity searches | 0 |

Energy, charge and schedule perturbations: zero violations. Independent real
directed-time checks: **{diameter['tested_views']} Views**, {diameter['anchor_count']}
anchors, zero violations. The initial first-leaf diagnostic had no represented
development actions; it is retained, and a supplementary diagnostic used the
first leaf with two C actions in H0 case 0. This changed no hierarchy or experiment
cases. Uncomputed/unreachable diameter certificates are not treated as finite.
No distance-metric theorem is assumed for selected-fastest-route actual lengths.

Numerical contract: effects/energy tolerance 1e-8 kWh, scheduled feasibility
1e-8 s, accepted cost key round(cost,7), safe bound L_num - 1e-6 s, theorem audit
2e-6 s / 1e-8 kWh. Margin tests add no slack: borderline negative slack is
inconclusive. Equality ties survive the outward lower-bound adjustment. Leaf
actions use the original accepted evaluator and tie rule.

## E. B1-O oracle potential

These are **logical Site-evaluation reduction potential** measurements. H0 already
paid to determine feasibility, performed roles, times, lengths and concrete costs
for every Site. Reading those results to filter and summarize Regions is also
oracle work. None is counted as actual saved online computation or routing.

Total semantic Site actions across primary cases: **{summary['total_semantic_site_actions']:,}**;
logical leaf evaluations: **{summary['total_logical_leaf_evaluations']:,}**.
Legacy eligible counts and excluded effect-free counts are recorded separately.
Best-bound-first traces retain bounds, pops, refinements, leaves, concrete work
and U - min(OPEN). A separate certified-gap column includes the saved pruned-node
lower floor, avoiding a false zero certificate after positive-epsilon termination.

| Role | Nonempty cases | Empty cases | Conditional median reduction |
| --- | ---: | ---: | ---: |
{role_lines}

This table conditions on nonempty role branches. Empty branches are never counted
as 100% pruning. Envelope, SOC, scenario, OD and role tables are in
`stratified_work.csv`; case-level data are in `logical_work.csv` and `role_work.csv`.

## F. Preregistered classification

{classification_text}

Strong GO remains median >=70% and P(r>=50%)>=75%; NO-GO remains median <50%
or P(r>=25%)<75%; otherwise gray zone. No difficult case was removed from H0–H5.

## G. Gap diagnosis and epsilon sensitivity

G_model=0 in this exact feasible one-stop diagnostic: the per-Site model b*(s)
is the accepted concrete objective itself, with no residual continuation
relaxation. G_agg is the concrete Region minimum minus component-minimum relaxed
cost. G_cert is unavailable because no deployable bound was implemented.
Across visited primary Views, median G_agg={summary['median_aggregation_gap']:.3f} s,
p95={summary['p95_aggregation_gap']:.3f} s. These are View-weighted diagnostics,
not independent case-level observations. Coarse component minima can come from
different Sites; refinement reduces this source of aggregation looseness.

| Role | Views | Median G_agg (s) | p95 G_agg (s) | Certified fraction |
| --- | ---: | ---: | ---: | ---: |
{gap_lines}

`gap_decomposition.csv` and `role_depth_gaps.csv` retain depth, role, OD,
envelope, SOC and scenario diagnostics. No redesign was attempted.

| Epsilon (s) | Cases | Nonempty cases | Conditional median reduction | Maximum observed cost gap (s) |
| --- | ---: | ---: | ---: | ---: |
{epsilon_lines}

All positive-epsilon searches ran only after exact primary correctness passed.
They are secondary work-versus-certified-gap diagnostics, not substitutes for
exact preservation. Full gap trajectories are `oracle_epsilon_*/trace_*.parquet`.

## H. B1-D deployable stage

**B1-D unresolved: no proven non-enumerative deployable certificate implemented.**
Exact performed-effect classification and oracle length oscillations currently
use prepaid per-Site query results. No cheap route-length bound or role filter
was invented, and no full scan was presented as saved work. Computational
break-even remains unresolved.

## I. Runtime and memory

H0 wall time: {h0['runtime_seconds']:.2f} s, peak {h0['peak_rss_mib']:.1f} MiB;
includes shared routing and exhaustive diagnostic work. Per-OD shared routing is
separate in `h0_runtime.csv`. Hierarchy construction plus reproducibility rerun:
{hierarchy['runtime_seconds']:.2f} s, recorded Python-process peak
{hierarchy['peak_rss_mib']:.1f} MiB (native child RSS is not included in this figure).
Oracle runs total {runtime.seconds.sum():.2f} s, peak
{runtime.peak_rss_mib.max():.1f} MiB. These are validation costs, not speedups.
Per-case oracle timings include summaries, audits and concrete leaf evaluations;
the H0 flat timing includes observation/serialization and is not an isolated
replaced-work denominator. Shared routing is reused from verified H0 artifacts
and credited with zero hierarchy savings. Native preprocessing RSS attribution
is limited to the process logs; no deployable timing gate is claimed.

## J. Limitations

30 development ODs, one-stop declared domain, fixed-envelope optimality only;
no real multi-stop result, final holdout, active information acquisition, user
learning or business ranking. Support remains the accepted geographic proxy;
chargers use the deterministic canonical curve. Feasible performed roles are
oracle query results. The zero-semantic denominator needs an explicit convention
before a 480-case empirical classification can be interpreted.

## K. Final gate statement

**{final_gate}. B1-D unresolved.**
All H0–H5 correctness gates pass. B2, Go-2 and holdout work were not started.

Reproduction entry points (fresh B1 outputs; scripts refuse to overwrite freezes):
`run_hierarchy_4r_h0.py`, `build_hierarchy_4r.py`,
`run_hierarchy_4r_oracle.py`, `check_hierarchy_4r_diameter.py --populated`,
`analyze_hierarchy_4r.py`, `finalize_hierarchy_4r.py` under `scripts/`, using
`/home/dy/miniconda3/envs/hiroute/bin/python`. The supplied amendment must be read
alongside the original B0/B1 documents. Archived blocker evidence is permanent.
'''
    report=ROOT/'docs/MILESTONE_4R_B1_REPORT.md';report.write_text(text)
    write_json(out/'resume_preservation_after.json',protection)
    acceptance=dict(passed=classified,status='completed' if classified else 'correctness_passed_classification_blocked',
        action_domain_amendment='applied',amendment_file_hash=sha256(ROOT/'docs/MILESTONE_4R_B1_ACTION_DOMAIN_AMENDMENT.md'),
        archived_blocker_report_hash=archive['docs/MILESTONE_4R_B1_BLOCKER_REPORT.md'],
        archived_blocker_acceptance_hash=archive['results/milestone_4r_b1/blocker_acceptance.json'],
        H0_cases_expected=480,H0_cases_evaluated=h0['cases_evaluated'],H0_cost_mismatches=h0['cost_mismatches'],
        H0_identity_only_changes=h0['identity_only_changes'],H0_passed=h0['passed'],
        **{f'H{i}':'passed' for i in range(1,6)},B1_O_status='experiment_complete',B1_O_classification=summary['classification'],
        B1_D_status='unresolved',protected_artifact_verification=protection,tests=counts,
        hierarchy_sha256=hierarchy['hierarchy_sha256'],zero_semantic_denominator_cases=93,
        final_gate_statement=final_gate,report_sha256=sha256(report),B2='not_started',
        source_sha256={str(p.relative_to(ROOT)):sha256(p) for base in ['src/hierarchy4r','scripts','tests'] for p in (ROOT/base).glob('*')
                       if p.is_file() and (base=='src/hierarchy4r' or 'hierarchy4r' in p.name or 'hierarchy_4r' in p.name)},
        git_status=subprocess.check_output(['git','status','--short'],text=True))
    write_json(out/'acceptance.json',acceptance)
    print(json.dumps({k:acceptance[k] for k in ['status','tests','H0_passed','B1_O_classification','B1_D_status']},indent=2))


if __name__=='__main__':main()
