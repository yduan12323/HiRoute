# HiRoute

HiRoute is a research codebase for directed road-network analysis and bounded
electric-vehicle stop planning. It contains reusable packages, versioned
experiment runners, frozen configuration and input metadata, regression tests,
and reproduction guidance. Generated run outputs are excluded from version
control.

## Research status

The latest recorded research checkpoint is
[`M5D_LIMITED_BY_DATA_OR_SCALE`](docs/CURRENT_RESEARCH_STATUS.md), dated
2026-10-17. It reports completed known-DEV work alongside unresolved scale and
historical accounting limits. These results are scoped to their recorded
inputs, source versions, and environments; they do not certify real-world
navigation safety. The [M5-D report](docs/MILESTONE_5D_REPORT.md) gives the
outcomes and remaining limits. This status page is the entry point for later
research updates.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/` | Reusable graph, envelope, opportunity, microplan, stop-planning, hierarchy, and time-cut packages |
| `experiments/` | Versioned research runners and their scoped contracts |
| `configs/` | Experiment settings and identities for external inputs |
| `tests/` | Unit, contract, and synthetic regression coverage |
| `ci/` | The explicit data-free installed-wheel test gate |
| `docs/` | Current status, reports, protocols, and reproduction instructions |
| `validation/` | Scoped validation records and supporting checks |

The original research formulations remain at the repository root in
[`RESEARCH_SPEC_v0.2.md`](RESEARCH_SPEC_v0.2.md) and
[`RESEARCH_SPEC.md`](RESEARCH_SPEC.md). Milestone specifications, protocols,
and theory audits are grouped under [`docs/authority/`](docs/authority/README.md).

## Install the validated environment

The validated full experiment environment is Linux x86-64 with Python 3.11.
From a shell initialized for Conda/Mamba, create it from the checked-in package
lock, then install the local project:

```bash
mamba create -n hiroute-repro --file environment-linux-64.lock -y
conda activate hiroute-repro
python -m pip install --no-deps --no-build-isolation -e .
```

Some regional data preparation also uses the separate pinned `osmium` toolchain.
Platform support, dependency details, and environment checks are in
[`docs/REPRODUCING.md`](docs/REPRODUCING.md).

## Test

For data-free development, run the isolated-wheel gate described in
[`ci/README.md`](ci/README.md). It builds and installs a wheel in a disposable
environment and runs the explicit synthetic regression set; it does not need
OSM data or historical experiment outputs. The GitHub workflow is
`.github/workflows/m5-code-only.yml`.

Legacy tests that require real graph data or prior milestone outputs are
opt-in. Their inputs and acceptance commands are documented in
[`docs/REPRODUCING.md`](docs/REPRODUCING.md); do not treat a data-free CI pass as
a real-data reproduction.

## Reproduce an experiment

Start with [`docs/REPRODUCING.md`](docs/REPRODUCING.md), then use the specific
versioned protocol and configuration linked from the relevant report. Each
reproduction should use a clean checkout and environment, retain its own run
directory, and record the exact command and runtime identity. Do not overwrite
historical outputs or substitute newer data for a frozen input.

For example, a prepared Milestone 4B workspace uses
`python scripts/run_microplan_benchmark.py`; the
[M4B report](docs/MILESTONE_4B_REPORT.md) and reproduction guide describe its
prior inputs and reproduction limits.

The repository preserves input, output, receipt, and historical evidence
integrity checks. Per-run source identities record which code produced an
outcome; they are provenance, not restrictions on future source changes. See
[`AGENTS.md`](AGENTS.md) and [`docs/SOURCE_PROVENANCE.md`](docs/SOURCE_PROVENANCE.md).
