# HiRoute consolidation implementation — 2026-11-10

## Delivered scope and acceptance boundary

Implemented the approved engineering consolidation around N64 Strong/Scale,
the public core and independent verification. The maintained packages run from
installed wheels outside the checkout. No full real cohort, holdout, province
rebuild or model training was started. Historical processed inputs remain the
accepted reproduction starting point; a new map was not substituted.

**Engineering and small-domain regressions are validated. Historical end-to-end
scientific reproduction, dependent historical deletions and real-workload
performance optimization remain blocked by missing external input closure.**
This is the stop condition in the approved plan, not a claim that all Phase B
scientific acceptance criteria have been satisfied.

## Commit boundaries

| Commit | Change |
| --- | --- |
| `679239d` | Requested pre-audit snapshot; no implementation edits |
| `a1554ce` | Phase A report and approved N64/core/comparator scope |
| `4fde4ad` | Data/query identity, routing, execution and pure statistical extraction; baseline record |
| `37f06b6` | Prepared N64 configuration, fresh cohort budgets, worker/workload separation and verified summaries |
| `636f988` | Independent comparator package and supervised candidate verification |
| `b95154f` | Nine audited empty placeholders removed |
| `95162cd` | Installed-wheel CI tiers, test-only differential oracle and manual historical workflows |
| `d33d63a` | Final child CPU accounting and explicit failed-cohort reporting |

Documentation is committed separately. No remote push, history rewrite or branch deletion.

## Old-to-maintained implementation mapping

| Original component | Maintained implementation / treatment |
| --- | --- |
| `tools/real_scale_inputs.py` | `hiroute.data.queries`; old module forwards for one cycle |
| `d04_cost_diagnostic.domain_digest` | `hiroute.data.identity`; diagnostics and freeze tools import it |
| `profile_small_cases.mac_monitors` | `hiroute.execution.platform`; original monitoring behavior retained |
| `hiroute.exact.road_index` and native C++ | `hiroute.routing.index`; old Python import forwards, C++ ships with routing package |
| `tools/run_real_scale_pilot.py` | `execution.worker`, `workload`, `pilot`; old entry forwards |
| Historical N64 controller | Retained for historical accounting; new `execution.cohort` only creates fresh runs |
| `report_n64_coverage_stage` numerical reduction | `evaluation.cohort`; historical controller-cost/reuse adapter retained |
| New archive integrity boundary | `data.artifacts`; explicit paths, sizes, SHA256 and required roles |
| New configuration boundary | `execution.config`; strict research schema separate from SolverConfig v1 |
| New public commands | `hiroute prepare`, `benchmark`, `summarize`; old validate/solve/run retained |
| Exact table, finite lookup, physical model, DAG, certificate, strict decision/witness, candidate importer | Independent `comparison/src/hiroute_compare/`; old tool modules forward |
| Split transport, raw graph reader and required road-certificate helpers | Same independent package; integrity/bounded-read checks retained |
| Shared file/path verification helpers | `hiroute_compare.io`; historical producer imports shared helpers |
| Independent verification entry | `hiroute-compare verify`; explicit sealed bundle and new output directory |
| Modern differential tests' `timecut5` dependencies | Six unchanged oracle modules in `tests/oracles/timecut5`; excluded from wheel |
| C operator REF-only replay test | Separate REF test module; core tier no longer requires REF |

The independent mathematical implementation remains distinct from the production
optimizer. The exact optimizer, losses/objectives, physical transitions, candidate
ordering and depth semantics were not rewritten. The package has no learned
model training or checkpoint stage to migrate.

## Pruning and retained uncertainty

Removed exactly these audited empty placeholders:

- `src/{acquisition,evaluation,planner,semantic,simulator,uncertainty}/.gitkeep`
- `experiments/{go1_abstraction,go2_acquisition,go3_joint}/.gitkeep`

They contained no implementation, data or retained caller and are recoverable
from Git. Replaced implementations in old tool paths are compatibility forwards,
not discarded functionality. The default test cohort and automatic CI exclude
historical M5D experiments. Manual historical workflows accept a source revision
and check out the snapshot's original layout rather than using mixed new/old code.

The following remain conservative retention items:

- Historical `src/timecut5` and its old callers: no production-wheel dependency;
  the small differential oracle is test-owned. The full historical package is
  retained pending unresolved input/caller closure.
- Old data producers and preprocessing chains, `environment.yml`, and external
  data/source provenance: retained as historical material, not default setup.
- `hiroute.data.shandong_attachment_cache` and potentially external public API
  callers: no destructive removal based merely on an absent in-repo import.
- Road-certificate functionality reused by independent validation: retained and
  tested. No global path-optimality claim is inferred from successful path replay.

No raw data, trained artifact, irreproducible result, failed-run record or
historical ledger was deleted. Larger deletions require restoration of the
relevant evidence and verification of retained callers.

## Contracts and execution changes

The N64 research profile explicitly preserves landmark A*, source-tree reuse,
seed pruning, inbound bound and eager pruning. Pending-activity screening stays
off. The default snapshot `solve` profile is unchanged. Effective per-energy
configuration and candidate preflights are saved, integrity checked, and tied
to per-run code/environment provenance. A new source version may prepare a new
run; no source hash lock, fixed source-file count or frozen source manifest was
introduced.

