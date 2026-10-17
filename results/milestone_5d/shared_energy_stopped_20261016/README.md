# Shared energy-screen matched DEV analysis (stopped batch)

## Outcome and denominator

The fixed six-row denominator is retained: OD02 FLAT and HIER and OD07 HIER have fresh independently verified routes. OD07 FLAT stopped on supervisory CPU before its 120-second exact budget and has no fresh replay. Both OD10 rows remain blocked/unlaunched. The OD07 pair and complete three-case comparison are unavailable. No failed or blocked row is assigned a zero improvement.

| Row | Fresh primary improvement | Search wall s | Observed exact s | Sampled screen rejects/decisions | Activation s | Graph-copy s | Sampled peak RSS bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| od02.flat | 12.981068813% | 214.005 | 120.146 | 6/41 | 2.156 | 0.992 | 4570959872 |
| od02.hier | 12.228967174% | 213.444 | 120.192 | 7/39 | 1.802 | 0.625 | 4576292864 |
| od07.hier | 19.883338903% | 216.904 | 120.159 | 244/336 | 1.851 | 1.069 | 4529295360 |

Full exact initial/best lexicographic keys and rational improvement values are in SUMMARY.json; complete authenticated records and phase/progress details are in EXTRACTED.json. All three verified rows strictly improve their initial witness. No global lower bound or optimality gap is available.

## Pair identity and scope

OD02 is the only completed pair. The extractor checks exact equality of common-seed digest, initial full key, original Hmax, effective query, domain, shared treatment, graph/anchor/potential certificates, native source/binary/compiler and energy kernel source/binary/compiler/flags. Both history guards were installed before first routing. Per-role mappings and process-specific receipts remain distinct. OD02 Hmax is 33; OD07 HIER retains 37. Both methods use the same energy screen, full routing and insertion-order policies; this is not an OFF/ON payoff test.

OD02 FLAT improves 12.981068813% versus HIER 12.228967174% (exact values above take precedence). Their last progress samples record 121 versus 100 attempted advances, two expanded prefix groups each, and search-provider source runs 32 versus 30. These do not establish causality for the quality difference. OD07 HIER reproduces the previously verified 19.883338903% key, but its current sampled work differs; no matched OD07 conclusion is possible.

## Construction and observation limits

All completed search certificates validate two passes over 11,561,067 edges on 5,892,498 nodes, quantum exponent 20, cap 2^62−1 and exact beta 9007199248848495/9007199254740992. Packed owned graph bytes are 369,954,144; construction scratch 140,524,244 plus potential 47,139,984 bytes. These components are not a complete transient process-memory bound. Activation includes construction/validation and must not be added to its nested timers. Graph-copy cost is separately reported. Full receipts retain arithmetic environment/history and exact graph/query/kernel bindings.

Counters are last complete samples with unknown unseen-tail health. Rejected immediate finishes are not counts of avoided native source runs, since some terminal routes would use cached labels. Guard-pending values describe samples, not proof of operations in flight at termination. Progress counters and status are sampled independently. Routing operation times are inclusive and nested; no additive speedup decomposition is claimed. RSS is sampled, with observed polling gaps; it is not an exact peak or aggregate hard memory guarantee.

## Infrastructure stop and bounded diagnosis

OD07 FLAT raw supervisor reason is supervisor_cpu_soft_budget; the outer terminal is controller_error (Controller CPU ceiling exceeded), cleanup true, accounting_complete false and full 670 CPU seconds charged. The worker reached exact entry, but only 44.765371271 seconds were observed before stopping; preparation observed wall was 159.659353307 seconds and whole supervisor wall 204.424551782 seconds. No replay or successor launch is permitted.

Absolute process CPU was 7.159991639 seconds at supervisor entry and 50.706864917 at accounting end, with actual 50/60 limits; the supervised delta was 43.548670405 seconds. Process polling took 1,592 samples and immutable polling 363, with observed maximum gaps 2.321s and 2.403s. Completed-search supervised CPU was 15.281s (OD02 FLAT), 18.320s (OD02 HIER), and 33.643s (OD07 HIER). This establishes rising measured supervisory cost and the stop, but the receipts lack per-component CPU timers, so they cannot attribute the cost to process-tree scanning, metadata authentication, or other checks. No historical unexplained overhead is relabeled as solved.

Failed-stage raw files are separately hashed after cleanup and explicitly labeled raw_postcleanup_evidence, not successful terminal-authenticated evidence. They are retained for diagnosis only, not as a 120-second solver outcome. The smallest next diagnosis is a separately bounded static-fixture profile of actual supervision components on this captured state, preserving the failed batch and solver budgets; no rerun or budget increase is implied.

Execution/accounting and all fifteen scheduled slots remain owned by the controller consolidated report. This analysis does not replace that ledger or hide the failed/blocked denominator.

## Published evidence

- [Six-row denominator, exact keys and matched-pair checks](SUMMARY.json)
- [Authenticated completed records and separately labeled raw failed-stage observations](EXTRACTED.json)
- [Consolidated controller outcome and history](CONTROLLER_REPORT.md)
- [All fifteen scheduled slots and conservative resource accounting](STOPPED_LEDGER.json)
- [Original identities, independent stopped audit and analysis review](PROVENANCE_AND_REVIEW.json)

Nine attempted stages include the failed full 670-second debit. Their conservative charge is 1639.793342497999985 CPU seconds; adding the full 720-second orchestration allowance gives 2359.793342497999985 / 6360. The six later slots were never launched. Historical development, tests and reporting are separate and partially measured. Prior [Go1 results](../go1_contribution_20261015/README.md), the [energy OFF/ON result](../energy_screen_ablation_20261016/README.md) and the original OD07 N128 exhaustion-unknown remain unchanged. This batch does not establish an OFF/ON payoff, a complete three-case comparison, a general HIER advantage or an optimality gap.

All 135 analysis evidence pins and 923 consolidated stopped-result pins were rehashed. Machine paths/process IDs are omitted; retained raw failed-stage evidence is diagnostic only. This compact publication is not a standalone graph/replay bundle, and it authorizes no numerical retry or source/default change.
