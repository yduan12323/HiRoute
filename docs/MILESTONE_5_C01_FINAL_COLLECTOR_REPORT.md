# M5-V C01 final collector acceptance report

Audit date: 2026-10-08 UTC. Host: `dyserver`; working directory:
`/home/dy/HiRoute/project`. Server access and all execution used the selected
connected Mac and existing SSH authentication. The branch at computation time
was `codex/milestone-4r-b1`.

## Accepted identity and conclusion boundary

The retained final collector accepts **C01-HIER-D1**, with dominance enabled,
`exact-adjacent-cut-coalescing-v1`, H=4, pool `OD00_energy_only`,
initial SOC=3/10, eight Sites and the original 2,047-region hierarchy.
This is the original indexed C01 query population, its numerical certificate
coverage, and its physical witness bindings. It is not a result for C01-D0,
FLAT-D1, other C32 cases, or all M5-V.

The actual collector return, acceptance receipt and independently checked
query rows agree: `single_C01_case_accepted=true`,
`single_C01_case_bound_valid=true`, and bound status `satisfied`.
All four global fields remain false: `full_population_complete`,
`full_C32_complete`, `whole_M5_complete`, `literal_G8_closed`.
The historical query index uses the admitted indexed restriction family;
this receipt does not close literal exact inherited-family G8. It makes no
point-level counterexample claim.

The [coverage audit](MILESTONE_5_V_COVERAGE_AUDIT.md) separates this measured
identity from the protocol gates and historical parity evidence.
The [receipt capsule](MILESTONE_5_C01_FINAL_COLLECTOR_RECEIPT.json) copies small
metadata, the exact argv, all input pins and final receipt pins. It is an index
to retained server evidence, not the raw certificate archive.

## Frozen input and source lineage

The C32 preparation input `results/milestone_5_real_export/query_states_resolved.json`
has SHA-256 `d4bd50215c8035552ca47a9bf4e175d580eb265a2e9acbeff5d574c60b08b57c`.
Its C01 direct-leg table SHA-256 is
`e3f0efcf8456d4e81ac9fdfb854304b1270b0c7ea21782a253cd03131d7f2f6c`;
restriction SHA-256 is
`4a12c150d4c2853504e3726e82ad39e6c6a30fde21a283f385ebcafbf8ecf3f2`.
The original tree digest is
`4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805`.
Selection manifest SHA-256:
`0e39ad906c01e05b4a4b764b3270360e309c24d1ae67d7a2e3533b6dca8af06a`;
export manifest:
`f846eb37219a34dea74aa9a79e7673b8cdae03ae281de189cb9b602a98ac380d`.
The adapter exports retain original binary64 values as exact ratios and the
original tree restrictions; see the
[adapter design](MILESTONE_5_REAL_SOLVER_ADAPTER_DESIGN.md).
Preparation of 32 states alone is not solver acceptance.

Collector source commit: `052a157b745cdaee463579bf8478d1f78d44838b`.
Git tree: `f12276c197e9fe580c6a392a08344e0604721470`.
The admitted 116-file source inventory SHA-256 is
`3090ccc44bcb8c1d8abb69cca627508b730018c273cb848b1fceb42f888e10fb`.
Python: `/home/dy/miniconda3/envs/hiroute/bin/python3.11`, version 3.11.16.

The chain intentionally contains several authenticated source versions:

