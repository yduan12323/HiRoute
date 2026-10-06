# M5 code-only regression gate

This checks installability and focused synthetic regressions for experimental
M5 code. It does **not** certify M5-V, full legacy-suite acceptance, real-data
reproduction, unrestricted optimality, or deployability.

## Reproduce locally

Use Linux x86-64 and Python **3.11.16**, matching the workflow. Run from the
repository root in a new, disposable environment:

```bash
python3.11 -m venv /tmp/hiroute-m5-ci-venv
/tmp/hiroute-m5-ci-venv/bin/python -m pip --isolated --disable-pip-version-check install \
  --index-url https://pypi.org/simple --require-hashes --only-binary=:all: \
  --no-cache-dir -r ci/m5-requirements.txt
/tmp/hiroute-m5-ci-venv/bin/python ci/run_m5_code_only.py
```

Choose another unused environment path when repeating this. The runner installs
the wheel into that environment; it never installs globally or edits the checkout.
Dependency installation needs PyPI access. Building and testing then use local
inputs, with no OSM download, Drive connection, credentials, or real graph needed.

`m5-requirements.txt` pins all 14 build/test dependencies and their registry
hashes. The intentionally reduced environment includes NumPy, SciPy and pandas.
It is **not** a recreation of the full Conda environment or a test of every
dependency declared in `pyproject.toml`. The local wheel is installed with
`--no-deps` for that reason. Dependency upgrades should be separately reviewed
and rerun rather than silently resolving newer versions.

## What runs

[`run_m5_code_only.py`](run_m5_code_only.py) is the exact, explicit test and
fixture allowlist. It:

1. Builds a fresh wheel from staged production source with the pinned build
   backend; rejects validators, experiments or tests inside the wheel.
2. Installs that wheel, stages repository validator source separately, and
   verifies production imports come from the environment. The test directory
   contains no `src` tree or repository pytest `pythonpath` override.
3. Runs the same 24 selected modules under normal Python and `python -OO`, with
   one-thread BLAS/OpenMP/MKL and external pytest plugin autoload disabled.
4. Rejects missing fixtures, zero collected tests, skips, errors and failures.

Coverage includes exact cut/PWA operators, bounded and tiny-HIER behavior,
coalescing, forged-incumbent replay, immutable-leg/export-input mocks,
independent REF adapter mocks, family provenance/receipts, invocation traces,
restricted affine suffix certificates/witnesses, and trace/coalescing guards.
Two additive v2 modules also cover continuous convex full-capacity charging
with positive nondecreasing slopes, and genuinely charging-free S-only cases.
They use explicit v2 models/ledgers and require result-plus-arrival-band witness
binding. They do not admit generic nonconvex PWA, real-leg integration,
coalescing, frozen numerical populations, or literal G8 closure.
Only the nine explicitly named synthetic/mock JSON fixtures are staged.

The v2 fixtures are hand-authored inside its test modules, so adding this
coverage needs no data fixture or dependency change. All v1 files, the locked
14-package environment and the workflow permissions/runner remain unchanged.

The initial rehearsal on the PR5 public tree passed **298 tests and 413
subtests in each mode**, with no skips. `-OO` produces the expected pytest
warning about assertions outside test modules; negative validator tests still
run. That warning is not a certificate of all optimized-runtime behavior.

The additive convex/no-curve v2 integration was rehearsed in a fresh environment
using the same hash-locked dependencies: **330 tests and 489 subtests in each
mode**, with no skips, in 38.1 seconds after dependency installation. These
counts include the existing affine-v1 regressions; they are focused CI evidence,
not a newly admitted frozen numerical population or a performance benchmark.

## Deliberately outside this gate

- Whole-suite `pytest` and legacy real-result tests. Those need the full
  geospatial stack (including pyrosm, igraph, GeoPandas, PyArrow and native
  tooling where used), processed graph/OD data and earlier milestone outputs.
  Even `-m 'not integration'` is not a reliable data-free substitute because
  collection/imports and some historical result tests have extra requirements.
- OSM preprocessing, graph reconstruction, real exports, the native streaming
  exporter, full independent REF/certificate archives, original A/B/C
  populations, and performance/holdout runs.
- Literal exact inherited-family G8 closure or an aggregate M5 acceptance
  record. Synthetic trace/suffix tests exercise their tooling but do not supply
  that research evidence. Coalesced/traced and real-network acceptance must
  match the specifically accepted modes; passing one does not certify all.

The [research master plan](../docs/time_cut_v2_authority/HIROUTE_RESEARCH_MASTER_PLAN.md)
keeps the stages distinct: §43 M5-T requires semantic/theorem closure; §44
M5-V independently validates REF/FLAT/HIER correctness; §45 M5-D follows M5-V
with frozen bounds, long-haul development, work reduction and growth analysis;
§46 M6-H uses untouched holdout after algorithms, thresholds and metrics freeze.
This workflow alone establishes none of those milestone decisions. At this
gate's introduction, literal inherited-family G8 and consolidated M5-V
acceptance remain open. Existing mathematical review is separate from CI.

## Workflow security, resources and rollout

The workflow uses standard `ubuntu-24.04`, one Python version and a 10-minute
job timeout. Normal and optimized tests run serially; newer runs cancel older
runs for the same event/ref. Local rehearsals used about 32–36 seconds after
dependencies were installed; the fresh pip environment occupied 332 MiB. Cold runner setup/network
time varies; allow a few minutes initially and measure the first hosted run.
These are observations/estimates, not a resource bound or performance claim.

Both official GitHub actions are pinned to full commit SHAs: [checkout
v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) and [setup-python
v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0). Permissions
are `contents: read`, checkout credentials are not persisted, and the workflow
does not use repository secrets, `pull_request_target`, custom runners, caches,
artifact uploads, publishing or deployment. GitHub still retains ordinary job
logs. See [GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

As verified on 2026-10-06, this repository is public and GitHub documents
standard hosted-runner compute as free for public repositories. This is
conditional on keeping that runner/repository category; private repositories
have plan quotas and larger runners are chargeable. This workflow does not
create Actions artifact/cache storage. See [billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and [runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

No required-check or branch-protection settings are changed by these files.
Before relying on the gate for a merge, review the diff and verify the first
GitHub-hosted run against the exact candidate commit. A local rehearsal does
not prove that the Actions workflow has run. Label any main-branch integration
as experimental unless the separate research acceptance is also complete.
