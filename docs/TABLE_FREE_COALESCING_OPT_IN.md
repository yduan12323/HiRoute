# Optional table-free coalescing integration

This is the existing `exact-adjacent-cut-coalescing-v1` representation applied
through `TableFreeRealProblem`; there is no new compression or pruning rule.
The existing synthetic and immutable-table entry points and production defaults
are unchanged. The new entry points are in `timecut5.coalesced_solver`:

- `table_free_problem(..., coalescing=False)` builds the selected adapter.
- `solve_bounded_table_free(..., coalescing=False)` runs bounded FLAT.
- `solve_hierarchical_table_free(..., root, coalescing=False)` runs bounded HIER
  with the caller's admitted Region tree, never a silently substituted tree.

All require the original origin, destination, Site catalog binding and native
selected-road provider. These are bounded diagnostic solver results: this module
neither admits a seed/bound nor claims independent REF correctness or unbounded
completion. The coalescing flag must be an actual boolean. OFF constructs the
unchanged `TableFreeRealProblem` and records zero coalescing work. ON uses the
same pre-/post-transition and dominance-reduction hooks as the existing optional
coalesced solver. Full physical state, rho, pi, affine time and chi must agree;
only connected exact unions merge. Open-open holes remain holes. Witness calls
continue through the original guarded parents, including inherited crops.
Known proof families are rejected before processing; certified recorded lineage
is not supported by this entry point.

## DEV runner integration and recovery

Both solver functions pass through `checkpoint_hook` and `incumbent_hook`.
FLAT also passes `singleton_bound`; HIER passes `bound_provider` and `incumbent`.
Both pass `verified_primary_upper` and `terminal_target_routing` unchanged.
Caller admission requirements for these objects have not been relaxed.

An incumbent callback should independently replay the proposed witness with a
fresh replay provider and `SparseSeedCatalog`/`replay_sparse_seed`, then atomically
persist its sequence, charge quantities, full key, and source bindings. A budget
stop can thus retain a feasible witness without claiming an exact optimum.
`ExactLayerReplay` remains same-engine reconstruction, not serialized frontier
restoration. Its source manifest includes the coalescing modules. The caller's
external policy/runtime/query hashes must bind the coalescing flag, dominance,
stop bound, routing/bound choices, and the rest of the run configuration. Never
reuse an OFF checkpoint as an ON checkpoint or pool their timing results.

## Finite test coverage

`test_table_free_coalesced_solver.py` uses only a three-node directed road graph,
source-bound native selected-edge labels, and separate fresh providers for the
independent physical replay. The FLAT/HIER × coalescing OFF/ON × dominance
OFF/ON matrix compares mathematical status, attained primary/secondary faces,
unattained component, and the complete executable key (when one exists).
Cases include attained charging, equal-primary action tie, primary unattained
strict charging, secondary unattained schedule plateau, attained plateau with
minimum total charge, and infeasibility. No fictitious executable key is created
for an unattained infimum.

Additional tests check every touching endpoint combination, distinct metadata,
original parent guards and cropped physical-prefix replay, default OFF behavior,
known-lineage rejection, and incumbent/checkpoint hooks in both engines and both
representation modes. A stop at depth 1 retains an independently replayed
incumbent and resumes to identical complete output via `ExactLayerReplay`.
A further sixteen-mode matrix combines both engines, both dominance settings,
both representations, and onward ALT OFF/ON, using strictly positive certified
onward potentials, real Region/singleton bound providers, a verified primary
upper bound, and independently replayed incumbent hooks.
The existing exact-coalescing regression suite also checks exhaustive endpoint
arrangements and deterministic random symbolic unions.

Run independently of historical timing experiments:

```sh
PYTHONPATH=src python -m pytest -q \
  tests/m5d_recovery/test_table_free_coalesced_solver.py \
  tests/test_coalesced_solver.py tests/test_time_cut_coalescing.py
```

This is functionality evidence only. It is not a large-road DEV performance gate,
an M5 correctness closure, a holdout result, or evidence of a runtime improvement.
