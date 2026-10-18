# Fixed scheduled FLAT/HIER matched-method gate

Status: independent prelaunch review PASS201. Import and `--plan` launch
nothing; freezing and every manifest consumer still reject any pending review
marker. Clean committed-source, actual-engine and frozen-manifest validation
remain required. No real road graph experiment is part of focused validation.

## Scope and fair comparison

Use the original previously exposed DEV
`OD06_energy_and_scheduled_soc3_10`, original ordered128 candidates, frozen
hierarchy and original fresh physical proposal seed. One newly executed common
preparation is shared unchanged by both methods. Hmax must remain39; drift
blocks both without seed repair or replacement. The completed prior HIER1200
result is background only, never a paired result or an improved search seed.

Run fixed FLAT then HIER, each with pending-window and post-service reducers ON,
analytic-C ON, projection support ON, q10 dyadic/onward ALT and target
terminal-energy routing. Envelope and coalescing remain OFF. Both use the
historical linear remaining-charge certificate-bound family. FLAT explicitly
passes the reviewed singleton adapter to `_solve_problem`; HIER explicitly
passes the common region provider to `_solve_hierarchical_problem`. Both pass
the same versioned reducer with the runtime admitted to their own live problem.
The same bound family does not imply identical region aggregation, queue order,
incumbent discovery or pruning. Times are descriptive fixed-order, shared-host
observations, not an isolated causal hierarchy effect.

All96 non-generated production entries remain byte-identical to
`f89e4f3087c8f11f3fafa2adc116eec5aaed272a`, digest
`c1a8ebc5a046b9ae402bb9337548d9b84037b9876853e99efa8b975263649547`.
Only exact `src/hiroute.egg-info/` metadata is omitted from that production
comparison; it is retained in the complete executable closure. No convex/count
runtime, lazy allocation backend, compactor, service-deadline screen, new query,
holdout, retry or automatic next run enters this gate. Reuse of prior lifecycle
helpers is explicit; no module-global monkeypatch installs policy or dispatch.
The corrected `SupervisorCancellation` helper and actual PyArrow import plus
in-memory Parquet roundtrip guard are inherited unchanged.

## Five retained slots and resource planning

The fixed denominator is one preparation, FLAT search, fresh FLAT full replay,
HIER search, fresh HIER full replay. All five run serially on CPU0 with one
numeric thread and at most one heavy worker. Blocked, failed and censored slots
remain retained. Unknown cleanup, launch/admission failure, memory-preflight
failure or an inadmissible worker stops subsequent launches without retry.

Each exact phase is1200 seconds through worker exit, including post-solver
finalization; each search worker has1500s wall/CPU soft limits (CPU hard1501).
Preparation has600s wall/CPU; each verifier has180s wall and120s CPU. Every
worker has8GiB address space. The five-worker reserve ceilings total3960s wall
and3840s CPU soft. The supervisor-only CPU soft ceiling is180s; this explicitly
allows five slots after the prior three-slot controller used55.27s CPU. Its
inherited hard ceiling must admit the1501s search child. These ceilings do not
establish aggregate CPU or memory isolation. Supervisor CPU and child resource
accounting must not be double-counted.

The [existing cohort resource policy](DEV_COHORT_PAIRED_PLAN.md#stages-entry-reuse-and-resource-policy)
keeps serial as default until complete process-tree observations justify any
concurrent proposal. Here no concurrent proposal is made. Immediately before
every heavy launch, read `/proc/meminfo` and require MemAvailable at least7168MiB:
a5120MiB planning estimate plus2048MiB OS/controller reserve. This is informed
by the previously observed approximately4032MiB per-process peak; it is not a
certified whole-process-tree peak P, a reservation or an aggregate hard bound.
MemAvailable can change immediately after reading. Missing/malformed telemetry
or a low observation blocks further starts. Retain the existing supervisor's
complete process-tree memory traces and owned cleanup receipts.

## Accounting and acceptance

Execute the fresh common preparation physically once and report that measured
pair cost once. Separately charge its entire measured wall cost to each standalone
method, plus that method's own search worker and fresh full replay. These stage
receipts do not observe each worker's full CPU usage; do not substitute
supervisor CPU or split total invocation CPU into invented per-method CPU. Preserve
setup, exact phase, post-solver finalization and replay details separately. Do
not sum nested inclusive timings or omit failed stages. No positive timing
result is required.

Each method's durable method tag, phase nonce, case, common-seed digest, source
closure, configuration, admission chain, Hmax and original seed key are bound.
Exact completion needs authenticated canonical terminal status and full key,
matching fresh full physical replay, healthy final observer and conserved final
operator counters. Pending statistics count the outer reducer; old post-service
statistics count only delegated fallback work. Live TIMEOUT snapshots are
censored and support only freshly replayed feasible evidence. If both complete,
compare full exact keys including action sequence, or the proper primary/secondary
unattained components. Do not require identical valid charge witnesses. Any
completed canonical disagreement blocks paired admission.

## Eventual interface

After independent review, clean committed-source validation and explicit source
freeze, the interface is:

```
python -m experiments.scheduled_method_pair_v1.run --plan
python -m experiments.scheduled_method_pair_v1.run --freeze --input-directory INPUTS --output MANIFEST.json
python -m experiments.scheduled_method_pair_v1.run --gate --manifest MANIFEST.json --manifest-sha256 SHA --output NEW_OUTPUT --cpu 0
```

These examples do not launch or authorize a run. Focused validation uses the
existing Python3.11 routing-CI environment with no installation, real OSM input,
user computer or server activity. Tiny native checks cover both methods,
reducer/runtime wiring, original-seed parity and independently recreated full
replay under normal Python and `-OO` on CPU2.

## Independent prelaunch evidence

Held-runtime review PASS201 binds the unchanged method dispatch, five-slot
lifecycle and admission logic, focused tests and plan. The review record SHA256
is `08a8c0ac8bcc1426a852eb2d5b789bfa529c8a2d5cf95d2bbdaf2b37fe421d93`.
Focused tests passed11 under normal Python (47.05s) and11 under `-OO` with
installed production imports (48.22s). Every installed timecut5/microplan
executable matched the frozen source. The optimized run reported only the
expected pytest optimized-assertion warning. Independent checks also passed10
installed-origin non-native tests in each mode and six real-process synthetic
endpoint modes: normal completion, detached-orphan completion, both verifier
failure positions, FLAT SIGINT and HIER SIGTERM. These check bounded lifecycle,
admission and tiny native routing behavior; they are not a real scheduled
experiment, performance measurement, aggregate memory guarantee or taskbook
acceptance. The controlled release changes only the review marker and review
text, followed by narrow pending-guard and approved-manifest checks.
