# Real-scale DEV research: two limited segments

Latest status: the authorized second-segment limited DEV is complete; overall
research success and the 60s/95% target remain unestablished. The segment-one
sections below are retained as historical evidence. The later second-segment
section records the new domains, results and current decision boundary.

## Existing facts (segment one, historical)

This is delivery segment one of `HIROUTE_REAL_SCALE_DECISION_AND_PLAN.md`
(2026-10-31), starting from origin/main `0d02b2bfadd5be937b8fb2f355b2d4728dd61ee2`
in a new checkout. Overall research success is **not established**. The old
`flat`, `flat_bb` and `hier` diagnostics remain available.

The reusable Shandong archive contains 2,986,695 road vertices, 5,900,232 directed
edges, 4,725 source Sites and 4,198 attached Sites. The old raw-cache path is absent;
existing processed roads and attachments were reused without a province rebuild
or new map acquisition. Attribution: OpenStreetMap contributors / Geofabrik,
ODbL 1.0, snapshot 2026-10-16. The modeled graph is province-polygon clipped;
results do not cover routes outside that frozen graph.

Streaming the existing JSON into a 530,374,281-byte exact edge TSV took 64.10 wall /
63.69 CPU seconds and 15.95 MB observed RSS on the existing Linux server. This
map conversion is separate from solve accounting. The numerical workstation was
Apple M3, 8 physical/logical cores, 16 GiB RAM, macOS 27.2 arm64, Python 3.11.15.
Each query used a fresh process and one numerical thread, without affinity pinning.

The frozen four OD are Heze–Rongcheng, Liaocheng–Weihai, Dezhou–Rongcheng and
Heze–Yantai. Municipal endpoints bind to nearest already attached Sites. The
candidate rule is a 50 km corridor, eight progress strata, unique access anchors
(excluding endpoint anchors), capability preference and deterministic detour/ID
ordering. Corridor, anchor deduplication and N truncation are **experimental
restrictions**, not proven full-province reductions. The unchanged model has
18 kWh initial energy, 60 kWh capacity, 6 kWh reserve and 0.16 kWh/km consumption.
Schedule windows use 2/5–7/10 of direct driving time and D=2700s.

## Algorithm changes

`exact.scale.solve_scale` exposes `flat_bb_strong` and `scale`. Both hold exact
post-stop families with complete histories, add only the next drive/stop and
keep terminal drives separate. Empty physical families stop expansion; terminal
infeasibility does not. No cross-history dominance or additional reducer is used.
A constant terminal-face summary preserves primary/secondary infima, attainment,
full `(J,Q,H,Pi)` comparison and a winning witness without retaining all terminals.

Both methods use the same deterministic feasibility beam, exact C/CS kernels,
road provider and singleton relaxation. Seed generation and independent physical
replay are charged. Only an actual executable J supplies U. Positive h+lambda
implies every primary-tie/improving plan has `H <= floor(U/(h+lambda))`; equality
depth remains. A missing seed is not an infeasibility proof. Unrestricted mode has
no diagnostic N/H/plan-count cap. Resource stops report UNKNOWN and preserve a
verified feasible record. Explicit diagnostic caps remain labelled.

For a physical piece tau(E), k past stops and at least one future action:

```
L = inf_E [tau(E)-t0 + T_R + h
           + max(mu_min*max(0,reserve+e_R-E), remaining_service*D)]
    + lambda*(k+1).
```

Past time is bounded by tau. Directed shortest-road time/length bound future
driving time/energy, independently. Necessary purchased energy and the smallest
charging slope bound charging time. Driving and overhead cannot overlap
charging/service in this model; charging and service may overlap, hence their
max. Additional stops, waits and window restrictions are relaxed. Exact affine
endpoints and the charging/service kink suffice for the infimum. Open endpoints
are safe lower bounds and never incumbents. Pruning requires strict `L > U`.

Regions sort by directed road-progress features, with Site ID only breaking ties.
Per-effect counts, masks and metric extrema are built once. Directed triangles
give `d(a,s)>=max(0,d(o,s)-d(o,a),d(a,z)-d(s,z))`; independent extrema safely weaken
this bound. Internal legality, bound and refinement queries do not scan members
or construct all-candidate action sets. Leaf materialization uses the exact
selected inbound leg. Strong Flat-BB receives the same information as singleton
records and does not build internal Region nodes. Different leaf/cache order is
not claimed as a pure batching effect.

The road index builds once per process, with two bounded scalar workspaces and
bounded leg caching. Its compact backend scales exact rationals by their common
denominator and uses arbitrary-precision integer Dijkstra. Greedy shortest-time
DAG reconstruction chooses node tuple, then edge-ID tuple; actual length is an
attribute. The older binary64 native router has different ties and is not used.
Frozen selected legs are a separate closed-world provider, never rerouted as an
ordinary graph. Restricted providers must expose every query anchor; missing
projection entries cannot silently become unreachability proofs.

## Real results

The first input version mistakenly counted S-only Sites in energy-only N.
Those six ingress rows remain in `real_scale_results.jsonl`, with requested and
actual qualified counts. SD01 requested 16/32 had only 10/17 legal charging Sites;
they are not N16/N32 energy scale evidence. Both methods exactly completed those
energy domains in 58.74/59.05s and 85.35/86.05s, using three positive charges.
Their 32-Site schedule variants timed out. A necessary corrected 32-charger domain
was subsequently run: both methods timed out at 120s with the same three-charge seed.

