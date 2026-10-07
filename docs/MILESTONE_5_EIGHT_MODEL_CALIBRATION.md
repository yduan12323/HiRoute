# Fixed eight-model numerical calibration

This version calibrates numerical certification on eight bindings from the
completed 256-model structural preview. It does not optimize a whole Region
query or certify the complete C01 suffix population. The preserved capture,
complete structural replay and preview are prerequisites, not rerun solvers.

Before any LP outcome is available, the runner authenticates the preview's
successful return, cold manifest, source and all payload commitments. It derives
the first and last selection positions at each prefix depth. The exact positions
are `[0, 63, 64, 159, 160, 223, 224, 255]`, covering all seven preview families.
The original 256-model depth counts must remain `[64, 96, 64, 32]`. Complete
family IDs, action words, arrival bands, model bytes and constants stay bound
to each separate occurrence. There is no cross-model certificate cache.

## Exact model and result obligations

The coordinator obtains a genuine fresh `CheckedBundle` through the existing
parallel family checker. It cannot manufacture one from the thin query index.
All selected models must match both the candidate and independently authored
model builders and the authenticated preview bytes before numerical work starts.
The family-check children must be reaped before the candidate children start.

Each one-shot candidate uses the unchanged five-stage `solve_model` protocol:

1. Strict feasibility, minimizing minus the common strict margin.
2. Primary closure optimum.
3. Strict feasibility on the primary optimal face.
4. Secondary optimum on that attained primary face.
5. Strict feasibility on the secondary optimal face.

Earlier certified infeasibility or primary nonattainment can stop this sequence.
An exactly zero strict margin is not strict feasibility. Face equations use the
raw certified linear objective before adding the model's J/Q constants. An
optimal closure point alone never proves attainment.

Candidate frames retain the complete ordered task and exact certificate for
each completed stage. The coordinator checks the full job identity and stage
coverage, then calls the unchanged independent `convex_checker.check_regime`.
For attained, primary-unattained and secondary-unattained results, it constructs
an exact feasible point from audited stage primals, lifts it through the original
family, and calls `convex_evidence.check_result_witness`. Nonattained approaches
use epsilon `1/1000000`; the construction uses a strict convex mixture of the
closed optimum and an audited strictly feasible point on the required face.
Original arrival bands, physical legs, schedule semantics, H and pi are checked.

Candidate timing is reported separately from independent exact checking and
physical reconstruction/rechecking. Every selected binding has a disposition.
Timeout, exhausted passes, bad certificates, incomplete frames, identity errors
or missing physical verification are unresolved. They cannot be counted as
infeasibility or a successful calibration. Even eight successful model checks
leave `query_optimum_certified`, `full_population_complete` and
`literal_G8_closed` false.

## Fixed resources and retained failure evidence

The entry-time absolute deadline is 480 seconds under the existing BATCH_REPLAY
guard: 16 GiB coordinator address space, 20 GiB sampled group RSS, 16 GiB host
available-memory reserve, and 20 GiB disk floor. The supervisor and coordinator
have separate CPUs; four further CPUs serve first the family pool and then the
LP candidate pool. Candidate children inherit the coordinator's process group,
so the existing outer guard owns crash cleanup.

Each candidate gets 1 GiB hard address space, a 768 MiB solver RSS check,
at most 12 native LP passes, and a real 30-second launch-to-exit deadline. BLAS
and HiGHS are configured for one thread. A separate pipe-collection thread
enforces these deadlines while the main thread performs independent checking.
Checking, witness lifting and publication have a separate 30-second per-model
main-thread timer, also bounded by the global deadline. At most 40 logical stage
slots and 96 candidate passes are possible across the eight bindings.

The Linux-only candidate uses the current exec address space's `/proc/self/status`
`VmHWM`, taking the maximum with `VmRSS` from the same bounded read. Required
fields, PID, units and integer values are checked; missing or malformed procfs
data fails closed. This peak survives releases within that address space.
`getrusage(RUSAGE_SELF).ru_maxrss` is retained only as a separately named
diagnostic because its counters survive `execve` and can include the large
coordinator image before exec. It must not reject a small fresh candidate.
The general `SolveBudget` default remains unchanged; only this worker injects
the explicit `linux-exec-vmhwm-v1` byte reader. Job limits and candidate frames
bind that measurement source. No parent-peak subtraction or raised cap is used.

These are kernel RSS observations, not an exact Python heap census. The unchanged
hard address-space limit and sampled whole-group guard remain additional limits.
See the Linux manual for [getrusage](https://man7.org/linux/man-pages/man2/getrusage.2.html)
and [proc status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html).
Synthetic regression allocates under 100 MiB in each process: a large live
parent execs a small child, then the child creates and frees its own over-cap
allocation. It demonstrates both the inherited-counter failure and rejection
of the child's own retained high-water mark. It invokes no optimizer. The
original failed C01 calibration and its zero-LP evidence remain preserved;
this source correction does not itself imply a successful retry.

Candidate stdout is bounded at 2 MiB and stderr at 64 KiB; consumed prefixes and
completed stage frames survive malformed output, timeout or worker failure.
Each stored candidate document may use at most 6 MiB to retain both its raw
base64 transcript and decoded stage objects without truncating either copy.
The calibration's aggregate domain payload charge is 64 MiB, with monotone
prewrite accounting, and each independent model-check document is at most
4 MiB. The existing group writer separately accounts its journals and supervisor
records. All artifacts use fresh immutable paths. Interrupted publication cannot
be accepted or retried by overwriting the attempt.

The returned manifest and separately retained successful launcher return are
both required for later completed acceptance. A partially successful calibration
retains available evidence but exits unresolved. Candidate output is always
untrusted until its own independent model/witness check passes.

## Reproduction and admission

Cloud tests use tiny fake candidates and hand-authored exact certificates. They
do not call the numerical optimizer. The server must run these focused tests
under its verified Python 3.11 interpreter before a separately admitted real run:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python -B -m unittest -q \
  test_suffix_calibration test_lp_calibration_jobs test_lp_calibration_run test_real_model_preview
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python -B -OO -m unittest -q \
  test_suffix_calibration test_lp_calibration_jobs test_lp_calibration_run test_real_model_preview
```

The RSS-source correction additionally requires `test_candidate_memory` in
both modes before a separately admitted fresh attempt.

The thin command is `python -B -m
experiments.time_cut_v2.recorded_real.calibration_run`. It accepts all explicit
source/historical-plan/completed-replay/logical-preview arguments of
`model_preview`, plus `--preview-attempt`, `--preview-return`,
`--preview-return-sha`, `--preview-summary-sha` and `--preview-source-sha`.
The execution coordinator supplies the verified retained-return paths, current
published commit and independently recomputed source inventory, allocated CPUs,
and a fresh attempt directory. No default path or unspecified prior artifact
grants authority. No real execution is implied by this code checkpoint.
