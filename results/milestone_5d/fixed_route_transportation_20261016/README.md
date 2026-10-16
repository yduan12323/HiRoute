# Completed fixed-route local-CS serialization comparison

Both fresh actual OD07 workers completed with independently checked road edges, event equations, native cleanup and identical input/direct-road-reference hashes. Independent read-only terminal audit passed: owned containment, identities, accounting and exact event recomputation. The original directed-road reconstruction was performed by each fresh worker and was not rerun during this final audit.

| Metric | Concurrent CS | Charge then activity at CS |
|---|---:|---:|
| Total trip seconds | 32497.725809385443 | 34257.673618564666 |
| Charge/activity overlap seconds | 1759.947809179223 | 0 |
| Vehicle stops | 2 | 2 |
| Charged kWh | 109.5629798400001 | 109.5629798400001 |
| Trip road distance km | 550.7238190000006 | 550.7238190000006 |
| Signed distance difference from selected-fastest reference km | 4.744465000000273 | 4.744465000000273 |
| Activity-start deadline slack seconds | 6209.415417787008 | 4449.467608607784 |
| Full physical feasibility | Passed | Passed |

Concurrent timing saves exactly 241885385058931547/137438953472000 seconds, approximately 1759.948 seconds or 29.33 minutes. This equals verified charge/activity overlap. Stops, saved selected trip legs, charge amounts, original query and repaired149 candidate domain are unchanged. Neither worker optimized or selected a new plan. This result concerns one known-DEV fixed route, not an optimized sequential planner or a population effect.

The direct road reference is freshly routed and its edge chain independently inspected in each worker. Both reference hashes match. Each required one additional origin-source computation. Its distance is that of the selected fastest-road path, not the shortest-distance route; direct EV energy feasibility is not asserted. Full exact rational measurements and edge-level raw evidence are summarized in summary.json. Complete raw worker outputs remain hash-bound in the local evidence inventory; this compact report does not redistribute private input snapshots.

Concurrent stage:23.13920812998549 wall seconds,23.913564792000003 conservative CPU seconds. Serialized stage:20.47620751798968 wall seconds,21.228572567 conservative CPU seconds. Total measured conservative stage charges45.142137359 plus120 declared orchestration allowance =165.142137359 /1460 reserved. These stage timings are computational replay costs, not travel times or solver speedup evidence. They exclude inter-launch gaps. Wait4 can double count waited descendants, per-process bounds are not aggregate cgroup guarantees, and historical development/tiny-test/reporting CPU is not part of this runtime reservation.

Admitted manifest97207058f36b0ff3144fc05f901f28a1d1a466c812c50d068c83a249482647eb. Original witness16aba96ef6700d1d073a558d0f6fa37f0b32eb10cce8c3ecd54b31648cc46457. No retry, holdout or graph modification occurred in the experiment; this report is its separate publication.

## Retained negative development history

Pure timing V1 was rejected for mutable identity acceptance; runtime V1 for insufficient predecessor authentication; runtime V2 for missing owned wait4/root checks and unbounded predecessor preflight. Corrected V2 pure timing and V3 controller versions passed review. V4 added only the separately checked direct-road reference. Earlier rejected code, reviews and the later native-router ownership fixture failure remain preserved. The earliest missing-package-path fixture failure occurred before durable fixture retention, and its auto-cleaned raw temporary receipt is unavailable; this limitation is explicitly retained. These fixture failures are not real-map outcome rows. Both admitted real-map rows completed without retries.

Original pending-review report remains unchanged as a historical predecessor. summary.json records its SHA, final audit SHA and exact accounting decimal165.142137359000003; displayed165.142137359 is rounded. This does not account for historical development/test CPU.

## Published evidence

- [Exact timing, physical-feasibility summary, accounting and negative history](summary.json)
- [Independent terminal audit projection](actual_audit.json)
- [Original evidence identities and final scoped review](PROVENANCE_AND_REVIEW.json)

The result compares concurrent activity and charging with charging followed by activity at the same CS stop on one fixed route. It is not a globally charge-first schedule, an optimized sequential planner, a solver-speed comparison or an optimality result. Both rows use screening OFF. Earlier [HIER energy-screen results](../energy_screen_ablation_20261016/README.md) and all prior failed and unknown outcomes remain unchanged.

All 114 retained evidence pins were rehashed during publication preparation. Machine paths and process IDs are omitted; exact rational observations and limitations remain. This compact report is not a standalone raw graph/replay bundle. No production source or default changes accompany it.
