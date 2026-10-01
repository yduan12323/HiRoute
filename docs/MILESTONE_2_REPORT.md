# Milestone 2 — Safe Detour Envelope

**Scope: structural correctness with respect to the frozen directed graph. This is not a claim of full legal, real-world or globally complete route feasibility.** No Opportunity Regions, POIs, charging, utilities, semantic processors, acquisition policies or decision-driven stopping are implemented.

## Preservation and reproducibility

Before implementation, all 14 existing tests passed. Git commit: `d865cd6f28eec3425c58b02c9051e5d6aa8549f3`; dirty state: `False`. The frozen PBF checksum matches the manifest and both processed graph fingerprints match metadata. Final preservation verified 28 existing files plus the raw PBF. No Milestone 1 graph, OD, routing configuration, report or result was regenerated. `RESEARCH_SPEC.md` remains SHA256 `d594f4ac78e1bfe8903c98d48bb20c4e9e3f2b15f1e8fed5fedde964be7ead04`.

Final suite: **26 passed, 0 failures, 0 errors, 0 skipped**. The original environment lock and graph engine are retained; packaging adds only the envelope module. Logs store configuration, seed, package versions, Git state and source fingerprints. Envelope, distance and containment tables identify cost, units, graph fingerprint and routing-config fingerprint; boundary diagnostics also carry provenance. Changing fallback speeds may change membership; sensitivity experiments must record new cost/config fingerprints.

## Definition and containment proof

For nonnegative directed edge cost c, compute C*=d(s,d), d_s(v)=d(s,v), and d_d(v)=d(v,d). For finite B≥C*:

\[
V_B=\{v:d_s(v)+d_d(v)\le B\},\qquad
E_B=\{(u,v):d_s(u)+c(u,v)+d_d(v)\le B\}.
\]

For any directed s–d path P with c(P)≤B, split it at a vertex v. The shortest prefix and suffix costs satisfy d_s(v)≤c(P[s:v]) and d_d(v)≤c(P[v:d]); adding gives d_s(v)+d_d(v)≤c(P)≤B. Split instead at an exact edge e=(u,v): d_s(u)+c(e)+d_d(v)≤c(P)≤B. Thus every vertex and exact parallel-edge ID of P belongs to its envelope. The proof also covers directed walks containing cycles. Nonnegative costs make shortest distances well defined. For the exact inequalities, edge endpoints lie in V_B by shortest-distance triangle inequalities. Masks are nested because increasing B increases only the threshold.

This is a containment guarantee, **not a sufficient test that a path assembled from retained edges respects B**. A synthetic test retains all edges of an over-budget cyclic walk. Over-budget routes must still have their total cost checked. Real sampled over-budget walks happened to be excluded; this does not establish a converse theorem.

## Implementation and directed semantics

`src/envelope/safe_detour.py` exposes `precompute_detour_distances`, `build_envelope_from_precomputed`, `compute_safe_detour_envelope`, and a progressive iterator. An `EnvelopeGraph` protocol uses the existing ordered endpoint/cost arrays. Forward computation calls `single_source_distances(s, direction="out")`. Reverse computation calls `single_source_distances(d, direction="in")`: this is traversal from d in the edge-reversed graph, so its entries are d_G(v,d), not d_G(d,v).

One distance pair and node/edge lower-bound arrays are cached per OD × cost. NumPy constructs read-only masks without per-edge Python loops or full graph copies. The primary experiment uses travel time in **seconds**; the API and real tests also support distance in **metres**. Infinite vertices/edges are excluded explicitly; unreachable ODs and nonfinite or sub-baseline budgets are rejected. The iterator yields views for caller inspection, with no automatic stopping rule. Strong/weak component counts are not computed, since they are optional diagnostics and would require additional subgraph materialization.

Configured ratios are [1.0, 1.05, 1.1, 1.2, 1.4, 1.6, 2.0]; the cap 2.00 is an experimental choice. Numerical membership uses `bound ≤ B + 1e-08 + 1e-10*B`. The small allowance covers double-precision accumulation and summation-order differences. At B=10,000 seconds it is about 1 microsecond; at B=300,000 metres it is about 30 micrometres. The maximum allowance in this time experiment was 2.2e-06 seconds; maximum baseline summation discrepancy was 2.55e-11 seconds. Zero-tolerance toy tests check the exact definitions independently. Tolerance is nonnegative and monotonic in B, so nesting is preserved.

