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

`m5-requirements.txt` pins all 15 build/test dependencies and their registry
hashes. The intentionally reduced environment includes NumPy, SciPy, pandas
and PyArrow. PyArrow is required by the recovery tests that import the real
parquet engine and round-trip a tiny in-memory buffer. Its wheel hash targets
the documented CPython 3.11 Linux x86-64 environment.
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
3. Runs the same explicitly selected modules under normal Python and `python -OO`, with
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
The recovered additions also check the immutable capture loader, container
ownership and streamed hashes, recorded coalescing, independent real-family
anchor/phase validation, and real/coalesced mock replay. These are code-only
reconstruction checks, not acceptance of historical source or real populations.
Only the explicitly named synthetic/mock fixtures in the runner are staged.
Former results-based unit fixtures now live under tests/fixtures; no archived
experiment output is staged.

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

The recovered loader/real-trace stack passed **393 tests and 748 subtests in
each mode**, with no skips, in a fresh installed-wheel rehearsal lasting
57.9 seconds after dependency installation. The same dependency lock and
explicit nine-fixture allowlist were used.

The separate `run_m6h_reference_code.py` gate runs the M6-H wrapper's tiny
synthetic interface tests in normal and `-OO` processes, using the installed
wheel and independently parsed mock leg tables. It rejects skips, empty
collection and failures; each process has a 90/100-second CPU limit, 2 GiB
address-space limit and 150-second parent wall timeout. Helper processes and
network access are denied. It checks the backend's supported API, unchanged
exhaustive enumeration, fresh seed/winner replay, adapter-issued depth bounds
and preservation of unresolved/unattained statuses. The depth certificate is
explicitly adapter-derived, not supplied by the backend. This code-only gate
does not rerun any scientific case or certify a real-map REF result.

## Deliberately outside this gate

- The opt-in legacy suite (`pytest --include-artifact-tests`). Those tests need the full
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

The workflow uses standard `ubuntu-24.04`, one Python version and a 35-minute
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

## Optional terminal-energy gate

`run_terminal_energy_code.py` uses the existing installed Python 3.11 wheel and
unchanged reduced dependency lock. It runs finite native energy/context/recovery
and evidence-lifecycle fixtures in normal and `-OO` modes, outside the source
checkout, under pre-import CPU 90/100 seconds, AS 2 GiB and wall 150 seconds per
mode (parent timeout 165 seconds). Native compiler children remain CPU 20/25 and
wall 30 seconds. No production graph is read. This is a separate opt-in gate;
existing reachable/target/recovery gates remain required and unchanged.

## Default pytest and archived research tests

A clean code-only checkout supports `python -m pytest` with the reduced CI
requirements above. Default collection is deliberately limited to the modules
in `tests/code_only_manifest.py` plus the five validator modules named in
`pyproject.toml`, matching the main installed-wheel gate. The four named
extended directories and bootstrap modules run in separate required CI processes.
This is a focused code regression suite, not the historical full test suite or
research acceptance. Explicitly naming a documented extended directory/module enables that group;
combining every group in one process is not a supported passing gate because
resource checks use process-lifetime peak RSS. Prefer the separate CI runners.
Existing legacy modules are explicitly registered in `LEGACY_MODULES`.
A newly added unclassified test module is a hard collection error, including
with artifact opt-in; register it in the main, isolated-gate, or legacy cohort.
Review and extend the main allowlist for new data-free tests. The pytest header announces this selection; `pytest --collect-only` lists
it. Explicitly requesting an excluded module reports a usage error with the
opt-in command instead of silently ignoring the request.

For independent reproduction, generate the required research inputs and outputs
at their configured paths (including `results/`) and install the full dependencies
used by the selected milestone. This switch only enables test collection; it is
not a complete reproduction pipeline. For historical inspection, an existing
archive can optionally supply historical evidence, but importing it is not
independent reproduction. For example:

```bash
python -m pytest --include-artifact-tests tests/test_m5d_terminal_summary.py
# Or, after generating all milestone inputs and outputs with full dependencies:
python -m pytest --include-artifact-tests
```

The switch enables collection of legacy modules; it does not download evidence,
certify its provenance or turn missing data into passing tests. It fails early
when generated JSON outputs under the research results tree are absent. Individual legacy tests can additionally
require milestone-specific `--require-*-results` / `--require-real-data` switches
for acceptance instead of their historical optional skips. See those modules
for the exact inputs. Historical terminal-summary projection checks refer to the
`results/milestone_5d/terminal_state_audit_20261014/inputs/` tree and are no longer
a default GitHub Actions step. The historical tranche linked-receipt assertion
is separately opt-in in `tests/test_dev_coverage_tranche_archive.py`. These
historical acceptance assertions are not claims that the entire legacy suite
can already run from independently generated outputs.

Required default fixtures remain hard failures if absent. The installed-wheel
runner checks each fixture before copying and rejects skips, errors, failures
and empty collection. Tiny hand-built cases and expected analytical values are
versioned under `tests/fixtures/`; bulk experiment outputs are not CI inputs.

The expanded synthetic recovery suite has a bounded 900-second timeout per
Python mode. The original 300-second bound expired before completion during
local rehearsal of the expanded suite; the workflow budget is now 35 minutes
to accommodate both modes plus the other serial gates. This increases the
allowed runtime, not research scope, test exclusions, or correctness criteria.

Default target/energy tests verify source-checkout origin; their required CI
runners set `HIROUTE_REQUIRE_INSTALLED_WHEEL=1` and independently enforce wheel
origin before executing tests. The archived sequential-transport comparator
receipt assertion is separately opt-in in `tests/test_sequential_transport_archive.py`.

### Combined-process rehearsal limitation

An earlier combined extended/default rehearsal reported 14 failures, 20 errors,
1,137 passes and 9,529 passing subtests. Three failures used definitions loaded
before the historical comparator/origin fixes; the remaining suffix failures
were process-lifetime LP peak-RSS cap exhaustion after large native/recovery
groups. An isolated suffix-and-changed-tests rehearsal passed 38 tests and 56 subtests in
6.59 seconds. The default now uses only the main CI cohort; extended groups
remain independently required through isolated runners. No resource cap was
weakened, and the combined extended run is not represented as passing.

### Fixture content audit

The source-only publication removes both the generated REF result/certificate
cache (`analytic_cases_ref_v2.json`) and the generated G8 trace bundle
(`g8_node_batch_fixture.json`). Relocating generated output under `tests/fixtures`
does not make it source. Post-service comparisons now evaluate the independent
exhaustive reference from the tiny input cases during each test run; node-domain
checks generate and validate their trace from a synthetic mock leg table. The
three node-domain tests are now part of the main isolated gate. See
`tests/fixtures/README.md` for the per-file input and hand-arithmetic provenance
audit. No historical solver results or trace cache are loaded as a fallback.

## Narrow road-policy logic

The required installed-wheel gate additionally includes
`tests/test_raw_way_policy_logic.py`, checking exact raw tags, original reference
closure, rejection near-misses, immutable callback copies, and duplicate-way
rejection. It mocks only the osmium decoder interface, so the existing pinned CI
dependencies do not change. The production `graph.raw_way_policy` import is
verified inside the installed wheel. These checks run in normal and `-OO` modes.

The separately selected geospatial integration gate
`tests/test_road_policy_amendment.py` additionally needs Shapely and Python osmium;
it is **not** run by this reduced CI environment. See
[the amendment disclosure](../docs/ROAD_POLICY_AMENDMENT.md) for its command,
dependencies, audit units, and the limits of its synthetic evidence.
