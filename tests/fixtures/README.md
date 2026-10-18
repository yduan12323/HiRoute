# Source input fixtures, not cached experiment results

Only small synthetic inputs and independently stated expected arithmetic belong
here. Tests must compute solver answers, traces and certificates at runtime.
Generated output is not made publishable by relocating it into this directory.

## Provenance and content audit

- `milestone_5_reference/frozen_cases_v2.json`: 18 tiny synthetic problem
  definitions with `independent_expected` values from hand calculations. Inputs
  cover attained, unattained and infeasible cases. The independent exhaustive
  reference runs afresh in `test_post_service_dominance.py`; no cached oracle
  results/certificates are loaded.
- `milestone_5_reference/audit_regression_cases.json`: three small adversarial
  input definitions, not recorded solver runs.
- `milestone_4r_b2_b21/hand_cases.json`: one hand-constructed clock/energy tie
  example. Its expected values include the written arithmetic derivation.
- `milestone_4r_b2_b21/case_construction_manifest.json`: input hash and statement
  of construction/analytical expectations; no execution results.
- `milestone_5_real_leg_contract/mock_solver_cases.json`: five explicitly
  synthetic leg tables, query/tree inputs and hand-arithmetic expectations.
  These are mock adapter contracts, not extracted road experiments. Input
  table/tree hashes verify their identities, not prior solver execution.
- `milestone_5_real_leg_contract/mock_solver_freeze.json`: hash, case count and
  hand-arithmetic provenance for those mock inputs.
- `invocation_trace_pilot_v1.json` and `invocation_trace_A06_regression.json`:
  small synthetic problem inputs used to produce invocation traces during tests;
  despite their names, they contain no stored execution trace.

The six milestone input/identity files were copied from the reviewed `00e5aa4`
snapshot. Their content, not their former directory name, determines inclusion.
The two invocation input files predate that relocation.

## Removed generated caches

`analytic_cases_ref_v2.json` was a generated oracle result/certificate cache,
not an input fixture. `g8_node_batch_fixture.json` contained a generated
trace/evidence bundle. Both have been removed from the published tree and
preserved separately with their external archive manifest. Tests now run the independent reference or generate and
verify the coalesced trace in memory from the small inputs above. They do not
read archived output as a fallback.

The publication preflight rejects top-level `results` or `evidence` payloads in
JSON fixture files. This is a guardrail, not a substitute for reviewing fixture
provenance. Missing required inputs are hard errors. See `ci/README.md` for the
isolated code gates and optional historical inspection.