| Stage | Source version / inventory |
| --- | --- |
| Original capture plan | commit `8f8bdf82b44bae3217d39fd5b27153f86b567c27`; inventory `844d0afa3276f3cb085ac174a562a59e409a4265e317bd8f4e55939e93b2d8ef` |
| Cached parallel structural replay | inventory `0739fbfb89b3622cf428ce677720bb8b420a3f09953661724cba4642bbad9d1a`; separately pinned replay plan/return |
| Logical suffix census | commit `ba21b8dbc39a320ed0b24ccb0d40a058e5d0a307`; inventory `808588f501a979b020e86f2d16f3c81f499937abecb037291e579c39720bbb43` |
| Initial block resume | `bf61640ceaf6dcafe28f7ab12d95e94c8f19bb93`; inventory `846ded63e7e3f6a3da5cc81d5f717deea2e4746a75e282d333291dbb05dcb579`; one registry entry |
| Earlier ordinary suffix windows | `ec10bdce88f54df30fa1c61cafe1b9e521b077df`; inventory `10023fc8b55f48e8d9fd0bd98d28ceb356ccba6e248cdca830217e36eb2132b0`; 50 entries |
| Windows 052–065 and successful 051 recovery | `67ac9844366c74186069fb86aa6672b568fef050`; inventory `dc902eb8d11fe651eed5f61eff6d2f1d1fde7ad99f2b72a2d3d5cd56362518cf`; 15 entries |
| Exact-only 066 recovery, windows 067–085, final collector | `052a157b745cdaee463579bf8478d1f78d44838b`; inventory `3090ccc44bcb8c1d8abb69cca627508b730018c273cb848b1fceb42f888e10fb`; 20 registry entries |

The reviewed policy `C01.suffix_window.sources.recovery066.001.json` authenticates
the four numerical registry source mappings. The capture/replay/census inputs
are independently pinned. The 86 registry entries are not 86 different cases,
and they must not all be relabeled as source 052a157b.

## Actual final evidence

The final registry covers 2,718 blocks, 695,712 unique logical models and
7,652,832 original model occurrences. Every occurrence is reconciled to the
original query population.

| Result | Count |
| --- | ---: |
| Original nonempty query events / attained optima | 12,172 |
| Empty-action query events / empty restricted families | 9,666 |
| Total original query events | 21,838 |
| Unique physical witness requests, all used | 1,790 |
| Physical witness bindings to nonempty queries | 12,172 |
| Satisfied bound queries | 12,172 |
| Vacuous empty-restricted-family bound queries | 9,666 |
| Missing bounds / bound counterexamples | 0 / 0 |
| Zero-length queries / all-excluded nonempty queries | 0 / 0 |

The collector reports complete numerical, physical and original-occurrence
evidence. A separate read-only verifier streamed all 21,838 query rows, checked
the actual return/acceptance/summary and manifest pins, and reconciled physical
bindings and the bound counters. The final evidence manifest has 11 entries.
Empty-action rows are retained with an explicit vacuous status; they are not
silently dropped from the denominator.

All paths in the following pin table resolve through the companion receipt
capsule under `results/milestone_5_recorded_remote/`. Sizes are bytes.

| Evidence | Size | SHA-256 |
| --- | ---: | --- |
| C01.suffix_registry.085.json | 4930034 | `4a8dcf510a565f403372df9a07b6f719d9a4f7d5ee2773ef348031495e51ae39` |
| C01.suffix_registry.085.json.run-return.json | 2234 | `8f4cc5ba16fc2f0209e6e8842b3debb03a8a02b767cef445edf444138062e2ad` |
| C01.suffix_registry.085.return.json | 18654 | `1067167a5d64164b5bb9ac828b139e183e240cf79674328fe4957e4f8d7ed4b9` |
| C01.suffix_window.sources.recovery066.001.json | 509 | `e4663080b5c1384bd51aca55a21f6a5474fad962e90c08422a307328376b10b3` |
| acceptance | 1002 | `a9d810572b1020d7e86a40f27991e51f5393ad8ef0149bee8f213aabab032542` |
| controller | 1269 | `3c0c9372888be80d40ee9d2c331862726b1383d2b3f4540c82793773fd63545e` |
| manifest | 1625 | `ac6037d4bcc2b5513c665ec93fdc49be59a6798253f27b784d2f1f28efc61d97` |
| runtime_return | 2234 | `01930ebebbeb04f2e7458b1c18eae4304b12c4a742ca3ca25cd663ba388879ca` |
| summary | 4606 | `7f73e664e97a2e75b03c9490728f0f8e93d83147457643f2e50c4abfd726d910` |
| command | 2808 | `7e69ce031179dd21d42006aa70f61a79b59ae8f8f7037be43b685575a9e01950` |
| postflight | 9550 | `26311b818d0a931710f888b198220f31c9a5215779057527369585503b326b94` |
| precheck | 6172 | `bd123fc2dfa89e7ea2a6b5850ec612ca2cf3295b46a9c7af1b2507bc38729767` |
| query_results | 64381586 | `b1f8cc1d45faa990ddc484579d3d6f04bd73a34e94f56c0bcbaecb4493cac63c` |
| physical_witnesses | 43650568 | `e2b1b03b8db2a76a40403f6918443be6e8e9a30b980a43b94f7d56aa9105639b` |

