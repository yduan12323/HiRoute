# HiRoute paper positioning and evidence limits

## Claim to retain

HiRoute studies source-bound single-trip EV stop planning with continuous charging and an optional hard-window human activity at a vehicle Stop Site. C, S, and CS are Site actions; compatible charge and activity can share one stop and one overhead. The exact diagnostic objective is lexicographic `(J, Q, H, Π)` on attained faces, so an unattained J infimum has no Q/H/Π optimum to report. This semantic contract is different from pure road fastest-feasible charging and fleet customer-service pricing.

## What current evidence establishes

The fixed six-base-query Pilot, summarized in [`fixed_pilot_summary_20261011.json`](../results/milestone_5d/continuation_20261011/fixed_pilot_summary_20261011.json), checked 18 nested input rows. Six OD02 rows had independently replayed multi-stop seeds; 12 OD00/OD01 rows retained `incumbent_search_failed`. Of 12 bounded exact FLAT/HIER method runs, the OD02 no-activity eight-Site pair attained the same independently replayed exact key after complete finite-domain search. Ten runs timed out and have no terminal exact key. The Pilot includes full selected-leg-table setup cost; it is not evidence of table-free large-domain deployment or a HiRoute win over published methods.

The [post-Pilot decision record](MILESTONE_5D_POSTPILOT_DECISION.md) identifies repeated immutable-table parsing during independent seed reconstruction as a source-visible setup bottleneck and proposes one reviewable performance change. It also separates the missing table-free certified provider and complete live OPEN recovery from that speed change. No optimized result, main matrix, ablation result, or external baseline run has been claimed.

## Literature comparison policy

Use [Baum et al.'s CHArge paper](https://arxiv.org/html/1910.09812) for continuous single-EV road charging algorithms, [Liang–Dabia–Luo](https://arxiv.org/html/2108.01273) for nonlinear-charging fleet branch-price-and-cut, and [Enerbäck–Eveborn–Rönnberg](https://drops.dagstuhl.de/entities/document/10.4230/OASIcs.ATMOS.2024.3) for charging-aware pricing completion bounds. Explain the model and objective mismatch before any runtime comparison. Do not call TheMarex/charge official CHArge code; do not claim the LiU repository is runnable while access, license, and build remain unverified. The detailed comparison and the proposed internal sequential baseline are in [`paper/related_work.md`](../paper/related_work.md).

## Smallest D5.4 baseline gate

Implement a separate sequential stop-duration policy on the same frozen query/leg/Site inputs: at a joint stop, charge first, then perform the activity within the unchanged hard window; count H and overhead once. Re-optimize continuous charge and Site sequence. Source-bind this policy and independently replay witnesses. Validate hard-window equality, joint-stop accounting, positive-charge endpoint nonattainment, and the completed toy exact-key cases before comparing Pilot rows. Label heuristic output as incumbent only. This is an internal model comparison, not a published-method reproduction and not a second post-Pilot performance optimization of FLAT/HIER.

Final holdout selection and access are protocol matters for a later phase; no holdout execution is part of the present work.
