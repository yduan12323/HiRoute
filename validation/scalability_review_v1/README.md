# Independent skyline correctness review, version 1

This graph-free audit independently checks the opt-in skyline against the unchanged baseline reducer. It is correctness evidence only; it establishes no real-road search completion, optimum or performance improvement.

## Reproduce

From the repository root, with a supported Python 3.11 environment:

```sh
python validation/scalability_review_v1/audit.py --output validation/scalability_review_v1/audit_results.json
```

`audit_results.json` records the exact executed interpreter/arguments, seeds, source SHA-256 digests, checkout HEAD and counts. The reviewed `pwa.py` change was uncommitted at audit time, so the file digest, rather than HEAD alone, identifies the source under test. Wall time is descriptive audit overhead and is not a benchmark.

The run checks:

- All 157,464 ordered triples of 54 `(tau, chi, rho, pi)` combinations and 2,000 seeded larger lists, including repeated `Cut` identities. The retained ordered object identities must match `reduce_cuts`.
- 250 seeded exact-rational PWA families with open/closed endpoints, affine crossings and repeated parent identities. Full exported provenance nodes, batches, roots, observed witness requests and witness values must match the baseline. Both arms execute 17,506 witness requests at epsilons 1 and 10^-50.
- Checks use explicit comparisons and remain effective under optimized Python.

## Review rationale and remaining scope

At fixed state and energy, the implementation's dominance preorder is the product of two total orders: `(tau, not chi)` and lexicographic `(rho, pi)`. After sorting by those orders and original index, precisely the strict running minima of the second order survive; input order is restored. The first equivalent witness is retained. Existing arrangement cells, callback validation, identity-based duplicate handling, parent indices and provenance construction remain unchanged.

The arrangement may still have quadratic size, and callback/provenance costs are unchanged. This audit is finite differential testing, not a universal proof or independent physical road replay. Separate worker tests cover an independently defined quadratic oracle and physical solver/trace integration.

`test_invocations.json` retains the separate directly relevant pytest invocation, including its two installed-origin precondition failures. These cannot be described as a full test pass. Those suites require the project's installed-package test harness for packaging checks.

## Point-selection mechanism benchmark

`PYTHONPATH=src:. ../hiroute-ci-venv/bin/python validation/scalability_review_v1/point_microbench.py`
reproduces the fixed synthetic 32/128/512-point experiment. The retained
`point_microbench_results.json` records five alternating-order repetitions and
separately counted scalar comparisons. It measures only point antichain selection;
arrangement construction, provenance, routing, durable replay and whole search
are excluded. No real-road speedup or scalability acceptance follows from it.
