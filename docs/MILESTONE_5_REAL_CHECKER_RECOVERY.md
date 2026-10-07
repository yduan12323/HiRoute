# Reconstructed independent real checker

This is new, reviewable source reconstructed above published PR7. The missing
historical `real5_v2` source was not recovered, and no old source hash is accepted
as identifying this implementation. No real C01/population capture, LP run,
external routing acceptance, or literal G8 closure is claimed.

`prepare_real_case(query, expected_query_sha256, table_bytes,
expected_table_sha256, original_tree_bytes, expected_tree_sha256)` returns an
immutable `TrustedRealCase`. Query identity is SHA256 of canonical JSON; the
other two pins bind exact input bytes. Its `case_snapshot()` and
`source_snapshot()` return detached dictionaries. `physics`, `regions`, and
`table` retain immutable values. Source-file hash declarations are provenance
claims, separately distinguishable from a verified payload identity.

`verify_bundle(bundle, trusted_case)` and
`verify_trace(trace, bundle_or_checked, trusted_case)` preserve the published
`validation.family5.checker.CheckedBundle` and
`validation.trace5.checker.CheckedTrace` class identities. Witness checking,
receipt checking, and exact reconstruction reuse the published mathematical
checker. The baseline keeps its detached canonical-JSON copies and hashing.
The internal `_verify_bundle(bundle, configured_case_dict, physics)` is the
published verifier body with only `_Physics.build` removed for explicit physics
injection; the public wrapper additionally checks physical state provenance.

The immutable-leg parser is adapted directly from the independently authored
published `validation/reference5/real_input.py`, replacing its package-local
error import. Original effect-array order is preserved to match the source
query. Importing this package does not import that package, its optimizer,
production search, numerical packages, or an LP solver. Immutable directed
time/actual-length pairs are never interpreted as graph edges or rerouted.
Their canonical binary64 hex and exact ratios are retained, including identity
legs for distinct coattached Sites.

The original tree's known construction annotations (`branch_factor`, `capacity`,
`mechanism`, Region `depth`, `early_leaf_reason`, and `road_node_count`) are
supported and type checked. Declared depth and branch width must agree with the
topology. These fields remain bound by the complete original-tree hash; graph
construction and road-node counts are not independently rederived here.

Original Region IDs, member order, child order and empty children survive exact
source-tree validation and restriction. Each original internal Region must be
a disjoint exact partition of its children; disconnected or cyclic Regions,
duplicate indices and boolean indices are rejected. The real trace mixin uses
the published grammar with set-based root coverage, while preserving the
trusted original order. Its bound is minimum selected incoming time plus
overhead/service and zero onward time. A missing direct terminal leg does not
exclude a reachable next action. Terminal policy uses physical anchors.

Physical location is derived recursively from provenance, not guessed from
the last Site name. A stop produces `(physical anchor, raw Site phase)`;
retag consumes that phase exactly once. Restrict/select preserve the phase,
and guarded unions require compatible phases. Comparison inputs with the same
wire state must also share the same derived physical anchor; different raw/road
phases at that same anchor remain legal. Drive/stop and even empty-image
physical batches require the correct physical anchor. A Site ID equal to its
own anchor permits legitimate zero identities; equality with another anchor
cannot create a new location. This closes the raw-Site/road-anchor collision
that textual-state-only checks miss.

The real query freeze uses `family5-exact-real-node-query-v2`, `real_input`, and
`onward_travel_lower_bound: "0"`. Leg context retains exact time, actual length,
consumption, reachability, binary64 hex, direction and immutable table SHA256.
This is a reconstructed source boundary, not a historical population artifact.

Published source references used for reconstruction:

- `validation/family5/checker.py`: `f6c4494b879752352f551a3b4ef6d6e53bf10ea7884bc6774ad002230469c900`
- `validation/trace5/checker.py`: `d35f1e9841eeac5d53dfdaf01b5f716b0141e95666354c55d4cb1432372e7b91`
- `validation/reference5/real_input.py`: `6e6c6c028da87bd23d31407a35fae324980c56318999873d0313534b17c64abb`

Validation uses only the five published mock cases in
`results/milestone_5_real_leg_contract/mock_solver_cases.json` plus small
adversarial variants. Both dominance modes replay. A separate consumer process
blocks production, reference optimizer, suffix optimizer, NumPy and SciPy
imports. The focused tests also demonstrate attacks that pass the reused
textual-state mathematics but fail the extra provenance/phase check, and a
physically valid same-final-key witness rejected by an inherited energy guard.

Run with Python 3.11:

```sh
PYTHONPATH=src:. python3.11 -m unittest tests.test_recovered_real_family -v
```

The additive `real5_v2.coalesced.verify_coalesced_trace` composes this trusted
physical/tree mixin with the reconstructed independent compact grammar. All five
published mock cases in both dominance modes retain their exact terminal results;
original member order and empty Regions are checked. Four focused integration
tests cover the ten runs, altered compact/guard/tree/family evidence and an
independent consumer subprocess with production/reference/LP imports blocked.
The composition still returns the exact published checked-object classes and
makes no real-population or suffix-optimization claim.

`real5_v2.shared_replay` is a storage adapter with the same mathematical replay
and exact query wire values. It streams the transitive-ancestry and population
hashes, then freezes repeated query subtrees with shared ownership. The full-copy
`coalesced` implementation remains the reference. Ten mock runs compare every
summary coordinate (apart from elapsed time), every expanded query and every
legacy query digest. No parent, guard, event or callback is omitted. This adapter
reduces avoidable duplication; it does not promise a real-case memory/time bound.