Scenario qualification now precedes truncation. Frozen 50 km energy pools contain
55/93/46/76 unique C-capable anchors, versus 334/930/275/488 schedule-qualified
anchors. Thus SD01/SD03 energy N64 and every energy N128 are unavailable. These
are explicit candidate-rule failures, not algorithmic infeasibility. No corridor
was expanded to fill rows.

The N64 main pilot comprises eight predeclared OD/scenario families:

| OD | Scenario | Strong Flat-BB | Scale | Positive charges in returned route |
|---|---|---:|---:|---:|
| SD01 | energy | input unavailable (55) | input unavailable (55) | — |
| SD01 | schedule | UNKNOWN120s | UNKNOWN120s |3 |
| SD02 | energy | UNKNOWN120s | UNKNOWN120s |2 |
| SD02 | schedule | UNKNOWN120s | UNKNOWN120s |2 |
| SD03 | energy | input unavailable (46) | input unavailable (46) | — |
| SD03 | schedule | **exact 106.09s** | **exact 108.94s** |2 |
| SD04 | energy | UNKNOWN120s | UNKNOWN120s |2 |
| SD04 | schedule | UNKNOWN120s | UNKNOWN120s |3 |

Per method: **1/8 exact completion at 120s**, five timeouts and two input failures;
1/6 among executable input domains. Exact completion within 60s is 0/8. All six
executable domains produced independently verified feasible routes within 59.8s,
but that is 6/8 of the declared cohort, not a 100% overall success claim. Censored
runs are not dropped and no completed-subset p95/median is presented as overall.

The exact N64 SD03 route is 627.620 km, with two positive charges and the same full
key in both methods. N is the 64 declared scenario-qualified Sites; one is safely
excluded by a directed road-unreachability proof, leaving 63 reachable. All relevant
depths remain covered. Across valid main inputs the independent shortest-distance
capacity bound requires at least two charges. Three-charge returned routes are
not labelled capacity-necessary. No four-charge layer is established.

The N128 SD01 schedule pair (128 declared, 127 reachable) both timed out at 120s,
retaining the same three-charge seed obtained at approximately 75s. Energy N128
is an input-domain failure. There is no N128 exact-completion claim.

The complete table has 33 rows: seven attained results, 17 timeouts, six input-domain
failures and three diagnostic infeasibility results. All 24 rows returning routes
have independent physical replay. Raw input/output histories stay in the ignored
local DEV directory; the small result table is the committed deliverable.

## Attribution and verification

In the completed N64 pair, both methods perform 314 exact transitions, 147 terminal
attempts and 716 leaf-route requests. Strong Flat-BB makes 9905 singleton bound
queries; Scale makes 6110 summary queries. OPEN peaks are 9210 versus 2259. This
supports cheaper grouping/OPEN management, **not extra exact pruning or an observed
wall-time gain**. Routing settles approximately 322/324 million vertices and
dominates total time. Search order and cache resumption can affect that work.

A separately declared SD02 energy N16 ablation shares the same actual seed and
60s allowance. With future-completion terms, Scale exactly finishes in 47.67s
(181 transitions,123 terminal attempts). Disabling future driving/energy/
charging-service terms, while retaining accurate prefix time and stop costs,
times out at 60s (1749 transitions, 1254 terminal attempts, partial counters).
Its two-charge route remains merely feasible; the completed variant finds a
three-charge optimum. This is evidence for the shared bound, not hierarchy.

The original Flat-BB / Strong / Scale comparison on SD01 energy N4,H=2 reports
infeasible **within that diagnostic cap** in 5.48/9.19/9.30s. All have no feasible
seed there. Strong infrastructure/seed preparation adds overhead on this small
domain. This is not unrestricted real-trip infeasibility or a large-domain
performance comparison.

Loaded-query time includes candidate/schedule preparation, required routing,
seed, search and witness work. Cold graph/index building/loading is separate,
reported per row, with completed compiler-child CPU included in the corrected
runner. Phase timers are exclusive; routing/operator timers are nested and
must not be added to phase totals. Resource-limited counters are partial.
The full cohort's largest process peak is 1.796 GiB; the largest query-extra
measurement is 0.592 GiB. Index residency, process peak and query-extra are
separate columns, under an 8 GiB query target and 2 GiB host-headroom guard.
Historical ingress excluded early preparation caches from its solver delta;
the table uses a conservative process-high-water minus loaded-RSS bound instead.

The existing OS supervisor is retained, with a loaded-query signal watchdog.
One initial Strong ingress supervisor lost its control connection: completed
solver output, CPU/RSS and physical replay survive, but aggregate host samples
do not. That valid row was not repeated. Subsequent supervisors were durable.
Experimental accounting ends at **3200.99 CPU seconds**, including a conservative
1000s allowance for development/earlier ingress, against 28800s; map export is
separate. No query limit or budget was increased after failure.

Final local verification: 104 tests, zero failures/errors/skips, with actual native
library loads. Coverage includes bound admissibility, disjoint coverage, energy/
time cases, equality, primary/secondary unattainment, empty prefix versus terminal
failure, time shifts, directed/tie routing, old-solver parity, one finite tiny
independent REF solve, a six-charge unrestricted correctness fixture and resource
UNKNOWN. The real graph is never fed to REF simple-path enumeration. Independent
physical replay is not an independent real-domain optimality certificate.

