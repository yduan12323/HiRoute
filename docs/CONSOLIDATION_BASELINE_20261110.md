# Consolidation baseline

Approved scope: N64 Strong/Scale, the public `hiroute` core, independent REF and
candidate verification. Snapshot: `679239d`; approved audit: `a1554ce`.

Baseline built from `git archive a1554ce`, outside the repository. Python 3.11.16,
setuptools 84.0.0, wheel 0.48.0. A new venv installed the core and REF wheels;
neither repository `src` directory was on `PYTHONPATH`.

| Wheel | SHA256 |
| --- | --- |
| hiroute 0.2.0 | 9ee7ef22e8aa897e4cf7acd47c50949332ec153ffa949e602e86f466c1584d3c |
| hiroute-ref 0.2.0 | 9970d6db83985997c6a7df3cad5b61be9b3e77f5ec6860a6301f5d24bedddfa0 |

Dependencies: pytest 9.1.1, NumPy 2.4.6, SciPy 1.17.1. Single numerical thread.
Eight baseline test modules: r0 contracts, exact search, C operator, prefix reuse,
semantic fixes, data producer, Scale bounds and Scale search. Test inputs were
copied unchanged. The initial staging omitted `tests/r0/c01_zero_stop_snapshot.json`;
after including that required fixture, both runs passed:

| Mode | Tests | Subtests | Wall time |
| --- | ---: | ---: | ---: |
| normal | 87 | 228 | 3.01 s |
| `-OO` | 87 | 228 | 3.39 s |

These timings describe verification, not solver performance gains. The `-OO`
pytest warning is expected; production contract checks use explicit exceptions.

Native verification uses g++ and Boost 1.83 headers extracted into the isolated
temporary workspace (no system installation). The extracted routing implementation,
input selection, pilot and historical N64 controller passed 44 regression tests,
including the required native routing test. No mathematical implementation changed.

The temporary build root is `/tmp/hiroute-consolidation-20261110`. Its contents
are disposable; the commands and test fixtures in the repository are the durable
verification mechanism. Wheel hashes above describe this run, not source locks.

## Scientific acceptance blocked by external inputs

The full historical graph TSV, supplemented catalog and bindings, original
candidate/table/DAG bundle and associated external receipts are not present in
this checkout. The audit report records expected paths and available identities.
No raw map replacement, full-matrix solve, holdout or province rebuild was run.
Engineering and small-domain regression results do not establish historical
end-to-end reproduction. Original raw PBF availability remains unresolved.
