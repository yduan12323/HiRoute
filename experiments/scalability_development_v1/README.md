# Separately bound 32/128-candidate development gates

This is an **executable, opt-in DEV experiment**, never a final holdout or a
replacement for any previous outcome. Both arms run HIER. The sole treatment is
`reduce_frontier_skyline` in place of `reduce_frontier`; neither the default
reducer nor production feature settings are changed. Source-cache telemetry is
observational and identical in both arms. No cache-locality change is enabled.

## Fixed order and admission

1. OD10_energy_only_soc19_25, original N32: fresh common preparation, baseline
   search, fresh baseline replay, skyline-only search, fresh skyline-only replay.
2. Stop and inspect that five-stage gate. A separate explicit N128 invocation is
   permitted only after all five stages have operational admission.
3. OD10_energy_only_soc19_25, original N128: same five-stage structure, separately
   generated common seed and incumbent-derived Hmax. No automatic next size,
   reverse order, repeat, other OD, combined arm, FLAT comparison, or holdout.

Original N32 is an insertion-ordered prefix of original N128. Both original query
bindings are authenticated before seed generation: query, candidate, Site,
anchor-catalog, sparse-domain, graph, hierarchy, pool, and historical router/tie
identities. Their physical query fields must agree; only the historical sparse
candidate-domain hash differs. The runtime source change rebinds that domain
explicitly and preserves the original query hash in the common artifact.

The incumbent is constructed independently of either exact arm. Its full key,
continuous physical witness, positive-overhead Hmax, original restricted tree,
native artifact and cache configuration are shared within each count. Two fresh
full-routing seed checks precede comparison. Each final incumbent receives another
fresh-process full-routing replay, even following a phase timeout.

Cross-size seeds are independently constructed. If their full keys, routes or
Hmax differ, the size contrast mixes candidate and initial-condition differences;
it cannot isolate candidate-count complexity. This gate is a selected known-DEV
engineering check, not an independent population sample. OD07's repaired149
result does not enter either count, and the original192/fixed24 outcomes remain
unchanged.

## Resource bounds and denominator

Per candidate count: one preparation + two searches + two verifiers = **5 stages**.
Each search receives an externally enforced **120-second exact phase**, after
seed/bound setup. Preparation/search workers each have600-second wall and
600-second per-process CPU soft limits; verifiers have180-second wall and
120-second CPU soft limits. CPU hard limits are soft+1 second. The dedicated
parent has a90-second soft CPU budget with its compatible inherited hard limit.

The worker wall reservation is2160 seconds and worker CPU-soft reservation2040
seconds per count; exact exposure is240 seconds. Across both separately admitted
counts:10 stages,4320 worker-wall seconds,4080 worker-CPU-soft seconds and180
parent soft seconds. Reservations are not measured usage and are not an aggregate
process-tree CPU proof. Gate-manifest/predecessor validation before the inherited
batch runner and CLI/finalization work must be separately accounted; the batch
parent timer alone is not the entire invocation cost.

Run **one road worker at a time**, pinned to one available CPU. All numerical
thread environments are1. The existing supervisor applies an8-GiB per-process
address-space limit and samples tree RSS; it is not an8-GiB aggregate RSS/cgroup
limit. Confirm current host headroom before launch and retain these limitations.
Earlier comparable workers sampled roughly3.1GiB peak RSS; this is context,
not a guaranteed bound. Do not run concurrent road arms. No new graph/native
code or second process supervisor is introduced.

Preparation failure, non-exact setup/wall timeout, invalid receipt, unknown cleanup,
replay failure, source drift, exhausted parent budget, or conflicting completed
exact answers stops admission. Every planned stage stays in the ledger, including
failed/blocked stages. A120-second exact-phase timeout with verified cleanup and
a fresh feasible replay can pass **operational admission**; it is never an exact
completion or feasibility proof for other domains. N128 checks the N32 manifest,
source, ledger digest and actual stage artifacts before proceeding.

## Measurements and success/failure criteria

- Primary engineering outcome: preserve physical feasibility, mathematical
  contract and all outcome statuses; inspect paired finite-horizon feasible full
  keys and whether either solver completes.
- When both complete, compare mathematical terminal payloads, including attained
  full keys or J/Q unattained infima. Different valid charge allocations are
  permitted. An exact-result disagreement is a correctness stop, not a speedup.
- Report both completion/resource-interruption rates against denominator2 per
  count. No timeout deletion, zero-speedup imputation, or pooling with old runs.
- Report cold-worker wall/setup and final replay separately. Add the entire shared
  preparation cost to each arm's standalone end-to-end estimate; do not silently
  give either arm a free seed. Do not call worker-stage wall a measured CPU total.
