# Opt-in initially reachable charging candidates

This API proposes an explicitly versioned candidate domain. Existing candidate selection and solver defaults are unchanged.

## Installed API

- `timecut5.portable_candidate_policy.build_portable_domain(...)` accepts an authenticated graph/router, original query/baseline site rows, the full eligible charging catalog and its binding metadata. It runs at most one origin source computation and reconstructs the existing selected fastest-path legs. It retains all baseline sites and all eligible omitted chargers satisfying the arrival-energy floor. Terminal reserve is reported separately. Distinct colocated site IDs are retained.
- `timecut5.portable_candidate_binding.derive_binding(...)` validates a pinned complete proposal and derives its actual candidate/site/anchor/sparse-domain/query identities. It does not verify a route or choose U/Hmax.
- `timecut5.frozen_candidate_catalog.build_catalog(...)` authenticates the existing frozen site/pool/geographic/slate format and recomputes corridor eligibility for the supplied OD. It is a frozen-format adapter, not a generic external-data loader.

All function inputs are keyword-only. `build_portable_domain` returns an immutable `PortableResult`; inspect its `ProposalStatus` before using its payload. Only `PROPOSED_COMPLETE` can produce a domain binding. Cap overflow returns `FALLBACK_REQUIRED` without a truncated candidate prefix; invalid or incomplete work returns `UNKNOWN`. The caller must explicitly handle either failure and may not substitute a previously expected list. The default cap is 256, not a promise that every complete union fits it.

## Trust boundary

The caller must authenticate graph bytes, native implementation/compiler identity, query, full eligibility catalog and original sparse-domain policy before invoking the core. Hash strings supplied by a caller alone do not establish trusted provenance. The core performs structural/read-only graph checks and input-consistency validation, not independent graph-file authentication. The eligible catalog must be recomputed from the actual query and authenticated sources, never filled from a prior measured reachability file.

Keep typed failures bound to the actual launch/query/catalog/reservation in a supervised production wrapper. A core failure may lack the successful proposal's binding payload. Do not treat a returned proposal or derived binding as permission to dispatch an exact solver.

After successful domain derivation, create a fresh provider for seed generation, persist a provisional witness and independently replay the complete route with fresh authenticated state. Derive the exact upper bound and depth limit only from that replay. Provider/native ownership, cleanup, source pins and resource limits remain the caller's responsibility.

## Scope

One known DEV execution of the source precursor computed 128 original sites plus 21 additions online, then found and separately physically verified a complete two-stop route. The 149-member expected identity was checked only after computation. This does not establish broad effectiveness, optimality or a general success rate. Initial reachable chargers may still lack subsequent charging bridges, compatible schedules or useful heuristic sequences. Geographically excluded chargers and slower lower-energy road paths are outside this policy. A negative selected-path result does not prove all-road infeasibility.

The cloud fixed-DEV policy→seed→verification controller is experimental orchestration, not an installed default. Its absolute paths, native source pins, one-case expected identity and admitted runtime manifests are evidence, not portable configuration defaults. No large dependency snapshot is installed by this change.

## Tests

Portable tests cover complete deterministic union, one-source enforcement, colocated identities, reserve-versus-floor handling, cap/incomplete failure behavior, source/query/domain binding and synthetic frozen-catalog eligibility. The private OD07 metadata fixture remains separately recorded in the completed experiment; it is not silently skipped by the installed package suite. Publication verification builds the existing project wheel, installs it into an isolated target and runs these tests plus relevant existing regressions from outside the source tree in normal and optimized Python modes.
