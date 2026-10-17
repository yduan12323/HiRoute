# OD02 search-extension DEV gate — 2026-10-17

**First real-graph integration of the three new-version arms produced independently
replayed feasible incumbents, after a separate verifier infrastructure recovery.**
All three exact searches reached their external 120-second phase limit. There is
no optimum, infeasibility proof, speedup, or overall D5/D2 completion claim.

The original seven-stage gate remains **FAILED_VERIFICATION**. Its ledger and
failed verifier receipt are preserved byte-for-byte. The separate recovery adds an
eighth attempted stage; it does not backfill the original gate to COMPLETED and
does not rerun numerical search.

## Frozen comparison and feasible results

Original execution source: `e00edaf6dcecbc9f71ae174862761ea13de6ea89`.
Manifest SHA256: `b719f5eb9414f1963d5517812630f9aeda7e32f2d089227f2601c79d18822cbd`.

OD02_energy_only_soc3_10, original N128 tree, a common freshly generated and
independently verified seed, Hmax33; full routing, search-only terminal-energy ON,
indexed ALT and two-source/1 GiB cache. Forward order only:
baseline → onward_only → coalescing_only. Same source and pinned environment.
Only one extension is enabled in either treatment. No historical timing pooling,
no holdout, no reverse-order run and no requirement for a positive result.

- Baseline: time_limit; independently accepted J =
  `89231180441089702031/3435973836800000`.
- Onward only: time_limit; independently accepted J =
  `22500600618780404673/858993459200000`.
- Coalescing only: time_limit; independently accepted J =
  `89231180441089702031/3435973836800000` after the separate verifier recovery.

All improve the same seed's feasible key. Baseline and coalescing have identical
complete `(J,Q,H,Π)` keys; onward's recorded J is worse than those two under this
one forward censored run. This is not a general ranking or performance result.
All complete keys, configurations, common seed identity and individual receipts
are preserved in `summary.json` and the evidence bundle.

## Failed verifier and explicit recovery chain

The original coalescing verifier failed after approximately 2.79 seconds with
`supervisor_exception: FileNotFoundError` while sampling a legitimately deleted
native temporary build directory `.build-n0lt_xa0`. Cleanup was verified. The
worker produced no stderr or accepted terminal verification in that attempt.

The fix uses descriptor-relative, no-follow output sampling. Only disappearing
non-root descendants are tolerated; root disappearance, links, special files,
entry limits, permission failures and directory-identity changes remain fail
closed. The fixed supervisor and deterministic race tests are archived as UTF-8
source in the evidence bundle. Normal and `-OO` supervisor/race regression each
passed 38 tests before recovery.

Fixed supervisor SHA256:
`54eb7ee71018b9a75694f23fddd3b5f941b83bbf56962fde6575ae624e91bf48`.

That external fixed supervisor governed the **unchanged original verifier argv**
in the original clean e00 source environment. The original manifest, common
artifact, arm-02 receipt and incumbent hashes were checked before and after.
Recovery provenance and its driver source are bundled. The separate verifier
returned SUCCESS with verified cleanup in **17.29474165799911 seconds**, freshly
replayed the complete coalescing incumbent key and retained `optimality_claim=false`.
The newer supervisor is an explicit infrastructure exception, not a silently
changed numerical-source manifest.

## Metrics and resource boundaries

All metrics are last-completed-checkpoint snapshots, not final 120-second counts.
Baseline and coalescing last reported layer-start depth2, around101.13s and102.15s;
onward last reported depth1 around1.94s. These unequal partial prefixes must not
be compared as full-run route work, throughput or speed. Setup and provider route
counters are separately retained; provider routing counters can include pre-search
seed work and therefore are not pure exact-search elapsed time.

At coalescing's last checkpoint, **672 calls accumulated 2128 input-piece and
1631 output-piece visits**. Repeated calls can count the same logical piece again.
These are neither unique-piece compression counts nor whole-search totals.
`source_cache_bytes` is an instantaneous gauge, not a cumulative lower bound.
Completed cumulative counters/maxima are partial lower bounds only.

Original denominator: 1 preparation + 3 searches + 3 verifiers =7 stages, including
all timeouts and the failed verifier. Original stage wall time sums to
517.3567500400059s; recovery adds a separately reported17.29474165799911s.
Original orchestration CPU was18.463300953s. These are not measured aggregate
worker CPU. Per-process CPU/address-space limits, sampled RSS/output sizes and
cleanup are in the receipts; no cgroup aggregate limit or cold-OS-cache claim.
Historical batches remain separate.

## Evidence and remaining work

Four files only: this README, `summary.json`, `evidence_index.json`, and
`evidence_bundle.json`. The bundle contains82 exact UTF-8 original files: manifest,
common seed/witness, all original stage ledgers/receipts/logs, durable incumbents,
partial metrics, native build receipts, recovered verification, provenance and
fixed-supervisor/driver source. Encode each `files` value as UTF-8 to recover its
original bytes; size and SHA256 must match the index. All82 entries passed an
actual persisted-bundle roundtrip. No graph inputs or native `.so` binaries are
included. This is self-contained evidence inspection, not a self-contained rerun
of the road experiment; reproduction also needs the frozen source/environment
and nine input artifacts named in the manifest.

Remaining, without claiming the whole assignment complete:

- D5: separately freeze and authorize reverse-order testing after this recovered
  integration admission; nothing launches automatically.
- D5: finish the applicable preregistered ablations/contrasts and resource
  reconciliation before any performance acceptance. No holdout is authorized here.
- D2: full live OPEN/frontier interruption-resume acceptance, certified lower-bound
  state and complete search/verifier accounting remain distinct from the durable
  feasible-incumbent recovery demonstrated here.
