# Retained A/B certificate review — 2026-10-11

This review is limited to the recovered checkpoint bytes and the newly recorded, bounded observational A replay. It makes no claim about the unavailable original A `stream_execution_v1` run. No REF LP regimes or full A/B populations were rerun. The production verifier stayed at `3ad6e385903b631579df059b48d9ea6037728da7`.

The adjacent `historical_ab_audit/MANIFEST.json` lists SHA-256 for each published auditor, input archive, generated receipt, and event mapping. `b_original_audit_evidence.tar.gz` retains the original `aggregate_g8_v3.py`, frozen verifier and LP checker sources/manifests, 20 aggregate LP certificates, 128 B traces and their reports, B case inputs and retained REF reports. It also contains the retained A inputs. Extract it under an `ab_evidence_tree/` directory. Extract `a_targeted_traces.tar.gz` under `a_trace_recovered/` and `a_trace_stage.tar.gz` beside it. The scripts in the audit directory then resolve their source paths directly.

## B: every visited node bound

The published `b64_g8_node_reaudit_20261011_independent.json` is a fresh execution of the original read-only `aggregate_g8_v3.py` (the `utc` field differs from the first replay). The independently run `verify_b_node_evidence.py` checks all 1,551 rows against exact trace bytes and event indexes, 64 trace reports, 64 referenced REF reports, and the 20 aggregate LP rows. Original evidence hashes are in `b_node_evidence_review_20261011.json`. The result is 20 aggregate LP superset, 444 global infimum, 627 global infeasibility, 144 directed reachability, 314 prefix superset infimum, and 2 empty prefix superset. No targeted REF regimes are needed for this conservative bound claim.

For each of the 20 LP rows, the frozen auditor rechecks the exact rational primal/dual certificate, independently regenerates the graph potentials and relaxation, matches the case and trace event, and proves `Region lower bound ≤ relaxed optimum`. The mathematical inclusion is: an exact inherited-mask node plan is an original physical plan extending its trace prefix and taking one listed C action; its projection has `H ≥ prefix length + 1`, `Q ≥ max(0, road energy + reserve − initial energy)`, and charge duration `D ≥ minimum segment slope × Q`. Dropping integrality, strict charge positivity, intermediate battery conditions, and other restrictions enlarges that set. Frozen edge and selected-leg potentials establish the route totals for every path in those 20 line-graph cases. Other B rows use an independently checked reachability exclusion, or a retained global/prefix REF infimum for a superset of the node plan set. None computes an exact node optimum or infers exact emptiness from a nonempty superset.

The recovered patch lacks 52 raw v2 streamed REF regime files. Their report-level `fully_replayed` status cannot be independently checked against those missing raw bytes. Original frozen REF records likewise have no raw certificate replay here. Those provenance limits apply to the 1,311 B rows using streamed REF reports and 240 using original frozen reports; the 20 independent LP rows are bound by their separate certificates. The retained B primary-bound claim is conditional on the authenticated reference reports where they supply an infimum.

## A: bounded observational events

The 56 new HIER traces from 28 retained A cases have 995 Region decisions and 119 unreachable enqueues. The exact event keys remain in `ab_gap_ledger_20261011.json`. The 848 Region decisions with `bound ≤` saved global primary infimum retain their historical REF-report dependence. The other 147 Region decisions and all 119 unreachable enqueues now have local, no-LP checks:

| Events | Result | Per-event proof |
| ---: | --- | --- |
| 139 strict prunes | certified for newly recorded events | 74 deduplicated `(case, prefix, actions)` superset models; 150 terminal sequence certificates, mapped back to trace hash and event index |
| 8 retained decisions with no global infimum | certified empty | `A18_capacity_overflow_infeasible`: selected direct leg needs 7 energy from initial 2; every route through `x` needs an `x→z` leg of 6, exceeding capacity 5 |
| 119 unreachable enqueues | certified empty | independent selected-leg reachability for every listed action and its destination continuation |

