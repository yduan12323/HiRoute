# Optional exact cut-piece coalescing

This standalone feature adds the explicitly selected
`exact-adjacent-cut-coalescing-v1` representation. Existing public solver APIs
keep their original behavior and default reducer. The feature is not enabled
globally.

## Entry points

The `timecut5.coalesced_solver` module provides
`solve_bounded_coalesced`, `solve_hierarchical_coalesced`,
`solve_bounded_real_coalesced`, and `solve_hierarchical_real_coalesced`.
They retain the input schemas, stop bound, action choices, route primitives,
dominance selection and tie rules of the corresponding baseline APIs. Two
private solver cores accept an optional reducer callback; its default remains
the existing reducer. Results include a representation version and piece-count
statistics. The real-adapter entry points reuse the already available adapter
interfaces and require no new data format.

## Exact representation and witnesses

Pieces merge only when their affine function, attainment flag, physical state,
charge total and full action tuple are equal, and their energy domains have a
connected exact union. Open-open touching intervals remain separate unless
another input contains the missing point. Singleton domains and all endpoint
flags are preserved exactly. No tolerance, energy grid, approximate equality
or additional depth pruning is introduced.

A merged piece retains immutable guarded references to its original pieces.
Witness dispatch selects an original constrained parent whose domain contains
the requested energy and uses that parent's existing witness callback. It does
not reconstruct an unrestricted predecessor or turn an unattained limit into
an executable optimum. Dispatch scans the retained parents in a fixed order;
minimal representation and optimal dispatch complexity are not claimed.

## Proof-family boundary

This optional solver mode supports untraced pieces only. Before compaction,
propagation, terminal processing or reduction, it rejects known `_family`
metadata, including singleton and no-merge inputs. The standalone primitive
also rejects an actual merge involving known proof families. A future traced
mode needs a fresh certified guarded-union constructor and compatible operators.
The feature does not close the literal inherited-family/G8 audit obligation.

## Synthetic validation and packaging

The two added test modules cover exact endpoint combinations, missing points,
singleton unions, differing contexts, attainment, guarded witness dispatch,
cropped physical prefixes, 250 seeded complete symbolic interval-union checks,
and baseline/optional parity in all four modes on the 18 existing synthetic
fixtures. They also verify reducer selection and early proof-family rejection.

From a Python 3.11 environment with the project's test dependencies:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m pytest -q \
  tests/test_time_cut_coalescing.py tests/test_coalesced_solver.py
```

The new modules are part of the existing `timecut5` package. This change's
publication scope is source code, synthetic tests and this document. Real-query
acceptance records, new route/Site data, provenance exports and certificates
are outside this feature PR. Synthetic checks alone do not establish real C32
acceptance, deployment performance, unrestricted correctness or holdout results.
