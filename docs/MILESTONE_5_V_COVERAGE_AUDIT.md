# M5-V remaining coverage audit

Original audit date: 2026-10-08 UTC; updated 2026-10-10 UTC. Original server source:
`052a157b745cdaee463579bf8478d1f78d44838b`, branch
`codex/milestone-4r-b1`, project `/home/dy/HiRoute/project`.

**Two C01 HIER identities are accepted: D-on and D-off.** The remaining
requested identities and complete original M5-V gate matrix are open.
The [D1 report](MILESTONE_5_C01_FINAL_COLLECTOR_REPORT.md) and
[D0 report](MILESTONE_5_C01_D0_FINAL_COLLECTOR_REPORT.md) provide separate
measured counts, source lineage, commands, resources and receipts.

The [machine-readable audit](MILESTONE_5_V_COVERAGE_20261008.json) is a
**reconstructed audit ledger**, not a recovered combined frozen manifest.
It now records all 92 byte-verified original A/B physical IDs and their
historical result rows. It separately expands the 32 observed C states into
96 requested HIER D-off/D-on and FLAT D-on identities. Only the two C01 HIER
identities have qualifying final-collector receipts on their respective sources.

## Authoritative scope and the 248 / 124 accounting

The [research master plan](time_cut_v2_authority/HIROUTE_RESEARCH_MASTER_PLAN.md),
section 44, says:

> Correctness only.
>
> No scalability gate.

It requires independent REF, flat exact quotient and hierarchical exact
quotient solvers. The plan does not directly freeze a 248/124 manifest.
Sections 45 and 46 separately cover deployable development and frozen-algorithm
holdout; neither should be counted as M5-V correctness completion.

The [formal specification](time_cut_v2_authority/HIROUTE_FORMAL_SPEC.md),
sections 27–29, requires an independent REF without quotient reduction or
Region pruning, complete production-key parity including status/attainment,
zero bounded-case violations, and separate theory closure.
The [B2/B2.1 protocol](../MILESTONE_4R_B2_B21_EXPERIMENT_PROTOCOL.md),
sections 16, 18, 20, 22 and 31, adds both FLAT dominance modes, exact action
partitioning, constrained Region bounds and the complete gate matrix.
A FLAT D-on projection alone omits an original FLAT D-off obligation.

The [frozen A/B metadata registry](FROZEN_AB_REGISTRY.md) directly states:

> metadata: 24 h4 inputs, 3 physical supplements, 1 merge supplement, and 64 B cases.

It directly records 92 physical identities and 184 HIER D-off/D-on variants.
It also states that this is not current solver acceptance, the capture wrapper
was absent, and A04 is algebra-only rather than a 29th physical A case.
The corresponding loader
[`frozen_ab_registry.py`](../src/timecut5/frozen_ab_registry.py) checks original
input bytes and historical outcome identities; it performs no optimization.

| Accounting layer | HIER D-off/D-on | FLAT D-on | Meaning |
| --- | ---: | ---: | --- |
| Verified expanded A28 + B64 inputs | 184 | 92 (projection only) | 92 IDs and historical outcomes restored; no current-source acceptance |
| Observed C32 preparation inputs | 64 (requested) | 32 (requested) | 32 actual state IDs and hashes available; not acceptance |
| Requested combined arithmetic | 248 | 124 | (28+64+32)×2 and (28+64+32); no full original freeze located |
| Qualifying collector identities | C01-HIER-D1 and C01-HIER-D0 | None observed | Two distinct indexed C01 original-query/bound/witness receipts |

Thus the requested 248 HIER / 124 FLAT-D1 numbers are a conditional arithmetic
projection over the expanded A28/B64/C32 inventory. They are not direct quoted
numbers from plan section 44, not 248/124 observed passing results, and not the
whole original protocol. No complete frozen combined manifest was located
in the audited server checkout or recovered A/B archive. Its existence
elsewhere is unresolved. The arithmetic does not authorize substituting
new synthetic cases or dropping inconvenient identities.

## Evidence levels and current-source gaps

| Evidence level | What it establishes | What remains open |
| --- | --- | --- |
| Recovered A28/B64 historical reports | Original IDs, scoped H4 comparisons: A 112/112 four-mode, B 256/256; zero reported status/key mismatches | Current-source acceptance, missing gate-specific traces, literal inherited-family G8, whole M5-V |
| Historical C32 four-mode parity summary | A reported 128/128 key comparison | Original-query proofs, physical witnesses and each current-source identity |
| Frozen A/B metadata intake | Six raw-byte pins, 92 IDs, 184 HIER variants and historical status/key shape validated; 15 tests pass | Capture wrapper and current optimization/query/bound acceptance |
| C01 structural replay | Sealed trace structure and query indexing, supplemented by historical REF canonical-key match | Raw historical REF certificate replay and numerical acceptance by replay alone |
| C01 final collectors (D1 and D0) | Separate original indexed query coverage, reconciled numerical evidence, physical bindings and bound status | C01 FLAT, other cases, literal exact inherited-family G8 and whole M5-V |

