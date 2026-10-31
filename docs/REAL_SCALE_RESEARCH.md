# Real-scale DEV search: segment-one result

## Existing facts

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
