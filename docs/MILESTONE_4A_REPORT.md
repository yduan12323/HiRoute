# Milestone 4A — Opportunity substrate and route-attached regions

Measured user-agnostic representation experiment only. No optimal-decision preservation, abstraction regret, final Go-1 success, microplans, utility, preference, semantic/LLM, minimax-regret, acquisition or adaptive utility stopping implementation is claimed.

## Preservation and acceptance

Initial commit `e86a282025641e1fb22f541132f23955b0792002`, dirty state `False`. All **36** prior tests passed before implementation. The two previous preservation checkpoints, Slovenia/extended raw datasets and graph fingerprints, six dated source hashes/headers and the selected polygon were verified. Final preservation: **True**, 291 prior files, zero changes. `RESEARCH_SPEC.md` remains SHA256 `d594f4ac78e1bfe8903c98d48bb20c4e9e3f2b15f1e8fed5fedde964be7ead04`. Prior raw/processed/results files and graph/envelope modules were not regenerated or edited. Final acceptance suite: **{'tests': 64, 'failures': 0, 'errors': 0, 'skipped': 0}**.

All 30 frozen remapped ODs × all seven original ratios × both methods are retained: 420 summary rows; 360 consecutive-expansion records; 840 sensitivity records (30 ODs × four practical ratios × seven configurations). The nine risky 2.00C* ODs `[0, 1, 4, 9, 10, 16, 19, 22, 23]` remain explicitly flagged. No practical-range OD carries the previous crop/source-gap risk flag.

## Frozen opportunity dataset

`data/raw/opportunities/slovenia_extended_75km/opportunities-260929.osm.pbf` and `inventory.parquet`, with read-only MANIFEST.yaml and PROVENANCE.json. PBF SHA256 `ad646f1e5e211ddf32464638a638f0821d33bf274a2ed5c89ba5a7685a0eedbe`; inventory SHA256 `d467606df7061b05f87fbcbbc6c2e9dc8e25121bb64c86686cb54f82eb778fb7`. Both were independently rebuilt from all six original source PBFs and reproduced **identical bytes**. Snapshot **2026-09-29T20:22:51Z**, exact 75 km extraction GeoJSON SHA256 `6c9a928b81e9f356e9963f68819f878b34687b9659b42c863c2d9c5b23b21ce4`. No live OSM or newer snapshot. Source attribution: OpenStreetMap contributors / Geofabrik, ODbL 1.0.

