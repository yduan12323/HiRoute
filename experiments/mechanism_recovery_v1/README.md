# Mechanism recovery v1

This is a **new experiment**, not an exact October 16 resume. Historical results,
UNKNOWN ownership and historical charges remain separate. No historical timing
is pooled. The checked-in manifest is deliberately nonlaunchable. No real graph
has been loaded or routed for validation of this runner.

## Frozen protocol

Only DEV OD02 energy-only SOC 3/10 N128; OD07 energy-and-scheduled SOC 3/10
original N128 plus the complete public reachable-candidate repair (expected149);
and OD10 energy-only SOC19/25 N32. OD10 uses its frozen32 binding/order/hash,
not an independently selected subset. Candidate cap failure blocks the case,
never truncates it. Nine source files are bound: the original six plus the
original full Site catalog, geographic screen and OD slate needed for repair.

Order: OD02 indexed/recompute, OD07 recompute/indexed, OD10 indexed/recompute;
then OD10 recompute/indexed, OD07 indexed/recompute, OD02 recompute/indexed.
Each case has one newly generated common seed, independently rerouted/replayed
before either arm. This is explicitly a new first-feasible streamed proposal
policy, not a claim to regenerate the historical finite-stream minimum.
Every arm checks the full lexicographic key, fresh-derived Hmax, query, Site,
original-tree, native artifact and source binding. Original Hmax values are
not hardcoded. No candidate count, witness leg count or stop depth is fabricated.

Both arms invoke the existing exact HIER solver. The only ALT difference is
indexed summaries versus recomputed identical extrema. Action masks/order and
original frozen hierarchy IDs/empty nodes are shared. Recompute constructs no ALT summaries during setup and retains no
ALT-summary index. ALT member-read instrumentation is disabled. No online parity
checker or progress observer is installed. Existing solver bookkeeping remains
unchanged. Package-owned routing and energy native artifacts are built/verified;
recovered archive binaries are never executed. Full routing is mandatory for
every explicit role. Energy screening is ON for search only. Fresh independent
verification providers have no search cache. Cache policy is identical in arms.

## Execution boundary and budgets

`python -m experiments.mechanism_recovery_v1.run --plan` prints the prospective
plan. `--worker prepare` and `--worker arm` are implemented for the supervisor;
`--batch` runs the frozen sequence through the single supervisor. All require
an external, SHA256-pinned, launchable manifest with exact verified published
source snapshot closure, installed dependency versions, compiler, input paths and
unchanged protocol. The checked-in manifest cannot pass this gate. Its source
commit is historical provenance only; it is not the executable closure.

Before any real launch, publish/review the committed code and create that closed
manifest. Pin compiler path and binary SHA256, version and flags. The common
preparation receipt seals actual router/energy build provenance and native
identity, exact query/domain, candidate repair, seed and Hmax; each arm freshly
replays it. All code must be committed before preparation or arm execution. For restored
snapshots without .git, source_identity requires the publisher-verified remote
commit, tree and complete relative-path Git blob map. Every blob and SHA256 is
rechecked locally, including detection of missing/unlisted executable sources.
Active installed timecut5/microplan source sets and bytes must match; a stale wheel
with the same version is rejected. This does not claim a clean local git worktree.

Three common preparation workers and twelve arm workers each have wall600s,
CPU600/601s, AS8GiB, one permitted core, numerical threads1. Parent CPU90s soft; inherited hard cap is preserved and must admit worker601s. A parent hard100s cap would incorrectly prevent those workers. The90s budget is cumulative for the whole orchestration, including preflight, not reset per stage. Before each launch it reserves10s for cleanup/finalization and stops when exhausted.
Maximum reserved worker wall is11160s and soft CPU10440s: three common
preparation workers600/600, twelve search workers600/600, twelve fresh terminal
verification workers180/120. Each arm's externally supervised phase is120s,
starting at the atomic identity-bound entry marker after native setup, graph
load, common-seed replay, landmark certification, summary/mask setup, and durable
seed publication. The600s containing stage charges all setup. The phase budget
includes incumbent persistence/replay and post-entry teardown until worker exit.
Its deadline is enforced by the supervisor even during native calls; Python
SIGALRM is used only by a tiny unit test, never by production workers.

