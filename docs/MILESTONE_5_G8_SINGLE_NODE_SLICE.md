# Bounded G8 single-node audit slice

The development-only `validation/suffix5/literal_g8_node.py` audits one query
from a verified real immutable-leg coalesced HIER trace. It derives the active
guarded family roots from the trace's `layer_start` occurrence, permitted
Region actions from its verified tree and immutable physics, and checks these
against the indexed query before accepting exact model certificates. Retained
ledgers must match that query's sequence and digests. The exact convex checker
reconstructs the complete ordered word and arrival-band model ledger.

On the small mock immutable-leg fixture, query 7 has one model and a certified
attained `J=14`; its recorded bound is `3`, so `3 <= 14`. A separate query has
zero enumerated models and is exact-empty. An empty optimum result can also
arise from nonzero models all certified infeasible; `exact_language_empty`
means zero enumerated models only. The genuine baseline real trace has a
different summary schema and returns `unsupported_original_node_domain`.
Synthetic hand-ledger checks require the explicit `indexed_only=True` mode.

Focused tests passed: 31 normal tests across `tests.test_literal_g8_node`,
`validation.suffix5.test_convex_checker`, and
`tests.test_recovered_real_coalesced`; 27 optimized (`-OO`) tests across the
first two modules. The real-node solve used 30 passes, 30 seconds, and the
existing 256 MiB cap. On Darwin, `ru_maxrss` is already bytes, so that test
passes an explicit byte-valued RSS reader; the initial default-reader run
failed because the Linux-oriented conversion multiplied that value by 1024.
The successful solve used 5 passes and observed 79,609,856 peak RSS bytes.

`max_models` caps accepted model count, while word and band enumeration is
eager and does not provide a hard time or memory bound. The connected-component
regression shows that one pair of identical cuts with different guarded
histories merges within a supported coalesced group. A genuine same-scalar
cross-occurrence substitution regression remains absent. This slice does not
establish global literal G8 or Milestone 5 acceptance.