Fresh runs preserve the 48-cell/96-slot denominator. Missing inputs, resource
failures, incomplete work and historical reuse remain distinguishable. Budgets
are reserved in whole method pairs; uncertain attempts retain reserved costs
and are not retried. Original historical accounting remains in its adapter.

Independent verification seals input files, reconstructs the original DAG,
rejects missing/ill-typed assignments, checks exact assertions and strict support,
physically replays the candidate and original upper witness, verifies raw paths
and rechecks artifacts. The parent enforces resource limits, cleans the process
group and checks body/witness receipts before issuing a new COMPLETE terminal.
The historical status remains UNKNOWN; feasible improvement is never promoted
to an optimum. Waited-child CPU accounting also catches short processes that
finish between monitor samples.

See [RESEARCH_PIPELINE.md](RESEARCH_PIPELINE.md) for formats, commands and limits.

## Validation evidence

The pre-refactor core and REF were built from `git archive a1554ce` and installed
in a new Python 3.11.16 environment. Both normal and `-OO` modes passed 87 tests
and 228 subtests. See [the baseline record](CONSOLIDATION_BASELINE_20261110.md).

Final test tiers build/install ordinary wheels and stage tests outside the
checkout, with no repository `src` on the package import path. Separate minimal
environments establish that core does not require REF/NumPy/SciPy/Z3 and that
comparator does not require core/REF. Native tests require a real C++17 compiler
and Boost headers rather than silently omitting native execution.

The test matrix and final mode counts are recorded in
`consolidation-validation.json`. Covered contracts include:

| Tier | Tests in each mode | Subtests in each mode |
| --- | ---: | ---: |
| Core (without REF/numerical extras) | 118 | 101 |
| REF | 92 | 167 |
| Native and installed worker | 38 | 49 |
| Geo | 41 | 15 |
| Historical differential oracle | 37 | 15 |
| Comparator (without core/REF) | 147 | 181 |
| Total | 473 | 528 |

- Exact path/node/edge tie order, literal aliases, positive charging, open/closed
  faces, C→S, negative start time, primary and secondary unattainment.
- N64 candidate/profile/seed/depth parity, full keys and independent physical
  replay; an actual installed-worker subprocess on a tiny directed graph.
- Wall/CPU/memory/host limits, process cleanup, checkpoint outcomes and UNKNOWN
  retention; no upgrade from a resource exit to mathematical completion.
- Complete N64 denominators, input shortages, stopped/failed work, historical
  reuse and tamper rejection for per-slot/terminal receipts.
- Independent strict-assignment, original-DAG and raw-path validation, including
  missing fields, altered paths, stale identities and receipt mismatches.
- Optional tiny PBF/spatial/charging tests; no real map rebuild.

Ten old/new method/case records compare exactly, including full attained keys,
unattained values and physical replay where applicable. The pre-refactor output
is [consolidation-exact-baseline.json](consolidation-exact-baseline.json);
`ci/exact_behavior_snapshot.py` reproduces the comparison without float tolerance.
Three existing historical-statistics checks also pass. None of these results
substitutes for the missing real artifact reproduction.

During verification, missing staged fixture files and one hidden REF test
dependency were detected and corrected. No scientific algorithm was changed
to make a test pass. The `-OO` pytest assertion warning is expected; installed
contract validation uses explicit exceptions.

## Missing external closure

| Required artifact | Audited identity/location | Current status |
| --- | --- | --- |
| N64 graph TSV | `hiroute-real-scale/data/real-scale-dev/real-scale-road.tsv`; SHA256 `8076e850b096c5cf74f307ae7ad34c2aebd1f1e53c3c4d092234d40078a4c54d` | Not restored in audited local paths |
| Supplemented catalog | `charging-coverage-artifacts-v1/audit-v1/shared-sites.json`; SHA256 `a71e0a645fd21a2f415b4b079033cfe631dfb2292a1a41ce43b439304805a1a9` | Not restored |
| Site bindings | Same archive, `site-bindings.json`; SHA256 `c981bbf5d529f61e0385b4424b5145c44b6afd7dbb35b90fd625792b1e28bf42` | Not restored |
| Historical E18/E48 candidate preflights and receipts | `n64-dev-stage-artifacts-v3` referenced in audit | Not restored |
| Independent complete leg table, raw-edge DB, candidate, original DAG and source receipts | External independent-verification bundle referenced by the improvement report | Not restored |
| Original 2026-10-16 PBF | Historical original input | Missing; no replacement used |
| External trusted archive manifest | Archive holder's sizes and digests, including auxiliary evidence | No complete manifest supplied |

The configuration freezes the existing matrix and historical graph identity.
It does not invent missing metadata or pretend local synthetic fixtures are the
original experiment. Once archives are restored, run the explicit integrity
check, then prepare fresh outputs. Actual full-matrix/holdout work still requires
the intended resource authorization.

## Performance and remaining work

No performance optimization or speedup claim is included. Native and worker
smoke timings are regression timings, not same-data research benchmarks. The
loader's repeated cold compilation, candidate preparation, routing/I/O and
intermediate memory remain profiling candidates; no optimization was justified
from inspection alone.

Next evidence-dependent steps are: restore the external manifest and inputs;
verify historical baselines and full candidate/table/DAG closure; establish any
remaining public callers; then remove only proven-unneeded historical branches.
Profile one bottleneck at a time on an authorized representative workload and
compare exact behavior before reporting measured performance gains. Historical
full-graph REF, holdout and optimum claims remain outside this implementation.
