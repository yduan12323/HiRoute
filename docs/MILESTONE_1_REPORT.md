# Milestone 1 technical report

Executed at 2026-09-30T13:47:41.244989+00:00. Only initial infrastructure and the road-graph milestone are implemented. `RESEARCH_SPEC.md` is unchanged (SHA256 `d594f4ac78e1bfe8903c98d48bb20c4e9e3f2b15f1e8fed5fedde964be7ead04`). All later research directories remain placeholders.

## Environment and data

Python 3.11.16, Pyrosm 0.13.1, igraph 1.0.0; isolated Mamba environment `hiroute`. `environment-linux-64.lock` pins exact Conda package URLs and SHA256 hashes; `environment.yml` records the portable package intent. Hardware details are in [SERVER_ENVIRONMENT.md](SERVER_ENVIRONMENT.md).

Dataset: **Slovenia**, [slovenia-260929.osm.pbf](https://download.geofabrik.de/europe/slovenia-260929.osm.pbf). OSM header snapshot: **2026-09-29T20:22:51+00:00**. Downloaded: 2026-09-30T13:22:03.572952+00:00. Size: 313,378,108 bytes. SHA256: `7fae267d1b5f691bcdf4d543dab907175dc77b740960042b48a751bf15a2d693`. Publisher MD5 also verified. Raw PBF is read-only and downloader refuses replacements. Attribution: OpenStreetMap contributors / Geofabrik; ODbL 1.0. Full metadata is in `data/raw/DATA_MANIFEST.yaml`.

## Graph and cost model

Directed igraph multigraph with **2,220,917 nodes** and **4,401,596 edges**. Largest strongly connected component has 2,168,708 nodes; all components are retained in the graph. No graph simplification, corridor selection or geographical buffering occurs. Stable sorted OSM IDs map to contiguous node/edge indices. Parquet stores WGS84 nodes, directed edge geometry as WKB, source tags, metres and seconds.

Free-flow speed is the configured road-class estimate capped by parsed numeric/directional/symbolic posted maxspeed. Numeric mph is converted to km/h; semicolon values use the minimum. Missing or unsupported tags explicitly fall back to class speed and remain identifiable. Time is `length_m * 3.6 / speed_kph`. Posted-cap edges: 531,839; class-fallback edges: 3,869,757. Full defaults are in `configs/routing.yaml`.

Pyrosm applies its driving filter. Additional static access policy uses motorcar → motor_vehicle → vehicle → access. Restricted, destination-only and unknown tagged access are excluded; conditional access and conditional one-way ways are excluded. One-way direction, reverse one-way, and implicit motorway/roundabout one-way are handled. Toll and dimension tags remain nullable; absence is not interpreted as a known negative. Filter counts are in graph metadata.

## Instances and validation

30 ODs: 10 each in 50–100, 100–200 and 200–400 km bands. Seed: 20260930. Fixed city anchors receive uniform-area jitter and nearest-node snapping; unsuitable snaps, duplicate pairs and nodes outside the largest SCC are rejected. This biases the smoke benchmark toward connected city travel, rather than claiming population-representative sampling.

Bands use distance-optimal paths (51.4–290.3 km); distance of the travel-time-optimal path is separately recorded. Every OD passes finite/nonnegative edge checks, directed sequence and exact parallel-edge validation, geometry endpoint checks (0.5 m tolerance), cost-sum checks and shortest-cost agreement. `route_validation.parquet` records per-OD validation and runtime. Test results: {'tests': 14, 'failures': 0, 'errors': 0, 'skipped': 0}. Separate full-PBF rebuild byte-identical: **True**.

## Measured performance

| Measure | Result |
| --- | ---: |
| Raw PBF | 298.86 MiB |
| Processed graph (tables + metadata) | 141.03 MiB |
| Preprocessing including parsing, conversion, writes and SCC computation | 106.93 s |
| Verified graph loading including table checksums and spatial index | 3.90 s |
| Median fastest-path query | 769.28 ms |
| p95 fastest-path query | 1025.35 ms |
| Preprocessing peak process RSS | 16666.8 MiB |
| Benchmark peak process RSS | 3410.9 MiB |

Query timings cover 90 calls after 3 warmup calls, with seeded shuffled OD order over 3 repeats. They include Dijkstra, path extraction and cost sums, and exclude geometry validation. OS page cache is not cleared; loading is a warm-cache measurement. RSS is Linux process high-water memory, not whole-server usage. Raw timings and full software/configuration/source fingerprints are saved under `results/milestone_1/`.

## Limits and later envelope concerns

This is a static passenger-car graph for infrastructure tests. Turn-restriction relations, node barriers, conditional speed rules, vehicle height/weight restrictions, traffic, intersection delays and ferry scheduling are not modeled. Thus structural shortest-path validity is verified, but real-world legal feasibility is not certified. These constraints must be represented before later hard-feasibility claims; a turn-aware state graph may alter the vertex definition for later envelope work.

Regional boundaries can remove cross-border alternatives, particularly in Slovenia. Future geographically complete envelopes need larger extracts or explicit boundary diagnostics. Class-speed assumptions affect mobility budgets and need sensitivity analysis. Disconnected vertices remain available and have infinite directed costs. `single_source_distances(..., direction="in")` supports destination-side reverse distances. Multi-source distances use O(V) output memory but run one Dijkstra per source; batch scaling needs measurement. Full graph retention and explicit nonnegative static costs provide the base for later envelope work; no envelope is implemented here.

## Reproduction

See [README.md](../README.md) for exact environment, download, graph, OD, test, rebuild and benchmark commands. Commands record Git commit and dirty state, source hashes, timestamp, configuration, seed, dataset metadata and package versions. Raw PBF is never edited in place; processed data can be regenerated. No live routing APIs, semantic modules, charging optimization, user models or dashboards were added.
