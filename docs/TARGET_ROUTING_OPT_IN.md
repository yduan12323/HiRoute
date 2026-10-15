# Opt-in destination-target routing

This API is an opt-in package integration candidate. `RoutingConfig()` keeps full
routing. Only an explicit `search` role with `search_mode='destination_target'`
may stop routing when the destination is settled. Generation, verification,
durable verification, recovery and landmark roles always use full routing.
Existing callers without an explicit role keep full routing.

## Construction and ownership

Use the installed package, its existing compiler configuration and a caller-owned
local cache. No OD06 identifier, experiment directory, admission file or graph
loader is embedded in this API.

```python
from microplan.native_artifact import build_artifact
from timecut5.routing_config import RoutingConfig

compiler = {'compiler': 'g++', 'compiler_flags': ['-O3', '-std=c++17']}
artifact = build_artifact(compiler, cache_dir)
policy = RoutingConfig(search_mode='destination_target')

# graph arrays and input hashes have already been authenticated by the caller.
with policy.create_context(
    graph, compiler, cache_dir, role='search', artifact=artifact,
    anchor_nodes=anchor_nodes,
    nodes_sha256=nodes_sha256, edges_sha256=edges_sha256,
    anchor_catalog_sha256=anchor_catalog_sha256,
) as search:
    problem = search.problem(
        query, sites, origin_anchor=origin_anchor,
        destination_anchor=destination_anchor,
        site_catalog_sha256=site_catalog_sha256,
    )
    # Pass problem to the existing solver. Numerical and search settings are
    # caller-owned and are unchanged by the routing policy.
```

Explicit roles require aligned contiguous int64 source/target arrays and float64
travel-time/distance arrays, all read-only, with finite nonnegative weights.
Dimensions and endpoints are validated. A conservative bound rejects potential
binary64 simple-path overflow. The caller must prevent mutation through writable
aliases and must authenticate the supplied input hashes against the graph data;
this API cannot infer that binding from arrays alone. Cache hits and native calls
check live owner/buffer identity. Full file authentication occurs at construction
and explicit trust/replay boundaries, rather than hashing files on every leg.

A context owns one native handle and its own provider caches. It is not
thread-safe. Close it after use; do not use a closed context or replace its graph
arrays. Loaded libraries use distinct immutable copies, so another context's
build does not overwrite a mapped library. The cache retains these load files;
callers own cache lifecycle and must not remove files while contexts are active.

## Independent physical replay

Use a newly constructed context with role `verification`, `durable_verification`
or `recovery`, sharing the exact artifact but no provider/cache objects with
search. These roles stay full even when the policy's search mode is target.
Recovery and durable-incumbent replay enforce the explicit role, full mode,
zero target calls and fresh caches before replay; they reauthenticate afterward.
The existing legacy replay contract remains available for role-less full-only
providers. It does not acquire the stronger new explicit-role guarantees.

For recovery, construct the fresh provider and its full-only problem factory,
then call the existing `recover_feasible_incumbent`. For durable verification,
the existing problem factory must construct a new full-only context per replay.
The caller owns and closes those contexts after the replay. Do not give a search
provider to either verifier, even if that search provider uses full mode.

## Numerical contract and cache scope

Target settlement uses the same compiled routine and strict relaxation rule as
full routing: the first nonstale destination pop stops before outgoing expansion.
The selected time/length labels and ordered predecessor edge chain must match
full routing for the same binary, graph edge order and input. Equal labels do not
replace predecessors. Zero-weight and parallel edges are allowed. Supported
explicit-role compiler flags exclude fast-math, and calls require round-to-nearest.
This is a supported-API contract, not a sandbox against hostile Python reflection.

Only destination-terminal table-free problem legs opt in. Intermediate legs remain full.
The separate table-backed RoadSelectedLegProvider retains its exact baseline
contract and always requests full source labels, even with a target-capable router.
A complete full-source cache entry may satisfy a target request. A target result
may populate the selected-leg cache, but its partial labels never enter the
full-source cache. `source_run_count` and `target_run_count` are distinct.
Explicit-role source identity includes the settlement contract and artifact
identity; it is role-neutral so independent full replay can verify a search
witness produced with that same build.

## Installed native provenance and platform limits

The build reads package resources using `importlib.resources`, including the
packaged `routing.cpp`. Its immutable receipt binds package source/wrapper/helper
bytes, resolved compiler driver bytes/version, flags, platform and output binary.
Each context authenticates the exact loaded mapping and symbol origins. Source
resource removal, receipt/binary tampering or changed mapping fails closed.

This is not a hermetic toolchain attestation: compiler subtools, shared runtime
libraries and external graph contents are not independently authenticated by this
helper. The compiler path is part of build identity. Copying the same installed
package resources to another location can preserve identity with the same
compiler; a different compiler installation need not. Local cache ownership is a
trust assumption. Authenticated native loading currently supports Linux only,
including legacy full callers; other platforms require a separately reviewed
implementation. The build keeps the existing compiler/shared-object convention.
Compiler children have 30-second wall and 20/25-second CPU limits; an inherited
stricter hard CPU limit is not increased.

## Validation and promotion gates

The supported project runtime remains Python 3.11 (`>=3.11,<3.12`). The existing
isolated-wheel Linux CI workflow now invokes `ci/run_target_routing_code.py` in
normal and `-OO` modes, checking installed import origins and rejecting skipped
or zero-test success. Its finite suite includes same-build full/target equality,
accepted baseline native equality, tie/zero/stale/parallel/rounding cases,
cache isolation, actual FLAT/HIER parity, fresh full recovery and durable replay,
role/handle/output guards, artifact tampering and relocated package resources.

Local recorded results use supplemental Python 3.12.14 with an explicit package
metadata override and existing third-party dependency paths. They do not satisfy
the Python 3.11 release gate. Exact-revision supported-wheel CI and focused review
must pass before promotion. The baseline fixture is a verified repository subset;
these local results do not claim the complete repository CI suite passed.

Prior real evidence covers one known development query in two fixed orders,
using frozen experimental wrappers. It motivates this opt-in integration; it does
not establish broad speedup, cross-build equivalence, general production
readiness, or whole-run timing acceptance. Defaults are unchanged, and no
production activation or source publication is included in this candidate.

## Reduced-dependency import boundary

Importing `microplan.routing` or the explicit routing policy does not require the
opportunity, envelope or graph-loading stack. `OpportunityId` in microplan model
annotations is a type-only import; annotations remain postponed strings. Runtime
type-hint introspection that resolves those annotations must supply the real
`OpportunityId` in `localns`, after importing its owning package in an environment
with its dependencies installed.

`from microplan import generate_plans` remains available and returns the original
`microplan.generation.generate_plans` function. Its import is deferred until that
export is requested. Generation still requires its real envelope dependencies;
missing dependencies raise normally and are not replaced with a fallback. Direct
submodule imports retain the same behavior. This separation does not change the
project dependency metadata or the hash-locked reduced code-only CI dependency set.

The routing CI runner installs its CPU limit before importing package modules.
Two additional cold installed-interpreter regressions block unused graph-related
imports and verify that generation is genuinely deferred while retaining its real
runtime dependency. The supported Python 3.11 gate must still run on the exact
published revision; local Python 3.12 evidence is supplemental.