## Structural validation

Toy tests cover asymmetric directions, corridors of C*, 1.1C*, 1.4C* and 2.1C*, geometrically direct but over-budget detours, parallel edges, one-way reachability, unreachable vertices, zero costs, origin=destination, invalid budgets and tolerance. Small random graphs are checked against independent SciPy Floyd–Warshall distances and exhaustive simple paths; real road paths are **not enumerated**.

All 30 unchanged ODs have 12 seeded waypoint-induced alternatives plus one baseline. Waypoints are sampled from configured minimum-through-node cost bands, including over-cap bands; this is controlled coverage, not uniform path sampling. igraph batches path extraction in each direction; incoming edge sequences are reversed before concatenation. Directed endpoint sequences and base costs (`math.fsum`) are checked. Walks may revisit vertices, which the theorem permits. This sampler is igraph-specific; the core envelope API is backend-independent.

Across **210 envelopes**, 2730 sample/budget checks had **zero violations**. There were 1037 strict c(P)≤B checks, or 1056 including the explicitly recorded numerical allowance. 1674 over-budget checks were made; 1674 were not contained. Every OD has an excluded over-cap witness. Baseline containment, retained-edge endpoints and node/edge nesting are checked for every ratio. Path fingerprints repeat exactly on ODs 0, 1 and 2; real tests independently check both cost dimensions. Empirical sampling supports the implementation; the proof establishes the general graph-theoretic property.

## Runtime and memory

| Operation | Median | p95 | Mean |
| --- | ---: | ---: | ---: |
| Forward all-node distances (s) | 1.130 | 1.156 | 1.134 |
| Reverse all-node distances (s) | 1.163 | 1.198 | 1.166 |
| Cached lower-bound arrays (s) | 0.037 | 0.037 | 0.037 |
| Envelope masks (ms) | 5.831 | 6.105 | 5.810 |

Each of 30 ODs has one measured forward and reverse array computation, reused for every budget. Each budget has 3 timed mask builds; the table uses the median of those repeats per envelope. Reported mask p95 is across those per-envelope medians. Bounds preparation is timed separately. Validation, statistics, sampling, serialization and boundary checks are excluded from mask timing. No backend rewrite or comparison was needed; igraph remains adequate for this offline smoke study, without establishing an en-route latency guarantee.

Verified graph load: 3.85 s. Boundary preparation: 0.47 s. Peak Linux process RSS: **1649.7 MiB**; loading alone reached 1626.0 MiB. Cached distances and lower bounds use **84.41 MiB per active OD**; one node/edge mask pair uses **6.32 MiB**. Graph storage dominates RSS. The experiment processes ODs sequentially and retains at most a few mask pairs. Keeping all 30 distance caches or all budget views would add memory; callers should stream or explicitly manage cache lifetime. Page caches are warm, timings are from this server, and RSS is process high-water memory.

## Envelope growth: all 30 ODs

| Ratio | Median node % | Node % range | Median edge % | Boundary-risk ODs |
| --- | ---: | ---: | ---: | ---: |
| 1.00 | 0.126 | 0.051–0.212 | 0.064 | 4 / 30 |
| 1.05 | 2.852 | 0.329–8.031 | 2.551 | 10 / 30 |
| 1.10 | 6.439 | 0.765–19.990 | 6.087 | 14 / 30 |
| 1.20 | 12.313 | 1.694–43.252 | 11.996 | 16 / 30 |
| 1.40 | 27.139 | 4.067–76.166 | 26.949 | 24 / 30 |
| 1.60 | 42.717 | 6.466–89.240 | 42.586 | 27 / 30 |
| 2.00 | 73.406 | 11.736–97.435 | 73.321 | 29 / 30 |

At the maximum ratio, 20 ODs exceed the configured 50% node-size diagnostic threshold. This threshold labels a large search space; it does not prune or stop expansion. The largest envelope retains 97.44% of graph nodes.

