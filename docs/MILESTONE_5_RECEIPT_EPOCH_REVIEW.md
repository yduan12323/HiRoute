# Private receipt epoch: code review only

The D0 driver stopped on window021's independent historical reconciliation
deadline. Window020 remains the last fully reconciled prefix; window021's
successful numerical execution, registration and immutable evidence remain
available. This change does not resume either window or launch window022.

`tools/receipt_epoch` is a separately pinned metadata tool. The standard
suffix_window controller, receipt verifier, numerical resource contract and
final collector are unchanged. There is no real-series numerical launcher or
disk-cache recovery entry point in this patch. Real admission needs a separate
review of the owning launcher, exact code inventory and original interpreter /
checkout boundary. Synthetic test results cannot provide that admission.

## Authority and transactions

Establish starts a new process epoch with independently retained actual runtime,
registration and registry pins. A complete ordinary registered prefix must pass
the existing full `reconcile_registry`, inside the same fresh 180-second phase.
The newest actual runtime must be precisely that prefix's last entry. The exact
source-policy allowlist is frozen. All original input, source, policy, worker CPU,
population and variant bindings are fixed for the epoch. The parent supplies a
reviewed complete source-file pinset, including the separate tool package.
Pins supplied by an untrusted file or a reconstructed caller return do not
attest execution; the existing verifier requires a trusted owning caller.

The epoch stores only private scope, compact checked receipts/registry, actual
caller pointers, hashes, and file/directory identities. Each prepare streams the
bytes of every unique historical file again, checks the full namespace and
identities, and returns one process-specific, single-use pending token for the
ordinary first32/max8192 selector. It does not construct or launch an LP.

Cold first rehashes historical bytes. The actual new registry must preserve the
entire ordered old prefix and append exactly one entry. Its actual caller pins,
paths, request inputs, original registry pointers, source/policy and resources
must match the pending window. The new entry goes through the unmodified full
`admit_new_completed_window`. The new registry must equal the old checked
registry plus this receipt, including exact canonical bytes. A final continuity
fence precedes a private state replacement. Any exception before or after that
replacement destroys the epoch; a lost reply cannot be retried in that process.

## Closure and safe filesystem consumption

Entry.dependencies alone is insufficient. The closure includes explicit proof,
catalogue, summary, selection and actual return anchors; complete closed window,
replay, logical-count and original capture phase trees; retained D1 seed attempt
trees when the known evidence-directory contract applies; every retained
dependency; and the complete reviewed source/tool directories. The original
capture request is derived only from an independently pinned replay request.
Establish also cold-verifies that capture's actual runtime return. Unknown
upstream or recovery receipt contracts fail closed, rather than silently
dropping dependencies.

Every closed tree includes journal, writer lock, spool, control and non-manifest
files. Hashing streams actual bytes with a bounded buffer and rejects hardlink
aliases, symlinks, special files, changed/replaced files, and short reads. All
path components are opened without following links. Complete directory names
and identities are compared before/after; shared ancestors retain stable
device/inode/mode/owner, allowing a new sibling window without allowing an
ancestor substitution. File identities include ctime as well as mtime, owner,
mode, link count, size, device and inode. Metadata continuity is an end fence
after an actual byte pass, never a substitute for that pass. Snapshot identity
is intentionally stricter than identical content restored into a new inode.

## Process and IPC boundaries

The service has a hard 2GiB address-space ceiling. Every operation gets a fresh,
finite, at-most-180-second monotonic deadline. The parent watchdog bounds pipe
writes and reads with the same deadline and destroys only the metadata child on
timeout or uncertain delivery. The service contains no numerical launcher.
There are no sockets or disk-state import. Pipe frames are capped at 4MiB,
strict JSON, and bound to a private process nonce plus a strictly increasing
sequence. Process death, EOF, malformed frames, stale tokens and reply failures
invalidate the in-memory state.

The owning Parent requires its trusted Python interpreter and uses a new empty
pycache_prefix with -B, so imports cannot reuse shared old bytecode. The actual
tool and verifier import origins are separate pins. The metadata-only CLI
loads the tool under a private package name and the original
verifier through a source loader which executes exactly safely consumed,
independently pinned bytes. Neither checkout is added to an unfiltered Python
path; unknown/native project imports are refused. Labels or binding.ROOT
reassignment are insufficient. No tool is connected to real evidence here.

Pause is explicit: if a window is pending, pause permits its numerical/registration
and cold boundary to finish, then prevents another prepare. No stop signal is
sent to a valid numerical task. A future owning launcher must also respect this
boundary and cannot reconstruct pending authority after a sidecar interruption.

Recovery must establish a fixed fully reconciled prefix from zero, then admit
retained successful later windows one at a time as new entries, using their
actual old returns without rerunning numerical work. Every establish/prepare/
cold includes all of its work in one original 180-second phase; splitting a
failed phase to extend its time is prohibited. Prefix017 followed by18–21 is a
future admission proposal, not an execution performed by these tests.

The final collector remains a new process doing independent full reconciliation.
Epoch reports do not exempt any collector inputs and confer neither query
optimum certification nor G8 closure. Full-history byte hashing remains linear
in retained evidence size; whether it fits the real phase limit is unmeasured.
Cold currently reads historical bytes once in rehash and again while capturing
the full candidate closure. Only the new window's archive receives semantic
admission in incremental cold; the repeated byte pass is an additional I/O cost,
not an exemption from historical authentication.

