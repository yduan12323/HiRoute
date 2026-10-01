# Milestone 3A data design

The existing Slovenia experiment reaches the national-extract boundary in 4, 10,
14, 16, 24, 27 and 29 of 30 ODs at ratios 1.00–2.00. At 2.00, 20 ODs retain
more than half the graph. This makes national truncation a plausible confounder.
The original graph, PBF, ODs and results remain the smoke-test substrate.

## Source investigation before large downloads

All selected sources are dated **260929**, matching Slovenia's OSM header time
2026-09-29T20:22:51Z. HTTP inspection confirmed these raw sizes:

| Candidate | Bytes | Decision |
| --- | ---: | --- |
| Alps | 2,324,621,979 | Reject as sole source: geographic polygon excludes most southern/eastern surroundings and does not contain Slovenia |
| Austria | 811,274,125 | Select for northern roads |
| Northeast Italy | 624,289,999 | Select for western roads; avoids full Italy (2,235,355,972 bytes) |
| Croatia | 200,023,570 | Select for southern/eastern roads |
| Hungary | 325,903,232 | Select for eastern roads |
| Bosnia-Herzegovina | 161,358,110 | Select to avoid a southern inland source seam |
| Europe | 35,079,064,877 | Reject: unnecessary download and processing volume |

Source URLs are `https://download.geofabrik.de/` followed by the exact paths in
`configs/regional.yaml`. The existing Slovenia PBF is the sixth source. Publisher
polygons are archived under `results/milestone_3a/boundary/`; they are coverage
proxies acquired separately, not snapshot-matched guarantees. The raw HTTP
inspection is retained in `source_inspection.json`. See [Geofabrik Europe](https://download.geofabrik.de/europe.html)
and [Alps](https://download.geofabrik.de/europe/alps.html).

## Candidate geography

Buffer the **archived** Slovenia extract polygon in EPSG:3035 (metres), using
Shapely `buffer(distance, quad_segs=16)`, then transform back to WGS84 for
extraction. This is an approximate metric geographic buffer, not an exact
geodesic or national-border buffer. The method, distance and base hash are
configurable. Every endpoint is measured after OSM-node snapping.

| Margin km | Approximate area km² | All-tag PBF estimate MB | Minimum endpoint distance to boundary km |
| ---: | ---: | ---: | ---: |
| 50 | 67,463 | 1,005 | 54.2 |
| 75 | 94,932 | 1,414 | 79.3 |
| 100 | 126,114 | 1,879 | 104.4 |
| 150 | 199,946 | 2,979 | 154.4 |
| 200 | 289,272 | 4,309 | 204.4 |

Size estimates extrapolate Slovenia's **all-tag** byte density across total
polygon area, including sea; density is heterogeneous, so these are planning
estimates, not predictions. Road-only estimates are calibrated by filtering
Slovenia. Select **100 km** initially: meaningful room beyond all endpoint
directions, while avoiding the much larger 150/200 km graph. The selected sources
cover the complete 50 km candidate; the 100 km candidate has approximately
682 km² outside their union, examined and reported as a source-coverage limitation.
The experiment must measure all seven ratios before any further expansion.

Header inspection confirmed all five selected neighboring PBFs share Slovenia's
exact snapshot timestamp; see `source_header_inspection.json`. The uncovered
100 km area has WGS84 bounds 13.0098–13.4883°E, 44.5504–44.9533°N, in the
Adriatic southwest of Istria. In addition to the crop-edge diagnostic, the
benchmark flags vertices within 1 km of this archived source-proxy gap. Coverage
proxies remain approximate, and this extra check cannot certify missing-road absence.

## Streaming and RAM plan

Install **osmium-tool 1.18.0** in a separate prefix, leaving the original Mamba
environment and its locks unchanged. Record an explicit binary-package lock.
Use `osmium extract -s complete_ways` for each source and the identical polygon,
then `osmium tags-filter ... w/highway` (retain referenced nodes and all tags),
then `osmium merge` to deduplicate overlapping same-snapshot objects. Pin output
headers, compression/thread settings, polygon bytes, sources and tool version.
`osmium check-refs` checks way-to-node completeness.

Pyrosm's predefined driving network positively requires `highway`; retaining
**all** highway ways and their nodes preserves its candidate input. Relations
are not used by this graph model. Verify this empirically by rebuilding a
filtered Slovenia PBF separately and comparing both Parquet fingerprints with
Milestone 1. No road classes, access rules, speed rules or directions are changed.
See [extract semantics](https://docs.osmcode.org/osmium/latest/osmium-extract.html),
[tag filtering](https://docs.osmcode.org/osmium/latest/osmium-tags-filter.html) and
[same-snapshot merge](https://docs.osmcode.org/osmium/latest/osmium-merge.html).

Milestone 1 measured 16,666.8 MiB RSS / 313,378,108 raw bytes (~55.8×).
The 100 km all-tag estimate would imply ~100 GiB: unsafe on this 57.75 GiB host.
Therefore **never parse the all-tag regional source**. After road-only calibration,
estimate RSS using the larger of original amplification and filtered-Slovenia
amplification, with 1.35× safety factor. Require <=38 GiB and >=10 GiB available
headroom. A live process-tree RSS monitor terminates the child if it breaches
either reserve or limit. A failed guard is a documented result, never permission
to force an unsafe run.

The measured highway-filter calibration produced a **53,047,053-byte** PBF.
Pyrosm preprocessing used **8,036.99 MiB** peak RSS and took **49.68 s**. Both
graph Parquet SHA256 fingerprints are **byte identical** to Milestone 1.
Filtered-PBF amplification is ~158.9×, larger per raw byte than the all-tag
ratio; the final guard deliberately uses the larger factor. This distinguishes
a smaller input from a claim that raw byte size alone predicts memory safely.

### Measured final selection: 75 km

Before Pyrosm, streaming merge of only Austria, Slovenia, northeast Italy and
Croatia within the 100 km candidate already produced **202,660,509 bytes**.
The calibrated estimate with the safety factor is **40.48 GiB**, above the
38 GiB limit, before the Hungarian/Bosnian contributions. The 100 km candidate
was rejected without starting Pyrosm. Its polygon, configuration and probe
measurements remain archived in `candidate_100km_design.json`,
`candidate_100km_rejection.json`, `partial_size_probe.json`,
`configs/regional_100km_candidate.yaml` and the original candidate cache.

The final crop selects the evaluated **75 km** margin: **94,932 km²**, with every
snapped OD endpoint at least **79.28 km** from its boundary. This reduces the
workload while retaining meaningful cross-border margin; empirical boundary
sufficiency is assessed at all seven original budgets. The source-proxy gap
shrinks to approximately **38.21 km²** in the Adriatic. Configuration, polygon,
raw directory and intermediate cache are separate from the 100 km candidate.
The final merged PBF must still pass the calibrated guard before parsing.

The frozen 75 km road PBF is **175,103,959 bytes** (167.0 MiB), SHA256
`af94c57d06b62dc0c53900eaf64c0d7d496c0cc14e14b7ebf8d8f030182097b2`.
Its calibrated preprocessing estimate is **34.98 GiB** with the safety factor.
Streaming extraction/filtering/merge took **139.14 s**, with largest command
RSS **3,733.85 MiB**. This measured road-only size is not directly comparable
to the all-tag density estimates in the candidate table.

### Original model-domain audit

The first guarded parse found four unsupported highway values in neighboring
data: `traffic_calming` (97 parsed segments), `yes` (21), `square` (4) and
`crossing` (3). The unchanged original normalizer correctly refused to assign
them a speed. The failed probe used 15,829.75 MiB peak RSS and stopped without
writing a graph; its measurements remain in `unsupported_input_probe.json`.

The complete 175,103,959-byte geographic PBF remains immutable. A streaming
histogram identifies raw classes outside the existing model and Pyrosm driving
exclusions; a tiny candidate PBF is parsed with the identical driving filter to
identify exactly the four active unsupported classes. Their **21 ways / 125
segments**, full tags and references are archived in a quarantine PBF and JSON.
Only those classes are removed from a second graph-input PBF; all other ways
and all nodes remain. No speed, access or directional rule is introduced.
The strict original normalizer stays unchanged. Uncosted ways are an explicit
limitation, not claimed legal/drivable links in the modeled graph.

This model-input filter also rebuilt Slovenia with both Parquet files byte
identical to Milestone 1. The graph-input PBF is **175,103,895 bytes**, SHA256
`e10a5d4bb2a927d1bdcf21a41d30971a9301a82e08656c0419ef45e3f92de7a7`.
Its own immutable manifest/provenance and independent reproduction are separate
from the complete geographic-crop manifest. The RAM guard uses the larger
amplification from both Slovenia controls before starting the final build.

## Interpretation contract

Geographic buffering cannot certify completeness for every path <=2C*. Prioritize
the measured boundary rates at 1.05, 1.10, 1.20 and 1.40 while keeping 2.00 as
the unchanged hard cap. The boundary diagnostic uses the same 1 km inward margin
and projection as Milestone 2; source coverage is inspected separately. Complete
ways can extend beyond the crop. Node proximity can miss crossings inside long
edges. Any success is empirical, relative to the frozen static road model.

Compare absolute node/edge counts, occupied 1 km² cells, bounding-box extent and
runtime as well as graph fractions. Each dataset uses its own C*, and baseline
changes are reported before envelope comparisons. Graph growth is computational
cost, not decision-value saturation. Opportunity Regions and utility-driven
stopping remain deferred.
