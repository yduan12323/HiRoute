# Matched frozen DEV coverage: final result

Six fixed searches completed, with four actual fresh physical replays and two explicit replay skips. All controller terminals permit continuation; every executed stage has verified cleanup. No further stages are scheduled.

## Outcomes

| Existing selected case | Method | Result | Whole search wall (s) | Observed exact wall (s) | Fresh saved-best replay |
|---|---|---|---:|---:|---|
| OD02_energy_only_soc3_10 N128 | FLAT | feasible_witness | 192.541854995 | 120.081325780 | improved_feasible_witness |
| OD02_energy_only_soc3_10 N128 | HIER | feasible_witness | 209.874181095 | 120.168745321 | improved_feasible_witness |
| OD07_energy_and_scheduled_soc3_10 N128 | HIER | seed_exhausted_unknown | 160.180511623 | none | explicitly skipped |
| OD07_energy_and_scheduled_soc3_10 N128 | FLAT | seed_exhausted_unknown | 119.096648793 | none | explicitly skipped |
| OD10_energy_only_soc19_25 N32 | FLAT | feasible_witness | 174.441598018 | 120.108109536 | initial_feasible_witness_retained |
| OD10_energy_only_soc19_25 N32 | HIER | feasible_witness | 177.099828066 | 120.106240662 | initial_feasible_witness_retained |

OD02 energy-only, lower SOC, N128: both methods independently recovered the same improved two-charge route. Primary objective fell by 12.981068813% from the independently admitted initial route, with full lexicographic improvement and original Hmax 33 preserved. Fresh processes verified original seed and saved best route. This establishes actual multi-charge feasibility in this selected domain. It does not establish optimality.

OD07 scheduled, lower SOC, N128: both methods completed the same heuristic seed enumeration with zero proposals and 59 source runs. Each clean completed empty checkpoint was authenticated; neither method dispatched exact search, and each replay was explicitly skipped. This does not prove candidate-domain or global infeasibility. Both failed-to-find rows remain in the six-row record; no expansion, replacement or retry occurred. The shared seed procedure limits this pair before the exact methods can be compared.

OD10 energy-only, higher SOC, N32: both methods retained the same initial one-charge full route, independently recovered in fresh processes. Original Hmax 26 was preserved; no improvement is claimed.

All four dispatched exact searches reached their 120-second cap. Each completed depth 1 and was interrupted during depth 2. Small polling/containment cleanup overruns explain observed exact wall values above 120 s. No optimum or global lower-bound conclusion is claimed.

## Phase timing definitions

Whole search wall is controller end-to-end wall, including parent preflight, child preparation, search and containment cleanup. First provisional persistence, independent feasible admission and actual exact engine start below are measured from worker start; the provisional snapshot is not yet independent admission. Observed exact wall is the authenticated watchdog clock, including terminal observation/cleanup delay. Separate replay wall belongs to its own process/controller stage.

| Attempt | Provisional saved (s) | Independent admission (s) | Actual exact start (s) | Replay whole wall (s) |
|---|---:|---:|---:|---:|
| od02_flat | 20.664278880 | 33.712445687 | 71.778220385 | 34.196030744 |
| od02_hier | 18.262869722 | 32.236279066 | 89.044223368 | 22.992842040 |
| od07_hier | none | none | none | none |
| od07_flat | none | none | none | none |
| od10_flat | 12.695679229 | 23.414403917 | 53.576402374 | 32.415979644 |
| od10_hier | 12.251989586 | 23.027695553 | 56.170787349 | 22.307232868 |

## Identity and interpretation

Both methods use the same authenticated original frozen hierarchy, retaining all 2,047 source node IDs and ordered edges, intersecting memberships with their selected candidate domain. Empty nodes and unary active branches remain; original multi-site leaves remain leaves. Original-topology preservation does not imply equivalence to full-site optimization. The historical sorted-ID experiments remain separately identified. All 88 source pins remain unchanged through terminal results.

Within each matched pair the original query, candidates, graph/native/compiler/cache policy and dynamically verified initial bound match. Each attempt independently cold-started provider state without route reuse. Provider-cold does not mean OS-cache-cold; sequential order, compilation/cache state and host contention were not controlled. These six observations do not establish a generalized HIER speed advantage or disadvantage. OD07 wall differences occurred before exact-method dispatch.

## Accounting

The twelve immutable stage records comprise six searches, four executed replays and two explicit replay skips. Stage charges total 1,277.109392533 CPU seconds. The full 120-second preparation allowance remains charged, giving **1,397.109392533 of 5,040 reserved CPU seconds**. Skip preflight bookkeeping is covered by that retained allowance; it is not a measurement of all preparation work. The execution uses per-process resource limits and one-core workers, with conservative wait4 accounting; it does not claim aggregate cgroup enforcement. Earlier phase charges and failed attempts remain unchanged.

## Exact provenance

- Admitted parent: 9fab252c4aaceb120d38772be8f7e1378c4e8bfdba8719e7abce167a20802474
- Reviewed prospective v2: fef9b76cfd5e6241238fca52988abaf39c2e3a3309b2f13f035bc80bfa8b223c
- Runtime source closure: 42787de6caacfd212eac11728b176b6a9c7b4faef36ac58f674e881d9744fc76
- Original hierarchy: 4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805

Exact row/query/domain/tree identities, rational full keys, saved-record hashes, source calls and stage charges are in [matched_result.json](matched_result.json). Raw search/replay/controller outputs and immutable matched_gate_ledger are retained. Independent review records are outside this evidence index. No extra numerical run is included or authorized by this report.

## Published evidence and reproduction boundary

The [full six-row result](matched_result.json), [four saved-witness/replay projections](witness_evidence.json), [twelve stage records including two explicit skips](stage_ledger.json), [independent review](final_review.json), and [original artifact identities](provenance.json) are included. All 307 original indexed artifacts were rehashed without mismatch against inventory d1d32574a814804f57b9243e3977c0594b524979e83385295c71896de3175060.

Progress snapshots recorded layer 1 end and layer 2 start for the four exact searches; no separate completed-layer reconstruction was run or claimed. Local queue bounds are prefix-local diagnostics, not global lower-bound certificates.

These are sanitized evidence projections. Original hashes refer to the archived originals, not sanitized file bytes. Absolute machine paths, path-keyed source maps and process identifiers are omitted. The witness projections are not loadable signed checkpoints or a standalone executable reproduction bundle; the matching graph/native/runtime would be needed for new physical replay. No new experiment or physical replay was performed to prepare this report, and no experimental coordinator is installed.

The [earlier frozen DEV coverage](../frozen_dev_coverage_20261015/README.md), including its original N32 controller failure and conservative charges, remains unchanged. Earlier sorted-ID hierarchy results are separately scoped. Original topology here retains all 2,047 nodes/edges but restricts memberships to selected candidates; it is not full-site problem equivalence. No generalized method superiority, holdout, optimum or global infeasibility claim follows.
