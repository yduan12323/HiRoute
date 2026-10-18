# Portable certified immediate-finish energy screen

The screen is **off by default**. `RoutingConfig()` and existing target-routing
APIs retain their prior behavior. This optional feature uses the same installed
native router, selected paths, ties, original binary64 path-length sums and
physical replay. It is not a replacement routing backend or a bound on the
whole future search. Full routing remains the default. Explicit
`RoutingConfig('destination_target', TerminalEnergyConfig())` combines the screen
with the existing search-only terminal-target mode. This combination is an
opt-in integration candidate, not a real-road performance or deployment claim.

## Explicit context API

Import `RoutingConfig, TerminalEnergyConfig` from `timecut5.routing_config`.
These imports stay lightweight; NumPy/kernel loading occurs only when requested.
Construct `RoutingConfig(terminal_energy=TerminalEnergyConfig())`, then call its
existing `create_context` with authenticated graph/file/catalog bindings and an
explicit role. Quantum exponent defaults to 20, cap to 2**62-1 and unsupported
floating environments to `reject`. Both fields remain finite and explicit in the
policy. A caller can prepare `timecut5.terminal_energy_artifact.build_artifact`
once using the compiler and the exact flags `-O3 -std=c++17 -fno-fast-math
-frounding-math`, and pass that `energy_artifact` to each context. Otherwise the
context builds/authenticates this package-owned artifact in the supplied cache.
The original router artifact and flags do not change.

### Combining the screen with terminal-target routing

The native target call executes the same priority queue, strict relaxation and
tie policy as the full call, stopping at the first nonstale destination pop.
Its finalized destination labels and ordered predecessor edge chain therefore
retain the full call's selected binary64 path. The energy certificate bounds
that same path sum; it does not depend on settling unrelated vertices. No
potential, beta, endpoint, or physical replay equation changes in the combination.

Only an authenticated package `ExactRouter` in the explicit search role and
either supported mode may produce guarded history. Certificates and history
receipts record the actual routing mode. Context creation still installs the
floating-environment/ownership guard before seed routing, and the provider's
outer leg guard covers the target call, selected-edge replay and cached returns.
A replacement guard cannot adopt prior target-call history. Closed equality
remains eligible; screened-out immediate finishes do not change later expansion.

The existing target seam remains destination-only: intermediate legs use full
routing, and generation/verification/durable verification/recovery/landmarks
remain full-only with an inactive screen. Full-source cache entries may satisfy
a terminal-target request; target-call partial labels never enter that cache.
Only their checked destination leg and ordered witness may enter the pair cache.
Role-neutral provider source identity still permits fresh independent full replay;
the actual search mode belongs to the caller's arm/configuration binding.

The combined finite regression module covers exact labels and edge chains for
parallel/zero/stale/rounding cases, certificate bounds, FLAT/HIER keys and action
order, future charging, open/closed endpoints, fresh full-only replay, cache
isolation, mode mutation, floating controls, and evidence closure. It adds no road
launch. Target calls still allocate and initialize four graph-sized output arrays;
they may visit most of a graph and do not retain a full-source cache entry. If a
source later needs an intermediate leg it may need a separate full run. Measure
these costs under a newly frozen comparison rather than assuming a speedup.

For search, context creation copies source/target/time/length arrays into private
immutable bytes and creates the native router on those exact owners. The context
installs the arithmetic/anchor/cache guard before returning the provider, so
seed replay and later cache hits already have authenticated history. Only
`context.problem(...)` constructs the destination certificate and attaches a
screen. Direct `create_router` remains only a router factory; it does not create
an owned energy context or activate a screen.

Generation, landmark, verification, durable_verification and recovery roles keep
full routing and carry the same stable config/kernel policy digest, but load no
energy kernel, construct no potential/certificate and attach no screen. This
shared policy is valid because screening does not change selected-leg semantics.
It lets fresh independent physical recovery retain the source/domain identity;
it does not relabel search caches as verification. Verification must still use
its own fresh context. A mistakenly attached screen is ignored by verification.
Both FLAT and HIER use the same immediate-finish seam; their action order,
frontiers, later charging/stops, strict bounds and witness replay stay unchanged.

## Arithmetic and trust boundary

The native kernel uses reverse CSR and an indexed bounded heap to obtain capped
integer potentials. Every original edge is independently checked twice:
q_e/2^k <= original distance, p(u) <= q_e+p(v), and p(destination)=0. All potentials
are finite between zero and cap, including disconnected vertices. No unreachable
claim is inferred from a capped potential.

For n vertices beta=max(0,1-(n-1)/2^53). Exact rational rate*beta*p/2^k bounds the
rounded selected-path energy from below. This accounts for each binary64
round-to-nearest addition; it does not equate real sums with rounded sums.
Nonnegative cycle erasure and monotonic rounded addition extend the simple-path
bound to any selected walk. Subnormal additions that underflow are exact on the
binary64 lattice; zero lengths and zero travel-time edges are supported. Finite
nonnegative inputs and conservative no-overflow checks are required. The current
certified platform is Linux x86-64/SSE2 binary64, nearest rounding, no FTZ/DAZ,
masked SSE/x87 exceptions, and the same process/thread throughout guarded work.
Volatile arithmetic probes cover subnormal inputs and results. Controls are
checked at each provider leg/label entry and exit, cached returns included, and
before each screen decision. The original router also retains its own guards.

