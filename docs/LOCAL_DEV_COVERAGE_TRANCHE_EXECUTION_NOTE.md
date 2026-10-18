# Tranche A source freeze and scope

This unpublished checkpoint follows the terminal original OD06 N128 method pair and its independent audit. All 96 production entries and existing helpers remain byte-identical to source 43e83b5. The new experimental wrapper authenticates original case/N bindings and seed-derived Hmax; it does not use the historical H_ref=4 placeholder as the search depth. No optional convex-count, lazy-native, compaction or deadline candidate is integrated.

Runnable order is OD01/OD03/OD04/OD05 high-SOC scheduled at N32, then the same four at N128. Each domain has one fresh original preparation and FLAT/HIER search-plus-replay: forty fixed slots. The complete preselected eight-query design is retained, but B cannot execute through this wrapper.

One heavy worker runs on CPU0. Exact phases are 1200 seconds and search workers have 1500-second wall/CPU caps; preparation is 600/600 and fresh replay 180 wall/120 CPU. Each process has an 8 GiB address-space cap. The per-pair supervisor has an absolute 180-second CPU ceiling; the whole queue has 1440 seconds and outer polling of 0.2 seconds, preserving inner 20 ms telemetry. The fixed conservative CPU-charge reservation is 36000 seconds under a separately declared 20-hour ceiling. It is a reservation, not measured unique CPU, and does not reconcile historical accounting gaps.

The read-only 7168 MiB available-memory check is a planning estimate, not a reservation or aggregate hard memory guarantee. Outer samples may miss peaks; inner traces remain authoritative within their sampled scope. All expected no-seed and failed/blocked descendants remain visible. Arbitrary errors never become no-seed outcomes; integrity, unsafe resource state, non-phase timeouts and unknown cleanup halt new starts. No retries, substitute queries or automatic candidate expansion are allowed.

This prospective source freeze does not establish new feasibility, exact completion, hierarchy superiority, holdout acceptance, GitHub publication or a main merge.
