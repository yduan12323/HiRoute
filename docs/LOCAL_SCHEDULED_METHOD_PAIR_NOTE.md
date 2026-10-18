# Fixed scheduled FLAT/HIER source freeze

This unpublished checkpoint follows the authenticated scheduled HIER completion
report d2389f2. The same96 production source entries are pinned to f89e4f3;
only a new method-aware experiment, its focused tests and evidence are added.
The separately validated lazy-native allocation and convex/count bound adapters
remain excluded, together with operator compaction and deadline screening.

Original OD06 N128/Hmax39 receives one fresh original common seed, FLAT search
and fresh replay, then HIER search and fresh replay. All five slots remain.
Both exact phases are1200 seconds, search-worker caps1500 wall/CPU seconds,
preparation600/600, and verifier180 wall/120 CPU. The dedicated supervisor's
180-second CPU soft ceiling is separate from those worker limits and does not
measure whole-worker CPU. Each process has8GiB address-space cap.

Heavy workers are serial onCPU0. The new available-memory observation floor is
7168MiB (5120MiB planning allowance plus2048MiB reserve), not a reservation or
aggregate hard RSS guarantee. It is rechecked before each heavy launch. The old
3840MiB-per-job concurrent assumption is not reused. Existing plan requires
complete memory evidence and2×1.25P+2GiB before admitting two jobs; the present
host does not justify that based on the new observed scheduled footprint.

The standalone wall cost of each arm includes the entire shared preparation
plus its own worker and fresh verifier. Nested timers are not added, total
invocation CPU is not split into invented per-arm worker CPU, and fixed order
plus shared-host/cache effects limit causal performance claims. Both completed
canonical outcomes and their own full replays must agree; a timeout remains in
the denominator and prevents a completed-pair speed ratio.

The historical treatment-only HIER success is not used as this pair's HIER
observation. Older600-second failures and interrupted accounting remain. This
source freeze claims no new paired result, positive speedup, holdout acceptance,
GitHub publication or main merge.
