# Fixed-timeout observation gate assessment

## Existing rule, unchanged

`ordered_evidence.compare_prefix` requires both worker-written terminal statuses to declare `matching_complete`, with no partial tail or pending request, before it allows its matched-speed claim. The admission policy separately permits authenticated exact-timeout prefixes and clean committed caps to proceed to independent physical replay. Neither continuation condition makes the whole-comparison gate true.

The worker publishes ordinary ordered status only when its observer closes. The deliberately enforced exact-wall timeout uses SIGKILL, which cannot execute that close. Even if the final recorded request happened to complete just before SIGKILL, absence of terminal status keeps the formal gate false. A committed cap status also deliberately has `matching_complete=false`. Natural worker completion before the time limit can satisfy the gate, so impossibility is conditional on termination by the planned forced timeout, rather than a claim about every run.

This is a sound conservative completeness gate, but it does not establish a useful complete-log result for a forced-timeout experiment. Repeating the same timed design is not a remedy. V8 retains the frozen rule and reports its result without reinterpretation. Authenticated completed common-prefix observations remain separately meaningful.

## Distinct evidence claims

1. Completed prefix: each paired begin/completion has authenticated order, request semantics, selected labels and edge-chain identity. Its measured call duration is complete. Equal requests up to the first divergence or shorter completed frontier can be described.
2. Outstanding recorded request: a begin without its completion is censored in the record. It does not prove that the worker was still executing that request when killed. Later progress may establish that additional work occurred beyond the recording frontier.
3. Committed cap: a validated v3 status and matching commit bind the exact event frontier, pending identity, cap threshold and configuration. This establishes a declared recording cap. It does not establish complete diagnostics or authorize a whole-comparison timing claim.
4. Status absent: authenticated controller timeout and cleanup establish how the owned process ended, while the ordered log's recording-stop reason remains unknown. An unpersisted observation I/O error is also possible. Do not infer clean cap or uninterrupted recording from status absence.
5. Corrupt, malformed or uncommitted status: fail the corresponding integrity gate. An authenticated process timeout must not repair bad bytes or turn a publication failure into a clean cap.

## Prospective parent-finalized censoring proposal

A future, separately reviewed candidate could have the controller publish an immutable observation-finalization record only after it has established that its owned worker is dead and cleanup is complete. Bind the exact source closure, stage identity, admission and reservation, native build/configuration, exact-start marker, authoritative stop request/kill/wait receipt, full final file hashes and byte lengths, parser-validated chain frontier, all terminal/commit files and any incomplete tail bytes. Record the last fully completed request and a separate pending request, rather than fabricating a completion or duration.

This parent record certifies the final captured bytes and process termination, not unseen worker state or the precise instant observation stopped. Classify at least complete natural close, committed clean cap, authenticated process cutoff with recording cause unknown, and corrupt/publication-failed evidence. If the future experiment needs the stronger claim that recording remained active until process cutoff, add explicit fail-closed observer health/recording-state transitions and controller-visible publication-error notification; design and test that protocol separately. A missing or stale notification cannot silently stand in for healthy recording.

Predeclare a distinct finite-prefix estimand: compare only semantically equal, fully completed requests common to both arms, grouped by phase and role; exclude the pending request and all unobserved suffix. Keep inclusive, wrapper and guarded-native durations separate because they overlap. State the exact count, exact-time coverage and first divergence. Such a prospective prefix gate need not assert whole-run completeness, equal work, unbiased censoring, pure native CPU, or general speed superiority. Keep independent fresh physical replay and resource/cleanup gates unchanged.

No implementation, numerical rerun, retroactive criterion change or new admission is made by this document.
