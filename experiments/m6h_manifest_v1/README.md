# Recovered source status (2026-10-19)

This is reviewed source recovery for disclosed-history new-map validation.
Real entrypoints remain held. See `docs/M6_DISCLOSED_RECOVERY_PROTOCOL.md`.
The following is historical documentation from snapshot 9598021, not a current
claim of source identity or a real-run authorization.

# Current status (2026-10-18): DATA_LIMITED; physical execution held

The approved bounded proposal now has a source-level physical worker, independent
REF and budgeted queue implementation, tested only on synthetic/exposed tiny
fixtures. The existing map has zero eligible groups under frozen exclusions.
No actual holdout inputs or runs were created. See
`docs/M6H_CURRENT_STATUS.md`, `docs/M6H_PHYSICAL_ADAPTER.md`,
`docs/M6H_INDEPENDENT_REFERENCE.md` and `docs/M6H_RESOURCE_QUEUE.md`.
Actual source/input release remains blocked for root review and a permitted viable
source. New-source scope is separate; nothing here authorizes its acquisition.

The following describes the original mock-only scaffold (`contract.py`,
`runner.py`, `mock_worker.py`), whose entrypoints stay permanently held and whose
results must never be used as physical evidence. Its historical remaining-work
list records the original preparation boundary, not the current implementation
inventory; current limitations are in the documents linked above.

# M6-H held manifest contract / mock supervisor adapter

Status: SOURCE PREPARATION ONLY. No selected OD, holdout data, input access,
selection, generation, freeze, hash, physical solve or independent REF run.
`freeze`, `consume`, `generate`, and `execute` always raise before touching their
arguments. There is no launch flag, environment override or approval boolean.
A later reviewed implementation and explicit final approval are necessary.
Production `src/` and the existing DEV wrappers are unchanged.

## What works

- Pure fixed-slot declaration: at most six anonymous group numbers; N8 low SOC,
  N32/N128 both SOCs. Default 30 domains, 156 operation slots, 60 method rows,
  six separate REF slots, 24 main domains/48 main results.
- Deterministic N8 -> N32 -> N128 ordering, alternating method order per phase.
  No retries or replacement. A declaration change invalidates plan validation.
- Explicit immutable bytes interface rather than importing DEV case allowlists.
  The implemented input adapter accepts only built-in synthetic records. It is
  deliberately NOT a generic real-data loader. Prefixes use the same ordered
  mock-site IDs at all N; no OD/map selection is performed.
- Mock admission checks bind input, source/runtime labels, method, tree, policy,
  common seed, exact Fraction-based Hmax, full mock key/attainment, double seed
  replay and fresh replay. Typed exhausted-stream no-seed stays UNKNOWN about
  feasibility. These checks test the contract, not real mathematical evidence.
- Reviewed `mechanism_recovery_v1.supervisor` supplies actual fresh subprocesses,
  CPU3 affinity, numeric threads=1, phase markers, wall/CPU/AS/file limits,
  process-tree observation, durable receipts and verified cleanup. Neither DEV
  `run.py` nor native compiler/solver is imported by the harness.
- Failure rows stay in denominators; ordinary resource failure can continue to
  the next executable arm/domain. Identity or cleanup uncertainty stops queue.
- Separate mock REF slot is bound to the same seed/Hmax/input. It reports
  `independent_mock_ref_no_physical_claim`, never independent exact-match evidence.
- Mock budget admission reserves an entire domain before launch, charges worst
  case even when unused, and retains every budget-blocked row. This reservation
  is NOT measured CPU accounting or an enforced aggregate CPU budget. Parent
  bookkeeping has a planning allowance, not a production parent RLIMIT.

## Tests

Synthetic engineering tests only (CPU3 is not the real CPU0 contract). From
this worktree, with an existing Python 3.11 interpreter, no installation:

    taskset -c 3 python3.11 -m unittest discover -s tests/m5d_recovery -p test_m6h_held_manifest.py -v

The mock-only harness uses 5-second startup-inclusive wall / 1-second CPU worker ceilings and 0.2-second
mock search phase. These are explicitly not the proposed 600/1500/180/120-second
real stages. All process fixtures are invented tiny records; test output is
under temporary directories and removed after assertions. No wheel rebuild.

## Genuine remaining work before a final executable protocol

1. Freeze exact selection/exposure exclusion and geographic grouping rules;
   establish legal map provenance from known records and count eligible groups
   only after approval. Group numbers in `plan()` do not prove independence.
2. Implement the real bound-input validator: complete query JSON, ordered Site
   records/effects/anchors, nested pool prefixes and shortage slots, hierarchy,
   graph, original vs runtime sparse-domain rebinding, canonical digest rules.
   Do not relax the existing site catalog, query, source or replay checks.
3. Bind executable transitive closure, installed package, Python/dependencies,
   compiler flags and native artifacts. Mock string identities are not source
   authentication. Do not claim the production 96-entry digest covers wrappers.
4. Factor an input-agnostic worker from the reviewed DEV lifecycle. Preserve
   original streamed seed plus fresh double replay, source/cache/native checks,
   seed-derived depth, durable phase identity, canonical terminal payloads,
   timeout incumbent semantics and fresh physical replay. The existing DEV
   runner cannot be launched with a different directory and called generic.
5. Independent physical REF adapter must consume the same actual input and full
   Hmax, with complete key and attainment semantics. H_ref=4 in the old query
   compiler is a fixture placeholder, not the M6-H reference depth. Mock REF
   only proves slot plumbing; no exact reference solver was implemented here.
6. Real global worker+parent CPU accounting, 48-hour deadline, per-domain worst
   case reservation, prelaunch MemAvailable check and proposed sampled aggregate
   RSS/host-memory stop remain to implement and test. Existing supervisor
   records sampled process-tree peak RSS but does not stop at 5 GiB aggregate
   or MemAvailable <2 GiB. RLIMIT_AS is per-process virtual address space.
7. Statistical frozen analysis and publication are outside this mock adapter.
   All exposed results stay development; none become holdout evidence.

No new approval is needed merely to continue this source preparation. The gate
is for real selection/generation/read/hash/consumption/execution after the final
protocol is concrete. This module is not a frozen final protocol or launchable
manifest, and makes no claim to be final-ready.
