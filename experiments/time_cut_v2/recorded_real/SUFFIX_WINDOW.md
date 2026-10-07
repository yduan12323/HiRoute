# Generic original-model suffix windows

`python -B -m experiments.time_cut_v2.recorded_real.suffix_window` performs one
window, using `BATCH_REPLAY`, the existing persistent candidate transport, and
the existing exact block proof archive. It does not launch another window or
retry incomplete work. This change is implementation and synthetic/hand-test
coverage only; it does not record a real numerical run.

The accepted pilot/resume covers original blocks `0,1352,2535,2687` (1,024
models). The first window therefore selects blocks `1..32`, or 8,192 original
models. Each later invocation selects the first at most 32 outstanding blocks
from its authenticated registry. The full catalogue remains 695,712 models
in 2,718 blocks; block 2,717 retains its original 160-model tail. An empty
terminal selection launches nothing and does not certify query optimality,
population completeness, or literal G8 closure.

The standard historical/replay/logical/capture and source arguments are the
same as `block_pilot`. Add required `--source-policy`, `--source-policy-sha`,
`--registry-output`, and `--registration-return-output`. The policy is
canonical JSON followed by one newline, with schema
`hiroute-reviewed-window-sources-v1` and a `reviewed_sources` mapping from full
commit IDs to source-inventory SHA256s. It must explicitly include the current
reviewed source and all historical receipt sources, including the fixed seed.
This separately supplied policy pin is trust input, never self-approval by a
registry or an observed current commit.

Execution authority additionally requires an independently observed invocation
of this reviewed controller in its trusted checkout and interpreter environment.
The controller and worker check the current checkout directory, loaded module
and child module resolution, the interpreter against the running process, and
loaded source pins before execution and through final publication. Both the
run binding and summary record these observed invocation origins. These checks
and recorded labels are not cryptographic code attestation: an arbitrary
`run_phase` success from an untrusted executable cannot establish reviewed
execution merely by spelling `-m suffix_window` in its arguments. Cold
admission deliberately stays in the same trusted checkout/environment unless
a separate migration is reviewed. The fixed historical seed has its own
separately accepted invocation and byte pins.

For the initial window supply `--seed-attempt`, `--seed-return`, `--old-archive`,
`--old-summary`, and `--old-selection`. Optional `--seed-result-sha` and
`--seed-decision-sha` may independently pin the corresponding accepted seed
files. The successful seed return and manifest have fixed reviewed pins.
For later windows supply only `--registry`, `--registry-sha`,
`--registry-return`, and `--registry-return-sha`. These latter SHA256s must be
the independently retained outputs of the preceding successful registration.
The CLI rejects mixed or partial admission modes. All unused fields remain
JSON null in the typed runtime input context; worker arguments omit them.

Choose a fresh `--attempt-dir`, one supervisor `--cpu`, and five ordered
`--worker-cpus` (coordinator then four candidates). Registration output paths
must be fresh, distinct, and outside the attempt. The actual `run_phase`
return is retained separately as `<registry-output>.run-return.json` before
receipt registration. Only after completed evidence admission does the
controller append a typed receipt, write a new registry, and retain the actual
`write_registry` return at `--registration-return-output`. Registration
failure preserves completed raw proof files. Its failure response includes the
exact actual `runtime_result`, including the acceptance receipt, so the caller
can retain it even if an immediate deadline/resource failure or a sidecar write
failure prevents confirmed file persistence. Any successfully written runtime
return sidecar is also preserved. A registry file without its separately retained successful registration
return is not authority for the next window. Existing output paths are never
overwritten. Failed-window recovery uses the existing cold archive replay
profile and is outside this normal-success runner.

The accepted work, including input admission and post-run registration,
is bounded by the original entry time plus 900 seconds. Safe process cleanup
may continue after expiry; no late registration is accepted. Existing live host
and disk checks remain active during registration. Each window keeps four
1 GiB AS / 768 MiB VmHWM candidate processes, at most 30 seconds and 12
passes per model, a 20 GiB group cap and 16 GiB host reserve. The cumulative
job-input cap is 128 MiB; both charged evidence and uncompressed proof archive
are capped at 512 MiB. No numerical cache is enabled. Original H4, eight-site,
2,047-region physical inputs and original query bindings remain mandatory.

Workers freshly admit the actual family and population, compare the typed
registry against them, and freeze all selected descriptors before creating
any model matrices. Completed evidence has exactly eight files:
`run-binding.json`, `batch-ledger.json`, `family-summary.json`, `block-plan.json`,
`base-registry.json`, `window-selection.json`, `model-proofs.jsonl.gz`, and
`window-summary.json`. Block progress on stdout is explicitly provisional;
full proofs remain in the existing v1 archive. Later scheduling consumes
authenticated compact metadata without rereading all historical archives;
the final collector must reconcile unique evidence dependencies separately.

Run synthetic and hand-certificate checks without LPs or a server:

```sh
PYTHONPATH=src:. python -B -m unittest tests.test_suffix_window_runner tests.test_suffix_window_receipts
```
