# Development-only DAG audit integration

Engine's explicit dag_audit option audits live assertions and the exact ordered
minimize objectives with the typed exporter. No parsed expressions enter the
solver. Original live model, objectives, action selectors, grounding, strict
support/attainment sequence, witness extraction and independent replay remain.
Default public solve/solve_real paths remain unchanged. The optional audit
requires a persistent output directory and the exporter's supported arithmetic
fragment; unsupported array formulas fail closed, with no legacy fallback.

Objective roots participate in the same DAG and symbol namespace as assertions,
including symbols used only in objectives. Exported minimize commands preserve
objective order. No check command is embedded; the receipt identifies the
corresponding live check and effective timeout. Future replay must explicitly
honor receipt identity and resource limits, not blindly execute a file.

Export, completion/payload verification, whole-file hashing and receipt I/O all
consume the existing end-to-end deadline. Timeout and started receipt are
persisted before check. An export, quota, hash, I/O or deadline failure returns
UNKNOWN without entering the solver. Completed UNKNOWN checks retain their
reason. A hard interruption can leave a started check, never a completed result.
Per-file node/byte limits and the external CPU/RSS/disk guards remain necessary.
A hash is integrity evidence, not proof against concurrent malicious rewriting.

Tiny gates compare all eight exact outcomes and strict-support/primary-face
traps while rejecting recursive solver.sexpr and parser entry. They check all
feasibility, optimization, better/face, attainment and lexicographic paths,
unchanged live assertions/objectives, objective-only symbols and exact rationals,
hash-bound complete audit files, started timeout receipts and precheck failures.
No full-size construction or solver query is admitted by this development stage.
