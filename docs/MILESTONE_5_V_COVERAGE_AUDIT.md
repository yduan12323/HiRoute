# M5-V remaining coverage audit

Original audit date: 2026-10-08 UTC; updated 2026-10-09 UTC. Original server source:
`052a157b745cdaee463579bf8478d1f78d44838b`, branch
`codex/milestone-4r-b1`, project `/home/dy/HiRoute/project`.

**Two C01 HIER identities are accepted: D-on and D-off.** The remaining
requested identities and complete original M5-V gate matrix are open.
The [D1 report](MILESTONE_5_C01_FINAL_COLLECTOR_REPORT.md) and
[D0 report](MILESTONE_5_C01_D0_FINAL_COLLECTOR_REPORT.md) provide separate
measured counts, source lineage, commands, resources and receipts.

The [machine-readable audit](MILESTONE_5_V_COVERAGE_20261008.json), updated
with the D0 receipt on 2026-10-09, is a
**reconstructed audit ledger**, not a recovered original frozen manifest.
It explicitly expands the observed C32 inputs into 96 requested identities
(HIER D-off/D-on and FLAT D-on), with two qualifying C01 HIER receipts on their respective frozen sources.
It retains unresolved A/B member lists as null, and does not invent IDs,
acceptance percentages, or successful vacuous cases.

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
| Declared expanded A28 + B64 | 184 | 92 (projection only) | A/B original IDs require missing input files |
| Observed C32 preparation inputs | 64 (requested) | 32 (requested) | 32 actual state IDs and hashes available; not acceptance |
| Requested combined arithmetic | 248 | 124 | (28+64+32)×2 and (28+64+32); no full original freeze located |
| Qualifying collector identities | C01-HIER-D1 and C01-HIER-D0 | None observed | Two distinct indexed C01 original-query/bound/witness receipts |

Thus the requested 248 HIER / 124 FLAT-D1 numbers are a conditional arithmetic
projection over the expanded A28/B64/C32 inventory. They are not direct quoted
numbers from plan section 44, not 248/124 observed passing results, and not the
whole original protocol. No complete frozen combined manifest was located
in the audited server checkout or small retained metadata. Its existence
elsewhere is unresolved. The arithmetic does not authorize substituting
new synthetic cases or dropping inconvenient identities.

## Evidence levels and current-source gaps

| Evidence level | What it establishes | What remains open |
| --- | --- | --- |
| Historical bounded numeric parity | Status/full-key comparison on its own bounded inputs and historical source | Original expanded A28/B64/C32 population and current-source rerun |
| Historical C32 four-mode parity summary | A reported 128/128 key comparison | Original-query proofs, physical witnesses and each current-source identity |
| Frozen A/B metadata intake | Original-byte/identity validation when six pinned files are present | Capture wrapper and current optimization/query/bound acceptance |
| C01 structural replay | Sealed trace structure and query indexing, supplemented by historical REF canonical-key match | Raw historical REF certificate replay and numerical acceptance by replay alone |
| C01 final collectors (D1 and D0) | Separate original indexed query coverage, reconciled numerical evidence, physical bindings and bound status | C01 FLAT, other cases, literal exact inherited-family G8 and whole M5-V |

Historical checkpoint evidence is explicitly bounded in
[`MILESTONE_5_CUT_CHECKPOINT.md`](../MILESTONE_5_CUT_CHECKPOINT.md):
18 new analytic + 100 generated cases and 400 cross-solver comparisons
do not mean original A20/B64/C32 completion or real 2,047-region integration.
The [real input audit](../experiments/time_cut_v2/real_inputs/REAL_INPUT_AUDIT.md)
and [adapter report](MILESTONE_5_REAL_INPUT_ADAPTER_REPORT.md) are historical
preparation records. Their then-missing real inputs have subsequently been
restored; preparation and restored input availability still do not prove
remaining solver identities.

The parent historical review reported A gaps in visited bounds, refinement,
deletion, algebra and reset coverage; B's exact inherited-family optimizer was
false; and C's 128/128 represented four-mode key parity. The original A/B/C
acceptance report files for those conclusions are not available on this
server. They are historical review context, not newly hashed server evidence
or current acceptance. Recover the original reports and source pins before
promoting any of these summaries into a current ledger.

The historical D1 collector at source `052a157b` required `dominance=True`
(`experiments/time_cut_v2/recorded_real/final_collector.py`, lines 228–230 at
052a157b), while `recorded_real/plan.py`, lines 103–105 and 195–198, fixes
C01, H4, eight Sites, 2,047 regions and the representation. C01's D1 receipt
cannot be copied to D0 or another case; D0 has its own accepted receipt at
source `3ad6e38`. The admitted indexed family also
cannot be renamed as literal inherited-family G8.

## Missing original A/B material

All six original files below were absent on the audited server. These are
**declared expected pins** copied from the registry authority, not hashes of
files read during this audit.

| Original file | Rows | Declared SHA-256 |
| --- | ---: | --- |
| `results/milestone_5_coalescing_prototype/frozen_A/physical_cases_h4.json` | 24 | `3d79795956e63cf5ada6ac4d73a49e5a70598169701447eda4b226d664b614f2` |
| `results/milestone_5_coalescing_prototype/frozen_A/physical_supplement.json` | 3 | `1b09f4895df68dd67e0362f88988c9f05c10e9bbf628ded24807bf577bc43a30` |
| `results/milestone_5_coalescing_prototype/frozen_A/physical_merge_supplement.json` | 1 | `121770eb0bef153d313dea7b02d7ab8156f846b3331cf896676a3cf72b5b6bd4` |
| `results/milestone_5_acceptance_b64/acceptance_populations/stage_b/cases.json` | 64 | `61a1d3f86da1c750ef127f7827f4ef68d2b5aa21babc314691ce095ed498f037` |
| `results/milestone_5_coalescing_prototype/frozen_A/FINAL_STAGE_A_RESULTS.json` | 28 | `163949bdf649412ecdd094b07de5ddbd8a436c7db4ca360851fe98d523de5c5c` |
| `results/milestone_5_acceptance_b64/acceptance_populations/evaluation_v2/B64_RESULTS.json` | 64 | `a45979a2a49909d61b25df46d35237120f85c46c8c266cf13b78c7ed627bb025` |

