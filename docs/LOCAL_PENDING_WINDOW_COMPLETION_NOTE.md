# Scheduled treatment-only completion source

This local checkpoint follows the isolated pending-window OFF/ON600 diagnostic at02493a4 and its separately recorded replay recovery. The source implements the same96 production files; no optional candidate is integrated. The additional budget is an explicitly separate1200-second exact phase (1500-second search-worker cap) on the unchanged original OD06 N128/Hmax39 with HIER and pending/post-service reduction ON. Three serial slots and all failures remain retained. Prior600 failures and interrupted verification/accounting remain unchanged.

This prospective source does not claim exact completion, a speed comparison, holdout acceptance or public/main publication. Source identity includes actual PyArrow engine import and a tiny in-memory Parquet roundtrip, in addition to distribution versions. The separate native lazy-allocation candidate is tested in another environment and excluded here.

## Experimental supervisor correction

Actual signal probes exposed a pre-existing helper defect: InterruptedError raised by a signal handler can be swallowed by selectors.EpollSelector.select. This checkpoint uses SupervisorCancellation, a RuntimeError subclass, in that handler; the existing exception cleanup path is unchanged. Independent real SIGINT/SIGTERM probes now retain failed search/blocked verification slots with verified owned-process cleanup. Only the new experiment dependency helper changes; all96 production files remain fixed. This does not identify the cause of the previous connection interruption.
