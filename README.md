# HiRoute research infrastructure — Milestones 1–3A

The authoritative formulation is [RESEARCH_SPEC.md](RESEARCH_SPEC.md). This implementation covers the frozen OSM driving graph and structurally validated Safe Detour Envelopes. Research modules beyond envelope infrastructure remain empty. Structural correctness is with respect to the frozen directed graph; full legal or real-world route feasibility is not certified.

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

`RoadGraph` is a typed protocol independent of the concrete backend. `Route` retains the exact selected edge IDs. Unreachable paths raise `NoPathError`; unreachable scalar costs/distances are infinity. `single_source_distances(origin, direction="in")` computes costs to the origin on directed edges. `multi_source_distances` returns the minimum over sources with O(V) output memory and one query per source.

This static graph does not enforce turn-restriction relations, node barriers, vehicle dimensions or time-dependent rules. It supports structural research smoke tests; later hard-feasibility work must account for these limits. Extract boundaries also truncate cross-border alternatives. Read the report before using this graph for later Safe Detour Envelope experiments.

## Milestone 2: Safe Detour Envelope

Continue from the existing Milestone 1 artifacts; do not rerun `build_graph.py`, `generate_instances.py`, or the Milestone 1 benchmark to execute Milestone 2. No new environment dependencies are required. Install the extended local package in the existing `hiroute` environment:

```bash
python -m pip install --no-deps --no-build-isolation -e .

# Check the original tests before starting the envelope experiment.
pytest -q tests/test_graph.py tests/test_preprocessing.py tests/test_download.py tests/test_real_graph.py --require-real-data

# For a new local run, capture a new checkpoint (exclusive write).
python scripts/verify_milestone_1.py --capture --checkpoint results/milestone_2/local_preservation_before.json

# Normally verifies the archived polygon already included in the repository.
python scripts/download_extract_boundary.py
python scripts/run_envelope_benchmark.py
python scripts/plot_envelopes.py

pytest -q --require-real-data --require-envelope-results --junitxml=results/milestone_2/tests.xml
python scripts/verify_milestone_1.py --checkpoint results/milestone_2/local_preservation_before.json
python scripts/write_envelope_report.py
```

If repeating a run with the same local checkpoint, omit `--capture` and verify it instead. The included `preservation_before.json`/`preservation_after.json` record the initial implementation run. If that checkpoint is present and your Milestone 1 artifacts are unchanged from the supplied run, use `python scripts/verify_milestone_1.py` directly. A checkpoint mismatch must be investigated, not overwritten. The independent `--require-envelope-results` test flag keeps the Milestone 1 reproduction workflow usable before Milestone 2 outputs exist; the final Milestone 2 command requires both graph data and envelope results.

`configs/envelope.yaml` controls the cost (`travel_time` in seconds, or `distance` in metres), ratios, experimental cap, numerical tolerance, seed, path sampling, boundary margin and figures. Membership compares each bound against `B + absolute + relative*B`. Defaults add at most microseconds to the time budgets in this experiment. Changing speeds or cost dimensions can change envelope membership; graph/routing fingerprints and explicit units are included in the result tables.

The precomputation computes `d(s,v)` using outgoing edges and `d(v,d)` using incoming edges from the destination. It caches node bounds `d_s+d_d` and edge bounds `d_s[source]+edge_cost+d_d[target]`. Each budget uses read-only NumPy masks over the original graph, preserving exact parallel-edge IDs. Distances are computed once per OD/cost, and ODs are processed sequentially. No full subgraph copies are written. Progressive iteration exposes views for future caller inspection without selecting a stopping budget or estimating utility.

```python
from envelope import NumericalTolerance, precompute_detour_distances, iter_progressive_envelopes

distances = precompute_detour_distances(graph, origin, destination, cost="travel_time")
budgets = [ratio * distances.baseline_cost for ratio in (1.0, 1.1, 1.4, 2.0)]
for envelope in iter_progressive_envelopes(distances, budgets, NumericalTolerance()):
    print(envelope.budget, envelope.unit, envelope.node_mask.sum(), envelope.edge_mask.sum())
```

Every path with total base cost at most B is retained. A route assembled from retained edges may still exceed B, so its total cost must be checked. The [Milestone 2 report](docs/MILESTONE_2_REPORT.md) gives the proof, numerical policy, synthetic tests, empirical path-containment checks, performance and envelope-growth tables.

