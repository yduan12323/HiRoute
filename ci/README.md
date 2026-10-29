# CI checks

CI builds and installs the `hiroute` core wheel and the separate `hiroute-ref`
wheel. It runs current contract, exact-search, CLI, producer and tiny REF tests
against those installed packages from a temporary directory. Historical
`timecut5` and related packages are staged from source only for differential
regressions; they are not included in the default HiRoute wheel.

## Run locally

Use Python 3.11 in a new environment. The workflow's lock installs the build,
pytest and legacy-test dependencies, then invokes the same bounded runner:

```sh
python3.11 -m venv /tmp/hiroute-ci
/tmp/hiroute-ci/bin/python -m pip install --require-hashes -r ci/m5-requirements.txt
/tmp/hiroute-ci/bin/python ci/run_m5_code_only.py
/tmp/hiroute-ci/bin/python ci/run_m6h_reference_code.py
```

The runner creates isolated wheel builds for the core and reference packages,
installs them without editing the checkout, and runs focused suites in normal
and optimized Python. It also runs a selected legacy regression cohort using
staged source modules. It does not install the project editably or expose
`src/` on the HiRoute test import path.

The PBF reader's geospatial dependencies are optional (`hiroute[geo]`) and are
not installed by this data-free gate. Tiny exact snapshots and synthetic OSM XML
fixtures exercise the installable core; no raw map, prior result, credential or
external artifact is used.

This CI is a code regression check. It does not certify broad-scale performance,
real-map independent REF equivalence, historical R0–R4 results or holdout work.
