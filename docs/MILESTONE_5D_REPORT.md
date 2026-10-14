## Representative synthetic ablations: 2026-10-14

Separately reviewed tiny-domain evidence now records 64 correctness cells and
192 descriptive reduction/coalescing timing rows, plus 36 exploratory routing
cold/warm rows and a distinct 36-row post-review confirmation. All final cells
passed their specified exact-outcome checks. The initial serialization-failed
harness attempt and exploratory review-order deviation remain preserved and
explicit. This uses frozen reference answers, not newly solved REF cases.

See [the evidence and source-reconstruction index](../results/milestone_5d/representative_ablations_20261014/README.md).
These results demonstrate synthetic correctness and selected-leg cache reuse;
they do not establish production long-haul performance. Additional verified
tightening, production table-free coalescing, the fixed 24-row production
supplement, full D6 accounting and final D8 closure remain open. Original
192-row main outcomes remain 148 timeouts, 44 seed failures and zero exact
completions. M5-D remains incomplete.

# Milestone 5D development evaluation — living report

## Current evidence update: 2026-10-14

**The original main matrix is terminal: 192/192 rows recorded, 148 time limits,
44 failed initial-solution searches, and zero exact completions. M5-D remains
in progress. No HIER computational benefit is demonstrated.** These are uploaded
terminal snapshots, not a claim that any server process is currently running.
The earlier dated observations are retained below for provenance and are no longer
the current status.

### Reproducible main-matrix audit

Run from the repository root:

```sh
python scripts/summarize_m5d_terminal_state.py \
  --manifest results/milestone_5d/terminal_state_audit_20261014/inputs/frozen_main_phase_v3_20261011.json \
  --state results/milestone_5d/terminal_state_audit_20261014/inputs/main_state.public.json \
  --parallel-state results/milestone_5d/terminal_state_audit_20261014/inputs/parallel_state.public.json \
  --output /tmp/hiroute-terminal-audit
python -m unittest discover -s tests -p test_m5d_terminal_summary.py
python -OO -m unittest discover -s tests -p test_m5d_terminal_summary.py
```

The [machine-readable summary](../results/milestone_5d/terminal_state_audit_20261014/terminal_summary.json)
and [all 192 normalized rows](../results/milestone_5d/terminal_state_audit_20261014/benchmark_results.jsonl)
are generated from byte-hashed minimal public projections. Original uploaded raw
state hashes are retained as provenance; raw scheduler tokens and host paths are
not published. Each projection validates its schema, kind and canonical payload
hash before summarization. The original private raw bytes cannot be reconstructed
or independently authenticated from the public projection alone. The audit rejects duplicate JSON keys,
missing/unexpected row IDs, manifest or continuation disagreement, denominator
exclusion, unfinished states, and inconsistent CPU totals. It intentionally rejects
new exact-status claims until a proof-aware audit is supplied; a status string
alone is insufficient to establish exactness.

- Denominator: 192 fixed rows, 96 FLAT/HIER bindings; none excluded.
- Exact completion: 0/192. Time limits: 148/192 (77.0833%). Failed initial search:
  44/192 (22.9167%). Neither class proves physical infeasibility.
- Paired exact completions: 0/96. Paired end-to-end speedup and its confidence
  interval are **NA**, not 1×. Equal timeout caps do not establish equal performance.
- The first 93 serial rows omit the observed phase. Their phase remains **unknown**.
  The 99 continuation rows record 73 `seed_started` timeouts and 26 `seed_failed`
  outcomes. Do not generalize this to all 148 timeouts.
- The 93 serial rows and 99 continuation rows form one matrix, not 291 rows.
  The continuation's 4-to-5-worker ramp is recorded in its uploaded state; it is
  a later execution amendment, not a rewriting of the original frozen limits.
- Uploaded snapshots reference durable receipts, but this consolidation does not
  re-fetch or independently revalidate every original server receipt. Missing
  per-row fields such as early-row wall time remain null; no timings are invented.

### CPU accounting and historical budget

Cgroup CPU is 99,559.649486 seconds (27.6554581906 hours):
48,608.328801 serial plus 50,951.320685 continuation seconds. The continuation's
host/controller cumulative total is 4,265.765481 seconds (1.1849348558 hours).
The known main-row-plus-continuation-host subtotal is 103,825.414967 seconds
(28.8403930464 hours). Per-row host counters are cumulative snapshots and must
**never be summed** or added again to that host total.

The frozen manifest records a conservative pre-main debit of 10.536667 hours.
Serial host overhead, transitions/final tails and reconciliation of the complete
original 48-CPU-hour ledger remain outstanding. The known subtotal is not a
complete project CPU total or proof that the original budget was satisfied.
Later separately authorized diagnostics/continuation work has separate ledgers;
it does not rewrite the original 192-row denominator or erase historical charges.

### Later recovery evidence, separate from the main comparison

