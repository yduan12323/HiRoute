# Milestone 3A — cross-border experimental graph

**Measured infrastructure milestone.** No Opportunity Region, semantic/LLM,
research acquisition module, utility model or decision-driven stopping code was implemented.
The authoritative specification remains unchanged, SHA256 `d594f4ac78e1bfe8903c98d48bb20c4e9e3f2b15f1e8fed5fedde964be7ead04`.

## Preservation and motivation

Initial Git commit `c70c1760c20b255e374da594d6ab6161e3f2a817`, dirty state `False`.
All **26** previous tests passed before changes. The original raw Slovenia PBF,
graph fingerprints, ODs and Milestone 1 preservation checkpoint were verified.
Final preservation verified **71** captured files and
the original PBF, with no changes. M1–M2 reports, original configs and results
remain intact. Final test suite: **{'tests': 36, 'failures': 0, 'errors': 0, 'skipped': 0}**.

Slovenia alone was insufficient: 29/30 envelopes approached its extract boundary
at 2C*, 20 retained >50% of its graph, and some retained nearly the whole national
graph. Even at 1.05, 1.10, 1.20 and 1.40, boundary rates were 10, 14, 16 and 24 of
30. National truncation could therefore masquerade as bounded-detour structure.
The new graph isolates geographic extent while retaining the original cost model.

## Source and geographic choice

