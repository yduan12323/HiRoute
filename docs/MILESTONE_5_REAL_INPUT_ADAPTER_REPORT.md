# Real compact inputs and immutable solver adapters

Status: preparation and mock parity verified; real C32 optimization has not run.
The delivered `579c6db` checkpoint remains immutable. This follow-up preserves
the original routing implementation and introduces a separate direct-leg input
boundary rather than interpreting route totals as graph edges.

## Results

- All six restored source files passed recorded size/SHA256 checks.
- Streaming native export: 105 unique source searches, 1,231 requested ordered
  pairs, 16 complete pool tables, 32 resolved query states, no unreachable pair.
  Nine extra co-attached Site instances retain distinct semantic identities.
- Every pool retains all 2,047 original Region indices and empty branches.
- Native pair/full calibration: 48 selected labels over three real sources,
  bitwise equal in both time and actual selected length. This is a subset check.
- Export elapsed 174.45 seconds; peak RSS 1,659,973,632 bytes. No full-array
  cache across sources, graph rebuild, Igraph or KD-tree was needed.
- Production read-only importer loaded all 32 states and recomputed their
  original-tree restrictions in 12.23 seconds, without invoking an optimizer.
- Five pre-solve frozen production mocks match independently implemented REF.
  Critical review adds 16 frozen adversarial mocks and 80 production variants,
  plus a separately frozen secondary-nonattainment case.
- Final targeted glob: 167 passed, 5 legacy integration tests skipped, and
  87 subtests passed. New adapter/exporter and independent-adapter tests passed.
  Installed-wheel standard-library validation separately passed all 117 tests
  under an isolated `python -I`.

Export manifest SHA256:
`f846eb37219a34dea74aa9a79e7673b8cdae03ae281de189cb9b602a98ac380d`.
Selection manifest SHA256:
`0e39ad906c01e05b4a4b764b3270360e309c24d1ae67d7a2e3533b6dca8af06a`.
Resolved states SHA256:
`d4bd50215c8035552ca47a9bf4e175d580eb265a2e9acbeff5d574c60b08b57c`.

## Contract and limits

Site IDs identify actions and pi; road anchors identify physical states.
Co-attached Sites use identity zero legs and remain separate choices. Terminal
exclusion uses destination road-anchor equality, including co-attached aliases.
The synthetic fixture route tie policy is unchanged. Real tables consume the
accepted native time/actual-length labels, including their direction and exact
binary64 records, without rerouting or assuming triangle inequalities.

All eight newly exported forward-native baseline values differ bitwise from
historical OD summary floats by approximately 9e-13 to 2.5e-11 seconds. The
export preserves those differences and computes windows only after exact ratio
conversion. Capacity, SOC, reserve, consumption 1/6250, overhead, penalty and
charging coefficients are separately declared exact rationals. No bitwise
legacy floating-evaluator equivalence is claimed.

Real HIER consumes the original restricted tree, uses exact immediate inbound
minima and a zero onward-time bound. It never prunes continuation because the
direct terminal leg is energy-infeasible. Full road-edge path witnesses are
not serialized; replay checks immutable physical primitives and stop equations.

Independent REF preflight counts 455,507,366 charging/max regimes after safe
physical exclusions. Exhaustive C32 jobs were not launched. Formal prerequisite
populations, reviewed resource-bounded independent oracle work and exact
node-constrained inherited-mask certificates remain separate gates. Current
frontier traces do not fully serialize inherited predecessor restrictions.

## Reproduce without loading the real graph

From the repository root with Python 3.11 and project test dependencies:

```sh
PYTHONPATH=src python -m pytest -q tests/test_time_cut_* tests/test_real_*.py
PYTHONPATH=src python -m pytest -q tests/test_reference5_real_adapter.py
```

Compact exported data and provenance are under `results/milestone_5_real_export`.
Original hierarchy bytes are already tracked at
`results/milestone_4r_b1/hierarchy.json`. See
`experiments/time_cut_v2/real_export/prepare_queries.py --help` for read-only
query import and `experiments/time_cut_v2/real_export/README.md` for the resource-preflight/export
command and `MILESTONE_5_REAL_SOLVER_ADAPTER_DESIGN.md` for consumer APIs. Tests
use mocks; loading the compact real cases remains read-only preparation.

The optimized-runtime replay correction is independently backportable as
`ef2f356`; it prevents forged incumbents under Python `-O` and `-OO`.
