# HiRoute research infrastructure — Milestone 1

The authoritative formulation is [RESEARCH_SPEC.md](RESEARCH_SPEC.md). This implementation covers a frozen OSM driving graph, typed routing, seeded OD instances and shortest-path validation. Research modules for later milestones remain empty.

## Environment

Run all commands from the repository root. The validated platform is Linux x86-64 with Python 3.11. See [server inventory](docs/SERVER_ENVIRONMENT.md). Mamba is preferred; Conda accepts the same explicit lock.

```bash
# Exact validated packages, builds and SHA256 hashes (Linux x86-64)
mamba create -n hiroute --file environment-linux-64.lock -y
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate hiroute
python -m pip install --no-deps --no-build-isolation -e .
```

For another platform, solve the portable specification instead; this is not the exact validated binary environment:

```bash
mamba env create -f environment.yml
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate hiroute
python -m pip install --no-deps --no-build-isolation -e .
```

`environment-resolved.yml` also pins the installed versions. Existing environments are not removed or replaced. If `hiroute` already exists, activate it and verify its packages before running. Commands can alternatively be prefixed with `mamba run -n hiroute` without activation. No ML frameworks are required.

## Frozen data and graph

The selected region is Slovenia. The dated Geofabrik URL, raw path and SHA256 are in `configs/data.yaml`; acquisition information is in `data/raw/DATA_MANIFEST.yaml`. Data attribution: © OpenStreetMap contributors, ODbL 1.0; extract by [Geofabrik](https://download.geofabrik.de/europe/slovenia.html).

```bash
python scripts/download_data.py
python scripts/build_graph.py
python scripts/generate_instances.py
```

The downloader verifies publisher MD5 and the pinned SHA256, writes a read-only raw file exclusively, and verifies an existing file instead of replacing it. On a fresh checkout, it restores the exact snapshot from the recorded URL and preserves the tracked manifest. A manifest/configuration mismatch or changed publisher content is an error. If the publisher eventually removes this dated file, restore the exact checksummed PBF from an archive; never substitute a newer snapshot under the same name.

Preprocessing verifies the PBF checksum and writes `nodes.parquet`, `edges.parquet` and `metadata.json` to `data/processed/graphs/slovenia/`. Processed artifacts can be rebuilt; raw data is not modified. The graph retains all directed components and parallel edges. Units are metres, seconds and km/h; coordinates and WKB geometry use WGS84. Node IDs are contiguous indices with original OSM node IDs retained. IDs are stable for the same dataset, configuration and pinned environment; they must not be transferred to a different dataset.

`configs/routing.yaml` defines the explicit road-class speed model, directional posted-speed caps and access policy. Destination-only, restricted or conditionally accessible ways are excluded from the unrestricted static graph. Toll and access tags remain nullable. See the [technical report](docs/MILESTONE_1_REPORT.md) for filtering details and limits.

OD generation creates 30 city-anchored pairs, with seed 20260930 and 10 pairs per shortest-distance band (50–100, 100–200, 200–400 km). Stored fastest-path distance and shortest distance are separate quantities. ODs include coordinates, snap distances, graph nodes, path node/edge sequences, travel times, dataset/graph fingerprints and per-query runtime. City anchors are fixed configuration, with no live geocoding.

## Tests, deterministic rebuild and benchmark

```bash
pytest -q --require-real-data --junitxml=results/milestone_1/tests.xml

# Rebuild from the same full raw PBF into a separate processed directory.
python scripts/build_graph.py --output-dir data/cache/graph-rebuild
python scripts/verify_rebuild.py data/cache/graph-rebuild

python scripts/run_benchmark.py
```

`--require-real-data` makes absent real data fail rather than skip. For fast development before downloading, run `pytest -q -m 'not integration'`. Tests cover graph loading, spherical nearest-node lookup, toy shortest paths, parallel edges, one-way direction, disconnected paths, reverse distances, invalid costs, speed/access policy, deterministic normalization and every real OD. Real route checks verify directed edge sequences, cost sums and geometry endpoints.

The benchmark revalidates every OD and reports graph size, preprocessing/loading time, median/p95 fastest-path query time and process peak RSS. Timings use shuffled OD order and warmup queries; they include route extraction and exclude geometry validation. It writes `results/milestone_1/benchmark.json`, per-query timing/validation Parquet, and [MILESTONE_1_REPORT.md](docs/MILESTONE_1_REPORT.md). The separate rebuild compares Parquet SHA256 hashes and records `deterministic_rebuild.json`.

Every command logs UTC time, Git commit/dirty state, source checksums, configuration, seed, dataset metadata and installed package versions to `results/milestone_1/logs/`. Binary data and detailed logs are ignored by Git; the manifest, configuration, lockfiles and concise results are tracked.

## Graph interface

```python
from graph.road_graph import IgraphRoadGraph

graph = IgraphRoadGraph.load("data/processed/graphs/slovenia")
origin = graph.nearest_graph_node(46.0569, 14.5058)
destination = graph.nearest_graph_node(46.5547, 15.6459)
route = graph.shortest_path(origin, destination, cost="travel_time")
cost_s = graph.shortest_path_cost(origin, destination, cost="travel_time")
distance_m = graph.shortest_path_cost(origin, destination, cost="distance")
```

`RoadGraph` is a typed protocol independent of the concrete backend. `Route` retains the exact selected edge IDs. Unreachable paths raise `NoPathError`; unreachable scalar costs/distances are infinity. `single_source_distances(origin, direction="in")` computes costs to the origin on directed edges. `multi_source_distances` returns the minimum over sources with O(V) output memory and one query per source. These are graph primitives only; no detour envelope is implemented.

This static graph does not enforce turn-restriction relations, node barriers, vehicle dimensions or time-dependent rules. It supports structural research smoke tests; later hard-feasibility work must account for these limits. Extract boundaries also truncate cross-border alternatives. Read the report before using this graph for later Safe Detour Envelope experiments.
