# Bounded profile after complete family validation

The completed family stage does not establish ordered invocation replay. The
ordered checker still independently reconstructs the exact union/reduction
selection sequence, node identities, compact occurrences, Region decisions and
ancestry commitments. The new diagnostic measures that work without replacing
any mathematical operation or accepting an earlier partial result.

Use the existing complete parallel runner with the additional explicit flag
`--ordered-trace-profile`, the `interval-join-v1` batch kernel and a newly renewed
source plan. It rechecks the original completed capture/return and recomputes
all family and scalar batch obligations with the existing four-worker group.
No solver is invoked. It does not trust or skip work based on a previous ledger.

After publishing the complete batch ledger and after-family marker, it starts a
180-second observation window. This includes the remaining physical-phase check,
trace construction and ordered traversal. Trace setup is separately counted, so
an expensive constructor cannot silently consume the entire window before
sampling starts. The launch has a fixed 480-second absolute deadline, with the
existing BATCH_REPLAY memory, host reserve, disk and evidence limits unchanged.

The observer records bounded 1 Hz stacks, stage call counts and inclusive wall/CPU
times for selection, dispatch partitions, node reconstruction/hash, compacts,
Region bounds, candidates, ancestry/cache/hash work and query construction. Samples
include trace/batch cursors and the next batch hash when available. Selection
samples expose active-list sizes and the current input index. It does not insert
per-pair hooks or copy a graph into diagnostics. The live replay reference is weak.
There are at most 182 samples, 64 selection-entry summaries and a 1 MiB report.

The diagnostic stops when its window ends or ordered traversal returns, before
callback receipts and query finalization. All diagnostic reports explicitly set
acceptance=false, structural_verified=false and literal_G8_closed=false. A normal
resource-phase return means only that the bounded observation completed. Real
checker errors still make the resource phase fail; any report is retained as
partial evidence. The default complete replay path is unchanged.

The existing invocation command and original capture pins are retained; add:

```sh
--batch-kernel interval-join-v1 --ordered-trace-profile
```

Use a fresh attempt and retain the exact successful launcher return. Source-plan
renewal must occur after publication. This is a targeted diagnostic command, not
an instruction to repeat the full 1,800-second run.

Tiny tests compare ten immutable mock traces with instrumentation disabled versus
enabled, including full query outputs and summaries apart from elapsed time.
They also check timer/hook restoration on return, error and interruption, weak
reference release, complete family revalidation, exact diagnostic output coverage,
false acceptance flags and prevention of callback work. Initial cloud checks use
Python 3.12 because that is the replacement environment; the project declares
Python 3.11 and requires its focused server preflight before this diagnostic.
