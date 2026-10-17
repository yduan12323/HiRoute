# OD07 independent sequential-feasible transport comparison, 2026-10-17

One predeclared known-DEV gate completed all three stages with SUCCESS and verified
cleanup: independent sequential construction, fresh sequential physical replay,
and fresh replay of the preselected stored joint plan. No retry, expansion,
changed order, additional search or holdout was run. This closes a bounded
real-data feasible-comparison gap, not an optimal-planning or performance claim.

## Frozen domain and evidence

Execution source: `66c2f459a52d9d28c85d87967a26034d3d074dec`.
External manifest SHA256:
`fdcebf7012ffb873191fcee824625546bdc4b9a218066cef0f71d861e808b4f3`.
The case is `OD07_energy_and_scheduled_soc3_10`, with original 128 Sites plus all
21 eligible initial-floor-reachable chargers, total 149, and declared Hmax 37.
The original query, Site IDs, original-tree identity, source/native identities
and exact selected edges are retained. Fresh full-routing providers independently
replayed both plans under the current domain; no historical certificate was
accepted as new feasibility evidence.

Construction used `first_sequential_feasible`: proposal ordinal 0, one tested
proposal, one accepted plan, `generation_complete=false`. The existing generator
retains its concurrent CS clock/pruning; proposals are screened by actual
sequential charge-then-service physical replay. This is an independently
constructed feasible plan, not a sequentially optimized stream, finite-stream
minimum, lower bound or exact optimum. Construction did not use the comparator's
route or charge amounts to generate/select its candidate. Hashing the frozen
comparator bundle was authentication only. It happened to produce the same route
and charge vector as the earlier common proposal; that coincidence does not turn
this independent construction into optimization.

The comparator was fixed before launch as original OD07 first indexed arm,
`execution/arm-03/artifacts/arm/incumbent.json`, in the published recovery bundle.
Artifact SHA256: `2fa2444d2cfe5f485436756e643fb7d3fab0e38041d7ab43f9551212accf4f75`.
Its original source was `d2474ec6795c7be67509a727517b3ad04b19b93e`; the source
binding is reported separately, and the new native/physical replay revalidates
its route and charges. That stored joint plan previously received a 120-second
exact-search window; the new sequential plan stops at first feasibility. Thus
search effort and selection policies are unequal.

## Transportation quantities

All displayed numbers are rounded; [summary.json](summary.json) retains exact
rational quantities, full sequences, charge vectors and signed differences.
Every delta below means **sequential minus joint**.

| Quantity | Sequential feasible | Stored joint, freshly replayed | Delta |
|---|---:|---:|---:|
| J, seconds-equivalent | 35457.673619 | 26791.211474 | +8666.462144 |
| Physical elapsed, seconds | 34257.673619 | 25591.211474 | +8666.462144 |
| Physical elapsed, hours | 9.516020 | 7.108670 | +2.407351 |
| Q, charged energy, kWh | 109.562980 | 71.448109 | +38.114871 |
| H, vehicle stops | 2 | 2 | 0 |
| Selected-path distance, km | 550.723819 | 521.093942 | +29.629877 |
| Driving consumption, kWh | 88.115811 | 83.375031 | +4.740780 |
| Terminal battery energy, kWh | 39.447169 | 6.073078 | +33.374091 |
| Charging/service overlap, seconds | 0 | 2155.615330 | -2155.615330 |
| CS service start, seconds | 10039.168366 | 12879.445160 | -2840.276794 |
| CS service completion, seconds | 12739.168366 | 15579.445160 | -2840.276794 |
| CS window margin, seconds | 4449.467609 | 1609.190815 | +2840.276794 |

J equals physical elapsed plus 600 seconds per stop, hence each plan adds 1200
seconds. Elapsed includes travel and stop dwell; it is not driving-only time.
Distances follow the travel-time-selected directed road paths, not shortest-distance
paths. Service times are absolute query-clock seconds (query start is zero);
window margin is latest allowed start minus actual start. Both margins are
positive. Sequential uses CS at `4r:node/4683740340`, then C at
`4r:node/10039741536`; joint uses C at `4r:node/9004845675`, then CS at
`4r:node/11013731180`.

Q is energy charged into the battery, **not driving consumption or energy saved**.
Driving consumption is exactly distance/6250 under the original physical rate.
Initial 18 kWh + Q - driving consumption equals each independently replayed
terminal battery energy exactly. Different terminal energy explains much of the
Q difference. The 8666.462144-second elapsed difference (144.441036 minutes)
combines different routes, charge amounts, stop/service timing, overlap and prior
search effort. It must not be attributed solely to overlap. No causal benefit,
fair solver-speed ranking, global sequential optimum, SOTA superiority, full
D5/Go1/M5-D acceptance or whole-project completion follows from this single
known-DEV pair.

## Computational accounting and preservation

Whole worker-stage wall, including setup/hash/native compilation/repair/replay
and supervisor cleanup, was 103.865139493s construction, 11.697058754s sequential
replay and 11.321183766s joint replay; sum 126.883382013s. These are computational
costs, separate from physical trip elapsed. Controller process CPU was
5.466541180s, a distinct scope that must not be added as measured total CPU.
The fixed limits were wall/soft per-process CPU 240/240, 120/120, 120/120 seconds,
one core, numerical threads 1 and AS 8 GiB per process, with controller CPU 120s.
Aggregate worker-tree CPU was not measured; local construction diagnostics omit
some setup and cannot substitute for a whole-run CPU cost. All three slots remain
in the ledger; there were no failed, blocked, unknown or pending slots.

[evidence_index.json](evidence_index.json) indexes 57 UTF-8 files, and
[evidence_bundle.json](evidence_bundle.json) preserves their exact bytes through
UTF-8 round-trip. It includes all execution UTF-8 artifacts, native receipts and
generated C++ sources, ledgers, logs, the closed manifest, and the complete
predeclared historical comparator bundle/index/results/readme so the original
whole-bundle and artifact hashes can be reproduced. Native `.so` and road parquet
inputs are excluded. Every indexed size and SHA256 was checked after round-trip.

The earlier four sequential timeouts and the separate fixed-route 29.33-minute
overlap report are unchanged. This report is a new independent construction
comparison and does not relabel or replace those results. No production source,
default, input or numerical-policy change accompanies this report.
