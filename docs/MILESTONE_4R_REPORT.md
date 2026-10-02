# Milestone 4R-A — State-aware EV stop-planning semantics

Completed on 2026-10-02 (Asia/Shanghai). Scope: the static vehicle-stop substrate,
independent EV energy/scheduled-stop requirements, flat deterministic reference,
minimal pure uncertainty/query contracts, synthetic semantic acceptance and a
30-OD **development** diagnostic. No new geographic data were downloaded.
The **revised Go-1 has not yet been established**. No new Region hierarchy, full
Go-2 acquisition policy, Bayesian planner, or final holdout validation is implemented.

## Audit and preservation

Normative source: `RESEARCH_SPEC_v0.2.md`. The supplied 4R prompt and implementation
plan, M1/M2/M3A/M4A/M4B reports, environment/lock files, graph/envelope APIs, M4A
inventory/taxonomy/attachment, M4B native routing and all prior tests were inspected
before new implementation. No applicable AGENTS.md was found. `.env.example` is empty.
Existing layout is `src/<package>`, `scripts/`, `configs/`, `results/milestone_*`,
`docs/MILESTONE_*_REPORT.md`; 4R follows it using `src/stopplan4r` and `results/milestone_4r`.

Initial commit: `5757944207802566a864509edb7bb4af208f6e31`. The worktree was already dirty with M4B
work and supplied formulation files; the complete initial status is recorded in
`preservation_before.json`. Work was isolated on `codex/milestone-4r-a`. No pre-existing
changes were discarded or committed. Packaging adds only `stopplan4r`; README adds
4R reproduction/context, and .gitignore follows the prior result-directory convention.

Before implementation, **84 original tests passed**, with zero failures,
errors or skips. The manifest records the exact **840 protected files**,
each relative pathname, byte length and SHA256. It covers all existing raw/processed
data (including source PBFs, opportunity evidence, both graphs and ODs), all M1–M4B
results/reports, existing graph/envelope/opportunity/microplan code, tests/configs,
environment locks and both specifications/supplied 4R documents. Transient caches
and Python bytecode are excluded. The complete file list is
[`preservation_before.json`](../results/milestone_4r/preservation_before.json).
Final verification: **840 hashes match; zero changed/missing files**.
The immutable M4B acceptance manifest additionally verifies all **56
accepted source-file hashes**, including prior utility scripts; zero mismatches.
This source check overlaps the initial manifest and is not a count of extra distinct files.
The protection scope is the starting worktree, preserving the author's already
updated formulation as well as accepted prior artifacts. Prior reports/results are
not regenerated. Existing acceptance tests additionally verify their historical
manifests and accepted result hashes.

## Exact inputs and environment

| Input artifact | SHA256 |
| --- | --- |
| `results/milestone_4a/opportunity_inventory.parquet` | `d467606df7061b05f87fbcbbc6c2e9dc8e25121bb64c86686cb54f82eb778fb7` |
| `results/milestone_4a/opportunity_attachment.parquet` | `a87ac248049218428805a9cf2f985c2db5c588e4381286b9401a5829faa0e464` |
| `results/milestone_3a/od_remapping.parquet` | `f38c0a81f42564e4f220d5c82de43d4454abfd8e962b09979d3dbdc8a447dcea` |
| `configs/data_extended.yaml` | `71bd7ed2fcd007f75e85c5b72652ff77d23ee28b24ec325f712fc073db0d20bf` |
| `configs/routing.yaml` | `373bc096448cdc507d5c00c27fc9560494f830151f5b976fd48b7ebb576c2024` |
| `RESEARCH_SPEC_v0.2.md` | `2ad0b9666646bd4d7ebea6e601422a02720b186c3302f604b23bfffa80c5226f` |
| `configs/stopplan_4r.yaml` | `d23ffe78fcc0d7bbed53c46e6610022d63b13803f4613dbc91cf3c84d69c294a` |
| `data/processed/graphs/slovenia_extended/nodes.parquet` | `7424eea357d98b54c4652062440a1d287d509f1b7250f7eabbcc5185cde923b5` |
| `data/processed/graphs/slovenia_extended/edges.parquet` | `37f0f75e71de97e0b045d53af23b181e034e6c3262a1a4079d582f37471bb1b8` |
| `data/processed/graphs/slovenia_extended/metadata.json` | `268d09781c5e51a486c0d6574b7439e964b6293aef2df07f64cc5772c6dfaadd` |