Every SUCCESS or owned TIMEOUT search stage is followed by an independently
budgeted fresh verification worker. Setup-time timeout without an incumbent
fails verification; it is not a feasible success. Verification loads only the
last committed durable file and reroutes/replays it. Source, common receipt and
search supervisor receipt are SHA256-bound; verification never trusts a saved
incumbent scalar. No stage budget is silently extended.

Search-window expiration returns only freshly recovered feasible evidence,
full key and improvement over the common seed; it never asserts optimality.
A process-level timeout may leave a durable witness, but that alone is not an
accepted terminal outcome. Lost receipts or uncertain owned-process cleanup
are UNKNOWN and stop the sequence. Every planned arm stays in the ledger,
including blocked, failed, timeout, verification failure and UNKNOWN outcomes.

Durable writes are synchronous and each accepted witness is rerouted/replayed
using a fresh verification-role provider, with prompt native cleanup. Search-only
timing includes incumbent persistence/replay invoked by search; postsearch replay
is charged to the separate terminal verification stage. Native compilation, source checks, loading, seed,
certification and setup are charged explicitly or to containing stage wall/CPU;
none is a free oracle. Fresh process/provider is not a cold OS-cache claim.

## Fixed first-DEV integration gate

After publication, source attestation and review of the admitted external
manifest, use the installed Python environment with repository root on
PYTHONPATH (never force an older checkout's src directory):

```
python -m experiments.mechanism_recovery_v1.run --gate \
  --manifest /absolute/path/admitted.json --manifest-sha256 <sha256> \
  --output /absolute/path/new-od02-gate --cpu <permitted-core>
```

`--gate` is fixed to OD02 energy-only SOC3/10 N128: prepare, indexed search,
indexed fresh verification, recompute search, recompute fresh verification.
It uses the unchanged full three-case source/input manifest; changing the
manifest's cases or order is not a supported subset mechanism. Case/strategy
arguments are rejected for gate/batch. Both gate arms share one immutable common
receipt and independently reverify the same full seed key and derived Hmax.

The gate ledger has scope `od02_gate` and an explicit five-stage denominator.
Its output directory must be new. It uses the same supervisor, source and input
gates, CPU/AS/affinity/output limits, external120s phase and cumulative90s parent
budget as the full batch. Common/search stages each reserve600s wall and600s
soft CPU; the two separate verifiers each reserve180s wall and120s soft CPU.
Gate reserve:2160 worker-wall seconds and2040 soft-CPU seconds. UNKNOWN stops
immediately. Failed preparation, failed search, or failed verification blocks
remaining gate stages; owned timeouts proceed only to fresh verification.
No case, order or threshold is selected from outcomes.

Review gate receipts before a separate `--batch` invocation. The gate does not
automatically launch the batch and its data/timing is not pooled into the batch.
The full batch remains27 stages with its own fresh directory and ledger; its
manifest/order/reserve is unchanged. Gate plus full batch reserve13320 worker-wall
seconds and12480 soft-CPU seconds across32 stages. A successful gate invocation
means the five stages completed their contracts, not that either120s search
proved optimality.

## Tests and limits

`PYTHONPATH=src:. python -m unittest tests.m5d_recovery.test_runner -v`

Synthetic tests exercise actual compiled native energy-ON HIER in both arms,
independent durable replay, input hash tampering, original hierarchy identities,
seed/key/Hmax/query/native mismatches and timeout semantics. Candidate policy and
supervisor tests are separate. These tests do not establish production performance
or feasibility and do not authorize launching the real graph or holdout.
