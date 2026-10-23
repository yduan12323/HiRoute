# M5-E2E failure exit — 2026-10-23

**Result:** `delivery_status: PARTIAL`; `clean_e2e_status: BLOCKED`. This report adds the 2026-10-23 repair attempt to the existing PR history; it does not replace earlier findings.

## Final status fields

| Gate | Status | Result |
|---|---|---|
| E0 source/environment | `BLOCKED_SOURCE_OR_ENVIRONMENT` | The installed code-only gate did not pass. |
| E1 no hidden data dependency | `PIPELINE_INCOMPLETE` | No repaired raw-to-query/pool/legs generation ran. |
| E2 microdomain exact comparison | `PARTIAL` | 0/3 cases completed; all 18 real A/B method slots remain `NOT_RUN`. |
| E3 semantic coverage | `COVERAGE_LIMITED` | No attained result; charge and activity-window coverage were not evaluated. |
| E4 clean rebuild | `REPRODUCTION_INCOMPLETE` | A repair environment and wheels were built, but the gate blocked continuation; B was not built. |
| E5 resources and evidence | `ACCOUNTING_OR_EVIDENCE_INCOMPLETE` | Old cleanup and accounting are recorded; no small-domain REF certificate exists. |
| E6 original Shandong bridge | `UNKNOWN` | The original binding was not fully inspected in this cycle; the bridge did not run because that dependency remained unverified. |
| E7 delivery | `DELIVERY_INCOMPLETE` | Review PR updated with this failure report; no real E2E acceptance. |

```text
delivery_status: PARTIAL
clean_e2e_status: BLOCKED
original_shandong_ref_status: UNKNOWN
operation_status: NOT_RUN_DEPENDENCY
```

## Repair and gate outcome

The retained evaluated source is b44f391ba1ccd98ed7f1d173ef165ee194e90ca1. One version-banner fix was prepared in repair source commit `04e87d21352fa93c8a04b4d4d4d92358b6aab5f6`: it accepts only exact first lines `osmium version 1.18.0` and `osmium version 1.18.0 (v1.18.0)`, with a following newline. Existing binary, library, and compiler identity checks remain.

The old b44 prepare invocation **started once** and failed at the version gate before raw input was read or processed; its receipt records cleanup verified and no map artifacts. In the repair epoch, prepare=0 and freeze=0. A new A environment and its core/tools wheels were built; B was not started.

The allowlisted source regression file passed 24 tests in normal mode. The documented installed synthetic gate then reported **40 passed, 11 setup errors in normal mode**. The added fixture looks for `experiments/shandong_preprocessing_v1/phases.py` relative to the test file, but the gate copies tests to a temporary directory without that source file. The `-OO` mode was **NOT_RUN** because normal mode failed. No second test or production-code adjustment was applied. Remote CI is **NOT_RUN**; the publication commit is marked `[skip ci]`.

## Original-domain status

No complete finite search of original N8 query, legs, seed/depth, and reference/root-freeze binding sources was performed in this cycle. The immutable private evidence archive contains an earlier report-draft label `NOT_RUN_MISSING_ORIGINAL_BINDING`; this report corrects that classification to `UNKNOWN`. The original bridge remains `NOT_RUN_DEPENDENCY`; do not infer that the binding is missing, and do not substitute microdomain evidence. Prior original-Shandong conclusions remain unchanged.

## Run and historical disposition

All 18 main-method slots remain `NOT_RUN`; no repaired A or B real graph or solver run occurred. Holdout did not run, and the PR remains unmerged. Historical M5-D remains `M5D_LIMITED_BY_DATA_OR_SCALE`; historical accounting remains `UNKNOWN`.

## Budget accounting

The original caps remain 28,800 CPU seconds and 43,200 external wall seconds. Current conservative remaining balance is **27024.969078 CPU seconds / 28535.638005 external wall seconds**.

- Previously measured work: 375.264447903 CPU seconds / 427.227571001 wall seconds. The original failed prepare additionally measured 0.257561 CPU seconds / 0.202588 wall seconds.
- Historical connector use: 4.7 wall seconds; CPU is unknown. Earlier conservative reserves include 600 CPU / 3,600 wall seconds and a 120 CPU / 150 wall second timeout charge.
- This repair, setup, gate diagnosis, evidence, and publication phase added conservative non-worker reserves of 92 CPU / 820 wall seconds. The cumulative charged balance includes these reserves; they are not measured numerical computation.

The new failure archive was backed up to the connected Drive with owner-only permissions and independently read back at the same byte count and SHA256. No public archive link is included here.