## Validation boundaries

Tests exercise actual safe streaming hashes, namespace substitutions/aliases,
restored mtime, in-read modification, per-phase invalidation, single-use tokens,
pause, process death and watchdog timeout. Incremental admission uses a genuine
small family/population with six charging bands and canonical blocks; only
its completed-source dispositions/upstream runtime boundary are synthetic, as
in the existing receipt fixtures. The old archive is not decoded again in
prepare or incremental cold. The independent full verifier still rejects old
archive mutation. Normal and -OO tests must both pass; real D0/D1 evidence is
never copied into the fixture or exported to the Mac.

## Metadata-only CLI and independent source contract

Run the absolute `tools/receipt_epoch/driver.py` with the selected Python's
`-I -B` flags. There are three operations: `fingerprint`,
`authenticate-retained`, and the owning parent's framed `private-worker`.
There is no numerical/series/collector command.

Every operation requires `--tool-root`, `--tool-commit`, `--verifier-root`,
and `--verifier-commit`. Fingerprint compares safe live Python bytes with the
exact Git blobs and reports the following independent admission facts:
`tool_source_sha`, `verifier_source_sha` (the original119-file census contract),
`verifier_import_sha` (the additional complete source import namespace),
`python_realpath`, and `python_sha`. Fingerprint is an observation, not approval.

Authenticate-retained/private-worker additionally require those five facts as
`--tool-source-sha`, `--verifier-source-sha`, `--verifier-import-sha`,
`--python-realpath`, and `--python-sha`. The worker rechecks the supplied contract,
acknowledges its digest in the process handshake, and checks both HEADs,
interpreter identity/bytes, and actual verifier import origin at every phase.
The establish payload's complete code pinset must equal that independently
bound import inventory; a caller cannot substitute a narrower code closure.
The historical numerical source-policy allowlist is unchanged; the tool's own
version is a separate attestation, not an approved numerical executor.

Authenticate-retained also requires `--policy FILE --policy-sha SHA256`,
`--prefix-handoff FILE --prefix-handoff-sha SHA256`, and an exclusive new
`--audit-log FILE`. The pinned prefix handoff supplies actual caller pointers
only; its previous passed/status fields do not restore epoch authority.
Initialization always performs a new full reconcile under one180-second phase.
An optional repeatable `--retained-window-return FILE SHA256` supplies each
independently retained original controller's registered stdout. Each retained
window gets one prepare and one complete new-entry cold admission, using its
actual outputs without any LP rerun. Final pause/close stops at the safe boundary.
Failures destroy the session with no automatic retry. All operations leave
historical input/return/evidence files unchanged; only the new capped audit log
is written.

Uncovered by synthetic tests: real prefix017 plus18–21 admission, native project
modules in an actual metadata import graph (they are deliberately refused), real closure
hash throughput within180 seconds, and real owning-launcher/numerical boundary
integration. These require independent review before execution. No real prefix
initialization or retained real-window admission is performed by this patch.

## Recorded synthetic validation

The final isolated Linux Python3.11.16 revision, restricted to two actual CPU
IDs with taskset, passed 332 unittest cases without skips in both normal
(87.488 seconds) and `-OO` (88.579 seconds) modes. The 23 selected
modules cover receipt epoch/origin, standard window receipts/runner/selector,
independent collector/query/fold/empty occurrences, D1 recovery receipts/runner/
core/plan, variant scope, D0 bootstrap, one-block limits, archive transport,
occurrence joins, calibration, census and indexed population/context. The
source-bound epoch/origin subset has 29 tests. These are code regressions,
not real-population acceptance results.

The pure metadata receipt fixtures declare six distinct CPU IDs. They never
launch a phase or assert host affinity, so all metadata checks also run on
small CI runners. Actual runtime preflight and production masks are unchanged.
The D1 recovery test restores its saved fixture CPU list after an intentional
alias mutation, rather than substituting the host's shorter affinity list.

The original 326-case logs, initial 28-case epoch log, and an intermediate
332-case failure logs are retained alongside the final runs under the server's
`/tmp/hiroute-epoch-review-xcb3rlj8`. The intermediate failure was a test's error
message expectation after adding the package-namespace rejection; the revised
assertion accepts both valid origin rejection paths. The earlier unrestricted
normal/-OO 332-case passes remain in final-v2 logs. A two-CPU final-v3 run
exposed the D1 fixture restoration issue described above; its failure is kept.
Final log files are `review-validation.final-v4.two-cpu.normal.log` and
`review-validation.final-v4.two-cpu.optimized.log`. Their metadata file records full
argv, tested source SHA256 pins, elapsed time and log SHA256 hashes. Publication
copies these test logs to a new persistent review directory on the server;
no server experiment archive is downloaded to the Mac.

CI runs the existing isolated-wheel regression and the bootstrap/epoch/receipt/
collector synthetic groups in normal and `-OO`. Each group retains the existing
120-second subprocess cap and the workflow's existing 10-minute cap. No real
series is invoked and no resource cap is increased.