The corrected scenario-qualified rows use code checkpoint `fde8205`; the labelled
historical mixed ingress preceded it. Final input guards reject nonfinite
resource limits and incomplete provider projections; actual pilot providers
already exposed all aliases, so these guards do not alter the measured domains
or require re-solving them. The final checkpoint cleanup only preserves already
verified route payloads.

## Incomplete work

This is **LIMITED segment-one evidence**, not overall research success. The 60s /
95% target is not met; N128 exactness and a real four-charge layer are not
established. N256/full-qualified-domain comparisons, external exact baselines,
application-value comparisons and frozen independent holdout were not run.
No SOTA, full-province optimum or cross-region generalization is claimed.

The existing province has 168 attached unique C-capable anchors under the declared
selection rule. Static geometry suggests approximately 60 km corridors would
support energy N64 for all four OD, and 126 km would support N128, without new
raw data. These are future candidate-policy proposals only. Boundary clipping
and the validity of any wider workload would still need review.

## Next decision

Keep Strong Flat-BB as the mandatory fair baseline and Scale as an experimental
batching path; this pilot does not justify a successful hierarchy claim. The next
research decision should address exact-road-query/seed cost, candidate-rule scope
and novelty before segment two. No second architecture, additional experiments,
holdout or automatic merge was started.

Reproduction requires C++17 and Boost.Multiprecision headers for the optional
compact backend, plus the existing processed inputs. Generate a fresh preflight
with `tools/real_scale_inputs.py preflight`, stream the graph with its
`export-edges` command, then run `tools/run_real_scale_pilot.py --preflight-only`.
The runner defaults to the declared `pilot_matrix`; `--domains 64`, `--ablation`
and `--diagnostic` select its scoped workloads.
Use fresh output paths and the same config. These are reproduction instructions,
not a request to repeat valid rows. The deliverable remains a draft PR for review.

## Authorized second segment: road queries and feasible seed

