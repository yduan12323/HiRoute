# Independent immutable-real REF adapter

This is the independent reference implementation of the shared immutable
selected-leg serialization contract. It imports no `timecut5`, production
parser, routing engine, hierarchy, propagation, reduction, or bound helper.
Only this reference's own sequence/regime/LP/certificate kernel is reused.

## API

- `IndependentLegTable.from_bytes(raw, expected_sha256)` verifies an immutable
  native-export payload independently.
- `query_from_resolved_state(state, table)` maps the frozen C32 resolved-state
  schema, checking native baseline bits, exact SOC, and rational schedule windows.
- `estimate_real_regimes(query, table)` performs exact physical exclusions and
  returns counts/certificates before any continuous LP is expanded.
- `solve_real_case(query, table, keep_evidence=True, regime_limit=None)` is the
  tree-independent bounded oracle. An explicit regime limit prevents an LP run
  exceeding that preflight count; exceeding it returns unresolved.
- `replay_real_witness(query, table, semantic_sequence, charges)` recomputes every
  leg from the table and replays the original charge/service/max semantics.
- `verify_source_files(table, paths)` explicitly checks local source-file hashes;
  payload hash claims are not silently treated as source verification.

`query` uses the original exact scalar names, with `origin` and `destination`
set to physical road-anchor strings and no `edges` or `sites` overrides. Table
Site records alone determine semantic IDs, anchors and explicit effects.
The resolved-state mapper handles the separately frozen C32 field names.

## Identity, direction and arithmetic

The parser checks SHA256, duplicate JSON keys, containers and scalar types,
complete unique ordered pair rows, exact hex/integer-ratio agreement, explicit
unreachable rows, positive nonidentity totals, signed-zero identity values,
backend tie/direction policy, source/selection/hierarchy hashes and boolean
reachability transitivity. It imposes no numeric triangle inequality.

Every actual movement is one direct immutable lookup. The table is never
converted into graph edges, recomposed, or rerouted. Unequal-length equal-time
alternatives cannot replace the accepted selected length. Physical input
provenance is retained in every witness leg, including direction and original
binary64 hex fields. Exact rational values mean the frozen binary64 totals,
not exact real edge sums or associative native float evaluation.

Distinct co-attached Site IDs remain distinct semantic actions and accepted
pi entries. Their intervening movement uses the physical identity zero row.
Terminality is checked by destination road anchor, including co-attached aliases;
a Site whose text resembles the destination but is attached elsewhere remains
an ordinary Site. Collision-free internal origin/destination keys are only
computational aliases; they never replace semantic Site IDs in the plan key.

The oracle consumes no Region tree. The required hierarchy hash is provenance,
not an optimization input. Changing a mock hierarchy hash does not change the
reference result, while original hash verification remains a preparation gate.

## Exact physical exclusions

Before charging/max-regime expansion, the reference can certify:

1. An immediate pair is road-unreachable: exclude that extension subtree.
2. Current anchor cannot reach destination: boolean transitivity excludes all
   continuations from that prefix.
3. Initial inbound consumption exceeds E0−Emin: exclude the extension subtree.
4. Later inbound consumption exceeds Emax−Emin: exclude the extension subtree.
5. A direct terminal candidate exceeds Emax−Ereserve, or the exact E0−Ereserve
   allowance at depth zero: exclude only that terminal candidate.

The last rule never excludes its continuation subtree. A selected direct leg
can be energy-infeasible while a charging continuation is feasible because
selected actual lengths are not a metric. All inequalities are exact and strict;
equality stays admissible. Exclusion records retain prefix/Site/road-anchor IDs,
input hash, exact consumption/limit/excess, reason and subtree-vs-terminal scope.
No incumbent, production bound, Region, or LP is needed for these exclusions.

## Actual export preflight, not optimization

`audit_real_export.py` independently parsed all 16 native tables, verified 27
referenced source files, auxiliary exports/native binary/original-tree hashes,
shared pair equality, selected Site identity/anchor/effect preservation, all 32
frozen physical query states, exact baseline/window arithmetic and restriction
file hashes. Graph inputs were streaming-hashed, never loaded into graph objects.
The original hierarchy topology is not parsed or used by REF.

Evidence is in `results/milestone_5_reference/real_adapter/actual_export_preflight.json`.
The all-reachable pre-export bound is 455,507,376 regimes. Exact physical
exclusions leave 455,507,366, removing only 10 infeasible depth-zero terminal
candidates. These are counts, not measured real-solve runtime conclusions.
No real optimization has run, and no Stage C acceptance is claimed. A separately
reviewed resource plan or certified optimized-reference mode is required before
launching that workload. Frozen Site selections and H_ref=4 remain unchanged.

## Verification commands

```sh
PY=/workspace/shared/navigation_audit/venv-python311/bin/python
$PY -m pytest -q tests/test_reference5_real_adapter.py \
  tests/test_reference5_certificate_recovery.py tests/test_reference5.py
$PY -m validation.reference5.audit_real_export \
  --export-root /workspace/shared/navigation_audit/real_leg_export \
  --manifest-sha256 f846eb37219a34dea74aa9a79e7673b8cdae03ae281de189cb9b602a98ac380d \
  --selection-manifest /workspace/shared/navigation_audit/acceptance_populations/stage_c/concrete_selection/selection_manifest.json \
  --selection-sha256 0e39ad906c01e05b4a4b764b3270360e309c24d1ae67d7a2e3533b6dca8af06a \
  --production-root /workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut \
  --output /tmp/independent-real-preflight.json
```
