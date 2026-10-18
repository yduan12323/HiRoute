# Reproducing HiRoute without publishing experiment data

The Git repository is the code distribution: implementation, runner scripts,
configuration, dependency locks, small synthetic fixtures and documentation.
Download public raw inputs on the machine doing the experiment. Generate graph,
cache, traces, logs and result tables there. Do not commit those outputs or upload
an old experiment bundle as a prerequisite for ordinary development.

## Platform support and versions

- The validated runtime is **Linux x86-64, Python 3.11**. The code-only workflow
  pins Python 3.11.16 and hash-locked wheels in `ci/m5-requirements.txt`.
- The full data pipeline uses `environment-linux-64.lock` (exact Conda package
  URLs/builds/hashes), C++17 `g++`, `curl`, `/usr/bin/time`, Linux `/proc` and Unix
  resource limits. Regional extraction separately requires **osmium 1.18.0**
  from `environment-osmium-linux-64.lock`. That osmium lock contains osmium-tool
  and libboost, not a complete operating-system runtime; system zlib/expat/bzip2/
  lz4/libstdc++/libgcc/libc/xxhash must also resolve (`ldd PATH_TO_OSMIUM` must
  show no `not found` entries). `environment.yml` is a portable solver
  input, not evidence of equivalence to the Linux lock.
- On Windows, use a Linux x86-64 WSL2 environment or Linux host. On macOS, use a
  Linux x86-64 VM/remote host. Those host routes are guidance, **not tested
  platforms**. Native Windows/macOS full runners are not supported; Apple ARM
  cannot use the x86-64 binary lock natively. Containerization alone does not
  establish timing equivalence, resource-limit equivalence or correctness.
- Record CPU, RAM, kernel, compiler, dependency lock, commit, command, random
  seeds and thread settings with every run. Compare correctness first; timing
  results from different hosts/caches are not interchangeable.

## Versioned experiment parameters

Keep fixed experiment parameters in reviewed, versioned configuration; generated
measurements never belong in that configuration. Current configurations are in
`configs/`: `data.yaml`/`data_extended.yaml` bind input identity and local paths,
`routing.yaml` defines routing/sampling, and `envelope.yaml`, `regional.yaml`,
`opportunity.yaml`, `microplan.yaml` and `stopplan_4r.yaml` define stage settings.
Small files in `configs/inputs/` pin external input identities. Commit parameter
changes before freezing a new experiment and record configuration hashes with
its outputs. Choose new output directories; do not overwrite an earlier run.

Some historical M5 gate policies remain Python constants or hash-bound manifests
under `experiments/`; they are not all configurable through `configs/` today.
The fixed grid14 screening recipe now uses
`configs/m5d/fixed_grid14_screen.json`; see [M5-D screen reproduction](M5D_SCREEN_REPRODUCTION.md).
Moving the remaining gate policies to explicit versioned configs and completing
the downstream M5 input-generation stages are separate remaining tasks. Do not silently
change their values or label a fresh configuration as the historical experiment.

## 1. Data-free development

From a fresh checkout, follow [the isolated-wheel gate](../ci/README.md).
It downloads only the pinned build/test packages, builds the local wheel and
runs synthetic regressions. No OSM files, historical run outputs, credentials
or artifact restoration are required. Default `pytest -q` uses the documented
code-only collection; it is not the complete historical acceptance suite.

## 2. Full Linux data environment

Use a separate experiment checkout/work directory, for example under
`$HOME/hiroute-runs/run-001`, rather than writing into your development checkout.
Use an unused environment and run directory for each reproduction. Commands
below run from that checkout's root; no `/workspace`, previous author's home,
fixed CPU number or previous worker environment is required.

```sh
mamba create -n hiroute-repro --file environment-linux-64.lock -y
mamba create -n hiroute-osmium --file environment-osmium-linux-64.lock -y
# Activate hiroute-repro using your Conda/Mamba installation's shell setup.
conda activate hiroute-repro
python -m pip install --no-deps --no-build-isolation -e .
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
python --version
g++ --version
curl --version
mamba run -n hiroute-osmium osmium --version
```

