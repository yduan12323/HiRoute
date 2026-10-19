# Disclosed recovered-history new-map validation (held)

This portable protocol is frozen before actual OD selection. It is intended for
new-map correctness and performance validation with recovered historical
exclusions and an explicit incomplete-registry gap list. It does not claim a
strict independent holdout. The default strict selection path remains held and
requires a complete registry. No real execution is enabled by this commit.

The recovered manifest, physical worker, independent REF, queue and generation
modules derive from the audited source snapshot 9598021. Only source is restored;
no historical result, actual map or registry is imported into Git. Historical
mock entrypoints and real entry guards remain closed. Their prior documentation
and source comments describe the historical implementation, not current approval.

`recovery_protocol.protocol()` is the portable exact design: six groups, 24 main
plus six N8 domains, 156 operational slots, 60 method rows and six REF slots. All
failures and exhausted slots remain; there is no replacement or favorable retry.
The original physical model, original capability-balanced 128-Site recipe,
original seed and full floor(Jseed/900) depth are retained without repair/clipping.

The M6 source identity now independently authenticates the newly approved
97-file production closure (SHA256 fe1232d4061ab43f92d320ee3937222e88c3e1eead054a53cdd49a6c2ac39fbc),
active package source, dependencies, interpreter and all experiment/validation
sources. Historical 95/96-source guards are unchanged and are not relabeled.

## Accounting boundary

The limit remains 144000 CPU seconds and the absolute deadline remains
2026-10-20T10:19:43.011913Z. The conditional 70893-second cumulative conservative
bound at 2026-10-19 04:45 UTC already includes the earlier 17413-second subtotal.
The interval until 10:05 UTC was idle. All cloud work after 10:05 is conservatively
charged at nine CPUs until the reviewed dedicated metered owner transition;
SELF plus waited CHILDREN then continues once. Nested receipt totals are never
summed. This is conditional conservative accounting, not recovered measurement.
Three historical failed infrastructure attempts consumed zero numerical slots;
their missing receipts remain an explicit evidence gap. No receipts are invented.

`make_continuation_budget` preserves this lineage. The new recovery_runner outer
waited owner authenticates a source-reviewed registry admission and preprocessing
config hash before source access, transfers a cumulative conservative bound to
its sole child, and includes that child's final receipt/exit in its authoritative
measurement. Transfer/setup overlap is conservative and is never summed. The
child retains its continuation budget through all five phases and the queue.
Generation has only a subordinate remaining-resource cap; it cannot reset the
owner's global account. Both historical real launcher entrypoints stay held.

The 70893 bound decomposes as 28773 historical + 41040 for 03:07–04:23 UTC
(4560 seconds × 9) + 1080 for 04:43–04:45 (120 × 9). Parent tool/worker history
confirms no owned jobs during 04:23–04:43 or 04:45–10:05. This reconciliation does
not restore missing original receipts or re-add the earlier 17413 subtotal.

The reviewed source release pins ROOT_RELEASE, ROOT_REGISTRY_ADMISSION,
ROOT_REGISTRY_BYTES_SHA256 and ROOT_PREPROCESSING_SHA256. Actual execution still
requires explicit root GO after the final source/configuration and test review. No environment or
CLI parameter bypasses the hold; runtime configuration must match those pins,
the exact portable protocol and the complete current executable source closure.

## Release checklist

- Bind canonical recovered registry and exact missing-artifact-list digests.
- Bind complete source/runtime/compiler, preprocessing config and toolchain.
- Preserve graph-specific node/Site namespace and graph-independent geography.
- Review the real continuation owner, generation/worker gate propagation and
  final waited receipt boundary; do not simply toggle historical guards.
- Freeze actual source/input artifacts only after explicit root GO.
- Run the fixed queue once and retain every unsuccessful slot.

## Synthetic startup regression

The initial restored mock-suite run retained two failures, and the isolated
reproduction retained one drift-path failure. The original mock's 0.5-second
startup-inclusive wall limit could expire before its asserted scenario was
admitted. A persisted direct diagnostic reached the expected INTEGRITY_FAILED
state. The mock-only wall allowance is now 5 seconds, with its 1 CPU-second
ceiling and 0.2-second exact-phase timeout unchanged. A 0.75-second synthetic
pre-phase startup delay explicitly tests that boundary; the separate timeout
negative must still report phase_timeout and verified cleanup. No physical
worker, scientific sample, resource ceiling or retry policy is changed.