The query archive is 64,381,586 bytes; the physical archive is 43,650,568 bytes.
Raw captures/certificates and historical attempts remain on the server and
are not added to Git. The original capture is 835,419,819 bytes with SHA-256
`66bdff79410db1e27aa7e1226e0698ef07bd7b5d307d00f61fbd07edaaede2ff`.
The original query index is 42,923,142 bytes with SHA-256
`9275e7b39e771b06cf1b4f79275b6e9ba91e6e61e8c386f8ca672f3f618c99fc`.

## Failure and recovery history

Original window 051 stopped on three unresolved exact-gap models:
411229, 411238 and 412024. Recovery 051.001 stopped during preparation because
a relative source-policy path did not match admission; no new LP worker ran.
Recovery 051.002 at 67ac9844 cold-checked 8,189 retained certificates and
completed the three missing certificates. The failed attempts remain retained.

Windows 052–065 completed at 67ac9844. Original window 066 stopped when an
owner Git Sync changed the source to 052a157b during execution. Its 8,192
certificates and 32 reports/checkpoints were retained, but that attempt was
not registered as successful. No agent rolled back the source.
Recovery 066.001 at 052a157b took 245.994 seconds, cold-checked all 8,192 retained
certificates, had zero fresh LP candidates, refreshed physical/registration
evidence and completed. Windows 067–085 then all completed at 052a157b.

The original request to run 052–085 at 67ac9844 therefore does **not** describe
one uninterrupted all-67ac9844 run. The admitted recovery and later source
policy record the actual source transitions. No failure was counted as a pass.

Some attempt-local `result.json` files are provisional; the externally
retained actual runtime/registration returns determine completion. The final
085 registration and actual runtime return are both pinned above. The single
final collector run began at 2026-10-08T12:11:32.478693Z and ended at
12:27:18.792609Z with exit code 0 and empty controller stderr.

## Tests, resources and continuity

At the admitted collector source, ten relevant modules ran **181 tests** under
ordinary Python and **181 tests** under `-OO`, with zero skips and exit 0.
Elapsed test times were 31.916 and 32.300 seconds. Modules:
`test_suffix_query_witnesses`, `test_suffix_final_collector`,
`test_final_collector_runtime`, `test_suffix_query_collection`,
`test_suffix_segment_fold`, `test_suffix_empty_occurrences`,
`test_suffix_window_recovery_receipts`, `test_suffix_window_recovery_core`,
`test_suffix_recovery_plan`, and `test_suffix_archive_reader`, all under
`tests.`. These focused tests do not replace the original A/B/C gate suite.

| Resource / measured result | Value |
| --- | --- |
| Absolute collector deadline | 3,600 seconds |
| Total evidence charge, including supervisor reserve | 1 GiB, including 16 MiB reserve |
| Coordinator address-space cap | 16 GiB |
| Group RSS cap | 20 GiB |
| Supervisor address-space cap | 512 MiB |
| Family workers | Four; 1 GiB address-space cap each |
| CPU allocation | Supervisor 0; coordinator 1; family workers 2–5 |
| Host free-memory floor / disk floor | 16 GiB / 20 GiB |
| Entry admission margin | At least 36.5 GiB available RAM and 21 GiB available disk |
| Actual collector wall time | 944.155991564 seconds |
| Sampled peak group RSS | 5,401,182,208 bytes |
| Charged worker evidence | 247,890,724 bytes |
| New numerical solver calls during collection | 0 |
| Worker exit / descendants reaped | 0 / true |

BLAS-related thread limits were all 1. Before launch, 1,374 distinct declared
registry/input pin files totaling 2,797,078,243 bytes were hashed. Continuity
at 12:29:54.835201Z checked unchanged identities for 1,812 retained files,
265 directories and 88 attempt trees totaling 3,048,255,023 bytes, unchanged
source inventory/HEAD/tree and a clean tracked worktree. No related jobs
remained; the existing UID lock was released. Three historical result
directories remained untracked. The docs publication subsequently changes
Git HEAD; it does not change these historical computation pins.

