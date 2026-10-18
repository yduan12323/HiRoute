# Rebuild the fixed M5-D physical-screen aggregate

The source-only repository does not need historical JSON results, local caches,
or downloaded maps committed to Git. Obtain/preprocess the specified map and Site
inputs on each platform using the input-acquisition instructions, then run the
producers below. Python 3.11, project dependencies and `g++` are required for the
routing stages; the new planning/aggregation script uses only the standard library.
The fixed experiment is versioned in `configs/m5d/fixed_grid14_screen.json`: grid
size, partition count, cutoff/order, expected populations and runtime input
references. Planning and aggregation both accept `--config` and record its hash;
changing config after planning is rejected. Runtime filesystem roots remain
command arguments/environment variables, not machine-specific config paths.

Run from the repository root with the project installed (or `PYTHONPATH=src`).

This recipe is an input screen, not an optimization experiment or evidence of
qualified two-charge queries. Do not change geography, cutoff, or candidates in
response to later optimization results.

## Fresh, portable run

Set `GRAPH` to a processed graph directory with `nodes.parquet`, `edges.parquet`
and `metadata.json`; set `SITES` to the attached Site parquet. Use a fresh writable
`RUN` directory. These are platform-local paths; there are no author-machine paths.
The existing producer scripts refuse to overwrite outputs or native caches.

```sh
export GRAPH=/path/to/processed/graph
export SITES=/path/to/attached/sites.parquet
export RUN=/path/to/new/screen-run
export CONFIG=configs/m5d/fixed_grid14_screen.json
GRID=$(python -c 'import json,os; print(json.load(open(os.environ["CONFIG"]))["grid_size"])')
mkdir -p "$RUN"
python scripts/m5d_geographic_screen.py \
  --nodes "$GRAPH/nodes.parquet" --sites "$SITES" --grid-size "$GRID" \
  --output "$RUN/geographic_screen_v5_grid14.json"
python scripts/m5d_aggregate_screen.py plan \
  --geographic-screen "$RUN/geographic_screen_v5_grid14.json" \
  --config "$CONFIG" --output "$RUN/grid14_partition_plan.json"
```

Execute the precommitted contiguous-origin plan without hand-editing ranges.
This Python driver works across platforms and avoids dependence on `sha256sum`:

```python
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

run, graph = Path(os.environ["RUN"]), Path(os.environ["GRAPH"])
config = Path(os.environ["CONFIG"])
geo = run / "geographic_screen_v5_grid14.json"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
plan = json.loads((run / "grid14_partition_plan.json").read_text())
for part in plan["partitions"]:
    i = part["index"]
    start, stop = part["origin_partition"]
    distance, proof = run / part["distance_file"], run / part["potential_file"]
    subprocess.run([
        sys.executable, "scripts/m5d_extrema_distance_native.py",
        "--graph-dir", str(graph), "--geographic-screen", str(geo),
        "--geographic-screen-sha256", sha(geo),
        "--native-cache", str(run / f"distance_cache_p{i}"),
        "--all-grid", "--origin-start", str(start), "--origin-stop", str(stop),
        "--micrometer-lower-bound", "--output", str(distance)], check=True)
    subprocess.run([
        sys.executable, "scripts/m5d_distance_potential_check.py",
        "--graph-dir", str(graph), "--pair-screen", str(distance),
        "--pair-screen-sha256", sha(distance),
        "--native-cache", str(run / f"potential_cache_p{i}"),
        "--output", str(proof)], check=True)
subprocess.run([
    sys.executable, "scripts/m5d_aggregate_screen.py", "aggregate",
    "--geographic-screen", str(geo),
    "--plan", str(run / "grid14_partition_plan.json"),
    "--input-dir", str(run), "--config", str(config), "--require-frozen-population",
    "--output", str(run / "grid14_aggregate.json")], check=True)
```

The versioned config validates expected populations and binds input references.
The additional frozen population flag requires the original 14x14 grid rule, 158 candidate
Sites, four partitions and 140 checked long pairs. It does not insert or alter
those results. Other populations may use the same validator without the fixed config/flag,
but cannot claim reproduction of the frozen M5-D slate. For 158 Sites, the plan
is exactly `[0,40), [40,80), [80,120), [120,158)` in the geographic producer's
latitude-cell/longitude-cell order. Long means strictly greater than
450001000000 integer micrometers; equality is excluded.

## What is checked and recorded

Aggregation rejects incomplete, overlapping, reordered or duplicated pair sets;
wrong endpoint anchors; mismatched graph/source identities; wrong cost modes or
cutoffs; inconsistent summary counts; missing/duplicate potential roots; incorrect
matched-target counts; and failed one-metre rounding-margin checks. Every source
screen and potential receipt is SHA-256-bound, along with the geographic input,
plan and aggregation tool. Empty-long-pair partitions have zero-root receipts;
they are valid but cannot silently remove required checks from other partitions.
The edge-potential producer itself performs the independent inequalities and
screen-label comparisons; aggregation validates its receipt and bindings, not the
raw graph again. A fabricated receipt is not cryptographic proof of computation.

Outputs are deterministic for identical input bytes. Runtime/compiler/platform
metadata in producer receipts can differ between reruns, so receipt/aggregate
hashes need not match historical hashes even when scientific results agree. The
aggregate does not copy elapsed times into its summaries or read historical
results. All source outputs are retained unchanged. No optimization selection is
performed.

## Downstream scope and remaining historical gates

`scripts/m5d_freeze_od_slate.py` consumes this aggregate schema and the four
screen/proof files under its existing canonical evidence directory
`results/milestone_5d/continuation_20261011/`. It also requires the separately
produced `results/milestone_5_real_export/query_states_resolved.json`. To use that
legacy consumer, stage the freshly generated files at those documented paths in
a clean workspace; never overwrite retained evidence. The aggregate's expanded
`source_sha256` mapping includes all four potential receipts as well as the
geographic/distance files and is compatible with its hash-check loop.

Separate historical artifact/hash gates in `candidates.py` and `export.py` are
unchanged. This producer closes the missing aggregation step; it does not bypass
those gates or establish an entirely portable downstream candidate/export
pipeline. Their migration needs explicit equivalent scientific validation, not
weaker checks or copied historic results.

Portable unit verification (no maps or downloads):

```sh
python -m pytest -q tests/test_m5d_aggregate_screen.py
```
