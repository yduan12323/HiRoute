"""Measured Milestone 4A report from machine-readable outputs; no utility evaluation."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from _common import ROOT,read_config,sha256


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',
                      *['| '+' | '.join(map(str,row))+' |' for row in rows]])


def main():
    cfg=read_config('configs/opportunity.yaml');result=ROOT/cfg['results_dir']
    benchmark=json.loads((result/'benchmark.json').read_text());audit=benchmark['quality_audit']
    compact=json.loads((result/'network_compact_reproducibility.json').read_text())
    manifest=yaml.safe_load((ROOT/cfg['raw_dir']/'MANIFEST.yaml').read_text())
    stats=pd.read_parquet(result/'region_stats.parquet');stability=pd.read_parquet(result/'expansion_stability.parquet')
    sensitivity=pd.read_parquet(result/'parameter_sensitivity.parquet');performance=pd.read_parquet(result/'performance.parquet')
    preservation=json.loads((result/'preservation_after.json').read_text());before=json.loads((result/'preservation_before.json').read_text())
    tests=ET.parse(result/'tests.xml').getroot();suites=list(tests.iter('testsuite'))
    totals={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    rows=[]
    for ratio in sorted(stats.ratio.unique()):
        g=stats[(stats.ratio==ratio)&(stats.method=='geographic baseline')]
        d=stats[(stats.ratio==ratio)&(stats.method=='decision-aware')]
        rows.append([f'{ratio:.2f}',f'{d.eligible_opportunities.median():,.1f}',f'{g.region_count.median():,.1f}',
                     f'{d.region_count.median():,.1f}',f'{100*g.compression_ratio.median():.1f}%',f'{100*d.compression_ratio.median():.1f}%',int(d.boundary_risk.sum())])
    compression=table(['Ratio','Median eligible','Median geographic regions','Median decision regions','Median geographic reduction','Median decision reduction','Risk ODs'],rows)
    practical=stats[stats.ratio.isin(cfg['regions']['sensitivity_ratios'])]
    comparison=[]
    for method,group in practical.groupby('method'):
        comparison.append([method,f'{group.weighted_progress_variance.median():.6g}',f'{group.weighted_detour_variance_s2.median():.2f}',
            f'{group.mean_geographic_bbox_diagonal_m.median():.1f}',f'{100*group.singleton_fraction.median():.1f}%',
            f'{100*group.network_disconnected_region_fraction.median():.2f}%',f'{group.mean_capability_count.median():.2f}'])
    coherence=table(['Method','Median weighted progress variance','Median weighted detour variance s²','Median mean bbox diagonal m','Median singleton fraction','Median disconnected fraction','Median mean capabilities'],comparison)
    stable_rows=[]
    for (method,previous,ratio),group in stability.groupby(['method','previous_ratio','ratio']):
        stable_rows.append([method,f'{previous:.2f}→{ratio:.2f}',f'{group.adjusted_rand_common.median():.3f}',
            f'{group.mean_best_full_member_jaccard.median():.3f}',f'{group.new_regions_without_old_members.median():.1f}',
            f'{group.merged_current_regions.median():.1f}',f'{group.split_old_regions.median():.1f}'])
    stable_table=table(['Method','Expansion','Median ARI common members','Median best full Jaccard','Median new regions','Median merges','Median splits'],stable_rows)
    sensitive_rows=[]
    for name,group in sensitivity.groupby('configuration'):
        sensitive_rows.append([name,f'{group.region_count.median():.1f}',f'{100*group.compression_ratio.median():.1f}%',
            f'{group.weighted_progress_variance.median():.6g}',f'{group.weighted_detour_variance_s2.median():.2f}',
            f'{group.clustering_seconds.median():.3f}'])
    sensitive_table=table(['Configuration','Median regions','Median compression','Median progress variance','Median detour variance s²','Median cluster seconds'],sensitive_rows)
    speed=[]
    for (stage,method),group in performance.groupby(['stage','method']):
        speed.append([stage+(' / '+method if method else ''),len(group),f'{group.seconds.median():.4f}',f'{group.seconds.quantile(.95):.4f}'])
    speed_table=table(['Stage','Measurements','Median seconds','p95 seconds'],speed)
    combos=[]
    for ratio,group in practical[practical.method=='decision-aware'].groupby('ratio'):
        combos.append([f'{ratio:.2f}',*[f'{group[key+"_regions"].median():.1f}' for key in ['charge+meal','charge+parking','meal+parking','sleep+charge','services+meal']]])
    combo_table=table(['Ratio','charge + meal','charge + parking','meal + parking','sleep + charge','services + meal'],combos)
    capability=table(['Capability','Objects (nonexclusive)'],[[k,f'{v:,}'] for k,v in audit['capability_counts'].items()])
    snaps=table(['Threshold m','Attached','Rejected','Coverage'],[[r['threshold_m'],f"{r['attached']:,}",f"{r['rejected']:,}",f"{100*r['attached_fraction']:.2f}%"] for r in audit['threshold_sensitivity']])
    quality=table(['Measure','Value'],[['Node / way / relation counts',' / '.join(f"{audit['object_type_counts'][t]:,}" for t in ['node','way','relation'])],
        ['Missing name rate',f"{100*audit['missing_name_rate']:.2f}%"],['Snap median / p95 / p99 m',' / '.join(f"{audit['snap_quantiles_m'][q]:.1f}" for q in ['0.5','0.95','0.99'])],
        ['Occupied 5 × 5 km cells',audit['occupied_density_cells']],['Median / p95 / max objects per occupied cell',' / '.join(f"{audit['density_cell_count_quantiles'][q]:.0f}" for q in ['0.5','0.95','1'])]])
    sources=table(['Source membership (not country)','Objects'],[[k,f'{v:,}'] for k,v in audit['source_membership_counts'].items()])
    p=practical.pivot(index=['instance_id','ratio'],columns='method',values=['weighted_progress_variance','weighted_detour_variance_s2'])
    reductions={}
    for key in ['weighted_progress_variance','weighted_detour_variance_s2']:
        a=p[key]['geographic baseline'];b=p[key]['decision-aware'];positive=a>0
        reductions[key]=float(np.median(1-b[positive]/a[positive]))
    worst=stability[stability.method=='decision-aware'].sort_values('adjusted_rand_common').head(8)
    worst_table=table(['OD','Expansion','ARI','Best Jaccard','Merges','Splits'],[[int(r.instance_id),f'{r.previous_ratio:.2f}→{r.ratio:.2f}',
        f'{r.adjusted_rand_common:.3f}',f'{r.mean_best_full_member_jaccard:.3f}',int(r.merged_current_regions),int(r.split_old_regions)] for r in worst.itertuples()])
    report=f'''# Milestone 4A — Opportunity substrate and route-attached regions

Measured user-agnostic representation experiment only. No optimal-decision preservation, abstraction regret, final Go-1 success, microplans, utility, preference, semantic/LLM, minimax-regret, acquisition or adaptive utility stopping implementation is claimed.

## Preservation and acceptance

Initial commit `{before['git_commit']}`, dirty state `{bool(before['git_status'])}`. All **36** prior tests passed before implementation. The two previous preservation checkpoints, Slovenia/extended raw datasets and graph fingerprints, six dated source hashes/headers and the selected polygon were verified. Final preservation: **{preservation['passed']}**, {preservation['verified_files']} prior files, zero changes. `RESEARCH_SPEC.md` remains SHA256 `{sha256(ROOT/'RESEARCH_SPEC.md')}`. Prior raw/processed/results files and graph/envelope modules were not regenerated or edited. Final acceptance suite: **{totals}**.

All 30 frozen remapped ODs × all seven original ratios × both methods are retained: 420 summary rows; 360 consecutive-expansion records; 840 sensitivity records (30 ODs × four practical ratios × seven configurations). The nine risky 2.00C* ODs `[0, 1, 4, 9, 10, 16, 19, 22, 23]` remain explicitly flagged. No practical-range OD carries the previous crop/source-gap risk flag.

## Frozen opportunity dataset

`{cfg['raw_dir']}/opportunities-260929.osm.pbf` and `inventory.parquet`, with read-only MANIFEST.yaml and PROVENANCE.json. PBF SHA256 `{manifest['files']['opportunities-260929.osm.pbf']}`; inventory SHA256 `{manifest['files']['inventory.parquet']}`. Both were independently rebuilt from all six original source PBFs and reproduced **identical bytes**. Snapshot **2026-09-29T20:22:51Z**, exact 75 km extraction GeoJSON SHA256 `{manifest['polygon_sha256']}`. No live OSM or newer snapshot. Source attribution: OpenStreetMap contributors / Geofabrik, ODbL 1.0.

Per source: osmium-tool 1.18.0 `tags-filter nwr/...` retains activity objects and referenced objects; `extract -s smart -S types=any` with the frozen polygon completes selected relation members; merge identical-snapshot extracts. This filter-first order avoids unrelated large relations while retaining activity geometry. Strategy semantics follow the [Osmium tags-filter](https://docs.osmcode.org/osmium/latest/osmium-tags-filter.html) and [smart extract](https://docs.osmcode.org/osmium/latest/osmium-extract.html) manuals. Only activity-filtered files are merged; no all-tag country union enters Pyrosm. Way-node reference checks found zero missing nodes. Full original OSM tags are retained, including uninterpreted/unknown attributes. Explicit taxonomy/exclusions live in configs/opportunity.yaml. Amenities: charging_station, restaurant/cafe/fast_food/food_court, pharmacy, toilets, parking; tourism: hotel/motel/hostel/guest_house; shop: supermarket/convenience; highway: rest_area/services. Explicit access=no/private is excluded. Parking-space objects and explicitly zero/one/two-space facilities are excluded. Unknown parking capacity stays unknown and does not imply a large facility. Remaining amenity=parking inventory can still include small untagged lots; this is a taxonomy limitation.

Candidates after taxonomy/exclusions in six cropped contributions: **{manifest['raw_candidate_count']:,}**; overlapping `(osm_type, osm_id)` copies: **{manifest['duplicate_count']:,}**; merged unique candidates: **{manifest['unique_candidate_count']:,}**. Different nearby businesses are never proximity-deduplicated. A physical facility may have separately tagged node/way/relation identities; semantic facility deduplication is deferred, so object counts are not certified business counts. Same-identity conflicting structured tags cause an error. **{manifest['excluded_count']}** candidates are excluded from the usable inventory: {manifest['exclusion_reasons']}. They remain auditable in the frozen PBF and extraction_exclusions.parquet. This is snapshot reproducibility relative to the source extracts, not a certificate of OSM completeness.

Node locations are exact OSM coordinates. Polygons/multipolygons use EPSG:3035 point-on-surface (never an out-of-object centroid); linear objects use normalized projected line midpoint. Polygon geometry takes priority when an OSM way also exports as a line. The representative point must lie inside the same research polygon. Unsupported/nonexportable relation geometries are counted explicitly. Original geometries, object identities, all source memberships, snapshot timestamp and geometry method are recorded. No entrance is inferred from an arbitrary nearby tag.

## Opportunity quality audit (completed before clustering)

Total located opportunities: **{audit['total_opportunities']:,}**. Capability counts overlap for explicitly multi-tagged objects:

{capability}

{quality}

{sources}

Country is not inferred from which overlapping extract contains an object; explicit addr:country values remain raw evidence, including inconsistent values. The complete source/explicit-country distribution and density grid are in quality_audit.json and opportunity_density.parquet. Parking constitutes {100*audit['capability_counts']['parking']/audit['total_opportunities']:.1f}% of objects, so aggregate compression is parking-dominated; category-filtered follow-up is needed before an activity-wide generalization.

## Road attachment and threshold sensitivity

Find four nearest candidate nodes in a spherical index of nodes with both incoming and outgoing allowed local-road edges, then choose the smallest WGS84 geodesic distance, breaking ties by graph ID. Motorway/trunk lanes and their link ramps are excluded as snap targets. Original static routing access exclusions remain unchanged. Record contiguous access node and original OSM node ID; distance and status remain recorded even for excessive snaps. This checks local routability, not entrance-level access or an off-road connection's legality. A POI across a fence, river, restricted driveway or pedestrian area can still snap incorrectly; pairwise road validation cannot repair an incorrectly chosen access node.

Selected threshold **{audit['selected_threshold_m']} m**: **{audit['attached_count']:,} attached**, **{audit['rejected_count']:,} excessive-snap rejections**. It retains 97.31% while 500 m adds only about 1.4 percentage points of coverage. Distribution and sensitivity justify an initial conservative cutoff, not a universally correct access distance.

{snaps}

## OD-specific decision features and eligibility

Reuse the unchanged envelope API once per OD: forward `d_s(v)=d(s,v)` on outgoing edges; reverse `d_d(v)=d(v,d)` on incoming edges from destination. At selected access node v: `H=d_s+d_d`; detour `Delta=H-C*` seconds; detour ratio `delta=H/C*`; normalized progress `r=d_s/H`. C*>0 is required; unreachable nodes are excluded. Reachable r lies in [0,1] and describes base-cost journey stage, not geometric route projection. The normalized coordinate is stable across budgets because distances are unchanged within an OD. Eligibility is `H <= B + 1e-8 + 1e-10*B`, exactly the prior numerical policy. Snap distance is an attachment diagnostic and contributes no invented off-road travel time; later access modeling may change H. No Euclidean route buffer or scalar user utility is used.

Typed Opportunity, Provenance, OpportunityId, DecisionOpportunity, ODContext and OpportunityRegion representations live in src/opportunity. Decision features retain progress, absolute/relative detour, road node identity, geographic/projected location and capabilities. Protocol OpportunityRegionBuilder permits alternative builders. All member access nodes and the original graph/topology fingerprint remain available for later gateways. Region anchors are member locations; **gateway identification is deferred to 4B/4C**.

## Exact region definitions and comparison

**Geographic baseline:** radius-neighbor connected components with radius 1200 m, equivalent to DBSCAN min_samples=1. It uses no decision or road features and retains singleton objects. Geographic chaining can create very large urban regions; this is a labelled baseline behavior, not the proposed abstraction.

**Decision-aware:** deterministic sparse agglomeration. Candidate links require geography <=1200 m and both directed road distances <=2500 m. Process links in ascending geographic distance then stable OSM identities. Merge only if the whole resulting component has progress range <=0.025, absolute detour range <=180 s, and projected bounding-box diagonal <=3000 m. Range constraints prevent progress/detour chaining beyond the configured tolerance. Every opportunity remains represented, including singleton regions. Activity capabilities are summarized after grouping, permitting related/complementary activities without learned embeddings or quality assumptions. These are representation hyperparameters, not user preference weights or claimed optimal constants.

Network pair screening indexes projected POI coordinates at maximum sensitivity radius 1800 m. A native C++17 bounded directed Dijkstra validator computes only sparse candidate pairs, with a 2500 m cutoff, batching requests sharing an access node. Both directions must pass; one-way asymmetry or a missing nearby river crossing can reject a pair. `inf` denotes beyond cutoff or unreachable, not proof of global disconnection. Search can use any original graph edges, not only envelope edges; it measures local structural road connectivity and does not certify that a multi-POI tour respects the OD budget. One transient CSR adjacency index exists in the native subprocess, no copied full graph is saved. The original igraph stays shared across budgets/ODs. Native source/compiler and cache provenance are hashed. Compact typed neighbor arrays and a C++ constrained-union kernel accelerate the same transparent algorithm; seeded empty/singleton/random toy cases verify exact region/statistic agreement with the Python reference. No all-pairs POI matrix is computed.

There are **{benchmark['network']['pair_count']:,} spatial candidate pairs**, **{benchmark['network']['validated_pair_count']:,}** pass both directed cutoffs. Connectivity diagnostics measure components under those validated local links. Decision regions have a connected local spanning graph; neither all-pairs network diameter nor bundle feasibility is asserted. Geographic spread is the bbox-diagonal upper bound on Euclidean diameter. `validated_network_edge_max_m` reports local accepted link spread, with finite-cutoff pair fraction and local component counts preserved per region. This is an explicitly limited network-spread diagnostic, not a hidden replacement by straight-line distances.

## Compression across budgets

All entries below are medians across 30 ODs; count medians and compression medians are computed separately and need not give the same quotient. Compression is `1-region_count/eligible_count` within each OD. Empty opportunity sets have undefined compression/singleton fractions, retained as null. The primary practical range is 1.05–1.40; 1.00, 1.60 and 2.00 remain measured.

{compression}

This is **representation compression only**, not decision-space abstraction regret or Go-1 acceptance.

## Decision coherence and geographic baseline

Practical-range table: medians across 120 OD-budget observations. Progress/detour variance is within-region population variance weighted by member count; singleton variance is zero. Including singletons can reward fragmentation, so compression and singleton rate accompany dispersion. Connectivity fraction uses the same screened road-distance graph for both methods.

{coherence}

Median paired reduction of weighted progress variance: **{100*reductions['weighted_progress_variance']:.1f}%**; detour variance: **{100*reductions['weighted_detour_variance_s2']:.1f}%**. These are descriptive same-OD comparisons, without significance tests or a downstream objective. Whole-region constraints mechanically limit dispersion; observed compression determines whether this limit is useful. Geography does not necessarily become less compact: bounded agglomeration can also be geographically smaller than the chaining baseline. No anticipated tradeoff is assumed in advance.

## Envelope expansion stability

ARI compares partitions on the intersection of old/new eligible members; it ignores the new members. Best-region Jaccard compares each old region's complete member set against candidate new full sets, and is averaged unweighted across old regions. New regions contain no old members. A merge means a new region overlaps multiple old regions; a split means an old region overlaps multiple new regions. Many-to-many evolution can count both. IDs are content-derived, not persistent tracked gateway identities. No strict nesting is imposed. No members disappear under expansion.

{stable_table}

Least-stable decision-aware examples (explicitly retained):

{worst_table}

ARI/Jaccard agreement must be read together; a high common-member ARI can hide substantial member growth. Deterministic greedy union can split regions when earlier new links alter allowed range unions. That instability is real, not renamed away. Persistent evolution/matching and gateway semantics require further work before online adaptive planning.

## Multi-capability co-location

Median number of decision-aware regions carrying each capability pair across 30 ODs:

{combo_table}

Capabilities may come from different region members or explicit multiple tags on one object. Co-location is structured OSM evidence only: it does not establish compatible opening hours, walking access, concurrent dwell, charger reliability, quality or feasible activity bundles. No bundling optimization or synthetic quality attributes were introduced.

## Parameter sensitivity

One-at-a-time progress 0.015/0.04, detour 120/300 s, local radius 750/1800 m, and default, for all ODs at four practical budgets. Road cutoff 2500 m and geographic span 3000 m remain fixed. This modest seven-configuration grid characterizes structure, with no utility objective or hyperparameter winner selected. Singleton retention remains min size 1.

{sensitive_table}

## Scalability and observed bottlenecks

{speed_table}

Extraction peak command RSS **{manifest['maximum_command_rss_mib']:.1f} MiB**; native network validator **{benchmark['network']['native_peak_rss_mib']:.1f} MiB**; Python experiment peak process RSS **{benchmark['process_peak_rss_mib']:.1f} MiB**. Cold compact neighbor revalidation reproduced the sparse pair table byte-for-byte, with wrapper time **{compact['network_seconds']:.2f} s**, serialization **{compact['serialization_seconds']:.2f} s**, parent peak **{compact['process_peak_rss_mib']:.1f} MiB** and native peak **{compact['native_peak_rss_mib']:.1f} MiB**. Native time file includes its separate measured wall time; the recorded wrapper network_seconds also includes initial Python typed-pair materialization. Current cold reproduction uses compact typed neighbor arrays to avoid that object overhead; the historical sparse-cache timing remains labelled and is not silently replaced. Final sequential OD experiment including features, clustering, sensitivity, statistics and serialization: **{benchmark['region_experiment_seconds']:.1f} s**. Graph loading and attachment are separate. Recorded peak process RSS is high-water memory, not simultaneous whole-server memory; source parsing and child peaks are separately measured. Rebuild extraction ran separately while the initial workload was being inspected; timings are workstation observations with warm caches, not controlled performance comparisons or interactive latency promises.

Partial benchmarks exposed quadratic parent traversal and expensive Python pair/union loops; path compression, compact neighbor arrays, SciPy sparse connectivity and the parity-tested native union kernel fixed the implementation bottlenecks. No frozen input changed and no partial result supplied scientific evidence. The verified native sparse-distance cache was reused for the final run; its original processing time/source/compiler record remains explicit. Ten million spatial pairs, Python pair objects, repeated region statistics and serialization are important costs; future scale should keep compact arrays and reuse sparse region topology. ODs stay sequential, distance pairs are computed once per OD and reused for seven budgets/sensitivity. No full graph copies or 30 concurrent distance caches are persisted.

## Outputs and diagnostics

Inventory, attachments, attachment_sensitivity, opportunity_density, extraction_exclusions, od_features, local_neighbor_pairs, regions, region_membership, region_stats, region_method_comparison, expansion_stability, parameter_sensitivity, performance Parquet; benchmark.json, quality_audit.json, network_benchmark.json, extraction.json, independent extraction_reproducibility.json, preservation records, tests.xml, logs and figures. benchmark.json checksums machine-readable tables. All new results live under results/milestone_4a; only compact metadata is Git-tracked. The raw activity PBF/inventory are independently checksummed under the separate opportunities raw directory.

Static figures: attachment audit in Ljubljana/Graz/Trieste, all-OD measured compression/coherence, full eligible-member route maps for representative ODs 0/4/21 at 1.10/1.40/2.00. SVG/PDF/PNG, plotted/source counts and QA notes are included. Maps are diagnostic, and membership/variance/connectivity tables are primary evidence. README gives exact reproduction commands; the independent rebuild uses a separate cache directory and refuses accidental overwrites.

## Provisional assessment and unresolved issues

The snapshot is reproducible, 97.31% attach within the documented 250 m approximation, sparse road validation is manageable offline, and the decision-aware range constraints provide measurable representation compression with substantially lower decision-feature dispersion. This supports proceeding to **offline microplan/gateway design and then explicit Go-1 abstraction-regret testing**, conditional on addressing access/topology and activity imbalance. It does not support a decision-preservation claim or unqualified online stability claim.

Before microplan compression: verify representative-to-entrance access (including fences/rivers/pedestrian/private links), quantify effects of parking dominance and missing activity tags/names, refine gateway extraction, measure full local microplan feasibility under directed roads and OD budgets, inspect unstable many-to-many region evolution, and consider alternate deterministic builders. The static graph still omits turn restrictions, node barriers, conditional legality, vehicle limits, traffic and ferry schedules. The nine maximum-budget boundary-risk ODs remain problematic for completeness. Source omissions and nonpolygon relations remain data limitations. Sensitivity is structural and cannot establish downstream utility robustness. No microplans or utility evaluation have been implemented or run.
'''
    (ROOT/'docs/MILESTONE_4A_REPORT.md').write_text(report)
    print('Wrote docs/MILESTONE_4A_REPORT.md')

if __name__=='__main__':main()
