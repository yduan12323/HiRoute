# Completed-window receipt contract

`window_receipts.py` authenticates the execution of an explicitly reviewed
verifier. It is not fresh numerical replay. It never constructs a
`CheckedBundle` or `CheckedTrace`, runs an LP, or promotes a failed historical
runtime to success. The caller's current source policy is an independently
reviewed map of full public commits to source-inventory SHA256 values. A source
declared only inside evidence is not an allowlist.

Admission requires the independently retained actual successful `run_phase`
return, its consumed-byte SHA, matching result/decision/manifest pins, exact
`BATCH_REPLAY`, the fixed module command and reconstructed input context. It
authenticates every manifest file through `read_phase_result`, then consumes the
complete proof archive with bounded reads. Every model disposition binds its
full record/model bytes, original descriptor and source context. The adapter
recomputes only checked-result aggregation and segment summaries. Complete
spans must match the independently admitted original catalogue exactly.

The return must have been retained from a trusted invocation of the reviewed
controller/verifier in an independently verified interpreter, checkout and
module environment. A genuine `run_phase` completion from an arbitrary program,
or matching source labels and command strings alone, does not satisfy this
precondition. Runtime receipts bind bytes and resources; they are not code
execution attestation. The fixed seed's invocation is independently reviewed;
new generic receipts are registered by the reviewed controller after its
current interpreter, checkout/module origins and loaded source checks.

The fixed seed is the successful `bf61640ceaf6dcafe28f7ab12d95e94c8f19bb93`
continuation, covering blocks 0, 1352, 2535 and 2687. Its 1,022 retained references
require the original failed archive `e7371f1ec32492ff05a05907b52261d9d10ab20112be9222f5aad1d3eb8360cc`
(756,356 bytes), original selection/summary and pinned cold receipt. Each old row
reference is checked against the consumed full old archive. The old runtime
stays failed; the successful reviewed continuation supplies the certificate
checking authority.

`ReceiptScope` holds an immutable source-authenticated population/catalogue,
distinct from mathematical checked objects. The controller can bootstrap it
with `scope_from_seed` or `scope_from_registered_registry`; workers instead pass
their genuine `AdmittedSuffixPopulation`, which additionally regenerates the
selected descriptors. `admit_seed_resume` returns a `CheckedRegistry`;
`admit_new_completed_window` returns a `CheckedWindowReceipt`. Constructors are
protected. `extend_registry` admits a disjoint new receipt.

The registry contains entry/source/runtime/input/dependency pins, exact block
spans, block-summary digests and segment spans/digests. Full certificates and
aggregate bodies remain in their pinned window archives/summaries. The registry
is capped at 16 MiB. `write_registry` creates a fresh canonical JSON+LF file,
checks its consumed bytes, and returns a registration receipt. The caller must
independently retain and pin that actual return after the function returns;
reconstructing one after interruption or trusting only a registry hash is not
admission.

`load_scheduling_registry` needs that independent registration return and pin.
It authenticates the compact metadata and catalogue for scheduling without
reading historical certificate arrays. Its `block_reports()` is unavailable.
Before final aggregation, `reconcile_registry` authenticates each unique entry
and upstream phase once, retains the complete original replay/logical proof
graph, and shares a bounded dependency cache. The runtime's mandatory full
manifest pass is preserved; archive consumption also verifies its consumed
compressed bytes. The resulting checked registry exposes detached block
reports. It still reports `fresh_numerical_replay=False` and does not claim query
optimality, complete population coverage, or literal G8 closure.

Data closure also consumes every file in the historical plan's pinned physical
input manifest: immutable leg table, original tree, export manifest, resolved
states, selection certificate, tree restriction and optional reference. The
replay plan must bind the same map. Those repository-relative files must remain
available in the trusted checkout; deleting a required table or export input
fails cold reconciliation. Historical source-code files are not data inputs
and are not reopened under their obsolete code pins. Per-entry decoded
selections/catalogues/documents are released after constructing each compact
receipt; the shared cache keeps pins and admitted summaries.

Every I/O path accepts the caller's absolute finite deadline and resource
callback. No callback, arbitrary flag, hash-only JSON or foreign population can
construct a checked receipt. All returned dictionaries are detached copies.
Tests use tiny genuine family/hand-certificate fixtures and explicitly fake
completed-source histories, with no native solver or real C01 execution.
