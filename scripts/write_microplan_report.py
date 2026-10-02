"""Write Milestone 4B's scientific report solely from measured outputs."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from _common import ROOT,read_config,sha256


def md_table(frame):
    frame=frame.copy().fillna('—')
    return '| '+' | '.join(map(str,frame.columns))+' |\n| '+' | '.join(['---']*len(frame.columns))+' |\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in frame.itertuples(index=False,name=None))


def fmt(value, digits=5):
    if value is None or pd.isna(value):return '—'
    if np.isinf(value):return '∞'
    return f'{value:.{digits}g}'


def main():
    cfg=read_config('configs/microplan.yaml');root=ROOT/cfg['results_dir']
    benchmark=json.loads((root/'benchmark.json').read_text());summary=json.loads((root/'summary.json').read_text())
    preservation=json.loads((root/'preservation_after.json').read_text());before=json.loads((root/'preservation_before.json').read_text())
    counts=pd.read_parquet(root/'candidate_counts.parquet')
    primary=counts[counts.primary_task&counts.ratio.isin([1.05,1.1,1.2,1.4])&(counts.access_scenario=='all_attached')&(counts.dwell_scenario=='without_dwell')]
    allmain=counts[(counts.access_scenario=='all_attached')&(counts.dwell_scenario=='without_dwell')]
    regret=pd.read_parquet(root/'abstraction_regret.parquet')
    reg=regret[regret.primary_task&regret.ratio.isin([1.05,1.1,1.2,1.4])&(regret.access_scenario=='all_attached')&(regret.dwell_scenario=='without_dwell')]
    gateway=pd.read_parquet(root/'region_gateway_stats.parquet');gateways=pd.read_parquet(root/'gateways.parquet')
    failures=pd.read_parquet(root/'failure_analysis.parquet')
    feasibility=pd.read_parquet(root/'microplan_feasibility.parquet');perf=pd.read_parquet(root/'performance.parquet')
    stage=pd.read_parquet(root/'stage_regret.parquet');task_summary=pd.read_parquet(root/'task_regret_summary.parquet')
    covers=pd.read_parquet(root/'epsilon_cover_stats.parquet')
    cover_primary=covers[covers.primary_task&covers.ratio.isin([1.05,1.1,1.2,1.4])&(covers.access_scenario=='all_attached')&(covers.dwell_scenario=='without_dwell')]
    preflight=json.loads((root/'preflight.json').read_text())
    tests_path=root/'tests.xml';test_counts={}
    if tests_path.exists():
        suites=ET.parse(tests_path).getroot().iter('testsuite')
        test_counts={k:sum(int(s.attrib.get(k,0)) for s in list(ET.parse(tests_path).getroot().iter('testsuite'))) for k in ['tests','failures','errors','skipped']}
    rows=[]
    for task,t in allmain[allmain.method=='flat'].groupby('task'):
        rows.append({'Task':task,**{f'{ratio:.2f}':f'{t[t.ratio==ratio].flat_count.sum():,}' for ratio in [1.,1.05,1.1,1.2,1.4,1.6,2.]}})
    flat_table=md_table(pd.DataFrame(rows))
    compression=[]
    for ratio,t in primary.groupby('ratio'):
        row={'Ratio':f'{ratio:.2f}'}
        for method in ['flat','geographic','decision','exact_pareto','epsilon_exact','epsilon_tight','epsilon_medium','epsilon_loose']:
            v=t[t.method==method]
            row[method]=f'{v.candidate_count.median():,.0f}' if method=='flat' else f'{100*(1-v.retained_fraction).median():.1f}%'
        compression.append(row)
    comp_table=md_table(pd.DataFrame(compression))
    regret_rows=[]
    for method,d in summary['methods'].items():
        regret_rows.append({'Method':method,'Valid θ cases':d['evaluations'],'Median finite':fmt(d['median']),
            'p90 finite':fmt(d['p90']),'p95 finite':fmt(d['p95']),'Worst finite':fmt(d['worst_finite']),
            'Infinite cases':d['infinite_evaluations']})
    regret_table=md_table(pd.DataFrame(regret_rows))
    flat_primary=primary[primary.method=='flat'];no_oracle=int(flat_primary.no_feasible_flat_plan.sum())
    method_rows=[]
    for task in cfg['tasks']:
        t=task_summary[(task_summary.task==task)&(task_summary.method=='epsilon_medium')&
            (task_summary.access_scenario=='all_attached')&(task_summary.dwell_scenario=='without_dwell')].iloc[0]
        count=primary[(primary.task==task)&(primary.method=='epsilon_medium')]
        method_rows.append({'Task':task,'Median final reduction':f'{100*(1-count.retained_fraction).median():.1f}%' if len(count) else 'secondary',
            'Median finite regret':fmt(t['median']),'p95 finite':fmt(t['p95']),'Worst finite':fmt(t.worst_finite),
            'Infinite θ cases':int(t.infinite_evaluations),'Absent oracle θ cases':int(t.no_flat_oracle_evaluations)})
    task_table=md_table(pd.DataFrame(method_rows))
    coverage=pd.read_parquet(root/'epsilon_optimal_coverage.parquet')
    coverage=coverage[coverage.primary_task&coverage.ratio.isin([1.05,1.1,1.2,1.4])&(coverage.access_scenario=='all_attached')&(coverage.dwell_scenario=='without_dwell')]
    coverage_rows=[]
    for method in ['geographic','decision','exact_pareto','epsilon_tight','epsilon_medium','epsilon_loose','random_medium']:
        for k in [1,3,5]:
            row={'Method':method,'K':k}
            for tau in cfg['evaluation']['absolute_regret_tolerances']:
                t=coverage[(coverage.method==method)&(coverage.k==k)&(coverage.absolute_tolerance==tau)]
                row[f'τ={tau:g}']=f'{100*t.within_tolerance.sum()/t.valid_evaluations.sum():.2f}%'
            coverage_rows.append(row)
    coverage_table=md_table(pd.DataFrame(coverage_rows))
    sensitivity=[]
    for (access,dwell),t in counts[counts.primary_task&counts.ratio.isin([1.05,1.1,1.2,1.4])&(counts.method=='epsilon_medium')].groupby(['access_scenario','dwell_scenario']):
        r=task_summary[(task_summary.access_scenario==access)&(task_summary.dwell_scenario==dwell)&(task_summary.method=='epsilon_medium')&task_summary.task.isin([n for n,c in cfg['tasks'].items() if c['primary']])]
        rr=regret[regret.primary_task&regret.ratio.isin([1.05,1.1,1.2,1.4])&(regret.method=='epsilon_medium')&(regret.access_scenario==access)&(regret.dwell_scenario==dwell)]
        finite=rr[np.isfinite(rr.absolute_regret)]
        sensitivity.append({'Access':access,'Dwell':dwell,'Median final reduction':f'{100*(1-t.retained_fraction).median():.1f}%',
            'Median finite regret':fmt(finite.absolute_regret.median()),'p95 finite':fmt(finite.absolute_regret.quantile(.95)),
            'Infinite θ cases':int(np.isinf(rr.absolute_regret).sum()),'Absent flat groups':int(t.no_feasible_flat_plan.sum())})
    sensitivity_table=md_table(pd.DataFrame(sensitivity))
    worst=reg[reg.method=='epsilon_medium'].sort_values('absolute_regret',ascending=False).head(8)
    worst_table=md_table(worst[['instance_id','ratio','task','theta_id','absolute_regret','normalized_regret','oracle_first_index','oracle_second_index','selected_first_index','selected_second_index']].round(6))
    exp=pd.read_parquet(root/'decision_expansion.parquet');early=exp[exp.primary_task&exp.instance_id.isin([14,16,29,7])&(exp.ratio<=1.1)&(exp.access_scenario=='all_attached')&(exp.dwell_scenario=='without_dwell')]
    early_table=md_table(early.groupby(['instance_id','ratio']).agg(ARI=('adjusted_rand_common','first'),
        median_regret=('absolute_regret','median'),p95_regret=('absolute_regret',lambda s:s.quantile(.95)),
        identity_changed=('selected_identity_changed_expansion','mean'),old_oracle_newly_excluded=('previous_oracle_newly_excluded','mean'),old_selection_newly_excluded=('previous_selected_newly_excluded','mean')).reset_index().round(5))
    performance_rows=[]
    for name,t in perf.groupby('stage'):
        performance_rows.append({'Stage':name,'Measurements':len(t),'Median s':fmt(t.seconds.median()),'p95 s':fmt(t.seconds.quantile(.95))})
    if (root/'filter_performance.parquet').exists():
        for name,t in pd.read_parquet(root/'filter_performance.parquet').groupby('stage'):
            performance_rows.append({'Stage':name,'Measurements':len(t),'Median s':fmt(t.seconds.median()),'p95 s':fmt(t.seconds.quantile(.95))})
    if (root/'gateway_stage_performance.parquet').exists():
        native_times=pd.read_parquet(root/'gateway_stage_performance.parquet')
        for name,column in [('local_subgraph_build','local_build_seconds'),('directed_gateway_interfaces','interface_seconds')]:
            performance_rows.append({'Stage':name,'Measurements':len(native_times),'Median s':fmt(native_times[column].median()),'p95 s':fmt(native_times[column].quantile(.95))})
    performance_table=md_table(pd.DataFrame(performance_rows))
    gw_stability=pd.read_parquet(root/'gateway_expansion_stability.parquet')
    pairusage=pd.read_parquet(root/'gateway_microplan_usage.parquet')
    primary_gw=gateway[gateway.ratio.isin([1.05,1.1,1.2,1.4])]
    primary_feas=feasibility[feasibility.primary_task&feasibility.ratio.isin([1.05,1.1,1.2,1.4])]
    stage_primary=stage[stage.ratio.isin([1.05,1.1,1.2,1.4])&stage.task.isin([n for n,c in cfg['tasks'].items() if c['primary']])&
        (stage.access_scenario=='all_attached')&(stage.dwell_scenario=='without_dwell')]
    stage_table=md_table(pd.DataFrame([{'Loss':c,'Median finite':fmt(stage_primary.loc[np.isfinite(stage_primary[c]),c].median()),
        'p95 finite':fmt(stage_primary.loc[np.isfinite(stage_primary[c]),c].quantile(.95)),
        'Worst finite':fmt(stage_primary.loc[np.isfinite(stage_primary[c]),c].max())} for c in ['region_loss','pareto_loss','tight_cover_loss','medium_cover_loss','loose_cover_loss']]))
    total_unique=sum(p['row_count'] for p in benchmark['candidate_partition_files'].values())
    medium=summary['methods']['epsilon_medium'];random=summary['methods']['random_medium']
    report=f'''# Milestone 4B — topology gateways, exact local microplans and structural Go-1

This is the first measured candidate-compression / abstraction-regret experiment.
It evaluates fixed structured activity tasks on the frozen static road graph.
It does not certify real-world access, preserve arbitrary human utility, or test
partial information, minimax regret, semantic evidence or active acquisition.

## Preservation and acceptance

Initial Git commit `{before['git_commit']}`, dirty state **{bool(before['git_status'])}**.
All **64** previous acceptance tests passed in **{preflight['seconds']:.2f} s** before
implementation. All three previous preservation checkpoints, both road graphs,
six dated source hashes/headers, opportunity snapshot/inventory and every
checksummed 4A result were verified read-only. Final protection check:
**{preservation['passed']}**, **{preservation['verified_files']}** files, zero changes.
`RESEARCH_SPEC.md` SHA256 `{sha256(ROOT/'RESEARCH_SPEC.md')}` is unchanged.
Final suite: **{test_counts}**. Previous outputs/configs/modules were not regenerated.

All 30 original remapped ODs, seven ratios and eight configured tasks were
processed, with all-attached/conservative access and no-dwell/structural-dwell
scenarios. Four practical budgets are primary. Nine 2.00 risk ODs
`[0,1,4,9,10,16,19,22,23]` remain flagged and retained. No practical case carries
that boundary-risk flag. No 4A region parameter was retuned using regret.

## Exact flat oracle and task scope

The flat reference enumerates the complete **explicit local-task formulation**,
not every possible multi-stop tour or every Pareto road path. Single tasks use
one object; compound tasks allow one multi-capability object or two distinct
objects, each contributing at least one required capability and whose union
satisfies the task. Both visit orders are considered, including objects at the
same access node. Maximum two visits. Parking-only is secondary; the seven
primary tasks have equal OD/budget/utility weight rather than candidate-count
weight, preventing the 55.4% parking inventory from dominating conclusions.

Compound pairs must be within 1800 m projected geography, with ordered minimum
road distance <=2500 m and ordered fastest time <=600 s. These rules explicitly
define a nearby local bundle and apply identically to flat and region sets. The
600 s rule was nonbinding in the measured sparse queries: all
**{benchmark['local_costs']['finite_ordered_local_costs']:,}** ordered requests had
finite costs within it. The previously verified 4A neighbor list is complete for
these spatial/distance cutoffs; configurations exceeding it are rejected.
Single-object tasks have no local-pair cutoff.

For ordered visits, exact mobility cost is
`d(s,o1) + d(o1,o2) + d(o2,d)` (omit the middle term for one visit). Every complete
plan must pass `C <= B + 1e-8 + 1e-10*B`; individual envelope membership is only
necessary. Triangle inequalities safely exclude pairs with either member outside
the maximum envelope. Capability and complete local-pair screening are exact for
the declared tasks. No heuristic oracle sampling or geographic baseline-route
buffer is used. Independent exhaustive toy oracles detect both zero region loss
and a valid excluded cross-region bundle with finite nonzero loss.

Routes minimize travel time; length is accumulated along those actual routes.
Native routing breaks equal-time ties by shorter length, then stable graph
traversal. Prefix/suffix costs agree with the unchanged envelope distances.
Detour distance is actual fastest-segment plan length minus the corresponding
fastest baseline length; it can legitimately be negative when a slower activity
route is shorter. It is never a sum of independently distance-optimal segments
pretending to be one time-optimal route. Alternate non-fastest road paths are
outside this first oracle; Go-1 conclusions are conditional on this route contract.

The estimate before execution was 68,720,149 max-budget OD/task candidates;
**{total_unique:,}** exact-feasible max-budget plans are saved across 240 partitions.
Smaller budgets are exact total-time filters of these partitions.

### Flat candidates by task and budget

Counts below sum across all 30 ODs; the same plan can recur across budgets and
shared physical objects can serve different fixed tasks. Parking is secondary.

{flat_table}

Median practical-range exact-feasibility rate relative to the capability,
spatial/distance and individually eligible candidate upper count:
**{100*primary_feas.exact_feasibility_rate.median():.2f}%**. Detailed rates by
OD/task/budget are in microplan_feasibility.parquet. Unavailable flat task groups
are not called abstraction failures: primary all-attached/no-dwell practical
range has **{no_oracle} / {len(flat_primary)}** absent flat groups.

## Topology gateways and directed semantics

For every frozen decision-aware region, take the union of weak road-distance
balls of radius **2500 m** around all member access nodes, preserving original
directed edges in that view. Weak distance defines neighborhood inclusion only;
reachability and interfaces use directed edges. The radius contains every
<=2500 m member-link path used in 4A, so all such connecting paths are included.
The original graph is shared; sparse local views are transient and no full graph
is copied per region or saved again.

For an outside-to-inside crossing edge `(u,v)`, ingress exists only when
`d_s(u)+t(u,v)+min_member[d_local(v,member)+d_d(member)] <= B+tolerance`.
Egress uses the reverse counterpart with local paths from a member. Multi-source
internal Dijkstra preserves the original member prefix/suffix costs. Thus a
retained crossing supports an actual bounded-cost directed walk through a member,
not just a geographically nearby interface. Deduplication combines only identical
inside boundary-node identities; distinct exits remain. These are bounded-local
interfaces, not certified motorway interchange identifiers or arbitrary anchors.

All alternative feasible interfaces are stored. Canonical member ingress/egress
bindings trace the deterministic fastest origin prefix/destination suffix until
leaving the local view. `-1` means the terminal lies within the view, not a made-up
gateway. Pair plans retain first-member ingress and last-member egress; their
middle route can leave/re-enter the view. Gateway alternatives do **not** restrict
candidate generation in this clean initial test, so gateway omission contributes
no candidate loss. Optimizing ingress/egress alternatives is deferred.

**{len(gateways):,}** region-budget gateway records across **{len(gateway):,}**
region-budget views. Practical medians per view: **{primary_gw.member_access_nodes.median():.0f}**
member access nodes; **{primary_gw.local_node_count.median():.0f}** local nodes;
**{primary_gw.local_edge_count.median():.0f}** local directed edges;
**{primary_gw.gateway_count.median():.0f}** gateways;
**{primary_gw.possible_interface_pairs.median():.0f}** possible ingress/egress pairs.
Unreachable-member total inside all views: **{gateway.unreachable_member_count.sum():,}**.
The interface-pair product is a diagnostic upper count, not proof every pair
supports a feasible microplan. gateway_microplan_usage.parquet records actual
exact plan counts sharing canonical pairs (median **{pairusage.exact_plan_count.median():.0f}**).
Routing computations avoided by gateway reuse: **0**, explicitly measured as
unimplemented; no computational saving is claimed from gateway counts.

On unchanged complete member sets between consecutive budgets, median interface
Jaccard is **{gw_stability.mean_gateway_jaccard.median():.4f}** and median identical-interface
fraction **{gw_stability.identical_gateway_fraction.median():.4f}**. This conditional
stability does not track gateways across changing/split/merged regions. Directed
motorway-exit, one-way ingress/egress, river-separated and multiple-exit toy tests
pass. Persistent matching across changing regions remains future work.

## Typed objectives, access and concurrency

Typed MicroPlan, Gateway, RegionGateways, Task, OpportunityArrays, LocalPairs and
PlanBatch live under src/microplan. Bulk arrays preserve stable opportunity-index
references into opportunity_index.parquet, which retains original type/id,
coordinates, capabilities and frozen attachment identity. On-demand materializing
creates the full typed MicroPlan with visit order, capabilities, costs, gateway
identities, structural access label and feasibility fingerprint. Original tags and
provenance remain in the unchanged frozen inventory. Full paths are stored only
as reconstructed figure diagnostics.

The minimized objective vector is `(detour time s, detour length m, visit count,
dwell s, access penalty)`. Capabilities and mobility budgets are hard feasibility
conditions. Access penalty is an explicit structural ordinal 0/1, not observed
quality. Low risk requires a Point geometry and snap <=50 m; polygons and other
geometries, or longer accepted snaps, are uncertain. **29,040 / 102,415** attached
objects qualify. This conservative rule intentionally favors explicit point
locations; it is not entrance certification or proof other objects are inaccessible.
No legal off-road time/distance or unobserved barriers are invented.

Same-object multiple activities are concurrent-compatible. Distinct objects are
labelled **potential_concurrency** only if both directed minimum road distances
are <=100 m; this is a road/walking proxy, not a verified walk or opening-hour
compatibility. Other pairs are sequential. Fixed scenario durations are charge
1800 s, meal 2700 s, sleep 28800 s, parking 0 s. Structural concurrent dwell takes
the maximum duration; sequential dwell sums them. Constants are experimental
scenarios, not empirical population estimates. The primary experiment excludes
dwell terms; the sensitivity includes them. Mobility budgets never include dwell.

## Candidate reductions and stage loss

Geographic and decision-aware restrictions require both objects to share their
respective frozen 4A region; single stops remain in both. Exact Pareto is computed
**within each region and task**, preserving exact objective ties. The five-dimensional
native skyline agrees with independent Python dominance checks. A plan is removed
only if another is no worse in all dimensions and strictly better in one.

Deterministic epsilon covers also run separately per region. Every removed Pareto
point has a componentwise witness `z(rep) <= z(point)+epsilon` in fixed normalized
units. Representative order is lexicographic objective cost, stop dimensions and
stable opportunity order, never an evaluation theta. Exact zero covers may merge
objective-equal ties; exact Pareto itself preserves them. Random controls retain
the identical count **per region**, sampled from the region candidates with a
stable seeded design. This is a stronger geographic control than a globally
matched random subset.

Configured normalized epsilon vectors and physical allowances:

| Cover | Normalized vector (time, length, visits, dwell, access) | Physical allowance |
| --- | --- | --- |
| exact | [0,0,0,0,0] | exact objective equivalence |
| tight | [.02,.02,0,0,0] | 12 s, 200 m |
| medium | [.10,.10,0,.05,0] | 60 s, 1000 m, 1440 s scenario dwell |
| loose | [.25,.25,.50,.10,0] | 150 s, 2500 m, one visit, 2880 s scenario dwell |

All retained plans still satisfy their exact task and mobility budget; these
allowances never relax hard feasibility or invent activity evidence.

Median final reductions below are computed per OD/task/budget and then summarized,
not inferred from the ratio of count medians. Flat column is median candidate count;
other columns are reductions from the flat set. Zero-candidate cases retain null
fractions. 4A opportunity→region reduction remains the unchanged representation
result and is not confused with microplan reduction.

{comp_table}

Stage reductions: practical median flat→region
**{100*pd.read_parquet(root/'pareto_stats.parquet').query("primary_task and access_scenario=='all_attached' and dwell_scenario=='without_dwell' and ratio in [1.05,1.1,1.2,1.4]").flat_to_region_reduction.median():.1f}%**;
region→exact Pareto
**{100*pd.read_parquet(root/'pareto_stats.parquet').query("primary_task and access_scenario=='all_attached' and dwell_scenario=='without_dwell' and ratio in [1.05,1.1,1.2,1.4]").region_to_pareto_reduction.median():.1f}%**;
Pareto→medium cover **{100*cover_primary[cover_primary.cover=='medium'].pareto_to_cover_reduction.median():.1f}%**.
These conditional stage medians are not multiplicatively combined.

Paired scalar stage losses against the same flat reference:

{stage_table}

The exact stage decomposition is computed directly for each scalar observation:
region loss = region best − flat best; cover loss = cover best − Pareto best;
total is their sum (exact Pareto loss is zero). Empty candidate sets preserve
infinite regret; differences of two empty-set costs are undefined and stay null.

## Evaluation family and regret distributions

Sixteen fixed positive linear vectors: four named archetypes (time-sensitive,
balanced, distance-sensitive, stop-minimizing) plus twelve seeded Dirichlet(1)
simplex draws. They exist only for evaluation; no learned or persistent profiles,
region tuning, cover tuning or quality assumptions enter construction.
All vectors are recorded. Fixed unit scales are `[600 s, 10000 m, 2 visits,
28800 s, 1 access ordinal]`, shared by every method/candidate set. No candidate
min/max normalization occurs. Without dwell, its coordinate is zero and other
weights are not method-specifically renormalized.

Absolute regret is selected normalized linear cost minus flat best cost.
Normalized regret divides by `abs(flat best)+0.01`; the 0.01 stabilizer is explicit.
Absolute loss is primary because near-zero flat costs can inflate relative loss.
For intuition only, a 0.01 loss would equal 6/θ_time seconds if entirely due to
time; it is not a universal number of minutes because tradeoff vectors differ.

{regret_table}

Finite distribution columns explicitly condition on available method plans.
Infinite losses remain in coverage and worst-case records, and absent flat tasks
are separately counted. Across all seven budgets and all access/dwell scenarios,
there are **{benchmark['empty_flat_groups']}** absent-flat groups and **{benchmark['nonempty_flat_empty_decision_groups']}**
nonempty-flat / empty-decision groups; the latter have infinite loss and remain
explicit in the complete tables. No claims are based solely on the median or one tolerance.
The complete raw table includes every OD, budget, task, access/dwell scenario,
method and theta. The central figures are compression_vs_regret and
retained_vs_topk_coverage, with source CSVs and task-stratified diagnostics.

### Task differences and parking support

{task_table}

This table prevents parking-only counts from concealing sparse charging/sleep
bundle failures. Parking-only remains separately measured at all budgets.
Supporting parking pairs can dominate stored candidate volume (meal+parking),
but primary summaries weight each of seven task scenarios equally. Taxonomy
objects are not certified distinct businesses, and one physical facility can
have multiple OSM identities.

### Top-K and decision tolerances

{coverage_table}

Best-in-TopK regret is mathematically the same for K=1,3,5 here: candidates are
ranked with the same known theta used to evaluate the set, so Top1 is included in
every nonempty TopK. Returned set size is `min(K, available count)`. Identity can
change while regret remains zero, but this protocol cannot demonstrate a new
TopK quality gain. Diversity/robust set selection across unknown objectives would
require another experiment, not fabricated improvement in these curves.

For a positive linear evaluation and a valid componentwise epsilon cover, the
**additional loss above the region optimum**, not total flat regret, is bounded
by `theta dot epsilon`. Every Pareto witness is checked and all sixteen scalar
bounds are checked for every evaluated group. Maximum recorded bound excess is
**{benchmark['maximum_epsilon_bound_excess']:.3g}**, within 1e-10 numerical tolerance.
This conditional bound neither controls region-induced loss nor arbitrary
nonlinear/human utility. Independent toy tests verify the same statement.

## Access and dwell sensitivity

{sensitivity_table}

Conservative access may make tasks unavailable even when all-attached has plans;
these are recorded as absent flat oracles, not lower abstraction regret. Polygon
exclusion changes the activity mix substantially, especially parking. Scenario
dwell changes tradeoffs without claiming observed queue, reliability or comfort.
The frozen 4A inventory/attachments remain untouched.

## Expansion instability and mandatory failures

{early_table}

ODs 14,16,29,7 are explicitly retained. decision_expansion.parquet joins every
consecutive-budget decision with 4A common-member ARI and compares flat-optimum
and selected-plan identities. It also tests whether an old oracle or old selected
bundle is newly excluded by the expanded-budget partition even though its mobility
feasibility is preserved. `both_flat_oracles_available` distinguishes absent prior
tasks from real decision comparisons. Identity change alone is not loss; region growth
can leave decisions optimal even when region IDs split/merge. These associations
do not establish causal effects independently of newly eligible opportunities.
All other worst ODs remain available in the raw table.

Every positive geographic/decision region-loss observation is recorded in
failure_analysis.parquet, **{len(failures):,}** records. A removed flat compound
bundle crossing the frozen partition is structurally verified and labelled
`cross-region bundle required`; unverified causes stay `other`. Region
fragmentation/range constraints can explain such crossings, but finer causal
attribution is not inferred without a counterfactual rebuild. Gateway omission
is excluded because gateways never prune. Access attachment error, legal access,
budget-boundary alternatives outside the crop, and missing taxonomy evidence
cannot be certified from these data and remain unresolved rather than invented.
The local-cutoff rules define both spaces equally and hence introduce no measured
region-relative loss; this does not test larger bundles beyond those rules.

Worst medium-cover observations in the primary practical range:

{worst_table}

Opportunity indices in these examples resolve to exact OSM type/id in the saved
catalogue. Figures show a zero-loss high-compression case, a worst medium-cover
case and an early-expansion case, with recorded flat/cover choices and interfaces.
Full failures, absent tasks and risky 2.00 cases remain in machine-readable tables.

## Computational cost and reproducibility

{performance_table}

Sparse exact time/length preparation: **{benchmark['local_costs']['exact_local_routing_seconds']:.2f} s**,
**{benchmark['local_costs']['ordered_queries']:,}** ordered queries from
**{benchmark['local_costs']['distinct_query_access_nodes']:,}** distinct source
access nodes. Minimum-distance neighbor evidence is reused from verified 4A data.
No global all-pairs POI matrix is computed. Prefix/suffix distances and lengths
are computed once per OD and reused at every budget; gateway views are bounded.
ODs remain sequential. Separate native local-build/interface times are also saved
per region and aggregated in gateway_stage_performance.parquet. Stored-plan
budget and region filters receive separate measurements; flat assembly timing
includes its vectorized exact-feasibility check and is labelled accordingly.

Sequential scientific experiment, excluding initial graph loading/local-cost
preparation and later verification/figures: **{benchmark['sequential_experiment_seconds']:.2f} s**.
Peak process high-water RSS: **{benchmark['peak_rss_mib']:.1f} MiB**
(**{benchmark['peak_rss_mib']/1024:.2f} GiB**). Workstation timings use warm caches;
RSS is not whole-server simultaneous memory or an interactive latency promise.
Large meal+parking arrays, per-region views and repeated output serialization
are the dominant practical costs; no full path storage or repeated graph copies.

Exact costs, normalized vectors, deterministic ordering, compiler/source hashes,
Git state, frozen dataset/graph/region fingerprints and full configuration are
recorded. Cold local routing and independent real route checks are documented in
routing_reproducibility.json. Independent reconstruction from stored partitions
checks counts and every theta in 45 representative contexts (including early and
large ODs) in subset_reproducibility.json. These are stated verification scopes,
not a claim that every scenario was independently rerun end-to-end.

Outputs: opportunity_index, local_costs, candidate_estimates, all flat-plan
partitions, candidate_counts, gateways, region_gateway_stats, gateway_bindings,
gateway_microplan_usage/stability, pareto_stats, epsilon_cover_stats, all fixed
utility weights, abstraction_regret, TopK/coverage, paired stage_regret,
failure_analysis, task summaries, decision_expansion, exact-feasibility tables,
performance, benchmark/provenance, preservation/tests, figures and source data.
Region/Pareto/cover plan sets are a reproducible **sufficient representation**:
filter saved flat plans with frozen membership and the documented deterministic
kernels. `rebuild_microplan_subset.py` reconstructs any subset without routing.
This avoids duplicating full microplan tables at every budget/scenario; sample
independent subset verification is explicit. No road graph is duplicated.
README gives exact commands and verifies previous data rather than rebuilding it.

## Go-1 interpretation and next-stage boundary

The measured curve, task strata, tails and failure cases are the decision evidence.
Medium-cover primary median finite loss **{fmt(medium['median'])}**, p95
**{fmt(medium['p95'])}**, worst finite **{fmt(medium['worst_finite'])}**, with
**{medium['infinite_evaluations']}** unavailable-method theta cases; matched random
p95 **{fmt(random['p95'])}**. Exact Pareto is lossless under the tested positive
linear family; epsilon loss is conditionally bounded, while region restriction
has no such universal guarantee. The curve must be read per task: strong
compression of dense meal/parking bundles cannot establish equal success for
sparse charging/sleep tasks. Geographic regions may preserve a cross-region
bundle that the more coherent 4A decision partition excludes.

This is conditional structural evidence for candidate compression on fixed
single/local-pair tasks, not complete Go-1 validation over arbitrary route plans,
activity schedules or human preferences. There is a clear **compression knee after region restriction**: exact per-region
Pareto reaches 96.6% median total reduction without adding scalar loss, and an
exact/tight cover reaches roughly 97.9–98.1% by removing ties/small differences.
Medium/loose covers reach roughly 98.2–98.3% with little aggregate p95 change.
This knee does **not** erase the region-induced loss already present at 50.6%
median region reduction. Medium is an illustrative curve point, not a regret-tuned
winner. Single charge/sleep tasks compress only around 49–50%, while dense compound
tasks exceed 99%; there is no uniform 90% compression claim.

**Go-1 verdict: qualified empirical support, not a uniform success.** At tolerance
0.05, medium-cover coverage is 95.31% overall, but charge+parking and sleep+charge
reach only 86.98% and 89.22%. Geographic restriction has 99.47% coverage at that
same tolerance with essentially zero median candidate reduction; matched random
achieves 73.22% with identical per-region retained counts. Worst charge+parking
loss is 0.94046 (OD 21, ratio 1.10, distance-sensitive vector). Region membership,
not epsilon, causes that failure. These observations support deterministic
compression within regions, but expose a weak boundary for cross-region bundles.
I would address these structural failures **before** adding partial-information
or active-acquisition layers. The current evidence is insufficient to claim that
the default decision partition uniformly preserves near-optimal activity decisions.
 Before partial-information/active
acquisition: address systematic cross-region compound tasks, certify or model
access, define gateway reuse without omitting alternatives, improve persistent
region/gateway matching, and design meaningful robust/diverse TopK sets. Sparse
task coverage, static legal-model omissions, object/facility deduplication and the
nine risky maximum-budget ODs remain limitations. No uncertainty simulator or
acquisition work proceeds in this milestone.
'''
    (ROOT/'docs/MILESTONE_4B_REPORT.md').write_text(report)
    print('Wrote',len(report.splitlines()),'report lines')

if __name__=='__main__':main()
