"""Write a measured technical report from saved Milestone 2 results."""
import json
import xml.etree.ElementTree as ET

import pandas as pd

from _common import ROOT
from _envelope_common import envelope_config, envelope_run


def main():
    config = envelope_config()
    _,_,_ = envelope_run("envelope_report",config)
    directory = ROOT/config["results_dir"]
    results = json.loads((directory/"benchmark.json").read_text())
    preservation = json.loads((directory/"preservation_after.json").read_text())
    before = json.loads((ROOT/preservation["checkpoint"]).read_text())
    suites = ET.parse(directory/"tests.xml").getroot().findall("testsuite")
    tests = {key:sum(int(suite.get(key,"0")) for suite in suites) for key in ["tests","failures","errors","skipped"]}
    if not preservation["passed"] or tests["failures"] or tests["errors"] or tests["skipped"] or results["containment_violations"]:
        raise RuntimeError("Cannot report completion with failed preservation, tests or containment checks")
    stats = pd.read_parquet(directory/"envelope_stats.parquet")
    checks = pd.read_parquet(directory/"path_containment_tests.parquet")
    growth_rows = "\n".join(f"| {r['ratio']:.2f} | {r['node_percent_median']:.3f} | {r['node_percent_min']:.3f}–{r['node_percent_max']:.3f} | {r['edge_percent_median']:.3f} | {r['boundary_risk_cases']} / 30 |" for r in results["growth"])
    clean = stats.loc[stats.instance_id.isin(results["boundary_safe_subset_ids"])]
    clean_rows = "\n".join(f"| {int(r.instance_id)} | {r.ratio:.2f} | {r.node_percent:.3f} | {r.edge_percent:.3f} |" for r in clean.itertuples())
    maximum = stats.loc[stats.ratio.eq(max(results["ratios"]))]
    large = maximum.loc[maximum.instance_id.isin(results["excessive_envelope_od_ids"])]
    large_rows = "\n".join(f"| {int(r.instance_id)} | {r.origin_city.replace('_',' ')} → {r.destination_city.replace('_',' ')} | {r.node_percent:.2f} |" for r in large.itertuples())
    timing_rows = "\n".join(f"| {label} | {results[key]['median']:.3f} | {results[key]['p95']:.3f} | {results[key]['mean']:.3f} |" for label,key in [
        ("Forward all-node distances (s)","forward_seconds"),("Reverse all-node distances (s)","reverse_seconds"),
        ("Cached lower-bound arrays (s)","lower_bound_seconds"),("Envelope masks (ms)","envelope_build_ms")])
    error = float((checks.loc[checks.method.eq("baseline"),"path_cost"]-checks.loc[checks.method.eq("baseline"),"budget"]/checks.loc[checks.method.eq("baseline"),"ratio"]).abs().max())
    boundary = results["boundary_metadata"]
    report = f'''# Milestone 2 — Safe Detour Envelope

**Scope: structural correctness with respect to the frozen directed graph. This is not a claim of full legal, real-world or globally complete route feasibility.** No Opportunity Regions, POIs, charging, utilities, semantic processors, acquisition policies or decision-driven stopping are implemented.

## Preservation and reproducibility

Before implementation, all 14 existing tests passed. Git commit: `{before['git_commit']}`; dirty state: `{bool(before['git_status'])}`. The frozen PBF checksum matches the manifest and both processed graph fingerprints match metadata. Final preservation verified {preservation['verified_file_count']} existing files plus the raw PBF. No Milestone 1 graph, OD, routing configuration, report or result was regenerated. `RESEARCH_SPEC.md` remains SHA256 `{results['run']['research_spec_sha256']}`.

Final suite: **{tests['tests']} passed, {tests['failures']} failures, {tests['errors']} errors, {tests['skipped']} skipped**. The original environment lock and graph engine are retained; packaging adds only the envelope module. Logs store configuration, seed, package versions, Git state and source fingerprints. Envelope, distance and containment tables identify cost, units, graph fingerprint and routing-config fingerprint; boundary diagnostics also carry provenance. Changing fallback speeds may change membership; sensitivity experiments must record new cost/config fingerprints.

## Definition and containment proof

For nonnegative directed edge cost c, compute C*=d(s,d), d_s(v)=d(s,v), and d_d(v)=d(v,d). For finite B≥C*:

\\[
V_B=\\{{v:d_s(v)+d_d(v)\\le B\\}},\\qquad
E_B=\\{{(u,v):d_s(u)+c(u,v)+d_d(v)\\le B\\}}.
\\]

For any directed s–d path P with c(P)≤B, split it at a vertex v. The shortest prefix and suffix costs satisfy d_s(v)≤c(P[s:v]) and d_d(v)≤c(P[v:d]); adding gives d_s(v)+d_d(v)≤c(P)≤B. Split instead at an exact edge e=(u,v): d_s(u)+c(e)+d_d(v)≤c(P)≤B. Thus every vertex and exact parallel-edge ID of P belongs to its envelope. The proof also covers directed walks containing cycles. Nonnegative costs make shortest distances well defined. For the exact inequalities, edge endpoints lie in V_B by shortest-distance triangle inequalities. Masks are nested because increasing B increases only the threshold.

This is a containment guarantee, **not a sufficient test that a path assembled from retained edges respects B**. A synthetic test retains all edges of an over-budget cyclic walk. Over-budget routes must still have their total cost checked. Real sampled over-budget walks happened to be excluded; this does not establish a converse theorem.

## Implementation and directed semantics

`src/envelope/safe_detour.py` exposes `precompute_detour_distances`, `build_envelope_from_precomputed`, `compute_safe_detour_envelope`, and a progressive iterator. An `EnvelopeGraph` protocol uses the existing ordered endpoint/cost arrays. Forward computation calls `single_source_distances(s, direction="out")`. Reverse computation calls `single_source_distances(d, direction="in")`: this is traversal from d in the edge-reversed graph, so its entries are d_G(v,d), not d_G(d,v).

One distance pair and node/edge lower-bound arrays are cached per OD × cost. NumPy constructs read-only masks without per-edge Python loops or full graph copies. The primary experiment uses travel time in **seconds**; the API and real tests also support distance in **metres**. Infinite vertices/edges are excluded explicitly; unreachable ODs and nonfinite or sub-baseline budgets are rejected. The iterator yields views for caller inspection, with no automatic stopping rule. Strong/weak component counts are not computed, since they are optional diagnostics and would require additional subgraph materialization.

Configured ratios are {results['ratios']}; the cap {config['max_ratio']:.2f} is an experimental choice. Numerical membership uses `bound ≤ B + {config['numerical_tolerance']['absolute']:g} + {config['numerical_tolerance']['relative']:g}*B`. The small allowance covers double-precision accumulation and summation-order differences. At B=10,000 seconds it is about 1 microsecond; at B=300,000 metres it is about 30 micrometres. The maximum allowance in this time experiment was {stats.tolerance_allowance.max():.3g} seconds; maximum baseline summation discrepancy was {error:.3g} seconds. Zero-tolerance toy tests check the exact definitions independently. Tolerance is nonnegative and monotonic in B, so nesting is preserved.

## Structural validation

Toy tests cover asymmetric directions, corridors of C*, 1.1C*, 1.4C* and 2.1C*, geometrically direct but over-budget detours, parallel edges, one-way reachability, unreachable vertices, zero costs, origin=destination, invalid budgets and tolerance. Small random graphs are checked against independent SciPy Floyd–Warshall distances and exhaustive simple paths; real road paths are **not enumerated**.

All 30 unchanged ODs have 12 seeded waypoint-induced alternatives plus one baseline. Waypoints are sampled from configured minimum-through-node cost bands, including over-cap bands; this is controlled coverage, not uniform path sampling. igraph batches path extraction in each direction; incoming edge sequences are reversed before concatenation. Directed endpoint sequences and base costs (`math.fsum`) are checked. Walks may revisit vertices, which the theorem permits. This sampler is igraph-specific; the core envelope API is backend-independent.

Across **{results['envelope_count']} envelopes**, {results['containment_check_count']} sample/budget checks had **zero violations**. There were {results['strict_within_budget_checks']} strict c(P)≤B checks, or {results['tolerated_within_budget_checks']} including the explicitly recorded numerical allowance. {results['over_budget_checks']} over-budget checks were made; {results['over_budget_not_contained']} were not contained. Every OD has an excluded over-cap witness. Baseline containment, retained-edge endpoints and node/edge nesting are checked for every ratio. Path fingerprints repeat exactly on ODs 0, 1 and 2; real tests independently check both cost dimensions. Empirical sampling supports the implementation; the proof establishes the general graph-theoretic property.

## Runtime and memory

| Operation | Median | p95 | Mean |
| --- | ---: | ---: | ---: |
{timing_rows}

Each of 30 ODs has one measured forward and reverse array computation, reused for every budget. Each budget has {config['benchmark']['mask_repeats']} timed mask builds; the table uses the median of those repeats per envelope. Reported mask p95 is across those per-envelope medians. Bounds preparation is timed separately. Validation, statistics, sampling, serialization and boundary checks are excluded from mask timing. No backend rewrite or comparison was needed; igraph remains adequate for this offline smoke study, without establishing an en-route latency guarantee.

Verified graph load: {results['verified_graph_load_seconds']:.2f} s. Boundary preparation: {results['boundary_preparation_seconds']:.2f} s. Peak Linux process RSS: **{results['peak_rss_mib']:.1f} MiB**; loading alone reached {results['loaded_graph_peak_rss_mib']:.1f} MiB. Cached distances and lower bounds use **{results['maximum_precomputed_bytes']/2**20:.2f} MiB per active OD**; one node/edge mask pair uses **{results['maximum_mask_bytes']/2**20:.2f} MiB**. Graph storage dominates RSS. The experiment processes ODs sequentially and retains at most a few mask pairs. Keeping all 30 distance caches or all budget views would add memory; callers should stream or explicitly manage cache lifetime. Page caches are warm, timings are from this server, and RSS is process high-water memory.

## Envelope growth: all 30 ODs

| Ratio | Median node % | Node % range | Median edge % | Boundary-risk ODs |
| --- | ---: | ---: | ---: | ---: |
{growth_rows}

At the maximum ratio, {len(large)} ODs exceed the configured {100*config['diagnostics']['excessive_node_fraction']:.0f}% node-size diagnostic threshold. This threshold labels a large search space; it does not prune or stop expansion. The largest envelope retains {maximum.node_percent.max():.2f}% of graph nodes.

| OD | Cities | Node % at maximum ratio |
| --- | --- | ---: |
{large_rows}

## Boundary diagnostics and interior subset

The [Geofabrik extract polygon]({boundary['source_url']}) is frozen separately, acquired at `{boundary['acquired_at_utc']}` (HTTP last modified: `{boundary['http_last_modified']}`), SHA256 `{boundary['sha256']}`. Publisher `.poly` files are not versioned to the PBF snapshot date; this polygon is therefore an approximate proxy. It is archived with metadata and never substituted by a fresh polygon during experiments.

Coordinates are projected to {config['boundary']['projection']}. A node is flagged if it falls outside the polygon eroded inward by {config['boundary']['interior_margin_m']} metres, including nodes outside the original polygon. An envelope has `boundary_risk=true` if any included node is flagged. This detects proximity only; it does not certify legal feasibility or geographic completeness and can miss a long edge's boundary crossing between its vertices. The frozen graph can retain full ways outside the polygon. Boundary flags do not change masks or the original ODs.

At the maximum ratio, **{len(results['boundary_risk_od_ids_at_max_ratio'])}/30** ODs are flagged. IDs: `{results['boundary_risk_od_ids_at_max_ratio']}`. The proxy-interior subset at the maximum scheduled ratio consists of IDs `{results['boundary_safe_subset_ids']}`; the complete all-OD results remain primary. Results for this subset:

| OD | Ratio | Node % | Edge % |
| --- | ---: | ---: | ---: |
{clean_rows}

This small subset cannot establish representative boundary-free performance. Regional borders can exclude valuable alternative corridors; larger extracts or more exact boundary analysis are needed before globally complete-envelope claims.

## Diagnostics, limitations and next-stage implications

Static figures under `results/milestone_2/figures/` show all-OD growth and ODs 0, 9 and 21 at ratios 1.1, 1.4 and 2.0. All envelope nodes are aggregated into {config['diagnostics']['map_grid_m']} m occupancy cells; source cell counts are retained and verified against node totals. Origin, destination and baseline are overlaid. No visual subsampling supplies correctness evidence. Editable SVG/PDF and PNG previews are provided with QA notes.

The graph omits enforcement of turn-restriction relations, node barriers, conditional access/time-dependent legality, vehicle dimensions, traffic and ferry schedules; some conditional roads were excluded in Milestone 1. The OSM extract may truncate cross-border alternatives. Costs depend on the unchanged estimated speed model. This milestone establishes graph-theoretic structure only.

Distance precomputation costs about two seconds per OD and inexpensive masks permit progressive budgets without recomputing distances. However the 2C* cap often yields nearly the entire regional network. Later work should measure the benefit of smaller starting budgets and manage boundary risk. No decision-value heuristic or stopping policy is invented here. **Numbering note:** the request calls Opportunity Region work “Milestone 3”; the authoritative specification assigns Milestone 3 to Adaptive Envelope and Milestone 4 to Opportunity Regions. This implementation preserves that order and implements neither research component. No Opportunity Region generation proceeds without explicit instruction.

Reproduction commands are in [README.md](../README.md). Machine-readable results include envelope statistics, distance timings, containment checks, boundary flags, the optional subset, benchmark metadata, logs, figures and before/after preservation records.
'''
    (ROOT/"docs/MILESTONE_2_REPORT.md").write_text(report)
    print("Wrote docs/MILESTONE_2_REPORT.md")


if __name__ == "__main__":
    main()
