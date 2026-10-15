# Related work and comparison boundary

This is a source-grounded manuscript draft. The three cited methods solve different physical or operational problems; their published numbers are not HiRoute benchmark results.

## Single-vehicle road routing with charging

Baum, Dibbelt, Gemsa, Wagner, and Zündorf's [CHArge work](https://doi.org/10.1287/trsc.2018.0889) minimizes a single battery-electric vehicle's overall road-trip time while choosing charging stops and continuous charging decisions. Its label-setting method propagates state-of-charge tradeoffs, with A* potentials and contraction-hierarchy techniques for road-network speedup; charging-station initiation overhead and heterogeneous charging behavior are part of the model. The [full paper](https://arxiv.org/html/1910.09812) is the appropriate algorithm source. HiRoute's scheduled human activity, same-stop charging/activity overlap, explicit C/S/CS Site actions, and lexicographic attained-face status for J then Q are distinct questions. That distinction does not establish superiority on CHArge's road-routing task.

The [TheMarex/charge repository](https://github.com/TheMarex/charge) is an experimental EV route-planning implementation associated with Niklaus's thesis, not a verified official implementation of the Baum et al. paper. The [keyan/ev_routing_engine repository](https://github.com/keyan/ev_routing_engine) describes a limited inspired implementation. Neither repository has been built or run in the frozen HiRoute input environment; neither should be labeled an official CHArge benchmark. An external comparison would first need verified code provenance, license, build, matching graph and charging policy, and an explicit common task.

## Fleet routing and pricing

[Liang, Dabia, and Luo](https://arxiv.org/html/2108.01273) study a fleet electric-vehicle routing problem with customer service, vehicle capacity, time windows, and piecewise-linear approximations to nonlinear charging. Their branch-price-and-cut method uses forward and backward recursive functions inside pricing to jointly evaluate route and charging decisions; the fleet objective is total route duration. These are important charging-aware exact-method precedents, but a customer-routing pricing subproblem is not the same experiment as HiRoute's single-road-trip activity and lexicographic terminal semantics. We have not verified an author-code build or a common-instance adapter.

[Enerbäck, Eveborn, and Rönnberg](https://drops.dagstuhl.de/entities/document/10.4230/OASIcs.ATMOS.2024.3) study a labeling algorithm for the elementary shortest-path pricing problem of EV routing with time windows and piecewise-linear recharging. Charging-aware completion bounds can be combined with ng-route relaxation; pricing may have dual-induced negative reduced costs. Their result supports a methodological comparison of bounds and labels, not a direct performance claim on HiRoute's road/activity problem. The [linked research repository](https://gitlab.liu.se/eliro15/labeling-algorithm-for-evrptw-plr) currently presents an Anubis access-denied page in our inspection; its license, build, and outputs remain unverified. No alternate access route was attempted.

## Comparable internal baseline to implement

**Current implementation boundary (2026-10-12):**
`sequential_no_overlap_baseline` independently replays the fixed deterministic
proposal stream under charge-then-service timing and selects its best feasible
proposal. It is a bounded construction comparator, not the exact re-optimization
described below. Its directed synthetic overlap test passes in normal and
optimized Python; no source-bound real sequential main comparison has run.
The earlier real OD02 N8 first-feasible diagnostic only compared seed selection
within one proposal stream. The four-row real supplemental comparison is
registered after main began in
[`MILESTONE_5D_SUPPLEMENTAL_PROTOCOL.md`](../docs/MILESTONE_5D_SUPPLEMENTAL_PROTOCOL.md)
and is now terminal: all four sequential attempts timed out before a completed baseline result. Do not attribute an exact sequential optimum or a real
transport benefit to the current evidence.

For the D5.4 internal *sequential charge-then-activity* baseline, retain exactly the same OD, candidate Site identities, selected directed road legs, battery and piecewise charging primitive, scheduled window, positive-charge rule, stop penalty, and finite search domain as the HiRoute comparison. At a single physical stop, charge first and then perform the scheduled activity: `dwell = overhead + charge_time + activity_duration` for a joint C/S event, with window compatibility checked at the actual activity start after charging. A shared vehicle stop contributes one H and one overhead. Pure C and pure S stops retain their ordinary semantics. This disallows overlap by a clearly stated baseline policy; it does not split one stop into two vehicle visits or charge overhead twice.

The baseline must *re-optimize* route, Site sequence, continuous charge amounts, and schedule timing under this sequential policy. Merely delaying the activity on a HiRoute witness is a feasibility transformation, not a baseline optimum. A minimal implementation can reuse the existing exact physical replay and selected-leg inputs with a separate, source-bound stop-duration policy; it must not silently redefine the accepted HiRoute exact solver. First test toy cases where charge/activity overlap changes feasibility or the best key, a joint action counts once, a hard window ends exactly at service start, and positive charge approaches but does not attain an endpoint. Independently replay every emitted witness. If the baseline search is only heuristic, report a feasible incumbent and gap/status as available, never an exact optimum. Compare only rows where both policies share the frozen input contract and explicitly record unmatched or timed-out rows.

None of these sources or internal diagnostics supports a claim that HiRoute beats a published state of the art. The fixed Pilot establishes one completed FLAT/HIER internal exact-key agreement and ten censored method runs; the original main is terminal with zero exact completions and external common-input baseline execution remains unavailable.

## Compact comparability matrix

| Family and existing citation | Domain and charging | Windows / objective | Same-stop activity overlap | Attained-face status | Same-input execution |
|---|---|---|---|---|---|
| Baum et al., CHArge; doi:10.1287/trsc.2018.0889; arxiv:1910.09812 | Single EV road routing; continuous charging and heterogeneous stations | Overall road-trip time; HiRoute human-activity window equivalence not established | HiRoute-style optional activity model not established | HiRoute J-then-Q unattainment handling not established by this review | No verified official common-input implementation run; candidate repositories are not verified author code |
| Liang, Dabia and Luo; arxiv:2108.01273 | Fleet routing/pricing; piecewise-linear nonlinear-charging representation; exact recursive functions | Customer capacity/time windows; total route duration | Same human-activity overlap contract not established | HiRoute attained-face equivalence not established | Author-code build and common-instance adapter not verified |
| Enerbäck, Eveborn and Rönnberg; doi:10.4230/OASIcs.ATMOS.2024.3 | EV routing pricing labels, charging-aware completion bounds, piecewise-linear recharging | Time windows; pricing with potentially negative reduced costs | Same human-activity overlap contract not established | HiRoute attained-face equivalence not established | Linked code access denied in prior review; license/build/output unverified |
| Internal sequential charge-then-service construction | Same fixed candidate and selected-leg domain; continuous proposal charges | Same activity window and declared key; best feasible fixed proposal | Deliberately disallowed; one combined stop and one overhead | Feasible construction only, not a global sequential optimum | Four prescribed supplemental attempts; all four attempts timed out before completion; no auditable transportation comparison |

These mismatches justify scoped methodological comparison and explicit unavailability of an external runtime claim. They do not establish HiRoute superiority or prove that other methods cannot be extended.
