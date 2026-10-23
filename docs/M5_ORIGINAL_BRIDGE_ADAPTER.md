# Original Shandong bridge adapter

The branch implements a fail-closed adapter for the original Shandong N8 REF and sequential FLAT/HIER stages. It has not been executed or accepted. The current disposition remains UNKNOWN / NOT_RUN_DEPENDENCY; no bridge claim or worker attempt was made.

## Separate installed layout

Do not use the general M5 tools wheel for this adapter: it contains an `experiments` tree that can shadow the trusted checkout. Build a dedicated bridge wheel and a setuptools editable namespace overlay instead:

```sh
python ci/build_m5e2e_bridge_tools.py --source-root /absolute/path/to/trusted/HiRoute --out /outside/bridge-artifacts
python -m pip --isolated install --no-deps /absolute/path/to/core.whl
python -m pip --isolated install --no-deps -e /outside/bridge-artifacts/original-source-overlay
python -m pip --isolated install --no-deps /outside/bridge-artifacts/wheelhouse/hiroute_m5e2e_original_bridge-0.1.0-py3-none-any.whl
cd /outside
/absolute/path/to/venv/bin/python -I -m ci.m5e2e_original_bridge --check-install --source-root /absolute/path/to/trusted/HiRoute --configuration /absolute/path/to/recovery-config.json --configuration-sha256 EXPECTED_SHA256
```

The builder requires clean, distinct bridge and trusted-source checkouts. The bridge wheel contains only the installed `ci` adapter and worker. The editable namespace overlay installs a `.pth`/finder entry in the venv and maps `experiments.*`, `validation.*`, and `scripts.*` to the exact trusted source checkout; isolated `-I` mode still uses that venv installation. Preflight imports the legacy physical/reference modules, `validation.reference5`, and the required FLAT/HIER helper modules, then verifies each loaded project module’s origin and source digest against the trusted closure (core packages must come from the installed venv). The bridge identity manifest binds the bridge revision, source revision, builder digest, and both wrapper file digests. The read-only `--check-install` path runs under the same isolated interpreter mode as the worker, verifies the recovery configuration and module root/revision, and prints INSTALL_READY or NOT_RUN_DEPENDENCY. It creates no claim and starts no numerical worker. Missing configuration fails closed. The builder resolves `--out` to an absolute path before creating the output tree, so the build subprocess changing cwd to its temporary stage cannot redirect `--outdir` or the subsequent wheel lookup.

This editable overlay is only a legacy-bridge compatibility layout. It is not the taskbook §11 non-editable clean A/B installation and cannot be cited as A/B installation evidence.

The regular launch must also use the installed adapter with `python -I -m ci.m5e2e_original_bridge`. Admission independently rechecks the installed wrapper identity, clean source checkout and revision, interpreter, trusted recovery closure, source root, manifest, common input, and master accounting before creating the single root-bound claim.

## Implemented execution policy

The parent derives a stable run identity from the root-validated continuation admission and bound parent waited-round receipt. A per-invocation freeze binds that identity to the installed wrapper, interpreter, trusted source identity/root, original inputs, accounting snapshot, run root, and method order.

The unchanged M6 root-freeze checks and mathematical worker implementation remain in use. FLAT/HIER are dispatched through the lower-level worker with a new taskbook-specific outer 300-second CPU/wall admission; the old `physical.worker` / `admit_method` 1200-second search admission is not called by this adapter. Only an early successful result proceeds to the fresh 120-second verifier. A 300-second outer limit remains incomplete and is never represented as the legacy 1200-second phase timeout. Terminal replay and complete-key comparison against authenticated REF are retained.

REF supervisor receipts are now settled in the master ledger before any worker-attestation read. TIMEOUT/FAILED results without an attestation retain the supervisor receipt digest, measured or conservative charge, cleanup state, and consumed claim; only a clean SUCCESS with a matching worker attestation can proceed to REF authentication and the two methods. CLI exit code 0 is reserved for BRIDGE_COMPLETE.

## Remaining fail-closed blockers

The available master accounting inventory does not have an independently verified authority proving that its source list is exhaustive. A caller-provided closed_world flag or empty unresolved list is insufficient. Some historical ledger ends lack receipt digests; the old ledger must remain immutable, and a sidecar must be derived from actual receipt files and verifiable fields. Missing receipts or an incomplete source inventory are not synthesized. Until those records and completeness source are verified, admission rejects before claim.

No reliable evidence currently establishes that the supplied original binding and full budget lineage are ready for this adapter. These are evidence gaps, not permission gaps. The code does not claim the bridge was run.

## Source and test status

The earlier numerical implementation identity `966912` and report-source identity `04cb5f` are separate from this bridge adapter. The newly built bridge wheel records its own bridge commit, trusted source commit, and artifact digests; none of these changes retroactively changes or validates the numerical source.

Unrun focused tests cover accounting closure and cleanup, caller-declared inventory rejection, evidence amount tampering, continuation-derived claim identity, wrapper drift, isolated worker input bindings, 300-second timeout classification, immutable invocation freeze, worker argument binding, incomplete REF status preservation, stale ledger snapshots, REF TIMEOUT settlement without attestation, missing install configuration, and BRIDGE_COMPLETE exit status. **None of these tests has been executed.** No numerical run, CI run, or holdout was performed.