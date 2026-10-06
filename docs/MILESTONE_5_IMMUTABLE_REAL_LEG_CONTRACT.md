# Immutable real-leg adapter contract, draft v1

Status: loader/export-contract and mocked validation only. **No Stage C solve or real-tree solver wiring is authorized by this document.** The delivered `579c6db` checkpoint remains unchanged on its original branch.

## 1. Physical identities and numerical scope

The synthetic bounded schema continues to select graph paths by `(time,node path,edge-ID path)`. This new schema instead consumes the already accepted real router's selected leg constants. It does not select routes and cannot turn a leg table into graph edges.

Keep three identities separate:

- Site ID: the action/capability identity and the identity recorded in pi.
- Road-anchor ID: the physical state location and the ordered-pair leg-table key.
- Region ID: the original frozen hierarchy array index.

Distinct Sites attached to one road anchor remain distinct actions and tuple choices. A movement between them uses the same-anchor zero leg. No positive fake edge or Site collapse is allowed. At the destination **road anchor**, the carried-forward terminal rule forbids further semantic stops/departure regardless of a co-attached Site's different textual ID. A Site named like the destination but attached elsewhere is not terminal merely by string equality.

Each accepted finite binary64 time/actual-length total is stored as both its canonical hexadecimal float string and its exact integer ratio. The two representations must agree bit/value-wise. Optimization will treat these frozen binary64 totals as exact rational constants. This is not a claim that they equal exact real-valued road-edge sums, that native float64 evaluation is associative, or that all rounded totals satisfy a triangle inequality.

Signed zero is permitted only for identity-leg values: the original sign remains in the hexadecimal field, while both signs map to the rational value zero. Consumers must retain that field to reproduce original bits; a ratio alone cannot encode signed zero.

## 2. Proposed payload and API

`src/timecut5/real_legs.py` will provide:

- `encode_binary64(value)` / `decode_binary64(record)` for lossless checked conversion.
- `ImmutableLegTable.from_bytes(data, expected_sha256)` to load an externally frozen payload; no optimization calls.
- `table.leg(source_anchor,target_anchor)` for direct immutable lookup only.
- `table.site(site_id)` and `table.action_sites(current_anchor,effect,remaining_schedule,candidates)` for Site/anchor-safe action identities.
- `weak_action_bound(table,state,candidates,effect,tau_infimum,start_time,overhead,stop_penalty,schedule)` for the non-metric bound below.
- `restrict_frozen_tree(bytes,expected_sha256,selected_site_ids)` for a topology-preserving selected-membership view, including empty children.
- `verify_source_files(table, actual_paths)` to distinguish verified, missing and mismatched source files.

The JSON payload has schema `hiroute.immutable_selected_legs.v1`, numerical contract `binary64_totals_as_exact_rationals_v1`, origin/destination road anchors, a complete declared anchor list, distinct Site records, and exactly one row per ordered anchor pair. Missing rows are errors; unreachable is explicit and has no finite substitute. Same-anchor rows are reachable and exactly zero.

Topological road reachability must remain transitively consistent even when rounded totals are non-metric. A complete table claiming reachable u→s and s→z but unreachable u→z is rejected. This is a boolean consistency check, not a recomputation of any numeric leg. A road-reachable but energy-infeasible direct destination leg can still be bypassed by a legal charging continuation; the initial bound does not infer energy infeasibility from the direct terminal leg.

Every reachable row records `time_s`, `actual_length_m`, and the label direction. The route backend identifies its accepted `(time,actual length,first discovery)` tie policy and source hashes. Direction policy is either forward-per-source or explicitly frozen per-leg. In the latter case every nonself leg must say forward-from-source or reverse-from-target. Forward/reverse float64 accumulation or discovery must never be mixed without recording the choice. Self rows use direction `identity`.

Required provenance includes source-file hashes, router source hashes, a selection-certificate hash, and the original hierarchy hash. A matching hash establishes identity only; it does not itself establish validity of candidate selection, path optimality, or a physical-model theorem. A real export remains blocked until those certificates are separately reviewed.

## 3. Deliberately weak non-metric bound

For a current physical State `(v,r,k)` and one effect over concrete candidate Sites, retain only Sites whose effect is applicable, whose anchor is not terminal, and whose **immediate** declared leg from v is reachable. Different co-attached Sites remain separate members.

Let `Tin=min_site table[v,anchor(site)].time`. Let tau be a proved lower time bound for the current frontier. The supplied h must be the common mandatory overhead, or a proved positive lower bound over every retained Site's overhead. The initial bound is:

- C: `tau + Tin + h - t0 + lambda*(k+1)`.
- S/CS: `max(a,tau+Tin+h)+D - t0 + lambda*(k+1)`.

**Onward travel lower bound is zero.** Future overhead, travel, charging, service and penalties are relaxed away; their nonnegativity is required. This bound neither assumes a triangle inequality nor filters candidates by their direct-to-destination energy consumption. Road reachability is checked separately for consistency, but this deliberately weak bound does not use it to add an onward cost or energy-infeasibility rule.

Primary-only pruning, once solver wiring is reviewed, remains strict `L>incumbent_J`; equality stays live. The loader has no incumbent, search or pruning implementation.

## 4. Actual hierarchy restriction

Hash-check the original serialized tree, validate its root, parent/child topology, Site membership indices and exact disjoint child partitions, then intersect each original Region's members with the selected Site set. Keep every Region ID, parent link and child list, including empty Regions. No new clustering, renumbering, rebalancing, or collapsed co-attached Site identities is allowed.

The restriction is an input view, not integration with real HIER search. Action-specific dynamic coverage and real bounds still require independent comparison before acceptance.

## 5. Export sequence and pending gates

1. Verify all required source artifacts and router/config hashes against the frozen manifest. Do not rebuild or silently replace missing inputs inside this loader.
2. Freeze the Stage C query/candidate policy and original Region restriction before optimization.
3. Choose and record a forward/reverse routing policy for every pair; query the accepted native router directly for every required ordered pair, including Site-to-Site pairs.
4. Encode every returned binary64 value losslessly. Preserve actual length of that selected fastest route, not shortest distance. Export explicit unreachable and identity rows.
5. Hash the complete payload and source/selection evidence. Have production and REF parse the same immutable physical inputs independently; share no optimization helpers.
6. Review physical-anchor state handling, witness route provenance, terminal co-location, Region coverage and zero-onward bound conformance before connecting either solver to real queries.

Mock tests must include rounded non-metric totals, equal-time alternatives with different actual lengths, co-attached distinct Sites, zero identity legs, rejection of contradictory road reachability, road-reachable but energy-infeasible direct terminal legs with charging continuations, destination aliasing, mixed direction rejection, tampered ratios/hashes, and original tree IDs/empty children. Passing them is not Stage C acceptance.

The eventual exporter must stream one source's accepted routing labels at a time and retain only requested pairs; it must not cache full time/length arrays for all anchors. Pair-query APIs may replace full-label runs only after a checked subset establishes identical selected totals and direction/tie behavior. No real graph is loaded by these utilities; graph-load and output-memory preflights remain mandatory before export.

Current PWA witness callbacks preserve inherited predecessor constraints in memory, but current affine interval/prefix traces do not serialize every inherited mask. A Region bound certificate over an unconstrained superset is labeled as such and cannot substitute for exact node-constrained REF optimization or emptiness certification. Future real solver wiring must carry this distinction forward.