Per source: osmium-tool 1.18.0 `tags-filter nwr/...` retains activity objects and referenced objects; `extract -s smart -S types=any` with the frozen polygon completes selected relation members; merge identical-snapshot extracts. This filter-first order avoids unrelated large relations while retaining activity geometry. Strategy semantics follow the [Osmium tags-filter](https://docs.osmcode.org/osmium/latest/osmium-tags-filter.html) and [smart extract](https://docs.osmcode.org/osmium/latest/osmium-extract.html) manuals. Only activity-filtered files are merged; no all-tag country union enters Pyrosm. Way-node reference checks found zero missing nodes. Full original OSM tags are retained, including uninterpreted/unknown attributes. Explicit taxonomy/exclusions live in configs/opportunity.yaml. Amenities: charging_station, restaurant/cafe/fast_food/food_court, pharmacy, toilets, parking; tourism: hotel/motel/hostel/guest_house; shop: supermarket/convenience; highway: rest_area/services. Explicit access=no/private is excluded. Parking-space objects and explicitly zero/one/two-space facilities are excluded. Unknown parking capacity stays unknown and does not imply a large facility. Remaining amenity=parking inventory can still include small untagged lots; this is a taxonomy limitation.

Candidates after taxonomy/exclusions in six cropped contributions: **106,280**; overlapping `(osm_type, osm_id)` copies: **990**; merged unique candidates: **105,290**. Different nearby businesses are never proximity-deduplicated. A physical facility may have separately tagged node/way/relation identities; semantic facility deduplication is deferred, so object counts are not certified business counts. Same-identity conflicting structured tags cause an error. **40** candidates are excluded from the usable inventory: {'no_exportable_geometry': 34, 'representative_outside_polygon': 6}. They remain auditable in the frozen PBF and extraction_exclusions.parquet. This is snapshot reproducibility relative to the source extracts, not a certificate of OSM completeness.

Node locations are exact OSM coordinates. Polygons/multipolygons use EPSG:3035 point-on-surface (never an out-of-object centroid); linear objects use normalized projected line midpoint. Polygon geometry takes priority when an OSM way also exports as a line. The representative point must lie inside the same research polygon. Unsupported/nonexportable relation geometries are counted explicitly. Original geometries, object identities, all source memberships, snapshot timestamp and geometry method are recorded. No entrance is inferred from an arbitrary nearby tag.

## Opportunity quality audit (completed before clustering)

Total located opportunities: **105,250**. Capability counts overlap for explicitly multi-tagged objects:

| Capability | Objects (nonexclusive) |
| --- | --- |
| charge | 2,796 |
| groceries | 7,300 |
| meal | 23,432 |
| parking | 58,340 |
| pharmacy | 1,833 |
| rest | 603 |
| services | 253 |
| sleep | 7,624 |
| toilets | 3,916 |

| Measure | Value |
| --- | --- |
| Node / way / relation counts | 37,146 / 67,163 / 941 |
| Missing name rate | 61.19% |
| Snap median / p95 / p99 m | 23.9 / 146.2 / 630.0 |
| Occupied 5 × 5 km cells | 3048 |
| Median / p95 / max objects per occupied cell | 11 / 135 / 1790 |

| Source membership (not country) | Objects |
| --- | --- |
| austria-260929 | 27,337 |
| hungary-260929 | 5,427 |
| slovenia-260929 | 24,361 |
| nord-est-260929 | 24,705 |
| croatia-260929 | 24,301 |
| bosnia-herzegovina-260929 | 109 |

Country is not inferred from which overlapping extract contains an object; explicit addr:country values remain raw evidence, including inconsistent values. The complete source/explicit-country distribution and density grid are in quality_audit.json and opportunity_density.parquet. Parking constitutes 55.4% of objects, so aggregate compression is parking-dominated; category-filtered follow-up is needed before an activity-wide generalization.

## Road attachment and threshold sensitivity

Find four nearest candidate nodes in a spherical index of nodes with both incoming and outgoing allowed local-road edges, then choose the smallest WGS84 geodesic distance, breaking ties by graph ID. Motorway/trunk lanes and their link ramps are excluded as snap targets. Original static routing access exclusions remain unchanged. Record contiguous access node and original OSM node ID; distance and status remain recorded even for excessive snaps. This checks local routability, not entrance-level access or an off-road connection's legality. A POI across a fence, river, restricted driveway or pedestrian area can still snap incorrectly; pairwise road validation cannot repair an incorrectly chosen access node.

Selected threshold **250 m**: **102,415 attached**, **2,835 excessive-snap rejections**. It retains 97.31% while 500 m adds only about 1.4 percentage points of coverage. Distribution and sensitivity justify an initial conservative cutoff, not a universally correct access distance.

| Threshold m | Attached | Rejected | Coverage |
| --- | --- | --- | --- |
| 100 | 96,712 | 8,538 | 91.89% |
| 250 | 102,415 | 2,835 | 97.31% |
| 500 | 103,930 | 1,320 | 98.75% |
| 1000 | 104,584 | 666 | 99.37% |

## OD-specific decision features and eligibility

Reuse the unchanged envelope API once per OD: forward `d_s(v)=d(s,v)` on outgoing edges; reverse `d_d(v)=d(v,d)` on incoming edges from destination. At selected access node v: `H=d_s+d_d`; detour `Delta=H-C*` seconds; detour ratio `delta=H/C*`; normalized progress `r=d_s/H`. C*>0 is required; unreachable nodes are excluded. Reachable r lies in [0,1] and describes base-cost journey stage, not geometric route projection. The normalized coordinate is stable across budgets because distances are unchanged within an OD. Eligibility is `H <= B + 1e-8 + 1e-10*B`, exactly the prior numerical policy. Snap distance is an attachment diagnostic and contributes no invented off-road travel time; later access modeling may change H. No Euclidean route buffer or scalar user utility is used.

Typed Opportunity, Provenance, OpportunityId, DecisionOpportunity, ODContext and OpportunityRegion representations live in src/opportunity. Decision features retain progress, absolute/relative detour, road node identity, geographic/projected location and capabilities. Protocol OpportunityRegionBuilder permits alternative builders. All member access nodes and the original graph/topology fingerprint remain available for later gateways. Region anchors are member locations; **gateway identification is deferred to 4B/4C**.

## Exact region definitions and comparison

**Geographic baseline:** radius-neighbor connected components with radius 1200 m, equivalent to DBSCAN min_samples=1. It uses no decision or road features and retains singleton objects. Geographic chaining can create very large urban regions; this is a labelled baseline behavior, not the proposed abstraction.

**Decision-aware:** deterministic sparse agglomeration. Candidate links require geography <=1200 m and both directed road distances <=2500 m. Process links in ascending geographic distance then stable OSM identities. Merge only if the whole resulting component has progress range <=0.025, absolute detour range <=180 s, and projected bounding-box diagonal <=3000 m. Range constraints prevent progress/detour chaining beyond the configured tolerance. Every opportunity remains represented, including singleton regions. Activity capabilities are summarized after grouping, permitting related/complementary activities without learned embeddings or quality assumptions. These are representation hyperparameters, not user preference weights or claimed optimal constants.

Network pair screening indexes projected POI coordinates at maximum sensitivity radius 1800 m. A native C++17 bounded directed Dijkstra validator computes only sparse candidate pairs, with a 2500 m cutoff, batching requests sharing an access node. Both directions must pass; one-way asymmetry or a missing nearby river crossing can reject a pair. `inf` denotes beyond cutoff or unreachable, not proof of global disconnection. Search can use any original graph edges, not only envelope edges; it measures local structural road connectivity and does not certify that a multi-POI tour respects the OD budget. One transient CSR adjacency index exists in the native subprocess, no copied full graph is saved. The original igraph stays shared across budgets/ODs. Native source/compiler and cache provenance are hashed. Compact typed neighbor arrays and a C++ constrained-union kernel accelerate the same transparent algorithm; seeded empty/singleton/random toy cases verify exact region/statistic agreement with the Python reference. No all-pairs POI matrix is computed.

There are **10,053,530 spatial candidate pairs**, **7,890,792** pass both directed cutoffs. Connectivity diagnostics measure components under those validated local links. Decision regions have a connected local spanning graph; neither all-pairs network diameter nor bundle feasibility is asserted. Geographic spread is the bbox-diagonal upper bound on Euclidean diameter. `validated_network_edge_max_m` reports local accepted link spread, with finite-cutoff pair fraction and local component counts preserved per region. This is an explicitly limited network-spread diagnostic, not a hidden replacement by straight-line distances.

## Compression across budgets

All entries below are medians across 30 ODs; count medians and compression medians are computed separately and need not give the same quotient. Compression is `1-region_count/eligible_count` within each OD. Empty opportunity sets have undefined compression/singleton fractions, retained as null. The primary practical range is 1.05–1.40; 1.00, 1.60 and 2.00 remain measured.

| Ratio | Median eligible | Median geographic regions | Median decision regions | Median geographic reduction | Median decision reduction | Risk ODs |
| --- | --- | --- | --- | --- | --- | --- |
| 1.00 | 35.0 | 3.0 | 6.5 | 90.4% | 84.5% | 0 |
| 1.05 | 2,571.0 | 34.5 | 104.0 | 98.7% | 95.9% | 0 |
| 1.10 | 5,370.0 | 72.0 | 239.5 | 98.5% | 95.1% | 0 |
| 1.20 | 7,976.5 | 183.0 | 537.5 | 97.5% | 93.1% | 0 |
| 1.40 | 12,702.0 | 441.0 | 1,052.5 | 96.2% | 91.3% | 0 |
| 1.60 | 18,120.5 | 759.0 | 1,703.5 | 96.1% | 90.6% | 0 |
| 2.00 | 31,971.5 | 1,401.5 | 3,321.0 | 95.7% | 90.2% | 9 |

This is **representation compression only**, not decision-space abstraction regret or Go-1 acceptance.

## Decision coherence and geographic baseline

Practical-range table: medians across 120 OD-budget observations. Progress/detour variance is within-region population variance weighted by member count; singleton variance is zero. Including singletons can reward fragmentation, so compression and singleton rate accompany dispersion. Connectivity fraction uses the same screened road-distance graph for both methods.

| Method | Median weighted progress variance | Median weighted detour variance s² | Median mean bbox diagonal m | Median singleton fraction | Median disconnected fraction | Median mean capabilities |
| --- | --- | --- | --- | --- | --- | --- |
| decision-aware | 1.32896e-05 | 1630.46 | 840.0 | 17.2% | 0.00% | 2.85 |
| geographic baseline | 0.000352319 | 18659.29 | 1566.4 | 22.7% | 4.56% | 2.93 |

Median paired reduction of weighted progress variance: **96.9%**; detour variance: **91.5%**. These are descriptive same-OD comparisons, without significance tests or a downstream objective. Whole-region constraints mechanically limit dispersion; observed compression determines whether this limit is useful. Geography does not necessarily become less compact: bounded agglomeration can also be geographically smaller than the chaining baseline. No anticipated tradeoff is assumed in advance.

## Envelope expansion stability

ARI compares partitions on the intersection of old/new eligible members; it ignores the new members. Best-region Jaccard compares each old region's complete member set against candidate new full sets, and is averaged unweighted across old regions. New regions contain no old members. A merge means a new region overlaps multiple old regions; a split means an old region overlaps multiple new regions. Many-to-many evolution can count both. IDs are content-derived, not persistent tracked gateway identities. No strict nesting is imposed. No members disappear under expansion.

| Method | Expansion | Median ARI common members | Median best full Jaccard | Median new regions | Median merges | Median splits |
| --- | --- | --- | --- | --- | --- | --- |
| decision-aware | 1.00→1.05 | 0.783 | 0.313 | 97.0 | 0.5 | 1.0 |
| decision-aware | 1.05→1.10 | 0.867 | 0.812 | 123.5 | 9.0 | 18.5 |
| decision-aware | 1.10→1.20 | 0.991 | 0.947 | 266.0 | 5.0 | 14.0 |
| decision-aware | 1.20→1.40 | 0.993 | 0.974 | 516.5 | 5.0 | 13.0 |
| decision-aware | 1.40→1.60 | 0.999 | 0.988 | 677.0 | 3.0 | 9.0 |
| decision-aware | 1.60→2.00 | 0.995 | 0.991 | 1432.0 | 3.0 | 12.0 |
| geographic baseline | 1.00→1.05 | 1.000 | 0.072 | 29.5 | 0.0 | 0.0 |
| geographic baseline | 1.05→1.10 | 0.987 | 0.584 | 43.0 | 3.0 | 0.0 |
| geographic baseline | 1.10→1.20 | 0.995 | 0.826 | 119.5 | 3.0 | 0.0 |
| geographic baseline | 1.20→1.40 | 0.996 | 0.916 | 239.5 | 3.0 | 0.0 |
| geographic baseline | 1.40→1.60 | 0.996 | 0.957 | 335.0 | 4.0 | 0.0 |
| geographic baseline | 1.60→2.00 | 1.000 | 0.966 | 657.5 | 3.5 | 0.0 |

Least-stable decision-aware examples (explicitly retained):

| OD | Expansion | ARI | Best Jaccard | Merges | Splits |
| --- | --- | --- | --- | --- | --- |
| 14 | 1.00→1.05 | 0.433 | 0.110 | 1 | 3 |
| 16 | 1.00→1.05 | 0.444 | 0.308 | 0 | 1 |
| 1 | 1.00→1.05 | 0.589 | 0.327 | 0 | 1 |
| 15 | 1.00→1.05 | 0.595 | 0.356 | 0 | 1 |
| 29 | 1.00→1.05 | 0.597 | 0.191 | 1 | 1 |
| 4 | 1.00→1.05 | 0.607 | 0.372 | 1 | 2 |
| 29 | 1.05→1.10 | 0.623 | 0.750 | 18 | 32 |
| 7 | 1.05→1.10 | 0.629 | 0.650 | 10 | 18 |

ARI/Jaccard agreement must be read together; a high common-member ARI can hide substantial member growth. Deterministic greedy union can split regions when earlier new links alter allowed range unions. That instability is real, not renamed away. Persistent evolution/matching and gateway semantics require further work before online adaptive planning.

## Multi-capability co-location

Median number of decision-aware regions carrying each capability pair across 30 ODs:

| Ratio | charge + meal | charge + parking | meal + parking | sleep + charge | services + meal |
| --- | --- | --- | --- | --- | --- |
| 1.05 | 21.5 | 22.0 | 69.5 | 13.0 | 3.0 |
| 1.10 | 36.0 | 41.0 | 150.5 | 25.0 | 6.5 |
| 1.20 | 61.5 | 71.5 | 278.5 | 41.5 | 12.5 |
| 1.40 | 103.5 | 114.0 | 494.0 | 69.0 | 21.5 |

Capabilities may come from different region members or explicit multiple tags on one object. Co-location is structured OSM evidence only: it does not establish compatible opening hours, walking access, concurrent dwell, charger reliability, quality or feasible activity bundles. No bundling optimization or synthetic quality attributes were introduced.

## Parameter sensitivity

One-at-a-time progress 0.015/0.04, detour 120/300 s, local radius 750/1800 m, and default, for all ODs at four practical budgets. Road cutoff 2500 m and geographic span 3000 m remain fixed. This modest seven-configuration grid characterizes structure, with no utility objective or hyperparameter winner selected. Singleton retention remains min size 1.

| Configuration | Median regions | Median compression | Median progress variance | Median detour variance s² | Median cluster seconds |
| --- | --- | --- | --- | --- | --- |
| default | 274.0 | 94.0% | 1.32896e-05 | 1630.46 | 0.039 |
| detour_loose | 218.5 | 95.3% | 1.51566e-05 | 3267.85 | 0.038 |
| detour_tight | 365.5 | 92.4% | 1.16556e-05 | 842.27 | 0.040 |
| progress_loose | 272.0 | 94.2% | 1.69264e-05 | 1646.74 | 0.039 |
| progress_tight | 320.0 | 92.9% | 7.5887e-06 | 1594.42 | 0.038 |
| radius_loose | 259.0 | 94.4% | 1.39466e-05 | 1655.97 | 0.048 |
| radius_tight | 326.5 | 93.2% | 1.23236e-05 | 1558.02 | 0.034 |

## Scalability and observed bottlenecks

| Stage | Measurements | Median seconds | p95 seconds |
| --- | --- | --- | --- |
| bounded_network_validation | 1 | 38.8103 | 38.8103 |
| distance_precomputation | 30 | 7.3032 | 7.6894 |
| global_spatial_neighbors | 1 | 0.2951 | 0.2951 |
| graph_attachment | 1 | 23.3308 | 23.3308 |
| graph_load | 1 | 9.9366 | 9.9366 |
| od_features | 30 | 0.3022 | 0.7542 |
| od_sparse_neighbors | 30 | 0.2722 | 0.3299 |
| region_clustering / decision-aware | 210 | 0.0409 | 0.5104 |
| region_clustering / geographic baseline | 210 | 0.0661 | 0.4848 |
| snapshot_extraction | 1 | 118.3007 | 118.3007 |
| snapshot_parsing | 1 | 19.7308 | 19.7308 |

Extraction peak command RSS **3784.5 MiB**; native network validator **1037.2 MiB**; Python experiment peak process RSS **5344.3 MiB**. Cold compact neighbor revalidation reproduced the sparse pair table byte-for-byte, with wrapper time **16.89 s**, serialization **1.87 s**, parent peak **5058.8 MiB** and native peak **1037.0 MiB**. Native time file includes its separate measured wall time; the recorded wrapper network_seconds also includes initial Python typed-pair materialization. Current cold reproduction uses compact typed neighbor arrays to avoid that object overhead; the historical sparse-cache timing remains labelled and is not silently replaced. Final sequential OD experiment including features, clustering, sensitivity, statistics and serialization: **552.2 s**. Graph loading and attachment are separate. Recorded peak process RSS is high-water memory, not simultaneous whole-server memory; source parsing and child peaks are separately measured. Rebuild extraction ran separately while the initial workload was being inspected; timings are workstation observations with warm caches, not controlled performance comparisons or interactive latency promises.

Partial benchmarks exposed quadratic parent traversal and expensive Python pair/union loops; path compression, compact neighbor arrays, SciPy sparse connectivity and the parity-tested native union kernel fixed the implementation bottlenecks. No frozen input changed and no partial result supplied scientific evidence. The verified native sparse-distance cache was reused for the final run; its original processing time/source/compiler record remains explicit. Ten million spatial pairs, Python pair objects, repeated region statistics and serialization are important costs; future scale should keep compact arrays and reuse sparse region topology. ODs stay sequential, distance pairs are computed once per OD and reused for seven budgets/sensitivity. No full graph copies or 30 concurrent distance caches are persisted.

## Outputs and diagnostics

Inventory, attachments, attachment_sensitivity, opportunity_density, extraction_exclusions, od_features, local_neighbor_pairs, regions, region_membership, region_stats, region_method_comparison, expansion_stability, parameter_sensitivity, performance Parquet; benchmark.json, quality_audit.json, network_benchmark.json, extraction.json, independent extraction_reproducibility.json, preservation records, tests.xml, logs and figures. benchmark.json checksums machine-readable tables. All new results live under results/milestone_4a; only compact metadata is Git-tracked. The raw activity PBF/inventory are independently checksummed under the separate opportunities raw directory.

Static figures: attachment audit in Ljubljana/Graz/Trieste, all-OD measured compression/coherence, full eligible-member route maps for representative ODs 0/4/21 at 1.10/1.40/2.00. SVG/PDF/PNG, plotted/source counts and QA notes are included. Maps are diagnostic, and membership/variance/connectivity tables are primary evidence. README gives exact reproduction commands; the independent rebuild uses a separate cache directory and refuses accidental overwrites.

## Provisional assessment and unresolved issues

The snapshot is reproducible, 97.31% attach within the documented 250 m approximation, sparse road validation is manageable offline, and the decision-aware range constraints provide measurable representation compression with substantially lower decision-feature dispersion. This supports proceeding to **offline microplan/gateway design and then explicit Go-1 abstraction-regret testing**, conditional on addressing access/topology and activity imbalance. It does not support a decision-preservation claim or unqualified online stability claim.

Before microplan compression: verify representative-to-entrance access (including fences/rivers/pedestrian/private links), quantify effects of parking dominance and missing activity tags/names, refine gateway extraction, measure full local microplan feasibility under directed roads and OD budgets, inspect unstable many-to-many region evolution, and consider alternate deterministic builders. The static graph still omits turn restrictions, node barriers, conditional legality, vehicle limits, traffic and ferry schedules. The nine maximum-budget boundary-risk ODs remain problematic for completeness. Source omissions and nonpolygon relations remain data limitations. Sensitivity is structural and cannot establish downstream utility robustness. No microplans or utility evaluation have been implemented or run.
