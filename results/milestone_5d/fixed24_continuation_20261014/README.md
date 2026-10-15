# Fixed24 continuation: immutable terminal accounting snapshot

The 24 frozen rows contain **23 clean wall timeouts and one infrastructure-unknown interruption**, with zero recorded exact results and zero comparable exact pairs. All recorded last phases are `seed_started`. This is complete outcome accounting, not 24 numerical solves, an infeasibility certificate, a speedup result, or M5-D acceptance.

- [Public report](public_report.json): exact approved bytes, SHA-256 `66d000910bad4b4fd39368f9483eb380523e54c238e29867a3330d2b7805333a`.
- [Receipt reconciliation](public_receipt_audit.json): exact approved bytes, SHA-256 `37e2938cb158e3a94847d6d4b1c11aa9e29151743b86620c467842721f254588`.
- [Public provenance](provenance.json): hash-bound public artifacts and reproduction limits.
- [Original report generator](generator/build_report.py) and [historical raw-receipt auditor](generator/audit_final_report.py): unchanged source bytes matching the hashes in the respective evidence records.

The report and audit were frozen before the combined checkpoint trial completed. Their references to that separate trial being pending/ongoing describe their snapshot time; they are not the final checkpoint disposition. See the separate combined-checkpoint evidence and final milestone report. Neither that trial nor the original 192-row matrix is included in this 24-row denominator.

## Reproduce public checks

From the repository root, using only Python's standard library:

    python results/milestone_5d/fixed24_continuation_20261014/verify_public_bundle.py
    python -m unittest discover -s results/milestone_5d/fixed24_continuation_20261014 -p 'test_public_bundle.py' -v
    python -OO -m unittest discover -s results/milestone_5d/fixed24_continuation_20261014 -p 'test_public_bundle.py' -v

These validate exact public/source hashes, the fixed denominator, public receipt-identity coverage, accounting arithmetic and conservative claim boundaries. They do not independently rerun private raw-receipt reconciliation. Synthetic unit tests are not numerical experiment evidence.

## Reproduce the original report with authorized private inputs

The exact report generator accepts `--root INPUT_ROOT --output NEW_OUTPUT --terminal`. `INPUT_ROOT` must contain the five original manifest/ledger snapshots listed with SHA-256 in the report's `provenance.source_snapshot_sha256`. Preserve their relative names. Output must be new; the generated report is deterministic and includes the generator's own source hash. Exact-byte reproduction from the retained snapshots was checked during bundle preparation.

The generator also copies raw inputs into its output. Those raw snapshots, host paths and invocation arguments are intentionally excluded from this public bundle. Their absence means a public-only reader can verify the published projection and hash anchors but cannot recreate original private receipts from hashes.

The archived auditor retains its original workspace-relative layout and `assert` checks for source-hash fidelity. It is a historical source artifact, not a portable public-only entrypoint, and must not be executed with optimized Python. The portable public validator above uses explicit exceptions and is tested with normal and `-OO` Python.

## Accounting and limitations

Known-row conservative charges total 13,789.5577064229998 seconds. Adding the unknown row's 670-second reservation and 480 seconds of preparation allocations gives 14,939.5577064229998 conservative-accounted seconds. This is not unique measured CPU: wait4 accounting may double-count descendants, and the unknown-row/preparation amounts are allocations. Do not add the overlapping original and recovery planning reservations. Historical 48-hour host-tail accounting remains unresolved.

The unknown row is not silently replaced or reclassified as a timeout. Previous-namespace cleanup remains unknown. Memory enforcement is per-process virtual address space, not aggregate RSS. No sequential feasible outcome or independently persisted sequential transportation witness was produced; no transportation-benefit or optimality claim is supported.
