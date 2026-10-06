# HiRoute remaining real-data and protocol gates

Read-only audit, 2026-10-06 UTC. Checkout commit `5bf5ae7a9dc9b8deb9e3e30c1878d30120f262e4` (restored upstream JSON merged); new bounded implementation files were in progress. No OSM download, rebuild, repository mutation, or solver run was performed by this audit.

## Bottom line

- The five missing physical inputs total **412,443,599 bytes (393.34 MiB)**. They are sufficient to load the accepted graph, ODs and static Sites without any raw OSM files.
- The historical Stage C candidate-order rule also refers to an accepted progress field. That field exists in `results/milestone_4a/od_features.parquet`; including it makes the simplest completely frozen bundle **481,252,049 bytes (458.96 MiB)**. A first-eight-OD projection can replace the full progress file if exported with provenance.
- The frozen **2,047-Region / 60,498-attached-Site tree** and all **1,024 leaf-bucket JSONs** already exist locally. The tree's actual SHA-256 matches its frozen manifest. The tiny-fixture HIER rebuilds a different binary tree and scans its members; it does not integrate this frozen hierarchy.
- These files unblock input construction, not M5-V acceptance or M5-D. The original A20/B64/C32 suites still need a versioned population/coverage certificate and complete REF/FLAT/HIER comparisons. A small new fixture collection is not a substitute for those populations.

## 1. Remaining protocol gates

Latest authority is `docs/time_cut_v2_authority/HIROUTE_FORMAL_SPEC.md` §§27–29 and `HIROUTE_RESEARCH_MASTER_PLAN.md` §§37–46. Original population details come from `MILESTONE_4R_B2_B21_EXPERIMENT_PROTOCOL.md` §§8–12, retained by `MILESTONE_5_B21_EXACT_VALIDATION_PROTOCOL_V1.md` §§24–26.

1. **Freeze a v2 acceptance protocol.** Map the time-cut semantics to the legacy themes and v1 reset coverage. Do not demand the refuted v1 attained-set equivalence as a passing assertion, or silently rewrite old expected results. Keep the historical v0/v1 failures and manifests unchanged. The latest authority's SQ-1–SQ-8 closure, constructive witnesses and finite PWA closure precede implementation acceptance.
2. **Algebra/operator coverage.** Verify idempotence, D/S/C/CS continuation congruence, merge laws, open/closed endpoints, plateau-created attainment, energy-wide representation, full-key reduction safety and equality-prune safety under v2. The older v1 protocol also specifies 50 objects each for D/S/C/CS and three-way merge, ten reset adversaries, and the permanent 76-kWh regression. Any superseding v2 population should explicitly map/replace those requirements, rather than call an unrelated generated count equivalent.
3. **Stage A: all 20 frozen themes.** Single charging segment; one breakpoint; multiple breakpoints; increasing/decreasing frontier; disconnected energy domain; interior merge intersection; deadline clipping; schedule-start switch; CS charge-dominant; CS schedule-dominant; CS branch switch; zero-charge limit; unattained positive-charge infimum; attained interior optimum; time/charge tie; tuple tie; energy-floor clip; capacity clip; two-charge redistribution; repeated-Site/depth case. Each needs a hand or independent expected-result certificate and an explicit semantic-coverage matrix. The restored original A15 is one case, not A20 completion.
4. **Stage B: exactly 64 deterministic cases.** Line/fork/diamond/directed asymmetric loop × low/medium SOC × schedule absent/present × chargers-only/mixed capability arrangement × slack/tight energy. At most six Sites, H_ref=4, canonical charging curve, stable IDs. Keep infeasible and unattained cases; freeze before comparison.
5. **Stage C: exactly 32 states.** Canonical `instance_id` order, first eight ODs (0–7), SOC 0.30/0.76 × `energy_only`/`energy_and_scheduled`; at most eight concrete Sites per state; H_ref=4. Freeze static candidate pool, ordering, class-preserving selection and hashes before solving. No outcome-guided selection and no scalability claim.
6. **Every applicable case:** independent sequence/regime REF; FLAT dominance off/on; HIER; exact status and attained `(J,Q,H,Pi)` agreement; independently replayable legal witnesses; lost/duplicate actions=0; child action partitions exact; Region lower bound ≤ independently constrained REF optimum; primary equality remains live. Compare witness validity, not arbitrary continuous allocations when multiple allocations have the same key. Report primary and secondary nonattainment distinctly.
7. **Separate depth check:** verify the incumbent-based production bound `floor(U_J/(h_min+lambda_stop))`, including larger-cap checks where feasible. H_ref=4 cannot be carried into a production claim. Lack of a verified incumbent is not a proof of unrestricted infeasibility.
8. **Evidence and preservation:** authority/protocol/candidate freezes; expected certificates; REF enumeration/regime/independence records; operator/branch/reduction traces; D-on/off results; hierarchy coverage/refinement/bound/equality audits; descriptive complexity/runtime tables; test logs; pre/post predecessor preservation; acceptance decision. Missing old binary evidence must remain “unavailable”, not be counted as hash-verified preservation.

