# Portable candidate library tests

These 26 deterministic, bounded tests exercise the explicit public modules
`timecut5.portable_candidate_policy`, `timecut5.portable_candidate_binding`, and
`timecut5.frozen_candidate_catalog`:

- 21 selected-leg policy tests from the reviewed portable core
- 3 sparse-domain binding tests from the reviewed portable core
- 2 metadata-loader tests using synthetic files and a mocked Parquet reader

The selected-leg policy tests use the unchanged real selected-leg reconstruction
provider with a synthetic router. They test policy mechanics, exact energy
arithmetic, fail-closed behavior, cleanup, and query binding. They establish no
production graph/native provenance, production route feasibility, runtime
admission, completeness beyond the stated policy, or default activation.

## Installed-package execution

Build and install the candidate wheel with the exact reviewed repository
baseline before running these tests. NumPy and pandas must be available in the
test environment. Do not add `src`, the frozen runtime workspace, or a dependency
snapshot to `PYTHONPATH`. The test files contain no `sys.path` changes.

From a directory outside the repository, run both commands with absolute paths:

```sh
"$VENV/bin/python" -I -B -m unittest discover \
  -s "$CANDIDATE/tests/portable_candidate" -t "$CANDIDATE/tests" \
  -p 'test_*.py' -v
"$VENV/bin/python" -I -B -OO -m unittest discover \
  -s "$CANDIDATE/tests/portable_candidate" -t "$CANDIDATE/tests" \
  -p 'test_*.py' -v
```

`unittest` discovers the test package through its standard test directory;
application imports resolve through the installed `timecut5` package. No test
launches a production worker, server experiment, or numerical road-network run.

## Explicit production-fixture exclusion

The reviewed runtime suite also contains
`CatalogTests.test_static_original_od07_full_catalog`. It is deliberately not
part of these portable default tests. It calls the runtime-specific
`prepare_online.make_spec` and `online_selection.baseline_selection`, authenticates
the original private frozen OD07 source files, and checks 641 eligible charging
sites, including 64 baseline chargers. Those private metadata files and runtime
orchestration dependencies are not part of this reusable library.

This is an explicit scope exclusion, not a skipped, weakened, or synthesized
production check. The original test remains unchanged with the frozen runtime
validation evidence. Passing this portable suite does not claim that the
production metadata test or the online gate was rerun. The original frozen test
must remain a separately controlled check whenever that production environment
is validated.