The source is the frozen 2026-09-29T20:22:51Z M4A inventory and M3A 75 km extended
directed driving graph. M1/M3A still govern graph semantics and omissions. The
existing `load_graph` verifies frozen PBF/graph hashes and routing configuration.
M4B's `ExactRouter.full` is reused solely for fastest-path times and corresponding
actual lengths; its C++ source/compiler command/version are recorded in
`diagnostic.json`. No old compound-task or Region restriction is reused.

Python: `3.11.16 (main, Sep  2 2026, 23:39:52) [GCC 15.3.0]`. Executable:
`/home/dy/miniconda3/envs/hiroute/bin/python`. Platform: `Linux-7.0.0-31-generic-x86_64-with-glibc2.43`.

- numpy: 2.4.6
- scipy: 1.17.1
- pandas: 3.0.6
- pyarrow: 25.0.0
- igraph: 1.0.0
- pytest: 9.1.1
- PyYAML: 6.0.3

No packages or system components were installed. The original environment files
are protected. `acceptance.json` records the complete installed package versions,
Git state and final 4R source hashes. The script compiler uses g++ `-O3 -std=c++17`;
the shared routing library is created only in `results/milestone_4r/native_cache`.

## Static Site schema and local support

M4A input fields used: typed `osm_type/osm_id`, `lat/lon`, existing `capabilities`,
`original_tags`, `geometry_type/geometry_method`, `source_datasets`, and
`snapshot_timestamp`. The matching attachment supplies `access_node`,
`access_osm_node_id`, `access_distance_m`, and `attachment_status`.
Identity joins are validated one-to-one; mismatched/duplicate identities fail.

Anchor rule is exactly the intersection with charge/parking/rest/services. A
meal/sleep/groceries/pharmacy/toilets-only object is never a vehicle waypoint.
One Site is retained per source identity, with ID `4r:<osm_type>/<osm_id>` and
stable typed-identity sorting. There is no spatial/semantic facility merging.
Unattached transport anchors remain static Sites with null road nodes and are
excluded from routing because their attachment is unavailable, not because of
Region membership. No socket-power, parking-availability, current charger-usability
or additional access interpretation is invented; original tags are retained verbatim.

Exact serialized columns:

```text
access_distance_m, access_node, access_osm_node_id, attachment_status, geometry_method, geometry_type, lat, lodging_count, lon, meal_count, nearest_lodging_m, nearest_meal_m, nearest_toilet_m, original_tags, osm_id, osm_type, site_id, snapshot_timestamp, source_datasets, support_method, support_radius_m, toilet_count, transport_capabilities
```

The schema is an allowlist. Tests reject extra detour, arrival time/SOC/energy,
generalized cost, progress and user-score columns after Parquet serialization.
These quantities live in `SiteEvaluation`, `SearchLabel`, `StopEvent`, `Plan` or
the trip-specific diagnostic table. OD, budget, SOC, windows, lambda_stop and
meal sufficiency thresholds are absent from the Site-builder interface. Thresholds
read stored counts without changing the Site or its ID. Primary radius is static
metadata; radius changes preserve identity. Rebuilding with reversed inventory
and attachment order reproduced both Site and support Parquets **byte-for-byte**.

There is no trustworthy pedestrian graph in the accepted substrate. Local support
therefore uses the explicitly labeled **spherical geographic-distance proxy**:
WGS84 unit-sphere cKDTrees, Earth radius 6,371,008.8 m, radius-to-chord conversion,
indexed ball counts and nearest-neighbor great-circle distances. Separate indexes
are built for meal, toilets and sleep (reported as lodging). All located raw
inventory objects may supply human-support evidence, even if vehicle-unattached.
Counts preserve raw identities, including co-located objects and an anchor's own
support tags. Nearest distances are within-radius minima; null means no observed
support in that radius. Zero/null is not a certificate that a real facility is absent.
This avoids Site×POI scans and does not rank/recommend businesses. Walking barriers,
entrances, crossings and opening hours are not modeled.

