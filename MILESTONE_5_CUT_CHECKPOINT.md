# HiRoute exact-cut bounded checkpoint

Validated local checkpoint on `codex/m5-time-cut-pwa`, based on upstream `cdf7fa7d41ad7c29e8d297c686dc1b20d2ac5c04`. No push or PR has been performed.

## Implemented and tested

- Versioned constructive time cuts; exact rational energy-wide Drive/S/C/CS propagation, attainment and inherited witnesses.
- Independent certified bounded REF; physical FLAT with dominance off/on; tiny deterministic action-partition HIER with its own incumbent, strict-primary pruning and equality retention.
- Original restored fixture: all REF/FLAT/HIER modes return `(44950,76,3,2C3C4S)` and independently replay valid physical witnesses. Different valid charge allocations are allowed.
- 18 independently frozen positive-domain cases, 100 independently generated bounded cases (400 cross-solver comparisons), six targeted attainment/incumbent regressions, and destination/route-grammar regressions pass.
- Final production tests: **78 passed, 64 subtests passed**. Independent REF tests: **87 passed**. All 78 production tests also run against the installed wheel outside the checkout; `hierarchy4r` and `timecut5` are packaged.
- Available historical suite on restored upstream and patched checkout: both **191 passed,29 failed,5 skipped,1 collection error**, with zero changed outcomes. Missing historical files/tools prevent full historical acceptance.

## Reproduce in Python 3.11

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_time_cut*.py' -v
python -m pytest tests/test_reference5.py -q
python experiments/time_cut_v2/run_bounded_validation.py \
  --cases results/milestone_5_reference/frozen_cases_v2.json \
  --reference results/milestone_5_reference/analytic_cases_ref_v2.json \
  --output /tmp/hiroute-bounded-parity.json
```

The REF tests need the repository's scientific Python test dependencies. Production cut/FLAT/HIER modules use the standard library.

## Evidence and limits

- [Semantic contract](docs/MILESTONE_5_TIME_CUT_CONTRACT_V2.md)
- [Conditional theory review](docs/MILESTONE_5_TIME_CUT_THEORY_REVIEW_V2.md)
- [PWA design](docs/MILESTONE_5_TIME_CUT_PWA_DESIGN_V2.md)
- [Independent operator review](experiments/time_cut_v2/oracle/REVIEW.md)
- [Independent solver audit](experiments/time_cut_v2/solver_audit/REPORT.md)
- [Exact real-input and remaining-gate audit](experiments/time_cut_v2/real_inputs/REAL_INPUT_AUDIT.md)
- Machine-readable results: `results/milestone_5_time_cut_v2/`, `results/milestone_5_reference/`.

This is bounded `H_ref` validation, not completion of the original A20/B64/C32 populations, real 2047-Region integration, deployable long-haul evaluation or holdout. Tiny-tree member scans are counted; no scalability claim is made.

Real Stage C needs a separate accepted-leg adapter: the accepted real router's equal-time convention differs from this synthetic graph selector. Immutable real fastest-route time/actual-length pairs must be consumed directly and losslessly, preserving co-attached Sites and zero self-legs; they must not be reinterpreted as graph edges and routed again. The input audit records the missing inputs at its audit time; later user-supplied/restored files must be reverified against that manifest.

The old v0/v1 failed assertions and evidence remain unchanged. Early foundation reports describe earlier checkpoints (including then-missing fixture/Python environment); the current checkpoint above supersedes those availability limitations without changing their historical record.