The separately archived [Geofabrik polygon](https://download.geofabrik.de/europe/slovenia.poly) is a geographic diagnostic proxy, not a PBF-date-matched certificate. Boundary risk flags any envelope vertex within 1 km of or outside its projected polygon. Flags do not change masks. The proxy-interior analysis subset remains separate from all 30 unchanged ODs; no global completeness claim is made. The frozen polygon and its metadata are included under `results/milestone_2/boundary/`, so the experiment requires no network access. The downloader can restore only the pinned content if the archive is missing.

Outputs under `results/milestone_2/` include:

- `envelope_stats.parquet`: 30 ODs × seven configured ratios, sizes, percentages, bounds, build time and memory.
- `distance_benchmark.parquet`: forward/reverse timings once per OD, bounds preparation and fingerprints.
- `path_containment_tests.parquet`: seeded paths/walks, exact path fingerprints and bounded/over-budget checks.
- `boundary_diagnostics.parquet`, `boundary_safe_subset.parquet`, `envelope_growth.parquet`.
- `benchmark.json`, `tests.xml`, preservation checks and reproducibility logs.
- `figures/`: static growth and three OD diagnostics, editable SVG/PDF, PNG previews, aggregate source data and QA notes.

Large tables, detailed logs and figures are generated locally and ignored by Git; compact summaries, configs and the frozen boundary are retained. To test the distance dimension in a separate output directory, copy `configs/envelope.yaml`, set `cost: distance` and a distinct `results_dir`, then run `python scripts/run_envelope_benchmark.py --config <copied-config>`. The APIs and real tests cover both dimensions; the default 30-OD benchmark uses travel time.

No Opportunity Region, POI, charging, semantic/LLM, utility, acquisition or decision-driven stopping code is present. The authoritative order assigns Milestone 3 to Adaptive Envelope and Milestone 4 to Opportunity Regions; further research work requires explicit instruction.

## Milestone 3A: cross-border data substrate

Slovenia remains the original smoke-test dataset. The additional graph uses the
same graph builder and unchanged `configs/routing.yaml`. Read the
[data design](docs/MILESTONE_3A_DATA_DESIGN.md) and
[measured report](docs/MILESTONE_3A_REPORT.md) before drawing geographic conclusions.
The selected 75 km EPSG:3035 buffer is configurable in `configs/regional.yaml`.
The measured 100 km candidate exceeded the preprocessing RAM estimate and was
retained separately without being parsed by Pyrosm.
To study another extent, copy the regional configuration and give it separate
polygon, raw, graph, result and cache paths; copy the archived source-coverage
polygons into its boundary directory. A frozen region's configuration is checked
before its polygon or raw artifact can be reused.
Frozen 260929 sources cover Austria, northeast Italy, Croatia, Hungary,
Bosnia-Herzegovina and the original Slovenia extract. Streaming extraction keeps
complete ways, then all highway ways and referenced nodes, before Pyrosm.
This is a road PBF; POI data are not part of this artifact.

Use a separate environment for osmium-tool, leaving the M1 Python lock unchanged:

```bash
mamba create -p ../osmium-env --file environment-osmium-linux-64.lock -y
# Run the following in the original hiroute Python environment.
pytest -q --require-real-data --require-envelope-results
python scripts/verify_milestone_3a_preservation.py
python scripts/prepare_regional_data.py polygon
python scripts/prepare_regional_data.py download
python scripts/prepare_regional_data.py calibrate --osmium ../osmium-env/bin/osmium
python scripts/prepare_regional_data.py extract --osmium ../osmium-env/bin/osmium
python scripts/prepare_regional_data.py verify-extraction --osmium ../osmium-env/bin/osmium
python scripts/prepare_regional_model_input.py --osmium ../osmium-env/bin/osmium
python scripts/prepare_regional_model_input.py --verify --osmium ../osmium-env/bin/osmium
python scripts/prepare_regional_data.py build
python scripts/run_regional_benchmark.py
python scripts/plot_regional_growth.py
HIROUTE_OSMIUM=../osmium-env/bin/osmium pytest -q --require-real-data --require-envelope-results --require-regional-results --junitxml=results/milestone_3a/tests.xml
python scripts/verify_milestone_3a_preservation.py
python scripts/write_regional_report.py
```

The source and crop checksums, exact commands, polygon hash, snapshot times and
tool versions are recorded under `results/milestone_3a/`. Downloads restore dated,
pinned sources and refuse changed checksums. Raw files are read-only and never
replace Slovenia. The independent calibration rebuild must reproduce the original
Slovenia graph Parquet files byte for byte. `build` evaluates a conservative RAM
estimate before launching Pyrosm; a live monitor enforces a 38 GiB RSS ceiling and
10 GiB available-memory reserve. Do not bypass a failed guard.

Neighboring data contain four way classes rejected by the original cost model.
The model-input stage audits them in a tiny driving-network probe, archives all
quarantined ways and tags, and removes only those unmodelled classes from a
separate PBF. The complete geographic road crop remains frozen. No speed or
access rule is added; a second Slovenia control must preserve both graph files
byte for byte. Its PBF checksum and reproducibility check are recorded separately
in `model_input_provenance.json` and `MODEL_DATA_MANIFEST.yaml`.

The osmium lock reproduces the two added binary packages on the validated Ubuntu
26.04.1 host; `osmium_environment.json` records exact host library versions and
hashes. No system package or original Python environment is replaced.
`extract` verifies an existing frozen crop; `verify-extraction` rebuilds it in a
separate cache and checks byte identity. Intermediate cache paths must be absent
for a fresh extraction verification; archive a prior cache before repeating.
For a locally rebuilt M1–M2 experiment with different run-log timestamps, capture
an exclusive local checkpoint after its initial tests and use that checkpoint
for both preservation checks:

```bash
python scripts/verify_milestone_3a_preservation.py --capture --checkpoint results/milestone_3a/local_preservation_before.json
python scripts/verify_milestone_3a_preservation.py --checkpoint results/milestone_3a/local_preservation_before.json
```

ODs are remapped by original OSM node ID with coordinate and original snapping
checks. New baseline routes, fastest-path and distance-optimal distances,
OSM-node overlap, absolute envelope sizes, occupied 1 km² cells, spatial extent,
boundary risk and timings are saved separately. Each dataset's ratio uses its
own baseline C*; comparisons retain both absolute budgets. The original 2C* cap
and all seven configured ratios remain unchanged. Occupied cells describe vertex
support, not continuous reachable area.

`envelope.expansion.EnvelopeExpansionPolicy` exposes `next_budget` and
`should_stop`; `FixedSchedulePolicy` visits the configured schedule, and
`iter_policy_envelopes` enforces a caller-provided cap. It does not estimate
utility, use graph saturation to stop, or implement the future scientific
decision-value rule. Opportunity Region generation still requires explicit instruction.