- At exact entry, snapshot routing telemetry. At complete layers or normal return,
  record deltas, interval-distinct sources, repeated full-source runs and per-source
  counts; source-cache bytes is an end gauge. Setup misses are excluded from the
  new search deltas. The old lifetime counters remain separately visible.
- Reducer call/piece-visit/inclusive-wall counters and inclusive durable-callback
  wall are captured equally in both arms. Durable callbacks create fresh routing
  contexts outside the search provider's counters. Other residual search wall is
  unallocated, not automatically attributed to reduction or routing.
- Forced timeout does not finalize a last checkpoint. Such counters are censored
  observations at unequal times, never whole120-second throughput. Count repeated
  piece visits as visits, not unique PWA pieces. An interrupted reducer/callback
  may be absent from the last completed metrics snapshot.
- Fixed baseline-first order and uncontrolled OS caches limit timing inference.
  This gate does not require a positive result. Exact finite correctness tests
  must pass before freezing; no statistical population speed claim follows from
  one OD/two counts. Full FLAT/HIER D5 comparison remains a separate next decision.

## Exact commands

Run from the repository root. The source must be committed and clean, and active
installed package bytes must match that commit. The parent owns staging/install
and code regression before the freeze. These commands use the restored cloud
Python3.11.17 environment; record that it differs from the historical CI document's
3.11.16 instruction. Use new, nonexistent output paths on every attempt.

Graph-free regression (normal and optimized):

    PYTHONPATH=tests/m5d_recovery:src ../hiroute-ci-venv/bin/python -m unittest discover -s tests/m5d_recovery -p test_scalability_development_gate.py -v
    PYTHONPATH=tests/m5d_recovery:src ../hiroute-ci-venv/bin/python -OO -m unittest discover -s tests/m5d_recovery -p test_scalability_development_gate.py -v

Print either prospective plan without running a graph:

    ../hiroute-ci-venv/bin/python -m experiments.scalability_development_v1.run --plan --candidate-count 32

Freeze after source/code review, with **no PYTHONPATH
source override**, so installed-source equality is actually checked:

    ../hiroute-ci-venv/bin/python -m experiments.scalability_development_v1.run --freeze --candidate-count 32 --input-directory ../recovery_inputs --output ../extension_runs/scalability_od10_n32_v1_manifest.json

The freeze prints the exact manifest SHA. Launch only the N32 gate using it and
an actually available CPU ID:

    ../hiroute-ci-venv/bin/python -m experiments.scalability_development_v1.run --gate --manifest ../extension_runs/scalability_od10_n32_v1_manifest.json --manifest-sha256 MANIFEST_SHA --output ../extension_runs/scalability_od10_n32_v1_execution --cpu AVAILABLE_CPU

After operational admission, a new explicit launch decision and current host
headroom check, freeze the N128 manifest with the same source/runtime:

    ../hiroute-ci-venv/bin/python -m experiments.scalability_development_v1.run --freeze --candidate-count 128 --input-directory ../recovery_inputs --output ../extension_runs/scalability_od10_n128_v1_manifest.json
    sha256sum ../extension_runs/scalability_od10_n32_v1_execution/ledger.json
    ../hiroute-ci-venv/bin/python -m experiments.scalability_development_v1.run --gate --manifest ../extension_runs/scalability_od10_n128_v1_manifest.json --manifest-sha256 N128_MANIFEST_SHA --prior-ledger ../extension_runs/scalability_od10_n32_v1_execution/ledger.json --prior-ledger-sha256 N32_LEDGER_SHA --output ../extension_runs/scalability_od10_n128_v1_execution --cpu AVAILABLE_CPU

No command above publishes, merges, changes original results, or runs final holdout.

## Scientific/engineering acceptance still open

The original taskbook remains broader than these gates. Larger-domain exact
completion, representative FLAT/HIER total-cost/completion comparison, feasible
multi-charge coverage at the original48-query scale, complete-candidate checks,
applicable development contrasts, and complete historical resource reconciliation
are not established by this experiment. Preserve the existing accepted scope of
completed-layer reconstruction; warm or arbitrary mid-layer resume is not an
added requirement. The independent first-sequential-feasible construction supplies
its bounded D5.4 comparison; sequential optimization is not an added acceptance
condition. Onward/coalescing and checkpoint evidence retain their recorded scopes.
The unresolved large-domain performance and historical accounting gates remain
explicit, and final holdout is unrun. This continuation adds new evidence and code
without redefining M5-D success or declaring project completion.