| Dated source | Raw bytes | Snapshot UTC |
| --- | --- | --- |
| [austria-260929.osm.pbf](https://download.geofabrik.de/europe/austria-260929.osm.pbf) | 811,274,125 | 2026-09-29T20:22:51+00:00 |
| [nord-est-260929.osm.pbf](https://download.geofabrik.de/europe/italy/nord-est-260929.osm.pbf) | 624,289,999 | 2026-09-29T20:22:51+00:00 |
| [croatia-260929.osm.pbf](https://download.geofabrik.de/europe/croatia-260929.osm.pbf) | 200,023,570 | 2026-09-29T20:22:51+00:00 |
| [hungary-260929.osm.pbf](https://download.geofabrik.de/europe/hungary-260929.osm.pbf) | 325,903,232 | 2026-09-29T20:22:51+00:00 |
| [bosnia-herzegovina-260929.osm.pbf](https://download.geofabrik.de/europe/bosnia-herzegovina-260929.osm.pbf) | 161,358,110 | 2026-09-29T20:22:51+00:00 |
| [slovenia-260929.osm.pbf](https://download.geofabrik.de/europe/slovenia-260929.osm.pbf) | 313,378,108 | 2026-09-29T20:22:51+00:00 |

All selected sources share **2026-09-29T20:22:51Z** exactly. The 2.325 GB Alps
candidate was inspected and rejected as the sole source because its polygon
does not contain Slovenia or adequately cover southern/eastern directions.
Full Europe and full Italy were unnecessarily large. Northeast Italy and the
five country sources supply a compact regional source union; Slovenia is reused.
See [data design](MILESTONE_3A_DATA_DESIGN.md) for pre-download inspection,
50/75/100/150/200 km candidate comparison and all size-estimate assumptions.

The selected **75 km approximate metric buffer**, in EPSG:3035, covers
94,932 km² including sea. Its closest snapped OD endpoint is 79.28 km from the
boundary. Buffer distance, projection and segmentation are configurable.
The base is the archived M2 extract proxy, not a claimed exact national border.
The initial 100 km candidate was rejected before Pyrosm: four source contributions
already merged to 202,660,509 road-PBF bytes, implying
40.48 GiB with the calibrated
safety factor, above the 38 GiB ceiling. The 75 km candidate was selected explicitly;
the original candidate polygon, configuration and measured probe remain separate.
The selected source proxies leave 38.21 km² in the
southwestern Adriatic uncovered. **0 ODs** have
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

Frozen cropped road PBF: **175,103,959 bytes**,
SHA256 `af94c57d06b62dc0c53900eaf64c0d7d496c0cc14e14b7ebf8d8f030182097b2`.
Extraction polygon SHA256 `6c9a928b81e9f356e9963f68819f878b34687b9659b42c863c2d9c5b23b21ce4`.
The crop is read-only under `data/raw/osm/slovenia_extended_75km/`; source downloads
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

Actual graph-input PBF: **175,103,895 bytes**, SHA256
`e10a5d4bb2a927d1bdcf21a41d30971a9301a82e08656c0419ef45e3f92de7a7`, at `data/raw/osm/slovenia_extended_75km/slovenia_extended-modeled-260929.osm.pbf`.
Its independent filter reproduction is byte identical. `MODEL_DATA_MANIFEST.yaml`
and `model_input_provenance.json` link it to the full geographic crop and list all
quarantined OSM identities. A second Slovenia control used the identical filter
and reproduced both original graph files byte for byte. Unmodelled ways remain
outside the graph's cost domain; they are an explicit data/model limitation.

The road filter reduced Slovenia's input to 53,047,053
bytes. Its independent Pyrosm rebuild produced **byte-identical original node
and edge Parquet files**, using 8037.0
MiB RSS in 49.68 s. The extended graph uses
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

**2 ODs** materially changed travel time; **2** improved
by at least 1%. Material IDs: `[4, 21]`.
Directed OSM-edge sequence changes: `[4, 21]`. Edge
identity uses OSM way, source node, target node and direction; edge-set Jaccard
and original-edge retention are recorded in the CSV. The node-set Jaccard below
is an additional identity-based overlap diagnostic, not geometric overlap.
Smaller extended baselines demonstrate routes absent from the national extract;
they are a scientific observation, not an error. The CSV also reports both
distance-optimal lengths separately from the fastest-route lengths below.

| OD | Cities | SI C* s | EXT C* s | EXT − SI s | Change % | SI fastest km | EXT fastest km | Node Jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | Piran → Murska_Sobota | 10653.42 | 10653.42 | +0.00 | +0.000 | 298.44 | 298.44 | 1.0000 |
| 1 | Koper → Murska_Sobota | 9989.52 | 9989.52 | +0.00 | +0.000 | 287.95 | 287.95 | 1.0000 |
| 2 | Ljubljana → Slovenj_Gradec | 4671.59 | 4671.59 | +0.00 | +0.000 | 106.92 | 106.92 | 1.0000 |
| 3 | Slovenj_Gradec → Ptuj | 4163.41 | 4163.41 | +0.00 | +0.000 | 87.55 | 87.55 | 1.0000 |
| 4 | Novo_mesto → Murska_Sobota | 8332.08 | 8067.34 | -264.74 | -3.177 | 189.72 | 198.17 | 0.1708 |
| 5 | Novo_mesto → Slovenj_Gradec | 6697.25 | 6697.25 | +0.00 | +0.000 | 166.15 | 166.15 | 1.0000 |
| 6 | Postojna → Kranj | 2942.11 | 2942.11 | +0.00 | +0.000 | 78.70 | 78.70 | 1.0000 |
| 7 | Postojna → Celje | 4667.11 | 4667.11 | +0.00 | +0.000 | 132.11 | 132.11 | 1.0000 |
| 8 | Murska_Sobota → Postojna | 8118.19 | 8118.19 | +0.00 | +0.000 | 232.89 | 232.89 | 1.0000 |
| 9 | Maribor → Nova_Gorica | 8534.70 | 8534.70 | +0.00 | +0.000 | 236.37 | 236.37 | 1.0000 |
| 10 | Murska_Sobota → Bled | 8095.05 | 8095.05 | +0.00 | +0.000 | 214.81 | 214.81 | 1.0000 |
| 11 | Koper → Maribor | 8288.69 | 8288.69 | +0.00 | +0.000 | 236.32 | 236.32 | 1.0000 |
| 12 | Bled → Postojna | 3652.34 | 3652.34 | +0.00 | +0.000 | 101.44 | 101.44 | 1.0000 |
| 13 | Celje → Novo_mesto | 4620.62 | 4620.62 | +0.00 | +0.000 | 85.92 | 85.92 | 1.0000 |
| 14 | Murska_Sobota → Maribor | 2194.22 | 2194.22 | +0.00 | +0.000 | 55.19 | 55.19 | 1.0000 |
| 15 | Bled → Koper | 5498.76 | 5498.76 | +0.00 | +0.000 | 154.62 | 154.62 | 1.0000 |
| 16 | Koper → Ptuj | 8641.24 | 8641.24 | +0.00 | +0.000 | 243.29 | 243.29 | 1.0000 |
| 17 | Ptuj → Velenje | 3601.45 | 3601.45 | +0.00 | +0.000 | 79.05 | 79.05 | 1.0000 |
| 18 | Celje → Nova_Gorica | 6917.73 | 6917.73 | +0.00 | +0.000 | 187.42 | 187.42 | 1.0000 |
| 19 | Piran → Murska_Sobota | 10950.25 | 10950.25 | +0.00 | +0.000 | 301.77 | 301.77 | 1.0000 |
| 20 | Ljubljana → Novo_mesto | 2599.00 | 2599.00 | +0.00 | +0.000 | 65.75 | 65.75 | 1.0000 |
| 21 | Nova_Gorica → Bled | 6400.97 | 6266.79 | -134.18 | -2.096 | 159.49 | 157.62 | 0.9035 |
| 22 | Nova_Gorica → Maribor | 8987.14 | 8987.14 | +0.00 | +0.000 | 238.70 | 238.70 | 1.0000 |
| 23 | Piran → Slovenj_Gradec | 9194.94 | 9194.94 | +0.00 | +0.000 | 228.99 | 228.99 | 1.0000 |
| 24 | Postojna → Slovenj_Gradec | 6374.82 | 6374.82 | +0.00 | +0.000 | 161.06 | 161.06 | 1.0000 |
| 25 | Kranj → Slovenj_Gradec | 5796.55 | 5796.55 | +0.00 | +0.000 | 121.24 | 121.24 | 1.0000 |
| 26 | Koper → Novo_mesto | 5977.33 | 5977.33 | +0.00 | +0.000 | 169.01 | 169.01 | 1.0000 |
| 27 | Celje → Ljubljana | 2889.29 | 2889.29 | +0.00 | +0.000 | 76.55 | 76.55 | 1.0000 |
| 28 | Celje → Maribor | 2365.92 | 2365.92 | +0.00 | +0.000 | 59.64 | 59.64 | 1.0000 |
| 29 | Koper → Celje | 6424.18 | 6424.18 | +0.00 | +0.000 | 184.47 | 184.47 | 1.0000 |

## Safe Detour Envelope and marginal growth

All original ratios **1.00, 1.05, 1.10, 1.20, 1.40, 1.60, 2.00** were measured;
the cap was not lowered. Distances are computed once per OD in the original
forward/outgoing and reverse/incoming directions. The existing mathematical
definition, numerical tolerance and path sampler are reused. There are
**2730** seeded path/budget checks and
**0** violations; baseline containment,
edge endpoints, deterministic masks and nesting were also checked.

Each dataset uses **its own C***. Consequently, equal ratios need not mean equal
absolute budgets when a baseline improves; both budgets are retained in the
cross-dataset table. Absolute sizes accompany graph percentages. Occupied-cell
area counts 1 km² projected cells containing envelope vertices; it does not
measure continuous reachable land. Bounding-box area is a spatial extent proxy.
Per-OD extents, counts, fractions, timings and consecutive marginal changes are
in `envelope_stats.parquet` and `envelope_comparison.csv`.

| Ratio | SI boundary ODs | EXT boundary ODs | EXT median nodes | EXT median edges | Added nodes median | Added edges median | Occupied cells km² median | BBox km² median |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.00 | 4 | 0 | 2,775 | 2,774 | — | — | 198.0 | 5,692.2 |
| 1.05 | 10 | 0 | 63,347 | 112,298 | 60,572 | 109,524 | 501.5 | 6,354.5 |
| 1.10 | 14 | 0 | 143,502 | 268,802 | 79,634 | 155,650 | 958.5 | 7,583.4 |
| 1.20 | 16 | 0 | 310,326 | 590,786 | 164,513 | 318,399 | 2,245.5 | 9,601.4 |
| 1.40 | 24 | 0 | 703,036 | 1,374,075 | 392,620 | 779,164 | 5,286.0 | 16,204.5 |
| 1.60 | 27 | 0 | 1,146,368 | 2,236,031 | 443,116 | 876,762 | 9,049.5 | 22,800.0 |
| 2.00 | 29 | 9 | 2,076,099 | 4,089,377 | 929,814 | 1,835,154 | 16,476.5 | 39,676.3 |

Absolute geographic and graph-size comparisons:

| Ratio | SI median nodes | EXT median nodes | SI median edges | EXT median edges | SI bbox km² median | EXT bbox km² median | EXT crop-risk ODs | EXT source-gap ODs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.00 | 2,804 | 2,775 | 2,804 | 2,774 | 5,692.2 | 5,692.2 | 0 | 0 |
| 1.05 | 63,347 | 63,347 | 112,298 | 112,298 | 6,354.5 | 6,354.5 | 0 | 0 |
| 1.10 | 142,996 | 143,502 | 267,936 | 268,802 | 7,583.4 | 7,583.4 | 0 | 0 |
| 1.20 | 273,459 | 310,326 | 528,022 | 590,786 | 9,601.4 | 9,601.4 | 0 | 0 |
| 1.40 | 602,734 | 703,036 | 1,186,188 | 1,374,075 | 13,111.4 | 16,204.5 | 0 | 0 |
| 1.60 | 948,718 | 1,146,368 | 1,874,462 | 2,236,031 | 16,786.6 | 22,800.0 | 0 | 0 |
| 2.00 | 1,630,290 | 2,076,099 | 3,227,289 | 4,089,377 | 25,493.9 | 39,676.3 | 9 | 0 |

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
design. The final consistency audit checked all 5,892,498 graph vertices against
the earlier geographic-overlay diagnostic and found identical risk bits; saved
envelope counts and distance/search measurements are unchanged. The audit is
recorded in `source_gap_projection_check.json`.

The practical-budget risk-reduction criterion (at least halving every rate at
1.05/1.10/1.20/1.40) is **True**. Suitable as an empirical cross-border substrate for later Opportunity Region experiments in the practical range.
Maximum-budget risk is reported above; no automatic repeated expansion follows
from remaining flagged ODs.
At 2.00C*, the flagged OD identities are `[0, 1, 4, 9, 10, 16, 19, 22, 23]`. All 30 ODs remain
in the experiment; these flags identify limitations without removing cases.

## Workstation cost and RAM guard

Streaming geographic extraction: **99.10 s** total across six
sources. Geographic extraction + highway filtering + merge: **139.14 s**.
These are measured processing time, excluding network acquisition. Per-command
peak RSS and elapsed time are retained; the largest streaming-command RSS was
**3733.8 MiB**. Extraction, filtering, merging and Pyrosm builds
run under live memory guards.
Filtered-Slovenia amplification was used rather than relying solely on M1's
all-tag PBF ratio. With a 1.35 safety factor, the pre-run estimate was
**35.11 GiB**, available RAM
**49.89 GiB**; the guard allowed the run.
The monitor enforces <=38 GiB child-tree RSS and >=10 GiB available-memory reserve.
The measured minimum available RAM during construction was
**28.81 GiB**; the monitor did not abort.

| Measurement | Slovenia | Extended |
| --- | --- | --- |
| Raw input to Pyrosm MiB | 298.86 | 166.99 |
| Graph nodes | 2,220,917 | 5,892,498 |
| Directed edges | 4,401,596 | 11,561,067 |
| Processed graph MiB | 141.03 | 388.63 |
| Preprocessing seconds | 106.93 | 157.14 |
| Preprocessing peak RSS MiB | 16666.8 | 22015.0 |
| Verified graph load seconds | 3.85 | 9.91 |
| Forward distances median / p95 s | 1.130 / 1.156 | 3.506 / 3.577 |
| Reverse distances median / p95 s | 1.163 / 1.198 | 3.602 / 3.664 |
| Mask build median / p95 ms | 5.831 / 6.105 | 15.446 / 16.129 |
| Envelope experiment process peak RSS MiB | 1649.7 | 5039.8 |

The original Slovenia preprocessing figures use the full all-tag PBF, whereas
the regional input is highway-filtered. The equal-graph Slovenia calibration
above is the corresponding road-only preprocessing control. Relative to that
control, extended preprocessing time is 3.16×
and peak RSS is 2.74×.
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