| OD | Cities | Node % at maximum ratio |
| --- | --- | ---: |
| 0 | Piran → Murska Sobota | 97.28 |
| 1 | Koper → Murska Sobota | 96.99 |
| 2 | Ljubljana → Slovenj Gradec | 50.78 |
| 4 | Novo mesto → Murska Sobota | 91.64 |
| 5 | Novo mesto → Slovenj Gradec | 80.29 |
| 7 | Postojna → Celje | 59.76 |
| 8 | Murska Sobota → Postojna | 93.29 |
| 9 | Maribor → Nova Gorica | 95.48 |
| 10 | Murska Sobota → Bled | 89.75 |
| 11 | Koper → Maribor | 94.26 |
| 13 | Celje → Novo mesto | 56.11 |
| 16 | Koper → Ptuj | 95.05 |
| 18 | Celje → Nova Gorica | 85.89 |
| 19 | Piran → Murska Sobota | 97.44 |
| 22 | Nova Gorica → Maribor | 96.29 |
| 23 | Piran → Slovenj Gradec | 94.59 |
| 24 | Postojna → Slovenj Gradec | 80.63 |
| 25 | Kranj → Slovenj Gradec | 67.22 |
| 26 | Koper → Novo mesto | 60.53 |
| 29 | Koper → Celje | 79.60 |

## Boundary diagnostics and interior subset

The [Geofabrik extract polygon](https://download.geofabrik.de/europe/slovenia.poly) is frozen separately, acquired at `2026-10-01T01:24:00.566767+00:00` (HTTP last modified: `Wed, 30 Sep 2026 03:02:42 GMT`), SHA256 `f5813a8cda35bb54b0d3123e62701165e10068f532b0aa0fda70926f2d7ddc32`. Publisher `.poly` files are not versioned to the PBF snapshot date; this polygon is therefore an approximate proxy. It is archived with metadata and never substituted by a fresh polygon during experiments.

Coordinates are projected to EPSG:3035. A node is flagged if it falls outside the polygon eroded inward by 1000 metres, including nodes outside the original polygon. An envelope has `boundary_risk=true` if any included node is flagged. This detects proximity only; it does not certify legal feasibility or geographic completeness and can miss a long edge's boundary crossing between its vertices. The frozen graph can retain full ways outside the polygon. Boundary flags do not change masks or the original ODs.

At the maximum ratio, **29/30** ODs are flagged. IDs: `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28, 29]`. The proxy-interior subset at the maximum scheduled ratio consists of IDs `[27]`; the complete all-OD results remain primary. Results for this subset:

| OD | Ratio | Node % | Edge % |
| --- | ---: | ---: | ---: |
| 27 | 1.00 | 0.054 | 0.027 |
| 27 | 1.05 | 0.524 | 0.415 |
| 27 | 1.10 | 1.326 | 1.164 |
| 27 | 1.20 | 3.342 | 3.110 |
| 27 | 1.40 | 6.619 | 6.340 |
| 27 | 1.60 | 11.225 | 10.951 |
| 27 | 2.00 | 23.830 | 23.608 |

This small subset cannot establish representative boundary-free performance. Regional borders can exclude valuable alternative corridors; larger extracts or more exact boundary analysis are needed before globally complete-envelope claims.

## Diagnostics, limitations and next-stage implications

Static figures under `results/milestone_2/figures/` show all-OD growth and ODs 0, 9 and 21 at ratios 1.1, 1.4 and 2.0. All envelope nodes are aggregated into 1000 m occupancy cells; source cell counts are retained and verified against node totals. Origin, destination and baseline are overlaid. No visual subsampling supplies correctness evidence. Editable SVG/PDF and PNG previews are provided with QA notes.

The graph omits enforcement of turn-restriction relations, node barriers, conditional access/time-dependent legality, vehicle dimensions, traffic and ferry schedules; some conditional roads were excluded in Milestone 1. The OSM extract may truncate cross-border alternatives. Costs depend on the unchanged estimated speed model. This milestone establishes graph-theoretic structure only.

Distance precomputation costs about two seconds per OD and inexpensive masks permit progressive budgets without recomputing distances. However the 2C* cap often yields nearly the entire regional network. Later work should measure the benefit of smaller starting budgets and manage boundary risk. No decision-value heuristic or stopping policy is invented here. **Numbering note:** the request calls Opportunity Region work “Milestone 3”; the authoritative specification assigns Milestone 3 to Adaptive Envelope and Milestone 4 to Opportunity Regions. This implementation preserves that order and implements neither research component. No Opportunity Region generation proceeds without explicit instruction.

Reproduction commands are in [README.md](../README.md). Machine-readable results include envelope statistics, distance timings, containment checks, boundary flags, the optional subset, benchmark metadata, logs, figures and before/after preservation records.
