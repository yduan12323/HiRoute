# HiRoute

HiRoute studies exact electric-vehicle stop planning. The maintained research
pipeline is **N64 Strong/Scale**, with an independently installable physical-model
verifier. Exact rational arithmetic, ordered candidates, physical replay and
failure denominators are preserved.

The current engineering release supports fresh controlled runs. Historical
end-to-end reproduction still requires external graph, catalog, candidate and
verification artifacts. The original 2026-10-16 PBF is unavailable here;
verified historical processed inputs are accepted. A newer map is a different
input and must not replace it.

## Install

Use Python 3.11. Installation builds wheels; an editable checkout is unnecessary.
From the repository root:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install ".[research]"
# Independent packages; install only the validation interfaces you need.
python -m pip install ./reference
python -m pip install ./comparison
```

Native routing additionally requires a C++17 compiler and Boost.Multiprecision
headers (Ubuntu: `g++ libboost1.83-dev`). Input preparation from existing catalogs
uses the standard library. Spatial attachment requires `hiroute[prepare]`;
new-map PBF production requires `hiroute[geo,prepare]` and the explicit source,
road policy, boundary and projection described in [the input guide](docs/REPRODUCING.md).

## Research workflow

First obtain the historical artifacts and their independently held manifest.
Set `artifact_root` to the restored archive and `artifact_manifest` to its trusted
manifest. Set `run_root` to a new parent directory. Each command below creates a
new output; the benchmark can consume the full declared DEV budget and is run
only when that cost is authorized.

```sh
hiroute prepare --config configs/research/n64.json \
  --artifact-root "$artifact_root" --manifest "$artifact_manifest" \
  --output "$run_root/prepared"

hiroute benchmark --prepared "$run_root/prepared" --output "$run_root/run"

hiroute summarize --input "$run_root/run" --output "$run_root/summary.json"
```

`prepare --check-only` verifies the full external manifest and frozen input
identities without selecting candidates or invoking a solver. Missing/corrupt
inputs produce an explicit `input-verification.json`; preparation fails closed.
Preparation records the complete effective configuration, candidate order and
per-run code/environment provenance. The N64 profile explicitly enables landmark
A*, source-tree reuse, seed pruning, inbound and eager bounds; pending-activity
screening remains off.

`benchmark` gives each method a supervised query process, an independent physical
replay and durable receipts. It creates a fresh budget ledger, preserves all 48
query cells / 96 method slots, and stops without retrying uncertain work. Historic
reuse rows remain historical observations; a fresh benchmark runs fresh pairs.

`summarize` verifies terminal and per-slot receipts and reports full and supported
denominators, failures, completion CDFs and censored median/p95 intervals. It
imports no solver or worker. A failed/interrupted cohort cannot become an exact
completion through reporting.

For a sealed independent candidate bundle:

```sh
hiroute-compare verify --bundle "$comparison_bundle" \
  --artifact-root "$comparison_root" --output "$run_root/independent-check"
```

This command verifies the complete assignment, original DAG, strict support,
physical replay, raw paths and matching receipts under its own resource limits.
Acceptance requires `terminal.json` with `status=COMPLETE` and its matching body
and witness receipts. The historical run remains UNKNOWN. The resulting witness
is a feasible improvement conditional on the supplied leg table, not an optimum.

See [formats, budgets and recovery boundaries](docs/RESEARCH_PIPELINE.md) and the
[implementation/verification report](docs/CONSOLIDATION_PHASE_B_20261110.md).

## Small exact example

The existing `validate`, `solve` and `run` interfaces and strict v1 `SolverConfig`
are preserved. `solve` does not automatically select the research N64 profile.

```sh
hiroute validate --problem tests/r0/c01_zero_stop_snapshot.json
hiroute solve --problem tests/r0/c01_zero_stop_snapshot.json \
  --config configs/rebuild/r1_flat.json --output /tmp/hiroute-example-new.json
```

## Maintained structure

```text
src/hiroute/
  contracts.py, cli.py          Public snapshots, solver configuration and commands
  data/                        Input validation, road policies, attachments, candidates
  exact/                       Exact optimization and independent physical replay
  routing/                     Python/native selected-leg providers
  execution/                   Effective configuration, workload, worker and coordinator
  runtime.py                   OS resource supervision
  evaluation/                  Pure receipt statistics and integrity-checked reports
reference/src/hiroute_ref/      Independent bounded reference optimizer
comparison/src/hiroute_compare/ Independent physical model and candidate verifier
configs/research/n64.json       Explicit adaptation of the frozen N64 protocol
ci/run_consolidated.py          Installed-wheel test tiers
tests/oracles/timecut5/        Minimal test-only historical differential oracle
```

Other historical source and research records remain recoverable and outside the
production wheel. Legacy script imports forward to the maintained modules for
one transition cycle. Deletion of unresolved historical dependencies is blocked
until the external input closure and retained callers are verified.

## Verification and evidence

[CI instructions](ci/README.md) separate core, native, geo, REF, comparator,
differential and explicit artifact checks. Normal and `-OO` checks use exact
behavioral assertions, not frozen source hashes or source-file counts. No full
real N64 cohort, province rebuild or holdout runs in default CI.

The [Phase A audit](docs/PIPELINE_CONSOLIDATION_PHASE_A_20261110.md),
[baseline](docs/CONSOLIDATION_BASELINE_20261110.md),
[research status](docs/CURRENT_RESEARCH_STATUS.md) and
[verified improvement record](docs/SEPARATELY_VERIFIED_IMPROVEMENT.md) retain the
scope and provenance of past research. Small-domain CI does not establish
historical real-map reproduction or a performance improvement.
