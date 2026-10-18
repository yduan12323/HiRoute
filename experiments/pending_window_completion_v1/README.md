# Prospective pending-window treatment-only completion diagnostic

This candidate passed independent prelaunch completion-gate review, including
the narrow supervisor cancellation correction. Importing it or running `--plan`
launches nothing. Freezing and every manifest consumer still reject any pending
review status. Approval is not a real result or a performance claim; no real
experiment is run by the focused tests.

The original known-DEV `OD06_energy_and_scheduled_soc3_10`, ordered N128
candidate pool and Hmax39 are retained. The previous pending OFF/ON pair each
exhausted its authenticated exact600-second phase. Its TIMEOUT receipts,
progress snapshots, interrupted verification evidence and separately recovered
fresh replay remain unchanged in their original locations. At checkpoint depth2,
the sampled cumulative reducer input was13333 pieces in both arms; output was
12359 OFF and1743 ON, including4948 late-primary discard visits ON. These are
censored repeated-work observations and justify only a separately declared
completion-feasibility diagnostic. They establish neither exact completion nor
a speedup.

## Fixed treatment, unchanged production

There is one arm: `pending_completion_on`. It uses HIER, pending-window ON,
post-service ON, analytic-C ON, projection support ON, envelope OFF, coalescing
OFF, q10 dyadic ALT, onward ALT, target terminal-energy routing, and the
historical remaining-charge runtime. It retains the original query, action
coverage, candidate order, hierarchy, physical seed policy and Hmax39. A fresh
preparation must replay the historical proposal seed; Hmax drift blocks the
search without seed replacement.

This is treatment-only completion feasibility on previously exposed DEV data.
It is not a matched speed study, an unexposed holdout, a retry of the earlier
600-second pair, or a replacement for any historical result. No positive result
is required. There is no automatic retry or next run.

The production source is pinned to commit
`02493a4d4248ffc0f96760efd40ed984c8f61a4e`: all96 non-generated `src/` entries
(95 historical entries plus the reviewed pending-window module) must retain
the exact digest
`c1a8ebc5a046b9ae402bb9337548d9b84037b9876853e99efa8b975263649547`.
Only the exact generated `src/hiroute.egg-info/` metadata prefix is omitted
from that production digest; its bytes remain in the complete closure. No
optional lazy native backend, charge-count runtime, operator compactor or
service-deadline screen enters this diagnostic. The earlier worktree and all
of its receipts are left untouched.

The reducer policy and exact engine hook are unchanged. The domain adapter
reuses the reviewed pending-window domain/progress/terminal authentication;
the lifecycle reuses its robust three-slot serial pipeline without the two-arm
coordinator. The historical product-order certificate remains unchanged.
Generation, seed validation, durable callbacks, final storage and fresh full
replay use the historical disabled analytic/support/envelope contexts. Only
exact search installs the experimental reducer.

## Three sequential slots and caps

The fixed denominator is preparation, treatment search, independent full
replay: exactly three sequential slots, one heavy worker at a time, fixed CPU0,
and one numeric thread. Failed, blocked and censored slots remain visible.
Preflight, artifact admission, cleanup and launch failures fail closed without
silently retrying or dropping a slot.

The authenticated exact phase is1200 seconds through worker exit, including
post-solver finalization. The search worker has1500-second total wall and CPU
soft ceilings (CPU hard1501). Preparation retains600-second wall/CPU ceilings;
fresh replay retains180-second wall and120-second CPU ceilings. Every heavy
worker has8GiB address space. Declared worker reserve is2280s wall and2220s CPU;
these are ceilings, not measured totals or aggregate RSS isolation. The
supervisor's90-second CPU soft budget preserves a hard limit sufficient for
its1501-second child. CPU pinning is shared-host scheduling, not isolation.

The existing low-level supervisor still enforces thread environment, output,
artifact, bounded cache and process-tree cleanup rules. The new schema,
treatment arm, policy, source closure and common-seed digest bind every phase,
progress/admission record, durable incumbent, terminal answer and fresh replay.
A timeout supports only a freshly replayed feasible incumbent. A returned
snapshot under TIMEOUT remains censored. Exact completion additionally needs
an authenticated canonical terminal status/full key (or proper unattained
components), unchanged Hmax, healthy final observer and conserved final
operator counters. Different valid charge witnesses remain allowed.

## Narrow supervisor cancellation correction

Independent prelaunch signal probes found a pre-existing helper bug: the
supervisor's signal handler raised `InterruptedError`, which Python's selector
polling can catch as an interrupted system call. A signal delivered during that
poll could be swallowed, permitting a later worker success receipt. This new
worktree alone changes the helper to a dedicated `RuntimeError`-derived
`SupervisorCancellation`, retaining the existing failure/owned-cleanup path.
The full source closure binds that helper delta; all96 production files and the
original frozen worktree remain unchanged. Real SIGINT/SIGTERM regressions
exercise the selector poll and cleanup of owned workers/detached descendants.
This finding does not establish the cause of the earlier executor connection
loss.

## Runtime and parquet-engine guard

The inherited source identity binds committed executable bytes, active package
bytes, Python version and installed dependency versions. Before a manifest can
be frozen, this adapter additionally imports the actual pandas `PyArrowImpl`,
`pyarrow.parquet` and its native `_parquet` extension, performs a one-row
in-memory parquet write/read, and records the Python executable and imported
engine-module file hashes. A missing or unusable engine fails before a frozen
file is created. Every manifest consumer repeats and matches that identity.
This catches the earlier routing-CI environment's missing-engine condition;
focused validation uses the existing Python3.11 environment with pyarrow26.0.0.
No dependency is installed by these checks.

## Focused validation and eventual interface

Focused tests use synthetic lifecycle/admission fault injection, tiny native
hand-built routing graphs and an in-memory parquet buffer. Run them on CPU2
under normal Python and `-OO`, with numeric threads1. They load no real OSM
input, start no real diagnostic, and touch no user computer or server.

After independent review and final immutable-source validation, the interface
is:

```
python -m experiments.pending_window_completion_v1.run --plan
python -m experiments.pending_window_completion_v1.run --freeze --input-directory INPUTS --output MANIFEST.json
python -m experiments.pending_window_completion_v1.run --gate --manifest MANIFEST.json --manifest-sha256 SHA --output NEW_OUTPUT --cpu 0
```

These commands document the interface; they do not authorize or launch a run.
The original frozen data directory is `recovery_inputs` outside this worktree.