Do not silently upgrade the pinned environment when a build is unavailable.
Report the unavailable package and solve/validate a separately named environment.
Full regional experiments are memory intensive: their current policy reserves
10 GiB headroom and limits monitored RSS to 38 GiB. Check the actual per-run
configuration and host capacity before starting; do not lower safety guards
to make an undersized VM appear equivalent. Code-only tests need neither
that allocation nor the regional data downloads.

## 3. Download and rebuild the public base inputs

The exact base extract is:

- URL: https://download.geofabrik.de/europe/slovenia-260929.osm.pbf
- SHA256: `7fae267d1b5f691bcdf4d543dab907175dc77b740960042b48a751bf15a2d693`
- Configuration: `configs/data.yaml`; identity/license: `data/raw/DATA_MANIFEST.yaml`
- Attribution: OpenStreetMap contributors, ODbL-1.0; extract by Geofabrik.

```sh
python scripts/download_data.py
python scripts/build_graph.py
python scripts/generate_instances.py
python scripts/build_graph.py --output-dir data/cache/graph-rebuild
python scripts/verify_rebuild.py data/cache/graph-rebuild
```

The downloader checks the pinned SHA256, publisher MD5 and content length;
existing raw inputs are verified rather than replaced. Graph generation verifies
raw identity. The independent rebuild checks deterministic processed artifacts.
Generated files live in ignored `data/raw/osm`, `data/processed`, `data/cache`
and `results` inside this dedicated run checkout. They are never code inputs
for the synthetic CI gate.

Dated publisher files can expire. A 404, checksum mismatch or changed snapshot
is a hard stop. Do not substitute `latest` or a nearby date. Locate an official
or otherwise trusted mirror of the identical pinned bytes and verify the SHA256,
or declare a new dataset version and regenerate/revalidate all dependent IDs.
This release does not promise indefinite availability of third-party downloads.

## 4. Regional inputs and successive experiments

The six dated regional source pins (URL, size, SHA256 and timestamp) are in
`configs/inputs/geofabrik-260929-sources.json`. Small frozen polygon inputs and
metadata are under `configs/inputs/boundary/`; they are input configuration,
not experimental output. The mutable publisher polygon URL must not silently
replace those pinned bytes.

Reproduce stages in dependency order: base graph/ODs → envelope → regional
extract/model/graph → opportunities → microplans → stop/hierarchy substrate →
M5 input construction. [README](../README.md) contains the stage commands and
individual protocol links. In a new run, use each preservation checker's
`--capture` mode before changing that stage; a historical checkpoint is not
present in the code distribution. Do not invoke a historical acceptance command
before its generating stage has completed.

For regional extraction, replace the old example `../osmium-env/bin/osmium`
with the absolute path to your installed `hiroute-osmium` executable; obtain it
with `mamba run -n hiroute-osmium which osmium`. This is a local installation
path, not a downloadable data artifact. Start with:

```sh
python scripts/download_extract_boundary.py
python scripts/prepare_regional_data.py polygon
python scripts/prepare_regional_data.py download
# Subsequent calibrate/extract/verify-extraction stages accept --osmium PATH.
```

Each experiment directory retains its executable runner and protocol. For
example, `python -m experiments.analytic_charge_gate_v1.run --plan` displays the
prospective design; `--freeze --input-directory INPUTS --output MANIFEST.json`
creates a new binding, and `--gate` consumes that manifest and its SHA256 with a
new output directory and an available `--cpu`. Read that runner's README for
its precise controls, input contract and resource budget before launching.
Do not copy historical manifests and claim a new input graph reproduces their
hash-bound domains. Preparation, exact solving, independent replay and terminal
accounting are separate checks; a timeout is never an exact completion.

The historical M5-D development gates currently bind intermediate inputs and
prior admission receipts. Retaining their source is not a claim that the whole
historical chain is a one-command clean-machine benchmark. Unavailable generation
steps or pinned data must be reported explicitly, not bypassed by
weakening hash checks. A new end-to-end run must regenerate and validate those
inputs before a historical gate can be admitted. Specifically:

- `scripts/m5d_freeze_od_slate.py` consumes `grid14_aggregate.json` with schema
  `hiroute.m5d.grid14_fixed_screen_aggregate.v1`, 140 checked pairs and four
  `grid14_distance_pN` / `grid14_potential_pN` evidence pairs. The new
  `scripts/m5d_aggregate_screen.py` produces that aggregate from newly generated,
  checked partition receipts and consumes versioned
  `configs/m5d/fixed_grid14_screen.json`. Follow the exact plan, screen,
  independent-potential and aggregate commands in
  [M5-D screen reproduction](M5D_SCREEN_REPRODUCTION.md). Synthetic/native
  checks validate this pipeline; the historical 158-site/140-long-pair
  population has not been freshly rerun as part of this code release.
- `experiments/time_cut_v2/real_export/export.py` produces
  `query_states_resolved.json`, but requires the six-file substrate verification,
  a versioned selection manifest, `preselection_freeze` and `output_hashes`.
- Historical M5 mechanism/candidate manifests bind old input digests. A portable
  new experiment still needs a documented downstream selection/freeze recipe
  and independent replay of the new
  query/pool/hierarchy bindings. Reusing historical digests is not that recipe.

These are remaining pipeline implementation requirements, not a request to
import old results. No old result bundle is
required for installing or testing the implementation.

## Metadata-only DEV plans and runtime pools

The two DEV planning documents (`dev_cohort_v1_bindings.json` and
`dev_coverage_prospective_selection_20261017.json`) contain selected case IDs,
counts, source locators and cryptographic commitments. They do not contain
processed candidate-pool records or ordered candidate-ID arrays. Their original
full versions are not source dependencies or required downloads.

Before executing a real DEV gate, generate its input directory through the
versioned data/query/pool pipeline. Pass that directory to the runner's
`--input-directory` freeze step. The loaders read generated `queries.json` and
`pools.json` there, verify the full ordered pool-prefix hash and ordered candidate
ID hash, and retain the independent sorted candidate/catalog/query/graph checks.
An absent input produces explicit generation instructions; a mismatched input
stops admission. No placeholder pools, implicit archive restore or network
fetch occurs on import. A different input version requires a new reviewed
configuration/freeze, not bypassing these commitments.

Synthetic code tests construct their own small deterministic toy pools in memory
and explicitly patch test bindings. Those toy records are never a production
fallback or an accepted replacement for a real experiment. Full historical
M5 downstream regeneration limitations described above still apply.

## Historical results

Reports describe past observations; the corresponding large evidence, logs and
binary output are intentionally not distributed in Git. Older report paths are
historical names, not fresh-checkout prerequisites. Markdown links to removed
artifacts lead here so they do not masquerade as available repository files.

Historical output inventories are retained only alongside independently held
external archives, not in the source repository. They are not required downloads
and are not a substitute for reproducing an experiment. For an existing archive,
provide its external JSON manifest explicitly. The manifest has a `files` list;
each entry contains a relative `path`, byte count `bytes`, and `sha256` digest.
Keep that manifest and generated outputs outside the checkout.

```sh
python tools/verify_artifacts.py --index /path/to/archive-manifest.json --root /path/to/existing/archive --prefix results/milestone_5d/
```

This opt-in command fails on absent or changed selected files with a useful
message. It does not download anything, modify the archive, or run in default
CI. Legacy tests similarly require explicit artifact opt-in (see `ci/README.md`).
For a new run, use the generating scripts and new manifests rather than this
historical hash comparison.

## Publication rule

Run `python tools/check_code_publication.py` before committing. It checks the
Git index for generated result/data paths and unexpectedly large new files.
`git status --ignored` shows local outputs excluded by scoped ignore rules;
JSON configs/schemas and synthetic fixtures remain normal tracked source.
The publication commit is based on the last public commit, with reviewed code
snapshotted from `00e5aa4dda8225a7d740e4ec2a42b1553a9d52b4`; it does not merge
private experiment history. Existing public history is preserved, not rewritten.