Raw opportunities: **105,250**; transport Sites:
**61,714**, of which **60,498** attached.
Nonexclusive anchor-capability counts: charge **2,796**, parking **58,340**,
rest **603**, services **253**. Overlap is retained; these counts do not sum to
the unique Site count. Attachment statuses: `{'attached': 60498, 'excessive_snap': 1216}`.

Primary satisfaction predicate is meal_count >= 1, independently configurable.
Fractions below use all transport Sites, including unattached static Sites.

| Radius m | Sites with observed meal support | All-Site meal fraction | Charger meal fraction | Toilet fraction | Lodging fraction |
| --- | ---: | ---: | ---: | ---: | ---: |
| 250 | 36,910 | 59.81% | 80.11% | 17.48% | 22.64% |
| 500 | 48,112 | 77.96% | 89.63% | 32.43% | 40.31% |
| 750 | 52,546 | 85.14% | 93.45% | 43.14% | 52.56% |

## EV model, state/actions and cost

Experimental canonical EV: 60 kWh, 0.16 kWh/km, terminal reserve 6 kWh (10%),
robust margin 0, execution energy floor 0. Parameters are validated/configurable.
Since consumption is nonnegative and depends on actual path length, checking
each leg's arrival floor enforces the floor throughout that leg. Terminal reserve
plus robust margin is a hard constraint. There is no terminal-energy reward.

The charging interface integrates a configurable nonlinear piecewise power curve:
0–50% at 100 kW, 50–80% at 60 kW, 80–100% at 30 kW. These are synthetic experimental
canonical parameters, **not measured vehicle/station performance**. Arrival and
departure energies are continuous decisions. No fixed charge-to-80% rule exists.
Small-world tests also use explicitly declared 60/30 kW constant curves to create
independently checkable outcomes. Per-Site synthetic curves are supported.

An executable action is a real Site vehicle stop. State labels retain anchor,
elapsed time, current energy, independent scheduled-status flag, distinct stop
count and accumulated generalized cost; event clocks are absolute while labels
are elapsed from the trip origin. The separate evaluator accepts a partial label
and clock origin and computes travel, arrival time/energy, detour, minimum energy
needed to finish directly, charging, support/window penalty and dwell. It never
mutates static facts. The multi-stop optimizer recomputes globally coupled energy
decisions rather than freezing that evaluator's direct-to-destination minimum.

Charging starts after overhead. A compatible local scheduled activity can occur
at the same anchor, with `overhead + max(charging, waiting + activity)` duration.
Without waiting this is precisely `overhead + max(charging, activity)`. An explicitly
incompatible activity starts after charging and adds sequential dwell. Charge,
meal support and toilet support at one anchor remain one vehicle stop. There is
no implicit fatigue inference or autonomous rest requirement.

`J = T_clock + lambda_stop * N_stop + P_requirements + distance_penalty * km`.
Actual driving/detour/overhead/waiting/charging/activity time is inside T_clock;
lambda_stop is a separate nuisance cost and does not re-add actual durations.
Default lambda_stop = 600 s, overhead = 300 s, distance penalty = 0. Hard scheduled
activity requires observed support and a start in its supplied window. A soft
activity can be omitted only by paying its miss penalty, or occur off-window with
configured per-second deviation penalty. No hidden primitive compound task exists.

## Exactness domain and search method

The small-world reference enumerates every distinct-Site order up to the explicit
maximum stop count and every assignment/omission of the independent scheduled
requirement. For each order it enumerates all arrival/departure charging-curve
segments. Within a segment cell, the charging integral is affine; a continuous
linear program enforces energy capacity/floors, clocks, dwell overlap and schedule
constraints and minimizes total cost. Extensions reoptimize the whole stop order,
so extra current charging can remove a downstream event. Resource labels are
materialized from the resulting policy, rather than discarding future plans by
a greedy prefix SOC. A secondary LP minimizes total added energy among cost ties,
preventing gratuitous charging hidden inside a long meal stop.

