# Real-scale DEV search

## Existing facts

This is delivery segment one of `HIROUTE_REAL_SCALE_DECISION_AND_PLAN.md`
(2026-10-31). Development starts from current origin/main
`0d02b2bfadd5be937b8fb2f355b2d4728dd61ee2` in a new checkout. It does not claim
completion of the overall research objective. The earlier mechanism study did
not establish an incremental hierarchy advantage. The old `flat`, `flat_bb`
and `hier` paths remain diagnostic baselines.

Actual reusable Shandong inputs exist: 2,986,695 road vertices, 5,900,232 directed
edges, 4,725 source Sites and 4,198 attached Sites. Existing processed artifacts
and attachments are reused. The old raw-cache path is absent; no province
rebuild or new map acquisition was performed. Input attribution is OpenStreetMap
contributors / Geofabrik, ODbL 1.0, snapshot 2026-10-16. The modeled graph is
province-polygon clipped; a route optimal within it need not be optimal in a
larger geographic graph.

The processed JSON-to-TSV export copied exact rational edge metrics, took
64.10 wall / 63.69 CPU seconds and 15.95 MB observed RSS. The 530,374,281-byte
TSV is local input, not committed data. Map preparation is separate from solve
budget and has no precomputed N-squared selected-leg table.

## Algorithm changes

`exact.scale.solve_scale` has two methods: `flat_bb_strong` and `scale`. Both own
an exact post-stop family at each full-history node, apply only the next drive
and stop, and keep the terminal drive separate. An empty physical family stops
that branch. An infeasible terminal attempt does not stop further actions.
No cross-history dominance or additional reducer is applied.

Both methods use the same deterministic exact feasibility seed, charging
operators and scalar completion relaxation. Every seed is physically replayed;
only an attained, executable record supplies upper bound U. With positive
h+lambda, any primary-tie/improving plan has
`H <= floor(U/(h+lambda))`. This is recomputed when U improves. No seed is not an
infeasibility proof. The unrestricted mode ignores no arbitrary N/H cap;
explicit diagnostic caps remain labelled as such. A wall/memory stop leaves
mathematical status UNKNOWN and preserves the available feasible record.

A terminal accumulator retains only the best primary infimum, its attainment,
the best secondary infimum on the attained primary face and one full-key
attained witness when present. Equal primary/secondary infima retain their
attainment distinction. Terminal histories are not permanently accumulated.

For a post-stop piece tau(E), k past stops and at least one future action, the
completion relaxation is

```
inf_E tau(E)-t0 + T_R + h
      + max(mu_min * max(0, reserve + e_R - E), remaining_service * D)
      + lambda * (k+1).
```

Past elapsed time is bounded by tau. Future drive time and energy are bounded
by directed shortest-road time and length, respectively. Positive marginal
charging slopes bound necessary charging time. Driving cannot overlap charging
or service; charging and service may overlap, hence their max. At least one
future overhead and stop penalty are necessary. Additional stops, windows and
waiting are relaxed. Affine endpoints and the charging/service kink suffice
for the exact infimum; an open endpoint is allowed as a lower bound, never as
an incumbent. Strict `lower > U` is required to prune, preserving equality and
the complete `(J,Q,H,Pi)` objective.

Static Regions sort by directed road-progress features, using Site ID only to
break ties. Per-effect counts, masks and metric extrema are built once.
Triangle inequalities in the underlying directed road metric give
`d(a,s) >= max(0,d(o,s)-d(o,a),d(a,z)-d(s,z))`. Region extrema provide a weaker
safe bound without inspecting members. Internal bound, legality and refinement
queries have no member scan or all-candidate action-set construction. Leaf
materialization checks its exact selected inbound leg; the same tightening is
available to both methods. Strong Flat-BB uses singleton records. Different
leaf order is reported; reduced expansion is not automatically a batching
causal effect.

The road index builds adjacency once and caches scalar workspaces and selected
legs with explicit bounds. The compact backend uses the exact LCM of input
rational denominators and arbitrary-precision integer Dijkstra. It reconstructs
the lexicographically smallest node path, then edge-ID path, on the shortest-time
DAG. Actual length is an attribute, never a tie-break objective. The older
binary64 native router has different tie semantics and is not substituted.
A frozen selected-leg provider is distinct from a routable road graph; missing
pairs cannot be manufactured by routing through other selected legs.