Observed historical evidence: the v0 construction manifest records A=1/20, B/C not constructed; v1 stopped at its first algebra counterexample before A/B/C. Current new files contain 18 independent bounded cases and 36 FLAT fixture variants, but no original A20/B64/C32 population-completion manifest was found during this audit. Work was concurrent, so this is a coverage warning, not a final test verdict.

## 2. Exact minimum input transfer

All six files below are currently absent. SHA-256 values and historical sizes are recorded in `required_input_manifest.json`; runnable checksum and path lists accompany this report.

| Path | Bytes | SHA-256 |
|---|---:|---|
| `data/processed/graphs/slovenia_extended/nodes.parquet` | 104,471,506 | `7424eea357d98b54c4652062440a1d287d509f1b7250f7eabbcc5185cde923b5` |
| `data/processed/graphs/slovenia_extended/edges.parquet` | 303,022,185 | `37f0f75e71de97e0b045d53af23b181e034e6c3262a1a4079d582f37471bb1b8` |
| `data/processed/graphs/slovenia_extended/metadata.json` | 13,978 | `268d09781c5e51a486c0d6574b7439e964b6293aef2df07f64cc5772c6dfaadd` |
| `results/milestone_3a/od_remapping.parquet` | 448,277 | `f38c0a81f42564e4f220d5c82de43d4454abfd8e962b09979d3dbdc8a447dcea` |
| `results/milestone_4r/stop_sites.parquet` | 4,487,653 | `e3e7d6d6667f7ab684ff83eb2646920516b01aef2e6ceb8170c689e71f6afd38` |
| `results/milestone_4a/od_features.parquet` | 68,808,450 | `be02c3bc750feb64dd5fc1df5a22f3862aa2d01aa26b4e30d0a53372b4a7894e` |

Source records: `results/milestone_4r/preservation_before.json`, `results/milestone_4r_b1/preservation_checkpoint.json`, `results/milestone_5_b21_v1/frozen_input_hash_manifest.json`.

No need to transfer raw PBFs, raw opportunity inventory, charger extraction, or all predecessor run outputs for new Stage C physics. `stop_sites.parquet` already embeds its static support aggregates; separate `local_support.parquet` is not required by `sites_from_table`. Existing config and source files are sufficient. Complete retrospective preservation of every historical artifact is a separate, larger requirement.

On the original machine holding these files, after copying the two accompanying text lists there:

```bash
cd /path/to/original/HiRoute
AUDIT=/path/to/real_input_audit
sha256sum -c "$AUDIT/stage_c_core.sha256" &&
  tar -cf /path/outside/repository/hiroute-stage-c-inputs.tar \
      -T "$AUDIT/stage_c_core_paths.txt"
```

This command only verifies/archives existing inputs; it does not download or rebuild anything. No command was run on the user's machine by this audit.

### Candidate-selection detail that must be frozen

The accepted progress definition is `d_T(o,v)/(d_T(o,v)+d_T(v,z))`, implemented in `src/opportunity/models.py::decision_features` and emitted as `progress` by `scripts/run_opportunity_benchmark.py`. The emitted table is limited to its then-frozen maximum envelope (2× baseline); it is not a complete static Site table. Join by `(instance_id, osm_type, osm_id)`, not row position. Audit which eligible Sites have a stored progress value, and specify handling for missing values before comparisons. Do not silently drop missing-progress Sites or assert “no accepted progress field exists.” Original Stage C fixes 32 states, not 128 envelope-ratio variants; it does not by itself select one of the older four diagnostic envelope ratios.

Preserve distinct static effect classes using capability/support predicates, not the old one-stop winner's realized effect. At a charging-and-support Site, C, S and CS can be distinct multi-stop actions. Do not import old one-stop effect-free filtering to discard a potentially useful multi-stop charge.

## 3. Safe compact alternative (design, not an existing exporter)

A local export on the machine holding the accepted graph can avoid transferring the graph. Build it outside the repository using existing readers and routing primitives; a new direct-leg adapter is required before consuming it.

