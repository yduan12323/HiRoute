"""Write the M3A report only from measured, separately preserved results."""
import json
import xml.etree.ElementTree as ET

import pandas as pd

from _common import ROOT, sha256


def table(headers, rows):
    lines=['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
    return '\n'.join(lines+['| '+' | '.join(map(str,row))+' |' for row in rows])


def main():
    out=ROOT/'results/milestone_3a'
    result=json.loads((out/'benchmark.json').read_text())
    extraction=json.loads((out/'extraction_provenance.json').read_text())
    preservation=json.loads((out/'preservation_after.json').read_text())
    before=json.loads((out/'preservation_before.json').read_text())
    calibration=json.loads((out/'calibration.json').read_text())
    model=json.loads((out/'model_input_provenance.json').read_text())
    model_control=json.loads((out/'model_calibration.json').read_text())
    model_reproduction=json.loads((out/'model_input_reproducibility.json').read_text())
    reproducibility=json.loads((out/'extraction_reproducibility.json').read_text())
    guard=json.loads((out/'memory_guard.json').read_text())
    monitored=json.loads((out/'preprocessing_benchmark.json').read_text())
    design=json.loads((out/'region_design.json').read_text())
    chosen=next(r for r in design['candidates'] if r['margin_km']==extraction['config']['buffer_km'])
    rejected=json.loads((out/'candidate_100km_rejection.json').read_text())
    tests=ET.parse(out/'tests.xml').getroot()
    test_counts={key:sum(int(s.attrib.get(key,0)) for s in tests.iter('testsuite'))
                 for key in ['tests','failures','errors','skipped']}
    if (not preservation['passed'] or not reproducibility['byte_identical']
            or not calibration['parquet_byte_identical'] or not model_control['parquet_byte_identical']
            or not model_reproduction['byte_identical'] or not result['routing_configuration_identical']
            or result['containment_violations'] or test_counts['failures'] or test_counts['errors'] or test_counts['skipped']):
        raise RuntimeError('Measured acceptance evidence is incomplete or failed')
    baseline=pd.read_parquet(out/'baseline_comparison.parquet')
    envelopes=pd.read_parquet(out/'envelope_stats.parquet')
    max_risk_ids=envelopes.loc[envelopes.ratio.eq(2.) & envelopes.boundary_risk,'instance_id'].tolist()
    si1=json.loads((ROOT/'results/milestone_1/benchmark.json').read_text())
    si2=json.loads((ROOT/'results/milestone_2/benchmark.json').read_text())
    sources=table(['Dated source','Raw bytes','Snapshot UTC'],[
        (f"[{r['url'].split('/')[-1]}]({r['url']})",f"{r['size_bytes']:,}",r['snapshot_timestamp'])
        for r in extraction['source_records']])
    growth=table(['Ratio','SI boundary ODs','EXT boundary ODs','EXT median nodes','EXT median edges',
                  'Added nodes median','Added edges median','Occupied cells km² median','BBox km² median'],[
        (f"{r['ratio']:.2f}",int(r['si_boundary_risk_ods']),int(r['boundary_risk_ods']),
         f"{r['nodes_median']:,.0f}",f"{r['edges_median']:,.0f}",
         '—' if r['ratio']==1 else f"{r['delta_nodes_median']:,.0f}",
         '—' if r['ratio']==1 else f"{r['delta_edges_median']:,.0f}",
         f"{r['occupied_grid_area_km2_median']:,.1f}",f"{r['bbox_area_km2_median']:,.1f}")
        for r in result['growth']])
    spatial_comparison=table(['Ratio','SI median nodes','EXT median nodes','SI median edges',
        'EXT median edges','SI bbox km² median','EXT bbox km² median','EXT crop-risk ODs','EXT source-gap ODs'],[
        (f"{r['ratio']:.2f}",f"{r['si_nodes_median']:,.0f}",f"{r['nodes_median']:,.0f}",
         f"{r['si_edges_median']:,.0f}",f"{r['edges_median']:,.0f}",
         f"{r['si_bbox_area_km2_median']:,.1f}",f"{r['bbox_area_km2_median']:,.1f}",
         int(r['crop_boundary_risk_ods']),int(r['source_gap_risk_ods'])) for r in result['growth']])
    routes=table(['OD','Cities','SI C* s','EXT C* s','EXT − SI s','Change %','SI fastest km','EXT fastest km','Node Jaccard'],[
        (int(r.instance_id),f'{r.origin_city} → {r.destination_city}',f'{r.si_baseline_time_s:.2f}',
         f'{r.ext_baseline_time_s:.2f}',f'{r.time_difference_s:+.2f}',f'{100*r.relative_time_difference:+.3f}',
         f'{r.si_fastest_distance_m/1000:.2f}',f'{r.ext_fastest_distance_m/1000:.2f}',f'{r.route_osm_node_jaccard:.4f}')
        for r in baseline.itertuples()])
    extraction_seconds=sum(r['elapsed_seconds'] for r in extraction['commands'])
    geographic_seconds=sum(r['elapsed_seconds'] for r in extraction['commands'] if 'extract' in r['command'])
    streaming_peak=max(r['process_peak_rss_mib'] for r in extraction['commands'])
    metrics=table(['Measurement','Slovenia','Extended'],[
        ('Raw input to Pyrosm MiB',f"{si1['raw_pbf_bytes']/2**20:.2f}",f"{model['resulting_pbf_size_bytes']/2**20:.2f}"),
        ('Graph nodes',f"{si1['node_count']:,}",f"{result['node_count']:,}"),
        ('Directed edges',f"{si1['edge_count']:,}",f"{result['edge_count']:,}"),
        ('Processed graph MiB',f"{si1['processed_graph_bytes']/2**20:.2f}",f"{result['graph_storage_bytes']/2**20:.2f}"),
        ('Preprocessing seconds',f"{si1['preprocessing_seconds']:.2f}",f"{result['preprocessing_seconds']:.2f}"),
        ('Preprocessing peak RSS MiB',f"{si1['preprocessing_peak_rss_mib']:.1f}",f"{result['preprocessing_peak_rss_mib']:.1f}"),
        ('Verified graph load seconds',f"{si2['verified_graph_load_seconds']:.2f}",f"{result['load_seconds']:.2f}"),
        ('Forward distances median / p95 s',f"{si2['forward_seconds']['median']:.3f} / {si2['forward_seconds']['p95']:.3f}",f"{result['forward_seconds']['median']:.3f} / {result['forward_seconds']['p95']:.3f}"),
        ('Reverse distances median / p95 s',f"{si2['reverse_seconds']['median']:.3f} / {si2['reverse_seconds']['p95']:.3f}",f"{result['reverse_seconds']['median']:.3f} / {result['reverse_seconds']['p95']:.3f}"),
        ('Mask build median / p95 ms',f"{si2['envelope_build_ms']['median']:.3f} / {si2['envelope_build_ms']['p95']:.3f}",f"{result['mask_ms']['median']:.3f} / {result['mask_ms']['p95']:.3f}"),
        ('Envelope experiment process peak RSS MiB',f"{si2['peak_rss_mib']:.1f}",f"{result['process_peak_rss_mib']:.1f}")])
    material=baseline.loc[baseline.material_time_change]
    improved=baseline.loc[baseline.relative_time_difference<=-0.01]
    relevant=[r for r in result['growth'] if r['ratio'] in [1.05,1.1,1.2,1.4]]
    substantial=all(r['boundary_risk_ods'] <= .5*r['si_boundary_risk_ods'] for r in relevant)
    suitability=('Suitable as an empirical cross-border substrate for later Opportunity Region experiments in the practical range.'
                 if substantial else 'Boundary risk still limits some practical-budget experiments; use the reported risk flags and analyze the remaining cases before further expansion.')
    text=f'''# Milestone 3A — cross-border experimental graph

**Measured infrastructure milestone.** No Opportunity Region, semantic/LLM,
research acquisition module, utility model or decision-driven stopping code was implemented.
The authoritative specification remains unchanged, SHA256 `{sha256(ROOT/'RESEARCH_SPEC.md')}`.

## Preservation and motivation

Initial Git commit `{before['git_commit']}`, dirty state `{bool(before['git_status'])}`.
All **26** previous tests passed before changes. The original raw Slovenia PBF,
graph fingerprints, ODs and Milestone 1 preservation checkpoint were verified.
Final preservation verified **{preservation['verified_files']}** captured files and
the original PBF, with no changes. M1–M2 reports, original configs and results
remain intact. Final test suite: **{test_counts}**.

Slovenia alone was insufficient: 29/30 envelopes approached its extract boundary
at 2C*, 20 retained >50% of its graph, and some retained nearly the whole national
graph. Even at 1.05, 1.10, 1.20 and 1.40, boundary rates were 10, 14, 16 and 24 of
30. National truncation could therefore masquerade as bounded-detour structure.
The new graph isolates geographic extent while retaining the original cost model.

## Source and geographic choice

{sources}

All selected sources share **2026-09-29T20:22:51Z** exactly. The 2.325 GB Alps
candidate was inspected and rejected as the sole source because its polygon
does not contain Slovenia or adequately cover southern/eastern directions.
Full Europe and full Italy were unnecessarily large. Northeast Italy and the
five country sources supply a compact regional source union; Slovenia is reused.
See [data design](MILESTONE_3A_DATA_DESIGN.md) for pre-download inspection,
50/75/100/150/200 km candidate comparison and all size-estimate assumptions.

The selected **{chosen['margin_km']} km approximate metric buffer**, in EPSG:3035, covers
{chosen['area_km2']:,.0f} km² including sea. Its closest snapped OD endpoint is {chosen['minimum_endpoint_boundary_distance_km']:.2f} km from the
boundary. Buffer distance, projection and segmentation are configurable.
The base is the archived M2 extract proxy, not a claimed exact national border.
The initial 100 km candidate was rejected before Pyrosm: four source contributions
already merged to {rejected['merged_partial_pbf_bytes']:,} road-PBF bytes, implying
{rejected['partial_estimated_rss_gib']:.2f} GiB with the calibrated
safety factor, above the 38 GiB ceiling. The 75 km candidate was selected explicitly;
the original candidate polygon, configuration and measured probe remain separate.
The selected source proxies leave {result['source_gap_area_km2']:.2f} km² in the
southwestern Adriatic uncovered. **{result['source_gap_proximity_ods']} ODs** have
an envelope vertex within 1 km of that gap across the scheduled ratios.

## Immutable extraction and identical graph semantics

`osmium-tool 1.18.0` / libosmium 2.21.0 runs in a separate prefix; the original
Python environment and locks were retained, and no system packages changed.
Exact added package URLs/hashes are in `environment-osmium-linux-64.lock`;
host library versions and hashes are in `osmium_environment.json`.
Per source: two-pass `extract -s complete_ways` with the identical hashed GeoJSON,
then `tags-filter w/highway` with referenced nodes, then same-snapshot `merge`.
All way tags remain available. `check-refs` confirms way-node reference completeness.
Relations are not used by the unchanged static routing model.

Frozen cropped road PBF: **{extraction['resulting_pbf_size_bytes']:,} bytes**,
SHA256 `{extraction['resulting_pbf_sha256']}`.
Extraction polygon SHA256 `{extraction['polygon_sha256']}`.
The crop is read-only under `{extraction['config']['raw_dir']}/`; source downloads
are separately frozen under `data/raw/osm/regional_source/`.
An independent full streaming re-extraction reproduced **identical PBF bytes**.
Source checksums, URLs, timestamps, exact commands and measured resources are
recorded in `sources.json`, `DATA_MANIFEST.yaml`, `extraction_provenance.json`
and `extraction_reproducibility.json`, without substituting live/latest data.

The initial graph parse stopped at the unchanged normalizer's class-domain guard:
**125 segments from 21 ways** had `crossing`, `square`, `traffic_calming` or `yes`
as their highway value, with no cost in the original model. The failed parse
and its resources remain in `unsupported_input_probe.json`. A streaming class
audit and tiny Pyrosm driving probe reproduced these classes and counts.
The 21 ways, all their tags and references are archived separately. Only these
unmodelled classes are removed from a second immutable input; every other way,
all nodes and all remaining tags are retained. No speed or access assumption
was added, and the original strict normalizer remains unchanged.

Actual graph-input PBF: **{model['resulting_pbf_size_bytes']:,} bytes**, SHA256
`{model['resulting_pbf_sha256']}`, at `{model['resulting_pbf_path']}`.
Its independent filter reproduction is byte identical. `MODEL_DATA_MANIFEST.yaml`
and `model_input_provenance.json` link it to the full geographic crop and list all
quarantined OSM identities. A second Slovenia control used the identical filter
and reproduced both original graph files byte for byte. Unmodelled ways remain
outside the graph's cost domain; they are an explicit data/model limitation.

The road filter reduced Slovenia's input to {calibration['filtered_pbf_size_bytes']:,}
bytes. Its independent Pyrosm rebuild produced **byte-identical original node
and edge Parquet files**, using {calibration['preprocessing_peak_rss_mib']:.1f}
MiB RSS in {calibration['preprocessing_seconds']:.2f} s. The extended graph uses
the same Pyrosm driving filter, access hierarchy, posted/class speed assumptions,
directed/parallel-edge handling, one-way rules, units, normalization and metadata
schema. Changing a dataset does not reinterpret national symbolic speeds;
unsupported values retain the original documented fallback.

## Original ODs and baseline comparison

All **30** original ODs were mapped by retained **OSM node identity**, not reused
contiguous IDs or regenerated coordinates. Coordinate and original geodesic snap
errors were verified within 0.5 m; per-endpoint identities and errors are saved.
There are no silently resnapped ODs. New route edge sequences and cost sums were
checked. Material travel-time change means >=1% absolute relative difference,
configured in `regional.yaml`.

**{len(material)} ODs** materially changed travel time; **{len(improved)}** improved
by at least 1%. Material IDs: `{result['material_time_change_ods']}`.
Directed OSM-edge sequence changes: `{result['topology_changed_ods']}`. Edge
identity uses OSM way, source node, target node and direction; edge-set Jaccard
and original-edge retention are recorded in the CSV. The node-set Jaccard below
is an additional identity-based overlap diagnostic, not geometric overlap.
Smaller extended baselines demonstrate routes absent from the national extract;
they are a scientific observation, not an error. The CSV also reports both
distance-optimal lengths separately from the fastest-route lengths below.

{routes}

## Safe Detour Envelope and marginal growth

All original ratios **1.00, 1.05, 1.10, 1.20, 1.40, 1.60, 2.00** were measured;
the cap was not lowered. Distances are computed once per OD in the original
forward/outgoing and reverse/incoming directions. The existing mathematical
definition, numerical tolerance and path sampler are reused. There are
**{result['containment_checks']}** seeded path/budget checks and
**{result['containment_violations']}** violations; baseline containment,
edge endpoints, deterministic masks and nesting were also checked.

Each dataset uses **its own C***. Consequently, equal ratios need not mean equal
absolute budgets when a baseline improves; both budgets are retained in the
cross-dataset table. Absolute sizes accompany graph percentages. Occupied-cell
area counts 1 km² projected cells containing envelope vertices; it does not
measure continuous reachable land. Bounding-box area is a spatial extent proxy.
Per-OD extents, counts, fractions, timings and consecutive marginal changes are
in `envelope_stats.parquet` and `envelope_comparison.csv`.

{growth}

Absolute geographic and graph-size comparisons:

{spatial_comparison}

The first ratio has no previous expansion step. Later deltas are raw differences
between consecutive, unequally spaced ratios. Plots show all 30 ODs and medians,
with no graph subsampling: [growth preview](../results/milestone_3a/figures/absolute_marginal_growth.png)
and [boundary preview](../results/milestone_3a/figures/boundary_risk.png);
editable PDF/SVG and source data accompany them. Graph-size growth/saturation
describes computational price, **not decision-value growth/saturation**.

## Boundary sufficiency and remaining limitations

The equivalent M2 diagnostic flags an envelope vertex within 1 km of or outside
the inward-buffered extraction polygon. An additional source-gap proximity flag
is included in the extended risk total and recorded separately. The crop is an
actual extraction geometry; publisher source polygons remain date-independent
proxies. Complete ways can extend beyond the crop, and a node-based flag can miss
crossings inside long edges. Neither buffering nor a zero flag guarantees global
completeness for every <=2C* path. Missing OSM roads and the static legal-model
limitations remain: turn restrictions, node barriers, vehicle constraints,
conditional legality, traffic and ferry schedules are not enforced.

Source-gap geometry uses projection-first overlay, consistently with the region
design. The final consistency audit checked all {result['node_count']:,} graph vertices against
the earlier geographic-overlay diagnostic and found identical risk bits; saved
envelope counts and distance/search measurements are unchanged. The audit is
recorded in `source_gap_projection_check.json`.

The practical-budget risk-reduction criterion (at least halving every rate at
1.05/1.10/1.20/1.40) is **{substantial}**. {suitability}
Maximum-budget risk is reported above; no automatic repeated expansion follows
from remaining flagged ODs.
At 2.00C*, the flagged OD identities are `{max_risk_ids}`. All 30 ODs remain
in the experiment; these flags identify limitations without removing cases.

## Workstation cost and RAM guard

Streaming geographic extraction: **{geographic_seconds:.2f} s** total across six
sources. Geographic extraction + highway filtering + merge: **{extraction_seconds:.2f} s**.
These are measured processing time, excluding network acquisition. Per-command
peak RSS and elapsed time are retained; the largest streaming-command RSS was
**{streaming_peak:.1f} MiB**. Extraction, filtering, merging and Pyrosm builds
run under live memory guards.
Filtered-Slovenia amplification was used rather than relying solely on M1's
all-tag PBF ratio. With a 1.35 safety factor, the pre-run estimate was
**{guard['estimated_rss_gib']:.2f} GiB**, available RAM
**{guard['available_ram_gib']:.2f} GiB**; the guard allowed the run.
The monitor enforces <=38 GiB child-tree RSS and >=10 GiB available-memory reserve.
The measured minimum available RAM during construction was
**{monitored['minimum_available_gib']:.2f} GiB**; the monitor did not abort.

{metrics}

The original Slovenia preprocessing figures use the full all-tag PBF, whereas
the regional input is highway-filtered. The equal-graph Slovenia calibration
above is the corresponding road-only preprocessing control. Relative to that
control, extended preprocessing time is {result['preprocessing_seconds']/calibration['preprocessing_seconds']:.2f}×
and peak RSS is {result['preprocessing_peak_rss_mib']/calibration['preprocessing_peak_rss_mib']:.2f}×.
Distance-search comparisons use the unchanged original Slovenia graph directly.

The workstation is adequate for this measured **sequential offline** graph and
envelope workload. This does not establish interactive latency, many simultaneous
OD caches or capacity for unrestricted European parsing. Warm filesystem caches
and process high-water RSS limit cross-machine interpretation. Distance and mask
timings exclude sampling, spatial statistics, serialization and validation.
One OD distance cache and a few masks are live at a time. RSS includes graph
storage; the benchmark's extra original-node, original-route edge and spatial arrays are documented
by its source and recorded run metadata.

## Expansion controller and deferred research

`EnvelopeExpansionPolicy` declares `next_budget` and `should_stop`.
`FixedSchedulePolicy` traverses only the configured ratios and stops at schedule
exhaustion; `iter_policy_envelopes` independently enforces the hard cap and
strictly increasing finite budgets. A caller may supply a manual stop policy.
No utility proxy, graph-saturation stop or Opportunity Region generator exists.
Decision-driven stopping needs region discovery, region upper/lower bounds and
the current Top-K threshold; those research components remain explicitly deferred.

## Reproduction and acceptance

Exact commands are in [README](../README.md). Every graph/benchmark run records
Git state, configuration, seed, source hashes, packages and specification hash.
M1–M2 outputs are read only. New tables, comparisons, plots, logs and measurements
reside under `results/milestone_3a/`. Existing tests plus regional extraction,
polygon hashing, construction, remapping, containment, schema, boundary and policy
tests passed. Opportunity Region work must not proceed without explicit instruction.
'''
    (ROOT/'docs/MILESTONE_3A_REPORT.md').write_text(text)
    print('Wrote measured Milestone 3A report')


if __name__=='__main__':main()
