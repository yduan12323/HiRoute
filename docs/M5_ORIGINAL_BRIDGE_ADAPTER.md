# Original Shandong bridge adapter

The branch contains a fail-closed adapter for the original Shandong N8 REF and its FLAT/HIER follow-up stages. The adapter code is **not yet runnable or accepted**. Its current disposition is **UNKNOWN / NOT_RUN_DEPENDENCY**: no bridge claim or worker attempt was made.

## Implemented adapter path

The parent derives the run identity from the root-validated continuation admission and its bound parent waited-round receipt. It validates the original N8 common input, manifest, SOC 0.30, seed-derived depth, configured interpreter, wrapper identity, and a per-invocation freeze binding the inputs, source identity, interpreter, accounting snapshot, run root, and method order.

Before the REF claim, the parent validates a fixed master accounting snapshot and exclusive global ledger. The claim is create-once under the authoritative root derived from the trusted continuation. The isolated worker rechecks the invocation freeze, wrapper and interpreter digests, trusted recovery configuration, source identity, and the unchanged M6 root gate. REF status and reason are saved before authentication failure is raised, so an incomplete result remains visible in the report.

After authenticated REF success, code is wired to run the original N8 FLAT and HIER methods sequentially, each under an outer 300-second CPU and wall limit. The original M6 1200-second phase gate is not changed. Only an early successful method result proceeds to the fresh 120-second verifier. A 300-second external limit is reported as incomplete and is not translated into the legacy 1200-second timeout state. Method results are compared against the authenticated REF full key.

The tools wheel builder records hashes for the two bridge wrappers. The worker command uses isolated Python mode (-I) and does not inject PYTHONPATH or mutate sys.path.

## Remaining fail-closed blockers

The current accounting file cannot independently prove that its declared inventory is exhaustive. A caller-provided closed_world flag or empty unresolved list is not an external completeness authority. Some historical ledger end rows also lack receipt digests; those rows must remain unchanged and require a verifiable sidecar binding to their original supervisor receipts. Until both the receipt lineage and an authoritative source inventory are available, the adapter must reject admission.

The installed layout also remains unresolved. The tools wheel currently packages an experiments tree, while the adapter requires the trusted recovery module's root to equal the original source checkout. The -I worker must import that exact, identity-checked source through a supported installation layout before any claim is created. The current code does not yet establish that compatibility. This is an implementation/install-layout blocker, not evidence that the historical binding is absent.

No accounting, receipt sidecar, or installation provenance has been fabricated to make these checks pass. The original Shandong binding remains unconfirmed in this execution context. No claim, REF, FLAT, or HIER worker was started.

## Review and verification status

Focused tests now cover ledger closure and cleanup, caller-declared accounting rejection, amount tampering, continuation-derived claim identity, wrapper drift, isolated worker command bindings, 300-second timeout classification, immutable invocation freezes, worker argument binding, and preservation of incomplete REF status. **These tests have not been run** because no certified global test budget was available. No numerical run, CI run, or holdout was performed.

The adapter is therefore submitted as implementation in progress, not as evidence of completed original-Shandong validation.