The complete C01-HIER-D1 original-node domain audit subsequently passed on checker commit `b6c92893b483b383fafa38ce51f6ed0a85c48c1e`, reusing the accepted numerical and physical evidence while freshly checking all 21,838 original query events. Its 39-file manifest SHA-256 is `5216ef596e878cde069f00835e730dce57a487a0292c7400e5710ed8af2ae302`; zero new LP calls were made. See the [scoped D1 report](MILESTONE_5_C01_FINAL_COLLECTOR_REPORT.md#full-original-node-domain-audit-003). The [D0 node-batch preflight](MILESTONE_5_C01_D0_NODE_BATCH_PREFLIGHT.md) authenticated all retained paths. A separately profiled 4 GiB full-node audit then passed on checker commit `6a91a6b18a858a10b5206cad17402db72d5972a8`, freshly checking all 35,685 original query events with zero new LP calls. Its 43-file manifest SHA-256 is `301fce572a3cc9acc7fa737ab6d30ec8de3829ab0960e6156aa5af697eaf5fe9`. See the [scoped D0 report](MILESTONE_5_C01_D0_FINAL_COLLECTOR_REPORT.md#full-original-node-domain-audit-001).

## 2026-10-10 focused source and retained-node check

On development source `1eaff29c49340cee63afe4cee3f97c864ce8c52e`, five
separately bounded, single-thread regression groups passed: 30 PWA/REF
certificate-recovery tests, 6 provenance/trace tests, 7 bounded/hierarchy
tests, 8 real-adapter tests, and 24 REF tests (75 total). The logs are retained
in the isolated server checkout `/home/dy/HiRoute/g8_node_review_1eaff29/`.
They check affected code paths, not original-population acceptance.

The restored B64 report, SHA-256
`a45979a2a49909d61b25df46d35237120f85c46c8c266cf13b78c7ed627bb025`,
identifies its 12 original-source cases lacking raw certificates as B01–B06
and B09–B14. It retains their result/reference identities, but those identities
do not replace the missing raw certificates. A subsequent [scoped recovery](MILESTONE_5_B_MISSING_CERTIFICATE_RECOVERY.md) freshly certified all 173,456 finite regimes for exactly those 12 cases on source `6a91a6b18a858a10b5206cad17402db72d5972a8`, with 48/48 four-mode matches and all 12 status/full-key/regime rows matching that historical report. This fills the missing raw-certificate gap for those cases while preserving the historical source boundary. For C32, the hash-verified 32-state
input inventory is `results/milestone_5_real_export/query_states_resolved.json`
(SHA-256 `d4bd50215c8035552ca47a9bf4e175d580eb265a2e9acbeff5d574c60b08b57c`)
with immutable leg tables and original tree restrictions. The reported
historical 128/128 parity has no original C32 report file in the audited
project directories; `results/milestone_5_reference/validation_summary_final.json`
explicitly marks historical A20/B64/C32 completion false. C32 exact results,
per-case raw certificates and current-source receipts remain unlocated.

C01-HIER-D1 original query 1473 has 75 retained model proof rows. The first
single-coordinator node audit did not complete: the 2 GiB attempt failed while
decoding the 835,419,819-byte capture; the established 16 GiB AS / 20 GiB RSS /
3,600-second attempt authenticated the historical source plan and decoded the
v2 capture but timed out during independent full-trace verification before a
`CheckedTrace` returned. No LP ran, no retained certificate was newly checked,
and no bound was newly accepted. Both failure reports and the exact input hashes
are preserved in the isolated checkout. These failures preceded the scoped
successful audit below.

At source `74e8cdc05e4acaf980de1736685af0319bc04c67`, fresh attempt
`/home/dy/HiRoute/g8_node_review_1eaff29/g8-node-collector-1473.003`
independently verified the complete frozen trace with four bounded family
workers, then checked all 75 retained LP certificates for original query
1473, exact model ordinals `[649404,649479)`. Its genuine checked-node result
is `verified_bound`, with `bound_status=satisfied`, recorded bound
`47405636699724177/8796093022208`, zero new solver calls, and
`literal_G8_closed=false`. The result is scoped to this one inherited-family
query occurrence; it does not close global G8 or revise the accepted D1
collector. The fixed `retained-node-audit-v1` supervisor completed in
1,149.56 seconds with all descendants reaped, under 3,600 seconds, 16 GiB
child AS, 20 GiB group RSS and 2 GiB charged evidence. Its 40-file manifest
was cold verified (SHA-256
`0669f8ad83643321e02f5f8de8aa2781e2ff6f9d64ef6010bdf33e5a3335d885`);
the node receipt SHA-256 is
`353a510db1e99b001840148b7da8f5c66c03e0366b0aa333ce9d82d7f59a5cd3`.
The complete preserved archive and manifest are copied to Mac
`/Users/dy/Documents/Codex/2026-10-07/task/hiroute-g8-node-1473-74e8cdc-20261010/`,
with archive SHA-256
`249a0e594565ec1bef46f5744ff8f483aadfd23a3ca5020f3002fb3d1408bddd`.

Historical checkpoint evidence is explicitly bounded in
[`MILESTONE_5_CUT_CHECKPOINT.md`](../MILESTONE_5_CUT_CHECKPOINT.md):
18 new analytic + 100 generated cases and 400 cross-solver comparisons
do not mean original A20/B64/C32 completion or real 2,047-region integration.
The [real input audit](../experiments/time_cut_v2/real_inputs/REAL_INPUT_AUDIT.md)
and [adapter report](MILESTONE_5_REAL_INPUT_ADAPTER_REPORT.md) are historical
preparation records. Their then-missing real inputs have subsequently been
restored; preparation and restored input availability still do not prove
remaining solver identities.

The recovered A report records 28 bounded H4 physical cases, 112/112
four-mode parity matches, zero status/key mismatches and passing scoped tests
for all 20 named themes. It explicitly does **not** claim 20 complete-graph
solves. A04 is algebra-only; its remaining visited-bound, dynamic refinement,
deletion, 50-algebra and reset obligations are separate. The B report records
64 distinct five-factor combinations, 256/256 full-solver comparisons and zero
mismatches. Its original-source raw certificates for 12 cases were not
retained; fresh scoped certificates for exactly those cases are now indexed in the [recovery receipt](MILESTONE_5_B_MISSING_CERTIFICATE_RECOVERY.json). `exact_inherited_family_optimizer_implemented=false`.
These are byte-verified historical reports at their stated source versions,
not present-source collector acceptance. The reported C 128/128 four-mode
parity remains a historical summary without the original report files here.

The historical D1 collector at source `052a157b` required `dominance=True`
(`experiments/time_cut_v2/recorded_real/final_collector.py`, lines 228–230 at
052a157b), while `recorded_real/plan.py`, lines 103–105 and 195–198, fixes
C01, H4, eight Sites, 2,047 regions and the representation. C01's D1 receipt
cannot be copied to D0 or another case; D0 has its own accepted receipt at
source `3ad6e38`. The admitted indexed family also
cannot be renamed as literal inherited-family G8.

## Recovered original A/B material and historical scope

On 2026-10-10 the user supplied the existing Library archive as a local
Downloads file. Its 23,810 bytes matched SHA-256
`7d001b1ce2ec83ac953b1891a93562e3b9060195e9dd5f5bcc6a9687b50e7679`.
All ZIP entries passed path, symlink and size checks. The six pinned files
were copied without replacing an existing server file to their documented
`/home/dy/HiRoute/project/results/` paths; their raw bytes matched the
[registry pins](FROZEN_AB_REGISTRY.md). The original Downloads file and the
separate server recovery copy remain intact. The earlier Library helper HTTP
403 remains a historical failed attempt; this recovery used the user's local
copy, with no retry of that transfer.

The trusted Python metadata intake returned `metadata_only_intake_validated`,
92 A/B physical cases, 184 HIER variants and `solver_executed=false`.
All 15 focused tests passed, including both original-population tests without
skips. The [machine ledger](MILESTONE_5_V_COVERAGE_20261008.json) lists each
A/B case ID, source file pin, historical status/key, and B factor levels.
The input `independent_expected` metadata remains separate from the actual
historical result rows.

| Recovered group | Historical report outcome | Scope boundary |
| --- | --- | --- |
| A28 | 24 attained, 2 infeasible, 1 primary unattained, 1 secondary unattained; 112/112 four-mode parity, zero reported key/status mismatches | H4 scoped diagnostics; A04 algebra-only, not a 29th physical case; not all 20 themes are complete graph solves |
| B64 | 48 attained, 16 infeasible; 64/64 distinct factor combinations, 256/256 full-solver comparisons, zero reported mismatches | H4 bounded diagnostic; 12 originally missing raw-certificate cases now freshly recovered on a separately pinned source; literal inherited-family optimizer incomplete |

S07 is now identified as `S07_effect_free_via_site_excluded` in the A input.
Its `sites={"v":[]}` row and historical A result report
`infeasible_within_H_ref` with four-mode parity. The historical row does not
establish a current-source S07 collector receipt.

## Mandatory semantic and structural checklist

The following checklist remains open at the full-population level; individual
passing rows require original identity, input hash, implementation/source,
representation, full expected/actual key, receipt and gate-specific evidence.

- [x] Recover original A case IDs and historical scoped theme mapping; separately audit the full-graph and gate-specific gaps: charging segment/breakpoints;
  increasing/decreasing frontier; disconnected energy domain; merge crossing;
  deadline/start clipping; all three CS dominance/branch-switch behaviors;
  zero-charge limit; unattained positive-charge infimum; attained interior;
  time/charge/Site-tuple ties; energy-floor/capacity clipping; two-charge
  redistribution; repeated-Site/depth behavior.
- [ ] Preserve additional terminal and C/S/CS sequence cases from B2/B2.1
  section 9, including effect-free Site/action semantics and infeasibility.
- [ ] Preserve independent REF and both FLAT dominance modes, full status/
  attainment/key comparisons and the original action-partition/Region-bound gates.
- [ ] Map original coalescing, refinement, pruning/deletion and visited bounds
  to actual query/physical evidence, distinguishing indexed supersets from
  the literal exact inherited family.
- [x] Recover B64 original IDs and historical source versions; verify all
  4 topology × 2 SOC × 2 schedule × 2 capability × 2 tightness combinations.
  Present-source acceptance remains open.
- [ ] Verify all 32 C states and requested solver identities separately;
  H4/eight-Site preparation alone is not proof.
- [ ] Retain the exact-validation protocol's 50 algebra objects, permanent
  44,950-second/76-kWh blocking regression, ten reset adversaries and
  explicit explanations for changed legacy expectations
  ([B2.1 exact protocol](../MILESTONE_5_B21_EXACT_VALIDATION_PROTOCOL_V1.md),
  sections 21–26). Its v1 equivalence claim was refuted; do not revive that
  refuted assertion as a new passing criterion.
- [ ] Freeze a complete aggregate case/solver/dominance/representation/input/
  source ledger and reconcile each receipt against all applicable gates.

## S07: preserve identity and distinguish a vacuous obligation

The restored original A input contains `S07_effect_free_via_site_excluded`
with `sites={"v":[]}` and an analytic certificate explaining that the
physically feasible via-v drive is effect-free and cannot become a semantic
stop. The restored historical A report records `infeasible_within_H_ref` and
four-mode parity for S07. It is a historical scoped result, not a
current-source acceptance receipt.

B2/B2.1 section 9 excludes effect-free via-Sites from the action set; section
18 requires exact partitioning of concrete semantic next actions. Conditional
on an authentic S07 input and a genuinely empty concrete action family, the
action-family bound obligation is vacuous. This is an inference from those
rules, not a separate current-source S07 acceptance statement. The two C01 collectors
demonstrate the required accounting pattern: D1 retains 9,666 and D0 retains
15,795 empty-action query rows with `vacuous_empty_restricted_family`.

Empty actions alone do not prove a whole case. S07 still needs matching current-source trace, denominator, terminal and
direct-drive feasibility, full-key and any applicable physical-witness checks
for present-source acceptance.
An empty family must be recorded as empty; it cannot be counted as a nonempty
attained optimum or justified by an unverified historical summary.

## Smallest rational next validation plan

1. **Preserve the recovered A/B input and historical identities.** All six
   source files and 92 IDs now validate. Keep their historical status/key
   reports bound to their original sources; locate any still-retained raw
   per-case certificates and the combined original gate manifest. No input
   recovery or duplicate solve is needed for the metadata step.
2. **Reconcile each remaining gate against these IDs.** Use the recovered
   A20 theme and B64 factor mappings, C32 state IDs, and source-specific
   reports. Separate historical parity from present-source original-query,
   physical-witness, FLAT D-off/D-on, algebra/reset and literal G8 proof.
   Expand computations only where a specific obligation lacks valid evidence.
3. **Preserve accepted D0 evidence.** C01-HIER-D0 has its own frozen
   population, independent cold receipts and final acceptance. Reuse its
   844,440 successful models, 3,299 blocks and 105 registry entries. Do not
   rerun them to fill unrelated gates.
4. **Choose the next gate from the reconciled gaps.** Prioritize a minimal
   original algebra/reset or literal inherited-family case with independent
   REF and physical witness checks, then expand only identities still lacking
   qualifying receipts. Whole M5-V completion requires all original
   correctness gates.

This 2026-10-10 update records A/B input recovery and metadata-only validation.
No numerical experiment or raw-evidence rewrite was launched.