This segment starts from merged main `0b61d1ff3d9715627e1a56fd8af7c886b9837b80`
(PR #24; main CI 41195558122 passed). Segment-one rows above remain historical
and are not rerun. The approved scope is exact road/seed cost, wider Shandong
workloads, limited DEV, then a draft PR and a main-experiment decision. No main
experiment or holdout is authorized here. The prior server source-upload denial
remains in force; all new work executes locally, with the existing OS supervisor.

The optional `landmark_astar` profile reuses the same arbitrary-precision,
integer-scaled directed graph, four scalar feature maps and selected-leg rule.
It pins two **complete** time trees `a(u)=d(O,u)` and `b(u)=d(u,D)`, sharing them
with the scalar LRU where possible. Pair work has a separate reusable workspace;
its residency, pinned trees, queues, query allocation and cold index are counted.
This is a memory/work tradeoff, not a free pair table. Precomputation remains
O(V+E) per landmark, with actual Dijkstra cost included in loaded query time.
Length relaxations remain independent shortest-distance metrics.

For the reverse search from pair target t toward source s, use
`h(u)=max(0, a(u)-a(s), b(s)-b(u))`. The a term is enabled only when a(s) is finite;
then a-unknown vertices can safely be excluded because s cannot reach them.
The b term is enabled only when both b(s) and b(t) are finite; every reverse
reachable u then reaches t and D, so b(u) is finite. Disabled terms are zero.
For an original edge v->u of time w, directed triangle inequalities give
`a(u)-a(s) <= w+a(v)-a(s)` and
`b(s)-b(u) <= w+b(s)-b(v)`. Zero is also consistent. Thus their maximum is a
consistent reverse potential and lower-bounds every u->...->s reverse path.
All arithmetic remains exact. Search continues through **equality** after s
settles, stopping only above its exact distance. Every vertex on an optimal
s->t suffix is therefore settled. Greedy reconstruction on tight edges then
preserves the original `(time, node tuple, edge-ID tuple)` rule, including
parallel edges and actual selected length. Positive times prevent tight cycles.
Queries to the pinned D reuse its complete tree. Missing paths remain missing;
frozen selected legs are never rerouted as a graph. Interrupted native work is
discarded; preparation can be repeated explicitly, without using partial trees.

The optional rank-lazy seed retains only the original best four next states
while generating them. Its unchanged rank is `(pending service, to-D time,
earliest tau, full plan)`. The first two coordinates are known before an exact
route or transition. Once four states exist, an action can be skipped only when
those two coordinates are **strictly greater** than the current fourth state's.
That cutoff can only improve as candidates arrive. A skipped state can never
enter the final beam; equality still runs exact transitions and compares the
remaining coordinates. Induction over depths therefore preserves the full beam
order and first executable seed of the original scan. This pruning is confined
to seed generation. Exact search, histories, lower bounds, attainment/full key,
relevant-depth proof and the absence of a seed-as-infeasibility inference are
unchanged. Strong Flat-BB and Scale receive identical profile and inputs.
The seed beam width has an explicit strictly-positive-integer API contract in
both modes: zero, negatives, booleans and nonintegers are rejected before index
construction and by the direct seed helper. The declared width four is unchanged;
a focused regression covers both modes and width one. No DEV rerun is needed.

### Frozen limited validation, before numerical execution

`configs/real_scale_road_seed_dev.json` declares ten new method/profile rows:

| Domain | OD / scenario | Corridor half-width | Candidate domain | Profiles/methods |
|---|---|---:|---|---|
| D01 | SD01 energy | 60 km | first 64 of 83 eligible C anchors | legacy Strong; route-only Strong; optimized Strong and Scale |
| D02 | SD03 energy | 60 km | all 64 eligible C anchors | optimized Strong and Scale |
| D03 | SD03 schedule | 60 km | first 128 of 368 eligible anchors | optimized Strong and Scale |
| D04 | SD02 energy | 126 km | first 128 of 143 eligible C anchors | optimized Strong and Scale |

The unchanged geometric/capability policy gives eligible energy/schedule counts
at 60 km of SD01 83/649, SD02 101/959, SD03 64/368 and SD04 84/515; at 126 km,
154/1453, 143/1311, 128/1064 and 156/1469. Widths were selected from static
availability, before solver outcomes. Wider corridor and N truncation are
workload definitions, not safe reductions or province-wide optimality claims.
D02 removes N truncation only **inside its declared corridor**. The physical
model is unchanged; no smaller battery or larger consumption is used.

The runner measures selection/manifest construction as preprocessing, reuses the
existing exact TSV and launches fresh guarded workers sequentially. Loaded query
preparation, landmarks, seed, search and witness replay share a 120s hard limit;
60s remains the main threshold. One numerical worker/thread, 8 GiB process cap,
8 GiB query-extra cap and 2 GiB host headroom apply. Carry 3200.991448329 CPU
seconds, add a conservative 60 CPU seconds for second-segment local development
microchecks before these runs, then charge every observed worker CPU including
cold index/compiler. This remains within the original 28800 CPU-second envelope.
No budget extension, extra matrix, real-graph simple-path REF or failed-row
replacement is permitted by this configuration. No segment-one result supplies
an incumbent or selection criterion.

### Second-segment results and attribution

The frozen ten rows ran once on the same local M3/16 GiB host at numerical source
checkpoint `b912391`. [The result table](road_seed_dev_results.jsonl) retains all
rows, exact keys, seed keys, physical-ledger summaries, timers, work and resource
counters. Its four candidate-domain digests were checked against the saved
manifests: every profile/method within a domain has identical candidates and
endpoints. All seed keys agree within their domain. Every attained Strong/Scale
pair has the same full optimum key. There were **7 attained rows and 3 time-limit
UNKNOWN rows**; all ten have independently physically replayed feasible witnesses.
No timed-out result is labelled optimal, and no valid segment-one row was repeated.
Final native input guards also reject NUL-containing C-interface arguments and
control characters in TSV identifiers, avoiding silent C-string truncation.
A post-run streaming audit found none in all 530374281 input bytes (2.706 wall /
2.673 CPU seconds, separate input QA, no solver). The valid measured query
inputs and numerical routing/seed behavior are unchanged; cold-load timings
remain explicitly those of checkpoint `b912391`.

| Domain/profile | Strong status / loaded seconds | Scale status / loaded seconds | First feasible Strong / Scale | Qualified / road-reachable N |
|---|---|---|---|---|
| D01 legacy | UNKNOWN / 120.01 | not declared | 39.90 / — | 64 / 64 |
| D01 route-only | attained / 97.77 | not declared | 5.85 / — | 64 / 64 |
| D01 optimized | attained / 95.35 | attained / 91.79 | 4.13 / 4.17 | 64 / 64 |
| D02 optimized | attained / 9.38 | attained / 9.22 | 3.75 / 3.76 | 64 / 63 |
| D03 optimized | attained / 49.13 | attained / 46.05 | 4.67 / 4.65 | 128 / 127 |
| D04 optimized | UNKNOWN / 120.07 | UNKNOWN / 120.06 | 4.24 / 4.31 | 128 / 125 |

Loaded times include routing preparation, seed, search and independent witness
checks; small time-limit overruns are exception cleanup, not extended search.
Cold index/compiler wall and CPU are separately recorded in every row. Native
routing, landmark and phase timers overlap and **must not be added**. Counts of
qualified Sites precede safe directed reachability exclusion. For D02, all 64
qualified corridor Sites were admitted, and exactly one was safely unreachable;
this is a complete corridor-domain result, not a province-domain result.
The preflight also describes undeclared OD/scenario combinations at each N;
its availability notices for those combinations are not extra solver rows.

For the two optimized methods, each attains **3/4 domains within 120s and 2/4
within 60s**. All eight optimized rows find a verified feasible plan within 4.68s.
The independent shortest-road-distance energy screen requires at least two
positive charges in all four domains. Actual best witnesses are D01 three
charges / 784.871 km, D02 two / 616.734 km, D03 two / 627.620 km and D04 two /
640.819 km (D04 only best known). The charging amounts are positive in the table.
D01 already has a feasible two-charge plan: its third optimal charge improves
the objective and is **not** physically necessary for feasibility. Exact search
visits depth five on D01 and four on D03, but this is not evidence for a real
four-charge optimal witness. Derived relevant depth remains 38/31/32/31 for
D01/D02/D03/D04, with no imposed depth truncation.

The controlled D01 road-only profile preserves the original 84 seed attempts and
identical seed key. Seed phase time falls from 34.99 to 2.26 seconds; including
all loaded preparation and physical replay, first feasibility falls from 39.90
to 5.85 seconds. The road profile includes pinned landmark reuse, elimination of
repeated scalar-tree eviction and exact A*, so these observations do not isolate
the heuristic from caching. The legacy row is censored at 120s; it is not an
exact total-runtime comparator. It settles 368.12 million scalar vertices while
reaching 173 transitions. Road-only completes 3525 transitions, with 11.76 million
scalar plus 117.59 million A* vertices settled. This shows a useful routing-cost
change, not a fixed-work wall-speed ratio or a new lower bound.

With the same new routing profile, rank-lazy seed reduces D01 seed attempts
84->20 and skips 64 strictly losing candidate routes, preserving the seed key.
Seed phase becomes 0.727 seconds and first feasibility 4.13 seconds. Full Strong
runtime changes 97.77->95.35 seconds: most of the end-to-end gain is routing,
and many skipped seed pairs are later needed by exact search. No separate
seed-only or full-factorial ablation was added.

On the three completed optimized domains, Strong and Scale have identical
exact transitions, terminal attempts and leaf routes: 3525/1254/7809 on D01,
106/33/152 on D02, and 518/214/1432 on D03. OPEN peaks are 72515->25176,
1930->478 and 24535->3883. Bound queries are 80256 singleton vs 64586 grouped,
2079 vs 1221, and 25937 vs 11123. This is batching/queue reduction with modest
single-run timing differences, **not stronger lower-bound or exact-expansion
pruning evidence**. Scale's RSS is not consistently lower. On timed-out D04,
Scale advances 1575 transitions vs Strong's 1514, with different ordering/work;
both retain the same best feasible full key. No hierarchy-win claim is supported.
Old/new geographic selections need not be supersets after deterministic N
truncation; segment-one timings are not same-domain performance controls.

Numerical worker CPU, conservatively including cold graph/compiler work, totals
**846.521758 seconds**. With carried 3200.991448329 and the predeclared 60-second
local-development allowance, charged solve/limited-REF accounting is
**4107.513206329 / 28800 CPU seconds**; **24692.486793671** remain. Selection and
manifest construction took **0.4011 wall / 0.3994 CPU seconds**, separately
reported; the existing TSV was reused without a new export/download. Maximum
observed process RSS was **2.327 GiB**, query-extra RSS **1.122 GiB**, and minimum
observed host available memory **3.059 GiB**, above the 2 GiB headroom guard.
There were no host/process memory stops, lost supervisors or substituted rows.

Local focused validation passed **109 tests** with actual native execution,
including 20 random tiny directed graphs checked against independent simple-path
enumeration, Unicode/parallel ties, exact rational weights, incomplete landmark
components, interrupted A* recovery, unchanged seed/full-key parity, equality,
unattainment, relevant depth, bound admissibility, and workload/resource guards.
The isolated wheel CI now requires native roads rather than allowing that test
to silently omit execution on a machine without C++17/Boost. This verification
requires the workflow's explicit Ubuntu C++/Boost 1.83 header installation; the
first isolated attempt correctly failed when those headers were absent. No
numerical solver or experimental row changed to address that environment issue.
Code verification
is separate from a main research experiment; the real graph never enters REF
simple-path enumeration. Final CI status is tracked on the draft PR.

Reproduce from a clean checkout with Python 3.11, C++17 and Boost.Multiprecision:

```sh
PYTHONPATH=src:tools python tools/run_road_seed_dev.py \
  --config configs/real_scale_road_seed_dev.json \
  --input-root /path/to/existing/real-scale-dev \
  --output-root data/road-seed-fresh
```

`input-root` must contain the existing exact `real-scale-road.tsv`,
`shared-sites.json` and `site-bindings.json`. `--preflight-only` checks availability
and host guards without solving; use a distinct output directory for the actual
run. The runner refuses an existing output directory, freezes the declared ten
jobs and uses the existing OS supervisor with one numerical worker/thread.
No graph source or solver source is uploaded to the previously denied server
location (`dy@202.112.148.131:/home/dy/HiRoute/real-scale-pilot-20261031/native-smoke`).
That prior source-disclosure denial was not retried or bypassed; the authorized
local path provided the results above.

### Remaining research boundary

This segment completes the approved road/seed implementation and limited DEV,
**not the entire taskbook**. The 60s/95% criterion is not met; energy N128 remains
UNKNOWN, and a real four-charge optimal case, larger/full-province domains,
external exact baselines, application-value comparisons, novelty validation,
main-scale matrix and independent frozen holdout remain unestablished. Wider
corridor feasibility does not validate a province-wide candidate policy.

Keep Strong Flat-BB as the mandatory fair baseline; keep Scale as the optional
batching comparison. The new road profile materially improves early feasibility
and makes this N128 schedule workload exactly runnable, but D01 still exceeds
60s and D04 still cannot finish within 120s. The next decision is whether these
limits justify a fixed, explicitly scoped main experiment and what novelty or
additional algorithmic evidence it must test. The current branch stops at a
draft PR with CI; no main experiment, holdout, further architecture, automatic
merge or resource purchase is started.

## D04 limited cost diagnosis (after PR #25)

PR #25 was squash merged at `2495ba5f41768747973f92571b8eb2011d319535`.
This continuation diagnoses the existing D04 / SD02 energy N128 timeout only;
it does not authorize an architecture, optimization campaign, main experiment,
holdout, new geography, changed physics or server source upload. Main merge CI
is monitored separately. Historical rows and their `b912391` provenance remain
unchanged.

### Existing evidence, before any new diagnostic

| Existing D04 120s row | Strong | Scale |
|---|---:|---:|
| Native A* seconds (inside native selected-leg seconds) | 69.454 | 72.568 |
| Native selected-leg seconds | 88.677 | 93.274 |
| Scalar-tree preparation seconds, disjoint in this profile | 3.368 | 3.427 |
| Remaining loaded time outside those native categories | 28.023 | 23.362 |
| A* pair requests / settled vertices | 1417 / 200531101 | 1539 / 209934551 |
| Selected-leg requests / Python cache hits / entries | 3096 / 1598 / 1497 | 3531 / 1902 / 1628 |
| Leaf requests / transitions / nonempty children | 2492 / 1514 / 1019 | 2852 / 1575 / 1078 |
| Late exact-leg bound rejections / empty children | 977 / 495 | 1276 / 497 |

The selected-leg timer includes A*, road witness reconstruction/JSON and native
resource callbacks; these nested timers cannot be added. Cached legs never reach
the 4096-entry capacity, and that cache is not cleared on timeout: there is no
leg-cache thrashing evidence. Mean A* settled work is about 141518/136410 vertices
per pair, compared with 150305 on completed D01 and 89744 on completed D03.
The D04 aggregate cost comes from many costly pairs, not just the seed (0.79s)
or C/CS propagation (5.64/6.15s). A* alone already exceeds 60s on the unfinished
120s trace, so eliminating Python overhead alone cannot meet the target on that
same work. This does not measure how much work remains for an exact proof.

About 59.1%/62.2% of requested leaves do not create a nonempty child, through late
bound rejection or an empty exact family. Counts alone do not reveal whether
those leaves consume most routing time. The logs also lack per-target reuse,
route-work tails, geometry association and the Python decode/bound split. These
are the specific remaining attribution questions; no algorithm change is made
from aggregate timings alone.

### Predeclared minimal diagnostic

`configs/d04_cost_diagnostic.json` freezes exactly **one** instrumented Strong
Flat-BB run on the identical D04 candidate-domain digest
`2196503277068b59652e84ab54729c25e8aa8f1705b329e09df451a5e2b0e4e0`, with the same
optimized routing/seed profile and unchanged model. The loaded hard limit is
**60s**, cold allowance 180s, one numerical worker/thread, 8 GiB process/query
extra caps and the existing 2 GiB host-headroom guard. Carry 4107.513206329 CPU
seconds and precharge a conservative **30 CPU seconds** for diagnostic development
and microchecks; add the actual fresh worker CPU including compiler/cold load.
There is no retry, second method/query, extra time or new performance-matrix row.

The optional worker hook observes existing calls only. It measures selected-leg
wall time plus native counter deltas, pre/late completion-bound work, region
travel relaxation, prefix propagation, terminal work excluding selected legs,
scalar/landmark preparation and incumbent callback. Per-request records associate
cost with cache hit, late rejection, empty/nonempty child, target reuse and static
geometry. Counter-poll/adapter overhead is separately measured. The profile does
not alter keys, bounds, cache policy, provider checks, search order or physical
transitions. A strict `>` late-cutoff classification preserves equality. Tiny
end-to-end regressions check complete keys, seeds, metrics, leaf-flow accounting,
patch restoration and native callback propagation.

The profiled, interrupted trace is diagnostic evidence only. Its wall time and
throughput cannot be compared with an uninstrumented method as performance
results. The unprofiled 120s Strong/Scale rows remain the paired evidence; any
proposal derived from the sampled prefix must state that limitation.

### Observed diagnostic result

The one profiled worker ran at checkpoint `4851ce292a283c5e2dc78cc71c416ffaaa18e5b3`.
It stopped at 60.060 loaded seconds as **UNKNOWN**, keeping an independently
verified two-positive-charge plan with the same best-known full key as the
original D04 rows. There was no retry or extra numerical query. The replayed
plan is 640.819 km; first feasibility was observed at 4.293s, a diagnostic
observation rather than a new performance comparison.

[The small diagnostic record](d04_cost_diagnostic.json) preserves the worker row,
measured buckets, leaf outcomes and the offline work sketch. Raw per-call records
remain in the ignored local run directory. Profile accounting closes exactly:
823 leaf requests = 113 late cuts + 274 empty families + 435 nonempty children
+ one interrupted request; 709 transitions = 274 + 435. Native event sums match
final native counters, and there are no source/target association mismatches.

| Disjoint measured loaded-window category | Seconds | Share |
|---|---:|---:|
| Native A* including its resource callbacks | 36.153 | 60.2% |
| Other native selected-leg work | 11.279 | 18.8% |
| Python/interop selected-leg remainder | 4.724 | 7.9% |
| Landmark and scalar preparation | 3.428 | 5.7% |
| Pre/late completion bounds and region travel relaxation | 2.141 | 3.6% |
| Exact prefix transitions, including seed transitions | 1.572 | 2.6% |
| Terminal remainder, incumbent callback, measured route-adapter overhead and other | 0.765 | 1.3% |

The first three rows total **52.155s / 86.8%** of the 60.060s observation window.
Other native leg work combines tight-DAG reconstruction, native JSON construction
and resource callbacks; Python/interop combines decoding, Fraction/path object
materialization, cache/check and call overhead. This instrumentation does not
isolate those subcomponents. Measured route-counter/adapter overhead was 0.033s;
other observer overhead is not independently isolated. The window begins just
after index construction, 0.0004s before the runner's loaded timer. The final
interrupted call includes cleanup. No nested native timer is counted twice.

Of 50.489s of search-leaf selected-leg time, **27.480s** ended in an empty exact
family and **9.386s** in a late bound cut: together **73.0%**. Nonempty children
account for 13.575s. Thus bound *evaluation cost* is small, while pre-route bound
*quality* still leaves costly requests that prove unproductive only after exact
routing. This does not by itself construct or validate a stronger admissible
bound.

Geometry does not support a corridor-cut shortcut: forward/equal-progress pairs
with both endpoints inside the original 50 km corridor consumed **96.3%** of leaf
routing time. Backward-inner pairs used 0.247s; pairs involving a wider-corridor
endpoint used 1.634s. Those are descriptive labels, not safe reductions. Excluding
wide/backward candidates would change the workload and does not address the
observed dominant work.

Completed leaf A* requests involved only **11 sources and 92 targets**. The five
hottest sources account for **74.5%** of leaf A* time, with 62–74 distinct targets
each (one other group has 82). Individual hot sources repeat 12.4–17.5 million
settled vertices over different pairs, versus 2.987 million vertices in the whole
graph. The origin already has its exact forward time tree: its 82 leaf pairs
settle 138248 vertices in total, while non-origin source groups are much more
costly. This comparison is mechanistic, not a controlled speed ratio: the pairs
differ. The pair cache correctly avoids repeated identical pairs, but does not
share the work of different targets from the same source.

A purely offline sketch examined an online trigger: after cumulative uncached
A* edge relaxations for a source reach the graph's 5900232 edges, charge a full
forward-tree build and keep one/two sources by LRU. This executes **no routing
algorithm** and predicts **no runtime or optimality**. With two entries, the
observed trace would request nine builds and subsequently revisit 245 pairs
whose old A* work totals 62.253 million settled vertices / 118.851 million edge
relaxations / 21.925 measured seconds. Nine whole-graph trees have an upper work
charge of 26.880 million vertices / 53.102 million edges. The canonical paths of
those later pairs contain 399735 vertices in total, but the full equality DAG
can be larger. One entry gives ten builds and addresses 192 later pairs. These
figures expose reuse, **not net saved work/time**: actual tree costs, remaining
reverse equality-DAG work, priority queues, eviction and memory effects are
unmeasured. They cover only the profiled prefix of an unfinished search.

The diagnostic worker consumed **68.720242 CPU seconds**, including compiler and
cold loading. Add the predeclared 30-second development allowance to the carried
4107.513206329: charged solve/limited-REF accounting is now
**4206.233448329 / 28800 CPU seconds**, leaving **24593.766551671**. Selection
preparation was separately 0.0474 wall / 0.0460 CPU seconds. Observed peak process
RSS was **1.885 GiB**, query-extra RSS **0.698 GiB**, and minimum host available
memory **2.913 GiB**. All original guards remained active. The main merge at
`2495ba5` passed [CI 41275042365](https://github.com/yduan12323/HiRoute/actions/runs/41275042365).
Focused local checks passed 31 tests, including actual native observation,
callback/resource forwarding, complete-result/seed/metric parity, equality,
leaf-flow closure, patch restoration, early-stop summaries and offline LRU work
accounting. The new draft PR tracks its own clean installed-wheel CI.

### Bounded next algorithm decision

The next change worth testing is **sharing a complete forward time tree for a
reused active road source**, using the existing exact Dijkstra index and the
existing two-entry scalar LRU after feature preparation. Use the fixed online
edge-work trigger above, not a hardcoded list of profiled Sites or an optimal
answer. On a cache hit, supply `h_s(u)=d(s,u)` to the current reverse A*. For an
original edge v->u, `d(s,u)<=d(s,v)+w(v,u)`, so this is a consistent reverse
potential; vertices unreachable from s cannot lie on an s->t path. Continue the
full equality contour and retain the existing greedy tight-DAG node/edge tie
reconstruction. The tree is road-query reuse only: histories and post-stop
families remain separate, and actual selected length/witnesses still come from
the same canonical road path.

This is a bounded modification to the current exact index, not another routing
architecture. Count dynamic tree construction inside the query, preserve both
resource guards, cap at two scalar workspaces, and give Strong/Scale the same
policy. A future implementation must first prove/test exact directed/tie parity,
interruption and cache eviction, then use only a predeclared D04 Strong/Scale
comparison at the existing limits. It must not assume zero reconstruction work,
feed the recorded optimum into a seed, or claim a 60s proof from this trace.

Do **not** spend the next step on changing the seed, C/CS kernel, geographic
selection or stop/depth semantics. Stronger pre-route bounds remain a later
possibility; this diagnosis has not validated one. No source-tree promotion,
algorithm optimization, wider experiment or holdout was executed here. The
current task stops at the diagnostic draft PR and this concrete proposed step;
D04 remains UNKNOWN and overall taskbook success remains unestablished.

Reproduce the single diagnostic, with a new output directory and the existing
input archive, using:

```sh
PYTHONPATH=src:tools python tools/d04_cost_diagnostic.py \
  --config configs/d04_cost_diagnostic.json \
  --input-root /path/to/existing/real-scale-dev \
  --output-root data/d04-cost-fresh
```

`--preflight-only` never launches a solver. A normal run writes `summary.json`,
the guarded worker result, measured profile and raw request records; summarizing
persisted records never launches another query. The default pilot path is
unchanged when `cost_diagnostic` is absent. The previous server upload denial
remains in force and was not retried or bypassed.

## Adaptive source-time reuse: authorized bounded implementation

This continuation starts from merged main
`968a9e729dce43dc87ae6c92f5e6c4730c6ee984` (PR #26). Main and its push CI are
verified/monitored independently from the new branch. The user authorized this
single exact-index change and ordinary development/verification follow-through;
no holdout, new architecture, physics change, wider geography or server upload
is included.

`NativeRoadIndex(..., source_tree_reuse=True)` is opt-in and requires the existing
`landmark_astar` mode and **two-slot scalar LRU**. For a non-origin physical
source without a complete forward time tree in those slots, count already
performed uncached old-potential A* edge relaxations, saturating at the graph's
edge count. Once that work reaches one graph edge count, build a complete forward
time tree **on the next needed pair miss**, not speculatively after the last
request. Existing paid forward trees may be reused. O already has its exact
pinned forward tree and does not trigger a redundant build; requests to pinned
D and cached/self legs retain their existing shortcuts.

The same `Graph::tree` exact Dijkstra constructs the tree. It replaces the scalar
LRU entry before allocating the new workspace; no additional persistent source
cache or source pin is created. A shared reference protects the selected tree
for the current pair only. Eviction can cause later recomputation, counted in
the same way. Construction and partial interrupted work are charged inside the
loaded query and selected-leg timer. Any native query failure clears distance
workspaces, pinned landmarks and observed-source work so partial trees cannot
silently survive. Scalar/A* vertices and edge scans, source build attempts,
completions, hits, evictions and time are reported. Dynamic build time overlaps
the native selected-leg/scalar timers: **do not add those nested timers**.
Total native settled work is `scalar_settled_vertices + astar_settled_vertices`;
source-build vertices are a subset of the scalar count, not an extra addend.

For a paid exact source tree, reverse A* uses `h_s(u)=d(s,u)`. For original edge
v->u with weight w, `d(s,u)<=d(s,v)+w`, so the potential is consistent in reverse
and lower-bounds every reverse continuation toward s. Vertices unreachable from
s cannot belong to an s->t path. Full equality-contour processing remains strict
`>` at the cutoff, followed by the unchanged greedy tight-DAG node/edge rule.
Forward scalar distances do **not** pick an arbitrary parent path or replace
actual selected length by shortest-distance length. Thus selected time, complete
node/edge ties, actual length and replay witness remain the same. Prefix families,
attainment/full `(J,Q,H,Pi)`, relevant depth, bounds and C/CS kernels are untouched.
This is road-work sharing across physical pairs, not cross-history state merging.

### Predeclared correctness and DEV validation

Before numerical validation, 120 related local tests passed with actual native
execution. New checks cover the lazy work threshold, exactly two scalar slots,
LRU eviction/rebuild and ordinary scalar interference; an independent tiny path
oracle covers 12 random directed graphs with Unicode/parallel ties and disjoint
components over repeated promotions. An adversarial source-first numeric queue
tie must still select the canonical 300m path instead of the 1m time-tied direct
edge. Interrupted full-tree construction and interrupted cached-source A* discard
partial state and retry correctly. Finite common-domain Strong/Scale results,
seed keys, primary/secondary unattainment and depth contracts match the reference
provider. Invalid flag/mode/cache contracts fail before loading an index. These
are correctness checks only, not real-graph REF enumeration or timing evidence.

`configs/source_time_reuse_dev.json` predeclares exactly **two new unprofiled
D04 / SD02 energy N128 rows**, Strong Flat-BB then Scale, with the same routing,
seed, kernels, information, model and resource policy. The existing 126 km domain
digest remains
`2196503277068b59652e84ab54729c25e8aa8f1705b329e09df451a5e2b0e4e0`.
The runner checks this input identity before launching workers. Both use the
existing 120s loaded hard limit and 60s target, one numerical worker/thread,
8 GiB process/query-extra caps and 2 GiB host headroom, with cold loading reported
separately. Source-tree construction is **not** moved outside the query deadline.
Carry **4206.233448329 CPU seconds**, precharge a conservative **60 seconds** for
this development/microverification, and add all fresh worker CPU including
compiler/cold load. The total envelope stays **28800 seconds**. Selection/manifest
preparation is reported separately.

There is no unchanged-baseline rerun, new domain, extra method/profile grid,
profiling run, automatic extension or data/model change. Old 120s D04 UNKNOWN
rows remain the baseline evidence; the prior 60s profiled row remains diagnostic
only. No runtime or exact-completion result is inferred from the offline sketch.
If this bounded change misses the target, preserve its termination and identify
the next bottleneck from observed work, rather than relabel success or adjust
battery, candidates, depth or time limits.
