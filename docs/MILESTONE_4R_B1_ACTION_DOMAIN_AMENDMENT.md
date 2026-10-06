# B1 action-domain amendment

Authorized by the user's B1 resume instruction on 2026-10-02. This supersedes
only conflicting B1 role/action-coverage clauses; accepted M1–4R-A artifacts,
B0 bounds, hierarchy parameters, numerical semantics and empirical thresholds
remain unchanged. The original blocker report and acceptance are archived as
`MILESTONE_4R_B1_BLOCKER_REPORT.md` and
`results/milestone_4r_b1/blocker_acceptance.json`.

## Action-Effect Principle

A Stop-Planning action exists only if the stop performs at least one modeled
decision effect. For B1, the effects are E = {C,S}: C means actually adding
positive charging energy in the accepted plan; S means actually satisfying the
active scheduled-stop requirement. The performed-effect set alpha(a_s,l) is a
subset of E. A concrete one-stop Site action belongs to the semantic domain iff
alpha(a_s,l) is nonempty. There is no N, neutral, or empty-effect Site role.

The zero-stop action a_0 is separate; it is not an empty-effect Site visit.
Feasible legacy visits with zero charging and no scheduled effect are excluded.
This does not assert that such a via-Site route cannot change mobility cost or
energy: road-path choice is distinct from stop-event choice. If exclusion changes
the optimum, stop and escalate mobility-path/stop-action coupling.

D_4RA denotes the accepted broader zero/one-stop diagnostic domain. D_B1 is
{a_0} union {a_s : alpha(a_s,l) is nonempty}, subject to the accepted feasibility
checks. B1 correctness is relative to D_B1; the accepted 4R-A milestone is unchanged.

## Performed effects and numerical contract (declared before H0)

Evaluate each eligible Site with the unchanged accepted `best_one_stop` routine.
Record its best concrete one-stop plan with the unchanged `plan_key`; zero-stop
is recorded separately. Capability alone never assigns a role. C is present iff
the stop's `charged_kwh > 1e-8` kWh, using the accepted energy-feasibility tolerance.
S requires an active schedule, actual scheduled start, Site support, and a start
inside the hard window with the accepted 1e-8 s tolerance. Roles are uniquely
C, S or CS. A meal-supported charger in an energy-only case is never CS.
Classification changes no static Site or Region artifact.

Cost ties use the accepted `round(generalized_cost_s, 7)` comparison. Identity
changes with equal rounded cost are recorded separately; differing rounded costs
fail H0. Incumbent selection still uses the complete accepted `plan_key` (cost,
charged energy, stop count, identity). No feasibility, objective, charging,
routing or tie rule in the accepted evaluator is modified.

## H0 migration gate

Before any hierarchy construction/freeze, audit 30 ODs x four ratios
(1.05/1.10/1.20/1.40) x two SOCs (0.30/0.76) x two scenarios
(energy_only/energy_and_scheduled): 480 cases. Compare J*_4RA and J*_B1 using
the unchanged evaluator and cost ties above. Require zero optimal-value
mismatches; identity-only changes may pass. Log all counts, excluded actions,
both optima and differences. A strict mismatch immediately prevents hierarchy
construction and all comparative interpretation; emit:

`H0 failed — mobility-path/stop-action coupling requires theoretical revision`

Do not introduce neutral roles, arbitrary road-node via actions, or weaken the
action-effect principle. If a failure interrupts the audit, report actual cases
evaluated rather than falsely claiming all 480 completed.

## Coverage after H0 passes

Only after H0 passes, the operative B1 action set is {a_0} disjoint-union
A_C disjoint-union A_S disjoint-union A_CS. Each included feasible Site action
has exactly one performed-effect role. Effect-free visits are absent and
zero-stop remains outside the tree. H4 preserves this semantic action set and
the exact parent/child Site partition. H2 compares hierarchy against J*_B1.
H1, H3, H5 are otherwise unchanged. Gate order is H0 through H5.

## Unchanged experiment contract

Topology-first binary hierarchy, primary capacity 64, optional capacities 32/128
with the same mechanism, deterministic identity ties; freeze before comparative
results. Primary epsilon 0; secondary 30/60/120 s only after exact gates pass.
Oracle summaries expose logical potential, never actual compute/routing savings.
The reduction denominator counts only semantic Site actions; report legacy
eligible and feasible counts separately. Strong GO: median reduction >=70% and
at least 75% of cases >=50%. NO-GO: median <50% or fewer than 75% of cases >=25%.
Otherwise gray zone. B1-D remains conditional on H0–H5, completed B1-O and a
proven non-enumerative certificate; unchanged deployable thresholds apply.
No B2, Go-2 or holdout experiment is authorized.