## Reproducible command and safe repetition conditions

The complete original argv is `actual_collector_command` in the receipt
capsule; its separately retained original command JSON has the command digest
in the table. This is a collector replay over retained numerical evidence,
not an independent re-solve of all models or a fresh global REF evaluation.

A future repetition requires a reviewed source checkout at the exact admitted
052a157b commit, the same hashed inputs, available resources, no conflicting
validation job and a newly admitted source policy. Do not roll back the active
development branch to reproduce this report. A later docs/source HEAD requires
fresh admission even if the 116-file source digest is unchanged. Keep a copy
of the receipt capsule outside that source checkout.

The following executable recipe uses the exact argv and only substitutes
fresh output paths. It is documentation for a separately authorized run;
it was not executed while writing this report. Set
`C01_RECEIPT_CAPSULE` to an absolute path to the companion JSON and
`C01_NEW_ID` to a reviewed unused ID such as
`C01.final_collector.reproduction.001`.

```python
import json, os, pathlib, re, subprocess

root = pathlib.Path("/home/dy/HiRoute/project")
capsule = json.loads(pathlib.Path(os.environ["C01_RECEIPT_CAPSULE"]).read_text())
expected = capsule["execution"]["source_commit"]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
if head != expected:
    raise SystemExit("Source HEAD needs fresh admission; historical argv is not applicable")
for args in (["git", "diff", "--quiet"], ["git", "diff", "--cached", "--quiet"]):
    subprocess.run(args, cwd=root, check=True)

fresh_id = os.environ["C01_NEW_ID"]
if not re.fullmatch(r"C01\.final_collector\.reproduction\.[0-9]{3}", fresh_id):
    raise SystemExit("Invalid fresh output ID")
stem = root / "results/milestone_5_recorded_remote" / fresh_id
outputs = {
    "--attempt-dir": str(stem),
    "--runtime-return-output": str(stem) + ".runtime-return.json",
    "--collector-output": str(stem) + ".acceptance.json",
}
controller = pathlib.Path(str(stem) + ".controller-return.json")
stderr = pathlib.Path(str(stem) + ".controller-stderr.txt")
if list(stem.parent.glob(fresh_id + "*")):
    raise SystemExit("Output prefix already exists; preserve historical results")
argv = list(capsule["actual_collector_command"])
for flag, value in outputs.items():
    argv[argv.index(flag) + 1] = value
env = dict(os.environ)
env.update(capsule["environment"])
with controller.open("xb") as out, stderr.open("xb") as err:
    code = subprocess.run(argv, cwd=root, env=env, stdout=out, stderr=err).returncode
if code:
    raise SystemExit(code)
# Acceptance requires cold verification of the new actual runtime return,
# acceptance, evidence manifest and query/physical bindings, not exit 0 alone.
```

Run it only after the admission prerequisites above. The collector enforces its
recorded fixed resource plan. Reuse neither an occupied output prefix nor a
provisional attempt-local result as a successful return.

## Historical parity is separate evidence

The recovered `results/recovered_historical_reference/C01.json` is a 9,589-byte
historical `REF-global-potentials-v1` report with SHA-256
`d36b45e4f30e491c43dd498df3514d58f368caae4d22d146084bc93a72228bcb`.
Its full canonical key matches the sealed structural replay:
J=`75266265459119279523/5497558138880000`,
Q=`965083296054641/26843545600000`, H=1,
Pi=`[["4r:way/1150158290","C"]]`.
The comparison did not replay historical raw certificates. It is not a newly
executed independent REF solve. The old replay's recorded
`pending_missing_historical_reference` field is preserved as historical
metadata; the later supplemental key comparison and current collector do not
rewrite it.

Likewise, bounded legacy numeric parity and the checkpoint's synthetic tests
are historical populations at their own source versions. They do not close
the original A28/B64/C32 identities or certify present-source D0/FLAT results.
See the coverage audit for the smallest remaining validation plan.
