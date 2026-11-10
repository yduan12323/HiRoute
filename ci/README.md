# Installed-wheel verification

Default CI uses `research-pipeline.yml`. It creates separate Python 3.11
environments for core, REF, native, geo, comparator and differential tiers.
No historical real solve, province rebuild or holdout runs automatically.

## Local commands

Start with a fresh Python 3.11 environment and the minimal hashed build/test lock:

```sh
python3.11 -m venv /tmp/hiroute-check
. /tmp/hiroute-check/bin/activate
python -m pip install --require-hashes -r ci/research-requirements.txt
python -m pip install --no-build-isolation ".[research]"
python ci/run_consolidated.py --group core
```

Optional tiers declare their own dependencies:

| Tier | Installation / prerequisite | Command |
| --- | --- | --- |
| REF | `python -m pip install ./reference` | `python ci/run_consolidated.py --group ref` |
| Native | REF, `./comparison`, C++17 and Boost.Multiprecision headers | `python ci/run_consolidated.py --group native` |
| Geo | `python -m pip install ".[geo,prepare]"` | `python ci/run_consolidated.py --group geo` |
| Differential | Core only; test-owned historical oracle | `python ci/run_consolidated.py --group differential` |
| Comparator | In its own environment: `python -m pip install ./comparison` and pytest | `python ci/run_consolidated.py --group comparator` |

The comparator tier runs without the core or REF package installed. Its pure
math, candidate assertions, transport and road-certificate tests use synthetic
inputs. The native tier includes the production-provider/independent-table bridge
and a tiny real worker subprocess with the explicit N64 profile.

The runner copies tests, fixtures and compatibility tools to a temporary directory
and checks that package imports resolve to installed wheels. It never adds the
repository `src` to `PYTHONPATH`. Every tier runs normal and `-OO` modes with
single-thread numerical settings and a bounded test-process timeout. Missing
required fixtures/dependencies fail rather than silently substituting a test.
`--record /new/file.json` preserves the output and dependency versions.

Ordinary `pytest` discovery is confined to the modern core tests. Optional and
historical modules stay explicitly registered and individually callable. The C
operator's independent REF replay has its own test module so core tests do not
silently require REF. Historical `timecut5` differential tests import only
`tests/oracles/timecut5`; those modules are absent from the production wheel.

## Explicit external artifact check

```sh
python ci/run_consolidated.py --group artifact \
  --artifact-root "$artifact_root" --manifest "$artifact_manifest"
```

The manifest uses `hiroute.artifact_manifest.v1` as documented in
[the pipeline guide](../docs/RESEARCH_PIPELINE.md). This command verifies every
listed external file and reports missing roles. It has no default artifact path,
no downloads and no implicit optional-pass result. `hiroute prepare --check-only`
additionally checks the frozen N64 input identities.

## Exact before/after comparison

```sh
python ci/exact_behavior_snapshot.py \
  --expected docs/consolidation-exact-baseline.json --output /tmp/exact-check-new.json
```

This runs five small attainment/tie cases for both Strong and Scale and compares
full exact statuses, keys and physical replays with the pre-refactor wheel.
The saved output is a behavioral baseline, not a source immutability gate.

Three existing read-only historical statistical checks remain separate:

```sh
python -B -m unittest discover -s tests -p test_research_reassessment.py
```

Old CI workflows now require manual dispatch with an explicit historical
`source_ref` (default snapshot `679239d`). They check out that revision to retain
its original source layout and dependency declarations. They do not constrain
normal evolution of the maintained pipeline. Historic runs and logs keep their
original input integrity and accounting checks.
