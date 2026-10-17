# Fixed three-DEV recovery batch, 2026-10-17

## Result

All27 predeclared stages were attempted:15 SUCCESS (3 common preparations and12 independent terminal verifications),12 owned search-phase TIMEOUT,0 FAILED,0 BLOCKED,0 UNKNOWN,0 pending. Each120-second search ended at its external deadline; none established optimality.

All six indexed/recompute pairs produced identical independently replayed full lexicographic keys. OD02 and OD07 improved their freshly generated common seeds in both orders. OD10 retained its common seed in both orders. This fixed experiment establishes no indexed terminal-quality advantage, no speedup, and no optimality. It does not prove universal equivalence or absence of an advantage beyond these cases/budgets.

## Frozen scope and identity

- Execution source commit: `d2474ec6795c7be67509a727517b3ad04b19b93e`
- Source tree: `6db987e8c617988590a064c891a9f6229ab10195`
- Manifest SHA256: `8659e2995a494642c0203ac0011ff8fb190a64ea9e0848688377a5c7ce309d56`
- Cases: OD02 energy-only SOC3/10 N128 Hmax33; OD07 energy-and-scheduled SOC3/10 N149 Hmax37; OD10 energy-only SOC19/25 N32 Hmax26. Hmax was freshly derived from each independently verified common seed.
- Order: OD02 indexed/recompute; OD07 recompute/indexed; OD10 indexed/recompute; then OD10 recompute/indexed, OD07 indexed/recompute, OD02 recompute/indexed.
- Both arms use full routing, search-only terminal energy, original restricted hierarchy, the same common seed/key/domain,1GiB/two-source caches, and disabled member-read instrumentation.
- Three preparations,12 searches,12 fresh separate verifiers. No appended samples, retuned limits or holdout work.

## Resource accounting

Summed worker-stage wall time:2083.902947925 seconds. Total batch-parent process CPU:67.521368542 seconds. The per-stage wall times, supervisor CPU and sampled process-tree RSS are recorded in results.json. They are not worker CPU measurements; sampled RSS is not a hard aggregate memory limit.

Common/search stage limits:600s wall, per-process CPU600/601s. Search phase:120s externally enforced. Fresh verification:180s wall, CPU120/121s. All workers:CPU0 affinity, per-process8GiB address-space cap; thread environment pinned to1. Parent: cumulative90s soft/cooperative budget with10s prelaunch headroom, inherited hard limit preserved, not a claimed hard aggregate90s cap. No cgroup aggregate cap or cold OS-cache claim.

The predeclared reserve was11160 worker-wall seconds and10440 worker soft-CPU seconds, plus parent90. Actual worker CPU totals were not recorded and must not be inferred from wall time.

## Evidence

`results.json` contains all six exact pairs,12 complete accepted keys, three common seed witnesses/full keys, all27 stage statuses and resource observations. `evidence_index.json` binds each original file's size and SHA256. `evidence_bundle.json` is a small self-contained UTF-8 archive of actual JSON receipts, durable witnesses, common artifacts, provenance receipts and logs. Recover bytes by UTF-8 encoding each `files` value; verify against the index. No maps, dependencies or rebuildable native binaries are included. Verification artifacts establish the recorded independent fresh replay; inspecting the archive does not rerun the graph.

The original execution directory was not modified. The separate OD02 v2 integration gate (358.593379219 worker-wall seconds, parent13.567987405 CPU seconds) is documented in `../recovery_gate_20261017/` and is not pooled. The earlier v1 gate remains UNKNOWN after an oversized control receipt, with verified cleanup and four unattempted stages (its prepare wall368.155204252s remains separate). Historical UNKNOWN charge1237.41498645 and older experiments remain separate, without timing pooling.
