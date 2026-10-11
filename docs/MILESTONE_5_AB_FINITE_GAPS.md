# A/B finite proof gaps from retained evidence

Follow-up: [MILESTONE_5_AB_CERTIFICATE_REVIEW.md](MILESTONE_5_AB_CERTIFICATE_REVIEW.md) records the later bounded certificate checks for the 139, 8, and 119 A events, the B source replay, and the remaining historical provenance limits. This page preserves the earlier preflight state.

This review uses the recovered `HiRoute-C32-128-checkpoint-a2c4a7f.zip` patch and the separately retained A inputs. It did not rerun any A/B REF population. The frozen production verifier at `/home/dy/HiRoute/project` was not updated.

## B64

The historical `bound_audit/g8_current_v3.json` output was absent, while the original `aggregate_g8_v3.py`, production traces, source cases, reference reports, and aggregate certificates were retained. Re-executing that read-only auditor produced `b64_g8_node_reaudit_20261011.json` (SHA-256 `eae6ba7c88bdc09a5e8d55a6ac2d5516553d2f869eb6895dc7eb8713b25acece`). The separate gap ledger checked each node's trace hash, event index, and referenced report/certificate hash.

All 1,551 visited nodes have sufficient conservative bounds: 20 independent aggregate superset LP, 444 global infimum, 627 global infeasibility, 144 reachability, 314 prefix superset infimum, and 2 empty prefix superset. Required targeted REF regimes for these retained cases: **0**. This does not establish exact node-family optima or classify every node's exact emptiness. Fifty-two historical v2 raw regime streams named by the omission map are also absent from the recovered patch; the v3 node audit did not require them.

## Stage A

The original A final report covers 28 fixed H4 cases but explicitly excludes every visited Region bound, dynamic action/refinement traces, and dominance-deletion continuation certificates. Its `stream_execution_v1` evidence directories and four source/registration identity files are absent from the recovered checkpoints. The retained input cases were replayed under the B frozen `579c6db` observational trace source, in an isolated server directory with 180-second and 2 GiB limits. All 28 cases × 2 HIER dominance modes matched saved status/key and the frozen versus traced implementation; 56 trace files were recorded in 17.19 seconds with zero optimizer calls. This new source binding and output match do not authenticate the original A trace producer.

The 56 traces contain 995 Region decisions and 119 unreachable events. Against the retained final global primary infima, 848 Region decisions satisfy a global conservative inequality. All 139 decisions requiring local superset proof are strict prunes: 74 unique `(case, prefix, actions)` queries across 14 cases. Eight retained decisions have no final global primary infimum. The 119 unreachable events still require an independent source-bound reachability check. Dynamic refinement and dominance-deletion continuation events were not emitted by this observational trace.

The 74 local query union preflight is 150 terminal sequences and 26,155 LP regimes, including 14,760 in `SUP_A05_disconnected_physical_union` and 8,748 in `A15_waiting_erases_prefix_time_advantage`. The B additive graph certificate does not apply to these A graphs/schedules; all 139 attempts rejected its graph restriction. No such proof was relabeled. A full targeted REF solve is therefore not approved by this receipt. The minimal next work is independent no-LP validation of the 119 unreachable events, suitable local superset inequalities for the 74 keys, and explicit recording/continuation checks for dynamic refinements and dominance deletions. Any LP subset should be chosen only after a new count and bounded resource plan, without rerunning completed A/B REF populations.

Machine-checkable event keys, source hashes, and exact open items are in `ab_gap_ledger_20261011.json` (SHA-256 `689aec55f3a4a2cd6288bfc47f3bfb7b27d8bcb544417f5525b0c6a081ee819e`). The bounded A trace archive SHA-256 is `990eea881ad7bf13d6be5131d1ad24de3257e2c757b97c6ede16a51a68a780ea`; its receipt SHA-256 is `6cb1cfe8e7aaeeca856891baaaaeaa75765249e1cfd7ebebddc00578fbd50a05`.