This is an exhaustive continuous optimizer **for the declared bounded distinct-
anchor/time-optimal-leg domain**, within LP/numerical tolerances. It does not claim
global optimality over arbitrary road path choices, anchor revisits or unbounded
stops. The LP uses 1e-8 primal/dual tolerances, a 1e-8 cost tie allowance and 1e-6
post-solve energy verification. Deterministic comparison rounds cost to 7 decimals
before energy/count/identity tie-breaking. Multi-stop use is limited to small
synthetic worlds; no real multi-stop search was attempted, capped or sparsified.

The real zero/one-stop evaluator visits **every** eligible Site, with no candidate
cap/energy grid. Monotone charging and no terminal reward imply minimum departure
energy sufficient to finish. It evaluates the schedule-start objective's relevant
breakpoints: earliest start, window endpoints and charge-end minus activity duration
(free charging-overlap slack). Analytic answers are independently checked against
the continuous LP, including soft windows and incompatible activities. Fastest
directed legs use actual lengths, with native ties minimizing length among equal
times. This is exhaustive one-stop Site selection on those supplied legs, not
an exact solution over all time/energy road-route alternatives.

Safe Detour Envelope eligibility is the M2 node criterion
`d(s,v)+d(v,d) <= ratio*C*`, with the existing 1e-8 + budget*1e-10 tolerance.
Budget is base mobility time, not generalized cost. Total driving time is checked
again by the evaluator. Eligibility excludes no Site by Region label. Only the
practical 1.05/1.10/1.20/1.40 ratios are used; these retain prior M3A practical-range
crop diagnostics, which do not certify complete external road coverage.

## Semantic and uncertainty acceptance

All 15 required behavioral scenarios pass in `tests/test_stopplan4r.py`: no forced
charge when energy suffices; rejecting infeasible noncharging travel; one overlapping
charger/scheduled stop; no restaurant waypoint; charge/meal/toilet count one;
no inferred fatigue stop; later window-aligned charger selection; no wait to 80%
from sufficient 76%; globally useful extra charging; lambda_stop tradeoff; decision
pruning before queries; viable unknown charger usability; unfavorable query fallback;
rejecting latency that destroys fallback; and Region labels never removing a plan.

The extra-15-minute case uses A/B charging to show that 15 additional current minutes
can eliminate a later 25-minute event (10-minute overhead + 15-minute charge), saving
10 clock minutes. Terminal reserve remains satisfied. A separate fast-later-charger
case selects two stops at zero nuisance penalty and one stop at higher lambda_stop.
Small worlds are checked against an independent finite exhaustive oracle that
enumerates stop orders, integer-kWh departure decisions and schedule-start options.
Those fixtures have continuous optima at the enumerated integer breakpoints;
the actual reference optimizer remains continuous. Nonlinear curve and reserve/
robust-margin tests check additional model boundaries.

The uncertainty layer distinguishes present/unknown/absent and station existence
from current usability. An unknown materially better candidate remains conditionally
viable. Cost intervals use `LB >= incumbent_UB - epsilon_dec` pruning, requiring
a finite guaranteed incumbent. Only after pruning does query logic inspect target,
supplied reliability and state-dependent fallback feasibility after latency. Tests
use an actual scheduled-stop deadline under a propagated trip clock, not an arbitrary
Region boundary. Query cost/latency/reliability are typed metadata; no probability
of usability or acquisition optimization is invented. Synthetic query observations
assume availability stays stable over the short tested decision horizon. Future
occupancy forecasting, moving-vehicle sensing, queue behavior and full Go-2 remain deferred.

Test results: pre-existing **84 passed**; dedicated semantic suite
**29 passed**; complete final suite **116 passed**, with
zero failures/errors/skips in each. Three artifact-level tests verify all 30 ODs,
cost/energy/anchor invariants, static schema/rebuild provenance and all protected hashes.
The saved JUnit XML/log files contain the exact results. Independent native/igraph
checks pass on **18 directed real routes** across
ODs 0/10/20; the frozen baseline is also checked on every OD.

## Development diagnostics

