# M5-V R12 final scoped acceptance and preservation

## Decision and source boundary

The mathematical candidate at `1cdf13b9f8893c11eba464ce9876354aba423a76` on `codex/milestone-4r-b1` is ready for **scoped M5-V correctness acceptance** under the pinned A28/B64 H4 inputs, the separately admitted C32/H4 representation, and the source-bound C01 HIER collector receipts. The independent final review found no new numerical-correctness blocker in this scope. `src/timecut5` and `validation/reference5` are byte-unchanged from the reviewed `2cc1ff2` checkpoint. The [exact candidate CI run](https://github.com/yduan12323/HiRoute/actions/runs/38124601465) passed installed-wheel and D0 bootstrap/one-block protocol jobs.

This is not a claim that a missing original combined 248-HIER/124-FLAT manifest was recovered or that C01 FLAT was collected. C01 HIER D-on and D-off remain accepted at their own historical source bindings; C32 remains a scoped optional adjacent-cut coalescing admission, not literal uncoalesced execution. The older B21-v1 ALG-4 equivalence remains refuted; the admitted v2 operator inventory is an explicit replacement mapping, not a retroactive v1 pass.

## Closed gate matrix

| Gate | Admitted evidence | Boundary |
| --- | --- | --- |
| A28/B64 frozen physical input and four modes | 92 unique IDs; 368/368 FLAT D-off/on and HIER D-off/on status/full-key comparisons with physical replay | Bounded H4 current-source candidate |
| HIER Region bounds and action partition | 2,665/2,665 visited/unreachable events checked by independent rational superset bounds or structural emptiness; 802/802 static splits partition the concrete action set | Dynamic refinement has zero operations in this candidate |
| Dominance and theory | 367 observed reductions, 2,533 cells, 3,526 witness mappings, separate 216 whole-domain frontier checks, and v2 SQ-1–SQ-8 theory under stated hypotheses | Instrumented current-source dominance is observational; the theorem and independent frontier checks carry separate roles |
| A/B final-result authority | [92/92 ledger (historical artifact)](REPRODUCING.md#historical-results); [29-case audit (historical artifact)](REPRODUCING.md#historical-results) checks 1,215,463 new exact regimes; 34 additional no-LP full-key proofs and three initial REF rows | Each row retains its pinned source/input; one S01 analytic/REF overlap counts once |
| Operator/reset v2 | 50 current-source objects for each of Drive, S, C, CS and three-way merge; ten named reset themes | Explicit v2 population replacing refuted v1 claim |
| Permanent 76-kWh regression | 11,072/11,072 finite regimes and original 28/48 charge witness replayed | One already-certified blocking case; not a new population run |
| C32 | 32 frozen states × four modes; 1,958 exact LP certificates, 96 strict-depth families and 128 physical witnesses independently rechecked | Scoped coalesced H4 admission only |
| C01 HIER D1/D0 | Separate accepted final collectors and full original-node cold audits: 21,838 and 35,685 query events; D0 covers 844,440 unique logical models | Historical source-bound HIER identities only; no C01 FLAT claim |

The [A/B completion report](M5_FINAL_AUTHORITY_COMPLETION.md), [current-source candidate review](MILESTONE_5_V_FINAL_CANDIDATE_REVIEW.md), [C32 admission](MILESTONE_5_C32_RETAINED_ADMISSION.md), [operator/reset inventory](MILESTONE_5_OPERATOR_RESET_INVENTORY.md), [C01 D1 report](MILESTONE_5_C01_FINAL_COLLECTOR_REPORT.md) and [C01 D0 report](MILESTONE_5_C01_D0_FINAL_COLLECTOR_REPORT.md) retain the case-level limits, hashes and receipts. Original lost A streams and historical B raw-stream gaps are not treated as passed flags: current-source analytic proofs and cold-checked exact certificates supply the final A/B authority. Earlier whitelist, supplemental-input and 2 GiB whole-envelope JSON failures remain in the 29-case proof archive rather than being hidden or counted as passes.

## Preservation and integration

The complete 29-case archive SHA-256 is `77f9a968c2508c29a084c361549801303b5653544703cd663ad31783f49e26c1`, with a 392-file manifest SHA-256 `71bb2931556e336824233b4a60aad40aa7ec403620129a8df1a1fe5addd75419`. Extraction and independent re-audit reproduce the 29-case audit receipt byte-for-byte (`cd8f26bdca77c66da57553a7317d87c9a8e91a073b932e27ff83ddc5bfe9468f`). All server experiment originals remain in the isolated tool directory; the Mac evidence archive is additive.

The production verifier `/home/dy/HiRoute/project` remains at `3ad6e385903b631579df059b48d9ea6037728da7`. Its read-only recomputed 119-file source inventory is `9b3f2a1b1c2a3b36533ea42e744b94e33f5929730ec7cfe11aa0f2e586caf5ad`; no D0 or REF worker remains running. Integration into `main` must use the reviewed branch by fast-forward if `origin/main` remains its ancestor. Do not pull the branch into the frozen production verifier as part of this acceptance.