`a_analytic_superset.py` verifies that the independent REF selected legs equal the frozen producer's selected legs for all target A cases. For each deduplicated query it enumerates every terminal sequence with the required prefix and next action. Every exact node plan must belong to one such sequence. For each sequence it computes a rational lower bound from selected-leg road time, all stop overheads and penalties, the minimum charging slope times the unavoidable total charge, and service duration/window lower bounds. It drops intermediate battery feasibility, charging upper bounds, strict charge positivity, and other constraints, so the represented plan set is a superset. For S at a separate stop, charge and service durations add; for CS, their total elapsed contribution is at least their maximum. The absolute service-window completion bound is checked separately. All 139 inequalities `Region bound ≤ minimum sequence lower bound` pass. The JSON stores every sequence's components, every query, and every event mapping. `a_residual_checks.py` verifies the 8 and 119 events independently.

The analytical replay used the B-frozen `579c6db` producer source because the original A source identity files and `stream_execution_v1` directories are missing. The bounded A run matched every saved case status/key and its frozen versus traced output, with zero optimizer calls in 17.19 seconds and a peak RSS of about 84 MiB. This certifies the new observed event set; it cannot prove the unavailable original A run visited exactly the same nodes. The A final report's 848 global comparisons also still depend on its historical reference results.

## Dominance continuation and refinement scope

`check_ab_dominance.py` observed all D-on reductions under the same B-frozen producer for 28 A and 64 B cases, comparing each final output with the frozen solver. In 12 seconds and about 81 MiB peak RSS, 367 reductions mapped 3,526 input cuts to dominating output cuts across 2,533 exact rational arrangement cells. The receipt stores per-cell input-to-output witness indexes. The arrangement includes singleton endpoints and affine crossings; within each open cell, active domains and the time order of affine cuts are fixed. Same-state, same-energy `probe.dominates` additionally checks time/attainment, `rho`, and prefix order. The sufficient continuation implication is Theorem 3.1 of `docs/MILESTONE_5_TIME_CUT_THEORY_REVIEW_V2.md`: at identical state and energy, no-worse time/attainment and `rho`, with prefix tie order when `rho` ties, preserves a no-worse counterpart for every legal suffix. The 92 D-on trace hashes are bound separately in `ab_dominance_trace_bindings_20261011.json`. This is a sufficient continuation preorder under that source, not an exhaustive enumeration of every future plan and not authentication of the lost original A producer.

The retained producer constructs a static binary Region tree once (`build_regions`), then visits existing children after each `partition` event; it has no dynamic Region refinement operation or event format. The retained D-on traces contain 158 A and 220 B static partitions, with no dynamic refinement or dominance-deletion event kind. Dynamic refinement therefore has **zero applicable operations in this producer**. A broader dynamic-refinement theorem, or a claim about the unavailable original A producer, remains outside this evidence. The dominance observation supplies new continuation coverage for this B-frozen source only.

## Reproduction

From a fresh directory containing the published audit files:

```sh
mkdir ab_evidence_tree a_trace_recovered
tar -xzf b_original_audit_evidence.tar.gz -C ab_evidence_tree
tar -xzf a_targeted_traces.tar.gz -C a_trace_recovered
tar -xzf a_trace_stage.tar.gz
python -B ab_evidence_tree/results/milestone_5_acceptance_b64/acceptance_populations/bound_audit/aggregate_g8_v3.py --output b_reaudit.json
python -B build_ab_gap_receipt.py
python -B verify_b_node_evidence.py
python -B a_analytic_superset.py
python -B a_residual_checks.py
```

`check_ab_dominance.py` requires its published receipt path to be absent because it uses exclusive creation; run it in a fresh copy of the extracted directory. Its 180-second alarm and 2 GiB RSS cap are enforced by the script. The originally staged server A trace replay also had a 180-second alarm and 2 GiB address-space cap. No replay command updates the production verifier.
