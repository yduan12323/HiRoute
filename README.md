# HiRoute

HiRoute is a Python package for exact bounded electric-vehicle stop-planning on
explicit directed road graphs. The current runnable core is `hiroute`; it does
not require the legacy experiment packages or the optional REF implementation.

## Current capabilities

| Area | Current support |
| --- | --- |
| Problem input | Versioned JSON `ProblemSnapshot`; exact rational numeric values; directed edges and explicit ordered Sites |
| Search domain | User-declared candidate order and depth bound; exact search is intended for bounded cases, with no broad-scale or unrestricted-optimality claim |
| Methods | `flat` and `hier` through the `exact_core_search` backend |
| Profiles | `reduction=none`, `charging_operator=bounded_time_cut_v2`, `coalescing=none`, `bound=none`; other profiles are rejected |
| Real input | Shandong PBF producer API with the `geo` extra, routing policy, boundary and projection; it validates input structure and policy without historical admission receipts |
| Independent REF | Separate package in `reference/`; optional, with a bounded snapshot interface |

The latest recorded project status remains limited: real-map REF confirmation and
holdout work are incomplete. See [current research status](docs/CURRENT_RESEARCH_STATUS.md)
for the historical scope. A synthetic CI pass is not research acceptance.

## Install and try

Python 3.11 is required. Build and install a wheel from a checkout:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install build
python -m build --wheel
wheel=$(find dist -maxdepth 1 -type f -name 'hiroute-*.whl' -print -quit)
test -n "$wheel"
python -m pip install "$wheel"
```

Run the included tiny exact example. It writes to a fresh temporary directory:

```sh
run_dir=$(mktemp -d)
hiroute validate --problem tests/r0/c01_zero_stop_snapshot.json
hiroute solve --problem tests/r0/c01_zero_stop_snapshot.json \
  --config configs/rebuild/r1_flat.json --output "$run_dir/result.json"
```

For Shandong PBF ingestion, install the wheel with its optional geospatial
requirements using `python -m pip install "$wheel[geo]"`. Supply the PBF,
`.poly` boundary, routing policy, query, projection and attachment parameters to
`hiroute.data.shandong.produce_shandong_snapshot`; no R0–R3 receipt or manually
computed problem digest is required. Input format, routing policy, endpoint,
Site and physical-model checks remain active.

## Tests and reproduction

The workflow builds and installs the core wheel, runs focused exact/search,
contract, CLI and producer regressions from outside the source tree, and runs
separate synthetic legacy differential and REF-interface checks. Run the same
workflow locally with the commands in [`ci/README.md`](ci/README.md). For
installation, input preparation and the scope of reproducible examples, see
[the usage and reproduction guide](docs/REPRODUCING_HIROUTE.md).

Historical reports and protocols remain under `docs/`; they describe their own
recorded inputs and do not gate ordinary package use.
