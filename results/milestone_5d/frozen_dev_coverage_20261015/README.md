# Finite frozen-DEV coverage result

## Outcome

Both remaining fixed cases produced saved feasible routes that survived separate fresh-process physical replay. OD06 scheduled low-SOC N128 persisted and recovered a strictly improved two-stop route. OD00 energy-only high-SOC N32 recovered its original one-stop route. Both exact searches reached their120-second caps, so neither result is an optimality certificate.

The earlier OD06 scheduled low-SOC N32 attempt is preserved as controller_error. Its worker completed the finite heuristic stream with zero proposals, and the independently reviewed additive audit supports that observation. This is unknown with respect to candidate-domain feasibility, not global infeasibility. The failure was a presence-only guard rejecting the observer's empty diagnostic checkpoint. N32 was not rerun. The separately admitted N128 attempt belongs to its larger, separately bound domain; its success is not backdated to N32.

## Measured rows

All phase times below are seconds since each search worker's entry, excluding parent preflight.

| Frozen selection | First persisted provisional route | Independent feasible admission | Actual exact engine start | Original Hmax | Fresh replay |
|---|---:|---:|---:|---:|---|
| OD06_energy_and_scheduled_soc3_10_n128_flat |67.585871242|78.971827546|111.767807062|39|Improved feasible witness|
| OD00_energy_only_soc19_25_n32_flat |13.240939138|22.980695633|54.029865413|28|Initial feasible witness retained|

The first saved route is provisional until independent admission. Actual exact entry is later still. The saved seed stream had one proposal/accepted route at its intentional first-feasible cutoff; it did not claim completed heuristic enumeration.

OD06's primary objective decreased from60345046666582454103/1717986918400000 (35125.440141758) to218197779590137848091/6871947673600000 (31751.955916136), a9.604105% reduction. Fresh replay verified strict improvement of the full lexicographic key, not only its scalar component, and retained the original depth39. The persisted route uses11118978435/CS then11067753859/C; its full physical witness and charges are in the durable record.

OD00's primary objective remains8781744473943886403/343597383680000 with its original full key and one charging stop6038626919/C. Fresh replay verified the original depth28 and did not claim improvement.

## Whole stages and conservative charges

| Stage | Whole-stage wall seconds | Observed exact seconds | Conservative CPU charge |
|---|---:|---:|---:|
| OD06 N128 search |232.496937993|120.087733992|260.920750961|
| OD06 fresh replay |22.056922858|—|22.795461676|
| OD00 N32 search |174.838630916|120.071938794|193.820233597|
| OD00 fresh replay |18.846665397|—|19.375518797|

Exactly two searches and two fresh replays ran. All four controller terminals have verified cleanup and successful continuation gates. No extra search or replay is pending.

New stage charges total496.911965031 CPU seconds. Adding the full new120-second preparation allowance gives616.911965031 against the1760 maximum. The earlier failed attempt's670 charge plus its120 preparation allowance remains790, with no refund. Combined accounting is1406.911965031 against2550 across the failed phase and separately admitted continuation.

Charges are conservative parent-plus-wait4 accounting and may include descendant overlap; they are not unique measured CPU. Preparation allowances are charged reservations, not measured preparation time. Whole-stage wall includes controller preflight, worker, cleanup and postchecks under the existing accounting boundary. Observed exact wall includes watchdog polling/cleanup overrun beyond the nominal120-second threshold. Per-process limits and one-core worker affinity are enforced; no aggregate cgroup CPU/RSS guarantee is claimed.

## Identity, repair and retained failure

Admitted continuation parent SHA256:8067a5d5141f29028544c170e49467e38e38607244a064aea8a5a7ec41d9e095. The86-file source closure is7a77a90e49411b58091047bccf3c6a086ca4b283f03157f07aa7ee04136b4da5. Query/domain hashes, complete keys, source counts and record/replay hashes are in FINAL_COVERAGE_RESULT.json and the per-stage manifests.

Numerical generator, exact kernels, dynamic U/Hmax rules, native/compiler/cache guards and durable physical replay remained the reviewed versions. The new classifier distinguishes a completed no-incumbent diagnostic from a saved witness, including all-rejected proposals. Interrupted no-incumbent diagnostics have a separate event/count predicate that can yield only resource_timeout_unknown after authenticated clean containment; they never authorize exhaustion or expansion. The launcher pins the approved N32 additive audit and all99 prior evidence files without rewriting the old ledger.

The historical N32 setup breakdown remains in the stopped report. Its86.451-second native-build wall interval includes compiler-child work that worker-only CPU does not measure; interval-specific compiler CPU is unavailable. This run does not establish a speed regression or its cause.

## Scope

These are a few existing frozen DEV selections, with no holdout and no new case. FLAT only was executed here; no HIER superiority or generalized performance claim follows. Both exact timeouts and the historical controller failure remain visible. The concrete success is one independently recovered improved route and one independently recovered retained route across separately bound candidate domains. More diverse matched-method coverage requires a separately reviewed finite plan.

## Published evidence and reproducibility boundary

- [Consolidated result](coverage_result.json): exact objective keys, query/domain identities, stage times and complete accounting.
- [Historical N32 record](historical_n32.json): controller failure and observed zero-proposal stream retained; feasibility remains unknown.
- [Witness and replay projections](witness_evidence.json): saved routes, event energies/times, derived exact charges and fresh-process replay results.
- [Final independent review](final_review.json) and [provenance](provenance.json): reviewed inventory identity and original selected artifact hashes.

All 161 original inventory entries were rehashed before preparing this publication. The original inventory digest is 9836c023bd03b45182c1fb7ff397dbf9d510a70174a49f6d247bf2fa9c00fe71. Absolute machine paths, path-keyed source maps and process identifiers are omitted from projections. Original hashes identify the archived originals, not the sanitized bytes. The witness projections are not signed/loadable checkpoint records; this compact publication does not supply the graph, native binary or experimental runtime needed for a new physical replay. No experiment or new physical replay was run to create it.

This report-only increment installs no experimental coordinator or solver code. It records later durable-route evidence separately from the earlier [cold-query pair](../cold_development_20261015/README.md); no timing or durable-hook benefit is attributed across those different runs.
