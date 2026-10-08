# Successful generic recovery receipts

`window_recovery_receipts.admit_completed_recovery` accepts the same admitted
population or authenticated scheduling scope used by `window_receipts`, plus
`recovery_attempt`, `recovery_return`, `recovery_return_sha`,
`recovery_result_sha`, `recovery_decision_sha`, and `recovery_manifest_sha`.
The result is the existing protected `CheckedWindowReceipt` type, with module
`suffix_window_recovery`. It can extend an existing `CheckedRegistry`; the
ordinary `suffix_window` scheduler then uses the newly completed whole blocks.
The current source commit/inventory must be independently reviewed. No source
hash for a future run is supplied by this code.

Admission requires the actual separately retained successful current runtime
return, the unchanged BATCH_REPLAY profile, the reviewed controller/interpreter
origin, canonical source policy, exact original first outstanding window, exact
base registry and registration return, all fresh worker evidence, and the
bounded canonical recovery plan. The recovery plan retains failed predecessors
as historical data. No failed predecessor is passed to `read_phase_result`,
reconstructed as a successful return, or accepted because of a completion flag.
Upstream structural/logical successful phases retain their existing admission
requirements.

Every ancestor proof stream is consumed at its independently supplied compressed
hash and size. Its full certificate rows are checked for original descriptor,
model, result, verification, candidate input, and source-context consistency.
Chronological retained references must match the exact full leaf row index and
SHA256, archive pin and source context; references cannot resolve to references,
future archives, missing proofs, foreign models or duplicate dispositions. Each
ancestor cold receipt and the current cold receipt must match that complete
closure. Full losing certificates remain dependencies, even though only compact
row bindings are held in controller memory.

The current archive must contain the exact retained/new complement with all
blocks complete, matching aggregates and physical winner receipts. Its final
transport accounts for the exact new model input bytes. Failed historical
transport may have submitted bytes beyond observed terminal outcomes, bounded
by the same input cap; an accounted transport requires equality. A zero-new-job
recovery has `recovery_mode: exact-only` and `transport: null`; fabricated empty
candidate transport is rejected. Same-source retries are allowed because source
identity is not an attempt identifier.

This is source-bound authentication of a reviewed execution, not another
numerical replay or cryptographic code attestation. A trusted independently
observed controller/environment invocation remains a requirement. Merely
manufacturing matching labels and a `run_phase` success cannot establish that
external trust. After receipt admission, independently retain the actual return
from `write_registry` before admitting the new registry for future scheduling.
A file written before a late failure does not substitute for that return.

All existing `block_resume` and `suffix_window` command parsing, optional-null
contexts, schemas and receipt bytes are unchanged. The old module receives only
a narrow source-module allowance and additive recovery dispatch. Tests use tiny
hand certificates and explicit synthetic reviewed-source protocol fixtures; no
real C01 archive, optimizer, server execution or final collector is involved.