The [supplemental evidence index](../results/milestone_5d/terminal_state_audit_20261014/supplemental_evidence_index.json)
binds the retained evidence used in this section. These exploratory trials are
not the preselected D5 supplement and do not replace failed main rows.

- OD06 N32's reachable sites being S-only explains a candidate-coverage failure;
  it does not mean broken charging equipment or global physical infeasibility.
  The N128 domain has a physically replayed two-stop feasible witness. A feasible
  incumbent is neither the completed heuristic minimum nor a global optimum.
- Two real, table-free FLAT/HIER runs entered exact search using the same verified
  incumbent and bounds, then both hit their 600-second end-to-end limits.
- Subsequent instrumented 120-second exact-search windows with one- and two-source
  caches show road-label work dominating completed operations in the sampled
  prefixes. More observed pieces under the same cap is not full-query speedup.
- Terminal-target early stopping did not demonstrate improvement. Its comparison
  also changed compiler optimization from `-O3` to `-O2` with strict floating-point
  options, so it cannot isolate an algorithm-only performance effect. It was not
  promoted as the default routing implementation.
- Existing completed-layer replay is available and charges reconstruction CPU.
  Durable mid-layer improved-incumbent export and a global OPEN certificate remain
  separate gaps. A current-prefix Region bound is not a global optimality gap.
