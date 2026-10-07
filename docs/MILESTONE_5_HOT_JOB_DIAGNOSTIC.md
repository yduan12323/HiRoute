# Four pinned hot jobs, one bounded profile

This is diagnostic preparation, not another whole-capture replay or a solver
run. The only selected indices are 11835–11838, which remained pending in both
previous four-worker profiles. Extraction checks the full capture hash, original
plan hash in the capture, both complete expected-batch lists, pending status,
batch content digests, context and every reconstructed job's exact SHA/byte count.
All JSON pins authenticate the same bounded raw bytes that are decoded, with
a 1 GiB capture cap, 32 MiB per ledger and 1 MiB extracted-manifest cap.
It writes both original v1/v2-kernel and v2/tau-kernel payloads without changing
ordered Piece descriptors. Any mismatch leaves the extraction incomplete.

The source snapshot and all input SHA values are explicit caller pins. The
remote executor must verify concrete paths rather than infer them. Known pins:

- Original plan: f590542e83370bfe8b37748ded4cac94b7d016b84735dcfc735099c0c709672d
- Capture: 66bdff79410db1e27aa7e1226e0698ef07bd7b5d307d00f61fbd07edaaede2ff
- V2 ledger: 576a9e163069e3883e4676350fe4727321a82c69eb3a7c4e56967c1eb59e4597
- Tau-kernel ledger: 43bfe0f4f67d470ef305f52b0f0417eab7fa8aa5a974277a0f64f1917f4a3b41

Extraction uses the unchanged serial replay guard with a shortened 120-second
absolute deadline. Its capture decode retains the existing 16 GiB AS envelope,
16 GiB host reserve and disk floor. It runs no family/equivalence calculation.
Eight bounded job files and jobs.json are retained through the existing evidence
writer. No failed artifact is overwritten or retried automatically.

After separate admission, profiling selects exactly one extracted job and one
kernel. The worker additionally lowers its hard AS cap to 1 GiB before reading
that job. It uses a 60-second post-binding observation within a 90-second total
phase under the unchanged serial guard. The outer guard still reports its
replay-v1 envelope; the tighter worker cap is explicit in this source. The
UID-wide lock and cleanup/return-receipt protocol remain unchanged.

The profile records arrangement CPU time and exact cell count, coverage cells
started/completed, current active supports, pair comparisons started/completed,
operation CPU time and 1 Hz bounded stacks. Pair counters add Python calls and
cell wrappers add one support scan, so this is a diagnostic with overhead, not
an uninstrumented throughput benchmark. If the job completes, its exact result
and certificate hash are retained and can be compared across kernels. A timeout
retains counters/stacks and never reports comparison completion or acceptance.

## Commands after exact source/input admission

Read the current committed source inventory using the existing diagnostic
inventory command. Use fresh attempt and caller-return paths with no-clobber.
Paths below are verified executor parameters, not guessed filenames:

```sh
set -o noclobber
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B \
 -m experiments.time_cut_v2.recorded_real.hot_jobs --mode extract \
 --capture VERIFIED_CAPTURE_PATH --capture-sha VERIFIED_CAPTURE_SHA256 \
 --plan-sha VERIFIED_ORIGINAL_PLAN_SHA256 \
 --v2-ledger VERIFIED_V2_LEDGER_PATH --v2-ledger-sha VERIFIED_V2_LEDGER_SHA256 \
 --v4-ledger VERIFIED_V4_LEDGER_PATH --v4-ledger-sha VERIFIED_V4_LEDGER_SHA256 \
 --source-commit REVIEWED_REMOTE_COMMIT --source-sha REVIEWED_SOURCE_INVENTORY_SHA256 \
 --cpu APPROVED_CPU --attempt-dir NEW_EXTRACTION_ATTEMPT > NEW_EXTRACTION_RETURN.json
```

Only after extraction finishes and jobs.json is independently hash-pinned:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -B \
 -m experiments.time_cut_v2.recorded_real.hot_jobs --mode profile \
 --manifest VERIFIED_EXTRACTED_JOBS_JSON --manifest-sha VERIFIED_MANIFEST_SHA256 \
 --index 11835 --kernel tau-precompute-v1 \
 --source-commit REVIEWED_REMOTE_COMMIT --source-sha REVIEWED_SOURCE_INVENTORY_SHA256 \
 --cpu APPROVED_CPU --attempt-dir NEW_ONE_JOB_PROFILE > NEW_PROFILE_RETURN.json
```

Use `--kernel v2` only for a separately admitted comparison. This implementation
changes no mathematical kernel; all observed comparison results remain generated
by the already reviewed v2 or tau-precompute-v1 functions.