The 30 existing ODs are repeatedly inspected **development data**, never holdout
evidence. There is no tuning against selected bad ODs. Windows are supplied uniformly
as 0.40–0.70 of each OD baseline time, activity duration 2700 s. Initial SOCs are
30% and 76%; both energy-only and independent energy+scheduled scenarios are run
at all four budgets, giving **480 cases**.

| Envelope ratio | Min Sites | Median Sites | Max Sites | Median chargers | Median meal-supported Sites |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1.05 | 215 | 1,760.5 | 5,252 | 49.5 | 1,626.0 |
| 1.10 | 549 | 3,817.0 | 7,641 | 102.5 | 3,332.0 |
| 1.20 | 932 | 5,560.0 | 11,905 | 161.5 | 4,734.0 |
| 1.40 | 1,333 | 8,432.0 | 19,754 | 230.5 | 6,843.5 |

| Scenario | Initial SOC | Cases | Feasible | Cannot instantiate | Zero stops | One stop | Charging |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| energy_and_scheduled | 30% | 120 | 120 | 0 | 0 | 120 | 104 |
| energy_and_scheduled | 76% | 120 | 120 | 0 | 0 | 120 | 12 |
| energy_only | 30% | 120 | 120 | 0 | 12 | 108 | 108 |
| energy_only | 76% | 120 | 120 | 0 | 108 | 12 | 12 |

These are deterministic feasibility/selection observations under assumed usable
attached chargers and the canonical curve, not claims of real operational availability.
At 76% SOC most energy-only cases choose no stop; scheduled cases still choose one
supported vehicle anchor and usually add no charge. All four configured scenarios
were instantiable on all 30 ODs/budgets in the restricted domain. Tables preserve an
explicit `cannot_instantiate_in_zero_one_stop_domain` outcome for any failed case;
it is not proof of infeasibility with additional stops or alternative road paths.
Future-stop coupling, two-stop nuisance tradeoffs and unknown-usability query/fallback
behavior cannot be instantiated by this real one-stop diagnostic and are supported
by synthetic tests only. No real multi-stop exact/approximate claim is made.

## Runtime, memory and full configuration

First static build including indexed support/serialization: **2.070 s**;
reordered-input reconstruction: **1.996 s**; support-index workload:
**1.224 s**. Static-build process peak RSS:
**849.3 MiB**. Per-support index build/query times and coordinate
storage bytes are in `site_build.json`; they exclude no raw evidence by facility deduplication.

Real diagnostic wall time, including graph load, native construction, OD planning
and independent checks: **162.29 s**. Verified graph load:
**11.16 s**. Real diagnostic peak RSS:
**4141.2 MiB (4.04 GiB)**.
Median OD routing: **2.367 s**; median one-stop planning:
**1.415 s**. ODs execute sequentially with one
shared native graph and one live forward/reverse label pair, not 30 simultaneous caches.
The guard checks a 38 GiB RSS ceiling and at least 10 GiB available memory reserve,
with 7 GiB projected additional allocation before graph loading and 1 GiB before
OD routing. All checks passed. RSS is process high-water memory on this warm-cache
workstation, not whole-server simultaneous memory or an interactive-latency promise.
Input/output hashing and final acceptance/report writing are separate from the
diagnostic's recorded timed section; no timing comparison with M4B is claimed.

Final test resource measurements (`/usr/bin/time -v`):

```text
Elapsed (wall clock) time (h:mm:ss or m:ss): 2:14.81
Maximum resident set size (kbytes): 8032732
Exit status: 0
```

Complete configuration used (no hidden SOC target or Site candidate cap):

