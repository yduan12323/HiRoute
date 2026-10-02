"""Write the measured 4R-A technical report from saved evidence."""
import json
import subprocess
import xml.etree.ElementTree as ET

import pandas as pd
import yaml

from _stopplan4r_common import ROOT, sha256, verify_protected, write_json


def test_counts(path):
    suites = list(ET.parse(path).getroot().iter('testsuite'))
    return {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ['tests', 'failures', 'errors', 'skipped']}


def main():
    out = ROOT / 'results/milestone_4r'
    before = json.loads((out / 'preservation_before.json').read_text())
    build = json.loads((out / 'site_build.json').read_text())
    diagnostic = json.loads((out / 'diagnostic.json').read_text())
    tests = test_counts(out / 'tests.xml')
    previous = test_counts(out / 'preexisting_tests.xml')
    semantic = test_counts(out / 'semantic_tests.xml')
    preserve = verify_protected()
    if not preserve['passed'] or any(t[k] for t in [tests, previous, semantic] for k in ['failures', 'errors', 'skipped']):
        raise ValueError('Cannot write a passing report with failed tests/protection')
    write_json(out / 'preservation_after.json', preserve)
    envelopes = pd.read_parquet(out / 'envelope_site_counts.parquet')
    runtime = pd.read_csv(out / 'diagnostic_runtime.csv')
    coverage_rows = '\n'.join(
        f'| {int(r["radius_m"])} | {r["meal_supported_count"]:,} | {r["meal_support_fraction"]:.2%} | {r["charger_meal_support_fraction"]:.2%} | {r["toilet_support_fraction"]:.2%} | {r["lodging_support_fraction"]:.2%} |'
        for r in build['support_coverage'])
    envelope_rows = '\n'.join(
        f'| {ratio:.2f} | {int(g.site_count.min()):,} | {g.site_count.median():,.1f} | {int(g.site_count.max()):,} | {g.charger_count.median():,.1f} | {g.meal_supported_count.median():,.1f} |'
        for ratio, g in envelopes.groupby('ratio'))
    outcome_rows = '\n'.join(
        f'| {s["scenario"]} | {s["initial_soc"]:.0%} | {s["cases"]} | {s["feasible_cases"]} | {s["cannot_instantiate_cases"]} | {s["zero_stop_cases"]} | {s["one_stop_cases"]} | {s["charging_cases"]} |'
        for s in diagnostic['summary'])
    input_rows = '\n'.join(f'| `{p}` | `{h}` |' for p, h in diagnostic['inputs'].items())
    config_text = yaml.safe_dump(diagnostic['configuration'], sort_keys=False).strip()
    versions = '\n'.join(f'- {p}: {v}' for p, v in before['environment']['packages'].items())
    tests_resources = (out / 'final_test_resources.txt').read_text()
    resources = '\n'.join(line.strip() for line in tests_resources.splitlines() if any(term in line for term in ['Elapsed (wall clock)', 'Maximum resident', 'Exit status']))
    text = f'''# Milestone 4R-A — State-aware EV stop-planning semantics

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

Initial commit: `{before['git_commit']}`. The worktree was already dirty with M4B
work and supplied formulation files; the complete initial status is recorded in
`preservation_before.json`. Work was isolated on `codex/milestone-4r-a`. No pre-existing
changes were discarded or committed. Packaging adds only `stopplan4r`; README adds
4R reproduction/context, and .gitignore follows the prior result-directory convention.

Before implementation, **{previous['tests']} original tests passed**, with zero failures,
errors or skips. The manifest records the exact **{len(before['files'])} protected files**,
each relative pathname, byte length and SHA256. It covers all existing raw/processed
data (including source PBFs, opportunity evidence, both graphs and ODs), all M1–M4B
results/reports, existing graph/envelope/opportunity/microplan code, tests/configs,
environment locks and both specifications/supplied 4R documents. Transient caches
and Python bytecode are excluded. The complete file list is
[`preservation_before.json`](../results/milestone_4r/preservation_before.json).
Final verification: **{preserve['verified_files']} hashes match; zero changed/missing files**.
The immutable M4B acceptance manifest additionally verifies all **{preserve['verified_accepted_source_files']}
accepted source-file hashes**, including prior utility scripts; zero mismatches.
This source check overlaps the initial manifest and is not a count of extra distinct files.
The protection scope is the starting worktree, preserving the author's already
updated formulation as well as accepted prior artifacts. Prior reports/results are
not regenerated. Existing acceptance tests additionally verify their historical
manifests and accepted result hashes.

## Exact inputs and environment

| Input artifact | SHA256 |
| --- | --- |
{input_rows}

The source is the frozen 2026-09-29T20:22:51Z M4A inventory and M3A 75 km extended
directed driving graph. M1/M3A still govern graph semantics and omissions. The
existing `load_graph` verifies frozen PBF/graph hashes and routing configuration.
M4B's `ExactRouter.full` is reused solely for fastest-path times and corresponding
actual lengths; its C++ source/compiler command/version are recorded in
`diagnostic.json`. No old compound-task or Region restriction is reused.

Python: `{before['environment']['python']}`. Executable:
`{before['environment']['executable']}`. Platform: `{before['environment']['platform']}`.

{versions}

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
{', '.join(build['static_columns'])}
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

Raw opportunities: **{build['raw_opportunity_count']:,}**; transport Sites:
**{build['site_count']:,}**, of which **{build['attached_site_count']:,}** attached.
Nonexclusive anchor-capability counts: charge **2,796**, parking **58,340**,
rest **603**, services **253**. Overlap is retained; these counts do not sum to
the unique Site count. Attachment statuses: `{build['attachment_status_counts']}`.

Primary satisfaction predicate is meal_count >= 1, independently configurable.
Fractions below use all transport Sites, including unattached static Sites.

| Radius m | Sites with observed meal support | All-Site meal fraction | Charger meal fraction | Toilet fraction | Lodging fraction |
| --- | ---: | ---: | ---: | ---: | ---: |
{coverage_rows}

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

Test results: pre-existing **{previous['tests']} passed**; dedicated semantic suite
**{semantic['tests']} passed**; complete final suite **{tests['tests']} passed**, with
zero failures/errors/skips in each. Three artifact-level tests verify all 30 ODs,
cost/energy/anchor invariants, static schema/rebuild provenance and all protected hashes.
The saved JUnit XML/log files contain the exact results. Independent native/igraph
checks pass on **{len(diagnostic['independent_route_checks'])} directed real routes** across
ODs 0/10/20; the frozen baseline is also checked on every OD.

## Development diagnostics

The 30 existing ODs are repeatedly inspected **development data**, never holdout
evidence. There is no tuning against selected bad ODs. Windows are supplied uniformly
as 0.40–0.70 of each OD baseline time, activity duration 2700 s. Initial SOCs are
30% and 76%; both energy-only and independent energy+scheduled scenarios are run
at all four budgets, giving **{diagnostic['case_count']} cases**.

| Envelope ratio | Min Sites | Median Sites | Max Sites | Median chargers | Median meal-supported Sites |
| --- | ---: | ---: | ---: | ---: | ---: |
{envelope_rows}

| Scenario | Initial SOC | Cases | Feasible | Cannot instantiate | Zero stops | One stop | Charging |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{outcome_rows}

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

First static build including indexed support/serialization: **{build['first_build_seconds']:.3f} s**;
reordered-input reconstruction: **{build['rebuild_seconds']:.3f} s**; support-index workload:
**{build['support_runtime']['seconds']:.3f} s**. Static-build process peak RSS:
**{build['peak_rss_mib']:.1f} MiB**. Per-support index build/query times and coordinate
storage bytes are in `site_build.json`; they exclude no raw evidence by facility deduplication.

Real diagnostic wall time, including graph load, native construction, OD planning
and independent checks: **{diagnostic['runtime_seconds']:.2f} s**. Verified graph load:
**{diagnostic['graph_load_seconds']:.2f} s**. Real diagnostic peak RSS:
**{diagnostic['peak_rss_mib']:.1f} MiB ({diagnostic['peak_rss_mib']/1024:.2f} GiB)**.
Median OD routing: **{runtime.routing_seconds.median():.3f} s**; median one-stop planning:
**{runtime.one_stop_planning_seconds.median():.3f} s**. ODs execute sequentially with one
shared native graph and one live forward/reverse label pair, not 30 simultaneous caches.
The guard checks a 38 GiB RSS ceiling and at least 10 GiB available memory reserve,
with 7 GiB projected additional allocation before graph loading and 1 GiB before
OD routing. All checks passed. RSS is process high-water memory on this warm-cache
workstation, not whole-server simultaneous memory or an interactive-latency promise.
Input/output hashing and final acceptance/report writing are separate from the
diagnostic's recorded timed section; no timing comparison with M4B is claimed.

Final test resource measurements (`/usr/bin/time -v`):

```text
{resources}
```

Complete configuration used (no hidden SOC target or Site candidate cap):

```yaml
{config_text}
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
'''
    path = ROOT / 'docs/MILESTONE_4R_REPORT.md'
    path.write_text(text)
    print(f'Wrote {path.relative_to(ROOT)} ({len(text.split())} words); tests={tests}; protected={preserve["verified_files"]}')


if __name__ == '__main__':
    main()
