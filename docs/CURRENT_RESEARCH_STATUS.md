# Current research status

M5-D outcome: **M5D_LIMITED_BY_DATA_OR_SCALE**. This closes the bounded evaluation report with explicit limitations; it does not declare unrestricted implementation or deployment acceptance. M5-V remains accepted within its historical scope.

The original 192-row M5-D matrix is terminal: 148 timeouts, 44 failed initial-solution searches and no exact completion. Current portable recovery code has passed exact-head CI at 7dbd82. Neither fact establishes large-scale performance acceptance.

The fixed24 supplement is terminal: 23 pre-search timeouts and one infrastructure-unknown interruption; no sequential comparison completed. Fresh FLAT and HIER recovery each reconstructed its depth 1 completed-layer envelope and independently replayed the same original feasible witness. Both exact searches timed out; no new optimum or performance gain was established. Historical accounting and undemonstrated comparison capabilities remain explicit limitations. See [the single M5-D report](MILESTONE_5D_REPORT.md). The experiment-level outcome and any remaining implementation gates must be reported separately. M6-H and automatic main merge remain outside this handoff.


## 2026-10-15 cold-query development increment

The seed generator now skips provably unnecessary outbound routing, with eight portable regression tests including 2,304 finite stream-equivalence cases. The [cold development evidence](../results/milestone_5d/cold_development_20261015/README.md) records a single known DEV control: the same first verified witness at roughly 253 to 75 seconds and 128 to 29 first-proposal source searches. Sequential ordering and OS caches are uncontrolled; this does not establish broad speedup, exact completion or hierarchy equivalence.

Cold-query and durable-incumbent coordinators remain experimental and are not installed APIs in this increment. Durability has tiny local validation only and was not active in either measured DEV pair. Later scalar improvements have no saved replayable route. Existing bounded milestone conclusions remain unchanged.
