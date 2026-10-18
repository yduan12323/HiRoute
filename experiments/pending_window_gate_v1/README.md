# Prospective conditional pending-service gate v1

This isolated diagnostic has passed independent proof, implementation and gate
review. Its prospective plan stays nonlaunchable; freezing still requires clean
immutable source and every pinned source/compiler/input check. A pending-review
marker blocks both freezing and manifest consumption. No real OSM or holdout
run has been launched for this gate. It leaves production defaults and all
historical gates unchanged.

## Fixed known-DEV comparison

The sole case is the original OD06_energy_and_scheduled_soc3_10, N128, Hmax39.
The original source query, complete candidate order and hierarchy are unchanged.
Both arms use HIER, analyticC, projection support, q10 time, target routing,
terminal energy and the historical remaining-linear bound family ON. The
existing completed-departure post-service reducer is ON in both arms. Only the
new conditional pending-window reducer changes:

- pending_off: new feature OFF, CPU0
- pending_on: new feature ON, CPU1

Envelope sweep, convex charge-count runtime, operator compaction and the separate
service-deadline screen are OFF and excluded from the accepted source. No
secondary pwa.py or optional runtime candidate may enter either arm.

The opt-in module version is pending-window-late-primary-order-v1. Its admitted
r=1 condition uses theta=a-h: only a strict-primary-worse historical skyline cut
with tau>theta, or tau=theta and chi=False, may be removed. Every affine
threshold root is an arrangement knot; attained threshold equality retains the
historical product tradeoff. Only the existing trusted complete-next-departure
full-State hooks and same-live-problem runtime admission may select this rule.
The code and conditional proof passed their own independent review in addition
to the lifecycle review. This document grants no launch authorization.

## Two independent pipelines and six retained slots

Exactly two fresh dedicated single-threaded pipeline processes run concurrently,
pinned to CPUs0/1. Each does a fresh historical, feature-independent preparation,
one exact search, and an independent full-routing replay. The coordinator only
supervises those two pipeline processes. A pipeline owns at most one heavy child
at a time, so at most two heavy workers run. There is no silent concurrency
reduction, automatic retry, substitute case or automatic next run.

All six slots remain in the durable ledger after failure, including unattempted
slots. A pipeline-local failure blocks its remaining slots while preserving the
other pipeline. A coordinator-level failure cleans up owned descendants, blocks
both pipelines and admits no aggregate result. Cleanup is verified through the
reviewed owned-process/subreaper pattern, rather than inferring it from a
vanished process. Admission failures retain original receipts and observations.

- Preparation: 600s wall / 600s CPU
- Exact phase: exactly600s from authenticated entry until worker exit, including
  final durable stores, serialization and post-solver finalization
- Search worker: 900s wall / 900s CPU, including setup outside the exact phase
- Fresh full-routing replay: 180s wall / 120s CPU
- Each process: 8GiB virtual-address-space cap; numeric threads one
- Each pipeline supervisor: 90s CPU soft budget, preserving an inherited hard
  cap which must admit the search worker's901s hard cap
- Each pipeline wall watchdog:1800s, above its1680s maximum worker wall reserve
- Combined worker wall reserve3360s and CPU soft reserve3240s; exact phases1200s

A read-only prelaunch MemAvailable observation must be at least8448MiB, matching
two3840MiB job estimates plus768MiB headroom. This is an observation, not memory
reservation, cgroup enforcement, an aggregate hard memory cap or an OOM
guarantee. Missing or insufficient readings fail before either pipeline starts.

## Physical pairing and authenticated outcomes

Preparations run separately and charge their own work. They always select the
historical preparation path, independent of treatment. Each preparation gets
fresh native routing contexts and independently replays the deterministic
proposal seed. Before any paired claim, admission requires exact canonical
agreement on both physical queries, complete seeds (including witness bytes,
full lexicographic keys, Hmax and stable native identities), candidate order,
hierarchy, source and input identities, cache policy and proposal ordinal.
Preparation timing and native receipt filesystem paths are not physical inputs
and may differ. Feature-dependent durable/domain hashes may legitimately differ.

Method and feature have separate explicit bindings in configuration, phase
identity, durable hashes, admissions, observer snapshots and result envelopes.
An authenticated SUCCESS receipt alone is insufficient. Completion needs a
healthy final observer, conserved terminal statistics, canonical exact terminal
payload and fresh full-routing replay of that arm's own durable witness.

Completed arms compare the canonical status and complete lexicographic key for
an attained optimum, or exact primary/secondary unattained-infimum components.
Treatment result witnesses and charging choices need not be byte-identical.
Timeout arms provide only independently replayed feasible incumbents; their
live multi-field snapshots are censored and nontransactional even if a snapshot
says returned. No positive performance result is required.

New pending counters cover all outer reducer calls. Old post-service counters
are unchanged and cover only calls actually delegated to that fallback reducer.
They are never relabeled as coextensive statistics. In a healthy final result,
old.calls = new.calls - new.strong_calls; new candidate_visits is the sum of
product_discarded, late_primary_discarded and kept_candidate_visits. A pending
strong cell may keep several parents, so selected_cells is not an output-piece
count. Final outputs include the delegated subset plus kept visits minus
same-original-parent connected-domain coalesces. No final conservation identity
is imposed on an interrupted live sample.

## Frozen source and interpretation

Stage only this gate and its focused test, plus the independently reviewed new
reducer module/test/proof document, onto immutable1a83b644. All existing95
production src entries must match d7a38c02 and digest
bcaf573c0d82ebee70cd877616aff9c5367883640794335ff8c081b385c57bea.
Exactly src/timecut5/pending_window_dominance.py is additionally allowed. Only
the exact generated src/hiroute.egg-info/ prefix is excluded from the95-entry
comparison; metadata still belongs to the complete frozen executable closure.
The manifest separately binds the new module hash/version, all adapter/lifecycle
bytes, compiler identity and every source input. Clean committed source and
active-package byte matching remain required when freezing and consuming it.

This is a previously exposed, deliberately selected scheduled DEV diagnostic,
not an outcome-blind sample, holdout or broad scalability result. CPU affinity
and thread limits do not create clean caches, hardware isolation, memory/I/O
isolation or independent shared-host observations. Timings are descriptive only.
All historical240/600-second outcomes remain separate, without pooling or
supersession.

## Validation and future interface

Focused tests use existing Python3.11, explicit clean-baseline production imports
plus only the reviewed new module, and CPU3. They cover synthetic admission,
resource policies, all failure positions, six-slot retention, separate counters,
physical pairing, both exact outcome forms and tiny native HIER OFF/ON fresh
full replay. No installs, real OSM or holdout launch are part of validation.

The following interface is prospective. Freeze and run only an independently
approved immutable source after all admission checks:

```
python -m experiments.pending_window_gate_v1.run --plan
python -m experiments.pending_window_gate_v1.run --freeze --input-directory INPUTS --output MANIFEST.json
python -m experiments.pending_window_gate_v1.run --gate --manifest MANIFEST.json --manifest-sha256 SHA --output NEW_OUTPUT
```
