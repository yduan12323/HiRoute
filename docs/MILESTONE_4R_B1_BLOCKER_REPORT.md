# Milestone 4R-B1 — pre-implementation contract blocker

Audit date: 2026-10-02 (Asia/Shanghai).

**B1 correctness failed — no empirical Go/No-Go interpretation.**
This statement records an unsatisfied action-coverage prerequisite, not a failed
480-case hierarchical experiment. That experiment has **not been run**.

## A. Scope and declared domain

The supplied B1 prompt was followed through baseline verification and contract
inspection. The accepted flat domain includes all envelope-eligible attached
vehicle Sites, including feasible stops that neither charge nor perform a
scheduled activity. B1 prompt §6 and protocol §5 permit only C/S/CS, require exact
role predicates, and require equality with the flat feasible action set.
These requirements cannot all hold on the accepted data.

## B. Baseline preservation

- Accepted commit: `20b658257fb67655e09229411783935e17084fa4` (Milestone 4R-A).
- Initial branch: `codex/milestone-4r-a`; only the three supplied B0/B1 documents
  were untracked before creating audit outputs. No accepted tracked changes.
- Audit branch: `codex/milestone-4r-b1`. No user work was committed.
- Original suite: **116 passed in 132.20 seconds**, no failures, errors or skips.
- Original 840-file preservation manifest and 56 accepted M4B source hashes
  match. All 13 recorded 4R-A source hashes, report/config hashes and the
  site-build/diagnostic input/output hashes match at initial audit.
- Post-audit verification is saved separately; old verification scripts that
  overwrite accepted result files were not invoked.

Exact test command (using the accepted environment):

```sh
HIROUTE_OSMIUM=../osmium-env/bin/osmium /home/dy/miniconda3/envs/hiroute/bin/python -m pytest -q --require-real-data --require-envelope-results --require-regional-results --require-opportunity-results --require-microplan-results --junitxml=results/milestone_4r_b1/preexisting_tests.xml
```

Audit evidence is in `results/milestone_4r_b1/`: `baseline_audit.json`,
`preexisting_tests.log`, `preexisting_tests.xml`, `preservation_checkpoint.json`,
and `preservation_after.json`. The checkpoint records existing files after the
test run; accepted historical manifests were independently verified before and
afterward. It is not misrepresented as a pre-test capture of every file.

Inspected: static Site schema, `best_one_stop`, `evaluate_site`, `plan_key`,
accepted envelope eligibility and mobility-budget recheck, native forward/reverse
time/actual-length labels, memory guards, report conventions, and B0/B1 contracts.
No packages were installed and no geographic data downloaded.

## C. Frozen hierarchy

Not constructed or frozen. Dependency availability was inspected: igraph,
networkit, networkx and scipy exist; pymetis and metis do not. No partition
mechanism was selected or benchmarked because the coverage prerequisite fails.

## D. Correctness H1–H5

The following real-data counterexample establishes the coverage conflict before
implementation. H1–H5 over 480 cases remain **not evaluated**; no zero-violation
tables are used to imply a pass.

| Quantity | Observed value |
| --- | --- |
| Development OD | 2 |
| Envelope ratio | 1.05 |
| Initial SOC | 0.76 |
| Scenario | energy_only |
| Eligible feasible one-stop actions satisfying none of C/S/CS | **81** |
| Example Site | `4r:node/8849224490` |
| Transport capability | rest |
| Meal support count | 0 |
| Inbound / outbound selected fastest time | 2741.556082 / 1930.029963 s |
| Inbound / outbound actual length | 71519.001 / 35401.022 m |
| Total driving time / envelope budget | 4671.586046 / 4905.165348 s |
| Arrival energy | 34.156960 kWh |
| Required departure energy | 11.664164 kWh |
| Charged energy | 0 kWh |
| Destination energy / reserve floor | 28.492796 / 6 kWh |
| One-stop generalized cost | 5571.586046 s |

The unchanged accepted `best_one_stop` constructs this feasible plan. Its
`assemble_plan` call was wrapped only to record returned objects before the final
argmin; the wrapper returns the original objects unchanged. No feasibility,
objective, tie rule, input configuration, or source file was modified.

The example has no charging capability, so C is false; meal_count is zero, so S
is false; consequently CS is false. Its vehicle stop is distinct from zero-stop.
Thus the flat feasible action belongs to none of the permitted role branches.
The static inventory contains 12,620 attached Sites with neither capability;
this count alone is not a claim that all are feasible for any particular query.

OD 0 was inspected first and yielded no feasible neutral-stop witness because
energy was insufficient. OD 2 was selected as the first accepted 1.05/76%
energy-only case whose flat optimum has zero stops. This is a contract
counterexample search, not an OD subset for performance evaluation.

Zero-stop is cheaper in this example (4671.586046 s). This does not repair exact
action-set equality: preserving a minimum and preserving every feasible action
are different contracts. No general zero-stop dominance theorem is assumed;
selected-fastest-route actual length need not satisfy triangle inequality.

Reproduce with:

```sh
/home/dy/miniconda3/envs/hiroute/bin/python results/milestone_4r_b1/reproduce_role_audit.py
```

Full unrounded evidence: `results/milestone_4r_b1/role_coverage_counterexample.json`.

## E. B1-O oracle potential

Not run. No pruning rates, routing savings or computational savings are claimed.

## F. GO/NO-GO classification

Not applicable: coverage prerequisite failed before comparative results.
The frozen performance thresholds were not applied or changed.

## G. Gap diagnosis

G_model, G_agg and G_cert are unavailable because no hierarchy experiment ran.
The diagnosed issue is incomplete role vocabulary relative to the declared flat
action set, not Region aggregation or certificate looseness.

## H. B1-D deployable stage

Not started: prerequisite B1-O/H1–H5 validation is incomplete.

## I. Runtime/memory

The OD 2 witness audit took 17.09 s and peaked at 4261.75 MiB RSS, including graph
load, native router construction, shared routing and witness evaluation. These
are diagnostic totals, not hierarchy timings or speedups. The accepted memory
guard passed. The earlier OD 0 audit was inconclusive; its runtime was not
instrumented. No total end-to-end B1 timing is asserted.

## J. Limitations and smallest defensible next change

Prompt §6 / protocol §5 must be clarified before implementation continues.
The smallest change that retains **exact action-set preservation** is to permit
an explicit neutral stop role (for example N) for actions assigned neither
charging nor scheduled activity, with no charging allowed, no scheduled activity,
and B0's no-charge feasibility margin. Define its predicate and action coverage
in the preregistered contract before running B1. The C/S/CS predicates, accepted
flat evaluator, Site inventory, case grid and hierarchy parameters can remain
unchanged. This is a proposed amendment, **not implemented or approved**.

Alternatively, any optimum-preserving domain reduction needs an explicit proof
and a revised action-coverage/accounting contract. It cannot be silently
substituted for the current equality requirement.

The 30 ODs remain development data. The intended domain is zero/one-stop within a
fixed envelope, with no real multi-stop or final holdout validation, no full active
information acquisition, and no user-learning/business-ranking claims.

## K. Final gate statement

**B1 correctness failed — no empirical Go/No-Go interpretation.**

Stopped under the supplied prompt's §26 escalation rule and prohibition on
silently weakening definitions. B1 implementation, 480-case comparison and B2
have not started. The accepted baseline is preserved.
