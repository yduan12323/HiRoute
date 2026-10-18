# M5-D portable recovery increment, 2026-10-13

This source-only increment is based on commit
`7e7327970d7de519b90b19f554a207633ff94847`. It consolidates separately reviewed
cloud artifacts into repository-relative source and focused synthetic tests.
It is not M5-D acceptance, a deployment approval, or permission to merge.

## Included behavior

- Bounded source-label reuse preserves native directed-path/tie semantics.
- Streaming seed observation preserves candidate order and completed-seed API
  behavior; an interrupted candidate enumeration is not a completed certificate.
- Feasible-incumbent recovery replays a complete saved witness and its source,
  query, domain, physics and equality-inclusive bound/depth bindings.
- The full-table feasible-incumbent entrypoint is explicitly opt-in and shares
  the original post-verification FLAT/HIER search body. The default API retains
  its completed-seed checks.
- Sparse/table-free feasible execution remains fixture-only. Its small-domain
  guard is retained. Production admission and controllers are not installed by
  this patch, and production execution must not bypass that guard.
- Optional bounded exact-progress observation records incomplete operation and
  frontier information. It supplies no global OPEN lower bound or proof gap.

The reviewed cache layer introduces API defaults of 128 MiB and at most two
source-label sets; setting its byte cap to zero restores uncached behavior. This
does not adopt the real-data trial configuration of two sources / 512 MiB.
Terminal-target/reverse routing and its build
flag differences are excluded. No native binary, graph, real query/witness,
large archive, raw run ledger, private artifact path or controller is published.

## Validation and provenance

`ci/run_m5_recovery_code.py` is registered as an additional workflow step after
the existing isolated-wheel gate. It runs the focused suite under normal and
optimized Python, rejects zero tests/skips/failures, and verifies production
imports originate from the installed wheel. The existing dependency lock and
legacy gate remain unchanged. The native seven-node route fixture needs g++.

Local source-tree validation used Python 3.12.14, whereas the repository's
supported packaging/CI environment is Python 3.11.16. Local focused success does
not establish supported-version wheel success or full legacy acceptance. The
exact commit's hosted workflow must pass before relying on the increment.

Pinned source snapshots under `tests/m5d_recovery/fixtures` are comparison
fixtures, not runtime fallbacks. The REF test manifest names canonical pinned
repository bytes, including their original newline representation; it is a new
synthetic-test allowlist, not an altered historical source-closure receipt.
Historical artifact receipts remain unchanged outside this patch.

The portable suite retains routing ties/cache eviction, candidate coverage,
streaming interruptions, source/domain/witness tamper rejection, full and sparse
tiny FLAT/HIER improvement/equality cases, and observer equivalence/durability.
Two controller-factory tests and the artifact-directory 51-case subprocess
comparison are intentionally not transplanted: their environment-bound runners
are absent. Their historical review is separate from this repository gate.

## Existing real-domain observations, not rerun here

The original hierarchy verified, and a recovered two-stop witness passed fresh
native route/physics replay. Its three legs matched 14,200 saved directed edge
IDs. The retained primary bound is
`232876014671007378489/6871947673600000`, with Hmax=37. The production comparison
used the explicitly declared sorted-ID Region policy, not equivalence with the
uploaded original hierarchy.

Both separately supervised 600-second production rows entered exact search and
were resource-censored. Neither established an optimum or infeasibility. Their
conservative combined row charge was 1198.978063968 CPU seconds; a separate
120-second preparation debit was not a measured complete development ledger.

The following 120-second one-source diagnostics also censored both methods.
Completed post-entry source searches were 51/53 (FLAT/HIER), with routing the
dominant observed cost. The subsequent two-source configuration trial reached
more advances (568/567 versus 243/249) but also censored both rows. These are
different incomplete prefixes, not a speedup comparison. Improved internal
objective coordinates lacked a complete saved reusable witness, so the original
independently replayed witness remains the durable incumbent evidence.

The later terminal-target experiment establishes no demonstrated performance
benefit; compiler-flag differences prevent attributing any difference solely to
the algorithm. No terminal-target implementation is included here.

Evidence identities: production exact manifest
`4bf96aa5027496f2680d1d6bb5a1658675b5f8e7704578ae5a39720a12331267`;
one-source diagnostic manifest
`f5dcb77997b32b47ad0204a5aaad00e9bb37aaf2226ca509eb80ed6cd1bb68e4`;
two-source manifest
`fb7d6f5bd625f4a78408b3f6b233cb53b8a67426b14cf56e71e943056ccddf5d`.
These identify existing reviewed evidence, not newly reconstructed receipts.

All these bounded development experiments are separate from the historical
192-row main denominator. Full final host/project CPU reconciliation, successful
exact outcomes and performance acceptance remain open. The fixed supplement and
holdout are not executed by this patch; no real OD was run to prepare it.