Reject only when every piece's energy upper endpoint is strictly below reserve
plus the bound, or equals it with an open endpoint. Closed equality stays
eligible. Such a rejection removes only this immediate finish; future charging
and stops remain. `unsupported='zero'` permanently disables nonzero screening
when the environment becomes unsupported; constructor/certificate/integrity
errors are never disguised as a successful zero certificate.

Graph owners, ndarray dtype/shape/strides/pointer, anchors and digest, cache
policy, provider/router/handle/library identities and source bindings are checked.
Graph file hashes remain caller-authenticated; the private arrays are additionally
hashed and bound to the certificate. Callers must preserve context/query identity.
The contract is single-threaded supported API use, not protection against hostile
private-cache edits, reflection, arbitrary native memory writes, or signal code
changing and restoring floating controls inside a call.

Installed `timecut5/*.cpp` resources, wrapper bytes, compiler driver/version/flags,
actual binary and actual mapped inode/symbol owners are authenticated. Each load
gets a unique read-only copy, preventing stale same-path dlopen identities. This
is scoped provenance, not a hermetic compiler/subtool/runtime attestation.

## Optional bounded evidence

`EnergyObservation(output, run_identity={...}, interval=.25,
on_async_error=callback)` from `timecut5.energy_observation` is a caller-owned,
single-context sink. Its bounded identity strings belong to the caller; there
are no experiment names, manifests, absolute archive paths or implicit globals.
Pass it to `create_context(observation=...)`. Certificate publication, file fsync
and directory fsync finish before the screen is attached or can be used.
Construction/publication failure raises to the caller.

`EnergyProgress(..., energy_observation=observation)` reuses the ordinary exact
observer's heartbeat. It requires an explicit caller failure-notification
callback. There are no implicit process exits. The callback must promptly notify
or terminate through the caller's supervising mechanism, including during a long
native call. Callback failure is itself sticky and visible; subsequent owner
operations and completion raise. Without this contract, use synchronous
`observation.sample()` only. Existing ordinary-progress error semantics remain
separate and must also be checked by the caller.

The heartbeat reads only precomputed hashes and fixed scalar tuples. It never
calls floating guards or routes, and does not serialize the full certificate per
poll. Screen calls add no I/O. Attempted/completed/rejected screen decisions and
pending/completed guarded routing are separately sampled coherent tuples, not
one cross-tuple transaction. Setup timings identify graph copy, guard installation,
activation, build-with-first-validation, separate second validation, and certificate
publication. Nested spans must not be added. I/O counters cover previous completed
publications only, excluding current write, serialization, throttle and lock wait.

Status/certificate/commit limits are 16 KiB/256 KiB/1 KiB. Stop the progress
heartbeat, close the context (native/source reauthentication and resource release),
then call `observation.complete(context)`. A final commit is linked only after
durable status publication. Its name is not crash-durable: loss safely rejects
completeness. A missing commit after termination is readable as interrupted,
censored evidence; a corrupt commit rejects parsing. The commit does not prove the process had no later failure.

After verified complete worker cleanup, the supervising caller pins the final
bytes and calls `read_status` with that hash and caller identity. Terminated or
unknown outcomes always produce censored, final-health-unknown evidence, even
when a commit exists. Only an independently authenticated clean terminal outcome
may set `clean_outcome_authenticated=True`; observed callback/exit/resource
failures take precedence. Staleness is measured from sampled monotonic time.
Scheduling/GIL/I/O delay is unbounded, so a plausible timestamp or absent observed
callback cannot prove health at kill. The reader is descriptive and grants no
feasibility, continuation or admission authority; callers separately authenticate
the complete expected certificate and independently replay physical witnesses.

## Costs and release gates

For n nodes/m edges, retained private input arrays cost 32m bytes. Construction
scratch is reverse CSR 8(n+1)+4m plus indexed heap 8n, and potential 8n; construction
total is 16n+8+4m scratch plus 8n potential. Full potential/heap/CSR are freed after
retaining anchor potentials. Copy-time overlap can retain old and new 32m input
arrays. Original graph loader, native adjacency/handles, route caches, Python
objects, masks and allocator overhead are additional. Construction, both scans,
copy/authentication and peak memory are charged per activated search worker;
there is no shared authenticated setup cache. Real deployment costs need an
explicit resource plan. No broad workload superiority or production admission
follows from this portable integration.

The supported release gate is the existing reduced/hash-locked Python 3.11 wheel
CI plus `ci/run_terminal_energy_code.py`, in normal and optimized modes, outside
the source tree with installed-origin checks and pre-import CPU/AS/wall limits.
Local Python 3.12 evidence is supplemental only; project metadata remains
`>=3.11,<3.12` and the reduced dependency lock is unchanged.