- The published recovery code at `1a6bd82b4b96df04c6e849525cdb30f39ba79d55`
  passed [Python 3.11 installed-wheel CI](https://github.com/yduan12323/HiRoute/actions/runs/38420415748).
  CI passing does not establish large-domain performance acceptance.

### Remaining work and decision boundary

1. D5: the fixed 24-row supplement remains unrun, including the separately frozen
   complete-universe checks and designated comparison/repeat/transport work.
   Reduction/coalescing/tightening/cold-warm contrasts are additional open items;
   ordinary repeats do not satisfy them. A source-equivalent member-scan contrast
   must not change both access strategy and bound semantics unnoticed.
2. D6: finish the scoped correctness evidence mapping, independent witness and
   full-key comparisons where exact results exist, per-stage costs and uncertainty,
   and historical ledger reconciliation. Preserve all failure and censored rows.
3. D8: consolidate related-work comparability, transportation value limitations,
   claims/evidence and reproducible result indexes into the stable entrances.
   This terminal-state audit repairs a stale entrance; it does not close all gaps.

A negative conclusion is permitted by the taskbook. The main matrix supports
“no computational benefit demonstrated on this matrix”; final classification as
`M5D_COMPLETED_WITHOUT_DEMONSTRATED_BENEFIT` or `M5D_LIMITED_BY_DATA_OR_SCALE`
requires closing or explicitly resolving the remaining deliverables, not silently
marking them passed. No final holdout or merge is authorized by this report.

## Historical observations (preserved verbatim)

# Milestone 5D development evaluation — living report

Status as of 2026-10-12 02:05 UTC: **main running; results and conclusions pending**. This document is a stable report shell and evidence index. The authoritative changing ledger is the server `state.json` at `/home/dy/HiRoute/m5d_main_a99f534_20261011/`; its receipts and phase logs are retained there. Do not infer an optimality, infeasibility, or HIER speed claim from this interim snapshot.

## Frozen question and denominator

The development slate has 12 ODs × two SOCs × two activity modes = 48 exact queries. Each has nested 32/128-Site inputs and separate FLAT/HIER rows: **192 fixed rows**. The serial scheduler starts at one worker, within the preregistered maximum of two. Each whole row includes graph load, native route setup, seed admission, bounds, exact search if admitted, and independent terminal replay, inside a 600-second, 8-GiB, 100%-CPU-quota cgroup. It retains time/memory limits and failed seeds in the denominator. Six separate complete-universe targets are frozen; their numerical checks are not part of these 192 rows and are unrun. Holdout is excluded. The frozen phase is [`frozen_main_phase_v3_20261011.json`](../results/milestone_5d/continuation_20261011/frozen_main_phase_v3_20261011.json), SHA-256 `a575039c65b8ce31b4f725e389685c5cb78e71ae6df7c2a99d66da7b70ce1064`.

## Source and input authority

The manifest's `source_commit_at_freeze` is `14f2b8440244ece73b2b796099624f8b1a593981`: it binds 35 source-file SHA-256 values, including the corrected structured terminal status, FLAT/HIER coordinate comparison, durable layer replay, and CPU quota. Commit `a99f534e7a952a1facfca1957413265129ed1b4e` added the manifest and is the isolated server checkout. Commit `5e43f48dae4358719f273b27196af9f272d97e32` added CI wiring only; all 35 frozen numerical source files at that branch head match the manifest. Exact-head CI runs [38157748654](https://github.com/yduan12323/HiRoute/actions/runs/38157748654) and [38158023759](https://github.com/yduan12323/HiRoute/actions/runs/38158023759) passed. The server production verifier `/home/dy/HiRoute/project` remains at `1af12a96ca7de909f5971e49f118322117bf07ec` in the last read-only check.

Frozen input hashes: 48-query payload `dc22c22bd56dbd763e41eecbc0da1310259990c25caef469783a49032ccaed7c`; ranked pools `4b93c90b0f4f77364cd9e58b5a779bccd11fb7b99819646c8096ed4f122fe937`; six complete Site universes `d262fbe2411d5fa5d78a242a5799b27c6f1f785348538c52ba192059634c9ff2`. The graph node and edge bytes are `7424eea357d98b54c4652062440a1d287d509f1b7250f7eabbcc5185cde923b5` and `37f0f75e71de97e0b045d53af23b181e034e6c3262a1a4079d582f37471bb1b8`.

## Interim result and accounting

At the dated snapshot, scheduler PID `2286454` was alive, 12/192 rows were terminal, and measured main cgroup CPU was **4,846.586684 seconds** (1.346274 hours). Six rows were `incumbent_search_failed` before solver start; six reached `time_limit` during seed admission. None of those six time-limited rows had `seed_verified` or `search_started` in its retained phase log. There was no `verification_failed`, memory-limit, or budget stop. These counts are a snapshot, not final statistics; consult `state.json` for later states. A failed deterministic finite proposal search is not an infeasibility proof. A timeout is censored, not an exact key.

The total new-numerical-work ceiling is **48 CPU hours**. The conservative charge before main is **10.536667 hours**, including source-bound input construction. Main has a distinct **32.5-hour (117,000-second) reservation**, not a claim of actual consumption. The outside-main reserve is **4.963333 hours (17,867.9988 seconds)**. The last observed main use leaves 112,153.413316 seconds of its own reservation. Remaining main allocation is not automatically transferred to supplemental work. The input debit and receipt hashes are in [`main_input_debit_20261011.json`](../results/milestone_5d/continuation_20261011/main_input_debit_20261011.json). The live state, rather than this dated report, determines later actual use.

The later 2026-10-12 02:22 UTC [`conservative budget reconciliation`](MILESTONE_5D_BUDGET_RECONCILIATION.md) links each historical charge, the preserved partial-unit full charge, the 180-second deviation, 14 completed main receipts, and the outside-main inventory. Its current supplemental allowance remains **unreserved**; it does not transfer unused main capacity.

One historical functionality-run deviation is retained and charged: the OD02 N8 same-engine recovery attempt at source `56d9f2f` was mistakenly configured for **180 seconds**, although the M5-D functionality limit was 120 seconds. It timed out after 180.096475 wall seconds and 181.253984 cgroup CPU seconds; the failure record and checkpoint remain preserved. [`sparse_functionality_cpu_debit_20261011.json`](../results/milestone_5d/continuation_20261011/sparse_functionality_cpu_debit_20261011.json) records the discrepancy. Subsequent functionality units use the 120-second guard. This deviation supplies no optimum claim and is not removed from the budget.

## Pending analyses and claim limits

- At terminal main state, tabulate all 192 row statuses, actual CPU/memory, reached phases, independently replayed attained keys, and any paired FLAT/HIER agreement or disagreement. Count censored and failed-seed rows in every denominator. Do not fill a speedup table from only successful rows without its selection denominator.
- The six complete eligible Site sets contain 6,087 Sites for each of the first four OD00 queries and 7,766 for each of the next two OD01 queries. Their inputs are frozen, but **no complete-universe numerical check has run**. A 128-Site subset is not a complete-universe result.
- `sequential_no_overlap_baseline` is a **bounded feasible construction**, not an exact sequential optimum. The earlier real OD02 N8 first-feasible comparison measured only seed selection within a fixed proposal stream. No real main-domain sequential transport benefit is established.
- The historical small-domain Pilot established one attained FLAT/HIER exact-key agreement and ten censored method rows. No HIER performance benefit on the development main, full universes, or published external methods is established. The member-scan ablation, representative repeats, and supplemental real sequential comparison are unrun; see [`MILESTONE_5D_SUPPLEMENTAL_PROTOCOL.md`](MILESTONE_5D_SUPPLEMENTAL_PROTOCOL.md).
- The supplemental ordinals 8 and 47 are a purposive post-start developmental subset; ordinal 8 belongs to the previously inspected successful OD02 Pilot family. They are not a blinded or unbiased sample. Reduction, coalescing, tightening, and cold/warm contrasts remain unrun and are not covered by ordinary repeats or the current supplemental CPU proposal. Complete ablation acceptance is not established.
- A pure member-scan ablation has not passed source-equivalent review: the legacy scanner uses exact selected-leg minima while production uses directed ALT summaries. A comparison that changes both is a combined bound/access contrast. Noncontemporaneous N128 timing against the main control is confounded by run order and host/cache state. Full-universe censored rows must report the last phase reached, especially whether seed admission completed before the time limit.
- The final holdout and PR merge are outside this evaluation phase.
