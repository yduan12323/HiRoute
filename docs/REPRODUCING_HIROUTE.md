# HiRoute usage and reproduction

This guide covers the current installable core and its bounded examples. It does
not certify large-scale routing, real-map REF equivalence or holdout performance.

## Build and install the core

Use Python 3.11 and a fresh environment. The default wheel contains `hiroute`
only; it does not include legacy experiment packages or an REF solver.

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install build
python -m build --wheel
wheel=$(find dist -maxdepth 1 -type f -name 'hiroute-*.whl' -print -quit)
test -n "$wheel"
python -m pip install "$wheel"
```

The core uses the Python standard library. For the Shandong PBF producer, install
the optional reader stack with `python -m pip install "$wheel[geo]"`. Build and
install the independent reference separately with `python -m pip install ./reference`
when a REF comparison is needed.

## Validate and solve a small snapshot

The repository includes a tiny zero-stop snapshot and exact flat configuration:

```sh
run_dir=$(mktemp -d)
hiroute validate --problem tests/r0/c01_zero_stop_snapshot.json
hiroute solve --problem tests/r0/c01_zero_stop_snapshot.json \
  --config configs/rebuild/r1_flat.json --output "$run_dir/result.json"
```

`ProblemSnapshot` validates schema fields, exact rational numbers, energy
bounds, directed-edge metrics, candidate identities, charging curves and depth
contracts. Its semantic content identifier is computed by the package; callers
do not need to provide or calculate it. Results include a run ID and the
computed problem identifier. Output creation is atomic and refuses to overwrite
an existing path.

The CLI accepts the installed package and explicit files; it does not need a
repository `PYTHONPATH`, editable install, migration script or historical
approval record. The smallest normal command for solving is:

```sh
hiroute solve --problem problem.json --config solver.json --output result.json
```

## Shandong data API

Install the wheel with `[geo]`. Call
`hiroute.data.shandong.produce_shandong_snapshot(raw_pbf, boundary_path, routing,
query, projection=..., max_distance_m=...)` with explicit routing/query data,
projection and attachment radius. The producer calculates ordinary source
fingerprints for its output records but does not require external SHA values,
source-tree hashes, prior receipts or R0–R3/C01–C24 approvals. It still checks
file availability, OSM tags, directed road policy, endpoint and candidate
bindings, exact model fields and physical input constraints.

The producer's PBF reader handles OSM roads and selected Sites; exact search
consumes a validated snapshot. It does not regenerate missing historical run
outputs or certify a new scientific experiment by itself.

## Tests and research limits

The GitHub workflow checks the installed core wheel and its focused exact,
contract, CLI and synthetic producer paths. Its historical package regressions
and tiny REF interface run separately. Reproduce those checks using
[`ci/README.md`](../ci/README.md). No test gate here performs a real-map run.

The recorded research state remains limited. Broad-scale performance, real-map
independent REF confirmation and holdout evaluation are not established by the
included fixture. Consult the dated reports under `docs/` for historical claims;
use a new checkout, environment and output directory for any future research
run, and record the actual input/configuration and software versions used.
