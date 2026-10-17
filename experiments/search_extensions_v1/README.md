# Search extensions: isolated prospective DEV gate

This package is executable but **disabled by default**. `--plan` only prints the
prospective manifest. No import, test, or default CLI starts a road experiment.
No old result, old witness, historical timing, holdout, or success requirement is
used. Compare only the three new-version arms in this gate.

## Fixed first gate

- OD02_energy_only_soc3_10, original N128 candidates and original hierarchy IDs.
- One newly generated, independently double-replayed common seed and its Hmax.
- Full native routing, terminal-energy screening ON only in search, exact indexed
  Region ALT, two-source / 1 GiB source cache, same pinned environment/source.
- Order: baseline → onward_only → coalescing_only. Exactly one feature enabled in
  either treatment. No combined arm.
- Each search receives an externally enforced **120-second exact phase**, beginning
  after graph/native/seed/bound setup. A completed proof may finish earlier.
- Every admitted search is followed by a separate fresh-process full-routing
  durable-incumbent replay. A timeout is admitted only for `phase_timeout` with
  a recorded phase entry; a setup/wall timeout cannot pass as exact search.
- Denominator: 1 preparation + 3 searches + 3 independent replays = **7 stages**.
  Failed, timed-out, blocked and unknown stages remain in the ledger. Preparation
  and search workers each have 600s wall/CPU limits; replays have 180s wall/120s CPU.
  Maximum worker reserve is 2940s wall and 2760s CPU; maximum exact-search exposure
  is 360s. Parent CPU soft reserve is 90s, as in the verified runner.

## Implementation and evidence

The existing recovery runner owns all process supervision, external deadlines,
compact result envelopes, source/input verification and owned cleanup. Its added
injection points preserve old defaults. There is no second supervisor.

The extension policy (arm, onward switch, coalescing switch, complete closed
manifest digest) is checked against runtime state and bound into every durable
incumbent domain/source identity. The original query, seed key, Hmax, original
tree, site catalog, graph/source closure and native identities remain bound.
Fresh replay uses unmodified, non-coalescing full-routing verification contexts;
the search-only extension binding is still required to admit its durable record.
Cross-arm incumbent recovery fails closed.

Each completed search records setup/search wall time, the full lexicographic key,
configuration, and a hash of `arm/metrics.json`. Metrics include source/target
route calls, source-cache counters, route wall/CPU time, coalescing input/output
pieces/maxima, and solver checkpoint counters. Metrics snapshots are atomic.
On a hard timeout cumulative counts and maxima at the last completed checkpoint
are **partial lower bounds**. `source_cache_bytes` is an instantaneous occupancy
gauge and is never a lower-bound claim. Checkpoint depth is the last observed
layer start. These snapshots must not be presented as final counts or exact search
runtime. Normal completion records final counters from the returned solver result.
Actual phase elapsed time/status is in the supervisor receipt. Checkpoint cadence
is layer-boundary driven, not a promise of periodic sampling during native calls.
A missing metrics artifact means missing data, never zero. No optimality claim is
made from a timeout, an improved feasible incumbent or a supervisor SUCCESS alone.

## Closure and launch

The checked-in manifest stays `launchable=false` until the parent explicitly
freezes reviewed source, all nine byte-identical inputs, compiler and runtime.
`source_identity` includes this entire new experiment package in the executable
closure. Use an external frozen manifest file, not a self-referential replacement
inside the source closure. Missing inputs or an uncommitted/source-drifted tree
fail before launch. A valid freeze is necessary but does not itself authorize a
large-graph run.

After explicit parent launch instruction only:

    python -m experiments.search_extensions_v1.run --gate \
      --manifest /absolute/frozen-manifest.json --manifest-sha256 SHA256 \
      --output /absolute/new-owned-output --cpu APPROVED_CPU

The gate stops on preparation failure, search failure other than exact phase
expiry, unknown/unverified cleanup, replay failure, drift or exhausted orchestration
budget. Completion means integration/replay admission, **not a positive result**.
Inspect all seven stages, full keys, metrics coverage and receipts before accepting.
There is no automatic batch, repeat, reverse-order or holdout path. Reverse order
(coalescing_only → onward_only → baseline) is a separate prospective run only
after first-gate acceptance and a new explicit parent launch decision; this CLI
intentionally implements only the first gate.

## Small-graph regression

    PYTHONPATH=tests/m5d_recovery:src ../hiroute-venv/bin/python \
      -m unittest discover -s tests/m5d_recovery -p test_search_extension_gate.py -v

These tests check default closure, policy tampering, fixed orchestration wiring,
three real native tiny-graph arms, common seed/Hmax, terminal-energy integration,
independent durable replay, complete keys and cross-arm rejection. They never
load the restored OD02 road graph.
