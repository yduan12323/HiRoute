# Prospective remaining-charge DEV gate

This separate, opt-in gate diagnoses the observed OD10 N32 bottleneck. It does
not alter prior gates/results or make final-holdout claims. It is not launchable
until its code, runtime API and pinned source closure are reviewed and frozen.
No default solver or routing behavior changes.

## Fixed comparison

Both sequential arms use the original OD10 N32 domain, original candidate
membership, physical query, hierarchy, Hmax, target routing, terminal-energy
screen, exact skyline reducer and onward ALT. One freshly generated full-routing feasible
seed is independently replayed twice and supplied identically to both arms.
The five stages are common preparation, OFF search, fresh full verification,
ON search, fresh full verification. Each search has the same externally enforced
120-second exact-search budget. Preparation and each arm have 600-second wall/
CPU limits; verification has 180-second wall/120-second CPU limits. All child
stages have 8 GiB address-space limits; supervisor CPU is capped at 90 seconds.
The same selected CPU runs all stages. Original bounded cache policy is retained.
There is no automatic larger size, repeat, 600-second search, or holdout run.

OFF delegates the existing indexed directed ALT region bound with onward travel enabled.
The ON arm uses the same onward-enabled original bound. ON uses

`max(existing_region_bound, runtime_prefix_bound, whole_route_bound(k + 1))`.

A queued region action promises a next stop, so every represented completion
has at least `k + 1` stops. Positive overhead plus stop penalty makes the whole
route bound monotonic in stop count. Every component is a complete primary
objective lower bound, so they are combined with max, never addition. The prefix
comes directly from the current solver's exact live problem. Runtime admission
and each evaluation enforce the public v1 physical-model, energy/travel
certificate, native owner and routing-history contract. There is no bound cache.
No arbitrary fabricated CutPiece is admitted as a solver frontier.

Original None/unreachable handling, Region masks, member accounting, effect
coverage and leaf actions are delegated unchanged. The engine still performs
strict `lower > current_upper` pruning; equality is retained. The wrapper never
changes Hmax or the domain, and never makes its own pruning decision. Explicit
unsupported-zero or no-curve status disables only the added bound. Integrity
errors propagate rather than becoming zero bounds.

## Activation evidence and interpretation

Before the search phase, ON admits against the actual live search problem and
its already-built ALT provider. It checks the whole-route bound at the verified
seed's stop count against the seed objective. It records B(0), B(seed H),
B(original Hmax), and the diagnostic integer threshold
`min(original Hmax, floor((seed J - B(0)) / (overhead + penalty)))`.
A threshold below seed H is an integrity error. The threshold is never applied
to the declared Hmax. These fields and admission SHA are present in the initial
observer state and the pre-search admission artifact. Three constant-count
whole-route calls are used, not an Hmax-length scan.

The stable policy/configuration, source closure and manifest enter portable
durable-incumbent binding. The detached runtime admission receipt and SHA are
separate evidence because they contain context-specific native identities.
Fresh full replay does not reuse or reconstruct that search context. Cross-arm
incumbent artifacts are deliberately rejected. Activation wall time is measured
separately during setup; receipt serialization is outside that activation clock.
The metric is not whole-setup CPU time.

Counter names distinguish bound calls, original None, disabled calls, tightened
bounds, enqueue-time strict-seed-prune opportunities, enqueue-time opportunities
under the current verified upper bound, and equality candidates. Opportunities
are not actual prunes. Actual engine prune/equality counts are sampled at layer
checkpoints; completed runs also report final actual pruning counts. A censored
last checkpoint can lag the active layer. A stronger bound can change queue
priority as well as pruning, and improvements in one arm's incumbent can change
later decisions. Do not claim a pruning-only causal speedup.

The inherited bounded observer is identical in both arms: 0.5-second persistence
interval, 32 recent events, at most 256 KiB per snapshot, no per-piece trace.
Active operation stacks survive hard timeout when the last write succeeded;
unfinished operation time is censored. Per-operation timings are nested and
inclusive. Runtime validation cost is inside the wrapper operation; durable
incumbent callback timing includes separate fresh verification work whose router
is outside main-provider routing counters. Maximum observed write gap means the
gap between persistence attempts, not completed durable fsyncs. Provider counters
are sampled individually rather than as an atomic routing-history transaction.
Observer overhead is only partially measured.

SUCCESS requires the authenticated arm result's progress/admission hashes and
healthy final observer state. A known final fsync error is inconclusive even if
the previously written snapshot looks healthy. TIMEOUT remains a censored prefix
with unknown final observer health, including a kill-after-return race. Receipt
statuses, phase identities, stage order, cleanup, common seed and fresh verifier
results must all pass independently. A timeout can pass operational/diagnostic
admission without proving exact completion. All completed exact answers must
agree. Negative or inconclusive outcomes remain recorded; no positive-result
retry criterion is present.

## Commands after source review, installation and freeze approval

From the immutable reviewed checkout, use the matching installed Python and
compiler with no source override. Outputs must be outside the source closure.
For example, with `PY` set to that Python:

```sh
OUT=$(mktemp -d ../remaining-charge-gate-XXXXXX)
CPU=$($PY -c 'import os; print(min(os.sched_getaffinity(0)))')
$PY -m experiments.remaining_charge_gate_v1.run --freeze \
  --input-directory ../recovery_inputs --output "$OUT/manifest.json"
SHA=$(sha256sum "$OUT/manifest.json" | cut -d' ' -f1)
taskset -c "$CPU" "$PY" -m experiments.remaining_charge_gate_v1.run --gate \
  --manifest "$OUT/manifest.json" --manifest-sha256 "$SHA" \
  --output "$OUT/gate" --cpu "$CPU"
```

Tiny development tests (no real road graph):

```sh
taskset -c 2 env PYTHONPATH=tests/m5d_recovery:src \
  ../hiroute-ci-venv/bin/python -m unittest test_remaining_charge_gate -v
```

This continuation addresses large-domain performance uncertainty. It does not
invent new acceptance obligations: general live-OPEN/midlayer resume was not a
required milestone outcome, and the existing independent first-feasible
sequential witness met the bounded D5.4 baseline. Historical accounting remains
limited to its recorded evidence; final holdout is still unrun.
