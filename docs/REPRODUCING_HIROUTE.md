# Reproducing HiRoute

This guide covers the package and its small deterministic tests. It does not include a particular experiment's inputs, identifiers, outputs, resource limits, or results.

## Install and run focused tests

Use Python 3.11 in a fresh environment. Build and install a wheel from the checked-out source, then run the exact-core and synthetic producer tests from the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip build pytest
python -m build --wheel
python -m pip install 'dist/hiroute-*.whl[geo]'
python -m pytest -q tests/test_exact_search.py tests/test_exact_pipeline.py tests/test_exact_pwa_migrations.py tests/test_exact_pwa_partition.py tests/test_exact_terminal.py tests/test_time_cut_v2.py tests/r0 tests/r2
python -m pytest -q tests/test_shandong_raw_policy.py tests/test_shandong_spatial.py tests/test_shandong_spatial_parallel.py tests/test_shandong_pbf.py tests/test_data_producer.py
```

The `geo` extra pins the Python geospatial readers. Raw-PBF processing also requires the corresponding native geospatial libraries; use the versions supported by the target platform and record them with the run. Tiny PBF files under `tests/data/` are synthetic fixtures only.

For tests that explicitly exercise the independent reference package, install it from `reference/` in the test environment and run the relevant reference CLI tests. The reference implementation is an audit path; it is not a production solver dependency.

## Parameterized request and resource admission

`configs/shandong-query.example.json` and `configs/resource-profile.example.json` contain placeholders only. Supply a separate local JSON parameter file, then render and validate both before any expensive work:

```sh
python tools/prepare_run.py --request-template configs/shandong-query.example.json --profile-template configs/resource-profile.example.json --parameters local-parameters.json --root . --output-dir local-admission
python tools/run_admitted.py --request local-admission/request.json --profile local-admission/resource-profile.json --admission local-admission/admission.json --receipt local-run/receipt.json --stdout local-run/stdout.log --stderr local-run/stderr.log -- python -m hiroute --help
```

The preparation step checks caller-supplied input checksums, routing-config shape, exact numeric fields, endpoint/candidate structure, unresolved placeholders, and whether the requested memory cap plus growth margin and headroom fit the current Linux `MemAvailable` sample. The generated admission record is a snapshot, not a continuous host-memory guarantee. The runner rechecks input hashes and headroom immediately before launch and delegates wall, CPU, and address-space caps to the installed supervisor. Receipts and rendered local configs should remain outside the source distribution; they contain per-run provenance. The tools have no embedded run IDs, input paths, resource values, or default budget.

The smoke tests exercise template substitution and rejection using only the included tiny synthetic fixtures. They validate request shape and hashes, not whether a real OSM graph contains or attaches a given endpoint or candidate.

## Input and output discipline

Pass source PBF, boundary, routing policy, and query configuration explicitly. A query configuration should bind the source and boundary checksums, units, endpoint identities and coordinates, candidate order, reference horizon, and any schedule fields. Resolve and validate every placeholder before processing. Store generated graphs, snapshots, receipts, and solver outputs outside the source checkout in a new run directory. Never treat a prior graph, output, seed, or witness as newly generated input.

Use a separate clean environment and new output directory for any independent rebuild. Compare the generated mathematical inputs and results under a comparison rule fixed before running; do not require byte identity of receipts that contain run metadata. Do not claim broad-domain validity from a finite synthetic test set.