```yaml
results_dir: results/milestone_4r
inventory: results/milestone_4a/opportunity_inventory.parquet
attachments: results/milestone_4a/opportunity_attachment.parquet
graph_data_config: configs/data_extended.yaml
development_ods: results/milestone_3a/od_remapping.parquet
support:
  radii_m:
  - 250
  - 500
  - 750
  primary_radius_m: 500
  meal_threshold: 1
  method: spherical_geographic_distance_proxy
ev:
  capacity_kwh: 60
  consumption_kwh_km: 0.16
  reserve_fraction: 0.1
  robust_margin_kwh: 0
  minimum_energy_kwh: 0
charging:
  label: synthetic_experimental_canonical_EV_not_measured_vehicle_performance
  bands:
  - - 0.5
    - 100
  - - 0.8
    - 60
  - - 1.0
    - 30
planner:
  overhead_s: 300
  lambda_stop_s: 600
  distance_penalty_s_per_km: 0
  maximum_stops: 1
diagnostics:
  envelope_ratios:
  - 1.05
  - 1.1
  - 1.2
  - 1.4
  initial_soc:
  - 0.3
  - 0.76
  window_baseline_fraction:
  - 0.4
  - 0.7
  scheduled_duration_s: 2700
  scheduled_hard: true
  miss_penalty_s: 7200
  time_penalty_per_s: 2
  compatible_with_charging: true
  real_multi_stop: deferred_no_feasibility_restriction_or_candidate_cap
  epsilon_dec_s: 60
memory:
  maximum_rss_gib: 38
  minimum_available_gib: 10
compiler: g++
compiler_flags:
- -O3
- -std=c++17
```

## Exact commands and outputs

Executed from `/home/dy/HiRoute/project`, using the existing environment:

```bash
git status --short
git switch -c codex/milestone-4r-a
/home/dy/miniconda3/envs/hiroute/bin/python -m pytest --require-real-data --require-envelope-results --require-regional-results --require-opportunity-results --require-microplan-results --junitxml=results/milestone_4r/preexisting_tests.xml
/home/dy/miniconda3/envs/hiroute/bin/python scripts/build_stop_sites_4r.py
/home/dy/miniconda3/envs/hiroute/bin/python -m pytest tests/test_stopplan4r.py -q --junitxml=results/milestone_4r/semantic_tests.xml
/home/dy/miniconda3/envs/hiroute/bin/python scripts/run_stopplan_4r_diagnostic.py
/usr/bin/time -v -o results/milestone_4r/final_test_resources.txt /home/dy/miniconda3/envs/hiroute/bin/python -m pytest --require-real-data --require-envelope-results --require-regional-results --require-opportunity-results --require-microplan-results --junitxml=results/milestone_4r/tests.xml
/home/dy/miniconda3/envs/hiroute/bin/python scripts/write_stopplan_4r_report.py
/home/dy/miniconda3/envs/hiroute/bin/python scripts/accept_stopplan_4r.py
git diff --stat
```

Commands wrote stdout/stderr to the corresponding preexisting_tests/site_build/
semantic_tests/diagnostic/tests logs in the new result directory. The first
protection capture was an inline Python audit before any source changes, recording
the manifest fields described above. On a fresh checkout it is reproducible with
`python scripts/accept_stopplan_4r.py --capture`; capture refuses replacement.
For independent reruns against an already captured checkout, retain the manifest.

Outputs include `stop_sites.parquet`, all-radius `local_support.parquet`, their
byte-identical reordered rebuilds, `support_coverage.csv`, `one_stop_diagnostics.csv`
and Parquet, `envelope_site_counts.parquet`, `diagnostic_runtime.csv`, provenance
JSONs, JUnit/test logs, protection records and final acceptance. `git_diff_stat.txt`
records the tracked diff, which includes pre-existing user changes and excludes
untracked new files; final-source fingerprints list the new 4R code separately.

## Limitations and gate boundary

Geographic accessibility, representative geometry and road snapping are proxies;
raw OSM object counts do not certify distinct facilities. Static access/charger
usability, queues and vehicle-specific curves are not established by these data.
The old graph retains its documented legality/turn/traffic/border limitations.
One-stop road-leg exactness does not imply general EV route optimality. The small
continuous reference scales exponentially in stop orders and charging segments;
continental multi-stop scaling is deferred rather than imposing unproven feasibility
restrictions. Real feasibility results assume canonical usable chargers. Query
contracts are minimal and do not solve information-acquisition selection or future
availability. No learned preferences, business ranking or new Region hierarchy is added.

Milestone 4R-A meets its scoped semantic acceptance gate. The **revised Go-1 has not
yet been established**; the next hierarchical experiment requires a separately
authorized stage and later a new holdout OD set. Work stops at this 4R-A gate.