- `manifest.json`: schema version; source commit; six source hashes; config/router source hashes; numeric encoding; deterministic routing/tie rule; static pool/selection policy; H_ref=4; selected OD IDs; freeze-before-solver marker; export and validation hashes.
- `selection.json`: each state's ordered full candidate-pool identities, static effect-class flags, accepted progress or explicit missing flag, selected ≤8 identities, and class coverage/reasons. Preserve auditability of the selection; no solver output may influence it.
- `cases.json`: the 32 physical queries; origin/destination road-anchor identities; original Site IDs with road-anchor mappings and C/S/CS capability/support flags; battery/charging/schedule/overhead/penalty constants; selected directed-leg references; original Region/ancestor IDs. Use the frozen EV constants (60 kWh, 0.16 kWh/km, 6 kWh reserve, 300 s overhead, 600 s stop penalty, 100/60/30 kW bands at SOC 0.5/0.8/1) and freeze schedule/numeric treatment explicitly.
- `legs.json`: all necessary ordered pairs among origin, destination and selected Site anchors (≤100 entries/state including self-pairs, ≤3,200 before deduplication). Each record has `source_anchor`, `target_anchor`, reachability, accepted `time_s`, **actual length of that selected fastest route** `length_m`, routing mode/source hash, and optional independently checked path witness/hash. Encode finite float64 primitive values losslessly (hex or integer-ratio plus a documented rational interpretation), never display-rounded decimals. Unreachable is explicit, never a finite substitute.
- `hierarchy.json`: use the already frozen tree, or an exact selected-membership restriction retaining original Region IDs/parent-child structure and empty children; no repartition/retuning. Include per-effect root/child/leaf coverage certificates. Compact integration still is not deployable runtime evidence.

Extraction building blocks: `scripts/_common.py::load_graph` validates processed-file hashes and routing configuration; `stopplan4r.sites.sites_from_table` reads the accepted Site schema; `microplan.routing.ExactRouter.full` supplies accepted directed fastest-time/actual-length labels. The existing `ODTravel` helper only handles origin→Site and Site→destination, so it cannot provide Site→Site multi-stop legs. Compute those on the accepted graph too. Export must declare forward/reverse label conventions and check consistency within the declared numerical contract; the native primitive uses float64, while new exact solvers use rationals.

**Critical consumer rule:** a leg table is an immutable routing oracle, not a graph. Do not feed it as `Problem.edges`, run Dijkstra/Floyd–Warshall on it, or replace a direct leg by a new equal-time via-Site route. That can change the selected route's physical length and therefore energy. Both REF and production may share these immutable physical primitives, but must independently optimize decisions. No all-graph shortest-path or raw-OSM revalidation claim follows from table replay alone.

Current `timecut5.bounded.Problem` orders equal-time routes by node path then edge IDs, independent of length. Accepted real `src/microplan/routing.cpp` minimizes `(time, actual length)` and retains first discovery for equal labels. A direct-table adapter must bypass the new graph selector and retain the accepted real totals. It must also preserve distinct co-attached Sites and zero-length/time movement between identical road anchors, and allow repeated Site actions. Do not add fake positive road edges for co-location.

## 4. Additional M5-D gates and substrate

M5-D is **not merely Stage C with more candidates**. Master plan §45 requires M5-V first, then a separately frozen deployable lower-bound design and long-haul multi-charge workload. Freeze actual workload/query parameters, incumbent acquisition and termination rules, safe bounds, instrumentation, timing protocol and metrics before comparative runs. No long-haul workload manifest or M5-D acceptance result was found.

The accepted tree is already present:

- `results/milestone_4r_b1/hierarchy.json`: 5,271,372 bytes, SHA-256 `4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805`.
- `results/milestone_4r_b1/hierarchy_build/primary_cells.bin`: 23,569,992 bytes, SHA-256 `abe92d977fb40bd043d8d61ee06c7e1af90c0bafb6b26f01bfab9194b63dff12`.
- `results/milestone_4r_b1d/leaf_buckets/*.json`: 1,024 files, 1,298,178 bytes, already present.

If the new design reuses the legacy ALT/boundary substrate, the further missing runtime files are:

- `results/milestone_4r_b1d/{summaries,counts,children}.npy`: 3,144,320 / 49,256 / 32,880 recorded bytes.
- `results/milestone_4r_b1d/landmarks/{travel_time,distance}_{0..7}_{out,in}.npy`: 32 arrays, **1,508,483,584 bytes total**, hashes in the accompanying manifest.
- For boundary augmentation: `results/milestone_4r_b1d2/{road_leaf_cells,subtree_ends,ingress,egress,boundary_offsets}.npy`, hashes in the accompanying manifest. The historical manifest records 29,708,212 bytes for its broader non-rebuild NPY+Parquet boundary payload; that total is not the exact five-array total.

These are reusable static inputs, not automatically valid multi-stop bounds. `DeployIndex`/`BoundaryIndex` and the existing `run_hierarchy_4r_*` scripts implement the older zero/one-stop experiment; legacy pruning includes primary `>=` and old static bucket logic. They must not be run unchanged and labeled M5-D. Prove new dynamic continuation bounds, retain primary equality, cover every C/S/CS action, and instrument internal scans/oracle access/routing cost. Report branch/piece growth, work reduction, component and end-to-end runtime, memory, and failures/NA cases. Keep exact shortest-distance lower bounds separate from fastest-route lengths used for energy.

Independent holdout remains a subsequent M6-H stage after algorithms, thresholds and metrics are frozen. Neither the accepted development geography nor a compact export is an untouched holdout.
