# Real completed-layer recovery evidence, 2026-10-14

## Result and scope

Both FLAT and HIER searches on the same OD06/N128 instance reached the 120-second exact-stage limit. Each retained a depth-1 checkpoint. Separate fresh bounded processes physically verified the saved feasible route and reconstructed the saved layer byte-for-byte from the ORIGINAL seed. Both recoveries passed and every process-group cleanup was verified.

The original two-stop feasible incumbent was unchanged. These results establish this bounded completed-layer recovery workflow on this instance. They do not establish exact optimization completion, a lexicographic gap, faster long-haul performance, arbitrary mid-layer resume, or full milestone acceptance.

See `summary.json` for numerical results, `ledger.json` for all four stages, and each `search_METHOD/` / `verify_METHOD/` directory for retained evidence. Both search timeouts remain in the record. Conservative charged CPU was 515.558138019 seconds across four stages, plus a 120-second preparation allowance, within the 1,160-second phase reservation. The allowance is not measured solver CPU or the full engineering cost. Limits were per-process virtual address space, not cgroup/aggregate-RSS hard enforcement.

## Provenance and privacy

`sanitized_manifest.json` is a deliberately NON-LAUNCHABLE public mirror of original approved manifest `fd5fcf3eb9b4ba461dc1f2c53b50652c3fb034a085c47760e3f4e65951817204`. Private workspace prefixes in receipts/manifests are replaced by `<WORKSPACE>`; the internal interpreter path is replaced by `<PYTHON_INTERPRETER>` while its digest is preserved. `ARTIFACT_INDEX.json` records original and public SHA-256 values, so formatting/path-redaction changes are not misrepresented as byte-identical raw receipts. Original unsanitized records were independently audited before publication.

Checkpoint and witness files are copied byte-for-byte; their content contains source identities and numerical state without private workspace paths. `source_snapshot/` contains the exact 157-file runtime source closure plus separately identifiable tiny-test support. The manifest's source map defines which files belonged to the measured runtime; test support must not be retroactively counted as runtime input. Graph Parquet files, compiler/native binaries and large external datasets are not embedded.

The prior durable-only phase was prepared but never run. Its manifest `78facc0cbf29ec594ae8f83dcd40b4a1cd7f1596aa6a83dc032a3b5da1b000cd` and preparation records remain preserved. This combined phase superseded its future execution rather than performing two redundant graph trials. Historical main-192 and supplementary-24 denominators and results are unchanged.

## Reproduce the tiny contract tests

Use the project's existing Python development environment with its dependencies installed. From the repository root:

```bash
E=results/milestone_5d/combined_checkpoint_20261014
PYTHONDONTWRITEBYTECODE=1 python "$E/source_snapshot/combined_checkpoint_trial/integration/test_sparse_layer_integration.py"
PYTHONDONTWRITEBYTECODE=1 python -OO "$E/source_snapshot/combined_checkpoint_trial/integration/test_sparse_layer_integration.py"
PYTHONDONTWRITEBYTECODE=1 python "$E/source_snapshot/combined_checkpoint_trial/real_trial/test_wrappers.py"
PYTHONDONTWRITEBYTECODE=1 python -OO "$E/source_snapshot/combined_checkpoint_trial/real_trial/test_wrappers.py"
PYTHONDONTWRITEBYTECODE=1 python "$E/source_snapshot/combined_checkpoint_trial/review/test_combined_recovery_orchestration.py"
PYTHONDONTWRITEBYTECODE=1 python -OO "$E/source_snapshot/combined_checkpoint_trial/review/test_combined_recovery_orchestration.py"
```

These run 11 dispatch tests, seven controller tests and two recovery-orchestration tests per mode. They do not load the production graph or silently run a large experiment. The orchestration test executes the actual worker recovery result/catch block with tiny real symbolic state; it is not a claim that the production admission gate accepts synthetic graphs.

The source snapshot is audit/reproduction material, not a ready-to-run new production benchmark. Re-running the real phase requires all original hash-matched graph/query/hierarchy/seed inputs, a newly reviewed execution manifest and bounded resource accounting. Do not execute the raw worker/controller merely by replacing public path placeholders.

## Native identity and interpretation

Actual loaded native source/options/compiler/binary are verified before normalizing only the binary output artifact path and matching compiler `-o` argument. All other identity remains bound. Recovery creates fresh providers and independently verifies physical routes, then reconstructs the original layer history rather than warm-starting with a later incumbent.

Stored primary lower bounds are conservative bounds only. A zero or coincident primary bound is not a lexicographic optimum certificate. Saved files always identify incomplete boundary evidence; final empty-layer completion is not inferred from them. The 120-second exact window includes checkpoint-session preparation, hashing, verification and persistence overhead.

The original bounded domain uses `H_ref=37`. HIER uses the declared sorted-ID binary Region tree; equivalence to the original production hierarchy is not claimed. Work after the last committed layer is recomputed, and partial Region queues are not restored.