## Real domain results

The four geometry-selected DEV OD are Heze–Rongcheng, Liaocheng–Weihai,
Dezhou–Rongcheng and Heze–Yantai. Municipal endpoints bind to nearest already
attached real Sites. Domains use the fixed 50 km corridor and eight progress
strata in `configs/real_scale_dev.json`, with nested N=16/32/64/128 orders.
There are 334/930/275/488 schedule-qualified unique anchors before N truncation.
The energy-only C-capable pools contain 55/93/46/76 anchors. N64 energy input
is unavailable for SD01/SD03 and all N128 energy inputs are unavailable under
the frozen 50 km rule; these rows remain input failures, without corridor expansion.
These are explicitly restricted candidate-domain optima, not full-province
optima or safe geographic filters. The eight OD/scenario families were chosen
before solver comparisons. Energy-only and scheduled variants share unchanged
18 kWh initial / 60 kWh capacity / 6 kWh reserve / 0.16 kWh/km model values.

The first input version mistakenly counted S-only Sites in energy-only N.
Those integration rows remain in `real_scale_results.jsonl` with both requested
and actual qualified counts. They are not N16/N32 energy scale evidence:
SD01 requested16/32 had only10/17 legal charging Sites. The corrected input
builder filters the full frozen order by scenario before truncation. It fails
explicitly when requested N exceeds the available legal pool.

At this review checkpoint, four attained results and two timeouts exist:

| SD01 integration domain | Strong Flat-BB | Scale | Physical route |
|---|---:|---:|---|
| Energy:10 qualified Sites (requested16 mixed) | exact58.74s | exact59.05s |3 positive charges, same full key |
| Energy:17 qualified Sites (requested32 mixed) | exact85.35s | exact86.05s |3 positive charges, same full key |
| Schedule:32 qualified Sites | UNKNOWN120s | UNKNOWN120s |3-charge feasible seed, same key |

The attained energy route is793.569km with7.699h driving. Its shortest-road
energy lower bound is741.402km, independently requiring at least2 charges
under the unchanged vehicle model; the attained optimum uses3. Every reported
executable witness passes a separate physical ledger. The first Strong Flat-BB
supervisor lost its control connection; the completed solver output, CPU/RSS
and replay survive, while aggregate host samples are unavailable. It was not
rerun. Subsequent supervisors are durable across control-connection resets.

The corrected scenario-qualified pilot and ablations are pending. There is
currently no N64/N128 completion or hierarchy-benefit claim.

## Attribution

A controlled pair shares the same model, candidate domain, index implementation,
feasibility seed policy and resource limits. Loaded query time includes candidate
and schedule preparation, required routing, seed, search and witness validation.
Index loading/building is cold-start cost and its residency is separately
reported, alongside process RSS and query-extra memory. Summary/singleton
queries, exact leaf routes, transitions, PWA work and OPEN are counted.

Small-domain checks cover common-domain parity with the old solver, a finite
independent REF solve, bound admissibility, disjoint coverage, energy/temporal
cases, equalities, primary/secondary unattainment, empty physical prefixes versus
terminal failure, time translations, directed/tie routing and input legality.
Every real executable result uses a separate physical-equation replay of its
recorded edge paths and charges. This does not enumerate simple paths on the
real graph or provide an independent real-domain optimality certificate.

## Incomplete work

The corrected real pilot, representative ablations and final table are pending.
The mixed-domain historical ingress has been retained and labelled explicitly.
The 50 km energy-domain shortage is a candidate-rule limitation: the existing
province contains168 attached unique C-capable anchors. A future approved
change to approximately60 km would support N64 for all four OD, and126 km
would support N128, without new raw data. Neither change was performed.
N256/main-scale experiments, external literature baselines, application-value
comparisons and untouched holdout remain outside this segment. This document
must not be read as overall research success or a claim that Scale wins.

## Next decision

After the draft PR and its real pilot results are reviewed, decide whether the
best method supports segment two and whether a hierarchy claim remains justified.
No automatic merge, second architecture, additional domain expansion or holdout
is authorized by this segment.
