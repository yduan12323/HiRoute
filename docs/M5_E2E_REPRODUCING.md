# Installed M5-E2E reproduction entrypoints

This recipe is implemented, but was not executed end-to-end on real inputs in the
2026-10-22 delivery: host memory safety admission failed. Do not bypass it.

## Source and installed artifacts

Use the exact evaluated source SHA from the delivery manifest, not moving main.
Create separate fresh checkouts, Python 3.11 environments and run roots for A/B.
Install the hash-locked `ci/m5-requirements.txt` for the synthetic gate. For actual
raw preprocessing, additionally use the exact installed package/version lock and
hashed requirements under `experiments/shandong_preprocessing_v1/`, osmium 1.18.0
and the recorded compiler. Do not replace pinned dependencies to make import pass.

Build/install the core wheel normally. Build the second wheel with
`python ci/build_m5e2e_tools.py --out /absolute/artifacts/tools` and install it
with `python -m pip --isolated install --no-deps /absolute/artifacts/tools/*.whl`.
Both wheels must come from one clean source commit. The tools artifact contains
embedded source and module identities, checked by every admitted CLI stage.
Record both wheel hashes. Run `python ci/run_m5e2e_code.py` for normal/-OO synthetic
checks; it stages tests outside the repo and checks installed import provenance.
It does not establish E4.

## Actual stages on an eligible host

Use absolute paths. Run from outside both source trees; unset PYTHONPATH.
Substitute A's paths in the following exact interface, then independently use B's
new checkout/environment/run root. Only the verified immutable raw cache and
package cache may be shared. The two builds MUST share one total budget root.

```sh
python -m experiments.m5e2e_v1.cli preflight \
  --source /work/source-A --config /work/source-A/configs/m5e2e/dev_real_micro_v1.json \
  --raw-cache /work/raw --run-root /work/build-A --budget-root /work/budget
```

For each next stage, use the same required arguments, replacing `preflight` with
`prepare`, `freeze`, `solve`, `verify`, then `summarize`. Preparation also needs
`--osmium /absolute/bin/osmium --compiler /absolute/bin/g++`. To compare, run
A's `summarize` with `--compare-run /work/build-B`. A blocked preflight permits only
summary, not numerical execution. Raw filenames and exact SHA/byte identities are
in the frozen configuration. Frozen polygon provenance is explicitly Oct 21, not
misrepresented as an Oct 16 historical polygon.

Prepare/freeze jointly retain the 90-minute/2-CPU-hour allowance for each build.
Methods/checks use separate 120-second workers. At most two prepare/freeze attempts
are admitted by the shared ledger. Unknown cleanup stops continuation. Setup,
installation, tests, metadata recovery and CI reservations must be added to the
round ledger; phase receipts alone are not the aggregate task accounting.

The original bridge is separate and is not launched by this CLI. Only an exactly
rebound exposed original N8/SOC0.30 seed-derived case may enter the unchanged
`experiments.m6h_manifest_v1.reference` contract, at most once. On this delivery
it is NOT_RUN_ENVIRONMENT and original REF remains UNKNOWN.

The E2E report lists unexecuted branches. Do not present canonical MATCH,
installed synthetic success, or source-identical wheels as clean real A/B success.