The registry names external archive `HiRoute-frozen-AB92-inputs-a2c4a7f.zip`,
SHA-256 `7d001b1ce2ec83ac953b1891a93562e3b9060195e9dd5f5bcc6a9687b50e7679`.
The parent thread confirmed the recovered ZIP is now saved in Library at
version 0, exactly 23,810 bytes, with the full archive digest above verified
in its cloud workspace. Those are parent-provided facts, not a hash check of
local bytes by this selected Mac/server execution environment. The original
package is already available; the user does not need to upload it again.

This task attempted the supported resolved-reference Library materialization
with an explicit destination on the selected Mac. Preparation returned a
signed transfer, but the current official transfer helper failed with HTTP
403. No local ZIP was installed. Under the authorized stop-on-permission-
failure instruction, no alternative download route was used. SSH transfer,
ZIP member validation, the six server file hashes and the real-population
registry tests therefore **were not executed**. The test suite's two original-
population tests are not recorded as passing or as attempted skips.

This is a Library access/server intake blocker, not a missing-user-upload
request. Until server intake is completed and checked, the 92 original
A/B member IDs and any source/
representation/query-specific receipts remain unresolved. Preserve historical
`independent_expected` separately from actual historical status/key rows;
do not substitute one for the other.

The original A20 thematic suite is a semantic coverage requirement, whereas
A28 is an expanded physical input inventory. Counting 28 files does not show
that every theme is covered.

## Mandatory semantic and structural checklist

The following checklist remains open at the full-population level; individual
passing rows require original identity, input hash, implementation/source,
representation, full expected/actual key, receipt and gate-specific evidence.

- [ ] Map the original 20 themes to physical cases: charging segment/breakpoints;
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
- [ ] Recover B64's deterministic original cases and their source versions;
  cover all 4 topology × 2 SOC × 2 schedule × 2 capability × 2 tightness strata.
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

The parent historical review supplied `sites={"v":[]}` for S07. The original
S07 input row, its frozen group/member identity and actual acceptance receipt
were not found in the server documents, code or small retained JSON. The
machine ledger keeps it as a pending label with no invented original ID,
input digest or successful receipt. It is not removed from any population.

B2/B2.1 section 9 excludes effect-free via-Sites from the action set; section
18 requires exact partitioning of concrete semantic next actions. Conditional
on an authentic S07 input and a genuinely empty concrete action family, the
action-family bound obligation is vacuous. This is an inference from those
rules, not a recovered S07 acceptance statement. The two C01 collectors
demonstrate the required accounting pattern: D1 retains 9,666 and D0 retains
15,795 empty-action query rows with `vacuous_empty_restricted_family`.

Empty actions alone do not prove a whole case. S07 still needs original
identity/input/source, trace and denominator, terminal/direct-drive feasibility,
status/attainment/full key and any applicable physical witness checks.
An empty family must be recorded as empty; it cannot be counted as a nonempty
attained optimum or justified by an unverified historical summary.

## Smallest rational next validation plan

1. **Close input and identity provenance first.** Resolve the supported Library
   materialization HTTP 403, retain the already-verified external archive
   identity, and locate the complete original aggregate freeze. Once locally
   materialized, verify its 23,810-byte size and full SHA-256, validate ZIP
   members, and transfer/extract into a fresh server input-recovery directory
   through the existing SSH route. Read and hash the six
   original files, then run metadata intake under the existing environment.
   The existing loader command is
   `PYTHONPATH=src python -m timecut5.frozen_ab_registry --input-root /path/to/extracted/tree`.
   Then set `HIROUTE_FROZEN_AB_ROOT` to that extracted tree and run
   `PYTHONPATH=src python -m unittest discover -s tests -p test_frozen_ab_registry.py -v`.
   Confirm the two original-population tests execute rather than skip, with
   92 actual physical IDs and 184 HIER identities. This metadata step performs
   no optimization and is not new numerical acceptance. Replace null member lists only with
   verified original IDs; retain S07 and algebra-only A04 with their correct roles.
2. **Build the gate mapping before deciding computation.** Map original themes,
   B64 strata, C32 state/solver identities and source-specific historical
   receipts. Mark each obligation as accepted, historical-only, vacuous with
   proof, unavailable or unverified. Locate S07's original row/trace and
   perform its smallest terminal/empty-family checks once identity is verified.
   Do not rerun every population merely because a summary is incomplete.
3. **Preserve accepted D0 evidence.** C01-HIER-D0 has its own frozen
   population, independent cold receipts and final acceptance. Reuse its
   844,440 successful models, 3,299 blocks and 105 registry entries. Do not
   rerun them to fill unrelated gates.
4. **Choose the next gate from the reconciled gaps.** Prioritize a minimal
   original algebra/reset or literal inherited-family case with independent
   REF and physical witness checks, then expand only identities still lacking
   qualifying receipts. Whole M5-V completion requires all original
   correctness gates.

This 2026-10-09 update records the separately completed D0 run and its
acceptance. No numerical experiment or raw-evidence rewrite was launched by
this documentation update.
